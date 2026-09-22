# Open behavioral research platform

A webcam-based human-behavior research platform built from open components —
screen-based eye tracking, facial expression analysis, voice analysis, and
respiration, from a consumer webcam and microphone. Browser-first remote data
collection, with a secondary in-lab mode for external sensor sync.

**Build target: academic / non-profit.** This is load-bearing, not a footnote —
it is what makes OpenFace 3.0, LibreFace and openSMILE usable at all. See
[Licensing](#licensing).

## Quick start

```bash
npm install
py -m venv .venv                          # python3 -m venv .venv on macOS/Linux
node tools/py.mjs -m pip install -r requirements.txt
npm run models                            # fetch model bundles (not committed)
npm run check                             # licences + all tests + the M0 gate
```

Then the three commands that are the product:

```bash
npm run serve                             # capture page, for the participant
npm run process -- tempdata --out out/    # bundle -> Parquet, gaze fit, fixations
npm run app                               # researcher app at localhost:5174
```

The capture page records locally; nothing uploads automatically. Finishing
offers a bundle (`session.json`, `browser_chunks.json`, `capture.webm`) to hand
to the pipeline. Camera access needs a secure context, which localhost
satisfies. One session produces four `source` values over ~796,000 rows, every
one carrying a master timestamp.

## Why this exists

`REPORT.md` is a cited research report covering this domain in depth. Its
central finding for the build: **iMotions is mostly an integrator, not an
inventor.** Only its gaze engine and respiration algorithm are in-house —
facial coding is licensed Affectiva AFFDEX, and voice is licensed audEERING
devAIce, itself built on openSMILE. Replacing the inference engines with open
or self-built equivalents is therefore tractable.

Read `REPORT.md` before changing anything in `engines/`. The accuracy budgets,
exclusion thresholds and failure modes it documents are encoded directly into
the engine contract, and several look like arbitrary constants if you have not
seen the evidence behind them.

## Status

**M0 (walking skeleton) complete. M1 (gaze) working end to end.**

`npm run check` → licence gate green, 342 tests (80 JS + 262 Python), M0 gate
PASS. `npm run verify:gaze` → GAZE GATE PASS.

| | |
|---|---|
| Engine contract, canonical tables, licence inventory | done |
| `face.mediapipe_blendshapes` — both placements | done |
| Alignment service, clapper detection | done |
| Capture page — chinrest, calibration, validation, instructions | done |
| `gaze.mediapipe_features` + per-participant ridge estimator | done |
| HMM fixation classification | done |
| AOIs, Holmqvist metrics, and an in-app editor | done |
| Researcher app — scanpath, AOI editor | done |
| Eval harness incl. the human-annotation arm | not started |
| L2CS-Net fine-tune | not started |
| M2 — `face.pyfeat_aus`, per-AU reliability tiers | done |
| M2 — inter-engine agreement + relative proportions | done |
| M2 — a second AU engine for cross-check | **blocked, see below** |
| M3 — `voice.opensmile_egemaps` (88 eGeMAPSv02 functionals) | done |
| M4 — `resp.motion_profiles`, waveform only | done |
| M4 — respiration validation study against an RIP belt | not started |
| Study definitions — protocol as data, content-hashed | done |

### What the numbers are

On one real session, one participant:

- **Gaze error 1.65°** on five held-out validation targets
- **1.50°** mean error to the target actually on screen, over 18 targets —
  measured independently of the above, and they agree
- 80 fixations, 69% of predicted gaze on-screen, 29.94 Hz capture

Both figures rest on **one participant and 18 targets**. That they agree is
meaningful; they are not a validated accuracy claim, and nothing here presents
them as one.

### The number respiration does not report

`resp.motion_profiles` emits a breathing *waveform* and three confidence
channels. It does **not** emit breaths per minute, and the flag that would
enable it defaults to off.

§2.4: across two dedicated research passes, no breaths-per-minute accuracy
figure for this class of method — webcam chest/shoulder motion against a chest
belt, RIP or spirometry — survived adversarial checking, and one specific
figure was explicitly refuted. A breathing rate is a number a clinician
recognises on sight, so shipping one this project cannot defend would be the
most damaging thing it could do.

The waveform is the more useful output anyway: inhale onsets, breath-holds and
sighs are all events on a waveform and none of them need a calibrated rate.
Unblocking the rate takes a validation study — simultaneous webcam and RIP
belt, Bland-Altman on 60s windows plus waveform cross-correlation, N≈30–40
stratified on skin tone, clothing, distance and framing.

Two related decisions this engine encodes:

- Respiration is **not rPPG**. §2.4 corrects a common premise: iMotions'
  respiration is chest/shoulder-motion ROI tracking band-passed to ~7.5–30
  cycles/min, architecturally distinct from facial rPPG for heart rate and far
  more compression-robust. They are two separate engineering problems.
- The grid of motion profiles is **fused late, never averaged up front**.
  §2.4's one surviving algorithmic finding is that multiple motion profiles
  beat a single combined 1D profile, and `test_multiple_profiles_beat_a_single_combined_profile`
  measures it rather than asserting it. The reason is phase: chest rise and
  shoulder rotation are not in phase, so naive averaging cancels the signal.

## The protocol is data

A study lives in `studies/<id>.json`, not in the code. What a participant was
told, which consent tiers they could choose from, which modalities ran, how
many calibration targets there were — none of those are properties of this
software, and until study definitions existed two of them were hard-coded in
it: a single `STUDY_DISCLOSURE` constant stated a retention period on every
study's behalf.

Three rules, each one this project has already paid for elsewhere:

**Content-hashed, and immutable once used.** The hash goes into every session
manifest and into the `sessions` table. Editing a study in place is not
prevented, but it is *visible*: a session processed afterwards reports
`study_edited_since_session`, and the researcher app says which sessions are no
longer comparable. This is §4.2's finding applied to protocols — identical
fixations yielded 77%, 88% and 93% dwell depending on AOI boundaries, and a
calibration grid or a retention promise has the same power. A version string
does not catch it, because nobody bumps a version while fixing a typo in a
disclosure.

**Validated, never defaulted.** A study missing a retention period is not a
study with a sensible default retention period. 45 CFR 46.116 requires the
element to be stated, and a default here would be this software putting an
unreviewed promise in front of a participant. A definition that does not
validate does not run, and the capture page shows a full-stop error naming the
file and the reason rather than a generic failure.

**Modalities are opt-in and enumerated.** The microphone is requested only when
a modality needs it. Respiration in particular runs because a study said so,
never because the engine was installed — §6.3 puts it at higher legal risk than
the other three.

The browser validates before consent is taken and the server validates before a
session enters the canonical tables, so `web/src/study.js` and `server/study.py`
are deliberate mirrors. The hash of the shipped `studies/m0.json` is pinned as a
literal in *both* test suites: if the two implementations ever canonicalise
differently, every session starts reporting "study edited since session", a
false alarm indistinguishable from a real one.

## Core design decisions

**Record-first, infer-later.** The browser captures and timestamps; it does not
own inference. Inference is a re-runnable, versioned, server-side job over
stored media. In-browser inference exists only for live participant feedback.
Rationale: §2.2 found engine choice swung valid-face-frame yield 43%→63% on
*identical video*, so a pipeline that cannot re-run permanently bakes in
whichever engine was picked first.

**Engines are pure, versioned functions.** `(media, params) → signals + events
+ quality`. An engine knows nothing about the database, the study runner, or
clock alignment. Every output row carries `source = engine_id@version`, so two
engines on one modality coexist and a re-run is an *append*, never a migration.

**Engines emit native timestamps only.** A separate, non-pluggable alignment
service fills `master_ts`. §3.3: `AudioContext.currentTime` is a different
clock from `performance.now()`, and letting each engine solve that itself ships
the same bug once per engine.

**Some things cannot be engines.** A calibrated gaze estimator needs to know
which target was on screen when, and stimulus events live on the master clock.
So `gaze.mediapipe_features` is an engine that emits features and knows nothing,
while `server/gaze_stage.py` is a pipeline stage that joins them to events after
alignment. Features are stored, so a better estimator re-fits without decoding
video again — which will happen, because §2.1 found humans reached 92% on the
same webcam video where WebGazer reached 70%.

**`probe()` before `run()`, and ineligibility is recorded.** Never a silent
skip. This is how the report's traps become machine-enforced rather than tribal
knowledge — rPPG refuses below a bitrate floor, voice-valence refuses when
noise suppression was applied, gaze refuses below 5 Hz effective sampling.

**Refuse rather than guess.** No anchor → `master_ts` NULL plus a recorded
reason. A failed chinrest → null geometry plus a reason, and `errorInDegrees`
then returns null rather than computing degrees from an assumed distance. A
zero-offset fallback looks aligned and is wrong by an unknown amount.

**Reliability is a schema field.** §2.2 measured AU12 at F1 .72–.83 and AU20 at
.13–.24. `reliability_tier` rides on every signal row so a rendering layer
structurally cannot present them as equals.

## Screen geometry, and why it came first

`errorInDegrees` was written to return `null` unless given a per-participant
viewing distance, so until the virtual chinrest existed the platform could not
express a spatial error in degrees at all — which is the unit every gaze result
is reported in. §5.1 measured viewing distance across 1,153 online participants
at mean 47.3cm, **SD 8.9cm**, range 17.4–68.3cm. A dva figure computed from a
nominal distance is a pixel count wearing a unit.

The error budget is **derived rather than asserted**. Propagating the published
blind-spot eccentricity SD (0.96° on a 13.5° constant) through the geometry
gives 7.4% relative uncertainty — ±3.5cm at the population mean distance, which
lands inside the independently-published 2.4–5.5cm MAE for the whole method. A
test pins that agreement, so editing one constant without the other fails the
build rather than silently mis-scaling every reported degree.

Two things are kept separate and both are stored:

| Column | Means | Floor |
|---|---|---|
| `geometry_precision_mm` | how much this participant's repetitions agreed | 0 |
| `geometry_error_mm` | what the estimate is actually worth | 55mm, always |

Five identical repetitions prove a careful participant. They prove nothing about
whether 13.5° was *their* eccentricity, which is unmeasured and is where the
real error lives.

## What the real runs found

Every bug below survived a green test suite and was found by running the thing
on real hardware. They share one cause: **synthetic fixtures are shaped like the
code's assumptions.** A generated clip has a sane frame count, a seek index, and
a flash the generator placed there. A browser's WebM has none of the three.

| | Synthetic said | Real data said |
|---|---|---|
| `CAP_PROP_FPS` | 30 | **1000.0** (WebM stores a timebase there) |
| `CAP_PROP_FRAME_COUNT` | 90 | **INT64_MIN** → `duration_s = −9.2e18` |
| Seeking | works | **`set()` returns True, then reads fail** |
| Clapper flash | 100 → 240, one frame | **185 → 193.5**, seven frames |
| Frame pump rate | n/a | **2.35 frames processed per camera frame** |

**The capture page's JavaScript had never executed.** The dev server served
`index.html` at `/`, so its relative `./src/main.js` resolved one directory too
high and 404'd. The page rendered — HTML and inline CSS are self-contained — and
was completely inert. It had passed every check, because `curl` was asked for
the *correct* paths while the page requested different ones. A fetch you
construct yourself cannot verify the fetches the page constructs.

**The clapper detector rejected the real flash.** It required a 15-luma rise;
the real flash was +8.5, a clean seven-frame plateau at the right instant. So
alignment failed and every server-side row would have carried a NULL
`master_ts`. The system refused rather than guessing, which is why the failure
was visible at all — but the test had encoded a flash no real room produces. A
camera already exposed for a lit room has almost no headroom when the screen
turns white. The detector is now a matched filter over the known flash duration
against a rolling local baseline, requiring pulse shape and edge sharpness; both
earn their place, because auto-exposure settling produced a +4 luma bump that
scored as high as the real flash and only edge sharpness separates them.

**Consistency is not validity — three times.** Five agreeing blind-spot marks
gave an impossible 2.4cm viewing distance. Four agreeing marks gave 96.6cm,
which was the *screen's measurement ceiling* — they agreed because they were all
pressed against the same wall. And the saturated run reported ±4mm precision
while being wrong by 2×, where a valid run reports ±28mm and is right. Tight
agreement was the symptom. **Any bounded measurement must report its bound
alongside its value, or saturation is indistinguishable from success.**

Measured end to end: the camera sees the clapper flash 27–54ms after the browser
draws it, consistently within a session. That latency also truncated the closing
clapper, which is why `TIMINGS.clapperPostrollMs` exists.

### The trap that cost 3.4 degrees

The first honest gaze number was 5.04°. Feature sets, scored on held-out
targets:

| feature set | held-out error |
|---|---|
| iris, linear | 2.17° |
| iris, quadratic | **1.30°** |
| iris quadratic + head pose | 1.65° *(shipped)* |
| every channel, linear | 5.04° ← *chosen by leave-one-out CV* |

**Leave-one-out cross-validation picked the worst model, confidently.**

Calibration points were presented in fixed spatial order, so target y correlated
with presentation index at r = +0.56. Head pitch drifted at r = +0.86 with order
while carrying almost no genuine vertical-gaze signal (r = +0.19 with target y)
— so the model predicted *y from elapsed time*. LOOCV structurally cannot detect
this: the held-out point's temporal neighbours stay in the training set.

Fixed at source — stimulus order is randomised with a recorded seed, which is
what §5.1 means when it notes jsPsych presents its grid in fixed order "unless
randomized" — and in the design matrix, which carries only iris terms plus head
pose. Eyelid aperture and inter-ocular distance are quality gates, not gaze
signals, and handing a drifting quantity to a regression is an invitation.

### Never single-engine on facial — and we currently are

§2.2 is the most consequential finding in the evidence base for this modality:
engine choice alone swung valid-frame yield 43%→63% and expression counts 3–4×
on **identical video**, with between-engine agreement at r = 0.37–0.75. That
spread is the *free uncertainty estimate* — the only empirical handle on how
much of a result is the face and how much is the detector.

There is currently one AU engine, so that figure is unavailable, and the app
says so explicitly rather than leaving a blank panel. A second engine is
blocked, not skipped:

- **LibreFace** pins `mediapipe==0.10.5`, which would downgrade the two working
  engines, and has no cp314 wheel.
- **OpenFace 3.0** is not on PyPI under any attributable name. The `openface`
  package there is a 0.0.0 placeholder; `openface-test` has no author, licence,
  homepage or summary, so it was not installed.

Getting a second AU source likely means building OpenFace 3.0 from the CMU
source repository.

#### Barely moved is not disagreed

Agreement machinery exists and runs, and building it surfaced a trap worth
recording. The first run reported min r = 0.065 for `blendshape.jawRight`
between two *placements of the same engine on the same pixels* — alarming, until
its mean turned out to be 0.0003 with sd 0.010. The participant never moved
their jaw sideways. Both engines correctly reported nothing, and correlating two
near-zero noise series gives approximately zero.

|  | before | after |
|---|---|---|
| channels measured | 51 | 24 |
| median r | 0.884 | 0.915 |
| **min r** | **0.065** | **0.813** |

27 channels are now excluded as barely-moved rather than counted as
disagreement. Placement comparisons are also labelled separately from engine
comparisons, because one model over the same pixels should agree closely — a low
value there is a bug, not the uncertainty §2.2 describes.

### Where the model is guessing

34% of predicted gaze landed off-screen, 11% beyond twice the screen
dimensions. The validation score cannot see this: it measures interpolation
*between* calibration points, while those samples' features left the calibrated
range — and the quadratic terms that buy accuracy inside it diverge outside. The
model looks most confident exactly where it is least supported.

So every prediction carries a `gaze.extrapolation` distance, the session carries
`gaze_onscreen_rate`, fixations are classified on on-screen samples only, and
the app shows coverage beside accuracy.

## Verification

Three gates, each answering a different question.

**`npm run check`** — licences, both test suites, and the M0 gate: one Parquet
file containing two `source` values for one channel in one session, both on the
master clock and therefore comparable, with the clapper uncertainty carried as
an explicit error bar rather than rounded away.

**`npm run process`** — the same criterion on real captured data, which is a
different claim and took eight fixes to reach. It passes: four sources,
~796,000 rows, all aligned.

**`npm run verify:gaze`** — the strongest check available, because the answer is
known in advance. During each calibration dwell exactly one dot was on screen
and the participant was told to look at it, so a working pipeline must put the
fixation there.

```
  pad (deg)   hit rate    mean error
        0.0         0%      1.50 deg
        1.0        39%      1.50 deg
        2.0        78%      1.50 deg
        3.0        94%      1.50 deg
        4.5       100%      1.50 deg   <- GAZE GATE: PASS
```

Note the ladder. Identical gaze and identical fixations give wildly different
hit rates purely from the boundary choice — §4.2 measured 77/88/93 from the same
effect on the same data. **A hit rate quoted without its padding is not a
measurement**, which is why AOI sets carry a content hash derived from their
geometry and every result reports the padding that produced it.

**Still unexercised:** nothing has been tested with more than one participant,
and the camera path has run on exactly one machine.

## The researcher app

Read-only and stdlib-only, both deliberately. Read-only because the canonical
tables are append-only and the thing that appends is the pipeline; a UI that
could edit a measurement could quietly un-record a refusal. Stdlib-only because
a research instrument's dependency list is part of its reproducibility story,
and a session browser does not justify adding to it.

Per session it shows alignment fraction, recovered geometry with its error bar,
capture rate against §5.3's 5 Hz exclusion threshold, luminance against §2.5's
fairness floor, per-engine licence, windowed quality traces, every channel with
its reliability tier, CSV export, and a scanpath filterable by analysis phase.

**AOIs are drawn on the scanpath**, with the *padded* outline shown alongside
the drawn one — at 4.5° on a 42 px/deg display the padded region is dramatically
larger, and someone drawing a tight box around a button is otherwise unaware
that a fixation two centimetres away will count. AOI definitions are the one
thing this app may write, and they are not measurements: a measurement is
something a participant produced and the pipeline recorded, an AOI is a question
someone decided to ask of it afterwards. Saving a changed set writes a new
immutable version, because §4.2's 77→88→93 finding means a result computed under
old boundaries must stay attributable to them.

**Gaze accuracy is deliberately not colour-coded.** §5.3 records that no
pass/fail cutoff is published for it, so the figure is shown beside §4.2's AOI
budget as context rather than graded. A green badge here would silently become
the project's inclusion criterion without anyone preregistering it.

## Layout

```
REPORT.md                       the research report — read this first
research/                       10 verified research passes backing it
packages/engine-contract/       the contract every engine implements
  src/manifest.ts               TypeScript types (browser engines)
  python/engine_contract/       Python mirror, media probing, engine loader
  schema/canonical_tables.sql   sessions / signals / events / quality / runs
engines/                        one directory per engine
  face.mediapipe_blendshapes/   reference engine, both placements
  gaze.mediapipe_features/      eye/iris features, server-batch
  face.pyfeat_aus/              Action Units, per-AU reliability tiers
  voice.opensmile_egemaps/      88 eGeMAPSv02 functionals, server-batch
  resp.motion_profiles/         chest/shoulder motion — waveform, no rate
server/
  alignment.py                  the one place clocks are reconciled
  tables.py / store.py          canonical tables: write side / read side
  pipeline.py                   media in, canonical tables out
  gaze_ridge.py / gaze_stage.py the estimator, and its join to stimulus events
  fixations.py                  two-state HMM, not I-VT
  aoi.py                        areas of interest, Holmqvist metrics
  agreement.py                  cross-engine agreement, relative proportions
  respiration.py                band-pass, multi-profile fusion, rate refusal
  consent.py                    tiered consent; pipeline.py enforces retention
  study.py                      protocol validation + hash (mirrors study.js)
  app.py                        researcher app
web/
  index.html, src/              participant capture page
  researcher/                   researcher UI
studies/                        one JSON file per protocol, immutable once used
tools/license-inventory/        "what would we rip out to go commercial?"
```

Engines are loaded by `engine_contract.loader.load_engine_module(engine_id)`,
never by `sys.path` order. With more than one engine installed, `import engine`
is ambiguous and resolves to whichever directory was inserted last — which
silently imported the facial engine into the gaze engine's tests.

## Commands

```bash
npm run serve                     # participant capture page
npm run process -- <dir> --out o/ # bundle -> canonical tables + gaze
#   --aus    also run Action Units (slow: ~0.25s/analysed frame)
#   --resp   also run respiration (waveform only, never a rate)
#   --no-gaze / --no-voice   skip those stages
npm run app                       # researcher app
npm run check                     # licences + all tests + M0 gate
npm run verify:gaze               # do fixations land on the right target?
npm run verify:m0                 # M0 gate on a synthetic clip
npm test / test:py / test:all     # JS / Python / both
npm run licenses                  # licence inventory
npm run licenses:commercial-gate  # exits 1 if a restricted engine is installed
npm run models                    # fetch model bundles
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
as *unverified*, never as permissive. `LICENSE` covers this repository's own
code only — MIT there does not mean the assembled system is free of commercial
restrictions, and the file says so.

## Participant data

`.gitignore` excludes captured media **and derived data**. That distinction is
deliberate: an extension-based rule caught `capture.webm` but not the
`browser_chunks.json` beside it, which holds several hundred thousand rows of
facial measurements. That is behavioural biometric data whether or not a face is
visible in it.

## Prerequisites

- Node ≥ 22 (verified on 24)
- Python ≥ 3.11 — verified on 3.14.7 with mediapipe 1.0.1, opencv 5.0.0,
  numpy 2.5.3, pyarrow 25.0.1

Model bundles are fetched rather than committed (`npm run models`): they are
large, versioned upstream, and their licence terms can differ from the
library's. `tools/fetch_models.py` records provenance for each.

On Windows, `tools/py.mjs` exists because npm scripts run via cmd.exe and cannot
take a forward-slash venv path; use `npm run py -- <args>` for anything in the
venv. Windows Python also needs `tzdata` (in `requirements.txt`) — it lacks the
IANA database, and pyarrow needs it to read tz-aware timestamps.

**Smart App Control blocks freshly-published Python wheels** on the machine this
was built on, at import rather than install. `pandas<3` and `scikit-learn<1.8`
are pinned for that reason and are policy bounds, not correctness ones. See
[`docs/windows-app-control.md`](docs/windows-app-control.md) — the recommended
fix is to run the Python half in WSL2, which the architecture already points at:
the browser does the capture, and the Python side is pure batch processing that
a real deployment would run on Linux anyway.
