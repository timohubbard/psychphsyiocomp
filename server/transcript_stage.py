"""The consent gate on transcription, and the only thing that runs the engine.

`speech.faster_whisper` is a pure function of audio and cannot see a session's
consent — that is what makes it an engine. But a transcript is the one output
in this project that anyone who opens the file can read, and the only one that
can contain something a participant said without meaning it to become a
record. So the decision about whether it may exist at all is made here,
against the tier they actually chose, and this module is the only caller.

The gate is deliberately conservative in three ways:

- **A missing tier is a refusal, not a default.** Elsewhere in this pipeline a
  missing tier means "keep the media and flag it", because deleting a
  recording on the strength of an absent field is unrecoverable. Here the
  asymmetry runs the other way: creating a transcript nobody consented to is
  the unrecoverable mistake, and not creating one costs a re-run.

- **It reads the tier the participant chose, not the tiers the study offered.**
  A study offering `media_plus_transcript` says a participant *could* have
  agreed; only the session record says whether they did.

- **It re-checks that the study offered the tier at all.** A session whose
  recorded tier is not among its study's `consent_tiers` is incoherent — the
  participant could not have been shown that option — and an incoherent
  consent record is not a basis for transcribing anyone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine_contract import describe_audio
from engine_contract.loader import load_engine_module

#: The one tier that permits a transcript. Mirrors `allowsTranscript` in
#: web/src/consent.js, and is a literal rather than an import because a typo
#: that silently widened this would be the worst bug in the project.
TRANSCRIBING_TIER = "media_plus_transcript"


def transcript_permitted(session_meta: dict[str, Any],
                         study: dict[str, Any] | None = None) -> tuple[bool, str]:
    """May this session be transcribed? Returns (permitted, reason).

    The reason is returned on success too, so a run row records WHY it was
    allowed rather than only that it was.
    """
    if not isinstance(session_meta, dict):
        return False, "no_consent_tier_recorded"

    consent = session_meta.get("consent")
    if not isinstance(consent, dict):
        # A consent block that is a string, a list, or absent is not a consent
        # record. Raising here would be worse than refusing: an exception can
        # be caught upstream and turned into a default, and the default that
        # would feel natural is "carry on with the rest of the pipeline".
        return False, "no_consent_tier_recorded"

    tier = consent.get("tier")
    if tier is None:
        return False, "no_consent_tier_recorded"
    if tier != TRANSCRIBING_TIER:
        return False, f"tier_does_not_permit_transcript:{tier}"
    if consent.get("understood") is not True:
        # The tier was selected but the disclosure was never acknowledged.
        return False, "disclosure_not_acknowledged"

    if isinstance(study, dict):
        offered = study.get("consent_tiers") or []
        if TRANSCRIBING_TIER not in offered:
            return False, "study_did_not_offer_the_tier"

    return True, "consented"


def run_transcript(writer, bundle, solution, *, study=None,
                   model_dir: str | Path | None = None,
                   params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Transcribe, if and only if the participant agreed to it.

    A refusal is RECORDED, not silent. `probe()` before `run()` is the rule
    everywhere here, and consent is a precondition of the same kind: a reader
    of the tables has to be able to tell "no transcript because nobody agreed"
    from "no transcript because the engine failed" from "no transcript because
    nobody ran it".
    """
    permitted, reason = transcript_permitted(bundle.metadata, study)
    if not permitted:
        return {"status": "refused", "reason": reason}

    wav = bundle.ensure_audio()
    if wav is None:
        return {"status": "no_audio", "reason": "consented but no audio track"}

    module = load_engine_module("speech.faster_whisper")
    engine = module.FasterWhisperTranscript(model_dir)
    media = describe_audio(wav, bundle.metadata.get("applied_audio_constraints"))

    params = dict(params or {})
    started = datetime.now(timezone.utc)
    eligibility = engine.probe(media)
    run_id = str(uuid.uuid4())

    if not eligibility.eligible:
        writer.add_run(run_id=run_id, manifest=engine.manifest, source=engine.source,
                       params=params, media_sha256=media.sha256, started=started,
                       ended=datetime.now(timezone.utc), status="ineligible",
                       eligibility=eligibility, solution=solution)
        return {"status": "ineligible", "reasons": list(eligibility.reasons)}

    chunks = list(engine.run(media, params))
    rows = writer.add_chunks(chunks, source=engine.source, params=params,
                             solution=solution)
    writer.add_run(run_id=run_id, manifest=engine.manifest, source=engine.source,
                   params=params, media_sha256=media.sha256, started=started,
                   ended=datetime.now(timezone.utc), status="ok",
                   eligibility=eligibility, solution=solution)

    quality = {q.metric: q.value for c in chunks for q in c.quality}
    return {"status": "ok", "rows": rows, "permitted_because": reason, **quality}
