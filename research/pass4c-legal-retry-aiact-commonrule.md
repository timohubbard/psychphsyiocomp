# Pass 4c: Legal Retry — AI Act Art 5(1)(f) Detail, Common Rule, MHMDA (retry of 3d Topics A/C partial, D still gap)

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection; captures participant webcam video and microphone audio; derives eye gaze, facial expressions/emotion, voice/vocal emotion, respiration). A prior pass on this topic partially completed: it CONFIRMED (unmerged, no adversarial refutation) the following and you should NOT re-research them — take them as given: EU AI Act Art 3(39) defines "emotion recognition system" by reference to biometric data; Recital 18 excludes physical states like pain/fatigue and mere detection of readily-apparent expressions unless used to infer emotion; the Commission published non-binding prohibited-practices guidelines 4 Feb 2025; the AI Act entered into force 1 Aug 2024; GDPR Art 9(1) prohibits processing special-category data including biometric data used for identification; Art 9(2)(a) explicit-consent and 9(2)(j) scientific-research exceptions exist; GDPR Art 4(14) defines biometric data with the identification-purpose qualifier as a DEFINING element (not merely a limitation); GDPR Art 4(15) defines health data broadly; the EDPB's Video Devices Guidelines 3/2019 state raw video is NOT itself Art 9 biometric data unless specifically processed to identify someone, and sets a 3-part test (nature/means/purpose, with purpose=identification being decisive).

This pass covers everything NOT yet researched. Prefer official regulatory texts, regulator guidance, and legal scholarship. Cite article/section numbers and dates.

TOPIC A — EU AI ACT ARTICLE 5(1)(f) PROHIBITION DETAIL. The exact text and scope of the Article 5(1)(f) prohibition on AI systems inferring emotions in the workplace and education institutions. Its two exceptions (medical reasons, safety reasons) and how narrowly they've been interpreted. Recital 44's stated rationale. Annex III high-risk classification for emotion recognition OUTSIDE the prohibited contexts (i.e. a research/market-research use case, not workplace/education) — is it high-risk, and what obligations follow (Art 50(3) transparency duty to inform exposed persons). The compliance timeline: 2 Feb 2025 (prohibitions effective), 2 Aug 2025 (GPAI/governance), 2 Aug 2026 (general applicability), 2 Aug 2027 (some high-risk). Article 99 penalties for prohibited-practice violations (up to 35M EUR / 7% global turnover). Any 2025-2026 news of AI Act simplification, delay, or "digital omnibus" proposals affecting this timeline.

TOPIC B — US STATE BIOMETRIC PRIVACY LAW, FOCUSED. Illinois BIPA (740 ILCS 14) Section 10: does the "scan of face geometry" definition of biometric identifier cover facial-expression-analysis (not identification) processing, and the statutory photographs/voice-recordings carve-outs. Section 15(a) retention-schedule requirement, 15(b) written-consent requirement, Section 20 statutory damages ($1,000 negligent / $5,000 intentional) and private right of action. The Cothron v. White Castle (Illinois Supreme Court 2023) per-scan-accrual holding and the August 2024 SB 2979 amendment that limited future accrual to one recovery per person. One or two named settlement amounts to size exposure (e.g. Facebook, BNSF, or a more recent 2024-2026 settlement). Texas CUBI (Bus. & Com. Code 503.001) — AG-only enforcement, no private right of action. Washington My Health My Data Act — whether its broad "consumer health data" definition could sweep in inferred emotion or physiological (respiration/heart-rate) data, and its unusual private right of action via the state Consumer Protection Act.

TOPIC C — HUMAN SUBJECTS RESEARCH ETHICS FOR VIDEO/AUDIO RECORDING. Under the US Common Rule (45 CFR 46), why audio/video recording of identifiable participants generally does NOT qualify for exempt review, and which of the 2018 revised Common Rule's exemption categories (list them, e.g. 46.104(d)(1)-(8)) might still apply or not apply to a webcam study. Elements required in informed consent (45 CFR 46.116) as applied to video/audio biometric capture — retention period disclosure, secondary-use/data-sharing disclosure. Whether/how documentation of informed consent can be waived for a remote online study (45 CFR 46.117). De-identification approaches for face video specifically (why blurring alone may not de-identify a person given gait/body/voice cues) and for voice (why voice is itself a biometric identifier resistant to simple anonymization).

TOPIC D — PRIVACY-PRESERVING ARCHITECTURE. On-device/edge/in-browser inference as a data-minimization strategy — is there published guidance (from a DPA, ICO, EDPB, or NIST) recommending or endorsing on-device biometric processing specifically to reduce GDPR/biometric-law exposure? GDPR Article 30 records-of-processing-activities requirement. Article 35 DPIA — the criteria (from Art 35(3) or the WP248/EDPB "nine criteria" guidance) that make biometric monitoring presumptively require a DPIA. Controller vs processor allocation when one platform serves multiple academic/commercial clients each running their own studies. Any concrete published retention-schedule guidance that could simultaneously satisfy BIPA 15(a) ("as soon as reasonably possible, but no later than 3 years") and GDPR storage limitation (Art 5(1)(e), no fixed period but "no longer than necessary").

If a specific detail cannot be found in a primary source, say so explicitly rather than omitting the topic.

---

## Summary

This pass adds substantive detail on EU AI Act Article 5(1)(f) (text, exceptions, Recital 44 rationale, Article 99 penalties) and on U.S. Common Rule informed-consent/exemption mechanics for webcam-based research, plus partial detail on Washington's My Health My Data Act. It produced NO confirmed claims on several topics the task explicitly asked for: Illinois BIPA (Sections 10/15/20, Cothron v. White Castle, SB 2979, settlement sizing), Texas CUBI, AI Act Annex III high-risk classification/Art 50(3) transparency duty for non-workplace emotion recognition, 2025-2026 "digital omnibus"/delay news, on-device-inference privacy guidance, GDPR Art 30/Art 35 DPIA criteria, controller/processor allocation, and BIPA/GDPR retention-schedule reconciliation -- these gaps are reported explicitly per instructions rather than omitted. Where claims exist, confidence is generally high for the AI Act and Common Rule material (unanimous 3-0 votes, primary-source cross-checks) and medium for the Washington MHMDA extensions (split 2-1 votes reflecting interpretive stretches of statutory text to novel physiological/inferred data). Legal research in this domain remains highly time-sensitive: the Commission's Article 5 guidelines (Feb 2025) are non-binding, and several 2025-2026 developments (omnibus simplification, BIPA damages litigation, Annex III implementing guidance) could not be verified this pass due to search-tool budget exhaustion noted repeatedly by verifiers.

## Findings

### 1. [high] (confidence: high)

**Claim:** AI Act Art 5(1)(f) prohibits placing on the market, putting into service, or using AI systems to infer emotions of a natural person in the workplace and education institutions, with exactly two named exceptions: systems placed on the market strictly for medical reasons or safety reasons (e.g., therapeutic-use systems). No other carve-outs (commercial, research, law-enforcement) appear in the provision.

**Evidence:** Merges claims [13] and [14] (3-0 votes each), cross-checked against EUR-Lex Recital 44 text independently by the verifier.

**Sources:** https://artificialintelligenceact.eu/article/5/ | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689


### 2. [high] (confidence: high)

**Claim:** Recital 44's stated rationale for the Art 5(1)(f) ban has two threads: (1) scientific-validity concerns -- limited reliability, lack of specificity, and limited generalisability of emotion-inference AI, since emotional expression varies across cultures and situations; and (2) risk of detrimental/unfavourable treatment of individuals or whole groups, explicitly tied to the imbalance of power in employment and education settings combined with the intrusive nature of these systems.

**Evidence:** Merges claims [0], [15], [16], [17] -- all 3-0 votes, verified against both EUR-Lex primary text and the artificialintelligenceact.eu companion site with near-verbatim quote matches.

**Sources:** https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689 | https://artificialintelligenceact.eu/recital/44/


### 3. [high] (confidence: high)

**Claim:** Art 99(3) of the AI Act sets the fine tier for prohibited-practice violations (including Art 5(1)(f)) at up to EUR 35,000,000 or, for an undertaking, up to 7% of total worldwide annual turnover for the preceding financial year, whichever is higher -- the Act's top penalty tier, distinct from lower tiers for high-risk/transparency obligations (up to EUR 15M/3%) and for supplying incorrect information (up to EUR 7.5M/1%).

**Evidence:** Claim [18], 3-0 vote, quote matches known primary AI Act text verbatim; verifier could not run live search to check for 2025-2026 amendments but found no evidence of change to Art 99 amounts specifically (only to timelines/high-risk scope reportedly).

**Sources:** https://artificialintelligenceact.eu/article/99/


### 4. [high] (confidence: high)

**Claim:** The Commission's 4 February 2025 prohibited-practices guidelines are explicitly non-binding soft law; only the CJEU has authority to give an authoritative/binding interpretation of the AI Act's prohibitions.

**Evidence:** Claim [5], 3-0 vote, verbatim quote from the Commission's own official announcement page: 'they are non-binding, with authoritative interpretations reserved for the Court of Justice of the European Union (CJEU).' Complements the already-confirmed 4 Feb 2025 publication date [4].

**Sources:** https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act


### 5. [low] (confidence: low)

**Claim:** GAP -- Annex III high-risk classification for emotion-recognition AI used OUTSIDE prohibited workplace/education contexts (e.g., a market-research/behavioral-research use case), and the associated Article 50(3) transparency duty to inform exposed persons, were NOT addressed by any claim that survived verification in this pass.

**Evidence:** No claim in the confirmed set addresses Annex III classification or Art 50(3). This is a direct gap against a topic the task explicitly requested; reported per instructions rather than silently omitted.


### 6. [low] (confidence: low)

**Claim:** GAP -- No confirmed claims this pass addressed 2025-2026 'digital omnibus,' AI Act simplification, or delay proposals affecting the compliance timeline (2 Feb 2025 prohibitions / 2 Aug 2025 GPAI / 2 Aug 2026 general applicability / 2 Aug 2027 some high-risk obligations).

**Evidence:** One verifier explicitly noted being unable to confirm or rule out omnibus-related changes because WebSearch was unavailable (session budget exhausted).


### 7. [high] (confidence: high)

**Claim:** Washington's My Health My Data Act (RCW 19.373.010) defines 'consumer health data' broadly as personal information linked or reasonably linkable to a consumer that identifies past/present/future physical or mental health status, expressly not limited to traditional medical records, and separately defines 'biometric data' (identification-linked, including gait and keystroke patterns) as a narrower, distinct category.

**Evidence:** Merges claims [1] (3-0) and [19] (2-1); both verified by direct fetch of the primary statutory text on the official WA legislature site.

**Sources:** https://app.leg.wa.gov/RCW/default.aspx?cite=19.373.010


### 8. [medium] (confidence: medium)

**Claim:** Within that definition, 'physical or mental health status' expressly includes (v) 'bodily functions, vital signs, symptoms, or measurements' -- vital signs standardly including heart rate and respiratory rate -- and separately (xiii) extends to information 'derived or extrapolated from nonhealth information ... through the use of an algorithm or machine learning.' This makes it plausible, though not judicially settled, that ML-inferred emotional/physiological signals (e.g., respiration, heart rate) computed from webcam video/audio could qualify as regulated 'consumer health data' under MHMDA.

**Evidence:** Merges claims [2] and [3], both verified 2-1 (split votes). Hedged 'could/plausibly' language; the 'emotional state' half rests on inference from adjacent provisions rather than an explicit standalone category; no case law or regulator guidance found applying this to inferred-emotion/webcam data.

**Sources:** https://app.leg.wa.gov/RCW/default.aspx?cite=19.373.010


### 9. [low] (confidence: low)

**Claim:** GAP -- No claims survived verification this pass on Illinois BIPA (740 ILCS 14): the Section 10 'scan of face geometry' definition and its applicability to facial-expression-analysis processing, the photographs/voice-recordings carve-outs, Section 15(a) retention-schedule and 15(b) written-consent requirements, Section 20 statutory damages ($1,000 negligent / $5,000 intentional) and private right of action, Cothron v. White Castle (Ill. Sup. Ct. 2023), the August 2024 SB 2979 amendment, or named settlement amounts to size exposure.

**Evidence:** None of the 22 verified claims touch BIPA. Direct, explicit gap against a major requested topic (Topic B).


### 10. [low] (confidence: low)

**Claim:** GAP -- No claims survived verification this pass on Texas CUBI (Bus. & Com. Code 503.001), including its AG-only enforcement and absence of a private right of action, nor on the Washington MHMDA's private right of action mechanism via the state Consumer Protection Act.

**Evidence:** The MHMDA definitional findings above were confirmed, but the enforcement-mechanism half of Topic B was not covered by any surviving claim.


### 11. [high] (confidence: high)

**Claim:** 45 CFR 46.116(b) requires nine basic elements of informed consent, (b)(1)-(b)(9), including: (b)(5) a statement describing the extent, if any, to which confidentiality of records identifying the subject will be maintained; (b)(8) a statement that participation is voluntary with no penalty for refusal; and (b)(9) one of two required disjunctive statements about future/secondary research use -- either that identifiers might be removed and data reused/distributed for future research without additional consent (if that's a possibility), or that data 'will not be used or distributed for future research studies.' These are the direct regulatory hooks for disclosing retention/confidentiality limits and secondary-use/data-sharing plans in a webcam biometric study's consent form.

**Evidence:** Merges claims [6], [7], [11], [12] (three 3-0 votes and one 2-1 vote), each independently verified against Cornell Law's mirror of the current 2018-revised Common Rule text with near-verbatim quotes.

**Sources:** https://www.ecfr.gov/current/title-45/part-46 | https://www.law.cornell.edu/cfr/text/45/46.116


### 12. [high] (confidence: high)

**Claim:** 45 CFR 46.117(c) permits an IRB to waive the requirement for signed documentation of informed consent (though not the consent process itself) when 'the research presents no more than minimal risk of harm to subjects and involves no procedures for which written consent is normally required outside of the research context' (one of three grounds) -- a plausible regulatory pathway for e-consent/click-through consent in remote/online webcam studies, subject to case-by-case IRB determination of minimal risk.

**Evidence:** Claim [8], 3-0 vote, verbatim quote confirmed against Cornell LII mirror (eCFR itself redirected to a bot-protection page during verification, so the secondary mirror was used as corroboration of the same in-force regulatory text).

**Sources:** https://www.ecfr.gov/current/title-45/part-46 | https://www.law.cornell.edu/cfr/text/45/46.117


### 13. [high] (confidence: high)

**Claim:** Common Rule exemption Categories 2 and 3 (45 CFR 46.104(d)(2) and (d)(3)) share a disjunctive three-pathway structure -- exemption applies if AT LEAST ONE of: (i) subject identity cannot readily be ascertained; (ii) disclosure of responses outside the study would pose no risk of criminal/civil liability or damage to financial standing, employability, educational advancement, or reputation; or (iii) identity is ascertainable but the IRB conducts a 'limited IRB review.' Category 3 (benign behavioral interventions) explicitly contemplates 'audiovisual recording' as a data-collection method for adult subjects. Because these are OR conditions, a webcam study with identifiable face/voice video is not automatically excluded from exemption -- it can qualify via pathway (ii) or (iii) even when identity is readily ascertainable.

**Evidence:** Merges claims [9], [10], [20], [21] (one 2-1, three 3-0 votes). Notably, a contrary claim asserting an AND reading was explicitly REFUTED 0-3 in this pass -- the correct reading is disjunctive (OR).

**Sources:** https://www.law.cornell.edu/cfr/text/45/46.104


### 14. [low] (confidence: low)

**Claim:** GAP -- No claims survived verification on de-identification approaches for face video specifically (why blurring alone may not de-identify given gait/body/voice cues) or for voice (why voice is itself a resistant-to-anonymization biometric identifier).

**Evidence:** This was an explicit sub-topic of Topic C in the task and no surviving claim addresses it; flagged as unresearched.


### 15. [low] (confidence: low)

**Claim:** GAP -- Topic D (privacy-preserving architecture) was entirely unaddressed by surviving claims: no confirmed source on (a) DPA/ICO/EDPB/NIST guidance endorsing on-device/edge/in-browser inference as a data-minimization strategy; (b) GDPR Article 30 records-of-processing-activities requirements; (c) Article 35 DPIA criteria (Art 35(3) or the WP248/EDPB 'nine criteria') for biometric monitoring; (d) controller-vs-processor allocation for a multi-tenant academic/commercial research platform; or (e) any concrete published retention-schedule guidance reconciling BIPA 15(a) with GDPR Art 5(1)(e) storage limitation.

**Evidence:** Zero of the 22 confirmed claims touch any part of Topic D. This is the single largest gap relative to the task's four requested topics.

## Refuted claims (do not use)

1. {"claim":"45 CFR 46.104(a)(2) exempts 'observation of public behavior (including visual or auditory recording)' from IRB review only when subjects' identity cannot readily be ascertained or disclosure poses no risk — meaning a webcam study that records identifiable faces/voices for research purposes does NOT qualify for this exemption category, supporting the research question's premise that video/audio recording of identifiable participants generally falls outside exempt review.","vote":"0-3","source":"https://www.ecfr.gov/current/title-45/part-46"}
2. {"claim":"The guidelines' stated purpose is to ensure consistent, effective, and uniform application of the AI Act's prohibited-practices provisions across EU member states.","vote":"0-3","source":"https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act"}
3. {"claim":"45 CFR 46.104(a)(4) (secondary research exemption) permits use of 'identifiable private information or identifiable biospecimens' under specified conditions — relevant to whether stored webcam video/audio datasets could later be reused for secondary research without new consent, distinct from the primary collection exemption analysis.","vote":"0-3","source":"https://www.ecfr.gov/current/title-45/part-46"}

## Open questions

1. Does BIPA's "scan of face geometry" (740 ILCS 14/10) cover facial-expression-analysis processing that never identifies an individual, and how do the statutory photographs/voice-recording carve-outs apply to a webcam emotion-recognition platform? What is the current post-Cothron/SB 2979 (Aug 2024) damages-accrual exposure, and what do named settlements (e.g., Facebook, BNSF, or a more recent 2024-2026 settlement) suggest for sizing risk?
2. Is emotion-recognition AI used for a research/market-research purpose (outside workplace/education) classified as high-risk under AI Act Annex III, and does Article 50(3) impose a concrete transparency/notice duty on researchers toward participants exposed to such a system -- and if so, what does compliance look like in practice?
3. Is there any published DPA, ICO, EDPB, or NIST guidance that specifically recommends or endorses on-device/edge/in-browser biometric inference as a way to reduce GDPR Article 9/biometric-law exposure, and what would a GDPR Article 35 DPIA (applying the EDPB/WP248 nine criteria) conclude for continuous webcam-based emotion/gaze/respiration monitoring?
4. What concrete, published retention-schedule model (if any) has been used or proposed to simultaneously satisfy BIPA Section 15(a)'s "as soon as reasonably possible, but no later than 3 years" rule and GDPR Article 5(1)(e)'s no-fixed-period "no longer than necessary" storage-limitation principle for the same dataset serving both an Illinois and an EU participant pool?

## Caveats

Two of the four requested topics (B's BIPA/Texas-CUBI half, and all of Topic D) have no surviving verified claims at all -- this reflects either that the underlying research sub-pass did not reach them or that claims made there failed adversarial verification and were dropped without being listed among the "refuted" examples shown; either way, these should be treated as open, not as "researched and found nothing." The Washington MHMDA extension claims (physiological/inferred-data coverage) are medium confidence only, resting on 2-1 split votes and hedged statutory-interpretation language rather than case law or regulator guidance. Several verifiers explicitly noted that WebSearch was unavailable/budget-exhausted during this pass, meaning verification relied on WebFetch of primary/companion-site text rather than a broader adversarial search for contradicting authority or recent (2025-2026) developments -- this particularly affects the AI Act "digital omnibus" question and any recent BIPA settlement/amendment news, none of which could be freshly checked. All EU AI Act material is time-sensitive: the Art 5 prohibitions took effect 2 Feb 2025 and Commission guidance is explicitly non-binding and subject to future CJEU interpretation or Commission revision. The Common Rule exemption analysis (46.104) is comparatively stable/mature law (2018 revision, unamended as of the source-check dates) and is the strongest-sourced portion of this pass.

## All sources

- {"url":"https://artificialintelligenceact.eu/article/5/","quality":"secondary","angle":"a","claimCount":4}
- {"url":"https://artificialintelligenceact.eu/recital/44/","quality":"secondary","angle":"a","claimCount":4}
- {"url":"https://artificialintelligenceact.eu/article/50/","quality":"secondary","angle":"a","claimCount":1}
- {"url":"https://artificialintelligenceact.eu/article/99/","quality":"secondary","angle":"a","claimCount":4}
- {"url":"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689","quality":"primary","angle":"b","claimCount":2}
- {"url":"https://app.leg.wa.gov/RCW/default.aspx?cite=19.373.010","quality":"primary","angle":"b","claimCount":4}
- {"url":"https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57","quality":"unreliable","angle":"b","claimCount":0}
- {"url":"https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act","quality":"primary","angle":"b","claimCount":4}
- {"url":"https://www.illinoiscourts.gov/","quality":"unreliable","angle":"b","claimCount":0}
- {"url":"https://www.ecfr.gov/current/title-45/part-46","quality":"primary","angle":"b","claimCount":5}
- {"url":"https://www.law.cornell.edu/cfr/text/45/46.104","quality":"primary","angle":"c","claimCount":5}
- {"url":"https://www.law.cornell.edu/cfr/text/45/46.116","quality":"primary","angle":"c","claimCount":5}
- {"url":"https://www.hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46/revised-common-rule-regulatory-text/index.html","quality":"unreliable","angle":"c","claimCount":0}
