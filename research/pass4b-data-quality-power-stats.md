# Pass 4b: Data-Quality Thresholds, Power/Attrition/Panel Quality, Epoching & Statistics (retry of 3b Topic E + 3c Topics C/D/E)

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection, participants at home). Prior passes already established: gaze metric definitions, viewing-distance/calibration geometry (virtual chinrest), jsPsych calibration defaults, and webcam gaze accuracy vs infrared. This pass covers what those passes failed to evidence — retry with narrower, more targeted scope than before. Prefer peer-reviewed methods papers, preregistrations, and published statistical/methodological guidance.

TOPIC A — DATA-QUALITY EXCLUSION THRESHOLDS. Find CONCRETE, CITABLE numeric thresholds actually used and published in online/webcam eye-tracking or behavioral studies to include or exclude participants or trials: maximum calibration/validation error (in px, % of screen, or degrees), minimum effective sampling rate in fps, maximum track-loss/data-loss percentage, minimum face-detection or gaze-detection rate, minimum proportion of samples on-screen. Search specifically within Methods/Participants sections of published online eye-tracking papers (e.g. search Google Scholar / PubMed for phrases like "excluded due to" "calibration error" "eye tracking" "online" or "webcam"), preregistrations on OSF, and any formal reporting-standard/checklist paper for eye-tracking data quality (Holmqvist et al.'s data-quality reporting recommendations, or a "COGA"/"minimal reporting standards for eye tracking" style paper). Report the actual numbers found and which specific paper used them, not generic advice.

TOPIC B — SAMPLE SIZE AND POWER FOR WEBCAM/ONLINE STUDIES. Any published power analysis, simulation-based power approach (e.g. the R `simr` package for mixed models), or explicit sample-size justification from an online or webcam eye-tracking/behavioral study. How researchers have inflated sample size to account for (a) webcam measurement error/attenuation relative to lab hardware and (b) anticipated attrition. Any published trial-count-per-condition reliability analysis for individual-level gaze or facial-expression estimates (e.g. split-half reliability, ICC as a function of number of trials).

TOPIC C — ATTRITION AND PANEL DATA QUALITY. Published dropout/attrition RATES (not just discussion) specifically for online studies requiring webcam/camera access, calibration, or eye tracking — cite actual percentages and the paper reporting them. Any published comparison of data quality (attention checks, careless-responding rates, bot prevalence) across Prolific vs MTurk vs CloudResearch vs other platforms — cite actual studies (e.g. Peer, Rothschild, Gordon, Evernden & Damer 2022 on Prolific; Chmielewski & Kucker 2020 on MTurk data quality decline; Douglas, Ewell & Brauer 2023) with their actual reported numbers.

TOPIC D — EPOCHING, BASELINE CORRECTION AND STATISTICAL METHODS FOR THIS DATA CLASS. How stimulus-event epoching and baseline correction are actually done for time-series gaze/pupillometry/physiological data in published methods — cite a concrete methods paper or textbook chapter with the actual procedure (e.g. pre-stimulus baseline window length, baseline correction formula — subtractive vs divisive). Cluster-based permutation testing for time-series eye-tracking or pupillometry data — cite the Maris & Oostenveld (2007) method and any eye-tracking-specific application paper. Growth curve analysis / GAMMs for time-course gaze data — cite Mirman's growth curve analysis work or a GAMM-for-eyetracking paper (e.g. van Rij, Hendriks, van Rijn, Baayen & Wood). The "keep it maximal" random-effects structure debate — cite Barr, Levy, Scheepers & Tily (2013) and its critique (Matuschek et al. 2017 or Bates et al.).

TOPIC E — DATA FORMATS AND EXPORT SCHEMA FOR MULTIMODAL BEHAVIORAL DATA. BIDS (Brain Imaging Data Structure) and any eye-tracking-specific BIDS extension proposal (search for "BIDS" "eye tracking" extension, or the "Eye Tracking BIDS Extension Proposal"/EEG-BIDS as an analogy). LSL's XDF file format structure. Any published or de facto standard for a canonical long-format event table / tidy data schema for multimodal behavioral/physiological time series (columns like participant_id, timestamp, stream, value, event). If no formal standard exists for this specific case, say so explicitly and instead report what adjacent standards (BIDS, XDF) actually specify structurally that a schema could borrow from.

If a specific numeric figure or named paper cannot be found, say so explicitly rather than omitting the topic.

---

## Summary

Across five topics, this pass found strong, citable numbers for Topics A–D but nothing for Topic E. Concrete data-quality thresholds exist: webcam gaze error runs 3–4.5° visual angle vs ~0.5° for infrared, a 5 Hz minimum sampling-rate cutoff has been published and applied (excluding 18/220 participants), and one large webcam eye-tracking study reported a full attrition funnel (253→202, ~20%, vs 73% in a prior study). Power/sample-size planning for webcam studies is evidenced by two independent published approaches: analytic inflation assuming a 50% online effect-size attenuation (18→63 participants) validated by an observed 52% [42%,62%] online/in-person effect-size ratio, and simulation-based mixed-model power analysis (mixedpower package and resampling) giving concrete N-vs-power curves. Platform data-quality comparisons are well evidenced (Peer et al. 2022; Chmielewski & Kucker 2020; a 5-platform PLOS ONE study), consistently ranking Prolific/CloudResearch above MTurk, Qualtrics, and Dynata, with exact attention-check pass rates and dropout percentages. Time-series statistical methods are anchored to named canonical papers (Maris & Oostenveld 2007 for cluster-based permutation testing, van Rij et al. 2019 for GAMM pupillometry with a specific 250 ms subtractive baseline, Mirman et al. 2008 for growth curve analysis), but Topic E (BIDS/XDF/tidy-format standards for multimodal behavioral data) and the Barr et al. 2013 "keep it maximal" random-effects debate returned no surviving evidence in this pass.

## Findings

### 1. [2-1] (confidence: high)

**Claim:** Webcam-based online eye tracking (e.g., WebGazer.js) has a spatial accuracy of ~3–4.5° visual angle, roughly 6–9x worse than in-lab infrared eye trackers (~0.5° visual angle) — a concrete numeric benchmark for setting calibration/accuracy-based exclusion thresholds in webcam studies.

**Evidence:** Verbatim from full text: 'WebGazer.js's spatial error is generally 3–4.5° of visual angle for online participants... In contrast, infrared systems achieve spatial accuracy on the order of 0.5° visual angle.' The paper's own empirical calibration data (RMS 4.8%/5.9% width/height, 3.3° Euclidean) independently corroborates the range. Vote 2-1.

**Sources:** https://www.semanticscholar.org/paper/e2d564584d282bd6a01a71fb9af9199e4455a021 (Bogdan, Dolcos, Buetti, Lleras & Dolcos, 2023, Behavior Research Methods)


### 2. [3-0] (confidence: high)

**Claim:** A published webcam eye-tracking study (Prystauka, Altmann & Rothman 2023) applied and reported a concrete minimum-sampling-rate exclusion threshold of 5 Hz (excluding 18 of 220 participants, with achieved sampling rate mean 19.7 Hz, SD 6.4, range 5.5–30.1 Hz) and a face-detection-confidence exclusion threshold of 0.5 (removing <0.1% of samples).

**Evidence:** Verbatim: 'We excluded participants with fewer than five samples per second, which resulted in the exclusion of 18 individuals'; 'Samples with values lower than 0.5 on the face_conf metric... were removed.' Vote 3-0.

**Sources:** https://link.springer.com/article/10.3758/s13428-023-02176-4 (Prystauka, Altmann & Rothman, 2023, Behavior Research Methods)


### 3. [3-0] (confidence: high)

**Claim:** The same webcam eye-tracking study reports a full, citable attrition funnel: of 253 initial participants, 26 failed calibration, 7 withdrew, and 18 were excluded for low sampling rate, yielding final N=202 (~20% overall attrition), explicitly contrasted with a 73% attrition rate reported in a prior online eye-tracking study (Slim & Hartsuiker, 2022).

**Evidence:** Verbatim: '253 subjects consented... 26 subjects did not pass the calibration stage and seven participants withdrew... The data from 18 more people were excluded due to the low sampling rate (<5 Hz)... 20% of participants failed to pass through to the analysis phase (cf. the 73% who failed in Slim & Hartsuiker, 2022).' Arithmetic verified (253-26-7-18=202). Vote 3-0.

**Sources:** https://link.springer.com/article/10.3758/s13428-023-02176-4 (Prystauka, Altmann & Rothman, 2023, Behavior Research Methods)


### 4. [2-1 / 3-0] (confidence: high)

**Claim:** Bogdan et al. (2023) explicitly inflated their online-sample power analysis to account for webcam measurement attenuation, assuming a 50% drop in effect size relative to in-person data (18 in-person → 63 online participants for the same effect at 80% power, α=.05), and this analytic inflation approach was empirically validated: aggregated across replicated effects, observed online effect sizes were only 52% [42%, 62%] the magnitude of in-person effect sizes.

**Evidence:** Verbatim: 'a minimum of 18 participants would be needed to identify emotion vs. neutral effects on in-person gaze, and 63 participants would be needed to identify online effects, assuming a 50% drop in effect size.' Abstract: 'the effect sizes were just 52% [42%, 62%] the size of those seen in-person.' Votes 2-1 and 3-0 respectively.

**Sources:** https://www.semanticscholar.org/paper/e2d564584d282bd6a01a71fb9af9199e4455a021 (Bogdan, Dolcos, Buetti, Lleras & Dolcos, 2023, Behavior Research Methods)


### 5. [3-0] (confidence: high)

**Claim:** Prystauka et al. (2023) directly compared two simulation/resampling-based power-analysis methods for online eye-tracking mixed-effects data: the mixedpower R package (1000 simulated datasets per sample size from a fitted lmer model) indicated 80% power at N=30 and N=170 for two effects; a resampling-with-replacement approach from their own large dataset indicated 80% power at N=20 and N=40 for the same two effects — giving concrete, citable N-vs-power figures for planning webcam eye-tracking sample sizes.

**Evidence:** Verbatim: mixedpower simulated 'new datasets... from 20 to 200 in increments of 10... 1000 times per every sample size,' giving 80% power at N=30 (verb constraint) and N=170 (lexical interference); resampling gave 80% power at N=20 and N=40 for the same effects. Vote 3-0.

**Sources:** https://link.springer.com/article/10.3758/s13428-023-02176-4 (Prystauka, Altmann & Rothman, 2023, Behavior Research Methods)


### 6. [3-0 (caveated)] (confidence: medium)

**Claim:** Simulation-based (Monte Carlo) power analysis for (G)LMMs — the general statistical approach underlying tools such as the R simr package — is formally defined as the proportion of repeated simulated experiments yielding a statistically significant result, per a peer-reviewed tutorial (Kumle, Võ & Draschkow, 2021).

**Evidence:** Quote: 'Suppose there really is an effect of a certain size and I run my experiment one hundred times - how many times will I get a statistically significant result?' Vote 3-0, but verifier flagged reliance on domain knowledge rather than a fresh fetch due to search-budget exhaustion. Note: a related claim that this specific paper works through both simr and mixedpower packages together, and a claim that its worked example concluded 180 subjects were needed, were both REFUTED (0-3 and 1-2 votes) and should not be cited.

**Sources:** https://doi.org/10.3758/s13428-020-01562-y (Kumle, Võ & Draschkow, 2021, Behavior Research Methods)


### 7. [3-0 (mostly)] (confidence: high)

**Claim:** Platform data-quality comparisons (Peer, Rothschild, Gordon, Evernden & Damer, 2022, and a related 5-platform PLOS ONE study) show consistent, large, citable differences: without data-quality filters, Prolific had the highest attention-check pass rate (68.7% passing both ACQs) vs. 46.6%/45.5% for MTurk-via-CloudResearch/raw MTurk and only 22.5%/22.1% for Qualtrics/Dynata; dropout rates were far higher on panel providers Qualtrics (20.6%) and Dynata (21.3%) than MTurk (11.5%), Prolific (2.5%), or MTurk-via-CloudResearch (0%) (χ²(4)=206.05, p<.001); MTurk showed 'alarmingly low' data quality even after standard approval-rating filters; in Study 1 (no filters), Prolific alone showed consistently high quality on all measures; and overall, Prolific and CloudResearch provided the highest-quality data at the lowest cost.

**Evidence:** Verbatim from Peer et al.: 'Prolific had the highest rate of passing ACQs with 68.7%... compared to 46.6% and 45.5% on MTurk(CR) and MTurk. Qualtrics and Dynata had the lowest... 22.5% and 22.1%'; 'Dropout rates differed significantly... χ2(4) = 206.05, p < .001'; 'MTurk exhibited alarmingly low data quality even with data quality filters'; 'only Prolific provided high data quality on all measures.' PLOS ONE study: 'Prolific and CloudResearch provided the highest quality data for the lowest cost'; SONA showed 17.92% partial-response attrition vs. 0% attrition on paid platforms. Votes 3-0 (x4) and 2-1/3-0 for the PLOS ONE claims.

**Sources:** https://doi.org/10.3758/s13428-021-01694-3 (Peer, Rothschild, Gordon, Evernden & Damer, 2022, Behavior Research Methods) | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0279720


### 8. [3-0 (caveated)] (confidence: medium)

**Claim:** MTurk data quality declined measurably around/after summer 2018: a four-wave study (Chmielewski & Kucker, 2020) found significant increases in participants failing response-validity indicators, decreased reliability/validity of a widely used personality measure, and failed replications of well-established findings during and after summer 2018 relative to before.

**Evidence:** Quote: 'During and to some extent post-summer 2018, we find significant increases in participants failing response validity indicators, decreases in reliability and validity of a widely used personality measure, and failures to replicate well-established findings.' Both sub-claims verified 3-0, but verifiers relied partly on domain knowledge/could not run a fresh WebSearch to independently re-confirm exact wording (search budget exhausted), hence medium rather than high confidence on the precision of secondary details.

**Sources:** https://doi.org/10.1177/1948550619875149 (Chmielewski & Kucker, 2020, Social Psychological and Personality Science)


### 9. [3-0] (confidence: high)

**Claim:** Cluster-based permutation testing — the standard method for controlling the multiple-comparisons problem in time-series EEG/MEG (and by extension eye-tracking/pupillometry) data — originates from Maris & Oostenveld (2007), whose method exploits nonparametric tests' freedom in choosing a test statistic to solve the multiple comparisons problem, formalized via a null hypothesis of identical probability distributions across conditions with proven Type I error control.

**Evidence:** Verbatim: 'Nonparametric statistical tests offer complete freedom to the user with respect to the test statistic... This freedom provides a straightforward way to solve the multiple comparisons problem (MCP)'; 'we formulate a null hypothesis (identical probability distribution in the different experimental conditions) and show that the nonparametric test controls the false alarm rate under this null hypothesis.' Both sub-claims verified 3-0, though one verifier noted reliance on strong prior knowledge rather than a fresh fetch due to search-budget exhaustion.

**Sources:** https://doi.org/10.1016/j.jneumeth.2007.03.024 (Maris & Oostenveld, 2007, Journal of Neuroscience Methods)


### 10. [2-1 / 3-0] (confidence: high)

**Claim:** For pupillometry time-course data, GAMMs (Generalized Additive Mixed Models) are recommended as the primary analysis method specifically because raw time-series analysis suffers from autocorrelated errors that inflate Type I error rates; the concrete published baseline-correction procedure is a 250 ms pre-trial window, averaged and subtracted (subtractive, not divisive, correction) from the raw pupil-dilation signal, explicitly to avoid distorting the dilation pattern.

**Evidence:** Verbatim: 'the direct analysis of time series... raises the problem of autocorrelated errors... Autocorrelated errors increase the probability of Type I errors'; 'The baseline was calculated as the average pupil dilation in the time window of 250 ms at the beginning of each trial... subtracted from the pupil dilation measures, but the pupil dilation was not divided by the baseline, to avoid changing the dilation pattern.' Votes 2-1 and 3-0.

**Sources:** https://doi.org/10.1177/2331216519832483 (van Rij, Hendriks, van Rijn, Baayen & Wood, 2019, Trends in Hearing)


### 11. [3-0] (confidence: high)

**Claim:** Growth Curve Analysis (GCA) — a multilevel/hierarchical regression technique explicitly designed to model change over time at both group and individual levels — was introduced for visual-world-paradigm eye-tracking fixation data by Mirman, Dixon & Magnuson (2008), specifically to address the prior lack of a statistically rigorous time-course analysis method in VWP research.

**Evidence:** Verbatim abstract: 'The statistical approach (growth curve analysis, a technique explicitly designed to assess change over time at group and individual levels) provides a rigorous means of analyzing time course data.' Vote 3-0.

**Sources:** https://doi.org/10.1016/j.jml.2007.11.006 (Mirman, Dixon & Magnuson, 2008, Journal of Memory and Language)


### 12. [n/a — no surviving claims] (confidence: low)

**Claim:** No confirmed evidence was found in this pass for Topic E (BIDS eye-tracking extension proposals, LSL/XDF file format structure, or a formal canonical long-format/tidy schema for multimodal behavioral time-series data). This is an explicit gap, not an absence-implies-no-standard conclusion.

**Evidence:** No claims addressing BIDS, an eye-tracking BIDS extension proposal, XDF/LSL file structure, or a canonical tidy-data schema appear among the 20 survived or even the refuted claims for this pass. The task instructions explicitly require stating this gap rather than omitting the topic.


### 13. [n/a — no surviving claims] (confidence: low)

**Claim:** The 'keep it maximal' random-effects structure debate (Barr, Levy, Scheepers & Tily, 2013, and its critiques by Matuschek et al. 2017 / Bates et al.) was not evidenced by any surviving claim in this pass, despite being explicitly requested.

**Evidence:** No claim in the confirmed or refuted lists cites Barr et al. 2013, Matuschek et al. 2017, or Bates et al. on random-effects structure. This is a gap requiring a follow-up targeted search.

## Refuted claims (do not use)

1. {"claim":"The study used explicit, published numeric participant-exclusion criteria for online eye-tracking data quality: Study 1 excluded 18 of 105 recruited online participants for responding to fewer than 75% of emotional trials, being extreme RT outliers (Z > 5), or having fewer than 75% usable/valid eye-tracking data.","vote":"0-3","source":"https://www.semanticscholar.org/paper/e2d564584d282bd6a01a71fb9af9199e4455a021"}
2. {"claim":"The study reports no numeric calibration/validation-error exclusion threshold, sampling-rate minimum, track-loss percentage cutoff, or face-detection-rate cutoff used to include/exclude participants or trials; the authors explicitly state they had no structured way to evaluate tracking-error quality at all, so no such thresholds were applied.","vote":"1-2","source":"https://www.semanticscholar.org/paper/0b421419f70beb827e6001dccf12fd76e794c322"}
3. {"claim":"The paper cites Webgazer's own validated lab accuracy figure as 4.17 degrees of visual angle (from Papoutsaki et al., 2016), explicitly contrasted with <1 degree for commercial/PCCR eye-trackers, and notes that because Webgazer runs client-side its sampling rate 'cannot be guaranteed and varies' - later stated elsewhere in the paper as approximately 30 Hz versus >60 Hz for research-grade PCCR trackers.","vote":"1-2","source":"https://www.semanticscholar.org/paper/0b421419f70beb827e6001dccf12fd76e794c322"}
4. {"claim":"The tutorial specifically recommends and works through two R packages for simulation-based power analysis of mixed-effects models: simr (Green & MacLeod, 2016) and mixedpower (Kumle et al., 2018).","vote":"1-2","source":"https://doi.org/10.3758/s13428-020-01562-y"}
5. {"claim":"In the paper's worked example (an eye-tracking reading study with an original design of 48 subjects x 120 sentences), simulation-based power analysis targeting 80% power for the weakest effect (native language) concluded that 180 subjects would be needed -- a concrete, citable sample-size-inflation figure derived from simulation rather than analytic formulas.","vote":"0-3","source":"https://doi.org/10.3758/s13428-020-01562-y"}

## Open questions

1. No formal BIDS eye-tracking extension proposal or XDF/tidy-schema standard was located in this pass — does a citable one actually exist (e.g., an 'Eye Tracking BIDS Extension Proposal' or a de facto tidy-data convention used by major online eye-tracking toolkits), and if so what are its actual column/field specifications?
2. No evidence was found for the Barr et al. (2013) 'keep it maximal' random-effects debate or its Matuschek et al. (2017)/Bates et al. critiques — a targeted follow-up search is needed since this was explicitly requested but entirely missing from survived claims.
3. What concrete calibration/validation-error threshold in pixels, percent of screen, or degrees (distinct from sampling-rate or general accuracy benchmarks) is actually published and applied as an inclusion/exclusion rule in webcam eye-tracking studies, beyond the 5 Hz sampling-rate cutoff and 3-4.5° general accuracy benchmark found here?
4. No split-half reliability or ICC-as-a-function-of-trial-count analysis for individual-level gaze or facial-expression estimates was found — is there a citable paper establishing how many trials per condition are needed for reliable individual-level (not just group-level) gaze/expression estimates in webcam studies?

## Caveats

(1) Several verifiers explicitly noted their session's WebSearch tool budget was exhausted and relied on direct primary-source fetches (via PMC, Springer, PLOS, CrossRef, PubMed eutils) or, in a few cases (Kumle et al. 2021 Monte Carlo definition; Chmielewski & Kucker 2020 exact wording; Maris & Oostenveld 2007 Type I error proof), on strong prior domain knowledge rather than a fresh independent search — these are flagged 'medium' confidence above even where the vote was 3-0. (2) Topic E (BIDS/XDF/tidy schema for multimodal behavioral data) returned zero surviving claims — this is a genuine evidence gap in this pass, not a synthesis omission; a dedicated follow-up search targeting 'Eye Tracking BIDS Extension Proposal', EEG-BIDS, and XDF specification documents is needed. (3) The Barr et al. (2013) 'keep it maximal' random-effects debate and its critiques (Matuschek et al. 2017, Bates et al.) were requested but not evidenced at all. (4) Five claims from this research pass were explicitly REFUTED on adversarial verification and must not be reused: a claimed 75%-completion/RT-outlier/75%-valid-data exclusion rule attributed to Bogdan et al.; a claim that Bogdan et al. reported no numeric thresholds at all; a claimed WebGazer 4.17° lab accuracy figure with ~30Hz vs >60Hz sampling comparison; a claim that the Kumle et al. tutorial works through both simr and mixedpower together; and a claimed 180-subjects worked-example conclusion from that same tutorial — these appear superficially plausible but did not survive verification and should be treated as false leads. (5) No formal calibration/validation-error threshold in px, %, or degrees (as opposed to sampling-rate or general accuracy benchmarks) was found as an actually-applied exclusion rule in any single paper — only the 5 Hz sampling-rate threshold (Prystauka et al.) and the general 3–4.5° accuracy benchmark (Bogdan et al.) were found as concrete numbers. (6) No split-half reliability or ICC-vs-trial-count analysis for individual-level gaze/facial-expression estimates was found despite being explicitly requested under Topic B. (7) The Peer et al. (2022) and PLOS ONE platform-comparison data are from 2020-2022 data collections; platform data-quality landscapes (especially MTurk and CloudResearch policies) can shift over time, so these figures should be treated as historical benchmarks from named studies, not necessarily current-day guarantees.

## All sources

- {"url":"https://www.semanticscholar.org/paper/e2d564584d282bd6a01a71fb9af9199e4455a021","quality":"primary","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":5}
- {"url":"https://www.semanticscholar.org/paper/3a2ddb01f7429c2873fe84457c0537843d506270","quality":"unreliable","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":0}
- {"url":"https://dl.acm.org/doi/10.1145/2168556.2168563","quality":"unreliable","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":0}
- {"url":"https://www.semanticscholar.org/paper/0b421419f70beb827e6001dccf12fd76e794c322","quality":"primary","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":5}
- {"url":"https://www.semanticscholar.org/paper/43daf8667182275f4f0b9a8a3c10fe61843022fd","quality":"unreliable","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":0}
- {"url":"https://www.semanticscholar.org/paper/d79589d5dbe2f17282e0bd1d84ff241921c665a6","quality":"unreliable","angle":"Topic A: exclusion thresholds and reporting standards","claimCount":0}
- {"url":"https://link.springer.com/article/10.3758/s13428-023-02176-4","quality":"primary","angle":"Topic B: power and sample size","claimCount":5}
- {"url":"https://doi.org/10.3758/s13428-020-01562-y","quality":"primary","angle":"Topic B: power and sample size","claimCount":5}
- {"url":"https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0279720","quality":"primary","angle":"Topic C: attrition and platform data quality","claimCount":5}
- {"url":"https://doi.org/10.3758/s13428-021-01694-3","quality":"primary","angle":"Topic C: attrition and platform data quality","claimCount":5}
- {"url":"https://doi.org/10.1177/1948550619875149","quality":"primary","angle":"Topic C: attrition and platform data quality","claimCount":5}
- {"url":"https://link.springer.com/article/10.3758/s13428-021-01694-3","quality":"primary","angle":"Topic C: attrition and platform data quality","claimCount":5}
- {"url":"https://journals.sagepub.com/doi/10.1177/1948550619875149","quality":"unreliable","angle":"Topic C: attrition and platform data quality","claimCount":0}
- {"url":"https://doi.org/10.1016/j.jneumeth.2007.03.024","quality":"primary","angle":"Topic D: time-series statistical methods","claimCount":4}
- {"url":"https://doi.org/10.1177/2331216519832483","quality":"primary","angle":"Topic D: time-series statistical methods","claimCount":5}
- {"url":"https://doi.org/10.1016/j.jml.2007.11.006","quality":"primary","angle":"Topic D: time-series statistical methods","claimCount":5}
- {"url":"https://doi.org/10.1016/j.jml.2017.01.001","quality":"primary","angle":"Topic D: time-series statistical methods","claimCount":5}
- {"url":"https://doi.org/10.1016/j.jml.2012.11.001","quality":"primary","angle":"Topic D: random effects debate","claimCount":4}
- {"url":"https://doi.org/10.1016/j.jml.2016.11.001","quality":"unreliable","angle":"Topic D: random effects debate","claimCount":0}
- {"url":"https://arxiv.org/abs/1506.04967","quality":"primary","angle":"Topic D: random effects debate","claimCount":3}
- {"url":"https://cran.r-project.org/web/packages/RePsychLing/index.html","quality":"unreliable","angle":"Topic D: random effects debate","claimCount":0}
- {"url":"https://github.com/bids-standard/bids-specification/pull/1128","quality":"primary","angle":"Topic E: data format standards","claimCount":5}
- {"url":"https://bids-specification.readthedocs.io/en/latest/modality-specific-files/physiological-recordings.html","quality":"primary","angle":"Topic E: data format standards","claimCount":5}
- {"url":"https://github.com/sccn/xdf/wiki/Specifications","quality":"primary","angle":"Topic E: data format standards","claimCount":5}
