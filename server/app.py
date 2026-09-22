"""Researcher app — a local HTTP server over the canonical tables.

    npm run app            # then open http://localhost:5174/

Deliberately stdlib-only. The dependency list of a research instrument is part
of its reproducibility story: every package added here is one a replication
attempt three years from now has to resolve, and a session browser does not
justify that cost. pyarrow is already required to read the tables at all.

Read-only by design. Nothing this server exposes can modify a session, because
the canonical tables are append-only and the thing that appends to them is the
pipeline. A UI that could edit measurements would be a UI that could quietly
un-record a refusal.
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

from store import channel_series, list_sessions, session_detail  # noqa: E402

WEB_DIR = ROOT / "web" / "researcher"


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
            return session_detail(self.data_root, parts[2])

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "series":
            channel = (query.get("channel") or [None])[0]
            if not channel:
                raise ValueError("channel is required")
            return channel_series(
                self.data_root, parts[2], channel,
                source=(query.get("source") or [None])[0],
                max_points=int((query.get("max_points") or ["2000"])[0]),
            )

        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "export":
            return self._export(parts[2], query)

        return None

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
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
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
