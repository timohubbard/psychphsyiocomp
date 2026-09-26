"""Persistence for AOI definitions.

AOI sets are **configuration, not measurement**, and that distinction is what
lets the researcher app write these while staying read-only about everything
else. A measurement is something a participant produced and the pipeline
recorded; nothing in a UI should be able to alter one, because a UI that could
edit a measurement could quietly un-record a refusal. An AOI is a question
someone decided to ask of that data afterwards. Different thing, different
store, different rules.

**Versions are immutable and history is kept.** §4.2 records one tool's hit rate
moving 77% -> 88% -> 93% purely from iteratively refining the *same* AOI
definitions on the *same* gaze data. Refinement is legitimate and expected — but
if editing a set silently replaced it, every number computed under the old
boundaries would become unreproducible and unattributable. So saving a changed
set writes a new version beside the old one, and results reference the content
hash that produced them.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoi import AOI, AOISet


def _dir(root: str | Path) -> Path:
    return Path(root) / "aoi_sets"


def list_sets(root: str | Path) -> list[dict[str, Any]]:
    """Every saved AOI set, newest version of each first."""
    d = _dir(root)
    if not d.exists():
        return []

    out: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "name": raw.get("name"),
            "version": raw.get("version"),
            "content_hash": raw.get("content_hash"),
            "created_utc": raw.get("created_utc"),
            "n_aois": len(raw.get("aois", [])),
            "stimulus_id": raw.get("stimulus_id"),
            "file": path.name,
        })
    out.sort(key=lambda r: (r["name"] or "", r["created_utc"] or ""), reverse=True)
    return out


def load(root: str | Path, name: str, version: str | None = None) -> AOISet:
    """Load a set by name, defaulting to its newest version.

    Loading by name alone is a convenience for interactive use. Anything that
    records a result should record the `content_hash` it actually used, because
    "the newest version" means something different tomorrow.
    """
    candidates = [r for r in list_sets(root) if r["name"] == name]
    if version is not None:
        candidates = [r for r in candidates if r["version"] == version]
    if not candidates:
        raise FileNotFoundError(f"no AOI set named {name!r}"
                                + (f" at version {version!r}" if version else ""))

    raw = json.loads((_dir(root) / candidates[0]["file"]).read_text(encoding="utf-8"))
    return AOISet(
        name=raw["name"], version=raw["version"],
        aois=tuple(AOI(aoi_id=a["aoi_id"], shape=a["shape"],
                       coords=tuple(a["coords"]), label=a.get("label"))
                   for a in raw["aois"]),
        stimulus_id=raw.get("stimulus_id"),
    )


def save(root: str | Path, aoi_set: AOISet) -> dict[str, Any]:
    """Write a set, as a new version if its geometry changed.

    Returns a summary including whether anything was written. Saving an
    unchanged set is a no-op rather than a new identical version, so a
    researcher clicking save twice does not create history that implies they
    changed their mind.
    """
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)

    digest = aoi_set.content_hash()
    existing = [r for r in list_sets(root) if r["name"] == aoi_set.name]
    if any(r["content_hash"] == digest for r in existing):
        return {"written": False, "reason": "unchanged", "content_hash": digest}

    # Version numbers count revisions of this name. They are a human-readable
    # ordering; the content hash is the identity.
    version = str(len(existing) + 1)
    stored = AOISet(name=aoi_set.name, version=version, aois=aoi_set.aois,
                    stimulus_id=aoi_set.stimulus_id)

    payload = {
        "name": stored.name,
        "version": version,
        "content_hash": stored.content_hash(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        **({"stimulus_id": stored.stimulus_id} if stored.stimulus_id else {}),
        "aois": [asdict(a) for a in stored.aois],
        # Restated in every file rather than assumed to be common knowledge.
        # Anyone reading one of these years later needs to know that the
        # boundaries in it are part of any result computed from them.
        "note": (
            "AOI hit rates are highly sensitive to boundary definition. REPORT.md "
            "§4.2 records one tool's hit rate moving 77%->88%->93% purely from "
            "refining the same definitions on the same gaze data. Report this "
            "content_hash and the padding alongside any hit rate computed from it."
        ),
    }

    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stored.name)
    path = d / f"{safe}.v{version}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {"written": True, "version": version, "content_hash": stored.content_hash(),
            "file": path.name, "n_aois": len(stored.aois)}


def history(root: str | Path, name: str) -> list[dict[str, Any]]:
    """Every version of one set, oldest first.

    Exposed because §4.2's finding makes the revision trail part of the method:
    a reader should be able to see that the boundaries were refined, and how
    much the answer moved when they were.
    """
    rows = [r for r in list_sets(root) if r["name"] == name]
    rows.sort(key=lambda r: int(r["version"] or 0))
    return rows
