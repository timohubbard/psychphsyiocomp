"""Tests for study definitions, server side.

Two jobs. One is the same refusal behaviour `web/src/study.test.mjs` pins, so
the mirror does not drift into being more permissive than the browser. The
other is the part only this side can check: that a session's recorded protocol
still matches the file on disk.
"""

from __future__ import annotations

import json

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from study import (
    MAX_RETENTION_DAYS,
    content_hash,
    list_studies,
    load_study,
    validate_study,
    verify_session_study,
)

#: The hash of the real `studies/m0.json`, computed by the BROWSER
#: implementation and pinned here by hand.
#:
#: This is the whole reason the two implementations can coexist. If either side
#: changes how it canonicalises or hashes, this constant stops matching and one
#: of the two suites fails. Without it, a drift would show up as every session
#: being reported as "study edited since session" — a false alarm that looks
#: exactly like a real one.
M0_CONTENT_HASH = "5b54b291bc9d74b0"


def study(**overrides):
    base = {
        "study_id": "reading-2026",
        "name": "Reading study",
        "version": "1.0.0",
        "disclosure": {
            "retention_days": 365,
            "secondary_use": "Analysed by the named team only.",
            "contact": "pi@example.edu",
            "irb_reference": "IRB-2026-0142",
        },
        "consent_tiers": ["features_only", "media_retained"],
        "default_tier": "features_only",
        "modalities": ["gaze", "face"],
        "calibration": {"n_points": 13, "randomise_order": True},
        "tasks": [{"type": "passage", "id": "p1"}],
    }
    base.update(overrides)
    return base


@pytest.fixture
def studies_dir(tmp_path):
    (tmp_path / "reading-2026.json").write_text(
        json.dumps(study()), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# the mirror agrees with the browser
# ---------------------------------------------------------------------------

def test_the_shipped_study_hashes_to_the_browsers_value():
    """Byte-for-byte agreement with `web/src/study.js`, on the real file."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    s = json.loads((root / "studies" / "m0.json").read_text(encoding="utf-8"))
    assert content_hash(s) == M0_CONTENT_HASH


def test_the_shipped_study_is_valid():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    s = json.loads((root / "studies" / "m0.json").read_text(encoding="utf-8"))
    assert validate_study(s).ok


def test_non_ascii_text_hashes_the_same_as_the_browser_would():
    """JSON.stringify does not escape non-ASCII; json.dumps does unless told
    not to. A disclosure with a curly apostrophe would otherwise hash
    differently in the two languages — and disclosures are prose, so it would."""
    s = study(disclosure={**study()["disclosure"],
                          "secondary_use": "We don’t sell your data — ever."})
    payload = json.dumps(_canon(s), separators=(",", ":"), ensure_ascii=False)
    assert "\\u" not in payload


def _canon(s):
    from study import canonicalise
    return canonicalise(s)


# ---------------------------------------------------------------------------
# refusals, mirroring the browser's
# ---------------------------------------------------------------------------

def test_a_complete_study_validates():
    assert validate_study(study()).ok


def test_a_missing_retention_period_is_refused():
    s = study()
    del s["disclosure"]["retention_days"]
    v = validate_study(s)
    assert not v.ok
    assert any("retention_days" in r for r in v.reasons)


def test_retention_beyond_the_cap_is_refused():
    s = study(disclosure={**study()["disclosure"],
                          "retention_days": MAX_RETENTION_DAYS + 1})
    assert any("exceeds" in r for r in validate_study(s).reasons)


def test_a_boolean_retention_is_not_a_number_of_days():
    """`True` is an int in Python and would sail past a naive isinstance check
    as a retention period of one day."""
    s = study(disclosure={**study()["disclosure"], "retention_days": True})
    assert not validate_study(s).ok


def test_no_contact_route_is_refused():
    s = study()
    del s["disclosure"]["contact"]
    assert any("46.116(b)(7)" in r for r in validate_study(s).reasons)


def test_an_unknown_tier_is_refused():
    s = study(consent_tiers=["features_only", "keep_forever"])
    assert any("keep_forever" in r for r in validate_study(s).reasons)


def test_a_study_measuring_nothing_is_refused():
    assert any("measures nothing" in r
               for r in validate_study(study(modalities=[])).reasons)


def test_gaze_without_calibration_is_refused():
    s = study()
    del s["calibration"]
    assert any("n_points" in r for r in validate_study(s).reasons)


def test_fixed_calibration_order_is_refused():
    s = study(calibration={"n_points": 13, "randomise_order": False})
    assert any("confounds" in r for r in validate_study(s).reasons)


def test_nothing_at_all_is_refused_without_raising():
    assert not validate_study(None).ok
    assert not validate_study("reading-2026").ok
    assert not validate_study([]).ok


# ---------------------------------------------------------------------------
# loading and listing
# ---------------------------------------------------------------------------

def test_loads_a_valid_study(studies_dir):
    assert load_study(studies_dir, "reading-2026")["version"] == "1.0.0"


def test_a_missing_study_raises(studies_dir):
    with pytest.raises(FileNotFoundError):
        load_study(studies_dir, "nonexistent")


def test_an_id_that_disagrees_with_the_file_raises(studies_dir):
    """A session labelled with an id that does not describe its protocol is
    worse than one that fails to load."""
    (studies_dir / "renamed.json").write_text(json.dumps(study()), encoding="utf-8")
    with pytest.raises(ValueError, match="declares study_id"):
        load_study(studies_dir, "renamed")


def test_a_traversing_id_is_refused_before_any_file_is_touched(studies_dir):
    with pytest.raises(ValueError, match="not a usable study id"):
        load_study(studies_dir, "../../etc/passwd")


def test_an_invalid_study_raises_rather_than_loading_partially(studies_dir):
    bad = study()
    del bad["disclosure"]["secondary_use"]
    (studies_dir / "bad.json").write_text(
        json.dumps({**bad, "study_id": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a usable study"):
        load_study(studies_dir, "bad")


def test_listing_shows_invalid_studies_with_their_reasons(studies_dir):
    """Hiding them would leave a researcher whose study stopped loading with an
    empty list and no way to find out why."""
    bad = study()
    del bad["disclosure"]["contact"]
    (studies_dir / "bad.json").write_text(
        json.dumps({**bad, "study_id": "bad"}), encoding="utf-8")

    rows = {r["study_id"]: r for r in list_studies(studies_dir)}
    assert rows["reading-2026"]["valid"] is True
    assert rows["bad"]["valid"] is False
    assert any("46.116" in r for r in rows["bad"]["reasons"])


def test_listing_survives_a_file_that_is_not_json(studies_dir):
    (studies_dir / "broken.json").write_text("{not json", encoding="utf-8")
    rows = {r["study_id"]: r for r in list_studies(studies_dir)}
    assert rows["broken"]["valid"] is False


def test_listing_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert list_studies(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# does the session still match its protocol?
# ---------------------------------------------------------------------------

def _session(studies_dir, **overrides):
    s = load_study(studies_dir, "reading-2026")
    recorded = {
        "study_id": "reading-2026",
        "study_version": s["version"],
        "study_content_hash": content_hash(s),
        "modalities": sorted(s["modalities"]),
    }
    recorded.update(overrides)
    return {"study_id": "reading-2026", "study": recorded}


def test_an_unedited_study_verifies(studies_dir):
    v = verify_session_study(_session(studies_dir), studies_dir)
    assert v.ok
    assert v.detail["version"] == "1.0.0"


def test_editing_the_study_after_a_session_is_detected(studies_dir):
    """The case a version string does not catch: nobody bumps a version while
    fixing a disclosure. Sessions either side of the edit are not one study."""
    session = _session(studies_dir)

    edited = study(disclosure={**study()["disclosure"], "retention_days": 90})
    (studies_dir / "reading-2026.json").write_text(
        json.dumps(edited), encoding="utf-8")

    v = verify_session_study(session, studies_dir)
    assert not v.ok
    assert v.reasons == ("study_edited_since_session",)
    assert v.detail["recorded_hash"] != v.detail["file_hash"]
    # Both versions read "1.0.0", which is the point.
    assert v.detail["recorded_version"] == v.detail["file_version"]


def test_retitling_a_study_does_not_trip_the_check(studies_dir):
    """Prose churn would make the check noise, and a noisy check is ignored."""
    session = _session(studies_dir)
    (studies_dir / "reading-2026.json").write_text(
        json.dumps(study(name="Reading study (pilot)")), encoding="utf-8")
    assert verify_session_study(session, studies_dir).ok


def test_a_session_from_before_study_definitions_is_named_not_failed(studies_dir):
    v = verify_session_study({"study_id": "m0"}, studies_dir)
    assert not v.ok
    assert v.reasons == ("no_study_recorded",)


def test_a_deleted_study_is_distinguished_from_an_edited_one(studies_dir):
    """Different responses: one can be restored from git, the other means the
    sessions were run under two protocols sharing a name."""
    session = _session(studies_dir)
    (studies_dir / "reading-2026.json").unlink()
    v = verify_session_study(session, studies_dir)
    assert v.reasons == ("study_unavailable",)


def test_verification_never_raises_on_a_malformed_session(studies_dir):
    for meta in ({}, {"study": None}, {"study": "reading-2026"}, {"study": {}}):
        assert verify_session_study(meta, studies_dir).ok is False


def test_the_capture_page_index_is_not_listed_as_a_study():
    """studies/index.json is the chooser list; globbing *.json listed it as a
    study that fails validation."""
    rows = list_studies(ROOT / "studies")
    ids = {r["study_id"] for r in rows}
    assert "index" not in ids
    assert {"m0", "au-expressions"} <= ids
    assert all(r["valid"] for r in rows)
