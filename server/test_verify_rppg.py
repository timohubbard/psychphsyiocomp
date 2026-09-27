"""The strap comparison: planted camera errors come back as the errors they were."""

from __future__ import annotations

import json

import numpy as np
import pytest

from alignment import ClockSolution
from engine_contract import Chunk, SignalRow
from pipeline import SessionBundle, _load_browser_chunks, process_session
from rppg import analyse
from tables import CanonicalWriter, SessionContext, read_session
from verify_rppg import (REFERENCE_SOURCE, Pair, agreement, by_snr, camera_windows, load_session,
                         reference_bpm, suggest_gate)

CAMERA = "cardiac.rppg_pos@0.1.0+server-batch"


def trace(bpm=72.0, seconds=60.0, fps=30.0, noise=0.0, seed=0):
    """A per-frame skin colour trace carrying a pulse, as the engine extracts it."""
    rng = np.random.default_rng(seed)
    ts = np.arange(0, seconds * 1000, 1000 / fps)
    p = np.sin(2 * np.pi * bpm / 60 * ts / 1000)
    rgb = np.column_stack([150 + 0.4 * p, 110 + 0.8 * p, 90 + 0.3 * p]) + rng.normal(0, noise, (len(ts), 3))
    return ts, rgb, np.full(len(ts), 120.0)


def strap(bpm=72.0, seconds=60.0, rr=True):
    beat = 60000 / bpm
    beats = np.arange(beat, seconds * 1000, beat)
    hr_ts = np.arange(1000, seconds * 1000, 1000.0)
    return (hr_ts, np.full(len(hr_ts), bpm), beats if rr else np.array([]),
            np.full(len(beats), beat) if rr else np.array([]))


def camera_from(ts, rgb, luma):
    waves, windows = analyse(ts, rgb, luma)
    grid = np.concatenate([g for g, _ in waves])
    bvp = np.concatenate([b for _, b in waves])
    return camera_windows(grid, bvp, np.array([w.center_ms for w in windows]),
                          np.array([w.luma for w in windows]))


def test_a_camera_that_agrees_has_no_bias():
    from verify_rppg import pairs_for
    pairs = pairs_for("s", camera_from(*trace()), *strap())
    a = agreement(pairs)
    assert a["n"] >= 20
    assert abs(a["bias"]) < 1.0 and a["within_5"] == 1.0


def test_a_planted_offset_is_reported_as_bias_not_hidden():
    from verify_rppg import pairs_for
    pairs = pairs_for("s", camera_from(*trace(bpm=80)), *strap(bpm=72))
    a = agreement(pairs)
    assert a["bias"] == pytest.approx(8, abs=1.0)
    assert a["within_5"] == 0.0


def test_rr_intervals_are_preferred_to_the_straps_smoothed_rate():
    hr_ts, _, rr_ts, rr = strap(bpm=60)
    stale = np.full(len(hr_ts), 90.0)            # the firmware's lagging average
    assert reference_bpm(30000, hr_ts, stale, rr_ts, rr) == pytest.approx(60)
    assert reference_bpm(30000, hr_ts, stale, np.array([]), np.array([])) == pytest.approx(90)


def test_a_window_the_strap_did_not_cover_is_not_compared():
    hr_ts, hr, rr_ts, rr = strap(seconds=20)
    assert reference_bpm(10000, hr_ts, hr, rr_ts, rr) is not None
    assert reference_bpm(22000, hr_ts, hr, rr_ts, rr) is None       # half the window is after it stopped


def test_limits_of_agreement_are_bias_plus_minus_1_96_sd():
    pairs = [Pair("s", i, 70 + e, 70, 5.0, 100, True) for i, e in enumerate([-2, 0, 2, 4, -4])]
    a = agreement(pairs)
    sd = np.std([-2, 0, 2, 4, -4], ddof=1)
    assert a["bias"] == 0 and a["loa_high"] == pytest.approx(1.96 * sd)
    assert a["mae"] == pytest.approx(2.4)


def test_the_snr_table_puts_every_window_in_exactly_one_bin():
    pairs = [Pair("s", i, 70, 70, snr, 100, snr >= 0) for i, snr in enumerate([-9, -3, -0.1, 0, 2.9, 3, 6, 40])]
    rows = by_snr(pairs)
    assert sum(a["n"] for _, a in rows) == len(pairs)
    assert [a["n"] for _, a in rows] == [1, 2, 2, 1, 2]


def test_no_gate_is_suggested_from_one_session():
    pairs = [Pair("s", i, 70, 70, 5.0, 100, True) for i in range(500)]
    gate, why = suggest_gate(pairs)
    assert gate is None and "3 sessions" in why


def test_the_gate_is_the_lowest_snr_where_the_errors_become_small():
    rng = np.random.default_rng(1)
    pairs = []
    for k in range(600):
        snr = rng.uniform(-6, 12)
        err = rng.normal(0, 12) if snr < 2 else rng.normal(0, 1.5)
        pairs.append(Pair(f"s{k % 3}", k, 70 + err, 70, snr, 100, snr >= 0))
    gate, _ = suggest_gate(pairs)
    assert gate in (2.0, 3.0)


def test_the_strap_goes_through_the_pipeline_and_back(tmp_path):
    """Browser chunk -> process_session -> tables -> load_session, with the camera
    rows written beside it the way the engine would."""
    hr_ts, hr, rr_ts, rr = strap(seconds=60)
    ref_rows = [{"stream": "reference", "channel": "reference.hr_bpm", "native_clock_id": "performance.now",
                 "native_ts": float(t), "value": float(v), "reliability_tier": "high"} for t, v in zip(hr_ts, hr)]
    ref_rows += [{"stream": "reference", "channel": "reference.rr_ms", "native_clock_id": "performance.now",
                  "native_ts": float(t), "value": float(v), "reliability_tier": "high"} for t, v in zip(rr_ts, rr)]
    p = tmp_path / "browser_chunks.json"
    p.write_text(json.dumps([{"source": REFERENCE_SOURCE, "signals": ref_rows}]))
    chunks, sources = _load_browser_chunks(p)
    meta = {"session_id": "s1", "participant_id": "p1", "study_id": "d",
            "consent": {"tier": "features_only", "retentionDays": 30}}
    bundle = SessionBundle(session_id="s1", participant_id="p1", study_id="d", browser_chunks=chunks,
                           browser_chunk_sources=sources, metadata=meta)

    ts, rgb, luma = trace()
    waves, windows = analyse(ts, rgb, luma)

    def camera_stage(writer, bundle, solution):
        master = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0, uncertainty_ms=0.0, n_anchors=0)
        rows = [SignalRow(stream="cardiac", channel="cardiac.bvp", native_clock_id="performance.now",
                          native_ts=float(t), value=float(v), reliability_tier="unvalidated")
                for g, b in waves for t, v in zip(g, b)]
        rows += [SignalRow(stream="cardiac", channel="cardiac.skin_luma", native_clock_id="performance.now",
                           native_ts=w.center_ms, value=w.luma, reliability_tier="high") for w in windows]
        writer.add_chunks([Chunk(signals=tuple(rows))], source=CAMERA, params={}, solution=master)

    summary = process_session(bundle, [], tmp_path / "out", extra_stages=[("camera", camera_stage)])
    assert REFERENCE_SOURCE in summary["sources"]
    pairs, refusal = load_session(tmp_path / "out", "s1")
    assert refusal is None
    a = agreement(pairs)
    assert a["n"] >= 20 and abs(a["bias"]) < 1.0


def test_a_session_without_a_strap_is_refused(tmp_path):
    w = CanonicalWriter(tmp_path, SessionContext("s1", "p", "st"))
    w.set_session_metadata({})
    w.close()
    pairs, refusal = load_session(tmp_path, "s1")
    assert pairs is None and refusal.startswith("no_reference")
