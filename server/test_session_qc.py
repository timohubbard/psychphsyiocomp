"""The session quality report, on sessions written through the real writer."""

from __future__ import annotations

import json

import pytest

import session_qc
from alignment import ClockSolution
from cohort import select
from engine_contract import Chunk, EventRow, QualityRow
from session_qc import SEVERITY, report, worst
from study import content_hash
from tables import CanonicalWriter, SessionContext

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0, uncertainty_ms=0.0, n_anchors=0)
FACE_BROWSER = "face.mediapipe_blendshapes@0.1.0+browser-live"
FACE_SERVER = "face.mediapipe_blendshapes@0.1.0+server-batch"

STUDY = {
    "study_id": "qc1", "name": "QC", "version": "1.0.0",
    "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk"},
    "consent_tiers": ["features_only", "media_retained"], "modalities": ["face"],
    "analysis": {"exclusions": [{"metric": "face_detect_rate", "min": 0.5}]},
}


@pytest.fixture
def studies(tmp_path, monkeypatch):
    root = tmp_path / "studies"
    root.mkdir()
    (root / "qc1.json").write_text(json.dumps(STUDY), encoding="utf-8")
    monkeypatch.setattr(session_qc, "STUDIES_ROOT", root)
    return root


def q(metric, value):
    return QualityRow(stream="face", metric=metric, window_start_native_ts=0.0,
                      window_end_native_ts=1000.0, value=value)


def session(out, sid, *, rates=None, luma=120.0, tier="features_only", audience="participants",
            stopped=True, chash=None):
    rates = {FACE_SERVER: 0.9} if rates is None else rates
    w = CanonicalWriter(out, SessionContext(sid, f"p_{sid}", "qc1"))
    w.set_session_metadata({"study": {"study_id": "qc1", "study_content_hash": chash or content_hash(STUDY),
                                      "study_version": "1.0.0", "audience": audience,
                                      "modalities": ["face"]},
                            "consent": {"tier": tier, "retentionDays": 30}, "achieved_fps": 30.0})
    events = (EventRow(event_type="recording_stop", native_clock_id="performance.now",
                       onset_native_ts=5000.0, offset_native_ts=None),) if stopped else ()
    for i, (src, rate) in enumerate(rates.items()):
        w.add_chunks([Chunk(events=events if i == 0 else (),
                            quality=(q("face_detect_rate", rate), q("mean_luminance", luma)))],
                     source=src, params={}, solution=MASTER)
    if not rates:
        w.add_chunks([Chunk(events=events)], source="runner@0.1.0", params={}, solution=MASTER)
    w.close()


def by_name(r, group=None):
    return {c["name"]: c for c in r["checks"] if group is None or c["group"] == group}


def test_a_declared_rule_fails_exactly_when_the_cohort_excludes(tmp_path, studies):
    session(tmp_path, "good")
    session(tmp_path, "bad", rates={FACE_SERVER: 0.2})
    included = {r["session_id"] for r in select(tmp_path, STUDY).included}
    for sid in ("good", "bad"):
        r = report(tmp_path, sid, gaze_gate=False)
        rule = by_name(r, "Declared exclusions")["face_detect_rate"]
        assert (rule["status"] == "fail") == (sid not in included)
        assert r["cohort"]["included"] == (sid in included)
    assert report(tmp_path, "bad", gaze_gate=False)["worst"] == "fail"


def test_a_rule_nobody_measured_fails_as_it_does_in_the_cohort(tmp_path, studies):
    session(tmp_path, "blank", rates={})
    rule = by_name(report(tmp_path, "blank", gaze_gate=False), "Declared exclusions")["face_detect_rate"]
    assert rule["status"] == "fail" and "not measured" in rule["why"]


def test_an_engine_default_only_ever_warns(tmp_path, studies):
    # Dark: below the manifest's own mean_luminance 30 — a warning, never a failure.
    session(tmp_path, "dark", luma=12.0)
    r = report(tmp_path, "dark", gaze_gate=False)
    luma = by_name(r, "Engine quality")["mean_luminance"]
    assert luma["status"] == "warn" and luma["basis"] == "default" and luma["threshold"] == ">= 30"
    assert all(c["status"] != "fail" for c in r["checks"] if c["basis"] == "default")


def test_pooling_warns_only_when_the_source_read_would_change_the_verdict(tmp_path, studies):
    session(tmp_path, "agree", rates={FACE_BROWSER: 0.9, FACE_SERVER: 0.95})
    session(tmp_path, "split", rates={FACE_BROWSER: 0.2, FACE_SERVER: 0.9})
    agree = by_name(report(tmp_path, "agree", gaze_gate=False), "Declared exclusions")["face_detect_rate"]
    split = by_name(report(tmp_path, "split", gaze_gate=False), "Declared exclusions")["face_detect_rate"]
    assert agree["status"] == "pass" and "pooled across 2 sources" in agree["why"]
    assert split["status"] == "warn" and "name a `source`" in split["why"]


def test_a_self_test_is_left_out_of_the_cohort_without_its_data_looking_bad(tmp_path, studies):
    session(tmp_path, "me", audience="developer")
    r = report(tmp_path, "me", gaze_gate=False)
    assert r["cohort"]["included"] is False and r["cohort"]["reason"].startswith("audience")
    assert r["worst"] == "pass"
    assert by_name(r)["audience"]["status"] == "info"


def test_an_edited_study_is_a_warning_and_its_rules_are_not_applied(tmp_path, studies):
    session(tmp_path, "old", chash="0" * 16)
    r = report(tmp_path, "old", gaze_gate=False)
    assert by_name(r)["study file matches"]["status"] == "warn"
    assert not by_name(r, "Declared exclusions")


def test_the_in_browser_tier_reports_no_recording_as_information(tmp_path, studies):
    session(tmp_path, "local", tier="features_in_browser")
    clock = by_name(report(tmp_path, "local", gaze_gate=False))["clock alignment"]
    assert clock["status"] == "info" and clock["value"] == "no recording"


def test_a_session_that_never_stopped_is_flagged(tmp_path, studies):
    session(tmp_path, "abandoned", stopped=False)
    assert by_name(report(tmp_path, "abandoned", gaze_gate=False))["recording stopped normally"]["status"] == "warn"


def test_info_never_makes_a_session_look_worse():
    assert worst([session_qc.Check("g", "n", "info", "info"), session_qc.Check("g", "m", "pass", "default")]) == "pass"
    assert list(sorted(SEVERITY, key=SEVERITY.get)) == ["info", "pass", "not_measured", "warn", "fail"]
