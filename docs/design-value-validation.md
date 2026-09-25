# Design-Value / NAAQS Validation

`docs/validation.md` shows that pyaermod drives AERMOD to reproduce EPA's
concentrations. This page covers the layer above that: the
post-processing in `pyaermod.design_values` that turns a concentration
time series into the number a permit application quotes.

That layer is where a regulatory wrapper is easiest to get quietly
wrong, because a wrong design value is still a plausible-looking
number. Everything below is a *known answer* — either read off the
regulation, computed by hand, or taken from EPA's own ranked output —
never a recorded pyaermod result.

## What the standards actually say

The NAAQS percentile forms are order statistics selected from a lookup
table, not interpolated quantiles. Each appendix sorts the year's daily
values from highest to lowest, looks the year's count of valid days up
in a table, and takes the *n*-th value from the top.

| Standard | Form | Full-year rank | Citation |
|---|---|---|---|
| PM2.5, 24-hour | 3-yr avg of annual 98th percentile of daily 24-hour averages | 8th highest | 40 CFR 50 app. N, Table 1 |
| NO2, 1-hour | 3-yr avg of annual 98th percentile of daily max 1-hour values | 8th highest | 40 CFR 50 app. S, Table 1 |
| SO2, 1-hour | 3-yr avg of annual 99th percentile of daily max 1-hour values | 4th highest | 40 CFR 50 app. T, Table 1 |
| O3, 8-hour | 3-yr avg of annual 4th-highest daily max 8-hour average | 4th highest | 40 CFR 50.19 |
| PM10, 24-hour | Highest 6th-high of the pooled 5-year record (H6H); H2H with one year | — | 40 CFR 50.6; Appendix W Table 8-2 |

`naaqs_percentile_rank(n_days, percentile)` implements the tables. Both
are transcribed into `tests/test_naaqs_rank_tables.py` and checked row by
row for **every** day count from 1 to 366.

The multi-year step matches AERMOD's own: rank each year independently,
then take the arithmetic mean of the annual values
(`SUMHNH(...) / DBLE(NUMYRS)` in `aermod.f`). Ranking the pooled
multi-year record instead gives a different — and wrong — answer, and a
test pins the difference.

## Evidence

### 1. The regulation, transcribed

`tests/test_naaqs_rank_tables.py` holds appendix N/S/T Table 1 as data
and asserts `naaqs_percentile_rank` reproduces each row for each day
count. It also pins that the result *differs* from
`Series.quantile(0.98, interpolation="linear")`, so a silent revert to
an interpolated quantile fails the suite instead of shipping.

### 2. Hand-computable series

On a year of 365 strictly decreasing daily values (365, 364, … 1) the
*k*-th highest is exactly `366 − k`, so every expected number is
arithmetic:

- 98th percentile → 358; 99th percentile → 362.
- Three years whose 8th-highest values are 358, 258 and 158 give a
  design value of 258 — the average of the annual ranks. Ranking the
  pooled 1095-day record would give 361.
- A 200-day year moves the 98th percentile to the 4th highest (app. S
  Table 1 row "151–200"), giving 197.

### 3. EPA's own ranked output

`tests/regulatory/test_epa_known_answers.py` needs **no AERMOD binary**:
it reads the concentration time series EPA ships (`postfiles/*.PST`) and
compares pyaermod's ranking against EPA's ranked tables for the same
run. Both sides come from identical numbers, so agreement is exact — no
tolerance is applied.

| Check | Reference file | Coverage |
|---|---|---|
| 1st-highest at every receptor | `plotfiles/*.PLT` | all 47 PST/PLT pairs in the reference set |
| Ranks 1–8 of the 24-hour series | `Outputs/PSET2PA.DA1`–`DA8` | EPA's `surfcoal` deck, every receptor |
| NAAQS design value | `plotfiles/PSDCRED_*.PLT` | AERMOD's own 1-hour NO2 design-value output, every receptor |
| Overall-maximum table | `Outputs/AERTEST.SUM` | ranks 1–3, value and coordinates |

The `PSDCRED` case is the strongest of the four: those plotfiles are
what AERMOD writes under its own 1-hour NO2 NAAQS processing
(`1ST-HIGHEST MAX DAILY 1-HR VALUES AVERAGED OVER n YEARS`), so matching
them receptor-by-receptor is EPA's implementation of the design-value
algorithm agreeing with pyaermod's.

The `.SUM` overall-maximum table is worth noting because it is easy to
misread: for rank *n* it lists the largest *n*-th-highest value at any
receptor, not the *n*-th largest value in the record. On AERTEST the
second row is 421.98845, while the second largest hourly value in the
`.PST` is 746.09714 at a different receptor.

## The same method, elsewhere

The pattern here -- find the artefact that already contains the answer,
and let the tool that consumes a format be the judge of it -- is what
the rest of this phase used too:

| Component | Oracle | Result |
|---|---|---|
| Design values | 40 CFR 50 app. N/S/T tables; EPA's `.PLT` / `DA1-8` / `.SUM` | exact |
| BPIP | EPA's BPIP-PRIME, compiled from source | exact, 6,480 direction comparisons |
| AERSURFACE | the binary's own setup pass (`RUNORNOT NOT`) | EPA's reference reproduced byte-for-byte; ~30 configurations accepted |
| AERMOD decks | AERMOD's setup pass, all 10 source types | accepted |
| AERSCREEN | *none yet* | see the known limitation in `pyaermod.aerscreen` |

## Running it

```bash
pytest tests/test_naaqs_rank_tables.py tests/regulatory/test_epa_known_answers.py
```

The EPA-fixture tests skip when the reference set is not unpacked under
`test_cases/` (see `pyaermod.epa_testcases.find_epa_testcase_set` and
`$PYAERMOD_EPA_TESTCASES`). Two very large `.PST` pairs carry
`@pytest.mark.slow` and need `-m slow`; nothing else is excluded, and a
collection guard fails the suite if fewer pairs than expected are found
so it cannot pass vacuously.
