"""Records of processing (UK GDPR / GDPR Art 30), generated from a study definition.

research/pass5-legal-gaps.md (GDPR section): Art 30 records are needed
regardless of headcount here, because the small-organisation exemption in
Art 30(5) does not survive special-category data or processing that is not
occasional — and face, voice and respiration streams are treated as special
category by default. Each deploying research group is the controller and owes
its own record.

Generated, not hand-written, for the same reason the consent screen is built
from the study file: a record written beside the protocol drifts from it. What
the study file cannot know — who the DPO is, where the data physically lives,
whether anything leaves the country — is marked TO COMPLETE, never guessed.
A record that invents a storage location is worse than one that admits a gap.

    npm run ropa -- <study_id>          prints Markdown
    npm run ropa -- <study_id> --out docs/ropa-<study_id>.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from study import (AUDIO_MODALITY_IDS, SPECIAL_CATEGORY_MODALITY_IDS, audience_of,
                   content_hash, is_usable_contact, load_study)

ROOT = Path(__file__).resolve().parents[1]
TODO = "**TO COMPLETE**"

#: What each modality collects, in the terms an Art 30 record uses.
_CATEGORIES = {
    "gaze": "eye-movement features and estimated on-screen gaze position",
    "face": "facial landmark and facial action unit time series (no identity matching)",
    "voice": "voice acoustic features (eGeMAPS functionals)",
    "respiration": "a breathing-movement waveform from chest and shoulder motion",
}

_TIER_KEEPS = {
    "features_only": "derived measurements only — the recording is deleted after analysis",
    "media_retained": "the video (and audio, where recorded) is kept with the measurements",
    "media_plus_transcript": "as above, plus a transcript of speech",
}


def record(study: dict[str, Any]) -> str:
    """The Art 30(1) record for one study, as Markdown."""
    d = study.get("disclosure") or {}
    mods = study.get("modalities") or []
    tiers = study.get("consent_tiers") or []
    special = [m for m in mods if m in SPECIAL_CATEGORY_MODALITY_IDS]
    audience = audience_of(study)

    lines = [
        f"# Record of processing — {study.get('name')} (`{study['study_id']}` v{study.get('version')})",
        "",
        f"Generated from `studies/{study['study_id']}.json`, content hash "
        f"`{content_hash(study)}`. Regenerate after any change to the study; a "
        "record for a different hash describes a different protocol.",
        "",
    ]
    if audience != "participants":
        lines += [
            "> **Developer self-test.** This study has no ethics reference and is "
            "not approved for participants. This record describes what running it "
            "on participants WOULD involve; it is not a record of an approved activity.",
            "",
        ]

    lines += [
        "| Art 30(1) | |",
        "|---|---|",
        f"| (a) Controller | {d.get('controller') or TODO} |",
        f"| (a) Contact | {d['contact'] if is_usable_contact(d.get('contact')) else TODO + ' — the study file holds a placeholder'} |",
        f"| (a) Data protection officer | {TODO} — not recorded in the study file |",
        f"| (b) Purposes | Research: {study.get('name')}. Ethics reference: "
        f"{d.get('irb_reference') or TODO}. Lawful basis (Art 6): "
        f"{d.get('lawful_basis') or TODO}. |",
        f"| (c) Data subjects | {'Research participants' if audience == 'participants' else 'The developer only (self-test)'} |",
        f"| (c) Personal data | {_categories(mods, tiers)} |",
        f"| (c) Special category (Art 9) | {_special(special, d)} |",
        f"| (d) Recipients | {d.get('secondary_use') or TODO} |",
        f"| (e) Transfers outside the UK/EEA | {TODO} — the platform is self-hosted and "
        "transfers nothing itself; record where the deploying group stores the data |",
        f"| (f) Retention | {_retention(d)} |",
        f"| (g) Security measures | {_security(tiers, mods)} |",
        "",
        "## Consent tiers offered",
        "",
        *[f"- `{t}`: {_TIER_KEEPS.get(t, t)}" for t in tiers],
        "",
        "Also required, and not generated: a DPIA (see `docs/dpia-template.md`) — "
        "presumptively mandatory for this processing.",
    ]
    return "\n".join(lines) + "\n"


def _categories(mods: list[str], tiers: list[str]) -> str:
    parts = ["a pseudonymous participant and session identifier",
             "consent record (what was shown and chosen)",
             "screen geometry and capture quality metrics"]
    parts += [_CATEGORIES[m] for m in mods if m in _CATEGORIES]
    if any(t in ("media_retained", "media_plus_transcript") for t in tiers):
        parts.append("face video" + (" and voice audio" if any(m in AUDIO_MODALITY_IDS for m in mods)
                                     else "") + " where the participant opts to keep it")
    if "media_plus_transcript" in tiers:
        parts.append("speech transcripts where the participant opts in")
    return "; ".join(parts)


def _special(special: list[str], d: dict[str, Any]) -> str:
    if not special:
        return "None expected (gaze only)."
    return (f"Treated as special category by default: {', '.join(special)} "
            "(research/pass5-legal-gaps.md — CJEU C-21/23, C-252/21). Condition relied on: "
            f"{d.get('special_category_basis') or TODO}")


def _retention(d: dict[str, Any]) -> str:
    days = d.get("retention_days")
    return (f"{days} days from each session, as told to every participant, enforced by "
            "`npm run retention` (which must be run on a schedule where the data lives); "
            "withdrawal on request by `npm run withdraw`, recording and measurements both.")


def _security(tiers: list[str], mods: list[str]) -> str:
    return ("Platform measures: capture and researcher servers bind to localhost only; "
            "the default tier deletes the recording after analysis; retention sweep and "
            "withdrawal with a deletion log that holds no participant identifier; no face "
            "matching or identity features; no emotion labels are produced. "
            f"Deployment measures (access control, encryption at rest, backups): {TODO}.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("study_id")
    ap.add_argument("--studies", type=Path, default=ROOT / "studies")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    text = record(load_study(args.studies, args.study_id))
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"  wrote {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
