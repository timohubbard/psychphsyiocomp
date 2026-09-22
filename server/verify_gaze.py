"""Gaze verification gate — do fixations land on the target that was on screen?

    npm run verify:gaze -- --data out --session <id>

`verify_m0.py` proves the plumbing carries two sources on one clock. This proves
the gaze estimate means something, and it is the strongest check available
because the answer is known in advance: during each calibration dwell there was
exactly one dot on screen and the participant was told to look at it. A working
pipeline must put the fixation there. Anything else is a fault somewhere between
the camera and the AOI, and this narrows down which.

It also demonstrates §4.2's warning rather than restating it. On the first real
session the hit rate moved 0% -> 39% -> 78% -> 94% -> 100% across padding from 0
to 4.5 degrees, on identical gaze and identical fixations. A hit rate quoted
without its padding is not a measurement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import numpy as np  # noqa: E402

from aoi import AOI, AOISet, analyse  # noqa: E402
from fixations import classify  # noqa: E402
from store import channel_series, list_sessions, session_detail  # noqa: E402

#: §4.2 says to pad to the measured spatial-error budget, ~3-4.5 degrees.
PAD_LADDER = (0.0, 1.0, 2.0, 3.0, 4.5, 6.0)

#: The gate. At the top of the published budget, fixations should be landing on
#: the target that was on screen essentially always — if they are not, the
#: estimate is not usable for AOI work regardless of what validation reported.
GATE_PAD_DEG = 4.5
GATE_HIT_RATE = 0.9


def load_gaze(out: str, session_id: str):
    d = session_detail(out, session_id)
    m = d["meta"]
    if not m.get("px_per_mm") or not m.get("viewing_distance_mm"):
        return None, None, None, d, None

    dpp = float(np.degrees(np.arctan2(1.0 / m["px_per_mm"], m["viewing_distance_mm"])))
    viewport = (float(m["screen_width_px"]), float(m["screen_height_px"]))

    gx = {t: v for t, v in channel_series(out, session_id, "gaze.x", max_points=10**9)["points"]}
    gy = {t: v for t, v in channel_series(out, session_id, "gaze.y", max_points=10**9)["points"]}
    ts = np.array(sorted(set(gx) & set(gy)))
    if not len(ts):
        return None, None, None, d, None

    x = np.array([gx[t] for t in ts])
    y = np.array([gy[t] for t in ts])
    return ts, x, y, d, (dpp, viewport)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "out")
    ap.add_argument("--session", default=None)
    args = ap.parse_args()

    sessions = list_sessions(args.data)
    if not sessions:
        print(f"\n  no processed sessions under {args.data}\n")
        return 1
    session_id = args.session or sessions[0]["session_id"]

    ts, x, y, d, geom = load_gaze(str(args.data), session_id)
    print("\n  GAZE VERIFICATION")
    print("  " + "-" * 72)
    print(f"  session          {session_id}")

    if geom is None:
        print("  REFUSED: no geometry — AOI hits cannot be expressed in degrees,")
        print("           and a pixel tolerance is not comparable between people.")
        return 1

    dpp, viewport = geom
    print(f"  geometry         {1/dpp:.0f} px/deg   viewport {viewport[0]:.0f}x{viewport[1]:.0f}")

    # Extrapolated predictions are the model guessing outside its calibration,
    # not measurements of where anyone looked.
    on = (x > -0.1) & (x < 1.1) & (y > -0.1) & (y < 1.1)
    print(f"  on-screen        {on.sum()}/{len(ts)} samples ({on.mean():.0%})")

    result = classify(ts[on], x[on], y[on], viewport_px=viewport, degrees_per_px=dpp)
    fixations = [e for e in result.events if e.kind == "fixation"]
    print(f"  fixations        {len(fixations)}  (HMM, not I-VT)")

    targets = []
    for e in d["events"]:
        if e["event_type"].endswith("_point_sampling") and e["onset"] and e["offset"]:
            meta = e["metadata"] or {}
            if "x" in meta:
                targets.append((float(meta["x"]), float(meta["y"]), e["onset"], e["offset"]))

    if not targets:
        print("  REFUSED: no calibration or validation dwell windows in this session")
        return 1
    print(f"  known targets    {len(targets)}")

    print(f"\n  {'pad (deg)':>10} {'hit rate':>10}   {'mean error':>12}")
    print("  " + "-" * 40)

    gate_rate = 0.0
    errors: list[float] = []
    for pad in PAD_LADDER:
        hits = checked = 0
        errors = []
        for tx, ty, t0, t1 in targets:
            overlapping = [f for f in fixations if f.onset_ts < t1 and f.offset_ts > t0]
            if not overlapping:
                continue
            checked += 1
            f = max(overlapping,
                    key=lambda f: min(f.offset_ts, t1) - max(f.onset_ts, t0))
            # A point AOI, so padding alone decides the tolerance. Any other
            # radius would mix the boundary choice into the thing being measured.
            s = AOISet("target", "1", (AOI("t", "circle", (tx, ty, 0.001)),))
            hits += analyse([f], s, pad_deg=pad, degrees_per_px=dpp,
                            viewport_px=viewport).n_hits
            errors.append(float(np.hypot((f.x - tx) * viewport[0],
                                         (f.y - ty) * viewport[1]) * dpp))

        rate = hits / max(checked, 1)
        if pad == GATE_PAD_DEG:
            gate_rate = rate
        print(f"  {pad:>10.1f} {rate:>9.0%}   {np.mean(errors):>10.2f} deg   (n={checked})")

    mean_err = float(np.mean(errors)) if errors else float("nan")
    print("\n  " + "-" * 72)
    print(f"  mean error to the target actually on screen: {mean_err:.2f} deg")
    print("  Compare against the validation figure — they are measured")
    print("  independently, so agreement is evidence and divergence is a fault.")

    ok = gate_rate >= GATE_HIT_RATE
    print(f"\n  GAZE GATE: {'PASS' if ok else 'FAIL'}  "
          f"({gate_rate:.0%} of fixations on target at {GATE_PAD_DEG} deg padding, "
          f"need {GATE_HIT_RATE:.0%})")
    print("\n  Note the ladder above. Identical gaze and identical fixations give")
    print("  wildly different hit rates purely from the boundary choice — §4.2")
    print("  measured 77/88/93 from the same effect. Always report the padding.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
