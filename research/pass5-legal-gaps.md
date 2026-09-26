# Pass 5: Legal gaps — BIPA, US states, EU AI Act, GDPR/UK GDPR, ethics and de-identification

**Researched 2026-09-26.** Supersedes `pass3d-legal-compliance-PARTIAL.md` and
`pass4d-bipa-cubi-INCOMPLETE.md`, and fills the gaps `pass4c` reported. This is
research backing, **not legal advice**; nothing here has been reviewed by counsel.

**Method, and how it differs from passes 1–4.** Five parallel research agents,
one per area. Each was told to use primary sources (statute text, Official
Journal, court opinions, regulator guidance), to quote verbatim, to search for
contrary authority or later change before accepting a claim, and to write
NOT VERIFIED rather than fill a gap from memory. There was **no separate
three-vote adversarial verification step** as in passes 1–4. In its place the
key claims were spot-checked against the downloaded source texts:

| Claim | Checked against | Result |
|---|---|---|
| Digital Omnibus is Reg. (EU) 2026/1744; Annex III high-risk moved to 2 Dec 2027; in force 3rd day after publication | OJ text | confirmed (signed Strasbourg 8 July 2026) |
| AI Act Art 2(6) research exclusion wording | OJ text | confirmed verbatim |
| Commission prohibited-practices guidelines para 249 (Recital 18, "readily apparent expressions") | Commission PDF | confirmed |
| WA MHMDA exempts Common Rule identifiable private information | RCW 19.373.100(1)(a)(iv) | confirmed |
| Colorado HB24-1130: "biometric identifier" = *can be* processed to identify; "biometric data" = *used or intended* for identification | session law text | confirmed — the obligations split along that line |
| CJEU C-21/23 "collation or deduction"; C-252/21 para 69 (accuracy and controller's aim irrelevant) | curia texts | confirmed |
| ICO DPIA list names "emotional response analysis" | ICO page | confirmed — under *market research involving neuro-measurement* |
| HIPAA Safe Harbor lettering | HHS de-identification guidance | (P) biometric identifiers incl. voice prints; (Q) full-face images; (R) other unique characteristic. The research brief had these wrong. |
| *G.T. v. Samsung*, 7th Cir. No. 25-1120, 7 Aug 2026 | 7th Cir. opinions site | **existence and date confirmed; the holding was NOT independently re-read** (PDF did not extract here) |

Source texts were downloaded during the session and are not committed; every
finding carries its URL. One editorial correction to the sections below: the
ethics section's sample consent wording lists "breathing rate" — the platform
emits a breathing *waveform* and deliberately no rate (see the main README).

**Jurisdiction is still unset.** Every study file's `disclosure.contact` is a
placeholder and no ethics route is named. Which of the sections below bind
depends on where participants are and which institution's ethics board
approves the study.

## What this means for the platform (synthesis)

*Analysis across the five sections below, not law.*

1. **The consent screen promises a deletion the code only half performs.**
   `features_only` is enforced: `pipeline.enforce_consent` deletes the
   recording after the engines run. But the screen also tells participants
   their data "is kept for N days and then deleted", and nothing acts on that
   N — `consent_retention_days` is written to the `sessions` table and read by
   nothing, so retained media and all derived data live indefinitely. Nor is
   there a per-participant delete path for withdrawal. BIPA §15(a), Colorado's
   deletion schedule, GDPR Art 5(1)(e) and Art 17(1)(b) all turn on deletion
   actually happening. **This is the first thing to build**, before anyone but
   the developer is recorded — and it is this codebase's recurring defect
   class: a declared field nothing reads.
2. **IRB oversight is the main thing keeping the platform outside US state
   law.** Washington's MHMDA and Colorado's biometric rules both exempt Common
   Rule research, and both otherwise reach non-profits. `irbReference` is
   currently optional; making it a recorded, required study attribute for
   anyone but the developer is what makes those exemptions demonstrable. Texas
   CUBI has no research exemption ("commercial purpose" undefined); BIPA has
   none, and whether a public university is a "State agency" is unverified.
3. **Treat facial AU extraction as covered by BIPA for Illinois participants.**
   *Wilk v. Brainshark* (emotion scoring from face video) survived dismissal;
   the courts that require identifiability test capability, not purpose, and a
   researcher holding consent records or raw video supplies the link.
4. **The strongest available mitigation conflicts with a standing decision.**
   BIPA (*G.T. v. Samsung*, as reported: no "collection" without control) and
   GDPR regulators (by analogy) favour extraction in the participant's browser
   with only derived features uploaded. The platform is deliberately
   **record-first, infer-later**: under `features_only` the video is uploaded,
   analysed server-side and then deleted — so the researcher does take control
   of it. The browser already runs MediaPipe blendshapes live; the AU engines
   do not. Whether to add an in-browser-only tier is Tim's call, not a fix.
5. **"Measurements only" must not be read as de-identified.** Close analogues
   re-identify people (VR blendshapes 43% cross-session among 116; eye
   movements 3.66% EER; voice 4.6% EER). The consent text already refuses
   "anonymous" for recordings; the `features_only` tier's "Nothing a person
   could watch or listen to" is true but should add that the measurements
   could, in principle, help identify someone. No study tests webcam-grade
   AU, gaze, eGeMAPS or short breathing traces — the platform's own pilot data
   could.
6. **Tell participants that automated analysis of face and voice happens.** The
   AI Act Art 50(3) notice has applied since 2 Aug 2026. Genuine research use is
   probably outside the Act (Art 2(6), per the Commission's Art 50 guidelines),
   but only while the use is *solely* scientific, and whether distributing the
   tool to other labs keeps it so is unsettled. A one-line notice in the
   consent flow costs nothing and the guidelines endorse merging it with GDPR
   information.
7. **Keep emotion out of the outputs and the documentation.** AU-level output
   is not emotion recognition (Recital 18; guidelines para 249); mapping AUs to
   "happy", arousal or stress is. The platform's refusal to name a valence
   channel is now also a legal position, and the README, examples and any
   dashboard must not undo it.
8. **In the EU, default respiration and affect streams to special-category
   data.** C-21/23 and C-252/21 make the controller's aim and the inference's
   accuracy irrelevant. A DPIA is presumptively required for each deploying
   group, and the Art 30 small-organisation exemption does not apply. Shipping a
   DPIA skeleton and a per-study record-of-processing stub would help users.
9. **Withdrawal needs a stated policy.** OHRP allows keeping or destroying
   already-collected data but consent must say which; under GDPR consent-based
   processing, withdrawal triggers erasure. Simplest honest promise: on request
   we delete raw media and derived features.
10. **Retention: shortest limit wins.** No published source reconciles BIPA's
    3-year cap (Colorado: 24 months after last interaction) with university
    record-keeping rules (e.g. Cornell: 3 years after closeout, 6 after
    publication). Raw media short and fixed; the long-lived record limited to
    what the group will defend as non-biometric — with counsel.

## Still not verified after this pass

- Whether distributing the platform to other labs keeps it "solely for
  scientific research" under AI Act Art 2(6).
- Whether a public university is a "State agency" excluded from BIPA.
- Whether unfunded academic research is a "commercial purpose" under Texas CUBI.
- Any authority classifying a breathing waveform as health data.
- Re-identification from webcam-grade AU, gaze, eGeMAPS or short breathing data.
- The Commission's high-risk guidelines are still in draft.

---


---

## Illinois BIPA

Research compiled 2026-09-26. This is research backing, not legal advice. Primary-source note: ilga.gov refused connections (ECONNREFUSED) for the whole session, so the statute text below comes from FindLaw's codified copy ("Current as of January 01, 2025"). It matches the post-SB 2979 text as quoted by the Seventh Circuit and by law-firm alerts. Court opinions were read in full from govinfo.gov / the 7th Cir. PDF where marked "(read in full)".

---

### 1. §10: "biometric identifier" and its exclusions

- **Claim:** The statute lists four kinds of biometric identifier: retina/iris scan, fingerprint, voiceprint, and scan of hand or face geometry. Photographs and several other items are excluded. Health-care/HIPAA information is also excluded.
- **Quote:** "'Biometric identifier' means a retina or iris scan, fingerprint, voiceprint, or scan of hand or face geometry. Biometric identifiers do not include writing samples, written signatures, photographs, human biological samples used for valid scientific testing or screening, demographic data, tattoo descriptions, or physical descriptions such as height, weight, hair color, or eye color. ... Biometric identifiers do not include information captured from a patient in a health care setting or information collected, used, or stored for health care treatment, payment, or operations under the federal Health Insurance Portability and Accountability Act of 1996. Biometric identifiers do not include an X-ray, roentgen process, computed tomography, MRI, PET scan, mammography, or other image or film of the human anatomy used to diagnose, prognose, or treat an illness or other medical condition or to further validate scientific testing or screening."
- **Source:** 740 ILCS 14/10, https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-10/ (FindLaw, current as of 2025-01-01). Official copy (unreachable this session): https://ilga.gov/Legislation/ILCS/Articles?ActID=3004&ChapterID=57&Print=True
- **Confidence:** High for the wording. Medium that no later amendment exists (see "Not verified").
- **Contrary authority checked:** I searched for BIPA amendments in 2025 and 2026 and found none after SB 2979. On the photographs exclusion, *Wilk v. Brainshark* (N.D. Ill. 2022) read "used for valid scientific testing or screening" as qualifying "photographs". The grammar does not support that reading, so treat it as an outlier. The "scientific testing or screening" wording qualifies *human biological samples* and imaging. **It is not a general research exemption.**

### 2. §10: "biometric information", "private entity", "written release", "electronic signature"

- **Claim:** "Biometric information" requires use to identify an individual. The definition of "private entity" includes *any individual* and expressly excludes State or local government agencies. Since SB 2979, a "written release" may be an electronic signature.
- **Quote:** "'Biometric information' means any information, regardless of how it is captured, converted, stored, or shared, based on an individual's biometric identifier used to identify an individual. ..." / "'Private entity' means any individual, partnership, corporation, limited liability company, association, or other group, however organized. A private entity does not include a State or local government agency. A private entity does not include any court of Illinois, a clerk of the court, or a judge or justice thereof." / "'Electronic signature' means an electronic sound, symbol, or process attached to or logically associated with a record and executed or adopted by a person with the intent to sign the record." / "'Written release' means informed written consent, electronic signature, or, in the context of employment, a release executed by an employee as a condition of employment."
- **Source:** Same as finding 1.
- **Confidence:** High.
- **Contrary authority checked:** I ran three searches for case law on whether a *public* university counts as a "State ... agency" under BIPA and found no decision (see "Not verified"). For *private* universities, see finding 12.

### 3. §15(a)–(e): the obligations

- **Claim:** A private entity that possesses biometric data must meet five requirements:
  - publish a retention and destruction policy, with destruction by the earlier of purpose-satisfied or 3 years after the last interaction;
  - give written notice and state the specific purpose and length of term, and get a written release before collection;
  - never sell or otherwise profit from the data;
  - disclose only with consent or on the other listed grounds;
  - protect the data to the industry standard of care, and at least as well as other confidential information.
- **Quote:** "(a) A private entity in possession of biometric identifiers or biometric information must develop a written policy, made available to the public, establishing a retention schedule and guidelines for permanently destroying biometric identifiers and biometric information when the initial purpose for collecting or obtaining such identifiers or information has been satisfied or within 3 years of the individual's last interaction with the private entity, whichever occurs first. ... (b) No private entity may collect, capture, purchase, receive through trade, or otherwise obtain a person's or a customer's biometric identifier or biometric information, unless it first: (1) informs the subject ... in writing that a biometric identifier or biometric information is being collected or stored; (2) informs the subject ... in writing of the specific purpose and length of term for which a biometric identifier or biometric information is being collected, stored, and used; and (3) receives a written release executed by the subject ... (c) No private entity in possession of a biometric identifier or biometric information may sell, lease, trade, or otherwise profit from a person's or a customer's biometric identifier or biometric information. (d) No private entity in possession ... may disclose, redisclose, or otherwise disseminate ... unless: (1) the subject ... consents ...; (2) ... completes a financial transaction requested or authorized by the subject ...; (3) ... required by State or federal law or municipal ordinance; or (4) ... required pursuant to a valid warrant or subpoena ... (e) ... (1) store, transmit, and protect from disclosure all biometric identifiers and biometric information using the reasonable standard of care within the private entity's industry; and (2) ... in a manner that is the same as or more protective than the manner in which the private entity stores, transmits, and protects other confidential and sensitive information."
- **Source:** 740 ILCS 14/15, https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-15/ (current as of 2025-01-01). §15(a) and (b) are quoted identically in *G.T. v. Samsung*, 7th Cir. No. 25-1120 (2026-08-07).
- **Confidence:** High.
- **Contrary authority checked:** I compared the text against the 7th Cir. quotation in *G.T.* and found it consistent.

### 4. §20: private right of action and damages, including the SB 2979 per-person rule

- **Claim:** Any "person aggrieved" may sue. Liquidated damages are $1,000 per negligent violation and $5,000 per intentional or reckless violation, or actual damages if greater, plus fees and injunctions. Since SB 2979, repeated collection of the same identifier from the same person by the same method is one §15(b) violation. Repeated disclosure to the same recipient is likewise one §15(d) violation.
- **Quote:** "(a) Any person aggrieved by a violation of this Act shall have a right of action in a State circuit court or as a supplemental claim in federal district court against an offending party. A prevailing party may recover for each violation: (1) against a private entity that negligently violates a provision of this Act, liquidated damages of $1,000 or actual damages, whichever is greater; (2) against a private entity that intentionally or recklessly violates a provision of this Act, liquidated damages of $5,000 or actual damages, whichever is greater; (3) reasonable attorneys' fees and costs ...; (4) other relief, including an injunction ... (b) For purposes of subsection (b) of Section 15, a private entity that, in more than one instance, collects, captures, purchases, receives through trade, or otherwise obtains the same biometric identifier or biometric information from the same person using the same method of collection in violation of subsection (b) of Section 15 has committed a single violation of subsection (b) of Section 15 for which the aggrieved person is entitled to, at most, one recovery under this Section."
- **Source:** 740 ILCS 14/20, https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-20/ (current as of 2025-01-01).
- **Confidence:** High.
- **Contrary authority checked:** *Cothron* (finding 5) said damages are discretionary. I checked whether §20(b)/(c) cover §15(a), (c) or (e): the text addresses only §15(b) and §15(d).

### 5. *Cothron v. White Castle*, 2023 IL 128004

- **Claim:** The Illinois Supreme Court held 4–3 that a separate claim accrues with each scan or transmission. It also said liquidated damages are discretionary, not mandatory. SB 2979 later superseded the per-scan result for §15(b) and (d).
- **Quote:** "a separate claim accrues under the Act each time a private entity scans or transmits an individual's biometric identifier or information in violation of section 15(b) or 15(d)"; "the General Assembly chose to make damages discretionary rather than mandatory under the Act."
- **Source:** *Cothron v. White Castle Sys., Inc.*, 2023 IL 128004, decided 2023-02-17, https://caselaw.findlaw.com/court/il-supreme-court/114634228.html. The 7th Cir. in *G.T. v. Samsung* (2026) cites it as "216 N.E.3d 918 ... as modified on denial of reh'g (July 18, 2023)".
- **Confidence:** High on the holding. Medium on the rehearing detail: FindLaw's summary said rehearing was denied without change to the majority, while the 7th Cir. cites it "as modified".
- **Contrary authority checked:** On whether the rule was superseded, see findings 6–7.

### 6. SB 2979 = Public Act 103-0769, signed and effective 2024-08-02

- **Claim:** SB 2979 became Pub. Act 103-0769, effective 2024-08-02, the day it was signed. It added the per-person single-violation rule (§20(b), (c)), defined "electronic signature", and added it to "written release".
- **Quote:** From the 7th Cir. in *Clay*: "Pub. Act. 103-0769, 2024 Ill. Laws 6788–89". From Faegre Drinker: "'Written release' means informed written consent, electronic signature, or, in the context of employment, a release executed by an employee as a condition of employment."
- **Source:** *Clay v. Union Pac. R.R.*, 7th Cir. No. 25-2185 (2026-04-01), https://caselaw.findlaw.com/court/us-7th-circuit/118259102.html. Faegre Drinker alert (2024-08-09), https://www.faegredrinker.com/en/insights/publications/2024/8/illinois-governor-signs-law-that-limits-damages-recoverable-under-the-biometric-information-privacy-act. King & Spalding alert (2024-08-12), https://www.kslaw.com/news-and-insights/illinois-bipa-reform-takes-effect (confirms the 2024-08-02 signing and immediate effect).
- **Confidence:** High.
- **Contrary authority checked:** The K&S alert mislabels the act as "Public Act 2979"; the correct number is 103-0769 (see Refuted leads). I could not reach the ILGA Public Act page.

### 7. The amendment applies retroactively: *Clay v. Union Pacific* (7th Cir. 2026-04-01) — lead CONFIRMED

- **Claim:** On 2026-04-01 the Seventh Circuit (Brennan, C.J.; Hamilton and Jackson-Akiwumi, JJ.; Nos. 25-2185, 25-2761, 25-2762) held the §20 amendment remedial. It therefore applies to cases pending on 2024-08-02, and three district-court rulings were reversed. It is reported at 171 F.4th 975, as cited in *G.T. v. Samsung*.
- **Quote:** "This amendment to BIPA Section 20 applies retroactively to cases pending at the time it was enacted."
- **Source:** https://caselaw.findlaw.com/court/us-7th-circuit/118259102.html (opinion, 2026-04-01). Covington, Inside Privacy (2026-04-07), https://www.insideprivacy.com/data-privacy/seventh-circuit-holds-that-bipa-amendment-applies-retroactively/. Duane Morris (2026-04-03), https://blogs.duanemorris.com/classactiondefense/2026/04/03/seventh-circuit-holds-bipa-amendment-applies-retroactively-reversing-three-illinois-federal-court-decisions/
- **Confidence:** High.
- **Contrary authority checked:**
  - Before *Clay*, N.D. Ill. judges were split. One ruling on 2025-04-10 held the amendment "substantive rather than procedural" (reported by Jackson Lewis and ArentFox Schiff).
  - I found no Illinois Supreme Court or Appellate Court ruling on retroactivity, and no report of rehearing en banc.
  - A federal court's prediction of Illinois law does not bind Illinois state courts.

### 8. Central question: face geometry must be *capable* of identifying a person (*Zellmer v. Meta*, 9th Cir. 2024)

- **Claim:** The Ninth Circuit held that face geometry scans are covered only if they can identify a person. The capability matters, not the purpose. Meta won because its "face signatures" were shown on the record to be unable to identify anyone and to contain no geometric information.
- **Quote:** "scans of face geometry fall within BIPA's list, but are not covered by BIPA if they cannot identify a person." / Describing *Hazlitt v. Apple*: "Hazlitt thus recognized that, even if a company does not use face scans to identify a person, BIPA applies if it could." / On the facts: the numbers "do not reveal any geometric information about the detected face in the image, nor do they correspond to facial features like the eyes or nose, or distances between them." / "That a face signature can predict a person's gender limits the pool of potential matches to approximately 50% of the population; this fails to identify anyone."
- **Source:** *Zellmer v. Meta Platforms, Inc.*, No. 22-16925, 104 F.4th 1117 (9th Cir. filed 2024-06-17), https://www.govinfo.gov/content/pkg/USCOURTS-ca9-22-16925/pdf/USCOURTS-ca9-22-16925-0.pdf (read in full).
- **Confidence:** High on the content. It is persuasive authority only: the Ninth Circuit is not an Illinois court.
- **Contrary authority checked:** *Konow v. Brink's* (finding 10) expressly doubts the identification test. *Wilk v. Brainshark* (finding 9) applied no such test. The Illinois Supreme Court has not ruled on the question. The standard is capability, not purpose, which cuts against "we only use it for expressions".

### 9. Emotion/expression analysis: *Wilk v. Brainshark* (N.D. Ill. 2022-09-27)

- **Claim:** This is the closest analogue to the platform. An AI tool that mapped a person's face in video to score **emotions** was held to plausibly collect a "scan of face geometry", and the motion to dismiss was denied. The court applied no identification test. The case later ended by stipulated dismissal, reportedly on 2023-07-26, so there was never a merits ruling.
- **Quote:** "Brainshark ... provides AI-powered technology that takes sales professionals' videos and applies facial-mapping technology to identify their emotions and other performance indicators. ... To do this, the technology scans individuals' facial geometry and analyzes each second of the video for the seller's emotions." / "the proper question here is whether a facial feature scan qualifies as a 'biometric identifier.' The Court finds that it does." / "Brainshark fails to explain how the term 'scan of face geometry' is unclear or how what it collected from Plaintiff's videos does not qualify."
- **Source:** *Wilk v. Brainshark, Inc.*, No. 1:21-cv-04794, Dkt. 45 (N.D. Ill. 2022-09-27, Blakey, J.), 631 F. Supp. 3d 522, PDF at https://www.fishlawfirm.com/documents/brainshark[1].pdf (read in full). Docket: https://dockets.justia.com/docket/illinois/ilndce/1:2021cv04794/406976
- **Confidence:** High on the ruling. Medium on how the case ended: the stipulated dismissal is from a search summary of the docket, not the docket itself.
- **Contrary authority checked:** This was a pleading-stage ruling that relied on the plaintiff's allegations and the defendant's marketing. *Zellmer* (finding 8) and the "must identify" district cases in finding 10 cut the other way.

### 10. Non-identity facial analysis in N.D. Ill.: the split, and the "other information" bridge

- **Claim:** N.D. Ill. judges are split. Several dismiss unless the defendant could link the scan to identity. Those cases are *Daichendt v. CVS* I (passport photos), *Clarke v. Aveda* and *Castelaz v. Estée Lauder* (virtual try-on), and *Martell v. X* (PhotoDNA hashes). But the test is met when the defendant holds other data, such as names, emails or an employment relationship, that could tie the scan to a person. That was the result in *Daichendt II* and in *Konow v. Brink's*, a driver-facing camera analysing drowsiness, where the motion to dismiss was denied.
- **Quote:** From *Konow* (Pallmeyer, J.):
  - "a defendant may violate BIPA even without using technology for the purpose of identifying an individual; instead, BIPA bars the collection of biometric data that 'merely could be used to identify a plaintiff.'"
  - "This court is not certain that the 'uniquely identifying' test is supported by BIPA's plain language. But assuming that it is, Plaintiff's Complaint plausibly states a claim even under this narrower approach."
  - "this narrower caselaw suggests that, to allege the collection of biometric identifiers, a plaintiff must show that the collected data could be used, 'whether alone or in conjunction with other methods or sources of information available,' to identify them."
  - "Clarke and Castelaz both involved commercial retailer defendants with no clear preexisting relationship to the plaintiffs."

  From *Clarke v. Aveda*: "Plaintiffs' complaint contains no plausible allegations that Aveda's collection of their biometric data made [Aveda] capable of determining their identities."
- **Source:** *Konow v. Brink's, Inc.*, No. 23-cv-760, Dkt. 29 (N.D. Ill. 2024-03-05), https://www.govinfo.gov/content/pkg/USCOURTS-ilnd-1_23-cv-00760/pdf/USCOURTS-ilnd-1_23-cv-00760-0.pdf (read in full). *Clarke v. Aveda Corp.*, No. 21-cv-04185 (N.D. Ill. 2023-12-01, Rowland, J.; dismissed without prejudice), https://caselaw.findlaw.com/court/us-dis-crt-n-d-ill-eas-div/115690596.html. *Martell v. X Corp.*, No. 23 C 5449 (N.D. Ill. 2024-06-13), per Covington, https://www.insideprivacy.com/privacy-and-data-security/illinois-federal-court-dismisses-bipa-suit-against-x-holding-biometric-identifiers-must-identify-individuals/
- **Confidence:** High on the opinions as quoted. These are district-court rulings, not binding precedent.
- **Contrary authority checked:**
  - I found no later ruling in *Konow*.
  - I found no Seventh Circuit or Illinois appellate ruling that resolves the identification question. *Svoboda v. Amazon* (finding 11) and *G.T. v. Samsung* (finding 13) both left it open.

### 11. Virtual try-on at the Seventh Circuit: *Svoboda v. Amazon* (class certified; merits open)

- **Claim:** The Seventh Circuit affirmed class certification for users of Amazon's virtual try-on. It treated "whether the facial data ... constitutes biometric identifiers or information" as an open, common merits question. It did not decide that question.
- **Quote:** "the VTO feature activates the camera on their device to capture their facial geometry from the live video or photo and then analyzes it to determine where to overlay the product." / "two common questions that may require expert discovery on the VTO software: (1) whether the facial data used by the operation of the VTO application constitutes biometric identifiers or information within the meaning of BIPA and (2) whether the use of the VTO means Amazon collected, captured, obtained, or possessed it."
- **Source:** *Svoboda v. Amazon.com Inc.*, 7th Cir. No. 25-1361, decided 2025-12-17 and amended 2026-03-06, https://www.govinfo.gov/content/pkg/USCOURTS-ca7-25-01361/pdf/USCOURTS-ca7-25-01361-2.pdf (read the relevant parts).
- **Confidence:** High.
- **Contrary authority checked:** *Theriot v. Louis Vuitton* (S.D.N.Y. 2022-12-05) denied dismissal of §15(b) claims over a try-on tool. Per ArentFox Schiff (2023-02-16), the contested issue there was *who* collected the data (Louis Vuitton or its vendor FittingBox), not whether the data could identify anyone. So *Theriot* is not authority on expression versus identity.

### 12. Voiceprints: capability is enough; "mere recording" is not a safe harbour

- **Claim:** Two 2026 rulings treat identification capability as sufficient for voice.
  - *Delgado v. Meta* (N.D. Cal., Illston, J.): summary judgment for Meta was denied. Meta had argued that audio files were "mere voice recordings" and never used to identify the user. The court declined to draw the line between recording and voiceprint, and left the case for trial on whether Meta's systems *could* identify the speaker.
  - *Zaluda v. Apple* (Cook County Cir. Ct., 2026-01-29): a Siri class was certified on the theory that the speech-recognition "feature vectors" are capable of identifying the speaker.

  I found **no case holding that a voice recording analysed only for non-identifying acoustic features is *not* a voiceprint.**
- **Quote:** From *Delgado*: "Today's decision need not and does not attempt to precisely delineate at what point voice data transforms from a 'mere voice recording,' as Meta puts it, into a 'voiceprint' under BIPA." / "it is enough that there is a dispute of material fact regarding whether Meta has collected biometric data that is capable of identifying an individual using technology Meta possesses." / "Meta's argument that there is no evidence that Meta actually identified plaintiff using her voice recordings misses the point." From *Zaluda* (via Duane Morris): the feature vectors "are capable of being used to identify a speaker."
- **Source:** Courthouse News, https://courthousenews.com/judge-denies-meta-summary-judgment-in-privacy-class-action-over-unauthorized-voiceprint-collection/ (order reported as unsealed 2026-06-25). Biometric Update (2026-08-25), https://www.biometricupdate.com/202608/meta-loses-bid-to-end-bipa-voiceprint-suit-as-case-moves-forward. Duane Morris (2026-02-10), https://blogs.duanemorris.com/classactiondefense/2026/02/10/illinois-state-court-grants-certification-of-bipa-class-comprised-of-customers-who-used-apples-siri-function/ (*Zaluda v. Apple*, No. 2019 CH 11771).
- **Confidence:** Medium. These are news and law-firm reports; I did not read the orders themselves, and the exact date of the *Delgado* order is unclear.
- **Contrary authority checked:**
  - *Robinson v. Meta* (N.D. Cal., Breyer, J., 2026-09-15) was dismissed under California's anti-hacking statute (CDAFA), not BIPA, and expressly did not decide the voiceprint question (Biometric Update, 2026-09-22).
  - I searched for a "voice recording is not a voiceprint" holding and found none.

### 13. No "possession" or "collection" without control: *G.T. v. Samsung* (7th Cir. 2026-08-07)

- **Claim:** The Seventh Circuit held that "possession", "collect", "capture" and "obtain" all require the company to have some **control** over the biometric data. Face templates created by software but kept only on the user's own device were not collected or possessed by the device maker. The court assumed, without deciding, that the data were biometric identifiers. It followed *Barnett v. Apple* (Ill. App. 2022) and *Bhavilai v. Microsoft* (N.D. Ill. 2024): "providing the tool versus using the tool."
- **Quote:** "the words 'possession,' 'collect,' 'capture,' and 'obtain,' as they appear in BIPA § 15(a) and (b), all require the subject company to have or have obtained some degree of 'control' over the biometric data in question." / "Manufacturing a device (and installing related software) that allows a user to voluntarily take pictures ... and, in the process, create face templates that remain parked within the confines of the user's own personal device not only falls short of triggering BIPA's statutory requirements but strays too far afield from the statute's heartland." / Footnote 2: "we will assume without deciding that the facial geometry data and facial templates in question constitute 'biometric identifiers' or 'biometric information' regulated by BIPA."
- **Source:** *G.T. v. Samsung Elecs. Am., Inc.*, 7th Cir. No. 25-1120 (argued 2025-10-28, decided 2026-08-07, Lee, J.), https://media.ca7.uscourts.gov/cgi-bin/OpinionsWeb/processWebInputExternal.pl?Submit=Display&Path=Y2026%2FD08-07%2FC%3A25-1120%3AJ%3ALee%3Aaut%3AT%3AfnOp%3AN%3A3587785%3AS%3A0 (read in full).
- **Confidence:** High.
- **Contrary authority checked:** *Hazlitt v. Apple* (S.D. Ill. 2021) found control adequately alleged; the Seventh Circuit rejected that line. I found no rehearing report; given how recently it was decided, this is not conclusive.

### 14. §25 exemptions; no research exemption

- **Claim:** §25 contains five construction provisions: (a) admission or discovery of evidence; (b) no conflict with the X-Ray Retention Act or HIPAA; (c) no application "in any manner" to GLBA Title V financial institutions and their affiliates; (d) no conflict with the Private Detective etc. Act; (e) no application to contractors, subcontractors or agents of a State agency or local government "when working for" it. **There is no research or academic exemption** in §25 or anywhere in the text read.
- **Quote:** "(c) Nothing in this Act shall be deemed to apply in any manner to a financial institution or an affiliate of a financial institution that is subject to Title V of the federal Gramm-Leach-Bliley Act of 1999 and the rules promulgated thereunder. ... (e) Nothing in this Act shall be construed to apply to a contractor, subcontractor, or agent of a State agency or local unit of government when working for that State agency or local unit of government."
- **Source:** 740 ILCS 14/25, https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-25/ (current as of 2025-01-01).
- **Confidence:** High on the text. Medium on "no research exemption", since the whole Act could not be read on ILGA; §§1, 5, 30 and 35 were not checked.
- **Contrary authority checked:**
  - I searched for a BIPA research exemption and found none. The only "scientific" wording is in the §10 exclusions (finding 1).
  - *Cisneros v. Nuance* (7th Cir. No. 24-2982, 2026-08-28) extended the §25(c) exemption to a voice-ID vendor of Charles Schwab doing a "GLBA activity" (Sheppard Mullin via Mondaq, 2026-09-15, https://www.mondaq.com/unitedstates/privacy-protection/1842734/seventh-circuit-upholds-that-vendors-can-share-their-clients-bipa-exemption). That is not relevant to research use.

### 15. Private universities and the GLBA "financial institution" exemption (district courts only)

- **Claim:** In online-proctoring cases, N.D. Ill. and C.D. Ill. courts dismissed BIPA claims against DePaul, Northwestern and Bradley. They held that these private universities are GLBA "financial institutions" because they take part in federal student aid. IIT's motion to dismiss was denied for lack of evidence at the pleading stage. There is no appellate ruling.
- **Quote:** From *Powell v. DePaul*, via Duane Morris: "the word 'significantly' means something less than 'primary'"; "the FTC has enforcement authority...and has determined that institutions of higher education...are financial institutions under GLBA."
- **Source:** *Powell v. DePaul Univ.*, No. 21-C-3001 (N.D. Ill. 2022-11-04, Gettleman, J.), per Duane Morris (2022-11-07), https://blogs.duanemorris.com/classactiondefense/2022/11/07/illinois-federal-court-holds-private-university-is-exempt-from-bipa-regulations/. *Duerr v. Bradley Univ.*, No. 21-cv-1096 (C.D. Ill. 2022-03-10), https://caselaw.findlaw.com/court/us-dis-crt-c-d-ill-peo-div/2172758.html. *Doe v. Northwestern Univ.* (N.D. Ill. 2022), per Dorsey (2026-06-16), https://www.dorsey.com/newsresources/publications/client-alerts/2026/6/bipa-financial-institution-exemption. For IIT: Goodwin (2023-01), https://www.goodwinlaw.com/en/insights/blogs/2023/01/banking-on-an-exemption-do-universities-qualify-as-financial-institutions-exempt-from-the-illinois-b
- **Confidence:** Medium-high. I read secondary summaries, not the opinions.
- **Contrary authority checked:** The IIT denial (above). I found no Seventh Circuit decision in *Duerr* or the other university cases. Separately, the exemption would protect the *university*, not necessarily an individual researcher or a separately incorporated vendor. "Private entity" includes "any individual".

### 16. Settlement figures (sizing exposure)

- **Claim and sources:**
  1. **$650 million.** *In re Facebook Biometric Info. Privacy Litig.*, No. 3:15-cv-03747-JD (N.D. Cal.), final approval 2021-02-26. Judge Donato: "By any measure, the $650 million settlement in this biometric privacy class action is a landmark result." Source: class counsel Robbins Geller, https://www.rgrdlaw.com/news-item-Landmark-650-Million-Settlement-in-Facebook-Biometric-Class-Action-Approved-as-a-Major-Win-for-Consumers-in-the-Area-of-Digital-Privacy.html. High.
  2. **About $51.75 million, paid as equity.** *In re Clearview AI Consumer Privacy Litig.* (N.D. Ill., Coleman, J., approved 2025-03-20): a 23% equity stake, "valued at approximately $51.75 million, based on Clearview's January 2024 valuation of $225 million." Source: Constangy (2025-10-28), https://www.constangy.com/newsroom/newsletters/moving-ahead-details-of-the-court-approved-clearview-settlement. High on the figure; the payout itself depends on a future exit.
  3. **$8.75 million, education sector.** *H.K. et al. v. Google LLC*, No. CC 20LL00017 (Cir. Ct. McDonough County, Ill.), over Face Match and Voice Match face and voice models of students on Google Workspace for Education. Final approval 2025-10-17; payments of $474.57 per claimant began 2026-02-13 (per openclassactions.com, a secondary source). Source: official settlement site, https://www.googleeducationbipasettlement.com/. High.
  4. **$6.25 million, online exam proctoring.** *Veiga v. Respondus, Inc.*, No. 2023LA000430 (Cir. Ct. DuPage County). Class: Respondus Monitor users in Illinois from 2015-11-11 to 2023-06-02. Respondus denied collecting any biometric data. Source: Top Class Actions, https://topclassactions.com/lawsuit-settlements/closed-settlements/respondus-online-exam-bipa-6-25m-class-action-lawsuit-settlement/. The official site https://www.bipa-examsettlement.com/ returned 403. Medium.
- **Confidence:** As marked on each item.
- **Contrary authority checked:** For Clearview, the equity-based valuation is contingent.

### Not verified

- **Official ILGA text and later amendments.** ilga.gov refused connections all session. The statute text is FindLaw's, current only to 2025-01-01. Searches found no amendment after Pub. Act 103-0769, but I could not confirm that against ILGA's list of source Public Acts.
- **Public universities as "State agencies".** The statute excludes "a State or local government agency", but I found no court decision on whether a public university (e.g. the University of Illinois) falls under it, after three searches. Sovereign-immunity and Court of Claims routes were also not researched.
- **Gaze tracking as an "iris scan".** I found no case on whether webcam gaze estimation (pupil or iris position rather than iris texture) is a "retina or iris scan". I did not search deeply.
- ***Gielow v. Pandora*** (Cook County No. 22-CH-11181). Only the November 2022 filing is verified; I found no ruling or outcome.
- ***Theriot v. Louis Vuitton*** opinion text. I relied on the ArentFox Schiff summary; Lexology returned 403.
- ***Delgado v. Meta*** order. I did not read the order itself, and its date is unclear: Courthouse News gives "May 20, 2025" alongside an unsealing on 2026-06-25; other reports say the "June decision" was in 2026. The case number was not found.
- **Northwestern, DePaul and IIT opinions.** Read only through law-firm summaries.
- **Illinois state-court position on the identification requirement.** I found no Illinois Appellate or Supreme Court decision on whether a face geometry scan must be capable of identifying. *Barnett v. Apple* (Ill. App. 2022) addresses possession and control, not identification.
- **Proctoring cases on the merits.** The expression-versus-identity question was not decided in any proctoring case I found. They were resolved on the GLBA exemption or settled.

### Refuted leads

- **"Delgado v. Meta" as a virtual try-on or face case.** Wrong. *Delgado v. Meta* is a **voiceprint** case about Facebook and Messenger audio (N.D. Cal., Illston, J.).
- **"Public Act 2979"** (King & Spalding alert, 2024-08-12). Wrong number. SB 2979 became **Pub. Act 103-0769**, per the 7th Cir. in *Clay* and Faegre Drinker.
- ***Theriot v. Louis Vuitton* as authority that identification is not required.** Not supported. Per the available summary, the contested issue was who collected the data (Louis Vuitton or its vendor FittingBox).
- ***Gielow v. Pandora* as a decided case.** Only the complaint is verified.
- ***Clay v. Union Pacific*, 7th Cir., April 2026 — CONFIRMED, not refuted.** Decided 2026-04-01; the amendment applies retroactively to pending cases.
- ***Zellmer v. Meta* (9th Cir. 2024) — CONFIRMED,** with the nuance in finding 8: the test is capability, not purpose.

### What this means for the platform (ANALYSIS, NOT LAW)

- **Expression-only AU extraction plausibly triggers BIPA for Illinois participants. Treat it as covered.** *Wilk v. Brainshark* (emotion scoring from face video) and *Konow* (face and eye analysis for drowsiness) both survived dismissal. Landmark-based AU pipelines compute actual facial geometry. That is the feature Meta's face signatures lacked in *Zellmer*, and its absence is what won that case.
- **"We never identify anyone" is weak where the researcher knows who the participant is.** The courts that require identification ask whether the data could identify the person "alone or in conjunction with other ... information available". Consent records, emails, participant-ID keys and especially **retained raw video** supply that link, as in *Daichendt II* and *Konow*. Truly anonymous sessions with no stored identity and no raw video are the fact pattern that won in *Clarke*, *Castelaz* and *Zellmer*.
- **Voice features carry similar risk.** No case holds that non-identifying acoustic analysis falls outside "voiceprint". *Delgado* and *Zaluda* use a capability test, so keeping raw audio linked to a participant makes the position harder to defend. Low-dimensional prosodic summaries (pitch, energy) are more defensible than speaker embeddings or MFCC matrices. Breathing waveforms from chest motion are not a listed identifier.
- **Processing in the browser helps, but only if identifying intermediates never leave the device.** *G.T. v. Samsung* and *Barnett* show there is no "possession" or "collection" without control. If landmarks and meshes are computed and discarded in the participant's browser, and only aggregate AU, gaze or breathing time-series are uploaded, the researcher arguably never obtains a scan. Uploading or retaining raw video or landmarks gives the researcher control.
- **Separating the open-source maintainer from the deploying researcher.** If the maintainer only publishes code and does not host sessions or receive data, *Bhavilai* ("providing the tool versus using the tool") and *G.T.* support treating the maintainer as a tool provider. A project-hosted server that receives data changes that.
- **Institutional exemptions are uncertain and are not a design basis.** Private universities have won the GLBA exemption in district courts but have also lost (IIT), with no appellate ruling. Public universities probably fall within the "State agency" exclusion, but that is unverified. "Any individual" is a private entity, so an individual researcher or a spin-out has no clear exemption. There is no research exemption.
- **A conservative design for Illinois participants, or for everyone, since location is hard to prove:**
  - a separate BIPA notice naming the data and the specific purpose, plus a signed release before capture (an e-signature is valid since 2024-08-02);
  - a public retention and destruction policy, deleting at study end and never beyond 3 years after last interaction;
  - no sale or profit from the data;
  - no disclosure without consent, which includes sharing raw video with collaborators;
  - security at least equal to other confidential data;
  - raw-video retention off by default;
  - extraction in the browser with landmarks discarded.
- **Exposure after *Clay*.** Per person, the maximum is roughly $1,000 (negligent) or $5,000 (intentional or reckless) per type of violation, plus plaintiff's attorneys' fees. Per-scan multiplication is gone. A study of 200 Illinois participants with no BIPA consent could still face six- to seven-figure statutory exposure. Settlements run from about $6 million (proctoring vendor) and $8.75 million (Google education) to $650 million (Facebook).


---

## US state law beyond BIPA

Research backing, not legal advice. Checked 2026-09-26. Statutory quotes were taken from official legislature sites (Texas `tcss.legis.texas.gov`, Washington `app.leg.wa.gov`, Colorado `leg.colorado.gov` session laws and signed acts, California `leginfo.legislature.ca.gov`, and Montana `docs.legmt.gov`). Press-release facts come from the AG's own site. Law-firm material is used only for interpretation and is labelled as such.

Platform assumed throughout: an open-source academic/non-profit web platform. It records webcam video and microphone audio and derives gaze, facial action units / expression scores, voice acoustic features and a breathing waveform. It does no identity matching and no cross-session templates. Raw video may be kept under a consent tier.

---

### Texas

**T1. CUBI definition, consent, disclosure and destruction rules**
- **Claim:** CUBI defines "biometric identifier" as a closed list. It applies only to capture "for a commercial purpose". It requires notice before capture plus consent. Destruction is due within a reasonable time and no later than the first anniversary of the date the collection purpose expires.
- **Quote:** "(2) "Biometric identifier" means a retina or iris scan, fingerprint, voiceprint, or record of hand or face geometry. (b) A person may not capture a biometric identifier of an individual for a commercial purpose unless the person: (1) informs the individual before capturing the biometric identifier; and (2) receives the individual's consent to capture the biometric identifier." … "(3) shall destroy the biometric identifier within a reasonable time, but not later than the first anniversary of the date the purpose for collecting the identifier expires, except as provided by Subsection (c-1)."
- **Source:** Tex. Bus. & Com. Code §503.001, https://tcss.legis.texas.gov/resources/BC/htm/BC.503.htm. The current text was last amended by Acts 2025, 89th Leg., R.S., Ch. 1174 (H.B. 149), Sec. 2, eff. January 1, 2026.
- **Confidence:** High (official statutory text).
- **Contrary authority checked:** The amendment history on the official page lists no amendment after HB 149. The one-year rule runs from when the *purpose expires*, not from collection. Some secondary sources summarise it loosely as "one year", which is inaccurate.

**T2. CUBI penalty and enforcement by the AG only**
- **Claim:** The penalty is up to $25,000 per violation. The statute gives enforcement only to the Attorney General and creates no private cause of action.
- **Quote:** "(d) A person who violates this section is subject to a civil penalty of not more than $25,000 for each violation. The attorney general may bring an action to recover the civil penalty."
- **Source:** Same as T1.
- **Confidence:** High that the text confers enforcement only on the AG. Medium on "no private right of action" as a judicial holding: I found no court decision squarely rejecting a private CUBI claim. The conclusion rests on the statute's text, which names only the AG.
- **Contrary authority checked:** I searched for private CUBI suits and dismissals and found none. Bracewell (Aug 12, 2024) reports the AG's position that capture and storage are *separate* violations, which could double exposure per person: "Under this theory, a single non-compliant collection would instantly double the penalty up to $50,000." (https://www.bracewell.com/resources/billion-dollar-liability-understanding-your-obligations-under-the-texas-capture-or-use-of-biometric-identifier-act/). That is the AG's litigation theory, not a ruling.

**T3. "Commercial purpose" is undefined, and there is no research exemption**
- **Claim:** CUBI does not define "commercial purpose". It has no academic, non-profit or research exemption. The only exemptions are §503.001(e): financial-institution voiceprints, AI training/development unless the system is used to uniquely identify someone, and security/fraud AI. Practitioners expect "commercial purpose" to be read broadly.
- **Quote:** The statute contains no definition of "commercial purpose" (full text reviewed). Exemption: "(e) This section does not apply to: … (2) the training, processing, or storage of biometric identifiers involved in developing, training, evaluating, disseminating, or otherwise offering artificial intelligence models or systems, unless a system is used or deployed for the purpose of uniquely identifying a specific individual". Bracewell: "The term 'commercial purpose' is not defined in the statute, and there is little guidance on the question. But, there is good reason to believe the term, 'commercial purpose,' will be broadly construed."
- **Source:** §503.001 (as T1); Bracewell LLP client alert, Aug 12, 2024 (URL above).
- **Confidence:** High that it is undefined and that no research exemption exists. Low on how a court would treat unfunded academic research: there is no case law.
- **Contrary authority checked:** I searched for any Texas court or AG opinion construing "commercial purpose" and found none. Washington's RCW 19.375 (W6) *does* define the term, narrowly. That contrast shows Texas chose not to.

**T4. Meta settlement: $1.4 billion, July 30, 2024**
- **Claim:** Texas settled its CUBI and DTPA suit against Meta for $1.4 billion, payable over five years. It was the first lawsuit and first settlement under CUBI.
- **Quote:** "Texas Attorney General Ken Paxton has secured a $1.4 billion settlement with Meta (formerly known as Facebook) … This is the first lawsuit brought and first settlement obtained under Texas's 'Capture or Use of Biometric Identifier' Act" … "The company will pay the state of Texas $1.4 billion over five years."
- **Source:** Texas OAG press release dated July 30, 2024, https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-secures-14-billion-settlement-meta-over-its-unauthorized-capture
- **Confidence:** High.
- **Contrary authority checked:** Do not confuse this with a separate later OAG release, "Secures Over $1 Billion from Meta in Historic Settlement that Protects Texas Kids Online". That concerns children's online safety, not CUBI.

**T5. Google settlement: $1.375 billion, announced in principle May 9, 2025 and finalized Oct 31, 2025**
- **Claim:** Texas announced a $1.375 billion settlement in principle with Google on May 9, 2025. It covers geolocation, incognito and biometric claims combined. The OAG announced on October 31, 2025 that Google had signed. This amount is **not** a biometric-only figure.
- **Quote:** (May 9, 2025) "Attorney General Ken Paxton secured a $1.375 billion settlement in principle with Google … In 2022, Attorney General Paxton sued Google for unlawfully tracking and collecting users' private data regarding geolocation, incognito searches, and biometric data." (Oct 31, 2025) "Google has signed the historic $1.375 billion settlement agreement with the State of Texas, marking the conclusion of two of the largest data privacy enforcement actions".
- **Source:** Texas OAG releases dated May 9, 2025 (https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-secures-historic-1375-billion-settlement-google-related-texans-data) and October 31, 2025 (https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-finalizes-historic-settlement-google-and-secures-1375-billion-big-tech).
- **Confidence:** High on amounts and dates. The releases do not allocate the amount between the biometric claims and the other claims.
- **Contrary authority checked:** Both OAG releases agree. The October release says the amount resolves "two" enforcement actions.

**T6. TRAIGA (HB 149): effective Jan 1, 2026; reaches biometrics mainly through government-use limits and CUBI amendments; no emotion-recognition provision**
- **Claim:** TRAIGA (Tex. Bus. & Com. Code chs. 551–554) took effect January 1, 2026. Its biometric provision, §552.054, binds only a "governmental entity", and that term excludes institutions of higher education. The section's "biometric data" definition excludes video and audio recordings and data generated from them. The chapter contains no provision on emotion recognition: the word "emotion" appears nowhere in chs. 551–554 or 503. The AG enforces exclusively, there is no private right of action, and penalties run from $10,000 to $200,000 per violation. HB 149 also amended CUBI, adding the AI-training carve-out (T3) and the rule that images publicly available online do not imply consent (§503.001(b-1)).
- **Quote:** "(3) "Governmental entity" … The term does not include: … (B) an institution of higher education, as defined by Section 61.003, Education Code". §552.054(a): "The term does not include a physical or digital photograph or data generated from a physical or digital photograph, a video or audio recording or data generated from a video or audio recording". §552.101: "(a) The attorney general has exclusive authority to enforce this chapter … (b) This chapter does not provide a basis for, and is not subject to, a private right of action".
- **Source:** Tex. Bus. & Com. Code chs. 551–552, https://tcss.legis.texas.gov/resources/BC/htm/BC.551.htm and https://tcss.legis.texas.gov/resources/BC/htm/BC.552.htm. Added by Acts 2025, 89th Leg., R.S., Ch. 1174 (H.B. 149), eff. January 1, 2026.
- **Confidence:** High (official text; searched for "emotion").
- **Contrary authority checked:** TRAIGA's private-sector prohibitions (§552.052 behavioural manipulation toward self-harm, harm or crime; §552.056 unlawful discrimination; §552.057 sexual content) do not concern emotion inference. §552.051 AI-interaction disclosure binds governmental agencies only.

---

### Washington – My Health My Data Act (RCW 19.373)

**W1. Enforcement through the Consumer Protection Act, including private suits**
- **Claim:** Any MHMDA violation is a per se unfair or deceptive act under the CPA (RCW 19.86). The CPA's private civil action (RCW 19.86.090) is therefore available to anyone "injured in his or her business or property". The WA AG says so expressly. The MHMDA itself contains no standalone "private right of action" clause: private enforcement is through §090 of the CPA.
- **Quote:** RCW 19.373.090: "A violation of this chapter is not reasonable in relation to the development and preservation of business, and is an unfair or deceptive act in trade or commerce and an unfair method of competition for the purpose of applying the consumer protection act, chapter 19.86 RCW." RCW 19.86.090: "Any person who is injured in his or her business or property by a violation of RCW 19.86.020 … may bring a civil action in superior court … the court may, in its discretion, increase the award of damages up to an amount not to exceed three times the actual damages sustained: PROVIDED, That such increased damage award for violation of RCW 19.86.020 may not exceed twenty-five thousand dollars". WA AG FAQ: "any violation of the Act is a per se violation of the Washington Consumer Protection Act (CPA), RCW 19.86, which is enforced by the Attorney General as well as through private action."
- **Source:** https://app.leg.wa.gov/RCW/default.aspx?cite=19.373&full=true (history 2023 c 191; no later amendments shown); https://app.leg.wa.gov/RCW/default.aspx?cite=19.86.090; WA AG FAQ at https://www.atg.wa.gov/protecting-washingtonians-personal-health-data-and-privacy (undated; "may be periodically updated").
- **Confidence:** High.
- **Contrary authority checked:** A private plaintiff must still show injury to "business or property" under the CPA. No court has yet ruled on how that applies to MHMDA claims (see W5).

**W2. Collection consent, separate sharing consent, and a separate signed "valid authorization" to sell**
- **Claim:** Collection requires consent for a specified purpose, unless the collection is necessary for a service the consumer requested. Sharing requires a separate consent. Sale requires a signed "valid authorization" that is separate from both, expires after one year, and must be kept for six years. "Consent" excludes broad terms-of-use acceptance.
- **Quote:** RCW 19.373.030(1)(b)(i): "With consent from the consumer for such sharing that is separate and distinct from the consent obtained to collect consumer health data". RCW 19.373.070(1): "it is unlawful for any person to sell or offer to sell consumer health data concerning a consumer without first obtaining valid authorization from the consumer. … This authorization must be separate and distinct from the consent obtained to collect or share consumer health data".
- **Source:** RCW 19.373.030, .070 (as W1).
- **Confidence:** High.
- **Contrary authority checked:** None found. The sections have not been amended since 2023.

**W3. Research exemptions: two routes, both tied to IRB or Common Rule oversight**
- **Claim:** (a) Data used for public-interest research that is approved, monitored and governed by an IRB (or a similar independent body) is excluded from "consumer health data" altogether. (b) Separately, the chapter does not apply to Common Rule "identifiable private information" or to personal data used in research conducted under those frameworks.
- **Quote:** RCW 19.373.010(8)(c): ""Consumer health data" does not include personal information that is used to engage in public or peer-reviewed scientific, historical, or statistical research in the public interest that adheres to all other applicable ethics and privacy laws and is approved, monitored, and governed by an institutional review board, human subjects research ethics review board, or a similar independent oversight entity that determines that the regulated entity or the small business has implemented reasonable safeguards to mitigate privacy risks associated with research, including any risks associated with reidentification." RCW 19.373.100(1)(a)(iv): "Identifiable private information for purposes of the federal policy for the protection of human subjects, 45 C.F.R. Part 46; … or personal data used or shared in research conducted in accordance with one or more of the requirements set forth in this subsection".
- **Source:** RCW 19.373.010, .100 (as W1).
- **Confidence:** High on the text. Low on how the exemption applies to a platform *operator* as distinct from each study's investigator: there is no guidance.
- **Contrary authority checked:** The WA AG FAQ does not discuss the research exemption. "Regulated entity" means "any legal entity", so non-profits are not excluded. Government agencies are excluded (RCW 19.373.010(23)).

**W4. Inferred data and biometrics: AG guidance covers inference; nothing addresses biometrics specifically**
- **Claim:** "Consumer health data" expressly includes biometric data, "bodily functions, vital signs … or measurements", and health status inferred from non-health data by algorithms or machine learning. The WA AG FAQ confirms that inferences count, using a purchase-based example. It does not address biometrics, facial expression or physiological signals. MHMDA's "biometric data" requires that the data "identifies a consumer".
- **Quote:** RCW 19.373.010(4): ""Biometric data" means data that is generated from the measurement or technological processing of an individual's physiological, biological, or behavioral characteristics and that identifies a consumer, whether individually or in combination with other data." RCW 19.373.010(8)(b)(xiii): "… derived or extrapolated from nonhealth information (such as proxy, derivative, inferred, or emergent data by any means, including algorithms or machine learning)." AG FAQ Q6: "The definition of consumer health data includes information that is derived or extrapolated from nonhealth data when that information is used by a regulated entity or their respective processor to associate or identify a consumer with consumer health data." It continues: "nonhealth data that a regulated entity collects but does not process to identify or associate a consumer with a physical or mental health status is not consumer health data."
- **Source:** RCW 19.373.010; WA AG FAQ (URL in W1).
- **Confidence:** High on the text and the FAQ. No court decision construes these terms (see W5).
- **Contrary authority checked:** CourtListener search on 2026-09-26 found no opinion construing MHMDA definitions.

**W5. First MHMDA suit against Amazon: filed Feb 2025, voluntarily dismissed June 2025**
- **Claim:** *Maxwell v. Amazon.com, Inc.*, No. 2:25-cv-00261 (W.D. Wash.), was filed on February 10, 2025 and widely reported as the first MHMDA class action (Amazon Ads SDK location data). It was consolidated into *In re Amazon Ads SDK Litigation*, No. 2:25-cv-00252-BJR. Both named plaintiffs then filed Rule 41(a)(1)(A)(i) voluntary dismissals, and the case was closed on June 6, 2025, **without any ruling on the MHMDA**.
- **Quote:** Docket: "22 NOTICE of Voluntary Dismissal as to party(s) Cassaundra Maxwell … (Entered: 05/29/2025)"; "27 NOTICE of Voluntary Dismissal as to party(s) Felix Kolotinsky … (Entered: 06/05/2025)"; "***Civil Case Terminated re 27 Notice of Voluntary Dismissal … this case is closed." (06/06/2025).
- **Source:** CourtListener RECAP docket, https://www.courtlistener.com/docket/69623838/in-re-amazon-ads-sdk-litigation/ (entries dated 2025-04-14, 2025-05-29, 2025-06-05, 2025-06-06). Filing reported by WilmerHale (Feb 20, 2025): https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20250220-first-lawsuit-filed-under-washingtons-my-health-my-data-act
- **Confidence:** High on the docket events (from docket text). I did not read the dismissal notices themselves, so I cannot say whether a settlement lay behind them.
- **Contrary authority checked:** Several 2026 secondary sources still describe the case as pending "in early motion practice". The docket contradicts that. Other MHMDA-citing suits exist (e.g. a CourtListener hit, *Brenneise v. Aios Inc.*, N.D. Cal. 3:25-cv-09779, filed 2025-11-13), but I found no merits ruling on the MHMDA in any case.

---

### Washington – biometric identifiers (RCW 19.375)

**W6. Narrow scope: "enroll", a narrowly defined "commercial purpose", an exclusion for recordings, and AG-only enforcement**
- **Claim:** RCW 19.375 regulates only *enrolling* a biometric identifier (turning it into a template stored in a database matched to a specific individual) "for a commercial purpose". "Commercial purpose" is defined narrowly as sale or disclosure for unrelated marketing. Photographs, video and audio recordings, and data generated from them, are excluded from "biometric identifier". Only the AG enforces the chapter.
- **Quote:** "(1) "Biometric identifier" … does not include a physical or digital photograph, video or audio recording or data generated therefrom". "(4) "Commercial purpose" means a purpose in furtherance of the sale or disclosure to a third party of a biometric identifier for the purpose of marketing of goods or services when such goods or services are unrelated to the initial transaction". "(5) "Enroll" means to capture a biometric identifier of an individual, convert it into a reference template that cannot be reconstructed into the original output image, and store it in a database that matches the biometric identifier to a specific individual." RCW 19.375.030(2): "This chapter may be enforced solely by the attorney general under the consumer protection act".
- **Source:** https://app.leg.wa.gov/RCW/default.aspx?cite=19.375&full=true (2017 c 299; no later amendments shown).
- **Confidence:** High.
- **Contrary authority checked:** "Person" excludes government agencies but includes any "organization", so non-profits are covered in principle. The enrollment and commercial-purpose elements are the operative limits.

---

### Colorado

**C1. HB24-1130: effective July 1, 2025; applies regardless of the CPA's volume thresholds**
- **Claim:** HB24-1130 was signed May 31, 2024 and took effect July 1, 2025. It amended C.R.S. 6-1-1304 so that the CPA applies to any controller that processes *any amount* of biometric identifiers or biometric data. For controllers below the normal thresholds, the CPA applies only as to that biometric data.
- **Quote:** "(b) CONTROLS OR PROCESSES ANY AMOUNT OF BIOMETRIC IDENTIFIERS OR BIOMETRIC DATA REGARDLESS OF THE AMOUNT … EXCEPT THAT A CONTROLLER THAT MEETS THE QUALIFICATIONS OF THIS SUBSECTION (1)(b) BUT DOES NOT MEET THE QUALIFICATIONS OF SUBSECTION (1)(a) OF THIS SECTION SHALL COMPLY WITH THIS PART 13 ONLY FOR THE PURPOSES OF A BIOMETRIC IDENTIFIER OR BIOMETRIC DATA THAT THE CONTROLLER COLLECTS AND PROCESSES." Section 5: "This act takes effect July 1, 2025".
- **Source:** 2024 Colo. Sess. Laws ch. 313 (HB24-1130), https://leg.colorado.gov/laws/session-laws/HB24-1130/313/download; bill page https://leg.colorado.gov/bills/hb24-1130 ("APPROVED by Governor May 31, 2024 / EFFECTIVE July 1, 2025").
- **Confidence:** High.
- **Contrary authority checked:** I found no 2025–2026 amendment to 6-1-1314 (search not exhaustive). New (1)(b) does not itself restate the Colorado nexus required by (1)(a). Practitioners read it as reaching any entity handling Colorado residents' biometrics.

**C2. HB24-1130: "biometric identifier" turns on what the data *can* do; "biometric data" turns on use for identification**
- **Claim:** A "biometric identifier" includes facial geometry or a facial map that *can be processed* to uniquely identify someone, whether or not it is used that way. "Biometric data" (sensitive data needing consent under 6-1-1308(7)) is limited to identifiers used or intended for identification, and excludes photos, audio and video unless they are used to identify.
- **Quote:** "(2.4) "BIOMETRIC IDENTIFIER" MEANS DATA GENERATED BY THE TECHNOLOGICAL PROCESSING, MEASUREMENT, OR ANALYSIS OF A CONSUMER'S BIOLOGICAL, PHYSICAL, OR BEHAVIORAL CHARACTERISTICS, WHICH DATA CAN BE PROCESSED FOR THE PURPOSE OF UNIQUELY IDENTIFYING AN INDIVIDUAL. "BIOMETRIC IDENTIFIER" INCLUDES: … (b) A VOICEPRINT; … (d) A FACIAL MAP, FACIAL GEOMETRY, OR FACIAL TEMPLATE". "(2.2)(b) "BIOMETRIC DATA" DOES NOT INCLUDE THE FOLLOWING UNLESS THE BIOMETRIC DATA IS USED FOR IDENTIFICATION PURPOSES: (I) A DIGITAL OR PHYSICAL PHOTOGRAPH; (II) AN AUDIO OR VOICE RECORDING; OR (III) ANY DATA GENERATED FROM A DIGITAL OR PHYSICAL PHOTOGRAPH OR AN AUDIO OR VIDEO RECORDING."
- **Source:** HB24-1130 §3 (as C1).
- **Confidence:** High on the text. Low on whether face landmarks used only for action units are a "facial map/geometry" that "can be processed" for identification: there are no rules or cases on this point.
- **Contrary authority checked:** The Colorado AG may make rules under 6-1-1314(7). I did not verify the content of any biometric-specific CPA rule amendments.

**C3. HB24-1130 requirements**
- **Claim:** A controller that processes biometric identifiers must meet five sets of requirements. (1) Adopt a public written policy with a retention schedule, an incident-response protocol, and deletion by the earliest of: the initial purpose being satisfied, 24 months after the consumer last interacted with the controller, or 45 days after an annual review finds the data no longer necessary. (2) Before collection, tell the consumer what is collected, the specific purpose, the retention period, and any disclosure to processors. (3) Not sell, lease or trade biometric identifiers, and disclose them only on narrow grounds. (4) Not deny service for refusing consent unless the processing is necessary. (5) Obtain consent before collecting "biometric data".
- **Quote:** "(III) INCLUDES GUIDELINES THAT REQUIRE THE DELETION OF A BIOMETRIC IDENTIFIER ON OR BEFORE THE EARLIEST OF THE FOLLOWING DATES: (A) THE DATE UPON WHICH THE INITIAL PURPOSE FOR COLLECTING THE BIOMETRIC IDENTIFIER HAS BEEN SATISFIED; (B) TWENTY-FOUR MONTHS AFTER THE CONSUMER LAST INTERACTED WITH THE CONTROLLER; OR (C) THE EARLIEST REASONABLY FEASIBLE DATE, WHICH DATE MUST BE NO MORE THAN FORTY-FIVE DAYS AFTER A CONTROLLER DETERMINES THAT STORAGE OF THE BIOMETRIC IDENTIFIER IS NO LONGER NECESSARY…". "(b) A CONTROLLER THAT PROCESSES A CONSUMER'S BIOMETRIC IDENTIFIER SHALL NOT: (I) SELL, LEASE, OR TRADE THE BIOMETRIC IDENTIFIER WITH ANY ENTITY".
- **Source:** C.R.S. 6-1-1314(2), (4) as enacted (as C1).
- **Confidence:** High.
- **Contrary authority checked:** The access right in 6-1-1314(5) applies only to entities that meet the ordinary 100k/25k thresholds (6-1-1314(5)(b)).

**C4. The CPA covers non-profits, but exempts Common Rule research data and some public higher-education data; enforcement is AG/DA only**
- **Claim:** The CPA has no entity-level exemption for non-profits, as the Colorado AG confirms. Its exemptions, which HB24-1130's legislative declaration says also apply to the biometric provisions, cover Common Rule identifiable private information and personal data used in research conducted under those frameworks. They also cover data held by a *state* institution of higher education for non-commercial purposes. There is no private right of action.
- **Quote:** C.R.S. 6-1-1304(2)(d): "IDENTIFIABLE PRIVATE INFORMATION, AS DEFINED IN 45 CFR 46.102, FOR PURPOSES OF THE FEDERAL POLICY FOR THE PROTECTION OF HUMAN SUBJECTS PURSUANT TO 45 CFR 46; … OR PERSONAL DATA USED OR SHARED IN RESEARCH CONDUCTED IN ACCORDANCE WITH ONE OR MORE OF THE CATEGORIES SET FORTH IN THIS SUBSECTION (2)(d)". (2)(o): "DATA MAINTAINED BY A STATE INSTITUTION OF HIGHER EDUCATION … IF THE DATA IS COLLECTED, MAINTAINED, DISCLOSED, COMMUNICATED, AND USED AS AUTHORIZED BY STATE AND FEDERAL LAW FOR NONCOMMERCIAL PURPOSES." 6-1-1311: "THE ATTORNEY GENERAL AND DISTRICT ATTORNEYS HAVE EXCLUSIVE AUTHORITY TO ENFORCE THIS PART 13". HB24-1130 §1(3): "all of the exceptions that apply to the entirety of the "Colorado Privacy Act" apply to the protections established for biometric data and biometric identifiers in this act." Colorado AG: "The law applies to entities, including nonprofits, that conduct business in Colorado…"
- **Source:** 2021 Colo. Sess. Laws ch. 483 (SB21-190), https://leg.colorado.gov/laws/session-laws/SB21-190/483/download; HB24-1130 §1(3); Colorado AG CPA page, https://coag.gov/resources/colorado-privacy-act/ (undated).
- **Confidence:** High on the 2021 text and the HB24-1130 declaration. Medium that (2)(d) and (2)(o) remain unamended today: I read the 2021 enactment, not a current consolidated C.R.S. The official C.R.S. is on Lexis and Justia blocked retrieval.
- **Contrary authority checked:** I searched for amendments removing the research exemption and found none.

**C5. Colorado AI Act SB24-205: never took effect; repealed and re-enacted by SB26-189 (ADMT), effective Jan 1, 2027**
- **Claim:** SB25B-004 (signed Aug 28, 2025) delayed SB24-205 to June 30, 2026. SB26-189 (signed May 14, 2026) then repealed and re-enacted part 17 as an automated-decision-making-technology law for "consequential decisions" (education, employment, housing, financial or lending services, insurance, health care, government services). It takes effect January 1, 2027. The signed act does not mention emotion recognition. It excludes from "developer" anyone who develops and uses an ADMT solely for research that is not used in a consequential decision.
- **Quote:** SB25B-004 summary: "The act extends the effective date of the requirements of Senate Bill 24-205 to June 30, 2026. APPROVED by Governor August 28, 2025". SB26-189: "SECTION 1. In Colorado Revised Statutes, repeal and reenact, with amendments, part 17 of article 1 of title 6". "(b) "DEVELOPER" DOES NOT INCLUDE A PERSON THAT: (I) DEVELOPS AND USES AN ADMT: (A) SOLELY FOR RESEARCH PURPOSES AND THE ADMT IS NOT USED IN A CONSEQUENTIAL DECISION IN THE RESEARCH". §5: "this act takes effect January 1, 2027."
- **Source:** https://leg.colorado.gov/bills/sb25b-004; https://leg.colorado.gov/bills/sb26-189 (Signed Act dated 05/14/2026, https://leg.colorado.gov/bill_files/116489/download).
- **Confidence:** High.
- **Contrary authority checked:** A search of the signed act for "emotion" and "biometric" found no hits. Research use outside consequential decisions is out of scope.

---

### California (CCPA/CPRA)

**CA1. Non-profits are generally not "businesses" under the CCPA**
- **Claim:** "Business" is limited to entities "organized or operated for the profit or financial benefit of its shareholders or other owners" that meet a threshold. The revenue threshold is $25M, CPI-adjusted to $26,625,000 from 2025. A non-profit is caught only if it is controlled by, and shares common branding with, a covered business, or if it voluntarily certifies.
- **Quote:** Civ. Code §1798.140(d)(1): "A sole proprietorship, partnership, limited liability company, corporation, association, or other legal entity that is organized or operated for the profit or financial benefit of its shareholders or other owners … that does business in the State of California, and that satisfies one or more of the following thresholds".
- **Source:** https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.140 (as amended by Stats. 2025, Ch. 67 (AB 1170), eff. Jan 1, 2026). Adjusted threshold: https://privacy.ca.gov/laws-and-regulations/monetary-thresholds-in-the-ccpa/
- **Confidence:** High on the text. Medium on the adjusted-dollar figure: I took it from CPPA-linked search results and did not read the page directly.
- **Contrary authority checked:** §1798.140(d)(2)–(4) (control/common branding, joint ventures, voluntary certification) are the only routes that could reach a non-profit. Public universities are government bodies and not "businesses" (inference from the text; not separately verified).

**CA2. Biometric information and sensitive personal information**
- **Claim:** "Biometric information" means characteristics used or intended to be used to establish identity. Its "processing … for the purpose of uniquely identifying a consumer" is sensitive personal information (SPI), as are health data and, since 2025, "neural data". The right to limit SPI (§1798.121) does not apply to SPI "collected or processed without the purpose of inferring characteristics about a consumer". Private suits are available only for security breaches (§1798.150).
- **Quote:** §1798.140(c): ""Biometric information" means an individual's physiological, biological, or behavioral characteristics … that is used or is intended to be used singly or in combination with each other or with other identifying data, to establish individual identity." §1798.140(ae)(2): "(A) The processing of biometric information for the purpose of uniquely identifying a consumer. (B) Personal information collected and analyzed concerning a consumer's health." (ae)(1)(G)(ii): ""Neural data" means information that is generated by measuring the activity of a consumer's central or peripheral nervous system, and that is not inferred from nonneural information."
- **Source:** Civ. Code §§1798.140, 1798.121, 1798.150 on leginfo (URLs as above; §1798.121 and §1798.150 amended by Stats. 2024, Ch. 121 (AB 3286), eff. Jan 1, 2025).
- **Confidence:** High.
- **Contrary authority checked:** §1798.145(c)(1)(C) separately exempts personal information collected in a clinical trial or biomedical research study under the Common Rule. §1798.146(a)(5) covers research as defined in 45 CFR 164.501.

**CA3. CPPA regulations name facial-expression and emotion inference, but bind only "businesses"**
- **Claim:** The CPPA's ADMT and risk-assessment regulations were approved by OAL on Sept 23, 2025 (per law-firm reports). They define "physical or biological identification or profiling" to include inferring emotion from facial expression or vocal intonation. They require a risk assessment before processing SPI, or before processing personal information intended to train emotion-recognition technology.
- **Quote:** §7001(ee): ""Physical or biological identification or profiling" means identifying or profiling a consumer using automated measurements or analysis of their physical or biological characteristics … This includes using biometric information, vocal intonation, facial expression, and gesture (e.g., to identify or infer emotion). This does not include processing physical or biological characteristics that do not identify, and cannot reasonably be linked with, a particular consumer." §7150(b)(6): "Processing the personal information of consumers, which the business intends to use to … train a facial-recognition, emotion-recognition, or other technology that verifies a consumer's identity, or conducts physical or biological identification or profiling of a consumer."
- **Source:** CPPA approved regulation text, https://cppa.ca.gov/regulations/pdf/ccpa_updates_cyber_risk_admt_appr_text.pdf (Cal. Code Regs. tit. 11). OAL approval date per Skadden (Oct 2025), https://www.skadden.com/insights/publications/2025/10/california-finalizes-cppa-regulations
- **Confidence:** High on the text. Medium on the approval date: secondary source only.
- **Contrary authority checked:** These are regulations under the CCPA, so they reach only CCPA "businesses" (CA1).

---

### Other 2025–2026 state laws on emotion or neural/biometric inference

**O1. Neural-data laws (CA, CO, MT, CT) do not reach camera- or microphone-derived signals, and Montana expressly excludes breathing rate and pupil dilation**
- **Claim:** The state neural-data definitions all require *measuring nervous-system activity*. California excludes data "inferred from nonneural information". Montana's SB 163 (2025) expressly excludes downstream physical effects such as pupil dilation, motor activity and breathing rate. Colorado's HB24-1058 "biological data", which includes neural data, is sensitive only when used for identification. Connecticut's SB 1295 (signed June 24, 2025) covers central-nervous-system activity only.
- **Quote:** Montana SB 163 (enrolled): "(b) The term does not include nonneural information, which means information about the downstream physical effects of neural activity, including by not limited to pupil dilation, motor activity, and breathing rate." Colorado HB24-1058 summary: "biological data … which data is used or intended to be used, singly or in combination with other personal data, for identification purposes. Biological data includes neural data".
- **Source:** Montana SB 163 enrolled bill, https://docs.legmt.gov/download-ticket?ticketId=3b69ebd2-d6c0-4dbf-8ba4-5a19b7cf86f7; https://leg.colorado.gov/bills/hb24-1058 (approved Apr 17, 2024, eff. Aug 7, 2024). CT definition and date per FPF (Aug 12, 2025), https://fpf.org/blog/the-neural-data-goldilocks-problem-defining-neural-data-in-u-s-state-privacy-laws/
- **Confidence:** High for Montana and Colorado (official text). Medium for Connecticut (FPF only). Montana's effective date (Oct 1, 2025) is per law-firm reports and was not seen in the enrolled text.
- **Contrary authority checked:** Montana's GIPA "entity" definition is tied to genetic testing or genetic data. I did not fully resolve how SB 163 extends obligations to neurotechnology-data holders.

**O2. No enacted state statute specifically regulating emotion recognition was found**
- **Claim:** I found no enacted 2025–2026 US state statute that specifically targets emotion recognition in a consumer or research setting. California AB 1883, which would bar employers' workplace-surveillance AI from collecting neural data or recognising emotional state, was reported as *pending* with the Governor as of Sept 14, 2026. It is workplace-only in any case.
- **Quote:** Kelley Drye (Sept 14, 2026): AB 1883 "prohibits employers from using workplace surveillance tools that employ AI to collect neural data or recognize an individual's emotional state".
- **Source:** https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/californias-2026-legislative-session-wraps-a-wave-of-privacy-and-ai-bills-reaches-the-governor-with-key-child-safety-and-ai-measures-signed-into-law
- **Confidence:** Medium. A negative finding from web searches is not exhaustive.
- **Contrary authority checked:** TRAIGA (T6) and SB26-189 (C5) were searched and have no emotion provision. The CPPA regulation (CA3) is the only binding US text found that names emotion inference.

---

### Not verified

- **CUBI "commercial purpose" as applied to unfunded academic research.** There is no statute definition, AG opinion or case, so it cannot be verified either way.
- **Any court holding that CUBI has no private right of action.** None was found. The conclusion rests on the statute naming only the AG.
- **How the Google $1.375B is split between biometric (CUBI) claims and the geolocation and incognito claims.** The OAG releases do not say.
- **Signing date of TRAIGA (HB 149).** I verified only the effective date (Jan 1, 2026, from the statute notes).
- **Current consolidated text of C.R.S. 6-1-1304(2)(d)/(o).** I read the 2021 enactment. Justia returned a bot check and the official C.R.S. is on Lexis. Later amendments to those subsections are not ruled out.
- **Colorado AG rule amendments implementing HB24-1130.** Not reviewed.
- **Why the MHMDA Amazon plaintiffs dismissed voluntarily (for example, settlement).** I read the docket entries only.
- **Whether any 2026 Washington session law amended RCW 19.373.** The official RCW shows 2023 c 191 only, and a search found nothing. I did not check the 2026 session-law tables.
- **Final status of California AB 1883.** Pending as of Sept 14, 2026; the Governor's action deadline has not been checked.
- **CCPA adjusted threshold ($26,625,000).** Taken from search results that point to privacy.ca.gov and cppa.ca.gov; I did not read the page directly.
- **Montana SB 163 effective date and entity scope for neurotechnology data.** Secondary sources only.

### Refuted leads

- **"Maxwell v. Amazon is pending / in motion practice" (several 2026 secondary sources).** Refuted. The consolidated case was voluntarily dismissed by both named plaintiffs and closed on June 6, 2025, with no MHMDA ruling (W5).
- **"Colorado AI Act takes effect June 30, 2026".** Superseded. SB24-205 was repealed and re-enacted by SB26-189 (signed May 14, 2026) as an ADMT and consequential-decisions law effective Jan 1, 2027 (C5).
- **"CUBI requires destruction one year after collection".** Inaccurate. The deadline is a reasonable time, no later than one year after the *purpose expires* (T1).
- **"Google paid $1.375B for biometric violations".** Overstated. The amount resolves combined geolocation, incognito and biometric claims (T5).
- **"TRAIGA regulates biometric or emotion AI generally".** Refuted. Its biometric section binds governmental entities only (excluding higher-education institutions) and excludes video- and audio-derived data. It has no emotion provision (T6).

### What this means for the platform (analysis, not law)

- **California CCPA/CPRA:** Probably does not reach an academic or non-profit operator, because the "business" definition is for-profit only. The CPPA's emotion-inference rules therefore also do not apply, unless a for-profit entity (for example a company deploying the platform) is the controller.
- **Texas CUBI:** Face landmarks used for action units, and voice features, could plausibly be a "record of face geometry" or a "voiceprint". Liability turns on the undefined "commercial purpose". Pure academic use has an argument for falling outside it, but there is no safe harbour, the AG construes the Act broadly, and penalties are per violation. Notice-and-consent plus a destruction schedule is cheap insurance.
- **Washington MHMDA:** This is the most plausible reach for a non-profit, because any legal entity is covered and private CPA suits are possible. A breathing waveform (a vital sign) and emotion or affect inferences could be "consumer health data". The clean path is the IRB-governed research carve-out, which puts weight on each study having IRB approval and oversight. The platform should make that a first-class, recorded study attribute.
- **Washington RCW 19.375:** Very unlikely to apply. There is no enrollment into an identity-matching database and no sale for marketing, and recordings and data derived from them are excluded.
- **Colorado CPA biometric rules (HB24-1130):** These apply regardless of size and cover non-profits. The risk is that facial geometry or voice features "can be processed" to identify someone even if the platform never does so. The Common Rule research exemption and the state-university non-commercial exemption are the likely outs. Otherwise, a public retention policy with 24-month and purpose-based deletion, pre-collection notice, and a no-sale commitment would be needed. Retained raw video under a consent tier is the part most likely to attract these duties.
- **Colorado AI law (SB26-189):** Not implicated, since research use involves no consequential decisions.
- **Neural-data laws:** Not implicated. Camera-derived breathing and gaze or pupil signals are expressly "nonneural" in Montana and "inferred from nonneural information" in California.
- **Design implications common to all these laws:** keep derived features non-identifying (no templates, no cross-session matching), keep raw-video retention time-boxed with deletion tied to purpose, obtain explicit separate consent for any sharing, and never sell data. Those measures satisfy the strictest common denominator across TX, WA and CO.


---

## EU AI Act

Research backing, not legal advice. Checked on 2026-09-26.

**How the sources were obtained.** EUR-Lex (`eur-lex.europa.eu`) sent back an HTTP 202 bot challenge to automated fetches. I therefore took the official Official Journal (OJ) texts from the Publications Office cellar. For the AI Act that is `publications.europa.eu/resource/celex/32024R1689`, which is the OJ L 2024/1689 XHTML file. For the Omnibus it is `publications.europa.eu/resource/celex/32026R1744`, the OJ L 2026/1744 file. These are the same texts that EUR-Lex serves. The quotes below were extracted from those files by machine and were not retyped. Commission guidance comes from the PDFs linked on digital-strategy.ec.europa.eu, and the quotes were extracted with pdftotext. Source texts were downloaded during the session and are not committed.

---

### 1. Scientific-research exclusion: Art 2(6)

- **Claim:** The Act does not apply at all to AI systems that are specifically developed **and** put into service for the *sole* purpose of scientific R&D. The exclusion also covers their output. The Omnibus did not amend Art 2(6).
- **Quote (Art 2(6)):** "This Regulation does not apply to AI systems or AI models, including their output, specifically developed and put into service for the sole purpose of scientific research and development."
- **Quote (Recital 25, key sentences):** "It is therefore necessary to exclude from its scope AI systems and models specifically developed and put into service for the sole purpose of scientific research and development. … Furthermore, without prejudice to the exclusion of AI systems specifically developed and put into service for the sole purpose of scientific research and development, any other AI system that may be used for the conduct of any research and development activity should remain subject to the provisions of this Regulation. In any event, any research and development activity should be carried out in accordance with recognised ethical and professional standards for scientific research and should be conducted in accordance with applicable Union law."
- **Quote (Commission Art 50 guidelines, para 21, 20.7.2026):** "However, if those systems are put into service or their outputs are being used for other purposes than for the sole purpose of scientific research and development, the relevant transparency obligations in Article 50 AI Act would still need to be complied with." The worked example that follows reads: "if researchers develop and place on the market or put into service an interactive AI system and wish to investigate whether natural persons are able to distinguish between AI systems and humans … they do not need to implement the respective transparency obligations under Article 50(1) and (2) AI Act. However, if the same interactive AI system is also put into service for purposes other than research and development, the relevant transparency obligations in Article 50 AI Act would need to be complied with."
- **Quote (prohibited-practices guidelines C(2025) 5052, para 31):** "research into cognitive and behavioural responses to AI-driven subliminal or deceptive stimuli … Such research is permitted, since it is excluded from the scope of the AI Act, notwithstanding the prohibition in Article 5(1)(a) AI Act."
- **Source:** Reg (EU) 2024/1689, OJ L 12.7.2024, http://data.europa.eu/eli/reg/2024/1689/oj. Art 50 guidelines, C(2026) 5054 final annex, 20.7.2026, https://ec.europa.eu/newsroom/dae/redirection/document/131215. Prohibited-practices guidelines, C(2025) 5052 final, 29.7.2025, https://ec.europa.eu/newsroom/dae/redirection/document/112367.
- **Confidence:** high for the text. Medium for how it applies to a tool that is distributed to third parties (see "What this means for the platform").
- **Contrary authority checked:** Omnibus Art 1(2) amends only Art 2(2), 2(7) and adds 2(13); paragraphs 6, 8 and 12 are unchanged. The draft high-risk guidelines (19.5.2026) apply Art 2(6) only in passing, to "AI systems used by academic institutions for modelling electoral behaviour for research purposes … it is likely that such AI system would be excluded under Article 2(6)". That is "likely", not certain. Scholarship: Finck, "In Search of the Lost Research Exemption", *GRUR International* 74(10), 19.8.2025, https://academic.oup.com/grurint/article/74/10/903/8238058. She argues that the "sole purpose" test is narrow and unclear, and that it fits badly with research whose outputs later find other applications. She calls for official guidance. No CJEU case law exists.

### 2. Pre-market R&D exclusion: Art 2(8)

- **Claim:** R&D and testing *before* an AI system is placed on the market or put into service are outside the Act. Testing in real-world conditions is not covered. The Act applies in full once the system is placed on the market or put into service.
- **Quote (Art 2(8)):** "This Regulation does not apply to any research, testing or development activity regarding AI systems or AI models prior to their being placed on the market or put into service. Such activities shall be conducted in accordance with applicable Union law. Testing in real world conditions shall not be covered by that exclusion."
- **Quote (C(2025) 5052, para 32):** "The exclusion in Article 2(8) AI Act is, however, without prejudice to the obligation to comply with the AI Act where an AI system is placed on the market or put into service as a result of such research and development activity. Testing in real-world conditions within the meaning of the AI Act is also not covered by that exclusion."
- **Relevant definitions (Art 3):** (9) "'placing on the market' means the first making available of an AI system or a general-purpose AI model on the Union market"; (10) "'making available on the market' means the supply of an AI system … for distribution or use on the Union market in the course of a commercial activity, whether in return for payment or free of charge"; (11) "'putting into service' means the supply of an AI system for first use directly to the deployer or for own use in the Union for its intended purpose"; (12) "'intended purpose' means the use for which an AI system is intended by the provider, including the specific context and conditions of use, as specified in the information supplied by the provider in the instructions for use, promotional or sales materials and statements, as well as in the technical documentation".
- **Source:** as in finding 1.
- **Confidence:** high.
- **Contrary authority checked:** The Omnibus did not amend Art 2(8). It did widen real-world testing outside sandboxes (new Art 60 wording and Art 60a), which is not relevant here.

### 3. Free and open-source exemption: Art 2(12). Art 5 and Art 50 are carved back in (verified)

- **Claim:** The exemption for free and open-source (FOSS) systems does **not** apply to high-risk systems, Art 5 systems or Art 50 systems. An emotion recognition system is both an Annex III high-risk system and an Art 50(3) system, so it cannot use Art 2(12). Monetised components also lose the benefit. Pure components that are not themselves an AI system are outside Art 50.
- **Quote (Art 2(12)):** "This Regulation does not apply to AI systems released under free and open-source licences, unless they are placed on the market or put into service as high-risk AI systems or as an AI system that falls under Article 5 or 50."
- **Quote (Recital 102):** A FOSS licence is one that "allows them to be openly shared and where users can freely access, use, modify and redistribute them or modified versions thereof".
- **Quote (Recital 103):** "AI components that are provided against a price or otherwise monetised, including through the provision of technical support or other services, including through a software platform, related to the AI component, or the use of personal data for reasons other than exclusively for improving the security, compatibility or interoperability of the software, with the exception of transactions between microenterprises, should not benefit from the exceptions provided to free and open-source AI components."
- **Quote (Art 50 guidelines, para 23–24):** "providers and deployers of open-source AI systems within the scope of Article 50 AI Act still need to ensure compliance with their respective transparency obligations." And: "providers of free and open-source AI components that cover software, data, models, tools, services or processes for customisation and integration into an AI system and that do not constitute in themselves (in part or in whole) an AI system, are not subject to the transparency obligations in Article 50 AI Act."
- **Quote (C(2025) 5052, para 36):** "This means that providers of AI systems cannot benefit from this exclusion if the AI system they place on the market or put into service constitutes a prohibited practice under Articles 5 AI Act."
- **Source:** as in finding 1.
- **Confidence:** high.
- **Contrary authority checked:** The Omnibus does not amend Art 2(12). I found no guidance that treats a non-commercial ("NC") licence as FOSS. Recital 102 requires that users can "freely … use", which suggests an NC licence is **not** FOSS for this purpose. That is my inference and not a ruling.

### 4. Annex III point 1(c): emotion recognition is high-risk in every setting, not just the workplace or education

- **Claim:** Every AI system "intended to be used for emotion recognition" is high-risk under Art 6(2), wherever it is used, unless it is prohibited under Art 5(1)(f) or the Art 6(3) filter applies. Point 1 carries the proviso "in so far as their use is permitted under relevant Union or national law". The Omnibus did not change Annex III point 1. It changed only the date on which the high-risk obligations apply (finding 8).
- **Quote (Annex III, point 1):** "Biometrics, in so far as their use is permitted under relevant Union or national law: … (b) AI systems intended to be used for biometric categorisation, according to sensitive or protected attributes or characteristics based on the inference of those attributes or characteristics; (c) AI systems intended to be used for emotion recognition."
- **Quote (Recital 54):** "… and emotion recognition systems that are not prohibited under this Regulation, should be classified as high-risk."
- **Quote (draft high-risk guidelines, para 126 example):** "emotion recognition systems outside the areas of workplace and education institutions, as well as such systems used in the areas of workplace and education institutions, when used for medical or safety reasons, are not prohibited, but qualify as high-risk."
- **Quote (draft high-risk guidelines, para 177, examples inside 1(c)):** "An AI system for the gaming industry that is intended to measure a gaming experience to further improve the product (real-life gaming experience). The AI system tracks body posture, facial expressions, eye closures and gazes to measure the reaction of the player, including their excitement, anger, frustration, amusement … It also identifies or infers gamers' emotions based on their biometric data." The same list includes a call-centre system that "evaluates vocal tone, pitch and volume to gauge customer satisfaction level for statistical reasons".
- **Quote (Art 50 guidelines, para 102, final):** "Since all emotion recognition systems are also classified as high-risk, unless prohibited under Article 5(1)(f) AI Act in the areas of workplace and education, the transparency obligation in Article 50(3) AI Act should apply in conjunction with the other safeguards and requirements applicable to high-risk AI systems."
- **Source:** AI Act as above. Draft Commission guidelines on the classification of high-risk AI systems, published 19.5.2026, https://ec.europa.eu/newsroom/dae/redirection/document/128561 (library page https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-classification-high-risk-ai-systems). Art 50 guidelines as above.
- **Confidence:** high for the text. The high-risk guidelines are still a **draft** (finding 9).
- **Contrary authority checked:** I looked for any narrowing of 1(c) to particular sectors and found none. Draft guidelines para 77 confirms the test turns on intended purpose: "If the intended purpose does not encompass one of the use cases listed in Annex III AI Act, the system is not 'intended to be used' for such a use case and therefore cannot be classified as high-risk".

### 5. Art 6(3) derogation from high-risk status

- **Claim:** An Annex III system is not high-risk if it poses no significant risk **and** meets one of four exhaustive conditions. A system that performs profiling is always high-risk. A provider relying on 6(3) must document its assessment and register. The Omnibus kept registration but slimmed down the Annex VIII content. The draft guidelines give **no** Art 6(3) example for emotion recognition and say the conditions "must be interpreted narrowly".
- **Quote (Art 6(3)):** "By derogation from paragraph 2, an AI system referred to in Annex III shall not be considered to be high-risk where it does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making. The first subparagraph shall apply where any of the following conditions is fulfilled: (a) the AI system is intended to perform a narrow procedural task; (b) the AI system is intended to improve the result of a previously completed human activity; (c) the AI system is intended to detect decision-making patterns or deviations from prior decision-making patterns and is not meant to replace or influence the previously completed human assessment, without proper human review; or (d) the AI system is intended to perform a preparatory task to an assessment relevant for the purposes of the use cases listed in Annex III. Notwithstanding the first subparagraph, an AI system referred to in Annex III shall always be considered to be high-risk where the AI system performs profiling of natural persons."
- **Quote (Art 6(4)):** "A provider who considers that an AI system referred to in Annex III is not high-risk shall document its assessment before that system is placed on the market or put into service. Such provider shall be subject to the registration obligation set out in Article 49(2)."
- **Quote (draft high-risk guidelines, para 88):** "As Article 6(3) represents an exception from rules aimed at (among others) protecting fundamental rights, the conditions must be interpreted narrowly."
- **Quote (Omnibus, Recital 23):** "While it remains crucial for effective market surveillance and public accountability that such AI systems are registered in the EU database, the registration requirements should be simplified and made more proportionate."
- **Source:** AI Act. Draft high-risk guidelines (19.5.2026). Reg (EU) 2026/1744 (OJ L 24.7.2026), http://data.europa.eu/eli/reg/2026/1744/oj.
- **Confidence:** high for the text. Low for whether any 6(3) condition fits an emotion-inferring research tool. Conditions (a) to (d) are framed around decision-making, and none maps cleanly onto measuring a participant.
- **Contrary authority checked:** The Omnibus adds Art 6(1a)–(1c), which deal with safety components under Annex I only. Art 6(3) is unchanged.

### 6. Art 50(3): transparency duty on deployers of emotion recognition and biometric categorisation, which applies from 2 August 2026

- **Claim:** A deployer must tell exposed persons that the system is operating. The only exception is for systems permitted by law for criminal-offence detection, prevention or investigation. The information must be given at the latest at first exposure. The duty applies from 2 Aug 2026, and the Omnibus did not defer it. It deferred only Art 50(2) watermarking for generative systems already on the market, to 2 Dec 2026.
- **Quote (Art 50(3)):** "Deployers of an emotion recognition system or a biometric categorisation system shall inform the natural persons exposed thereto of the operation of the system, and shall process the personal data in accordance with Regulations (EU) 2016/679 and (EU) 2018/1725 and Directive (EU) 2016/680, as applicable. This obligation shall not apply to AI systems used for biometric categorisation and emotion recognition, which are permitted by law to detect, prevent or investigate criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties, and in accordance with Union law."
- **Quote (Art 50(5)):** "The information referred to in paragraphs 1 to 4 shall be provided to the natural persons concerned in a clear and distinguishable manner at the latest at the time of the first interaction or exposure. The information shall conform to the applicable accessibility requirements."
- **Quote (Art 50 guidelines, paras 100, 105, 110):** "The obligation therefore applies regardless of whether the persons are exposed to such systems in real-time or those systems are operated ex post." / "The AI Act does not require including information about the reasons for the system's operation …" / "The information obligation under Article 50(3) AI Act does not, in itself render the use of an emotion recognition and biometric categorisation system lawful. … In certain cases, deployers can consider adding notifications pursuant to Article 50(3) AI Act to the information provided to data subjects under Union data protection law."
- **Quote (Art 113, date):** "It shall apply from 2 August 2026." Art 50 is in Chapter IV, and no exception in Art 113 (original or as amended) covers Chapter IV.
- **Quote (Omnibus, new Art 111(4)):** "Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video or text content, that have been placed on the market before 2 August 2026 shall take the necessary steps in order to comply with Article 50(2) by 2 December 2026."
- **Source:** AI Act. Reg (EU) 2026/1744. Art 50 guidelines C(2026) 5054, 20.7.2026. The Commission policy page (https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-transparency-obligations) states: "Article 50 of the AI Act applies from 2 August 2026."
- **Confidence:** high.
- **Contrary authority checked:** The Omnibus replaces only Art 50(7) (codes of practice). Paragraph 3 is unchanged.

### 7. Where Art 3(39) stops, per the Commission's guidance: facial expressions, a smile, physiological signals

- **Claim (a), a smile or other expression alone is not emotion recognition:** Detecting a readily apparent expression, such as a smile, is not emotion recognition. **Concluding** that the person is happy is. The Commission's own example of counting smiles is out of scope.
  - **Quote (C(2025) 5052, para 249):** "However, when these readily apparent expressions or gestures are used for identifying or inferring emotions or intentions, they are covered by the prohibition. For example, – The observation that a person is smiling is not emotion recognition. – Identifying whether a person is sick is not emotion recognition. – A TV broadcaster using a device that allows to track how many times its news presenters smile to the camera is not emotion recognition. – Concluding that a person is happy is emotion recognition. An AI system that infers that an employee is unhappy, sad or angry towards customers (e.g., from body gestures, a frown or the lack of a smile) is 'emotion recognition'."
  - The draft high-risk guidelines repeat this for Annex III 1(c) at para 177: "The mere observation that a person is smiling is not emotional recognition."
- **Claim (b), emotions are read widely and "attitudes" do not avoid the definition:**
  - **Quote (para 247–248):** "the concept of emotions or intentions should be understood in a wide sense and not interpreted restrictively. … These examples are not exhaustive." "The prohibition should not be circumvented by referring to attitudes, and includes cases where the AI system finds on the basis of the biometric data that a person is showing for example an angry attitude."
- **Claim (c), physiological and behavioural signals are biometric data, and arousal or stress count as emotions:**
  - **Quote (para 251):** "Behavioural biometrics encompass a variety of modalities … ranging from signatures, gait, voice, and keystrokes through to eye tracking and heartbeats, electroencephalography (EEG), or electrocardiograms (ECG)." And: "An AI system inferring emotions from key stroke (way of typing), facial expressions, body postures or movements is based on biometric data".
  - **Quote (para 255 example):** "An education institution using AI-based eye tracking software … (gaze point …) is not prohibited, because the system does not identify or infer emotions. By contrast, if the system is also used to detect emotions, such as emotional arousal and anxiousness, this would fall within the scope of the prohibition."
  - **Quote (para 263 example):** "An employer would be prohibited from deploying AI-enabled devices … for measuring anxiety based on measured stress levels or for measuring boredom of employees".
  - **Quote (draft high-risk guidelines, para 125):** "the definition of biometric data in the AI Act does not include the wording 'which allow or confirm the unique identification' … since it aims to cover AI systems that use biometric data not only in cases where the AI system identifies an individual".
- **Claim (d), the prohibition is limited by the four conditions in para 242:** placing on the market, putting into service or use; inferring emotions; workplace or education; not for medical or safety reasons. Para 239 notes: "Emotion recognition systems that do not fall under the prohibition are considered high-risk pursuant to point (1)(c) of Annex III AI Act."
- **Claim (e), research settings:** The guidelines address research **only** in the general scope section (paras 30–33, R&D exclusions). The emotion recognition chapter (section 7) does not discuss research participants or academic studies. The paras 254–255 examples on role-play, training and language apps are the closest analogues.
- **Source:** Commission Guidelines on prohibited AI practices. The content was approved on 4.2.2025 as C(2025) 884 final (https://ec.europa.eu/newsroom/dae/redirection/document/112366). The formal Communication is C(2025) 5052 final of 29.7.2025, and it is the document the Commission page now serves as "Guidelines … (English)" (https://ec.europa.eu/newsroom/dae/redirection/document/112367). Landing page dated 04 February 2025: https://digital-strategy.ec.europa.eu/en/library/commission-publishes-guidelines-prohibited-artificial-intelligence-ai-practices-defined-ai-act. The page states that they "are non-binding".
- **Confidence:** high that the quotes are accurate against C(2025) 5052. Medium that the paragraph numbers match the February 2025 text (see Not verified).
- **Contrary authority checked:** No guidance mentions FACS "action units", AU intensities or valence. I searched all three Commission documents for "action unit", "FACS" and "valence" and found nothing. Draft high-risk guidelines para 390 lists "micro-expressions or facial muscle activity" as polygraph modalities under Annex III 7(a) in the border context, which is not relevant here. On voice, the draft high-risk guidelines (law-enforcement examples, around para 362) treat tools that "transcribe interviews and flag changes in tone (e.g. higher tone, slower/faster speaking pace), without drawing conclusions" as outside 6(b), but add: "It should, however be checked whether a particular use case would not amount to emotion recognition system and thus fall under point 1 of the Annex III". The Art 50 guidelines (July 2026) cite C(2025) 5052 as the current prohibited-practices guidance (footnote 12), so I found no later revision.

### 8. Digital Omnibus on AI: adopted and in force; Annex III high-risk obligations deferred to 2 December 2027

- **Claim:** The Commission proposed the Omnibus as COM(2025) 836 on 19.11.2025 (procedure 2025/0359(COD)). Parliament adopted its position on 16.6.2026 and the Council decided on 29.6.2026. It was signed on 8.7.2026 as **Regulation (EU) 2026/1744**, published in the OJ on 24.7.2026, and entered into force on 27.7.2026 ("third day following that of its publication"). Chapter III Sections 1–3 (classification, requirements and provider/deployer obligations, which include Art 26 deployer duties) now apply from **2 Dec 2027** for Annex III systems and from **2 Aug 2028** for Annex I systems. The new Art 5 nudification/CSAM prohibitions apply from 2 Dec 2026. Articles 102–110 apply from 27 Jul 2026. Art 4 on AI literacy is softened to "take measures to support".
- **Quote (Omnibus Art 1(40), new Art 113 third para (c)):** "Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from: (i) 2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and (ii) 2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I".
- **Quote (new Art 113 (a)):** "Chapters I and II shall apply from 2 February 2025, with the exception of Article 5(1), first subparagraph, points (ba) and (bb), and Article 5(1a) and (1b) which shall apply from 2 December 2026".
- **Quote (new Art 111(2), grace period):** "this Regulation shall apply to operators of high-risk AI systems … that have been placed on the market or put into service before the date of application of Chapter III referred to in Article 113, only if, as from that date, those systems are subject to significant changes in their designs." Recital 39 explains that the grace period attaches to the "type and model" once the first unit is lawfully placed.
- **Source:** Reg (EU) 2026/1744, OJ L 24.7.2026, http://data.europa.eu/eli/reg/2026/1744/oj. Commission news "AI Omnibus enters into force", 27.7.2026, https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force. Proposal: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex:52025PC0836.
- **Confidence:** high, from the OJ text itself.
- **Contrary authority checked:** Search-result summaries of law-firm alerts agree on the dates: K&L Gates, "EU Digital Omnibus on AI Enters Into Force" (URL dated 7-31-2026), and White & Case, "EU AI Omnibus enters into force". I did not read either in full; the OJ text is the primary source here. The Omnibus does not amend Art 2(6), 2(8), 2(12), Art 3(39)/(40), Art 5(1)(f), Art 6(3), Art 50(3) or Annex III point 1. I checked this against its full list of amending instructions.
- **What applied from 2 Aug 2026 (original Art 113 general date, as amended):** Chapter IV (Art 50(1), (3) and (4); 50(2) for new systems, with the transitional date above for existing ones), together with the rest of the Regulation that is not otherwise dated. That does **not** include Chapter III Sections 1–3, which are now Dec 2027 or Aug 2028. Already applying before that: Chapters I–II (definitions, AI literacy, Art 5 prohibitions) from 2 Feb 2025, and Chapter III Section 4, Chapter V (GPAI), Chapter VII, Chapter XII (penalties) and Art 78 from 2 Aug 2025.

### 9. High-risk classification guidelines are still in draft

- **Claim:** The Art 6(5) guidelines were due by 2 Feb 2026. As of this check they exist only as a **draft** published on 19.5.2026, with a targeted consultation open until 23.7.2026. The Commission says the final text will be adopted after the consultation. The final Art 50 guidelines (para 101) already point to "the Commission guidelines on the classification of high-risk AI systems" for the meaning of "emotion recognition system".
- **Quote (Commission policy page):** "Following the publication of the draft, another targeted stakeholder consultation is open until 23 July 2026. Feedback received is going to be incorporated in the final version of the guidelines before adoption by the Commission."
- **Source:** https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-high-risk-systems (fetched 2026-09-26).
- **Confidence:** medium. The page may be stale, and a final version could have appeared without the page being updated.
- **Contrary authority checked:** One search summary claimed "final guidelines will be adopted by the end of 2026". I could not trace that to a primary source.

### 10. Is an engine that outputs action units a "biometric categorisation system" under Art 3(40)?

- **Claim:** Probably not, but the question is unresolved. Art 3(40) requires assigning *natural persons* to *specific categories*. Recital 16 and the guidelines describe categories as attributes of the person (sex, age, hair or eye colour, tattoos, "behavioural or personality traits", ethnicity and so on). Continuous frame-level AU intensities describe transient facial movements, not the person. If Art 3(40) did apply, the consequences would be (i) the Art 50(3) notice duty, which applies to "any" biometric categorisation system, and (ii) high-risk status only for categorisation by *sensitive* attributes under Art 9(1) GDPR (Annex III 1(b)), which AUs are not.
- **Quote (Art 3(40)):** "'biometric categorisation system' means an AI system for the purpose of assigning natural persons to specific categories on the basis of their biometric data, unless it is ancillary to another commercial service and strictly necessary for objective technical reasons".
- **Quote (Recital 16):** "Such specific categories can relate to aspects such as sex, age, hair colour, eye colour, tattoos, behavioural or personality traits, language, religion, membership of a national minority, sexual or political orientation."
- **Quote (C(2025) 5052, para 276):** "The categorisation of an individual by a biometric system is typically the process of establishing whether the biometric data of an individual belongs to a group with some pre-defined characteristic. … Persons may also simply be categorised for statistical reasons, without being identified and without the objective to identify them."
- **Quote (Art 50 guidelines, para 104):** "Importantly, unless prohibited under Article 5(1)(g) AI Act, Article 50(3) AI Act applies to any biometric categorisation systems (e.g. age or gender classification based on biometric data), regardless of whether they fall or not in the scope of high-risk AI systems under the AI Act."
- **Quote (draft high-risk guidelines, para 170):** "biometric data must be used as an input, while a sensitive or protected attribute or characteristic is the output of the AI system inferred from the biometric data."
- **Source:** as above.
- **Confidence:** medium-low. No guidance addresses AU output, and "behavioural … traits" is open-ended. The riskier boundary is Art 3(39), not 3(40): the moment AUs are mapped to emotions, the system is an emotion recognition system.
- **Contrary authority checked:** I found none that classifies AU or facial-expression coding as biometric categorisation. The caller's phrase "the 7-day definition problem" did not match anything I could locate. I have treated it as meaning "the Art 3(39)/3(40) definitional boundary".

---

### Not verified

- **February vs July paragraph numbering.** The Commission page now serves C(2025) 5052 final (29.7.2025) as the English guidelines. The 4.2.2025 C(2025) 884 file is only a 2-page approval note. I did not obtain the separately hosted February 2025 annex text, so I cannot confirm that paras 30–36 and 239–263 carry the same numbers there. Cite C(2025) 5052.
- **Final high-risk classification guidelines.** I did not confirm whether they were adopted after 23.7.2026. The Commission page fetched on 26.9.2026 still describes a draft.
- **Corrigenda to Reg 2024/1689.** A cellar lookup for `32024R1689R(01)`–`(03)` returned 404, which may be a URL-format problem. I could not confirm that no corrigendum touches Art 2(6), 2(12), 3(39), 3(40), 50(3) or Annex III(1)(c). No secondary source reported one.
- **National implementing law.** Annex III point 1 applies "in so far as their use is permitted under relevant Union or national law". I did not survey Member State law restricting emotion recognition in research.
- **Whether a university subject pool counts as an "education institution" or "workplace" under Art 5(1)(f).** No guidance addresses research participants who are students or paid staff. It matters only if the Art 2(6) exclusion does not apply.
- **Whether free, non-commercial public release is "placing on the market".** That requires "in the course of a commercial activity" (Art 3(10)). If it is not, the relevant trigger is "putting into service". I found no guidance on non-commercial academic distribution.

### Refuted leads

- **"The Omnibus delayed Art 50."** Refuted. Only Art 50(2) marking for generative systems already on the market before 2.8.2026 received a transitional date (2.12.2026). Art 50(3) applied from 2.8.2026.
- **"Annex III obligations still start 2 Aug 2026."** Refuted by Reg 2026/1744: 2.12.2027.
- **"The Omnibus links high-risk dates to availability of standards."** That was the Nov 2025 **proposal** (COM(2025) 836). The adopted text sets fixed dates.
- **"The Feb 2025 guidelines are the current version."** Superseded in form. The adopted Communication is C(2025) 5052 final (29.7.2025), and the Art 50 guidelines of July 2026 cite it.
- **"Emotion recognition is high-risk only in the workplace or education."** Refuted. In those settings it is *prohibited*, subject to the medical and safety exceptions. Everywhere else it is high-risk under Annex III 1(c).
- **"Open-source release exempts it."** Refuted for emotion recognition by the carve-back in Art 2(12).

### What this means for the platform (analysis, not law)

- **Developer (Art 2(6) and 2(8)):** Building and testing the platform before release is covered by Art 2(8). Once it is released, Art 2(6) protects the platform only if it is "specifically developed … for the sole purpose of scientific research" as an **intended purpose** stated by the provider (Art 3(12) includes documentation and "promotional … statements"). A general behavioural-measurement tool released so that anyone can use it for anything risks falling under Recital 25's "any other AI system that may be used for the conduct of … research … should remain subject". Stating research-only purpose in the README, licence and documentation helps. A licence permissive enough to be FOSS works against a "sole purpose" claim, and a non-commercial licence works against the Art 2(12) FOSS claim (Recital 102). Art 2(12) is unavailable anyway if the system is an emotion recognition system.
- **Researcher who deploys it on participants:** The Commission's closest analogy (Art 50 guidelines para 21, researchers putting an interactive AI system into service to study human participants) treats that use as inside Art 2(6). This suggests a bona fide academic study using a research-only tool is outside the Act, including Art 5(1)(f) and Art 50(3). That stops as soon as the same deployment serves another purpose, such as commercial UX or marketing testing, product improvement or student assessment. The draft high-risk guidelines explicitly place a game-experience tool that tracks facial expressions and gaze to measure excitement and frustration inside Annex III 1(c).
- **Outputting AUs rather than emotion labels helps, but only partly:** Recital 18 and guidelines para 249 support the view that detecting a smile or frown and counting it is not emotion recognition. The definition, though, is purpose-based ("for the purpose of identifying or inferring"), and Recital 18 ends "unless they are used for identifying or inferring emotions". If the documentation, examples, dashboards or default analyses map AUs to happiness or arousal, the system's purpose becomes emotion recognition. A researcher who does that mapping is then plausibly using an emotion recognition system.
- **"Readily apparent" is the soft spot:** A frown or smile is named in Recital 18. Subtle or low-intensity AUs, and acoustic functionals such as jitter and shimmer, are not obviously "readily apparent". No guidance addresses FACS or AUs. Expect a regulator to look at what the outputs are used for rather than how they are labelled.
- **Breathing waveform and voice features:** Physiological and behavioural signals are "biometric data" under the AI Act's broad definition (paras 251–252; draft HR para 125). Using them to infer stress, anxiety or arousal is treated as emotion recognition (paras 255 and 263). Raw waveforms and rate estimates alone look like "physical states" or measurement, not emotions.
- **If the platform falls outside Art 2(6):** It would be an Annex III 1(c) high-risk system. Provider obligations would apply from 2.12.2027, with Art 111(2) grace for an unchanged type or model already placed before then. Deployers would owe the Art 50(3) notice from 2.8.2026 (already live) and the Art 5(1)(f) ban in workplace or education settings (live since 2.2.2025). The Art 6(3) filter looks like a poor fit.
- **Cheap hedge regardless of scope:** Build an Art 50(3)-style notice into the participant consent flow ("this session uses automated analysis of your face and voice …"). The Art 50 guidelines (para 110) endorse merging it with GDPR information, and it costs almost nothing. Keep the default outputs at AU and acoustic level, with no emotion or valence mapping shipped. Document the research-only intended purpose.
- **Open question worth a lawyer's view:** whether distributing the platform to other labs is "putting into service" by the developer for each lab's research, which keeps it inside 2(6), or making a general tool available, which puts it outside 2(6). No guidance or case law settles this.


---

Researched 2026-09-26. This is research backing, not legal advice. Quotes below are copied from primary texts that were downloaded during this session. Where a text came from a mirror, the finding says so. Source texts were downloaded during the session and are not committed.

Scope excludes points already established elsewhere: Art 4(14), EDPB Guidelines 3/2019, the existence of Art 9(2)(a)/(j), and Art 4(15).

## GDPR and UK GDPR

### A. Indirect special-category data, health data and emotion inference

**1. CJEU C-184/20 (OT v Vyriausioji tarnybinės etikos komisija): data that reveal special-category information indirectly fall within Art 9(1).**
- **Claim:** Art 9(1) covers data that reveal sensitive information "indirectly, following an intellectual operation involving deduction or cross-referencing". The Court applied this reading to data "concerning" health as well as to data "revealing" a category. It rejected a split between those two verb forms.
- **Quote:**
  - para 120: "it should be determined whether data that are capable of revealing the sexual orientation of a natural person by means of an intellectual operation involving comparison or deduction fall within the special categories of personal data".
  - para 123: "whilst the use, in those provisions, of the verb 'reveal' is consistent with the taking into account of processing not only of inherently sensitive data, but also of data revealing information of that nature indirectly, following an intellectual operation involving deduction or cross-referencing, the preposition 'concerning' seems, on the other hand, to signify the existence of a more direct and immediate link…"
  - para 124: "Such an interpretation, which would result in a distinction being drawn according to the type of sensitive data at issue, would not, however, be consistent with a contextual analysis of those provisions, in particular with Article 4(15) of the GDPR…"
  - para 127: "those provisions cannot be interpreted as meaning that the processing of personal data that are liable indirectly to reveal sensitive information concerning a natural person is excluded from the strengthened protection regime prescribed by those provisions, if the effectiveness of that regime and the protection of the fundamental rights and freedoms of natural persons that it is intended to ensure are not to be compromised."
  - Ruling point 2: "Article 8(1) of Directive 95/46 and Article 9(1) of Regulation 2016/679 must be interpreted as meaning that the publication, on the website of the public authority …, of personal data that are liable to disclose indirectly the sexual orientation of a natural person constitutes processing of special categories of personal data".
- **Source:** Judgment of the Court (Grand Chamber), 1 August 2022, ECLI:EU:C:2022:601. Official text: CELEX 62020CJ0184, fetched from the Publications Office (https://publications.europa.eu/resource/celex/62020CJ0184) because EUR-Lex and curia.europa.eu blocked automated fetches.
- **Confidence:** High.
- **Contrary authority checked:**
  - The narrower "concerning = direct link" reading appears only as the Advocate General's framing (para 123), and the Court rejected it (para 124).
  - A leaked November 2025 draft of the Digital Omnibus reportedly limited Art 9 to data that "directly" reveal. That wording is not in the official proposal (see finding 21 and Refuted leads).
  - No later CJEU judgment narrowing this holding was found. C-21/23 (2024) re-applies it.

**2. CJEU C-252/21 (Meta Platforms v Bundeskartellamt): the Art 9(1) prohibition applies whatever the controller's aim and whether or not the inference is accurate.**
- **Claim:** It does not matter whether the controller intends to derive sensitive information or whether the derived information is correct. If processing allows special-category information to be revealed, Art 9 applies.
- **Quote:**
  - para 69: "that fundamental prohibition, laid down in Article 9(1) of the GDPR, is independent of whether or not the information revealed by the processing operation in question is correct and of whether the controller is acting with the aim of obtaining information that falls within one of the special categories referred to in that provision."
  - para 70: "the objective thereof is to prohibit such processing, irrespective of its stated purpose."
- **Source:** Judgment (Grand Chamber), 4 July 2023, ECLI:EU:C:2023:537, CELEX 62021CJ0252 (Publications Office text).
- **Confidence:** High.
- **Contrary authority checked:** C-21/23 para 87 repeats this holding. The UK ICO applies a different, intention-based test (finding 8). No EU authority contradicting it was found.

**3. CJEU C-21/23 (Lindenapotheke): health data include data capable of revealing health status "by means of an intellectual operation involving collation or deduction", even with only a degree of probability.**
- **Claim:** "Data concerning health" is interpreted broadly. It is enough that data are *capable* of revealing health status by deduction, and probability is sufficient.
- **Quote:**
  - para 81: "the concept of 'data concerning health' referred to in Article 9(1) of that regulation … must be interpreted broadly".
  - para 83: "in order for personal data to be classified as data concerning health, within the meaning of Article 8(1) of Directive 95/46 and Article 9(1) of the GDPR, it is sufficient that they are capable of revealing information about the health status of the data subject by means of an intellectual operation involving collation or deduction".
  - para 87: "That fundamental prohibition is independent of whether or not the information revealed by the processing operation in question is correct and of whether the data controller is acting with the aim of obtaining information that falls within one of the special categories…"
  - para 90: "…constitutes data concerning health … even where it is only with a certain degree of probability, and not with absolute certainty, that those medicinal products are intended for those customers."
  - Ruling point 2: "…the information which the customers of that operator enter when ordering the medicinal products online, such as their name, the delivery address and the details required for individualising the medicinal products, constitutes data concerning health, within the meaning of those provisions, even where the sale of those medicinal products does not require a prescription."
- **Source:** Judgment (Grand Chamber), 4 October 2024, CELEX 62023CJ0021 (Publications Office final text). This matches the provisional curia text mirrored at https://collab.dpa.gr/wp-content/uploads/2024/10/CJEU_C-21.23-Lindenapotheke_en.pdf.
- **Confidence:** High.
- **Contrary authority checked:** Secondary sources (Bird & Bird; Taylor Wessing; the EU Law Analysis blog, Dec 2024) report that AG Szpunar's opinion of 25 April 2024 proposed a stricter "certain degree of certainty" threshold, and that the Court did not follow it. The AG opinion text was not read directly (see Not verified).

**4. EDPB Guidelines 03/2020: health data include information that "becomes health data by cross referencing" or "because of its usage in a specific context".**
- **Quote:**
  - para 7: "the term 'data concerning health' must be given a wide interpretation."
  - para 8, items 2 and 4: "2. Information that becomes health data by cross referencing with other data thus revealing the state of health or health risks (such as the assumption that a person has a higher risk of suffering heart attacks based on the high blood pressure measured over a certain period of time)." … "4. Information that becomes health data because of its usage in a specific context…"
- **Source:** EDPB Guidelines 03/2020 on the processing of data concerning health for the purpose of scientific research in the context of the COVID-19 outbreak, adopted 21 April 2020. https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_202003_healthdatascientificresearchcovid19_en.pdf
- **Confidence:** High.
- **Contrary authority checked:** None found. These guidelines were written for the COVID context, but they restate the general definition.

**5. WP29 (2015) health-data criteria for raw sensor data. This is the closest authority to a breathing waveform.**
- **Claim:**
  - A single physiological reading without context is generally not health data.
  - The same measure recorded over time, or combined with other data, or used to draw health conclusions, is health data.
  - Scale and retention matter.
- **Quote:**
  - "a single registration of a person's weight, blood pressure or pulse/heart rate (if not excessive in absolute terms), at least without any further information about age or sex, does not allow for the inference of information about the actual or likely future health status of that person. However, that aspect measured over time, especially in combination with age and sex, may be used to determine a significant aspect of an individual's health".
  - "personal data are health data when: 1. The data are inherently/clearly medical data 2. The data are raw sensor data that can be used in itself or in combination with other data to draw a conclusion about the actual health status or health risk of a person 3. Conclusions are drawn about a person's health status or health risk (irrespective of whether these conclusions are accurate or inaccurate…)".
  - fn 5: "a pedometer tracking and storing how many steps one has taken for a few days (and deleting such data after a week by default) may not process 'health data'. But an app combining several years' worth of … vital statistics, as well as a mood diary) will be processing health data."
  - "the systematic analysis of such messages for the purpose of diagnosis/health risk prevention or medical research certainly qualifies as the processing of health data."
- **Source:** Article 29 Working Party, Annex "health data in apps and devices" to its letter of 5 February 2015. https://ec.europa.eu/justice/article-29/documentation/other-document/files/2015/20150205_letter_art29wp_ec_health_data_after_plenary_annex_en.pdf
- **Confidence:** High on the text. Medium on its current weight: it predates the GDPR, and this session did not confirm that the EDPB endorsed it. Its "probability/aim" reasoning also sits uneasily with C-252/21 and C-21/23.
- **Contrary authority checked:** C-21/23 (probability is sufficient) and C-252/21 (aim is irrelevant) push further than WP29's "single reading" carve-out. How far that carve-out survives is unresolved.

**6. EDPS TechDispatch #1/2021 on Facial Emotion Recognition: facial emotion recognition (FER) can infer special-category data, including health data.**
- **Quote:**
  - "in some contexts, algorithms may infer special categories of personal data, such as political opinions or health data. … by the lack of facial expressions, algorithms are able to detect signs of alexithymia … This finding can be linked to severe psychiatric and neurological disorders, such as psychosis. Furthermore, analysis of historical data on one's emotional state may reveal other health conditions such as depression."
  - On necessity: "It has to be carefully assessed, whether deploying FER is indeed necessary for achieving the pursued objectives or whether there is a less intrusive alternative."
  - Disclaimer: "The contents of this publication do not imply a policy position of the EDPS."
- **Source:** EDPS TechDispatch Issue 1/2021, 26 May 2021. https://www.edps.europa.eu/system/files/2021-05/21-05-26_techdispatch-facial-emotion-recognition_ref_en.pdf
- **Confidence:** High on the text. Low on legal weight: it is expressly not a policy position.
- **Contrary authority checked:** The document makes no recommendation about on-device or local processing (see Refuted leads).

**7. EDPB-EDPS Joint Opinion 5/2021 on the AI Act: using AI to infer emotions is "highly undesirable", with a carve-out for health and research.**
- **Quote:** para 35: "the EDPB and the EDPS consider that the use of AI to infer emotions of a natural person is highly undesirable and should be prohibited, except for certain well-specified use-cases, namely for health or research purposes (e.g., patients where emotion recognition is important), always with appropriate safeguards in place and of course, subject to all other data protection conditions and limits including purpose limitation."
- **Source:** EDPB-EDPS Joint Opinion 5/2021, 18 June 2021. https://www.edpb.europa.eu/system/files/2021-06/edpb-edps_joint_opinion_ai_regulation_en.pdf
- **Confidence:** High.
- **Contrary authority checked:** The executive summary drops the carve-out ("should be prohibited."). The body text quoted above controls. This is a policy opinion on draft legislation, not an interpretation of Art 9. The final AI Act emotion-recognition rules were out of scope and not researched here.

**8. UK: the ICO applies an intention-based test to inferred special-category data, which diverges from CJEU C-252/21 and C-21/23.**
- **Quote:**
  - "Whether or not inferred data counts as special category data and triggers Article 9 depends on whether: your processing intends to make an inference linked to one of the special categories of data; or you intend to treat someone differently on the basis of inferred information linked to one of the special categories of data. If this is the case, then you are processing special category data regardless of how confident you are that the inference is correct."
  - "Even if you're not drawing an inference or treating people differently, there may still be an obvious risk that other people could (rightly or wrongly) infer something from the data … you should think carefully about how you ensure fairness…"
  - Page banner: "Due to changes made by the Data (Use and Access) Act, this guidance is under review and may be subject to change."
- **Source:** ICO, "What is special category data?". https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-is-special-category-data/ (fetched 2026-09-26). The page notes an update that "no longer focuses on the certainty of an inference"; its date was not captured.
- **Confidence:** High that this is the ICO's current published position.
- **Contrary authority checked:** This conflicts with C-252/21 para 69 and C-21/23 para 87, both of which make the controller's aim irrelevant. Both judgments postdate 31 Dec 2020. Their status in UK courts was not verified (see Not verified).

**9. UK: ICO biometric guidance (first phase, published 23 Feb 2024). Biometric data are defined by the qualities of the data, not how they are used. "Special category biometric data" requires use for unique identification. Other special-category status depends on intent to infer.**
- **Quote:**
  - "Personal information must meet specific requirements to be biometric data. These relate to qualities of the information itself, not how you use it."
  - "Not all biometric data is automatically special category biometric data. It only becomes this if you use it to uniquely identify someone."
  - "even if this is not your purpose, the biometric data you process may still be considered another type of special category information. For example, you could use biometric data to infer someone's racial or ethnic origin or consider it as health data. Whether you consider this to be special category information depends on if you intend to infer this information from the biometric data."
  - On transient processing: "It is still processing if you only briefly create, collect or store information (sometimes known as transient processing). … Data protection requirements still apply to you, regardless of how quickly you may delete it."
- **Source:** ICO, Biometric data guidance: Biometric recognition, "Key data protection concepts". https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/key-data-protection-concepts/. Publication date 23 Feb 2024 is per the ICO consultation page (https://ico.org.uk/about-the-ico/ico-and-stakeholder-consultations/2024/10/ico-consultation-on-the-draft-biometric-data-guidance/). The page is currently marked "under review" because of the DUAA.
- **Confidence:** High.
- **Contrary authority checked:**
  - Emotion recognition: the guidance does not address it. No "emotion" text was found on the pages checked.
  - The ICO's planned second phase (biometric classification) was not found as published.
  - ICO's AI and biometrics strategy page says: "Risks of bias and discrimination are particularly acute in speculative AI systems that attempt to infer traits, emotions or intentions from physical or behavioural characteristics … the science underpinning these systems is highly contested" (https://ico.org.uk/about-the-ico/our-information/our-strategies-and-plans/artificial-intelligence-and-biometrics-strategy/where-we-will-focus/; strategy launched 2025, exact date not captured).

**10. UK: ICO statement on emotion analysis, 26 October 2022.**
- **Quote:**
  - "Emotional analysis technologies process data such as gaze tracking, sentiment analysis, facial movements, gait analysis, heartbeats, facial expressions and skin moisture."
  - "Emotion analysis relies on collecting, storing and processing a range of personal data, including subconscious behavioural or emotional responses, and in some cases, special category data. This kind of data use is far more risky than traditional biometric technologies that are used to verify or identify a person."
  - Deputy Commissioner Stephen Bonner: "Developments in the biometrics and emotion AI market are immature. They may not work yet, or indeed ever." … "The only sustainable biometric deployments will be those that are fully functional, accountable and backed by science. As it stands, we are yet to see any emotion AI technology develop in a way that satisfies data protection requirements, and have more general questions about proportionality, fairness and transparency in this area."
  - "Organisations that do not act responsibly, posing risks to vulnerable people, or fail to meet ICO expectations will be investigated."
- **Source:** ICO press release "'Immature biometric technologies could be discriminating against people' says ICO in warning to organisations", 26 Oct 2022. The original ico.org.uk URL (…/news-and-blogs/2022/10/immature-biometric-technologies-…) returned 404 on 2026-09-26. The text was taken from the official-release republication at https://wired-gov.net/wg/news.nsf/articles/immature+biometric+technologies+could+be+discriminating+against+people+says+ico+in+warning+to+organisations+26102022091000?open= and matches TechCrunch and Computer Weekly reports.
- **Confidence:** Medium-high, because the text comes from a mirror.
- **Contrary authority checked:** The later ICO biometric guidance (2024) does not withdraw this statement. The 2025 AI and biometrics strategy repeats the "contested science" concern.

### B. DPIA

**11. Art 35(1) and 35(3), verbatim (identical in UK GDPR; no DUAA amendments to Art 35 are noted on legislation.gov.uk).**
- **Quote:**
  - 35(1): "Where a type of processing in particular using new technologies, and taking into account the nature, scope, context and purposes of the processing, is likely to result in a high risk to the rights and freedoms of natural persons, the controller shall, prior to the processing, carry out an assessment of the impact of the envisaged processing operations on the protection of personal data. A single assessment may address a set of similar processing operations that present similar high risks."
  - 35(3): "A data protection impact assessment referred to in paragraph 1 shall in particular be required in the case of: (a) a systematic and extensive evaluation of personal aspects relating to natural persons which is based on automated processing, including profiling, and on which decisions are based that produce legal effects concerning the natural person or similarly significantly affect the natural person; (b) processing on a large scale of special categories of data referred to in Article 9(1), or of personal data relating to criminal convictions and offences referred to in Article 10; or (c) a systematic monitoring of a publicly accessible area on a large scale."
  - Recital 91 also: "A data protection impact assessment should also be made where personal data are processed for taking decisions regarding specific natural persons following any systematic and extensive evaluation … or following the processing of special categories of personal data, biometric data…"
- **Source:** Regulation (EU) 2016/679, OJ L 119, 4.5.2016 (CELEX 32016R0679, Publications Office text). UK: https://www.legislation.gov.uk/eur/2016/679/article/35
- **Confidence:** High.
- **Contrary authority checked:** The Digital Omnibus proposal would move the Art 35(4)/(5) lists to EU level (EDPB proposes, Commission adopts by implementing act). It is not adopted (finding 21).

**12. WP248 rev.01: the nine criteria, and the "two criteria" rule of thumb. Endorsed by the EDPB and not superseded.**
- **Quote:**
  - Opening: "the following nine criteria should be considered."
  - "1. Evaluation or scoring, including profiling and predicting, especially from 'aspects concerning the data subject's performance at work, economic situation, health, personal preferences or interests, reliability or behavior, location or movements' (recitals 71 and 91)."
  - "2. Automated-decision making with legal or similar significant effect".
  - "3. Systematic monitoring: processing used to observe, monitor or control data subjects, including data collected through networks or 'a systematic monitoring of a publicly accessible area' (Article 35(3)(c))."
  - "4. Sensitive data or data of a highly personal nature: this includes special categories of personal data as defined in Article 9 … as well as personal data relating to criminal convictions or offences".
  - "5. Data processed on a large scale".
  - "6. Matching or combining datasets".
  - "7. Data concerning vulnerable data subjects (recital 75): … Vulnerable data subjects may include children …, employees, more vulnerable segments of the population requiring special protection (mentally ill persons, asylum seekers, or the elderly, patients, etc.), and in any case where an imbalance in the relationship between the position of the data subject and the controller can be identified."
  - "8. Innovative use or applying new technological or organisational solutions".
  - "9. When the processing in itself 'prevents data subjects from exercising a right or using a service or a contract'".
  - Rule of thumb: "In most cases, a data controller can consider that a processing meeting two criteria would require a DPIA to be carried out. … However, in some cases, a data controller can consider that a processing meeting only one of these criteria requires a DPIA."
- **Source:** WP29, Guidelines on DPIA, WP248 rev.01, adopted 4 April 2017, last revised 4 October 2017. PDF: https://ec.europa.eu/newsroom/article29/redirection/document/47711. EDPB list of endorsed WP29 guidelines (entry 6, no superseding document listed): https://www.edpb.europa.eu/endorsed-wp29-guidelines_en. Endorsed at the first EDPB plenary, 25 May 2018 (Endorsement 1/2018).
- **Confidence:** High.
- **Contrary authority checked:** The EDPB adopted a common DPIA *template* on 10 March 2026 (consultation 14 April to 9 June 2026). The EDPB news item says "it is not mandatory for organisations to use the EDPB template" and does not reference or replace WP248 (https://www.edpb.europa.eu/news/enhancing-compliance-and-consistency-edpb-adopts-dpia-template_en, 14 April 2026). Whether a final version has been adopted since June 2026 was not verified.

**13. National Art 35(4) lists that name biometric, behaviour/emotion or vulnerable-subject processing.**
- **Quote:**
  - **ICO (UK)**
    - "Innovative technology: processing involving the use of innovative technologies, or the novel application of existing technologies (including AI). A DPIA is required where this processing is combined with any of the criteria from the European guidelines."
    - "Biometrics: any processing of biometric data. A DPIA is required where this processing is combined with any of the criteria from the European guidelines."
    - "Tracking: processing which involves tracking an individual's geolocation or behaviour, including but not limited to the online environment."
    - "Targeting of children or other vulnerable individuals…"
    - Innovative-technology examples include "market research involving neuro-measurement (e.g. emotional response analysis and brain activity)" and "smart technologies (including wearables)".
    - Page banner: "Due to changes made by the Data (Use and Access) Act, this guidance is under review".
  - **Irish DPC**
    - "6) Processing biometric data to uniquely identify an individual or individuals or enable or allow the identification or authentication of an individual or individuals in combination with any of the other criteria set out in WP29 DPIA Guidelines."
    - "4) Systematically monitoring, tracking or observing individuals' location or behaviour."
    - It also notes: "it is good practice to carry out a DPIA for any major new project involving the use of personal data".
  - **CNIL (France)**
    - "Traitements de données biométriques aux fins d'identifier une personne physique de manière unique parmi lesquelles figurent des personnes dites « vulnérables » (élèves, personnes âgées, patients, demandeurs d'asile, etc.)".
    - No emotion or behaviour-analysis item.
  - **DSK (Germany)**
    - Item 13: "Automatisierte Auswertung von Video- oder Audio-Aufnahmen zur Bewertung der Persönlichkeit der Betroffenen". Example: "Ein Callcenter wertet automatisiert die Stimmungslage der Anrufer aus."
    - Item 11: "Einsatz von künstlicher Intelligenz zur Verarbeitung personenbezogener Daten zur Steuerung der Interaktion mit den Betroffenen oder zur Bewertung persönlicher Aspekte der betroffenen Person".
    - Item 1: biometric data "zur eindeutigen Identifizierung … wenn mindestens ein weiteres … Kriterium aus WP 248 Rev. 01 zutrifft".
- **Source:**
  - ICO "When do we need to do a DPIA?": https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/when-do-we-need-to-do-a-dpia/ (fetched 2026-09-26).
  - DPC "List of Types of Data Processing Operations which require a DPIA", 15 Nov 2018 (rev): https://www.dataprotection.ie/sites/default/files/uploads/2018-11/Data-Protection-Impact-Assessment.pdf
  - CNIL list (v2): https://www.cnil.fr/sites/default/files/atoms/files/liste-traitements-avec-aipd-requise-v2.pdf
  - DSK Muss-Liste, Version 1.1 of 17.10.2018: https://www.lda.bayern.de/media/dsfa_muss_liste_dsk_de.pdf
- **Confidence:** High on the texts.
- **Contrary authority checked:** No list found exempts research use. The DSK list is reported by secondary sources to cover the non-public sector (German public universities fall under Land law and Land authority lists). That scope was not verified in the PDF. Later revisions of the DPC and CNIL lists were not checked.

### C. Records of processing (Art 30)

**14. Art 30(1) contents and the Art 30(5) under-250 exemption. Special-category processing, non-occasional processing, or risky processing each defeat the exemption. UK text is identical.**
- **Quote:**
  - 30(1): "Each controller … shall maintain a record of processing activities under its responsibility. That record shall contain all of the following information: (a) the name and contact details of the controller and, where applicable, the joint controller, … (b) the purposes of the processing; (c) a description of the categories of data subjects and of the categories of personal data; (d) the categories of recipients …; (e) where applicable, transfers of personal data to a third country …; (f) where possible, the envisaged time limits for erasure of the different categories of data; (g) where possible, a general description of the technical and organisational security measures referred to in Article 32(1)."
  - 30(2): processors must keep a record of "all categories of processing activities carried out on behalf of a controller".
  - 30(5): "The obligations referred to in paragraphs 1 and 2 shall not apply to an enterprise or an organisation employing fewer than 250 persons unless the processing it carries out is likely to result in a risk to the rights and freedoms of data subjects, the processing is not occasional, or the processing includes special categories of data as referred to in Article 9(1) or personal data relating to criminal convictions and offences referred to in Article 10."
- **Source:** GDPR (CELEX 32016R0679). UK: https://www.legislation.gov.uk/eur/2016/679/article/30 (no DUAA amendment shown).
- **Confidence:** High.
- **Contrary authority checked:** The "Omnibus IV" proposal COM(2025) 501 (21 May 2025) would replace 30(5) with: "The obligations referred to in paragraphs 1 and 2 shall not apply to an enterprise or an organisation employing fewer than 750 persons unless the processing it carries out is likely to result in a high risk to the rights and freedoms of data subjects, within the meaning of Article 35." Its explanatory memorandum says a recital would clarify "that the processing of special categories of personal data in accordance with Article 9(2)(b) does not, as such, trigger the obligation" (https://commission.europa.eu/document/download/7fd9c846-b894-4f9f-b164-3b926d1b264b_en?filename=Proposal+GDPR+Omnibus.pdf). The EDPB/EDPS statement of 9 July 2025 welcomed it. **Adoption status was not verified** (see Not verified).

### D. Controller / processor allocation

**15. EDPB Guidelines 07/2020: "essential means" belong to the controller; tools and platforms can create joint control; the research-platform example.**
- **Quote:**
  - para 40: "'Essential means' are means that are closely linked to the purpose and the scope of the processing, such as the type of personal data which are processed ('which data shall be processed?'), the duration of the processing ('for how long shall they be processed?'), the categories of recipients ('who shall have access to them?') and the categories of data subjects ('whose personal data are being processed?'). … 'Non-essential means' concern more practical aspects of implementation, such as the choice for a particular type of hard- or software or the detailed security measures which may be left to the processor to decide on."
  - para 45: "It is not necessary that the controller actually has access to the data that is being processed."
  - para 55: "an important criterion to identify converging decisions in this context is whether the processing would not be possible without both parties' participation in the purposes and means in the sense that the processing by each party is inseparable, i.e. inextricably linked."
  - para 62: "If the entity involved in the processing does not pursue any purpose(s) of its own in relation to the processing activity, but is merely being paid for services rendered, it is acting as a processor rather than as a joint controller."
  - para 65: "This scenario can notably arise in case of platforms, standardised tools, or other infrastructure allowing the parties to process the same personal data and which have been set up in a certain way by one of the parties to be used by others that can also decide how to set it up. The use of an already existing technical system does not exclude joint controllership when users of the system can decide on the processing of personal data to be performed in this context."
  - para 67: "the choice made by an entity to use for its own purposes a tool or other system developed by another entity, allowing the processing of personal data, will likely amount to a joint decision on the means of that processing by those entities."
  - fn 29: "The provider of the system can be a joint controller if the criteria mentioned above are met, i.e. if the provider participates in the determination of purposes and means. Otherwise, the provider should be considered as a processor."
  - Example "Research project by institutes": "all institutes qualify as joint controllers for the personal data processing that is done by storing and disclosing information from this platform since they have decided together the purpose of the processing and the means to be used (the existing platform). Each of the institutes however is a separate controller for any other processing that may be carried out outside the platform for their respective purposes."
- **Source:** EDPB Guidelines 07/2020 on the concepts of controller and processor in the GDPR, Version 2.0, adopted 7 July 2021. https://www.edpb.europa.eu/system/files/2023-10/EDPB_guidelines_202007_controllerprocessor_final_en.pdf
- **Confidence:** High.
- **Contrary authority checked:** No later EDPB revision was found. Paras 65 and 67 and fn 29 all assume the tool provider takes part in, or provides, the processing. They do not address a developer who only publishes code (see finding 17 and Not verified).

**16. CJEU joint-controllership line of cases.**
- **Quote:**
  - **Wirtschaftsakademie (C-210/16)**
    - para 35: "the mere fact of making use of a social network such as Facebook does not make a Facebook user a controller jointly responsible for the processing of personal data by that network".
    - para 38: "Directive 95/46 does not, where several operators are jointly responsible for the same processing, require each of them to have access to the personal data concerned."
    - para 39: the administrator is a controller jointly with Facebook "by its definition of parameters depending in particular on its target audience and the objectives of managing and promoting its activities".
    - para 43: "the existence of joint responsibility does not necessarily imply equal responsibility of the various operators".
  - **Jehovan todistajat (C-25/17)**
    - para 68: "a natural or legal person who exerts influence over the processing of personal data, for his own purposes, and who participates, as a result, in the determination of the purposes and means of that processing, may be regarded as a controller".
    - para 75: joint controller "without it being necessary that the community has access to those data, or to establish that that community has given its members written guidelines or instructions in relation to the data processing."
  - **Fashion ID (C-40/17)**
    - para 74: a person "cannot be considered to be a controller … in the context of operations that precede or are subsequent in the overall chain of processing for which that person does not determine either the purposes or the means."
    - para 85: liability "is, however, limited to the operation or set of operations involving the processing of personal data in respect of which it actually determines the purposes and means".
  - **Nacionalinis visuomenės sveikatos centras (C-683/21)**, relevant to software development
    - para 31: it is necessary to examine "whether that entity actually exerted influence, for its own purposes, over the determination of the purposes and means of the processing in question."
    - Ruling 2: joint control "does not require that there be an arrangement between those entities".
    - Ruling 3: "the use of personal data for the purposes of the IT testing of a mobile application constitutes 'processing', … unless such data have been rendered anonymous … or unless it involves fictitious data which do not relate to an existing natural person."
- **Source:** Judgments of 5 June 2018 (ECLI:EU:C:2018:388), 10 July 2018 (ECLI:EU:C:2018:551), 29 July 2019 (ECLI:EU:C:2019:629) and 5 December 2023 (ECLI not captured). Texts are CELEX 62016CJ0210, 62017CJ0025, 62017CJ0040 and 62021CJ0683, from the Publications Office.
- **Confidence:** High.
- **Contrary authority checked:** No later narrowing was found. C-683/21 (2023) reaffirms and extends the line.

**17. Developers ("producers") of software are not addressed by Art 25. The GDPR only "encourages" them.**
- **Quote:**
  - Recital 78: "When developing, designing, selecting and using applications, services and products that are based on the processing of personal data or process personal data to fulfil their task, producers of the products, services and applications should be encouraged to take into account the right to data protection when developing and designing such products, services and applications and, with due regard to the state of the art, to make sure that controllers and processors are able to fulfil their data protection obligations."
  - EDPB 4/2019 para 94: "Although not directly addressed in Article 25, processors and producers are also recognized as key enablers for DPbDD, they should be aware that controllers are required to only process personal data with systems and technologies that have built-in data protection."
  - Same guidelines: "controllers … should not choose producers or processors who do not offer systems enabling or supporting the controller to comply with Article 25, because controllers will be held accountable for the lack of implementation thereof."
- **Source:** GDPR recital 78. EDPB Guidelines 4/2019 on Article 25, Version 2.0, adopted 20 October 2020: https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf
- **Confidence:** High.
- **Contrary authority checked:** No authority was found that makes a developer who only publishes code (and processes no data) a controller or processor. No authority was found that expressly says they are neither (see Not verified).

### E. On-device / in-browser processing as mitigation

**18. What regulators actually say about local processing and feature extraction.**
- **Quote:**
  - **EDPB 4/2019 (Art 25)**
    - para 74: "The controller should verify whether the relevant purposes can be achieved by processing less personal data, or having less detailed or aggregated personal data or without having to process personal data at all."
    - para 76 elements: "Data avoidance - Avoid processing personal data altogether when this is possible…"; "Aggregation - Use aggregated data when possible."; "Data flow - The data flow should be made efficient enough to not create more copies than necessary."
    - This is generic and does not specifically mention on-device or edge processing.
  - **EDPB 01/2020 (connected vehicles)**, the explicit EDPB statement on local processing:
    - para 73: "vehicle and equipment manufacturers, service providers and other data controllers should, wherever possible, use processes that do not involve personal data or transferring personal data outside of the vehicle … This scenario offers the advantage of guaranteeing to the user the sole and full control of his/her personal data and, as such, it presents, 'by design', less privacy risks … It also enables the processing of sensitive data such as biometric data…"
    - para 78: "'hybrid processing' … to generate numerical scores that are transferred … In this way, the insurance company does not gain access to the raw behavioural data but only to the aggregate score that is the result of the processing. This ensures that principles of data minimization are satisfied by design."
  - **CNIL, "caméras augmentées" (July 2022)**, safeguards supporting proportionality: "le traitement local des données (dans des dispositifs physiquement accolés aux caméras), l'intégration de mécanismes permettant la suppression quasi immédiate des images sources ou la production d'informations anonymes (par exemple pour la réalisation d'opérations de comptage)."
  - **ICO biometric guidance (2024)**
    - "On-device verification is a technique that can reduce the amount of biometric data created and shared … no biometric data leaves it – only a token or proof of the verification."
    - It also says this "may also mean that you are less likely to have control over how the biometric data is processed … this may make it more difficult for you to identify security threats".
  - **EDPB Opinion 11/2024 (airport facial recognition)**, press summary of 24 May 2024:
    - "individuals should have maximum control over their own biometric data". Compatible options: data "stored in the hands of the individual or in a central database but with the encryption key solely in their hands".
- **Source:**
  - EDPB 4/2019 (above).
  - EDPB Guidelines 01/2020, Version 2.0, adopted 9 March 2021: https://www.edpb.europa.eu/system/files/documents/2021-03/edpb_guidelines_202001_connected_vehicles_v2.0_adopted_en.pdf
  - CNIL position: https://www.cnil.fr/sites/cnil/files/atoms/files/cameras-intelligentes-augmentees_position_cnil.pdf
  - ICO: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/how-do-we-keep-biometric-data-secure/
  - EDPB: https://www.edpb.europa.eu/news/news/2024/facial-recognition-airports-individuals-should-have-maximum-control-over-biometric_en
- **Confidence:** High on the texts. Medium on transferring them to this platform, since each comes from a different sector.
- **Contrary authority checked:**
  - The ICO's transient-processing point (finding 9) and C-683/21 ruling 3 both confirm that short-lived or local processing is still "processing".
  - The ICO flags a security and control trade-off.
  - The EDPS TechDispatch on FER contains no on-device recommendation.
  - No regulator was found saying that in-browser feature extraction takes processing outside the GDPR when results are sent to a researcher. The WP29 2015 "domestic exception" applies only where "no personal data are transmitted outside the device", and fn 6 says it "does not exempt the data controller … for the processing for his own purposes."

### F. Research provisions

**19. Art 89(1), Art 17(3)(d), Art 5(1)(e) and Art 5(1)(b), verbatim (EU GDPR).**
- **Quote:**
  - **Art 89(1):** "Processing for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes, shall be subject to appropriate safeguards, in accordance with this Regulation, for the rights and freedoms of the data subject. Those safeguards shall ensure that technical and organisational measures are in place in particular in order to ensure respect for the principle of data minimisation. Those measures may include pseudonymisation provided that those purposes can be fulfilled in that manner. Where those purposes can be fulfilled by further processing which does not permit or no longer permits the identification of data subjects, those purposes shall be fulfilled in that manner."
  - **Art 17(3)(d):** "Paragraphs 1 and 2 shall not apply to the extent that processing is necessary: … (d) for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes in accordance with Article 89(1) in so far as the right referred to in paragraph 1 is likely to render impossible or seriously impair the achievement of the objectives of that processing".
  - **Art 5(1)(e):** "kept in a form which permits identification of data subjects for no longer than is necessary for the purposes for which the personal data are processed; personal data may be stored for longer periods insofar as the personal data will be processed solely for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes in accordance with Article 89(1) subject to implementation of the appropriate technical and organisational measures required by this Regulation in order to safeguard the rights and freedoms of the data subject ('storage limitation')".
  - **Art 5(1)(b)** (research is compatible further processing): "further processing for … scientific or historical research purposes or statistical purposes shall, in accordance with Article 89(1), not be considered to be incompatible with the initial purposes".
  - **Art 17(1)(b):** erasure applies where "the data subject withdraws consent on which the processing is based according to point (a) of Article 6(1), or point (a) of Article 9(2), and where there is no other legal ground for the processing".
  - **Recital 159:** research "should be interpreted in a broad manner including for example technological development and demonstration, fundamental research, applied research and privately funded research."
- **Source:** GDPR (CELEX 32016R0679, OJ version; a 2018 corrigendum exists but was not checked for these articles).
- **Confidence:** High.
- **Contrary authority checked:**
  - Art 89(2) derogations (from Arts 15, 16, 18 and 21) need Union or Member State law. They do not cover Art 17, which has its own 17(3)(d).
  - The Digital Omnibus proposal would add a definition of "scientific research" and make research further processing "compatible … independent of the conditions of Article 6(4)". Not adopted (finding 21).

**20. UK: DUAA 2025 changes to research and special categories, now in force.**
- **Quote:**
  - **New Art 4(2) (DUAA s.67):** "References in this Regulation to the processing of personal data for the purposes of scientific research … are references to processing for the purposes of any research that can reasonably be described as scientific, whether publicly or privately funded and whether carried out as a commercial or non-commercial activity." In force 5.2.2026 (S.I. 2026/82).
  - **New Art 4(6) (DUAA s.68, broad consent):** consent "given to the processing of personal data for the purposes of an area of scientific research" is treated as valid where "at the time the consent is sought, it is not possible to identify fully the purposes", it is "consistent with generally recognised ethical standards", and "the data subject is given the opportunity to consent only to processing for part of the research". In force 5.2.2026.
  - **New Chapter 8A (DUAA s.86)**, which replaces Art 89:
    - Art 84B(1): "Personal data may only be processed for RAS purposes if— (a) the processing consists of the collection of the personal data …, (b) the processing is carried out in order to convert the personal data into information which can be processed in a manner which does not permit the identification of a data subject, or (c) without the processing, the RAS purposes cannot be fulfilled."
    - Art 84C(2): "The requirement is not satisfied if the processing is likely to cause substantial damage or substantial distress to a data subject".
    - Art 84C(3): "…not satisfied if the processing is carried out for the purposes of measures or decisions with respect to a particular data subject …, except where the purposes … include the purposes of approved medical research".
    - Art 84C(4): "The requirement is only satisfied if the safeguards include technical and organisational measures for the purpose of ensuring respect for the principle of data minimisation …, such as, for example, pseudonymisation."
    - "(4) Omit Article 89". In force 5.2.2026.
  - **Consequential amendments:** UK Art 5(1)(e) and Art 17(3)(d) now read "in accordance with Article 84B". UK Art 5(1)(e) no longer contains the EU phrase "subject to implementation of the appropriate technical and organisational measures…". UK Art 9(2)(j) now requires that research processing "is carried out in accordance with Article 84B".
  - **New Art 11A (DUAA s.74):** "The Secretary of State may by regulations— (a) make provision so that an additional description of processing of personal data is subject to the prohibition in Article 9(1)…". In force 20.8.2025 (S.I. 2025/904).
  - UK Art 30(5) is unchanged.
  - UK Art 25 gains 1A/1B ("children's higher protection matters" for information society services likely to be accessed by children).
- **Source:** Data (Use and Access) Act 2025 (c. 18), ss. 67, 68, 74, 86, 87: https://www.legislation.gov.uk/ukpga/2025/18/section/67 (and /68, /74, /86). UK GDPR as amended: https://www.legislation.gov.uk/eur/2016/679/article/5 , /article/9 , /article/17 , /article/25 , /article/30.
- **Confidence:** High.
- **Contrary authority checked:**
  - No regulations under Art 11A adding biometric or emotion data as a new special category were found. The search was not exhaustive (see Not verified).
  - ICO guidance pages are flagged "under review" because of the DUAA, so ICO positions may change.

**21. EU Digital Omnibus proposal COM(2025) 837 (19 Nov 2025): proposed GDPR changes relevant here. Not adopted.**
- **Quote (proposed text):**
  - New Art 9(2)(k): "processing in the context of the development and operation of an AI system as defined in Article 3, point (1), of Regulation (EU) 2024/1689 or an AI model, subject to the conditions referred to in paragraph 5."
  - New Art 9(2)(l): "processing of biometric data is necessary for the purpose of confirming the identity of a data subject (verification), where the biometric data or the means needed for the verification is under the sole control of the data subject."
  - Art 35(4): "The Board shall prepare and transmit to the Commission a proposal for a list of the kind of processing operations which are subject to the requirement for a data protection impact assessment". Lists would be adopted "by way of an implementing act".
  - New definition: "'scientific research' means any research which can also support innovation, such as technological development and demonstration. … This does not exclude that the research may also aim to further a commercial interest."
- **Source:** COM(2025) 837 final, Publications Office cellar ebf17714-c56e-11f0-8da2-01aa75ed71a1 (DOC_1). Status: European Parliament Legislative Train, "The Digital Omnibus Regulation Proposal", status "Tabled", with a note that a COREPER mandate vote was cancelled (https://www.europarl.europa.eu/legislative-train/theme-a-new-plan-for-europe-s-sustainable-prosperity-and-competitiveness/file-digital-package, page state as of 1 Aug 2026 per fetch).
- **Confidence:** High on the proposal text. Medium on status (the legislative train can lag).
- **Contrary authority checked:** The official text contains no amendment to Art 9(1) limiting it to "directly" revealing data. Latham & Watkins (27 Nov 2025) likewise describes only the (k)/(l) additions. The separate "AI Omnibus" was adopted in June 2026 per secondary sources; that is outside GDPR and was not verified.

### Not verified

- **Omnibus IV (COM(2025) 501) adoption.** Whether the Art 30(5) change (750 employees / high risk) has been adopted or is in force. The Council agreed its position on 24/26 Sept 2025, but no OJ publication was found. Treat the current Art 30(5) as law.
- **Digital Omnibus after August 2026.** Whether the Council or Parliament positions reintroduce any narrowing of Art 9(1), or change Art 35 lists, after the August 2026 legislative-train update.
- **AG Szpunar's opinion in C-21/23 (25 April 2024).** Read only through secondary sources. The opinion text (CELEX 62023CC0021) was not read directly.
- **UK weight of post-2020 CJEU judgments.** The effect in UK courts of judgments after 31 Dec 2020 (C-252/21, C-21/23, C-683/21), under the European Union (Withdrawal) Act 2018 as amended, was not checked in this session.
- **Respiration or breathing data.** No EDPB, DPA or court authority was found that specifically classifies respiration waveforms or breathing rate, or voice-derived arousal, as health data. The analysis rests on C-21/23, WP29 2015 and EDPB 03/2020 by analogy.
- **Status of the WP29 2015 health-data annex.** Not checked against the EDPB list of endorsed WP29 documents.
- **Open-source developer who never receives data.** No authority was found stating expressly that such a developer is neither controller nor processor. A search snippet claimed an ICO example where a company is "not a processor" "for the software provision". That text was not found on the current ICO controller/processor pages.
- **ICO second-phase biometric guidance (biometric classification / emotion).** Not found as published.
- **Art 11A regulations.** No UK regulations under Art 11A adding new special categories were found, but the search was not systematic.
- **National list scopes and revisions.** Whether the DSK Muss-Liste applies only to the non-public sector (secondary sources say so). Whether the Irish DPC or CNIL lists have been revised since 2018/2019.
- **EDPB DPIA template.** Whether the final version (post-consultation, after 9 June 2026) has been adopted.
- **GDPR corrigendum.** The 2018 GDPR corrigendum was not checked for effects on the articles quoted.

### Refuted leads

- **"The Digital Omnibus narrows Art 9 to data that 'directly' reveal special categories."** This is in the leaked pre-19-Nov-2025 draft only. The official COM(2025) 837 text amends Art 9 only by adding (2)(k), (2)(l) and para 5. Some vendor blogs still state the narrowing as if it were in the proposal.
- **"C-413/23 P (4 Sept 2025) is an Art 9 inferred-data ruling."** A search summary said so. The judgment is EDPS v SRB under Regulation 2018/1725 (information duty and pseudonymised data). It contains no Art 9 discussion. The summary had merged it with C-184/20.
- **"EDPS TechDispatch on FER recommends on-device processing."** It does not. It also states it is "not … a policy position of the EDPS".
- **"EDPB Guidelines 4/2019 recommend edge or on-device processing."** They do not say so explicitly. They set out general minimisation elements (data avoidance, aggregation, data flow). The explicit EDPB local-processing recommendation is in Guidelines 01/2020 (connected vehicles).
- **"EDPB/EDPS called for a blanket ban on emotion recognition."** The Joint Opinion 5/2021 summary reads that way, but para 35 excepts "health or research purposes … with appropriate safeguards".
- **"Under ICO guidance, facial data not used for identification is not biometric data."** The ICO says biometric-data status turns on "qualities of the information itself, not how you use it". Only *special category* biometric status depends on an identification purpose.
- **The ICO 2022 emotion-analysis release on ico.org.uk.** The original URL now returns 404. The text was confirmed from an official-release mirror.

### What this means for the platform

*Analysis, not law. These points apply the findings above and have not been reviewed by counsel.*

- **DPIA: presumptively required for each deploying research group.**
  - WP248 criteria met: 4 (face video and voice are "highly personal"; affect and physiology may be Art 9) and 8 (innovative technology). Criterion 1 (scoring affect or behaviour) is plausibly met, and criterion 7 is met when participants are students of the researcher, patients or children. That makes at least two criteria.
  - The ICO list names "neuro-measurement (e.g. emotional response analysis)" as innovative technology, and the DSK item 13 fits closely.
  - Suggested action: ship a pre-filled DPIA skeleton (the EDPB 2026 template structure) with the tool.
- **Treat derived physiological and affect streams as special-category data by default in the EU.**
  - A single short respiration trace probably is not health data on the WP29 "single reading" logic.
  - However, C-21/23 ("capable of revealing … by … deduction", probability suffices) and C-252/21/C-21/23 (the controller's aim is irrelevant) make it risky to rely on that. The risk is highest for longitudinal sessions, clinical samples, or data linked with questionnaires.
  - Suggested default: an Art 9 condition (explicit consent, or 9(2)(j) where national law provides it), with this documented in the DPIA.
  - The UK ICO's intent-based test is more lenient but does not protect EU participants.
- **Facial action units and gaze used without identification are not special-category biometric data** (ICO explicit; EU per EDPB 3/2019, already established). They remain personal data, and in the ICO's view may still be "biometric data" (non-special). Never add face matching or re-identification features, because that would flip the classification.
- **Controller allocation.**
  - Each research group that runs a study is a controller for it (Art 4(7)).
  - Groups running a shared study on one instance are likely joint controllers and need an Art 26 arrangement (EDPB research-institutes example).
  - An institution hosting an instance for other groups, with no purposes of its own, is a processor and needs an Art 28 contract.
  - The code author who publishes software and receives no data has no identified GDPR role. That changes if the author hosts a demo, collects telemetry or crash reports, or tests with real recordings of other people (C-683/21 ruling 3).
- **Art 30 records are needed regardless of headcount**, because Art 9 data and non-occasional processing defeat 30(5). The Omnibus IV relaxation is only a proposal. Suggested action: provide an exportable per-study record-of-processing (RoPA) stub.
- **Architecture defaults (supported by analogy, not by a rule).** The analogies are EDPB 01/2020, the CNIL 2022 smart-cameras position, ICO on-device guidance and EDPB Opinion 11/2024.
  - Run feature extraction in the browser.
  - Upload only derived features or aggregates by default.
  - Keep raw video local unless the participant opts into the retention tier.
  - Keep transcripts consent-gated.
  - Store identifiers separately from data (pseudonymisation, Art 89(1) / UK Art 84C(4)).
  - Do not claim that in-browser processing takes anything outside the GDPR (ICO on transient processing; WP29 fn 6).
- **Research exemptions are narrow.**
  - Art 17(3)(d) applies only where erasure would "render impossible or seriously impair" the research.
  - Where the legal basis is consent, withdrawal triggers Art 17(1)(b).
  - Suggested action: build a per-participant delete path covering raw video and derived features.
  - In the UK, Art 84C bars research processing used for measures or decisions about the individual, and processing likely to cause substantial damage or distress. No per-participant feedback of "emotion scores" should be used for decisions.
- **Watch-list.** Monitor these rather than design around them yet: the Digital Omnibus (new Art 9(2)(k), EU-wide DPIA lists), Omnibus IV (Art 30), ICO guidance revisions after the DUAA, and any UK Art 11A regulations.


---

Checked 2026-09-26. This is research backing, not legal advice. Every quote below was read in the primary source or an archived copy of it. Where I only saw a secondary copy, the entry says so. Raw downloads are in `raw/` next to this file.

## Research ethics, de-identification and retention

### A. Face video, derived facial features and gaze

**1. Blurring and pixelation do not reliably de-identify faces against a trained recogniser**
- **Claim:** In one study, simple neural networks trained on obfuscated images identified pixelated, YouTube-blurred and P3-encrypted faces far above chance. The authors, looking at the same blurred faces, could not identify them.
- **Quote:** "On the AT&T [2] dataset of black-and-white faces from 40 individuals, we achieve accuracy of 57% against blurring, 97% against P3 with threshold 20, and over 95% against all examined forms of mosaicing, vs. 2.5% for random guessing. On the FaceScrub [32] dataset of photos of over 530 celebrities, we achieve accuracy of 57% against mosaicing with 16 × 16 windows and 40% against P3 with threshold 20, vs. 0.19% for random guessing." The authors also wrote: "Anecdotally, the authors of this paper were at a complete loss when trying to identify the blurred faces by sight. Our simple neural network, however, was able to recognize individuals with 57.75% accuracy (Table 3)." Top-5 accuracy on blurred faces was 85.75% (Table 3). Their conclusion: "obfuscating an image so as to make it unrecognizable by a human may no longer be sufficient for privacy."
- **Source:** McPherson, Shokri, Shmatikov, "Defeating Image Obfuscation with Deep Learning", arXiv:1609.00408 (v1 2016-09-01, v2 2016-09-06). https://arxiv.org/abs/1609.00408
- **Confidence:** High for the numbers as reported.
- **Contrary evidence checked:** The attack is closed-set. The attacker trains on obfuscated images of the same people it later identifies: 40 or 530 known identities. It does not show open-set identification against the general population. The study is from 2016 and small. It supports "not reliable against a motivated attacker who has reference images". It does not support "anyone can re-identify a blurred face". An independent study, Oh, Benenson, Fritz, Schiele, "Faceless Person Recognition", ECCV 2016 (arXiv:1607.08438), points the same way: "a handful of images is enough to threaten users' privacy, even in the presence of obfuscation". I found no peer-reviewed study showing that blur or pixelation of the whole face is robust against a trained recogniser.

**2. Abstract facial-motion streams (blendshapes) re-identify people**
- **Claim:** Avatar-animation facial-motion data identifies individuals. The data is headset blendshape coefficients, which are conceptually close to AU or blendshape time series, not video. Identification is very high within a session and much lower but above chance across sessions and devices.
- **Quote (abstract):** "The data used is not raw video, but rather, abstract representations that are used to animate digital avatars. Our analysis shows that individuals can be re-identified from this data with up to 98% balanced accuracy, are even identifiable across device types, and that emotional states can be inferred with up to 86% accuracy." Body text: "The best result is 43% balanced accuracy for the face data of the Meta when using the EYKT model. We conclude that the identification across sessions is possible, but most of the learned features from E1 identify the specific session and are not general for the individual." Cross-headset: "The best accuracy for facial motion data is achieved by EYKT with 63%" (chance 0.02 in that table).
- **Source:** Castro, Hanisch, Fallahi, Strufe, "FacialMotionID: Identifying Users of Mixed Reality Headsets using Abstract Facial Motion Representations", arXiv:2507.11138 (2025-07-15). https://arxiv.org/abs/2507.11138. This is a preprint. I found no journal reference.
- **Confidence:** Medium. The numbers are verbatim, but the paper is not peer-reviewed and the population is 116 participants. The 98% figure is a random split within a session, which overstates real-world linkability. The 43% cross-session figure is the more relevant one.
- **Contrary evidence checked:** The data comes from VR headsets, whose sensors see the lower and upper face at close range. Webcam AU estimates (for example from py-feat, OpenFace or MediaPipe blendshapes) are noisier. I found no study measuring re-identification from webcam AU time series specifically. That gap is listed under Not verified. An older, smaller study agrees in direction: Kashyap, Tulyakov, Govindaraju, "Facial Behavior as a Soft Biometric", ICB 2012. They used manual FACS coding of 20 interviewees and got "exact matches were found to be 50%, 50% and 55% respectively among 20 individuals. The baseline is 5%". https://www.acsu.buffalo.edu/~tulyakov/papers/Kashyap_ICB2012_FacialBehavior.pdf

**3. Motion-derived behavioural streams in general can be uniquely identifying at scale**
- **Claim:** Head and hand motion identified 1 user among more than 50,000 VR users. This is included because the platform may derive head pose.
- **Quote:** From the paper's abstract, confirmed in search results and the USENIX listing: "a user can be uniquely identified amongst the entire pool of 50,000+ with 94.33% accuracy from 100 seconds of motion data" (N=55,541, trained on 5 minutes per person).
- **Source:** Nair et al., "Unique Identification of 50,000+ Virtual Reality Users from Head & Hand Motion Data", USENIX Security 2023. https://www.usenix.org/conference/usenixsecurity23/presentation/nair-identification
- **Confidence:** Medium. I read this quote via the search index and the USENIX page listing, not the PDF body.
- **Contrary evidence checked:** The data is VR head and hand motion relative to game objects, not webcam head pose. It is only weakly transferable to this platform.

**4. Eye movements are a recognised behavioural biometric**
- **Claim, part 1:** Eye-tracking data can reveal biometric identity and many sensitive attributes.
- **Quote:** "Our analysis of the literature shows that eye tracking data may implicitly contain information about a user's biometric identity, gender, age, ethnicity, body weight, personality traits, drug consumption habits, emotional state, skills and abilities, fears, interests, and sexual preferences."
- **Source:** Kröger, Lutz, Müller, "What Does Your Gaze Reveal About You? On the Privacy Implications of Eye Tracking", in Privacy and Identity Management (IFIP AICT 576), Springer 2020, open access CC-BY. DOI 10.1007/978-3-030-42504-3_15. I read the abstract via the Semantic Scholar API; Springer and the IFIP library blocked direct fetch.
- **Claim, part 2 (numbers):** With research-grade 1000 Hz data, 5 s of reading gives 3.66% equal error rate (EER) for authentication. Performance degrades sharply as the sampling rate falls.
- **Quote:** "…achieves state-of-the-art EMB performance in the authentication scenario on high-quality data, namely 3.66% EER when enrolling and authenticating with just 5 s of eye movements during a reading task." Also: "Authentication accuracy remains relatively stable as the sampling rate is degraded from 1000 Hz down to 250 Hz, starts to noticeably worsen at 125 Hz, and then drops significantly starting at 50 Hz." Table, 5 s inputs: 125 Hz 8.77%, 50 Hz 15.52%, 31.25 Hz 23.37% EER. And: "we are able to achieve around 5.09% EER with 60 s of 31.25 Hz data".
- **Source:** Lohr and Komogortsev, "Eye Know You Too", arXiv:2201.02110v2 (2022-03-28); published version in IEEE TIFS 2022. https://arxiv.org/abs/2201.02110
- **Confidence:** High for the numbers. Low for how far they transfer to webcam gaze.
- **Contrary evidence checked:** The authors themselves caution: "simply degrading the sampling rate of high-quality data is not a sufficient proxy for other eye-tracking devices". The data comes from an EyeLink 1000, with 322 participants, and measures authentication (verification against an enrolled template), not open-set identification. The authors also say "behavioral biometric traits are generally not distinctive enough for large-scale identification". Webcam gaze (for example WebGazer) has much worse spatial accuracy and irregular ~30 Hz sampling. I found no study measuring re-identification from browser-webcam gaze (see Not verified).

### B. Voice

**5. Voice anonymisation is hard. Even the best challenge systems are only partially anonymised against informed attackers.**
- **Claim, VoicePrivacy 2020:** Best EERs under a semi-informed attacker were 16–26%. 50% means chance-level privacy.
- **Quote:** "Anonymization is also achieved only partially and always at the cost of utility… While for the ignorant attack model, many systems achieve EERs above 50%, the best results are in the range of 33 - 43% for the lazy-informed attack model, and in the range of 16 - 26% for the semi-informed attack model."
- **Source:** Tomashenko et al., "The VoicePrivacy 2020 Challenge: Results and findings", Computer Speech & Language 74 (2022) 101362; arXiv:2109.00648v4 (2022-09-26). https://arxiv.org/abs/2109.00648
- **Claim, VoicePrivacy 2024:** Unprotected speech gives 4.6% EER, which means speakers are easily linkable. Top systems reached about 40–49.5% EER against the baseline attacker. Stronger attackers later cut the "best" systems to at most 20% EER.
- **Quote:** "The EER for original, unprotected test data is 4.6%." "…only 6 submitted systems … meet the criteria for the fourth strongest category (EER > 40%). However, two of these (T10-2 and T12-5) are non-compliant with the challenge rules." "…privacy evaluation is vulnerable to overestimation: four top-performing systems that initially achieved an EER ≥ 40% were later shown to be vulnerable to attacks that reduced EERs to less that [sic] 20%." Also: "The original ASV system on unprotected data exhibits substantial male bias (EER=8.8% for female speakers and EER=0.4% for male speakers)".
- **Source:** Tomashenko et al., "The Third VoicePrivacy Challenge: Preserving Emotional Expressiveness and Linguistic Content in Voice Anonymization", arXiv:2601.11846v1 (2026-01-17). https://arxiv.org/abs/2601.11846. ScienceDirect lists a Computer Speech & Language version (S0885230826000513); I did not open it.
- **Confidence:** High.
- **Contrary evidence checked:** Cascaded ASR→TTS (speech recognition, then speech synthesis) reaches EER 49.5% (T8-1), close to chance. So voice can be anonymised well, but only by destroying paralinguistic content (emotion UAR, unweighted average recall, 30.6%). This matters for a platform that wants voice affect features.

**6. Whether eGeMAPS functionals alone enable speaker re-identification: partially evidenced only**
- **Claim:** The only direct evidence I found is an EPFL MSc thesis, not peer-reviewed. It benchmarked openSMILE eGeMAPS (88-dim) and ComParE features on 1,251-speaker VoxCeleb1 identification. The features performed "significantly higher than chance" but far below self-supervised embeddings. The thesis reports only a figure line averaged across both openSMILE sets, not an eGeMAPS-specific number.
- **Quote:** "Almost all models outperform low-level acoustic features (openSMILE features, spectrograms, and cochleagrams) in speaker identification accuracy. These data-driven features show significantly higher performance than chance-level." And, about HuBERT: "…outperforming openSMILE acoustic features with more than 40%." Table 5.1 lists "openSMILE/eGeMAPS … 88".
- **Source:** G. Elbanna, "Evaluating Speaker Identity Coding in Self-supervised Models and Humans", EPFL MSc thesis 2023, arXiv:2406.10401. https://arxiv.org/abs/2406.10401
- **Confidence:** Low. The work is not peer-reviewed, the number is not isolated, and the passage is ambiguous. It is not clear whether "significantly higher than chance" refers to the self-supervised models or the openSMILE features.
- **Contrary evidence checked:** I searched for peer-reviewed eGeMAPS speaker-verification EERs and found none. Separately, eGeMAPS by design contains F0 and formant (F1–F3) statistics, which are classic speaker-dependent parameters. That is my inference, not a verified re-identification result.

### C. Respiration

**7. Long-duration nasal airflow patterns identify individuals**
- **Claim:** 24-hour nasal airflow recordings identified members of a 97-person cohort with 96.8% accuracy. The patterns were stable at retest.
- **Quote:** "We found that we could identify members of a 97-participant cohort at a remarkable 96.8% accuracy from nasal airflow patterns alone. … individual identification by nasal airflow fingerprints was on par with or better than voice recognition."
- **Source:** Soroka et al., "Humans have nasal respiratory fingerprints", Current Biology, 2025-06-12, doi:10.1016/j.cub.2025.05.008. I read the abstract via the Europe PMC API.
- **Confidence:** High for the abstract. Low for transfer to this platform.
- **Contrary evidence checked:** The study used a dedicated wearable that logs each nostril separately for up to 24 hours. A few minutes of camera- or microphone-derived breathing waveform is a very different signal. I found no study testing re-identification from short camera-derived respiration (see Not verified). The claim that 24-hour breathing data identifies people is supported. The claim that this platform's breathing waveform re-identifies people is not.

### D. US regulatory text and guidance

**8. HIPAA Safe Harbor: the letters are (P) and (Q), not (Q) and (R)**
- **Quote (45 CFR 164.514(b)(2)(i), eCFR current text):** "(P) Biometric identifiers, including finger and voice prints; (Q) Full face photographic images and any comparable images; and (R) Any other unique identifying number, characteristic, or code, except as permitted by paragraph (c) of this section". Safe Harbor also requires "(ii) The covered entity does not have actual knowledge that the information could be used alone or in combination with other information to identify an individual who is a subject of the information." The alternative path, expert determination under (b)(1), requires an expert to determine "that the risk is very small that the information could be used, alone or in combination with other reasonably available information, by an anticipated recipient to identify an individual".
- **Source:** eCFR API, 45 CFR 164.514, fetched 2026-09-26. https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.514. The OCR de-identification guidance (2012-11-26, archived copy) paraphrases (Q) as "Full-face photographs and any comparable images". For (R) it says: "A characteristic may be anything that distinguishes an individual and allows for identification."
- **Confidence:** High.
- **Contrary evidence checked:** None needed, since this is regulatory text. Note that HIPAA applies only to covered entities and business associates. A research group adopting it voluntarily is choosing a benchmark, not meeting a legal obligation.

**9. Common Rule identifiability: "readily ascertained", and the mandated reexamination is overdue**
- **Quote (45 CFR 46.102(e)(5)):** "Identifiable private information is private information for which the identity of the subject is or may readily be ascertained by the investigator or associated with the information." Section 46.102(e)(7) requires agencies to reexamine this "within 1 year and regularly thereafter (at least every 4 years)" and to publish a list of "technologies or techniques that produce identifiable private information". SACHRP (the HHS advisory committee, not OHRP guidance), in recommendations approved 2022-10-19, says: "The Common Rule explicitly calls for reexamination of identifiability at 45 CFR 46.102(e)(7); such a reexamination is overdue. Information can be captured so that the identity of the human subjects cannot be 'readily ascertained,' but the ability to combine datasets makes it very difficult to abide by the implicit promise to research subjects that data collected in this way will not be associated with them as individuals in the future."
- **Source:** eCFR 45 CFR 46.102 (fetched 2026-09-26). SACHRP, "IRB Considerations on the Use of Artificial Intelligence in Human Subjects Research", archived hhs.gov copy.
- **Confidence:** High for the text. The status of the list is covered under Not verified.
- **Contrary evidence checked:** I searched for any OHRP or NIH guidance stating that audio or video recordings are per se identifiable. I found none. University IRB guidance treats them as identifiable. For example, Penn State IRB Guideline XI (released 2022-04-01): "AVP involves recording identifiable information about subjects which may or may not be of a sensitive nature." That is institutional practice, not federal guidance.

**10. OHRP 2010 withdrawal guidance: already-collected data may be kept. It is still posted.**
- **Quote:** "OHRP interprets the HHS regulations at 45 CFR part 46 as allowing investigators to retain and analyze already collected data relating to any subject who chooses to withdraw from a research study or whose participation is terminated by an investigator without regard to the subject's consent, provided such analysis falls within the scope of the analysis described in the IRB-approved protocol. This is the case even if that data includes identifiable private information about the subject." On destruction: "For research not subject to regulation and review by FDA, investigators, in consultation with the funding agency, certainly can choose to honor a research subject's request that the investigator destroy the subject's data or that the investigator exclude the subject's data from any analysis." On consent text, for research not under FDA or HIPAA: "the investigator should inform subjects whether the investigator intends to either: (1) retain and analyze already collected data relating to the subject up to the time of subject withdrawal; or (2) honor a research subject's request that the investigator destroy the subject's data or that the investigator exclude the subject's data from any analysis." Withdrawal also ends new collection, including "recording private behavior without interacting or intervening with the subject (e.g., recording mother-infant interactions in the home environment using video cameras…)".
- **Source:** OHRP, "Guidance on Withdrawal of Subjects from Research: Data Retention and Other Related Issues", dated September 21, 2010 (PDF, archived copy). The hhs.gov page is still live in a Wayback snapshot of 2026-09-12, with "Content last reviewed June 2, 2026". https://www.hhs.gov/ohrp/regulations-and-policy/guidance/guidance-on-withdrawal-of-subject/index.html. hhs.gov returned 403 to direct fetch.
- **Confidence:** High.
- **Contrary evidence checked:** The scope is "non-exempt human subjects research conducted or supported by HHS". The guidance cites pre-2018 section numbers (46.116(a)(8), 46.102(f)). It is permissive under the Common Rule only; GDPR, BIPA or IRB conditions can still require deletion. Under GDPR, Art 17(3)(d) removes the right to erasure only where it "is likely to render impossible or seriously impair the achievement of the objectives of that processing" for Art 89(1) research. That is a narrower bar than OHRP's.

### E. Retention

**11. BIPA 15(a) and GDPR 5(1)(e) conflict in structure. I found no published guidance proposing one reconciled schedule.**
- **Quote (BIPA 740 ILCS 14/15(a)):** "A private entity in possession of biometric identifiers or biometric information must develop a written policy, made available to the public, establishing a retention schedule and guidelines for permanently destroying biometric identifiers and biometric information when the initial purpose for collecting or obtaining such identifiers or information has been satisfied or within 3 years of the individual's last interaction with the private entity, whichever occurs first."
- **Quote (BIPA definitions):** "'Biometric identifier' means a retina or iris scan, fingerprint, voiceprint, or scan of hand or face geometry. Biometric identifiers do not include writing samples, written signatures, photographs, human biological samples used for valid scientific testing or screening…" and "A private entity does not include a State or local government agency."
- **Quote (GDPR Art 5(1)(e)):** "kept in a form which permits identification of data subjects for no longer than is necessary for the purposes for which the personal data are processed; personal data may be stored for longer periods insofar as the personal data will be processed solely for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes in accordance with Article 89(1) subject to implementation of the appropriate technical and organisational measures…"
- **Source:** BIPA text from ilga.gov via Wayback (2023 and 2024 captures; ilga.gov refused direct connection). GDPR text via gdpr-info.eu; the EUR-Lex fetch returned 202 with an empty body.
- **Finding:** GDPR has no fixed maximum and expressly allows longer storage for research. BIPA has a hard ceiling and no research exemption in its text; the only science carve-out covers "human biological samples". A combined schedule therefore has to take the shorter of the two. I searched law-firm, DPA and university sources for published guidance reconciling the two into one schedule and found **none**. The Norton Rose Fulbright post "BIPA and the record retention requirement" (2022-12-06) addresses only BIPA timing. Northwestern's BIPA policy (effective 2019-06-06) covers facility access, not research, and sets destruction "within six (6) months of when the initial purpose … has been satisfied".
- **Confidence:** High for the texts. Medium for "none exists", because a search can only establish absence weakly.
- **Contrary evidence checked:** Whether webcam-derived landmarks or AUs are a "scan of face geometry", and whether eGeMAPS is a "voiceprint", is unresolved in what I read (see Not verified). If they are not, BIPA may reach only retained raw media.

**12. University research-data retention minimums can exceed BIPA's 3-year cap**
- **Quote (Cornell Policy 4.21, last updated 2026-01-27):** "Research data is retained for a minimum of three years after the final project closeout." If the data appears in publications, "the data and images must be available for an additional six years." For WCM: "primary data and supporting images are available for the University for at least six years after publication." It also notes that the Office of Research Integrity "typically require[s] retention for six years after the close of a grant".
- **Quote (2 CFR 200.334, federal awards):** "The recipient and subrecipient must retain all Federal award records for three years from the date of submission of their final financial report."
- **Source:** https://policy.cornell.edu/policy-library/research-data-retention and the eCFR API for 2 CFR 200.334.
- **Confidence:** High.
- **Conflict analysis:** BIPA's clock runs from the participant's "last interaction", which for a one-session study is the recording date. University and federal clocks run from project closeout or publication, which is usually later. If the retained data are BIPA "biometric identifiers or information", a 3-year-plus-closeout or 6-years-after-publication minimum cannot be met for them. The way out is to classify the retained research record so that it excludes biometric identifiers, not to stretch the retention period.

### F. Emotion-recognition critiques

**13. Barrett et al. 2019**
- **Quote (published abstract):** "how people communicate anger, disgust, fear, happiness, sadness, and surprise varies substantially across cultures, situations, and even across people within a single situation. Furthermore, similar configurations of facial movements variably express instances of more than one emotion category." Conclusion text, from the author-accepted manuscript at eprints.gla.ac.uk/178385: "the facial configurations in question are not 'fingerprints' or diagnostic displays that reliability and specifically signal particular emotional states regardless of context, person and culture. It is not possible to confidently infer happiness from just a smile, anger from a scowl, or sadness from a frown, as numerous technology tries to do when applying what they mistakenly believe to be the scientific facts."
- **Source:** Barrett, Adolphs, Marsella, Martinez, Pollak, Psychological Science in the Public Interest 20(1):1–68, 2019-07, doi:10.1177/1529100619832930 (abstract via Europe PMC; manuscript via Glasgow eprints).
- **Confidence:** High for the abstract. Medium for the conclusion wording, because the published version may differ slightly from the manuscript.
- **Contrary evidence checked:** Cowen et al., Nature 2021 (doi:10.1038/s41586-020-3037-7) report "each kind of facial expression had distinct associations with a set of contexts that were 70% preserved across 12 world regions". This supports some cross-cultural regularity. It does not contradict Barrett's point that a single expression cannot be reliably read as a single emotion.

**14. AI Now 2019**
- **Quote:** "1. Regulators should ban the use of affect recognition in important decisions that impact people's lives and access to opportunities. Until then, AI companies should stop deploying it. Given the contested scientific foundations of affect recognition technology… it should not be allowed to play a role in important decisions about human lives, such as who is interviewed or hired for a job, the price of insurance, patient pain assessments, or student performance in school."
- **Source:** AI Now 2019 Report, p. 6. https://ainowinstitute.org/wp-content/uploads/2023/04/AI_Now_2019_Report.pdf
- **Confidence:** High.

**15. Regulator statements (none from a professional body found for 2023–2026)**
- **UK ICO, 2022-10-26 (regulator, not a professional body):** "Developments in the biometrics and emotion AI market are immature. They may not work yet, or indeed ever." Also: "we are yet to see any emotion AI technology develop in a way that satisfies data protection requirements". The ICO lists "gaze tracking … facial movements … heartbeats, facial expressions" as emotional-analysis inputs. Source: the ICO press release as mirrored by wired-gov.net; the ico.org.uk URL returned 404.
- **EU AI Act (Reg. 2024/1689):** Art 5(1)(f) prohibits AI systems "to infer emotions of a natural person in the areas of workplace and education institutions, except where the use of the AI system is intended to be put in place or into the market for medical or safety reasons". Art 2(6): "This Regulation does not apply to AI systems or AI models, including their output, specifically developed and put into service for the sole purpose of scientific research and development." Source: artificialintelligenceact.eu, a secondary host. The lead-in wording of 5(1)(f) returned by that site differed from my recollection of the Official Journal text, so only the quoted core is relied on. Confidence: medium.
- **Contrary evidence checked:** I searched for APA and BPS statements from 2023–2026 and found none on facial-expression emotion inference. See Not verified.

### Not verified
- **Re-identification from webcam-derived AU or blendshape time series or MediaPipe landmarks.** I found no study. The evidence is from VR headsets (item 2) and manual FACS (Kashyap). Shi, Samal and Marx (CVIU 2006), "How effective are landmarks and their geometry for face recognition?", exists, but I could not read its numbers.
- **Re-identification from browser-webcam gaze (for example WebGazer).** I found no study. The only numbers are from EyeLink data downsampled to 31.25 Hz, which the authors say is not a proxy.
- **An eGeMAPS-specific speaker-identification or EER number.** Only a thesis figure line averaged with ComParE is available.
- **Re-identification from short camera- or microphone-derived breathing waveforms.** I found no study. I also did not check whether Soroka et al. report accuracy for windows shorter than 24 hours, because the full text was paywalled.
- **VoicePrivacy 2022 results.** Not separately checked; the 2020 and 2024 results are above.
- **Whether HHS ever published the 46.102(e)(7)(ii) list of identifiability-generating technologies.** SACHRP said in 2022 the reexamination was "overdue". I found nothing later, but hhs.gov blocked direct access.
- **Whether BIPA covers derived face landmarks or AUs as a "scan of face geometry", or acoustic functionals as a "voiceprint".** Case law was not reviewed. The status of university BIPA defences was also not reviewed: the GLBA "financial institution" exemption is being litigated, and some public universities may be "State … agency".
- **The BPS "Ethics guidelines for the use of Artificial Intelligence in Psychological Research".** The draft is out for consultation, with a deadline of 2026-09-28. I could not read the draft or confirm whether it addresses emotion inference.
- **APA statement on emotion AI, 2023–2026.** None found.

### Refuted leads
- **"(Q) full face… (R) biometric identifiers, including finger and voice prints".** The lettering is wrong. Biometric identifiers are **(P)**, full-face images are **(Q)**, and **(R)** is "any other unique identifying number, characteristic, or code". Citations in consent or IRB text should use (P) and (Q).
- **"Kröger et al. 2020 shows gaze is re-identifying".** It is a literature review, not an experiment. It shows that gaze "may implicitly contain information about a user's biometric identity". The quantitative evidence comes from the eye-movement-biometrics papers (item 4).
- **"McPherson shows blurred faces are identifiable by anyone".** The result is closed-set: the attacker has training images of the same 40 or 530 people.

### What this means for the platform
*These bullets are analysis, not legal advice.*
- **Do not call the "derived features only" tier "de-identified" or "anonymous".** Per-frame AU or blendshape streams, gaze traces and voice features are behavioural-biometric-type data. Published work re-identifies people from close analogues: blendshapes 43% cross-session among 116 people, eye movements 3.66% EER, voice 4.6% EER on raw speech. There is no study clearing webcam-grade versions. "Reduced identifiability" or "no raw audio or video kept" is honest; "de-identified" is not.
- **This tier does not meet HIPAA Safe Harbor.** Voice-derived features plausibly fall under "(P) biometric identifiers … voice prints" or "(R) any other unique identifying … characteristic". Safe Harbor also fails if the group has "actual knowledge" that the data could identify someone, and item 2 arguably gives that knowledge. Any de-identification claim for a US health-context user would need expert determination, not a checklist.
- **Say what is removed, not what is impossible.** Good consent text: "Your video and audio recordings will be deleted within N days of processing. We keep measurements computed from them, such as facial-movement scores, where you looked, voice pitch and loudness, and breathing rate, linked to a study code, not your name." Avoid "cannot be used to identify you".
- **Aggregate features before retention if you want a stronger claim.** Per-session summary statistics carry less identity signal than full time series. The trade-off should be tested, for example by running a re-identification check on the platform's own pilot data, before anything stronger is claimed.
- **Pick a withdrawal policy and state it.** OHRP explicitly allows either retaining already-collected data or destroying it on request, but says consent should tell participants which one applies. Given GDPR and BIPA exposure, the simpler promise is "on request we delete your raw media and your derived features". Add "data already included in published aggregate analyses cannot be removed" if that is true.
- **Set retention at the shortest applicable limit and design around the conflict.** No published source reconciles BIPA and GDPR, so assume the shortest limit applies. Raw media (plausibly BIPA "face geometry" or "voiceprint" once processed) should be deleted on a short fixed schedule well inside 3 years. The long-lived research record that university or ORI rules may require (3 years after closeout, or 6 years after publication at Cornell) should be restricted to data the group is prepared to defend as non-biometric. That classification is unverified, so get counsel's view before relying on it.
- **Keep emotion labels out of the consent language and the outputs.** Report "facial action unit activity" and "vocal arousal proxies", not "emotions detected". Barrett et al. and the ICO both undercut confident emotion inference. The EU AI Act bans emotion inference in workplace and education settings, but Art 2(6) exempts systems built solely for scientific research. That exemption would not cover a platform later offered to employers or schools.
- **Tell participants that breathing and gaze are included.** Both are listed by the ICO as emotional-analysis inputs. Breathing has published identification results only for 24-hour wearable data, and gaze only for research-grade trackers, so the consent text should describe them as "measurements that could, in principle, help identify you" rather than as harmless.
