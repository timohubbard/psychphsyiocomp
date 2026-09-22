# Open behavioral research platform

A webcam-based human-behavior research platform built from open components —
screen-based eye tracking, facial expression analysis, voice analysis, and
respiration, from a consumer webcam and microphone. Browser-first remote data
collection, with a secondary in-lab mode for external sensor sync.

**Build target: academic / non-profit.** This is load-bearing, not a footnote —
it is what makes OpenFace 3.0, LibreFace and openSMILE usable at all. See
[Licensing](#licensing) below.

## Why this exists

`REPORT.md` is a cited research report covering this domain in depth. Its
central finding for the build: **iMotions is mostly an integrator, not an
inventor.** Only its gaze engine and respiration algorithm are in-house —
facial coding is licensed Affectiva AFFDEX, and voice is licensed audEERING
devAIce, which is itself built on openSMILE. Replacing the inference engines
with open or self-built equivalents is therefore tractable.

Read `REPORT.md` before changing anything in `engines/`. The accuracy budgets,
exclusion thresholds and failure modes it documents are encoded directly into
the engine contract, and several look like arbitrary constants if you haven't
seen the evidence behind them.

## Layout

```
REPORT.md                       the research report — read this first
research/                       10 verified research passes backing it
packages/engine-contract/       the contract every engine implements
  src/manifest.ts               TypeScript types (browser engines)
  python/engine_contract/       Python mirror (server engines)
  schema/canonical_tables.sql   signals / events / quality / runs
engines/                        one directory per engine
  face.mediapipe_blendshapes/   M0 reference engine — copy this one
tools/license-inventory/        "what would we rip out to go commercial?"
web/                            participant capture page (M0, in progress)
server/                         alignment service + Parquet writer (M0, in progress)
```

## Core design decisions

**Record-first, infer-later.** The browser captures and timestamps; it does not
own inference. Inference is a re-runnable, versioned, server-side job over
stored media. In-browser inference exists only for live participant feedback
(calibration, face-in-frame, lighting). Rationale: §2.2 found engine choice
swung valid-face-frame yield 43%→63% on *identical video*, so a pipeline that
cannot re-run permanently bakes in whichever engine was picked first.

**Engines are pure, versioned functions.** `(media, params) → signals + events
+ quality`. An engine knows nothing about the database, the study runner, or
clock alignment. Every output row carries `source = engine_id@version`, so two
engines on one modality coexist and a re-run is an *append*, never a migration.

**Engines emit native timestamps only.** A separate, non-pluggable alignment
service fills `master_ts`. §3.3: `AudioContext.currentTime` is a different
clock from `performance.now()`, and letting each engine solve that itself ships
the same bug once per engine.

**`probe()` before `run()`, and ineligibility is recorded.** Never a silent
skip. This is how the report's traps become machine-enforced rather than tribal
knowledge — rPPG refuses below a bitrate floor, voice-valence refuses when
noise suppression was applied, gaze refuses below 5 Hz effective sampling.

**Reliability is a schema field.** §2.2 measured AU12 at F1 .72–.83 and AU20 at
.13–.24. `reliability_tier` rides on every signal row so a rendering layer
structurally cannot present them as equals.

## Setup

```bash
npm install
py -m venv .venv                          # python3 -m venv .venv on macOS/Linux
node tools/py.mjs -m pip install -r requirements.txt
npm run models                            # fetch model bundles (not committed)
npm run check                             # licences + both test suites
```

## Commands

```bash
npm test                          # JS/browser tests
npm run test:py                   # Python/server tests
npm run test:all                  # both
npm run licenses                  # licence inventory
npm run licenses:commercial-gate  # exits 1 if a restricted engine is installed
npm run models                    # fetch model bundles
npm run check                     # licences + all tests
npm run py -- <args>              # run anything in the venv, cross-platform
```

## Licensing

Every engine declares its licence in `engine.manifest.json`. `npm run licenses`
walks them and prints which would need replacing to go commercial.

This build is academic/non-profit, so restricted engines are legitimately in
use. The inventory exists so that if the position ever changes, the answer is
one command away instead of an archaeology project. Verified during research:

| Engine | Status |
|---|---|
| OpenFace 3.0 | "ACADEMIC OR NON-PROFIT ORGANIZATION NONCOMMERCIAL RESEARCH USE ONLY" |
| openSMILE 3.0 | "not allowed to use the open-source version ... for any sort of commercial product" |
| LibreFace | USC research licence |
| audEERING SER model | CC-BY-NC-SA-4.0 |
| rPPG-Toolbox | Responsible AI License — use-based restrictions, not OSI |
| WebGazer.js | GPLv3, and unmaintained since Feb 2026 |
| Py-Feat | MIT — but ships a non-commercial InsightFace weight to exclude |
| MediaPipe, SpeechBrain, emotion2vec, L2CS-Net | permissive |

The licence tool fails safe: a manifest that omits `commercial_use` is bucketed
as *unverified*, never as permissive.

## Status

M0 (walking skeleton) complete. M1 (gaze) started.

- [x] Engine contract — TS + Python, canonical table schema
- [x] Licence inventory tool, with fail-safe bucketing
- [x] `face.mediapipe_blendshapes` — browser placement, 12 unit tests
- [x] `face.mediapipe_blendshapes` — server placement, 31 tests incl. end-to-end
- [x] Capture page + stimulus sequence (13-pt calibration, 5-pt validation, sync clappers)
- [x] Alignment service + Parquet writer
- [x] **M0 gate passing** — `npm run check`

Both placements share one `engine.manifest.json` and are pinned to the same
head-pose convention by tests on each side — a nod must read as pitch in both,
or the same video would yield different pose depending on where it was
processed.

**M0 success criterion — met.** `npm run verify:m0` runs a full session and
asserts it: one Parquet file, two `source` values for one channel in one
session, both on the master clock and therefore comparable.

```
face.mediapipe_blendshapes@0.1.0+browser-live    10 rows  10 aligned  ±0ms
face.mediapipe_blendshapes@0.1.0+server-batch    89 rows  89 aligned  ±33ms
```

The ±33ms on the server rows is the clapper anchor uncertainty — one frame at
30fps. That is an honest error bar, not a rounding artefact: §3.3 is explicit
that AV sync is a ceiling rather than a bug to fix.

### M1 — gaze

- [x] Virtual chinrest — screen geometry per participant (`web/src/chinrest.js`)
- [x] `sessions` canonical table — geometry queryable beside the signals
- [x] Capture page verified in a real browser (first time — see below)
- [x] **Real capture run** — full session on live hardware, through the pipeline
- [ ] Validation metrics (`percent_in_roi`, `average_offset`, `samples_per_sec`)
- [ ] MediaPipe eye normalisation + per-participant ridge baseline (the floor)
- [ ] Eval harness, including the human-annotation arm
- [ ] L2CS-Net fine-tune, ONNX export
- [ ] HMM fixation classifier (**not** I-VT/I-DT — §4.1)

**Why the chinrest came first.** `errorInDegrees` was written in M0 to return
`null` unless given a per-participant viewing distance, so until geometry
existed the platform could not express a spatial error in degrees at all —
which is the unit every gaze result is reported in. §5.1 measured viewing
distance across 1,153 online participants at mean 47.3cm, **SD 8.9cm**, range
17.4–68.3cm; a dva figure computed from a nominal distance is a pixel count
wearing a unit.

The error budget is **derived rather than asserted**. Propagating the published
blind-spot eccentricity SD (0.96° on a 13.5° constant) through the geometry
gives 7.4% relative uncertainty — ±3.5cm at the population mean distance, which
lands inside the independently-published 2.4–5.5cm MAE for the whole method. A
unit test pins that agreement, so if either constant is ever edited without the
other, the build fails rather than silently mis-scaling every reported degree.

Two things are kept deliberately separate and both are stored:

| Column | Means | Floor |
|---|---|---|
| `geometry_precision_mm` | how much this participant's own repetitions agreed | 0 |
| `geometry_error_mm` | what the estimate is actually worth | 55mm, always |

Five identical repetitions prove a careful participant. They prove nothing
about whether 13.5° was *their* blind-spot eccentricity, which is unmeasured
and is where the real error lives. Reporting precision as accuracy is how a
method with centimetre error starts quoting millimetre confidence.

A failed chinrest **refuses** — null geometry plus a recorded reason — and does
not stop the session. Everything except the dva conversion is unaffected, and
`geometry_refusal_reason` keeps "the participant tried and the method declined
to guess" distinguishable from "the task never ran". Those are different
exclusion decisions and only one is about the participant.

### M0 on real data

`npm run verify:m0` proves the machinery against a synthetic clip.
`server/process_bundle.py` runs a session a participant actually produced:

```bash
npm run py -- server/process_bundle.py tempdata --out out/
```

On the first real session — 7 minutes, 82MB, 44 events:

```
sources          face.mediapipe_blendshapes@0.1.0+browser-live
                 face.mediapipe_blendshapes@0.1.0+server-batch
signal rows      865,242
aligned rows     865,242 / 865,242
M0 criterion on REAL data: PASS
```

That took eight fixes to achieve, none of which the synthetic tests could have
surfaced. A synthetic clip has a sane frame count, a seek index, and a flash the
generator placed there. A browser's WebM has none of the three:

| What broke | Synthetic said | Real data said |
|---|---|---|
| `CAP_PROP_FPS` | 30 | **1000.0** (WebM stores a timebase there) |
| `CAP_PROP_FRAME_COUNT` | 90 | **INT64_MIN**, giving `duration_s = -9.2e18` |
| Seeking | works | **`set()` returns True, then reads fail** |
| Clapper flash | 100 → 240, one frame | **185 → 193.5**, seven frames |
| Frame pump rate | n/a | **2.35 frames processed per camera frame** |

The clapper one was the most consequential. The detector required a 15-luma
rise; the real flash was +8.5 — unmistakable to the eye, a clean plateau at
exactly the right instant — so alignment failed and every server-side row would
have carried a NULL `master_ts`. The system refused rather than guessing, which
is the designed behaviour and why the failure was visible at all. But the test
had encoded a flash no real room produces: a camera already exposed for a lit
room has almost no headroom left when the screen turns white.

The detector is now a matched filter over the known 200ms flash duration
against a rolling local baseline, requiring pulse shape and edge sharpness. Both
of those earn their place: auto-exposure settling produced a +4 luma bump over
13 frames that scored as high as the real flash, and only edge sharpness
separates them — a screen turning white puts ~82% of its rise into one frame
interval, and a ramp cannot.

Measured end to end: the camera sees the flash **~54ms** after the browser draws
it. That latency also truncated the closing clapper, which is why
`TIMINGS.clapperPostrollMs` now exists.

### A note on verification

The capture page was confirmed working in Chrome on 2026-09-22 — and that pass
found that **the page's JavaScript had never executed at all.** `tools/serve.mjs`
served `web/index.html` at `/`, so the document's base URL was `/` and its
relative `./src/main.js` resolved one directory too high and 404'd. The page
still rendered, because the HTML and inline CSS are self-contained; it was
simply inert.

It had passed every check we had. `curl` returned 200 on every module — but
`curl` was asked for the *correct* paths, while the page was requesting
different ones. A fetch you construct yourself cannot verify the fetches the
page constructs.

Driving the chinrest UI in the browser then found three more: inverted retry
messages, a card silently shrunk by its flex parent so the measured width was
not the rendered one, and a missing plausibility bound that accepted a 2.4cm
viewing distance because the five bad repetitions agreed with each other.
Consistency is not plausibility; they are now separate gates.

Every one of these lived in the layer between tested arithmetic and real
rendering. The arithmetic was right the whole time.

**Still unexercised: the camera path.** Nothing here has called `getUserMedia`.

## Running a session

```bash
npm run serve      # then open http://localhost:5173/
```

The page records locally and nothing uploads automatically; finishing offers a
bundle (`session.json`, `browser_chunks.json`, `capture.webm`) to hand to the
pipeline. Camera access needs a secure context, which localhost satisfies.

## Prerequisites

- Node ≥ 22
- Python ≥ 3.11 — verified on 3.14.7 with mediapipe 1.0.1, opencv 5.0.0,
  numpy 2.5.3, pyarrow 25.0.1

Model bundles are fetched rather than committed (`npm run models`): they are
large, versioned upstream, and their licence terms can differ from the
library's. `tools/fetch_models.py` records provenance for each.
