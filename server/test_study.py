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


#: The participant fixture's hash, computed by the BROWSER implementation. Every
#: field added after m0 is set there, so this pins the optional hashed part the
#: way M0_CONTENT_HASH pins the fixed part.
PARTICIPANT_FIXTURE_HASH = "bbf9131e9314dc57"


def test_the_participant_fixture_hashes_to_the_browsers_value():
    s = json.loads((ROOT / "server" / "fixtures" / "participant-study.json")
                   .read_text(encoding="utf-8"))
    assert validate_study(s).reasons == ()
    assert content_hash(s) == PARTICIPANT_FIXTURE_HASH


# ---------------------------------------------------------------------------
# who a study may be run on — mirrors study.test.mjs
# ---------------------------------------------------------------------------

def participant_study(disclosure=None, **overrides):
    s = study(audience="participants", **overrides)
    s["disclosure"] = {
        **s["disclosure"],
        "contact": "a.researcher@uni.ac.uk",
        "irb_reference": "REC-2026-0417",
        "controller": "University of Somewhere",
        "lawful_basis": "UK GDPR Art 6(1)(e)",
        "special_category_basis": "UK GDPR Art 9(2)(j)",
        **(disclosure or {}),
    }
    return s


def _reasons(s):
    return " | ".join(validate_study(s).reasons)


def test_a_complete_participant_study_validates():
    assert validate_study(participant_study()).ok


def test_no_audience_is_a_developer_self_test_and_still_valid():
    from study import audience_of
    assert audience_of(study()) == "developer"
    assert validate_study(study()).ok


def test_an_unknown_audience_is_refused():
    assert "unknown audience" in _reasons(study(audience="everyone"))


def test_participants_without_an_ethics_reference_are_refused():
    assert "irb_reference" in _reasons(participant_study({"irb_reference": None}))


def test_the_shipped_placeholder_contact_is_refused_for_participants():
    s = participant_study({"contact": "Replace this with the investigator and the "
                                      "route to the ethics board."})
    assert "placeholder" in _reasons(s)


def test_a_contact_with_no_route_is_refused_for_participants():
    assert "no email address" in _reasons(participant_study({"contact": "the PI"}))


def test_an_example_org_address_is_a_template():
    assert "placeholder" in _reasons(participant_study({"contact": "pi@example.org"}))


def test_participants_need_the_controller_and_the_art_6_basis():
    r = _reasons(participant_study({"controller": None, "lawful_basis": None}))
    assert "controller" in r and "lawful_basis" in r


def test_special_category_modalities_need_an_art_9_condition_gaze_does_not():
    assert "face recorded but no disclosure.special_category_basis" in _reasons(
        participant_study({"special_category_basis": None}))
    assert validate_study(participant_study({"special_category_basis": None},
                                            modalities=["gaze"])).ok


def test_present_but_empty_fields_are_refused_whoever_the_audience():
    s = study()
    s["disclosure"]["controller"] = "  "
    assert "controller is present but empty" in _reasons(s)


def _item(**over):
    return {"stimulus_id": "forest", "kind": "image", "src": "stimuli/forest.png",
            "sha256": "a" * 64, "duration_ms": 4000, **over}


def _with_stimuli(items, **extra):
    return study(tasks=[{"type": "stimuli", "items": items, **extra}])


def test_a_well_formed_stimuli_task_validates():
    assert validate_study(_with_stimuli([_item(), _item(stimulus_id="sea", kind="video",
                                                         src="stimuli/sea.webm")])).ok


def test_stimulus_refusals_mirror_the_browser():
    assert "no items" in _reasons(_with_stimuli([]))
    assert "forest is used twice" in _reasons(_with_stimuli([_item(), _item()]))
    assert "kind must be image or video" in _reasons(_with_stimuli([_item(kind="audio")]))
    for bad in ("../out/x.png", "stimuli/../../x.png", "/etc/passwd"):
        assert "path under stimuli" in _reasons(_with_stimuli([_item(src=bad)])), bad
    assert "sha256 must be 64" in _reasons(_with_stimuli([_item(sha256="ABC")]))
    assert "duration_ms must be between" in _reasons(_with_stimuli([_item(duration_ms=0)]))
    assert "duration_ms must be between" in _reasons(_with_stimuli([_item(duration_ms=True)]))
    assert "sound must be true or false" in _reasons(_with_stimuli([_item(sound="yes")]))
    assert "randomise must be true or false" in _reasons(_with_stimuli([_item()], randomise="no"))


def test_the_shipped_stimulus_example_validates_and_its_hashes_match_the_files():
    """The browser refuses a changed file before consent; this catches it at
    commit time instead, on the real files."""
    import hashlib
    s = json.loads((ROOT / "studies" / "stimulus-example.json").read_text(encoding="utf-8"))
    assert validate_study(s).ok
    for task in s["tasks"]:
        for it in task.get("items", []):
            data = (ROOT / "studies" / it["src"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == it["sha256"], it["src"]


def test_conditions_mirror_the_browser():
    ok = study(conditions={"arms": ["A", "B"]}, tasks=[{"type": "calibration", "arms": ["A"]}])
    assert validate_study(ok).ok
    assert "at least two arms" in _reasons(study(conditions={"arms": ["A"]}))
    assert "repeats an arm" in _reasons(study(conditions={"arms": ["A", "A"]}))
    assert "defines no conditions" in _reasons(study(tasks=[{"type": "calibration", "arms": ["A"]}]))
    assert "non-empty subset" in _reasons(study(conditions={"arms": ["A", "B"]},
                                                tasks=[{"type": "calibration", "arms": ["C"]}]))


def test_conditions_are_hashed_and_the_completion_link_is_not():
    base = study(conditions={"arms": ["A", "B"]})
    assert content_hash(base) != content_hash(study(conditions={"arms": ["A", "C"]}))
    assert content_hash(base) == content_hash({**base, "recruitment": {
        "completion_url": "https://app.prolific.com/submissions/complete?cc=X"}})


def test_an_unsafe_completion_link_is_refused():
    assert "https address" in _reasons(study(recruitment={"completion_url": "http://example.org/?cc=X"}))
    assert validate_study(study(recruitment={"completion_url": "http://localhost:5173/done"})).ok


def test_an_analysis_plan_validates_and_is_not_in_the_protocol_hash():
    plan = {"exclusions": [{"metric": "achieved_fps", "min": 5}],
            "epochs": [{"name": "e", "event_type": "stimulus", "channels": ["gaze.x"],
                        "pre_ms": 200, "post_ms": 1000, "baseline_ms": [-200, 0]}]}
    assert validate_study(study(analysis=plan)).ok
    assert content_hash(study(analysis=plan)) == content_hash(study())


def test_analysis_refusals_mirror_the_browser():
    r = lambda a: _reasons(study(analysis=a))  # noqa: E731
    assert "needs a metric" in r({"exclusions": [{"min": 1}]})
    assert "needs a min or a max" in r({"exclusions": [{"metric": "x"}]})
    assert "min is above max" in r({"exclusions": [{"metric": "x", "min": 2, "max": 1}]})
    base = {"name": "e", "event_type": "stimulus", "channels": ["c"], "pre_ms": 200, "post_ms": 500}
    assert "unique slug name" in r({"epochs": [base, base]})
    assert "list of channels" in r({"epochs": [{**base, "channels": []}]})
    assert "inside the window" in r({"epochs": [{**base, "baseline_ms": [-500, 0]}]})
    assert "resample_hz" in r({"epochs": [{**base, "resample_hz": 0}]})


_LIKERT = {"id": "l", "kind": "likert", "prompt": "How?", "points": 7, "anchors": ["low", "high"]}


def _q(items, **disclosure):
    s = study(tasks=[{"type": "questions", "id": "qs", "items": items}])
    s["disclosure"].update(disclosure)
    return s


def test_questions_validate_and_free_text_needs_the_study_to_opt_in():
    choice = {"id": "c", "kind": "choice", "prompt": "Which?",
              "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}
    slider = {"id": "s", "kind": "slider", "prompt": "How much?", "min": 0, "max": 100,
              "anchors": ["none", "lots"], "allow_skip": True}
    assert validate_study(_q([_LIKERT, choice, slider])).ok
    text = {"id": "t", "kind": "text", "prompt": "Anything?"}
    assert "must opt in with disclosure.free_text: true" in _reasons(_q([text]))
    assert validate_study(_q([text], free_text=True)).ok


def test_question_refusals_mirror_the_browser():
    r = lambda items, **d: _reasons(_q(items, **d))  # noqa: E731
    assert "unknown keys for a likert item: anchor" in r([{**_LIKERT, "anchor": ["x"]}])
    assert "points must be a whole number from 2 to 11" in r([{**_LIKERT, "points": 12}])
    assert "anchors must be two labels" in r([{**_LIKERT, "anchors": ["only one"]}])
    assert "item 2 needs a unique slug id" in r([_LIKERT, _LIKERT])
    assert "kind must be likert, choice, slider or text" in r([{**_LIKERT, "kind": "essay"}])
    assert "options must be 2 to 12" in r([{"id": "c", "kind": "choice", "prompt": "x",
                                            "options": [{"id": "a", "label": "A"}]}])
    assert "min < max" in r([{"id": "s", "kind": "slider", "prompt": "x", "min": 5, "max": 5,
                              "anchors": ["a", "b"]}])
    assert "needs 1 to 50 items" in r([])
    assert "prompt must be 1 to 500 characters" in r([{**_LIKERT, "prompt": ""}])
    assert "free_text is true but no question asks for typed text" in r([_LIKERT], free_text=True)
    assert "free_text must be true or false" in r([_LIKERT], free_text="yes")


def test_free_text_is_hashed_only_when_present():
    t = _q([{"id": "t", "kind": "text", "prompt": "x"}], free_text=True)
    no_flag = _q([{"id": "t", "kind": "text", "prompt": "x"}])
    assert content_hash(t) != content_hash(no_flag)
    assert "free_text" not in [k for k, _ in _canon(study())]


def test_the_questions_example_hashes_the_same_in_both_languages():
    """Pinned from the browser's contentHash on studies/questions-example.json."""
    from study import load_study
    assert content_hash(load_study(ROOT / "studies", "questions-example")) == "794711c5c833f767"


def _with_contrast(**over):
    epochs = [{"name": "e", "event_type": "stimulus", "channels": ["c"], "pre_ms": 500, "post_ms": 2000}]
    c = {"name": "k", "epochs": "e", "channel": "c", "arms": ["A", "B"], "window_ms": [200, 1000],
         "n_permutations": 5000, "seed": 1, "cluster": {"p_threshold": 0.05}}
    c.update(over)
    return study(conditions={"arms": ["A", "B"]}, analysis={"epochs": epochs, "contrasts": [c]})


def test_a_declared_contrast_validates_and_leaves_the_protocol_hash_alone():
    assert validate_study(_with_contrast()).ok, _reasons(_with_contrast())
    assert content_hash(_with_contrast()) == content_hash(study(conditions={"arms": ["A", "B"]}))


def test_contrast_refusals_mirror_the_browser():
    r = lambda **o: _reasons(_with_contrast(**o))  # noqa: E731
    assert "unknown keys: windows_ms" in r(windows_ms=[0, 1])
    assert "epoch set in analysis.epochs" in r(epochs="nope")
    assert "one of that epoch set's channels" in r(channel="x")
    assert "two different arms" in r(arms=["A", "A"])
    assert "two different arms" in r(arms=["A", "C"])
    assert "inside the epoch" in r(window_ms=[-900, 100])
    assert "from 1000 to 100000" in r(n_permutations=10)
    assert "seed must be a whole number" in r(seed=True)
    assert "seed must be a whole number" not in r(seed=3.0)        # 3.0 is whole in JS too
    assert "tail must be" in r(tail="both")
    assert "p_threshold" in r(cluster={"p_threshold": 2})
    assert "cluster has unknown keys: tail" in r(cluster={"tail": "two"})
    no_arms = study(analysis=_with_contrast()["analysis"])
    assert "defines no conditions" in _reasons(no_arms)
    assert "must be a list" in _reasons(study(analysis={"contrasts": None}))


def test_the_in_browser_tier_may_be_offered_for_gaze_and_face():
    s = study(consent_tiers=["features_in_browser", "features_only"],
              default_tier="features_in_browser", modalities=["gaze", "face"])
    assert validate_study(s).ok


def test_the_in_browser_tier_is_refused_for_server_only_modalities():
    for m in ("voice", "respiration"):
        s = study(consent_tiers=["features_in_browser"], default_tier="features_in_browser",
                  modalities=["gaze", m])
        assert f"{m} can only be measured" in _reasons(s)


def test_fields_added_after_m0_are_hashed_only_when_set():
    assert len(_canon(study())) == 11
    assert [k for k, _ in _canon(participant_study())][11:] == [
        "audience", "controller", "lawful_basis", "special_category_basis"]


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


def test_a_transcript_tier_needs_a_microphone():
    """Mirrors study.js. Offering transcription in a face-only study records a
    consent to transcribe a session that has no audio."""
    from study import validate_study
    s = study()
    s["modalities"] = ["face"]
    s["consent_tiers"] = ["features_only", "media_plus_transcript"]
    v = validate_study(s)
    assert not v.ok
    assert any("no modality records audio" in r for r in v.reasons)
    s["modalities"] = ["face", "voice"]
    assert validate_study(s).ok
