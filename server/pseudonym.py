"""Pseudonymous participant identifiers, and the table that links them back.

A panel identifier (a Prolific ID) is a direct identifier: the panel can name
the person behind it. The capture page keeps it out of session.json and writes
it to identifiers.json instead (web/src/recruitment.js). This module turns it
into a pseudonym before any table is written, so the canonical tables, the
researcher app and every export carry only `p_…`.

**Keyed, not a plain hash.** SHA-256 of a Prolific ID is reversible by anyone
who can enumerate or guess IDs, which is the panel itself. An HMAC with a key
that never leaves the deploying group is not, and the same ID still maps to the
same pseudonym across that group's sessions — which cohort analysis needs.

**The link is kept, apart.** Withdrawal arrives as "please delete my data —
my Prolific ID is 5f3…", so the raw ID must be resolvable to the pseudonym.
`out/_keys/linking.jsonl` holds exactly that, beside the key, and nothing
else holds it: UK GDPR Art 89(1) names pseudonymisation with the additional
information kept separately as the research safeguard (research/pass5).
Withdrawal removes the participant's rows from it (server/retention.py).

Both files are gitignored. Losing the key makes future pseudonyms differ from
past ones; it is written once and never rotated by this code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEY_FILE = "pseudonym.key"
LINK_FILE = "linking.jsonl"
PREFIX = "p_"


def _dir(out_root: str | Path) -> Path:
    return Path(out_root) / "_keys"


def _key(out_root: str | Path) -> bytes:
    """The deployment's key, created on first use."""
    d = _dir(out_root)
    path = d / KEY_FILE
    if not path.exists():
        d.mkdir(parents=True, exist_ok=True)
        # Exclusive create: two processes starting at once must not each write
        # a different key and split one participant into two pseudonyms.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(secrets.token_hex(32))
    return bytes.fromhex(path.read_text(encoding="utf-8").strip())


def pseudonym(out_root: str | Path, platform: str, raw_id: str) -> str:
    """`p_` + 16 hex of HMAC-SHA256(key, "platform:raw_id")."""
    msg = f"{platform}:{raw_id}".encode("utf-8")
    return PREFIX + hmac.new(_key(out_root), msg, hashlib.sha256).hexdigest()[:16]


def links(out_root: str | Path) -> list[dict[str, Any]]:
    path = _dir(out_root) / LINK_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def link(out_root: str | Path, ids: dict[str, Any], session_id: str) -> str:
    """Pseudonymise one session's identifiers and record the link. Returns the pseudonym."""
    platform = str(ids.get("platform") or "url")
    raw = ids.get("participant")
    if not isinstance(raw, str) or not raw:
        raise ValueError("identifiers.json has no participant identifier")
    p = pseudonym(out_root, platform, raw)
    if not any(r["pseudonym"] == p and r.get("session_id") == session_id
               for r in links(out_root)):
        d = _dir(out_root)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / LINK_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "pseudonym": p, "platform": platform, "raw_participant_id": raw,
                "panel_study_id": ids.get("study"), "panel_session_id": ids.get("session"),
                "session_id": session_id,
                "linked_utc": datetime.now(timezone.utc).isoformat(),
            }, sort_keys=True) + "\n")
    return p


def resolve(out_root: str | Path, raw_id: str) -> set[str]:
    """Every pseudonym a raw panel identifier maps to (any platform)."""
    return {r["pseudonym"] for r in links(out_root) if r.get("raw_participant_id") == raw_id}


def forget_sessions(out_root: str | Path, session_ids: set[str]) -> int:
    """Remove the linking rows of deleted sessions. Returns how many went.

    By session, because a link row is written per session: once a session's
    data is gone, the row tying its pseudonym to a person has nothing left to
    point at and would be the last identifying trace of it.
    """
    rows = links(out_root)
    keep = [r for r in rows if r.get("session_id") not in session_ids]
    if len(keep) != len(rows):
        path = _dir(out_root) / LINK_FILE
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in keep),
                        encoding="utf-8")
    return len(rows) - len(keep)


def apply_to_bundle(out_root: str | Path, bundle, bundle_dir: str | Path) -> str | None:
    """Replace a bundle's participant_id with its pseudonym, if it has identifiers.

    Called by process_bundle before anything is written. Returns the pseudonym,
    or None for a bundle with no identifiers.json (it keeps whatever id its
    manifest carried — "anonymous" for a session run without panel IDs).
    """
    path = Path(bundle_dir) / "identifiers.json"
    if not path.exists():
        return None
    ids = json.loads(path.read_text(encoding="utf-8"))
    p = link(out_root, ids, bundle.session_id)
    bundle.participant_id = p
    bundle.metadata["participant_id"] = p
    return p
