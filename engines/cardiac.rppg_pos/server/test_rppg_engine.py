"""The rPPG engine on video: a synthetic face whose skin pulses at a known rate.

The maths is tested on traces in server/test_rppg.py. This checks the part
that touches pixels: the landmarker finds the face, the forehead and cheek
mask lands on skin, and the colour change survives to a rate. The clip is
written LOSSLESSLY (FFV1) — a lossy codec at test sizes would erase a pulse of
a few levels, which is §2.4's compression finding, not a bug in the engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine_contract import describe_video
from engine_contract.loader import load_engine_module
from synthetic_face import draw_face

MODEL = Path(__file__).resolve().parents[3] / "models" / "face_landmarker.task"
MANIFEST = Path(__file__).resolve().parents[1] / "engine.manifest.json"
eng = load_engine_module("cardiac.rppg_pos")


def pulsing_clip(path: Path, bpm: float = 75.0, seconds: float = 24.0, fps: float = 30.0) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), fps, (640, 480))
    if not writer.isOpened():
        pytest.skip("this OpenCV build cannot write FFV1")
    rng = np.random.default_rng(0)
    for k in range(int(seconds * fps)):
        p = np.sin(2 * np.pi * (bpm / 60) * k / fps)
        # (B, G, R): the pulsatile vector, a few levels at most, plus sensor noise.
        frame = draw_face(skin_delta=(1.6 * p, 2.4 * p, 1.0 * p), mouth_open=0.1)
        frame = np.clip(frame.astype(np.int16) + rng.integers(-1, 2, frame.shape), 0, 255).astype(np.uint8)
        writer.write(frame)
    writer.release()
    return path


@pytest.mark.skipif(not MODEL.exists(), reason="face landmarker model not fetched (npm run models)")
def test_a_pulsing_face_gives_its_rate(tmp_path):
    clip = pulsing_clip(tmp_path / "pulse.avi")
    engine = eng.RppgPOS(MODEL)
    media = describe_video(clip)
    assert engine.probe(media).eligible
    [chunk] = list(engine.run(media, {}))
    hr = [s.value for s in chunk.signals if s.channel == "cardiac.hr_bpm"]
    q = {r.metric: r.value for r in chunk.quality}
    assert q["face_found_rate"] > 0.9
    assert hr, "no window passed"
    assert np.median(hr) == pytest.approx(75, abs=3)
    assert all(s.native_clock_id == "video_pts" for s in chunk.signals)


@pytest.mark.skipif(not MODEL.exists(), reason="face landmarker model not fetched (npm run models)")
def test_a_still_face_gets_no_rate(tmp_path):
    clip = pulsing_clip(tmp_path / "still.avi", bpm=0.0)
    [chunk] = list(eng.RppgPOS(MODEL).run(describe_video(clip), {}))
    hr = [s for s in chunk.signals if s.channel == "cardiac.hr_bpm"]
    snr = [s.value for s in chunk.signals if s.channel == "cardiac.snr_db"]
    assert len(hr) <= len(snr) * 0.2          # noise alone rarely clears the gate
    assert snr, "every window's SNR is still reported"


def test_no_face_means_no_skin_and_a_roi_lost_event():
    engine = eng.RppgPOS(MODEL) if MODEL.exists() else pytest.skip("no model")
    ts = np.arange(0, 20000, 33.3)
    rgb = np.full((len(ts), 3), np.nan)
    luma = np.full(len(ts), np.nan)
    [chunk] = list(engine.from_trace(ts, rgb, luma, {}))
    assert not [s for s in chunk.signals if s.channel == "cardiac.hr_bpm"]
    assert [e.event_type for e in chunk.events] == ["roi_lost"]
    assert {r.metric: r.value for r in chunk.quality}["face_found_rate"] == 0.0


def test_the_mask_covers_forehead_and_cheeks_only():
    class P:
        def __init__(self, x, y):
            self.x, self.y = x, y
    lm = [P(0.5, 0.5)] * 478
    lm = list(lm)
    for region, (cx, cy) in zip(eng.REGIONS, ((0.5, 0.25), (0.35, 0.55), (0.65, 0.55))):
        for k, i in enumerate(region):
            a = 2 * np.pi * k / len(region)
            lm[i] = P(cx + 0.06 * np.cos(a), cy + 0.04 * np.sin(a))
    m = eng.skin_mask(lm, 200, 200)
    assert m is not None
    assert m[50, 100] == 255 and m[110, 70] == 255 and m[110, 130] == 255   # forehead, cheeks
    assert m[100, 100] == 0 and m[160, 100] == 0                            # nose, mouth


def test_the_manifest_says_what_it_does_not_claim():
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert raw["modality"] == "cardiac"
    tiers = {s["channel"]: s["reliability_tier"] for s in raw["outputs"]["signals"]}
    assert tiers["cardiac.hr_bpm"] == "unvalidated"
    assert "NOT emitted" in raw["capability_notes"]["no_hrv"]
    assert "rPPG-Toolbox" in raw["license"]["notes"]
