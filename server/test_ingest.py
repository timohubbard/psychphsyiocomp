"""The upload endpoint, over real HTTP: what it takes, and every way it refuses."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

import ingest
import retention

TOKEN = "t" * 32


@pytest.fixture
def server(tmp_path):
    inbox, out = tmp_path / "inbox", tmp_path / "out"
    srv = ingest.make_server(inbox, out, TOKEN, 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", inbox, out
    srv.shutdown()
    srv.server_close()


def call(base, method, path, body=b"", token=TOKEN):
    req = urllib.request.Request(base + path, data=body if method != "GET" else None,
                                 method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def manifest(sid="s1", tier="features_only", days=30):
    return json.dumps({"session_id": sid, "participant_id": "p_pending", "study_id": "d",
                       "created_utc": datetime.now(timezone.utc).isoformat(),
                       "consent": {"tier": tier, "retentionDays": days}}).encode()


def test_a_whole_bundle_uploads_and_seals(server):
    base, inbox, _ = server
    assert call(base, "PUT", "/ingest/s1/session.json", manifest())[0] == 200
    assert call(base, "PUT", "/ingest/s1/browser_chunks.json", b"[]")[0] == 200
    assert call(base, "PUT", "/ingest/s1/capture.webm", b"\x1aE\xdf\xa3video")[0] == 200
    status, body = call(base, "POST", "/ingest/s1/complete")
    assert status == 200 and body["files"] == ["browser_chunks.json", "capture.webm", "session.json"]
    assert (inbox / "s1" / "capture.webm").read_bytes() == b"\x1aE\xdf\xa3video"
    assert not list((inbox / "s1").glob("*.part"))
    assert ingest.upload_refusal(inbox / "s1") is None


def test_no_token_or_a_wrong_one_is_refused(server):
    base, inbox, _ = server
    assert call(base, "PUT", "/ingest/s1/session.json", manifest(), token=None)[0] == 401
    assert call(base, "PUT", "/ingest/s1/session.json", manifest(), token="x" * 32)[0] == 401
    assert not (inbox / "s1").exists()


def test_session_json_must_come_first(server):
    base, *_ = server
    status, body = call(base, "PUT", "/ingest/s1/capture.webm", b"video")
    assert status == 409 and "session.json must be uploaded first" in body["error"]


def test_only_bundle_files_and_no_paths(server):
    base, inbox, _ = server
    for path in ("/ingest/s1/notes.txt", "/ingest/s1/..%2Fescape.json",
                 "/ingest/..%2F..%2Fx/session.json"):
        assert call(base, "PUT", path, manifest())[0] in (400, 404), path
    assert not any(p.name == "escape.json" for p in inbox.parent.rglob("*"))


def test_a_manifest_for_another_session_is_refused(server):
    base, *_ = server
    status, body = call(base, "PUT", "/ingest/s1/session.json", manifest(sid="s2"))
    assert status == 400 and "different session" in body["error"]


def test_oversized_files_are_refused(server, monkeypatch):
    base, *_ = server
    monkeypatch.setitem(ingest.CAPS, "session.json", 10)
    assert call(base, "PUT", "/ingest/s1/session.json", manifest())[0] == 413


def test_a_recording_under_features_in_browser_is_refused(server):
    base, inbox, _ = server
    call(base, "PUT", "/ingest/s1/session.json", manifest(tier="features_in_browser"))
    status, body = call(base, "PUT", "/ingest/s1/capture.webm", b"video")
    assert status == 403 and "never leave their device" in body["error"]
    assert not (inbox / "s1" / "capture.webm").exists()


def test_a_withdrawn_session_is_gone(server):
    base, inbox, out = server
    out.mkdir()
    (out / retention.TOMBSTONES).write_text(json.dumps({
        "session_id": "s1", "reason": "withdrawn", "deleted_utc": "2026-09-01T00:00:00+00:00"}) + "\n")
    status, body = call(base, "PUT", "/ingest/s1/session.json", manifest())
    assert status == 410 and "leftover copy" in body["error"]
    assert not (inbox / "s1").exists()


def test_an_expired_session_is_gone(server):
    base, *_ = server
    old = json.dumps({"session_id": "s1", "participant_id": "a", "study_id": "d",
                      "created_utc": "2020-01-01T00:00:00+00:00",
                      "consent": {"tier": "features_only", "retentionDays": 30}}).encode()
    assert call(base, "PUT", "/ingest/s1/session.json", old)[0] == 410


def test_sealed_is_sealed(server):
    base, *_ = server
    call(base, "PUT", "/ingest/s1/session.json", manifest())
    call(base, "PUT", "/ingest/s1/browser_chunks.json", b"[]")
    call(base, "POST", "/ingest/s1/complete")
    assert call(base, "PUT", "/ingest/s1/capture.webm", b"late")[0] == 409
    assert call(base, "POST", "/ingest/s1/complete")[0] == 409


def test_it_cannot_complete_without_the_manifest_and_chunks(server):
    base, inbox, _ = server
    call(base, "PUT", "/ingest/s1/session.json", manifest())
    status, body = call(base, "POST", "/ingest/s1/complete")
    assert status == 409 and "browser_chunks.json" in body["error"]
    assert "never completed" in ingest.upload_refusal(inbox / "s1")


def test_the_inbox_is_a_retention_root_by_default():
    assert retention.ROOT / "tempdata" / "inbox" in retention.default_media_roots()


def test_a_refused_first_upload_leaves_no_folder_behind(server):
    """Found by deploy_check's probe: a rejected manifest used to leave an
    empty session folder in the inbox."""
    base, inbox, _ = server
    assert call(base, "PUT", "/ingest/s1/session.json", manifest(sid="s2"))[0] == 400
    assert call(base, "PUT", "/ingest/s2/session.json", b"not json")[0] == 400
    assert not (inbox / "s1").exists() and not (inbox / "s2").exists()
