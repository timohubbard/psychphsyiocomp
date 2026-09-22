# Pass 4d: BIPA/CUBI Deep Dive (INCOMPLETE — hit session rate limit 3rd time, 38/90 agents, synthesis failed)

**IMPORTANT:** Most claims below are UNVERIFIED because the adversarial verification step was rate-limited, NOT because they were checked and found false (see errored vs refuted below — everything here is errored, nothing was actually refuted). Treat as raw leads pulled from named sources (FindLaw statutory text, JD Supra law-firm alerts, Wikipedia), not as verified findings. Cross-check before citing in the final report as fact.

**Research question:**

EXTREMELY NARROW SINGLE-TOPIC RESEARCH PASS, US biometric privacy statutes only, for a project building a webcam-based research platform capturing facial video, gaze, and voice from participants (not for identification purposes — for behavioral/emotion research). Prefer official statutory text (Illinois General Assembly ILGA site, Texas statutes site, Washington state legislature site) and named court opinions/law firm client alerts over blog commentary. Give exact section numbers, dollar figures, and dates.

TOPIC A — ILLINOIS BIPA (740 ILCS 14/1 et seq.), THE BIOMETRIC INFORMATION PRIVACY ACT. Section 10 (740 ILCS 14/10): quote or closely paraphrase the definitions of "biometric identifier" (does it include "scan of ... face geometry"?) and "biometric information." Does the statutory text or any Illinois court opinion address whether analyzing a face for EXPRESSION/EMOTION (not identity matching) counts as a "scan of face geometry"? Quote the statutory carve-outs excluding "photographs," "writing samples," "demographic data," and "physical descriptions" from biometric identifiers, and whether "voice recordings" used for non-identification purposes are excluded — the actual carve-out language and any case interpreting it.

TOPIC B — BIPA ENFORCEMENT MECHANICS. Section 15(a) (740 ILCS 14/15(a)): the written retention schedule and destruction guideline requirement, and its "no later than 3 years after last interaction" outer bound. Section 15(b): the informed written consent requirement before collection. Section 20: statutory damages of $1,000 per negligent violation and $5,000 per intentional/reckless violation, and that it creates a private right of action for "any person aggrieved." The Illinois Supreme Court's Cothron v. White Castle Systems, Inc. (2023 IL 128004, Feb 17, 2023) decision on whether each individual scan (not just the first) creates a separate claim/accrual. The August 2024 Illinois SB 2979 amendment to BIPA limiting recovery to a single instance of statutory damages per person regardless of number of scans/collections — its effective date and exact effect on the Cothron holding going forward.

TOPIC C — BIPA SETTLEMENT SIZING. Name 2-4 concrete BIPA settlements with their dollar amounts: Facebook/Meta ($650 million, In re Facebook Biometric Information Privacy Litigation, N.D. Cal. 2021), Clearview AI, BNSF Railway, Google (Google Photos BIPA settlement), TikTok, Six Flags, or any 2024-2026 settlement. Cite the case name and amount.

TOPIC D — TEXAS CUBI AND OTHER STATE LAW. Texas Capture or Use of Biometric Identifier Act (CUBI), Business & Commerce Code Section 503.001: its definition of biometric identifier, its consent requirement, its retention/destruction requirement, and that enforcement is EXCLUSIVELY by the Texas Attorney General with no private right of action (contrast this explicitly with BIPA). Any Texas AG enforcement action or settlement (e.g. against Google or Meta) with dollar figures. Also briefly: does Washington's My Health My Data Act's definition of "consumer health data" have any published legal commentary specifically addressing whether it could cover inferred emotional state, gaze/attention data, or camera-derived physiological signals (heart rate, respiration) as opposed to conventional health records?

---

## Confirmed (3-vote verified)

### 1. [3-0]

**Claim:** RCW 19.373.010 defines biometric data under the Washington My Health My Data Act as data that must both derive from physiological/biological/behavioral measurement AND be capable of identifying a consumer — not any facial, voice, or behavioral data collection.

**Quote:** "Data that is generated from the measurement or technological processing of an individual's physiological, biological, or behavioral characteristics and that identifies a consumer."

**Source:** https://app.leg.wa.gov/rcw/default.aspx?cite=19.373

### 2. [2-0]

**Claim:** BIPA defines 'biometric identifier' to include a scan of face geometry, alongside retina/iris scan, fingerprint, and voiceprint.

**Quote:** "a retina or iris scan, fingerprint, voiceprint, or scan of hand or face geometry"

**Source:** https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-10/

### 3. [2-0]

**Claim:** BIPA's definition of 'biometric identifier' statutorily excludes photographs, writing samples/signatures, demographic data, and physical descriptions (height, weight, hair/eye color).

**Quote:** "Writing samples and written signatures; Photographs; Demographic data; Physical descriptions (height, weight, hair color, eye color)"

**Source:** https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-10/

### 4. [3-0]

**Claim:** BIPA defines 'biometric information' as information based on a biometric identifier that is used to identify an individual, and this definition excludes information derived from the excluded categories (photographs, physical descriptions, etc.).

**Quote:** "any information, regardless of how it is captured, converted, stored, or shared, based on an individual's biometric identifier used to identify an individual"

**Source:** https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-10/

## Unverified (rate-limited during verification — raw leads only)

### 1. [unverified, rate-limited — not refuted, just untested]

**Claim:** The statute's enumerated examples of biometric data explicitly limit facial imagery and voice recordings to those from which an identifier template can be extracted, directly bearing on whether webcam facial video/voice capture used only for emotion/behavior research (not identification) would fall outside the biometric data definition.

**Source:** https://app.leg.wa.gov/rcw/default.aspx?cite=19.373

### 2. [unverified, rate-limited — not refuted, just untested]

**Claim:** The Seventh Circuit Court of Appeals held in Clay v. Union Pacific Railroad Co. (decided April 1, 2026) that Illinois's 2024 BIPA amendments apply retroactively to pending litigation, precluding plaintiffs from recovering per-scan statutory damages.

**Source:** https://www.jdsupra.com/legalnews/one-and-done-seventh-circuit-holds-bipa-8104003/

### 3. [unverified, rate-limited — not refuted, just untested]

**Claim:** Illinois amended Section 20 of BIPA, effective August 2, 2024, to classify multiple scans/collections using the same method as a single violation, overriding the per-scan accrual theory the Illinois Supreme Court had permitted in Cothron v. White Castle System, Inc. (2023).

**Source:** https://www.jdsupra.com/legalnews/one-and-done-seventh-circuit-holds-bipa-8104003/

### 4. [unverified, rate-limited — not refuted, just untested]

**Claim:** The amendment restricts a plaintiff to at most one statutory-damages recovery per person per collection method, regardless of how many times biometric data was scanned or collected via that method.

**Source:** https://www.jdsupra.com/legalnews/one-and-done-seventh-circuit-holds-bipa-8104003/

### 5. [unverified, rate-limited — not refuted, just untested]

**Claim:** The Seventh Circuit (in Clay v. Union Pacific Railroad Co., decided April 1, 2026) held that Illinois' 2024 amendment to BIPA (SB 2979) applies retroactively, changing the damages standard from per-scan liability to a single-violation standard.

**Source:** https://www.jdsupra.com/topics/biometric-information-privacy-act/

### 6. [unverified, rate-limited — not refuted, just untested]

**Claim:** BIPA Section 20 sets statutory damages of $1,000 per negligent violation and $5,000 per intentional or reckless violation.

**Source:** https://en.wikipedia.org/wiki/Illinois_Biometric_Information_Privacy_Act

### 7. [unverified, rate-limited — not refuted, just untested]

**Claim:** The Facebook/Meta BIPA class action settled for $650 million, approved in February 2021, in In re Facebook Biometric Information Privacy Litigation (N.D. Cal.).

**Source:** https://en.wikipedia.org/wiki/Illinois_Biometric_Information_Privacy_Act

### 8. [unverified, rate-limited — not refuted, just untested]

**Claim:** Consumer health data under RCW 19.373.010 is defined broadly to include biometric data and data derived from non-health information through algorithms or machine learning, which could arguably sweep in inferred emotional states or physiological signals (e.g., heart rate) derived from camera data if such inferences are linked to a consumer's health status.

**Source:** https://app.leg.wa.gov/rcw/default.aspx?cite=19.373

### 9. [unverified, rate-limited — not refuted, just untested]

**Claim:** The Act defines consent with a heightened, opt-in standard and expressly bars several common web-consent mechanisms from qualifying, relevant to contrasting MHMDA's consent bar with BIPA Section 15(b)'s written-consent requirement.

**Source:** https://app.leg.wa.gov/rcw/default.aspx?cite=19.373

### 10. [unverified, rate-limited — not refuted, just untested]

**Claim:** The statute also excludes biological materials used for scientific testing, medical imaging used for diagnosis/treatment, and organ/tissue donation materials from 'biometric identifier.'

**Source:** https://codes.findlaw.com/il/chapter-740-civil-liabilities/il-st-sect-740-14-10/

### 11. [unverified, rate-limited — not refuted, just untested]

**Claim:** Before this retroactivity ruling, per-scan damages exposure could be enormous: one plaintiff's individual claim implicated potential recovery of about $7.5 million based on roughly 1,500 fingerprint scans, and aggregated putative class actions raised exposure exceeding billions of dollars.

**Source:** https://www.jdsupra.com/legalnews/one-and-done-seventh-circuit-holds-bipa-8104003/

### 12. [unverified, rate-limited — not refuted, just untested]

**Claim:** The Seventh Circuit reasoned the BIPA amendment is a remedial/procedural change affecting only available statutory damages (not substantive liability standards), which under Illinois law justifies applying it retroactively to pending cases.

**Source:** https://www.jdsupra.com/legalnews/one-and-done-seventh-circuit-holds-bipa-8104003/

### 13. [unverified, rate-limited — not refuted, just untested]

**Claim:** JD Supra's BIPA topic page includes law firm commentary specifically discussing the Clearview AI facial recognition litigation as a BIPA case study.

**Source:** https://www.jdsupra.com/topics/biometric-information-privacy-act/

### 14. [unverified, rate-limited — not refuted, just untested]

**Claim:** A court allowed biometric/voice privacy claims against Otter.ai (an AI note-taking service) to proceed, per an article dated 8/26/2026.

**Source:** https://www.jdsupra.com/topics/biometric-information-privacy-act/

### 15. [unverified, rate-limited — not refuted, just untested]

**Claim:** Six Flags reached a $36 million BIPA class-action settlement in 2021 over fingerprint collection at its theme parks.

**Source:** https://en.wikipedia.org/wiki/Illinois_Biometric_Information_Privacy_Act

### 16. [unverified, rate-limited — not refuted, just untested]

**Claim:** The first BIPA settlement was L.A. Tan Enterprises for $1.5 million on December 1, 2016, with individual class member payments of $125 to $150.

**Source:** https://en.wikipedia.org/wiki/Illinois_Biometric_Information_Privacy_Act

### 17. [unverified, rate-limited — not refuted, just untested]

**Claim:** BIPA requires covered entities to obtain consent before collecting or disclosing biometric identifiers, destroy the data in a timely manner, store it securely, and maintain a reasonable standard of care.

**Source:** https://en.wikipedia.org/wiki/Illinois_Biometric_Information_Privacy_Act

