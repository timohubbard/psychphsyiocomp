"""The Art 30 record is generated from the study, and admits what it cannot know."""

from __future__ import annotations

import json
from pathlib import Path

from ropa import TODO, record
from study import content_hash

ROOT = Path(__file__).resolve().parent.parent


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_a_participant_study_fills_every_field_it_can():
    s = _load("server/fixtures/participant-study.json")
    r = record(s)
    assert "University of Somewhere, Research Data Office" in r
    assert "REC-2026-0417" in r
    assert "Art 6(1)(e)" in r and "Art 9(2)(j)" in r
    assert "180 days" in r
    assert content_hash(s) in r, "a record must say which protocol it describes"
    assert "Developer self-test" not in r


def test_what_the_study_cannot_know_is_marked_never_guessed():
    r = record(_load("server/fixtures/participant-study.json"))
    for gap in ("Data protection officer", "Transfers outside", "Deployment measures"):
        line = next(l for l in r.splitlines() if gap in l)
        assert TODO in line, line


def test_face_is_flagged_special_category_and_gaze_alone_is_not():
    s = _load("server/fixtures/participant-study.json")
    assert "Treated as special category by default: face" in record(s)
    s["modalities"] = ["gaze"]
    assert "None expected (gaze only)" in record(s)


def test_the_shipped_m0_is_described_as_a_self_test_with_its_gaps_marked():
    r = record(_load("studies/m0.json"))
    assert "Developer self-test" in r
    controller = next(l for l in r.splitlines() if "(a) Controller" in l)
    assert TODO in controller
    contact = next(l for l in r.splitlines() if "(a) Contact" in l)
    assert TODO in contact and "Replace this" not in contact, \
        "a template contact must not be recorded as if it were one"


def test_retained_media_and_transcripts_appear_only_when_offered():
    s = _load("studies/m0.json")          # offers all three tiers, records voice
    r = record(s)
    assert "face video and voice audio where the participant opts to keep it" in r
    assert "speech transcripts" in r
    s["consent_tiers"] = ["features_only"]
    r = record(s)
    assert "face video" not in r and "transcripts" not in r
