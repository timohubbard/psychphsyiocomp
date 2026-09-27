"""Persistence for human annotations, and the codebooks they are made against.

Like AOI sets, annotations are **not measurements**. A measurement is something
a participant produced and the pipeline recorded; an annotation is a judgement
a coder made about it afterwards. That is why the researcher app may write
these while staying read-only about the canonical tables — but it makes
annotations the second write path, so the distinction is worth being precise
about rather than assumed.

Three rules that fall out of what the annotations are *for*:

**Raters are kept apart, permanently.** The whole value of a human reference
standard is that you can measure how much the humans disagreed
(`evaluation.py`). Merging raters at write time destroys exactly the quantity
the reference standard exists to provide, and it cannot be recovered
afterwards. So one file per (codebook, session, rater), never a combined one.

**A rater must not see another rater's labels.** Independence is the
assumption every agreement coefficient rests on; a coder who can see what the
last one chose is not a second observation, and kappa computed over
contaminated labels reads high for the wrong reason. The read API therefore
serves one rater's own work back to them and nobody else's.

**Codebooks are versioned and hashed, like AOI sets and studies.** §4.2's
77 -> 88 -> 93 finding is about refining definitions on fixed data, and a
category list is a definition. Labels are stored against the codebook hash
they were made under, because "present" means something different once the
category description changes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: A rater is identified by a slug the researcher assigns — never by a name,
#: an email, or anything else that identifies a person. Coders are people too,
#: and a study's data files are not the place to record who coded what under
#: their own name.
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _dir(root: str | Path) -> Path:
    return Path(root) / "annotations"


def _codebook_dir(root: str | Path) -> Path:
    return Path(root) / "codebooks"


def _check_id(value: str, what: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.match(value):
        raise ValueError(f"{what} must be a slug of letters, digits, dash or "
                         f"underscore: {value!r}")
    return value


# ---------------------------------------------------------------------------
# codebooks
# ---------------------------------------------------------------------------

def codebook_hash(codebook: dict[str, Any]) -> str:
    """Hash what makes two coders' labels comparable: the categories AND the
    items.

    The description of a category is included on purpose. "Present" means
    something different once the definition of present changes, and labels made
    under the old wording are not comparable with labels made under the new.

    The item list is included for a sharper reason. The hash is the directory
    annotations are filed under, so leaving items out meant a codebook with a
    changed item list shared a bucket with the old one — and two raters who
    coded different sets of moments would be pooled as though they had coded
    the same ones. Every agreement coefficient over that is meaningless, and
    nothing about it would look wrong.

    Name and prose stay out: retitling a codebook does not change what was
    coded, and a hash that churns on prose gets ignored.
    """
    payload = json.dumps(
        [
            [[c.get("id"), c.get("label"), c.get("description")]
             for c in sorted(codebook.get("categories") or [],
                             key=lambda c: str(c.get("id")))],
            # Order matters here and is NOT sorted: the sequence a coder is
            # shown moments in is part of the protocol, for the same reason
            # calibration order is.
            [float(t) for t in (codebook.get("items") or [])],
        ],
        separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def validate_codebook(codebook: Any) -> tuple[bool, list[str]]:
    """A codebook that cannot be coded against is refused, not repaired."""
    reasons: list[str] = []
    if not isinstance(codebook, dict):
        return False, ["no codebook"]

    if not SAFE_ID.match(str(codebook.get("codebook_id", ""))):
        reasons.append("codebook_id must be a slug")
    if not str(codebook.get("name", "")).strip():
        reasons.append("no codebook name")

    cats = codebook.get("categories")
    if not isinstance(cats, list) or len(cats) < 2:
        # One category is not a decision. A coder who can only say "present"
        # produces labels with no variance, and every agreement coefficient
        # over them is undefined or meaningless.
        reasons.append("a codebook needs at least two categories")
    else:
        seen = set()
        for c in cats:
            if not isinstance(c, dict) or not SAFE_ID.match(str(c.get("id", ""))):
                reasons.append(f"category id must be a slug: {c!r}")
                continue
            if c["id"] in seen:
                reasons.append(f"duplicate category id: {c['id']}")
            seen.add(c["id"])
            if not str(c.get("label", "")).strip():
                reasons.append(f"category {c['id']} has no label")
            if not str(c.get("description", "")).strip():
                # Not pedantry. An undefined category is where coders diverge,
                # and the divergence shows up later as a low kappa nobody can
                # explain.
                reasons.append(
                    f"category {c['id']} has no description — an undefined "
                    f"category is where raters silently disagree")

    items = codebook.get("items")
    if not isinstance(items, list) or not items:
        reasons.append("no items to annotate")
    elif not all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in items):
        reasons.append("items must be timestamps in milliseconds")
    elif not all(math.isfinite(t) and t >= 0 for t in items):
        reasons.append("items must be finite, non-negative milliseconds into the recording")
    elif len({float(t) for t in items}) != len(items):
        # Labels are keyed by the moment, so a repeated moment collapses into
        # one label: the rater answers it once and is never counted complete.
        reasons.append("an item appears twice — each moment can be asked about once")

    return not reasons, reasons


def item_key(t: float | int | str) -> str:
    """The one spelling of a moment, used wherever labels are keyed by it.

    A browser writes 1000 as "1000" and Python writes 1000.0 as "1000.0"; keyed
    naively, a codebook stored with floats refused every label the coding page
    sent. Whole milliseconds are spelled as integers, everything else as the
    float's repr.
    """
    f = float(t)
    return str(int(f)) if f.is_integer() else repr(f)


def _canonical_items(items: list[Any]) -> list[int | float]:
    return [int(float(t)) if float(t).is_integer() else float(t) for t in items]


def check_codebook(codebook: Any) -> dict[str, Any]:
    """Validity, reasons and the hash it would be saved under — without saving.

    The codebook builder asks this on every edit, so the page never mirrors
    these rules in JavaScript that could drift from them.
    """
    ok, reasons = validate_codebook(codebook)
    try:
        content = codebook_hash(codebook) if isinstance(codebook, dict) else None
    except (TypeError, ValueError):
        content = None
    return {"valid": ok, "reasons": reasons, "content_hash": content}


def save_codebook(root: str | Path, codebook: dict[str, Any]) -> dict[str, Any]:
    """Write a codebook version. Existing versions are never overwritten."""
    ok, reasons = validate_codebook(codebook)
    if not ok:
        raise ValueError("; ".join(reasons))

    d = _codebook_dir(root)
    d.mkdir(parents=True, exist_ok=True)

    content = codebook_hash(codebook)
    record = dict(codebook)
    record["items"] = _canonical_items(codebook["items"])   # see item_key
    record["content_hash"] = content
    record["created_utc"] = datetime.now(timezone.utc).isoformat()

    path = d / f"{codebook['codebook_id']}.{content}.json"
    if path.exists():
        # Identical content: return the existing version rather than writing a
        # second copy with a new timestamp. Re-saving an unchanged codebook is
        # not a new version of it.
        return json.loads(path.read_text(encoding="utf-8"))

    path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return record


def load_codebook(root: str | Path, codebook_id: str,
                  content_hash: str | None = None) -> dict[str, Any]:
    _check_id(codebook_id, "codebook_id")
    d = _codebook_dir(root)
    if content_hash:
        _check_id(content_hash, "content_hash")
        path = d / f"{codebook_id}.{content_hash}.json"
        if not path.exists():
            raise FileNotFoundError(f"no codebook {codebook_id}@{content_hash}")
        return json.loads(path.read_text(encoding="utf-8"))

    matches = sorted(d.glob(f"{codebook_id}.*.json"))
    if not matches:
        raise FileNotFoundError(f"no codebook {codebook_id}")
    newest = max(matches, key=lambda p: json.loads(
        p.read_text(encoding="utf-8")).get("created_utc", ""))
    return json.loads(newest.read_text(encoding="utf-8"))


def list_codebooks(root: str | Path) -> list[dict[str, Any]]:
    d = _codebook_dir(root)
    if not d.exists():
        return []
    out = []
    for path in sorted(d.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # How much coding sits under this version — counts only, never labels,
        # so the builder can say what a change would leave behind without
        # anyone seeing what a rater chose.
        filed = list((_dir(root) / f"{raw.get('codebook_id')}.{raw.get('content_hash')}").glob("*.json"))
        out.append({
            "codebook_id": raw.get("codebook_id"),
            "name": raw.get("name"),
            "content_hash": raw.get("content_hash"),
            "created_utc": raw.get("created_utc"),
            "n_categories": len(raw.get("categories") or []),
            "n_items": len(raw.get("items") or []),
            "n_label_sets": len(filed),
            "n_sessions_coded": len({p.name.split(".")[0] for p in filed}),
        })
    out.sort(key=lambda r: (r["codebook_id"] or "", r["created_utc"] or ""),
             reverse=True)
    return out


# ---------------------------------------------------------------------------
# annotations
# ---------------------------------------------------------------------------

def _path(root, codebook_id, content_hash, session_id, rater_id) -> Path:
    return (_dir(root) / f"{codebook_id}.{content_hash}"
            / f"{session_id}.{rater_id}.json")


def save_annotation(root: str | Path, *, codebook_id: str, content_hash: str,
                    session_id: str, rater_id: str,
                    labels: dict[str, str]) -> dict[str, Any]:
    """Store one rater's labels for one session under one codebook version.

    Overwrites that rater's own previous submission — a coder revising their
    own work is normal — but can never touch another rater's file, because the
    rater id is part of the path rather than a field inside a shared one.
    """
    for value, what in ((codebook_id, "codebook_id"), (content_hash, "content_hash"),
                        (session_id, "session_id"), (rater_id, "rater_id")):
        _check_id(value, what)

    if not isinstance(labels, dict) or not labels:
        raise ValueError("no labels submitted")

    codebook = load_codebook(root, codebook_id, content_hash)
    valid = {str(c["id"]) for c in codebook["categories"]}
    unknown = sorted(set(labels.values()) - valid)
    if unknown:
        raise ValueError(f"labels not in this codebook version: {unknown}")

    items = {item_key(t) for t in codebook["items"]}
    try:
        labels = {item_key(k): v for k, v in labels.items()}
    except (TypeError, ValueError):
        raise ValueError("labels must be keyed by the item's milliseconds") from None
    stray = sorted(set(labels) - items)
    if stray:
        raise ValueError(f"labels for items not in this codebook: {stray[:5]}")

    path = _path(root, codebook_id, content_hash, session_id, rater_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "codebook_id": codebook_id,
        "codebook_content_hash": content_hash,
        "session_id": session_id,
        "rater_id": rater_id,
        "labels": labels,
        "n_items": len(codebook["items"]),
        "n_labelled": len(labels),
        "complete": len(labels) == len(codebook["items"]),
        "submitted_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return record


def load_annotation(root: str | Path, *, codebook_id: str, content_hash: str,
                    session_id: str, rater_id: str) -> dict[str, Any] | None:
    """One rater's own labels, for resuming their own work.

    Deliberately the only per-rater read: serving one coder another's labels
    would break the independence every agreement coefficient assumes.
    """
    for value, what in ((codebook_id, "codebook_id"), (content_hash, "content_hash"),
                        (session_id, "session_id"), (rater_id, "rater_id")):
        _check_id(value, what)
    path = _path(root, codebook_id, content_hash, session_id, rater_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def raters_for(root: str | Path, *, codebook_id: str, content_hash: str,
               session_id: str) -> list[dict[str, Any]]:
    """Who has coded this session, and how far they got — without their labels.

    Progress is not contamination; the labels are. A coordinator needs to know
    whether a second rater has finished, and can learn that without being shown
    what either of them chose.
    """
    for value, what in ((codebook_id, "codebook_id"), (content_hash, "content_hash"),
                        (session_id, "session_id")):
        _check_id(value, what)

    d = _dir(root) / f"{codebook_id}.{content_hash}"
    if not d.exists():
        return []

    out = []
    for path in sorted(d.glob(f"{session_id}.*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "rater_id": raw.get("rater_id"),
            "n_labelled": raw.get("n_labelled"),
            "n_items": raw.get("n_items"),
            "complete": raw.get("complete"),
            "submitted_utc": raw.get("submitted_utc"),
        })
    return out


def label_matrix(root: str | Path, *, codebook_id: str, content_hash: str,
                 session_id: str) -> dict[str, Any]:
    """All raters' labels, aligned on the items every one of them completed.

    This is the ONLY read that crosses raters, and it exists for
    `evaluation.py` rather than for a UI. Items any rater left blank are
    dropped rather than imputed: a coder who skipped an item did not label it,
    and filling it in with the majority would manufacture agreement out of
    someone's uncertainty — inflating exactly the ceiling the reference
    standard is supposed to measure honestly.
    """
    codebook = load_codebook(root, codebook_id, content_hash)
    rows = []
    for meta in raters_for(root, codebook_id=codebook_id,
                           content_hash=content_hash, session_id=session_id):
        rec = load_annotation(root, codebook_id=codebook_id,
                              content_hash=content_hash,
                              session_id=session_id, rater_id=meta["rater_id"])
        if rec:
            rows.append(rec)

    if not rows:
        return {"raters": [], "items": [], "labels": [], "n_dropped": 0}

    items = [item_key(t) for t in codebook["items"]]
    common = [t for t in items if all(t in r["labels"] for r in rows)]

    return {
        "raters": [r["rater_id"] for r in rows],
        "items": common,
        "labels": [[r["labels"][t] for t in common] for r in rows],
        "n_dropped": len(items) - len(common),
        "codebook_id": codebook_id,
        "codebook_content_hash": content_hash,
    }
