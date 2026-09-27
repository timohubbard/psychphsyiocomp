"""Receive session bundles from the capture page, instead of a participant's Downloads.

"Browser-first remote collection" used to end with a participant saving three
files and somehow getting them to the researcher. This is the receiving end:

    PUT  /ingest/<session_id>/<file>     one bundle file, streamed to disk
    POST /ingest/<session_id>/complete   seal the upload
    GET  /ingest/health                  is uploading available at all

It binds to localhost and demands a bearer token on every request. The capture
server (`serve.mjs --ingest`) proxies /ingest/* to it and adds the token
itself, so the token never reaches a browser. The rules, each a refusal:

- **session.json first.** It carries the consent tier, and the tier decides
  what may follow: under `features_in_browser` a recording must never arrive,
  and one that tries is refused (403) rather than stored and deleted later.
- **Only the bundle's own file names**, each with a size cap (413 above it),
  and a session id that matches the manifest — no path from the request ever
  reaches the filesystem unchecked.
- **A withdrawn or expired session is refused (410 Gone)**, with
  retention.refusal_for, the check processing uses: a participant who
  withdrew must not reappear because a tab was left open.
- **Written to .part, then renamed**, so a half-received file is never taken
  for a whole one; **sealed once** — after `complete`, nothing more (409).
  `.upload.json` records the state, and process_bundle refuses a folder whose
  upload was never completed.

What it does not do: authenticate the participant. Anyone who can load the
capture page can upload a bundle, which is true of any public study link;
the caps, the one-shot seal and the refusals bound what they can do.

    INGEST_TOKEN=<secret> npm run ingest            (default port 5175)
    INGEST_TOKEN=<secret> npm run serve -- --ingest (in another terminal)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from retention import refusal_for  # noqa: E402

#: The bundle's files, and the most each may be. A 10-minute 720p capture at
#: the recorder's 4 Mbps is ~300 MB; the cap leaves room without being open.
CAPS = {
    "session.json": 20 * 2**20,
    "browser_chunks.json": 400 * 2**20,
    "identifiers.json": 64 * 2**10,
    "capture.webm": 2 * 2**30,
    "capture.mp4": 2 * 2**30,
}
MEDIA = {"capture.webm", "capture.mp4"}
STATUS = ".upload.json"
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_CHUNK = 1 << 20


class IngestError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


def _status(folder: Path) -> dict[str, Any]:
    path = folder / STATUS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "complete": False, "files": {}}


def _write_status(folder: Path, status: dict[str, Any]) -> None:
    tmp = folder / (STATUS + ".part")
    tmp.write_text(json.dumps(status, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, folder / STATUS)


def receive_file(inbox: Path, out: Path, session_id: str, name: str,
                 stream, length: int) -> dict[str, Any]:
    """Store one file of one session's bundle. Raises IngestError to refuse."""
    if not _SESSION_ID.match(session_id):
        raise IngestError(400, "not a session id")
    if name not in CAPS:
        raise IngestError(400, f"{name!r} is not a bundle file")
    if length < 0:
        raise IngestError(411, "Content-Length is required")
    if length > CAPS[name]:
        raise IngestError(413, f"{name} is {length} bytes; the cap is {CAPS[name]}")

    folder = inbox / session_id
    status = _status(folder)
    if status["complete"]:
        raise IngestError(409, "this upload is already complete")
    if name != "session.json" and not (folder / "session.json").exists():
        raise IngestError(409, "session.json must be uploaded first — it decides what may follow")

    if name != "session.json":
        manifest = json.loads((folder / "session.json").read_text(encoding="utf-8"))
        if name in MEDIA and (manifest.get("consent") or {}).get("tier") == "features_in_browser":
            raise IngestError(403, "the participant chose features_in_browser: "
                                   "their recording must never leave their device")

    folder.mkdir(parents=True, exist_ok=True)
    part = folder / (name + ".part")
    digest = hashlib.sha256()
    received = 0
    with open(part, "wb") as fh:
        while received < length:
            block = stream.read(min(_CHUNK, length - received))
            if not block:
                break
            fh.write(block)
            digest.update(block)
            received += len(block)
    if received != length:
        _discard(part, folder)
        raise IngestError(400, f"body ended after {received} of {length} bytes")

    if name == "session.json":
        try:
            manifest = json.loads(part.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _discard(part, folder)
            raise IngestError(400, "session.json is not JSON") from None
        if manifest.get("session_id") != session_id:
            _discard(part, folder)
            raise IngestError(400, "session.json names a different session")
        refusal = refusal_for(out, session_id, manifest)
        if refusal:
            _discard(part, folder)
            raise IngestError(410, refusal)

    os.replace(part, folder / name)
    status["files"][name] = {"bytes": received, "sha256": digest.hexdigest()}
    status["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _write_status(folder, status)
    return {"stored": name, "bytes": received}


def _discard(part: Path, folder: Path) -> None:
    """Drop a refused file, and its session folder if the refusal left it empty.

    Every refusal path, not just one: a folder left behind by a rejected upload
    is litter the retention sweep then has to reason about, and repeated junk
    requests would fill the inbox with it.
    """
    part.unlink(missing_ok=True)
    try:
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass


def complete(inbox: Path, session_id: str) -> dict[str, Any]:
    """Seal an upload. Needs session.json and browser_chunks.json at least."""
    if not _SESSION_ID.match(session_id):
        raise IngestError(400, "not a session id")
    folder = inbox / session_id
    status = _status(folder)
    if status["complete"]:
        raise IngestError(409, "this upload is already complete")
    missing = [f for f in ("session.json", "browser_chunks.json") if f not in status["files"]]
    if missing:
        raise IngestError(409, f"cannot complete without {', '.join(missing)}")
    status["complete"] = True
    status["completed_utc"] = datetime.now(timezone.utc).isoformat()
    _write_status(folder, status)
    return {"complete": True, "files": sorted(status["files"])}


def upload_refusal(bundle_dir: str | Path) -> str | None:
    """Why process_bundle must not process this folder yet, or None."""
    path = Path(bundle_dir) / STATUS
    if path.exists() and not _status(Path(bundle_dir))["complete"]:
        return ("this bundle's upload was never completed — some files may be "
                "missing or partial. Wait for it, or ask the participant to upload again.")
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, inbox: Path, out: Path, token: str, **kw):
        self.inbox, self.out, self.token = inbox, out, token
        super().__init__(*args, **kw)

    def log_message(self, fmt, *args):  # quieter: one line per request, no bodies
        sys.stderr.write(f"  ingest {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}\n")

    def _reply(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        got = self.headers.get("Authorization", "")
        return hmac.compare_digest(got.encode(), f"Bearer {self.token}".encode())

    def _route(self) -> list[str] | None:
        parts = self.path.split("?")[0].strip("/").split("/")
        return parts[1:] if parts and parts[0] == "ingest" else None

    def do_GET(self):  # noqa: N802
        if not self._authorised():
            return self._reply(401, {"error": "unauthorised"})
        if self._route() == ["health"]:
            return self._reply(200, {"ok": True})
        return self._reply(404, {"error": "not_found"})

    def do_PUT(self):  # noqa: N802
        if not self._authorised():
            return self._reply(401, {"error": "unauthorised"})
        route = self._route()
        if not route or len(route) != 2:
            return self._reply(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            result = receive_file(self.inbox, self.out, route[0], route[1], self.rfile, length)
        except IngestError as exc:
            self.close_connection = True   # the unread body must not be parsed as a request
            return self._reply(exc.status, {"error": str(exc)})
        return self._reply(200, result)

    def do_POST(self):  # noqa: N802
        if not self._authorised():
            return self._reply(401, {"error": "unauthorised"})
        route = self._route()
        if not route or len(route) != 2 or route[1] != "complete":
            return self._reply(404, {"error": "not_found"})
        try:
            return self._reply(200, complete(self.inbox, route[0]))
        except IngestError as exc:
            return self._reply(exc.status, {"error": str(exc)})


def make_server(inbox: Path, out: Path, token: str, port: int) -> ThreadingHTTPServer:
    inbox.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer(("127.0.0.1", port),
                               partial(Handler, inbox=inbox, out=out, token=token))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--inbox", type=Path, default=ROOT / "tempdata" / "inbox")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--port", type=int, default=int(os.environ.get("INGEST_PORT", 5175)))
    args = ap.parse_args(argv)
    token = os.environ.get("INGEST_TOKEN", "")
    if len(token) < 16:
        # No default token: a guessable one would be an open upload endpoint.
        print("  INGEST_TOKEN must be set to a secret of at least 16 characters.")
        return 1
    server = make_server(args.inbox, args.out, token, args.port)
    print(f"\n  ingest          http://127.0.0.1:{args.port}/ingest/  (localhost only)")
    print(f"  inbox           {args.inbox}")
    print("  capture page    run `npm run serve -- --ingest` with the same INGEST_TOKEN\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
