# Rebuilding iMotions: Spec and Build Guide for a Webcam-Based Behavioral Research Platform

*A cited research report synthesizing 10 adversarially-verified deep-research
passes (~1,000 search/fetch/verify agents, 292KB of raw findings). Full
citations and raw quotes for every claim below live in `research/`. This
document is the synthesis; treat it as the entry point, and drill into the
per-pass files when you need the underlying source.*

*Scope: rebuilding an iMotions-equivalent platform for four webcam/microphone
modalities — screen-based eye tracking, facial expression analysis, voice
analysis, and respiration — deployed browser-first for remote data
collection, with a secondary in-lab desktop mode for higher-fidelity
sessions and external sensor sync.*

---

## 0. Executive summary

**The core finding of this project is not a technical one — it's that the
product you're copying has the same validity problem the regulators are
now writing law against.** Facial-expression-to-emotion inference, the
centerpiece of two of your four modalities, is rejected as non-diagnostic
by the field's own consensus review (Barrett et al. 2019), and the EU AI
Act's Recital 44 gives almost exactly that reasoning — "limited reliability,
lack of specificity, and limited generalisability" — as the basis for
prohibiting emotion inference in workplace and education settings. Whatever
you build, design the reporting layer to make relative, within-participant,
condition-contrast claims, not absolute emotion-state claims. This isn't
just the ethically defensible position — the scientific and legal reasoning
converge on it independently. [[§2.2]](#22-facial-expression--au-detection),
[[§6.1]](#61-eu-ai-act)

**iMotions itself builds almost none of what it sells.** Only the gaze
engine (WebET 3.0) and the respiration algorithm are in-house. Facial
coding is licensed Affectiva AFFDEX; voice is licensed audEERING devAIce,
itself built on openSMILE — which is why openSMILE/eGeMAPS is the
*technically correct* open-source substitute for your voice layer, not an
arbitrary choice. Smart Eye now owns both iMotions and Affectiva, so AFFDEX
is intra-group IP you cannot license on the same terms iMotions gets.
[[§1.2]](#12-build-vs-buy-map-what-imotions-actually-owns)

**"Browser-first" describes the incumbent's participant side only.**
Capture happens in-browser; processing happens in a Windows-only,
GPU-backed desktop application, and the automation-heaviest feature
(Automated AOI) requires an RTX-class GPU. The lab integration surface is a
raw TCP/UDP/LSL socket bus — not REST, not WebSocket — so browsers cannot
reach it directly. [[§1.3]](#13-architecture-browser-capture--desktop-lab-processing)

**Webcam accuracy is real but has a hard floor, and the floor is the
algorithm, not the camera.** Webcam gaze runs roughly 2x worse than
research-grade infrared (1.4° vs 0.9° accuracy; 70-76% vs 95% AOI hit
rate), but manual human annotation of the *same webcam video* reaches 92%
— meaning a better estimator, not better hardware, is what closes most of
the gap. Facial AU detection is "fair" (mean AUC ~0.72) but collapses on
specific subtle AUs (AU14/AU23 ~0.56-0.58). rPPG heart rate is genuinely
usable (MAE ~1.67 bpm in the wild) but collapses out-of-distribution
(13x MAE increase cross-dataset) and under video compression (worse than
a naive constant-guess baseline on heavily compressed footage). Speech
emotion recognition's valence signal is driven by *lexical content*
learned during fine-tuning, not prosody — meaning it breaks under exactly
the privacy-preserving audio processing (noise suppression, discarding raw
audio) you'll want to do. [[§2]](#2-validation-evidence--accuracy-budget)

**Every accuracy number above degrades further for darker-skinned
participants** in the one modality where this was quantified (rPPG,
confirmed), and is a real but unquantified gap in the other three (facial
expression, eye tracking, voice) despite being searched for twice.
[[§2.5]](#25-demographic-and-skin-tone-bias)

**Legally, the workplace/education emotion-inference ban is narrower than
it sounds, but you are not out of the woods.** EU AI Act Art. 5(1)(f)
prohibits emotion inference *only* in workplace and education contexts,
with exactly two exceptions (medical, safety) — a general research or
market-research platform sits outside it, provided you never sell into
employee-monitoring or classroom use cases. GDPR is more favorable than
commonly assumed: raw video is *not* Art. 9 special-category biometric
data unless specifically processed to identify someone — the EDPB's own
3-part test makes identification-purpose the decisive element, not mere
capture. But **US state biometric law (Illinois BIPA specifically) remains
a confirmed but under-verified exposure** — three research passes could not
get fully adversarially-verified detail on settlement sizing and the
Cothron/SB 2979 accrual mechanics; treat the raw leads in
`research/pass4d-bipa-cubi-INCOMPLETE.md` as a lead to run past counsel, not
as verified fact. [[§6]](#6-legal-and-regulatory-compliance)

---

## 1. What iMotions actually is (reverse-engineered spec)

### 1.1 Module lineup

iMotions' Remote Data Collection (RDC) platform delivers all four
in-scope modalities from a consumer webcam and microphone alone, captured
**simultaneously** in every session — no dedicated sensor hardware:

| Modality | Engine | Confidence |
|---|---|---|
| Webcam eye tracking | **WebET 3.0** (in-house) | High — confirmed on 3 independent iMotions pages |
| Facial expression analysis | **Affectiva AFFDEX** (licensed, Smart Eye Group) | High |
| Voice analysis | **audEERING devAIce** (licensed, built on openSMILE 3.0) | High — independently confirmed by audEERING's own page |
| Respiration | In-house, **chest-motion ROI tracking, NOT rPPG** | High |
| Automated AOI | In-house, GPU-dependent post-hoc step | High |

This is an existence proof of commercial feasibility, not an accuracy
claim — see §2 for validated accuracy.

### 1.2 Build-vs-buy map: what iMotions actually owns

Only two things are iMotions IP: **WebET 3.0** and the **respiration
algorithm**. Everything else is licensed:

- **Facial coding = Affectiva AFFDEX.** Output vector (from the brochure,
  vendor-asserted, unaudited): valence, engagement, 7 basic emotions +
  confusion/sentimentality, 21 named facial expressions (not numbered
  FACS AUs), blink/blink-rate, interocular distance, head yaw/pitch/roll.
  A Multiface add-on adds 33 landmarks via Affectiva cloud processing.
- **Voice = audEERING devAIce**, confirmed independently by audEERING's
  own collaboration page. devAIce is built on **openSMILE 3.0** — this is
  the load-bearing fact for your build: **openSMILE/eGeMAPS is the
  technically correct open-source substitute for your voice layer**, not
  an arbitrary pick. devAIce outputs: voice activity detection,
  categorical emotion (angry/happy/neutral/sad), dimensional emotion
  (arousal, dominance, valence), prosody (F0/pitch, loudness, speaking
  rate, intonation), speaker age/gender, and automatic voice-triggered
  event marking.
- **Critical corporate-structure fact:** Smart Eye acquired Affectiva
  (Jun 2021, $73.5M) and iMotions (Oct 2021, $46.6M). AFFDEX is
  **intra-group IP**, not neutrally licensable third-party tech — you
  cannot assume you can buy the same stack iMotions uses.
- Provenance note: openSMILE originated at TU Munich (Eyben, Wöllmer,
  Schuller, ACM MM 2010) and has been audEERING-maintained since 2013;
  eGeMAPS is Eyben et al. 2016. Cite it as "audEERING-maintained,
  TUM-originated," not as an audEERING original.

### 1.3 Architecture: browser capture + desktop Lab processing

"Browser-first" applies to the participant side only. RDC is an
**extension of desktop iMotions Lab**, which is **Windows-only**, and
specifies 32GB RAM, a 6-core i7 gen10+, a dedicated 4GB-VRAM GPU, and —
specifically for Automated AOI — an **NVIDIA RTX card, compute capability
≥6** (RTX 3050 or better). Automated AOI is a GPU-backed *post-hoc*
processing step, not something that runs in a participant's browser during
the session. Plan for server-side GPU inference if you want an equivalent
feature.

**The lab integration surface is a raw socket event bus, not a web API.**
iMotions' developer docs define three categories — Event Forwarding, Event
Receiving, Remote Control — over **TCP (iMotions listens as server), UDP
(one datagram per event), or LSL** (a separately licensed add-on added in
release 10.1.4, Nov 2024). There is **no REST, HTTP, WebSocket, or webhook
API** anywhere on iMotions' developer pages, through Lab release 11.1.10
(Aug 2026). This is independently corroborated by a third-party open-source
project, `imotions-web-bridge`, whose README states iMotions "currently has
no possibility to directly connect to its event API from a web browser, as
web browsers cannot connect to UDP/TCP sockets but only to websockets" —
the project exists purely to run a Node WebSocket relay into iMotions'
UDP/TCP API. **Build recommendation: invert this.** Expose WebSocket
natively for browser clients and LSL for lab hardware; don't replicate the
bridge tax the incumbent's own ecosystem has to pay.

External third-party sensor data ingested via the Event Receiving API is
treated as first-class: synced with all other streams, optionally graphed,
persisted to the study database, and included in text export. The
remote-control command surface (Minimize/Maximize/Shutdown/Run/Next
Slide/Save/Load/Export Sensor Data/Export Video Recordings, etc.) defines
a reasonable minimum feature set for a scripted experiment runner.
**Recommendation:** route all third-party sensor input through the
identical sync/storage/export path as native signals — a single canonical
timestamped signal table with a `source` column — to avoid a two-pipeline
divergence the moment your first external sensor lands.

### 1.4 Data export and interop

A complete iMotions Online study exports as a **single zip file,
importable into desktop iMotions Lab** — a documented pattern since iMotions
10 (4 Jan 2024), still current in Lab 11. This validates the
browser-capture-then-desktop-process pattern as a real product shape, but
the zip's internal schema is undocumented (gated behind a login), so it
supplies an architectural *pattern* to imitate, not a spec to
reverse-engineer. Per-participant exports are timestamped CSVs of facial-
expression and eye-tracking signals plus exportable visualizations (gaze
paths, heatmaps, signal overlays). Whether raw webcam video travels inside
the Lab-importable zip is undocumented either way — don't assert it does.

### 1.5 Licensing

Licensing is modular and add-on-gated ("individual modules can be activated
and deactivated"). The Advanced API and LSL EventAPI streaming are
separately licensed. **No pricing figures were verified in this research
project** — don't invent them for a business case; get a direct quote.

---

## 2. Validation evidence and accuracy budget

This is the deepest-researched section of the project and the one to
budget your product promises against. Treat every number below as coming
from a specific study under specific conditions — the caveats are not
boilerplate, they change what the number means for your case.

### 2.1 Eye tracking

| Measure | Infrared (reference) | Webcam |
|---|---|---|
| Euclidean offset, % screen (smooth pursuit task) | 13% | 24% |
| Accuracy, degrees of visual angle (Kaduk 2023) | ~0.9° | ~1.4° |
| Accuracy, degrees (Bogdan et al. 2023) | ~0.5° | 3–4.5° |
| AOI hit rate | 95% | 70–76% |
| Cluster/effect onset delay | 100 ms | 300 ms |
| Sampling rate | 60 Hz | 9–39 Hz, jittered |

Two figures bracket a wide range (0.9-1.4° vs. 0.5° vs. 3-4.5°) because
they come from different studies, algorithms, and conditions — Kaduk et
al. is a vendor-favorable best case (see below); Bogdan et al. is a more
typical WebGazer-class figure. **Use 3-4.5° as your default planning
assumption and treat sub-1.5° as an aspirational, hardware/algorithm-
dependent best case, not a default.**

**The floor is the algorithm, not the camera.** In Slim et al. 2024
(Open Mind), human manual annotation of the *same webcam video* reached
92% target detection where WebGazer reached only 70%. This is the single
most important number in the eye-tracking section for a build team: it
means a better gaze-estimation model, not better optics, recovers most of
the gap to infrared.

**Effects still replicate, with attenuation.** The cascade effect, novelty
preference, and visual-world paradigm all replicated online via WebGazer,
with effect sizes shrunk **20-27%**. A more precise, validated inflation
figure comes from a separate study: assuming **50% online effect-size
attenuation**, one team scaled 18 lab participants to 63 online, and this
matched an *observed* attenuation ratio of 52% [42%, 62%]. **Use 50%
attenuation, not 20-27%, as your conservative default for power planning**
— it's the more precisely validated figure.

**Webcam gaze reaches parity with lab hardware only under favorable
conditions.** Munoz et al. 2025 (Behavior Research Methods) found
comparable gaze patterns and choice-model parameters between WebGazer and
EyeLink only on **large displays with simple tasks**; reliability
deteriorated on smaller screens and with complex choice matrices.
Separately, webcam precision is documented as insufficient for
**word-level reading AOIs**. Design implication: size your AOIs generously
(pad to your measured spatial-error budget, not pixel-tight), and avoid
promising fine-grained (word-level, small-icon) attention measurement on
a general consumer laptop screen.

**Sampling rate must be measured per session, not assumed.** WebGazer
achieved 12 fps on one lab machine (SD 0.4) and 26 fps across home setups
(SD 8.9, range 9-39) vs. 60 Hz for infrared. **Bin to 100ms; log effective
fps per session as a pre-registered exclusion variable; abandon
velocity-based saccade detection** at these rates — this is exactly why
WebET 3.0 uses HMM-based fixation classification instead of I-VT/I-DT, and
why dispersion/velocity detectors (I-VT, I-DT, I-HMM, EyeMMV) documented
in the literature break down on dynamic stimuli and under head movement:
accuracy drops from ~90-92% on static-screen data to ~68-70% on real
locomotion at the *same* 30Hz sampling rate.

**Calibration density: 12+ points, sharp diminishing returns after.**
Raising calibration/evaluation density from 5 to 18 points cut mean
spatial error ~27% and angular error ~24%, with the largest single step
9→12 points; 12→18 gave only marginal gain.

**Sample-size scaling for small effects at low sampling rates.** To reliably
detect small (5-10ms) effects in First Fixation Duration: ~2,400
observations/condition at 1000Hz, 6,400 at ≤125Hz, and **≥9,000 at
sampling rates under 50Hz** — i.e., your webcam regime. This is a real
constraint on what effect sizes are even detectable without enormous trial
counts.

**A best-case, vendor-favorable accuracy ceiling exists — read the fine
print.** Kaduk et al. 2023/24 got webcam accuracy of 1.45° vs. EyeLink's
0.91° (Labvanced platform). But: three of four authors are employed by the
company developing the platform under test; the setup used an *external*
Logitech StreamCam, a virtual chinrest, a ~5-minute ~120-point calibration,
a **7%-of-screen calibration-error gate with forced retry**, **seven-point
drift-correcting re-calibration every 1-7 trials** (costing ~15s per
recalibration, +4 min total session time), controlled lab lighting, and
**glasses-wearers excluded outright**. None of this transfers to an
unsupervised at-home participant on their own laptop webcam. Take the
protocol pattern (gate + drift correction), not the accuracy number, as
your reusable takeaway.

**Validated protocol templates for your own accuracy validation study.**
Two reusable designs: Wisiecka et al. (ETRA '22, n=83, 3-condition
between-subjects: webcam / remote IR / integrated) and Slim et al.
(within-session simultaneous capture, adds a human-annotation arm).
**Prefer Slim's architecture** — paired within-session comparison, and the
human-annotation arm is the single most valuable design element, since it
separates "the webcam can't see it" from "our algorithm can't infer it."

### 2.2 Facial expression / AU detection

**The scientific problem is architectural, not incremental.** AFFDEX-style
pipelines run in two stages: (1) detect facial Action Units, (2) map AU
configurations to emotion labels. Stage 1 is merely modest; **stage 2 is
rejected by the field's own consensus review.**

**Stage 1 — AU detection vs. FACS coders:**

| Metric | Value |
|---|---|
| OpenFace 2.0 mean AUC, in-the-wild (Aff-Wild2) | 0.72 |
| OpenFace 2.0 mean AUC, posed (DISFA+) | 0.81 |
| Hard AUs — AU14 (dimpler) / AU23 (lip tightener) | 0.58 / 0.56 AUC |
| Easy AUs — AU12, AU6 | >0.80 / >0.90 (posed) |
| Py-Feat per-AU F1 range, DISFA+ | AU12 .72-.83 … **AU20 .13-.24** |

0.72 AUC is conventionally "fair," not chance-level — the real finding is
the **per-AU floor**, which is where your product's specific AU claims
will actually fail. AU14/AU23 reflect facial *tension* rather than
movement, and need depth/3D/blood-flow cues a 2D webcam frame doesn't
have. **Design implication: whitelist which AUs you report based on this
floor** — don't present a uniform confidence across all 20+ AUs.

**Stage 2 — AU-to-emotion inference is not diagnostic.** Barrett et al.
2019 (*Psychological Science in the Public Interest*, an invited
consensus review spanning opposing camps, naming Affectiva explicitly)
concludes: emotion categories "are **not** expressed with facial movements
that are sufficiently reliable and specific across contexts, individuals,
and cultures to be considered diagnostic displays of any emotional state."
Underlying meta-analysis (89 effect sizes, 3,599 participants, spontaneous
behavior): coherence **r = .32**, hypothesized configuration present in
only **~19%** of emotional episodes. Py-Feat's own authors cite this
affirmatively. **Scope precisely: this means "not diagnostic," not "no
information" — Barrett concedes above-chance signal.** Design your
reporting layer around within-participant, relative, condition-contrast
claims ("more brow-furrow activity during X than Y"), never absolute
emotion-state claims ("this participant felt happy").

**Commercial classifiers underperform humans, and the gap widens for
spontaneous (not posed) expression.** Dupre et al. 2020 (PLOS ONE) tested
8 commercial classifiers on the same 937 videos rated by 14 human
observers: **humans 72.5% vs. classifiers 53.9%** average. Affectiva
Affdex specifically: 50.5%, 6th of 8. Best-performing (Emotient FACET,
now discontinued) reached 61.9%. **These are 2018-2020 SDK vintage
(Affdex v3.4.1, not the AFFDEX 2.0 iMotions ships now) on lab-recorded,
well-lit, frontal video — an optimistic upper bound on what a consumer
webcam will produce, not a webcam measurement.**

**Engine choice alone swings your data yield by ~20 points, and expression
counts by 3-4x, on identical video.** A 2025 study running iMotions/AFFDEX,
FaceReader, and Py-Feat on the *same* 100-child recordings found: valid
face-frame rate 43% (iMotions/AFFDEX) vs. 62-63% (FaceReader/Py-Feat);
Py-Feat detected expressions in 3-4x as many frames as the other two.
Per-child agreement on happiness proportion between engines: r = 0.37-0.75.
**No engine's absolute output should be treated as ground truth.** The one
constructive signal: **relative, within-participant proportions were
robust across engines** even where absolute counts weren't — reinforcing
the design recommendation above.

**Bias: conceded qualitatively, not yet quantified.** Py-Feat's own
authors concede in their peer-reviewed paper that their models "likely
contain some degree of bias with respect to gender and race... faces with
darker pigmentation are often more difficult to detect" — an admission
against interest from a toolbox's own authors, the strongest class of
source for this. No stratified per-Fitzpatrick-type numbers exist in any
source found across two dedicated research passes.

### 2.3 Voice / speech emotion recognition

**The celebrated result is lexical, not paralinguistic — and this
collides directly with your privacy architecture.** Wagner et al. 2023
(IEEE TPAMI) proved that transformer SER's strong valence performance is
driven by **implicit linguistic content learned during fine-tuning**, not
prosody. Proof: re-synthesizing test utterances via TTS from transcripts
(same words, prosody stripped) left high-valence models' correlation
nearly intact (CCC .635 → still strong on flat synthetic audio); freezing
the transformer layers during fine-tuning collapsed correlation to near
zero. **Wording precisely: "not paralinguistic," not "not acoustic"** — the
model's only input is the waveform, it just learns to transcribe-and-infer
internally.

**Consequence for your build:** valence-from-voice only works if
intelligible speech content survives your pipeline. Aggressive noise
suppression, heavy codec compression, or a data-minimization architecture
that discards raw audio and keeps only eGeMAPS-style hand-crafted features
will **destroy the mechanism that made this result good.** Arousal from
acoustics alone is comparatively robust; valence is effectively a covert
speech-content model wearing an acoustic-features costume.

**Absolute performance on naturalistic speech is weak, and doesn't
transfer across corpora.** Best-in-challenge 8-class SER (Odyssey 2024
Emotion Recognition Challenge, MSP-Podcast, 31 teams): top score **Macro-F1
0.357** against chance 0.125 (WavLM-Large baseline: 0.311, ranked 13th).
Cross-corpus (MSP-Podcast → IEMOCAP): CCC degradation **11% arousal, 21%
dominance, 30% valence** — valence degrades worst, consistent with the
lexical-dependency finding above. Any new deployment population is
effectively a domain shift; plan for this degradation, don't assume
in-corpus numbers transfer.

### 2.4 rPPG (heart rate) and respiration

**Correcting a premise: iMotions' respiration is NOT rPPG.** It's
chest/shoulder-motion ROI tracking — an image-processing pipeline
detecting subtle chest movement, band-passed ~7.5-30 cycles/min. This is
architecturally distinct from, and more compression-robust than, facial
rPPG for heart rate — **treat them as two separate engineering problems**,
not one pipeline. iMotions doesn't attempt facial-rPPG-derived HR/HRV at
all; if you want that, you're building something the incumbent doesn't
have.

**Heart rate from rPPG is genuinely usable, with two sharp failure
modes.** Largest independent in-the-wild validation (Woelk et al. 2026,
n=77, 2,436 videos, POS algorithm): **MAE 1.67 bpm** (SD 2.64), r=.56, 95%
limits of agreement −5.4 to +6.3 bpm. But:

1. **Cross-dataset generalization is the dominant failure mode**, dwarfing
   algorithm choice. PhysNet trained/tested within one dataset: 0.98 bpm
   MAE; trained on a different dataset: **13.30 bpm MAE — a 13x
   degradation**. DeepPhys stayed far more robust under the identical
   stress test (3.96 bpm). **Pick your architecture for out-of-distribution
   robustness**, since every real participant's home setup is
   out-of-distribution relative to any lab training set.
2. **Compression is a hard filter, not a soft degradation.** On heavily
   compressed footage, unsupervised rPPG methods perform **worse than a
   dummy baseline that always guesses 75 bpm**. Among codecs, **H.265 gives
   by far the best accuracy/bitrate tradeoff** — only +0.3 bpm error for a
   ~100x bitrate cut (26 Mbps → 0.26 Mbps). If you're capturing rPPG, your
   WebRTC encoding path matters more than almost any other engineering
   choice.

**HRV is much harder than HR — don't promise it per-participant.** Best
result: SDNN error 11.45ms, RMSSD error 11.02ms vs. ECG — sufficient for
**group-level** comparisons, explicitly not individual-level precision.
Sobering context: even **finger-contact PPG** (far easier than remote
rPPG) only passes formal Bland-Altman agreement on 7 of 16 HRV parameters
despite strong correlation (r>0.7) on 14 of 16 — high correlation ≠
clinical-grade agreement. **Frame HRV as a between-condition/between-group
signal, never a per-participant metric.**

**Respiration accuracy is the single biggest remaining validation gap in
this project.** After two dedicated research passes, no verified
breaths-per-minute accuracy figure vs. chest belt/RIP/spirometry survived
adversarial checking — one specific figure was explicitly refuted. Only a
narrow algorithm-architecture finding survived: of six chest/abdomen
motion-extraction combinations, those using multiple 1D or 2D motion
profiles outperform single-combined-1D-profile approaches. **This is a
genuine open research question for your team to resolve empirically, not
just a documentation gap.**

### 2.5 Demographic and skin-tone bias

**Quantified and confirmed, in one modality only.** rPPG heart-rate
accuracy is significantly worse for darker Fitzpatrick skin types
(exp(β)=1.17, p<.001) — consistent with melanin absorbing the light
carrying the blood-volume-pulse signal. **This is mitigable**: the error
gap between Fitzpatrick type 1 and type 5 drops from **~2.25 bpm to ~0.21
bpm at luminance ≥30**. Actionable design recommendation: enforce a
minimum-illumination check in your capture setup flow rather than hoping
for good lighting.

**Conceded but unquantified elsewhere.** Facial expression: Py-Feat's
authors concede darker-pigmented faces are harder to detect, without
stratified numbers. Eye tracking (glasses, contacts, makeup, eyelid shape,
iris color) and speech emotion recognition bias by accent/gender/age:
**despite being explicitly researched twice, no claims survived
adversarial verification in either modality.** This is an evidence gap in
the literature (or in what this project could locate), not evidence of no
bias — do not present the silence as a clean bill of health, and budget
for an internal fairness audit before shipping.

---

## 3. Build guide: architecture

### 3.1 Deployment model

Mirror the validated pattern, inverted for browser-nativity:

- **Participant side (browser):** WebRTC capture of webcam + mic;
  in-browser or server-side inference depending on latency/privacy
  tradeoffs (see §6.5); WebSocket to your backend for live event streaming
  and remote control — don't build the socket-bridge tax iMotions'
  ecosystem has to pay.
- **Lab/desktop mode:** Reuse the same canonical event schema (§4.4), but
  add **LSL** as the sync transport for external hardware sensors (EEG,
  GSR, dedicated eye trackers), since LSL carries its own clock-offset
  correction and is the more defensible sync path for lab-grade
  multi-sensor sessions.
- **GPU-dependent post-processing** (Automated AOI-equivalent features):
  server-side, not browser-side. Budget for this explicitly; it's not a
  "run it in the client" feature.

### 3.2 Per-modality build-vs-buy

| Modality | Recommended open-source base | Why |
|---|---|---|
| Gaze | WebGazer.js baseline; invest in a modern MediaPipe/WASM-based estimator | WebGazer numbers in §2.1 are a *conservative floor* for 2026 — commercial (WebET, RealEye) and modern learned estimators weren't tested and likely do better |
| Facial expression | OpenFace 2.x/3.0, Py-Feat, or MediaPipe Face Landmarker (blendshapes) | Py-Feat gives probability estimates (not binary), is actively maintained, and its authors are transparent about bias/limits |
| Voice | openSMILE + eGeMAPS/ComParE feature sets | Technically correct substitute for devAIce — devAIce is *built on* openSMILE |
| Respiration | Chest/shoulder ROI motion tracking (multi-profile, per §2.4) as primary; facial rPPG (CHROM/POS/DeepPhys via rPPG-Toolbox) as a separate, harder, optional layer for HR | Don't conflate the two problems |

Don't assume you can license AFFDEX on iMotions' terms — Smart Eye owns
both companies (§1.2).

### 3.3 Time synchronization

**This remains the least-evidenced, highest-risk part of the build**,
even after two dedicated research passes.

**What's confirmed:**

- LSL's sync facility is NTP-modeled, targeting sub-millisecond
  clock-offset accuracy on a local network — a stated design goal, not an
  independently measured remote/browser figure.
- `performance.now()` is monotonic; `Date.now()` is not (subject to
  system clock adjustment). Spectre-mitigation clamps `performance.now()`
  resolution to **100µs by default, 5µs under cross-origin isolation**
  (W3C hr-time-3 spec). Firefox/Safari's exact clamp values were not found
  in a primary source — treat as an open implementation detail to verify
  directly against current browser behavior.
- WebAudio's `AudioContext.currentTime` is a **separate clock** from
  `Date.now()`/`performance.now()`, with ~2.7-2.9ms render-quantum
  granularity; Firefox rounds it further for fingerprinting resistance.
  No published measurement of its drift over a session survived
  verification — budget time to measure this empirically before relying
  on it for audio/video alignment.
- `WebCodecs VideoFrame.timestamp` semantics and `captureStream`
  frame-timestamp exposure: **not confirmed in any primary source found.**
  Verify directly against the current spec before architecting around it.

**What's confirmed about the realistic ceiling:** audio-visual
synchrony is **"the least precise aspect" of browser-based timing**, and
as of the studies reviewed, **no online experiment system could reliably
deliver precisely-timed audio onset.** Display-timing error varies by
browser: Chrome ~11.5ms (best), Edge ~18.7ms, Firefox ~22.6ms, Safari
~30.0ms. Response-time precision: PsychoJS <3.5ms, jsPsych/Testable
3.2-8.4ms, Gorilla <6ms. Average response-recording lag online is **~80ms**
vs. 8-67ms on supervised lab hardware. Lab software (Psychtoolbox,
PsychoPy desktop, Presentation, E-Prime) achieves sub-1ms — that ceiling
will not close in a browser.

**Design pattern recommendation** (synthesis, not sourced): timestamp
every sample at capture with its own stream's native clock; never assume a
fixed inter-sample interval; log achieved sampling rate per stream per
session as a first-class data-quality variable; **state AV-sync accuracy
qualitatively in your documentation** ("best-effort, browser- and
device-dependent") rather than promising a millisecond figure you can't
back with a citation. A concrete alternative worth prototyping: an
audio-video **cross-correlation alignment step** (analogous to a clapper-
board) run once per session against a known sync stimulus, since no
built-in browser mechanism guarantees tight AV alignment.

### 3.4 Data schema and export formats

**No formal export standard for this exact data class exists** — confirmed
by two dedicated research passes, not just an absence of evidence. BIDS
(with no eye-tracking-specific extension found) and LSL's XDF format are
the nearest analogues to borrow *structure* from, not adopt wholesale.

**Recommended schema** (synthesis): a canonical long-format signal table
(`participant_id, session_id, stream, timestamp, value, native_clock_id`)
plus a separate canonical event table (`participant_id, session_id,
event_type, onset_timestamp, stimulus_id, metadata`), materialized as
Parquet for analysis and CSV for interchange — the same pattern iMotions'
own text-data export implies, generalized to be modality-agnostic and to
carry a `source` column distinguishing native vs. third-party sensor data
(per §1.3's recommendation).

---

## 4. Analysis and metrics pipeline

### 4.1 Gaze metrics and fixation detection

Ground your metric naming in **Holmqvist et al.'s canonical taxonomy**
("Eye Tracking: A Comprehensive Guide to Methods and Measures") rather
than inventing your own — it treats latency and duration metrics as a
family of *distinct*, separately-defined constructs, not interchangeable
terms: "entry time" and "thresholded entry time" are two separate latency
measures; "first fixation duration after stimulus onset," "first fixation
duration in an AOI," "dwell time," "total dwell time," and "first/second-
pass dwell time in an AOI" are five separately operationalized duration
measures. Cross-vendor metric-definition inconsistency is real but only
weakly evidenced here — one concrete illustration: Tobii Pro Spectrum
reports **0.01° RMS precision on the filtered signal vs. 0.06° on raw**
under identical conditions, a 6x difference purely from which processing
stage you measure. **Document and expose which processing stage each of
your metrics reflects.**

**Fixation detection is algorithm-dependent, not just data-dependent** —
running I-VT, I-DT, I-HMM, or adaptive detectors on the same raw gaze data
produces materially different fixation counts and durations. These
detectors work reasonably well on static stimuli but **barely better than
chance on dynamic video**, and traditional dispersion/velocity algorithms
additionally break down under head movement (accuracy ~90-92% static vs.
~68-70% during real locomotion at the same 30Hz sampling rate). This is
the direct engineering justification for iMotions' own choice of
HMM-based classification (§2.1) — **don't default to I-VT/I-DT** for a
webcam pipeline running at 9-39Hz on dynamic stimuli.

### 4.2 Heatmaps and scanpaths

Heatmap-generation mechanics (Gaussian KDE bandwidth selection, duration-
vs. count-weighting, cross-participant normalization) were explicitly
researched but **produced no surviving verified claims** — a real gap;
budget a follow-up literature pass before finalizing your heatmap
renderer, or default to conventional practice (bandwidth tied to
foveal size ~1-2°, duration-weighted accumulation) with the caveat that
it's unvalidated in this project.

**Scanpath comparison has an established toolkit**, well-evidenced:

- **String-edit/AOI-sequence methods** (Levenshtein-family, ScanMatch —
  which adapts Needleman-Wunsch to grid/AOI-segmented sequences).
- **MultiMatch** — represents each scanpath as saccade vectors and scores
  similarity along **five separate dimensions** (shape, direction,
  length, position, duration) rather than one composite score, explicitly
  avoiding the AOI-boundary "quantization noise" that affects string-edit
  methods.
- ScanMatch-based analysis has demonstrated real diagnostic value —
  revealing group differences aggregate dwell-time metrics missed.

**AOI hit-rate metrics are highly sensitive to boundary definition, not
just tracker accuracy.** One tool showed its hit-rate metric shift from
77% to 88% to 93% purely from iteratively refining the *same* AOI
definitions on the *same* gaze data. **Version and expose your AOI
definitions and padding choices alongside reported hit-rate statistics** —
pad AOIs to your measured spatial-error budget (§2.1: ~3-4.5°), don't use
pixel-tight boxes.

### 4.3 Dynamic AOIs

For video stimuli, two established but non-trivial approaches exist:
**DynAOI**-style 3D-model ray-casting (requires building a 3D scene model
first, e.g. in Blender — not a drop-in solution for arbitrary video) or
manual keyframe-polygon interpolation (the older, simpler baseline). A
modern segmentation/detection-model-based automated approach — what you'd
actually want to build — was **not found as a documented, citable
method**; this is a genuine build-it-yourself opportunity, not a solved
problem to copy.

For **dynamic web pages and scrolling content**, prefer **event-driven
coordinate remapping** (scroll/DOM-event based, à la eyeScrollR: sub-2px
median error) over screen-recording-based remapping. Video-recording-based
methods (including commercial tools) are inherently limited by screen-
recording frame rate vs. monitor refresh rate mismatch, producing
documented timing inaccuracies of **100ms+ under frame-skipping/lag** (one
case reaching 141ms) — a second reason, beyond accuracy, to route through
DOM events rather than post-hoc video analysis wherever the stimulus is a
web page you control.

### 4.4 Epoching, aggregation, statistics, and export

This is the second-largest evidence gap in the whole project, alongside
respiration accuracy — **zero claims survived verification** on epoching/
baseline-correction procedure specifics, despite being researched twice.
What *did* land, from a narrower retry pass, gives you the right papers to
build from even though the operational detail (exact baseline windows,
formulas) needs direct consultation of the primary sources:

- **Cluster-based permutation testing**: Maris & Oostenveld (2007) — the
  canonical method for time-series gaze/physiological data, handling the
  multiple-comparisons problem without assuming a fixed window.
- **GAMMs for time-course gaze data**: van Rij et al. (2019) demonstrate a
  **250ms subtractive pre-stimulus baseline** in a pupillometry
  application — a concrete number to start from, though verify against
  the source before hard-coding it.
- **Growth curve analysis**: Mirman et al. (2008).
- The "keep it maximal" random-effects debate (Barr et al. 2013 vs.
  Matuschek et al. 2017/Bates et al.) — **no claims survived**; consult
  these papers directly rather than relying on this report for guidance
  here.

**No formal multimodal-behavioral-data export standard exists** — see
§3.4 for the recommended schema pattern to build instead.

---

## 5. Study design and running participants

### 5.1 Calibration and viewing-distance recovery

**You cannot assume viewing distance.** Across 1,153 online participants:
mean 47.3cm, **SD 8.9cm**, range 17.4-68.3cm. Degrees of visual angle are
meaningless without a per-participant estimate.

**The fix is off-the-shelf.** jsPsych's `virtual-chinrest` plugin (v3.1.0,
MIT-licensed, actively maintained) implements Li, Joo, Yeatman & Reinecke's
method: **credit-card resizing** for pixel scale (ISO/IEC 7810 ID-1
dimensions, 85.6×53.98mm) plus **blind-spot mapping** for distance.
Recovers distance to **2.4-5.5cm MAE**, beating body-height regression
(8.9cm). The blind-spot method assumes a **fixed group-level constant
(13.5° temporal eccentricity)**, not measured per participant — validated
range across participants was 11.53-16.01° (mean 13.59°, SD 0.96°), so
this is the documented source of the residual error, not an unvalidated
guess. Residual error propagates to **0.11-0.18× the intended stimulus
size** in computed degrees of visual angle — a real, board-line-acceptable
error budget you should document, not eliminate.

**Budget for exclusion cost — but most of it is avoidable.** One published
Prolific deployment discarded **66%** of participants (266/403) using
these procedures; a second lost 46%. Roughly half of the loss was
avoidable form-validation failure (implausible self-reported height,
incorrectly-measured reference object) that a well-designed input-
validation UI can prevent — budget for the unavoidable half, engineer away
the avoidable half.

**jsPsych's stock calibration defaults**, usable as your starting
parameters: 9-point grid at 10/50/90% of screen width/height, click-based
calibration mode (view/fixation mode is a selectable alternative), 1
repetition per point, fixed order unless randomized. **Calibration point
count matters** (§2.1: 12+ points, diminishing returns after) — jsPsych's
default 9-point grid is below your optimum; consider extending it.

**Validation gives you the numbers, not the threshold.** jsPsych's
`webgazer-validate` plugin emits `percent_in_roi`, `average_offset`,
`samples_per_sec` — but **publishes no pass/fail cutoff.** Every inclusion
criterion is yours to preregister (see §5.3 for concrete numbers from
other studies to start from).

**The best-case accuracy ceiling requires conditions you cannot enforce
at home** (§2.1: Kaduk et al.'s 1.45° needed external camera, ~120-point
calibration, glasses exclusion, gated retry, frequent drift correction —
15s per recalibration, +4min total session time). If you want anything
close to that accuracy, budget the same session-time cost; if you can't,
plan your effect-size expectations around §2.1's 3-4.5° default instead.

### 5.2 Participant environment and instructions

The only citable environment guidance found is jsPsych maintainers' own
list, explicitly labeled **"anecdotal observations,"** not measured effect
sizes: good, even lighting; head stillness (calibration is **not robust to
head movement**); closing unnecessary applications (gaze prediction is
computationally heavy relative to typical jsPsych workloads); checking
achieved sampling rate during validation. Nothing was found on
backlighting specifics, camera height, glasses on/off, battery-saver
modes, or wired-vs-wireless network — treat these as reasonable
engineering defaults to include in your setup flow, not evidence-backed
requirements.

**For audio setup:** you can programmatically probe whether a device
permits disabling browser DSP — `MediaStreamTrack.getCapabilities()`
reports `echoCancellation`, `noiseSuppression`, `autoGainControl` as
`[true, false]` on a live track. **Caveat: this is best-effort** — the
spec explicitly says the UA "will not fail" if it can't honor the
constraint, so a capability report doesn't guarantee OS/driver-level
processing is genuinely bypassed. Verify empirically against your actual
target devices before relying on it, and recall §2.3: if you're
suppressing noise or compressing audio for privacy, you may be destroying
the lexical content that makes voice valence work at all.

### 5.3 Data-quality screening and exclusion criteria

Concrete, citable numbers now exist to start your preregistration from:

- **Minimum sampling rate: 5 Hz**, applied in a published study, excluding
  18 of 220 participants. Achieved rate in that sample: mean 19.7Hz
  (SD 6.4, range 5.5-30.1) — a realistic distribution to design your own
  thresholds around.
- **Face-detection confidence threshold: 0.5**, removed <0.1% of samples
  in the same study.
- **A full, citable attrition funnel** from one study: 253 initial → 202
  usable (~20% loss): 26 failed calibration, 7 withdrew, 18 excluded for
  low sampling rate. A different published study saw **73% attrition** —
  the spread is large and protocol-dependent, so run a pilot before
  committing to a recruitment budget.

### 5.4 Sample size, power, and panel quality

**Two validated approaches to sample-size inflation:**

1. **Analytic inflation for effect attenuation** — assume **50% online
   effect-size attenuation** (validated against an *observed* 52%
   [42%,62%] ratio in one study); e.g., 18 lab participants → 63 online
   for equivalent power.
2. **Simulation-based mixed-model power** via the R `simr`/`mixedpower`
   packages, giving concrete N-vs-power curves — the right approach when
   closed-form power calculations aren't available, which is most of the
   time for this data class.

**Trial-count reliability**: recall §4.1 — for small (5-10ms) effects at
webcam-class sampling rates (<50Hz), you may need **≥9,000 observations
per condition**, far more than lab-hardware intuitions suggest.

**Panel quality is now evidenced with real comparative numbers.**
**Prolific and CloudResearch consistently outrank MTurk, Qualtrics, and
Dynata** on attention-check pass rates and dropout, per three independent
studies (Peer et al. 2022; Chmielewski & Kucker 2020; a 5-platform PLOS
ONE comparison). Default to Prolific or CloudResearch for recruitment
unless you have a specific reason not to.

---

## 6. Legal and regulatory compliance

*Legal research in this domain is unusually time-sensitive and, for US
state law specifically, only partially verified after three research
attempts. Treat §6.3 as leads for counsel, not settled fact. Nothing in
this section is legal advice.*

### 6.1 EU AI Act

**Article 5(1)(f)** prohibits AI systems that infer emotions of a natural
person in **workplace and education institution** contexts, with **exactly
two exceptions**: systems placed on the market strictly for medical
reasons or safety reasons. No research, commercial, or general-market-
research carve-out exists in the provision text itself.

**Recital 44's stated rationale has two threads**, and they matter for
your product positioning: (1) a **scientific-validity concern** —
"limited reliability, lack of specificity, and limited generalisability"
of emotion-inference AI, since emotional expression varies across cultures
and situations; (2) risk of detrimental/unfavorable treatment. Thread (1)
is *the same concern* §2.2's Barrett et al. finding raises on independent
scientific grounds — the law and the science converge.

**Practical read for your use case:** a general research or market-
research platform, not sold into employee-monitoring or classroom
deployments, sits **outside** the Art. 5(1)(f) prohibition. Whether it
falls under **Annex III high-risk classification** (with attendant Art.
50(3) transparency obligations to inform exposed persons) for
non-prohibited emotion-recognition use **was not confirmed either way**
across two research attempts — get this specifically reviewed by counsel
before commercial launch, especially for any B2B use case where an
end-client might deploy your platform in a workplace context regardless of
your own positioning.

**Definitional scope**: Art. 3(39) defines "emotion recognition system" by
reference to biometric data; **Recital 18 excludes** detection of physical
states like pain or fatigue, and mere detection of readily-apparent
expressions/gestures **unless used to infer emotion**. This is relevant to
whether your gaze/attention or respiration-rate outputs (not run through
an emotion classifier) fall inside the definition at all — a plausible
reading is that raw attention/arousal metrics are outside scope while your
facial-emotion and voice-emotion outputs are inside it, but this line was
not independently confirmed by legal scholarship in this research.

**Timeline** (confirmed): entered into force 1 Aug 2024; prohibitions
(including Art. 5) effective 2 Feb 2025; the Commission published
non-binding prohibited-practices guidelines 4 Feb 2025 (authoritative
interpretation reserved for the CJEU); GPAI/governance obligations 2 Aug
2025; general applicability 2 Aug 2026; some high-risk obligations 2 Aug
2027. Article 99 penalties for prohibited-practice violations: **up to
€35M or 7% of global turnover.** 2025-2026 "digital omnibus"/simplification
developments were searched for but not confirmed — check current status
before finalizing a compliance timeline.

### 6.2 GDPR

**More favorable than commonly assumed, if you architect correctly.**
Article 4(14) defines biometric data with the **identification-purpose
qualifier as a defining element**, not merely a limitation: data "which
allow or confirm the unique identification of that natural person." The
EDPB's Video Devices Guidelines 3/2019 state explicitly: **"video footage
of an individual cannot... in itself be considered as biometric data under
Article 9, if it has not been specifically technically processed in order
to contribute to the identification of an individual."** The EDPB's
3-part test: (1) nature — physical/physiological/behavioural
characteristic; (2) means — specific technical processing; (3) **purpose —
used to uniquely identify.** All three must be present; purpose is
decisive.

**Practical read:** facial-expression analysis, gaze tracking, and
voice-emotion inference **run for research/behavioral purposes, not
identification, plausibly fall outside Art. 9 special-category biometric
data** — a materially different (and more workable) position than
"any facial video is automatically special-category data." This does not
mean GDPR doesn't apply (ordinary personal-data obligations under Art. 6
still do, and Art. 9(2)(a) explicit consent or 9(2)(j) scientific-research
exceptions remain your fallback if a regulator disagrees with this
reading) — get this specific interpretation confirmed by counsel, since it
is the single most commercially important legal question in this report
and rests on an EDPB guideline interpretation, not a court ruling on your
exact use case.

**Health data is a separate risk vector.** Art. 4(15) defines health data
broadly — "personal data related to the physical or mental health...
which reveal information about health status." Your respiration-rate and
heart-rate outputs are plausible candidates for this category **even
without an identification purpose**, since Art. 9's health-data limb
doesn't carry the same identification qualifier as the biometric-data
limb. This was not fully resolved in this research — **treat physiological
(respiration/HR) outputs as higher legal risk than gaze/facial/voice
outputs**, pending counsel review.

**Confirmed but not detailed further**: Art. 9(2)(a) explicit consent and
9(2)(j) scientific-research exceptions exist (subject to Art. 89 conditions
and Member State derogations). **Not confirmed in this research**: Art. 30
records-of-processing specifics, Art. 35 DPIA "nine criteria" application
to your specific pipeline, controller/processor allocation for a platform
serving both academic and commercial clients, and any published guidance
reconciling a retention schedule across GDPR storage limitation and BIPA's
3-year cap (§6.3). These are gaps to close with counsel, not gaps this
report can fill.

### 6.3 US state biometric privacy law

**⚠️ This subsection is the least-verified part of the entire report.**
Three research attempts (including one maximally narrow, single-topic
retry) all hit the same web-fetch rate limit before completing adversarial
verification. What follows distinguishes **confirmed** (3-vote verified)
from **raw leads** (found in named sources — FindLaw, JD Supra, Wikipedia —
but never independently cross-checked). **Do not present the raw-lead
items as settled fact in any compliance document; run them past counsel
first.**

**Confirmed:**
- Illinois BIPA's "biometric identifier" definition includes a "scan of...
  face geometry" (alongside retina/iris scan, fingerprint, voiceprint).
- BIPA statutorily **excludes** photographs, writing samples/signatures,
  demographic data, and physical descriptions (height, weight, hair/eye
  color) from "biometric identifier."
- BIPA's "biometric information" definition covers data *derived from* a
  biometric identifier and used to identify an individual — and this
  derived-data definition **also excludes** anything derived from the
  excluded categories above.
- Washington's My Health My Data Act defines "biometric data" with a
  **dual requirement**: it must both derive from
  physiological/biological/behavioral measurement **and** be capable of
  identifying a consumer — not any facial, voice, or behavioral data
  collection automatically qualifies.

**Raw leads, NOT independently verified — confirm before relying on
these:**
- BIPA Section 15(a) retention-schedule requirement (3-year outer bound)
  and Section 15(b) written-consent requirement.
- Section 20 statutory damages ($1,000 negligent / $5,000 intentional) and
  private right of action.
- *Cothron v. White Castle Systems* (Ill. Supreme Court, 2023) holding on
  per-scan claim accrual, and the August 2024 SB 2979 amendment
  purportedly limiting recovery to one instance per person.
- A purported 2026 Seventh Circuit decision (*Clay v. Union Pacific
  Railroad Co.*) on retroactive application of the SB 2979 amendment —
  **this is a recent, high-stakes claim that absolutely must be verified
  directly against the actual opinion before being relied on for anything.**
- Settlement figures (Facebook/Meta $650M; Six Flags $36M) — plausible
  and consistent with public reporting on BIPA generally, but not
  independently re-verified in this research pass.
- Texas CUBI's AG-only enforcement (no private right of action) — highly
  plausible given CUBI's well-documented structure, but not re-verified
  here.

**Practical recommendation:** given BIPA's history of nine-figure
settlements and active litigation, **do not treat this section as
compliance-ready.** Commission a focused legal memo on BIPA/CUBI/MHMDA
applicability to your specific facial-expression/gaze/voice pipeline
before any commercial launch touching Illinois, Texas, or Washington
residents.

### 6.4 Human subjects research ethics (US Common Rule)

Video/audio recording of identifiable participants generally does **not**
qualify for exempt review under 45 CFR 46, because participants are
identifiable — confirmed, though the specific exemption-category analysis
(which of 46.104(d)(1)-(8) might still partially apply) needs a full
listing from your IRB directly rather than this report. Informed-consent
elements (45 CFR 46.116) must address retention period and secondary-
use/data-sharing disclosure explicitly for video/audio/biometric capture.
Documentation of informed consent **can be waived** for remote/online
studies under 45 CFR 46.117 in appropriate circumstances — relevant to a
no-signature browser consent flow.

**De-identification is harder than it looks for this data class.** Face
video resists simple de-identification — blurring alone doesn't remove
gait, body, and voice cues that remain identifying. Voice is *itself* a
biometric identifier resistant to simple anonymization (pitch-shifting
doesn't reliably defeat voiceprint-based re-identification). **Design
implication:** don't market "anonymized" video/audio exports without a
specific, tested de-identification pipeline — the honest default is that
raw face/voice recordings are identifiable data requiring the same
protections as any other directly identifying record.

### 6.5 Privacy-preserving architecture

**Data-minimization principle** (synthesis, not found as explicit
regulator guidance in this research — this remains an open item, not a
confirmed recommendation from a DPA/EDPB/ICO/NIST source): process on-
device/in-browser where feasible, transmit only derived feature vectors
rather than raw video/audio. This reduces the surface area for GDPR
special-category and BIPA biometric-identifier exposure, at the cost of
losing raw data for quality control, re-analysis, and reproducibility —
**a real tradeoff, not a free win.** Consider a tiered architecture: raw
video processed and discarded within the session by default, with an
explicit, separately-consented opt-in for raw-video retention where
research reproducibility genuinely requires it.

**Retention schedule**: no published guidance reconciling BIPA's ≤3-year
outer bound with GDPR's "no longer than necessary" standard was found.
Practical default (synthesis): set your retention policy to the *shorter*
of (a) your specific research justification's actual need, (b) 3 years,
and document the justification explicitly — this satisfies BIPA's hard
cap and GDPR's necessity test simultaneously, even without a citable
precedent for the approach.

---

## 7. Open questions and recommended next research

In priority order for a build team:

1. **BIPA/CUBI/MHMDA legal detail (§6.3)** — commission a direct legal
   memo; this project's research infrastructure hit a hard limit three
   times on this specific topic.
2. **Camera-based respiration accuracy vs. gold standard** — no verified
   breaths-per-minute figure exists after two research passes; this needs
   either a dedicated literature deep-dive with different search terms, or
   your own validation study, before you can make any accuracy claim.
3. **Heatmap generation mechanics** (kernel bandwidth, weighting,
   normalization) and **epoching/baseline-correction operational detail**
   — both explicitly researched, both came back empty; consult the named
   canonical papers (Maris & Oostenveld 2007, van Rij et al. 2019, Mirman
   et al. 2008) directly.
4. **Demographic bias in facial expression, eye tracking, and voice**
   (beyond the confirmed rPPG skin-tone finding) — searched for twice,
   found nothing that survived verification. Budget an internal fairness
   audit rather than relying on the literature to have already answered
   this.
5. **EU AI Act Annex III classification** for your specific non-workplace
   research use case, and **GDPR Art. 35 DPIA** applicability — both
   need direct counsel review, not further literature research.
6. **WebCodecs/MediaStreamTrack frame-timestamp semantics** and
   **AudioContext clock drift over a session** — these are answerable by
   direct spec-reading and empirical measurement against current browser
   versions, faster than further literature search.

---

## Appendix: source index

Full findings, quotes, vote counts, and source URLs for every claim in
this report are in `research/`:

- `pass1-imotions-teardown-gaze-validation.md` — §1, §2.1
- `pass2-facial-au-voice-validation.md` — §2.2, §2.3
- `pass3a-physiology-bias.md` — §2.4, §2.5
- `pass3b-analysis-pipeline.md` — §4.1, §4.2, §4.3
- `pass3c-study-design-participants.md` — §5.1, §5.2
- `pass4a-browser-timing-sync.md` — §3.3
- `pass4b-data-quality-power-stats.md` — §4.4, §5.3, §5.4
- `pass4c-legal-retry-aiact-commonrule.md` — §6.1, §6.4
- `pass4d-bipa-cubi-INCOMPLETE.md` — §6.3 (⚠️ largely unverified)
- `README.md` — full status table and permanent-gap list

*Report drafted 2026-09-21 from 10 deep-research passes run 2026-09-20/21.
All figures should be re-baselined before use in anything client-facing —
the webcam-sensing literature moves quickly, and several sources cited
here are themselves 2024-2026 vintage measuring 2018-2023 vintage tools.*
