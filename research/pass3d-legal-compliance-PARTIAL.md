# Pass 3d: Legal & Regulatory Compliance (PARTIAL — synthesis failed, session limit hit at 72/105 agents; needs re-run)

**Research question:**

NARROW SINGLE-TOPIC RESEARCH PASS for a project building a webcam-based human-behavior research platform (browser-first remote data collection; captures participant webcam video and microphone audio; derives eye gaze, facial expressions and inferred emotion, voice/vocal emotion, and respiration). Other passes cover technical validation, analysis pipelines and study design. Research ONLY LEGAL, REGULATORY AND ETHICAL COMPLIANCE. This is gating for a commercial build, so prefer official regulatory texts, regulator guidance, and legal analyses from named law firms or academic legal scholarship over blog commentary. Cite article and section numbers and give dates.

TOPIC A — EU AI ACT AND EMOTION RECOGNITION. Regulation (EU) 2024/1689. The Article 3(39) definition of an "emotion recognition system" and Article 3(34) "biometric categorisation system". The Article 5(1)(f) PROHIBITION on AI systems that infer emotions of a natural person in the workplace and in education institutions, its exceptions (medical and safety reasons), and Recital 44's reasoning. Which of the four modalities in scope fall inside the definition — note that Recital 18 addresses whether physical states like pain or fatigue count, and whether gaze/attention tracking or physiological arousal measurement is in or out. Annex III high-risk classification for emotion recognition outside the prohibited contexts, and the Article 50(3) transparency obligation to inform exposed persons. The compliance timeline: entry into force, the 2 February 2025 applicability of prohibitions and AI literacy, 2 August 2025 for GPAI and governance, 2 August 2026 general applicability, 2 August 2027 for some high-risk. Penalty levels under Article 99 (up to 35M EUR or 7% for prohibited practices). Also note any 2025-2026 developments on delay or simplification of the AI Act timeline, and the Commission's guidelines on prohibited practices.

TOPIC B — GDPR AND BIOMETRIC DATA. Article 4(14) definition of biometric data and the crucial "for the purpose of uniquely identifying a natural person" qualifier — analyze carefully whether facial expression analysis, emotion inference and gaze tracking constitute Article 9 special-category biometric data when NOT used for identification, and what EDPB guidance says (including the EDPB guidelines on facial recognition and on video device processing, Guidelines 3/2019). Whether inferred emotion or health-adjacent physiological data (respiration, heart rate) is special-category data under Article 9 as health data. Lawful bases: Article 6 and Article 9(2)(a) explicit consent, Article 9(2)(j) scientific research, and the conditions and Member State derogations under Article 89. Requirements for valid explicit consent, and why consent is fragile in employment and other imbalanced relationships. Article 35 DPIA — when mandatory, and the criteria lists that make biometric/large-scale monitoring presumptively require one. Article 22 automated decision-making. International transfers and data residency. Transparency, retention limitation, and the right to erasure with regard to video recordings. Note also the UK GDPR position and the ICO's October 2022 public warning about emotion-analysis technology.

TOPIC C — US BIOMETRIC PRIVACY LAW. Illinois BIPA, 740 ILCS 14: the Section 10 definitions of "biometric identifier" and "biometric information" — specifically whether a scan of face geometry covers facial expression analysis, and the photographs/voice recordings carve-outs and their judicial interpretation. Section 15(a) retention schedule and destruction policy requirements, 15(b) informed written consent and written release, 15(c) prohibition on profiting from biometric data, and 15(d) disclosure limits. Section 20 private right of action, statutory damages of 1,000 USD negligent / 5,000 USD intentional or reckless, and the Cothron v. White Castle per-scan accrual decision plus the August 2024 SB 2979 amendment limiting accrual to a single recovery. Notable settlements to size the exposure (Facebook 650M, Google, Clearview, BNSF). Texas CUBI (Business & Commerce Code 503.001) and its AG-only enforcement plus the Meta and Google settlements. Washington My Health My Data Act — its broad "consumer health data" definition, whether biometric and inferred-emotion data falls inside it, its consent and authorization requirements and its private right of action. Colorado's HB24-1130 biometric amendments and any other 2024-2026 state biometric or AI laws relevant to emotion recognition, including Colorado's AI Act.

TOPIC D — HUMAN SUBJECTS RESEARCH ETHICS. IRB/REC review for studies that record participants' webcam video and audio: why video and audio recording generally precludes exempt status under the US Common Rule (45 CFR 46.104) because participants are identifiable, and which exemption categories may still apply. Informed consent language and elements for video/audio capture, biometric derivation, retention periods, and data sharing/secondary use. Consent for online/remote studies without a signature — waiver of documentation of informed consent. Withdrawal mechanics after recording. De-identification options for face video and voice: face blurring/avatarization, extracting and retaining only derived features, voice anonymization, and why face and voice are inherently identifiable. Special populations (children, employees, students, clinical). Also cover the specific ethical critiques of emotion recognition as a research and commercial technology.

TOPIC E — PRIVACY-PRESERVING ARCHITECTURE AND OPERATIONAL COMPLIANCE. Concrete architectural patterns that reduce legal exposure: on-device/edge inference in the browser so raw frames never leave the participant's machine, transmitting only derived feature vectors; the tradeoff against needing raw video for quality control, re-analysis and reproducibility; federated or local-first processing; data minimization applied to biometric pipelines. Retention schedule design and automated deletion. Encryption in transit and at rest, access controls and audit logging. Data-residency and regional processing for GDPR. Records of processing (Article 30), processor/controller allocation when a platform serves academic and commercial clients, and data processing agreements. Vendor and sub-processor risk. Practical guidance on writing a retention and destruction policy that satisfies BIPA 15(a) and GDPR storage limitation simultaneously.

---

## Summary

Synthesis step was skipped or failed — returning 11 verified claims unmerged.

## Findings

_No findings extracted._
## Confirmed (unsynthesized/unmerged)

### 1. [3-0]

**Claim:** Article 3(39) of the EU AI Act defines an 'emotion recognition system' as an AI system used to identify or infer the emotions or intentions of natural persons on the basis of their biometric data.

**Quote:** "an AI system for the purpose of identifying or inferring emotions or intentions of natural persons on the basis of their biometric data"

**Sources:** https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689


### 2. [3-0]

**Claim:** Recital 18 narrows the scope of 'emotion recognition system' by excluding detection of physical states such as pain or fatigue, and excludes systems that merely detect readily apparent expressions, gestures or movements unless those are used to identify or infer emotions -- relevant to whether gaze/attention tracking or physiological arousal measurement falls inside the Article 3(39) definition.

**Quote:** "physical states, such as pain or fatigue"

**Sources:** https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689


### 3. [3-0]

**Claim:** The European Commission published guidelines on prohibited AI practices under the AI Act (Regulation (EU) 2024/1689) on 4 February 2025, and these guidelines are explicitly non-binding, with authoritative interpretation reserved for the CJEU.

**Quote:** "they are non-binding, with authoritative interpretations reserved for the Court of Justice of the European Union (CJEU)"

**Sources:** https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act


### 4. [3-0]

**Claim:** The EU AI Act (Regulation (EU) 2024/1689) entered into force on 1 August 2024.

**Quote:** "The AI Act entered into force on August 1, 2024."

**Sources:** https://digital-strategy.ec.europa.eu/en/policies/ai-pact


### 5. [3-0]

**Claim:** Article 9(1) GDPR establishes a general prohibition on processing special categories of personal data, which include biometric data used for identification purposes, genetic data, health data, and data concerning racial or ethnic origin, political opinions, religious or philosophical beliefs, trade union membership, and sex life or sexual orientation.

**Quote:** "Article 9(1) prohibits processing of data revealing: racial or ethnic origin, political opinions, religious or philosophical beliefs, or trade union membership along with genetic data, biometric data for identifying individuals, health data, and data concerning sex life or sexual orientation."

**Sources:** https://gdpr-info.eu/art-9-gdpr/


### 6. [2-1]

**Claim:** Article 9(2)(a) GDPR provides an exception to the special-category prohibition where the data subject has given explicit consent to processing for one or more specified purposes, subject to a Member State law override.

**Quote:** "The data subject may authorize processing for one or more specified purposes unless national law prevents lifting the prohibition."

**Sources:** https://gdpr-info.eu/art-9-gdpr/


### 7. [2-1]

**Claim:** Article 9(2)(j) GDPR permits processing of special category data for archiving purposes in the public interest, scientific or historical research purposes, or statistical purposes, conditioned on compliance with Article 89(1).

**Quote:** "Processing for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes is permitted per Article 89(1)."

**Sources:** https://gdpr-info.eu/art-9-gdpr/


### 8. [3-0]

**Claim:** GDPR Article 4(14) defines 'biometric data' as personal data resulting from specific technical processing relating to physical, physiological or behavioural characteristics, but only 'which allow or confirm the unique identification of that natural person' - i.e., the identification-purpose qualifier is a defining element of the term, not a separate limitation.

**Quote:** "Personal data resulting from specific technical processing relating to the physical, physiological or behavioural characteristics of a natural person, which allow or confirm the unique identification of that natural person, such as facial images or dactyloscopic data"

**Sources:** https://gdpr-info.eu/art-4-gdpr/


### 9. [2-0]

**Claim:** GDPR Article 4(15) defines 'data concerning health' broadly as personal data related to physical or mental health that reveal information about health status, which is relevant to whether respiration/heart-rate or emotion-adjacent physiological data could qualify as Article 9 special category health data even without an identification purpose.

**Quote:** "Personal data related to the physical or mental health of a natural person, including the provision of health care services, which reveal information about his or her health status"

**Sources:** https://gdpr-info.eu/art-4-gdpr/


### 10. [2-0]

**Claim:** Video footage of an individual is not in itself biometric data under Article 9 GDPR unless it has been specifically technically processed to contribute to identification of that individual — mere capture of facial images by a camera is not automatically special-category data.

**Quote:** "The video footage of an individual cannot however in itself be considered as biometric data under Article 9, if it has not been specifically technically processed in order to contribute to the identification of an individual."

**Sources:** https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_en


### 11. [3-0]

**Claim:** The EDPB sets out a three-part test for when data becomes Article 9 special-category biometric data: (1) nature of data relates to physical/physiological/behavioural characteristics, (2) it results from specific technical processing, and (3) the purpose of processing is to uniquely identify a natural person — all three must be present, meaning purpose (identification) is the decisive qualifier, not mere capture or even feature extraction.

**Quote:** "To sum up, in light of Article 4.14 and 9, three criteria must be considered: - Nature of data : data relating to physical, physiological or behavioural characteristics of a natural person, - Means and way of processing : data resulting from a specific technical processing, - Purpose of processing: data must be used for the purpose of uniquely identifying a natural person."

**Sources:** https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_en

## Refuted claims (do not use)

1. {"claim":"Article 5(1)(f) prohibits placing on the market, putting into service, or using AI systems intended to detect the emotional state of individuals specifically in workplace and education situations (subject to medical/safety exceptions noted separately in the Article's text).","vote":"0-3","source":"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689"}
2. {"claim":"The Commission's guidelines on prohibited AI practices cover harmful manipulation, social scoring, and real-time remote biometric identification as the AI practices deemed unacceptable, but the page content retrieved does not explicitly reference Article 5(1)(f) emotion recognition in the workplace/education prohibition or Article 3(39)/3(34) definitions.","vote":"0-3","source":"https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act"}
3. {"claim":"Per this Commission page, the AI Office and national authorities assumed enforcement powers on 2 August 2026 (the page frames this date as the enforcement-powers milestone, distinct from the Aug 2 2026 'general applicability' framing used elsewhere).","vote":"1-2","source":"https://digital-strategy.ec.europa.eu/en/policies/ai-pact"}
4. {"claim":"Some high-risk AI system requirements under the AI Act will not become fully applicable until December 2027, per this Commission source (note: this is stated as 'December 2027,' which should be checked against the Article 6/113 text commonly cited as '2 August 2027' for certain high-risk obligations).","vote":"0-2","source":"https://digital-strategy.ec.europa.eu/en/policies/ai-pact"}

## Unverified

1. {"claim":"The EDPB gives a worked example directly analogous to non-identifying trait classification (age/gender): a video system that detects physical characteristics to classify a person into a category (e.g., for customized advertising) WITHOUT generating biometric templates to uniquely identify them does not fall under Article 9 — this supports the reading that facial-expression/emotion classification that does not identify the individual likewise stays outside Article 9's biometric special category (though the Guidelines do not address emotion recognition specifically).","erroredVotes":2,"validVotes":1,"source":"https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_en"}
2. {"claim":"HB24-1130 amends the Colorado Privacy Act to require any 'controller' of biometric identifiers/biometric data to adopt a written policy covering a retention schedule, a data-security-incident response protocol, and deletion guidelines with specific deletion trigger dates.","erroredVotes":3,"validVotes":0,"source":"https://leg.colorado.gov/bills/hb24-1130"}
3. {"claim":"HB24-1130 was signed into law by the Colorado Governor on May 31, 2024, but its provisions do not take effect until July 1, 2025.","erroredVotes":3,"validVotes":0,"source":"https://leg.colorado.gov/bills/hb24-1130"}
4. {"claim":"CUBI defines 'biometric identifier' narrowly as a retina/iris scan, fingerprint, voiceprint, or record of hand or face geometry -- it does not on its face reach facial expression analysis or emotion inference outputs, only the underlying face/hand geometry capture itself.","erroredVotes":3,"validVotes":0,"source":"https://statutes.capitol.texas.gov/Docs/BC/htm/BC.503.htm"}
5. {"claim":"CUBI enforcement is exclusively public (Texas Attorney General), with no private right of action, and the civil penalty is capped at $25,000 per violation -- materially lower ceiling per-violation than BIPA's $1,000/$5,000 statutory damages structure, but AG-only (no class-action exposure).","erroredVotes":3,"validVotes":0,"source":"https://statutes.capitol.texas.gov/Docs/BC/htm/BC.503.htm"}
6. {"claim":"CUBI requires informed notice and consent before capturing a biometric identifier for a commercial purpose (analogous to BIPA 15(b)), and separately requires reasonable-care storage/transmission protection and destruction of the identifier within one year after the purpose for collection expires (analogous to BIPA 15(a)).","erroredVotes":3,"validVotes":0,"source":"https://statutes.capitol.texas.gov/Docs/BC/htm/BC.503.htm"}
7. {"claim":"The Common Rule's research-with-recording exemption is NOT automatically barred by identifiability of subjects: category (d)(2) covers research involving 'observation of public behavior (including visual or auditory recording)' and expressly allows exemption even when subject identity CAN be readily ascertained, provided an IRB conducts a 'limited IRB review' under §46.111(a)(7).","erroredVotes":3,"validVotes":0,"source":"https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46/subpart-A/section-46.104"}
8. {"claim":"For adult subjects, exemption category (d)(3)(i) specifically covers 'benign behavioral interventions' collected via 'audiovisual recording' — directly on point for webcam-based emotion-recognition studies — and offers the same three-pronged test: unidentifiable recording, low disclosure risk, or limited IRB review.","erroredVotes":3,"validVotes":0,"source":"https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46/subpart-A/section-46.104"}
9. {"claim":"The baseline (non-limited-review) path to exemption under (d)(2) and (d)(3) requires that recorded data be non-identifying: information must be recorded 'in such a manner that the identity of the human subjects cannot readily be ascertained, directly or through identifiers linked to the subjects' — which webcam facial/voice video ordinarily fails to satisfy absent de-identification, supporting the premise that identifiable video/audio recording generally routes research out of straightforward exemption and into limited or full IRB review.","erroredVotes":3,"validVotes":0,"source":"https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46/subpart-A/section-46.104"}
10. {"claim":"The 2018 Common Rule expanded the number of exempt research categories from six (under the pre-2018 rule) to eight, now codified at 45 CFR __.104 (i.e., 46.104 for HHS).","erroredVotes":3,"validVotes":0,"source":"https://www.federalregister.gov/documents/2017/01/19/2017-01058/federal-policy-for-the-protection-of-human-subjects"}

## All sources

- {"url":"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689","quality":"primary","claimCount":5}
- {"url":"https://artificialintelligenceact.eu/article/5/","quality":"secondary","claimCount":4}
- {"url":"https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act","quality":"primary","claimCount":4}
- {"url":"https://en.wikipedia.org/wiki/Artificial_Intelligence_Act","quality":"secondary","claimCount":5}
- {"url":"https://digital-strategy.ec.europa.eu/en/policies/ai-pact","quality":"primary","claimCount":5}
- {"url":"https://gdpr-info.eu/art-9-gdpr/","quality":"primary","claimCount":5}
- {"url":"https://gdpr-info.eu/art-4-gdpr/","quality":"primary","claimCount":3}
- {"url":"https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_en","quality":"primary","claimCount":5}
- {"url":"https://en.wikipedia.org/wiki/Biometric_Information_Privacy_Act","quality":"secondary","claimCount":5}
- {"url":"https://leg.colorado.gov/bills/hb24-1130","quality":"primary","claimCount":4}
- {"url":"https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57","quality":"unreliable","claimCount":0}
- {"url":"https://statutes.capitol.texas.gov/Docs/BC/htm/BC.503.htm","quality":"primary","claimCount":5}
- {"url":"https://app.leg.wa.gov/rcw/default.aspx?cite=19.373","quality":"unreliable","claimCount":0}
- {"url":"https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46/subpart-A/section-46.104","quality":"primary","claimCount":5}
- {"url":"https://www.hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46/index.html","quality":"unreliable","claimCount":0}
- {"url":"https://www.hhs.gov/ohrp/regulations-and-policy/guidance/index.html","quality":"unreliable","claimCount":0}
- {"url":"https://www.hhs.gov/ohrp/regulations-and-policy/guidance/faq/informed-consent/index.html","quality":"unreliable","claimCount":0}
- {"url":"https://www.microsoft.com/en-us/research/uploads/prod/2018/09/Framework-Emotional-AI-Rights.pdf","quality":"unreliable","claimCount":0}
- {"url":"https://www.federalregister.gov/documents/2017/01/19/2017-01058/federal-policy-for-the-protection-of-human-subjects","quality":"primary","claimCount":5}
- {"url":"https://gdpr-info.eu/art-25-gdpr/","quality":"secondary","claimCount":4}
- {"url":"https://gdpr-info.eu/art-32-gdpr/","quality":"primary","claimCount":4}
- {"url":"https://gdpr-info.eu/art-30-gdpr/","quality":"secondary","claimCount":4}
- {"url":"https://gdpr-info.eu/art-28-gdpr/","quality":"primary","claimCount":4}
