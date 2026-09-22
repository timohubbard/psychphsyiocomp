# iMotions rebuild — deep research index

Research project: rebuild an iMotions-equivalent webcam-based human-behavior
research platform (browser-first remote data collection, secondary in-lab
desktop mode). Modalities: webcam eye tracking, facial expression analysis,
voice analysis, camera-based respiration. Deliverable: both a
functional/methodological spec and an engineering build guide.

**Research phase is complete.** The consolidated, synthesized deliverable is
`../REPORT.md`. Everything in this folder is raw backing material — 10
adversarially-verified deep-research passes (~1,000 search/fetch/verify
agents total), each with full citations. Consult these when you need the
underlying quote, source URL, or vote count behind a claim in the report.

## Passes

| # | File | Topic | Status |
|---|---|---|---|
| 1 | `pass1-imotions-teardown-gaze-validation.md` | iMotions module lineup, supplier attribution, Event API/LSL, Online→Lab export, webcam gaze accuracy vs. infrared | ✅ Complete (16 findings) |
| 2 | `pass2-facial-au-voice-validation.md` | Facial AU detection vs. FACS coders, AU→emotion mapping validity (Barrett et al.), commercial classifier benchmarks, SER benchmarks | ✅ Complete (7 findings) |
| 3a | `pass3a-physiology-bias.md` | rPPG HR accuracy, HRV recoverability, camera respiration, video compression, skin-tone/Fitzpatrick bias | ✅ Complete (9 findings, 7 refuted) |
| 3b | `pass3b-analysis-pipeline.md` | Gaze metric definitions, fixation detection, heatmaps, scanpaths, dynamic AOIs | ⚠️ Partial (Topics A-C solid; D/E gaps filled by pass 4a/4b) |
| 3c | `pass3c-study-design-participants.md` | Calibration/viewing-distance recovery, jsPsych defaults, Kaduk vendor accuracy study, getUserMedia audio | ⚠️ Partial (Topic A solid; C/D/E gaps filled by pass 4b) |
| 3d | `pass3d-legal-compliance-PARTIAL.md` | Initial legal pass | ❌ Synthesis failed (superseded by 4c/4d) |
| 4a | `pass4a-browser-timing-sync.md` | Browser timing APIs, Bridges/Anwyl-Irvine web-experiment timing accuracy | ✅ Complete (13 findings, retry of 3b Topic D) |
| 4b | `pass4b-data-quality-power-stats.md` | Exclusion thresholds, power/attrition/panel quality, epoching/stats, BIDS/XDF export | ✅ Complete (13 findings, retry of 3b Topic E + 3c C/D/E) |
| 4c | `pass4c-legal-retry-aiact-commonrule.md` | EU AI Act Art 5(1)(f) detail, Recital 44, Common Rule/IRB mechanics | ✅ Complete (15 findings, retry of 3d) |
| 4d | `pass4d-bipa-cubi-INCOMPLETE.md` | Illinois BIPA, Texas CUBI, WA MHMDA | ❌ **Incomplete** — hit fetch rate limit 3x; 4 verified + 17 unverified raw leads (untested, not refuted) |

## Known permanent gaps (after 3 attempts each)

- **BIPA/CUBI enforcement mechanics**: exact settlement figures (Facebook
  $650M etc.), the Cothron v. White Castle per-scan holding, and the SB 2979
  amendment's precise effect were never adversarially verified — only raw
  leads from FindLaw/JD Supra/Wikipedia in pass 4d. Cross-check before citing
  as fact in anything client-facing.
- **EU AI Act Annex III high-risk classification** for emotion recognition
  *outside* the workplace/education prohibition (i.e. the research-only use
  case) — not confirmed either way.
- **GDPR Art 30 (records of processing) / Art 35 DPIA "nine criteria"** for
  biometric monitoring — not confirmed.
- **Controller/processor allocation** for a platform serving both academic
  and commercial clients — not confirmed.
- **A retention-schedule design reconciling BIPA's 3-year cap with GDPR
  storage limitation** — no published guidance found.
- **On-device/edge inference as a recognized DPA/regulator-endorsed
  mitigation** — not confirmed (architecturally sound regardless, just not
  found as citable regulator guidance).
- Face/expression demographic bias (Rhue 2018, Gender Shades), eye-tracking
  bias (glasses/makeup/iris color), SER bias by accent — asked for twice,
  never survived verification.
- Formal multimodal-behavioral-data export standard — confirmed *not to
  exist*; BIDS/XDF are analogues to borrow structure from, not a ready-made
  spec.

_Last updated: 2026-09-21._

## Local source PDFs

`sources/` holds a few full-text PDFs subagents fetched during research
(kept because they're cited repeatedly and re-fetching is wasteful):
`holmqvist.pdf` (the eye-tracking methods textbook), `gazealytics.pdf`,
`eyescrollr.pdf`, `yk2021.pdf`. Not an exhaustive source archive — most
citations in the report are URLs only; see each pass file's "All sources"
section for the full list.
