# Studies

One JSON file per study. A study is the *protocol*: what the participant was
told, what they were asked to do, and which measurements were taken. None of
those are properties of this software, which is why they live here rather than
in `web/src/`.

The capture page loads `studies/<id>.json` from `?study=<id>`. A definition
that does not validate does not run — see `web/src/study.js`.

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
