"""Tests for the consent gate on transcription.

This is the one gate in the project where the conservative direction is
*refuse*. Everywhere else a missing consent field means keep-and-flag, because
deleting a participant's recording on the strength of an absent field is
unrecoverable. Here the asymmetry inverts: creating a transcript nobody agreed
to is the unrecoverable act, and declining to create one costs a re-run.

So these tests are mostly about what does NOT get transcribed.
"""

from __future__ import annotations

from transcript_stage import TRANSCRIBING_TIER, transcript_permitted


def meta(tier="media_plus_transcript", understood=True, **extra):
    consent = {"tier": tier, "understood": understood}
    consent.update(extra)
    return {"consent": consent}


def study(tiers=("features_only", "media_retained", "media_plus_transcript")):
    return {"study_id": "s", "consent_tiers": list(tiers)}


# ---------------------------------------------------------------------------
# permitted
# ---------------------------------------------------------------------------

def test_the_transcribing_tier_permits_a_transcript():
    ok, reason = transcript_permitted(meta(), study())
    assert ok
    assert reason == "consented"


def test_a_reason_is_returned_on_success_too():
    """The run row records WHY it was allowed, not only that it was."""
    assert transcript_permitted(meta(), study())[1]


def test_it_works_without_a_study_when_one_is_not_available():
    """A session bundle predating study definitions still has a consent
    record, and that record is the participant's actual decision."""
    ok, _ = transcript_permitted(meta(), None)
    assert ok


# ---------------------------------------------------------------------------
# refused
# ---------------------------------------------------------------------------

def test_a_missing_tier_refuses_rather_than_defaulting():
    """The inverse of `enforce_consent`, deliberately. There, no tier means
    keep the media; here it means produce nothing."""
    ok, reason = transcript_permitted({"consent": {}}, study())
    assert not ok
    assert reason == "no_consent_tier_recorded"


def test_no_consent_block_at_all_refuses():
    ok, reason = transcript_permitted({}, study())
    assert not ok
    assert reason == "no_consent_tier_recorded"


def test_the_media_retained_tier_does_not_imply_a_transcript():
    """Agreeing that a recording may be kept is not agreeing that the words in
    it may be written down and read."""
    ok, reason = transcript_permitted(meta(tier="media_retained"), study())
    assert not ok
    assert "media_retained" in reason


def test_the_features_only_tier_refuses():
    ok, reason = transcript_permitted(meta(tier="features_only"), study())
    assert not ok
    assert "features_only" in reason


def test_an_unrecognised_tier_refuses_rather_than_being_treated_as_permissive():
    ok, _ = transcript_permitted(meta(tier="keep_everything"), study())
    assert not ok


def test_a_tier_chosen_but_never_acknowledged_refuses():
    """The radio button was set and the disclosure checkbox was not. The
    capture page will not submit that, but a hand-edited bundle can."""
    ok, reason = transcript_permitted(meta(understood=False), study())
    assert not ok
    assert reason == "disclosure_not_acknowledged"


def test_a_truthy_but_non_true_acknowledgement_refuses():
    """`understood: "yes"` is not consent, it is a string."""
    assert not transcript_permitted(meta(understood="yes"), study())[0]


def test_a_tier_the_study_never_offered_refuses():
    """Incoherent: the participant could not have been shown that option, so
    whatever produced this record was not the consent flow."""
    ok, reason = transcript_permitted(
        meta(), study(tiers=("features_only", "media_retained")))
    assert not ok
    assert reason == "study_did_not_offer_the_tier"


def test_a_study_offering_the_tier_is_not_on_its_own_sufficient():
    """The study says the participant COULD have agreed. Only the session
    record says whether they did."""
    ok, _ = transcript_permitted(meta(tier="features_only"), study())
    assert not ok


# ---------------------------------------------------------------------------
# the constant itself
# ---------------------------------------------------------------------------

def test_exactly_one_tier_permits_transcription():
    assert TRANSCRIBING_TIER == "media_plus_transcript"


def test_the_gate_never_raises_on_a_malformed_session():
    """A bundle that cannot be parsed must not become a bundle that gets
    transcribed because an exception was swallowed upstream."""
    for m in ({}, {"consent": None}, {"consent": "yes"}, {"consent": []}):
        ok, reason = transcript_permitted(m, study())
        assert ok is False
        assert reason
