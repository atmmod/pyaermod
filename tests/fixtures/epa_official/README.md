# EPA official AERMOD test cases

Selected files from EPA's official **AERMOD Test Cases** archive, used
as regression fixtures to ensure pyaermod stays compatible with the
real-world AERMOD reference.

## Files checked in

Source archive:
<https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_test_cases.zip>
(EPA release of 2026-07-09, ~489 MB), reference set
`aermet26135_aermod26135` unless noted. Vendored 2026-08-22.

| File | Source | Purpose |
|---|---|---|
| `aertest.inp` | `aermet26135_aermod26135/inputs/aertest.inp` | Canonical "simple point source with PRIME downwash" example. Differs from the 24142 copy only in whitespace and the lower-case met filenames (`aermet2.sfc`). |
| `AERMET2.SFC` / `AERMET2.PFL` | `aermet26135_aermod26135/meteorology/aermet2.{sfc,pfl}` (renamed to upper case) | Meteorology for AERTEST, produced by AERMET v26135. Values identical to the 24142 files; v26135 writes four-digit years (`1988` vs `88`). |
| `AERTEST_01H.PLT` | `aermet26135_aermod26135/plotfiles/AERTEST_01H.PLT` | 1-hour HIGH-1ST PLOTFILE produced by AERMOD v26135. Data rows are byte-identical to the 24142 plotfile; only the two banner lines (version, date) differ. |
| `AERTEST.SUM` | `aermet_24142_aermod_24142/Outputs/AERTEST.SUM` | AERMOD **24142** summary output for AERTEST. Kept at 24142 deliberately: the 26135 summary echoes the four-digit-year met through a two-character field (`**` in the year column), and `tests/test_cli.py` asserts the 24142 banner. |

All files are products of U.S. EPA and are in the public domain.

## What the fixtures prove

`tests/test_real_aermod.py` runs `aertest.inp` through a real AERMOD
binary and compares every receptor against `AERTEST_01H.PLT`. With a
gfortran -O2 build of AERMOD v26135 all 144 receptors match bit-for-bit;
because the 26135 and 24142 plotfile data rows are identical, the same
check holds for a 24142 build. See `src/pyaermod/versions.py` for what
"validated" means project-wide and `docs/validation.md` for the
full-suite parity report.

## Full archive

The full EPA test-case bundle (~489 MB zipped, ~10.6 GB unpacked) ships
three reference sets side by side:

| Set | Meteorology | Model |
|---|---|---|
| `aermet24142_aermod24142` | AERMET 24142 | AERMOD 24142 |
| `aermet24142_aermod26135` | AERMET 24142 | AERMOD 26135 |
| `aermet26135_aermod26135` | AERMET 26135 | AERMOD 26135 |

Each set has the same layout (`inputs/` 53 decks, `meteorology/`,
`postfiles/` 143 reference `.PST`, `plotfiles/`, `Outputs/`). Note the
naming changed from the pre-2026 bundle's `aermet_24142_aermod_24142`;
`pyaermod.epa_testcases.find_epa_testcase_set` accepts both spellings and
picks the set matching the AERMOD binary on PATH (or
`$PYAERMOD_EPA_TESTCASES`).

Unpack the archive under `<repo>/test_cases/` (gitignored) to enable
`tests/regulatory/`, `tests/test_epa_cases.py`, `tests/test_real_cases.py`
and `scripts/run_epa_parity.py`; the scheduled `epa_parity.yml` workflow
does this automatically. `download_all.py` fetches the same archive into
`tests/fixtures/epa_official/full/` for the regression tests in
`tests/test_regression_epa_official.py`.

## Versions

Fixtures in this directory track AERMOD v26135 / AERMET v26135
(`AERTEST.SUM` excepted, see above). When a new AERMOD release ships:

1. Unpack the new archive (see above) and diff each vendored file against
   the new set's copy; vendor the new copy only if the differences are
   provenance-only (banner, date, formatting) or you have re-verified the
   bit-exact AERTEST regression against a build of the new release.
2. Update `VALIDATED_AERMOD_VERSIONS` / `VALIDATED_AERMET_VERSIONS` in
   `src/pyaermod/versions.py` once the parity suite passes against the
   new release's reference set.
3. Run `pytest tests/test_real_aermod.py tests/test_regression_epa_official.py`
   and update any asserted values that shift.
