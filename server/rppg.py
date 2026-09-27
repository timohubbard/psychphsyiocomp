"""Pulse from facial skin colour (remote photoplethysmography) — the maths core.

Pure functions over arrays, so the part that can be silently wrong is testable
without a face, a model or a video; engines/cardiac.rppg_pos only extracts the
per-frame skin colour and hands it here.

**POS, not a trained network.** Wang, den Brinker, Stuijk & de Haan (2017),
"Algorithmic principles of remote PPG", IEEE TBME 64(7). Each short window of
the RGB trace is normalised by its own mean (removing the skin's colour and the
lighting's level) and projected onto the plane orthogonal to the skin tone,
where blood-volume change and specular/motion change separate; the two
projections are combined in the ratio of their spreads. It has no weights,
so there is no training set to be out of distribution to — REPORT.md §2.4's
dominant failure mode — and the largest in-the-wild validation it cites
(Woelk et al. 2026, n=77) measured POS at MAE 1.67 bpm against a reference.

**Its failure modes are handled by refusing, not by smoothing.**
- Compression can erase the pulse (§2.4: worse than guessing 75 bpm on
  heavily compressed video). So each window's spectrum is scored — SNR, after
  de Haan & Jeanne (2013): power at the peak and its first harmonic against
  the rest of the heart-rate band — and a rate is emitted only where the peak
  stands above everything else.
- Error rises on darker skin in dim light, and the gap closes at luminance
  >= 30 (§2.5). The skin region's own luminance is measured per window and
  gates the rate the same way.
- Heart-rate VARIABILITY is not emitted. §2.4: rPPG HRV is usable for group
  comparisons at best, never per participant.

The band (0.7-4 Hz, 42-240 bpm) and the windows are the literature's usual
choices; they are parameters, recorded with every run.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from respiration import bandpass

HR_BAND_HZ = (0.7, 4.0)
RATE_HZ = 30.0
POS_WINDOW_S = 1.6
MIN_SNR_DB = 0.0
MIN_LUMA = 30.0
MAX_GAP_MS = 500.0


def uniform(ts_ms: np.ndarray, rgb: np.ndarray, *, rate_hz: float = RATE_HZ,
            max_gap_ms: float = MAX_GAP_MS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Resample an irregular per-frame trace (any number of columns) onto a uniform grid,
    per unbroken segment.

    A MediaRecorder video's frame times are not regular, and a spectrum of an
    irregular series is not the spectrum of the pulse. Gaps longer than
    `max_gap_ms` (face lost, frames dropped) split the trace: interpolating
    across them would invent half a second of pulse.
    """
    order = np.argsort(ts_ms)
    ts, rgb = np.asarray(ts_ms, float)[order], np.asarray(rgb, float)[order]
    ok = ~np.isnan(rgb).any(axis=1) & ~np.isnan(ts)
    ts, rgb = ts[ok], rgb[ok]
    segments = []
    if len(ts) < 2:
        return segments
    breaks = np.where(np.diff(ts) > max_gap_ms)[0]
    starts = np.concatenate([[0], breaks + 1])
    ends = np.concatenate([breaks + 1, [len(ts)]])
    step = 1000.0 / rate_hz
    for a, b in zip(starts, ends):
        if b - a < 2:
            continue
        grid = np.arange(ts[a], ts[b - 1], step)
        if len(grid) < 2:
            continue
        cols = [np.interp(grid, ts[a:b], rgb[a:b, k]) for k in range(rgb.shape[1])]
        segments.append((grid, np.stack(cols, axis=1)))
    return segments


def pos(rgb: np.ndarray, rate_hz: float = RATE_HZ, window_s: float = POS_WINDOW_S) -> np.ndarray:
    """The POS blood-volume-pulse signal from an (n, 3) RGB trace, overlap-added."""
    rgb = np.asarray(rgb, float)
    n = len(rgb)
    w = int(round(window_s * rate_hz))
    out = np.zeros(n)
    if n < w or w < 2:
        return out
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for t in range(n - w + 1):
        c = rgb[t:t + w].T
        mean = c.mean(axis=1, keepdims=True)
        if np.any(mean <= 0):
            continue
        s = proj @ (c / mean)
        sd1 = s[1].std()
        h = s[0] + (s[0].std() / sd1 if sd1 > 0 else 0.0) * s[1]
        out[t:t + w] += h - h.mean()
    return out


def spectrum_peak(x: np.ndarray, rate_hz: float = RATE_HZ,
                  band: tuple[float, float] = HR_BAND_HZ) -> tuple[float | None, float | None]:
    """(peak frequency in Hz, SNR in dB) of one window.

    SNR after de Haan & Jeanne (2013): power at the peak and at its first
    harmonic, against the rest of the band. "At the peak" is the window's own
    main lobe, ±2/T for a Hann window of length T — ±0.2 Hz at 10 s. A fixed
    ±0.1 Hz (the paper's figure, for its longer windows) counted half of a
    pure tone's own energy as noise here; the first test run showed a clean
    planted pulse scoring 0-3 dB. The harmonic gets 0.1 Hz more, because the
    pulse wanders within a window and the harmonic wanders twice as far.
    White noise scores about -4 dB; a clear pulse, well above 0.
    """
    x = np.asarray(x, float)
    if len(x) < 8 or not np.isfinite(x).all() or x.std() == 0:
        return None, None
    x = (x - x.mean()) * np.hanning(len(x))
    nfft = 1 << int(np.ceil(np.log2(len(x) * 8)))
    p = np.abs(np.fft.rfft(x, nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / rate_hz)
    inband = (f >= band[0]) & (f <= band[1])
    if not inband.any():
        return None, None
    f0 = float(f[inband][np.argmax(p[inband])])
    lobe = 2.0 * rate_hz / len(x)
    sig = inband & ((np.abs(f - f0) <= lobe) | (np.abs(f - 2 * f0) <= lobe + 0.1))
    noise = inband & ~sig
    ps, pn = float(p[sig].sum()), float(p[noise].sum())
    if pn <= 0:
        return f0, float("inf")
    return f0, 10.0 * np.log10(ps / pn)


@dataclass
class HRWindow:
    center_ms: float
    hr_bpm: float | None
    snr_db: float | None
    luma: float
    passed: bool
    reason: str | None


def heart_rate_windows(grid_ms: np.ndarray, bvp: np.ndarray, luma: np.ndarray, *,
                       rate_hz: float = RATE_HZ, window_s: float = 10.0, step_s: float = 2.0,
                       min_snr_db: float = MIN_SNR_DB, min_luma: float = MIN_LUMA) -> list[HRWindow]:
    """A heart rate per window, or the reason there is none."""
    w, s = int(round(window_s * rate_hz)), max(1, int(round(step_s * rate_hz)))
    out = []
    for a in range(0, len(bvp) - w + 1, s):
        seg = bvp[a:a + w]
        f0, snr = spectrum_peak(seg, rate_hz)
        lum = float(np.mean(luma[a:a + w]))
        center = float(grid_ms[a + w // 2])
        reason = None
        if f0 is None:
            reason = "flat_signal"
        elif lum < min_luma:
            reason = "too_dark"
        elif snr < min_snr_db:
            reason = "low_snr"
        out.append(HRWindow(center, None if f0 is None else 60.0 * f0, snr, lum, reason is None, reason))
    return out


def analyse(ts_ms: np.ndarray, rgb: np.ndarray, luma: np.ndarray, *, rate_hz: float = RATE_HZ,
            window_s: float = 10.0, step_s: float = 2.0, min_snr_db: float = MIN_SNR_DB,
            min_luma: float = MIN_LUMA, pos_window_s: float = POS_WINDOW_S):
    """Everything from a per-frame trace: [(grid_ms, bvp)] per segment, and the HR windows."""
    stacked = np.column_stack([np.asarray(rgb, float), np.asarray(luma, float)])
    waves, windows = [], []
    for grid, cols in uniform(ts_ms, stacked, rate_hz=rate_hz):
        bvp = pos(cols[:, :3], rate_hz, pos_window_s)
        if len(bvp) >= int(rate_hz * 2):
            bvp = bandpass(bvp, rate_hz, HR_BAND_HZ)
        waves.append((grid, bvp))
        windows += heart_rate_windows(grid, bvp, cols[:, 3], rate_hz=rate_hz, window_s=window_s,
                                      step_s=step_s, min_snr_db=min_snr_db, min_luma=min_luma)
    return waves, windows
