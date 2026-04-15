# EPA official AERMOD test cases

Selected files from EPA's official **AERMOD Test Cases** archive, used
as regression fixtures to ensure pyaermod stays compatible with the
real-world AERMOD reference.

## Files checked in

| File | Source | Purpose |
|---|---|---|
| `aertest.inp` | `aermet_24142_aermod_24142/inputs/aertest.inp` | Canonical "simple point source with PRIME downwash" example |
| `AERTEST_01H.PLT` | `aermet_24142_aermod_24142/plotfiles/AERTEST_01H.PLT` | 1-hour HIGH-1ST PLOTFILE produced by AERMOD v24142 |
| `AERTEST.SUM` | `aermet_24142_aermod_24142/Outputs/AERTEST.SUM` | AERMOD summary output for AERTEST |

All three are products of U.S. EPA and are in the public domain.

## Full archive

The full 234 MB EPA test-case bundle covers 40+ test cases spanning
chemistry modes, deposition, terrain, buoyant line sources, urban
modeling, etc. It's too big to vendor; fetch on demand with:

```bash
python tests/fixtures/epa_official/download_all.py
```

The script downloads
<https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_test_cases.zip>
and unpacks it under `tests/fixtures/epa_official/full/` (gitignored).
Regression tests that need the full set skip cleanly if that directory
is absent.

## Versions

Fixtures in this directory track AERMOD v24142 (AERMET v24142).
When a new AERMOD release ships, regenerate this directory:

1. `python tests/fixtures/epa_official/download_all.py --force`
2. `cp full/aermet_<new>_aermod_<new>/inputs/aertest.inp .`
3. `cp full/aermet_<new>_aermod_<new>/plotfiles/AERTEST_01H.PLT .`
4. `cp full/aermet_<new>_aermod_<new>/Outputs/AERTEST.SUM .`
5. Run `pytest tests/test_regression_epa_official.py` and update any
   asserted values that shift.
