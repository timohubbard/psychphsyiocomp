"""Study definitions, server side.

A deliberate mirror of ``web/src/study.js`` rather than a shared
implementation, because the two run in places that cannot share a module: the
browser validates before a participant is asked to consent, and this validates
before a session is written into the canonical tables.

The one thing that MUST agree between them is ``content_hash``. A session
manifest carries the hash the browser computed; this recomputes it from the
study file on disk and compares. When they differ, the study was edited after
that session was collected — which is exactly the case a version string does
not catch, because nobody bumps a version while fixing a typo in a disclosure.

``verify_session_study`` therefore reports a *finding*, not an exception. The
data is already collected and is not made worse by being read; what would make
it worse is quietly treating it as comparable with sessions run under the
edited protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Mirrors CONSENT_TIERS in web/src/consent.js.
CONSENT_TIER_IDS = ("features_in_browser", "features_only", "media_retained",
                    "media_plus_transcript")

#: Mirrors BROWSER_MODALITIES: the only modalities measurable when the video
#: never leaves the participant's browser.
BROWSER_MODALITY_IDS = ("gaze", "face")

#: Mirrors MODALITIES in web/src/study.js.
MODALITY_IDS = ("gaze", "face", "voice", "respiration")

#: Mirrors AUDIO_MODALITIES in web/src/study.js: modalities that need the microphone.
AUDIO_MODALITY_IDS = ("voice",)

#: BIPA's 3-year outer bound, mirroring MAX_RETENTION_DAYS.
MAX_RETENTION_DAYS = 3 * 365

#: Mirrors AUDIENCES in web/src/study.js. Absent means "developer".
AUDIENCES = ("developer", "participants")

#: Mirrors SPECIAL_CATEGORY_MODALITIES: treated as Art 9 data by default
#: (research/pass5-legal-gaps.md — CJEU C-21/23, C-252/21).
SPECIAL_CATEGORY_MODALITY_IDS = ("face", "voice", "respiration")

#: Mirrors PLACEHOLDER and CONTACT_ROUTE in web/src/study.js.
_PLACEHOLDER = re.compile(r"replace (this|with)|placeholder|\btodo\b|\btbd\b|example\.[a-z]+",
                          re.IGNORECASE)
_CONTACT_ROUTE = re.compile(r"[^\s@]+@[^\s@]+\.[a-z]{2,}|https?://\S+\.\S+", re.IGNORECASE)

#: Hashed only when present, in this order, after the fixed eleven — so studies
#: written before these fields existed keep the hashes their sessions recorded.
#: Must match the `optional` list in web/src/study.js `canonicalise`.
_OPTIONAL_HASHED = (
    ("audience", lambda s, d: s.get("audience")),
    ("controller", lambda s, d: d.get("controller")),
    ("lawful_basis", lambda s, d: d.get("lawful_basis")),
    ("special_category_basis", lambda s, d: d.get("special_category_basis")),
    ("conditions", lambda s, d: s.get("conditions")),
)

MIN_CALIBRATION_POINTS = 5


@dataclass(frozen=True)
class Verdict:
    """The result of a check that must not raise on bad data."""

    ok: bool
    reasons: tuple[str, ...] = ()
    detail: dict[str, Any] | None = None


def validate_study(study: Any) -> Verdict:
    """Mirror of ``validateStudy``. Never repairs, never defaults."""
    if not isinstance(study, dict):
        return Verdict(False, ("no study definition",))

    reasons: list[str] = []

    if not _is_id(study.get("study_id")):
        reasons.append("study_id must be a slug of letters, digits, dash or underscore")
    if not _non_empty(study.get("name")):
        reasons.append("no study name")
    if not _non_empty(study.get("version")):
        reasons.append("no study version")

    d = study.get("disclosure")
    if not isinstance(d, dict):
        reasons.append("no disclosure block")
    else:
        days = d.get("retention_days")
        if not isinstance(days, (int, float)) or isinstance(days, bool) or days <= 0:
            reasons.append("disclosure.retention_days must be a positive number of days")
        elif days > MAX_RETENTION_DAYS:
            reasons.append(
                f"disclosure.retention_days {days} exceeds the "
                f"{MAX_RETENTION_DAYS}-day cap")
        if not _non_empty(d.get("secondary_use")):
            reasons.append("no disclosure.secondary_use")
        if not _non_empty(d.get("contact")):
            reasons.append("no disclosure.contact — required by 45 CFR 46.116(b)(7)")
        for field in ("irb_reference", "controller", "lawful_basis", "special_category_basis"):
            value = d.get(field)
            if value is not None and not _non_empty(value):
                reasons.append(f"disclosure.{field} is present but empty")

    audience = study.get("audience")
    if audience is not None and audience not in AUDIENCES:
        reasons.append(f"unknown audience: {audience} (expected {' or '.join(AUDIENCES)})")
    if audience_of(study) == "participants" and isinstance(d, dict):
        reasons.extend(_participant_gate(study, d))

    tiers = study.get("consent_tiers")
    if not isinstance(tiers, list) or not tiers:
        reasons.append("no consent_tiers offered")
    else:
        for t in tiers:
            if t not in CONSENT_TIER_IDS:
                reasons.append(f"unknown consent tier: {t}")
        default = study.get("default_tier")
        if default is not None and default not in tiers:
            reasons.append("default_tier is not among the tiers offered")

    mods = study.get("modalities")
    if not isinstance(mods, list) or not mods:
        reasons.append("no modalities enabled — a study that measures nothing")
    else:
        for m in mods:
            if m not in MODALITY_IDS:
                reasons.append(f"unknown modality: {m}")

    if isinstance(mods, list) and "gaze" in mods:
        cal = study.get("calibration")
        n = cal.get("n_points") if isinstance(cal, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or n < MIN_CALIBRATION_POINTS:
            reasons.append(
                f"gaze needs calibration.n_points of at least {MIN_CALIBRATION_POINTS}")
        if isinstance(cal, dict) and cal.get("randomise_order") is False:
            reasons.append(
                "calibration.randomise_order is false — fixed stimulus order "
                "confounds target position with time and breaks cross-validation")

    if "tasks" in study and not isinstance(study["tasks"], list):
        reasons.append("tasks must be a list when present")
    elif isinstance(study.get("tasks"), list):
        reasons.extend(_stimuli_reasons(study["tasks"]))
    reasons.extend(_condition_reasons(study))
    rec = study.get("recruitment")
    if isinstance(rec, dict) and "completion_url" in rec and not _safe_completion_url(
            rec["completion_url"]):
        reasons.append("recruitment.completion_url must be an https address "
                       "(or localhost for testing)")

    # Mirrors study.js: a transcript tier with no microphone offers a choice
    # that cannot happen and records consent to transcribe a silent session.
    if (isinstance(tiers, list) and "media_plus_transcript" in tiers
            and isinstance(mods, list) and not any(m in AUDIO_MODALITY_IDS for m in mods)):
        reasons.append("media_plus_transcript is offered but no modality records audio")

    # Mirrors study.js: the no-video tier cannot promise a server-only measurement.
    if isinstance(tiers, list) and "features_in_browser" in tiers and isinstance(mods, list):
        server_only = [m for m in mods if m not in BROWSER_MODALITY_IDS]
        if server_only:
            reasons.append(f"features_in_browser is offered but {', '.join(server_only)} "
                           "can only be measured from a recording on the server")

    return Verdict(not reasons, tuple(reasons))


#: Mirrors STIMULUS_SRC, SHA256 and MAX_STIMULUS_MS in web/src/study.js.
_STIMULUS_SRC = re.compile(r"^stimuli/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_STIMULUS_MS = 10 * 60 * 1000


def _is_ms(v: Any, *, minimum: float) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and v == v and v not in (float("inf"),) and v >= minimum)


def _stimuli_reasons(tasks: list[Any]) -> list[str]:
    """Mirror of ``stimuliReasons`` — image and video items."""
    reasons: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict) or task.get("type") != "stimuli":
            continue
        items = task.get("items")
        if not isinstance(items, list) or not items:
            reasons.append("a stimuli task has no items")
            continue
        if "randomise" in task and not isinstance(task["randomise"], bool):
            reasons.append("stimuli.randomise must be true or false")
        if "isi_ms" in task and not _is_ms(task["isi_ms"], minimum=0):
            reasons.append("stimuli.isi_ms must be a non-negative number of milliseconds")
        for it in items:
            it = it if isinstance(it, dict) else {}
            sid = it.get("stimulus_id")
            where = f"stimulus {sid}" if _is_id(sid) else "a stimulus"
            if not _is_id(sid):
                reasons.append("stimulus_id must be a slug of letters, digits, dash or underscore")
            elif sid in seen:
                reasons.append(f"stimulus_id {sid} is used twice — AOIs and results are keyed on it")
            if _is_id(sid):
                seen.add(sid)
            if it.get("kind") not in ("image", "video"):
                reasons.append(f"{where}: kind must be image or video")
            src = it.get("src")
            if not isinstance(src, str) or not _STIMULUS_SRC.match(src) or ".." in src:
                reasons.append(f"{where}: src must be a path under stimuli/")
            if not isinstance(it.get("sha256"), str) or not _SHA256.match(it["sha256"]):
                reasons.append(f"{where}: sha256 must be 64 lower-case hex digits")
            d = it.get("duration_ms")
            if not (_is_ms(d, minimum=1) and d <= MAX_STIMULUS_MS):
                reasons.append(f"{where}: duration_ms must be between 1 and {MAX_STIMULUS_MS}")
            if "sound" in it and not isinstance(it["sound"], bool):
                reasons.append(f"{where}: sound must be true or false")
    return reasons


def _condition_reasons(study: dict[str, Any]) -> list[str]:
    """Mirror of ``conditionReasons``."""
    reasons: list[str] = []
    c = study.get("conditions")
    arms = c.get("arms") if isinstance(c, dict) and isinstance(c.get("arms"), list) else None
    if "conditions" in study:
        if not arms or len(arms) < 2:
            reasons.append("conditions.arms needs at least two arms")
        elif not all(_is_id(a) for a in arms):
            reasons.append("conditions.arms must be slugs")
        elif len(set(arms)) != len(arms):
            reasons.append("conditions.arms repeats an arm")
    for task in study.get("tasks") if isinstance(study.get("tasks"), list) else []:
        if not isinstance(task, dict) or "arms" not in task:
            continue
        if not arms:
            reasons.append(f"task {task.get('type')} names arms but the study defines no conditions")
        elif (not isinstance(task["arms"], list) or not task["arms"]
              or any(a not in arms for a in task["arms"])):
            reasons.append(f"task {task.get('type')}: arms must be a non-empty subset "
                           "of conditions.arms")
    return reasons


def _safe_completion_url(url: Any) -> bool:
    """Mirror of ``isSafeCompletionUrl`` in web/src/recruitment.js."""
    from urllib.parse import urlparse
    if not isinstance(url, str):
        return False
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return (u.scheme == "https" and bool(u.netloc)) or (
        u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))


def audience_of(study: dict[str, Any]) -> str:
    """Mirror of ``audienceOf``: absent means the developer testing their build."""
    return study.get("audience") or "developer"


def is_usable_contact(contact: Any) -> bool:
    """A contact a participant could actually use: not a template, and an
    email or web address in it. The test the participant gate applies."""
    return (_non_empty(contact) and not _PLACEHOLDER.search(contact)
            and bool(_CONTACT_ROUTE.search(contact)))


def _participant_gate(study: dict[str, Any], d: dict[str, Any]) -> list[str]:
    """Mirror of ``participantGate`` — what a study needs before it runs on others."""
    reasons = []
    if not _non_empty(d.get("irb_reference")):
        reasons.append("audience is participants but there is no disclosure.irb_reference "
                       "(the ethics committee approval reference, REC or IRB)")
    contact = d.get("contact")
    if _non_empty(contact) and not is_usable_contact(contact):
        reasons.append("disclosure.contact is still a placeholder or gives no email address "
                       "or web address a participant could use")
    if not _non_empty(d.get("controller")):
        reasons.append("no disclosure.controller — UK GDPR Art 13(1)(a): who is responsible "
                       "for the data")
    if not _non_empty(d.get("lawful_basis")):
        reasons.append("no disclosure.lawful_basis — UK GDPR Art 13(1)(c): the Art 6 basis")
    special = [m for m in (study.get("modalities") or [])
               if m in SPECIAL_CATEGORY_MODALITY_IDS]
    if special and not _non_empty(d.get("special_category_basis")):
        reasons.append(f"{', '.join(special)} recorded but no disclosure.special_category_basis "
                       "— the Art 9 condition relied on for data treated as special category")
    return reasons


def canonicalise(study: dict[str, Any]) -> list[list[Any]]:
    """The hashed subset, in the order ``web/src/study.js`` uses.

    Byte-for-byte agreement with the JS is the whole point, so this returns the
    same nested-array shape rather than a dict: the JS hashes an array of
    `[key, value]` pairs precisely so key order cannot depend on the language's
    object semantics.
    """
    d = study.get("disclosure") or {}
    fixed = [
        ["study_id", study.get("study_id")],
        ["version", study.get("version")],
        ["retention_days", d.get("retention_days")],
        ["secondary_use", d.get("secondary_use")],
        ["contact", d.get("contact")],
        ["irb_reference", d.get("irb_reference")],
        ["consent_tiers", sorted(study.get("consent_tiers") or [])],
        ["default_tier", study.get("default_tier")],
        ["modalities", sorted(study.get("modalities") or [])],
        ["calibration", study.get("calibration")],
        ["tasks", study.get("tasks")],
    ]
    optional = [[key, get(study, d)] for key, get in _OPTIONAL_HASHED]
    return fixed + [pair for pair in optional if pair[1] is not None]


def content_hash(study: dict[str, Any]) -> str:
    """Must equal ``contentHash`` in the browser for the same study.

    `JSON.stringify` and this `json.dumps` agree only when the separators match
    and nothing needs escaping differently, hence `ensure_ascii=False` and the
    compact separators. A test hashes the real `studies/m0.json` in both
    languages, because a mismatch here would silently flag every session as
    having run under an edited protocol.
    """
    payload = json.dumps(canonicalise(study), separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_study(root: str | Path, study_id: str) -> dict[str, Any]:
    """Read and validate ``<root>/<study_id>.json``.

    Raises, unlike ``verify_session_study``: a caller asking for a study by id
    wants that study, and half of one is not useful.
    """
    if not _is_id(study_id):
        raise ValueError(f"not a usable study id: {study_id!r}")

    path = Path(root) / f"{study_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no study definition at {path}")

    study = json.loads(path.read_text(encoding="utf-8"))
    if study.get("study_id") != study_id:
        raise ValueError(
            f"{path} declares study_id {study.get('study_id')!r}, not {study_id!r}")

    verdict = validate_study(study)
    if not verdict.ok:
        raise ValueError(f"{path} is not a usable study: {'; '.join(verdict.reasons)}")
    return study


#: studies/index.json — the list the capture page offers when a URL names no
#: study (a static host cannot enumerate a directory).
STUDY_INDEX = "index.json"


def list_studies(root: str | Path) -> list[dict[str, Any]]:
    """Every study file, valid or not.

    Invalid ones are listed with their reasons rather than hidden. A researcher
    whose study stopped loading needs to see it and why, not an empty list.
    """
    root = Path(root)
    if not root.exists():
        return []

    out = []
    for path in sorted(root.glob("*.json")):
        # The capture page's chooser list, not a study. Without this it is
        # listed as a study that fails validation.
        if path.name == STUDY_INDEX:
            continue
        try:
            study = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            out.append({"study_id": path.stem, "valid": False,
                        "reasons": [f"unreadable: {exc}"]})
            continue

        verdict = validate_study(study)
        row = {
            "study_id": study.get("study_id", path.stem),
            "name": study.get("name"),
            "version": study.get("version"),
            "modalities": study.get("modalities") or [],
            "consent_tiers": study.get("consent_tiers") or [],
            "retention_days": (study.get("disclosure") or {}).get("retention_days"),
            "audience": audience_of(study),
            "valid": verdict.ok,
            "reasons": list(verdict.reasons),
        }
        if verdict.ok:
            row["content_hash"] = content_hash(study)
        out.append(row)
    return out


def verify_session_study(session_meta: dict[str, Any],
                         root: str | Path) -> Verdict:
    """Does this session's recorded protocol still match the file on disk?

    A finding rather than an exception. The session is already collected and is
    not made worse by being read; what would make it worse is treating it as
    comparable with sessions run under an edited protocol.

    Four outcomes worth distinguishing, because they need different responses:

    - no study block at all — a session captured before study definitions
      existed, or by a page that did not record one
    - the study file is gone — the protocol cannot be reconstructed
    - the file is there and the hash matches — comparable
    - the file is there and the hash DIFFERS — the study was edited after this
      session, and sessions on either side of that edit are not one study
    """
    recorded = session_meta.get("study")
    if not isinstance(recorded, dict) or not recorded.get("study_id"):
        return Verdict(False, ("no_study_recorded",),
                       {"study_id": session_meta.get("study_id")})

    study_id = recorded["study_id"]
    try:
        study = load_study(root, study_id)
    except (FileNotFoundError, ValueError) as exc:
        return Verdict(False, ("study_unavailable",),
                       {"study_id": study_id, "detail": str(exc)})

    actual = content_hash(study)
    claimed = recorded.get("study_content_hash")
    if claimed != actual:
        return Verdict(False, ("study_edited_since_session",), {
            "study_id": study_id,
            "recorded_hash": claimed,
            "file_hash": actual,
            "recorded_version": recorded.get("study_version"),
            "file_version": study.get("version"),
        })

    return Verdict(True, (), {"study_id": study_id, "content_hash": actual,
                              "version": study.get("version")})


def _is_id(v: Any) -> bool:
    if not isinstance(v, str) or not 0 < len(v) <= 64:
        return False
    if not (v[0].isascii() and v[0].isalnum()):
        return False
    return all(c.isascii() and (c.isalnum() or c in "_-") for c in v)


def _non_empty(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())
