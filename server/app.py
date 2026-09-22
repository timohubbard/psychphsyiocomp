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
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import aoi_store  # noqa: E402
from aoi import AOI, AOISet, analyse  # noqa: E402
from fixations import classify  # noqa: E402
from study import content_hash as study_hash  # noqa: E402
from study import list_studies, load_study, verify_session_study  # noqa: E402
from store import (  # noqa: E402
    agreement_report,
    channel_series,
    list_sessions,
    phases,
    scanpath,
    session_detail,
)

WEB_DIR = ROOT / "web" / "researcher"
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


def _opt_float(values):
    """First value of a query param as a float, or None if absent."""
    v = (values or [None])[0]
    return float(v) if v is not None else None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_root: Path, **kwargs):
        self.data_root = data_root
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    # -- routing -----------------------------------------------------------

    def do_GET(self):  # noqa: N802  (stdlib naming)
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if not path.startswith("/api/"):
            return super().do_GET()

        try:
            payload = self._route(path, query)
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

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "export":
            return self._export(parts[2], query)

        if parts == ["api", "studies"]:
            return {"studies": list_studies(STUDIES_ROOT)}

        if len(parts) == 3 and parts[:2] == ["api", "studies"]:
            # Returns the whole definition, not a summary: the point of opening
            # one is to read the disclosure a participant was shown.
            study = load_study(STUDIES_ROOT, parts[2])
            return {"study": study, "content_hash": study_hash(study)}

        if parts == ["api", "aoi-sets"]:
            return {"sets": aoi_store.list_sets(self.data_root)}

        if len(parts) == 4 and parts[:2] == ["api", "aoi-sets"] and parts[3] == "history":
            return {"versions": aoi_store.history(self.data_root, parts[2])}

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "agreement":
            return agreement_report(self.data_root, parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "aoi":
            return self._aoi_analysis(parts[2], query)

        return None

    def do_POST(self):  # noqa: N802
        """The only write path, and only for AOI definitions."""
        parsed = urlparse(self.path)
        if parsed.path != "/api/aoi-sets":
            return self._json({"error": "not_found", "detail": parsed.path}, status=404)

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            aoi_set = AOISet(
                name=str(body["name"]), version="pending",
                aois=tuple(AOI(aoi_id=str(a["aoi_id"]), shape=a["shape"],
                               coords=tuple(float(c) for c in a["coords"]),
                               label=a.get("label"))
                           for a in body["aois"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._json({"error": "bad_request", "detail": str(exc)}, status=400)

        return self._json(aoi_store.save(self.data_root, aoi_set))

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
    args = ap.parse_args()

    data_root = args.data.resolve()
    handler = partial(Handler, data_root=data_root)

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
    print(f"  sessions found   {n}\n")
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
