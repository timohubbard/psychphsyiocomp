"""Scoring rules: an engine read as a codebook category, and scored against raters.

The synthetic session plants a known answer — AU12 high exactly at the moments
the raters called "smile" — on a recording clock that is deliberately NOT the
master clock (offset 5 s, rate 1.001). A rule that ignored the clock would read
the wrong moments and score badly; one that inverts it correctly scores at the
raters' own level.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

import numpy as np
import pytest

import annotation_store
import scoring_rules as sr
from alignment import ClockSolution
from engine_contract import (Chunk, Eligibility, EngineLicense, EngineManifest, EngineOutputs,
                             EngineProvenance, InputSpec, SignalRow)
from tables import CanonicalWriter, SessionContext

VIDEO = ClockSolution(clock_id="video_pts", offset_ms=5000.0, rate=1.001, uncertainty_ms=5.0, n_anchors=2)
SOURCE = "face.opengraphau_aus@0.1.0+server-batch"
ITEMS = [float(1000 * (i + 1)) for i in range(40)]
TRUTH = ["smile" if i % 3 == 0 else "neutral" for i in range(40)]
CODEBOOK = {"codebook_id": "smiling", "name": "Is the participant smiling?",
            "categories": [{"id": "smile", "label": "Smiling", "description": "Lip corners pulled up."},
                           {"id": "neutral", "label": "Not smiling", "description": "Anything else."}],
            "items": ITEMS}


def manifest():
    return EngineManifest(
        engine_id="face.opengraphau_aus", version="0.1.0", modality="face", runtime="python-cpu",
        placement="server-batch", inputs=[InputSpec(kind="video")], params_schema={},
        outputs=EngineOutputs(signals=[], events=[], quality=[]),
        license=EngineLicense(spdx="Apache-2.0", commercial_use="yes", url="http://x"),
        provenance=EngineProvenance())


def write_session(out, sid, *, gap=None, params=None, solution=VIDEO, extra_params=None):
    w = CanonicalWriter(out, SessionContext(sid, "p_x", "st"))
    w.set_session_metadata({})
    ts = np.arange(0.0, 42000.0, 1000 / 30)
    smile_at = [ITEMS[i] for i in range(40) if TRUTH[i] == "smile"]
    rows = []
    for t in ts:
        if gap and gap[0] <= t <= gap[1]:
            continue
        v = 0.9 if any(abs(t - s) <= 300 for s in smile_at) else 0.1
        rows.append(SignalRow(stream="face", channel="au.AU12", native_clock_id="video_pts",
                              native_ts=float(t), value=v, reliability_tier="high"))
    w.add_chunks([Chunk(signals=tuple(rows))], source=SOURCE, params=params or {}, solution=solution)
    if extra_params is not None:
        w.add_chunks([Chunk(signals=tuple(rows[:10]))], source=SOURCE, params=extra_params, solution=solution)
    w.add_run(run_id=f"r-{sid}", manifest=manifest(), source=SOURCE, params=params or {},
              eligibility=Eligibility(eligible=True, reasons=(), detail=None), solution=solution,
              media_sha256="0" * 64, started=datetime.now(timezone.utc))
    w.close()


@pytest.fixture
def root(tmp_path):
    cb = annotation_store.save_codebook(tmp_path, CODEBOOK)
    h = cb["content_hash"]
    write_session(tmp_path, "s1")
    r2 = list(TRUTH)
    r2[1], r2[2] = "smile", "smile"          # the second rater disagrees twice
    for rater, labels in (("r1", TRUTH), ("r2", r2)):
        annotation_store.save_annotation(tmp_path, codebook_id="smiling", content_hash=h, session_id="s1",
                                         rater_id=rater, labels={str(int(t)): lab for t, lab in zip(ITEMS, labels)})
    return tmp_path


def rule(root, **over):
    h = annotation_store.load_codebook(root, "smiling")["content_hash"]
    r = {"rule_id": "au12-smile", "name": "AU12 over 0.5 is a smile", "codebook_id": "smiling",
         "codebook_version": h, "source": SOURCE, "channel": "au.AU12", "window_ms": [-200, 200],
         "statistic": "median", "min_samples": 3,
         "bins": [{"below": 0.5, "category": "neutral"}, {"below": None, "category": "smile"}]}
    r.update(over)
    return r


def matrix(root):
    h = annotation_store.load_codebook(root, "smiling")["content_hash"]
    return annotation_store.label_matrix(root, codebook_id="smiling", content_hash=h, session_id="s1")


OK = {"ok": True, "reasons": []}


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------

def test_a_complete_rule_validates(root):
    assert sr.check_rule(root, rule(root))["valid"]


def test_a_rule_is_refused_for_what_it_gets_wrong(root):
    reasons = lambda **o: " | ".join(sr.check_rule(root, rule(root, **o))["reasons"])  # noqa: E731
    assert "exactly one engine source" in reasons(source="any")
    assert "exactly one of channel or derived" in reasons(derived={"kind": "gaze_onscreen"})
    assert "not in that codebook version: grin" in reasons(
        bins=[{"below": 0.5, "category": "neutral"}, {"below": None, "category": "grin"}])
    assert "strictly increasing" in reasons(bins=[{"below": 0.5, "category": "neutral"},
                                                  {"below": 0.2, "category": "smile"},
                                                  {"below": None, "category": "smile"}])
    assert "open-ended" in reasons(bins=[{"below": 0.5, "category": "neutral"}, {"below": 1, "category": "smile"}])
    assert "does not exist" in reasons(codebook_version="0" * 16)
    assert "unknown keys: threshold" in reasons(threshold=0.5)


def test_a_category_the_rule_can_never_predict_is_said(root):
    got = sr.check_rule(root, rule(root, bins=[{"below": 0.5, "category": "neutral"},
                                               {"below": None, "category": "neutral"}]))
    assert got["valid"] and "can never predict: smile" in got["notes"][0]


def test_a_rule_version_is_never_overwritten(root):
    a = sr.save_rule(root, rule(root))
    assert sr.save_rule(root, rule(root, name="renamed"))["content_hash"] == a["content_hash"]
    b = sr.save_rule(root, rule(root, window_ms=[-300, 300]))
    assert b["content_hash"] != a["content_hash"]
    assert len(sr.list_rules(root, "smiling")) == 2


# ---------------------------------------------------------------------------
# reading the engine at each moment
# ---------------------------------------------------------------------------

def test_moments_are_read_through_the_recording_clock(root):
    p = sr.predict(root, "s1", rule(root), ITEMS)
    assert p["clock"] == {"offset_ms": 5000.0, "rate": 1.001} or p["clock"]["rate"] == pytest.approx(1.001)
    assert p["predictions"] == TRUTH


def test_the_engine_is_scored_on_the_raters_terms(root):
    out = sr.engine_arm(root, "s1", sr.save_rule(root, rule(root)), matrix(root), use="raw", origin=OK)
    assert out["refusal"] is None, out
    ev = out["evaluation"]
    assert ev["engine_score"] == pytest.approx(1.0)
    assert ev["ceiling"] == pytest.approx(38 / 40)          # the raters agreed on 38 of 40
    assert out["coverage"] == 1.0


def test_an_engine_that_misses_a_quarter_of_the_moments_is_not_scored(tmp_path):
    annotation_store.save_codebook(tmp_path, CODEBOOK)
    # No face from 0.9 s to 11.1 s: the moments at 1-10 s have no samples, and the
    # one at 11 s has too few left in its window — eleven abstain, 29 answered.
    write_session(tmp_path, "s1", gap=(900, 11100))
    h = annotation_store.load_codebook(tmp_path, "smiling")["content_hash"]
    for rater in ("r1", "r2"):
        annotation_store.save_annotation(tmp_path, codebook_id="smiling", content_hash=h, session_id="s1",
                                         rater_id=rater, labels={str(int(t)): lab for t, lab in zip(ITEMS, TRUTH)})
    m = annotation_store.label_matrix(tmp_path, codebook_id="smiling", content_hash=h, session_id="s1")
    out = sr.engine_arm(tmp_path, "s1", sr.save_rule(tmp_path, rule(tmp_path)), m, use="raw", origin=OK)
    assert out["refusal"]["reason"] == "low_coverage" and out["n_answered"] == 29


def test_an_unchecked_recording_start_refuses_the_engine_arm(root):
    out = sr.engine_arm(root, "s1", sr.save_rule(root, rule(root)), matrix(root), use="raw", origin=None)
    assert out["refusal"]["reason"] == "pts_origin_unverified"
    bad = {"ok": False, "reasons": ["the playback copy starts at 2.000 s, not 0"]}
    assert "2.000 s" in sr.engine_arm(root, "s1", sr.save_rule(root, rule(root)), matrix(root),
                                      use="raw", origin=bad)["refusal"]["detail"]


def test_a_rule_for_another_codebook_version_is_refused(root):
    other = annotation_store.save_codebook(root, {**CODEBOOK, "items": ITEMS[:35]})
    r = sr.save_rule(root, rule(root, codebook_version=other["content_hash"]))
    assert sr.engine_arm(root, "s1", r, matrix(root), use="raw", origin=OK)["refusal"]["reason"] == "wrong_codebook_version"


def test_a_session_without_a_recording_clock_is_refused(tmp_path):
    browser = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0, uncertainty_ms=0.0, n_anchors=0)
    write_session(tmp_path, "s1", solution=browser)
    with pytest.raises(sr.Refused, match="no_recording"):
        sr.recording_clock(tmp_path, "s1")


def test_two_runs_of_one_source_with_different_parameters_are_refused(tmp_path):
    annotation_store.save_codebook(tmp_path, CODEBOOK)
    write_session(tmp_path, "s1", extra_params={"threshold": 0.3})
    with pytest.raises(sr.Refused, match="ambiguous_fit"):
        sr.predict(tmp_path, "s1", rule(tmp_path), ITEMS)


# ---------------------------------------------------------------------------
# the recording's zero
# ---------------------------------------------------------------------------

def _clip(path, offset_s=0.0):
    import imageio_ffmpeg
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", "testsrc=duration=1:size=64x48:rate=30", "-c:v", "mpeg4"]
    if offset_s:
        cmd += ["-output_ts_offset", str(offset_s)]
    subprocess.run(cmd + [str(path)], check=True)
    return path


def test_a_recording_that_starts_at_zero_passes_and_one_that_does_not_is_refused(tmp_path):
    zero, late = _clip(tmp_path / "a.mkv"), _clip(tmp_path / "b.mkv", offset_s=2.0)
    assert sr.pts_origin(zero, zero)["ok"]
    got = sr.pts_origin(zero, late)
    assert not got["ok"] and "playback copy starts at 2.000 s" in got["reasons"][0]
