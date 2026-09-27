"""Saving study definitions and stimulus files from the study builder.

These are the researcher app's fourth and fifth write paths, and like the
other three they write CONFIGURATION, never measurement. Two rules make them
safe to expose in a UI:

**A study is fixed once anyone has been recorded under it.** Sessions record
the study's content hash, and server/study.py compares it with the file on
disk: editing a used study in place would make every one of its sessions
report "protocol edited since session", indistinguishable from a real edit
nobody meant. So a save over a study with sessions is refused; the builder
offers a new study_id instead (studies/README.md, "Immutable once used"). A
study with no sessions yet is a draft and may be overwritten — but only when
the caller says so, so a typo in a new id cannot silently replace another
study.

**A stimulus file is its hash.** Studies name stimuli by sha256, so replacing
a file with different bytes would change the picture under every study that
uses it, and the capture page would then refuse them all. Uploading different
bytes under an existing name is refused; identical bytes are a no-op.

Both are validated with the same server/study.py the pipeline uses, so the
builder cannot save something the capture page would refuse.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from study import STUDY_INDEX, content_hash, validate_study

#: What the builder may upload as a stimulus, and what kind each is.
STIMULUS_KINDS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
                  ".webm": "video", ".mp4": "video"}
MAX_STIMULUS_BYTES = 200 * 2**20
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


class StoreRefused(Exception):
    def __init__(self, status: int, detail: str, **extra: Any):
        super().__init__(detail)
        self.status = status
        self.extra = extra


def sessions_under(out_root: str | Path, study_id: str) -> list[str]:
    """Session ids recorded under a study, from the canonical tables."""
    import pyarrow.parquet as pq
    found = []
    for path in sorted(Path(out_root).glob("session_id=*/sessions.parquet")):
        for row in pq.read_table(path, columns=["session_id", "study_id"]).to_pylist():
            if row["study_id"] == study_id:
                found.append(row["session_id"])
    return found


def save_study(studies_root: str | Path, out_root: str | Path, study: dict[str, Any], *,
               overwrite: bool = False) -> dict[str, Any]:
    """Validate and write studies/<study_id>.json, and list it in the index."""
    verdict = validate_study(study)
    if not verdict.ok:
        raise StoreRefused(400, "the study does not validate", reasons=list(verdict.reasons))

    root = Path(studies_root)
    sid = study["study_id"]
    path = root / f"{sid}.json"
    if path.exists():
        used = sessions_under(out_root, sid)
        if used:
            raise StoreRefused(
                409, f"{len(used)} session(s) were recorded under {sid}; editing it would make "
                     "them all report an edited protocol. Save it under a new study_id.",
                sessions=used, suggestion=_next_id(root, sid))
        if not overwrite:
            raise StoreRefused(409, f"studies/{sid}.json already exists (no sessions yet). "
                                    "Confirm to overwrite this draft.", can_overwrite=True)

    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(study, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    index_path = root / STUDY_INDEX
    index = (json.loads(index_path.read_text(encoding="utf-8"))
             if index_path.exists() else {"studies": []})
    if sid not in index["studies"]:
        index["studies"].append(sid)
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return {"saved": f"studies/{sid}.json", "study_id": sid, "content_hash": content_hash(study)}


def _next_id(root: Path, sid: str) -> str:
    base = re.sub(r"-v\d+$", "", sid)
    n = 2
    while (root / f"{base}-v{n}.json").exists():
        n += 1
    return f"{base}-v{n}"


def save_stimulus(studies_root: str | Path, filename: str, data: bytes) -> dict[str, Any]:
    """Store an uploaded stimulus under studies/stimuli/. Returns its study item fields."""
    if not _NAME.match(filename) or ".." in filename:
        raise StoreRefused(400, "a stimulus file name may use letters, digits, . _ and - only")
    kind = STIMULUS_KINDS.get(Path(filename).suffix.lower())
    if kind is None:
        raise StoreRefused(400, f"stimuli must be one of {', '.join(sorted(STIMULUS_KINDS))}")
    if not data:
        raise StoreRefused(400, "the file is empty")
    if len(data) > MAX_STIMULUS_BYTES:
        raise StoreRefused(413, f"stimuli are capped at {MAX_STIMULUS_BYTES // 2**20} MB")

    digest = hashlib.sha256(data).hexdigest()
    folder = Path(studies_root) / "stimuli"
    path = folder / filename
    if path.exists():
        existing = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing != digest:
            raise StoreRefused(409, f"stimuli/{filename} already exists with different content; "
                                    "studies name it by hash, so it cannot be replaced. "
                                    "Upload it under a new name.")
    else:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {"src": f"stimuli/{filename}", "sha256": digest, "kind": kind, "bytes": len(data)}
