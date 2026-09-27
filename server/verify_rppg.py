"""Camera heart rate against a chest strap: how far off it is, and at what SNR.

    npm run verify:rppg                                  every session with a strap
    npm run verify:rppg -- --session s_x --plot out.png  one session, Bland-Altman plot

Read-only. The camera side is `cardiac.rppg_pos`; the reference is the strap
the capture page reads with `?hrstrap=1` (web/src/hrstrap.js). A session with
no strap is refused — there is nothing to compare against, and the engine's
own SNR is not evidence of accuracy.

**Every window, not just the ones that passed.** The engine stores a heart
rate only where a window clears its gate, but it stores the pulse wave for
every moment. This recomputes the ungated per-window rate from that wave with
the engine's own code (rppg.heart_rate_windows), so the table shows accuracy in
the SNR bins the gate currently throws away too. That is what the gate should
be chosen from: today's 0 dB is a literature default (de Haan & Jeanne), not a
number measured on this webcam and this codec.

**The reference.** Per window, 60000 / mean RR interval where the strap sends
RR intervals (from the ECG R-peak, exact over the window), else the median of
its reported rate (which most straps smooth over several seconds). A window is
compared only when the strap covered at least 80% of it.

Metrics, per Bland & Altman (1986): bias (camera − strap), 95% limits of
agreement (bias ± 1.96 SD), MAE, RMSE, and the share within 5 bpm, which is the
tolerance ANSI/CTA-2065 uses for consumer heart-rate monitors.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))

from rppg import MIN_LUMA, MIN_SNR_DB, RATE_HZ, heart_rate_windows  # noqa: E402

REFERENCE_SOURCE = "reference.ble_heart_rate@0.1.0+browser-live"
CAMERA_PREFIX = "cardiac.rppg_pos@"
WINDOW_S = 10.0
STEP_S = 2.0
MIN_COVERAGE = 0.8
WITHIN_BPM = 5.0
SNR_EDGES = (-np.inf, -3.0, 0.0, 3.0, 6.0, np.inf)

#: Before a gate is suggested: enough sessions that one lucky face does not set
#: it, and enough windows per bin that the MAE is not three numbers.
GATE_MIN_SESSIONS = 3
GATE_MIN_WINDOWS = 100
GATE_CANDIDATES = tuple(float(t) for t in range(-3, 10))
GATE_MIN_EDGE_WINDOWS = 20


@dataclass(frozen=True)
class Pair:
    session_id: str
    center_ms: float
    camera_bpm: float
    reference_bpm: float
    snr_db: float
    luma: float
    passed: bool          # would the engine's stored gate have emitted this window

    @property
    def error(self) -> float:
        return self.camera_bpm - self.reference_bpm


def reference_bpm(center_ms: float, hr_ts: np.ndarray, hr: np.ndarray,
                  rr_ts: np.ndarray, rr: np.ndarray, window_s: float = WINDOW_S) -> float | None:
    """The strap's rate over one window, or None where it did not cover it."""
    a, b = center_ms - window_s * 500, center_ms + window_s * 500
    need = MIN_COVERAGE * window_s * 1000
    inside = (rr_ts >= a) & (rr_ts <= b)
    if inside.sum() >= 3 and rr[inside].sum() >= need:
        return 60000.0 / float(np.mean(rr[inside]))
    inside = (hr_ts >= a) & (hr_ts <= b)
    if inside.sum() >= 3 and hr_ts[inside].max() - hr_ts[inside].min() >= need - 2000:
        return float(np.median(hr[inside]))
    return None


def split_segments(ts: np.ndarray, rate_hz: float = RATE_HZ) -> list[np.ndarray]:
    """Index arrays of unbroken runs in a resampled grid (a gap > 1.5 samples splits)."""
    if not len(ts):
        return []
    breaks = np.flatnonzero(np.diff(ts) > 1.5 * 1000 / rate_hz) + 1
    return np.split(np.arange(len(ts)), breaks)


def camera_windows(bvp_ts: np.ndarray, bvp: np.ndarray, luma_ts: np.ndarray, luma: np.ndarray,
                   min_snr_db: float = MIN_SNR_DB, min_luma: float = MIN_LUMA):
    """Every window's (center, bpm, snr, luma, passed), recomputed from the stored wave."""
    out = []
    for idx in split_segments(bvp_ts):
        # Luma is stored per window; the per-sample value for the recompute is
        # the nearest stored one, and the pass/fail uses the stored value itself.
        near = np.interp(bvp_ts[idx], luma_ts, luma) if len(luma_ts) else np.full(len(idx), np.inf)
        for w in heart_rate_windows(bvp_ts[idx], bvp[idx], near, window_s=WINDOW_S, step_s=STEP_S,
                                    min_snr_db=-np.inf, min_luma=-np.inf):
            if w.hr_bpm is None or not np.isfinite(w.snr_db):
                continue
            lum = float(np.interp(w.center_ms, luma_ts, luma)) if len(luma_ts) else float("nan")
            out.append((w.center_ms, w.hr_bpm, w.snr_db, lum,
                        bool(w.snr_db >= min_snr_db and lum >= min_luma)))
    return out


def pairs_for(session_id: str, camera, ref_hr_ts, ref_hr, ref_rr_ts, ref_rr) -> list[Pair]:
    out = []
    for c, bpm, snr, lum, passed in camera:
        ref = reference_bpm(c, ref_hr_ts, ref_hr, ref_rr_ts, ref_rr)
        if ref is not None:
            out.append(Pair(session_id, c, bpm, ref, snr, lum, passed))
    return out


def agreement(pairs: list[Pair]) -> dict[str, float]:
    if not pairs:
        return {"n": 0}
    e = np.array([p.error for p in pairs])
    sd = float(np.std(e, ddof=1)) if len(e) > 1 else float("nan")
    bias = float(np.mean(e))
    cam = np.array([p.camera_bpm for p in pairs])
    ref = np.array([p.reference_bpm for p in pairs])
    r = float(np.corrcoef(cam, ref)[0, 1]) if len(e) > 2 and cam.std() > 0 and ref.std() > 0 else float("nan")
    return {"n": len(e), "bias": bias, "loa_low": bias - 1.96 * sd, "loa_high": bias + 1.96 * sd,
            "mae": float(np.mean(np.abs(e))), "rmse": float(np.sqrt(np.mean(e ** 2))),
            "within_5": float(np.mean(np.abs(e) <= WITHIN_BPM)), "r": r}


def by_snr(pairs: list[Pair]) -> list[tuple[str, dict[str, float]]]:
    rows = []
    for lo, hi in zip(SNR_EDGES[:-1], SNR_EDGES[1:]):
        label = (f"< {hi:g} dB" if not np.isfinite(lo) else
                 f">= {lo:g} dB" if not np.isfinite(hi) else f"{lo:g} to {hi:g} dB")
        rows.append((label, agreement([p for p in pairs if lo <= p.snr_db < hi])))
    return rows


def suggest_gate(pairs: list[Pair], max_mae: float = WITHIN_BPM, min_within: float = 0.8):
    """The lowest SNR gate whose surviving windows are within 5 bpm on average and
    at least 80% of the time — or None with the reason there is not yet one.

    Both over everything kept AND over the margin (the 3 dB just above the
    gate). Pooled alone, the accurate high-SNR windows dilute the junk: on a
    planted set where everything under 2 dB was noise, a pooled test accepted
    -1 dB with a quarter of the kept windows wrong by ~10 bpm. Every window a
    gate admits at its edge should itself be usable.
    """
    sessions = {p.session_id for p in pairs}
    if len(sessions) < GATE_MIN_SESSIONS:
        return None, f"needs {GATE_MIN_SESSIONS} sessions with a strap; have {len(sessions)}"
    if len(pairs) < GATE_MIN_WINDOWS:
        return None, f"needs {GATE_MIN_WINDOWS} compared windows; have {len(pairs)}"
    for t in GATE_CANDIDATES:
        kept = [p for p in pairs if p.snr_db >= t and np.isfinite(p.luma) and p.luma >= MIN_LUMA]
        if len(kept) < GATE_MIN_WINDOWS // 2:
            break
        a = agreement(kept)
        edge = agreement([p for p in kept if p.snr_db < t + 3.0])
        if edge["n"] < GATE_MIN_EDGE_WINDOWS:
            continue
        ok = lambda s: s["mae"] <= max_mae and s["within_5"] >= min_within  # noqa: E731
        if ok(a) and ok(edge):
            return t, f"{a['n']} windows kept ({a['n'] / len(pairs):.0%}), MAE {a['mae']:.1f} bpm"
    return None, "no candidate gate meets MAE <= 5 bpm with 80% within 5 bpm"


def load_session(data: Path, session_id: str) -> tuple[list[Pair] | None, str | None]:
    """Pairs for one stored session, or (None, refusal)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    from tables import read_session

    sig = read_session(data, session_id, "signals")
    chans = pa.array(["cardiac.bvp", "cardiac.skin_luma", "reference.hr_bpm", "reference.rr_ms"])
    t = sig.filter(pc.is_in(sig["channel"], value_set=chans)).select(
        ["source", "channel", "master_ts", "value"]).to_pylist()
    ref = [r for r in t if r["source"] == REFERENCE_SOURCE and r["master_ts"] is not None]
    if not ref:
        return None, "no_reference (no strap was worn: capture with ?hrstrap=1)"
    cam = [r for r in t if r["source"].startswith(CAMERA_PREFIX) and r["master_ts"] is not None]
    if not cam:
        return None, "no_camera_heart_rate (process with --rppg, or a study declaring `cardiac`)"
    if len({r["source"] for r in cam}) > 1:
        return None, "ambiguous_source (more than one rPPG source in this session)"

    def series(rows, ch):
        pts = sorted((r["master_ts"], r["value"]) for r in rows if r["channel"] == ch)
        return (np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float))

    bvp_ts, bvp = series(cam, "cardiac.bvp")
    luma_ts, luma = series(cam, "cardiac.skin_luma")
    hr_ts, hr = series(ref, "reference.hr_bpm")
    rr_ts, rr = series(ref, "reference.rr_ms")
    pairs = pairs_for(session_id, camera_windows(bvp_ts, bvp, luma_ts, luma), hr_ts, hr, rr_ts, rr)
    if not pairs:
        return None, "no_overlap (the strap and the camera never covered the same 10 s)"
    return pairs, None


def plot(pairs: list[Pair], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    a = agreement([p for p in pairs if p.passed])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for passed, colour, label in ((False, "#bbbbbb", "failed the gate"), (True, "#d6455d", "passed the gate")):
        sel = [p for p in pairs if p.passed is passed]
        ax.scatter([(p.camera_bpm + p.reference_bpm) / 2 for p in sel], [p.error for p in sel],
                   s=10, c=colour, label=f"{label} (n={len(sel)})")
    if a["n"] > 1:
        for y, style in ((a["bias"], "-"), (a["loa_low"], "--"), (a["loa_high"], "--")):
            ax.axhline(y, color="#d6455d", ls=style, lw=1)
    ax.set_xlabel("mean of camera and strap (bpm)")
    ax.set_ylabel("camera − strap (bpm)")
    ax.set_title("Camera heart rate against a chest strap (Bland–Altman)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def _fmt(a: dict[str, float]) -> str:
    if a["n"] == 0:
        return "     0"
    return (f"{a['n']:>6} {a['bias']:>+7.1f} {a['loa_low']:>+7.1f} {a['loa_high']:>+7.1f} "
            f"{a['mae']:>6.1f} {a['rmse']:>6.1f} {a['within_5']:>7.0%}")


def main() -> int:
    from store import list_sessions

    ap = argparse.ArgumentParser(description="camera heart rate against a chest strap — writes nothing")
    ap.add_argument("--data", type=Path, default=ROOT / "out")
    ap.add_argument("--session", action="append", default=None)
    ap.add_argument("--plot", type=Path, default=None, help="write a Bland-Altman PNG here")
    args = ap.parse_args()

    ids = args.session or [s["session_id"] for s in list_sessions(args.data)]
    pairs: list[Pair] = []
    for sid in ids:
        got, refusal = load_session(args.data, sid)
        if refusal:
            if args.session:
                print(f"  {sid}: refused — {refusal}")
            continue
        pairs += got
    if not pairs:
        print("\n  No session has both a strap reference and camera heart rate. Record one with "
              "?hrstrap=1 on a study declaring `cardiac`, then process it.\n")
        return 1

    head = f"  {'':18} {'n':>6} {'bias':>7} {'LoA lo':>7} {'LoA hi':>7} {'MAE':>6} {'RMSE':>6} {'<=5bpm':>7}"
    print(f"\n  Camera heart rate vs strap — {len({p.session_id for p in pairs})} session(s), "
          f"{WINDOW_S:g} s windows every {STEP_S:g} s  (bpm)\n")
    print(head)
    print(f"  {'passed the gate':18} {_fmt(agreement([p for p in pairs if p.passed]))}")
    print(f"  {'every window':18} {_fmt(agreement(pairs))}")
    print("\n  by SNR (every window, gated or not)\n" + head)
    for label, a in by_snr(pairs):
        print(f"  {label:18} {_fmt(a)}")
    gate, why = suggest_gate(pairs)
    print(f"\n  current gate: SNR >= {MIN_SNR_DB:g} dB, skin luma >= {MIN_LUMA}")
    print(f"  suggested gate: {'SNR >= %g dB — ' % gate if gate is not None else 'none — '}{why}\n")
    if args.plot:
        plot(pairs, args.plot)
        print(f"  plot written to {args.plot}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
