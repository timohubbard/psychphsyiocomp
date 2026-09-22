# Pass 3b: Analysis, Metrics & Data Pipeline

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection, secondary in-lab mode, modalities: webcam eye tracking, facial expression, voice, camera respiration). Other passes cover validation accuracy, study design and law. Research ONLY the ANALYSIS, METRICS AND DATA-PIPELINE layer. Prefer peer-reviewed methods papers, authoritative textbooks/handbooks, and official technical documentation.

TOPIC A — GAZE METRIC DEFINITIONS. Precise, citable definitions and computation of AOI-based eye-tracking metrics: time to first fixation (entry time), first fixation duration, total fixation duration / dwell time, fixation count, visit/revisit count, exit time, AOI hit rate, ratio/percentage fixated, and time-to-first-mouse-click style behavioral joins. Cover Holmqvist et al. "Eye Tracking: A Comprehensive Guide to Methods and Measures" as the canonical reference, and vendor metric definitions (Tobii Pro, SMI, iMotions) where they differ — definitional inconsistency between platforms is a real and documented problem worth surfacing. Also cover fixation detection algorithms and their parameterization: I-VT, I-DT, I-HMM, Nystrom & Holmqvist adaptive, and which are appropriate at low (10-40 Hz) sampling rates.

TOPIC B — HEATMAPS AND SCANPATHS. How attention heatmaps are actually generated: Gaussian kernel density estimation, choice of kernel bandwidth and its relationship to tracker accuracy and foveal size (~1-2 degrees), duration-weighted versus fixation-count-weighted accumulation, normalization within and across participants, absolute versus relative scaling, and the documented ways heatmaps mislead. Scanpath comparison methods: string-edit/Levenshtein distance, ScanMatch (Cristino et al. 2010), MultiMatch (Jarodzka/Dewhurst et al.), eyenalysis, sequence alignment and transition-matrix/Markov approaches, plus scanpath clustering. Report the known strengths and failure modes of each.

TOPIC C — DYNAMIC AOIs AND AUTOMATED AOI DETECTION. Defining areas of interest on moving video stimuli: keyframe interpolation, object tracking, and modern automated approaches (segmentation/detection models applied to stimulus video). Also cover AOI definition on dynamic web pages and scrolling content, and the mapping problem for screen recordings. Include published guidance on AOI margin/padding sizing relative to tracker spatial error.

TOPIC D — TIME SYNCHRONIZATION OF ASYNCHRONOUS MULTIMODAL STREAMS. This is the hardest engineering problem in the build. Cover: Lab Streaming Layer (LSL) architecture, its clock-offset estimation and post-hoc dejittering, and published measurements of the synchronization accuracy actually achieved with LSL. Browser-side timing: performance.now() versus Date.now(), the monotonic clock, timer resolution clamping and jitter introduced as a Spectre mitigation, requestAnimationFrame and requestVideoFrameCallback for per-frame video timestamps, MediaStreamTrack timestamps, the WebAudio AudioContext clock and its drift relative to the system clock, and how to align an audio stream with a video stream in a browser. Published measurements of stimulus presentation timing accuracy in browsers (the Bridges et al. / Anwyl-Irvine et al. "Timing accuracy of web experiments" line of work, jsPsych, PsychoPy/PsychoJS, Gorilla, Lab.js). What synchronization accuracy is realistically achievable remotely, and what design patterns (per-stream hardware timestamps, common clock, post-hoc cross-correlation alignment, audio sync tones, photodiode-equivalents) mitigate the error.

TOPIC E — EPOCHING, AGGREGATION, STATISTICS AND EXPORT. Stimulus-event epoching and baseline correction for time-series physiological and gaze data. Aggregation across trials and participants, and the problem of unequal and variable sampling rates. Appropriate statistical methods for this data class: cluster-based permutation testing (Maris & Oostenveld), generalized additive mixed models (GAMMs) and growth-curve analysis for time-course gaze data, (generalized) linear mixed-effects models with crossed random effects and the "keep it maximal" random-effects debate, divergence-point analysis, and multiple-comparison control. Data formats and interoperability for long-term reuse: BIDS and its eye-tracking BEP/extension, LSL XDF, Parquet and canonical long-format event tables, and any emerging standards for multimodal behavioral data. Give concrete recommendations on schema design for a canonical timestamped signal table plus an event table.

---

## Summary

Across 22 verified claims, the strongest, best-evidenced material for the analysis/metrics/data-pipeline layer clusters into three areas: (1) gaze-metric definitions and fixation-detection are canonically fixed by Holmqvist et al. but are algorithm-dependent in practice — the same raw data yields materially different fixation/saccade counts and durations depending on which detector (I-VT, I-DT, I-HMM, adaptive) is applied, and detectors that work reasonably well on static stimuli perform barely better than chance on dynamic video and degrade further under head movement/locomotion, which is a first-order risk for a webcam-based, dynamic-stimulus platform; (2) scanpath comparison has a well-established toolkit (Levenshtein/ScanMatch's Needleman-Wunsch-family string-edit methods on AOI sequences vs. MultiMatch's five-dimension vector-based comparison that avoids AOI-boundary quantization noise), with modern visual-analytics tools (Gazealytics) demonstrating that scanpath/AOI-hit-rate metrics are highly sensitive to AOI boundary definition; and (3) dynamic-AOI and cross-device mapping problems (DynAOI's 3D-model matching vs. manual keyframe-polygon interpolation; eyeScrollR's deterministic scroll-offset mapping for web pages vs. commercial video-recording-based tools whose frame-rate mismatch can introduce 100ms+ timing error) are solved problems in principle but require careful engineering choices specific to the browser/webcam context. For Topic D, only LSL's high-level sync architecture (NTP-inspired, sub-millisecond design goal on a local network) survived verification — no confirmed claims exist on browser-native timing APIs (performance.now, requestVideoFrameCallback, WebAudio clock drift) or on published remote-timing-accuracy studies (Bridges/Anwyl-Irvine, jsPsych/PsychoJS/Gorilla), which is the single largest evidence gap relative to the research questions posed. Topic E (epoching, aggregation, statistics, BIDS/XDF/Parquet export) produced zero surviving confirmed claims, so no citable synthesis can be offered there from this verification pass. Vendor-to-vendor metric-definition inconsistency (Topic A's explicit ask) is only evidenced for one vendor (Tobii Pro Spectrum's filtered-vs-raw precision spec), not for cross-vendor (SMI/iMotions) comparisons.

## Findings

### 1. [3-0 (x2, merged)] (confidence: high)

**Claim:** Holmqvist et al.'s 'Eye Tracking: A Comprehensive Guide to Methods and Measures' (Oxford, 2011) treats AOI latency and duration metrics as a family of distinct, separately-defined constructs rather than interchangeable terms: entry time in AOI vs. thresholded entry time are two separate latency measures (Ch.13), and first fixation duration after stimulus onset, first fixation duration in an AOI (and second), dwell time, total dwell time, and first/second-pass dwell time in an AOI are five separately operationalized duration/dwell measures (Ch.11).

**Evidence:** Both claims were verified directly against the book's own table of contents (primary source, unanimous 3-0 votes). This establishes the canonical taxonomy a research platform should map its own metric names onto, but the evidence is structural (TOC-level) rather than the full operational definitions/formulas themselves, which were not independently re-verified in this pass.

**Sources:** https://www.biblos.pk.edu.pl/ST/2017/06/100000296643/100000296643_Holmqvist_EyeTracking.pdf


### 2. [3-0, 3-0, 2-1 (merged)] (confidence: high)

**Claim:** Fixation/saccade event detection is algorithm-dependent, not just data-dependent: running I-VT, I-DT, I-HMM, adaptive (Nyström & Holmqvist) and other detectors on the same raw gaze data produces substantially different fixation/saccade durations and counts. These detectors perform reasonably well on static stimuli but only barely better than chance on dynamic (video) stimuli, and traditional dispersion/velocity-based algorithms (I-VT, I-DT, I-HMM, EyeMMV) additionally break down during head movement/locomotion because gaze-stabilization behavior inflates apparent dispersion beyond what static-scene algorithms expect (demonstrated by accuracy dropping from ~90-92% on static-screen data to ~68-70% on real locomotion data at the same 30Hz sampling rate).

**Evidence:** Merges three related claims from Andersson/Larsson/Holmqvist/Stridh/Nyström (2017, Behavior Research Methods, peer-reviewed, canonical) and Anantrasirichai/Gilchrist/Bull (mobile eye-tracking event detection paper). Direct implication for the platform: fixation counts/durations must be reported with the specific algorithm and parameters used, and standard detectors should not be assumed reliable on dynamic web/video content or during head movement without validation. Note two related, more specific claims from the second source (CNN outperforming other methods by up to 16%; a 40Hz Nyquist argument for why 30Hz sampling is inadequate) were explicitly refuted on verification (0-3/1-2 votes) and should not be relied on.

**Sources:** https://www.researchgate.net/publication/303359171_One_algorithm_to_rule_them_all_An_evaluation_and_discussion_of_ten_eye_movement_event-detection_algorithms | https://seis.bristol.ac.uk/~eexna/papers/event_detection.pdf


### 3. [3-0] (confidence: medium)

**Claim:** Required sample sizes to reliably detect small (5-10ms) effects in First Fixation Duration scale sharply as sampling rate drops: ~2400 observations/condition recommended at 1000Hz, 6400 at ≤125Hz, and at least 9000 at sampling rates under 50Hz.

**Evidence:** Verified verbatim against the primary peer-reviewed source across three matching figures. Directly relevant to a webcam platform (which will often sample well under 50Hz): small-effect designs need much larger per-condition sample sizes than researchers accustomed to lab-grade trackers typically plan for. Caveat: this appears to derive from one study's simulation/subsampling analysis, not yet cross-validated by independent replication, so treat as an evidence-based rule of thumb. A related, more optimistic claim from the same paper -- that low sampling rates do not prevent detection of cognitive effects, supporting low-cost webcam trackers -- was explicitly refuted (0-3 vote) and should not be cited.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC12149270/


### 4. [3-0] (confidence: medium)

**Claim:** Vendor-reported precision/quality figures for eye-tracking hardware depend heavily on which processing stage is measured -- e.g., Tobii Pro Spectrum specifies 0.01° RMS precision for the Savitzky-Golay-filtered signal vs. 0.06° RMS for the raw (unfiltered) signal under identical (optimal, head-supported) conditions -- illustrating a documented source of cross-vendor metric non-comparability.

**Evidence:** Verified against the live vendor spec page. This is a single-vendor illustration of the definitional-inconsistency problem the research question asked about; no confirmed claims document analogous SMI or iMotions figures or cross-vendor comparisons, so this finding should be treated as a proof-of-concept of the problem rather than a full cross-vendor survey (a real gap -- see open questions).

**Sources:** https://www.tobii.com/products/eye-trackers/screen-based/tobii-pro-spectrum


### 5. [3-0, 3-0, 3-0, 3-0, 2-1, 3-0, 3-0 (merged across 7 claims)] (confidence: high)

**Claim:** Scanpath comparison has two established, well-differentiated method families: (1) string-edit/sequence-alignment methods operating on AOI-labeled sequences -- Levenshtein-style string edit distance and ScanMatch (which adapts the Needleman-Wunsch algorithm to grid/AOI-segmented fixation sequences, per Cristino et al. 2010) -- and (2) MultiMatch, a vector-based method that represents each scanpath as a sequence of saccade vectors (simplified via amplitude/direction clustering, temporally aligned via a Dijkstra-based algorithm) and scores similarity along five separate dimensions (shape, direction, length/amplitude, position, duration) rather than one composite score, explicitly avoiding the 'quantization noise' / AOI-boundary misclassification problem that affects string-edit/AOI-based methods. A modern open-source tool (Gazealytics) implements Needleman-Wunsch-based AOI-sequence scoring directly. In an applied study, ScanMatch-based scanpath analysis revealed meaningful group differences (e.g., in surveillance target-identification errors) that traditional aggregate dwell-time metrics failed to discriminate.

**Evidence:** Seven separate claims (Holmqvist TOC taxonomy; Gazealytics' Needleman-Wunsch implementation; MultiMatch's five dimensions and its vector/clustering/Dijkstra mechanism; MultiMatch's quantization-noise avoidance rationale, 2-1 vote; ScanMatch's Needleman-Wunsch/Levenshtein-family algorithm; and ScanMatch's demonstrated diagnostic value over aggregate metrics) converge on a coherent, well-sourced picture from primary peer-reviewed methods papers. This directly supports building both an AOI-sequence string-alignment metric and a coordinate-based MultiMatch-style metric into the platform's scanpath-comparison layer, and suggests scanpath-level analysis can surface effects that simple duration/count aggregates miss.

**Sources:** https://www.biblos.pk.edu.pl/ST/2017/06/100000296643/100000296643_Holmqvist_EyeTracking.pdf | https://arxiv.org/pdf/2303.17202 | https://link.springer.com/article/10.3758/s13428-012-0212-2 | https://link.springer.com/article/10.3758/s13428-018-1154-0


### 6. [3-0] (confidence: medium)

**Claim:** AOI hit-rate metrics are highly sensitive to how AOI boundaries are defined: an interactive visual-analytics tool (Gazealytics) showed its 'hit-any-AOI-rate (HAAR)' metric changing from 77% to 88% to 93% purely as a function of iteratively refining the same AOI definitions on the same gaze data.

**Evidence:** Verified directly against the paper's own reported figures. Single source, but a concrete, quantified illustration of a documented problem: AOI hit-rate/percentage-fixated statistics are not robust to AOI definition choices, so a platform reporting these metrics needs to expose and version its AOI definitions and margin/padding choices, not just the resulting percentages.

**Sources:** https://arxiv.org/pdf/2303.17202


### 7. [3-0, 2-1 (merged)] (confidence: high)

**Claim:** Automated dynamic-AOI definition for video stimuli has a documented middle ground: DynAOI (Papenmeier & Huff, 2010) automates AOI creation for animations built from an underlying 3D model, by ray-casting gaze data against the model's static and dynamic objects (rather than manually interpolating hand-drawn polygons between keyframes, the prior state of the art exemplified by SMI BeGaze); but for real-world video footage it still requires a 3D scene model to be constructed first (manually, e.g. in Blender, by approximating objects with simple geometric primitives and animating them at keyframes) -- it is not a general-purpose automated detector for arbitrary video.

**Evidence:** Both claims verified directly against the primary paper's abstract, methods, and conclusion. This is directly relevant to Topic C: it documents the historical contrast between keyframe-interpolated hand-drawn polygon AOIs (the older/simpler approach) and 3D-model-based automated matching (DynAOI's approach), and flags that even 'automated' dynamic-AOI tools of this generation are not a drop-in solution for arbitrary real-world/webcam video without upstream 3D reconstruction or (implicitly) a modern segmentation/detection-model-based replacement, which the research topic asked about but no confirmed claims addressed.

**Sources:** https://doi.org/10.3758/brm.42.1.179


### 8. [3-0, 2-1 (merged)] (confidence: medium)

**Claim:** For mapping gaze coordinates onto dynamic/scrollable web-page content, a deterministic algorithm based on mouse-scroll event data (eyeScrollR) can remap screen-space fixations to full-page coordinates with sub-2px median error (validated at ~1.1px median, 1.67% of points >3px error, against blind manual coding across 479 fixations spanning 4 pages x 4 settings), avoiding the heuristic computer-vision approaches used by some commercial tools. By contrast, video-recording-based gaze-mapping methods (manual coding and commercial software such as Tobii, iMotions, Gazepoint, WebLink) are inherently limited by screen-recording frame rate being lower than monitor refresh rate, and under computational lag/frame-skipping this can produce timing inaccuracies of 100ms or more (with one documented empirical case reaching 141ms).

**Evidence:** Both claims verified against the same primary source (a preprint later peer-reviewed as Larigaldie, Dreneva & Orquin, Behavior Research Methods 2024). This is a single (self-authored/self-validated, not independently replicated) source, so treat the specific numbers as evidence-based estimates from the tool's own developers rather than field consensus, but the underlying mechanism (video sample rate vs. display refresh rate mismatch) is basic and uncontested signal-timing physics. Directly actionable for the platform: prefer event-driven (scroll/DOM-event) coordinate remapping over screen-recording-based remapping wherever possible, since the latter has a documented 100ms+ error mode relevant to Topic D's synchronization concerns as well.

**Sources:** https://doi.org/10.31234/osf.io/ymubw


### 9. [3-0, 3-0 (merged)] (confidence: high)

**Claim:** Lab Streaming Layer's built-in time-synchronization facility is explicitly designed (modeled on the Network Time Protocol, NTP, and implemented within the LSL library itself) to achieve sub-millisecond clock-offset accuracy across a local network of computers.

**Evidence:** Both claims verified verbatim against LSL's official technical documentation (primary, authoritative, current). This establishes the architectural baseline for Topic D's hardest problem, but note this is a stated design goal on a local network, not an independent empirical measurement of achieved accuracy in a distributed/remote browser deployment -- no confirmed claims in this pass covered actual published LSL accuracy measurements, post-hoc dejittering specifics, or any browser-native timing API (performance.now/Date.now jitter, requestVideoFrameCallback, WebAudio clock drift), which remain unaddressed gaps for the platform's core synchronization design.

**Sources:** https://labstreaminglayer.readthedocs.io/info/intro.html

## Refuted claims (do not use)

1. {"claim":"The study concludes that low eye-tracker sampling rates do not prevent detection of cognitive processing effects during reading, supporting use of low-cost/low-sampling-rate webcam-class trackers for reading research.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC12149270/"}
2. {"claim":"The paper's proposed CNN-based fixation identification method outperforms existing methods (I-VT, I-HMM, EyeMMV) by up to 16% in classification accuracy on real 30-Hz mobile eye tracker data (SMI), with specific reported accuracies of I-VT=69.41%, I-HMM=70.33%, EyeMMV=68.82% vs. the proposed CNN method=80.29%.","vote":"1-2","source":"https://seis.bristol.ac.uk/~eexna/papers/event_detection.pdf"}
3. {"claim":"Mobile eye trackers typically sample at 30-60 Hz (versus 1000 Hz for stationary research-grade trackers), and because the Nyquist frequency needed to adequately track saccades is 40 Hz, 30 Hz sampling is below the theoretical requirement for reliable fixation/saccade discrimination.","vote":"0-3","source":"https://seis.bristol.ac.uk/~eexna/papers/event_detection.pdf"}

## Open questions

1. No confirmed claims address Topic E at all (epoching/baseline correction, cluster-based permutation testing, GAMMs/growth-curve analysis, mixed-effects models, BIDS/XDF/Parquet schema design) -- this entire layer needs a dedicated follow-up research pass.
2. No confirmed claims address browser-native timing mechanics (performance.now vs Date.now, Spectre-mitigation timer clamping/jitter, requestAnimationFrame/requestVideoFrameCallback, MediaStreamTrack timestamps, WebAudio AudioContext clock drift) or published remote web-experiment timing-accuracy studies (Bridges/Anwyl-Irvine, jsPsych, PsychoJS, Gorilla, Lab.js) -- this is the single biggest gap relative to Topic D, which the task called 'the hardest engineering problem in the build.'
3. Cross-vendor metric-definition inconsistency (Tobii Pro vs. SMI vs. iMotions) is evidenced for only one vendor (Tobii); no verified claims document how SMI or iMotions define comparable metrics (e.g., fixation filters, dwell time) differently, so the documented 'definitional inconsistency between platforms' problem the task flagged remains only partially substantiated.
4. Heatmap generation mechanics (Gaussian KDE bandwidth selection, its relationship to tracker accuracy/foveal size, duration- vs. count-weighted accumulation, absolute vs. relative normalization, and documented ways heatmaps mislead) produced zero surviving confirmed claims despite being explicitly requested in Topic B -- needs targeted follow-up.

## Caveats

This synthesis is bounded strictly by what survived the 3-vote adversarial verification pass; it is not a fresh literature review, so absence of a claim here does not mean the underlying literature doesn't exist, only that no claim on that sub-topic was both proposed and verified in this pass. Several structural/high-confidence claims (e.g., the two Holmqvist TOC claims, the two LSL doc claims) verify only that a definition or design-goal statement exists in the canonical source, not the full operational detail (formulas, exact thresholds) behind it -- treat these as pointers to the right chapter/page rather than complete definitions. Several findings rest on a single primary source (Tobii spec page; Gazealytics paper; eyeScrollR preprint/paper; DynAOI 2010 paper), so cross-validation against independent sources is still needed before treating specific numbers as field consensus. Three claims relevant to webcam/low-sampling-rate feasibility were explicitly refuted on verification (low sampling rate not preventing effect detection; a CNN method beating I-VT/I-HMM/EyeMMV by up to 16%; a 40Hz-Nyquist argument against 30Hz sampling) -- do not cite these even though they surfaced during research. The DynAOI and Anantrasirichai et al. sources are ~10-16 years old; the underlying oculomotor/geometric mechanisms they describe are unlikely to be outdated, but tooling built since then (e.g., modern video segmentation-based AOI detection, which Topic C explicitly asked about) is undocumented here. Multiple verifiers noted their WebSearch budget was exhausted and so could not run independent corroboration/contradiction searches beyond the primary source itself -- verification for several claims rests on direct primary-source reading only, which is strong but not multi-source triangulation.

## All sources

- {"url":"https://www.biblos.pk.edu.pl/ST/2017/06/100000296643/100000296643_Holmqvist_EyeTracking.pdf","quality":"primary","angle":"Gaze metric definitions & fixation algorithms","claimCount":5}
- {"url":"https://www.researchgate.net/publication/303359171_One_algorithm_to_rule_them_all_An_evaluation_and_discussion_of_ten_eye_movement_event-detection_algorithms","quality":"primary","angle":"Gaze metric definitions & fixation algorithms","claimCount":5}
- {"url":"https://www.researchgate.net/publication/41452096_An_adaptive_algorithm_for_fixation_saccade_and_glissade_detection_in_eyetracking_data","quality":"unreliable","angle":"Gaze metric definitions & fixation algorithms","claimCount":0}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC12149270/","quality":"primary","angle":"Gaze metric definitions & fixation algorithms","claimCount":4}
- {"url":"https://seis.bristol.ac.uk/~eexna/papers/event_detection.pdf","quality":"primary","angle":"Gaze metric definitions & fixation algorithms","claimCount":5}
- {"url":"https://link.springer.com/article/10.3758/s13428-024-02529-7","quality":"primary","angle":"Vendor metric inconsistency","claimCount":4}
- {"url":"https://imotions.com/blog/learning/10-terms-metrics-eye-tracking/","quality":"blog","angle":"Vendor metric inconsistency","claimCount":5}
- {"url":"https://arxiv.org/pdf/2303.17202","quality":"primary","angle":"Vendor metric inconsistency","claimCount":4}
- {"url":"https://www.sciencedirect.com/topics/psychology/eye-tracking-system","quality":"unreliable","angle":"Vendor metric inconsistency","claimCount":0}
- {"url":"https://www.tobii.com/products/eye-trackers/screen-based/tobii-pro-spectrum","quality":"primary","angle":"Vendor metric inconsistency","claimCount":5}
- {"url":"https://imotions.com/products/imotions-lab/modules/eye-tracking-screen-based/","quality":"secondary","angle":"Vendor metric inconsistency","claimCount":5}
- {"url":"https://link.springer.com/article/10.3758/s13428-012-0212-2","quality":"primary","angle":"Heatmaps and scanpath comparison methods","claimCount":5}
- {"url":"https://link.springer.com/article/10.3758/s13428-018-1154-0","quality":"primary","angle":"Heatmaps and scanpath comparison methods","claimCount":3}
- {"url":"https://dl.acm.org/doi/fullHtml/10.1145/3517031.3529243","quality":"unreliable","angle":"Heatmaps and scanpath comparison methods","claimCount":0}
- {"url":"https://doi.org/10.3758/brm.42.1.179","quality":"primary","angle":"Dynamic AOI automation on video/web","claimCount":4}
- {"url":"https://doi.org/10.1145/2370216.2370363","quality":"unreliable","angle":"Dynamic AOI automation on video/web","claimCount":0}
- {"url":"https://doi.org/10.1002/bdm.1867","quality":"unreliable","angle":"Dynamic AOI automation on video/web","claimCount":0}
- {"url":"https://doi.org/10.31234/osf.io/ymubw","quality":"primary","angle":"Dynamic AOI automation on video/web","claimCount":5}
- {"url":"https://labstreaminglayer.readthedocs.io/info/intro.html","quality":"primary","angle":"Browser multimodal time synchronization","claimCount":4}
- {"url":"https://doi.org/10.7717/peerj.9414","quality":"primary","angle":"Browser multimodal time synchronization","claimCount":5}
- {"url":"https://doi.org/10.3758/s13428-020-01501-5","quality":"primary","angle":"Browser multimodal time synchronization","claimCount":5}
- {"url":"https://developer.mozilla.org/en-US/docs/Web/API/Performance/now","quality":"primary","angle":"Browser multimodal time synchronization","claimCount":5}
- {"url":"https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback","quality":"primary","angle":"Browser multimodal time synchronization","claimCount":5}
- {"url":"https://doi.org/10.1016/j.jneumeth.2007.03.024","quality":"primary","angle":"Epoching, statistics, and data standards","claimCount":4}
- {"url":"https://bids-specification.readthedocs.io/","quality":"primary","angle":"Epoching, statistics, and data standards","claimCount":5}
- {"url":"https://github.com/sccn/xdf","quality":"primary","angle":"Epoching, statistics, and data standards","claimCount":5}
- {"url":"https://doi.org/10.1016/j.jml.2012.11.001","quality":"primary","angle":"Epoching, statistics, and data standards","claimCount":5}
- {"url":"https://mikabr.github.io/eyetrackingR/","quality":"unreliable","angle":"Epoching, statistics, and data standards","claimCount":0}
- {"url":"https://parquet.apache.org/docs/","quality":"primary","angle":"Epoching, statistics, and data standards","claimCount":4}
