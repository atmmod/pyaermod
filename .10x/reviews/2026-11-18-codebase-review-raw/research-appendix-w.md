# Appendix W research: which AERMOD options are regulatory (2017 vs 2024 revisions)

Researched 2026-11-19. Everything below was read from primary sources fetched in this session. Nothing is from memory.
Library state read at <repo>, commit 5f87a14 (branch claude/codebase-review-2026-11-18). Nothing in the repository was edited.

## Sources read

| Tag | What | URL | Revision / as-of |
|---|---|---|---|
| AW-CUR | eCFR current Appendix W, full text | https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-40?part=51&appendix=Appendix%20W%20to%20Part%2051 | Current text. The eCFR version list shows the latest substantive version is dated 2025-03-21, the delayed effective date of the 2024 rule. |
| AW-2017 | eCFR point-in-time Appendix W | https://www.ecfr.gov/api/versioner/v1/full/2018-01-01/title-40.xml?part=51&appendix=Appendix%20W%20to%20Part%2051 | 2018-01-01 snapshot, i.e. the 2017 revision as in force. Diffed against the 2024-11-01 snapshot: the only differences are dashes and one typo, so it is unchanged up to the 2024 rule. |
| AW-PRE | eCFR point-in-time Appendix W | https://www.ecfr.gov/api/versioner/v1/full/2017-01-01/title-40.xml?part=51&appendix=Appendix%20W%20to%20Part%2051 | 2017-01-01 snapshot, i.e. the pre-2017 Guideline (the 2005-era text) |
| AW-VER | eCFR version list | https://www.ecfr.gov/api/versioner/v1/versions/title-40.json?part=51&appendix=Appendix%20W%20to%20Part%2051 | Substantive versions dated 2017-01-17, 2024-11-29, 2025-01-28 and 2025-03-21, among others |
| FR-2017 | Final rule 82 FR 5182, published 2017-01-17 (FR Doc 2016-31747), preamble and rule | https://www.federalregister.gov/documents/full_text/text/2017/01/17/2016-31747.txt | Effective date 2017-02-16 per the FR API, delayed to 2017-03-21 (82 FR 8499) and then to 2017-05-22 (82 FR 14324) |
| FR-DELAY17 | 82 FR 8499 and 82 FR 14324 | https://www.federalregister.gov/documents/full_text/text/2017/01/26/2017-01822.txt , https://www.federalregister.gov/documents/full_text/text/2017/03/20/2017-05462.txt | Each table lists 82 FR 5182: the first moves 2/16/2017 to 3/21/2017, the second moves it to 5/22/2017 |
| FR-PROP23 | Proposed rule 88 FR 72826, published 2023-10-23 (FR Doc 2023-22876) | https://www.federalregister.gov/documents/full_text/text/2023/10/23/2023-22876.txt | Proposal. Downloaded but only its existence and citation were used. |
| FR-2024 | Final rule 89 FR 95034, published 2024-11-29 (FR Doc 2024-27636), "Guideline on Air Quality Models; Enhancements to the AERMOD Dispersion Modeling System" | https://www.federalregister.gov/documents/full_text/text/2024/11/29/2024-27636.txt | The rule's DATES line says effective 2025-01-28 |
| FR-DELAY25 | 90 FR 8254, published 2025-01-28 (FR Doc 2025-01866) | https://www.federalregister.gov/documents/full_text/text/2025/01/28/2025-01866.txt | Its table lists 89 FR 95034 with a new effective date of 3/21/2025. I found no further delay; eCFR shows the 2024 text as current. |
| UG26 | AERMOD User's Guide EPA-454/B-26-001, July 2026 (v26135) | https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_userguide.pdf | Latest on SCRAM |
| AIG26 | AERMOD Implementation Guide EPA-454/B-26-002, July 2026 | https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_implementation_guide.pdf | Latest on SCRAM |
| MCB | AERMOD Model Change Bulletins 1 to 19 | https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_mcbs.zip | MCB12 v16216, MCB13 v18081, MCB15 v21112, MCB16 v22112, MCB17 v23132, MCB18 v24142 (2024-05-21), MCB19 v26135 |
| MEMO26 | v26135 release memo, 2026-07-09 | https://gaftp.epa.gov/air/aqmg/scram/models/preferred/aermod/AERMOD_26135_transmittal_memo.pdf | |
| NO2-2010 / SO2-2010 | Clarification memos of 2010-06-28 (NO2) and 2010-08-23 (SO2) | https://gaftp.epa.gov/Air/aqmg/SCRAM/mchisrs/ClarificationMemo_AppendixW_Hourly-NO2-NAAQS_FINAL_06-28-2010.pdf , https://gaftp.epa.gov/Air/aqmg/SCRAM/mchisrs/ClarificationMemo_AppendixW_Hourly-SO2-NAAQS_FINAL_08-23-2010.pdf | Written against the pre-2017 Appendix W section numbers |
| PM-2022 | Guidance for Ozone and Fine Particulate Matter Permit Modeling, EPA-454/R-22-005, July 2022 | https://www.epa.gov/system/files/documents/2022-07/Guidance_for_O3_PM25_Permit_Modeling.pdf | The SCRAM page also links an April 30, 2024 clarification memo, which I did not read |

---

## A5. NO2 tiers (Appendix W §4.2.3.4)

### Text read
- 2017 revision: AW-2017 §4.2.3.4(b)–(f). Supporting text: FR-2017 preamble §IV.A.2 (NO2 discussion, around FR p. 5189) and MCB12 (v16216).
- Current (2024) revision: AW-CUR §4.2.3.4(b)–(f) and FR-2024 preamble §III.A.1.b and §III.B. Status in the model: UG26 §3.2.5 (around p. 3-32) and the MODELOPT table (p. 3-4).

### What it says
- **Both revisions, ¶(b):** there are three tiers. Tier 1 is "full" conversion. Tier 2 assumes ambient equilibrium between NO and NO2. Tier 3 is a set of detailed screening techniques that use ambient ozone and the in-stack NO2/NOx ratio. All three tiers are screening techniques, so their use must be agreed with the appropriate reviewing authority. Negative emission rates need consultation with the EPA Regional Office.
- **¶(c), Tier 1:** model NOx with a refined model and assume total conversion of NO to NO2. In pyaermod this is a run with no chemistry option.
- **¶(d), Tier 2:** multiply the Tier 1 result by ARM2. The national default bounds are a minimum ratio of 0.5 and a maximum of 0.9. The reviewing agency may set a lower minimum based on in-stack ratios. **The text is the same in 2017 and in the current revision: ARM2 is the Tier 2 method in both.** FR-2017 states that ARM2 replaced the old ARM as Tier 2, and MCB12 records that v16216 dropped the BETA requirement for PVMRM, OLM and ARM2. UG26 calls ARM2 a "regulatory option, can be used with DFAULT keyword".
- **¶(e), Tier 3:** applied case by case. Tier 3 use "shall occur in consultation with the EPA Regional Office in addition to the appropriate reviewing authority". That is consultation, not alternative-model approval; alternative techniques come under ¶(f) and need Regional Office approval under §3.2.
  - In 2017, OLM and PVMRM are the two Tier 3 techniques. FR-2017 also says the method named "PVMRM2" in v15181 became the regulatory "PVMRM", and the old PVMRM code was removed.
  - In the current revision, ¶(e) names OLM, PVMRM and GRSM as three detailed screening techniques "that may be used for most sources" (the eCFR text misspells GRSM as "Generic Set Reaction Method"). GRSM also needs hourly ambient NOx in addition to hourly ozone. FR-2024 §III.B says ¶(e) was revised "to adopt the Generic Reaction Set Method (GRSM) as a regulatory Tier 3 detailed screening technique".
  - **TTRM and TTRM2 are not named in either revision.** UG26 lists them as non-regulatory ALPHA options that need the ALPHA keyword and cannot be used with DFAULT.
- **Model status (UG26 §3.2.5):** ARM2 is the regulatory Tier 2 option and PVMRM, OLM and GRSM are regulatory Tier 3 options, "therefore, any one of the four options can be used with the DFAULT keyword."

### What the code and docs say now
- `src/pyaermod/regulatory.py:196`: the 2017 profile has `allow_chemistry_methods=("OLM", "PVMRM")`. ARM2 is not in the list, so a Tier 2 ARM2 run is flagged.
- `regulatory.py:220`: the "2023" profile has `("OLM", "PVMRM")`. ARM2 and GRSM are both flagged.
- `regulatory.py:80`: the dataclass default is `("OLM", "PVMRM", "GRSM")`, with no ARM2. `regulatory.py:248`: SCREENING_PROFILE also has OLM, PVMRM and GRSM but no ARM2.
- `regulatory.py:189-191` (2017 description) says "the only DFAULT-compatible NO2 chemistry methods are OLM and PVMRM". ARM2 was also DFAULT-compatible from v16216 (MCB12).
- `regulatory.py:198-200` and `:210`, and `docs/regulatory-matrix.md:15, :29-36`, list "PVMRM2" as a BETA method.
- `src/pyaermod/chemistry_presets.py:91-95` (`arm2_preset` docstring) says ARM2 is "Not accepted by Appendix W for new submittals." `chemistry_presets.py:143` (`suggest_chemistry_for`) says ARM2 is a "fallback; not Appendix-W-compliant".
- `chemistry_presets.py:112-113` says GRSM is "Preferred over OLM/PVMRM in Appendix W 2023 where documented."
- `chemistry_presets.py:8` lists PVMRM2 among the presets.
- `docs/use-cases.md:206` says Tier 2 is ARM2 and Tier 3 is OLM or PVMRM.

### Match or mismatch
- **MISMATCH:** neither profile accepts ARM2, but ARM2 is the regulatory Tier 2 method in both revisions and AERMOD accepts it with DFAULT.
- **MISMATCH:** the chemistry_presets ARM2 docstrings are wrong for both revisions.
- **MISMATCH:** PVMRM2 has not existed as a separate option since v16216. It was folded into PVMRM in the 2017 rule, and the keyword is absent from UG26 and from the local v24142 Fortran (`grep PVMRM2 aermod/*.f` returns nothing). Calling it BETA in v23132/v24142 is wrong.
- **MISMATCH (current revision):** GRSM is regulatory Tier 3 under the 2024 rule, but the "2023" profile flags it.
- **MISMATCH:** "Preferred over OLM/PVMRM in Appendix W 2023" has no basis. Appendix W has no 2023 revision and expresses no preference among the Tier 3 methods. The FR-2024 preamble says EPA plans future NO2 guidance on how to choose between them.
- **MATCH:** `use-cases.md:206` matches the 2017 revision. It is incomplete for the current revision because GRSM is missing.

### What would have to change
- 2017 profile: accept ARM2, OLM and PVMRM without flagging. Tier 1 (no chemistry) is already unflagged. Flag GRSM, TTRM and TTRM2. GRSM did not exist in 2017; see A9.
- Current profile: accept ARM2, OLM, PVMRM and GRSM. Flag TTRM and TTRM2 (ALPHA).
- Both profiles can add an advisory note: Tier 2 and Tier 3 are screening techniques used in agreement with the reviewing authority, and Tier 3 also needs consultation with the EPA Regional Office (¶(e)). That consultation is not alternative-model approval.
- Remove PVMRM2 from `EPA_APPENDIX_W_2023_BETA_METHODS`, the notes, the docs and the `chemistry_presets.py:8` docstring.
- Fix the ARM2 docstrings and the GRSM "preferred" claim in chemistry_presets.py.

---

## A6. GRSM: history and status

### Text read
MCB15 (v21112, 2021-04-22), MCB16 (v22112), MCB17 (v23132), MCB18 (v24142, 2024-05-21), UG26 §3.2.2.7 and §3.2.5, AIG26 (around p. 30), AW-CUR §4.2.3.4(e), and FR-2024 §II.C, §III.A.1.b and §IV.

### What it says
- GRSM first appeared in **v21112 (April 2021)**. MCB15 lists it under "Formulation updates – ALPHA", with TTRM.
- **v22112** moved it from ALPHA to BETA. MCB16 lists this under "Formulation updates – BETA".
- **v23132** carried the GRSM reformulation as a "Proposed Regulatory Update", referring to the 2023 GRSM TSD (EPA-454/R-23-009).
- **v24142 (May 2024)**: MCB18 says "Remove BETA flag restriction for GRSM", with GRSM promulgated as a regulatory option in the 2024 update to the Guideline.
- UG26 says GRSM was added as an ALPHA option in 21112, became BETA in 22112, and was "promulgated as a regulatory option in version 24142". It can be used with DFAULT.
- FR-2024 finalizes "GRSM as a regulatory non-default, detailed Tier 3 NO2 screening option in AERMOD version 24142". The same preamble (§II.C, §IV) says every v23132 BETA option was promulgated and "no additional beta options remain within AERMOD". AW-CUR §4.2.3.4(e) names GRSM as a Tier 3 technique.
- In EPA's wording, "non-default" here means GRSM is an option the user selects, not the default behaviour, and its use is subject to the Tier 3 consultation in ¶(e). It does not mean GRSM conflicts with the DFAULT keyword: UG26 says it can be used with DFAULT. EPA describes COARE in AERMET with the same phrase, "non-default regulatory option".
- MEMO26 and MCB19 (v26135) only fix GRSM bugs. They make no status change.

### What the code and docs say now
- `regulatory.py:191` says "GRSM was still BETA in 2017".
- `regulatory.py:210, :222-225`: PVMRM2 and GRSM are BETA in v23132/v24142, and "v26135 drops the BETA flag for GRSM but it remains a non-DFAULT option".
- `regulatory.py:231-235`: `EPA_APPENDIX_W_2023_BETA_METHODS = ("PVMRM2", "GRSM")`.
- `docs/regulatory-matrix.md:15` says GRSM remains BETA through 2023. `regulatory-matrix.md:30-32` says it is BETA in v23132/v24142 and that "v26135 removes the BETA flag".

### Match or mismatch
- **MATCH:** "GRSM was BETA in v23132" is correct.
- **MISMATCH:** GRSM was not BETA in v24142. The BETA flag was removed in **v24142**, not v26135.
- **MISMATCH:** "remains a non-DFAULT option" is wrong for the AERMOD keyword. UG26 says GRSM can be used with DFAULT.
- **MISMATCH:** the current Appendix W does name GRSM as a regulatory Tier 3 option.
- **MISMATCH:** the claim about GRSM in 2017 is false; see A9.

### What would have to change
- In a current-rule profile, GRSM should be allowed. If a note is wanted, it is the Tier 3 consultation note that also applies to OLM and PVMRM.
- Correct the notes and docs: GRSM was ALPHA in 21112, BETA in 22112 and 23132, and regulatory from v24142 under 89 FR 95034.
- A profile meant to describe 2023 (the 2017 rule plus v23132) may still flag GRSM, but the reason is that it was BETA in v23132.

---

## A7. Design-value ranks and length of the meteorological record

### Text read
- AW-2017 and AW-CUR §8.4.2(e) (length of record), §9.1(d), §9.2.2(a)–(c) (design concentration) and §8.3.1(a).
- AW-PRE §7.2.1.1(b)–(c) (the pre-2017 text).
- UG26 §3.2.16.2 (PM-10) and §3.2.17 (1-hour NO2 and SO2).
- NO2-2010, SO2-2010 and PM-2022 §IV (pp. 51-52).

### What it says
- **Length of record, §8.4.2(e), both revisions:** "5 years of adequately representative NWS or comparable meteorological data, at least 1 year of site-specific, or at least 3 years of prognostic meteorological data, are required." If 1 to 5 years of site-specific data are available, they are preferred. Consecutive years are preferred. The current text adds "(either land-based or overwater based)" after site-specific. §9.1(d) adds that the 3-year averaging period of ambient monitoring design values does not set the length of record for modelling.
- **Ranks in the 2017 and current Appendix W:** neither revision contains a "sixth-highest" rule for PM10, nor a high-second-high rule for one year of NAAQS data.
  - §9.2.2(a)(i): the NAAQS design concentration is background (§8.3) combined with the modelled impact.
  - §9.2.2(b): the form of the NAAQS governs how background and modelled values are combined. It defers the details to "the applicable modeling guidance available on the EPA's SCRAM website", and says modelled values should not be rounded.
  - §9.2.2(c), PSD increments only: the highest, second-highest increase for short-term averages must not exceed the increment, and annual averages must not exceed it either.
- **Pre-2017 Appendix W (AW-PRE §7.2.1.1(b)):** this is where the PM10 rule lived. With 5 years of NWS data, the highest sixth-highest concentration over the whole period is the design value. In general, with n years modelled, the (n+1)th highest over the period is the design value. Otherwise the highest-second-high per year applies. §7.2.1.1(c): with less than 5 years of NWS data or less than a full year of site-specific data, use the highest value. This text was replaced in 2017.
- **Current EPA statement of the PM10 rank (UG26 §3.2.16.2):** PM-10 compliance modelling uses the High-N+1-High over N years, which is the H6H for five years of NWS data. That gives H2H for one year and H4H for three years.
- **1-hour NO2:** NO2-2010 says the modelled contribution follows the form of the standard, the 98th percentile of daily-maximum 1-hour values averaged across the years modelled. The 5-year average, or the average over the site-specific years, is an unbiased estimate of the 3-year average. Rolling 3-year averages are not required, and complete years should be used. UG26 §3.2.17: the 98th percentile is the 8th-highest daily maximum.
- **1-hour SO2:** SO2-2010 says the same with the 99th percentile, which is the 4th-highest daily maximum (UG26 §3.2.17). Its "first tier" for background is to add the overall highest hourly background.
- **PM2.5 (PM-2022 §IV, pp. 51-52):** add the modelled design concentration to the monitor-based design value.
  - 5 years of NWS data: the 5-year average of the annual 98th-percentile 24-hour values, or the 5-year average of the annual means.
  - 1 year of site-specific data: the 98th-percentile value, or the annual mean.
  - 2 to 5 years of site-specific data: the multi-year average.
  - 3 years of prognostic data: the 3-year average.
- **Other record lengths:** Appendix W gives no rank rule for lengths other than 1 and 5 years. The memoranda handle 1 to 5 years by averaging the annual percentile across the years modelled. For PM10, the N+1 rule applies (UG26).

### What the code and docs say now
- `docs/use-cases.md:175`: "For PM10, the NAAQS compares the H6H over five years, or the H2H for one year".
- `use-cases.md:218`: NO2 design value is the H8H averaged over 5 years, plus background.
- `use-cases.md:230`: SO2 design value is the 99th percentile (4th-highest daily maximum) averaged over the years modelled.

### Match or mismatch
- **MATCH in substance:** the ranks in use-cases.md agree with UG26 and the memoranda.
- **Attribution caveat:** the PM10 H6H/H2H rule is not in the 2017 or current Appendix W. It comes from the pre-2017 Guideline §7.2.1.1(b), carried forward in UG26 §3.2.16.2. Any code or doc that cites "Appendix W" for H6H should cite UG26 §3.2.16.2 or the PM10 form in 40 CFR 50 instead. I did not read 40 CFR 50 Appendix K in this session.
- A checker that hard-codes "5 years NWS / ≥1 year site-specific / ≥3 years prognostic" matches §8.4.2(e) in both revisions.

### What would have to change
Nothing is wrong in substance. Optionally cite UG26 §3.2.16.2 for H6H, and §9.2.2(b) plus the memoranda for the NO2, SO2 and PM2.5 forms. For record lengths other than 1 or 5 years, apply N+1 for PM10 and the multi-year average of the annual percentile for NO2, SO2 and PM2.5.

---

## A9. The 2017 profile notes (LOWWIND3, ADJ_U*, GRSM) and what the 2024 rule changed

### Text read
- FR-2017 preamble §IV.A.2: the ADJ_U* and LOWWIND3 discussion (around FR pp. 5186-5188).
- AW-2017 Appendix A to Appendix W, §A.1(b)(2)(ii). This addendum is retitled "Addendum A" in AW-CUR and the same text is there.
- MCB8, MCB11 (v15181), MCB12 (v16216), MCB13 (v18081) and MCB15.
- UG26 §3.2.3.
- FR-2024 §II.C, §III.A.1 and §IV.

### What it says
- **ADJ_U\* (2017):** EPA adopted the proposed ADJ_U* option "in AERMET as a regulatory option" (FR-2017). It applies to NWS airport data, site-specific data without turbulence parameters, and prognostic data. It should not be used with measured turbulence data (sigma-theta or sigma-w). The appendix codifies this in A.1(b)(2)(ii): with site-specific data that include turbulence, ADJ_U* requires approval as an alternative model under §3.2. The text is unchanged in AW-CUR. UG26 §3.2.3 agrees: ADJ_U* was BETA from v12345 and regulatory from v16216. MCB12 records that AERMOD checks the PROFFILE for turbulence data to decide whether an ADJ_U* run is "regulatory" or non-DFAULT.
- **LOWWIND3 (2017):** proposed, then **not adopted**. FR-2017 says EPA is "not incorporating LOWWIND3 as a regulatory option in AERMOD at this time" and defers action on the LOWWIND options in general. LOWWIND3 was a non-DFAULT BETA option added in v15181 (MCB11). LOWWIND1 and LOWWIND2 were BETA options from v12345 (MCB8).
- **GRSM in 2017:** it did not exist. FR-2017 never mentions GRSM. The 2017 rule cites v16216, and the MCBs show GRSM first in v21112 (2021) as ALPHA.
- **2024 rule (FR-2024 §III.A.1):** three updates became regulatory in v24142, all previously v23132 BETA options:
  - COARE in AERMET, a "non-default regulatory option" for overwater use that needs consultation;
  - GRSM, regulatory non-default Tier 3;
  - RLINE, a new regulatory source type, with no BETA flag needed even with urban or terrain.
  - RLINEXT stays ALPHA.
  - On low wind, FR-2024 §IV says the original LOW_WIND BETA options (LOWWIND1/2/3) "are no longer implemented in AERMOD". LOW_WIND was recategorized as ALPHA in v18181 (MCB13 and UG26 give 18081). **No low-wind default changed.**
  - The rule also updated the §8.3 background recommendations.

### What the code and docs say now
- `regulatory.py:188-191` (2017 description): "permits LOWWIND3 and ADJ_U* only for documented cases … GRSM was still BETA in 2017."
- `regulatory.py:195` and `:216`: both profiles have `allowed_low_wind=("LOWWIND3",)`.
- `regulatory.py:198-200` (2017 notes): "Use of BETA options (GRSM, PVMRM2, ADJ_U*) requires agency concurrence and is not permitted under DFAULT."
- `regulatory.py:65-66`: "Appendix W (2017) allows LOWWIND3 for specific documented cases."
- `regulatory.py:18-19`: cites "subsequent EPA memoranda on LOWWIND3 and ADJ_U*". I found no such memoranda; not verified either way.
- `docs/regulatory-matrix.md:14`: "only `LOWWIND3` is currently accepted with documentation".
- `regulatory-matrix.md:38-41`: lists ADJ_U* as a "2023 update", permitted with agency review.

### Match or mismatch
- (a) **MISMATCH:** LOWWIND3 was never permitted. The 2017 rule declined to adopt it; it was a BETA option that cannot run with DFAULT and was removed in v18081.
- **MISMATCH:** ADJ_U* is not BETA and does not need concurrence in general. It has been a regulatory AERMET option since 2017 (v16216), and needs §3.2 alternative-model approval only when the site-specific data include measured turbulence.
- **MISMATCH:** the ADJ_U* item in regulatory-matrix.md is misdated: it is a 2017 change, not a 2023 one.
- (b) **MISMATCH:** "GRSM was still BETA in 2017" is false; GRSM did not exist until v21112.
- **MISMATCH:** "PVMRM2 BETA" in 2017 is false. The 2017 rule made the PVMRM2 method the regulatory PVMRM.

### What would have to change
- 2017 profile:
  - `allowed_low_wind=()`;
  - drop the LOWWIND3 and ADJ_U* "documented cases" wording;
  - note that ADJ_U* is regulatory except with site-specific turbulence data (A.1(b)(2)(ii));
  - say GRSM did not exist (it was added as ALPHA in v21112);
  - drop PVMRM2.
- Current profile: `allowed_low_wind=()`. Mention RLINE and COARE as regulatory from v24142, and RLINEXT, LOW_WIND, TTRM and TTRM2 as ALPHA.

---

## A10. Low wind under the current rule and current AERMOD

### Text read
- AW-CUR: searched the whole text for low-wind options.
- FR-2024 §IV ("Low Wind Default Overrides").
- UG26 §3.2.3 (pp. 3-22 to 3-24), the MODELOPT ALPHA entry (p. 3-3) and the keyword index.
- MCB13 (v18081) items 4 and 5, MCB15 item 4 and MCB16 ALPHA item 6.
- Local v24142 source: `aermod/coset.f`, where LOW_WIND without ALPHA is an error.

### What it says
- **Appendix W:** no LOW_WIND or LOWWIND option appears anywhere in the current text. The only low-wind regulatory item is ADJ_U* in AERMET.
- **FR-2024 §IV:** LOW_WIND is an ALPHA option.
- **UG26 §3.2.3:** LOW_WIND is an ALPHA option, present since 18081 and updated in 21112 and 22112. It needs `MODELOPT ALPHA`, and ALPHA "cannot be used with DFAULT keyword". The local coset.f requires ALPHA for LOW_WIND.
  - Syntax: `CO LOW_WIND SVmin [WSmin [FRANmax [SWmin [BigT [FRANmin [PBAL]]]]]]`, optional and non-repeatable. The parameters and ranges are:

    | Parameter | Meaning | Range | Default |
    |---|---|---|---|
    | SVmin | minimum sigma-v | 0.01–1.0 m/s | 0.2 |
    | WSmin | minimum wind speed | 0.01–1.0 m/s | 0.2828 |
    | FRANmax | maximum meander factor | 0.0–1.0 | 1.0 |
    | SWmin | minimum sigma-w | 0.0–3.0 m/s | 0.02 |
    | BigT | time scale for TRAN | 0.5–48 h | 24 |
    | FRANmin | minimum meander factor | 0.0–1.0, ≤ FRANmax | 0.0 |
    | PBAL | momentum-balance meander, a flag | | |

  - The guide says LOWWIND1, LOWWIND2 and LOWWIND3 "have since been removed from AERMOD".
- **Removal of LOWWIND1/2/3:** MCB13 is the bulletin for **AERMOD v18081**. Item 4 says "Individual BETA options LOWWIND1, LOWWIND2, LOWWIND3 were removed and replaced with LOW_WIND ALPHA option". FR-2024 §IV says "18181" for the ALPHA recategorization; that looks like a typo for 18081, since no 18181 release appears in the MCB list.
- **Answer:** under the current rule and current AERMOD (v26135), **no LOW_WIND or LOWWIND option can be used in a regulatory DFAULT run.**

### What the code and docs say now
- `regulatory.py:79, :195, :216`: `allowed_low_wind=("LOWWIND3",)`. Only SCREENING_PROFILE (`:247`) has `()`.
- `regulatory.py:84-85` and `src/pyaermod/validator_advanced.py:258-260`: forbid `use_lowwind1/2/3`.
- `src/pyaermod/pathways.py:677` (comment: e.g. "LOWWIND3") and `pathways.py:930-931`: write `LOW_WIND  {low_wind_option}`.

### Match or mismatch
- **MISMATCH:** allowing LOWWIND3 is wrong under every revision and for every AERMOD version from v18081 on.
- **Side finding:** `pathways.py:930-931` would write `CO LOW_WIND LOWWIND3`, which is not valid LOW_WIND syntax (it takes numeric SVmin...). It would also need MODELOPT ALPHA.

### What would have to change
- Set `allowed_low_wind=()` in both EPA profiles, and in the dataclass default if that default is meant to be regulatory.
- Treat any `low_wind_option` as ALPHA, which is incompatible with DFAULT.
- Optionally model LOW_WIND as numeric parameters, which is out of scope here.

---

## Naming: is there a "2023" revision?

### Facts
- **No 2023 revision of Appendix W exists.** The revisions in force have been the 2017 rule (82 FR 5182, effective 2017-05-22 after two delays) and the 2024 rule.
- 2023 events:
  - the **proposal**, 88 FR 72826, published 2023-10-23;
  - **AERMOD v23132**, the model version that carried GRSM, RLINE and COARE as BETA "proposed regulatory updates" (MCB17).
- The final rule is **89 FR 95034, published 2024-11-29.** The rule states an effective date of 2025-01-28. 90 FR 8254 delayed it to **2025-03-21**. The eCFR's latest version is dated 2025-03-21 and contains the 2024 text, with GRSM in §4.2.3.4(e).
- The profile `EPA-AppendixW-2023` describes itself as "as-of 2023". The Appendix W in force in 2023 was the 2017 text. As a snapshot of the 2017 rule plus v23132, GRSM-as-BETA is right. PVMRM2 and LOWWIND3 are wrong for that snapshot too.
- The name is factually wrong if it is read as an Appendix W revision. It is defensible only as a label for "the state in 2023". It does not represent the currently effective Appendix W, which is the 2024 rule, effective 2025-03-21.
- The module docstring (`regulatory.py:11-12`) refers to `EPAReg2024Profile`, which does not exist in the module (`__all__` at `:269-276`).

---

## Background concentrations (§8.3, §9.2.2): supports "modelled value excludes background"

### Text read
AW-2017 §8.3.1(a) and §9.2.2(a)(i), and AW-CUR §8.3.1(a) and §9.2.2(a)(i).

### What it says
Both revisions say background concentrations are "essential in constructing the design concentration, or total air quality concentration" in a cumulative impact analysis (§8.3.1(a)). They also say the background should not include the project source's own impacts. Under §9.2.2(a)(i), the NAAQS design concentration combines the appropriate background (§8.3) with the modelled impact of the source, and that combined value is what is compared with the NAAQS.

### Match
- A GUI note saying a modelled value "excludes background" and must be combined with background before NAAQS comparison is supported, in both revisions.
- The 2024 rule also added a reference to EPA's Draft Guidance on Developing Background Concentrations in §8.3.1(a).
- AERMOD's own BACKGRND keyword can add background inside the run. A modelled value excludes background only when no SO BACKGRND is included in the source group.
