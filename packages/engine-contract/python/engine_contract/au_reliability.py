"""Per-Action-Unit reliability tiers, from the published evidence.

In the contract rather than in an engine, because this is a property of the
MEASUREMENT PROBLEM and not of any one detector. AU14 and AU23 are hard because
they reflect facial *tension* rather than movement, and need depth, 3D or
blood-flow cues that a 2D webcam frame does not carry — that is true whichever
model is looking at the frame. Py-Feat and OpenFace must therefore agree on the
tiering, or the same AU would carry different confidence depending on which
engine happened to run.

§2.2's design instruction is explicit: **whitelist which AUs you report based on
the per-AU floor, rather than presenting a uniform confidence across all 20+.**
A mean AUC of 0.72 is "fair" and says almost nothing about where a specific
claim will fail; the spread is what matters.

WHAT IS AND IS NOT EVIDENCED HERE. Only five AUs have per-unit figures in the
evidence base. Everything else is `moderate` and flagged `stratified=False`,
which means "not separately measured", not "measured and found average". That
distinction is the whole point: a tier presented without it would be an
invention wearing the authority of the cited ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["high", "moderate", "low"]


@dataclass(frozen=True)
class AUReliability:
    au: str
    tier: Tier
    #: False when no per-AU figure exists and the tier is a default.
    stratified: bool
    evidence: str | None = None


#: The five AUs the evidence base gives individual numbers for.
#:
#: Sources, all §2.2:
#:   AU06, AU12 — >0.90 / >0.80 AUC posed (OpenFace 2.0); Py-Feat F1 .72-.83
#:                on DISFA+ for AU12. The two most reliable units by a distance.
#:   AU14, AU23 — 0.58 / 0.56 AUC. Barely above chance. These encode tension,
#:                not movement.
#:   AU20       — Py-Feat F1 .13-.24 on DISFA+. The floor of the whole set, and
#:                the single strongest argument against uniform confidence.
_MEASURED: dict[str, tuple[Tier, str]] = {
    "AU06": ("high", "OpenFace 2.0 >0.90 AUC posed (cheek raiser)"),
    "AU12": ("high", "OpenFace 2.0 >0.80 AUC posed; Py-Feat F1 .72-.83 DISFA+"),
    "AU14": ("low", "OpenFace 2.0 0.58 AUC — tension, not movement; needs depth cues"),
    "AU20": ("low", "Py-Feat F1 .13-.24 DISFA+ — the floor of the set"),
    "AU23": ("low", "OpenFace 2.0 0.56 AUC — tension, not movement; needs depth cues"),
}

#: Mean AUC across AUs, for context when reporting an unstratified tier.
MEAN_AUC_IN_THE_WILD = 0.72
MEAN_AUC_POSED = 0.81


def reliability(au: str) -> AUReliability:
    """Tier for one AU, normalising `au01`, `AU1` and `AU01` to the same unit."""
    key = normalise(au)
    if key.endswith(("_L", "_R")):
        # One side of a bilateral movement. The evidence base has no per-side
        # figure for ANY unit, including AU06 and AU12, so inheriting the
        # bilateral tier would lend AU12's measured reliability to a quantity
        # nobody measured — with half the pixels to work from.
        return AUReliability(
            au=key, tier="low", stratified=False,
            evidence=("lateralised unit: no per-side figure exists in the "
                      "evidence base for any AU; the bilateral tier is not "
                      "inherited"),
        )
    if key in _MEASURED:
        tier, evidence = _MEASURED[key]
        return AUReliability(au=key, tier=tier, stratified=True, evidence=evidence)
    return AUReliability(
        au=key, tier="moderate", stratified=False,
        evidence=(f"no per-AU figure in the evidence base; mean AUC "
                  f"{MEAN_AUC_IN_THE_WILD} in the wild, {MEAN_AUC_POSED} posed"),
    )


def normalise(au: str) -> str:
    """`au1`, `AU1`, `AU01` -> `AU01`; `AUL12`, `AU12L`, `AU12_L` -> `AU12_L`.

    Detectors label these inconsistently and a mismatch would silently drop an
    AU out of the tiering and into the unstratified default — which is exactly
    the failure this module exists to prevent.

    Laterality is preserved, not stripped. The first version kept only the
    digits, which is fine for Py-Feat but maps OpenGraphAU's `AUL12` (left lip
    corner puller) onto `AU12` — and the left side would then be written into
    the bilateral channel, where it overwrites the real AU12 frame by frame
    and agrees with it suspiciously well.
    """
    s = str(au).strip().upper().replace("-", "_")
    body = s[2:] if s.startswith("AU") else s
    digits = "".join(c for c in body if c.isdigit())
    if not digits:
        return s
    letters = body.replace("_", "").replace(digits, "", 1)
    side = letters if letters in ("L", "R") else ""
    key = f"AU{int(digits):02d}"
    return f"{key}_{side}" if side else key


def low_confidence_aus() -> tuple[str, ...]:
    """AUs the evidence says not to make specific claims about."""
    return tuple(sorted(a for a, (t, _) in _MEASURED.items() if t == "low"))


def high_confidence_aus() -> tuple[str, ...]:
    return tuple(sorted(a for a, (t, _) in _MEASURED.items() if t == "high"))
