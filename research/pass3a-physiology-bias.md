# Pass 3a: rPPG, Respiration & Demographic Bias

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection, secondary in-lab mode). Other passes cover eye tracking, facial AU, voice, study design and law. Research ONLY camera-based physiological measurement and demographic bias. Prefer peer-reviewed primary sources and benchmark papers; flag vendor claims as unverified.

TOPIC A — rPPG HEART RATE VALIDATION. Independent peer-reviewed accuracy of remote photoplethysmography heart rate versus ECG or contact PPG, reported as MAE/RMSE in bpm and Pearson r, on the standard benchmarks: UBFC-rPPG, PURE, VIPL-HR, MMPD, COHFACE, MAHNOB-HCI, and any in-the-wild/unconstrained datasets. Compare classical unsupervised algorithms (Green, ICA, CHROM, POS, LGI, PBV) against deep methods (DeepPhys, PhysNet, TS-CAN, EfficientPhys, PhysFormer, RhythmFormer). Use the rPPG-Toolbox (Liu et al., NeurIPS 2023 Datasets & Benchmarks) and pyVHR papers as the authoritative cross-algorithm comparisons, including their cross-dataset generalization tables — the key question is how much performance drops when training and test datasets differ.

TOPIC B — HRV RECOVERABILITY. Whether heart-rate-variability metrics (RMSSD, SDNN, pNN50, LF/HF, inter-beat intervals) are actually recoverable from consumer webcam video, and with what error versus ECG. Cover the sampling-rate and frame-rate requirements for beat-to-beat interval precision, why 30 fps is marginal for IBI estimation, interpolation/upsampling approaches, and published agreement statistics (Bland-Altman limits of agreement, ICC). Include skeptical/negative findings — papers concluding HRV from webcam is unreliable.

TOPIC C — CAMERA-BASED RESPIRATION. Accuracy of camera-derived respiration rate versus chest belt (respiratory inductance plethysmography), spirometry or capnography, in breaths-per-minute error. Cover both approaches: (1) chest/shoulder region-of-interest MOTION tracking, including optical flow and profile/edge methods — this is what iMotions actually implements; and (2) face-derived respiration extracted from the rPPG signal via respiratory sinus arrhythmia or amplitude modulation. Report which is more robust and under what conditions, and how each degrades with subject movement, clothing, posture and seated-at-desk framing.

TOPIC D — VIDEO COMPRESSION AND FRAME-RATE JITTER. Quantified effect of video compression on the rPPG signal — this is known to be severe and is decisive for a browser-based architecture. Cover codec (H.264, H.265, VP8/VP9, AV1), bitrate and constant-rate-factor effects on rPPG SNR and HR error; chroma subsampling; the specific problem that WebRTC and browser capture apply lossy encoding and adaptive bitrate; and published results on how much bitrate is required before rPPG becomes unusable. Also cover variable/jittered frame rate and dropped frames, and timestamp handling. Include any work on transmitting raw or lightly-compressed frames, or on-device processing, as mitigations.

TOPIC E — DEMOGRAPHIC AND SKIN-TONE BIAS, ACROSS MODALITIES. (1) rPPG performance stratified by Fitzpatrick skin type or melanin index — the physical basis (light absorption in melanin reducing the blood-volume-pulse signal) and quantified error disparities; note that pulse oximetry's documented racial bias is relevant background. (2) Face detection and facial expression recognition disparities by race, gender and age, including Rhue (2018) on Black faces being assigned more negative emotion, Buolamwini & Gebru Gender Shades, and Nagpal et al. 2019. (3) Webcam eye-tracking performance with eyeglasses, contact lenses, mascara/eye makeup, and variation in eyelid shape including epicanthic fold; also any published effects of iris colour on appearance-based gaze estimation. (4) Speech emotion recognition bias by gender, age, accent, and non-native/L2 speech. For each, name the datasets and audits that document the disparity and give numbers where published.

---

## Summary

Camera-based physiological sensing for a browser-first platform looks genuinely usable but strongly conditional. Independent benchmarks (rPPG-Toolbox) and a large 2026 naturalistic validation study converge on webcam heart-rate error of roughly 1-4 bpm MAE under favorable conditions, but accuracy collapses by 10x+ under cross-dataset/out-of-distribution conditions or heavy video compression, with H.265 the most compression-tolerant codec and legacy compressed formats pushing accuracy below a naive constant-guess baseline — directly relevant to WebRTC's lossy, adaptive-bitrate capture. Heart-rate variability is much harder to recover than heart rate itself: webcam-derived RMSSD/SDNN show ~11ms error vs ECG, enough for group-level comparisons but not individual-level precision, and even finger-contact PPG fails formal agreement tests on several HRV parameters despite high correlation. Camera-based respiration accuracy is almost entirely unverified in this pass (only a narrow motion-profile algorithm finding survived; the headline breaths-per-minute accuracy number was refuted), and of the four demographic-bias sub-questions asked, only rPPG skin-tone bias survived verification — accuracy degrades markedly for darker Fitzpatrick types but the gap nearly closes under strong illumination — while face/expression-recognition bias, eye-tracking bias, and speech-emotion-recognition bias evidence did not survive 3-vote verification at all.

## Findings

### 1. [3-0] (confidence: high)

**Claim:** rPPG-Toolbox (Liu et al., NeurIPS 2023 Datasets & Benchmarks; arXiv:2210.00716) is the standard cross-algorithm, cross-dataset rPPG benchmarking platform: it implements classical unsupervised methods (GREEN, ICA, CHROM, LGI, PBV, POS, OMIT) and deep methods (DeepPhys, PhysNet, TS-CAN, EfficientPhys, PhysFormer, RhythmFormer, BigSmall, iBVPNet, PhysMamba, FactorizePhys) across six benchmark datasets (UBFC-rPPG, PURE, SCAMPS, MMPD, BP4D+, UBFC-Phys — notably NOT VIPL-HR, COHFACE, or MAHNOB-HCI), reports MAE/MAPE as its primary results-table metrics, and supports train-on-X/test-on-Y cross-dataset evaluation as a first-class, documented workflow.

**Evidence:** Merges claims 0, 3, 4, 5, 6, 7 (all 3-0 votes, all primary paper/repo sources).

**Sources:** https://arxiv.org/pdf/2210.00716 | https://proceedings.neurips.cc/paper_files/paper/2023/hash/d7d0d548a6317407e02230f15ce75817-Abstract-Datasets_and_Benchmarks.html | https://github.com/ubicomplab/rPPG-Toolbox | https://github.com/ubicomplab/rPPG-Toolbox/blob/main/README.md?plain=1


### 2. [3-0] (confidence: high)

**Claim:** Cross-dataset generalization (training and testing on different datasets) is the dominant driver of rPPG error, far larger than differences between algorithms on a single dataset. PhysNet's MAE rose from 0.98 bpm (PURE→PURE, within-dataset) to 13.30 bpm (SCAMPS→PURE), a >13x increase, while under the identical SCAMPS→PURE condition DeepPhys stayed far more robust (MAE 3.96±1.67 bpm, r=0.83±0.07 vs PhysNet's 13.30±2.00 bpm, r=0.51±0.11) — architecture choice strongly affects out-of-distribution robustness. Even on harder, more diverse benchmarks (MMPD), the best current methods (RhythmFormer, RhythmMamba) still show ~3-3.16 bpm MAE and 6.8-7.3 RMSE.

**Evidence:** Merges claims 1, 2, 8, all 3-0 votes on primary peer-reviewed benchmark papers.

**Sources:** https://arxiv.org/pdf/2210.00716 | https://arxiv.org/pdf/2404.06483


### 3. [3-0] (confidence: medium)

**Claim:** In truly naturalistic, in-the-wild webcam recordings (not curated lab clips), average heart-rate estimation is reasonably accurate but per-recording reliability is only moderate: the largest published independent validation (n=77 participants, 2,436 videos) found MAE 1.67 bpm (SD 2.64) vs ECG, mean Pearson r=.56, and 95% limits of agreement of -5.39 to +6.28 bpm for its best-performing pipeline (POS algorithm).

**Evidence:** Single primary source (claim 13, vote 3-0); large, rigorous, peer-reviewed (Behavior Research Methods, 2026), but not yet independently replicated, so held at medium rather than high per the multiple-primary-source bar.

**Sources:** https://link.springer.com/article/10.3758/s13428-026-02953-x


### 4. [3-0] (confidence: medium)

**Claim:** Video compression severely and quantifiably degrades rPPG accuracy, which is decisive for a browser/WebRTC architecture. On highly compressed datasets (MAHNOB-HCI/H.264, COHFACE/MPEG-4), unsupervised-method HR accuracy is often worse than a dummy baseline that always guesses 75 bpm, versus 0.22-0.36 bpm MAE on the lossless PURE dataset. Among lossy codecs, H.265 gives by far the best accuracy/bitrate trade-off (only +0.3 bpm error for a ~100x bitrate cut, 26 Mbps → 0.26 Mbps), but even the mildest lossy compression settings tested still measurably worsen accuracy versus lossless.

**Evidence:** Merges claims 10, 11, both 3-0 votes, but both from a single primary paper (Gudi, Bittner & van Gemert 2020) with no independent corroborating quantitative source found in this pass.

**Sources:** https://arxiv.org/pdf/2012.15846


### 5. [3-0] (confidence: medium)

**Claim:** HRV metrics are markedly harder to recover accurately from camera video than HR itself, and reliability is inconsistent across studies. The best direct webcam-vs-ECG validation found substantial per-recording HRV error (SDNN error 11.45±14.34 ms, RMSSD error 11.02±9.78 ms) — sufficient to detect group-level differences (e.g., by participant characteristics) but explicitly described as limited at the individual level. Separately, HRV error is reported as worst specifically on datasets with heavy compression noise (MAHNOB-HCI, COHFACE) or large/fast motion (VIPL-HR, ECG-Fitness), with ~30 ms RMSSD proposed as a rough threshold for 'acceptably accurate' given the normal human range of 19-75 ms RMSSD.

**Evidence:** Merges claims 12 and 14, both unanimous (3-0) but each resting on a single primary study.

**Sources:** https://link.springer.com/article/10.3758/s13428-026-02953-x | https://arxiv.org/pdf/2012.15846


### 6. [2-1] (confidence: low)

**Claim:** A systematic review/meta-analysis (43 studies, 8 contributing to the pooled RMSSD estimate) reports a pooled absolute standardized error of 0.188 (95% CI 0.066-0.309, I2=11.69%) between PPG-derived and ECG-derived RMSSD — but this only narrowly survived verification (split 2-1 vote), and it pools heterogeneous PPG sources/devices rather than webcam rPPG specifically, so its applicability to remote camera-based measurement is uncertain.

**Evidence:** Claim 9, vote 2-1 (split, not unanimous), single source, and scope (PPG in general, not specifically webcam) only loosely matches the research question.

**Sources:** https://pubmed.ncbi.nlm.nih.gov/42655500/


### 7. [2-1] (confidence: medium)

**Claim:** Skeptical/negative finding on HRV recoverability: even with signal-favorable finger-contact PPG (not contactless webcam rPPG), while most derived HRV parameters correlate strongly with ECG (14 of 16 parameters, r>0.7, p<.001), only 7 of 16 (AVNN, TP, VLF, LF, HF, nLF, nHF) fall within formally acceptable Bland-Altman agreement limits, and several time-domain metrics including RMSSD fail agreement despite the high correlation — showing that strong correlation alone does not establish clinical-grade agreement, a caution that applies at least as strongly to harder, contactless webcam rPPG.

**Evidence:** Claim 16, vote 2-1 (split). Directly responsive to the research brief's explicit request for skeptical/negative HRV findings, but note this study used transmissive finger-on-lens smartphone PPG, not remote/webcam rPPG — an important scope caveat.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC4309304/


### 8. [3-0] (confidence: low)

**Claim:** For camera-based respiration, only a narrow algorithmic finding survived verification: of six benchmarked chest/abdomen motion-extraction combinations (2 motion estimators [cross-correlation, optical flow] x 3 spatial representations [single combined 1D profile, multiple 1D profiles, 2D profile]), combinations using a single combined 1D correlation profile perform clearly worse than those using multiple 1D or 2D profiles. No verified breaths-per-minute accuracy-vs-chest-belt/RIP number survived this pass (the specific optical-flow accuracy claim, 2.1 bpm daylight / 4.4 bpm IR, was refuted at 1-2), and no face-derived/RSA-based respiration claim survived at all.

**Evidence:** Claim 17, vote 3-0, but scope is very narrow (algorithm architecture, not accuracy vs. gold-standard) and the topic's core accuracy question (motion vs. RSA/face-derived respiration, degradation with movement/clothing/posture) has no surviving quantitative claims.

**Sources:** https://iopscience.iop.org/article/10.1088/1361-6579/ac5b49


### 9. [3-0] (confidence: medium)

**Claim:** rPPG heart-rate accuracy is significantly worse for participants with higher (darker) Fitzpatrick skin type scores (exp(β)=1.17, p<.001), consistent with the known physical mechanism of increased melanin light absorption reducing the blood-volume-pulse signal, but this disparity is greatly reduced under stronger illumination: the HR-error gap between Fitzpatrick type 1 and type 5 drops from ~2.25 bpm to ~0.21 bpm at luminance ≥30.

**Evidence:** Claim 15, vote 3-0, single primary source (Woelk et al. 2026, n=77) but large, rigorous, and directly quantifies both the disparity and a mitigation (illumination).

**Sources:** https://link.springer.com/article/10.3758/s13428-026-02953-x

## Refuted claims (do not use)

1. {"claim":"On the PURE dataset benchmark, RhythmMamba achieves the lowest heart-rate error of any compared method, with MAE of 0.23 bpm and RMSE of 0.34 bpm.","vote":"0-3","source":"https://arxiv.org/pdf/2404.06483"}
2. {"claim":"SDNN showed a smaller but still nonzero pooled absolute standardized error of 0.134 (95% CI: 0.014 to 0.255) between PPG-derived and ECG-derived measures, with zero heterogeneity across studies (I2=0%).","vote":"1-2","source":"https://pubmed.ncbi.nlm.nih.gov/42655500/"}
3. {"claim":"vPPG-derived SDNN showed strong agreement with ECG-derived SDNN: MAE 3.5 ms (11.0% relative) and RMSE 4.5 ms (15.7%), Pearson r = 0.98 (p < 0.001).","vote":"0-3","source":"https://www.medrxiv.org/content/10.1101/2025.02.13.25322028v1.full"}
4. {"claim":"vPPG-derived lnRMSSD showed weaker agreement than SDNN with ECG: MAE 0.24 (7.3% relative), RMSE 0.31 (9.9%), Pearson r = 0.88 (p < 0.001).","vote":"0-3","source":"https://www.medrxiv.org/content/10.1101/2025.02.13.25322028v1.full"}
5. {"claim":"The camera-derived HRV values exhibited a systematic overestimation bias relative to ECG, particularly at low HRV values, per Bland-Altman analysis.","vote":"0-3","source":"https://www.medrxiv.org/content/10.1101/2025.02.13.25322028v1.full"}
6. {"claim":"The study used an unfixed camera frame rate of only 20-30 fps and argued this was adequate for HRV extraction (above Nyquist rate) only after resampling/upsampling the signal to 800 Hz via cubic spline interpolation.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC4309304/"}
7. {"claim":"The recommended optical-flow method with multiple 1D vertical profiles (OF-M1D) achieved a mean absolute error of 2.1 bpm in daylight conditions and 4.4 bpm in night/IR conditions, evaluated on a programmable respiratory phantom.","vote":"1-2","source":"https://iopscience.iop.org/article/10.1088/1361-6579/ac5b49"}

## Open questions

1. Has anyone validated rPPG/HRV/respiration accuracy specifically on WebRTC/MediaRecorder-captured, adaptively-bitrate-encoded browser video (as opposed to post-hoc re-encoded benchmark clips), and what is the actual real-world bitrate/CRF floor at which browser-based rPPG becomes unusable?
2. Given HRV's poor individual-level reliability (even finger-contact PPG fails Bland-Altman agreement on RMSSD, and webcam SDNN/RMSSD error is ~11ms), is any camera-derived HRV metric defensible for individual-level research conclusions, or should the platform restrict itself to group-level/relative-change HRV designs?
3. Why did no claims survive verification on face/expression-recognition demographic bias (Rhue, Gender Shades, Nagpal), eye-tracking bias from eyewear/makeup/iris color, or speech-emotion-recognition bias — is this a genuine gap in the peer-reviewed literature, or a gap in this pass's search/sourcing that warrants a dedicated follow-up research pass?
4. What is the actual accuracy of camera-derived respiration rate versus chest-belt/RIP or spirometry in realistic seated-at-desk, webcam framing (the platform's actual use case), and how does it compare between chest-motion tracking and face-derived RSA/amplitude-modulation approaches — this remains essentially unanswered after verification removed the only quantitative accuracy claim.

## Caveats

(1) Coverage gap: of Topic E's four requested sub-areas (rPPG/skin-tone bias, face-detection/expression-recognition demographic bias, webcam eye-tracking bias from glasses/makeup/iris color/eyelid shape, speech-emotion-recognition bias by gender/age/accent), only the rPPG/skin-tone sub-area produced claims that survived 3-vote verification — no claims about Rhue (2018), Buolamwini & Gebru Gender Shades, Nagpal et al. 2019, eye-tracking eyewear/makeup/iris effects, or speech-emotion bias survived. This is an evidence gap in this verification pass, not evidence that no disparity exists in those areas. (2) Topic C (respiration) is similarly under-evidenced: the one narrow surviving claim addresses motion-extraction algorithm architecture only, not accuracy vs. chest-belt/RIP/spirometry/capnography, degradation with movement/clothing/posture, or the RSA/face-derived-respiration comparison the brief asked for; the specific accuracy number that would have answered this was refuted (1-2 vote). (3) A single very recent paper (Woelk et al. 2026, Behavior Research Methods) supplies the strongest evidence for HR-in-the-wild accuracy, HRV group-vs-individual reliability, and skin-tone bias mitigation by illumination — these findings are internally consistent and unanimously verified, but not yet independently replicated by a second study. (4) Two claims (HRV meta-analysis pooled error, smartphone-PPG Bland-Altman) survived only 2-1 split adversarial votes, indicating some verifier disagreement; treat their specific numbers as more tentative than the unanimous (3-0) findings. (5) Several intuitively-plausible claims were explicitly refuted by 3-vote verification and must NOT be cited even though they matched prior expectations: strong webcam SDNN/RMSSD agreement with ECG (r=.98), systematic HRV overestimation bias, RhythmMamba as SOTA on PURE, and 20-30fps being adequate for HRV after upsampling. (6) The Gudi et al. 2020 compression study (arXiv:2012.15846) is ~5-6 years old in a fast-moving field; while its qualitative conclusion (compression destroys the subtle pulsatile color signal) is architecture-independent and likely still holds, its specific codec/bitrate numbers may not reflect newer encoders or WebRTC-specific adaptive-bitrate behavior, which nothing in this pass tested directly. (7) The HRV meta-analysis (pooled error 0.188) mixes heterogeneous PPG device types/modalities, not exclusively webcam rPPG, so it should not be read as a webcam-specific error bound.

## All sources

- {"url":"https://arxiv.org/pdf/2210.00716","quality":"primary","angle":"rPPG heart-rate accuracy benchmarks","claimCount":5}
- {"url":"https://proceedings.neurips.cc/paper_files/paper/2023/hash/d7d0d548a6317407e02230f15ce75817-Abstract-Datasets_and_Benchmarks.html","quality":"primary","angle":"rPPG heart-rate accuracy benchmarks","claimCount":4}
- {"url":"https://github.com/ubicomplab/rPPG-Toolbox","quality":"primary","angle":"rPPG heart-rate accuracy benchmarks","claimCount":5}
- {"url":"https://github.com/ubicomplab/rPPG-Toolbox/blob/main/README.md?plain=1","quality":"primary","angle":"rPPG heart-rate accuracy benchmarks","claimCount":4}
- {"url":"https://arxiv.org/pdf/2404.06483","quality":"primary","angle":"rPPG heart-rate accuracy benchmarks","claimCount":5}
- {"url":"https://www.semanticscholar.org/paper/rPPG-Toolbox:-Deep-Remote-PPG-Toolbox-Liu-Narayanswamy/268dba9d96f5eaf5f0c71aad1f9e2c534e5f427e","quality":"unreliable","angle":"rPPG heart-rate accuracy benchmarks","claimCount":0}
- {"url":"https://pubmed.ncbi.nlm.nih.gov/42655500/","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":4}
- {"url":"https://www.medrxiv.org/content/10.1101/2025.02.13.25322028v1.full","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":5}
- {"url":"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12473955/","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":5}
- {"url":"https://arxiv.org/pdf/2012.15846","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":5}
- {"url":"https://link.springer.com/article/10.3758/s13428-026-02953-x","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC4309304/","quality":"primary","angle":"HRV recoverability and skepticism","claimCount":5}
- {"url":"https://iopscience.iop.org/article/10.1088/1361-6579/ac5b49","quality":"primary","angle":"Camera-based respiration accuracy","claimCount":5}
- {"url":"https://www.mdpi.com/2076-3417/15/7/3422","quality":"unreliable","angle":"Camera-based respiration accuracy","claimCount":0}
- {"url":"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9267568/","quality":"primary","angle":"Camera-based respiration accuracy","claimCount":5}
- {"url":"https://doi.org/10.3390/s23073387","quality":"primary","angle":"Camera-based respiration accuracy","claimCount":5}
- {"url":"https://library.imaging.org/ei/articles/36/10/IPAS-248","quality":"primary","angle":"Compression and frame-rate degradation of rPPG","claimCount":4}
- {"url":"https://www.sciencedirect.com/science/article/abs/pii/S1746809424015039","quality":"unreliable","angle":"Compression and frame-rate degradation of rPPG","claimCount":0}
- {"url":"https://arxiv.org/html/1907.11921","quality":"primary","angle":"Compression and frame-rate degradation of rPPG","claimCount":5}
- {"url":"https://www.researchgate.net/publication/331083505_Physiological_Signal_Preserving_Video_Compression_for_Remote_Photoplethysmography","quality":"unreliable","angle":"Compression and frame-rate degradation of rPPG","claimCount":0}
- {"url":"https://www.nature.com/articles/s41746-025-01973-9","quality":"primary","angle":"Skin-tone/melanin bias in rPPG","claimCount":5}
- {"url":"https://www.medrxiv.org/content/10.1101/2025.10.13.25337878.full.pdf","quality":"primary","angle":"Skin-tone/melanin bias in rPPG","claimCount":5}
- {"url":"https://www.nejm.org/doi/full/10.1056/NEJMc2029240","quality":"unreliable","angle":"Skin-tone/melanin bias in rPPG","claimCount":0}
- {"url":"https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3281765","quality":"primary","angle":"Demographic bias in face, gaze, and speech sensing","claimCount":5}
- {"url":"https://en.wikipedia.org/wiki/Joy_Buolamwini","quality":"secondary","angle":"Demographic bias in face, gaze, and speech sensing","claimCount":5}
- {"url":"https://arxiv.org/pdf/2112.06522","quality":"primary","angle":"Demographic bias in face, gaze, and speech sensing","claimCount":4}
- {"url":"https://arxiv.org/pdf/2507.12580","quality":"primary","angle":"Demographic bias in face, gaze, and speech sensing","claimCount":5}
