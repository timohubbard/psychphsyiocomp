# Studies

One JSON file per study. A study is the *protocol*: what the participant was
told, what they were asked to do, and which measurements were taken. None of
those are properties of this software, which is why they live here rather than
in `web/src/`.

The capture page loads `studies/<id>.json` from `?study=<id>`. A definition
that does not validate does not run — see `web/src/study.js`.

## Building a study: the study builder

`npm run app`, then **Study builder** (`/builder.html`). It is a form over
everything in this file, in seven numbered sections:

1. basics, and who the study may be run on;
2. what participants are told;
3. what is measured;
4. the consent options offered, and which is pre-selected;
5. tasks in order, including pictures and videos dropped straight into
   `stimuli/` with their hashes computed;
6. conditions and the completion link;
7. the analysis plan.

The header always shows whether the capture page will accept the study and
holds the Save button. Every problem is shown where it is fixed: under the
field it names, or at the foot of its section. The section list on the left
counts each section's problems.

Beside the form, live:

- every problem in full, each a link to where it is fixed;
- the protocol hash;
- **the participant's journey**: what they go through, in order, per condition;
- **the consent screen**, in the words a participant will read;
- the raw JSON, for anything the form does not cover.

The journey has one lane per condition, side by side, so a difference between
arms shows at a glance. Each lane has a strip across the top with the session
to scale. Below it:

- what happens before recording (consent, camera, the screen-distance check);
- the recording, one block per task, sized by its length and coloured by kind,
  with thumbnails of its pictures and videos;
- what happens after (upload or download, and the panel's completion link).

Click a block to jump to its task in the form. It is drawn from the same
`buildSequence` the capture page runs, so it cannot show an order the
participant would not get.

These come from the capture page's own modules, so the builder cannot call a
study valid that a participant's page would refuse.

Saving writes `studies/<study_id>.json` and adds it to `index.json`.

- A study that already has sessions is refused, and offered a new id.
- An existing draft is overwritten only when you confirm.
- A stimulus file cannot be replaced by different bytes.

Commit the saved files to version them.

## Immutable once used

**Do not edit a study that has collected a session.** Copy it to a new
`study_id` and change that.

Each definition is content-hashed, and the hash is written into every session
manifest. This is the same rule AOI sets follow, for the same reason: §4.2
found identical fixations yielding 77%, 88% and 93% dwell depending on AOI
boundaries. A protocol has the same property with more force — a different
calibration grid, a different passage, a different retention promise, and the
sessions are not comparable. Editing in place silently merges two studies under
one name, and the hash is what makes that visible rather than preventing it.

The hash covers what makes sessions comparable and deliberately skips `name`
and `notes`: retitling does not change what was measured, and a hash that
churns on prose gets ignored.

## Required fields

| field | why |
|---|---|
| `study_id`, `name`, `version` | identity |
| `disclosure.retention_days` | 45 CFR 46.116; capped at 1095 (BIPA's 3-year bound) |
| `disclosure.secondary_use` | 45 CFR 46.116 |
| `disclosure.contact` | 45 CFR 46.116(b)(7) — a route back to a human |
| `disclosure.irb_reference` | the ethics committee reference (REC or IRB); required for `participants`, and never an empty string |
| `consent_tiers` | which of the four tiers this study offers — see *Consent tiers* below |
| `modalities` | opt-in, enumerated |
| `calibration.n_points` | required when `gaze` is enabled; ≥ 5 |

None of these are defaulted. A study missing a retention period is not a study
with a sensible default retention period: the element has to be *stated*, and
inventing one would put an unreviewed promise in front of a participant.

## Consent tiers

| tier | recording | what can be measured |
|---|---|---|
| `features_in_browser` | never made — the camera feeds the in-browser engines only | gaze features and blendshapes, computed on the participant's device. Only `gaze` and `face` may be enabled; a study offering it with `voice` or `respiration` is refused, because those need the recording on a server |
| `features_only` | made, analysed on the server, then deleted | everything |
| `media_retained` | kept | everything, and it can be re-analysed |
| `media_plus_transcript` | kept, plus a transcript of speech | everything, plus the words |

`features_in_browser` is the strongest privacy option (research/pass5): the
video never leaves the device. The cost is that the AU engines, voice and
respiration cannot run, and nothing can ever be re-checked against a recording.
`studies/in-browser-example.json` shows it.

## Recruitment and conditions

**Panel identifiers.** Open the study the way Prolific does:
`/?study=<id>&PROLIFIC_PID=…&STUDY_ID=…&SESSION_ID=…`, or `?pid=` for
anything else.

- **In the browser:** the raw ID never enters `session.json`, which carries
  `participant_id: "p_pending"`. The ID is saved separately in
  `identifiers.json`.
- **On processing:** `server/pseudonym.py` replaces it with
  `p_` + HMAC-SHA256 under a per-deployment key, before anything is written.
  The key and the table linking IDs to pseudonyms live in `out/_keys/`
  (gitignored). That is the "additional information kept separately" that
  makes the data pseudonymous (UK GDPR Art 89(1)).
- **Withdrawal:** `npm run withdraw -- <Prolific ID>` finds every session by
  the ID the participant actually knows, and deletes the linking rows with
  the data.

**`conditions`** — `{"arms": ["A", "B"]}` (hashed: it is protocol).

- Each participant is assigned an arm uniformly at random from
  `crypto.getRandomValues`. The draw (seed, method) is logged as a
  `condition_assigned` event and the arm goes in the `condition` column.
- A reload keeps the same arm. Assignment is not balanced across
  participants, because a static page cannot count them; check the split
  from the events.
- A task with `"arms": ["A"]` runs only for arm A, and the consent screen
  describes that participant's arm.

**`recruitment.completion_url`** — where to send a participant when they
finish, e.g. Prolific's `…/submissions/complete?cc=CODE`.

- It must be https (or localhost for testing).
- The link appears only after the data has been saved, never before.
- It is not hashed: a completion code changes per posting without the
  protocol changing.

`studies/panel-example.json` shows all three.

## The analysis plan: `analysis`

Declared in the study, before any data is seen, and run with
`npm run cohort -- <study_id> [--csv-dir DIR]` (server/cohort.py).

The plan is **not** in the protocol hash, because changing an exclusion does
not change what participants did. It has its own `analysis_hash`, printed and
stamped on every result.

**`exclusions`** — `[{"metric": …, "min"?: …, "max"?: …}]`, applied in order.

- `metric` is a sessions-table column (`achieved_fps`, `viewing_distance_mm`, …)
  or a quality metric, taken as its median over the session
  (`face_detect_rate`, `iris_valid_rate`, `gaze_average_offset_deg`, …).
- A metric that was never measured excludes the session as `not_measured`,
  shown apart from `failed`. A criterion nobody measured is not a criterion
  met.

The funnel always starts with two further steps:

- self-tests are left out (unless `--include-developer`);
- sessions whose recorded protocol hash differs from the file are left out
  (unless `--allow-mixed`).

**`epochs`** — `[{"name", "event_type", "channels", "source"?, "stimulus_id"?,
"pre_ms", "post_ms", "baseline_ms": [start, end], "resample_hz"}]`.

- Cut on the master clock around each matching event and resampled onto a
  grid. Gaps over 250 ms are left empty, never interpolated across.
- Baseline-corrected by the mean over `baseline_ms`.
- Refused, with a reason row, when an epoch:
  - has no master timestamp,
  - covers less than half its window,
  - or has no baseline samples.
- A channel produced by more than one source must name the `source`.

**`aoi_pad_deg`** — padding for AOIs drawn on stimuli, in degrees. There is
no default (§4.2), so without it per-stimulus AOI metrics are refused.
**`heatmap_sigma_deg`** — the heatmap blur in degrees (default 1°). It is
converted per participant through their own geometry, so the same blur is the
same visual angle for everyone.

**`npm run export -- <study_id>`** writes one zip of the cohort:

- `provenance.json`;
- CSVs: sessions, attrition, events, signals per session, epochs, and
  per-stimulus gaze, AOI and facial-change results;
- heatmaps as a CSV grid and a PNG over the picture;
- a BIDS-*style* layout, clearly marked as not validated BIDS.

The zip is audited before it is kept. No recording, no `identifiers.json`, no
key material, and no raw panel ID anywhere in its bytes — or it is not
written.

`studies/stimulus-example.json` carries a plan. On the real posed session,
smile epochs on each expression hold put both "smile broadly" trials top
(baseline-corrected blendshape 0.95, 0.93), "closed smile" next (0.30), and
lip-corners-down and jaw-drop at zero.

## Who a study may be run on: `audience`

A study with no `audience` is a **developer self-test**: the person who built
the software, testing it on themselves. Every study shipped here is one. The
capture page shows a red *DEVELOPER SELF-TEST* line under the protocol name,
the consent screen tells anyone else to stop, the session records
`audience: developer`, and the researcher app labels it *self-test*.

`"audience": "participants"` declares that the protocol has been through an
ethics committee. The route is UK/EU (UK GDPR / GDPR), so the study must then
also carry everything a participant must be told when the data is collected
(UK GDPR Art 13):

| field | required for `participants` |
|---|---|
| `disclosure.irb_reference` | the REC/IRB approval reference |
| `disclosure.contact` | must contain an email address or web address, and must not be a template ("Replace this…", `example.org`) |
| `disclosure.controller` | Art 13(1)(a): who is responsible for the data |
| `disclosure.lawful_basis` | Art 13(1)(c): the Art 6 basis, e.g. public task |
| `disclosure.special_category_basis` | when `face`, `voice` or `respiration` is enabled: the Art 9 condition relied on. These streams are treated as special-category data by default (research/pass5-legal-gaps.md) |

All of these are shown on the consent screen and stored in the consent record.
They are hashed only when set, so adding them did not change the hash of any
study written before they existed.

## Modalities

`gaze`, `face`, `voice`, `respiration`. Two carry warnings the definition makes
you see at the point you enable them:

- **`voice`** produces eGeMAPS acoustic features and no valence channel. §2.3:
  the acoustics are the open part and the mapping to affect is the licensed,
  unpublished part.
- **`respiration`** produces a waveform and no breathing rate (§2.4), and is
  plausibly health data under GDPR Art. 4(15) even with no identification
  purpose (§6.3) — higher legal risk than the other three.

`voice` is the only modality that requests the microphone. Respiration is
chest/shoulder motion, not sound and not rPPG.

A **transcript** is not a modality. It is produced by
`speech.faster_whisper`, runs only for sessions whose consent tier is
`media_plus_transcript`, and is off unless the pipeline is given `--transcript`.
Offering that tier in `consent_tiers` makes it *possible*; only the
participant's own choice makes it happen.

## Tasks

`tasks` is the stimulus sequence, in order. The known types:

| type | what it does |
|---|---|
| `chinrest` | the virtual-chinrest step (runs in setup, adds no stage) |
| `calibration` | `calibration.n_points` targets, order randomised |
| `validation` | five held-out targets, deliberately not a calibration subset |
| `rest_fixation` | a centre cross; `duration_ms` optional |
| `read_aloud` | `passage: "default"` or your own array of lines |
| `free_speech` | `prompts: "default"` or your own; `duration_ms` optional |
| `expression_prompts` | posed facial movements, ready → hold → relax; `expressions: "default"` or your own `[{id, text, target_aus}]`, `repeats` (default 2, each shuffled), `hold_ms` optional. Each trial's events carry the AUs it asked for |
| `stimuli` | images and videos, one at a time after a fixation cross: `items: [{stimulus_id, kind: "image"\|"video", src: "stimuli/…", sha256, duration_ms, sound?}]`, `randomise` (default true, seeded), `isi_ms` (default 1000). See *Stimuli* below |

### Stimuli

Files live in `studies/stimuli/` and are named in the study by **sha256**. The
hash is inside the study's content hash, so the protocol covers the pixels,
not just the file name. The capture page fetches and checks every file before
consent: a missing or changed file is a setup error, not a surprise halfway
through a session. Everything is preloaded into memory, so an onset is a paint
time rather than a network time.

Each presentation writes a `stimulus` event. `stimulus_id` is the item's id,
and the span is onset to offset. The metadata records:

- where it was placed (`rect_norm`, as fractions of the stage — the same frame
  gaze is estimated in);
- its natural size and sha256;
- how onset was stamped: `animation_frame` for images, or
  `first_presented_frame` (requestVideoFrameCallback) for videos.

Videos play muted unless `"sound": true`. `duration_ms` is required for videos
too, as the most they are shown for, because the participant is told how long
the task takes.

AOIs can be drawn on a stimulus rather than on the screen. Save an AOI set with
`stimulus_id` and give coordinates as fractions of the image. Each session's
recorded `rect_norm` then places them where that participant's display showed
the picture (`server/aoi.py` `to_stage`). `tools/make_stimuli.py` generated
the example files; `studies/stimulus-example.json` uses them.

A task whose modality is not enabled is dropped — `read_aloud` in a study
without `voice` would ask a participant to speak into a microphone nobody
requested. An *unknown* task type is an error, not an omission: running a
quietly degraded version of someone's protocol is the worst available option.

The two sync clappers always bookend the sequence and a study cannot remove
them. One anchor gives the aligner an offset; two let it fit a rate, and
consumer clocks differ by tens of ppm.

Participant-facing counts and durations are derived from the stages, never
written beside them. An instruction reading "13 dots" above a 9-dot grid is the
same defect as a stale comment, except a participant acts on it.

## Before running a real participant

`m0.json` is the pilot protocol, transcribed from what the capture page used to
hard-code. It is immutable, so do not edit it: copy it to a new `study_id`, set
`"audience": "participants"` and fill in the fields above. Validation refuses
the copy until every one is real. The disclosure text needs to match what your
ethics committee actually approved. This file is not ethics advice, and nothing
in it has been reviewed by anyone.
