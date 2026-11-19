# NAAQS rule text vs pyaermod design-value code (research, 2026-11-19)

## Sources read

All rule text was read from the eCFR versioner API (raw XML, converted to plain text locally; nothing summarised by a third party):

- Part 50 sections and appendices, point-in-time 2026-11-16:
  `https://www.ecfr.gov/api/versioner/v1/full/2026-11-16/title-40.xml?part=50&section=<50.x>`,
  `...?part=50&appendix=Appendix%20<X>%20to%20Part%2050`, and the whole of Part 50, `...?part=50`.
- The eCFR titles endpoint (`/api/versioner/v1/titles.json`) reports Title 40 as "up to date as of 2026-11-17", latest amended/issue date 2026-11-16. That is the as-of date for every citation below.
- Appendix W to Part 51 (Guideline on Air Quality Models), same point in time: `...?part=51&appendix=Appendix%20W%20to%20Part%2051`. Its source note is 89 FR 95043, Nov. 29, 2024.
- The renderer endpoint (`/api/renderer/v1/content/enhanced/current/...`) returned 302 redirects. The versioner XML was used instead. It is the same eCFR text.

Equations in Appendices K and N are images in the XML, so they are not in the text. The prose around each equation states what it computes, and the answers below rely only on that prose.

Code read (read-only): the main checkout at `<repo>`. `git diff main` is empty for all three files.
- `src/pyaermod/naaqs.py`
- `src/pyaermod/design_values.py`
- `docs/design-value-validation.md`

The code does no rounding or truncation anywhere: grep finds no `round(` or `floor` in either module. It also has no quarterly logic for PM2.5 or PM10.

---

## A1. Rounding / truncation of the design value before comparison with the level

### Rule text read
50.8(d); App. K 1.0(b)–(c), 2.1(b), 3.1(b),(d); App. N 3.0(b)–(c), 4.3, 4.4(d), 4.5(c); App. R 3(b), 5; App. S 2(c), 4.1, 4.2; App. T 2(c), 4.1, 4.2; App. U 3(a),(b),(e). All at the URLs above, as of 2026-11-17. Also Appendix W to Part 51, 9.2.2(b).

### What it says (per standard)

| Standard | Rule on the final value | Intermediate values | Cite |
|---|---|---|---|
| PM2.5 annual | DV rounded to nearest **0.1 µg/m³**, x.x5 rounds up | Intermediate calculations not rounded. Reported data truncated to 1 decimal µg/m³. AQS 24-h averages truncated to 1 decimal | N 4.3(a), 4.4(d); 3.0(b),(c) |
| PM2.5 24-hour | DV rounded to nearest **1 µg/m³**, 0.5 rounds up | Same as above | N 4.3(b), 4.5(c) |
| PM10 24-hour | No concentration DV. A daily value is an exceedance if it is above 150 **after rounding to nearest 10 µg/m³** (values ending in 5 round up). Quarterly estimated exceedances rounded to 0.01. Annual estimate and the 3-year expected exceedances rounded to **0.1** (≥0.05 up) and compared with 1 | — | K 1.0(b) "Exceedance"; 2.1(b); 3.1(b),(d) |
| NO2 annual | DV rounded to nearest **1 ppb** (0.5 up) | Hourly data reported in ppb, truncated to 1 decimal | S 4.1(a),(b) |
| NO2 1-hour | DV (3-yr mean) rounded to nearest **1 ppb** | Daily maxima not rounded | S 4.2(b),(c) |
| SO2 1-hour | DV rounded to nearest **1 ppb** | Daily maxima and the annual 99th percentile not rounded. Hourly data truncated to 0.1 ppb | T 4.1(a)–(c) |
| O3 8-hour | DV **truncated** to 3 decimals in **ppm** (equal to whole ppb) | Hourly data and 8-h averages also truncated to 3 decimals ppm | U 3(a),(b),(e) |
| CO | Averages stated to 1 decimal. Comparison in **ppm as integers**, ≥0.5 rounds up | — | 50.8(d) |
| Pb | 3-month means rounded to nearest **0.01 µg/m³** (0.xx5 up). The DV is the highest 3-month mean, with no further rounding | Monthly means not rounded. Daily data truncated to 3 decimals | R 5(a)–(c); R 3(b) |

**Monitoring-only scope.** Appendices N, S, T, U and R are written for monitor data only. They speak of "monitoring site" and AQS reporting, and none of them mentions modelled data.
- Appendix K is the exception. K 1.0(c) says the monitoring discussion applies to modelling data as well, "subject to EPA modeling guidelines". K 3.1(e) also mentions "monitoring or modeling data".
- 50.8(d) (CO) does not restrict itself to either.
- 50.1(l) defines an exceedance as a "measured or modeled concentration" above the level.
- For modelling, Appendix W 9.2.2(b) is explicit: modelled concentrations "should not be rounded" before the design concentration is compared to the NAAQS or PSD increments.

### What the code and docs say now
- `design_values.py:1187` sets `exceeds = design_value > std.level_ugm3` on the unrounded value. Nothing in `design_values.py` or `naaqs.py` rounds or truncates.
- `docs/design-value-validation.md` says nothing about rounding.

### Match or mismatch
- **For modelled data:** no rounding matches Appendix W 9.2.2(b). The comparison is also correct: each standard is met when the value is at or below the level (N 4.1/4.2 via 50.20(b),(c); S 3.1(a), 3.2(a); T 3.1(a); U 4(a)), so "exceeds" means "greater than".
- **For monitor-style output:** the appendix conventions above are not applied.
- **PM10 gap:** K's definition of an exceedance rounds each daily value to the nearest 10 µg/m³. Under K, a modelled 152 µg/m³ is not an exceedance. Under the code it is above 150. K 1.0(c) applies K to modelling only "subject to EPA modeling guidelines", and Appendix W says not to round, so the two texts point different ways. The maintainer needs to decide.

### What would have to change
- **Nothing is required for modelled design values.** At most, document that modelled values are deliberately unrounded, citing App. W 9.2.2(b).
- **Optional:** an opt-in "monitoring convention" rounding per the table above. This would change computed numbers only for users who opt in.
- **PM10:** a decision on the 155 vs 150 threshold. Adopting K's rounding would change the exceedance flag for daily values in [150, 155).

---

## A2. Which section holds the current PM2.5 standards

### Rule text read
50.20 (source note: 89 FR 16380, Mar. 6, 2024); 50.18 (78 FR 3277, 2013); 50.13 (2006); 50.7 (1997); Appendix N 1.0(a), 4.1(a), 4.2(a). As of 2026-11-17.

### What it says
- **50.20(a)** sets the primary standards at 9.0 µg/m³ annual arithmetic mean and 35 µg/m³ 24-hour.
- **50.20(b):** the annual standard is met when the Appendix N annual mean is at or below 9.0.
- **50.20(c):** the 24-hour standard is met when the 98th percentile is at or below 35.
- **50.18** is still codified with 12.0 annual and 35 24-hour (2013).
- **50.13** holds the 2006 primary and secondary standards (15.0 annual, 35 24-hour). It is the current *secondary* source.
- Appendix N 4.1(a)/4.2(a) say the levels are "specified in §§ 50.7, 50.13, 50.18, and 50.20 as applicable".
- The 2024 rule begins at 89 FR 16202. The eCFR source note for the 50.20 text cites page 16380, and Appendix N's amendment is at 16381.

### What the code and docs say now
- `naaqs.py:83-84` gives `level 9.0`, `"40 CFR 50.18"`. This is wrong: 50.18 says 12.0.
- `naaqs.py:85-86` cites the 24-hour standard as `"40 CFR 50.18"`. The level is right, but the section is superseded.
- `design_values.py:428` ("PM2.5 annual NAAQS (40 CFR 50.18)") and `:1096` ("(40 CFR 50.18, Appendix N)") repeat the same citation.
- `naaqs.py:77-79`: the comment "PM2.5 24-hr was 35 µg/m³ before 2024" is misleading. It is still 35 µg/m³.

### Match or mismatch
Mismatch in the citation only.

### What would have to change
- Annual label: `"40 CFR 50.20(b); App. N"`. The level 9.0 is in 50.20(a).
- 24-hour label: `"40 CFR 50.20(c); App. N"` for the primary standard. The 35 µg/m³ secondary is in 50.13(c).
- Fix the docstrings at `design_values.py:428,1096` and the comment at `naaqs.py:77`.
- No computed number changes.

---

## A3. PM2.5 annual mean and 24-hour 98th percentile under Appendix N

### Rule text read
App. N 1.0(c) definitions ("Annual mean", "Creditable samples", "Design values", "98th percentile", "Quarterly data capture rate"); 3.0(c),(e); 4.1(b)–(c); 4.2(b)–(c); 4.4(a)–(d); 4.5(a)–(c), Table 1. As of 2026-11-17.

### What it says

**Annual mean**
- It is a weighted mean "based on quarterly means" (1.0(c)).
- 4.4(a): first average the daily values within each calendar quarter.
- 4.4(b): the annual mean is the average of the quarterly means, over the quarters with at least one daily value.
- 4.4(c): the DV is the 3-year average of the annual means. It is rounded per 4.3 only at the end (4.4(d)).
- So it is **not** the mean of all daily values in the year.

**Annual completeness (4.1(b))**
- A year is complete when **each of the four quarters** has at least 75% data capture.
- Capture is creditable samples ÷ scheduled samples, rounded to an integer percent.
- A year with ≥11 creditable samples in each quarter also counts if the result is above the level.
- 4.1(c) adds the min/max quarterly-value substitution tests. 4.1(d) allows Administrator discretion.

**Daily values**
- A daily value is a midnight-to-midnight 24-h average.
- It is valid with ≥18 hours, averaged over the hours available. It is also valid with fewer hours if substituting zero still gives ≥35.5 (3.0(c)).

**24-hour 98th percentile (4.5)**
- **Per year:** sort all daily values (creditable and extra) in descending order. The rank n comes from Table 1, keyed on the **annual number of creditable samples** (the sum of the four quarterly counts), not the count of all samples.
- Table 1: 1–50→1, 51–100→2, 101–150→3, 151–200→4, 201–250→5, 251–300→6, 301–350→7, 351–366→8.
- 4.5(b): the DV is the **mean of the three annual 98th percentiles**.
- 4.2(b) completeness: 75% capture in each quarter. A year still counts with fewer samples (at least one creditable sample) if the result is above the level. There is a maximum-value substitution test (4.2(c)).

### What the code and docs say now
**24-hour PM2.5**
- `design_values.py:509-531` with `:278-296`: per-year rank from Table 1 on that year's count of days with data, then the mean across years (`:299-321`).
- `:154-188`: `naaqs_percentile_rank`, using `ceil((1-p/100)·n)`. This reproduces Table 1: 50→1, 51→2, …, 351→8.
- `docs/design-value-validation.md:23` describes it correctly.
- A daily value from hourly input is the plain mean of whatever hours exist (`:244-262`). There is no 18-hour validity rule.
- There is no quarterly completeness check. Only a year-count warning is issued.

**Annual PM2.5**
- `design_values.py:1152-1157` with `annual_mean` `:423-452`: the mean of **all rows** in each year (hourly or daily), then the mean of the years.
- There is no quarterly weighting and no quarterly completeness.

### Match or mismatch
**24-hour:** matches in form (rank per year, then average over 3 years), and the rank table matches.
- For modelled data every day is "creditable", so counting days with data is the right n.
- The missing completeness checks and the missing 18-hour daily-validity rule only matter for gappy input.

**Annual:** mismatch.
- Appendix N takes the mean of quarterly means, not the mean of all values.
- With a complete modelled year the two differ, because quarters have different lengths: 90/91, 91, 92 and 92 days, so the all-hours mean weights Q3 and Q4 slightly more.
- With gaps they can differ a lot.

### What would have to change
- **Annual PM2.5:** compute the daily mean → the quarterly mean of the daily values → the mean of the quarters that have data → the mean over the years. This **changes computed numbers**, usually slightly for complete years.
- **Optionally:** the per-quarter 75% completeness check, and the 18-of-24-hour daily validity rule. These only change results for incomplete input.
- **24-hour:** no change to the numbers for complete data.

---

## A4. NO2 annual and 1-hour

### Rule text read
50.11(a),(b),(e),(f),(g); App. S 1(c) (Design values), 3.1(a)–(c), 3.2(b)–(c), 4.1, 4.2, 5.1, 5.2, Table 1. As of 2026-11-17.

### What it says

**Annual primary**
- **50.11(a)** sets the level: 53 ppb, annual average.
- **50.11(e)** sets the form: met when "the annual average concentration in a calendar year" is ≤53 ppb, per App. S.
- App. S 1(c)(1): the annual DV is "the annual mean value for a monitoring site for **one year**". It is not a multi-year average.
- S 5.1(a): the annual mean is the plain average of all reported 1-hour values.
- **Completeness, S 3.1(b):** valid when "at least 75 percent of the hours **in the year** are reported". There is **no per-quarter** requirement for the primary standard.
  - The per-quarter wording (75% in each calendar quarter) appears only in **50.11(g)**, which is the *secondary* 0.053 ppm standard. That paragraph also rounds to 3 decimals ppm.
  - S 3.1(c) allows Administrator discretion.
- Rounding to whole ppb: S 4.1(b).

**1-hour**
- **50.11(f):** met when the 3-year average of the annual 98th percentile of the daily maximum 1-hour values is ≤100 ppb.
- S 5.2(a): the annual 98th percentile is the **higher** of two procedures, each using Table 1 (same as App. N Table 1):
  - Procedure 1 uses days with ≥75% of hours: n = their count, values = their daily maxima.
  - Procedure 2 uses days with at least one hour.
- S 5.2(b): the DV is the mean of the three annual values, rounded to whole ppb. Daily maxima are not rounded (4.2(b)).
- **Completeness, S 3.2(b):** three consecutive complete years. A year is complete when all 4 quarters are complete. A quarter is complete when ≥75% of its days are complete. A day is complete with ≥75% of its hours.
  - Alternatives: 3.2(c)(i) when the result is above the level and ≥75% of days in each quarter have at least one hour; 3.2(c)(ii) and (iii) are substitution tests.

### What the code and docs say now
**Annual**
- `design_values.py:775-777`: `_NO2_ANNUAL_COMPLETENESS = 0.75` of the year.
- `:1003-1062`: the per-year check is hours covered ≥0.75 × 8760/8784 for sub-daily values. Days or months are counted for 24-HR and MONTH values.
- The default `highest_year` (`:1071`, `:1096-1116`) takes the highest complete year. Incomplete years are dropped with a warning.
- If no year is ≥75%, it falls back to the whole-record mean (`:1050-1059`).
- `multi_year_mean` (`:989-992`, `:1117-1123`) averages the years.
- `naaqs.py:93-94` cites `"40 CFR 50.11"` with no paragraph.

**1-hour**
- `design_values.py:534-551` with `:278-296`: the daily maximum, the per-year Table 1 rank on the count of days with any data, then the mean of the years.
- `docs/design-value-validation.md:24` describes this correctly.

### Match or mismatch
**Annual**
- The 75%-of-hours-in-the-year rule matches S 3.1(b). The per-quarter test would be wrong for the primary standard, and the code correctly does not apply it.
- The single-calendar-year DV matches. Taking the highest complete year is equivalent to requiring every year to meet 53 ppb.
- Not supported by Part 50:
  - the `multi_year_mean` option (it may come from modelling guidance, which was not checked);
  - the whole-record fallback (Part 50 leaves this to Administrator discretion, S 3.1(c)).
- Citations at `design_values.py:961,1098` already say 50.11(e).

**1-hour:** matches for complete data. The count of days with any data is Procedure 2. For complete modelled data the two procedures give the same n and the same values. There are no day/quarter completeness checks.

### What would have to change
- **Labels:** `naaqs.py:94` → "40 CFR 50.11(a),(e); App. S" for the annual standard, and "50.11(b),(f); App. S" for the 1-hour.
- **Optional:** mark `multi_year_mean` and the whole-record fallback as outside the Part 50 form.
- **Optional:** Procedure 1 vs 2, and quarterly completeness for 1-hour. These matter only for gappy data.
- No numbers change for complete data.

---

## A7. PM10 24-hour form

### Rule text read
50.6(a); App. K 1.0(b) definitions, 1.0(c), 2.1(a)–(b), 2.3, 3.1(a)–(e); a grep of the whole of Part 50 for "sixth", "second-highest" and "second highest"; Appendix W to Part 51 (89 FR 95043), searched for "sixth", "6th", "H6H", "H2H", "second-highest" and "Table 8-2", with 9.2.2(b)–(c) read. As of 2026-11-17.

### What it says
- **50.6(a):** 150 µg/m³, 24-hour. The standards are attained when the **expected number of days per calendar year** with a 24-hour average above 150 µg/m³ is **equal to or less than one**, per Appendix K.
- **K 2.1(a):** in the simplest case, count the exceedances in each calendar year and average them over the **past 3 calendar years**.
  - Incomplete years are adjusted quarter by quarter (3.1).
  - K 3.1(d) allows "the most recent 3 or more representative years".
- Exceedance definition (K 1.0(b)): a daily value above 150 after rounding to the nearest 10 µg/m³.
- Comparison with 1.0 is made on a value rounded to 0.1 (K 2.1(b)). So 1.05 → 1.1 is the lowest failing rate.
- K 1.0(c): the principles apply to modelling data, subject to EPA modelling guidelines.
- K 3.1(e): no incomplete-data adjustment is needed for a complete (365-day) modelling record.

**No order-statistic forms for PM10 in Part 50.** The words "sixth-highest", "H6H" and "second-highest" do not appear anywhere in Part 50 for PM10.
- "Second-highest" appears only in **50.4(d)** and **50.5(c)**, the old SO2 24-hour and 3-hour standards.

**Appendix W (current text) has no H6H either.**
- Its **Table 8-2** is "Point Source Model Emission Inputs for NAAQS Compliance in PSD Demonstrations". It is an emissions-input table, not a ranking rule.
- "Highest, second-highest" appears in App. W only for **PSD short-term increments** (9.2.2(c)).
- App. W 9.2.2(b) sends the form-specific details to EPA modelling guidance on SCRAM.

So the H6H-over-5-years / H2H-over-1-year convention is not in 40 CFR 50 and not in the current App. W text. It may live in EPA modelling guidance outside the CFR; that guidance was not read.
- Arithmetic check: with N complete years, "expected exceedances ≤1 per year averaged over N years" is the same as "at most N exceedance days in total". For N = 5 that means the 6th-highest pooled daily value must not be an exceedance. So H6H-over-5-years is consistent with K, but only as a derivation.
- Two differences from K remain:
  - K's default is a 3-year average, not 5. (3 or more representative years is allowed.)
  - K's exceedance threshold is effectively ≥155 µg/m³ after rounding, unless modelled values are left unrounded per App. W.

### What the code and docs say now
- `naaqs.py:89-90` labels the form `"not exceeded > 1/yr (5-yr avg)"`.
- `design_values.py:574-603`: the docstring says "Appendix W Table 8-2 ranks the pooled multi-year record and takes the highest sixth-high (H6H) … or H2H with a single year". The default rank is 6 if ≥5 years, else 2. It is applied to the pooled record. Form string `"H{rank}H (highest {rank}-highest 24-hour)"`.
- `docs/design-value-validation.md:27`: "Highest 6th-high of the pooled 5-year record (H6H); H2H with one year | 40 CFR 50.6; Appendix W Table 8-2".
- `docs/use-cases.md:175` makes the same H6H/H2H claim.

### Match or mismatch
**Mismatch in labelling and citation.**
- The Part 50 form is expected exceedances per calendar year ≤1, averaged over 3 (or more representative) years, per App. K.
- "5-yr avg" and H6H/H2H are not Part 50 language.
- Table 8-2 does not say this.

**The computation is a derivation:**
- H6H over 5 complete years and H2H over 1 complete year are both equivalent to "≤1 expected exceedance per year".
- For 2, 3 or 4 years, the code's H2H default is **not** equivalent. The equivalent rank would be N+1: H3H, H4H or H5H.
  - Example: 3 years with 2 exceedance days in one year average 0.7 per year, which is attainment under K. The code's H2H flags this as exceeding.

### What would have to change
- **`naaqs.py:89` form label:** "expected exceedances ≤ 1/yr (App. K; 3-yr avg)".
- **`naaqs.py:90` citation:** "40 CFR 50.6(a); App. K".
- **Docstring and docs:** drop "Appendix W Table 8-2". Cite the EPA modelling guidance that actually prescribes H6H/H2H, if one exists (not verified here), or present it as the derived equivalent.
- **Default rank:** change to N+1 for N complete years (or compute expected exceedances directly). This **changes numbers** for 2–4-year records. Results for 1 and 5 years are unchanged.
- **The 150 vs 155 rounding question** (see A1) could change flags too.

---

## A8. Ozone, Appendix U

### Rule text read
50.19(a)–(d); App. U 1(c), 3(a)–(e), 4(a)–(b), Examples 1–2. As of 2026-11-17.

### What it says
- **8-hour averages:** moving (running) 8-hour averages are computed for every hour and stored in the **first (start) hour** of the period (U 3(b)).
  - Valid with ≥6 of 8 hours, divided by the hours available.
  - With ≤5 hours, valid if substituting zero still exceeds the level (sum > 0.567 ppm).
  - Truncated to 3 decimals ppm.
- **Daily maximum (U 3(c)):** the highest of the **17** consecutive 8-hour averages starting at 7:00 a.m. through 11:00 p.m. (LST) of that day. The last period runs 11 p.m. to 7 a.m. the next day.
- **Valid day (U 3(d)):** at least 13 of the 17 periods are valid, or the daily maximum is above the level.
- **Form (U 3(e), 4(a); 50.19(b)):** the annual 4th-highest daily maximum (valid days only), averaged over 3 consecutive years.
- **DV (U 3(e)):** in ppm, **truncated** to 3 decimals. Example 1: 0.065666 → 0.065.
- **Completeness (U 4(b)):** ≥90% of the season's days on average over the 3 years, and ≥75% in any one year. A DV above the level is always valid.

### What the code and docs say now
- `design_values.py:606-621` (`o3_8hr_design_value`) takes AERMOD 8-HR values, gets the daily maximum by calendar date (`_daily_series` max, `:244-262`), then the 4th-highest per year and the mean over the years. There is no truncation.
- `_coverage_unit` docstring `:784-785` says AERMOD's N-HR values are block averages ("an 8-HR value covers 8 hours"). That would mean at most 3 non-overlapping 8-hour blocks a day, stamped by ending hour. This is the repo's own statement; it was not re-checked against the AERMOD Fortran here.
- `naaqs.py:111-112` and `docs/design-value-validation.md:26` give the form correctly. Both cite 50.19, which is correct.

### Match or mismatch
- The form (4th-highest, 3-year average) matches.
- The daily-maximum definition does not match if the input is AERMOD block 8-HR averages:
  - Appendix U needs running averages, assigned to the start hour, over the 07:00–23:00 start window.
  - The code takes the maximum over the calendar day of whatever 8-HR values are stamped that day.
- The 13-of-17 validity rule and the U 4(b) completeness rule are not applied.
- Truncation is not applied. That is consistent with App. W 9.2.2(b) for modelled values.

### What would have to change
- Compute running 8-hour averages from 1-HR values:
  - store each at its start hour;
  - take the daily maximum over start hours 07–23, including hours that spill into the next day;
  - optionally apply the 6-of-8 and 13-of-17 rules.
- This **changes computed numbers** relative to block averages. The running maximum is ≥ the block maximum.

---

## SO2, Appendix T (supporting A1)

### Rule text read
50.17(a)–(b); 50.21; App. T 1(c), 3.1(b)–(c), 4.1, 5.1, Table 1 (source note 89 FR 105785, Dec. 27, 2024). As of 2026-11-17.

### What it says
- **Form:** the 3-year average of the annual 99th percentile of daily maximum 1-hour values, met at ≤75 ppb (50.17(b); T 3.1(a), 5.1(b)).
- **Rank:** T 5.1(a) uses the higher of Procedure 1 (days with ≥75% of hours) and Procedure 2 (days with at least one hour). Table 1: 1–100→1, 101–200→2, 201–300→3, 301–366→4.
- **Completeness (T 3.1(b)):** three consecutive complete years. All four quarters must be complete. A quarter is complete with ≥75% of its days complete, and a day is complete with ≥75% of its hours. There are substitution alternatives (3.1(c)).
- **Rounding (T 4.1):** the daily maxima and the annual 99th percentile are not rounded. The DV is rounded to the nearest whole ppb.
- **New secondary standard:** 50.21 (Dec. 2024) adds an annual secondary standard of 10 ppb, as the 3-year average of annual means of daily means (T 3.2, 5.2).

### What the code and docs say now
- `design_values.py:554-571`: per-year rank from Table 1 on the day count, then the mean of the years.
- `PERCENTILE_99_RANK_TABLE` at `:147-151` matches Table 1.
- `naaqs.py:98-100` cites 50.17, which is correct.
- `docs/design-value-validation.md:25` describes it correctly.
- There is no rounding and no completeness checks. The secondary annual standard (50.21) is not in the table.

### Match or mismatch
Matches for complete modelled data. The lack of rounding is consistent with App. W.

### What would have to change
- Optional: cite "50.17(b); App. T".
- Optional: add the 50.21 secondary annual row if the library wants secondary standards.
- No numbers change.

---

## CO and Pb (supporting A1)
- **CO, 50.8(a):** 9 ppm 8-hour and 35 ppm 1-hour, "not to be exceeded more than once per year".
  - 50.8(c): an 8-hour average is valid with ≥6 hours.
  - 50.8(d): the rounding rule in the A1 table.
  - `naaqs.py:102-109` matches. There is no CO design-value function.
- **Pb, 50.16(b):** met when the maximum 3-month mean over a 3-year period is ≤0.15 µg/m³.
  - App. R 6(d): the DV is the highest valid rolling 3-month mean over the 38-month period. Rounding per R 5.
  - `naaqs.py:114-117` matches. There is no Pb design-value function.
