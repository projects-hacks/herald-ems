# Santa Clara County EMS protocols for every call type: trauma, sepsis and STEMI pre-alert checklists

Research date: 2026-09-24. Scope: which current Santa Clara County EMS Agency documents Herald needs so it can work on every
call type (not only stroke), where to get them, and what the county itself says a Trauma Alert, a sepsis notification and a
STEMI Alert must contain. Every clinical statement below is quoted from a county document with its section and page, or is
marked **non-county** with its source. Nothing here is a treatment recommendation; drug and treatment text is quoted only
where it defines a fact the receiving team needs (for example "time of aspirin administration" as a documentation element).

Files: the PDFs are in `data/protocols/santa_clara/archive/` (current or reference) and `archive/previous/` (superseded),
with source URLs, capture URLs, page counts and sha256 in `data/protocols/santa_clara/archive/SOURCES.md`.

---

## 1. Summary

**Downloaded (2026-09-24, from Wayback Machine captures of the county's own URLs):** 27 files in `archive/` and 3
superseded versions in `archive/previous/`. All 30 open in `pdfinfo` as valid PDFs.

| Need | Current county document | Effective | In archive? |
|---|---|---|---|
| Trauma triage / Trauma Alert criteria | Policy 605 Prehospital Trauma Triage (inside AO 2025-005) | 2025-04-01 | yes (already there; PDF pages 25-27 clean copy) |
| Trauma center destination | Policy 602 911 EMS Patient Destination §VI.C and Table B (inside AO 2025-005) | 2025-04-01 (AO 2025-006 and AO 2025-007 amend it; not archived) | yes (already there) |
| Trauma treatment protocol | 700-A16 Trauma Care; 700-P16 Pediatric Trauma Care; 700-S06 Falls; 700-M17 Traumatic Hemorrhage Control; 700-M02 Pleural Decompression | 2026-01-01 (P16: 2025-01-01) | yes (new) |
| Sepsis (adult) and the county's sepsis notification criteria | 700-A04 Sepsis | 2026-01-01 | yes (new) |
| Shock | 700-A10 Shock; 700-P10 Pediatric Shock | 2026-01-01 | yes (new) |
| STEMI / chest pain / 12-lead transmission | 700-A08 Chest Pain - Suspected Cardiac Ischemia; 700-M09 12-Lead Electrocardiogram; Policy 430 STEMI Center Standards | 2025-01-01; 2024-01-01; 2025-02-15 | yes (new) |
| Cardiac arrest / ROSC | 700-A07 Cardiac Arrest | 2026-01-01 | **no** (only the superseded 2025-01-01 version, in `previous/`); 700-P07 Pediatric Cardiac Arrest 2026-01-01 **yes** |
| Respiratory distress | 700-A11 Respiratory Distress | 2026-01-01 | **no** (superseded 2025 version in `previous/`); 700-P11 Pediatric Respiratory Distress 2025-01-01 **yes** |
| Seizure | 700-A02 Seizure | 2026-01-01 | **no** (superseded 2025 version in `previous/`); 700-P02 Pediatric Seizure 2026-01-01 **yes** |
| Overdose / poisoning | 700-A15 Poisoning and Overdose; 700-P15 Pediatric Poisoning and Overdose | 2025-01-01 | yes (new) |
| Hypoglycemia (referenced by 700-A13 and 700-S04) | 700-A03 Hypoglycemia; 700-P03 Pediatric Hypoglycemia | 2025-01-01 | yes (new) |
| Pediatric general care | 700-S05 Routine Medical Care Pediatric; Policy 602 §VI.H; Policy 410 Pediatric Receiving Center Standards | 2026-01-01 | yes (new) |
| General assessment / documentation | 700-S04 Routine Medical Care Adult; Policy 501 Hospital Radio Reports; Policy 500 ePCR Documentation | 2026-01-01; 2025-01-01; 2020-01-01 | yes (500 new; 509 Elite ePCR guideline failed: the only capture is truncated) |
| Changes summaries | 2026 cycle memo (2025-09-19); 2025 cycle memo (2024-09-24) | 2026-01-01; 2025-01-01 | yes (2025 memo new) |

**Could not be downloaded** (no public archive holds them; exact URLs in §4): 700-A02, 700-A05, 700-A07, 700-A11, 700-P05,
700-S02, 700-S15 (all effective 2026-01-01), the 2025 "Summary of Policies Included in EMS Update", AO 2025-006 and AO
2025-007 (both amend Policy 602), and Policy 509.

**Key findings**

1. **The county has its own sepsis notification criteria.** 700-A04 §1.3-1.4 (effective 2026-01-01) defines four SIRS
   criteria (temperature below 96 °F or above 100.4 °F, heart rate above 90, respiratory rate above 20, EtCO2 below 25 mmHg)
   and calls for "Advanced notification to hospital of suspected sepsis patient if two or more SIRS criteria are met". So a
   national fallback is not needed for the criteria themselves. It is **not** a named "Sepsis Alert": Policy 501 lists only
   Trauma, Stroke and STEMI Alerts as specialty-center radio reports, so Herald should call it a "sepsis pre-notification".
2. **In Santa Clara a Yellow trauma criterion is still a Trauma Alert.** Policy 602 §VI.C defines Trauma Alert Patients as
   meeting the Red criteria "or Moderate Risk Mechanism of Injury or EMS Judgement (Yellow Criteria)", and all adult Trauma
   Alert Patients go to "the closest open Adult Trauma Center". This differs from the national 2021 guideline that Herald's
   `config/scores/field_triage.yaml` follows (Yellow there means "preferentially" a trauma center, need not be the highest
   level).
3. **Policy 501 §IV.E fixes what a Trauma Alert report must add:** the mechanism of injury and the anatomic and physiologic
   criteria from Policy 605.
4. **The STEMI checklist is mostly right but misses three county items:** the monitor reading "STEMI" or "Acute MI Suspected"
   (the alert trigger), transmission of the 12-lead to the selected STEMI center, and the time of aspirin administration
   (700-A08 §3.2, §1.4, §6.3). The existing "Anticoagulants" item is not in any county STEMI document.
5. **The vocabulary already covers most facts.** Keys added on 2026-09-24 (`vitals.gcs_total`, `vitals.etco2`,
   `vitals.pain`, `meds.given`, `procedures.done`, `trauma.mechanism`, `trauma.injuries`, `infection.suspected`,
   `patient.pregnancy_weeks`) cover trauma and sepsis. **NEW keys still needed:** `ecg.transmitted` and
   `ecg.stemi_reading` for STEMI, and a structured way to record which Policy 605 criteria are met (`trauma.criteria`,
   §10). Two more are optional: a time of injury and a patient-contact time.

---

## 2. How "current" was established, and how sure it is

**Access.** `ems.santaclaracounty.gov` and `files.santaclaracounty.gov` return HTTP 403 (a Cloudflare "Attention Required"
block page) to scripts, including requests with a normal browser User-Agent and Accept headers (tested 2026-09-24). A
fetch through a separate web-fetch service also returned 403. archive.today has no captures of the county file host.
Everything was therefore read from Wayback Machine captures of the county's own URLs, the same approach used for the
existing archive. The county serves the same files under two paths, `files.santaclaracounty.gov/exjcpb1541/<yyyy-mm>/...`
and `files.santaclaracounty.gov/<yyyy-mm>/...`; the second path is the one that holds 200 captures of the 2024-09 files.

**Evidence used to decide which version is in force:**

| Evidence | What it shows | Where |
|---|---|---|
| "EMS Update 2025" page, captured 2026-01-11 | The 26 documents revised with effect from 2026-01-01, with their links: 302, 410, 700-A02, A04, A05, A07, A10, A11, A13, A14, A16, A18, A20, M02, M17, P02, P05, P07, P10, S02, S04, S05, S06, S15, S16, S17 (+ S17 Schedule A), and the two change summaries | https://web.archive.org/web/20260111090359/https://ems.santaclaracounty.gov/ems-update-2025 |
| 2026 cycle change memo (2025-09-19), already in the archive | The treatment changes taking effect 2026-01-01 | `archive/2026-policy-protocol-changes-summary.pdf` |
| 2025 cycle change memo (2024-09-24) | The 2025-01-01 cycle: "All treatment protocols received three new sections" (Patient Care Goals, Pertinent Assessment Findings, Key Documentation Elements), and "No changes to treatment" for 700-A03, A07, A08, A10, A11, A13, A14, A15 | `archive/2025-policy-protocol-changes-summary.pdf` |
| "Administrative Order" news list, captured 2026-01-09 | AOs through AO 2025-009 (2025-11-25). None after AO 2025-005 changes Policy 605, 700-A04, 700-A08 or 700-A16 | https://web.archive.org/web/20260109023426/https://ems.santaclaracounty.gov/news/1061 |
| Policy manual list, latest capture 2025-09-10 | 184 documents, paginated; only the first page is archived | https://web.archive.org/web/20250910132457/https://ems.santaclaracounty.gov/services/find-ems-policies-protocols-and-plans |
| BLS/ALS protocol list, captured 2024-11-11 | Titles and numbers of every 700-series protocol | https://web.archive.org/web/20241111080021/https://ems.santaclaracounty.gov/services/find-ems-policies-protocols-and-plans/blsals-protocols |

**Rule applied:** a document revised in the 2026 cycle is current in its 2025-09 publication. A document not revised in the
2026 cycle is current in its most recent earlier publication (the 2024-09 publication, effective 2025-01-01, for all
treatment protocols; older for some procedures and policies). Each file's printed "Effective" and "Replaces" dates were
read and agree with this (for example 700-A04 "Effective: January 1, 2026 / Replaces: January 1, 2025").

**What is genuine and what is uncertain:**

- **Genuine:** the effective dates and the quoted text, read from the PDFs themselves.
- **Uncertain: anything after January 2026.** The newest captures are the AO list (2026-01-09), the EMS Update page
  (2026-01-11) and the site home page (2026-05-18; its news shows APOT/bypass reports, a meeting reschedule and an open
  comment period for a new Policy 621, with no clinical protocol change). A 2026 administrative order or a 2026 EMS Update
  (policies effective 2027-01-01; the 2025 training cycle opened on 24 September) could exist and would not be visible here.
  Check the live manual or the Eolas app before real use.
- **700-M09 (12-lead ECG)** was read from the pre-migration county site (`emsagency.sccgov.org`, capture 2024-02-24). The
  county's November 2024 protocol list links a file of the same name (`migrated/Policy_700-M09.pdf`), neither change memo
  lists M09, and the file says "Effective: January 1, 2024". It is very likely identical to the county's current file, but
  that was not verified byte for byte.
- **700-A08 (chest pain)** effective 2025-01-01 was read from a 2024-11-13 capture. An older copy effective 2024-01-01 also
  exists in the Wayback Machine (pre-migration site). It was not kept, because the 2025 version replaces it.
- **Policy 602 amendments:** AO 2025-006 (posted 2025-08-11) and AO 2025-007 (posted 2025-10-16) are both described as
  "Administrative Changes to Policy 602". Their text is not archived, so Table B (which hospital provides which service)
  may have changed after April 2025. Check them before relying on the destination lists in §5.2 and §7.1.

---

## 3. Document inventory by call type

Status: **C** = current (in force as of the 2026-01-01 cycle); **S** = superseded, kept for reference only (in `previous/`);
**M** = current but missing (download by hand, §4). "Capture" gives the Wayback timestamp; the full capture URL is in
`SOURCES.md`.

| Call type | No. | Title | Effective | St. | File in `archive/` | Pages | County URL (VersionId where the site uses one) | Capture |
|---|---|---|---|---|---|---|---|---|
| Trauma | 605 | Prehospital Trauma Triage (in AO 2025-005) | 2025-04-01 | C | AO-2025-005_policy-602-destination_eff-2025-04-01.pdf (PDF pp. 22-24 tracked changes, **pp. 25-27 clean**) | 27 | https://files.santaclaracounty.gov/exjcpb1541/2025-03/ao-2025-005.pdf?VersionId=hoI6kUYnjpaiCdXV5IMZfhAhGEPmUxmm | 20250714175706 |
| Trauma / all | 602 | 911 EMS Patient Destination (in AO 2025-005) | 2025-04-01 | C* | same file (PDF pp. 2-11 tracked changes, **pp. 12-21 clean**, Table B on p. 20) | 27 | as above | as above |
| Trauma | 700-A16 | Trauma Care | 2026-01-01 | C | 700-A16_trauma-care_eff-2026-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a16.pdf?VersionId=NC2vIyxvUeJRvv4bFB6IRF00J0wJpbvm | 20260111090419 |
| Trauma | 700-S06 | Falls | 2026-01-01 | C | 700-S06_falls_eff-2026-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s06.pdf?VersionId=cK3AlZTopYqtricNMihHZVoThj.pS5Of | 20260111090438 |
| Trauma | 700-M17 | Traumatic Hemorrhage Control | 2026-01-01 | C | 700-M17_traumatic-hemorrhage-control_eff-2026-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-m17.pdf?VersionId=2.eKtUUqCQZMFHXclfuPvmjv6CF6gcUC | 20260111090416 |
| Trauma | 700-M02 | Pleural Decompression | 2026-01-01 | C | 700-M02_pleural-decompression_eff-2026-01-01.pdf | 1 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-m02.pdf?VersionId=0NDOBfMDvWprxKwjwJsQwOBM2msICDkK | 20260111090429 |
| Trauma (peds) | 700-P16 | Pediatric Trauma Care | 2025-01-01 | C | 700-P16_pediatric-trauma-care_eff-2025-01-01.pdf | 2 | https://files.santaclaracounty.gov/2024-09/700-p16.pdf?VersionId=a_RulfueuVuz3vftlUWgeSfMUfXqekmZ | 20241113051653 |
| Trauma (hospital) | 420 | Trauma Center Standards | 2025-02-15 | C | 420_trauma-center-standards_eff-2025-02-15.pdf | 9 | https://files.santaclaracounty.gov/exjcpb1541/2025-02/policy-420.pdf?VersionId=mYRbHuA4WxXr4oPVLh5dlC500YvgeXuc | 20250811052656 |
| Sepsis | 700-A04 | Sepsis | 2026-01-01 | C | 700-A04_sepsis_eff-2026-01-01.pdf | 1 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a04.pdf?VersionId=llKIHwZNTKdIfmC1DHSq8pLdpZe1BOO. (capture of the same path without VersionId) | 20260111090446 |
| Sepsis / shock | 700-A10 | Shock | 2026-01-01 | C | 700-A10_shock_eff-2026-01-01.pdf | 1 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a10.pdf?VersionId=iOY4wLWFhhHadmcmR6HSNae_RqcSGX4z | 20260111090444 |
| Shock (peds) | 700-P10 | Pediatric Shock | 2026-01-01 | C | 700-P10_pediatric-shock_eff-2026-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-p10.pdf?VersionId=X50V.A_HU0AkQMdEqLUgUbAuQ3SUameR | 20260111090421 |
| STEMI | 700-A08 | Chest Pain - Suspected Cardiac Ischemia | 2025-01-01 | C | 700-A08_chest-pain-suspected-cardiac-ischemia_eff-2025-01-01.pdf | 3 | https://files.santaclaracounty.gov/2024-09/700-a08.pdf?VersionId=zn1ExoHOzov2.K0pZI0GkN3P512olGXb | 20241113062608 |
| STEMI | 700-M09 | 12-Lead Electrocardiogram | 2024-01-01 | C | 700-M09_12-lead-ecg_eff-2024-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/migrated/Policy_700-M09.pdf (VersionId not archived) | 20240224001437 (pre-migration site) |
| STEMI (hospital) | 430 | STEMI Center Standards | 2025-02-15 | C | 430_stemi-center-standards_eff-2025-02-15.pdf | 7 | https://files.santaclaracounty.gov/exjcpb1541/2025-02/policy-430.pdf?VersionId=Tssdc8ndRnCLjIxTPS35C2zm1pNYdESY | 20250811045438 |
| Cardiac arrest / ROSC | 700-A07 | Cardiac Arrest | 2026-01-01 | M | (superseded 2025-01-01 copy: previous/700-A07_cardiac-arrest_eff-2025-01-01.pdf, 7 pp.) | - | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a07.pdf?VersionId=boctz_KO0lzczqwJLLMwNQK8.q.MiyC8 | none |
| Cardiac arrest (peds) | 700-P07 | Pediatric Cardiac Arrest | 2026-01-01 | C | 700-P07_pediatric-cardiac-arrest_eff-2026-01-01.pdf | 6 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-p07.pdf?VersionId=0ii5ni64ZkKaQNIqMdRmMASI8pwP.u4A | 20260111090419 |
| Dysrhythmia | 700-A14 | Tachycardia with Pulses | 2026-01-01 | C | 700-A14_tachycardia-with-pulses_eff-2026-01-01.pdf | 3 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a14_0.pdf?VersionId=iKA.Epd8FMBZsck18yLY2Tbc78iWMoKB | 20260111090441 |
| Dysrhythmia | 700-A05 | Bradycardia | 2026-01-01 | M | - | - | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a05.pdf?VersionId=SVNL9xjz6ZUFnzX9nVDiQLQ93ufPOh7a | none |
| Respiratory | 700-A11 | Respiratory Distress | 2026-01-01 | M | (superseded copy: previous/700-A11_respiratory-distress_eff-2025-01-01.pdf, 3 pp.) | - | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a11.pdf?VersionId=TCPG1ja.Z6.fU_qafnGWCETcF9oZhG6c | none |
| Respiratory (peds) | 700-P11 | Pediatric Respiratory Distress | 2025-01-01 | C | 700-P11_pediatric-respiratory-distress_eff-2025-01-01.pdf | 2 | https://files.santaclaracounty.gov/2024-09/700-p11.pdf?VersionId=4AUm131FmMKvw8Ocbrw33qqe8Wo8huqS | 20241113045411 |
| Seizure | 700-A02 | Seizure | 2026-01-01 | M | (superseded copy: previous/700-A02_seizure_eff-2025-01-01.pdf, 2 pp.) | - | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a02.pdf?VersionId=6hjMgfVRCDkevZ0LmTxaQSNPdyS0iBeE | none |
| Seizure (peds) | 700-P02 | Pediatric Seizure | 2026-01-01 | C | 700-P02_pediatric-seizure_eff-2026-01-01.pdf | 2 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-p02.pdf?VersionId=j3BB7zpc1oO_5r69yFk4.CZS.rZIx1O1 | 20260111090414 |
| Overdose | 700-A15 | Poisoning and Overdose | 2025-01-01 | C | 700-A15_poisoning-and-overdose_eff-2025-01-01.pdf | 2 | https://files.santaclaracounty.gov/2024-09/700-a15.pdf?VersionId=a7vCGOfflLXv015K8VU0STtdnd6EpXUR | 20241113062859 |
| Overdose (peds) | 700-P15 | Pediatric Poisoning and Overdose | 2025-01-01 | C | 700-P15_pediatric-poisoning-and-overdose_eff-2025-01-01.pdf | 2 | https://files.santaclaracounty.gov/2024-09/700-p15.pdf?VersionId=h76oEjhI5BQWgvst3QTVrWTVgtGAj9cX | 20241113050033 |
| Hypoglycemia | 700-A03 | Hypoglycemia | 2025-01-01 | C | 700-A03_hypoglycemia_eff-2025-01-01.pdf | 1 | https://files.santaclaracounty.gov/2024-09/700-a03.pdf?VersionId=NBlYgy6jBss8RTSIshQn_EDJJlvlgI0d | 20250807014643 |
| Hypoglycemia (peds) | 700-P03 | Pediatric Hypoglycemia | 2025-01-01 | C | 700-P03_pediatric-hypoglycemia_eff-2025-01-01.pdf | 1 | https://files.santaclaracounty.gov/2024-09/700-p03.pdf?VersionId=b5WqrFcm8At8wI2Ed4QxJnveCd8WMpCa | 20241113043117 |
| OB | 700-A18 | Gynecological and Obstetrical Emergencies | 2026-01-01 | C | 700-A18_gynecological-obstetrical-emergencies_eff-2026-01-01.pdf | 4 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a18_0.pdf?VersionId=Lx3.Ijp.b0cVWxTwbk0lBMQN0JmBpx5I | 20260111204139 |
| Behavioral | 700-A20 | Behavioral Emergency - Combative | 2026-01-01 | C | 700-A20_behavioral-emergency-combative_eff-2026-01-01.pdf | 3 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a20.pdf?VersionId=7uMz4ZUp_PYpwHGSbDyZNi9r9jQH0icy | 20260111090413 |
| Pediatric general | 700-S05 | Routine Medical Care Pediatric | 2026-01-01 | C | 700-S05_routine-medical-care-pediatric_eff-2026-01-01.pdf | 3 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s05.pdf?VersionId=QnKyUhbYGzzQB1AuMMHyxOUjMhumdolF | 20260111090425 |
| Pediatric (hospital) | 410 | Pediatric Receiving Center Standards | 2026-01-01 | C | 410_pediatric-receiving-center-standards_eff-2026-01-01.pdf | 5 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/410.pdf?VersionId=nBdMBiXUder0ZaBjB1iO1xoMxdrPzNK0 | 20260111090451 |
| General assessment | 700-S04 | Routine Medical Care Adult | 2026-01-01 | C | 700-S04_routine-medical-care-adult_eff-2026-01-01.pdf (already there) | 3 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s04.pdf?VersionId=dffCKzVxvjEXaRO4jYZ6IA8vxnFL1tJp | 20260111090426 |
| Radio report | 501 | Hospital Radio Reports | 2025-01-01 | C | 501_hospital-radio-reports_eff-2025-01-01.pdf (already there) | 3 | https://files.santaclaracounty.gov/exjcpb1541/2024-09/policy-501.pdf?VersionId=lPXZcOawuog6grDdame1RLjgdP7cNQgl | (already there) |
| Documentation | 500 | Electronic Patient Care Record (ePCR) Documentation | 2020-01-01 | C | 500_epcr-documentation_eff-2020-01-01.pdf | 5 | https://files.santaclaracounty.gov/exjcpb1541/migrated/newPolicy500.pdf?VersionId=jqEsC15xks9SC.0TtpXyftuYJ.jurU.h | 20250114071108 |
| Documentation | 509 | Elite ePCR Documentation Guideline | unknown | M | - (the only capture stops at 1,048,576 bytes and does not open) | - | https://files.santaclaracounty.gov/exjcpb1541/migrated/Policy509.pdf?VersionId=4Gq8ALasH9FRskA8esTYFn4ToMHiGEqg | 20250114070206 (truncated) |
| Inventory | 302 | Prehospital Care Asset - Minimum Inventory Requirements | 2026-01-01 | C | 302_minimum-inventory_eff-2026-01-01.pdf | 13 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/302.pdf?VersionId=IhpHDZXgkzfPHeSOiosCjWfuVj4QBoHK | 20260111090442 |
| Changes summary | - | 2026 cycle: "Santa Clara County EMS Protocol/Policy Summary of Changes" (memo 2025-09-19) | 2026-01-01 | C | 2026-policy-protocol-changes-summary.pdf (already there) | 6 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/ems-policy-protocol-changes-summary.pdf?VersionId=h_JWuvxZE2dSayMfWxH_BFuNNzhgAR0D | 20260111090427 |
| Changes summary | - | 2025 cycle: "Santa Clara County EMS Protocol/Policy Revisions" (memo 2024-09-24) | 2025-01-01 | C (reference) | 2025-policy-protocol-changes-summary.pdf | 6 | https://files.santaclaracounty.gov/2024-09/changeoverview.pdf?VersionId=9qTm_.Z2KoP0dxoq.0pypFSDlTzG3eNr | 20250116050115 |
| Changes summary | - | Summary of Policies Included in EMS Update (2025 cycle) | 2026-01-01 | M | - | - | https://files.santaclaracounty.gov/exjcpb1541/2025-09/summary-of-policies-included-in-ems-update.pdf?VersionId=xfr0mO9WS7POvLxTJkl15V8wpo2_P_eI | none |
| Stroke (already there) | 700-A13 | Stroke | 2026-01-01 | C | 700-A13_stroke_eff-2026-01-01.pdf | 3 | current link: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a13.pdf?VersionId=j_y.Az3_zYbeNZ4OWTejiuWMEBmg3kSg (the archived copy was read from the same path without a VersionId) | 20260111090437 |

\* Policy 602 is amended by AO 2025-006 and AO 2025-007, which are not archived (§2).

**Found but not downloaded (current, low priority for pre-alerts):** 700-S16 and 700-S17 (911 EMS Nurse Navigation,
2026-01-01, captured) and Policies 422 and 432 (trauma and cardiac interfacility transfer, 2025-02-15, captured). Other
current 700-series protocols (A01 Abdominal, A06 Burns, A09 Environmental, A12 Allergic Reaction/Anaphylaxis, A19 Crush
Injury, P01, P06, P09, P12, P14, P18, the M-series procedures, S01, S09-S14) exist in their 2024-09 or older publications. They
can be added the same way when a call type needs them.

---

## 4. Documents that could not be downloaded (for the team lead)

No public archive holds these. Download each in a normal browser, save it into `data/protocols/santa_clara/archive/` with
the naming style `<number>_<short-title>_eff-YYYY-MM-DD.pdf`, and add a row with its sha256 to `SOURCES.md` (the same list is
there).

| Document | Why it matters | County URL |
|---|---|---|
| 700-A07 Cardiac Arrest (2026-01-01) | cardiac arrest and ROSC; the 2026 cycle changed traumatic-arrest rules and post-ROSC blood pressure support | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a07.pdf?VersionId=boctz_KO0lzczqwJLLMwNQK8.q.MiyC8 |
| 700-A11 Respiratory Distress (2026-01-01) | respiratory calls; the 2026 cycle added an SpO2 goal of 88-92% for COPD | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a11.pdf?VersionId=TCPG1ja.Z6.fU_qafnGWCETcF9oZhG6c |
| 700-A02 Seizure (2026-01-01) | seizure calls; referenced by 700-A13 §2.4 and 700-S06 §1.9 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a02.pdf?VersionId=6hjMgfVRCDkevZ0LmTxaQSNPdyS0iBeE |
| 700-A05 Bradycardia (2026-01-01) | dysrhythmia; referenced by 700-S06 §1.8 | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a05.pdf?VersionId=SVNL9xjz6ZUFnzX9nVDiQLQ93ufPOh7a |
| 700-P05 Pediatric Bradycardia (2026-01-01) | pediatric dysrhythmia | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-p05.pdf?VersionId=5ETckO_wL2_Al.cLFc7uQezFLKW8yFAr |
| 700-S02 ALS to BLS Transition of Care (2026-01-01) | the 2025 cycle made Red-criteria Trauma Alert patients ineligible for BLS transition | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s02.pdf?VersionId=2gxnY9KOD5cCmvy1Ed1pMG2ep4Dhr_3q |
| 700-S15 Abuse (new, 2026-01-01) | abuse, assault, domestic violence, human trafficking | https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s15.pdf?VersionId=Y8D6tJO_ODO.gn.3f2B5IMIlcDh80vNy |
| Summary of Policies Included in EMS Update | full list of the 2026 cycle | https://files.santaclaracounty.gov/exjcpb1541/2025-09/summary-of-policies-included-in-ems-update.pdf?VersionId=xfr0mO9WS7POvLxTJkl15V8wpo2_P_eI |
| AO 2025-006 (Policy 602 administrative changes, posted 2025-08-11) | may change Table B destinations | https://files.santaclaracounty.gov/exjcpb1541/2025-08/administrative-order-2025-006.pdf?VersionId=N2SX4u8FSEV_SiFj_aP_7KqaJsWoqLH4 |
| AO 2025-007 (Policy 602 administrative changes, posted 2025-10-16) | may change Table B destinations | PDF link not archived; open https://ems.santaclaracounty.gov/ao-2025-007-administrative-changes-policy-602-911-ems-patient-destination |
| Policy 509 Elite ePCR Documentation Guideline | documentation fields | https://files.santaclaracounty.gov/exjcpb1541/migrated/Policy509.pdf?VersionId=4Gq8ALasH9FRskA8esTYFn4ToMHiGEqg |

Also check the live policy manual (https://ems.santaclaracounty.gov/services/find-ems-policies-protocols-and-plans) for
anything published after January 2026 (§2).

---

## 5. Trauma: what the county defines

### 5.1 Trauma Alert criteria: Policy 605 Prehospital Trauma Triage (effective April 1, 2025)

Source: `AO-2025-005_policy-602-destination_eff-2025-04-01.pdf`, clean copy on PDF pages 25-27 (Policy 605 pages 1-3).
PDF pages 22-24 hold the same policy with tracked changes and "Deleted:" notes. Index only the clean copy.

- **§II.A** (p. 1): "Trauma alert patients are injured patients who meet ACS National Guidelines for Field Triage Criteria."
- **§II.B** (p. 1): "Injured patients are to be identified as a Trauma Alert Patient if one or more of the criteria below are
  met:"

**High Risk Injury Pattern (Red Criteria)**, §II.B, p. 1:

| Code | Exact text |
|---|---|
| A | "Penetrating injuries to head, neck, torso, and proximal extremities" |
| B | "Skull deformity, suspected skull fracture" |
| C | "Suspected spinal injury with new motor or sensory loss" |
| D | "Chest wall instability, deformity, or suspected flail chest" |
| E | "Suspected pelvic fracture" |
| F | "Suspected fracture of two or more proximal long bones" |
| G | "Crushed, degloved, mangled, or pulseless extremity" |
| H | "Amputation proximal to wrist or ankle" |
| I | "Active bleeding requiring a tourniquet or wound packing with continuous pressure" |

**Mental Status and Vital Signs (Red Criteria)**, §II.B, pp. 1-2:

| Code | Exact text |
|---|---|
| J | "Unable to follow commands (motor GCS <6)" |
| K | "Respiratory rate less than 10 or greater than 29 breaths per minute" |
| L | "Respiratory distress or need for respiratory support" |
| M | "Room-air pulse oximetry less than 90%" |
| N | "Vital signs below the following parameters: 1. Age 0-9 years: Systolic BP less than 70 mmHg + 2x age years 2. Age 10-64 years: Systolic BP less than 90 mmHg 3. Age older than 65 years: Systolic BP is less than 110 mmHg 4. Age 10 and older: Heart rate is greater than Systolic BP" |

**Moderate Risk Mechanism of Injury (Yellow Criteria)**, §II.B, p. 2:

| Code | Exact text |
|---|---|
| O | "Auto crash with partial or complete ejection" |
| P | "Auto crash with intrusion > 12 inches occupant site, > 18 inches any site, or need for extrication" |
| Q | "Death in passenger compartment" |
| R | "Child (age 0-9) unrestrained or in unsecure child safety seat" |
| S | "Vehicle telemetry data consistent with severe injury" |
| T | "Rider separated from transport vehicle with significant impact (eg. Motorcycle, ATV, horse etc.)" |
| U | "Rollover with unrestrained occupant" |
| V | "Pedestrian/bicycle rider thrown, run over, or with significant impact" |
| W | "Fall from height > 10 feet (all ages)" |

**Special Considerations (EMS Judgement)**, §II.B criterion X, pp. 2-3: "There are other factors that might influence
destination which patients should be treated in Trauma Centers. The following should be considered in prehospital trauma
triage when a traumatic injury is also present:"

| Code | Exact text |
|---|---|
| X.1 | "Patients with minor traumatic injuries also on anti-coagulants or with bleeding disorders" |
| X.2 | "Time-sensitive extremity injury" |
| X.3 | "EMS provider judgment to transport patient to a trauma center" |
| X.4 | "Hanging/mechanical asphyxiation in cardiac arrest with suspected head or neck injury" |
| X.5 | "Unwitnessed drowning with suspected head or neck injury" |
| X.6 | "Low-level falls with significant head impact" |
| X.7 | "Any pregnant patient beyond 20 weeks gestation (uterine fundus palpated at or above the umbilicus) in cardiac arrest, that does not meet obvious death criteria" |

**Major Burn Criteria**, §III.A, p. 3: "Patients with burn injuries are to be identified as major burn criteria if any of the
following are present: 1. Partial thickness burns greater than 10% of the total body surface area 2. Burns that include the
face, hands, feet, genitalia, perineum, or major joints 3. Full thickness burns 4. Electrical burns, including high voltage
(1,000v) and lightning injury 5. Chemical burns 6. Inhalation injury 7. Burn injury in patients with pre-existing medical
disorders that could complicate management, prolong recovery, or affect mortality". §III.B: "Transport all identified major
burn patients to a designated burn center". §III.D: patients who meet major burn and trauma alert criteria, where "the
traumatic injuries poses a greater risk of morbidity or mortality", go to "the closest trauma center".

### 5.2 Destination: Policy 602 911 EMS Patient Destination (effective April 1, 2025)

Clean copy, PDF pages 12-21 (Policy 602 pages 1-10).

- **§VI.C** (PDF p. 14, policy p. 3): "Trauma Alert Patients – Patients that meet High Risk Injury Pattern, Mental Status,
  and/or Vital Sign (Red Criteria) or Moderate Risk Mechanism of Injury or EMS Judgement (Yellow Criteria) according to Santa
  Clara County Prehospital Care Policy 605: Prehospital Trauma Triage."
  - §VI.C.1: "Injured patients that do not meet trauma alert criteria shall be transported to a destination prescribed by
    Section III: Routine Patient Destination."
  - §VI.C.2: "Adult Trauma Alert Patients shall be transported to the closest open Adult Trauma Center, identified in Table
    B: Approved In-County Services, determined by distance or time of travel."
  - §VI.C.3: "Pediatric Trauma Alert Patients shall be transported to the closest open Pediatric Trauma Center, identified
    in Table B: Approved In-County Services, determined by distance or time of travel."
  - §VI.C.4: "Pregnant trauma alert patients more than twenty (20) weeks gestation are to be transported to the closest
    trauma center with an approved Level III Neonatal ICU (Stanford Hospital or Santa Clara Valley Medical Center)."
  - §VI.C.5: if all trauma centers are not accepting, the "Closest emergency department to the incident location as
    determined by total emergency ambulance transport time; and That is accepting emergency ambulance patients."
- **§VI.D** (PDF p. 15, policy p. 4): "Burn Patients – Patients meeting major burn criteria as per Santa Clara County
  Prehospital Care Policy #605: Prehospital Trauma Triage shall be transported to the Burn Center at Santa Clara Valley
  Medical Center (VMC) via the Trauma Center."
- **§VI.H** (PDF p. 16, policy p. 5): "Pediatric Patients – Patients that are less than 15 years of age". This matches 700-S05
  §2.4 "Pediatric is defined as under 15 years of age".
- **§IV.B** In-Extremis (PDF p. 13, policy p. 2), relevant to hemorrhage: "A visible external bleed that cannot be controlled
  by EMS personnel where significant blood loss continues to occur despite the use of direct pressure and/or application of a
  tourniquet." In-extremis patients go to the closest hospital "not on internal disaster" (§IV.C).
- **AO 2025-005 §II** (PDF p. 1): "All Trauma Alert Patients will be transported to the closest appropriate Adult or
  Pediatric Trauma Center by either distance or time of transport. Field providers should monitor EMResource to confirm
  availability of specialty services prior to making a transport destination decision."

**Table B, Approved In-County Services** (PDF p. 20), read with Herald's own `read_check_table` reader on 2026-09-24:

| Service | Facilities (Table A IDs) |
|---|---|
| Adult Trauma Center | RSJ, SUH, VMC |
| Pediatric Trauma Center | SUH, VMC |
| Burn Center | VMC |
| STEMI Center | ECH, GSH, KSC, OCH, RSJ, STH, SUH, VMC |
| Advanced Pediatric Center | KSC, SUH, VMC |
| General Pediatric Center | ECH, GSH, KSC, OCH, RSJ, SLH, STH, SUH, VMC |
| Comprehensive Stroke Center (already in config) | ECH, GSH, KSC, RSJ, SUH |
| Primary Stroke Center (already in config) | ECH, GSH, KSC, LGH, OCH, RSJ, SLH, STH, SUH, VMC |

(Level III NICU trauma destination per §VI.C.4: SUH, VMC.) These rows could go into `config/counties/santa_clara.json`
`destinations.audit.services` next to the stroke rows. Check AO 2025-006 and AO 2025-007 first (§2).

### 5.3 What the Trauma Alert radio report must contain: Policy 501 (effective January 1, 2025)

- **§II.C** (p. 1): "Trauma Alerts, STEMI Alerts, Stroke Alerts, and critical patient transports, transporting with red lights
  and sirens (RLS), to the hospital shall be transmitted via self-initiated radio on the designated hospital ringdown channel."
- **§III.A** (pp. 1-2), standard report: "1. Demographics: a. Unit ID (agency, type, number) b. Estimated Time of Arrival c.
  Patient's Age d. Patient's Sex 2. EMS provider's primary impression and patient's chief compliant [sic] 3. State any
  pertinent medical history, pertinent medications, pertinent allergies, or other significant findings from physical
  assessment. 4. Vital Signs: explain and report abnormal vital signs; otherwise state "within normal limits" 5. Treatment
  provided: drugs given, airway status, or procedures completed."
- **§IV.C** (p. 2): "Specialty center hospital reports should occur prior to departure from the scene".
- **§IV.D** (p. 2): specialty reports "shall start with a clear statement indicating what type of alert applies to the
  patient (Trauma Alert, Stroke Alert, or STEMI Alert)".
- **§IV.E** (p. 2): "Additional information for Trauma Alert shall contain the following: 1. State the Mechanism of Injury
  according to Santa Clara County Prehospital Care Policy #605: Prehospital Trauma Triage 2. State the Anatomic and
  Physiologic Trauma Criteria for transport to a trauma center according to Santa Clara County Prehospital Care Policy #605:
  Prehospital Trauma Triage".
- Example (p. 2): "Medic 9 enroute with a Trauma Alert, ETA is ten minutes, 24-year-old female bilateral femur fractures,
  secondary to a long fall. GCS=3, BP=100/50, Pulse= 120. Pt is intubated."

### 5.4 Trauma treatment protocols: facts they tie to the alert

- **700-A16 Trauma Care** (effective January 1, 2026):
  - §2.3 (p. 1): "Determine if the patient is a trauma alert patient (Policy 605), and select the appropriate trauma center
    (Policy 602)".
  - §2.8 (p. 1): "If patient is a Trauma Alert Patient all BLS and ALS care except for airway management and spinal motion
    restriction is to be completed en route to the selected Trauma Center".
  - §3.4.3 (p. 1) lists "Injury is less than 3 hours old" as one condition of a medication indication. Quoted only because it
    makes the **time of injury** a fact the receiving team and the chart need.
  - §5.2 (p. 2): "Target scene time less than 10 minutes for unstable patients or those likely to need surgical
    intervention".
  - §6 Key Documentation Elements (p. 2): "6.1. Mechanism of injury 6.2. Primary and secondary survey 6.3. Vital signs
    including neurologic status assessments according to (700-S04) 6.4. Scene time 6.5. Procedures performed and patient
    response."
- **700-S06 Falls** (effective January 1, 2026):
  - §1.2.1 (p. 1): "If patient meets trauma alert criteria (Policy 605) follow the Trauma Care Protocol (700-A16) select the
    appropriate trauma center and transport immediately (Policy 602). Exceptions may apply to hospice/advance directive
    patients."
  - §1.11 (p. 1): "If patient fell more than 72 hours ago and does not meet any "Red" Prehospital Trauma Triage criteria,
    activation as Trauma Alert Patient is not required". This is new in the 2026 cycle (2026 memo: "If time of fall was more
    than 72 hours and no other Red Trauma Triage Criteria are met, do not activate as Trauma Alert Patient"). It makes the
    **time of the fall** a checklist fact.
  - §3.3 (p. 1): "Patients with bleeding disorders or taking anticoagulants are at an increased risk for cerebral hemorrhage.
    For patients whose head may have hit ground/object yet have no apparent injuries can be transported to closest ED for
    evaluation."
  - Page 2 is a flowchart image with no text layer. It needs a `figures` entry like 700-A13 page 3.
- **700-P16 Pediatric Trauma Care** (effective January 1, 2025): §2.3 (p. 1) same Trauma Alert step as 700-A16. §6 (p. 2)
  Key Documentation Elements: "Mechanism of Injury", "Primary and Secondary Survey", "Vital signs according to Routine Medical
  Care – Pediatric (700-S05)", "Scene time".
- **700-M17 Traumatic Hemorrhage Control** (effective January 1, 2026): wound packing (§1.2) and tourniquet (§2). §1.2.3
  (p. 1): "If the wound is large enough to accept multiple gauze, a count should be maintained and communicated to the
  receiving hospital." A tourniquet or wound packing is itself Red criterion I.
- **700-S04 §2.2** (p. 1): "Glasgow Coma Scale on every patient and every reassessment".

### 5.5 County criteria compared with the national 2021 guideline in `config/scores/field_triage.yaml`

National source: Newgard CD et al., National Guideline for the Field Triage of Injured Patients, J Trauma Acute Care Surg
2022;93(2):e49-e60 (local copy `/home/hp18/Documents/team-last-minute/.agent/sources/field-triage-guideline-2021.txt`).

| Point | County (Policy 605 / 602) | National 2021 | What it means for Herald |
|---|---|---|---|
| What Yellow means | Yellow (mechanism or EMS judgement) is a **Trauma Alert** and goes to "the closest open Adult Trauma Center" (602 §VI.C, §VI.C.2) | Yellow: "preferentially transported to a trauma center ... (need not be the highest-level trauma center)" | In this county a Yellow hit should show "Trauma Alert (Yellow, Policy 605 X/O-W)", not a lower tier. `field_triage.yaml` is national; the county rule belongs in the county config. |
| SBP by age | "Age 10-64 years: ... less than 90"; "Age older than 65 years: ... less than 110" | "Age 10–64" and "Age ≥ 65" | Read literally, the county text covers no band at exactly 65. The county says its criteria are the ACS national ones (605 §II.A), and Herald's `age_min: 65` follows the national ≥65. Keep it and note the county wording gap. |
| HR > SBP | "Age 10 and older" | 10-64 and ≥65 (same) | same |
| Respiratory distress / need for respiratory support | Red criterion L | Red | **Not in `field_triage.yaml`** (it has motor GCS, RR, room-air SpO2, SBP, HR>SBP). It needs a fact source (§10). |
| Rollover | "Rollover with unrestrained occupant" (U) is Yellow | not in 2021 | county-only criterion |
| Low-level falls | "Low-level falls with significant head impact" (X.6), **no age limits** | "young children (age ≤ 5 years) or older adults (age ≥ 65 years)" | county is broader |
| Anticoagulants | "minor traumatic injuries also on anti-coagulants or with bleeding disorders" (X.1) | "Anticoagulant use" | county adds bleeding disorders |
| Pregnancy | ">20 weeks ... in cardiac arrest" (X.7); any pregnant Trauma Alert over 20 weeks goes to a trauma center with a Level III NICU (602 §VI.C.4) | "Pregnancy > 20 weeks" (Yellow) | ask pregnancy weeks for any injured patient who could be pregnant; the county uses it for destination |
| Hanging, drowning with suspected head/neck injury | X.4, X.5 | not listed | county-only |
| Child abuse, special healthcare needs, burns with trauma | not in 605 §II (burns handled in §III.D) | Yellow EMS judgment | national only |
| Fall older than 72 h | no Trauma Alert unless a Red criterion is met (700-S06 §1.11) | not addressed | county-only |

### 5.6 Structure notes for indexing Policy 605

- The clean copy numbers two sections "II." ("II. Trauma Alert Patient" and "II. Trauma Alert – Ambulance Transport"), then
  "III. Major Burn Criteria". The criteria under §II.B restart lettering at "A." and run to "X.", which the outline heading
  style reads as a new level. Cite them as "Policy 605 §II.B criterion J" to stay unambiguous.
- The AO file repeats every page in a tracked-changes copy with "Deleted:" margin notes (602 on PDF pp. 2-11, 605 on pp.
  22-24). A document entry for 605 should use `"pages": [25, 27]`, the way 602 already uses `[12, 21]`.

---

## 6. Sepsis: what the county defines

### 6.1 County criteria: 700-A04 Sepsis (effective January 1, 2026; replaces January 1, 2025; one page)

- §1 Patient Care Goals:
  - "1.1. Maintain systolic blood pressure greater than 90 mmHg to ensure adequate perfusion"
  - "1.2. Administer fluids to address tachycardia, hypotension, or signs of circulatory compromise"
  - "1.3. Identification of Systemic Inflammatory Response Syndrome (SIRS) Criteria"
    - "1.3.1. Temperature less than 96 °F or greater than 100.4 °F"
    - "1.3.2. Heart rate greater than 90 bpm"
    - "1.3.3. Respiratory rate greater than 20 bpm"
    - "1.3.4. ETCO2 less than 25 mmHg"
  - **"1.4. Advanced notification to hospital of suspected sepsis patient if two or more SIRS criteria are met"**
- §2.3: "Treat associated signs and symptoms of shock as appropriate (700-A10)"
- §4 Pertinent Assessment Findings, "4.1. Signs of infection can include:"
  - "4.1.1. Lungs – Cough, dyspnea, chest pain, sputum production"
  - "4.1.2. Genitourinary – Dysuria, discharge, abdominal/flank pain"
  - "4.1.3. Skin/soft tissue – Rashes, erythema, broken skin/decubitus ulcers, joint pain"
  - "4.1.4. CNS – Headaches, convulsions, photophobia, neck pain"
  - "4.1.5. Gastrointestinal – Diarrhea, vomiting, abdominal pain, jaundice"
- §5 Key Documentation Elements: "5.1. Assessment findings indicative of infection 5.2. Abnormal vital sign findings 5.3.
  Response to medication/procedures"

How to read it:

- These are the classic SIRS criteria adapted for the field. White-cell count is replaced by EtCO2 below 25 mmHg, and the low
  temperature cut-off is 96 °F (35.6 °C), not the classic 36 °C (96.8 °F). Use the county numbers as written.
- The trigger is "**suspected sepsis patient**" with two or more SIRS criteria, so a suspected infection (§4.1, `infection.suspected`)
  is part of the rule, not only the vital signs. Tachycardia and tachypnea from trauma or anxiety alone should not open the
  sepsis checklist.
- It is a hospital **advance notification**, not a named alert. Policy 501 §II.C and §IV.A name only "Trauma Alerts, STEMI
  Alerts, Stroke Alerts" (plus RLS critical transports) for the ringdown channel. A sepsis notification is therefore a
  standard hospital report under §II.B ("via cellular phone or the services dispatch centers"), unless the unit is running red
  lights and sirens. This is an inference from 501, flagged for review. Herald wording: "Sepsis pre-notification criteria met
  (700-A04 §1.4)".
- In the 2026 cycle the county changed only the vasopressor reference in 700-A04 (2026 memo: "Directed to follow 700-A10
  Shock protocol for push-dose epinephrine"). The 2025 cycle added IV acetaminophen for fever and "Specified total dose of 1L
  fluid bolus". Neither changes the criteria.

### 6.2 Related county text

- **700-A10 Shock** §4.1 (effective January 1, 2026, p. 1): "Decreased perfusion manifested by altered mental status, or
  abnormalities in capillary refill or pulses, decreased urine output (1 mL/kg/hr): 4.1.1. Cardiogenic, hypovolemic,
  obstructive shock: capillary refill greater than 2 seconds, diminished peripheral pulses, mottled cool extremities 4.1.2.
  Distributive shock: flash capillary refill, bounding peripheral pulses". §5 Key Documentation Elements: "5.1. Medications
  administered 5.2. Vital signs according to Routine Medical Care – Adult (700-S04) 5.3. Neurologic status assessment 5.4.
  Amount of fluid given".
- **700-S04** (effective January 1, 2026, p. 1): "2.7. Temperature on every initial assessment"; "2.8. Baseline vital signs,
  except for temperature, will be assessed every ten (10) minutes on stable patients and every five (5) minutes on unstable
  patients"; "3.2. Capnography on every patient that received an airway adjunct BLS or ALS".
- **EtCO2 may not be measured.** 700-S04 requires capnography only for patients with an airway adjunct, and Policy 302
  (effective 1/1/2026) stocks a "Capnography Device (colorimetric or waveform)". A colorimetric device gives no mmHg number.
  In the checklist, EtCO2 must show as **not measured** (missing), never as "criterion not met" (AGENTS invariant 6).
- **No lactate** appears in any county sepsis document or in the Policy 302 minimum inventory.

### 6.3 National context (**non-county**; the county has its own criteria, so these are background only)

- **Surviving Sepsis Campaign 2021** (Evans L, Rhodes A, Alhazzani W, et al. Intensive Care Med 2021;47:1181-1247 and Crit
  Care Med 2021;49:e1063-e1143; https://link.springer.com/article/10.1007/s00134-021-06506-y): "We recommend against using
  qSOFA compared with SIRS, NEWS, or MEWS as a single screening tool for sepsis or septic shock" (strong recommendation,
  moderate-quality evidence).
- **Surviving Sepsis Campaign 2026** (Prescott H, Antonelli M, Alhazzani W, et al. Crit Care Med 2026, doi
  10.1097/CCM.0000000000007075; also in Intensive Care Med, https://link.springer.com/article/10.1007/s00134-026-08361-1;
  statements as published on the SCCM guideline page
  https://www.sccm.org/clinical-resources/guidelines/guidelines/surviving-sepsis-campaign-international-guidelines-for-management-of-sepsis-and-septic-shock-2026):
  - "For acutely ill patients in hospital, we 'recommend' using NEWS, NEW2 [sic], MEWS, or SIRS over qSOFA as a single tool to
    screen for sepsis." (strong, moderate)
  - "In acutely ill adults en route to hospital by ambulance or flight, we 'suggest' using a standard sepsis screening tool
    over not using a screening tool." (conditional, very low)
  - "For adults with possible, probable, or definite sepsis or septic shock, we 'suggest' measuring blood lactate."
    (conditional, low). This is a hospital measure. It does not justify adding a lactate key now.
  - The prehospital statement names no specific tool. A search-engine summary said the panel preferred no single tool
    because of false-positive screens, but no page that could be opened confirmed it, so treat it as unverified. The full
    text (Crit Care Med) was paywalled and was not read directly.
- **NAEMSP:** no dedicated NAEMSP position statement on prehospital sepsis recognition was found (search of naemsp.org
  position statements and the literature, 2026-09-24). Cite none.
- **NASEMSO National Model EMS Clinical Guidelines (2022):** the county's 2025-cycle memo names these guidelines as the basis
  of the "Patient Care Goals / Pertinent Assessment Findings / Key Documentation Elements" sections
  (https://nasemso.org/wp-content/uploads/National-Model-EMS-Clinical-Guidelines_2022.pdf).

**For Herald:** the county SIRS rule is the county criterion and belongs in the county config. NEWS2 (already
`config/scores/news2.yaml`) is a published score consistent with SSC 2026's advice to use a standard screening tool. Show both
side by side, each with its source. Neither decides anything.

---

## 7. STEMI: what the county defines (re-check of the existing checklist)

### 7.1 County text

**700-A08 Chest Pain - Suspected Cardiac Ischemia** (effective January 1, 2025; replaces January 1, 2024; the 2025 memo says
"No changes to treatment"; not revised in the 2026 cycle):

- §1 Patient Care Goals (p. 1): "1.1. 12-lead ECG obtained within 10 minutes of patient contact 1.2. Determine time of
  symptom onset 1.3. Administration of ASA and NTG unless contraindications present 1.4. Transmission of 12-lead ECG and
  STEMI Alert advanced notification to receiving hospital"
- §3.2 (p. 1): "Obtain quality, artifact free, 12 Lead ECG, if 12 Lead ECG states "STEMI" or "Acute MI Suspected": 3.2.1.
  Determine closest most appropriate STEMI receiving center 3.2.2. Transmit 12 Lead ECG to the selected STEMI Center, when
  the first transmission capable monitor arrives, regardless of ETA to receiving facility (700-M09) 3.2.3. Provide advanced
  notification of STEMI Alert patient (Policy 501)"
- §5.2 (p. 2): "12-lead ECG should be obtained according to findings listed in (700-M09) as ACS/STEMI can present with
  atypical pain, vague or only generalized complaints"
- **§6 Key Documentation Elements (p. 2): "6.1. Time of symptom onset 6.2. Time of first 12 Lead ECG 6.3. Time of aspirin
  administration 6.4. Time of STEMI Alert notification to hospital"**
- §7.2 (p. 2) names phosphodiesterase-inhibitor use "within the past 48 hours" and IV epoprostenol or treprostinil as reasons
  to withhold nitroglycerin. Quoted only because these are "pertinent medications" (501 §III.A.3). Herald does not advise
  on nitroglycerin.
- Page 3 is a flowchart image with no text layer (needs a `figures` entry).

**700-M09 12-Lead Electrocardiogram** (effective January 1, 2024):

- §2.2 (p. 1): "The criteria for ST elevation is at least 1mm ST segment elevation in inferior lead, or at least a 2mm ST
  segment elevation in anterior or lateral leads, or 2 or more contiguous leads."
- §3.1 (p. 1): "Obtain a 12-lead ECG on any adult patient with one or more of the following findings:" substernal pain;
  discomfort or tightness radiating to the jaw, left shoulder or arm; palpitations; symptoms indicating cardiogenic shock;
  bradycardia or tachycardia; epigastric pain; diaphoresis; dyspnea; pulmonary edema; anxiety with feeling of impending doom;
  syncope/dizziness; "Atypical presentation such as generalized weakness, nausea, vomiting especially in women, elderly and
  diabetics"; as identified in another county policy; paramedic discretion (§3.1.1-3.1.14). These are good **triggers** for
  opening the STEMI checklist.
- §4.1 (p. 1): "Obtain first ECG prior to leaving scene" (the county text reads "Endotracheal Obtain first ECG", a typo).
- §4.8 (p. 2): "Serial 12-lead EKGs, en-route, are encouraged but do not need to be transmitted once SRC notified"
- §4.9 (p. 2): "ECG criteria for STEMI Alerts: ... Most manufacturers demarcate STEMI's with three (3) asterisks before and
  after the text and use capitalized and bolded text. 4.9.1. If the ECG monitor reading identifies a STEMI: 4.9.1.1.
  Immediately notify the receiving hospital with a STEMI ALERT and transmit the 12 lead ECG to the STEMI receiving hospital
  4.9.1.2. Transmission of the ECG can dramatically reduce the door to balloon time. Transmission shall be completed as soon
  as possible"
- Page 2 "STEMI Location Interpretation" is an image (needs a `figures` entry).

**Policy 501** (effective January 1, 2025): §II.C, STEMI Alerts go by ringdown radio. §IV.C, "prior to departure from the
scene". §IV.D, the report starts with "STEMI Alert". Example (p. 2): "Medic 25 enroute with a STEMI ALERT, ETA is eleven
minutes, 56-year-old male complaining of severe chest pain. Pt is pale, cool, diaphoretic, GCS 14, BP=90/60, Pulse= 60,
RR=10, ECG confirmed STEMI. Asprin [sic], Nitro, and Morphine given".

**Policy 602** (effective April 1, 2025):

- §VI.F (PDF pp. 15-16): "STEMI Alert Patients – Patients that are identified as meeting STEMI Alert Criteria according to
  Santa Clara County Prehospital Care Policy #700-A08: Chest Pain - Suspected Cardiac Ischemia shall be transported to: 1. The
  closest STEMI Receiving Center identified in Table B: Approved In-County Services to the incident location as determined by
  total emergency ambulance transport time; and 2. That is accepting emergency ambulance patients that meet STEMI Alert."
- §VI.G (PDF p. 16): "ROSC (Return of Spontaneous Circulation) – Adult Patients achieving ROSC of cardiac etiology according
  to Santa Clara County Prehospital Care Policy #700-A07: Cardiac Arrest shall be transported to: 1. The closest STEMI
  Receiving Center ..."
- Table B STEMI Centers: ECH, GSH, KSC, OCH, RSJ, STH, SUH, VMC (§5.2 above).

**Policy 430 STEMI Center Standards** (effective February 15, 2025), §VII.A (p. 3): a STEMI Receiving Center must "1. Agree to
accept all EMS suspected STEMI patients according to applicable EMS policies/protocols." and "5. Have the ability and process
to receive ECGs wirelessly transmitted by pre-hospital personnel."

### 7.2 Existing Herald STEMI checklist compared with the county

Current `config/checklists.yaml` `alerts.stemi.items`: `symptom.onset`, `ecg.twelve_lead_time`, `ecg.attached`,
`allergies`, `meds.anticoagulant`, `vitals.sbp`.

| Existing item | County support | Verdict |
|---|---|---|
| `symptom.onset` Symptom onset | 700-A08 §1.2, §6.1 | keep |
| `ecg.twelve_lead_time` 12-lead time | 700-A08 §6.2 ("Time of first 12 Lead ECG"); goal §1.1 within 10 minutes of patient contact | keep; label "First 12-lead time" |
| `ecg.attached` 12-lead attached | The county asks for **transmission to the STEMI center** (700-A08 §1.4, §3.2.2; 700-M09 §4.9.1.1; 430 §VII.A.5). Per the labeling guide, "attached" means the 12-lead is attached. | keep as Herald's own relay attachment; add the county item "12-lead transmitted to STEMI center" (NEW `ecg.transmitted`) |
| `allergies` Allergies | 501 §III.A.3 "pertinent allergies" (standard report, not STEMI-specific) | keep |
| `meds.anticoagulant` Anticoagulants | **Not in any county STEMI document.** Only 501 §III.A.3 "pertinent medications". | keep only if the team wants it for the cath lab, with a non-county source (a local cardiology choice), or move it to `unknowns` |
| `vitals.sbp` Blood pressure | 501 §III.A.4 vital signs; SBP thresholds recur in 700-A08 §2.4 and §3.3 | keep |
| missing: monitor reading "STEMI" / "Acute MI Suspected" | 700-A08 §3.2; 700-M09 §4.9.1 (this is what makes it a STEMI Alert) | add (NEW `ecg.stemi_reading`) |
| missing: time of aspirin | 700-A08 §6.3 | add, from existing `meds.given` (drug "aspirin"), shown as documentation, never as a prompt to give it |
| missing: STEMI Alert notification time | 700-A08 §6.4 | from the relay's own send log (system event, not a spoken fact) |
| missing: destination | 602 §VI.F (closest open STEMI Receiving Center) | `transport.destination` + Table B STEMI list |
| missing: ETA, age, sex | 501 §III.A.1 | existing keys; part of every alert header |

---

## 8. Other call types: quick reference for the broad copilot

Status as in §3. Key Documentation Elements are the county's own list of what must be charted. They are the natural
per-call-type "what is missing" list.

- **Cardiac arrest / ROSC.** Current 700-A07 (2026) not archived. From the 2026 memo: "Traumatic cardiac arrest do not
  resuscitate if PEA less than 40 bpm/asystole or transport time greater than 20 minutes"; for ROSC, dopamine replaced "per
  700-A10" (push-dose epinephrine); magnesium added for torsades. The superseded 2025 version (`previous/`, p. 4) lists Key
  Documentation Elements: "Resuscitation attempted and all interventions performed; Arrest witnessed; Location of arrest;
  First monitored ECG rhythm; CPR prior to EMS arrival; Outcome upon arrival at hospital; Any ROSC; Presumed cardiac arrest
  etiology" (§14.1-14.8). The current **700-P07** (2026, p. 4) has the same §14 list. Its §12 ROSC (p. 3) includes "Continue
  ventilations at a rate and volume to keep ETCO2 between 30-40 mmHg" and "Blood Glucose Level, readings of less than 60mg/dl
  require interventions". Adult ROSC of cardiac cause goes to the closest STEMI Receiving Center (602 §VI.G). The 2025 A07 §1.5
  (p. 1): "For medical (non-traumatic) causes of cardiac arrest without obvious signs of death, 20 minutes of resuscitation
  efforts on-scene prior to making transport decision". Re-check this against the 2026 text when downloaded.
- **Respiratory distress.** Current 700-A11 (2026) not archived. 2026 memo: ipratropium combined with the first albuterol dose,
  magnesium if no change in COPD/asthma, "SpO2 goal 88-92% for COPD". The superseded 2025 version §9 (p. 2) Key Documentation
  Elements: initial vital signs and exam; interventions with airway method, equipment size and number of attempts; vitals after
  interventions; "Post-intubation with advanced airway, EtCO2 value and capnograph should be documented immediately after
  airway placement, with each patient movement ... and at the time of patient transfer in the ED"; respiratory rate and SpO2
  at baseline and after each intervention. §8.3: "Severe respiratory distress may manifest with hypoxia, altered mentation,
  diaphoresis, or inability to speak more than 2–3 words". Current **700-P11** (2025) covers children.
- **Seizure.** Current 700-A02 (2026) not archived (2026 memo: midazolam dosing-interval and base-contact changes). Superseded
  2025 version §1.2 (p. 1): "Identify Status Epilepticus characterized by continuous seizure lasting more than 5 minutes OR
  more than one seizure without return to baseline mental status". §6 (pp. 1-2) Key Documentation: seizures witnessed by
  providers with duration and type, eye deviation, apnea/cyanosis/vomiting/incontinence/fever, medications given by non-EMS
  personnel, neurologic status including GCS and pupils. 700-A13 §2.4 routes seizure during stroke symptoms to 700-A02. Status
  epilepticus in a child under 15 is a "critically ill" criterion for an Advanced Pediatric Receiving Center (602 §VI.H.1.f).
  Current **700-P02** (2026).
- **Overdose / poisoning, 700-A15** (2025): §2.3 "Blood Glucose Level (BGL)"; §2.4 "Determine the substance and/or dosage of
  the overdose"; §3.2 "Consider 12-lead ECG". §12 Key Documentation (p. 2): "Repeat evaluation and documentation of signs and
  symptoms ... Identification of possible etiology of poisoning ... Initiating measures on scene to prevent exposure of
  bystanders ... Time of symptoms onset and time of initiation of exposure specific treatments". Current **700-P15** (2025).
- **Hypoglycemia, 700-A03** (2025): the county threshold is 60 mg/dL (§2.4.1, §3.2: "60mg/dl or less"; 700-S04 §2.9.2 "less
  than 60 mg/dl along with symptoms of hypoglycemia or altered mental status requires intervention (700-A03)"). §4 Pertinent
  findings include "Trauma due to falls or other mechanism" and "Insulin pump and oral hypoglycemic agents". §5 Key
  Documentation: glucose and vitals "before and after interventions" and "Potential causes of hypoglycemia". Children:
  **700-P03** and 700-S05 §3.9.2 ("less than 60 mg/dl or 45 mg/dl for neonates").
- **Pediatric general care, 700-S05** (2026): §2.1-2.4 define neonate (0-4 weeks), infant (1 month-1 year), child (older than 1
  year), and "Pediatric is defined as under 15 years of age". §3 vitals are like the adult ones (BP except neonates). 602
  §VI.H.1 lists the "critically ill" criteria that send a child to an Advanced Pediatric Receiving Center (KSC, SUH, VMC):
  cardiac dysrhythmia, poor perfusion, severe respiratory distress, persistent altered mental status, stroke-like symptoms,
  status epilepticus, BRUE, ROSC, suspicion of child abuse, paramedic discretion.
- **General assessment and documentation, 700-S04** (2026): §2.2-2.6, GCS, BP, RR, pulse and SpO2 "on every patient and every
  reassessment". §2.7 temperature on every initial assessment. §2.8 vitals every 10 minutes if stable and **every 5 minutes if
  unstable** (the county config's `reassess_min: 10` covers only the stable case). §2.9 glucose "on assessment of ALOC,
  stroke, and suspected diabetics". §6.2 "Pain scale score must be documented prior to and post administration of any
  analgesic" (new in 2026; `vitals.pain`). §10.5 "Documentation shall include, at a minimum, medication name, dose, route,
  time of administration, and patient response (including vital signs)" (`meds.given`). Policy 500 (2020) sets the ePCR rules,
  including leaving the ePCR with the receiving facility.

---

## 9. Proposed checklists

Principles, from AGENTS.md: the model only extracts facts. The checklists and alert criteria are deterministic data in
`config/`, each with its county citation. Nothing says "give" or "do". Missing facts show as missing. Keys are those in
`config/vocabulary.yaml` as of 2026-09-24 04:55 (the run E keys are already there); **NEW** marks a key that does not exist
yet.

### 9.1 Trauma Alert checklist (Santa Clara)

Opens on: a dispatch or chief complaint with an injury mechanism ("fall", "MVC", "crash", "GSW", "stab", "assault",
"pedestrian", "struck", "ejected", "rollover", "burn", "trauma"), or on any `trauma.mechanism` / `trauma.injuries` fact.

| # | Item (label) | Herald key | Key status | County source | Notes |
|---|---|---|---|---|---|
| 1 | Mechanism of injury | `trauma.mechanism` | existing | 501 §IV.E.1; 605 §II.B O-W; 700-A16 §6.1 | the report must state it |
| 2 | Injuries found (anatomic criteria) | `trauma.injuries` | existing | 501 §IV.E.2; 605 §II.B A-I | free text, as said |
| 3 | Policy 605 criteria met (Red A-N, Yellow O-W, X.1-X.7) | `trauma.criteria` | **NEW** (§10) | 501 §IV.E.2 ("State the Anatomic and Physiologic Trauma Criteria"); 602 §VI.C | the deterministic Trauma Alert decision reads this plus the vitals; starts unconfirmed (medic taps) |
| 4 | GCS (total) | `vitals.gcs_total` | existing | 700-S04 §2.2; 700-A16 §6.3; 501 example "GCS=3" | |
| 5 | Follows commands (motor GCS) | `vitals.gcs_motor` | existing | 605 J | already in `field_triage.yaml` |
| 6 | Systolic BP | `vitals.sbp` | existing | 605 N.1-N.3 (age bands); 501 §III.A.4 | needs `patient.age` |
| 7 | Heart rate | `vitals.hr` | existing | 605 N.4 (HR > SBP, age 10+) | |
| 8 | Respiratory rate | `vitals.rr` | existing | 605 K | |
| 9 | SpO2 on room air | `vitals.spo2` + `vitals.on_oxygen` | existing | 605 M ("Room-air pulse oximetry less than 90%") | already `room_air_below` in `field_triage.yaml` |
| 10 | Respiratory distress / respiratory support | `procedures.done` (bvm ventilation, cpap, supraglottic airway, intubation) + `trauma.criteria` "L" | existing + **NEW** | 605 L | the finding "respiratory distress" has no key; carry it as criterion L |
| 11 | Age | `patient.age` | existing | 605 N; 602 §VI.C.2-3 (adult vs pediatric under 15, 602 §VI.H / 700-S05 §2.4) | |
| 12 | Sex | `patient.sex` | existing | 501 §III.A.1.d | |
| 13 | Anticoagulants or bleeding disorder | `meds.anticoagulant` (+ `trauma.criteria` "X.1" for a bleeding disorder) | existing | 605 X.1; 700-S06 §3.3 | |
| 14 | Pregnancy over 20 weeks | `patient.pregnancy_weeks` | existing | 602 §VI.C.4 (destination SUH/VMC); 605 X.7 | ask only when relevant (UI rule) |
| 15 | Time of injury / fall | `symptom.onset` (reuse) or **NEW** `trauma.injury_time` | decision (§10) | 700-S06 §1.11 (falls over 72 h without a Red criterion are not a Trauma Alert); 700-A16 §3.4.3 | |
| 16 | Treatment given (tourniquet, packing, airway, drugs) | `procedures.done`, `meds.given` | existing | 501 §III.A.5; 605 I; 700-M17 §1.2.3 (gauze count to the hospital); 700-A16 §6.5 | |
| 17 | Destination (closest open adult / pediatric trauma center) | `transport.destination` | existing | 602 §VI.C.2-3, Table B (adult RSJ, SUH, VMC; pediatric SUH, VMC); burns VMC (602 §VI.D) | check AO 2025-006/-007 |
| 18 | ETA | `transport.eta_min` | existing | 501 §III.A.1.b | |
| 19 | Allergies, medications, history | `allergies`, `meds.list` | existing | 501 §III.A.3 | via `default_unknowns` |
| 20 | Scene time | existing scene clock (`snapshot._clocks` "scene") | existing (clock) | 700-A16 §5.2 (target under 10 minutes if unstable), §6.4 | the county config could carry `scene_target_min: 10` for trauma |

Derived deterministic outputs (county config, not the model):

- "Trauma Alert: Red (605 §II.B J, N.2)" when any Red criterion is met from confirmed facts.
- "Trauma Alert: Yellow (605 §II.B W)" for mechanism or EMS judgement. In Santa Clara this is still a Trauma Alert (602 §VI.C).
- "Not a Trauma Alert (700-S06 §1.11)" for a fall more than 72 hours old with no Red criterion.
- Destination hint from Table B: adult trauma center, pediatric trauma center if under 15, trauma center with Level III NICU if
  over 20 weeks pregnant, burn center via the trauma center.

### 9.2 Sepsis pre-notification checklist (Santa Clara)

Opens on: `infection.suspected` present, or a dispatch or complaint of "fever", "sepsis", "septic", "infection",
"pneumonia", "UTI", "cellulitis", "wound infection".

| # | Item (label) | Herald key | Key status | County source | Notes |
|---|---|---|---|---|---|
| 1 | Suspected infection and source | `infection.suspected` | existing | 700-A04 §1.4 ("suspected sepsis patient"), §4.1.1-4.1.5, §5.1 | the labeling guide's categories (respiratory, urinary, skin, ...) map to the county's lungs / genitourinary / skin-soft tissue / CNS / GI |
| 2 | Temperature | `vitals.temp` | existing (°C) | 700-A04 §1.3.1 (below 96 °F or above 100.4 °F); 700-S04 §2.7 | county thresholds in °C: below 35.56, above 38.0. Store the °F text and the °C value in config |
| 3 | Heart rate | `vitals.hr` | existing | 700-A04 §1.3.2 (above 90) | |
| 4 | Respiratory rate | `vitals.rr` | existing | 700-A04 §1.3.3 (above 20) | |
| 5 | EtCO2 | `vitals.etco2` | existing | 700-A04 §1.3.4 (below 25 mmHg) | show "not measured" when absent; colorimetric devices give no number (302) |
| 6 | Systolic BP | `vitals.sbp` | existing | 700-A04 §1.1 (goal above 90); 700-A10 | |
| 7 | Mental status | `vitals.consciousness` / `vitals.gcs_total` | existing | 700-A10 §4.1 ("altered mental status"); 700-S04 §2.2 | |
| 8 | SpO2 | `vitals.spo2` | existing | 700-S04 §2.6 | also feeds NEWS2 |
| 9 | Fluids and medications given, and response | `meds.given` | existing | 700-A04 §5.3; 700-A10 §5.1, §5.4 ("Amount of fluid given") | documentation, not advice |
| 10 | Age, sex, ETA, allergies, medications | `patient.age`, `patient.sex`, `transport.eta_min`, `allergies`, `meds.list` | existing | 501 §III.A | |

Derived deterministic output: a county "SIRS (700-A04)" criteria score. Proposed file
`config/scores/sirs_santa_clara.yaml` (kind `criteria`) or a county-config block, with four criteria and the rule "≥ 2 of 4
with a suspected infection → Sepsis pre-notification criteria met (700-A04 §1.4)". Show "incomplete" while an input is
missing (for example "2 of 3 measured, EtCO2 not measured"). Show NEWS2 next to it as a published, non-county score (SSC 2026).

### 9.3 STEMI Alert checklist (Santa Clara)

Opens on: the existing triggers plus the 700-M09 §3.1 findings ("chest pain", "substernal", "jaw", "left arm", "palpitations",
"epigastric", "diaphoretic", "impending doom", "syncope") and any `ecg.*` fact. Keep the triggers in config and cite 700-M09
§3.1.

| # | Item (label) | Herald key | Key status | County source |
|---|---|---|---|---|
| 1 | Monitor reads "STEMI" / "Acute MI Suspected" | `ecg.stemi_reading` | **NEW** | 700-A08 §3.2; 700-M09 §4.9.1 |
| 2 | Symptom onset | `symptom.onset` | existing | 700-A08 §1.2, §6.1 |
| 3 | First 12-lead time | `ecg.twelve_lead_time` | existing | 700-A08 §6.2; goal §1.1 (within 10 min of patient contact); 700-M09 §4.1 (before leaving scene) |
| 4 | 12-lead transmitted to the STEMI center | `ecg.transmitted` | **NEW** | 700-A08 §1.4, §3.2.2; 700-M09 §4.9.1.1-4.9.1.2; Policy 430 §VII.A.5 |
| 5 | Aspirin time (documentation) | `meds.given` (drug "aspirin", time) | existing | 700-A08 §6.3 |
| 6 | Systolic BP (+ HR, RR) | `vitals.sbp`, `vitals.hr`, `vitals.rr` | existing | 501 §III.A.4 and example |
| 7 | Allergies | `allergies` | existing | 501 §III.A.3 |
| 8 | Destination: closest open STEMI Receiving Center | `transport.destination` | existing | 602 §VI.F, Table B (ECH, GSH, KSC, OCH, RSJ, STH, SUH, VMC) |
| 9 | ETA, age, sex | `transport.eta_min`, `patient.age`, `patient.sex` | existing | 501 §III.A.1 |
| 10 | STEMI Alert notification time | relay send log | system event | 700-A08 §6.4; 501 §IV.C (before leaving scene) |
| (opt.) | 12-lead attached to the Herald relay | `ecg.attached` | existing | Herald's own relay, not a county item |
| (opt.) | Anticoagulants | `meds.anticoagulant` | existing | not in county STEMI documents; 501 §III.A.3 "pertinent medications" only |

ROSC: 602 §VI.G sends adult ROSC of cardiac cause to the same STEMI center list. The cardiac arrest items (§8) should become
their own checklist once the 2026 700-A07 is downloaded.

### 9.4 Suggested data shape (proposal for whoever owns `config/checklists.yaml`; not applied)

```yaml
# config/checklists.yaml (sketch). County-specific criteria and destinations stay in config/counties/santa_clara.json.
alerts:
  trauma:
    label: Trauma alert
    source: "Santa Clara Policy 605 §II.B (AO 2025-005, eff. 2025-04-01); Policy 501 §IV.E; Policy 602 §VI.C"
    items:
      - [trauma.mechanism, Mechanism of injury]
      - [trauma.injuries, Injuries found]
      - [trauma.criteria, Policy 605 criteria met]        # NEW key
      - [vitals.gcs_total, GCS]
      - [vitals.sbp, Systolic BP]
      - [vitals.hr, Heart rate]
      - [vitals.rr, Respiratory rate]
      - [vitals.spo2, SpO2 (room air)]
      - [meds.anticoagulant, Anticoagulants / bleeding disorder]
      - [symptom.onset, Time of injury]                   # or NEW trauma.injury_time
    triggers: [fall, mvc, crash, collision, gsw, gunshot, stab, assault, pedestrian, struck, ejected, rollover, burn, trauma]
    unknowns: [meds.anticoagulant, patient.pregnancy_weeks, allergies]
  sepsis:
    label: Sepsis pre-notification
    source: "Santa Clara 700-A04 §1.3-1.4 (eff. 2026-01-01)"
    items:
      - [infection.suspected, Suspected infection (source)]
      - [vitals.temp, Temperature]
      - [vitals.hr, Heart rate]
      - [vitals.rr, Respiratory rate]
      - [vitals.etco2, EtCO2]
      - [vitals.sbp, Systolic BP]
      - [vitals.consciousness, Mental status]
      - ["@sirs_sc", SIRS criteria (700-A04)]              # NEW county score file
    triggers: [fever, sepsis, septic, infection, pneumonia, uti, urosepsis, cellulitis]
    unknowns: [infection.suspected, allergies]
  stemi:
    label: STEMI alert
    source: "Santa Clara 700-A08 §1, §3.2, §6 (eff. 2025-01-01); 700-M09 §4.9; Policy 501 §IV; Policy 602 §VI.F"
    items:
      - [ecg.stemi_reading, Monitor reads STEMI]           # NEW key
      - [symptom.onset, Symptom onset]
      - [ecg.twelve_lead_time, First 12-lead time]
      - [ecg.transmitted, 12-lead transmitted]             # NEW key
      - [meds.given, Aspirin time]                         # engine needs a record-field matcher (drug == aspirin)
      - [vitals.sbp, Blood pressure]
      - [allergies, Allergies]
    triggers: [chest pain, stemi, 'mi ', heart attack, acs, st elevation, substernal, epigastric, palpitations, diaphoretic]
    unknowns: [symptom.onset, allergies]
```

Engine gaps these shapes expose (for the owner of `herald/checklists`):

- a checklist item that matches a **record field** (`meds.given` where drug is "aspirin") rather than key presence;
- the **per-county** override for non-stroke alerts (today only the stroke checklist is replaced by the county's; trauma and
  sepsis criteria are county-specific);
- the checklist's `source` string, shown in the UI and sent in the relay.

---

## 10. Keys: existing vs NEW

Existing and sufficient (in `config/vocabulary.yaml` as of 2026-09-24): `patient.age`, `patient.sex`,
`patient.pregnancy_weeks`, `complaint.chief`, `symptom.onset`, `vitals.sbp`, `vitals.hr`, `vitals.rr`, `vitals.spo2`,
`vitals.on_oxygen`, `vitals.temp` (°C), `vitals.etco2`, `vitals.gcs_total`, `vitals.gcs_motor`, `vitals.consciousness`,
`vitals.glucose`, `vitals.pain`, `meds.given`, `procedures.done`, `meds.anticoagulant`, `meds.list`, `allergies`,
`trauma.mechanism`, `trauma.injuries`, `infection.suspected`, `ecg.twelve_lead_time`, `ecg.attached`, `transport.destination`,
`transport.eta_min`.

**NEW keys proposed:**

| Key | Type | Why (county source) | Labeling rule sketch |
|---|---|---|---|
| `ecg.stemi_reading` | bool | the STEMI Alert trigger: 12-lead "states "STEMI" or "Acute MI Suspected"" (700-A08 §3.2; 700-M09 §4.9.1) | true when the medic says the monitor reads STEMI / acute MI suspected / "*** STEMI ***"; false only on an explicit "no STEMI on the 12-lead". A photo reading of the ECG starts unconfirmed (invariant 4). |
| `ecg.transmitted` | bool (or `time`) | "Transmit 12 Lead ECG to the selected STEMI Center" (700-A08 §3.2.2, §1.4; 700-M09 §4.9.1.1) | "12-lead sent / transmitted to Good Sam" → true. Future tense gives nothing. |
| `trauma.criteria` | list (accumulate), values are county criterion codes from the county config (e.g. `605.A` ... `605.X.7`), `require_tap: true` | Policy 501 §IV.E.2 requires stating the Policy 605 criteria; a deterministic Trauma Alert decision cannot read free-text `trauma.injuries` | The extractor maps what was said to a code from the county's list (for example "unstable pelvis" → `605.E`, "on a BiPAP / bagging him" → `605.L`). The codes and their text live in `config/counties/santa_clara.json`, so another county adds its own list without code changes (AGENTS rule 4). |

**Optional / decision needed:**

| Key | Type | Why | Recommendation |
|---|---|---|---|
| `trauma.injury_time` | time | 700-S06 §1.11 (fall more than 72 hours ago); 700-A16 §3.4.3 | Prefer **reusing `symptom.onset`** ("fell three days ago" is already a time or duration as spoken, LABELING_GUIDE §4) and label the trauma item "Time of injury". Add the new key only if the UI must show both a symptom onset and an injury time on one call. |
| `scene.patient_contact_time` | time | 700-A08 §1.1 "within 10 minutes of patient contact" | Use the incident start (scene clock) as a proxy for now, and say so in the UI. |
| `vitals.lactate` | float mmol/L | SSC 2026 (non-county, hospital measure) | **Do not add now.** Not in any county document or the Policy 302 inventory. |

---

## 11. Notes for indexing these documents (county config `documents`)

- **Effective-date parsing:** `config/knowledge.yaml` `effective_pattern` is `Effective:\s+([A-Z][a-z]+ \d{1,2}, \d{4})`.
  Policy 302 and Policy 410 print "Effective Date: 1/1/2026", which does not match. The superseded 700-A11 prints "January
  1,2025" (no space), which does not match either.
- **Heading styles:** the 700-series files use the `decimal` style ("1.3.1."). Policies 420, 430, 500 and 605 use `outline`.
  700-M17 opens with an unnumbered "Patient Eligibility" paragraph before "1.".
- **Image-only pages** (need `figures` entries like 700-A13 p. 3): 700-A08 p. 3 (treatment flowchart), 700-S06 p. 2 (fall
  flowchart), 700-M09 p. 2 ("STEMI Location Interpretation").
- **AO 2025-005:** add a second document entry `605` pointing at the same file with `"pages": [25, 27]` and
  `heading_style: outline`. Do not index pages 2-11 or 22-24 (tracked changes).
- **Table B:** add the trauma, burn, STEMI and pediatric rows to `destinations.audit.services` (§5.2) after checking AO
  2025-006/-007.
- **Superseded files in `previous/`** (700-A02, 700-A07, 700-A11, all effective 2025-01-01) are for reference and comparison.
  Do not index them as current. Replace them with the 2026 versions from §4.
- Facility-standards policies (410, 420, 430, 302) are rarely what a paramedic searches for. Index them after the 700-series
  and 501/602/605, or keep them as reference only.

---

## 12. Decisions for the team lead

1. **Download by hand** the documents in §4, above all 700-A07, 700-A11 and 700-A02 (effective 2026-01-01) and AO
   2025-006/-007 (Table B may have changed).
2. **`trauma.criteria` as enumerated county codes** (recommended) vs. leaving the Policy 605 decision to the medic's tap on
   free-text injuries. With codes, the Trauma Alert and its relay line ("Trauma Alert, Red 605-E suspected pelvic fracture")
   are deterministic and cited. Without them, Herald can only show the vitals-based part (`field_triage.yaml`).
3. **Sepsis wording and channel:** "Sepsis pre-notification (700-A04 §1.4)" as a standard hospital report, not a ringdown
   "Sepsis Alert" (inferred from Policy 501; please confirm).
4. **County vs national trauma rule:** in Santa Clara a Yellow hit is a Trauma Alert (602 §VI.C). Put the county rule in the
   county config and keep `field_triage.yaml` as the national published score shown for reference.
5. **STEMI "Anticoagulants" item:** keep it (non-county, for the cath lab) or move it to `unknowns`.
6. **Time of injury:** reuse `symptom.onset` (recommended) or add `trauma.injury_time`.

---

## 13. Sources

County documents (all retrieved 2026-09-24 via the Wayback Machine; full capture URLs and sha256 in
`data/protocols/santa_clara/archive/SOURCES.md`):

- Santa Clara County EMS Agency, Policy 605 Prehospital Trauma Triage and Policy 602 911 EMS Patient Destination, in AO
  2025-005, effective 2025-04-01:
  https://files.santaclaracounty.gov/exjcpb1541/2025-03/ao-2025-005.pdf?VersionId=hoI6kUYnjpaiCdXV5IMZfhAhGEPmUxmm
- 700-A04 Sepsis, eff. 2026-01-01: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a04.pdf?VersionId=llKIHwZNTKdIfmC1DHSq8pLdpZe1BOO.
- 700-A16 Trauma Care, eff. 2026-01-01: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a16.pdf?VersionId=NC2vIyxvUeJRvv4bFB6IRF00J0wJpbvm
- 700-S06 Falls, eff. 2026-01-01: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s06.pdf?VersionId=cK3AlZTopYqtricNMihHZVoThj.pS5Of
- 700-A10 Shock, eff. 2026-01-01: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-a10.pdf?VersionId=iOY4wLWFhhHadmcmR6HSNae_RqcSGX4z
- 700-A08 Chest Pain - Suspected Cardiac Ischemia, eff. 2025-01-01: https://files.santaclaracounty.gov/2024-09/700-a08.pdf?VersionId=zn1ExoHOzov2.K0pZI0GkN3P512olGXb
- 700-M09 12-Lead Electrocardiogram, eff. 2024-01-01: https://web.archive.org/web/20240224001437/https://emsagency.sccgov.org/sites/g/files/exjcpb266/files/bls/als-protocols-procedures/Policy_700-M09.pdf
- Policy 501 Hospital Radio Reports, eff. 2025-01-01: https://files.santaclaracounty.gov/exjcpb1541/2024-09/policy-501.pdf?VersionId=lPXZcOawuog6grDdame1RLjgdP7cNQgl
- Policy 430 STEMI Center Standards, eff. 2025-02-15: https://files.santaclaracounty.gov/exjcpb1541/2025-02/policy-430.pdf?VersionId=Tssdc8ndRnCLjIxTPS35C2zm1pNYdESY
- 700-S04 / 700-S05 Routine Medical Care, eff. 2026-01-01: https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s04.pdf?VersionId=dffCKzVxvjEXaRO4jYZ6IA8vxnFL1tJp ;
  https://files.santaclaracounty.gov/exjcpb1541/2025-09/700-s05.pdf?VersionId=QnKyUhbYGzzQB1AuMMHyxOUjMhumdolF
- 2026 cycle change memo (2025-09-19): https://files.santaclaracounty.gov/exjcpb1541/2025-09/ems-policy-protocol-changes-summary.pdf?VersionId=h_JWuvxZE2dSayMfWxH_BFuNNzhgAR0D
- 2025 cycle change memo (2024-09-24): https://files.santaclaracounty.gov/2024-09/changeoverview.pdf?VersionId=9qTm_.Z2KoP0dxoq.0pypFSDlTzG3eNr
- EMS Update 2025 page (list of documents effective 2026-01-01): https://web.archive.org/web/20260111090359/https://ems.santaclaracounty.gov/ems-update-2025
- Administrative Order list (through AO 2025-009): https://web.archive.org/web/20260109023426/https://ems.santaclaracounty.gov/news/1061
- 400-section renumbering notice (Policies 400-442, eff. 2025-02-15): https://web.archive.org/web/20250715004134/https://ems.santaclaracounty.gov/updates-400-section-ems-policy-manual

Non-county:

- Newgard CD, et al. National Guideline for the Field Triage of Injured Patients: Recommendations of the National Expert Panel
  on Field Triage, 2021. J Trauma Acute Care Surg 2022;93(2):e49-e60.
- Evans L, et al. Surviving Sepsis Campaign: International Guidelines for Management of Sepsis and Septic Shock 2021.
  https://link.springer.com/article/10.1007/s00134-021-06506-y
- Prescott H, Antonelli M, Alhazzani W, et al. Surviving Sepsis Campaign: International guidelines for management of sepsis
  and septic shock 2026. Crit Care Med 2026; doi 10.1097/CCM.0000000000007075.
  https://www.sccm.org/clinical-resources/guidelines/guidelines/surviving-sepsis-campaign-international-guidelines-for-management-of-sepsis-and-septic-shock-2026
- NASEMSO National Model EMS Clinical Guidelines 2022: https://nasemso.org/wp-content/uploads/National-Model-EMS-Clinical-Guidelines_2022.pdf
- NAEMSP position statements index (no sepsis statement found): https://naemsp.org/position-statements/
