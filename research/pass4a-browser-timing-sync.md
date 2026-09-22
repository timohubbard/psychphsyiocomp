# Pass 4a: Browser Timing APIs & Web Experiment Sync Accuracy (retry of 3b Topic D)

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection). Prior passes already established: gaze metric definitions (Holmqvist taxonomy), heatmap/scanpath methods, and LSL's high-level sync architecture. This pass failed last time to produce any verified claims on the two hardest topics — retry with narrower scope. Prefer peer-reviewed methods papers and official technical/API documentation (MDN, W3C specs).

TOPIC A — BROWSER-NATIVE TIMING APIS FOR MULTIMODAL SYNC. performance.now() versus Date.now(): which is monotonic, which is subject to system clock adjustment, and their documented resolution/precision. Timer resolution clamping and jitter introduced as a Spectre/timing-attack mitigation in Chrome, Firefox and Safari — cite the actual clamped resolution values (e.g. Chrome's ~100 microseconds to 5 microseconds cross-origin-isolated, Firefox's 1-2ms, Safari's ~1ms) and how/whether they can be relaxed (Cross-Origin-Isolation headers). requestAnimationFrame timing versus requestVideoFrameCallback for obtaining per-frame video presentation timestamps from a <video> or camera MediaStreamTrack — cite the W3C/WHATWG spec text defining what timestamp each callback receives. MediaStreamTrack and getUserMedia frame timestamps — what timestamp metadata, if any, is exposed per video frame in the browser (e.g. via WebCodecs VideoFrame.timestamp, or captureStream). The WebAudio AudioContext clock (currentTime) — its relationship to and drift from the system/performance clock, and published measurements of that drift over a session. How to align an audio stream's AudioContext-clock timestamps with a video stream's rAF/rVFC timestamps in the same browser tab — cite any concrete engineering writeups, W3C Media Timing / Media Synchronization explainer documents, or academic papers proposing a solution.

TOPIC B — PUBLISHED WEB EXPERIMENT TIMING ACCURACY. The specific line of empirical papers benchmarking stimulus-presentation and response-timing accuracy of in-browser experiment software: Bridges, Pitiot, MacAskill & Peirce "The timing mega-study" (2020, PeerJ) comparing PsychoPy/PsychoJS, jsPsych, Lab.js, Gorilla, Testable, and E-Prime — report the actual measured millisecond error/variability figures for each platform from that paper. Anwyl-Irvine, Dalmaijer, Hodges & Evershed "Realistic precision and accuracy of online experiment platforms, web browsers, and devices" (2021, Behavior Research Methods) — report its measured display and response-time error figures across browsers and devices, including any figures broken out by operating system or browser. Any published guidance from these papers or others on the realistic ceiling for cross-modal (e.g. audio-to-video, or stimulus-to-physiological-signal) synchronization accuracy achievable in an uncontrolled, unsupervised, remote browser session — as opposed to a supervised lab session.

If a specific numeric figure cannot be found in a primary source, say so explicitly rather than omitting the topic — an "unable to verify precise ms figure, but mechanism X is documented" finding is more useful than silence.

---

## Summary

Yes — ready, and here is the synthesis. Topic B (published web-experiment timing accuracy) is well-supported: the Bridges et al. (2020, PeerJ) and Anwyl-Irvine et al. (2021, BRM) papers converge on browser-based platforms being measurably less precise than lab software across display, response, and especially audio-visual-sync timing, with concrete per-platform millisecond figures for both display duration and response-time error. Topic A (browser-native timing APIs) is partially confirmed: performance.now()'s monotonicity and Spectre-driven coarsening (100µs default / 5µs cross-origin-isolated) are solidly documented in the W3C hr-time-3 spec and MDN, and the Web Audio currentTime clock's separateness from Date.now() and its render-quantum granularity (~2.9ms/2.7ms) are equally well documented, including Firefox's specific fingerprinting-driven rounding of that clock. However several sub-questions in Topic A — Firefox/Safari's exact performance.now() clamp values, WebCodecs VideoFrame.timestamp/captureStream frame-timestamp semantics, published AudioContext-clock drift measurements, and any concrete audio/video alignment engineering writeup or W3C explainer — were not found as verified primary-source claims in this pass and should be treated as open/unresolved rather than confirmed. The realistic ceiling for cross-modal sync in unsupervised remote sessions is best evidenced indirectly: ~80ms average response-time recording lag online (vs. 8–67ms in supervised lab hardware) and the qualitative, repeatedly-confirmed finding that audio-visual synchrony is "the least precise aspect" of browser experiments — but no specific millisecond figure for AV-sync error itself survived verification (a specific numeric AV-sync claim was in fact refuted 0-3), so that ceiling should be stated qualitatively, not quantitatively.

## Findings

### 1. [3-0 (x4 merged claims)] (confidence: high)

**Claim:** Browser-based/online experiment platforms deliver measurably worse timing precision than lab-based desktop software across all measured dimensions (display, response, audio-visual sync), and audio-visual synchrony is specifically the weakest, most OS/browser-variable aspect of browser-based timing — the closest documented proxy for a 'ceiling' on cross-modal sync in unsupervised remote sessions. No online system could reliably deliver audio with precisely-timed onset as of the study.

**Evidence:** Paper's own abstract/discussion, quoted verbatim across 4 independently-verified sub-claims: 'Online studies did not deliver the same level of precision as lab-based systems, with slightly more variability in all measurements... especially in audio-visual synchrony which is the least precise aspect'; 'No online system can yet provide audio stimuli with precisely timed onsets.'

**Sources:** https://doi.org/10.7717/peerj.9414 | https://pmc.ncbi.nlm.nih.gov/articles/PMC7512138/


### 2. [3-0 (x3 merged claims)] (confidence: high)

**Claim:** Among browser platforms, PsychoPy/PsychoJS gives the best response-time precision (<3.5ms in every browser; inter-trial variability <4ms on every OS/browser combo, 0.2ms on Ubuntu/Chrome). Most other packages stay under ~10ms: jsPsych and Testable ~3.2–8.4ms inter-trial variability, Gorilla <6ms, Lab.js up to 8.44ms.

**Evidence:** Direct paper quotes: 'most of the packages achieved precision at least under 10 ms in all browsers, with PsychoPy achieving a precision under 3.5 ms in all'; 'PsychoPy... under 4 ms on every browser/OS combination... 0.2 ms inter-trial variability for Ubuntu Chrome'; jsPsych 3.2-8.4ms, Gorilla <6ms per Results text.

**Sources:** https://doi.org/10.7717/peerj.9414 | https://pmc.ncbi.nlm.nih.gov/articles/PMC7512138/


### 3. [2-1 (split)] (confidence: medium)

**Claim:** Lab-based (non-browser) platforms — Psychtoolbox, PsychoPy desktop, NBS Presentation, E-Prime — achieve mean timing precision under 1ms across visual, audio and response measures, i.e. the sub-1ms precision ceiling against which browser platforms are benchmarked.

**Evidence:** Paper quote: 'Psychtoolbox, PsychoPy, Presentation and E-Prime provided the best timing, all with mean precision under 1 millisecond across the visual, audio and response measures.' Split vote reflects one verifier flagging the claim's added 'ceiling' framing as an interpretive gloss rather than a direct quote.

**Sources:** https://doi.org/10.7717/peerj.9414


### 4. [3-0 (x2 merged claims)] (confidence: high)

**Claim:** Display (stimulus-duration) timing error varies substantially by browser: Chrome ~11.5ms mean delay (least variance, 'best all-round'), Edge ~18.7ms, Firefox ~22.6ms (largest variance across devices), Safari ~30.0ms (highest of the three major browsers).

**Evidence:** Paper Table 1/Figure 5 figures verified directly: Chrome 11.50ms, Edge 18.72ms, Firefox 22.58ms, Safari 30.02ms mean Visual Duration Delay; text states 'Firefox showed the largest amount of variance out of all the browsers... The best all-round browser was Chrome—it showed the least variance across devices and platforms.'

**Sources:** https://doi.org/10.3758/s13428-020-01501-5


### 5. [3-0] (confidence: high)

**Claim:** Lab.js was the most precise browser-based platform for visual display timing specifically (lowest SD, mean error 9.8ms, max delay 16.49ms ≈ one frame at 60Hz).

**Evidence:** Paper Table 1 and text quote verified verbatim: 'had a maximum delay of 16.49 ms (one frame at 60 Hz) and an average of 9.8 ms' with lowest SD (4.69ms) among Gorilla/Lab.js/PsychoJS/jsPsych.

**Sources:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8367876/


### 6. [3-0] (confidence: high)

**Claim:** Response-time recording delay averages ~80ms across online platforms (Gorilla 78.5ms, Lab.js 71.3ms, PsychoJS 82.3ms, jsPsych 87.4ms) — larger than lab-hardware delays of 8–67ms — documenting a realistic stimulus-to-response timing floor for unsupervised/remote browser sessions vs. supervised lab sessions.

**Evidence:** Paper quote verified verbatim: 'particularly noteworthy are the larger delays (compared to lab-based software set-ups) in the recording of response times, which on average lag 80 ms', corroborated by per-platform Table 2 figures (78.53/71.33/82.28/87.40ms) and contrast with Bridges et al.'s 8-67ms lab button-box figures.

**Sources:** https://doi.org/10.3758/s13428-020-01501-5


### 7. [3-0] (confidence: high)

**Claim:** These figures derive from a large primary empirical dataset (>110,000 trials, Black Box Toolkit hardware validation, 10 software packages incl. PsychoPy, E-Prime, Presentation, Psychtoolbox, OpenSesame, Expyriment, Gorilla, jsPsych, Lab.js, Testable, across Windows/macOS/Ubuntu and multiple browsers) — supporting the strength assigned to the above findings.

**Evidence:** Abstract verified verbatim via Semantic Scholar/PMC mirror: lists all 10 packages, Black Box Toolkit method, Windows/macOS/Ubuntu plus browser testing, and 'The results, from over 110,000 trials, highlight the wide range of timing qualities...'

**Sources:** https://doi.org/10.7717/peerj.9414


### 8. [3-0 (x2 merged claims)] (confidence: high)

**Claim:** performance.now() is spec-guaranteed monotonic (relative to Performance.timeOrigin; two same-origin readings can never show a negative difference) and is NOT subject to system-clock adjustment, unlike Date.now() which is tied to system/Unix-epoch time and is subject to clock skew/adjustment (NTP sync, DST, manual changes).

**Evidence:** MDN: 'performance.now()... is relative to the timeOrigin property which is a monotonic clock: its current time never decreases and isn't subject to adjustments.' W3C hr-time-3 normative text: 'The difference between any two chronologically recorded time values returned from the now() method MUST never be negative if the two time values have the same time origin,' contrasted with the spec's own note that wall-clock time 'may not always be monotonically increasing.'

**Sources:** https://developer.mozilla.org/en-US/docs/Web/API/Performance/now | https://www.w3.org/TR/hr-time-3/


### 9. [3-0 (x2 merged claims)] (confidence: high)

**Claim:** performance.now() resolution is deliberately coarsened as a documented Spectre-class timing-attack / fingerprinting mitigation: 100 microseconds by default (non-cross-origin-isolated contexts), relaxed to 5 microseconds when the page is cross-origin isolated (COOP/COEP headers giving crossOriginIsolatedCapability = true). This is a normative requirement in the W3C hr-time-3 spec's 'coarsen time' algorithm, motivated explicitly by cache-timing and speculative-execution (Spectre) attacks.

**Evidence:** MDN verified verbatim: 'Resolution in isolated contexts: 5 microseconds. Resolution in non-isolated contexts: 100 microseconds.' W3C spec normative algorithm: 'Let time resolution be 100 microseconds... If crossOriginIsolatedCapability is true, set time resolution to be 5 microseconds,' with Security Considerations citing cache attacks and speculative-execution exploits.

**Sources:** https://developer.mozilla.org/en-US/docs/Web/API/Performance/now | https://www.w3.org/TR/hr-time-3/


### 10. [3-0] (confidence: high)

**Claim:** Firefox applies its own fingerprinting-driven rounding specifically to AudioContext.currentTime (not directly confirmed for performance.now() in this pass): 1ms default (privacy.reduceTimerPrecision), 0.02ms in cross-origin-isolated contexts, 16.667ms+ with privacy.resistFingerprinting enabled. Chrome and Safari add no equivalent extra rounding to currentTime since they derive it from audio sample-frame counts.

**Evidence:** MDN verified verbatim: 'Default settings (privacy.reduceTimerPrecision enabled): Rounding interval: 1 ms, or 0.02 ms in cross-origin-isolated contexts' and 'With privacy.resistFingerprinting enabled: Rounding interval: 16.667 ms or... whichever is larger'; same page notes Chrome/Safari apply no such extra rounding.

**Sources:** https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/currentTime


### 11. [3-0 (x2 merged claims)] (confidence: high)

**Claim:** The WebAudio AudioContext.currentTime clock is a distinct timeline, explicitly documented as separate from and not derived from/synced to the system clock (Date.now()). It does not advance continuously but jumps in discrete increments of one render quantum (128 samples): ~2.9ms at 44.1kHz, ~2.7ms at 48kHz — so repeated reads within a block return an identical value.

**Evidence:** MDN verified verbatim: 'This audio timeline is separate from the system clock used by Date.now().' and 'this value advances in increments of one audio rendering block, or render quantum... approximately 2.9 ms at a sampleRate of 44.1 kHz, or 2.7 ms at 48 kHz. Repeated reads can return the same value until the next block is processed.' Corroborated by W3C Web Audio spec's own currentTime definition.

**Sources:** https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/currentTime


### 12. [3-0] (confidence: high)

**Claim:** requestVideoFrameCallback()'s VideoFrameCallbackMetadata exposes mediaTime — the frame's presentation timestamp (PTS) on the video element's own video.currentTime media timeline — distinct from the same metadata's presentationTime/expectedDisplayTime fields, which are wall-clock DOMHighResTimeStamp values on the Performance timeline. This gives script both a media-timeline and a wall-clock timestamp per video frame.

**Evidence:** WICG spec verified verbatim: mediaTime defined as 'The media presentation timestamp (PTS) in seconds of the frame presented (e.g. its timestamp on the video.currentTime timeline).' Spec separately defines presentationTime/expectedDisplayTime as Performance/wall-clock DOMHighResTimeStamp values.

**Sources:** https://wicg.github.io/video-rvfc/


### 13. [2-1 (split)] (confidence: medium)

**Claim:** rVFC callbacks are specified to fire immediately before rAF callbacks within the same event-loop turn, with both guaranteed to reflect on screen at the same next v-sync — the documented ordering/timing relationship between the two per-frame callback APIs.

**Evidence:** WICG spec Introduction verified verbatim: 'are executed immediately before existing window.requestAnimationFrame() callbacks. Changes made from within both callback types within the same turn of the event loop will be visible on screen at the same time, with the next v-sync.' Split vote reflects a minor clause-attachment paraphrase flagged by one verifier as non-substantive.

**Sources:** https://wicg.github.io/video-rvfc/

## Refuted claims (do not use)

1. {"claim":"Keyboard response-time error on the Gorilla platform was approximately 80 ms and was consistent across different operating systems, indicating response-timing offsets on this order are a realistic floor for browser-based RT measurement regardless of OS.","vote":"0-3","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8367876/"}
2. {"claim":"Auditory (sound) presentation timing is substantially less accurate than visual timing in browser-based experiments, with average auditory delays reaching the hundreds-of-milliseconds range rather than the tens-of-milliseconds range seen for visual stimuli — directly bearing on the realistic ceiling for audio-to-video/cross-modal sync in unsupervised remote sessions.","vote":"1-2","source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8367876/"}
3. {"claim":"Audio-visual synchrony error in browser-based platforms varies drastically by browser/OS combination and can exceed 100 ms in some cases, giving a concrete empirical bound on cross-modal (audio-to-video) sync accuracy achievable in an uncontrolled browser session — e.g. Gorilla showed inter-trial AV-sync variability over 10 ms in five browsers tested and lags exceeding 100 ms in three cases, while Lab.js's AV-sync lag ranged from about -4.9 ms to 198.05 ms across OS/browser pairings.","vote":"0-3","source":"https://doi.org/10.7717/peerj.9414"}

## Open questions

1. What are the actual documented performance.now() clamp/resolution values specifically for Firefox (~1-2ms) and Safari (~1ms), as opposed to the generic W3C spec baseline (100µs/5µs) confirmed here? Only Firefox's analogous AudioContext.currentTime rounding was verified this pass, not performance.now() itself.
2. What timestamp metadata (if any) does WebCodecs VideoFrame.timestamp or MediaStreamTrack/captureStream expose per video frame, and how does it relate to rVFC's mediaTime/presentationTime? No claim on this was found/verified in this pass.
3. Are there any published empirical measurements of AudioContext-clock drift relative to performance.now()/system clock over the course of a session (e.g., minutes to hours)? None were found; only the static render-quantum granularity mechanism was confirmed.
4. Is there a concrete engineering writeup, W3C Media Timing/Media Synchronization explainer, or peer-reviewed method for aligning AudioContext-clock (currentTime) timestamps with rAF/rVFC video timestamps in the same tab? No such primary/peer-reviewed source was confirmed this pass despite being explicitly asked for.

## Caveats

Time-sensitivity: the two core Topic-B papers are from 2020 (Bridges et al., PeerJ) and 2021 (Anwyl-Irvine et al., BRM) — browser engines and JS timing behavior have continued to evolve since, and the authors themselves caution results may not generalize to arbitrary home hardware/OS combinations; treat the specific ms figures as historical benchmarks of those platform versions, not guaranteed current-day numbers. Split-vote (2-1) findings — the sub-1ms lab-platform ceiling and the rVFC-before-rAF v-sync ordering claim — are somewhat weaker than the unanimous 3-0 findings and warrant independent re-verification if load-bearing for design decisions. Several sub-questions in Topic A explicitly did NOT survive verification and have no confirmed numeric answer in this pass (see open questions) — per the task's own instruction, this is reported explicitly rather than silently omitted. A specific numeric claim about audio-visual-sync error magnitude (e.g., Gorilla >100ms, Lab.js up to ~198ms) was checked and REFUTED (0-3 vote), as was a claim that auditory delays reach "hundreds of ms" and a claim that Gorilla's ~80ms RT error is OS-consistent — so while the qualitative finding "AV sync is the least precise aspect" is well-confirmed, no specific millisecond ceiling for AV-sync error itself should be cited as verified. All verifier passes in this research operated with the WebSearch tool budget exhausted, so cross-checking relied on direct primary-source WebFetch rather than broader adversarial web search — a structural limitation across every claim above, though primary-source fetch is generally the stronger verification method for spec/paper-text claims.

## All sources

- {"url":"https://doi.org/10.7717/peerj.9414","quality":"primary","angle":"b","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC7512138/","quality":"primary","angle":"b","claimCount":5}
- {"url":"https://doi.org/10.3758/s13428-020-01501-5","quality":"primary","angle":"b","claimCount":5}
- {"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC8367876/","quality":"primary","angle":"b","claimCount":4}
- {"url":"https://developer.mozilla.org/en-US/docs/Web/API/Performance/now","quality":"primary","angle":"c","claimCount":3}
- {"url":"https://www.w3.org/TR/hr-time-3/","quality":"primary","angle":"c","claimCount":4}
- {"url":"https://wicg.github.io/video-rvfc/","quality":"primary","angle":"c","claimCount":5}
- {"url":"https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/currentTime","quality":"primary","angle":"c","claimCount":5}
