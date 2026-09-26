# DPIA template — webcam behavioural research with this platform

A starting point for the **data protection impact assessment** a deploying
research group owes before running participants. It follows the ICO's DPIA
template (screening → description → consultation → necessity → risks →
measures → sign-off) and pre-fills what is true of *this software*, citing
`research/pass5-legal-gaps.md`. Everything specific to a study or a
deployment is marked **TO COMPLETE**. This is not legal advice and nobody
has reviewed it; the group's DPO signs the real one.

Generate the matching record of processing (Art 30) with
`npm run ropa -- <study_id>`. It is built from the same study file.

## 1. Why a DPIA is needed

Presumptively required (research/pass5, GDPR section):

- **WP248 rev.01 (endorsed by the EDPB) criteria met: at least two.**
  - **4, sensitive or highly personal data.** Face video and voice are highly
    personal. Respiration and affect-adjacent streams are treated as Art 9
    data by default.
  - **8, innovative technology.**
  - **1, evaluation or scoring,** plausibly: facial and vocal measures of
    reactions.
  - **7, vulnerable data subjects,** where participants are the researcher's
    students, patients or children.
- **ICO list of processing likely to need a DPIA:** it names
  "neuro-measurement (e.g. emotional response analysis …)" under innovative
  technology.
- **German DSK list, item 13:** automated evaluation of video or audio
  recordings.

## 2. The processing

| | |
|---|---|
| Nature | Browser capture of webcam video (and microphone audio if `voice` is enabled), timestamped against on-screen tasks. Server-side analysis produces gaze, facial action units, voice acoustics and a breathing waveform. Output is measurements only: no identity matching, no emotion labels, no breathing rate. |
| Scope | Modalities, retention period and tiers: see the `npm run ropa` output. Number of participants, and how often: **TO COMPLETE** |
| Context | Who the participants are, and their relationship to the researchers: **TO COMPLETE**. Recruitment channel: **TO COMPLETE** |
| Purposes | **TO COMPLETE** (the research question). The platform's own intended purpose is solely scientific research. See §5 R5. |

## 3. Consultation

**TO COMPLETE:** DPO, ethics committee (REC/IRB reference in the study
file), participant or public involvement, and information security.

## 4. Necessity and proportionality

- **Lawful basis.** Art 6: `disclosure.lawful_basis`. Art 9 condition:
  `disclosure.special_category_basis`. The platform refuses to run a
  `participants` study without both.
- **Minimisation.**
  - Modalities are opt-in per study.
  - The default tier (`features_only`) deletes the recording after analysis.
  - Raw media is kept only if the participant chooses it.
  - Transcripts need their own tier.
  - `features_in_browser`: the video never leaves the participant's device.
    Only gaze and face (blendshapes, gaze features) can be offered under it,
    and it is the strongest available mitigation for R1 and R2.
- **Accuracy and validity.**
  - The two facial AU engines disagree materially on posed movements. See
    the README, "What the two engines say about each other".
  - Emotion cannot be read reliably from facial movement (Barrett et al.,
    2019). The platform therefore emits AUs, not emotions.
  - Respiration emits no rate, because no accuracy figure survived checking.
- **Retention.**
  - The period stated to each participant is enforced by
    `npm run retention`. **It must be scheduled where the data lives:**
    **TO COMPLETE**.
  - Copies outside the platform's folders (Downloads, zips, backups) are not
    found automatically: **TO COMPLETE** (the procedure for them).
- **Rights.**
  - Withdrawal deletes the recording and every measurement
    (`npm run withdraw`).
  - The consent screen states this, gives a session code to quote, and names
    the ICO complaint route.
- **Transparency.** The consent screen shows the UK GDPR Art 13 items and an
  automated-analysis notice (EU AI Act Art 50(3)), and stores the exact text
  shown with each session.

## 5. Risks

Likelihood, severity and residual risk are for the deploying group to score:
**TO COMPLETE**.

| # | Risk | Source | Platform measures | Deployment measures |
|---|---|---|---|---|
| R1 | Re-identification from retained video or audio | Face and voice are identifying; blurring does not fix it | Default tier deletes media; `features_in_browser` never records at all (a recording that arrives anyway is deleted unread); retention sweep; tombstones stop a withdrawn session being re-processed | **TO COMPLETE** access control, encryption at rest |
| R2 | Re-identification from *derived* features | VR blendshapes 43% cross-session among 116 people; eye movements 3.66% EER; voice 4.6% EER (research/pass5, ethics) | Consent says the measurements are still personal data and never calls them anonymous; no identity features; panel IDs replaced by keyed pseudonyms before any table is written, the key and link kept apart in `out/_keys/` (Art 89(1)) | **TO COMPLETE**: who can read `out/_keys/` |
| R3 | Health or other special-category inference (e.g. from respiration or affect) | CJEU C-21/23: data "capable of revealing" health "by collation or deduction"; C-252/21: aim and accuracy irrelevant | Respiration opt-in, waveform only; Art 9 condition required | **TO COMPLETE** |
| R4 | Invalid emotion inference used to judge an individual | Barrett et al. 2019; the AU engines' measured disagreement | No emotion labels are emitted; the consent notice says nothing is decided about the participant | Do not use per-participant scores for decisions (UK DPA 2018 Art 84C conditions) |
| R5 | Function creep into workplace or education use | AI Act Art 5(1)(f) prohibits emotion recognition there (since 2 Feb 2025); the research exclusion (Art 2(6)) covers solely scientific use only | Research-only intended purpose; outputs are AUs, not emotions | **TO COMPLETE**: do not deploy for employers or schools |
| R6 | The retention promise is not kept | Deletion is an explicit command | Researcher app names overdue sessions at startup; `process` refuses expired sessions | Schedule the sweep: **TO COMPLETE** |
| R7 | Unauthorised access to capture or analysis servers | — | Both servers bind to localhost; the capture server serves only page code, never data | **TO COMPLETE** hosting, network, accounts |
| R8 | A transcript captures incidental sensitive content | A transcript contains whatever was said | Separate opt-in tier; hallucination gates drop low-confidence text | **TO COMPLETE** review before sharing |
| R9 | Measurement quality differs by skin tone, glasses or lighting | Conceded in REPORT.md, not yet quantified | Per-session quality metrics and refusals are reported | A fairness audit before claims about groups: **TO COMPLETE** |

## 6. Measures approved and residual risk

**TO COMPLETE** (for each risk: measure, effect on risk, residual risk,
approved yes/no).

## 7. Sign-off

| | Name / date | Notes |
|---|---|---|
| Measures approved by | **TO COMPLETE** | |
| Residual risks approved by | **TO COMPLETE** | If high, consult the ICO before processing (Art 36) |
| DPO advice | **TO COMPLETE** | |
| Review date | **TO COMPLETE** | Also re-run whenever the study's content hash changes |
