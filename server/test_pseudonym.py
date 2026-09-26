"""Panel identifiers become pseudonyms before anything is written, and can be forgotten."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import pseudonym
import retention
from pipeline import SessionBundle, process_session
from tables import read_session

PROLIFIC = {"platform": "prolific", "participant": "5f3aA9e1c0ffee", "study": "st1", "session": "se1"}


def test_the_same_id_always_maps_to_the_same_pseudonym_and_others_do_not(tmp_path):
    a = pseudonym.pseudonym(tmp_path, "prolific", "abc")
    assert a == pseudonym.pseudonym(tmp_path, "prolific", "abc")
    assert a.startswith("p_") and len(a) == 18
    assert a != pseudonym.pseudonym(tmp_path, "prolific", "abd")
    assert a != pseudonym.pseudonym(tmp_path, "url", "abc"), "platform is part of the identity"


def test_it_is_keyed_not_a_plain_hash(tmp_path):
    """Anyone who can list Prolific IDs could reverse a plain SHA-256. A
    different deployment's key gives a different pseudonym for the same ID."""
    import hashlib
    p = pseudonym.pseudonym(tmp_path / "one", "prolific", "abc")
    assert p != pseudonym.pseudonym(tmp_path / "two", "prolific", "abc")
    assert p[2:] != hashlib.sha256(b"prolific:abc").hexdigest()[:16]


def test_the_key_is_created_once_and_reused(tmp_path):
    first = pseudonym.pseudonym(tmp_path, "url", "x")
    key = (tmp_path / "_keys" / "pseudonym.key").read_text()
    assert pseudonym.pseudonym(tmp_path, "url", "x") == first
    assert (tmp_path / "_keys" / "pseudonym.key").read_text() == key


def _bundle_dir(tmp_path, ids=PROLIFIC, sid="s1"):
    d = tmp_path / "media" / "dl"
    d.mkdir(parents=True)
    manifest = {"session_id": sid, "participant_id": "p_pending", "study_id": "d",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "consent": {"tier": "features_only", "retentionDays": 30}}
    (d / "session.json").write_text(json.dumps(manifest))
    (d / "identifiers.json").write_text(json.dumps({**ids, "session_id": sid}))
    return d


def test_process_bundle_writes_only_the_pseudonym(tmp_path):
    out = tmp_path / "out"
    d = _bundle_dir(tmp_path)
    bundle = SessionBundle.from_dir(d)
    p = pseudonym.apply_to_bundle(out, bundle, d)
    process_session(bundle, [], out)

    row = read_session(out, "s1", "sessions").to_pylist()[0]
    assert row["participant_id"] == p
    raw = PROLIFIC["participant"]
    for f in (out / "session_id=s1").rglob("*.parquet"):
        assert raw.encode() not in f.read_bytes(), f"raw panel ID in {f.name}"


def test_withdrawal_by_the_raw_panel_id_finds_processed_and_unprocessed_sessions(tmp_path):
    out, media = tmp_path / "out", tmp_path / "media"
    d = _bundle_dir(tmp_path)
    bundle = SessionBundle.from_dir(d)
    pseudonym.apply_to_bundle(out, bundle, d)
    process_session(bundle, [], out)

    later = media / "later"
    later.mkdir()
    (later / "session.json").write_text(json.dumps({
        "session_id": "s2", "participant_id": "p_pending", "study_id": "d",
        "created_utc": datetime.now(timezone.utc).isoformat()}))
    (later / "identifiers.json").write_text(json.dumps({**PROLIFIC, "session_id": "s2"}))

    sessions = retention.collect_sessions(out, [media])
    got = retention.resolve_withdrawal(PROLIFIC["participant"], sessions)
    assert [s.session_id for s in got] == ["s1", "s2"]


def test_withdrawal_removes_the_link_and_the_tombstone_holds_no_id(tmp_path):
    out, media = tmp_path / "out", tmp_path / "media"
    d = _bundle_dir(tmp_path)
    bundle = SessionBundle.from_dir(d)
    pseudonym.apply_to_bundle(out, bundle, d)
    process_session(bundle, [], out)
    assert pseudonym.resolve(out, PROLIFIC["participant"])

    assert retention.main(["withdraw", PROLIFIC["participant"], "--out", str(out),
                           "--media", str(media), "--apply"]) == 0
    assert pseudonym.resolve(out, PROLIFIC["participant"]) == set()
    log = (out / retention.TOMBSTONES).read_text()
    assert PROLIFIC["participant"] not in log
    assert not d.exists(), "identifiers.json goes with its bundle"


def test_a_bundle_without_identifiers_keeps_its_own_id(tmp_path):
    b = SimpleNamespace(session_id="s", participant_id="anonymous", metadata={})
    assert pseudonym.apply_to_bundle(tmp_path, b, tmp_path) is None
    assert b.participant_id == "anonymous"


def test_identifiers_without_a_participant_are_refused(tmp_path):
    with pytest.raises(ValueError):
        pseudonym.link(tmp_path, {"platform": "prolific"}, "s1")
