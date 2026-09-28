"""Export a study's cohort as one zip: CSV, a BIDS-style layout, heatmaps, provenance.

    npm run export -- <study_id> [--zip PATH] [--include-developer]

What goes in is decided by server/cohort.py — the declared exclusions, the
protocol check, self-tests left out — so an export is always a cohort, never
"whatever is in out/". Everything is keyed by the pseudonymous participant id.

**The zip is audited before it is kept.** It must contain no recording (no
.webm/.mp4/.wav), no identifiers.json, nothing from out/_keys/, and no raw
panel identifier anywhere in any file's bytes — checked against the
pseudonym link table itself. A failing export is deleted and the command
fails: an export is the thing most likely to leave the building.

**BIDS-style, not BIDS.** research/pass4b found no standard for irregular,
multi-source behavioural streams; BIDS is borrowed for its layout (sub-/ses-/
events.tsv, participants.tsv, dataset_description.json) and says so in the
README it writes. Signals go in long format per source, because they are not
regularly sampled and pretending otherwise would mean resampling on export.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

from cohort import EpochSpec, attrition_rows, epochs, select  # noqa: E402
from inference import as_rows, participant_curves, participant_rows, run_contrasts  # noqa: E402
from pseudonym import links  # noqa: E402
from session_qc import rows_for_export  # noqa: E402
from stimulus_summary import (DEFAULT_HEATMAP_SIGMA_DEG, heatmap, heatmap_png,  # noqa: E402
                              session_summary)
from study import load_study  # noqa: E402
from tables import read_session  # noqa: E402

MEDIA_SUFFIXES = (".webm", ".mp4", ".wav", ".mkv", ".mov")


class ExportRefused(Exception):
    pass


def _csv_bytes(rows: list[dict[str, Any]], delimiter: str = ",") -> bytes:
    buf = io.StringIO()
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(buf, fieldnames=keys, delimiter=delimiter, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})
    return buf.getvalue().encode("utf-8")


def _label(s: str) -> str:
    """A BIDS label: alphanumerics only."""
    return re.sub(r"[^A-Za-z0-9]", "", s or "") or "unknown"


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _withhold_typed(event: dict[str, Any], typed: set[str], include: bool) -> dict[str, Any]:
    """A response event with its typed text removed (and remembered, for the audit)."""
    if event.get("event_type") != "response" or not event.get("metadata"):
        return event
    meta = json.loads(event["metadata"])
    text = meta.get("value_text")
    if not text:
        return event
    if include:
        return event
    typed.add(text)
    meta.pop("value_text")
    meta["value_text_withheld"] = True
    return {**event, "metadata": json.dumps(meta)}


def response_rows(events: list[dict[str, Any]], sessions: list[dict[str, Any]],
                  include_free_text: bool) -> list[dict[str, Any]]:
    """One row per answered (or skipped) question: what questions.csv-style tools expect."""
    cond = {s["session_id"]: s.get("condition") for s in sessions}
    rows = []
    for e in events:
        if e.get("event_type") != "response" or not e.get("metadata"):
            continue
        m = json.loads(e["metadata"])
        row = {"session_id": e["session_id"], "participant_id": e["participant_id"],
               "condition": cond.get(e["session_id"]), "task_id": m.get("task_id"),
               "item_id": m.get("item_id"), "kind": m.get("kind"), "value": m.get("value"),
               "skipped": m.get("skipped"), "rt_ms": m.get("rt_ms"), "n_changes": m.get("n_changes"),
               "answered_master_ts": e.get("onset_master_ts")}
        if m.get("kind") == "text":
            row["value_text"] = m.get("value_text") if include_free_text else None
            row["value_text_withheld"] = bool(m.get("value_text_withheld")) and not include_free_text
        rows.append(row)
    return rows


def build(out: Path, study: dict[str, Any], zip_path: Path, *,
          include_developer: bool = False, allow_mixed: bool = False,
          studies_root: Path = ROOT / "studies", include_free_text: bool = False) -> dict[str, Any]:
    cohort = select(out, study, include_developer=include_developer, allow_mixed=allow_mixed)
    analysis = study.get("analysis") or {}
    files: dict[str, bytes] = {}
    sessions = cohort.included

    files["csv/sessions.csv"] = _csv_bytes(sessions)
    files["csv/attrition.csv"] = _csv_bytes(attrition_rows(cohort))
    # Every check behind "usable", with where each threshold came from — for
    # the included sessions only, like every other file here.
    files["csv/session_qc.csv"] = _csv_bytes(
        rows_for_export(out, sessions, study, cohort.analysis_hash, studies_root))

    all_events = []
    for s in sessions:
        sid = s["session_id"]
        ev = read_session(out, sid, "events").to_pylist()
        all_events += ev
        sig = read_session(out, sid, "signals").select(
            ["session_id", "participant_id", "source", "stream", "channel", "master_ts",
             "value", "value_text", "reliability_tier"]).to_pylist()
        files[f"csv/signals/{sid}.csv.gz"] = gzip.compress(_csv_bytes(sig), mtime=0)

    # Typed answers can carry a name or a diagnosis, so they leave the building
    # only when asked for. Withheld from every file, and the audit below checks
    # that no typed answer's text survives anywhere in the archive.
    typed: set[str] = set()
    all_events = [_withhold_typed(e, typed, include_free_text) for e in all_events]
    files["csv/events.csv"] = _csv_bytes([{k: v for k, v in e.items()
                                           if k not in ("native_clock_id",)} for e in all_events])
    files["csv/responses.csv"] = _csv_bytes(response_rows(all_events, sessions, include_free_text))

    epoch_rows_by = {}
    refusals = []
    for d in analysis.get("epochs", []):
        spec = EpochSpec.from_study(d)
        rows, ref = epochs(out, sessions, spec)
        epoch_rows_by[spec.name] = (spec, rows)
        refusals += ref
        files[f"csv/epochs_{spec.name}.csv"] = _csv_bytes(rows)
    files["csv/epoch_refusals.csv"] = _csv_bytes(refusals)

    # What every test below ran on: one curve per participant, not per epoch.
    for name, (spec, rows) in epoch_rows_by.items():
        prow = []
        for ch in spec.channels:
            prow += participant_rows(participant_curves(rows, ch), name, ch)
        files[f"csv/participant_epochs_{name}.csv"] = _csv_bytes(prow)
    contrast_summary = []
    if analysis.get("contrasts"):
        results = run_contrasts(analysis, {n: rows for n, (_, rows) in epoch_rows_by.items()})
        crow, clrow = as_rows(results, cohort.analysis_hash)
        files["csv/contrasts.csv"] = _csv_bytes(crow)
        files["csv/clusters.csv"] = _csv_bytes(clrow)
        for c in analysis["contrasts"]:
            files[f"analysis/{c['name']}.R"] = r_script(
                c, epoch_rows_by[c["epochs"]][0], study_id=cohort.study_id,
                protocol=cohort.content_hash, analysis=cohort.analysis_hash).encode("utf-8")
        contrast_summary = [{"name": r["name"], "seed": r["seed"], "n_permutations": r["n_permutations"],
                             "refusal": (r.get("refusal") or {}).get("reason")} for r in results]

    # Facial response per stimulus: the mean baseline-corrected value over the
    # time the stimulus was up, from every epoch set locked to stimuli.
    face = {}
    for spec, rows in epoch_rows_by.values():
        if spec.event_type != "stimulus":
            continue
        for r in rows:
            if r["t_ms"] >= 0:
                key = (r["session_id"], r["participant_id"], r["condition"], r["stimulus_id"],
                       r["channel"], spec.name)
                face.setdefault(key, []).append(r["value_bc"])
    files["csv/stimulus_face.csv"] = _csv_bytes([
        {"session_id": k[0], "participant_id": k[1], "condition": k[2], "stimulus_id": k[3],
         "channel": k[4], "epoch_set": k[5], "mean_change_from_baseline": sum(v) / len(v),
         "n_samples": len(v)} for k, v in sorted(face.items())])

    pad = analysis.get("aoi_pad_deg")
    gaze_rows, aoi_rows, blink_rows, heart_rows, stim_refusals = [], [], [], [], []
    for s in sessions:
        r = session_summary(out, s, pad_deg=pad)
        gaze_rows += r["gaze"]
        aoi_rows += r["aoi"]
        blink_rows += r["blinks"]
        heart_rows += r["heart"]
        stim_refusals += r["refusals"]
    files["csv/stimulus_gaze.csv"] = _csv_bytes(gaze_rows)
    files["csv/stimulus_aoi.csv"] = _csv_bytes(aoi_rows)
    files["csv/stimulus_blinks.csv"] = _csv_bytes(blink_rows)
    # Every row tiered unvalidated: camera heart rate has no reference yet.
    files["csv/stimulus_heart.csv"] = _csv_bytes(heart_rows)
    files["csv/stimulus_refusals.csv"] = _csv_bytes(stim_refusals)

    sigma = analysis.get("heatmap_sigma_deg", DEFAULT_HEATMAP_SIGMA_DEG)
    heat_summary = {}
    items = {it["stimulus_id"]: it for t in study.get("tasks") or [] if t.get("type") == "stimuli"
             for it in t.get("items", [])}
    for stim_id, item in items.items():
        density, n, ref = heatmap(out, sessions, stim_id, sigma_deg=sigma)
        stim_refusals += ref
        heat_summary[stim_id] = {"participants": n, "sigma_deg": sigma}
        if density is None:
            continue
        files[f"heatmaps/{stim_id}.csv"] = "\n".join(
            ",".join(f"{v:.6g}" for v in row) for row in density).encode("utf-8")
        tmp = zip_path.with_suffix(f".{stim_id}.png")
        heatmap_png(density, tmp, background=studies_root / item["src"]
                    if item["kind"] == "image" else None)
        files[f"heatmaps/{stim_id}.png"] = tmp.read_bytes()
        tmp.unlink()

    files.update(_bids(study, sessions, all_events, out))

    files["provenance.json"] = json.dumps({
        "study_id": cohort.study_id, "study_version": study.get("version"),
        "protocol_content_hash": cohort.content_hash, "analysis_hash": cohort.analysis_hash,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "platform_commit": _git_commit(),
        "include_developer": include_developer, "allow_mixed": allow_mixed,
        "funnel": [{"step": f.label, "remaining": f.remaining} for f in cohort.funnel],
        "heatmaps": heat_summary,
        "contrasts": contrast_summary,
        "typed_answers": "included" if include_free_text else "withheld (npm run export -- --include-free-text)",
        "participant_ids": "pseudonymous (server/pseudonym.py); no raw panel identifier "
                           "is in this archive — audited before it was written",
    }, indent=2).encode("utf-8")

    _audit(files, out, withheld=typed)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    return {"zip": str(zip_path), "files": len(files), "sessions": len(sessions),
            "funnel": [(f.label, f.remaining) for f in cohort.funnel]}


def r_script(contrast: dict[str, Any], spec: EpochSpec, *, study_id: str, protocol: str,
             analysis: str) -> str:
    """A mixed-model analysis of one declared contrast, as R — generated, not run.

    The permutation tests in contrasts.csv are the preregistered result. A mixed
    model is the analysis a reviewer will ask for next (REPORT.md §4.4: random
    intercepts for participant and item, GAMMs for the time course), and
    fitting one well means choices about random slopes that should be made by
    the person defending them. So this writes the model rather than running a
    guess at it, with the hashes that say which data and which plan it is for.
    """
    lo, hi = contrast["window_ms"]
    a, b = contrast["arms"]
    items = spec.event_type == "stimulus"
    item_term = " + (1 | stimulus_id)" if items else ""
    item_by = " + stimulus_id" if items else ""
    return f"""# GENERATED, NOT RUN — review every modelling choice before relying on it.
# study {study_id} · protocol {protocol} · analysis plan {analysis}
# contrast "{contrast['name']}": {a} vs {b} on {contrast['channel']} ({contrast['epochs']}), window {lo}..{hi} ms
#
# The preregistered result is the permutation test in csv/contrasts.csv
# (seed {contrast['seed']}, {contrast['n_permutations']} permutations). These models are the
# follow-up a reviewer will ask for; their random-effects structure is yours to defend.
# Self-test sessions share participant_id "anonymous" but are not one person: an
# export for analysis should not contain them (npm run export without --include-developer).

library(lme4)
library(mgcv)

d <- read.csv("csv/epochs_{contrast['epochs']}.csv")
d <- subset(d, channel == "{contrast['channel']}" & condition %in% c("{a}", "{b}"))
d$condition <- factor(d$condition, levels = c("{b}", "{a}"))   # estimate: {a} minus {b}
d$participant_id <- factor(d$participant_id)

# 1. Window means, one per epoch, with random intercepts for participant{' and stimulus' if items else ''}.
w <- aggregate(value_bc ~ participant_id + session_id + epoch{item_by} + condition,
               data = subset(d, t_ms >= {lo} & t_ms <= {hi}), FUN = mean)
m_window <- lmer(value_bc ~ condition + (1 | participant_id){item_term}, data = w)
summary(m_window)

# 2. The time course: a smooth per condition, and a random smooth per participant
#    (factor smooths, van Rij et al. 2019). Compare with the cluster test in csv/clusters.csv.
m_time <- bam(value_bc ~ condition + s(t_ms, by = condition, k = 20)
              + s(t_ms, participant_id, bs = "fs", m = 1, k = 10),
              data = d, discrete = TRUE)
summary(m_time)
"""


def _bids(study: dict[str, Any], sessions: list[dict[str, Any]], events: list[dict[str, Any]],
          out: Path) -> dict[str, bytes]:
    task = _label(study["study_id"])
    files = {
        "bids/dataset_description.json": json.dumps({
            "Name": study.get("name"), "BIDSVersion": "1.9.0", "DatasetType": "raw",
            "GeneratedBy": [{"Name": "open-behavioral-platform", "CodeURL": "local"}],
        }, indent=2).encode(),
        "bids/README": (
            "BIDS-style layout, NOT validated BIDS. BIDS has no specification for\n"
            "irregularly sampled, multi-source behavioural streams (webcam gaze, facial\n"
            "action units, voice features). The layout (sub-/ses-, events.tsv,\n"
            "participants.tsv) is borrowed for familiarity. Timeseries are long-format\n"
            "per source (onset in seconds from recording start, channel, value) because\n"
            "resampling them on export would invent samples.\n").encode(),
        "bids/participants.tsv": _csv_bytes(
            [{"participant_id": f"sub-{p}", "condition": c} for p, c in sorted({
                (_label(s["participant_id"]), s.get("condition") or "n/a") for s in sessions})],
            delimiter="\t"),
    }
    by_session: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_session.setdefault(e["session_id"], []).append(e)
    for s in sessions:
        sub, ses = _label(s["participant_id"]), _label(s["session_id"])
        stem = f"bids/sub-{sub}/ses-{ses}/beh/sub-{sub}_ses-{ses}_task-{task}"
        evs = by_session.get(s["session_id"], [])
        start = next((e["onset_master_ts"] for e in evs if e["event_type"] == "recording_start"
                      and e["onset_master_ts"] is not None), None)
        if start is None:
            start = min((e["onset_master_ts"] for e in evs if e["onset_master_ts"] is not None),
                        default=0.0)
        files[f"{stem}_events.tsv"] = _csv_bytes([{
            "onset": round((e["onset_master_ts"] - start) / 1000, 6),
            "duration": (round((e["offset_master_ts"] - e["onset_master_ts"]) / 1000, 6)
                         if e["offset_master_ts"] is not None else "n/a"),
            "trial_type": e["event_type"], "stimulus_id": e.get("stimulus_id") or "n/a",
        } for e in evs if e["onset_master_ts"] is not None], delimiter="\t")
        sig = read_session(out, s["session_id"], "signals").to_pylist()
        for src in sorted({r["source"] for r in sig}):
            rows = [{"onset": round((r["master_ts"] - start) / 1000, 6), "channel": r["channel"],
                     "value": r["value"] if r["value"] is not None else r["value_text"]}
                    for r in sig if r["source"] == src and r["master_ts"] is not None]
            files[f"{stem}_desc-{_label(src)}_timeseries.tsv.gz"] = gzip.compress(
                _csv_bytes(rows, delimiter="\t"), mtime=0)
    return files


def _audit(files: dict[str, bytes], out: Path, withheld: set[str] = frozenset()) -> None:
    """Refuse an archive that carries media, identifiers, keys, a raw panel ID,
    or a typed answer that was meant to be withheld."""
    problems = []
    for name in files:
        low = name.lower()
        if low.endswith(MEDIA_SUFFIXES):
            problems.append(f"{name}: a recording")
        if "identifiers.json" in low or "_keys" in low or low.endswith(".key"):
            problems.append(f"{name}: identifying or key material")
    raws = {r["raw_participant_id"] for r in links(out) if r.get("raw_participant_id")}
    for name, data in files.items():
        blob = gzip.decompress(data) if name.endswith(".gz") else data
        for raw in raws:
            if raw.encode("utf-8") in blob:
                problems.append(f"{name}: contains a raw panel identifier")
        # Short answers ("no", "ok") would match by chance; the identifying
        # ones are longer. JSON-escaped too, since that is how events carry it.
        for text in (t for t in withheld if len(t.strip()) >= 8):
            if text.encode("utf-8") in blob or json.dumps(text)[1:-1].encode("utf-8") in blob:
                problems.append(f"{name}: contains a typed answer that should have been withheld")
    if problems:
        raise ExportRefused("export refused — " + "; ".join(sorted(set(problems))))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("study_id")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--studies", type=Path, default=ROOT / "studies")
    ap.add_argument("--zip", type=Path, default=None)
    ap.add_argument("--include-developer", action="store_true")
    ap.add_argument("--allow-mixed", action="store_true")
    ap.add_argument("--include-free-text", action="store_true",
                    help="include typed answers (they can identify people; withheld by default)")
    args = ap.parse_args(argv)

    study = load_study(args.studies, args.study_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = args.zip or args.out / "exports" / f"{args.study_id}-{stamp}.zip"
    try:
        summary = build(args.out, study, zip_path, include_developer=args.include_developer,
                        allow_mixed=args.allow_mixed, studies_root=args.studies,
                        include_free_text=args.include_free_text)
    except ExportRefused as exc:
        print(f"\n  {exc}\n")
        return 1
    print(f"\n  EXPORT  {args.study_id}")
    for label, n in summary["funnel"]:
        print(f"    {n:>5}  {label}")
    print(f"\n  {summary['sessions']} session(s), {summary['files']} file(s) -> {summary['zip']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
