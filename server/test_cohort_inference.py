"""A declared contrast, end to end through real session tables.

test_inference.py holds the statistics to known answers on arrays. This checks
the plumbing around them: sessions written by the canonical writer, selected
by cohort.select, cut by cohort.epochs, contrasted by the app's cohort view and
by the export — so the page and the zip report the same test on the same
participants.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import zipfile

import numpy as np
import pytest

import app
import export
from alignment import ClockSolution
from engine_contract import Chunk, EventRow, SignalRow
from study import content_hash, validate_study
from tables import CanonicalWriter, SessionContext

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0,
                       uncertainty_ms=0.0, n_anchors=0)
STUDY = {
    "study_id": "arms", "name": "Arms", "version": "1.0.0",
    "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk"},
    "consent_tiers": ["features_only"], "modalities": ["face"],
    "conditions": {"arms": ["warm", "cold"]},
    "analysis": {
        "epochs": [{"name": "smile", "event_type": "stimulus", "channels": ["blendshape.s"],
                    "pre_ms": 500, "post_ms": 1500, "baseline_ms": [-500, 0]}],
        "contrasts": [{"name": "warm_vs_cold", "epochs": "smile", "channel": "blendshape.s",
                       "arms": ["warm", "cold"], "window_ms": [300, 1200],
                       "n_permutations": 2000, "seed": 11, "cluster": {"p_threshold": 0.05}}],
    },
}


def write(out, sid, pid, arm, effect, rng):
    w = CanonicalWriter(out, SessionContext(sid, pid, "arms"))
    w.set_session_metadata({"study": {"study_id": "arms", "study_content_hash": content_hash(STUDY),
                                      "audience": "participants"}, "condition": arm})
    ts = np.arange(0.0, 6000.0, 1000 / 30)
    onsets = (1000.0, 3500.0)
    def val(t):
        on = any(o + 300 <= t <= o + 1200 for o in onsets)
        return 0.1 + (effect if on else 0.0) + rng.normal(0, 0.05)
    face = [SignalRow(stream="face", channel="blendshape.s", native_clock_id="performance.now",
                      native_ts=float(t), value=float(val(t)), reliability_tier="moderate") for t in ts]
    events = tuple(EventRow(event_type="stimulus", native_clock_id="performance.now",
                            onset_native_ts=o, offset_native_ts=o + 2000, stimulus_id=f"pic{k}",
                            metadata={}) for k, o in enumerate(onsets))
    w.add_chunks([Chunk(signals=tuple(face), events=events)],
                 source="face.mediapipe_blendshapes@0.1.0+browser-live", params={}, solution=MASTER)
    w.close()


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out"
    rng = np.random.default_rng(3)
    for i in range(6):
        write(o, f"w{i}", f"p_w{i}", "warm", 0.3, rng)
        write(o, f"c{i}", f"p_c{i}", "cold", 0.0, rng)
    return o


def test_the_plan_is_a_valid_study():
    assert validate_study(STUDY).ok, validate_study(STUDY).reasons


def test_the_cohort_view_reports_the_contrast_on_participant_means(out):
    v = app.cohort_view(out, STUDY, include_developer=False, allow_mixed=False)
    ep = v["epochs"][0]
    assert ep["averaging"] == "mean of participant means" and ep["n_participants"] == 12
    assert ep["n_epochs"] == 24        # two stimuli each — but twelve people
    [c] = v["contrasts"]
    assert c["refusal"] is None and c["n"] == {"warm": 6, "cold": 6}
    assert c["window"]["p"] < 0.01 and c["window"]["diff"] > 0.2
    assert any(k["significant"] for k in c["cluster"]["clusters"])
    assert set(c["curves"]) == {"warm", "cold"}


def test_the_export_carries_the_same_test_and_the_model_to_run_next(out, tmp_path):
    z = tmp_path / "x.zip"
    export.build(out, STUDY, z)
    with zipfile.ZipFile(z) as f:
        names = set(f.namelist())
        assert {"csv/contrasts.csv", "csv/clusters.csv", "csv/participant_epochs_smile.csv",
                "analysis/warm_vs_cold.R"} <= names
        [row] = list(csv.DictReader(io.StringIO(f.read("csv/contrasts.csv").decode())))
        r_code = f.read("analysis/warm_vs_cold.R").decode()
    view = app.cohort_view(out, STUDY, include_developer=False, allow_mixed=False)["contrasts"][0]
    assert float(row["p"]) == pytest.approx(view["window"]["p"])      # page and zip agree
    assert row["analysis_hash"] and row["seed"] == "11"
    assert "GENERATED, NOT RUN" in r_code and row["analysis_hash"] in r_code
    assert "lmer(" in r_code and "bam(" in r_code
    if shutil.which("Rscript"):
        p = tmp_path / "m.R"
        p.write_text(r_code, encoding="utf-8")
        subprocess.run(["Rscript", "-e", f"invisible(parse('{p.as_posix()}'))"], check=True)
