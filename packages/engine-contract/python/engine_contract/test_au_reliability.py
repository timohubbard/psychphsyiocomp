"""Tests for the per-AU reliability tiering."""

from __future__ import annotations

import pytest

from engine_contract.au_reliability import (
    MEAN_AUC_IN_THE_WILD,
    high_confidence_aus,
    low_confidence_aus,
    normalise,
    reliability,
)


def test_the_two_reliable_aus_are_tiered_high():
    """AU06 and AU12 are the only units the evidence puts above 0.80 AUC."""
    assert reliability("AU06").tier == "high"
    assert reliability("AU12").tier == "high"


def test_the_hard_aus_are_tiered_low():
    """AU14 and AU23 encode facial TENSION rather than movement, and need depth
    or blood-flow cues a 2D webcam frame does not carry. AU20 is the floor of
    the whole set at F1 .13-.24."""
    for au in ("AU14", "AU20", "AU23"):
        assert reliability(au).tier == "low", au


def test_a_measured_tier_cites_its_evidence():
    r = reliability("AU20")
    assert r.stratified is True
    assert ".13" in r.evidence


def test_an_unmeasured_au_is_moderate_but_flagged_unstratified():
    """'Not separately measured' and 'measured and found average' are different
    claims. Presenting the first as the second would be an invention wearing the
    authority of the cited ones."""
    r = reliability("AU04")
    assert r.tier == "moderate"
    assert r.stratified is False
    assert str(MEAN_AUC_IN_THE_WILD) in r.evidence


def test_label_variants_normalise_to_one_unit():
    """Detectors label these inconsistently, and a mismatch would silently drop
    an AU out of the tiering into the unstratified default."""
    for variant in ("AU1", "au1", "AU01", "au01", "1"):
        assert normalise(variant) == "AU01"


def test_normalising_is_applied_by_the_lookup_itself():
    assert reliability("au12").tier == "high"
    assert reliability("AU12").tier == "high"


def test_an_unrecognisable_label_does_not_crash():
    r = reliability("smile")
    assert r.tier == "moderate"
    assert r.stratified is False


def test_the_whitelists_match_the_tiers():
    assert set(low_confidence_aus()) == {"AU14", "AU20", "AU23"}
    assert set(high_confidence_aus()) == {"AU06", "AU12"}


def test_no_au_is_both_high_and_low():
    assert not set(high_confidence_aus()) & set(low_confidence_aus())
