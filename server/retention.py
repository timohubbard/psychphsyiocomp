"""Retention and withdrawal: make the consent screen's deletion promise true.

The consent screen tells every participant their data "is kept for N days and
then deleted". Until this module, `features_only` was enforced (the recording
is deleted after the engines run — `pipeline.enforce_consent`) but N was not:
`consent_retention_days` was written to the sessions table and read by nothing,
so retained media and every derived row lived indefinitely. A declared field
nothing reads is this codebase's recurring defect class, and this one was a
promise to a participant. research/pass5-legal-gaps.md, synthesis item 1:
BIPA §15(a), Colorado's deletion schedule, GDPR Art 5(1)(e) and Art 17(1)(b)
all turn on deletion actually happening.

What "your data" means here is what the screen says: everything. A session's
footprint is

    out/session_id=<id>/                       every derived table
    out/annotations/*/<id>.<rater>.json        labels about the recording
    <media root>/<folder>/                     the raw bundle — session.json,
                                               browser_chunks.json, the capture,
                                               and the audio and playback caches
                                               written beside it

AOI sets and codebooks are not keyed by session and are method configuration,
so they stay.

Three rules, each a refusal rather than a guess:

**The participant's own record decides, not the study file.** Expiry is the
session's start plus the retention period *that participant was shown*, read
from the session's own consent record. A study edited afterwards to a longer
period cannot extend a promise already made.

**No recorded period means no automatic deletion.** The two pilots predate
consent tiers. Deleting a recording on the strength of a missing field is not a
recoverable mistake — the same rule `enforce_consent` follows — so such a
session is reported as having no expiry, never swept.

**Deletion leaves a tombstone, and processing honours it.** A downloaded bundle
usually has copies (the browser's Downloads folder, a zip). Without a record,
re-running `process` on one would quietly resurrect a withdrawn participant.
`out/deletions.jsonl` records the session id, the reason and the time — and
deliberately not the participant id, which would make the log itself the
thing that should have been deleted. `refusal_for` is what `process_bundle`
checks before it writes anything.

Nothing here deletes by default. Both commands print exactly what would go and
act only with --apply.

    npm run retention                       what has expired, and what would go
    npm run retention -- --apply            delete it
    npm run withdraw -- <session or participant id> [--apply]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
TOMBSTONES = "deletions.jsonl"


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    participant_id: str | None
    study_id: str | None
    started_utc: datetime | None
    consent_tier: str | None
    retention_days: int | None
    #: Where the record was read from: 'table' (processed) or 'bundle' (a raw
    #: download never processed — it still carries a promise).
    origin: str

    def expires_utc(self) -> datetime | None:
        if self.started_utc is None or self.retention_days is None:
            return None
        return self.started_utc + timedelta(days=self.retention_days)

    def no_expiry_reason(self) -> str | None:
        if self.retention_days is None:
            return "no_retention_recorded"
        if self.started_utc is None:
            return "no_start_time_recorded"
        return None


@dataclass
class DeletionPlan:
    session_id: str
    paths: list[Path] = field(default_factory=list)
    #: Things that belong to the session but will not be deleted automatically,
    #: each with the reason — surfaced so they are dealt with by hand, not missed.
    manual: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# reading what exists
# ---------------------------------------------------------------------------

def _utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int | None:
    # bool is an int in Python; a retention period of True is not one day.
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bundle_manifests(media_roots: Iterable[Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Every session.json under the media roots — one level down, and at the root.

    The root itself is included so that a bundle downloaded straight into it (as
    the pilot's once was) is still found and reported, even though it is never
    deleted automatically.
    """
    found = []
    for root in media_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for manifest in [root / "session.json", *sorted(root.glob("*/session.json"))]:
            if not manifest.is_file():
                continue
            try:
                found.append((manifest, json.loads(manifest.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError):
                continue
    return found


def _from_table(session_dir: Path) -> SessionRecord | None:
    path = session_dir / "sessions.parquet"
    if not path.exists():
        return None
    rows = pq.read_table(path).to_pylist()
    if not rows:
        return None
    r = rows[0]
    return SessionRecord(
        session_id=r["session_id"], participant_id=r.get("participant_id"),
        study_id=r.get("study_id"), started_utc=_utc(r.get("started_utc")),
        consent_tier=r.get("consent_tier"),
        retention_days=_int(r.get("consent_retention_days")), origin="table")


def _from_manifest(meta: dict[str, Any]) -> SessionRecord:
    consent = meta.get("consent") or {}
    return SessionRecord(
        session_id=meta["session_id"], participant_id=meta.get("participant_id"),
        study_id=meta.get("study_id"), started_utc=_utc(meta.get("created_utc")),
        consent_tier=consent.get("tier"),
        retention_days=_int(consent.get("retentionDays")), origin="bundle")


def collect_sessions(out: Path, media_roots: Iterable[Path]) -> dict[str, SessionRecord]:
    """Every session anywhere, processed or not, keyed by session id.

    A bundle that was downloaded and never processed carries the same promise as
    one that was, so it is found from its own session.json. Where both exist
    the table wins: it is the record the pipeline wrote from that manifest.
    """
    sessions: dict[str, SessionRecord] = {}
    for _, meta in _bundle_manifests(media_roots):
        if meta.get("session_id"):
            sessions[meta["session_id"]] = _from_manifest(meta)
    for session_dir in sorted(Path(out).glob("session_id=*")):
        rec = _from_table(session_dir)
        if rec is not None:
            sessions[rec.session_id] = rec
    return sessions


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def plan_deletion(session_id: str, out: Path, media_roots: Iterable[Path]) -> DeletionPlan:
    """Everything on disk that belongs to one session. Deletes nothing."""
    out = Path(out)
    plan = DeletionPlan(session_id)

    session_dir = out / f"session_id={session_id}"
    if session_dir.is_dir():
        plan.paths.append(session_dir)

    # Labels are keyed <codebook>.<hash>/<session>.<rater>.json. Matched on the
    # exact session id plus the dot, so s_ab never takes s_abc's labels with it.
    for label in sorted((out / "annotations").glob(f"*/{session_id}.*.json")):
        plan.paths.append(label)

    roots = [Path(r).resolve() for r in media_roots]
    protected = [*roots, out.resolve(), ROOT]
    for manifest, meta in _bundle_manifests(media_roots):
        if meta.get("session_id") != session_id:
            continue
        folder = manifest.parent.resolve()
        if any(p == folder or folder in p.parents for p in protected):
            # Never delete a media root, the output root, the repo, or anything
            # containing one of them. A bundle sitting loose in such a directory
            # shares it with everything else there, and picking its files out by
            # name is the guess this module refuses to make.
            plan.manual.append(
                f"{manifest.parent}: bundle files are not in a folder of their "
                "own — delete this session's files by hand")
            continue
        plan.paths.append(manifest.parent)
    return plan


def expired(sessions: dict[str, SessionRecord], now: datetime) -> list[SessionRecord]:
    return sorted((s for s in sessions.values()
                   if s.expires_utc() is not None and s.expires_utc() <= now),
                  key=lambda s: (s.expires_utc(), s.session_id))


def resolve_withdrawal(identifier: str,
                       sessions: dict[str, SessionRecord]) -> list[SessionRecord]:
    """A session id names one session; a participant id names all of theirs.

    Withdrawal is by the person, so a participant id must reach every session
    they took part in — including ones only present as unprocessed bundles.
    """
    if identifier in sessions:
        return [sessions[identifier]]
    return sorted((s for s in sessions.values() if s.participant_id == identifier),
                  key=lambda s: s.session_id)


# ---------------------------------------------------------------------------
# acting
# ---------------------------------------------------------------------------

def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def apply_deletion(plan: DeletionPlan, record: SessionRecord | None, out: Path,
                   reason: str, now: datetime) -> dict[str, Any]:
    """Delete everything in the plan and write the tombstone.

    The tombstone is written LAST, after every deletion succeeded: a log that
    said a session was gone while its files were still there would be worse
    than no log.
    """
    for path in plan.paths:
        _remove(path)
    stone = {
        "session_id": plan.session_id,
        "study_id": record.study_id if record else None,
        "reason": reason,
        "deleted_utc": now.isoformat(),
        "removed": [_describe(p, Path(out)) for p in plan.paths],
        "manual": plan.manual,
    }
    Path(out).mkdir(parents=True, exist_ok=True)
    with open(Path(out) / TOMBSTONES, "a", encoding="utf-8") as f:
        f.write(json.dumps(stone, sort_keys=True) + "\n")
    return stone


def _describe(path: Path, out: Path) -> str:
    """What was removed, without writing folder names a person chose.

    A bundle folder is named by whoever downloaded it, and might carry a
    participant's name. The kind of thing removed is enough for the record.
    """
    try:
        rel = path.resolve().relative_to(out.resolve())
    except ValueError:
        return "raw bundle folder"
    return "derived tables" if rel.parts[0].startswith("session_id=") else "annotation"


def tombstones(out: Path) -> dict[str, dict[str, Any]]:
    path = Path(out) / TOMBSTONES
    if not path.exists():
        return {}
    stones = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            s = json.loads(line)
            stones[s["session_id"]] = s
    return stones


def refusal_for(out: Path, session_id: str, manifest: dict[str, Any],
                now: datetime | None = None) -> str | None:
    """Why this bundle must not be processed, or None if it may be.

    Checked by process_bundle before anything is written. A deleted session is
    refused whatever copy of it turns up; an expired one is refused because
    processing it would create data past the date the participant was told it
    would be gone.
    """
    now = now or datetime.now(timezone.utc)
    stone = tombstones(out).get(session_id)
    if stone:
        return (f"session {session_id} was deleted on {stone['deleted_utc'][:10]} "
                f"({stone['reason']}). This bundle is a leftover copy — delete it "
                "rather than process it.")
    expires = _from_manifest(manifest).expires_utc()
    if expires is not None and expires <= now:
        return (f"session {session_id} expired on {expires.date()} under the "
                "retention period its participant was shown. Run `npm run "
                "retention -- --apply` instead of processing it.")
    return None


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def _print_plan(plan: DeletionPlan) -> None:
    if not plan.paths and not plan.manual:
        print("      nothing on disk")
    for p in plan.paths:
        print(f"      {p}")
    for m in plan.manual:
        print(f"      MANUAL  {m}")


def _run(targets: list[SessionRecord], out: Path, media: list[Path], reason: str,
         apply: bool, now: datetime) -> int:
    for rec in targets:
        plan = plan_deletion(rec.session_id, out, media)
        print(f"\n  {rec.session_id}  (study {rec.study_id}, {rec.origin})")
        _print_plan(plan)
        if apply:
            apply_deletion(plan, rec, out, reason, now)
            print("      deleted")
    if targets and not apply:
        print("\n  dry run — nothing deleted. Add --apply to delete the above.")
    print("\n  Copies outside these folders — the browser's Downloads, a zip, a "
          "backup — are not found by this and must be removed by hand.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # On each subcommand rather than the top level, because the npm scripts
    # fix the subcommand and everything the user types lands after it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", type=Path, default=ROOT / "out")
    common.add_argument("--media", type=Path, action="append",
                        help="raw bundle root; repeatable (default: tempdata)")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sw = sub.add_parser("sweep", parents=[common],
                        help="delete sessions past their retention period")
    sw.add_argument("--apply", action="store_true")
    wd = sub.add_parser("withdraw", parents=[common],
                        help="delete one participant's or session's data")
    wd.add_argument("identifier", help="a session id or a participant id")
    wd.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    media = args.media or [ROOT / "tempdata"]
    now = datetime.now(timezone.utc)
    sessions = collect_sessions(args.out, media)

    print(f"  derived data   {args.out}")
    print(f"  raw bundles    {', '.join(str(m) for m in media)}")

    if args.cmd == "withdraw":
        targets = resolve_withdrawal(args.identifier, sessions)
        if not targets:
            print(f"\n  no session or participant '{args.identifier}' found — "
                  "nothing deleted")
            return 1
        print(f"\n  WITHDRAWAL of {args.identifier}: {len(targets)} session(s)")
        return _run(targets, args.out, media, "withdrawn", args.apply, now)

    due = expired(sessions, now)
    print(f"\n  {len(sessions)} session(s) found, {len(due)} past retention")
    for s in sorted(sessions.values(), key=lambda s: s.session_id):
        exp = s.expires_utc()
        state = (s.no_expiry_reason() if exp is None
                 else f"EXPIRED {exp.date()}" if exp <= now
                 else f"kept until {exp.date()}")
        print(f"    {s.session_id:<22} {str(s.consent_tier):<22} {state}")
    if not due:
        return 0
    return _run(due, args.out, media, "retention_expired", args.apply, now)


if __name__ == "__main__":
    sys.exit(main())
