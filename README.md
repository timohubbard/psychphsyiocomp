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

**M0 (walking skeleton) complete. M1 (gaze) working end to end. All four
modalities run on real footage; facial has two AU engines. As of 2026-09-27
it can run a study end to end:**

- image and video stimuli, recruitment from a panel and between-subject
  conditions;
- upload, pseudonymisation, retention and withdrawal;
- cohort analysis, and an audited export.

What it still needs is a deployment, an ethics approval and people (see
*Picking this up*).

`npm run check` → licence inventory, 873 tests (244 JS + 629 Python), M0 gate
PASS. `npm run verify:gaze` → GAZE GATE PASS on the pilot, **FAIL on the second
session** (83% of fixations on target at 4.5°, need 90%; 3.2° to target vs
1.5°) — see "The second real session" below.

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
| Eval harness — kappa, human ceiling, refusals | done |
| Human-annotation UI for collecting the reference labels | done — playback verified in Chrome |
| L2CS-Net fine-tune | not started |
| M2 — `face.pyfeat_aus`, per-AU reliability tiers | done |
| M2 — inter-engine agreement + relative proportions | done |
| M2 — `face.opengraphau_aus`, the second AU engine | done |
| M2 — posed-expression task + per-engine scoring against it | done — first recording scored (`s_muirbs2a`) |
| M3 — `voice.opensmile_egemaps` (88 eGeMAPSv02 functionals) | done |
| M4 — `resp.motion_profiles`, waveform only | done |
| M4 — respiration validation study against an RIP belt | not started |
| Study definitions — protocol as data, content-hashed | done |
| `speech.faster_whisper` — transcripts, consent-gated | done — 13% word error on real read-aloud |
| Clock alignment from both clappers, placed by expected position | done |
| End-to-end capture smoke test (headless Chrome, fake camera) | done — `npm run smoke:capture -- --study m0` drives the chinrest too, and checks the page recovers the distance it was driven at |
| Retention sweep and withdrawal, with a deletion log processing honours | done — `npm run retention`, `npm run withdraw` |
| Ethics gate (`audience`), consent wording, DPIA template, `npm run ropa` | done — wording awaits sign-off |
| `features_in_browser` tier: video never leaves the device; gaze features in the browser | done — not yet run on a real face |
| Image and video stimuli (sha256-checked, paint-time onsets, AOIs drawn on the stimulus) | done — `studies/stimulus-example.json` |
| Prolific parameters → keyed pseudonyms; between-subject conditions; completion link | done — `studies/panel-example.json` |
| Remote upload: capture page → `serve.mjs --ingest` → `server/ingest.py` inbox | done — localhost only; see *Deploying* |
| Cohort: declared exclusions, attrition funnel, baseline-corrected epochs | done — `npm run cohort -- <study>` |
| Per-stimulus gaze/AOI/face results, degree-blurred heatmaps, audited export zip (CSV + BIDS-style) | done — `npm run export -- <study>` |
| Cohort page in the researcher app (funnel, epoch curves, heatmaps) | done — `/cohort.html`; `npm run verify:cohort-view` |
| Study builder: form, live validation + consent preview, stimulus upload, used studies fixed | done — `/builder.html`; `tools/verify_builder.mjs` |

### Picking this up

**Before anyone but the developer is recorded** — from
`research/pass5-legal-gaps.md`, whose opening synthesis gives the reasons:

- **The retention sweep runs on a schedule on this machine** (since
  2026-09-27). `npm run retention:schedule` registers a daily Windows task
  (03:00; it runs late if the machine was off) that deletes whatever has passed
  the period each participant was shown, and records each run in
  `out/retention_runs.jsonl`. The researcher app prints when the sweep last ran
  and warns if no run has been recorded in 48 hours. Wherever the data is
  deployed, schedule it there too. On Linux, a daily cron line running
  `node tools/py.mjs server/retention.py sweep --apply --record` does the same.
  `npm run withdraw -- <session, pseudonym or Prolific ID> --apply` removes one
  person's data. `npm run retention` on its own is a dry run.
- **Get a real study approved and filled in.** The route is UK/EU, decided
  2026-09-26, and the gate is built: a study runs on anyone but the developer
  only with `"audience": "participants"`. Validation then refuses it until it
  carries:
  - a REC reference;
  - a real contact;
  - the data controller;
  - the Art 6 lawful basis;
  - the Art 9 condition, when face, voice or respiration is recorded.

  The study builder (`npm run app` → *Study builder*) walks through every
  field and shows the consent text as participants will read it. The ethics
  approval itself needs a person.
- **Sign off the consent wording** — written overnight and live on the consent
  screen, quoted in full under *Awaiting sign-off* below. The DPIA template
  (`docs/dpia-template.md`) and `npm run ropa -- <study>` (the Art 30 record,
  generated from the study file) are ready for a deploying group to complete.
- **Deploy behind HTTPS** — see *Deploying for remote collection*. Nothing
  faces the internet yet.
- **First real sessions through the new paths (2026-09-27).** Both at
  30 fps, both passed the gaze gate:
  - `s_mujrz6x7` (stimulus-example): gaze 2.26° from the server's features.
  - `s_mujs3eue` (in-browser-example, no recording at all): gaze 4.44° from
    the browser's features.

  On the same session and the same targets, the browser's features gave
  **3.23° against the server's 2.26°**. So on this evidence the in-browser tier
  costs about 1° of gaze accuracy for never recording, from one session.

  Per-stimulus results, AOIs on the picture, heatmaps, cohort and export all
  ran on it without a refusal. On both mirror-image pictures, gaze stayed on
  the right half, whichever shape was there. That is how the participant
  looked, not estimator bias: horizontal validation error is −0.008 of the
  stage (every target within ±0.03). The only systematic error is +0.087
  vertically, on the channel already tiered low.

#### Deploying for remote collection (written, not yet run on a server)

**`deploy/README.md` is the full procedure.** One Linux host:

- Caddy, for HTTPS and headers;
- systemd units for the capture server, the ingest service, and a daily
  retention timer;
- the researcher app, reached over an SSH tunnel.

`npm run deploy:check -- https://<domain>` then checks the deployment from
outside. It was rehearsed against local servers, where it caught an ingest bug
(a rejected upload left an empty folder in the inbox), now fixed. The Caddy
config strips Prolific IDs and client addresses from its access logs: a default
log would have held every participant's raw panel ID. What remains is a host,
a domain and an approved study. To run it locally:

1. Start the ingest service: `INGEST_TOKEN=<secret ≥16 chars> npm run ingest`.
   It writes to `tempdata/inbox/<session_id>/`.
2. Start the capture server with the same token: `npm run serve -- --ingest`.
3. Both bind 127.0.0.1 on purpose. Put them behind HTTPS as
   `deploy/README.md` describes.

The participant then sees *Send to the study* beside *Download*. The ingest
service:

- requires `session.json` first;
- refuses a recording under `features_in_browser`, and any withdrawn or expired
  session (410);
- caps every file, and seals each upload once.

`npm run process -- tempdata/inbox/<id>` refuses an upload that was never
sealed. Retention and withdrawal already search the inbox. Not built: TLS, the
proxy, or any authentication of participants. Anyone who can load a public
study link can upload a bundle, and the caps and refusals bound what they can
do.

#### Awaiting sign-off: consent wording added 2026-09-26

Written to be conservative, shipped live, and listed here verbatim so each
sentence can be accepted, changed or struck. Source: `web/src/consent.js`
unless noted. Every one is also stored in the session's consent record.

1. **Automated-analysis notice** (`analysisNotice`, AI Act Art 50(3)),
   shown under the first paragraph. The list of measures is built from the
   study's modalities:
   > **Automated analysis.** Software analyses the recording automatically to
   > measure {where on the screen you look / how the muscles of your face move
   > / the sound of your voice (pitch, loudness and timing — not your words) /
   > the movement of your chest and shoulders as you breathe}. It does not
   > identify who you are, it does not label your emotions, and nothing is
   > decided about you from it. The researchers may use these measurements to
   > study reactions such as attention or emotion.
2. **Measurements only** tier, a third bullet:
   > These numbers are still personal data. Patterns in them could, in
   > principle, help identify you, so they are protected like the recording.
3. **Withdrawal and complaint** (`withdrawalText`), after "You can stop at any
   time…":
   > **Changing your mind:** If you change your mind later, contact us (above)
   > with the session code shown at the end, within the {N} days. We will
   > delete your recording and every measurement taken from it. The only thing
   > we cannot take back is a result already combined into a published summary
   > that does not identify anyone. You can also complain to a data protection
   > authority — in the UK, the Information Commissioner's Office (ico.org.uk).
4. **Session code** on the end screen (`web/src/main.js`):
   > Your session code is {s_…}. Keep it if you might want your data deleted
   > later — quote it to the contact on the consent screen.
5. **Self-test warning**, shown only for studies without
   `"audience": "participants"`:
   > **Developer self-test.** This study has no ethics approval recorded and is
   > not for participants. If someone has asked you to take part in research
   > through this page, stop here and contact them.
6. **UK GDPR Art 13 lines**, shown when the study states them:
   > **Responsible for your data:** {controller} ·
   > **Legal basis:** {lawful_basis}; {special_category_basis}
7. **The `features_in_browser` tier**, offered only by studies that list it:
   > **Measurements only, made on this device** — Your video never leaves this
   > computer. The measurements are made here, in your browser, and only the
   > numbers are saved.
   > · Numbers computed on your own device — where you looked, how your face
   > moved. · No video and no audio is ever saved or sent anywhere. · These
   > numbers are still personal data. Patterns in them could, in principle,
   > help identify you, so they are protected like any other personal data.
   > *Only the simpler measurements your browser can make are possible, and
   > they can never be re-checked against the recording.*

Then, most valuable first. The first four need a person or hardware; the rest
can be done at a keyboard.

1. **Human labels on the posed recording** (`s_muirbs2a`, in `tempdata/s_test/`)
   via the annotation page (`npm run app -- --media tempdata`), at least two
   raters — the reference standard `server/evaluation.py` scores engines
   against. The engine-vs-request scores are in "What the two engines say about
   each other"; AU20 is the unit only labels can settle. More posed sessions,
   from other faces, are what would turn n = 2 per AU into a figure.
2. To record another: `npm run serve` (fresh — an old server keeps its old
   routing), open `localhost:5173/?study=au-expressions`, check the blue
   *Protocol* line names it, record (~4.5 min), Download into its own
   `tempdata/<folder>/`, then `npm run process -- tempdata/<folder> --out out
   --aus` (~18 min, almost all Py-Feat).
3. **Why gaze failed its gate on the second session** (3.2° vs 1.5°). Needs
   more sessions with lighting, distance and frame rate varied one at a time.
   Frame rate first: the failing session and the one after it captured at
   ~20 fps against a 30 fps request. Every session at ~30 fps has passed: the
   pilot at 29.9, and both 2026-09-27 sessions at 29.9 and 30.0 (2.26° and
   4.44°). This is suggestive, not controlled — distance differed too (45.7 vs
   38.8 cm).
4. **Respiration validation** against an RIP belt, before any rate is emitted.
5. L2CS-Net fine-tune (not started; its gaze datasets carry research-only EULAs
   someone has to accept by hand).

Local state that is not in git: `out/` holds three real sessions
(`s_mucntzzh` — raw video lost, audio survives; `s_mud6trnr` — complete;
`s_muirbs2a` — posed expressions, raw bundle in `tempdata/s_test/`);
`tempdata/<session_id>/` holds raw bundles; `models/` holds the fetched
weights (`npm run models`).

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

### The one output that needs permission first

`speech.faster_whisper` produces a transcript, and it is the only thing here
that runs *only* when a participant said it could. `media_plus_transcript` is
the single permitting tier; the gate lives in `server/transcript_stage.py`,
not in the engine, because an engine is a pure function of media and cannot
see a session's consent.

The gate inverts this project's usual default. Everywhere else a missing
consent field means keep-and-flag, because deleting someone's recording on the
strength of an absent field is unrecoverable. Here the asymmetry runs the other
way: creating a transcript nobody agreed to is the unrecoverable act, and
declining to create one costs a re-run. So a missing tier refuses, an
unacknowledged disclosure refuses, and a tier the study never offered refuses
as incoherent.

**Whisper hallucinates, and that is handled as a first-class failure.** Given
silence or room tone it will emit a complete, fluent, plausible sentence. In a
research record this is worse than a wrong number: a wrong number is visibly a
measurement, while a fabricated sentence is indistinguishable from a quotation
attributed to a named participant. Two independent gates apply per segment and
both must hold — the model's own `no_speech_prob` and its mean token
log-probability — plus a cross-segment check for the decoder repeat loops that
neither per-segment gate can see. A rejected segment is recorded with its
timing and confidence but **without its text**, so the rejection is auditable
without the fabrication being kept.

Verified against both controls: synthesised speech transcribes exactly at
p=0.997 language confidence, and 30 seconds of digital silence produces a
`no_speech_prob = 0.93` hallucination ungated that the gates drop. No word
error rate is claimed — published Whisper WERs come from curated corpora, not
from a consumer microphone after the browser's DSP.

### Measured against people, not against 1.0

`agreement.py` compares two engines. `evaluation.py` compares an engine to
people, which is a different question with a different trap: an engine scored
against one person's labels is scored against that person, and calling the
result accuracy launders one opinion into ground truth. `reference_from`
therefore **refuses** a single rater rather than warning.

**The human ceiling travels with every score.** §2.1: coders reached 92% on
the same webcam video where WebGazer reached 70%. If two coders agree at 0.70,
an engine agreeing at 0.68 is at the bar — reporting it against an implied 1.0
calls that a failure. An engine *above* the ceiling is flagged too, and not as
a triumph: agreeing with a majority vote more than the people who cast it is a
property of majority voting.

**The kappa paradox is detected, not documented.** Two label sets with
identical 85% agreement score kappa 0.700 when the categories are balanced and
0.316 when one dominates — measured, in a test, on the textbook tables. Most
AUs are absent in most frames, so the skewed table is the normal case in
behavioural coding rather than an edge case. Every kappa ships with its
prevalence and bias indices, a confidence interval, and, when the paradox
fires, a note saying which number to read and which to explain. The flag
detects the phenomenon directly — high agreement under low kappa — because the
first version thresholded a proxy on prevalence and missed the textbook case at
0.75 while the thing it stood for was plainly present.

Refusals throughout, in the project's usual shape: too few items, a single
category both coders used for everything, ragged rater lists, an unknown
ceiling statistic. A `Refusal` is falsy, so a caller cannot use one as a score
by accident.

### Collecting the human labels

`web/researcher/annotate.html` is the coding arm. A coder picks a codebook, a
session and a rater ID, then answers one categorical question per moment. The
interaction is deliberately that small, because this is the reference standard
everything else is measured against and anything that biases a coder biases
every accuracy figure downstream.

Four things it will not do, each because doing it inflates the ceiling
silently rather than visibly:

- **Show another rater's labels.** Independence is what every agreement
  coefficient assumes. There is no API route that would return them, so this
  is enforced rather than observed.
- **Show the engine's prediction.** A coder who can see what the model said is
  scoring the model's confidence, and the resulting agreement is circular.
- **Preselect anything, or offer "unsure".** A default is the answer a tired
  coder gives, and one that matches the majority manufactures agreement.
- **Let a coder skip ahead to the easy items.** They can stop and resume; a
  ceiling measured on the easy half is not the ceiling.

Labels are filed per (codebook version, session, rater) — never merged at
write time, because merging destroys the disagreement the reference standard
exists to measure and it cannot be recovered afterwards. Codebooks are hashed
over their categories *and* their item list: the hash is the directory
annotations are filed under, so leaving items out meant two coders who coded
different moments would pool as though they had coded the same ones. A test
caught that.

An item any rater left blank is dropped from the matrix rather than imputed.
Filling it with the majority would manufacture agreement out of someone's
uncertainty.

The app serves recordings for this with `--media <dir>`, and refuses with a
**403 rather than a 404** when the consent tier did not retain the recording —
"the participant said no" and "the file is missing" are different facts and a
UI that showed one message for both would teach people to treat a refusal as a
glitch.

**Playback is remuxed before it is served.** A MediaRecorder WebM has no
duration in its header and no cue index, so Chrome sits at `readyState 0` with
nothing buffered rather than failing — it looks like a slow network. A
stream-copy remux fixes it in 0.2 s for a 119 MB capture and is cached beside
the source. This is the same fact that made `describe_video` measure FPS from
packet timestamps rather than trust `CAP_PROP_FRAME_COUNT`, which returned
INT64_MIN on that file.

**Verified in Chrome's real media stack, with a control.** `npm run
verify:playback -- <session_id>` plays a real session through the app's route
in headless Chrome: metadata with a finite duration, a decoded frame, a seek
to 120 s that lands exactly, playback advancing. `npm run
verify:playback:control` is the check on that check. Headless Chrome records a
fresh 12 s MediaRecorder WebM from a canvas, and the same remux produces the
playable copy. Both are probed from one throwaway origin, and the control holds
only if the raw file fails and the remux passes all four checks. It does. Measured
there, the raw file does NOT sit at readyState 0: served with byte ranges it
loads, decodes and even plays, but reports duration `NaN` and cannot seek. That
is the failure a coder would actually hit, since they could not jump to a
moment. (The readyState-0 stall above was the 119 MB capture served without
ranges.)

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

### The second real session, and what it broke

A participant was sent to `/?study=au-expressions` to record posed facial
movements, and recorded the whole M0 gaze pilot instead. That one session, plus
a fake-camera run of the page, surfaced seven defects — four of them places
where the page ignored the protocol it had been given.

**The URL never reached the page.** The dev server redirects `/` to
`/web/index.html` and dropped the query string doing it; `main.js` then fell
back to `m0` directly under a comment saying "There is no fallback", and nothing
on screen named the protocol. Now the redirect keeps the query, the protocol is
named under the title before the camera can be enabled, and a URL naming no
study gets a chooser (`studies/index.json`, kept equal to the folder by a test).
The URL given to the participant had never been loaded once — every unit test
passed straight over it. `npm run smoke:capture` now drives real headless Chrome
with a fake camera through the redirect, consent, every stage and Download, and
checks the files that come out.

**The chinrest ran for every study.** `chinrest` sat in the hashed task list and
nothing read it; `voice-only-example.json` claimed to skip it. **The consent
screen described M0 to everyone** — "video and audio ... while you look at some
dots and read a short passage aloud" — including a face-only study with no
microphone and no dots, and its tier text promised to keep audio that did not
exist. Both are now derived from the protocol, and the consent record stores
the wording actually shown. A study offering the transcript tier without a
microphone no longer validates.

**Clock alignment trusted the strongest flash.** It paired the single brightest
luminance pulse with the *first* clapper, always. On the fake-camera run — a
camera that cannot see the screen — it aligned to a pulse 92 s from any flash
the page drew, at ±47 ms. On the real session the two genuine flashes scored
4204 and 3995: a slightly brighter closing flash would have shifted every video
row by 204 s, reported as aligned. And the second clapper was never used, so the
drift fit two bookend clappers exist for never ran. Each drawn flash now has an
expected video position (`recording_start` is logged on the master clock and
PTS starts at 0 there; measured 29 ms off on the pilot), only a detection within
1.5 s of it is accepted, both become anchors, and their spacing must match. The
fit on the real session: rate 0.999886 — ~114 ppm of camera-clock drift.

**Transcripts were timed from segments that crossed silence.** With the VAD on,
the answer to the free-speech prompt was stamped 217.0 s; the prompt appeared at
236.6 s. Segment times now come from their first and last word (238.6 s).
**And the VAD clipped the first words**: "The old harbour" became "Starver" in
`base` and "Carver" in `small` — identical across models, which is what pointed
at the audio path. Word error on the known 92-word passage:

| | base | small |
|---|---|---|
| VAD at library default | 21.7% | 19.6% |
| VAD threshold 0.35 | 20.7% | **13.0%** |
| no VAD | 20.7% | 14.1% |

No configuration produced text outside the speaking windows, so the VAD stays on
(threshold 0.35) and the default checkpoint is now `small`. One participant and
92 words: a justified default, not a claimed accuracy.

Gaze on that session was 2.61° held-out against the pilot's 1.65°. Two-anchor
alignment did not change it (2.58° with one anchor), so it is not a timing
effect; the session was darker (median luma 91 vs 138), slower (19.8 fps) and
closer (38.8 cm vs 47.5 cm). Two sessions cannot separate those. It also
**fails the gaze gate**: 83% of fixations on target at 4.5° padding against
the 90% the gate requires, and 3.22° mean error to the target on screen. Re-run
with the old single-anchor alignment it scores 89% and 3.20° — the mean error
is unchanged and the percentage differs by about one fixation (89 vs 92
classified), so the failure belongs to the session, not to the new alignment.
The gate is doing its job: it is the first real session that did not meet it.

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

### Never single-engine on facial

§2.2 is the most consequential finding in the evidence base for this modality:
engine choice alone swung valid-frame yield 43%→63% and expression counts 3–4×
on **identical video**, with between-engine agreement at r = 0.37–0.75. That
spread is the *free uncertainty estimate* — the only empirical handle on how
much of a result is the face and how much is the detector.

So `--aus` runs two engines, and they are deliberately unalike:

| | `face.pyfeat_aus` | `face.opengraphau_aus` |
|---|---|---|
| face finder | RetinaFace | MediaPipe, warped onto a measured template |
| model | XGBoost over HOG features | ResNet-50 + AU-relation graph (ME-GraphAU, IJCAI 2022) |
| output | occurrence probability | occurrence score (cosine, thresholded at 0.5 upstream) |
| licence | MIT; AU weights unconfirmed | Apache-2.0 code, vendored; weights' datasets research-only |

The 18 AUs they share carry identical channel names, so `server/agreement.py`
pairs them with no mapping table. LibreFace (pins `mediapipe==0.10.5`) and
OpenFace 3.0 (not on PyPI under any attributable name) were the two options
tried first and remain blocked.

#### Five things the second engine surfaced

**Upstream loads its weights with `strict=False`, and its demo builds the wrong
architecture.** `demo.py --stage 2` constructs the stage-1 network whatever the
flag says. Measured: the stage-2 checkpoint loaded that way leaves **8 tensors at
random initialisation and discards 49**, and still runs and emits plausible
numbers. The engine vendors the model code (`graphau_model.py`, notice and
changes stated), loads strictly, and refuses a checkpoint whose SHA-256 is not
the one the manifest names — the weights come from a Google Drive link that can
be re-pointed.

**The shared AU normaliser was folding left into bilateral.** It kept only the
digits, so OpenGraphAU's `AUL12` became `AU12` and would have been written into
the real AU12 channel frame by frame. Laterality is now preserved (`AU12_L`), and
a lateralised unit is tiered `low` rather than inheriting AU12's `high` — no
per-side figure exists in the evidence base for any AU. The 14 lateral channels
are off by default.

**Crop geometry is measured, not chosen.** All six of upstream's demo images
place the eye midpoint at (0.50, 0.49) with inter-ocular distance 0.234 of the
width (range 0.219–0.244). The engine warps every frame onto that template.
Against upstream's own preprocessing on those images, scores correlate at r =
0.975–0.991 across AUs; shrinking with area averaging before the warp halved the
remaining per-AU error (mean 0.019–0.054 → 0.013–0.026), because a 4× bilinear
downscale aliases where upstream's PIL resize does not.

**Py-Feat forces the whole process onto one thread.** It sets
`OMP_NUM_THREADS=1` on import — a macOS workaround for torch and xgboost loading
different OpenMP runtimes — and that is process-wide. After Py-Feat had run,
OpenGraphAU took **908 ms/frame instead of 112**. The engine now sets torch's
thread count for its own forward passes and restores it after; outputs are
identical to 1e-7 either way, and xgboost is unaffected.

**Py-Feat's `unit` was wrong.** Its manifest said "intensity"; the XGBoost model
returns `predict_proba`, an occurrence probability. Corrected. Both engines now
declare what they emit, which is also why their values can be correlated at all
and why neither should be read absolutely.

#### What the two engines say about each other

On the pilot session, 18 shared AUs, 446 aligned frames each: **median r = 0.14,
range −0.57 to +0.54.** That is well below §2.2's 0.37–0.75, and it is *not* a
measurement of what §2.2 measured. The recording is the M0 gaze protocol; the
face is neutral throughout. MediaPipe's smile blendshapes never exceed 0.015 at
the 99th percentile and cheek-squint is exactly zero, so there was no AU12 or
AU06 to agree about. The 0.01 variance floor that catches this for blendshapes
does not catch it here, because AU classifiers are noisier than blendshapes on a
still face. An agreement figure is only as informative as the behaviour in the
recording — a neutral recording cannot estimate between-engine uncertainty.

One thing does show through. On that neutral face Py-Feat reached AU12 = 0.89
and AU06 = 0.86 — confident smiles that are not there — while OpenGraphAU peaked
at 0.30. That is §2.2's 3–4× over-calling, reproduced.

As a positive control, both engines were run on upstream's six demo images,
which carry real expressions. Pooled over 108 image×AU pairs, **r = 0.36** — the
bottom edge of §2.2's range. On the two broad smiles they agree at r = 0.70 and
0.58 and both call the smile configuration (AU 6, 7, 10, 12, 14, 25); on subtle
faces they diverge, with Py-Feat calling up to 10 AUs present where OpenGraphAU
calls 2. **This control favours OpenGraphAU**: those images are likely drawn from
its own training data. It shows the engine responds to expressions; it does not
show which engine is right.

The second session made the case from the other side. It contained speech, so
the mouth moved while the rest of the face stayed neutral — and the engines
agreed where there was movement and not where there was none: **AU25 (lips
part) r = 0.61, AU17 r = 0.59**, against AU12 r = −0.26 and a median of 0.23
over all 18. The agreement report now carries, for each engine and AU, the share
of frames that engine itself called present (score ≥ 0.5, both engines' own
decision boundary). On the pilot's neutral face **Py-Feat called AU06 present in
60% of frames and AU12 in 37%; OpenGraphAU in 0%.** The researcher app shows
those beside the r they qualify, and says when a protocol elicited no movement.

**Measuring it properly:** the `au-expressions` study (`/?study=au-expressions`,
~4.5 min, face only) asks for ten movements twice each in shuffled order, each
as ready (neutral) → timed 4 s hold → relax, and stamps the requested AUs into
every hold event. `server/expression_scoring.py` then scores each engine per AU
— **sensitivity** (target holds vs the same trials' neutral phase, as an AUC),
**specificity** (vs holds of other movements; legitimately lower where anatomy
couples units), and **agreement on held movements only** — in the pipeline's
output and as a "Posed movements" panel in the app. It scores against what was
*asked for*, not what the face did; human labels via the annotation page remain
the reference standard.

**The first posed recording** (`s_muirbs2a`, 2026-09-26, one participant, all
20 trials, 19.7 fps) puts the §2.2 comparison on behaviour that happened. Over
all frames, median r across the 18 shared AUs rose from 0.14 (pilot) and 0.23
(speech) to **0.37**; on the 20 held movements it is **0.60** (range −0.56 to
0.88 over 14 AUs) — inside §2.2's 0.37–0.75 for the first time, because there
was finally something to agree about.

| | median sensitivity | median specificity | AUs below 0.7 sensitivity |
|---|---|---|---|
| OpenGraphAU | 1.00 | 0.99 | AU17 (0.68) |
| Py-Feat | 0.99 | 0.89 | AU23 (0.07), AU20 (0.50), AU15 (0.55), AU17 (0.57) |

The expected result was "Py-Feat sensitive but unspecific". That is half
right. Its specificity is lower (0.89 vs 0.99; AU12 0.73, the smile over-call
again), but its larger failure is **missing lower-face movements**. For AU23 its
score was *lower* during the requested lip press than at rest, while it scored
the same press as AU24 (0.97): it saw the movement and named it differently.

MediaPipe blendshapes are the third signal that separates "the engine missed
it" from "the face did not do it": `mouthFrown` for AU15 and `mouthShrugLower`
for AU17 both score sensitivity 1.00, so those movements happened and the
engines that missed them missed them. That covers Py-Feat on AU15/AU17 and
OpenGraphAU on AU17 (where its values barely move: sd 0.047). AU20 stays
unresolved. OpenGraphAU finds it (1.00) while Py-Feat (0.50) and
`mouthStretch` (0.10) do not, and the two engines anti-correlate on its holds
(r = −0.56). Either the lip stretch was faint or only one signal can see it;
human labels decide. The blendshapes cannot referee AU06, AU09 or AU10, because
`cheekSquint`, `noseSneer` and `mouthUpperUp` stayed at zero even during the
requested movements.

Every figure is **n = 2 target holds per AU** (4 for AU12 and AU25) against 20
neutral windows, one participant, and scored against what was requested. It
favours OpenGraphAU on this face; it is not an accuracy claim for either engine.

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
  face.opengraphau_aus/         the second AU engine, for §2.2's cross-check
  voice.opensmile_egemaps/      88 eGeMAPSv02 functionals, server-batch
  resp.motion_profiles/         chest/shoulder motion — waveform, no rate
  speech.faster_whisper/        transcripts; only runs with the transcript tier
server/
  alignment.py                  the one place clocks are reconciled
  tables.py / store.py          canonical tables: write side / read side
  pipeline.py                   media in, canonical tables out
  gaze_ridge.py / gaze_stage.py the estimator, and its join to stimulus events
  fixations.py                  two-state HMM, not I-VT
  aoi.py                        areas of interest, Holmqvist metrics
  agreement.py                  cross-engine agreement, relative proportions
  evaluation.py                 engine vs humans, and the ceiling humans set
  annotation_store.py           codebooks and labels; raters kept apart
  respiration.py                band-pass, multi-profile fusion, rate refusal
  consent.py                    tiered consent; pipeline.py enforces retention
  study.py                      protocol validation + hash (mirrors study.js)
  transcript_stage.py           the consent gate on transcription
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
#   open localhost:5173/?study=<id>  — no ?study= shows a chooser, never a default
npm run smoke:capture             # the whole page, headless, fake camera (needs serve)
#   --study <id>   default au-expressions
npm run process -- <dir> --out o/ # bundle -> canonical tables + gaze
#   --aus    also run Action Units — BOTH engines, so §2.2's spread exists
#   --au-engines pyfeat|opengraphau   one only (the app will say what is lost)
#   --resp   also run respiration (waveform only, never a rate)
#   --no-gaze / --no-voice   skip those stages
npm run app                       # researcher app
#   --media <dir>   serve session recordings to the annotation page
npm run verify:playback -- <id>   # does that recording play in real Chrome? (needs app --media)
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
| OpenGraphAU | Apache-2.0 code (vendored); weights trained on research-only datasets, EULAs unverified |
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
