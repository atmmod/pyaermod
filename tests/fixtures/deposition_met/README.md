# Wet meteorology for the deposition example

Four days of AERMET output with rain, so that
`tests/test_example_deposition.py` can show that wet deposition and wet
depletion produce values. The vendored `epa_official/AERMET2.SFC` has
no precipitation (AERMOD warns W496 and every WDEP value is 0.00000).

| File | Contents |
|---|---|
| `HOUSTON_1996-02-26_29.SFC` | Header line and the 96 hourly records for 1996-02-26 01 to 1996-02-29 24 of `HOUSTON.SFC`, unchanged |
| `HOUSTON_1996-02-26_29.PFL` | The same 96 hours of `HOUSTON.PFL` (one level per hour), unchanged |

`HOUSTON.SFC` and `HOUSTON.PFL` are the output of EPA's AERMET test
case EX04 (Houston Intercontinental surface data in ISHD format, Lake
Charles upper air, 1996), run with AERMET v26135 built from EPA's
source. The inputs `EX04_S1.INP`, `EX04_S2.INP`, `03937-96.FSL` and
`722430~1.DAT` are byte-identical to `EX04 (Houston)` in EPA's
`aermet_def_testcases_24142` archive. SHA-256 of the full-year files:

- `HOUSTON.SFC`: `625f4ab2126d95426458501c2e6705cd33397e862f63d8438e69cf956fd9d994`
- `HOUSTON.PFL`: `c4447c8c2697fc20a95984f52282448e43957bc19fed38405fcfae2d11dc8ccd`

The window was picked as the wettest four whole days of 1996 with no
calm or missing hours: 19 hours with precipitation, 28.4 mm in all.
AERMET v24142 gives the same values for these hours; only the year is
written with two digits.
