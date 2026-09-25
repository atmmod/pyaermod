# pyaermod-written decks and their AERMOD outputs

Unlike `../epa_official/`, nothing here was shipped by EPA. These are
decks pyaermod wrote and files a gfortran build of AERMOD v26135
(`scripts/build_aermod.sh`) produced from them.

| Files | Purpose |
|---|---|
| `simple_point.inp.expected` | Golden deck for the writer's byte-identical round-trip test. |
| `sample_plotfile.plt`, `sample_maxifile.max` | Small hand-made AERMOD auxiliary files for the parsers. |
| `so2_1hr_design.inp`, `so2_1hr_{maxdaily,mxdybyyr,maxdcont}.dat` | `naaqs_output_pathway("SO2")` deck (RECTABLE 1-4, MAXDAILY, MXDYBYYR, MAXDCONT ALL 4 4) run on EPA's `anch-99_adju` meteorology (Anchorage 1999, a full year) with two discrete receptors. |
| `no2_1hr_design.inp`, `no2_1hr_{maxdaily,mxdybyyr,maxdcont}.dat` | Same for NO2 (rank 8). |

The MAXDAILY files hold every day's maximum 1-hour value at each receptor
(365 x 2 rows); `tests/test_design_values.py::TestAermodDesignValueOutputs`
computes the 99th/98th-percentile design value from them with pyaermod
and requires it to equal AERMOD's own MXDYBYYR rank row and MAXDCONT
total exactly. Regenerate with the decks and the meteorology from EPA's
`aermod_test_cases.zip` (`aermet26135_aermod26135/meteorology/`).
