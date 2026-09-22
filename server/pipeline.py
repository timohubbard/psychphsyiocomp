"""Session pipeline — media in, canonical tables out.

Ties together the three pieces that must not know about each other:

    engines          pure functions, native timestamps only
    alignment        the one place clocks are reconciled
    tables           the canonical append-only output

The ordering matters and is deliberate. ``probe()`` runs before ``run()``, and
an ineligible engine still produces a ``runs`` row explaining why — never a
silent skip. That is how REPORT.md's traps become machine-enforced rather than
tribal knowledge.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alignment import Anchor, ClockRegistry, detect_clapper_in_luma
from engine_contract import Engine, MediaDescriptor
from tables import CanonicalWriter, SessionContext

#: The browser's monotonic clock is the master. Everything else is expressed
#: relative to it, because that is the clock the stimulus events are stamped
#: against and stimulus-relative timing is what the science depends on.
MASTER_CLOCK = "performance.now"


@dataclass
class SessionBundle:
    """What the capture page uploads.

    ``events`` are stamped against the master clock by the browser itself, so
    they need no alignment — they *define* it.
    """

    session_id: str
    participant_id: str
    study_id: str
    video_path: Path | None = None
    audio_path: Path | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    #: Signals the browser produced live, already on the master clock.
    browser_chunks: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dir(cls, path: str | Path) -> SessionBundle:
        """Load a bundle written by the capture page."""
        p = Path(path)
        manifest_path = p / "session.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"no session.json in {p}")
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))

        video = p / "capture.webm"
        if not video.exists():
            video = p / "capture.mp4"

        # The browser-live source travels beside the manifest. Loading it here is
        # what makes the M0 criterion reachable from a REAL capture: without it a
        # downloaded bundle silently yields one source instead of two, and the
        # gate only ever passed because verify_m0 builds its browser chunk in
        # memory. The capture page has always written this file; nothing read it.
        chunks_path = p / "browser_chunks.json"
        browser_chunks: list[Any] = []
        if chunks_path.exists():
            browser_chunks = _load_browser_chunks(chunks_path)

        return cls(
            session_id=meta["session_id"],
            participant_id=meta["participant_id"],
            study_id=meta.get("study_id", "default"),
            video_path=video if video.exists() else None,
            events=meta.get("events", []),
            browser_chunks=browser_chunks,
            metadata=meta,
        )

    def sync_marker_ts(self) -> float | None:
        """When the capture page drew the sync flash, on the master clock."""
        for e in self.events:
            if e.get("event_type") == "sync_clapper":
                return float(e["onset_native_ts"])
        return None


def _load_browser_chunks(path: Path) -> list[Any]:
    """Deserialise the capture page's live-engine output into contract types.

    Rows are rebuilt as ``SignalRow``/``QualityRow`` rather than passed through
    as dicts so that a shape change in the browser fails here, loudly, at the
    boundary — instead of surfacing later as a missing Parquet column.

    Unknown keys are ignored deliberately: the browser may add fields ahead of
    the server learning about them, and that should not break ingestion of the
    fields both sides already agree on.
    """
    from engine_contract import Chunk, QualityRow, SignalRow

    raw = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []

    for c in raw:
        signals = tuple(
            SignalRow(
                stream=s["stream"],
                channel=s["channel"],
                native_clock_id=s["native_clock_id"],
                native_ts=float(s["native_ts"]),
                value=s["value"],
                reliability_tier=s["reliability_tier"],
            )
            for s in c.get("signals", ())
        )
        quality = tuple(
            QualityRow(
                stream=q["stream"],
                metric=q["metric"],
                window_start_native_ts=float(q["window_start_native_ts"]),
                window_end_native_ts=float(q["window_end_native_ts"]),
                value=float(q["value"]),
            )
            for q in c.get("quality", ())
        )
        if signals or quality:
            chunks.append(Chunk(signals=signals, quality=quality))

    return chunks


def build_registry(
    bundle: SessionBundle,
    *,
    video_luma: list[tuple[float, float]] | None = None,
) -> ClockRegistry:
    """Establish clock relationships for a session.

    The sync clapper is the anchor: the capture page flashes the screen at a
    known ``performance.now()``, and that flash shows up as a luminance spike in
    the decoded video. Matching the two gives a *measured* offset.

    When either side is missing, no anchor is added — and the video stream then
    stays unaligned, with the reason recorded. §3.3 is explicit that AV sync is
    a ceiling rather than a bug to fix, so an honest NULL beats a confident
    guess.
    """
    reg = ClockRegistry(master_clock_id=MASTER_CLOCK)

    marker_master_ts = bundle.sync_marker_ts()
    if marker_master_ts is None or not video_luma:
        return reg

    detected = detect_clapper_in_luma(video_luma)
    if detected is None:
        return reg

    video_ts, uncertainty = detected
    reg.add_anchor(
        Anchor(
            clock_a="video_pts", ts_a=video_ts,
            clock_b=MASTER_CLOCK, ts_b=marker_master_ts,
            uncertainty_ms=uncertainty, label="sync_clapper",
        )
    )
    return reg


def process_session(
    bundle: SessionBundle,
    engines: list[tuple[Engine, dict[str, Any]]],
    out_root: str | Path,
    *,
    video_luma: list[tuple[float, float]] | None = None,
    extra_stages: list[Any] | None = None,
) -> dict[str, Any]:
    """Run engines over a session bundle and write the canonical tables.

    :returns: a summary dict for logging and for the verification notebook
    """
    ctx = SessionContext(
        session_id=bundle.session_id,
        participant_id=bundle.participant_id,
        study_id=bundle.study_id,
    )
    writer = CanonicalWriter(out_root, ctx)
    registry = build_registry(bundle, video_luma=video_luma)

    # Capture-side session facts, including the virtual-chinrest geometry.
    # Written before any engine runs, because a session whose geometry was
    # refused is still a session worth processing — every channel except the
    # degrees-of-visual-angle conversion is unaffected by it.
    session_row = writer.set_session_metadata(bundle.metadata)

    summary: dict[str, Any] = {
        "session_id": bundle.session_id,
        "runs": [],
        "sources": set(),
        "geometry_method": session_row["geometry_method"],
        "degrees_per_px": writer.degrees_per_px(),
    }

    # Browser-live output is already on the master clock.
    if bundle.browser_chunks:
        master_solution = registry.solve(MASTER_CLOCK)
        source = bundle.metadata.get(
            "browser_source", "face.mediapipe_blendshapes@0.1.0+browser-live"
        )
        writer.add_chunks(
            bundle.browser_chunks, source=source,
            params=bundle.metadata.get("browser_params", {}),
            solution=master_solution,
        )
        summary["sources"].add(source)

    # Stimulus events, stamped by the browser against the master clock.
    if bundle.events:
        from engine_contract import Chunk, EventRow

        rows = tuple(
            EventRow(
                event_type=e["event_type"],
                native_clock_id=MASTER_CLOCK,
                onset_native_ts=float(e["onset_native_ts"]),
                offset_native_ts=(
                    float(e["offset_native_ts"])
                    if e.get("offset_native_ts") is not None else None
                ),
                stimulus_id=e.get("stimulus_id"),
                metadata=e.get("metadata"),
            )
            for e in bundle.events
        )
        writer.add_chunks(
            [Chunk(events=rows)], source="runner@0.1.0",
            params={}, solution=registry.solve(MASTER_CLOCK),
        )

    # Server-side engines over the stored media.
    for engine, params in engines:
        if bundle.video_path is None:
            continue

        # From the contract, not from whichever module happens to be named
        # `engine` on sys.path — media probing is shared infrastructure and
        # every engine must be handed an identically-built descriptor.
        from engine_contract.media import describe_video

        media: MediaDescriptor = describe_video(bundle.video_path)

        started = datetime.now(timezone.utc)
        eligibility = engine.probe(media)
        source = getattr(engine, "source", engine.manifest.source)
        solution = registry.solve("video_pts")
        run_id = str(uuid.uuid4())

        if eligibility.eligible:
            n = writer.add_chunks(
                engine.run(media, params), source=source,
                params=params, solution=solution,
            )
            status = "ok"
            summary["sources"].add(source)
        else:
            # Recorded, not skipped. The absence of signal rows is itself
            # information, and the reason has to survive to analysis time.
            n = 0
            status = "ineligible"

        writer.add_run(
            run_id=run_id, manifest=engine.manifest, source=source, params=params,
            eligibility=eligibility, solution=solution,
            media_sha256=media.sha256, started=started, status=status,
        )
        summary["runs"].append({
            "run_id": run_id, "source": source, "status": status,
            "rows": n, "aligned": solution.aligned,
            "unaligned_reason": solution.unaligned_reason,
        })

    # Stages that are not engines: they need the master clock, which engines
    # are forbidden to know about. The gaze estimator is the first of these.
    for stage in (extra_stages or []):
        summary["gaze"] = stage(writer, bundle, registry.solve("video_pts"))

    paths = writer.close()
    summary["sources"] = sorted(summary["sources"])
    summary["signal_rows"] = writer.signal_count
    summary["paths"] = {k: str(v) for k, v in paths.items()}
    return summary
