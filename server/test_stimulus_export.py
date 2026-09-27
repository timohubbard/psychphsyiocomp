"""Per-stimulus gaze, AOIs on the picture, heatmaps, and the audited export zip."""

from __future__ import annotations

import gzip
import json
import zipfile

import numpy as np
import pytest

import aoi_store
import export
import pseudonym
from alignment import ClockSolution
from aoi import AOI, AOISet
from engine_contract import Chunk, EventRow, QualityRow, SignalRow
from stimulus_summary import heatmap, session_summary
from study import content_hash
from tables import CanonicalWriter, SessionContext, read_session

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0,
                       uncertainty_ms=0.0, n_anchors=0)
RECT = {"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.5}
STUDY = {
    "study_id": "st", "name": "Stim", "version": "1.0.0",
    "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk"},
    "consent_tiers": ["features_only"], "modalities": ["gaze", "face"],
    "calibration": {"n_points": 13},
    "analysis": {"aoi_pad_deg": 0.0, "epochs": [
        {"name": "smile", "event_type": "stimulus", "channels": ["blendshape.s"],
         "pre_ms": 500, "post_ms": 1500, "baseline_ms": [-500, 0]}]},
    "tasks": [{"type": "stimuli", "items": [
        {"stimulus_id": "pic", "kind": "image", "src": "stimuli/scene_left.png",
         "sha256": "629b0f1ebc823f79ca8138bc1c7d61768a8fcc7e4edf20a41dba736b903b2dc1",
         "duration_ms": 2000}]}],
}


def write(out, sid, *, pid="p_abc", geometry=True, gaze_at=(0.2, 0.2)):
    w = CanonicalWriter(out, SessionContext(sid, pid, "st"))
    w.set_session_metadata({
        "study": {"study_id": "st", "study_content_hash": content_hash(STUDY),
                  "audience": "participants"},
        "achieved_fps": 30.0,
        "geometry": ({"ok": True, "viewing_distance_mm": 500.0, "px_per_mm": 3.78}
                     if geometry else {"ok": False}),
    })
    ts = np.arange(0.0, 4000.0, 1000 / 30)
    gaze = [SignalRow(stream="gaze", channel=ch, native_clock_id="performance.now",
                      native_ts=float(t), value=v, reliability_tier="moderate")
            for t in ts for ch, v in (("gaze.x", gaze_at[0]), ("gaze.y", gaze_at[1]))]
    w.add_chunks([Chunk(signals=tuple(gaze),
                        events=(EventRow(event_type="gaze_fixation", native_clock_id="performance.now",
                                         onset_native_ts=1100.0, offset_native_ts=1600.0,
                                         stimulus_id=None,
                                         metadata={"x": gaze_at[0], "y": gaze_at[1]}),))],
                 source="gaze.ridge@0.1.0+server-fit", params={}, solution=MASTER)
    face = [SignalRow(stream="face", channel="blendshape.s", native_clock_id="performance.now",
                      native_ts=float(t), value=(0.8 if t >= 1000 else 0.1),
                      reliability_tier="moderate") for t in ts]
    w.add_chunks([Chunk(signals=tuple(face),
                        events=(EventRow(event_type="stimulus", native_clock_id="performance.now",
                                         onset_native_ts=1000.0, offset_native_ts=3000.0,
                                         stimulus_id="pic",
                                         metadata={"rect_norm": RECT,
                                                   "stage_px": {"width": 1000, "height": 1000},
                                                   "presentation": "stim_01_pic"}),),
                        quality=(QualityRow(stream="face", metric="face_detect_rate",
                                            window_start_native_ts=0.0, window_end_native_ts=1.0,
                                            value=1.0),))],
                 source="face.mediapipe_blendshapes@0.1.0+browser-live", params={}, solution=MASTER)
    w.close()


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out"
    aoi_store.save(o, AOISet("pic_regions", "x", (
        AOI("topleft", "rect", (0.0, 0.0, 0.5, 0.5)),
        AOI("bottomright", "rect", (0.5, 0.5, 1.0, 1.0))), stimulus_id="pic"))
    return o


def _row(out, sid):
    return read_session(out, sid, "sessions").to_pylist()[0]


def test_gaze_and_aoi_metrics_are_computed_on_the_picture(out):
    write(out, "s1")
    r = session_summary(out, _row(out, "s1"), pad_deg=0.0)
    g = r["gaze"][0]
    assert g["stimulus_id"] == "pic" and g["share_on_stimulus"] == 1.0 and g["n_fixations"] == 1
    by = {a["aoi_id"]: a for a in r["aoi"]}
    # (0.2, 0.2) on the stage is (0.25, 0.25) on the picture: in topleft only.
    assert by["topleft"]["n_fixations"] == 1
    assert by["topleft"]["time_to_first_fixation_ms"] == pytest.approx(100.0)
    assert by["bottomright"]["n_fixations"] == 0
    assert by["bottomright"]["time_to_first_fixation_ms"] is None, "never entered is not zero"


def test_aoi_metrics_are_refused_without_a_declared_padding(out):
    write(out, "s1")
    r = session_summary(out, _row(out, "s1"), pad_deg=None)
    assert {a["refusal"] for a in r["aoi"]} == {"no_aoi_pad_deg"}


def test_the_heatmap_peaks_where_gaze_was_on_the_picture(out):
    write(out, "s1")
    density, n, refusals = heatmap(out, [_row(out, "s1")], "pic", grid=(40, 40), sigma_deg=0.5)
    assert n == 1 and refusals == []
    assert density.sum() == pytest.approx(1.0)
    y, x = np.unravel_index(np.argmax(density), density.shape)
    assert (x, y) == (10, 10), "gaze at (0.25, 0.25) of the picture"


def test_a_participant_without_geometry_is_refused_not_blurred_in_pixels(out):
    write(out, "s1", geometry=False)
    density, n, refusals = heatmap(out, [_row(out, "s1")], "pic")
    assert density is None and n == 0 and refusals[0]["reason"] == "no_geometry"


def test_each_participant_weighs_the_same_in_a_heatmap(out):
    write(out, "a", gaze_at=(0.2, 0.2))     # picture (0.25, 0.25)
    write(out, "b", gaze_at=(0.4, 0.4))     # picture (0.75, 0.75)
    density, n, _ = heatmap(out, [_row(out, "a"), _row(out, "b")], "pic",
                            grid=(40, 40), sigma_deg=0.5)
    assert n == 2
    assert density[10, 10] == pytest.approx(density[30, 30], rel=1e-6)


def test_the_export_zip_holds_the_cohort_and_nothing_it_must_not(out, tmp_path):
    write(out, "s1")
    z = tmp_path / "x.zip"
    summary = export.build(out, STUDY, z)
    assert summary["sessions"] == 1
    names = set(zipfile.ZipFile(z).namelist())
    for expected in ("provenance.json", "csv/sessions.csv", "csv/attrition.csv", "csv/events.csv",
                     "csv/signals/s1.csv.gz", "csv/epochs_smile.csv", "csv/stimulus_gaze.csv",
                     "csv/stimulus_aoi.csv", "csv/stimulus_face.csv", "heatmaps/pic.csv",
                     "heatmaps/pic.png", "bids/dataset_description.json", "bids/participants.tsv"):
        assert expected in names, expected
    assert any(n.endswith("_events.tsv") for n in names)
    assert not any(n.endswith((".webm", ".mp4", ".wav")) or "identifiers" in n for n in names)
    prov = json.loads(zipfile.ZipFile(z).read("provenance.json"))
    assert prov["protocol_content_hash"] == content_hash(STUDY) and prov["analysis_hash"]
    face = zipfile.ZipFile(z).read("csv/stimulus_face.csv").decode()
    assert "blendshape.s" in face


def test_an_export_carrying_a_raw_panel_id_is_refused_and_not_written(out, tmp_path):
    pseudonym.link(out, {"platform": "prolific", "participant": "RAWPANELID123"}, "s1")
    write(out, "s1", pid="RAWPANELID123")        # as if pseudonymisation had been skipped
    z = tmp_path / "x.zip"
    with pytest.raises(export.ExportRefused, match="raw panel identifier"):
        export.build(out, STUDY, z)
    assert not z.exists()


def test_signals_in_the_export_are_the_tables_rows(out, tmp_path):
    write(out, "s1")
    z = tmp_path / "x.zip"
    export.build(out, STUDY, z)
    csv_text = gzip.decompress(zipfile.ZipFile(z).read("csv/signals/s1.csv.gz")).decode()
    assert csv_text.count("\n") - 1 == read_session(out, "s1").num_rows


def test_the_cohort_page_sees_the_cohort_the_export_writes(out):
    """The app route uses the same select/epochs/heatmap as the CLI and the
    export, so the page cannot show a different cohort from the zip."""
    import app
    write(out, "s1")
    v = app.cohort_view(out, STUDY, include_developer=False, allow_mixed=False)
    assert [f["remaining"] for f in v["funnel"]] == [1, 1, 1]
    assert v["epochs"][0]["n_epochs"] == 1 and "blendshape.s" in v["epochs"][0]["curves"]
    assert v["heatmaps"][0]["stimulus_id"] == "pic" and v["heatmaps"][0]["grid"] is not None
    # What the page needs to draw the density over the picture, as the export does.
    assert (v["heatmaps"][0]["src"], v["heatmaps"][0]["kind"]) == ("stimuli/scene_left.png", "image")
    assert v["analysis_hash"] and v["content_hash"] == content_hash(STUDY)
