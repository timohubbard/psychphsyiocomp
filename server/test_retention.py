"""Retention and withdrawal: the consent screen's deletion promise, enforced.

Built on the real on-disk shapes — a CanonicalWriter's session folder, the
annotation store's file naming, a bundle folder as the capture page downloads
it — because a fixture shaped like this module's assumptions would prove only
that the module agrees with itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import retention
from retention import (apply_deletion, collect_sessions, expired, plan_deletion,
                       refusal_for, resolve_withdrawal, tombstones)
from tables import CanonicalWriter, SessionContext

START = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def manifest(session_id, participant_id="p1", days=30, tier="media_retained",
             created=START):
    m = {"session_id": session_id, "participant_id": participant_id,
         "study_id": "au-expressions", "created_utc": created.isoformat()}
    if tier is not None:
        m["consent"] = {"tier": tier, "retentionDays": days}
    return m


def processed(out, session_id, **kw):
    """A session as the pipeline leaves it: the real writer, real tables."""
    m = manifest(session_id, **kw)
    w = CanonicalWriter(out, SessionContext(session_id, m["participant_id"],
                                            m["study_id"]))
    w.set_session_metadata(m)
    w.close()
    return m


def bundle(media, folder, session_id, **kw):
    """A bundle folder as downloaded, with the caches processing writes beside it."""
    d = media / folder
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps(manifest(session_id, **kw)))
    for name in ("capture.webm", "browser_chunks.json",
                 "capture.audio.wav", "capture.playback.webm"):
        (d / name).write_bytes(b"x")
    return d


def label(out, session_id, rater="r1"):
    d = out / "annotations" / "cb.0123abcd"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session_id}.{rater}.json"
    p.write_text("{}")
    return p


@pytest.fixture
def roots(tmp_path):
    out, media = tmp_path / "out", tmp_path / "media"
    out.mkdir()
    media.mkdir()
    return out, media


# -- expiry -----------------------------------------------------------------

def test_expiry_is_the_start_plus_the_period_the_participant_was_shown(roots):
    out, media = roots
    processed(out, "s1", days=30)
    rec = collect_sessions(out, [media])["s1"]
    assert rec.expires_utc() == START + timedelta(days=30)
    assert expired({"s1": rec}, START + timedelta(days=30)) == [rec]
    assert expired({"s1": rec}, START + timedelta(days=30) - timedelta(seconds=1)) == []


def test_a_session_with_no_recorded_period_never_expires(roots):
    """The pilots predate consent tiers. A missing field is not a deletion order."""
    out, media = roots
    processed(out, "pilot", tier=None)
    rec = collect_sessions(out, [media])["pilot"]
    assert rec.expires_utc() is None
    assert rec.no_expiry_reason() == "no_retention_recorded"
    assert expired({"pilot": rec}, START + timedelta(days=10_000)) == []


def test_the_table_decides_not_a_later_edit_to_the_bundle(roots):
    """What the pipeline recorded is the promise; a manifest edited afterwards to
    a longer period cannot extend it."""
    out, media = roots
    processed(out, "s1", days=30)
    bundle(media, "dl", "s1", days=900)
    assert collect_sessions(out, [media])["s1"].retention_days == 30


def test_an_unprocessed_bundle_still_carries_its_promise(roots):
    """A recording downloaded and never processed must not live forever."""
    out, media = roots
    bundle(media, "never_processed", "s9", days=7)
    rec = collect_sessions(out, [media])["s9"]
    assert rec.origin == "bundle"
    assert expired({"s9": rec}, START + timedelta(days=8)) == [rec]


def test_a_boolean_retention_is_not_a_number_of_days(roots):
    out, media = roots
    d = media / "b"
    d.mkdir()
    m = manifest("s1")
    m["consent"]["retentionDays"] = True
    (d / "session.json").write_text(json.dumps(m))
    assert collect_sessions(out, [media])["s1"].retention_days is None


# -- what a deletion covers -------------------------------------------------

def test_the_plan_covers_tables_labels_and_the_whole_bundle(roots):
    out, media = roots
    processed(out, "s1")
    b = bundle(media, "Tims download", "s1")
    lab = label(out, "s1")
    plan = plan_deletion("s1", out, [media])
    assert set(plan.paths) == {out / "session_id=s1", lab, b}
    assert plan.manual == []


def test_a_label_for_a_session_whose_id_extends_this_one_is_not_taken(roots):
    out, media = roots
    mine, theirs = label(out, "s_ab"), label(out, "s_abc")
    assert plan_deletion("s_ab", out, [media]).paths == [mine]
    assert theirs.exists()


def test_a_bundle_loose_in_a_media_root_is_reported_never_deleted(roots):
    """The pilot was once downloaded straight into tempdata/. Deleting the root
    would take every other bundle with it."""
    out, media = roots
    (media / "session.json").write_text(json.dumps(manifest("loose")))
    plan = plan_deletion("loose", out, [media])
    assert plan.paths == []
    assert len(plan.manual) == 1 and "by hand" in plan.manual[0]


def test_a_folder_containing_the_output_root_is_never_deleted(tmp_path):
    """--media pointed one level too high must not take out/ with a bundle."""
    parent = tmp_path / "work"
    out = parent / "out"
    out.mkdir(parents=True)
    (parent / "session.json").write_text(json.dumps(manifest("s1")))
    plan = plan_deletion("s1", out, [tmp_path])
    assert plan.paths == [] and plan.manual


# -- acting -----------------------------------------------------------------

def test_apply_removes_everything_and_leaves_other_sessions_alone(roots):
    out, media = roots
    processed(out, "s1")
    processed(out, "s2", participant_id="p2")
    b1, b2 = bundle(media, "one", "s1"), bundle(media, "two", "s2")
    l1, l2 = label(out, "s1"), label(out, "s2")
    aoi = out / "aoi_sets" / "stim.json"
    aoi.parent.mkdir()
    aoi.write_text("{}")

    rec = collect_sessions(out, [media])["s1"]
    apply_deletion(plan_deletion("s1", out, [media]), rec, out, "withdrawn", START)

    assert not (out / "session_id=s1").exists() and not b1.exists() and not l1.exists()
    assert (out / "session_id=s2").exists() and b2.exists() and l2.exists()
    assert aoi.exists(), "AOI sets are method configuration, not session data"


def test_the_tombstone_records_the_deletion_but_not_the_participant(roots):
    out, media = roots
    processed(out, "s1", participant_id="alice@example.org")
    bundle(media, "alice's download", "s1", participant_id="alice@example.org")
    rec = collect_sessions(out, [media])["s1"]
    apply_deletion(plan_deletion("s1", out, [media]), rec, out, "withdrawn", START)

    raw = (out / retention.TOMBSTONES).read_text()
    assert "alice" not in raw, "the log must not become the thing to delete"
    stone = tombstones(out)["s1"]
    assert stone["reason"] == "withdrawn"
    assert sorted(stone["removed"]) == ["derived tables", "raw bundle folder"]


def test_a_deleted_session_is_refused_whatever_copy_turns_up(roots):
    """A bundle has copies. Re-processing one must not resurrect a withdrawal."""
    out, media = roots
    processed(out, "s1")
    rec = collect_sessions(out, [media])["s1"]
    apply_deletion(plan_deletion("s1", out, [media]), rec, out, "withdrawn", START)
    why = refusal_for(out, "s1", manifest("s1"), now=START)
    assert why and "leftover copy" in why


def test_an_expired_bundle_is_refused_rather_than_processed(roots):
    out, _ = roots
    m = manifest("s1", days=30)
    assert refusal_for(out, "s1", m, now=START + timedelta(days=29)) is None
    assert "expired" in refusal_for(out, "s1", m, now=START + timedelta(days=31))


def test_a_session_with_no_period_is_processed_not_refused(roots):
    out, _ = roots
    assert refusal_for(out, "p", manifest("p", tier=None),
                       now=START + timedelta(days=10_000)) is None


# -- withdrawal ---------------------------------------------------------------

def test_withdrawing_a_participant_reaches_every_session_they_took(roots):
    out, media = roots
    processed(out, "s1", participant_id="p1")
    bundle(media, "later", "s2", participant_id="p1")   # never processed
    processed(out, "s3", participant_id="p2")
    got = resolve_withdrawal("p1", collect_sessions(out, [media]))
    assert [s.session_id for s in got] == ["s1", "s2"]


def test_withdrawing_by_session_id_takes_only_that_session(roots):
    out, media = roots
    processed(out, "s1", participant_id="p1")
    processed(out, "s2", participant_id="p1")
    got = resolve_withdrawal("s2", collect_sessions(out, [media]))
    assert [s.session_id for s in got] == ["s2"]


def test_the_commands_are_dry_runs_unless_told(roots, capsys):
    out, media = roots
    processed(out, "old", days=1)
    b = bundle(media, "dl", "old", days=1)
    common = ["--out", str(out), "--media", str(media)]

    assert retention.main(["sweep", *common]) == 0
    assert (out / "session_id=old").exists() and b.exists()
    assert "dry run" in capsys.readouterr().out

    assert retention.main(["withdraw", "nobody", *common]) == 1
    assert (out / "session_id=old").exists()

    assert retention.main(["sweep", *common, "--apply"]) == 0
    assert not (out / "session_id=old").exists() and not b.exists()
    assert tombstones(out)["old"]["reason"] == "retention_expired"
