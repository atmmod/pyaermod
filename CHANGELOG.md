# Changelog

All notable changes to PyAERMOD will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Property-based round-trip over the ME and OU pathways, and polar
  receptor grids** — `tests/test_property_pathways.py`. Those pathways
  were pinned to fixed values in the existing property tests, so every
  field on them went unexercised.
- **Deck-acceptance cases for the output pathway** — the PLOTFILE,
  POSTFILE and RECTABLE keywords have field-count-sensitive syntax that
  varies with the averaging period, so each configuration is now run
  through AERMOD's setup check.

- **Deck-acceptance tests for every source type** —
  `tests/test_source_deck_acceptance.py` generates a minimal deck for
  each of pyaermod's ten source types and runs AERMOD's own setup pass
  (`RUNORNOT NOT`) over it, asserting no fatal errors. It carries a
  coverage guard that fails when a new source type is added without a
  case, and a self-check that a deliberately broken deck *is* reported,
  so the suite cannot pass vacuously.
- **Property-based round-trip over all ten source types** —
  `tests/test_property_all_sources.py`. The existing property tests
  covered the three types the reader supported when they were written.
- **`ControlPathway.alpha` / `.beta`** — the non-regulatory MODELOPT
  options. AERMOD refuses RLINEXT outright without ALPHA.

- **Real-binary parity for BPIP-PRIME and AERSURFACE.** Both had EPA
  Fortran available and neither had ever been run against it.
  `scripts/build_bpip.sh` and `scripts/build_aersurface.sh` fetch and
  compile them (into `./bin`), and `make test-binaries` puts that
  directory on PATH so the binary-backed suite is one command.
  - `tests/test_bpip_known_answers.py` compares `pyaermod.bpip` against
    EPA's BPIP-PRIME direction by direction, at the F8.2 print
    resolution BPIP writes with.
  - `tests/test_real_aersurface.py` builds the deck for EPA's published
    RDU test case with `AERSURFACEConfig`, runs it, and compares the
    surface characteristics to EPA's shipped reference file. They are
    identical apart from the run timestamp.
- **`pyaermod.epa_sources`** — registry of EPA SCRAM download locations
  for AERMOD, AERMET, AERMAP, AERSURFACE, AERSCREEN, MAKEMET, BPIP and
  BPIP-PRIME source and test-case archives. Every URL was discovered by
  listing its SCRAM directory and verified to return a zip; an opt-in
  network test (`PYAERMOD_NETWORK_TESTS=1`) re-lists each directory so
  an EPA rename fails a test instead of 404-ing in CI later.
- **`pyaermod.bpip` GEP influence-zone test** — `BPIPCalculator` now
  reports zeros for wind directions where the stack lies outside the
  structure influence zone, as BPIP does, with `influence_test=False`
  to inspect the raw projected geometry.

- **NAAQS design-value known-answer tests** — the design-value math is now
  pinned against evidence rather than smoke-tested. `tests/test_naaqs_rank_tables.py`
  transcribes 40 CFR part 50 appendix N Table 1, appendix S Table 1 and
  appendix T Table 1 and checks the new `naaqs_percentile_rank()` against
  every row for every day count 1–366, then pins design values on series
  whose answer is arithmetic (365 strictly decreasing daily values → the
  98th percentile is exactly the 358th). `tests/regulatory/test_epa_known_answers.py`
  compares pyaermod's ranking against EPA's *own* ranked output — no
  AERMOD binary needed, since both sides derive from the concentrations
  in EPA's shipped `.PST` files:
  - the 1st-highest value at every receptor of all 47 `.PST`/`.PLT` pairs
    in the reference set, exactly (no tolerance);
  - ranks 1 through 8 of the 24-hour series in EPA's `surfcoal` deck
    against its eight `PSET2PA.DA1`–`DA8` plotfiles — the depth the
    98th-percentile forms need;
  - AERMOD's own NAAQS design-value plotfiles (`PSDCRED_*`, written under
    its 1-hour NO2 processing) against
    `nth_highest_daily_max_design_value()`, receptor by receptor;
  - the `.SUM` overall-maximum table, which ranks the largest *n*-th
    highest value per receptor rather than the *n*-th largest value in
    the record.
- **`pyaermod.design_values.naaqs_percentile_rank()`** — the EPA rank-table
  lookup, with both regulatory tables exported as
  `PERCENTILE_98_RANK_TABLE` / `PERCENTILE_99_RANK_TABLE`.
- **`pyaermod.design_values.nth_highest_daily_max_design_value()`** — the
  general form behind the 1-hour NO2, 1-hour SO2 and 24-hour PM2.5
  standards, and the one AERMOD itself computes under `NO2AVE` / `SO2AVE`
  / `PM25AVE`: rank each year's daily series independently, then average
  those annual values across years (`SUMHNH / NUMYRS` in `aermod.f`).
- **`AERMODAuxResult.concentration_column` / `.values()`** — callers no
  longer have to guess whether AERMOD spelled the column `CONC` or
  `AVERAGE CONC`.
- **`pyaermod.aermod_outputs.parse_fortran_format()`** — expands the
  Fortran FORMAT statement AERMOD prints in every auxiliary-file header
  into field widths, so records are sliced at the offsets AERMOD wrote
  them at.

- **Headless smoke tests for the NiceGUI GUI** — `tests/test_gui_v2_smoke.py`
  drives the real `gui_v2` shell through `nicegui.testing.User` (in-process
  ASGI, no browser): every tab renders its key controls; a minimal project
  (title, one point source via the Sources editor dialog, a receptor grid,
  met file names) is filled in through the UI, saved and reloaded via
  `project_io` with an identical AERMOD deck, and run against a fake
  `aermod` on `PATH` with the Results tab asserted for both the no-output
  and parsed-output cases. `gui_v2` is now measured by coverage (only
  `desktop.py`, the pywebview wrapper, stays omitted). Requires the new
  `pytest-asyncio` dev dependency.
- **Regulatory-grade numeric regression** — `tests/test_real_aermod.py` now
  compares every AERTEST receptor against EPA's published reference plotfile
  (`tests/fixtures/epa_official/AERTEST_01H.PLT`) to a tight tolerance
  (rtol=1e-4), proving pyaermod drives the real AERMOD Fortran to reproduce
  EPA's own concentrations field-for-field — not merely that a run completes.
  A gfortran -O2 build reproduces all 144 receptors bit-for-bit.
- **Synthetic-DEM analytic regression for AERMAP** — `test_real_aermap.py`
  now builds a tiny USGS-format UTM DEM whose elevation is an exact tilted
  plane, runs it through the real AERMAP binary via `AERMAPRunner`, and
  asserts the extracted receptor elevations match the closed-form plane at
  on-node receptors (max deviation 0 with a gfortran build). Independent
  numeric ground truth, fully self-contained (no vendored DEM, no downloads).
- **Validated-version declarations** — `pyaermod.versions.VALIDATED_AERMOD_VERSIONS`
  / `VALIDATED_AERMET_VERSIONS` (`("26135", "24142")`, newest first; exported
  from the package API and `regulatory_parity`) state exactly which EPA
  releases the bit-exact AERTEST regression and the full test-suite parity
  have been run against. `AERMODOutputParser` now logs one warning when an
  output file was produced by a release outside that list.
- **EPA reference-set resolver** — `pyaermod.epa_testcases.find_epa_testcase_set`
  locates EPA's unpacked test-case sets under `test_cases/` accepting both
  naming conventions (`aermet_24142_aermod_24142` and the July-2026 bundle's
  `aermet24142_aermod24142` / `aermet24142_aermod26135` /
  `aermet26135_aermod26135`), honours `$PYAERMOD_EPA_TESTCASES`, and prefers
  the set whose AERMOD version matches the `aermod` binary on PATH
  (`aermod_binary_version`, from `aermod --help`), then the newest validated
  release. `tests/regulatory/`, `tests/test_epa_cases.py`,
  `tests/test_real_cases.py`, `tests/test_regression_epa_official.py` and
  `scripts/run_epa_parity.py` all resolve through it; regulatory test IDs now
  carry the set name (`[aermet26135_aermod26135/aertest.inp]`).
- **Parity report provenance** — `scripts/run_epa_parity.py` now stamps a
  Provenance table into `docs/validation.md`: AERMOD version (parsed from
  the `*** AERMOD - VERSION NNNNN ***` banner of a produced `.out`, falling
  back to `aermod --help`), binary path, `gfortran --version`, the EPA
  reference set, pyaermod version, git SHA (`-dirty` when applicable),
  platform and UTC timestamp. New `--testcase-dir` (or
  `$PYAERMOD_EPA_TESTCASES`) and `--clean-scratch` options; exit 2 when the
  fixtures or binary are missing, 1 when any comparison fails.
- **Scheduled EPA parity CI** — `epa_parity.yml` now runs weekly (Tuesday
  07:00 UTC, staggered from the Monday real-binary smokes) as well as on
  dispatch (archive URL inputs optional, defaulting to the canonical SCRAM
  URLs — the old default pointed at a non-existent `aermod_testcases.zip`).
  It compiles EPA's current AERMOD, fetches both EPA test-case archives via
  `scripts/fetch_epa_source.sh`, unpacks only the sets the suite needs (the
  set matching the compiled AERMOD version for parity, the 24142 set for the
  parser regressions, `aermet_def_testcases_24142` for the AERMET parsers —
  each AERMOD set is ~3.5 GB unpacked) and caches the unpacked trees with
  `actions/cache` (key = URLs + upstream ETag/Last-Modified + AERMOD
  version + salt; saved right after unpacking so a later failure keeps the
  cache). It runs `tests/regulatory`, `tests/test_epa_cases.py`,
  `tests/test_real_cases.py`, `tests/test_real_aermet.py` and
  `scripts/run_epa_parity.py`, fails if any test fails, if the fixture-gated
  tests all skipped, or if any deck leaves tolerance, and uploads the
  regenerated `docs/validation.md` as an artifact (never auto-commits).
  Before the cache is saved, a prune step cuts each unpacked tree down to
  the directories some test in this repo actually opens — resolved with the
  same `find_epa_testcase_set` the tests use, so it cannot drift from them:
  `inputs/`, `meteorology/`, `postfiles/` of the parity set, `Outputs/`,
  `postfiles/`, `plotfiles/` of the 24142 set (a set filling both roles
  keeps the union), and `output_files/` + `salem/` of
  `aermet_def_testcases_24142`. The 24142 set also keeps `inputs/`, which
  no test reads but `EPATestCaseSet.exists()` requires — without it the set
  survives on disk yet drops out of `find_epa_testcase_set`, so
  `tests/test_epa_cases.py` and `tests/test_real_cases.py` skip and the
  all-skipped guard fails the job (11 MB). What the prune actually reclaims
  in CI is the AERMET raw example datasets whose products are already in
  `output_files/` (873 MB → 174 MB, ~90 % of the saving) plus the Windows
  `.bat`/`.exe` runners and the empty `rdata/` drop boxes: **7.91 GB →
  7.14 GB, 770 MB (9.7 %) freed**. The clauses dropping EPA's `plots_*/`
  comparison images and R driver scripts are defence for a local full
  unpack only — CI's selective `unzip` never extracts them, so they
  contribute 0 MB of that total. Afterwards the step re-checks every kept
  directory *and* re-resolves both sets through `find_epa_testcase_set`,
  failing the job before the save if one came out missing, empty, or no
  longer resolvable. The regulatory harness also deletes each
  deck's staged scratch (~40 MB) in a fixture finalizer. The three
  real-binary smoke workflows gained `timeout-minutes: 30` (`epa_parity`
  already had 120) so a stalled gaftp fetch cannot hold a runner for the
  six-hour default.
- **AERMOD v26135 keyword audit** — `docs/keyword-audit-v26135.md` compares
  the 122-entry keyword table in EPA's v26135 `modules.f` (and the
  per-pathway `KEYWRD .EQ.` dispatch) against `input_reader.py`: per
  pathway, handled+tested / handled+untested / unhandled lists, the reader's
  MODELOPT and source-type coverage, and five follow-ups (`MAXIFILE`
  argument order, RLINEXT/AREAPOLY/BUOYLINE not constructed, `GRIDPOLR`
  heuristics, the undelivered `unparsed_lines` promise). All 53 decks in the
  v26135 archive parse. `tests/test_input_reader.py` gains parametrised
  one-line decks for every previously untested branch and a pass-through
  test for every unhandled keyword; `input_reader.py` coverage 85.0 % →
  99.8 % (the one remaining line is an unreachable guard).

### Upgrade notes — `AERSURFACEConfig`

`AERSURFACEConfig`'s fields changed, because the deck it built was not
in any AERSURFACE format: it emitted `TITLE`, `LOCATION`, `NLCDFILE`,
`SNOW_TEMPER`, `OUTPATH` and friends, none of which AERSURFACE has ever
accepted, and the real binary aborted in its control-file parser. No
code that ran AERSURFACE can have depended on the old fields; code
written against them can.

Passing an old field name now raises a `TypeError` naming the
replacement, rather than a bare "unexpected keyword argument".

| Old | New |
|-----|-----|
| `nlcd_file` | `land_cover_file` |
| `radius_roughness_km` | `zo_radius_km` |
| `snow_cover_per_month=[...]` | months in the `WINTERWS` season: `seasons={"WINTERWS": (1,), ...}` |
| `moisture_per_month=[...]` | one `moisture="AVERAGE" \| "WET" \| "DRY"` |
| `output_dir` | `sfcchar_file` (plus `*_grid_file` for the optional grid outputs) |
| `extra_lines` | `extra_co_lines` / `extra_ou_lines` |
| `sectors=[30, 60, 225]` | `sectors=[(30, 60, "NONAP"), (60, 225, "AP"), (225, 30, "NONAP")]` |
| `utc_offset` | *removed* — AERSURFACE has no UTC-offset keyword |
| `snow_regime` | *removed* — use `snow=True/False`; `CLIMATE` has no temperature regime |
| `radius_albedo_bowen_km` | *removed* — AERSURFACE averages over the single `ZORADIUS` |

```python
# Old — produced a deck AERSURFACE rejected
cfg = AERSURFACEConfig(
    title="Salem", site_id="SALEM", latitude=44.92, longitude=-123.04,
    utc_offset=-8, nlcd_file="NLCD_2019.img", nlcd_year=2019,
    snow_regime="CONTINENTAL_WARM", radius_roughness_km=1.0,
)

# New
cfg = AERSURFACEConfig(
    title="Salem", site_id="SALEM", latitude=44.92, longitude=-123.04,
    land_cover_file="NLCD_2019_LC.tiff", nlcd_year=2019,
    zo_radius_km=1.0, moisture="AVERAGE", snow=True,
    sfcchar_file="salem_sfc.txt",
)
```

These fields are new and have no old equivalent: `title_two`, `datum`,
`canopy_file`, `impervious_file`, `site_type`, `zo_method`, `frequency`,
`debug_options`, `run`, and the `*_grid_file` outputs.

### Changed
- **`docs/validation.md` regenerated against AERMOD v26135** (gfortran 15.2
  build, EPA set `aermet26135_aermod26135`): **142 / 142** POSTFILE
  comparisons within EPA's ±0.001 slope margin in 323 s (the previous
  104 / 104 figure was produced against the pre-2026 24142 bundle with no
  recorded version). Informational cross-version run of the same v26135
  binary against the `aermet24142_aermod24142` references: 136 / 142, the
  six misses all GRSM NO2 cases (slopes 0.946–1.117) — EPA's v26135 GRSM
  changes, not a pyaermod regression — which is why the harness now scores
  against the reference set matching the binary's version.
- **Vendored EPA fixtures refreshed to the v26135 archive**
  (`tests/fixtures/epa_official/`; EPA bundle of 2026-07-09, set
  `aermet26135_aermod26135`): `AERTEST_01H.PLT` (data rows byte-identical to
  the 24142 file; only the two banner lines differ), `aertest.inp`
  (whitespace and lower-case met filenames only), `AERMET2.SFC`/`.PFL`
  (values identical; AERMET 26135 writes four-digit years). `AERTEST.SUM`
  deliberately stays at 24142 (the 26135 summary prints `**` in its
  two-digit year column). `tests/test_real_aermod.py` passes bit-exact
  against a gfortran build of AERMOD v26135. Version notes in module
  docstrings, README and docs now say 26135 (AERMAP stays 24142 — EPA's
  current AERMAP source is still `aermap_source_code_24142`; the GRSM note
  records that v26135 drops its BETA flag while it remains non-DFAULT).
- **Library code no longer prints.** `import pyaermod` is now silent: the
  `Warning: folium not installed. Interactive maps unavailable.` (and the
  matching matplotlib) line that `pyaermod.visualization` wrote to stdout on
  every import is now a `DEBUG`-level log record. That line was not merely
  untidy — it broke the scheduled parity workflow, whose version probe reads
  `python -c "... print(aermod_binary_version())"` through command
  substitution: the warning landed inside the captured value, and a
  multi-line value is invalid in `$GITHUB_OUTPUT`, so the run died with
  `Invalid format 'Warning: folium not installed...'` before compiling
  anything. The workflow now also takes only the last line and rejects a
  non-numeric version, so a future stray print degrades to the fallback
  instead of failing the run; the user-facing signal stays
  the `ImportError` with an install hint raised by the first feature that needs
  the package. `AERMODVisualizer.plot_contours` / `create_interactive_map`
  ("Figure saved to ...") and `AERMODResults.export_to_csv` ("Exported results
  to ...") report through `logging.getLogger(__name__)` at `INFO` instead of
  `print()`. `print()` remains only in `cli.py`, the NiceGUI GUI, the explicit
  `pyaermod.print_info()` banner, and `if __name__ == "__main__":` demo blocks.
  `tests/test_import_silence.py` pins the guarantee in a fresh subprocess.
- **Benchmark gate has a noise floor.** `benchmarks/compare_benchmarks.py`
  gained `--min-baseline-ms` (default 5.0): a benchmark whose baseline is
  below the floor is listed under `IGNORED` but never fails the PR — the gate
  previously failed a PR on `aux_parse/plotfile_100rows 0.172 -> 0.235 ms
  (+36.8%)`, pure noise on a sub-millisecond operation. `run_benchmarks.py`
  now times each benchmark over `--rounds` independent rounds (default 5) and
  reports the minimum instead of a single timing; the round count is recorded
  in the JSON. `tests/test_benchmarks_harness.py` proves +40% on a 0.2 ms
  baseline passes while +40% on a 50 ms baseline still fails.
- **mypy is gated, not advisory.** `scripts/mypy_gate.py` runs
  `mypy src/pyaermod` (config from `pyproject.toml`), counts `error:`
  diagnostics and compares against the integer committed in
  `mypy-baseline.txt`; CI (`tests.yml`, Python 3.12 leg, mypy pinned) fails
  only if the count *increases*, and prints the exact
  `python scripts/mypy_gate.py --update` command when it decreases. Existing
  type errors are untouched. The baseline is authoritative for the
  `.[dev,all]` environment CI uses: typed optional packages (`nicegui`,
  `ezdxf`, ...) surface errors that `ignore_missing_imports` hides when they
  are absent, so a partial install reports a different count (the gate's
  failure message says so; `make typecheck` pins the same mypy as CI).
  The baseline is **78**, and it is only meaningful measured on that leg.
  There is deliberately no `python_version` pin: pinning 3.11 while the gate
  runs on 3.12 made mypy reject numpy 2.5's own stubs (`Type statement is
  only supported in Python 3.12 and greater`) and abort before checking any
  project code. The count is dependency-sensitive too — numpy 2.5 types
  `ArrayLike` precisely enough to surface nine further errors in
  `geospatial.py` and `visualization.py` that numpy 2.4 did not — so a
  baseline measured on an older local environment understates it, which is
  how it was first committed nine too low.
- **Honest dependency floors, validated in CI.** The optional-extra lower
  bounds in `pyproject.toml` were aspirational (`geopandas>=0.10` predates
  shapely 2 / pandas 2; `shapely>=1.8`, `matplotlib>=3.3`, `scipy>=1.7`,
  `pyproj>=3.0`, `rasterio>=1.2`, `requests>=2.25`, `nicegui>=2.0`). They are
  raised to `matplotlib>=3.7`, `scipy>=1.10`, `folium>=0.14`, `pyproj>=3.4`,
  `geopandas>=0.14`, `rasterio>=1.3`, `shapely>=2.0`, `requests>=2.32.2` and
  `nicegui>=3.0` (`numpy>=1.24`, `pandas>=2.0`, `tqdm>=4.60`, `ezdxf>=1.0`
  unchanged). `requests>=2.32` is forced by nicegui — even nicegui 2.0.0
  requires `requests>=2.32.0`, so the previous `[all]` floor set was not
  co-installable at all — and `nicegui>=3.0` is the line the GUI itself
  needs (nothing under `src/` imports `nicegui.testing`). The headless smoke
  tests do *not* exercise that floor: `user_simulation` and
  `ElementFilter(local_scope=)` only landed in NiceGUI 3.4.0, so
  `tests/test_gui_v2_smoke.py` skips below it rather than claiming coverage
  it does not have — the min-deps leg caught the original `minversion="3.0"`
  guard letting collection through and then failing on the missing module.
  The requests
  floor lands on `2.32.2` rather than `2.32.0` because 2.32.0 and 2.32.1
  are yanked on PyPI ("Yanked due to conflicts with CVE-2024-35195
  mitigation"): the exact pin in `min-constraints.txt` made the `min-deps`
  leg install a withdrawn release (pip honours an `==` pin on a yanked
  version, warning as it does so), and no range resolution will ever land
  there anyway. 2.32.2 is the oldest 2.32.x that is still a real
  candidate. A new
  `min-constraints.txt` pins the oldest versions that satisfy those floors
  together (resolvability proven with
  `pip install --dry-run --ignore-installed -e ".[dev,all]" -c min-constraints.txt`),
  and a `min-deps` leg in `tests.yml` (Python 3.11) installs `.[dev,all]`
  under those constraints and runs the suite, so the floors are checked
  rather than guessed. It earned its keep immediately: `fiona` is pulled in
  by geopandas, which declares only `fiona >=1.8.21` with no upper bound, so
  the oldest-everything resolve paired geopandas 0.14 with a current fiona —
  and fiona 1.10 removed `fiona.path.ParsedPath`, which geopandas 0.14 calls
  on every read, failing eight shapefile tests with `module 'fiona' has no
  attribute 'path'`. `min-constraints.txt` now caps it at the last 1.9.x.
- The real-AERMOD test suite runs AERMOD once via a session-scoped fixture
  instead of re-invoking it per test.
- `real_aermod.yml` CI now also re-runs when the EPA reference plotfile or
  `aermod_outputs.py` change.
- **Hardened EPA real-binary CI against gaftp flakiness and version churn.**
  The real-binary workflows (`real_aermod`, `real_aermap`, `real_aermet`,
  `epa_parity`) now:
  - fetch EPA SCRAM archives via `scripts/fetch_epa_source.sh` — `curl --fail`,
    retries with backoff, and validation that the archive is a real zip before
    compiling (previously a rate-limited/error response from `gaftp.epa.gov`
    was silently saved as the "zip" and failed the job on `unzip`); and
  - derive the extracted source directory from the archive instead of pinning
    a name, so EPA's rename of the AERMOD source dir
    (`aermod_source_code_24142` → `aermod_source_v26135`) and AERMET's flat,
    Fortran-90 layout no longer break the compile. Verified locally: AERMOD
    v26135 still reproduces the vendored 24142 AERTEST reference bit-for-bit.
- **EPA source version is pinned per run and surfaced in CI.**
  `scripts/fetch_epa_source.sh` now prints the archive's top-level directory
  (EPA encodes the version in it, e.g. `aermod_source_v26135`; `<flat
  archive>` for AERMET) after every successful fetch or cache reuse, and
  appends `EPA source: <dir> from <url>` to `$GITHUB_STEP_SUMMARY` when set.
  `real_aermod.yml` / `real_aermap.yml` / `real_aermet.yml` gained a
  `workflow_dispatch` input `source_url` (default = the current SCRAM URL) to
  try a new EPA release without editing the workflow, and cache the downloaded
  zip with `actions/cache` keyed on the URL plus the calendar month (so a
  same-URL EPA re-release is still picked up within a month while gaftp
  flakiness inside the month is absorbed). The derived-dir and
  `chmod -R u+w` compile logic is unchanged.
- **Repo hygiene.** `.DS_Store` and `aermod/.DS_Store` are no longer tracked
  (they were already gitignored, so they showed as perpetually modified). A
  `Makefile` adds `test`, `test-full` (installs `.[dev,all]`, then the whole
  suite with coverage), `lint` and `typecheck` targets mirroring CI;
  `CONTRIBUTING.md` documents the GDAL prerequisite for the `[geo]` extra and
  `make test-full` as the pre-PR check.

### Fixed
- **PLOTFILE and POSTFILE wrote a field AERMOD does not have.** Both
  carried an output-type token (`CONC`, `DDEP`, ...), and PLOTFILE also
  wrote a rank on the PERIOD/ANNUAL form, which takes none. AERMOD
  counts fields: the result was a fatal "Too Many Parameters Specified
  For the Keyword of PLOTFILE" and "Invalid Parameter Specified.
  Troubled Parameter: FORMAT". There is no per-file output type in
  AERMOD -- the quantity written is a MODELOPT setting -- so
  `OutputPathway.output_type` is now documented as inert and no longer
  emitted.
- **The reader read the PLOTFILE rank as the filename.** It took a fixed
  field position, so a PERIOD-form plotfile round-tripped
  `plot_file="p.dat"` into `plot_file="FIRST"`.
- **`RECTABLE ALLAVE 10` asks AERMOD for the tenth-highest value alone,
  not the top ten.** `receptor_table_rank=10` therefore produced a table
  of one rank, and any PLOTFILE requesting FIRST against it was rejected
  as an invalid HIVALU. The writer now emits the range form
  (`ALLAVE 1-10`), and the reader understands bare ranks, ranges and the
  ordinal-word forms (`FIRST-THIRD`, `EIGHTH`) alike -- it previously
  fell back to the default rank for all but a bare number.

- **Three of the ten source types produced decks AERMOD rejects.**
  Verified against the real binary's setup pass:
  - `AREAPOLY` wrote its `LOCATION` at the polygon *centroid* while
    AERMOD requires the first vertex ("ARVERT: First Vertex Does Not
    Match LOCATION"), and omitted the vertex count from `SRCPARAM`,
    which is a fatal "Not Enough Parameters" and then makes every
    `AREAVERT` line overflow an unset limit. Four distinct fatal errors
    from one source.
  - `BUOYLINE` wrote `BLPINPUT` with no group ID, so AERMOD filed the
    parameters under the implicit group `ALL` and then failed with "No
    BLPINPUT record for BLPGROUP ID".
  - `RLINEXT` needs `MODELOPT ... ALPHA`, which `ControlPathway` had no
    way to emit.
- **The reader silently dropped AREAPOLY, RLINEXT and BUOYLINE
  sources.** `parse_aermod_input` returned successfully with an empty
  source list -- no error, no warning -- so a project could lose its
  emissions with nothing to show for it. All three are now
  reconstructed, including `AREAVERT` vertex rings and the
  `BLPINPUT`/`BLPGROUP` pairing that turns buoyant line *segments* back
  into a source. All ten source types now round-trip.

- **AERSURFACE decks used keywords AERSURFACE does not have.**
  `AERSURFACEConfig.to_aersurface_input()` emitted `TITLE`, `LOCATION`,
  `NLCDFILE`, `NLCDYEAR`, `SNOW_TEMPER`, `SECTORS_LIST`, `OUTPATH` and
  friends -- none of which exist. The real format is pathway-based
  (`CO STARTING` / `OU STARTING`) with `TITLEONE`, `CENTERLL`,
  `DATAFILE`, `ZORADIUS`, `CLIMATE`, `FREQ_SECT`, `SECTOR`, `SEASON`,
  `RUNORNOT`, `SFCCHAR`. Fed the old deck, AERSURFACE v26135 aborted
  immediately with a Fortran bounds error in its control-file parser.
  Rewritten to the real format, with sectors as
  `(start, end, "AP"|"NONAP")` triples, season-to-month assignment
  (including `WINTERWS` for continuous snow cover), and the canopy and
  impervious rasters that 2001-and-later NLCD releases carry. This is a
  breaking change to `AERSURFACEConfig`'s fields; the class never
  produced a usable deck, so no working code depended on them.
- **BPIP reported downwash where EPA reports none.** `BPIPCalculator`
  had no structure-influence-zone test, so a stack 400 m from a 13 m
  building came back with a full-size building for all 36 directions
  instead of zeros -- enough to make AERMOD apply downwash the GEP
  criteria exclude.
- **BPIP's XBADJ and YBADJ were the projected centroid.** XBADJ is the
  along-flow coordinate of the projected building's *upwind face*
  (`-BUILDLEN/2` for a stack at the building centre, where the old code
  returned 0) and YBADJ the negated crosswind midpoint. The rotation
  also ran the wrong way, which an axis-aligned rectangle cannot reveal
  because its projected width and length are symmetric in wind
  direction.
- **`Building` rejected any footprint that was not a quadrilateral**,
  including the six-corner L-shape in EPA's own first BPIP test case.
  Any polygon of three or more corners is accepted.

- **NAAQS percentiles were interpolated quantiles, not the regulatory
  order statistics.** `pm25_24hr_design_value`, `no2_1hr_design_value`
  and `so2_1hr_design_value` computed the annual percentile with
  `Series.quantile(..., interpolation="linear")`. The standards do not
  interpolate: 40 CFR part 50 appendices N, S and T sort each year's
  daily values from highest to lowest and read the rank off a table keyed
  on the year's count of valid days — the **8th highest** for a full-year
  98th percentile, the **4th highest** for a full-year 99th percentile.
  Linear interpolation lands *between* ranks (0.98 × 364 = 356.72) and
  reports a number the regulation never defines, biased low against the
  standard. Now rank-based, with the rank chosen per receptor-year from
  that year's own day count.
- **PM2.5 and PM10 24-hour design values used each day's peak hour as the
  24-hour value.** Both functions called the daily-*maximum* helper on
  hourly input, despite the docstring promising an average. A day with
  one hour at 240 µg/m³ and 23 hours at zero was scored as 240 rather
  than 10. Hourly input is now averaged over the day for the 24-hour
  standards; input already carrying AERMOD `AVE='24-HR'` block averages
  is unchanged.
- **The PM10 24-hour form ignored the multi-year window.** It always
  returned the high-second-high and left averaging to the caller. It now
  follows Appendix W Table 8-2: the highest *sixth*-high (H6H) of the
  pooled record when five years are modelled, H2H otherwise, overridable
  via `rank=`. Unlike the percentile standards this form is not averaged
  across years.
- **Design values silently pooled source groups and duplicated
  receptors.** A POSTFILE holding several `SRCGROUP`s was ranked as one
  mixed series; the functions now require a single group and say how to
  filter. A deck that declares the same receptor twice (EPA's own
  `surfcoal` does) made the 2nd-highest value a copy of the 1st —
  repeated rows are now collapsed, and receptors that genuinely share
  (x, y) but differ in concentration raise instead of being merged.
- **`naaqs_percentile_rank` boundary rounding.** The rank is computed in
  exact rational arithmetic: `math.ceil(0.02 * 50)` is 2 in binary
  floating point, which would put a 50-day year on the second-highest
  value where appendix S Table 1 says the highest. Caught by the new
  table test.
- **`get_naaqs("Pb", ...)` always raised `KeyError`.** The lookup
  upper-cased the caller's string, and `"Pb".upper()` is not the table
  key `"Pb"`. Lookup is now case-insensitive and the error lists the
  available pollutants.
- **Every AERMOD PLOTFILE from a deposition run was unreadable.**
  `read_plotfile` detected the file type from the first header line
  mentioning one, which is `MODELING OPTIONS USED: ... DDEP WDEP ...` —
  so a deposition run's plotfile was classified `DDEP` and rejected. The
  options line is now excluded and the `"<kind> FILE OF ..."` declaration
  wins. Seven of EPA's reference plotfiles were affected.
- **Auxiliary-file column labels were shifted by one for every real
  AERMOD output.** The header line was split on any whitespace, so
  AERMOD's two-word labels `AVERAGE CONC` and `NET ID` each became two
  columns and every label after them named the wrong data. Labels are
  now split on two-or-more spaces, and rows are sliced using the Fortran
  FORMAT AERMOD prints in the header — which is also the only way a
  blank trailing `NET ID` (discrete receptors) parses as blank instead of
  pulling every later column one place left.

- **EPA fixture tests skipped silently after EPA renamed the archive sets.**
  `tests/test_epa_cases.py` looked only at a hard-coded Dropbox path, and
  `tests/regulatory/` plus `tests/test_real_cases.py` at the pre-2026
  `aermet_24142_aermod_24142` name, so with the current EPA bundle unpacked
  every one of them still skipped (the file-parametrised cases did not even
  collect). With the resolver and the archive present they collect as
  350 / 54 / 323 tests; regulatory: 47 passed / 7 skipped against a compiled
  v26135; the two parser modules: 673 passed against the 24142 set (after
  the phantom-4HR fix below). Those two modules skip, with the discovered
  set named in the reason, when only another AERMOD version is present —
  their assertions quote 24142 values.
- **Phantom `4HR` averaging period in `AERMODOutputParser`.** The `4-HR`
  section pattern also matched inside `24-HR` headers, so every run with a
  24-hour average gained a bogus `4HR` result duplicating the 24-hour table
  (surfaced by `tests/test_epa_cases.py` on AERTEST and FLATELEV once those
  tests ran). Period patterns are now anchored (`(?<![0-9])(?:...)`) so they
  cannot start inside a longer number. Wrapping the alternation in a group
  fixes a second latent bug: interpolated bare, `24-HOUR|24HR|24-HR` split
  the *surrounding* section regex into three top-level branches, so only the
  last spelling carried the `RESULTS` tail and the capture group and the
  other two matched with `group(1) is None` — the `X-HOUR` and `XHR`
  spellings never selected a table. No shipped result changes: AERMOD only
  ever writes the `X-HR` spelling in its section headers (checked across
  every `.out`/`.SUM` in EPA's v26135 archive), so the broken branches were
  unreachable in practice. Regression in
  `tests/test_output_parser_periods.py`.
- **`AERMODOutputParser` effectively hung on multi-MB `.out` files.** The
  second, free-form section pattern
  (`\*\*\*.*?<period>.*?RESULTS.*?\*\*\*…`, `re.DOTALL`) backtracks from
  every `***` in the file out to EOF, and `parse()` tries all eleven period
  patterns against every output — so on EPA's 2.3 MB `allsrcs.out` a single
  *absent* period cost ~291 s in that pattern (the first, line-anchored
  pattern rejects the same input in 0.014 s).
  `tests/test_epa_cases.py::TestOutputParserEdgeCases` never got past
  `allsrcs.out`. Both section patterns require the period token to occur
  somewhere, so `_parse_concentration_table` now returns `None` early after
  one linear `re.search` for it — equivalent by construction, and it turns
  the pathological case into a single scan. `allsrcs.out`: no completion in
  over six minutes → 0.30 s; the whole EPA `.out` set parses in under a
  second per file.
- **`tests/test_source_importers.py` skipped entirely whenever `ezdxf` was
  absent** — a module-level `pytest.importorskip("ezdxf")` hid the seven
  geopandas shapefile tests too. The skip is now a class-scoped fixture on
  `TestDxfImporter` only; the shapefile tests run wherever geopandas is
  installed (`source_importers.py` coverage 11.8 % → 52.8 % in the local
  env). All five shapefile fixtures now write through one `_write_shapefile`
  helper — three of them still called `gdf.to_file` directly — which falls
  back to writing the layer through fiona (no `.prj`, which the importers do
  not read) if geopandas' writer raises pyproj's `Invalid value supplied
  'WktVersion.WKT2_2019'`. That is a defensive guard, not a live workaround:
  it was seen once under coverage tracing but does not reproduce on the
  current pin (geopandas 0.14.4, fiona 1.9.6, pyproj 3.6.1, coverage
  7.13.3), where `to_file` succeeds for all six writes and the fallback is
  never entered.
- **`AERMODRunner._extract_error_message` swallowed read errors** around the
  `.err`/`.out` files (`except Exception: pass`), so a Latin-1 byte in
  AERMOD's output — a degree sign in the banner is enough — raised
  `UnicodeDecodeError` and the caller saw only "AERMOD failed with return
  code N" instead of the `FATAL` line. Both files are now read as Latin-1
  with replacement, only `OSError` is tolerated, and that is logged at
  DEBUG. Tests cover non-UTF-8 bytes in both files and the logged fallback.
- **GUI v2 Run/Results/editor crashes found by the new smoke tests:**
  - the Run button always raised `ImportError` (`from ..._optional import
    HAS_TERRAIN` — no such name), so AERMOD could never be launched from the
    GUI; the stray import is removed;
  - the Run tab wrote its deck as `aermod.inp`, the name `AERMODRunner`
    reserves for the symlink it points at the deck — the runner unlinked the
    deck and replaced it with a self-referencing symlink, and then failed
    renaming `aermod.out` onto itself. The deck is now written as
    `pyaermod_gui.inp`;
  - the Results tab read `run_info.title` / `.pollutant` and iterated
    `results.concentrations` as a list of objects with `max_x` / `max_y` /
    `source_group`; the parser provides `jobname` / `pollutant_id`, a
    `{period: ConcentrationResult}` mapping and a `max_location` tuple, so any
    real output raised `AttributeError`;
  - the source/receptor editor dialog crashed (`float() argument ... not
    'list'`) for every source with polygon `vertices`, because the form
    helper's numeric check was a substring test that claimed
    `List[Tuple[float, float]]` — and silently rendered
    `Optional[Tuple[DepositionMethod, float]]` as a number box, letting a
    float be written into a tuple-typed field. `is_numeric` now resolves the
    annotation (`typing.get_type_hints`, `get_origin`/`get_args`, unwrapping
    `Optional`/`Union`, with a structural parser for unresolvable string
    annotations) and is true only when the type *is* `int`/`float`,
    optionally with `None`; list annotations are still dispatched first;
  - tightening `is_numeric` then made the five building-downwash dimensions
    (`building_height`, `building_width`, `building_length`,
    `building_x_offset`, `building_y_offset` on the point/volume/area
    sources) uneditable: they are `Optional[Union[float, List[float]]]`,
    which is correctly *not* numeric, and fell through to the read-only-label
    escape hatch, so a building height could no longer be typed at all.
    `emit_field` now dispatches these on the current value — a number box
    (clearable) while the field holds a scalar or nothing, the one-per-line
    list editor once it holds a 36-sector vector — so neither shape is
    thrown away. Clearing either widget stores `None` rather than `0.0` or
    `[]`: the writer emits the keyword for any non-`None` value, and an
    empty list is rejected as "not 36 values";
  - `Optional[str]` fields (e.g. `OutputPathway.summary_file`) were rendered
    as read-only labels instead of text inputs.
- **`AERMAPRunner.run` passed the input file *stem* instead of its full
  name** as AERMAP's command-line argument, so AERMAP could not locate the
  runstream and exited without processing (still returning code 0) — runs
  silently produced no output. Now passes the full filename.
- **Title round-trip** — `ControlPathway.to_aermod_input()` now normalizes
  `TITLEONE`/`TITLETWO` whitespace (collapsing leading/trailing/internal runs)
  to match how AERMOD's free-form, unquoted runstream parser reads titles back.
  Previously a title with surrounding or doubled spaces was emitted verbatim
  but re-read collapsed, so `write -> read` was not a fixed point. The
  property-based round-trip strategy is restricted to the representable
  (normalized, non-empty) title domain accordingly.

## [2.0.0] - 2026-05-04

The deprecation-cleanup major release. **Breaking changes** — read the
upgrade notes below before upgrading.

### Removed

- **Streamlit GUI** — the legacy `pyaermod.gui` module, the
  `pyaermod-gui` console script, the `_gui_runner.py` shim, and the
  full `tests/test_gui.py` (~920 lines) are gone. The replacement is
  the NiceGUI app shipped in v1.9 (`pyaermod-app` browser mode,
  `pyaermod-desktop` native window).
- **`gui` extra** as a Streamlit alias.
- **`gui-modern` / `gui-modern-desktop` extras** — renamed (see below).
- **`pyaermod-gui` console script.**

### Renamed

- **Extras**:
  - `gui-modern`        →  `gui`         (NiceGUI, browser mode)
  - `gui-modern-desktop` →  `gui-desktop` (NiceGUI + pywebview, native)
- The `all` extra now includes `nicegui` instead of Streamlit.

### Changed (breaking)

- **`AERMODProject.to_aermod_input()` and `.write()` validate by default.**
  The deprecation cycle landed in v1.5 (DeprecationWarning when
  `validate=` is omitted). v2.0 flips the default from `False` to `True`.
  Pass `validate=False` explicitly to skip validation if your tests or
  scripts construct intentionally-incomplete projects.

### Upgrade notes

Most users only need to change one thing:

```bash
# Old
pip install pyaermod[gui]
pyaermod-gui

# New
pip install pyaermod[gui]
pyaermod-app             # browser
pyaermod-desktop         # native window
```

If you scripted `to_aermod_input()` without `validate=`, your code now
runs the validator before generating the deck. To preserve the v1.x
behaviour:

```python
project.to_aermod_input(validate=False)
```

If you imported anything from `pyaermod.gui`, switch to
`pyaermod.gui_v2`. The public API (`AppState`, `save_project`,
`load_project`, page render functions) is documented in
[the gui_v2 reference](api/gui_v2.md).

## [1.9.0] - 2026-05-04

### Added — NiceGUI app + desktop bundles

The NiceGUI-based GUI v2 ships alongside the legacy Streamlit GUI for
the entire 1.9.x cycle. The Streamlit GUI is **deprecated** in favour
of NiceGUI; it will be removed in v2.0. Both are functional today.

#### Five-stage delivery

- **WP-1.9-A**: scaffold + project I/O. ``AppState`` per-session
  state dataclass, ``project_io.{save,load}_project`` JSON
  round-trip, ``app.{build_app,build_and_run}`` shell, fully
  rendered Project tab, placeholder banners for the other six tabs.
  New ``pyaermod-app`` and ``pyaermod-desktop`` console scripts.
- **WP-1.9-B**: Sources tab. Generic dataclass-field-walker emits
  the right widget per field annotation (str → input, float/int →
  number, bool → checkbox, vertices → textarea round-trip). One
  generic form covers all 10 source types.
- **WP-1.9-C**: Receptors + Meteorology tabs. Field-form helper
  extracted to ``pyaermod.gui_v2._form`` so every page is a thin
  list-of-fields shim. Receptors covers all 3 receptor types
  (Cartesian / Polar / Discrete); Meteorology splits primary vs.
  advanced fields under an expansion panel.
- **WP-1.9-D**: Output + Run + Results tabs. Run dispatches
  AERMOD via :class:`AERMODRunner`, captures stdout / stderr
  tails, and stamps :attr:`AppState.last_run_dir`. Results parses
  the .OUT file via :class:`AERMODOutputParser`, shows run info
  + sources + max concentrations + POSTFILE listing.
- **WP-1.9-E**: PyInstaller bundles for Win/Mac/Linux.
  ``packaging/pyaermod_desktop.spec`` plus a release-tag-triggered
  GitHub Actions workflow that builds the bundle on each OS and
  attaches the artifacts to the GitHub Release. ``docs/desktop.md``
  for end-user installation.

#### New extras

- ``pyaermod[gui-modern]`` — NiceGUI only (browser tab mode)
- ``pyaermod[gui-modern-desktop]`` — NiceGUI + pywebview (native
  desktop window)

#### New console scripts

- ``pyaermod-app`` — launches NiceGUI in a browser tab
- ``pyaermod-desktop`` — launches NiceGUI inside a pywebview window

### Changed

- Coverage gate continues at 95%. ``gui_v2/`` modules are excluded
  from coverage measurement (mirroring how ``gui.py`` was excluded
  for Streamlit) — UI render code is exercised end-to-end during
  manual QA, not unit-tested.

### Deprecated

- The Streamlit GUI (``pyaermod-gui`` / ``pyaermod.gui``) is
  deprecated in favour of NiceGUI. Functionality is unchanged in
  1.9.x; removal is planned for v2.0.

## [1.8.0] - 2026-05-04

### Added

#### WP-A: AERSCREEN wrapper
- `pyaermod.aerscreen.AERSCREENConfig` dataclass + `AERSCREENSourceType`
  StrEnum (POINT, FLARE, AREA, VOLUME, CAPPED, HORIZONTAL) with full
  per-source-type validation. Optional building downwash, terrain
  (lat/lon + DEM file), urban dispersion (population), Auer landuse
  code, and explicit-or-AUTO downwind distance scheme.
- `pyaermod.aerscreen_runner.AERSCREENRunner` mirroring the AERSURFACE
  runner pattern: stages `aerscreen.inp` in cwd, file-redirected
  stdout/stderr (pipe-deadlock safe), FATAL-in-output detection.
- pyaermod now wraps the **complete** EPA AERMOD family: AERMOD,
  AERMET, AERMAP, AERSURFACE, AERSCREEN, BPIP-PRIME.

#### WP-B: SHP + DXF source importers
- `pyaermod.source_importers.from_shapefile()` — imports any
  geopandas-readable file (.shp, .gpkg, .geojson) into pyaermod
  source dataclasses. Default geometry mapping: Point → PointSource,
  Polygon → AreaPolySource, LineString → LineSource. Override via
  `source_type=` (e.g. `RLineSource` for road centerlines). Optional
  `attribute_map=` for renaming truncated/cryptic shapefile columns.
- `pyaermod.source_importers.from_dxf()` — imports AutoCAD DXF
  (POINT, LINE, LWPOLYLINE, POLYLINE, CIRCLE entities). Closed
  polylines → AreaPoly, open → Line. Circles discretized to
  16-vertex polygons. Optional `z_as_height=True` uses DXF z
  elevation as stack/release height (rooftop emission models).
- New `pyaermod[cad]` optional extra: `ezdxf>=1.0.0` (~5 MB, MIT,
  pure Python). Added to the `all` extra.

## [1.7.0] - 2026-05-04

### Added — "Regulatory-grade open source"

#### WP-1: EPA AERMOD test-suite parity harness
- `pyaermod.regulatory_parity` module with `score_postfile_pair()` and
  `passes_parity()` helpers; pass criterion is best-fit slope within
  ±0.001 of 1.0 — the same margin EPA's own
  `Compare_AERMOD_test_cases.R` script publishes.
- Parametric pytest harness in `tests/regulatory/` covering all 41
  EPA AERMOD test decks plus the 5-year MULTYEAR PM-10 chain.
- Reproducible parity report at `docs/validation.md`:
  **104 / 104 POSTFILE comparisons within EPA tolerance.**
- `.github/workflows/epa_parity.yml` — workflow_dispatch CI job that
  compiles AERMOD from EPA source, fetches the test-case bundle, runs
  the harness, and uploads the rendered report.
- `scripts/run_epa_parity.py` for local report regeneration.

#### WP-2: AERSURFACE wrapper
- `pyaermod.aersurface.AERSURFACEConfig` dataclass with full validation
  (NLCD-year whitelist, snow-regime enum, per-month moisture / snow-cover
  lists, sector angles).
- `pyaermod.aersurface_runner.AERSURFACERunner` mirroring the AERMET
  runner pattern: stages `aersurface.inp` in cwd, file-redirected
  stdout/stderr, FATAL-in-output detection.
- pyaermod now wraps every preprocessor in the EPA AERMOD chain
  (AERMET, AERMAP, AERSURFACE, BPIP).

#### WP-3: Design-value / NAAQS post-processing
- `pyaermod.naaqs` reference table: PM2.5, PM10, NO2, SO2, CO, O3, Pb
  with 40 CFR Part 50 citations. PM2.5 annual reflects the 2024 EPA
  review (9.0 µg/m³).
- `pyaermod.design_values` design-value computations:
  `pm25_24hr_design_value`, `no2_1hr_design_value`,
  `so2_1hr_design_value`, `pm10_24hr_design_value`,
  `o3_8hr_design_value`, `annual_mean`, `add_background`,
  and the one-stop `naaqs_compliance_report()` dispatcher.
- Every function cites its 40 CFR Part 50 reference in its docstring.

#### WP-4: KMZ / Google Earth exporter
- `pyaermod.kmz_export.to_kmz()` — zero-dependency Google Earth
  exporter built on stdlib `zipfile` + `xml.etree`. Folders for
  Sources, Receptors, and Contours, each pre-styled.
- Optional pyproj-driven UTM → WGS84 reprojection.
- `ContourPolygon` dataclass for caller-supplied contour rings
  (interoperates with `geospatial.generate_contours`).

## [1.6.0] - 2026-05-04

### Robustness pass (items A–H)

#### Added
- **Path-traversal sandbox**: `read_aermod_input(path, sandbox=True)` raises
  `PathTraversalError` when referenced files (SURFFILE, PROFFILE, OZONEFIL,
  postfile, plot/summary/max files) escape the deck's parent directory.
- **Concurrent-run lock**: `AERMODRunner` acquires an fcntl/msvcrt advisory
  lock on the working directory so parallel jobs don't clobber each other.
- **Coverage gate**: CI fails below 95% (`--cov-fail-under=95`).
- **Benchmark regression gate**: PR benchmarks fail on >25% regression vs main.
- **Hypothesis fuzz tests**: property-based coverage on the input reader.
- **Advisory mypy step** in CI (Python 3.12, `continue-on-error`); baseline
  68 errors logged as a notice for ratcheting toward strict mode.
- **Salem stage-1 end-to-end test** for AERMET when EPA fixtures are present.

#### Changed
- **AERMET runner**: stages the deck as `aermet.inp` in the cwd before
  invoking the binary — AERMET v24142 reads from a fixed filename, not stdin.
  The previous stdin approach silently failed on the real binary.
- **Pipe-fix parity**: AERMET and AERMAP runners now redirect stdout/stderr
  to files (matching the AERMOD runner), avoiding 64 KB pipe-buffer deadlocks
  on chatty runs.
- **`validate=` deprecation**: `AERMODProject.to_aermod_input()` and
  `.write()` now emit a `DeprecationWarning` when `validate=` is omitted.
  In 2.0 the default flips from `False` to `True`. Pass `validate=True` or
  `validate=False` explicitly to silence the warning.

## [1.0.0] - 2026-02-14

### Added

#### Source Types
- **AreaSource** — rectangular area sources with rotation angle
- **AreaCircSource** — circular area sources with configurable vertex count
- **AreaPolySource** — irregular polygonal area sources
- **VolumeSource** — 3D emission volumes with initial dispersion
- **LineSource** — general linear sources (conveyors, pipelines)
- **RLineSource** — roadway-specific sources with mobile source physics
- **RLineExtSource** — extended roadway with per-endpoint elevations, optional barriers and road depression
- **BuoyLineSource** / **BuoyLineSegment** — buoyant line source groups with BLPINPUT/BLPGROUP
- **OpenPitSource** — open pit mine/quarry sources

#### Modules
- **Validator** (`pyaermod.validator`) — configuration validation for all 5 AERMOD pathways with cross-field checks
- **BPIP** (`pyaermod.bpip`) — building downwash / BPIP integration with 36-direction building parameters
- **AERMET** (`pyaermod.aermet`) — meteorological preprocessor input generation (Stages 1-3)
- **AERMAP** (`pyaermod.aermap`) — terrain preprocessor input generation with `from_aermod_project()` bridge
- **POSTFILE** (`pyaermod.postfile`) — POSTFILE output parser with timestep/receptor queries, auto-detection of text (PLOT) and binary (UNFORM) formats
- **Geospatial** (`pyaermod.geospatial`) — coordinate transforms (UTM/WGS84), GeoDataFrame creation, contour generation, GeoTIFF/GeoPackage/Shapefile/GeoJSON export
- **Terrain** (`pyaermod.terrain`) — DEM tile download from USGS TNM, AERMAP runner, output parser, elevation update pipeline
- **GUI** (`pyaermod.gui`) — 7-page Streamlit web application for interactive AERMOD workflow

#### Background Concentrations
- `BackgroundConcentration` and `BackgroundSector` dataclasses for ambient background levels
- Three modes: uniform value, period-specific values, or sector-dependent concentrations
- `SourcePathway.background` field generating `BACKGRND` and `BGSECTOR` keywords

#### Deposition Modeling
- `DepositionMethod` enum (`DRYDPLT`, `WETDPLT`, `GASDEPVD`, `GASDEPDF`)
- `GasDepositionParams` and `ParticleDepositionParams` for gas and particle deposition settings
- Deposition fields added to all 10 source types with shared `_deposition_to_aermod_lines()` helper
- `OutputPathway.output_type` for selecting concentration vs. deposition output

#### EVENT Processing
- `EventPeriod` and `EventPathway` dataclasses for event-based analysis
- `ControlPathway.eventfil` for linking event file
- `AERMODProject.write(event_filename=...)` generates EV pathway with `EVENTPER` records

#### NO2 / SO2 Chemistry Options
- `ChemistryMethod` enum: OLM, PVMRM, ARM2, GRSM
- `ChemistryOptions` dataclass with method, default NO2/NOx ratio, and ozone data
- `OzoneData` dataclass supporting ozone file, uniform value, or sector-specific values
- `ControlPathway.chemistry` field generating `MODELOPT`, `O3VALUES`, `OZONEFIL`, `NOXFIL` keywords
- Per-source `no2_ratio` field on `PointSource`

#### Source Group Management
- `SourceGroupDefinition` dataclass with group name, member source IDs, and description
- `SourcePathway.group_definitions` generating `SRCGROUP` keywords
- Per-group PLOTFILE output via `OutputPathway.plot_file_groups`

#### Building Downwash Expansion
- Building downwash (PRIME) fields extended from `PointSource` to also support `AreaSource` and `VolumeSource`
- `_building_downwash_lines()` and `_set_building_from_bpip()` module-level helpers shared across source types
- Terrain grid elevations via `CartesianGrid.terrain_elevations` and `PolarGrid.terrain_elevations`

#### Binary POSTFILE Deposition
- `UnformattedPostfileParser` now handles deposition records with `has_deposition` parameter (auto-detect or explicit)
- Parses 3N floats into concentration, dry deposition, and wet deposition columns

#### GUI Enhancements
- **ProjectSerializer**: JSON save/load for complete session state with round-trip fidelity
- **AreaCirc/AreaPoly forms** in SourceFormFactory
- **BPIP integration**: building forms, BPIP calculator wired to point, area, and volume sources
- **AERMAP elevation import**: 5th tab in receptor editor for terrain elevation upload
- **AERMET configuration**: dual-mode meteorology page (existing files vs. 3-stage AERMET config)
- **POSTFILE viewer**: 4th tab in Results Viewer with timestep slider, receptor time-series, animation GIF
- **Chemistry Options UI**: NO2 chemistry configuration with method, ozone data, and NOx file inputs
- **Source Groups UI**: create/delete source groups, per-group PLOTFILE checkboxes
- **Statistics helpers**: cross-period summary table, ranked receptor table, model complexity indicator
- **Export format detection**: dynamic format list based on installed optional dependencies

#### Testing & Quality
- 1166 tests across 18 test files, 95% code coverage
- 315 EPA v24142 integration tests parsing official test case outputs
- End-to-end mock pipeline tests (input generation → output parsing → visualization → postfile)
- `conftest.py` with shared fixtures for all test files
- Property-based testing with Hypothesis strategies for source types
- `ruff` linting (replaced flake8) with comprehensive rule set
- `.pre-commit-config.yaml` for automated lint on commit
- Performance benchmarks in `benchmarks/` directory

#### Documentation
- 7 Jupyter tutorial notebooks (Getting Started through Advanced Features)
- 7 example scripts (area sources, volume sources, line sources, BPIP, chemistry, deposition, end-to-end)
- MkDocs documentation site with Material theme and mkdocstrings API reference

### Changed
- **Package layout**: moved from flat root modules to `src/pyaermod/` package structure
- **Imports**: `from pyaermod.input_generator import ...` (was `from pyaermod_input_generator import ...`)
- **Python**: minimum version raised to 3.11 (was 3.8) — required by NumPy 2.1+, SciPy 1.14+, Pandas 2.3+
- Updated `setup.py` extras: added `[geo]`, `[gui]`, `[terrain]`, `[all]` dependency groups
- CI matrix runs Python 3.11, 3.12, 3.13 with GDAL system dependencies

## [0.1.0] - 2026-02-04

### Added
- **PointSource** with full stack parameters and building downwash (PRIME) support
- **Receptor grids**: Cartesian, polar, and discrete receptors
- **AERMOD input generation** for all 5 pathways (CO, SO, RE, ME, OU)
- **Output parser**: parse `.out` files to pandas DataFrames, extract metadata, find max concentrations
- **Visualization**: contour plots (matplotlib), interactive maps (folium)
- **Runner**: `AERMODRunner` with subprocess execution, `BatchRunner` for parallel processing
- Project setup: `setup.py`, MIT license, `.gitignore`

---

[Unreleased]: https://github.com/atmmod/pyaermod/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/atmmod/pyaermod/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/atmmod/pyaermod/releases/tag/v0.1.0
