"""Respiration from chest and shoulder motion — the signal-processing core.

A correction first, because it shapes everything: **iMotions' respiration is not
rPPG.** §2.4 establishes it is chest/shoulder-motion ROI tracking — an
image-processing pipeline detecting subtle chest movement, band-passed to
roughly 7.5-30 cycles per minute. That is architecturally distinct from, and far
more compression-robust than, facial rPPG for heart rate. They are two separate
engineering problems.

**This is the project's single biggest validation gap, and the code says so.**
After two dedicated research passes, no verified breaths-per-minute accuracy
figure against a chest belt, RIP or spirometry survived adversarial checking —
one specific figure was explicitly *refuted*. Exactly one algorithmic finding
survived:

    Of six chest/abdomen motion-extraction combinations, those using MULTIPLE
    1D or 2D motion profiles outperform single-combined-1D-profile approaches.

So the pipeline keeps the profiles separate for as long as possible and fuses
them late, and `rate_bpm` is withheld behind an explicit flag until a validation
study exists. A breathing rate is a number a clinician would recognise, and
emitting one this project cannot defend would be the most damaging thing it
could ship.

The waveform is the more valuable output anyway: it supports inhale-onset,
breath-hold and sigh events, none of which need a calibrated rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

#: Breathing band, in Hz. 0.125-0.5 Hz is 7.5-30 cycles per minute, matching
#: §2.4's description of iMotions' own band exactly. Wider would admit the
#: postural sway and head-nod frequencies that sit just below it.
RESP_BAND_HZ = (0.125, 0.5)

#: Output rate for the waveform. Far above the ~0.5 Hz Nyquist requirement, so
#: inhale-onset timing is not quantised by the output grid.
WAVEFORM_RATE_HZ = 25.0

#: Grid the ROI is divided into. §2.4's surviving finding is that multiple
#: profiles beat one combined profile, so the grid exists to be kept apart, not
#: averaged early.
GRID = (4, 4)

#: Minimum in-band power share for a cell to be considered periodic enough to
#: contribute. Chosen as a starting point, not from evidence — §2.4 provides no
#: number here, and pretending otherwise would be inventing a citation.
MIN_PERIODICITY = 0.15


def bandpass(x: np.ndarray, rate_hz: float,
             band: tuple[float, float] = RESP_BAND_HZ) -> np.ndarray:
    """Zero-phase band-pass over the breathing band.

    Zero-phase matters more here than it usually does. A causal filter delays
    the signal by a frequency-dependent amount, and the output of this engine is
    used to time inhale ONSETS against stimulus events on the master clock — a
    phase shift would move every breath relative to the thing that supposedly
    caused it, consistently and invisibly.

    Implemented by filtering forwards and backwards over a detrended, reflected
    signal rather than by calling scipy: the project does not otherwise depend on
    scipy, and an FFT-domain brick-wall over a reflected segment is both exactly
    zero-phase and easy to reason about at these lengths.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8:
        return np.zeros(n)

    # Remove the linear trend first. A participant slowly leaning forward puts a
    # ramp under the breathing signal, and a ramp has energy at every frequency
    # including inside the band.
    t = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(t, x, 1)
    detrended = x - (slope * t + intercept)

    # Reflect at both ends so the implicit circular wrap of an FFT does not
    # create a discontinuity, which would ring back into the band.
    pad = min(n, max(8, n // 2))
    padded = np.concatenate([detrended[pad:0:-1], detrended, detrended[-2:-pad - 2:-1]])

    spectrum = np.fft.rfft(padded)
    freqs = np.fft.rfftfreq(len(padded), d=1.0 / rate_hz)
    spectrum[(freqs < band[0]) | (freqs > band[1])] = 0.0

    return np.fft.irfft(spectrum, n=len(padded))[pad:pad + n]


def periodicity_index(x: np.ndarray, rate_hz: float,
                      band: tuple[float, float] = RESP_BAND_HZ) -> float:
    """In-band power as a share of total power, after detrending.

    This is what ranks one grid cell against another. A cell showing the
    participant's jumper moving with their breath has most of its energy inside
    the band; a cell showing a static bookshelf has none, and a cell showing an
    arm gesture has a broadband burst. All three look similar in amplitude and
    completely different here.
    """
    x = np.asarray(x, dtype=float)
    if len(x) < 8:
        return 0.0

    t = np.arange(len(x), dtype=float)
    slope, intercept = np.polyfit(t, x, 1)
    detrended = x - (slope * t + intercept)

    power = np.abs(np.fft.rfft(detrended)) ** 2
    freqs = np.fft.rfftfreq(len(detrended), d=1.0 / rate_hz)

    total = float(power[1:].sum())        # drop DC
    if total <= 0:
        return 0.0
    in_band = float(power[(freqs >= band[0]) & (freqs <= band[1])].sum())
    return in_band / total


@dataclass
class FusionResult:
    waveform: np.ndarray
    #: Which grid cells contributed, strongest first.
    cells_used: list[int] = field(default_factory=list)
    periodicity: list[float] = field(default_factory=list)
    refusal: str | None = None


def fuse_profiles(profiles: np.ndarray, rate_hz: float, *,
                  top_k: int = 4, min_periodicity: float = MIN_PERIODICITY,
                  band: tuple[float, float] = RESP_BAND_HZ) -> FusionResult:
    """Combine per-cell motion profiles into one respiration waveform.

    ``profiles`` is ``(n_cells, n_samples)``.

    LATE, AND ONLY THE PERIODIC CELLS. §2.4's one surviving algorithmic finding
    is that multiple motion profiles outperform a single combined 1D profile, so
    averaging the grid up front — the obvious implementation — is the specific
    thing the evidence says not to do. Cells are ranked by periodicity and only
    the best contribute.

    Sign alignment before averaging is the subtle part. Chest rise and shoulder
    rotation are not in phase, and a cell that moves down while another moves up
    will cancel it. Each contributing cell is correlated against the strongest
    one and flipped if it is anti-correlated, so opposed-but-real motion adds
    instead of destroying itself. That is the actual reason naive averaging loses
    the signal, rather than anything about noise.
    """
    profiles = np.atleast_2d(np.asarray(profiles, dtype=float))
    n_cells, n_samples = profiles.shape
    if n_samples < 8:
        return FusionResult(np.zeros(n_samples), refusal="too_short")

    filtered = np.vstack([bandpass(p, rate_hz, band) for p in profiles])
    scores = np.array([periodicity_index(p, rate_hz, band) for p in profiles])

    eligible = np.where(scores >= min_periodicity)[0]
    if len(eligible) == 0:
        return FusionResult(np.zeros(n_samples), periodicity=scores.tolist(),
                            refusal="no_periodic_cells")

    order = eligible[np.argsort(scores[eligible])[::-1]][:top_k]
    reference = filtered[order[0]]

    aligned = []
    for idx in order:
        cell = filtered[idx]
        if np.std(cell) < 1e-12 or np.std(reference) < 1e-12:
            continue
        # Flip anti-correlated cells rather than discarding them: an
        # out-of-phase cell carries the same breath, measured from the other
        # side of the body.
        sign = 1.0 if np.corrcoef(cell, reference)[0, 1] >= 0 else -1.0
        aligned.append(sign * cell / (np.std(cell) or 1.0))

    if not aligned:
        return FusionResult(np.zeros(n_samples), periodicity=scores.tolist(),
                            refusal="degenerate_cells")

    return FusionResult(
        waveform=np.mean(aligned, axis=0),
        cells_used=[int(i) for i in order],
        periodicity=scores.tolist(),
    )


@dataclass
class RateEstimate:
    bpm: float | None
    #: Cross-check from inter-peak intervals in the time domain.
    bpm_time_domain: float | None
    agreement: float | None
    confident: bool
    reason: str | None = None


def estimate_rate(waveform: np.ndarray, rate_hz: float,
                  band: tuple[float, float] = RESP_BAND_HZ,
                  *, max_disagreement_bpm: float = 2.0) -> RateEstimate:
    """Breathing rate, by two independent routes that must agree.

    The FFT peak and the median inter-peak interval fail differently: a spectral
    peak survives a couple of missed breaths but is pulled by any periodic
    artefact in band, while inter-peak timing tracks individual breaths but is
    wrecked by a single spurious peak. Requiring them to agree turns two weak
    estimators into one that knows when it is wrong.

    On disagreement it returns ``confident=False`` and no number, rather than
    picking a winner. §2.4 is unambiguous that no bpm figure from this class of
    method survived adversarial checking, so a disagreement is the expected
    outcome on hard input and should look like one.
    """
    x = np.asarray(waveform, dtype=float)
    if len(x) < 16 or np.std(x) < 1e-12:
        return RateEstimate(None, None, None, False, "waveform too short or flat")

    spectrum = np.abs(np.fft.rfft(x - x.mean()))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / rate_hz)
    in_band = (freqs >= band[0]) & (freqs <= band[1])
    if not in_band.any():
        return RateEstimate(None, None, None, False, "no spectral bins in band")

    peak_hz = float(freqs[in_band][np.argmax(spectrum[in_band])])
    bpm_fft = peak_hz * 60.0

    # Time domain: zero-crossings rising through the mean, which is more robust
    # on a band-limited signal than peak-picking on a noisy derivative.
    centred = x - x.mean()
    rising = np.where((centred[:-1] <= 0) & (centred[1:] > 0))[0]
    if len(rising) < 3:
        return RateEstimate(None, None, None, False,
                            "fewer than three breaths observed")

    intervals_s = np.diff(rising) / rate_hz
    bpm_time = float(60.0 / np.median(intervals_s)) if np.median(intervals_s) > 0 else None
    if bpm_time is None:
        return RateEstimate(None, None, None, False, "degenerate intervals")

    disagreement = abs(bpm_fft - bpm_time)
    confident = disagreement <= max_disagreement_bpm

    return RateEstimate(
        bpm=bpm_fft if confident else None,
        bpm_time_domain=bpm_time,
        agreement=float(disagreement),
        confident=confident,
        reason=None if confident
        else f"FFT {bpm_fft:.1f} and inter-breath {bpm_time:.1f} bpm disagree by "
             f"{disagreement:.1f}, above the {max_disagreement_bpm} bpm limit",
    )


@dataclass
class Confidence:
    """Everything a reader needs to decide whether to believe the waveform.

    Non-negotiable, per the build plan, and the reason is stark: no verified
    accuracy figure exists anywhere for this method. A calibrated confidence
    channel is what makes the output shippable at all — the claim is "here is
    the signal and how much to trust it", never "here is the breathing rate".
    """

    periodicity: float
    cells_used: int
    motion_artifact: bool
    roi_luminance: float | None
    effective_fps: float
    usable: bool
    reasons: list[str] = field(default_factory=list)


def assess_confidence(fusion: FusionResult, *, effective_fps: float,
                      roi_luminance: float | None,
                      gross_motion: float, gross_motion_limit: float = 3.0) -> Confidence:
    """Judge a fused waveform against everything known about how it was made."""
    reasons: list[str] = []

    best = max(fusion.periodicity) if fusion.periodicity else 0.0
    if fusion.refusal:
        reasons.append(fusion.refusal)
    if best < MIN_PERIODICITY:
        reasons.append(f"peak periodicity {best:.2f} below {MIN_PERIODICITY}")

    # Below ~2x the top of the band there are too few samples per breath for the
    # waveform shape to survive, let alone inhale-onset timing.
    if effective_fps < RESP_BAND_HZ[1] * 4:
        reasons.append(f"{effective_fps:.1f} fps is too low for the breathing band")

    artifact = gross_motion > gross_motion_limit
    if artifact:
        reasons.append("gross body motion dominates the ROI")

    # §2.5's luminance floor applies here too: this is a camera-based
    # physiological measurement, and the same bias argument holds.
    if roi_luminance is not None and roi_luminance < 30:
        reasons.append(f"ROI luminance {roi_luminance:.0f} below the fairness floor of 30")

    return Confidence(
        periodicity=best,
        cells_used=len(fusion.cells_used),
        motion_artifact=artifact,
        roi_luminance=roi_luminance,
        effective_fps=effective_fps,
        usable=not reasons,
        reasons=reasons,
    )


def resample(x: np.ndarray, src_hz: float, dst_hz: float = WAVEFORM_RATE_HZ) -> tuple[np.ndarray, float]:
    """Resample a waveform onto the output grid, returning ``(values, dt_ms)``."""
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or src_hz <= 0:
        return x, 1000.0 / dst_hz

    duration_s = len(x) / src_hz
    n_out = max(2, int(duration_s * dst_hz))
    src_t = np.arange(len(x)) / src_hz
    dst_t = np.linspace(0.0, duration_s, n_out, endpoint=False)
    return np.interp(dst_t, src_t, x), 1000.0 / dst_hz
