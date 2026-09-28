"""Researcher app — a local HTTP server over the canonical tables.

    npm run app            # then open http://localhost:5174/

Deliberately stdlib-only. The dependency list of a research instrument is part
of its reproducibility story: every package added here is one a replication
attempt three years from now has to resolve, and a session browser does not
justify that cost. pyarrow is already required to read the tables at all.

Read-only about MEASUREMENTS. Nothing this server exposes can modify a session,
because the canonical tables are append-only and the thing that appends to them
is the pipeline. A UI that could edit a measurement would be a UI that could
quietly un-record a refusal.

AOI definitions are the one exception, and they are not measurements. An AOI is
a question someone decided to ask of the data afterwards, stored separately, and
versioned immutably — see aoi_store. The session data it is asked about stays
untouched either way.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import annotation_store  # noqa: E402
import aoi_store  # noqa: E402
import scoring_rules  # noqa: E402
import session_qc  # noqa: E402
import study_store  # noqa: E402
from aoi import AOI, AOISet, analyse  # noqa: E402
from fixations import classify  # noqa: E402
from retention import collect_sessions, expired, last_sweep, sweep_health  # noqa: E402
from study import content_hash as study_hash  # noqa: E402
from study import list_studies, load_study, verify_session_study  # noqa: E402
from store import (  # noqa: E402
    agreement_report,
    channel_series,
    expression_report,
    list_sessions,
    phases,
    scanpath,
    session_detail,
)

WEB_DIR = ROOT / "web" / "researcher"
#: The capture page's modules, served read-only at /src/ for the study builder.
CAPTURE_SRC = ROOT / "web" / "src"

#: Returned by a route that has already written the response itself.
SENT = object()


def _find_media(media_root: Path, session_id: str) -> Path | None:
    """Locate a session's recording under a bundle root.

    Matches on the session.json rather than on a directory name, because a
    bundle directory is named by whoever downloaded it and the session id is
    the only thing that is actually the session's.
    """
    for manifest in sorted(Path(media_root).glob("*/session.json")):
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get(
                    "session_id") != session_id:
                continue
        except (json.JSONDecodeError, OSError):
            continue
        for name in ("capture.webm", "capture.mp4"):
            candidate = manifest.parent / name
            if candidate.exists():
                return candidate
    return None
STUDIES_ROOT = ROOT / "studies"


def _study_check(meta: dict) -> dict:
    """Does this session's recorded protocol still match the file on disk?

    Reconstructs what `verify_session_study` expects from the sessions table
    rather than from session.json, because the table is what survives: a
    bundle directory is a working file and the canonical tables are the record.
    """
    recorded = {
        "study_id": meta.get("study_id"),
        "study_version": meta.get("study_version"),
        "study_content_hash": meta.get("study_content_hash"),
    }
    if not recorded["study_content_hash"]:
        recorded = None
    verdict = verify_session_study({"study_id": meta.get("study_id"),
                                    "study": recorded}, STUDIES_ROOT)
    return {"ok": verdict.ok, "reasons": list(verdict.reasons),
            "detail": verdict.detail}


def cohort_view(data_root: Path, study: dict, *, include_developer: bool,
                allow_mixed: bool) -> dict:
    """The cohort page's data: the funnel, mean epoch curves, heatmap grids.

    Read-only and computed from the same functions the CLI and the export use
    (cohort.py, stimulus_summary.py), so the page cannot show a different
    cohort from the one `npm run export` writes.
    """
    from cohort import EpochSpec, epochs, select
    from stimulus_summary import DEFAULT_HEATMAP_SIGMA_DEG, heatmap, per_stimulus_table

    from inference import participant_curves, pooled_mean, run_contrasts

    c = select(data_root, study, include_developer=include_developer, allow_mixed=allow_mixed)
    analysis = study.get("analysis") or {}
    epoch_sets, rows_by_set = [], {}
    for d in analysis.get("epochs", []):
        spec = EpochSpec.from_study(d)
        rows, refusals = epochs(data_root, c.included, spec)
        rows_by_set[spec.name] = rows
        # Mean of PARTICIPANT means: someone with ten epochs is one person, and
        # pooling epochs let whoever sat longest dominate the curve.
        per = {ch: participant_curves(rows, ch) for ch in spec.channels}
        epoch_sets.append({
            "name": spec.name, "event_type": spec.event_type,
            "n_epochs": len({(r["session_id"], r["epoch"]) for r in rows}),
            "n_participants": max((len(pc.by_participant) for pc in per.values()), default=0),
            "averaging": "mean of participant means",
            "refusals": len(refusals),
            "curves": {ch: pooled_mean(pc) for ch, pc in per.items() if pc.by_participant},
        })
    contrasts = run_contrasts(analysis, rows_by_set) if analysis.get("contrasts") else []
    sigma = analysis.get("heatmap_sigma_deg", DEFAULT_HEATMAP_SIGMA_DEG)
    heatmaps = []
    for t in study.get("tasks") or []:
        for it in t.get("items", []) if t.get("type") == "stimuli" else []:
            density, n, refused = heatmap(data_root, c.included, it["stimulus_id"], sigma_deg=sigma)
            # kind and src let the page lay the density over the picture itself,
            # as export.heatmap_png does: the grid is in the picture's own frame.
            heatmaps.append({"stimulus_id": it["stimulus_id"], "kind": it.get("kind"), "src": it.get("src"),
                             "participants": n,
                             "refused": len(refused), "sigma_deg": sigma,
                             "grid": None if density is None else density.round(6).tolist()})
    return {
        "study_id": c.study_id, "content_hash": c.content_hash, "analysis_hash": c.analysis_hash,
        "include_developer": include_developer, "allow_mixed": allow_mixed,
        "funnel": [{"step": f.label, "remaining": f.remaining,
                    "excluded": [{"session_id": s, "reason": r} for s, r in f.excluded]}
                   for f in c.funnel],
        "epochs": epoch_sets, "heatmaps": heatmaps, "contrasts": contrasts,
        "per_stimulus": per_stimulus_table(data_root, c.included, pad_deg=analysis.get("aoi_pad_deg")),
    }


def _opt_float(values):
    """First value of a query param as a float, or None if absent."""
    v = (values or [None])[0]
    return float(v) if v is not None else None


class Handler(SimpleHTTPRequestHandler):
    # HTTP/1.1, not the stdlib's HTTP/1.0 default. Chrome's media stack will
    # not stream ranged video over 1.0: the annotation page's <video> sat at
    # readyState 0 with nothing buffered for fifteen seconds while `curl`
    # fetched the same 118 MB file without complaint. Safe here because every
    # response this handler writes sets an accurate Content-Length, which is
    # what 1.1 keep-alive requires — `_json` and `_send_file` both do, and
    # SimpleHTTPRequestHandler does for static files.
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, data_root: Path, media_root: Path | None = None,
                 **kwargs):
        self.data_root = data_root
        self.media_root = media_root
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    # -- routing -----------------------------------------------------------

    def do_GET(self):  # noqa: N802  (stdlib naming)
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if path.startswith("/src/"):
            return self._capture_module(path)
        if path.startswith("/stimuli/"):
            return self._stimulus_file(path)
        if not path.startswith("/api/"):
            return super().do_GET()

        try:
            payload = self._route(path, query)
            if payload is SENT:
                return None
        except PermissionError as exc:
            # Distinct from 404 on purpose: "the participant said no" is a
            # different fact from "the file is missing", and a UI that showed
            # the same message for both would teach people to treat a refusal
            # as a glitch.
            return self._json({"error": "refused", "detail": str(exc)}, status=403)
        except FileNotFoundError as exc:
            return self._json({"error": "not_found", "detail": str(exc)}, status=404)
        except ValueError as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            # Surfaced rather than swallowed: a researcher staring at an empty
            # panel cannot tell a genuinely empty session from a broken query.
            return self._json({"error": "server_error", "detail": repr(exc)}, status=500)

        if payload is None:
            return self._json({"error": "not_found", "detail": path}, status=404)
        return self._json(payload)

    def _route(self, path: str, query: dict[str, list[str]]):
        parts = [p for p in path.split("/") if p]

        if parts == ["api", "sessions"]:
            return {"sessions": list_sessions(self.data_root)}

        if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
            d = session_detail(self.data_root, parts[2])
            # Composed here rather than in store.py: the read side answers
            # questions about the tables, and this is a question about a file
            # outside them that may have changed since.
            d["study_check"] = _study_check(d["meta"])
            return d

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "series":
            channel = (query.get("channel") or [None])[0]
            if not channel:
                raise ValueError("channel is required")
            return channel_series(
                self.data_root, parts[2], channel,
                source=(query.get("source") or [None])[0],
                max_points=int((query.get("max_points") or ["2000"])[0]),
            )

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "scanpath":
            def num(key):
                v = (query.get(key) or [None])[0]
                return float(v) if v is not None else None
            return {**scanpath(self.data_root, parts[2], num("start"), num("end")),
                    "phases": phases(self.data_root, parts[2])}

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "qc":
            # Is this session usable — every check with where its threshold came from.
            return session_qc.report(self.data_root, parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "media":
            return self._media(parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "export":
            return self._export(parts[2], query)

        if parts == ["api", "studies"]:
            return {"studies": list_studies(STUDIES_ROOT)}

        if len(parts) == 4 and parts[:2] == ["api", "studies"] and parts[3] == "cohort":
            flag = lambda k: (query.get(k) or ["0"])[0] == "1"  # noqa: E731
            return cohort_view(self.data_root, load_study(STUDIES_ROOT, parts[2]),
                               include_developer=flag("include_developer"),
                               allow_mixed=flag("allow_mixed"))

        if len(parts) == 3 and parts[:2] == ["api", "studies"]:
            # Returns the whole definition, not a summary: the point of opening
            # one is to read the disclosure a participant was shown.
            study = load_study(STUDIES_ROOT, parts[2])
            return {"study": study, "content_hash": study_hash(study)}

        if parts == ["api", "codebooks"]:
            return {"codebooks": annotation_store.list_codebooks(self.data_root)}

        if parts == ["api", "scoring-rules"]:
            return {"rules": scoring_rules.list_rules(
                self.data_root, (query.get("codebook") or [None])[0], (query.get("version") or [None])[0])}

        if len(parts) == 3 and parts[:2] == ["api", "scoring-rules"]:
            return scoring_rules.load_rule(self.data_root, parts[2], (query.get("version") or [""])[0])

        if len(parts) == 3 and parts[:2] == ["api", "codebooks"]:
            return annotation_store.load_codebook(
                self.data_root, parts[2],
                (query.get("version") or [None])[0])

        # /api/annotations/<codebook>/<session>/<rater>?version=<hash>
        #
        # One rater's OWN labels, for resuming their own work. There is no
        # route that serves a coder somebody else's labels: independence is
        # what every agreement coefficient rests on, and a coder who can see
        # the last one's choices is not a second observation.
        if len(parts) == 5 and parts[:2] == ["api", "annotations"]:
            _, _, codebook_id, sess, rater = parts
            return {"annotation": annotation_store.load_annotation(
                self.data_root, codebook_id=codebook_id,
                content_hash=(query.get("version") or [""])[0],
                session_id=sess, rater_id=rater)}

        if len(parts) == 3 and parts[:2] == ["api", "annotation-progress"]:
            # Who has coded this session and how far they got — no labels.
            return {"raters": annotation_store.raters_for(
                self.data_root,
                codebook_id=(query.get("codebook") or [""])[0],
                content_hash=(query.get("version") or [""])[0],
                session_id=parts[2])}

        if len(parts) == 3 and parts[:2] == ["api", "reliability"]:
            return self._reliability(parts[2], query)

        if parts == ["api", "aoi-sets"]:
            return {"sets": aoi_store.list_sets(self.data_root)}

        if len(parts) == 4 and parts[:2] == ["api", "aoi-sets"] and parts[3] == "history":
            return {"versions": aoi_store.history(self.data_root, parts[2])}

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "agreement":
            return agreement_report(self.data_root, parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "expressions":
            return expression_report(self.data_root, parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "aoi":
            return self._aoi_analysis(parts[2], query)

        return None

    def _capture_module(self, path: str):
        """The capture page's own study modules, read-only, for the study builder.

        The builder validates, hashes and previews a study with the SAME code
        the capture page runs (web/src/study.js and what it imports), so it
        cannot call a study valid that a participant's page would refuse, or
        preview a consent screen that differs from the real one. Plain module
        names only; nothing else under web/ is reachable this way.
        """
        name = path[len("/src/"):]
        if not re.fullmatch(r"[a-z_]+\.js", name) or not (CAPTURE_SRC / name).is_file():
            return self._json({"error": "not_found", "detail": path}, status=404)
        body = (CAPTURE_SRC / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return None

    def _stimulus_file(self, path: str):
        """A study's picture, read-only, for the thumbnails in the builder's journey.

        Pictures only: the journey marks a video with ▶ rather than loading it.
        """
        name = path[len("/stimuli/"):]
        kinds = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        ctype = kinds.get(Path(name).suffix.lower())
        file = STUDIES_ROOT / "stimuli" / name
        if (ctype is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", name)
                or ".." in name or not file.is_file()):
            return self._json({"error": "not_found", "detail": path}, status=404)
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None

    def do_POST(self):  # noqa: N802
        """The write paths, and there are only five.

        All five write CONFIGURATION or JUDGEMENT, never measurement. An AOI
        is a question asked of the data afterwards; a codebook is the same; an
        annotation is a person's answer; a study definition and its stimuli
        are the protocol, fixed once anyone is recorded under it
        (server/study_store.py). Nothing here can alter a row the pipeline
        wrote, because a UI that could edit a measurement could quietly
        un-record a refusal.
        """
        parsed = urlparse(self.path)

        if parsed.path == "/api/studies":
            return self._post_study()
        if parsed.path == "/api/stimuli":
            return self._post_stimulus(parse_qs(parsed.query))
        if parsed.path == "/api/codebooks":
            return self._post_codebook(parse_qs(parsed.query))
        if parsed.path == "/api/scoring-rules":
            return self._post_scoring_rule(parse_qs(parsed.query))
        if parsed.path == "/api/annotations":
            return self._post_annotation()
        if parsed.path != "/api/aoi-sets":
            return self._json({"error": "not_found", "detail": parsed.path}, status=404)

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            stimulus_id = body.get("stimulus_id")
            if stimulus_id is not None and not (
                    isinstance(stimulus_id, str) and stimulus_id
                    and all(c.isalnum() or c in "_-" for c in stimulus_id)):
                raise ValueError(f"stimulus_id must be a slug, got {stimulus_id!r}")
            aoi_set = AOISet(
                name=str(body["name"]), version="pending",
                aois=tuple(AOI(aoi_id=str(a["aoi_id"]), shape=a["shape"],
                               coords=tuple(float(c) for c in a["coords"]),
                               label=a.get("label"))
                           for a in body["aois"]),
                stimulus_id=stimulus_id,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

        return self._json(aoi_store.save(self.data_root, aoi_set))

    def _media(self, session_id: str):
        """Stream a session's recording, for the annotation page.

        Two refusals before a byte is served, and they are different things:

        - The consent tier did not retain media. In practice the file is
          already gone — `enforce_consent` deleted it after the engines ran —
          but the check runs on the tier rather than on the filesystem, because
          "the file happens to be missing" and "the participant said no" are
          not the same fact and should not produce the same message.
        - No media root was configured. The canonical tables do not record
          where a bundle lives, and inventing a path would be how a UI starts
          reading files nobody pointed it at.
        """
        detail = session_detail(self.data_root, session_id)
        tier = (detail.get("meta") or {}).get("consent_tier")

        # A session with NO recorded tier serves, matching `enforce_consent`:
        # there, a missing tier keeps the media, because acting on an absent
        # field is not recoverable. The pilots captured before tiered consent
        # existed are all in this state, and the recording is on the
        # researcher's own disk either way — this route is not a new
        # disclosure, it is a local file being read locally.
        if tier is not None and tier not in ("media_retained", "media_plus_transcript"):
            raise PermissionError(
                f"consent tier {tier!r} did not retain this recording")

        if self.media_root is None:
            raise FileNotFoundError(
                "no media root configured; start the app with --media <dir>")

        path = _find_media(self.media_root, session_id)
        if path is None:
            raise FileNotFoundError(f"no recording found for {session_id}")

        # Remuxed once, cached beside the source. A MediaRecorder WebM has no
        # duration and no cue index, and Chrome responds to that by waiting
        # forever at readyState 0 rather than failing — which looks like a slow
        # network and is not.
        from engine_contract import prepare_playback
        self._send_file(prepare_playback(path))
        return SENT

    def _send_file(self, path: Path):
        """Serve a file, honouring a Range request so the video can seek.

        Without Range the browser downloads the whole recording before it can
        show the first frame, and a coder stepping through forty moments would
        wait for it once per page load.
        """
        size = path.stat().st_size
        ctype = {".webm": "video/webm", ".mp4": "video/mp4",
                 ".wav": "audio/wav"}.get(path.suffix.lower(),
                                          "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200

        if rng and rng.startswith("bytes="):
            raw = rng.split("=", 1)[1].split(",")[0]
            lo, _, hi = raw.partition("-")
            if lo:
                start = int(lo)
                end = int(hi) if hi else size - 1
            elif hi:
                start = max(size - int(hi), 0)
            start = max(0, min(start, size - 1))
            end = max(start, min(end, size - 1))
            status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        with path.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _post_study(self):
        """Save a study from the builder. See server/study_store.py for the rules."""
        try:
            body = self._body()
            if not isinstance(body.get("study"), dict):
                raise ValueError("expected {\"study\": {...}}")
            return self._json(study_store.save_study(
                STUDIES_ROOT, self.data_root, body["study"],
                overwrite=bool(body.get("overwrite"))))
        except study_store.StoreRefused as exc:
            return self._json({"error": "refused", "detail": str(exc), **exc.extra},
                              status=exc.status)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

    def _post_stimulus(self, query):
        """Store an uploaded stimulus file; the body is the file's bytes."""
        name = (query.get("name") or [""])[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > study_store.MAX_STIMULUS_BYTES:
                self.close_connection = True
                raise study_store.StoreRefused(
                    413, f"stimuli are capped at {study_store.MAX_STIMULUS_BYTES // 2**20} MB")
            data = self.rfile.read(length)
            return self._json(study_store.save_stimulus(STUDIES_ROOT, name, data))
        except study_store.StoreRefused as exc:
            return self._json({"error": "refused", "detail": str(exc), **exc.extra},
                              status=exc.status)

    def _post_codebook(self, query):
        """Save a codebook version — or, with ?check=1, only say whether it would save.

        The check is how the codebook builder validates as you type: the rules
        live here once, in annotation_store, and the page never mirrors them.
        """
        try:
            body = self._body()
            if (query.get("check") or [""])[0] == "1":
                return self._json(annotation_store.check_codebook(body))
            return self._json(annotation_store.save_codebook(self.data_root, body))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

    def _post_annotation(self):
        try:
            body = self._body()
            return self._json(annotation_store.save_annotation(
                self.data_root,
                codebook_id=str(body["codebook_id"]),
                content_hash=str(body["content_hash"]),
                session_id=str(body["session_id"]),
                rater_id=str(body["rater_id"]),
                labels=body["labels"]))
        except (KeyError, TypeError, ValueError, FileNotFoundError,
                json.JSONDecodeError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

    def _reliability(self, session_id: str, query):
        """Inter-rater agreement, and an engine's score against the ceiling.

        Returns the refusal verbatim when there is not enough to compute one.
        A UI showing "—" where a refusal belongs teaches people the number is
        merely missing.
        """
        from evaluation import cohens_kappa, evaluate_against, reference_from

        codebook_id = (query.get("codebook") or [""])[0]
        version = (query.get("version") or [""])[0]
        use = (query.get("use") or ["raw"])[0]

        matrix = annotation_store.label_matrix(
            self.data_root, codebook_id=codebook_id,
            content_hash=version, session_id=session_id)

        out = {"matrix": {k: v for k, v in matrix.items() if k != "labels"},
               "n_raters": len(matrix["raters"])}

        ref = reference_from(matrix["labels"], use=use)
        if not ref:
            out["refusal"] = {"reason": ref.reason, "detail": ref.detail}
            return out

        out["reference"] = ref.as_dict()

        # Pairwise kappa between the first two raters, for the prevalence and
        # bias indices — the ceiling alone does not say whether a low number
        # is the task or the base rate.
        if len(matrix["labels"]) >= 2:
            k = cohens_kappa(matrix["labels"][0], matrix["labels"][1])
            out["kappa"] = k.as_dict() if k else {"refusal": k.reason}

        # The engine arm, only under a declared, hashed scoring rule
        # (server/scoring_rules.py) — inventing a mapping in the UI is how a
        # result stops being attributable. No rule named, no engine score.
        out["engine"] = None
        rule_ref = (query.get("rule") or [""])[0]
        if rule_ref:
            rule_id, _, version = rule_ref.partition("@")
            rule = scoring_rules.load_rule(self.data_root, rule_id, version)
            out["engine"] = scoring_rules.engine_arm(
                self.data_root, session_id, rule, matrix, use=use, origin=self._pts_origin(session_id))
        return out

    def _pts_origin(self, session_id: str):
        """Whether this session's recording, and the copy raters played, start at 0."""
        if self.media_root is None:
            return None
        path = _find_media(self.media_root, session_id)
        if path is None:
            return {"ok": False, "reasons": [f"no recording found for {session_id} under the media folder"]}
        from engine_contract import prepare_playback
        return scoring_rules.pts_origin(path, prepare_playback(path))

    def _post_scoring_rule(self, query):
        """Save a scoring rule version — or, with ?check=1, only say whether it would save."""
        try:
            body = self._body()
            if (query.get("check") or [""])[0] == "1":
                return self._json(scoring_rules.check_rule(self.data_root, body))
            return self._json(scoring_rules.save_rule(self.data_root, body))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

    def _aoi_analysis(self, session_id: str, query):
        """Run a saved AOI set against a session's fixations."""
        name = (query.get("set") or [None])[0]
        if not name:
            raise ValueError("set is required")
        pad_deg = float((query.get("pad_deg") or ["4.5"])[0])

        aoi_set = aoi_store.load(self.data_root, name,
                                 (query.get("version") or [None])[0])

        d = session_detail(self.data_root, session_id)
        m = d["meta"]
        if not m.get("px_per_mm") or not m.get("viewing_distance_mm"):
            return {"refusal": "no_geometry", "provenance": aoi_set.provenance()}

        import math
        dpp = math.degrees(math.atan2(1.0 / m["px_per_mm"], m["viewing_distance_mm"]))
        viewport = (float(m["screen_width_px"]), float(m["screen_height_px"]))

        sp = scanpath(self.data_root, session_id,
                      _opt_float(query.get("start")), _opt_float(query.get("end")))

        class _F:
            kind = "fixation"

            def __init__(self, f):
                self.x, self.y = f["x"], f["y"]
                self.onset_ts = f["t"]
                self.offset_ts = f["t"] + f["duration_ms"]

        result = analyse([_F(f) for f in sp["fixations"]], aoi_set,
                         pad_deg=pad_deg, degrees_per_px=dpp, viewport_px=viewport)

        return {
            "refusal": result.refusal,
            "hit_rate": result.hit_rate,
            "n_fixations": result.n_fixations,
            "n_hits": result.n_hits,
            "pad_deg": result.pad_deg,
            "pad_x": result.pad_x,
            "pad_y": result.pad_y,
            "provenance": result.provenance,
            "aois": [{"aoi_id": a.aoi_id, "shape": a.shape,
                      "coords": list(a.coords), "label": a.label}
                     for a in aoi_set.aois],
            "metrics": {k: vars(v) for k, v in result.metrics.items()},
        }

    def _export(self, session_id: str, query):
        """CSV of one channel. Streams as a download rather than JSON."""
        channel = (query.get("channel") or [None])[0]
        if not channel:
            raise ValueError("channel is required")
        series = channel_series(self.data_root, session_id, channel,
                                source=(query.get("source") or [None])[0],
                                max_points=10_000_000)

        lines = ["master_ts_ms,value"]
        lines += [f"{t},{v}" for t, v in series["points"]]
        body = "\n".join(lines).encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{session_id}_{channel.replace(".", "_")}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None  # already written

    # -- plumbing ----------------------------------------------------------

    def _json(self, payload, status: int = 200):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Bound to localhost and read-only, but a research machine may have other
        # local services; there is no reason for any of them to read this.
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """Refuse to start when something already holds the port.

    `HTTPServer` sets `allow_reuse_address = 1`, which on Windows means
    SO_REUSEADDR — and there that flag lets a SECOND process bind a port another
    process is already listening on. Both appear in `netstat` as LISTENING, the
    older one keeps receiving the requests, and the new one prints its startup
    banner and serves nothing. Restarting the app to pick up a code change then
    silently does nothing, which is exactly how a stale `store.py` kept serving
    an older response shape after the module had been fixed on disk.

    A bind failure is the honest outcome: it names the problem instead of
    presenting a running server that is not the one handling traffic.
    """

    allow_reuse_address = False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "out",
                    help="directory holding session_id=* folders")
    ap.add_argument("--port", type=int, default=5174)
    ap.add_argument("--studies", type=Path, default=None,
                    help="study definitions (default: studies/)")
    ap.add_argument("--media", type=Path, default=None,
                    help="directory holding capture bundles, so the annotation "
                         "page can play a session's recording back")
    args = ap.parse_args()

    data_root = args.data.resolve()
    media_root = args.media.resolve() if args.media else None
    if args.studies:
        global STUDIES_ROOT
        STUDIES_ROOT = args.studies.resolve()
    handler = partial(Handler, data_root=data_root, media_root=media_root)

    # Localhost only. This serves participant-derived measurements, and binding
    # it to every interface would publish them to the network by default.
    try:
        server = _ExclusiveHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"\n  port {args.port} is already in use: {exc}")
        print("  Another researcher app is still running and would keep serving")
        print("  the requests — including from the code you just changed.")
        print("  Stop it, or pass --port <n>.\n")
        return 1
    n = len(list_sessions(data_root))
    print(f"\n  researcher app   http://localhost:{args.port}/")
    print(f"  reading          {data_root}")
    print(f"  media            {media_root or 'not configured (--media)'}")
    print(f"  sessions found   {n}\n")
    # Deletion is an explicit command, never a side effect of starting the app,
    # but a session kept past what its participant was told must not go unseen.
    overdue = expired(collect_sessions(data_root, [media_root] if media_root else []),
                      datetime.now(timezone.utc))
    if overdue:
        print(f"  PAST RETENTION   {len(overdue)} session(s): "
              f"{', '.join(s.session_id for s in overdue)}")
        print("  Their participants were told this data would be deleted. Run:")
        print("    npm run retention -- --apply\n")
    # Whether the scheduled sweep is actually running — a task that silently
    # stopped looks exactly like one that is working until something expires.
    health = sweep_health(data_root, datetime.now(timezone.utc))
    last = last_sweep(data_root)
    print(f"  retention sweep  {'last ran ' + last['ran_utc'][:16] + ' UTC' if last else 'never recorded'}")
    if health:
        print(f"  WARNING          {health}\n")
    if n == 0:
        print("  No processed sessions. Run:")
        print("    npm run py -- server/process_bundle.py <bundle-dir> --out out/\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
