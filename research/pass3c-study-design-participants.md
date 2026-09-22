# Pass 3c: Study Design & Running Participants

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection with participants at home on their own hardware; modalities: webcam eye tracking, facial expression analysis, voice analysis, camera-based respiration). Other passes cover validation accuracy, the analysis pipeline, and legal compliance. Research ONLY STUDY DESIGN AND RUNNING PARTICIPANTS. Prefer peer-reviewed methods papers, published protocols, preregistrations and authoritative platform documentation.

TOPIC A — CALIBRATION, VALIDATION AND DRIFT. Calibration protocols for webcam/appearance-based gaze estimation: number and spatial layout of calibration points, target presentation duration, click-based versus fixation-based calibration, the WebGazer click-and-cursor-movement self-calibration approach and its limitations. Validation trials: how to measure and report calibration quality mid-study, and published validation-trial designs. Drift over a session and drift correction strategies, re-calibration triggers and cadence, and the cost in participant time and attrition. Also cover screen-size and viewing-distance estimation without hardware — the credit-card/known-object resizing method and blind-spot mapping used by jsPsych, Gorilla and Li, Joo, Yeatman & Reinecke's "Virtual Chinrest" (Scientific Reports 2020) — and how accurately viewing distance can actually be recovered, since degrees of visual angle depend on it.

TOPIC B — PARTICIPANT ENVIRONMENT AND INSTRUCTIONS. Which participant-side instructions measurably improve webcam data quality: ambient and frontal lighting, avoiding backlighting/windows, camera height and framing, viewing distance, head stability without a chinrest, removing glasses or not, closing other applications and browser tabs, using a laptop on a stable surface, disabling battery-saver and low-power modes, wired versus wireless network. Device and browser requirements and exclusions. Evidence on how much each instruction actually helps versus being folklore. Also cover audio-side setup for voice capture: microphone type, room acoustics, and whether to disable browser automatic gain control, noise suppression and echo cancellation in getUserMedia constraints for research-grade audio.

TOPIC C — DATA-QUALITY SCREENING AND EXCLUSION CRITERIA. Concrete published thresholds used to include or exclude participants and trials in online eye-tracking and webcam studies: maximum calibration/validation error, minimum effective sampling rate (fps), maximum track-loss or data-loss percentage, minimum face-detection rate, proportion of samples on-screen, and per-trial quality flags. How to preregister these thresholds and the argument for a priori versus post hoc exclusion. Reporting standards for eye-tracking data quality (e.g. the Holmqvist et al. data-quality reporting guidelines, and any eye-tracking reporting checklists). Also: fraud, bot and inattentive-responder detection in online samples — attention checks, instructional manipulation checks, catch trials, response-time floors, duplicate-IP and VPN detection, and the documented prevalence of bots and low-effort responders.

TOPIC D — SAMPLE SIZE, POWER AND EXPERIMENTAL DESIGN. Power analysis for within-subject and mixed designs with time-series outcomes; simulation-based power analysis for mixed-effects models (e.g. the simr package and equivalents) since closed-form power is usually unavailable for this data class. How to inflate sample size for measurement error and the documented 20-30% effect-size attenuation seen when moving from infrared to webcam eye tracking, and for expected attrition. Trial counts and reliability — how many trials per condition are needed for stable individual-level gaze and expression estimates. Counterbalancing and randomization schemes (Latin squares, block randomization, randomizing stimulus order and AOI positions to control side bias) and their implementation in online experiment runners.

TOPIC E — RECRUITMENT, ATTRITION AND PANEL QUALITY. Documented attrition and dropout rates in online behavioral and webcam studies specifically, including the additional dropout caused by requiring camera permission, calibration, and long sessions; how to budget over-recruitment. Comparative data quality across participant sources — Prolific, MTurk, CloudResearch, university pools, and commercial market-research panels — drawing on the published comparisons of data quality across platforms. Consent-rate and permission-grant rates for webcam access. Compensation, dropout mid-session, partial-data handling, and the ethics of paying participants whose data is later excluded for quality reasons.

---

## Summary

This pass returned solid, primary-sourced answers for only part of TOPIC A (calibration, validation, drift, and hardware-free screen/distance geometry) plus one fragment each of TOPIC B (participant-side setup guidance) and audio capture constraints; TOPICS C, D and E (exclusion thresholds and reporting standards, power/sample size, recruitment and attrition) returned essentially nothing and must be re-run. What is well established: remote participants' viewing distances vary enough (mean 47.3 cm, sd 8.9 cm, range 17.4-68.3 cm, n=1153) that degrees of visual angle cannot be assumed, and the hardware-free remedy — credit-card resizing for pixel scale plus blind-spot mapping for distance, shipping as jsPsych's virtual-chinrest plugin v3.1.0 — recovers distance to roughly 2.4-5.5 cm mean absolute error, leaving an irreducible ~11% error in computed stimulus size even with the best method, at a real cost: 66% of participants were excluded in one published deployment of these procedures. For gaze itself, a vendor-authored in-lab study puts a good webcam system at ~1.45 deg accuracy vs 0.91 deg for an EyeLink (a ~0.5 deg penalty, not an order of magnitude), but only with an external camera, a ~5-minute ~120-point calibration, a virtual chinrest, glasses-wearers excluded, a 7%-of-screen calibration-error gate with forced retry, and seven-point drift-correcting re-calibration every 1-7 trials — none of which transfers unexamined to unsupervised at-home participants. jsPsych supplies the concrete implementable defaults (9-point 10/50/90 grid, click vs. view calibration modes, and a validate trial emitting percent-in-ROI, average/median offset and samples-per-second) but publishes no pass/fail threshold, so every inclusion criterion remains the researcher's to preregister.

## Findings

### 1. [3-0] (confidence: high)

**Claim:** Viewing distance in uncontrolled online samples varies enough that degrees of visual angle cannot be assumed from a nominal distance, so a per-participant distance estimate is mandatory rather than optional.

**Evidence:** Li, Joo, Yeatman & Reinecke (Sci Rep 2020) measured n=1153 online participants: 'Our participants' viewing distances were between 17.4 cm and 68.3 cm with mean = 47.3 cm and sd = 8.9 cm.' The ~9 cm sd (~±19% of the mean) is the operationally important number; the near-fourfold span is tail-driven and the extreme low values (17.4 cm) plausibly include measurement error or non-compliant responders. Sample was LabintheWild (unpaid volunteers), so generalisation to Prolific/MTurk panels is inference, though nothing contradicts it.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/


### 2. [3-0] (confidence: high)

**Claim:** Hardware-free viewing-distance recovery (blind-spot / virtual chinrest) achieves roughly 2.4-5.5 cm mean absolute error and beats self-report proxies, but the residual leaves ~11-18% error in computed degrees of visual angle.

**Evidence:** Two independent primary papers converge. Li et al. 2020 (lab validation): 53.0 ± 0.69 cm estimated against a 53.0 cm chinrest with 2.36 cm mean absolute error (n=19); 3.25 cm MAE (sd 2.40) across three seating distances × two displays (n=12). Brascamp 2021 (online, Prolific): blind-spot method 5.5 cm MAE vs 8.9 cm for body-height regression with natural positioning and 7.6 cm for height + arm's-length instruction. Crucially, Brascamp also reports the end-to-end consequence in angular terms — 'average absolute errors are 0.18 dva (height and natural), 0.14 dva (height and arm's length), and 0.11 dva (blind spot and natural)', which the paper itself glosses as 0.11-0.18 times the intended stimulus size. Three qualifications: (a) the Li et al. figures are lab numbers and should not be assumed to hold for unsupervised at-home participants; (b) Brascamp's 5.5 cm is error against participants' self-measured distance, not experimenter ground truth; (c) the 11-18% dva error combines distance error AND card-based screen-size error, so it is total hardware-free size-control error, and it is a post-exclusion best case.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/ | https://pmc.ncbi.nlm.nih.gov/articles/PMC8383908/


### 3. [3-0] (confidence: high)

**Claim:** The distance estimate rests on a fixed group-level anatomical constant — the blind spot assumed at 13.5 degrees temporally — not measured per participant, which is the identified source of the residual error.

**Evidence:** jsPsych docs: participants 'focus on a black square on the screen with their right eye closed, while a red dot repeatedly sweeps from right to left'; the plugin uses the square-to-dot distance at disappearance and 'This estimation assumes that the blind spot is located at 13.5° temporally.' The primary paper confirms 13.5° was chosen because the method captures the blind-spot entry point (not centre) and because preliminary calibration on a few participants gave the most accurate results. Measured entry-point eccentricity across participants ranged 11.53°-16.01° (mean 13.59°, SD 0.96°), and the authors attribute minor distance-estimation inaccuracy to exactly this individual variation. So the constant is group-calibrated and end-to-end validated, not arbitrary — describe it as 'not measured per participant' rather than 'unvalidated'. Error propagates roughly proportionally: a ~7% distance error yields ~7% error in computed dva for small angles.

**Sources:** https://www.jspsych.org/latest/plugins/virtual-chinrest/ | https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/


### 4. [3-0] (confidence: high)

**Claim:** Screen-geometry and distance-estimation procedures carry a large participant-exclusion cost, but most of it is avoidable input-validation failure rather than an intrinsic cost of the method.

**Evidence:** Brascamp 2021 Experiment 2: 266 of 403 Prolific participants (66%) discarded — blind-spot criterion alone 78, incorrectly reported line length 56, implausible body height 21, multiple criteria 111. Experiment 1 independently lost 207/454 (46%), so the magnitude is not a one-off. Two of the four exclusion reasons are form-validation failures the author says can be designed away (he recommends programming experiments to accept only plausible height values and proposes a tiered approach to reduce data loss); the blind-spot criterion as sole cause was 78/403 = 19%. The blind-spot criterion here was a study-specific repeat-consistency check, not a universal standard. These are post-hoc data-quality exclusions in a methods paper, NOT dropout/attrition — do not cite this as an attrition or permission-grant rate.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8383908/


### 5. [3-0] (confidence: high)

**Claim:** Screen-geometry recovery is an off-the-shelf, citable component: jsPsych ships a maintained virtual-chinrest plugin (v3.1.0) implementing the published method, with credit-card resizing (ISO/IEC 7810 ID-1 defaults, 85.6 × 53.98 mm) for pixel scale and blind-spot mapping for distance.

**Evidence:** Official plugin docs state the plugin 'provides a virtual chinrest that can measure the distance between the participant and the screen', credit Li, Joo, Yeatman & Reinecke (2020) and recommend citing it. Parameter table: item_width_mm default 85.6, item_height_mm default 53.98 (matching credit-card ID-1 dimensions); on-screen instruction is 'Click and drag the lower right corner of the image until it is the same size as a credit card held up to the screen' with a ruler fallback (3.37 in / 85.6 mm). Outputs px2mm, scale_factor, and view_dist_mm / win_width_deg / win_height_deg when blindspot_reps > 0. npm registry independently confirms dist-tags.latest = 3.1.0, published 2025-01-07 — a real maintained package. Two caveats: 'no hardware' is loose (a physical card is required), and scale_factor is only meaningful when resize_units is set away from its default of 'none'. A non-jsPsych platform must still port the MIT-licensed code.

**Sources:** https://www.jspsych.org/latest/plugins/virtual-chinrest/


### 6. [3-0] (confidence: high)

**Claim:** jsPsych/WebGazer's stock calibration defaults are a 9-point grid at 10/50/90 percent of screen width and height, presented in fixed order, one repetition per point, click-based by default — and click vs. passive fixation is a selectable parameter, not a fixed property of WebGazer.

**Evidence:** webgazer-calibrate parameter table: calibration_points default [[10,10],[10,50],[10,90],[50,10],[50,50],[50,90],[90,10],[90,50],[90,90]]; calibration_mode default 'click' with 'view' as the alternative; repetitions_per_point default 1; randomize_calibration_order default false; time_to_saccade 1000 ms and time_per_point 1000 ms (both applying ONLY in 'view' mode — in click mode 'the point will remain on the screen until clicked'). Plugin source (next_calibration_round()) shuffles only if randomize_calibration_order is true, confirming fixed order is the runtime default, not just a documented flag. IMPORTANT CITATION FIX: two of the three verified claims in this group were cited to the webgazer-VALIDATE page, which contains none of these parameters; the correct source is the webgazer-CALIBRATE page. Nuance on the second half: WebGazer's native self-calibration is intrinsically click/cursor-driven; jsPsych's 'view' mode still trains WebGazer through the same screen-position API by supplying an assumed fixation coordinate after time_to_saccade. So the mode choice is a jsPsych-layer design decision, not native WebGazer fixation regression.

**Sources:** https://www.jspsych.org/latest/plugins/webgazer-calibrate/ | https://www.jspsych.org/latest/overview/eye-tracking/


### 7. [3-0] (confidence: high)

**Claim:** jsPsych supplies a concrete mid-study validation recipe with four logged quality metrics but publishes no pass/fail threshold, leaving the inclusion criterion entirely to the researcher.

**Evidence:** The webgazer-validate plugin outputs raw_gaze (per point), percent_in_roi (per point, tolerance set by roi_radius, default 200 px), average_offset (per point: average x and y distance from the point, plus median distance r of samples from that average offset — note r is from the average offset, not from the target), and samples_per_sec (a single scalar, the mean of per-point rates, NOT per point). Defaults: 9-point 10/50/90 grid, validation_duration 2000 ms, time_to_saccade 1000 ms. The plugin page documents no benchmark, cutoff or interpretation guidance. The overview page recommends 'performing calibration and validation periodically throughout your experiment' and its worked example fires a recalibrate timeline when validation_data.percent_in_roi.some(x => x < 50) — but that 50% is an illustrative value a researcher sets, which reinforces rather than contradicts the 'no published threshold' point. Note the adversarial pass explicitly REFUTED the stronger framing of that 50%/200px loop as 'jsPsych's canonical a priori recalibration threshold' — do not cite it as a standard.

**Sources:** https://www.jspsych.org/latest/plugins/webgazer-validate/ | https://www.jspsych.org/latest/overview/eye-tracking/


### 8. [3-0] (confidence: medium)

**Claim:** A well-engineered webcam eye tracker can come within ~0.5 deg of an infrared EyeLink 1000 (1.45 vs 0.91 deg accuracy) — but only under boundary conditions no at-home remote platform can reproduce, and the evaluation was authored by the platform's vendor.

**Evidence:** Kaduk, Goeke, Finger & König (Behavior Research Methods, 2023/24), simultaneous same-subject recording, 23 recruited / 19 analysed: webcam overall accuracy 1.4 deg (Large Grid M = 1.45, SD 0.76), precision 1.1 deg per abstract (Results grand mean is actually 1.23), vs EyeLink 0.91 deg (SD 0.54) accuracy and 1.02 deg precision. Confidence is medium, not high, because: (a) three of four authors are employees of Scicovery, which develops the Labvanced platform under test — disclosed, peer-reviewed, but a developer-run evaluation of its own product; (b) boundary conditions are far from at-home — external Logitech StreamCam, virtual chinrest at medium-strict sensitivity, ~5-minute ~120-point calibration, controlled lab lighting, screen-size error threshold <7%; (c) spectacle wearers were EXCLUDED outright, which is impossible in a general online panel; (d) n=19 and the authors note the sampling rate is unsuitable for microsaccades. This is NOT evidence that ~1.4 deg is achievable for participants at home on their own hardware. Separately, the adversarial pass refuted the specific characterisation of the ~120-point/7-head-pose calibration as a standalone claim, so describe the calibration burden cautiously.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11289017/


### 9. [3-0] (confidence: medium)

**Claim:** That study's operational quality controls give two transferable protocol patterns: an up-front calibration-error gate with forced retry (error < 7% of total screen size), and frequent task-specific in-session re-calibration with an explicit drift-correction computation.

**Evidence:** Gate: 'Only subjects with a calibration error of less than 7% of the total screen size were allowed to continue in the experiment. In case of a failure, the subject was informed that the calibration accuracy was insufficient and the calibration had to be repeated.' This is a gate-with-retry, not an exclusion rule — nobody was necessarily dropped by it (the one reported exclusion was on a different criterion: fewer than 20% of target offset-related fixations detected). Drift: 'we choose to recalibrate seven points after every six trials in the Large Grid, every trial for the Smooth Pursuit Task, and every seven trials for Free View', and 'This drift correction feature calculated the cross-validated systematic error across those seven points and subsequently accounted for this in future gaze predictions.' Cost is quantified: recalibrations 'take around 15 s, adding an additional 4 min to the total time of the experiment'. Three limits on transfer: 7%-of-screen-size is a Labvanced-internal metric, not degrees, and cannot be ported without conversion (the same paper's EyeLink criteria were average error < 1.0 deg, max < 1.5 deg); the setting was a supervised lab, so the pass rate should not be assumed at home; and the seven-point cross-validated drift correction is Labvanced-specific — WebGazer has no equivalent. 'A priori' here means fixed in the procedure, not preregistered.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11289017/


### 10. [3-0] (confidence: medium)

**Claim:** The only participant-environment guidance recovered is the jsPsych maintainers' own list — camera feed quality, good lighting, head stillness (calibration is explicitly not robust to head movement), and device compute load — and the documentation itself labels these anecdotal, so TOPIC B's 'evidence vs folklore' question is essentially unanswered.

**Evidence:** The Tips for Improving Data Quality section states 'The quality of the camera feed is essential. Good lighting makes a big difference', advises a well-lit room, states 'Participants need to keep their head relatively still during and after calibration. The calibration is not robust to head movements', notes gaze prediction 'consumes more computational resources than most other things that jsPsych is typically used for' with advice to close unnecessary applications and check sampling rate during validation, and recommends continuous click-based self-calibration by moving the continue button around the screen (jsPsych.extensions.webgazer.startMouseCalibration()). Confidence is capped at medium because the page prefaces the list with 'These are some anecdotal observations about factors that improve data quality' and solicits community additions — these are maintainer heuristics, not measured effect sizes. Head-stillness and lighting are independently corroborated in the webcam gaze literature; the click-and-cursor self-calibration recommendation is the weakest item and is qualified elsewhere. Nothing was recovered on backlighting, camera height, glasses, battery-saver modes, wired vs wireless, or device/browser exclusions.

**Sources:** https://www.jspsych.org/latest/overview/eye-tracking/


### 11. [3-0] (confidence: high)

**Claim:** For voice capture, a platform can programmatically detect whether a participant's device permits disabling browser DSP: echoCancellation, noiseSuppression and autoGainControl are constrainable audio properties whose supported values a live track reports via getCapabilities().

**Evidence:** MDN's Constraints page shows an example capabilities object containing autoGainControl: [true, false], echoCancellation: [true, false], noiseSuppression: [true, false] and states you call MediaStreamTrack.getCapabilities() to get supported capabilities and their values. The getCapabilities page independently documents the same three and repeats the [true,false] output. Four caveats that matter operationally: (1) constraints are best-effort — MDN says the UA 'will attempt to obtain media with echo cancellation enabled or disabled as specified, if possible, but will not fail if this can't be done', so a [true,false] capability report is not a guarantee the DSP is genuinely bypassed (OS/driver processing can persist); verify empirically. (2) echoCancellation is ConstrainBooleanOrDOMString (values can include 'all'/'remote-only'), so 'boolean' is slightly loose. (3) getCapabilities only reached cross-browser Baseline in October 2024, so older participant browsers need a feature-detect fallback. (4) It requires a live track, so the query happens after mic permission but before recording. Nothing was recovered on microphone type, room acoustics, or whether disabling these stages actually improves research-grade voice features.

**Sources:** https://developer.mozilla.org/en-US/docs/Web/API/Media_Capture_and_Streams_API/Constraints | https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities

## Refuted claims (do not use)

1. {"claim":"The Virtual Chinrest estimates viewing distance without hardware by combining a credit-card resizing task (to get logical pixel density from a known 85.60 mm object) with a blind-spot mapping task that exploits the blind spot's consistent ~15 degree horizontal eccentricity, computing distance as d = s / tan(15 degrees).","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/"}
2. {"claim":"Viewing distance drifts within a single online session: across three repeated blind-spot tests, the average within-subject standard deviation of estimated viewing distance was 3.9 cm, with individual participants ranging up to 22.7 cm, implying repeated distance measurement rather than a single up-front calibration.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/"}
3. {"claim":"The credit-card/known-object resizing method for screen scaling is highly reliable for pixel geometry: 345 of 353 participants (97.7%) who completed the card procedure produced a vertical/horizontal pixel aspect ratio within 0.95-1.05.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8383908/"}
4. {"claim":"Their webcam calibration protocol was substantially heavier than typical online 5-9-point routines: a default 5-minute procedure comprising seven distinct head poses with approximately 12 targets each (~120 calibration points), plus smooth-pursuit and head-movement components.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11289017/"}
5. {"claim":"The calibration plugin itself records no data, so calibration quality must be measured with a separate webgazer-validate trial — making a validation trial a required, separate step in a jsPsych webcam eye-tracking protocol.","vote":"0-3","source":"https://www.jspsych.org/latest/plugins/webgazer-validate/"}
6. {"claim":"jsPsych's reference webcam eye-tracking protocol uses a 5-point click-based calibration grid at [[25,25],[75,25],[50,50],[25,75],[75,75]] (percent of screen width/height) with 2 repetitions per point, i.e. 10 calibration clicks total — a concrete, implementable default layout for browser-based gaze calibration.","vote":"0-3","source":"https://www.jspsych.org/latest/overview/eye-tracking/"}
7. {"claim":"jsPsych's canonical drift/recalibration trigger is a conditional loop that re-runs calibration whenever any validation point has fewer than 50% of samples inside the 200 px ROI — a published, concrete a priori recalibration threshold.","vote":"0-3","source":"https://www.jspsych.org/latest/overview/eye-tracking/"}

## Open questions

1. What are the real-world figures for the questions that returned nothing — camera-permission grant rate, calibration-stage dropout, and total attrition in unsupervised at-home webcam studies — and how much over-recruitment do published studies actually budget? This is the single biggest gap and it directly determines project feasibility and cost.
2. Does the claimed 20-30% effect-size attenuation from infrared to webcam eye tracking have a primary source, and what is the correct procedure for inflating sample size for measurement error in mixed-effects designs with time-series outcomes (simulation-based power via simr or equivalents)? Nothing in this pass touched power, trial counts for stable individual-level estimates, or counterbalancing.
3. What quantitative exclusion thresholds do published online eye-tracking studies actually preregister — minimum effective fps, maximum track-loss, minimum face-detection rate, proportion of samples on-screen — and what do the Holmqvist et al. data-quality reporting guidelines specify for reporting them? Only two study-specific gates were recovered, both non-portable.
4. Which participant-side instructions have measured effects on webcam data quality rather than anecdotal endorsement, and does disabling echoCancellation/noiseSuppression/autoGainControl measurably improve research-grade voice features — or does OS/driver-level processing persist regardless, making the constraint a false reassurance?
5. How much does virtual-chinrest distance recovery degrade from the 2.4-5.5 cm lab/screened figures under genuinely unsupervised at-home conditions without the strict blind-spot consistency exclusions, given that Brascamp states dropping those exclusions would increase error and that 66% of his sample was discarded?

## Caveats

COVERAGE IS THE BIGGEST PROBLEM. Of five topics, only TOPIC A is meaningfully covered. TOPIC B returned one anecdotal maintainer list plus one API fact — nothing on backlighting, camera height/framing, glasses, closing tabs, battery-saver, wired vs wireless, device/browser exclusions, microphone type or room acoustics, and no effect-size evidence separating instruction from folklore. TOPIC C returned no published exclusion thresholds beyond two study-specific ones (7% of screen size; <20% detected offset fixations), NOTHING on minimum fps, track-loss percentage, face-detection rate, the Holmqvist et al. data-quality reporting guidelines, eye-tracking reporting checklists, or bot/inattentive-responder prevalence and detection. TOPIC D (power analysis, simulation-based power for mixed models, simr, the 20-30% webcam effect-size attenuation, trial counts for reliable individual estimates, counterbalancing schemes) returned ZERO claims. TOPIC E (attrition, camera-permission grant rates, Prolific/MTurk/CloudResearch quality comparisons, compensation ethics for excluded data) returned ZERO claims. Do not let the density of TOPIC A findings disguise this; these topics need a re-run.

PROCESS WEAKNESS. Every verifier reported the session's WebSearch budget exhausted (200/200), so no adversarial search for contradicting literature was performed on ANY claim. All verification rests on direct primary-source reading. That is strong for 'what does this document say' claims (jsPsych defaults, MDN APIs, what one study did) and weaker for empirical generalisations (distance recovery accuracy, exclusion rates) where a replication reporting worse performance could exist unseen.

CITATION ERRORS TO FIX BEFORE PUBLICATION. Claims about calibration_points, calibration_mode, repetitions_per_point, randomize_calibration_order, time_per_point and time_to_saccade were cited to https://www.jspsych.org/latest/plugins/webgazer-validate/, which contains none of them. The correct URL is https://www.jspsych.org/latest/plugins/webgazer-calibrate/. Separately, the 5.5 cm blind-spot figure is Brascamp (2021), NOT Li, Joo, Yeatman & Reinecke (2020) — the '(virtual chinrest)' parenthetical in the source claim invites misattribution.

SOURCE-INDEPENDENCE WEAKNESS. Eleven of eighteen claims come from just four sources, and the two most load-bearing gaze-performance claims (accuracy vs EyeLink; the 7% gate and drift cadence) come from a single vendor-authored paper. Two sources are software documentation, which is authoritative for 'what the tool does' but carries no validity evidence.

SCALE AND UNIT CONFUSIONS TO AVOID. Do not mix Brascamp's cm distance errors with his dva stimulus-extent errors. Do not read Li et al.'s '53.0 ± 0.69 cm' as per-participant spread — 0.69 is SEM; the operational number is the 2.36 cm MAE. Do not port Labvanced's '7% of total screen size' into degrees without conversion. Note samples_per_sec is a single scalar, not per validation point.

TIME SENSITIVITY. Software facts (jsPsych plugin versions and defaults, MDN Baseline status of getCapabilities) were verified 2026-09-20 and will drift; re-verify before implementation. The measurement papers (2020, 2021, 2023/24) are stable, but webcam gaze estimation is an actively moving field and the infrared-vs-webcam gap figure specifically should be re-checked.

SEVEN CLAIMS WERE REFUTED, including two that would have been directly useful: a within-session viewing-distance drift figure (3.9 cm average within-subject SD across three repeated blind-spot tests) and a canonical jsPsych recalibration trigger. Treat both as unsupported. Note the surviving literature still recommends repeated within-session distance measurement (Brascamp, on postural-change grounds), but the specific drift magnitude did not survive verification.

## All sources

- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC6976612/","quality":"primary","angle":"Academic methods — calibration, drift and screen geometry","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8383908/","quality":"primary","angle":"Academic methods — calibration, drift and screen geometry","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11289017/","quality":"primary","angle":"Academic methods — calibration, drift and screen geometry","claimCount":5}
- {"url":"https://www.jspsych.org/latest/plugins/virtual-chinrest/","quality":"primary","angle":"Academic methods — calibration, drift and screen geometry","claimCount":5}
- {"url":"https://www.jspsych.org/latest/plugins/webgazer-validate/","quality":"primary","angle":"Academic methods — calibration, drift and screen geometry","claimCount":5}
- {"url":"https://www.jspsych.org/latest/overview/eye-tracking/","quality":"primary","angle":"Practitioner/implementation — participant setup and capture constraints","claimCount":5}
- {"url":"https://developer.mozilla.org/en-US/docs/Web/API/Media_Capture_and_Streams_API/Constraints","quality":"primary","angle":"Practitioner/implementation — participant setup and capture constraints","claimCount":5}
- {"url":"https://www.w3.org/TR/mediacapture-streams/","quality":"primary","angle":"Practitioner/implementation — participant setup and capture constraints","claimCount":5}
- {"url":"https://ling.auf.net/lingbuzz/005748","quality":"primary","angle":"Practitioner/implementation — participant setup and capture constraints","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11225961/","quality":"primary","angle":"Reporting standards and screening thresholds","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11133053/","quality":"primary","angle":"Reporting standards and screening thresholds","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC10841511/","quality":"primary","angle":"Reporting standards and screening thresholds","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC10794474/","quality":"primary","angle":"Reporting standards and screening thresholds","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8480459/","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":5}
- {"url":"https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0279720","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11170515/","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC12396152/","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":5}
- {"url":"https://doi.org/10.1177/17456916221120027","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":4}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC10700412/","quality":"primary","angle":"Contrarian/skeptical — bots, fraud and panel quality","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11289066/","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8329985/","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8613146/","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://www.journalofcognition.org/articles/10.5334/joc.10","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11627531/","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC12568607/","quality":"primary","angle":"Statistical design — power, trials and counterbalancing","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC10550147/","quality":"primary","angle":"Attrition, permission grant rates and recruitment budgeting","claimCount":5}
- {"url":"https://researcher-help.prolific.com/en/articles/445219-how-do-i-reject-or-return-a-submission","quality":"primary","angle":"Attrition, permission grant rates and recruitment budgeting","claimCount":5}
