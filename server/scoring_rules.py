"""Scoring rules: how an engine's output is read as a codebook category.

Human labels (annotation_store) give a reference standard and its ceiling
(evaluation.reference_from). To score an ENGINE against it, its continuous
output has to become one of the codebook's categories at each coded moment —
"AU12 above 0.5 means smiling", "gaze on screen for most of the window means
looking at the screen". That mapping is a decision, and a result is only
attributable if the decision is fixed, named and hashed before the score is
seen. So it is a record, like a codebook or an AOI set:

    out/scoring_rules/<rule_id>.<hash>.json      immutable, one file per version

A rule names ONE source (never "any": two engines are two measurements), one
channel or a derived predicate, the window around each moment, how the window
is summarised, and ordered bins from value to category. It is bound to one
codebook version, because the categories and the moments are that version's.

**Moments are recording time; signals are selected on the master clock.**
A codebook item is milliseconds into the session's recording (the coding page
seeks the video there). Every server engine's rows carry a clock solution from
the recording's clock to the master clock (runs.clock_offset_ms, clock_rate),
so each moment is converted once — master = item × rate + offset — and rows
are selected by master_ts. That works for every source, including the gaze
estimator whose rows are already on the master clock.

**The recording's own zero is checked, not assumed.** The mapping above holds
only if the container starts at 0, so that the browser's currentTime and the
engines' frame times share an origin. `pts_origin` reads the start time of the
raw recording and of the remuxed playback copy the coding page actually plays;
anything else refuses the engine arm for that session.

**An engine that abstains is not scored on the easy half.** Moments with too
few samples in the window get no prediction. The reference is recomputed on
exactly the answered moments so the ceiling stays comparable, coverage is
reported, and below 80% coverage the score is refused — dropping the moments
where the face was lost would flatter every engine.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.compute as pc

import annotation_store
from tables import read_session

SAFE_ID = annotation_store.SAFE_ID
STATISTICS = ("median", "mean", "max")
DERIVED = ("gaze_onscreen",)
MIN_COVERAGE = 0.8
RULE_KEYS = {"rule_id", "name", "description", "codebook_id", "codebook_version", "source", "channel",
             "derived", "window_ms", "statistic", "min_samples", "bins"}
_UNHASHED = ("name", "description", "created_utc", "content_hash")


def _dir(root: str | Path) -> Path:
    return Path(root) / "scoring_rules"


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------

def rule_hash(rule: dict[str, Any]) -> str:
    """Everything that changes a prediction; not the name or the prose."""
    payload = {k: v for k, v in rule.items() if k not in _UNHASHED}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def validate_rule(rule: Any, codebook: dict[str, Any] | None) -> tuple[bool, list[str], list[str]]:
    """(ok, reasons, notes). A rule that cannot produce an answerable score is refused."""
    if not isinstance(rule, dict):
        return False, ["no rule"], []
    reasons: list[str] = []
    notes: list[str] = []
    extra = sorted(set(rule) - RULE_KEYS - {"created_utc", "content_hash"})
    if extra:
        reasons.append(f"unknown keys: {', '.join(extra)}")
    if not SAFE_ID.match(str(rule.get("rule_id", ""))):
        reasons.append("rule_id must be a slug")
    if not str(rule.get("name", "")).strip():
        reasons.append("no rule name")
    if codebook is None:
        reasons.append("the codebook version it names does not exist")
    src = rule.get("source")
    if not isinstance(src, str) or not src.strip() or src.strip() in ("*", "any"):
        # Two engines are two measurements; scoring "whichever answered" would
        # make the result a blend nobody chose.
        reasons.append("source must name exactly one engine source")
    ch, der = rule.get("channel"), rule.get("derived")
    if (ch is None) == (der is None):
        reasons.append("give exactly one of channel or derived")
    elif ch is not None and not (isinstance(ch, str) and ch.strip()):
        reasons.append("channel must be a channel name")
    elif der is not None and not (isinstance(der, dict) and der.get("kind") in DERIVED
                                  and isinstance(der.get("margin", 0.1), (int, float))
                                  and 0 <= der.get("margin", 0.1) <= 0.5):
        reasons.append(f"derived must be one of {', '.join(DERIVED)} with a margin from 0 to 0.5")
    w = rule.get("window_ms")
    if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, (int, float)) for x in w)
            and w[0] < w[1] and -5000 <= w[0] and w[1] <= 5000):
        reasons.append("window_ms must be [start, end] around the moment, within 5 seconds")
    if rule.get("statistic") not in STATISTICS:
        reasons.append(f"statistic must be one of {', '.join(STATISTICS)}")
    ms = rule.get("min_samples")
    if not (isinstance(ms, int) and not isinstance(ms, bool) and ms >= 1):
        reasons.append("min_samples must be a whole number of at least 1")
    bins = rule.get("bins")
    if not isinstance(bins, list) or len(bins) < 2:
        reasons.append("bins must map at least two value ranges to categories")
    else:
        cats = {str(c["id"]) for c in (codebook or {}).get("categories", [])}
        lows = [b.get("below") for b in bins if isinstance(b, dict)]
        if len(lows) != len(bins):
            reasons.append("each bin is {below, category}")
        else:
            if lows[-1] is not None:
                reasons.append("the last bin must be open-ended (below: null)")
            bounded = lows[:-1]
            if any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in bounded) or any(
                    bounded[i] >= bounded[i + 1] for i in range(len(bounded) - 1)):
                reasons.append("bin thresholds must be numbers in strictly increasing order")
            used = [b.get("category") for b in bins]
            unknown = sorted({str(u) for u in used} - cats) if codebook else []
            if unknown:
                reasons.append(f"categories not in that codebook version: {', '.join(unknown)}")
            unreachable = sorted(cats - {str(u) for u in used})
            if unreachable:
                # Allowed — a rule may never predict "closed eyes" — but said,
                # because agreement on that category is then zero by design.
                notes.append(f"this rule can never predict: {', '.join(unreachable)}")
    return not reasons, reasons, notes


def check_rule(root: str | Path, rule: Any) -> dict[str, Any]:
    cb = _codebook_for(root, rule)
    ok, reasons, notes = validate_rule(rule, cb)
    return {"valid": ok, "reasons": reasons, "notes": notes,
            "content_hash": rule_hash(rule) if isinstance(rule, dict) else None}


def _codebook_for(root, rule) -> dict[str, Any] | None:
    if not isinstance(rule, dict):
        return None
    try:
        return annotation_store.load_codebook(root, str(rule.get("codebook_id", "")),
                                              str(rule.get("codebook_version", "")) or None)
    except (FileNotFoundError, ValueError):
        return None


def save_rule(root: str | Path, rule: dict[str, Any]) -> dict[str, Any]:
    """Write a rule version. Existing versions are never overwritten."""
    cb = _codebook_for(root, rule)
    ok, reasons, notes = validate_rule(rule, cb)
    if not ok:
        raise ValueError("; ".join(reasons))
    content = rule_hash(rule)
    path = _dir(root) / f"{rule['rule_id']}.{content}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    record = {**{k: v for k, v in rule.items() if k not in ("created_utc", "content_hash")},
              "content_hash": content, "created_utc": datetime.now(timezone.utc).isoformat(),
              "notes": notes}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def load_rule(root: str | Path, rule_id: str, content_hash: str) -> dict[str, Any]:
    for v, what in ((rule_id, "rule_id"), (content_hash, "content_hash")):
        if not SAFE_ID.match(str(v)):
            raise ValueError(f"{what} must be a slug")
    path = _dir(root) / f"{rule_id}.{content_hash}.json"
    if not path.exists():
        raise FileNotFoundError(f"no scoring rule {rule_id}@{content_hash}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_rules(root: str | Path, codebook_id: str | None = None,
               codebook_version: str | None = None) -> list[dict[str, Any]]:
    d = _dir(root)
    out = []
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if codebook_id and r.get("codebook_id") != codebook_id:
            continue
        if codebook_version and r.get("codebook_version") != codebook_version:
            continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# reading the engine at each moment
# ---------------------------------------------------------------------------

class Refused(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


def recording_clock(out: str | Path, session_id: str) -> tuple[float, float]:
    """(offset_ms, rate) mapping recording time to the master clock, from the runs table."""
    runs = read_session(out, session_id, "runs").to_pylist()
    sols = {(round(r["clock_offset_ms"], 6), round(r["clock_rate"], 12)) for r in runs
            if r.get("status") == "ok" and r.get("clock_id") == "video_pts"
            and r.get("clock_offset_ms") is not None and r.get("clock_rate") is not None}
    if not sols:
        raise Refused("no_recording", "no engine ran on a recording of this session, so there is no "
                      "recording time for the codebook's moments to refer to")
    if len(sols) > 1:
        raise Refused("inconsistent_clock_solutions",
                      f"the engines disagree on how the recording maps to the master clock: {sorted(sols)}")
    return next(iter(sols))


def _samples(out, session_id, rule) -> tuple[np.ndarray, np.ndarray]:
    sig = read_session(out, session_id, "signals")
    mine = sig.filter(pc.equal(sig["source"], rule["source"]))
    if not mine.num_rows:
        raise Refused("no_signal", f"no rows from {rule['source']} in this session")
    if len(set(mine["params_hash"].to_pylist())) > 1:
        raise Refused("ambiguous_fit", f"{rule['source']} was run with different parameters in this "
                      "session; a rule cannot say which run it means")
    if rule.get("channel"):
        t = mine.filter(pc.equal(mine["channel"], rule["channel"]))
        ts = np.asarray(t["master_ts"].to_pylist(), dtype=float)
        vs = np.asarray(t["value"].to_pylist(), dtype=float)
    else:
        from gaze_stage import onscreen_mask
        xs = {r["master_ts"]: r["value"] for r in mine.filter(pc.equal(mine["channel"], "gaze.x"))
              .select(["master_ts", "value"]).to_pylist()}
        ys = {r["master_ts"]: r["value"] for r in mine.filter(pc.equal(mine["channel"], "gaze.y"))
              .select(["master_ts", "value"]).to_pylist()}
        common = sorted(k for k in set(xs) & set(ys) if k is not None)
        ts = np.asarray(common, dtype=float)
        pred = np.array([[xs[k], ys[k]] for k in common], dtype=float).reshape(-1, 2)
        vs = onscreen_mask(pred, margin=float(rule["derived"].get("margin", 0.1))).astype(float)
    ok = ~(np.isnan(ts) | np.isnan(vs))
    if not ok.any():
        raise Refused("no_signal", f"no aligned {rule.get('channel') or 'gaze'} rows from {rule['source']}")
    order = np.argsort(ts[ok])
    return ts[ok][order], vs[ok][order]


def categorise(value: float, bins: list[dict[str, Any]]) -> str:
    for b in bins:
        if b["below"] is None or value < b["below"]:
            return str(b["category"])
    return str(bins[-1]["category"])


def predict(out: str | Path, session_id: str, rule: dict[str, Any],
            items_ms: list[float]) -> dict[str, Any]:
    """One category per moment, or None where the engine had too few samples."""
    offset, rate = recording_clock(out, session_id)
    ts, vs = _samples(out, session_id, rule)
    stat = {"median": np.median, "mean": np.mean, "max": np.max}[rule["statistic"]]
    lo, hi = rule["window_ms"]
    preds, values = [], []
    for item in items_ms:
        m = item * rate + offset
        a, b = np.searchsorted(ts, m + lo, side="left"), np.searchsorted(ts, m + hi, side="right")
        if b - a < rule["min_samples"]:
            preds.append(None)
            values.append(None)
            continue
        v = float(stat(vs[a:b]))
        values.append(v)
        preds.append(categorise(v, rule["bins"]))
    return {"predictions": preds, "values": values, "clock": {"offset_ms": offset, "rate": rate}}


# ---------------------------------------------------------------------------
# the recording's zero
# ---------------------------------------------------------------------------

def container_start_s(path: str | Path) -> float | None:
    """The container's start time in seconds, from ffmpeg's own report."""
    import imageio_ffmpeg
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True)
    m = re.search(r"start:\s*(-?[0-9.]+)", r.stderr)
    return float(m.group(1)) if m else None


def pts_origin(video: str | Path, playback: str | Path, *, tolerance_s: float = 0.017) -> dict[str, Any]:
    """Do the raw recording and the copy the coding page plays both start at 0?

    Half a frame at 30 fps is the tolerance: a moment coded at t in the browser
    and read at t by the engines must be the same frame.
    """
    raw, play = container_start_s(video), container_start_s(playback)
    reasons = []
    for name, v in (("recording", raw), ("playback copy", play)):
        if v is None:
            reasons.append(f"the {name}'s start time could not be read")
        elif abs(v) > tolerance_s:
            reasons.append(f"the {name} starts at {v:.3f} s, not 0")
    return {"ok": not reasons, "recording_start_s": raw, "playback_start_s": play, "reasons": reasons}


# ---------------------------------------------------------------------------
# the engine arm
# ---------------------------------------------------------------------------

def engine_arm(out: str | Path, session_id: str, rule: dict[str, Any], matrix: dict[str, Any],
               *, use: str, origin: dict[str, Any] | None) -> dict[str, Any]:
    """Score one rule against the raters, on the moments the engine answered."""
    from evaluation import MIN_ITEMS, evaluate_against, reference_from

    base = {"rule_id": rule["rule_id"], "rule_version": rule["content_hash"], "source": rule["source"],
            "channel": rule.get("channel") or f"derived:{rule['derived']['kind']}"}
    if origin is None or not origin.get("ok"):
        return {**base, "refusal": {"reason": "pts_origin_unverified",
                                    "detail": "; ".join((origin or {}).get("reasons") or
                                                        ["the recording's start time could not be checked "
                                                         "(start the app with --media <dir>)"])}}
    if rule["codebook_id"] != matrix.get("codebook_id") or rule["codebook_version"] != matrix.get("codebook_content_hash"):
        return {**base, "refusal": {"reason": "wrong_codebook_version",
                                    "detail": "the rule was written for a different codebook version"}}
    items = [float(k) for k in matrix["items"]]
    try:
        p = predict(out, session_id, rule, items)
    except Refused as r:
        return {**base, "refusal": {"reason": r.reason, "detail": r.detail}}
    answered = [i for i, x in enumerate(p["predictions"]) if x is not None]
    coverage = len(answered) / len(items) if items else 0.0
    base.update({"n_items": len(items), "n_answered": len(answered), "coverage": coverage,
                 "clock": p["clock"]})
    if coverage < MIN_COVERAGE:
        return {**base, "refusal": {"reason": "low_coverage",
                                    "detail": f"the engine answered {len(answered)} of {len(items)} moments "
                                              f"({coverage:.0%}); scoring only those would drop the hard ones"}}
    if len(answered) < MIN_ITEMS:
        return {**base, "refusal": {"reason": "too_few_items",
                                    "detail": f"{len(answered)} answered moments; {MIN_ITEMS} are needed"}}
    raters = [[row[i] for i in answered] for row in matrix["labels"]]
    ref = reference_from(raters, use=use)
    if not ref:
        return {**base, "refusal": {"reason": ref.reason, "detail": ref.detail}}
    ev = evaluate_against([p["predictions"][i] for i in answered], ref)
    if not ev:
        return {**base, "refusal": {"reason": ev.reason, "detail": ev.detail}}
    return {**base, "evaluation": ev.as_dict(), "refusal": None}
