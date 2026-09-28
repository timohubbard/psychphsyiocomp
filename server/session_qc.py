"""Is this session usable? One report, from what the pipeline already stored.

    npm run qc -- --session s_x          one session
    npm run qc -- --study stimulus-example   every session recorded under a study

Read-only. Every check says where its threshold came from, because a quality
report is only as trustworthy as its least-sourced number:

- `declared` — the study's own `analysis.exclusions`, evaluated exactly as
  `cohort.select` evaluates them. `fail` here means the cohort WILL drop this
  session; a rule nobody measured fails, as it does there.
- `default` — the engine's own manifest (`warn_below`/`warn_above`, sourced to
  §5.3 and §2.5 in each manifest) or the platform's gaze gate. These can only
  ever `warn`: a default is advice, and a study that wants it enforced
  declares it.
- `info` — reported with no threshold, because none has evidence behind it
  (blink rate, heart rate, clock uncertainty).

Whether the cohort includes the session is reported separately from the data
quality. A developer self-test is excluded from analysis by design, not because
its data is bad, so mixing the two would paint every self-test red.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import numpy as np  # noqa: E402

STUDIES_ROOT = ROOT / "studies"
ENGINES_ROOT = ROOT / "engines"

#: Worst first. `info` never makes a session look worse.
SEVERITY = {"fail": 4, "warn": 3, "not_measured": 2, "pass": 1, "info": 0}


@dataclass
class Check:
    group: str
    name: str
    status: str
    basis: str
    value: float | str | None = None
    unit: str | None = None
    source: str | None = None
    threshold: str | None = None
    why: str | None = None


def worst(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=SEVERITY.get, default="info")


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _manifest_quality(engine_id: str) -> dict[str, dict[str, Any]]:
    path = ENGINES_ROOT / engine_id / "engine.manifest.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {q["metric"]: q for q in (raw.get("outputs") or {}).get("quality", [])}


def unit_of(metric: str) -> str | None:
    """The unit any engine manifest gives this metric, for display."""
    for path in sorted(ENGINES_ROOT.glob("*/engine.manifest.json")):
        spec = _manifest_quality(path.parent.name).get(metric)
        if spec:
            return spec.get("unit")
    return None


def _fmt(v: float | None, unit: str | None) -> str:
    if v is None:
        return "—"
    if unit == "proportion":
        return f"{v:.0%}"
    return f"{v:.3g}"


def _by_metric_source(quality_rows) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = {}
    for r in quality_rows:
        v = _num(r["value"])
        if v is not None:
            out.setdefault((r["metric"], r["source"]), []).append(v)
    return out


def declared_checks(out: Path, row: dict[str, Any], study: dict[str, Any],
                    metric_sources: dict[str, set[str]]) -> list[Check]:
    from cohort import session_metric

    checks = []
    for rule in (study.get("analysis") or {}).get("exclusions", []):
        metric, lo, hi, src = rule["metric"], rule.get("min"), rule.get("max"), rule.get("source")
        bounds = " and ".join(p for p in (f">= {lo}" if lo is not None else "",
                                          f"<= {hi}" if hi is not None else "") if p)
        v = session_metric(out, row, metric, src)
        if v is None:
            checks.append(Check("Declared exclusions", metric, "fail", "declared", None, None, src, bounds,
                                "not measured — the cohort excludes a session whose criterion was never measured"))
            continue
        def passes(x):
            return (lo is None or x >= lo) and (hi is None or x <= hi)

        ok = passes(v)
        why = None if ok else "this session will be excluded from the cohort"
        status = "pass" if ok else "fail"
        pooled = sorted(metric_sources.get(metric, ())) if src is None else []
        if len(pooled) > 1:
            # Pooling only matters when it changes the answer: warn when reading
            # one engine rather than another would flip the verdict.
            each = {s: session_metric(out, row, metric, s) for s in pooled}
            verdicts = {passes(x) for x in each.values() if x is not None}
            note = (f"median pooled across {len(pooled)} sources; "
                    + ", ".join(f"{s.split('@')[0]}+{s.split('+')[-1]} {_fmt(x, unit_of(metric))}"
                                for s, x in each.items() if x is not None))
            if len(verdicts) > 1:
                note += " — the verdict depends on which is read: name a `source` in the rule"
                if ok:
                    status = "warn"
            why = f"{why}; {note}" if why else note
        checks.append(Check("Declared exclusions", metric, status, "declared", v, unit_of(metric), src,
                            bounds, why))
    return checks


def default_checks(by_ms: dict[tuple[str, str], list[float]]) -> list[Check]:
    """Each engine's own manifest thresholds, per source that wrote the metric."""
    checks = []
    for (metric, source), vals in sorted(by_ms.items()):
        spec = _manifest_quality(source.split("@", 1)[0]).get(metric)
        if not spec or (spec.get("warn_below") is None and spec.get("warn_above") is None):
            continue
        v = float(np.median(vals))
        lo, hi = spec.get("warn_below"), spec.get("warn_above")
        bad = (lo is not None and v < lo) or (hi is not None and v > hi)
        thr = " and ".join(p for p in (f">= {lo}" if lo is not None else "",
                                       f"<= {hi}" if hi is not None else "") if p)
        checks.append(Check("Engine quality", metric, "warn" if bad else "pass", "default", v,
                            spec.get("unit"), source, thr,
                            (spec.get("description") or "") + (" — below the engine's own threshold" if bad else "")))
    return checks


def report(out: str | Path, session_id: str, study: dict[str, Any] | None = None,
           *, gaze_gate: bool = True, studies_root: str | Path | None = None,
           known_cohort: dict[str, Any] | None = None) -> dict[str, Any]:
    """{session_id, checks, worst, cohort} for one session.

    `known_cohort` skips the cohort lookup when the caller already knows it — the
    export, whose sessions are by construction the included ones.
    """
    studies_root = Path(studies_root) if studies_root else STUDIES_ROOT
    from study import load_study, verify_session_study
    from tables import read_session

    out = Path(out)
    row = read_session(out, session_id, "sessions").to_pylist()[0]
    quality = read_session(out, session_id, "quality").to_pylist()
    runs = read_session(out, session_id, "runs").to_pylist()
    events = read_session(out, session_id, "events").to_pylist()
    mods = set(json.loads(row.get("study_modalities") or "[]"))
    tier = row.get("consent_tier")
    in_browser = tier == "features_in_browser"
    checks: list[Check] = []

    # --- protocol ---------------------------------------------------------
    verdict = verify_session_study({"study_id": row.get("study_id"), "study": {
        "study_id": row.get("study_id"), "study_version": row.get("study_version"),
        "study_content_hash": row.get("study_content_hash")} if row.get("study_content_hash") else None},
        studies_root)
    checks.append(Check("Protocol", "study file matches", "pass" if verdict.ok else "warn", "default",
                        row.get("study_content_hash"), None, None, None,
                        None if verdict.ok else ", ".join(verdict.reasons)
                        + " — sessions either side of an edit are not one study"))
    checks.append(Check("Protocol", "audience", "info", "info", row.get("audience") or "not recorded",
                        why="developer self-tests are left out of cohort analysis unless asked for"
                        if row.get("audience") != "participants" else None))
    checks.append(Check("Protocol", "consent tier", "info", "info", tier,
                        why="no recording exists; server engines cannot run" if in_browser else None))
    if study is None and verdict.ok:
        try:
            study = load_study(studies_root, row["study_id"])
        except (FileNotFoundError, ValueError):
            study = None

    # --- timing -----------------------------------------------------------
    unaligned = [r for r in runs if r.get("unaligned_reason")]
    if in_browser:
        checks.append(Check("Timing", "clock alignment", "info", "info", "no recording",
                            why="browser measurements are stamped on the master clock directly"))
    elif unaligned:
        checks.append(Check("Timing", "clock alignment", "warn", "default", f"{len(unaligned)} run(s) unaligned",
                            why=unaligned[0]["unaligned_reason"]))
    elif runs:
        checks.append(Check("Timing", "clock alignment", "pass", "default", f"{len(runs)} run(s) aligned"))
    unc = [_num(r.get("clock_uncertainty_ms")) for r in runs if _num(r.get("clock_uncertainty_ms")) is not None]
    fps = _num(row.get("achieved_fps"))
    if unc:
        frames = f" ({max(unc) * fps / 1000:.1f} frames)" if fps else ""
        checks.append(Check("Timing", "clock uncertainty", "info", "info", max(unc), "ms",
                            why=f"the clapper places the recording on the master clock to within this{frames}"))

    # --- setup ------------------------------------------------------------
    if row.get("geometry_refusal_reason") or not row.get("viewing_distance_mm"):
        checks.append(Check("Setup", "screen geometry", "warn" if "gaze" in mods else "info",
                            "default" if "gaze" in mods else "info", "refused",
                            why=(row.get("geometry_refusal_reason") or "not recorded")
                            + (" — gaze cannot be expressed in degrees" if "gaze" in mods else "")))
    else:
        checks.append(Check("Setup", "viewing distance", "pass", "default",
                            row["viewing_distance_mm"] / 10, "cm", None, None,
                            f"± {row['geometry_error_mm'] / 10:.1f} cm ({row.get('geometry_method')})"
                            if row.get("geometry_error_mm") is not None else row.get("geometry_method")))
    audio = row.get("applied_audio_constraints")
    if "voice" in mods:
        applied = json.loads(audio) if audio else None
        still = [k for k, v in (applied or {}).items() if v is True]
        checks.append(Check("Setup", "audio processing off", "warn" if still or applied is None else "pass",
                            "default", ", ".join(still) or ("no audio track" if applied is None else "all off"),
                            why="speech-content voice channels need echo cancellation, noise suppression "
                                "and gain control off" if still or applied is None else None))

    # --- engine quality (manifest defaults) ---------------------------------
    by_ms = _by_metric_source(quality)
    checks += default_checks(by_ms)

    # --- measures ---------------------------------------------------------
    if "gaze" in mods:
        if gaze_gate:
            from verify_gaze import held_out_gate
            g = held_out_gate(str(out), session_id)
            if g["status"] == "refused":
                checks.append(Check("Gaze", "held-out gate", "not_measured", "default", why=g["reason"]))
            else:
                checks.append(Check("Gaze", "held-out gate", "pass" if g["status"] == "pass" else "warn",
                                    "default", g["hit_rate"], "proportion", "gaze.ridge", f">= {g['need']:.0%} "
                                    f"at {g['pad_deg']}°",
                                    f"{g['hits']}/{g['checked']} held-out fixations on target; mean error "
                                    f"{g['mean_error_deg']:.2f}° (verify_gaze)"))
        for metric, unit in (("gaze_average_offset_deg", "deg"), ("gaze_onscreen_rate", "proportion")):
            vals = [v for (m, _), vs in by_ms.items() if m == metric for v in vs]
            if vals:
                checks.append(Check("Gaze", metric, "info", "info", float(np.median(vals)), unit))
    blink = {m: vs[0] for (m, s), vs in by_ms.items() if s.startswith("blinks.")}
    if blink:
        checks.append(Check("Blinks", "blink rate", "info", "info", blink.get("blink_rate_per_min"), "per min",
                            why="no threshold: rate depends on the task (reading and screens suppress it)"))
        checks.append(Check("Blinks", "eyes closed", "info", "info", blink.get("eyes_closed_fraction"),
                            "proportion", why="share of face-present time in a blink or closure (not PERCLOS)"))
    hr = {m: vs[0] for (m, s), vs in by_ms.items() if s.startswith("cardiac.")}
    if "hr_median_bpm" in hr:
        checks.append(Check("Heart rate", "median heart rate", "info", "info", hr["hr_median_bpm"], "bpm",
                            why="UNVALIDATED — camera heart rate has not been compared with a reference"))

    # --- completion -------------------------------------------------------
    types = [e["event_type"] for e in events]
    checks.append(Check("Completion", "recording stopped normally",
                        "pass" if "recording_stop" in types else "warn", "default",
                        why=None if "recording_stop" in types else "no recording_stop event — the session "
                        "may have been abandoned or the page closed"))
    if "gaze" in mods and study is not None:
        want = (study.get("calibration") or {}).get("n_points", 13)
        got = sum(t == "calibration_point_sampling" for t in types)
        checks.append(Check("Completion", "calibration points", "pass" if got >= want else "warn", "default",
                            got, None, None, f">= {want}", None if got >= want else "fewer than the study asks for"))
        got_v = sum(t == "validation_point_sampling" for t in types)
        checks.append(Check("Completion", "validation points", "pass" if got_v >= 5 else "warn", "default",
                            got_v, None, None, ">= 5", None if got_v >= 5 else "the gaze gate needs all five"))

    # --- declared ---------------------------------------------------------
    metric_sources: dict[str, set[str]] = {}
    for (m, s) in by_ms:
        metric_sources.setdefault(m, set()).add(s)
    if study is not None:
        checks += declared_checks(out, row, study, metric_sources)

    return {"session_id": session_id, "study_id": row.get("study_id"),
            "checks": [asdict(c) for c in checks],
            "worst": worst([c for c in checks]),
            "cohort": known_cohort or cohort_verdict(out, row, study)}


def cohort_verdict(out: Path, row: dict[str, Any], study: dict[str, Any] | None) -> dict[str, Any]:
    """Would `cohort.select`, with its defaults, include this session — and if not, why."""
    if study is None:
        return {"included": None, "reason": "study file unavailable or edited since this session"}
    from cohort import select
    c = select(out, study)
    if any(r["session_id"] == row["session_id"] for r in c.included):
        return {"included": True, "reason": None}
    for step in c.funnel:
        for sid, why in step.excluded:
            if sid == row["session_id"]:
                return {"included": False, "reason": why, "step": step.label}
    return {"included": False, "reason": "not recorded under this study"}


def rows_for_export(out: Path, sessions: list[dict[str, Any]], study: dict[str, Any],
                    analysis_hash: str, studies_root: str | Path | None = None) -> list[dict[str, Any]]:
    rows = []
    for s in sessions:
        for c in report(out, s["session_id"], study, studies_root=studies_root,
                        known_cohort={"included": True, "reason": None})["checks"]:
            rows.append({"session_id": s["session_id"], **c, "analysis_hash": analysis_hash})
    return rows


def main() -> int:
    from store import list_sessions
    from study import load_study

    ap = argparse.ArgumentParser(description="session quality report — writes nothing")
    ap.add_argument("--data", type=Path, default=ROOT / "out")
    ap.add_argument("--session", action="append", default=None)
    ap.add_argument("--study", default=None)
    args = ap.parse_args()
    sessions = list_sessions(args.data)
    if args.session:
        ids = args.session
    elif args.study:
        ids = [s["session_id"] for s in sessions if s.get("study_id") == args.study]
    else:
        ids = [s["session_id"] for s in sessions]
    study = load_study(STUDIES_ROOT, args.study) if args.study else None
    mark = {"pass": "ok  ", "warn": "WARN", "fail": "FAIL", "not_measured": "n/m ", "info": "    "}
    for sid in ids:
        r = report(args.data, sid, study)
        c = r["cohort"]
        verdict = ("included" if c["included"] else f"excluded — {c['reason']}") if c["included"] is not None \
            else c["reason"]
        print(f"\n  {sid}  ({r['study_id']})   worst: {r['worst'].upper()}   cohort: {verdict}")
        group = None
        for ch in r["checks"]:
            if ch["group"] != group:
                group = ch["group"]
                print(f"   {group}")
            val = ch["value"] if isinstance(ch["value"], str) else (
                "" if ch["value"] is None else _fmt(ch["value"], ch["unit"]))
            src = f"  [{ch['source'].split('+')[0]}{'+' + ch['source'].split('+')[1] if '+' in ch['source'] else ''}]" \
                if ch["source"] else ""
            thr = f"  (need {ch['threshold']}, {ch['basis']})" if ch["threshold"] else ""
            unit = f" {ch['unit']}" if ch["unit"] not in (None, "proportion") else ""
            print(f"     {mark[ch['status']]} {ch['name']:28} {val}{unit}{thr}{src}")
            if ch["why"] and ch["status"] in ("warn", "fail", "not_measured"):
                print(f"          {ch['why']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
