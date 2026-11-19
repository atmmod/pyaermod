# docs-accuracy findings (reviewer: docs-accuracy)

Pages FULLY checked (every code block run or read, quoted messages and names grepped against code):
README.md, docs/index.md, docs/quickstart.md, docs/install.md, docs/architecture.md, docs/common-errors.md,
docs/regulatory-matrix.md, docs/aermet-tuning-guide.md, docs/aermap-troubleshooting.md (deck output reproduced byte-for-byte),
docs/api/index.md, CONTRIBUTING.md, RELEASING.md, docs/desktop.md, docs/browser.md.
Checked in depth but not every sentence: docs/gui-guide.md (all quoted UI strings, defaults, limits grepped against gui_v2/*; all matched),
docs/ensemble.md (signatures and constants; the measured timings not re-run), docs/benchmarks.md (flags, files, runner behaviour; numbers not re-run).
SAMPLED only: docs/use-cases.md (its ten scripts are embedded from examples/use_cases and run by tests/test_use_cases.py; I checked the
imported names and the prose claims about fields, not the quoted result numbers), docs/psd.md (blocks run OK; Fortran constants spot-checked),
docs/validation.md (generated report; 142/142 matches 142 rows), docs/design-value-validation.md (numbers in tests not re-run).
Coverage of tests/test_docs_examples.py: only quickstart.md and docs/teaching/student-guide/*.md. All other pages' Python blocks are untested.
I executed every other page's python blocks (repro/docs-accuracy/run_blocks.py): failures were only blocks needing files/AERMOD, the
`--8<--` includes in use-cases.md (not expanded by my runner), or the real findings below.
Earlier reviews (.10x/reviews/2026-11-11, 2026-11-17): no docs items there; nothing to carry over.

### DOCS-1 [DOCS] [high] aermet-tuning-guide's QA workflow fails on every .SFC it reads
- Where: docs/aermet-tuning-guide.md:85-99 (QA section) and :143-170 (Recommended workflow, step 4); code src/pyaermod/met_qaqc.py:139,205,222,265,319
- What: the page tells the reader to run `records = read_surface_file("stn.sfc")["data"].to_dict("records"); run_all_qaqc(records)`. The page itself admits (line 101-105) that run_all_qaqc then "reports every field as missing", and the "Recommended workflow" snippet repeats the failing call without the rename and ends with `if report.n_errors: raise SystemExit(...)`, so the recommended script aborts on every good met file.
- Evidence: VERIFIED, repro/docs-accuracy/qaqc.py on tests/fixtures/postfile_types/HOUSTON_0228.SFC: columns are wind_speed, temp, L, Zic...; qaqc looks up wind_speed_ms, temp_c, monin_obukhov_m. Output: "4 records, 4 missing (100.0%), 3 errors" ([ERROR] missing wind_speed_ms, temp_c; low_wind: no valid wind_speed_ms).
- Fix: either map the columns in the snippet (rename wind_speed->wind_speed_ms, temp->temp_c (check units: .SFC temp is K, met_ingest temp_c is C), L->monin_obukhov_m ...) or, better, make run_all_qaqc accept the .SFC names, then delete the paragraph that admits the mismatch. Until then the workflow's step 4 must not raise on n_errors.

### DOCS-2 [BUG/DOCS] [high] `AERMODProject.write()` empties the existing file before it refuses an invalid project; docs say it "refuses"
- Where: src/pyaermod/input_generator.py:254-290 (`with open(output_path,'w') as f: f.write(self.to_aermod_input(...))`); docs claim at docs/quickstart.md:~325 ("`project.write()` checks the project ... and refuses one AERMOD would stop on"), docs/common-errors.md:21-25, docs/architecture.md:33
- What: the file is opened for writing (truncated) before `to_aermod_input()` runs validation. A refused write therefore destroys a previously good deck at that path (the usual edit-and-rewrite workflow of read_aermod_input -> change -> write("same.inp")).
- Evidence: VERIFIED, repro/docs-accuracy (inline script): existing bad.inp containing "OLDCONTENT", `_empty_project().write("bad.inp")` raises ValueError and bad.inp is then 0 bytes. Also creates parent dirs/empty file for a project that fails.
- Fix: build `text = self.to_aermod_input(...)` first (and the event text), then open and write. The docs sentence then becomes true as written.

### DOCS-3 [DOCS] [high] common-errors.md documents an AERMOD error code that does not exist: "ERRMSG.TMP has E101 = missing input or met file"
- Where: docs/common-errors.md:131-137 (heading, anchor {#e101})
- What: AERMOD has no code 101 (aermod/modules.f ERRCOD list goes 100, 105, 109, ...). A missing met file gives E500 (documented 40 lines later, modules.f:3049), a missing aermod.inp is a Fortran open failure with no E-code (aermod.f:83). Nothing in src/ or docs links to #e101.
- Fix: delete the section, or retitle "Immediate crash: missing deck" and say AERMOD stops with a Fortran open error; point missing met files to E500. `Validator.validate(project, check_files=True)` advice can stay.

### DOCS-4 [DOCS] [medium] common-errors.md "Cryptic Fortran crashes" table lists four messages AERMOD never prints
- Where: docs/common-errors.md:233-238 (table)
- What: `** FATAL ** negative U*`, `** FATAL ** bad mixing height`, `*** ERROR *** XY array out of bounds`, `*** ERROR *** pollutant not recognized` appear nowhere in aermod/*.f (grep -i "negative U\*|bad mixing|XY array|pollutant not recog" -> no hits). AERMOD's messages are "XX Ennn line N MODNAM: text" (see the E480/E500 sections of the same page). A reader grepping their .out for these strings finds nothing; the causes given are guesses.
- Fix: replace the table with real codes (e.g. E350/E3xx met-data messages from modules.f) or delete it.

### DOCS-5 [DOCS] [medium] common-errors.md: two "input-generation errors" are not messages pyaermod emits
- Where: docs/common-errors.md:13-17 ("averaging period not supported for pollutant"), :13 ("validator.py line ~195"), :183-188 ("ANNUAL average requested, ran for single day")
- What: (a) no such validator message exists (grep "not supported for" in src/: none) and nothing rejects ANNUAL for a "1-hour-designed" pollutant (SO2/PM25 with ["ANNUAL","24"] validates; the only pollutant-dependent period check is MAXDAILY et al., validator.py:2216-2224, E162/E163). (b) the duplicate-source check is at validator.py:314-321, not ~195 (stale line number). (c) the real text is "ANNUAL averaging requested but met range is a single day (...)" (validator_advanced.py:309-314).
- Fix: delete (a) or replace with the E162/E163 MAXDAILY message; change (b) to "validator.py, `_validate_sources`" without a line number; quote (c) correctly.

### DOCS-6 [DOCS] [medium] regulatory-matrix.md: the profile API does not check NOSTD/LOWWIND1/2/FLAT/BETA flags, and the page says it "automates most of these"
- Where: docs/regulatory-matrix.md:3-5, :14 (Stack-tip downwash row), :16, :74-82 (custom profile), :90-92; code src/pyaermod/regulatory.py:81-87 (forbid_nondefault_flags), validator_advanced.py:251-262 (NONDEFAULT_OPTION_FLAGS)
- What: both lists name ControlPathway attributes `flat_terrain`, `no_stack_tip_downwash`, `use_lowwind1`, `use_lowwind2`, `use_lowwind3`, `beta_options`, `use_nondefault`, `use_area_rural` that do not exist on ControlPathway (pathways.py has only `extra_model_options: List[str]` and `low_wind_option`). `getattr(ctrl, attr, None)` is always None, so `check()`/`apply()` and `_check_dfault_consistency` never fire for them.
- Evidence: VERIFIED, repro/docs-accuracy/reg.py: project with `extra_model_options=["NOSTD","LOWWIND1"]`, regulatory_default=True: `EPA_APPENDIX_W_2017.check(p)` -> [] and `.apply(p)` -> [] (options left in place). The matrix row "don't add NOSTD to extra_model_options" is good advice but nothing enforces it; "advanced_validate will then allow non-default options without flagging them" is vacuous.
- Fix (code): have the profile check `extra_model_options` (NOSTD, LOWWIND1/2, BETA) and `low_wind_option`; (docs, minimum) say the profile checks regulatory_default, terrain, low_wind_option and chemistry only, and drop "automates most of these". Also "`ControlPathway.urban_option` per source if urban" (line 11) is wrong: urban_option is the urban AREA NAME for URBANOPT (pathways.py:664-667); the per-source flag is a source field (URBANSRC).

### DOCS-7 [DOCS] [medium] architecture.md says BPIP-PRIME has a module that writes its input and one that runs it
- Where: docs/architecture.md:43-45
- What: "The other EPA programs each have a module that writes its input and one that runs it: ... AERSURFACE, AERSCREEN and BPIP-PRIME (`bpip`)". `bpip.py` is a pure-Python reimplementation of the projection (its docstring says so; `grep subprocess|Runner src/pyaermod/bpip.py prime.py` is empty); there is no BPIP runner/deck writer. EPA's BPIPPRM is only used by tests.
- Fix: "...AERSURFACE and AERSCREEN. BPIP-PRIME's building-dimension calculation is reimplemented in Python (`bpip`, `prime`) and checked against EPA's program."

### DOCS-8 [DOCS] [medium] api/index.md: stale "1.x" stability promise, `geo` extra enables `terrain`, unquoted extras, unlisted module pages
- Where: docs/api/index.md:104-123 (extras table, `pip install pyaermod[viz]` unquoted; `geo` row lists `terrain`), :125-135 ("every 1.x release", "always True in 1.x"; prints "pyaermod API v2.0"); src/pyaermod/api.py:474-475; mkdocs.yml:71-
- What: (1) project is 2.3.0 and API_VERSION is "2.0"; the promise and the snippet comment still say 1.x (api.py:474 comment is stale too). (2) `terrain` needs the `terrain` extra (requests; DEMDownloader raises without it, terrain.py:28,144) not `geo`; the `terrain`, `cad` and `gui-desktop` extras are missing from the table that install.md has. (3) install.md warns zsh breaks unquoted brackets; this table is unquoted. (4) Pages that exist in docs/api and in mkdocs nav but are in none of the index tables: aerscreen, aerscreen_runner, aersurface, aersurface_runner, design_values, naaqs, epa_sources, kmz_export, source_importers, regulatory_parity. The cli row lists "(validate, run, parse, plotfile, profile)" but omits `info` and `gui` (cli.py:14-37).
- Fix: "every 2.x release"/"always True in 2.x"; point to install.md for extras (or copy its table, quoted); add the missing modules to the tables.

### DOCS-9 [DOCS] [low] RELEASING.md: "all three files" then lists five; 2.2.0-era wording is stale after 2.3.0
- Where: RELEASING.md:33-41, :45-50, :133 ("the first release after 2.2.0"), :19-21
- What: step 1 says "Bump the version in all three files" and lists pyproject, __init__, api, conda recipe, CITATION (five). Step 2 still says "For v2.2.0 the section already exists with a YYYY-MM-DD placeholder" and "(v2.2.0's are written...)"; CHANGELOG already has a dated 2.3.0 section. conda step says "the first release after 2.2.0" although 2.3.0 is released and conda is still unpublished. `mkdocs build --strict` is a gate but docs/requirements.txt is never named.
- Fix: "all five files"; delete the v2.2.0-specific sentences; "the first release after the recipe is ready"; add `pip install -r docs/requirements.txt` before mkdocs.

### DOCS-10 [DOCS] [low] CONTRIBUTING.md: `pre-commit install` needs a package the dev extra does not install; test-full runs e2e
- Where: CONTRIBUTING.md:11-15 and :44-50; pyproject.toml:[project.optional-dependencies].dev; Makefile:34-36
- What: `pip install -e ".[dev,all]"` then `pre-commit install` fails with command not found (dev has no pre-commit; .pre-commit-config.yaml exists). `make test-full` uses `-o addopts=""` which drops pytest.ini's `-m "not slow and not e2e"`, so it also collects tests/e2e, while the same page warns to keep "not e2e" unless Playwright is installed, and calls test-full "the whole suite including slow tests". Minor: "Docstrings: NumPy style" but much of src uses Google-style `Args:` (output_parser.py, runner.py).
- Fix: add `pre-commit` to `dev` or write `pip install pre-commit` first; say test-full also collects the e2e journeys (they skip without Playwright, if that is true) or add `-m "not e2e"` to the target.

### DOCS-11 [DOCS] [low] design-value-validation.md: "all 10 source types" is stale
- Where: docs/design-value-validation.md:119; tests/test_source_deck_acceptance.py:3 (docstring says ten) and params at :60-160
- What: the test now covers 13 source types plus three scalar-downwash variants; the page and the test's docstring still say 10. Also "all 47 PST/PLT pairs" (line 79) is not asserted anywhere (the test guards only `>= 40`, test_epa_known_answers.py:168).
- Fix: "all 13 source types"; "the PST/PLT pairs in the reference set (47 in aermet26135_aermod26135)" only if that is counted from the archive.

### DOCS-12 [DOCS] [low] validation.md provenance is inconsistent with its own reproduction recipe
- Where: docs/validation.md:8-18 and :172
- What: the generated table says "pyaermod 2.0.0, Git commit df9b346" (commit not present in this repository: `git tag --contains df9b346` -> malformed object name) while the reproduction text says "git checkout v2.2.0 # the tag the report was made from". Both cannot be true; the report predates v2.2.0 (last regenerated 2026-08-24, ff4b6b9 only touched it for release prep) and the checkout the recipe sends readers to is not the one the numbers came from.
- Fix: regenerate with scripts/run_epa_parity.py on the release tag (the weekly epa_parity.yml already regenerates it as an artifact) or change the sentence to name the commit the table lists.

### DOCS-13 [DOCS] [low] README.md / docs/index.md citation block names 2.2.0 while the package is 2.3.0; Project Structure is stale
- Where: README.md:176-178, docs/index.md:62-64 (version 2.2.0 + DOI 10.5281/zenodo.23512927, which CITATION.cff:31 labels "v2.2.0, minted by Zenodo on 2026-10-20"), README.md:128-151
- What: consistent with RELEASING step 3 (DOI recorded after release) but v2.3.0 is tagged and CITATION.cff says version 2.3.0 date-released 2026-11-18, so the README citation names a different version than the file it points to until step 3 is done. README Project Structure lists 11 of ~50 modules and says input_generator.py is "all source types" (sources.py holds them since v1.5; input_generator is the facade, per docs/api/index.md). docs/index.md Preprocessors list omits AERSURFACE, AERSCREEN (architecture.md and the api index document them).
- Fix: do RELEASING step 3 for v2.3.0 and (since there are now two places) let one point to the other; replace the Project Structure tree with a link to architecture.md.

## Verified OK (no finding), for the record
- README, quickstart, docs/index: all imports, class/argument names (`CartesianGrid.from_bounds`, `run_aermod`, `AERMODRunResult.runtime_seconds/output_file`, `period_plot_file_names`, `plot_contours(plotfile=)`, `read_postfile(output_types=)`, `column_for`, `max_concentration`, `get_timestep`, `Validator.validate().is_valid/.errors`, BackgroundConcentration/SourceGroupDefinition fields) exist with those signatures; 13 source types list matches `_SOURCE_TYPES` and README keyword list.
- install.md: extras table equals pyproject; Python 3.11-3.14 claim matches gui_install_smoke matrix (3.11, 3.14) and classifiers 3.11-3.13 (CI tests 3.11-3.13; 3.14 only in the GUI install smoke - fine); quoted messages and --port/--no-browser/--host match gui_v2/__init__.py; `pyaermod info`, `pyaermod gui`, `python -m pyaermod.gui_v2` exist.
- gui-guide.md and desktop.md: every quoted UI string, default (600 s timeout, 25 rows/page, 10 recent files, ~/.pyaermod/recent_files.json, PYAERMOD_RECENT_FILES, pyaermod_gui.inp, 100 MB POSTFILE limit, 1024 px drawer, blank-project defaults, receptor defaults, seven step names) matches src/pyaermod/gui_v2. Only nit: the header readiness line reads "Ready to run, with N warnings" when warnings exist (steps.py:180); the guide shows only "Ready to run".
- browser.md: scripts (app_dev_server.py --replay, build_lite_site.sh, make_lite_notebooks.py, docs/lite/requirements.txt), notebook names, sample data labels, MAX_TABLE_ROWS=500, 0.5 m CSV match, AERMODRunner.start/run_batch exist.
- aermap-troubleshooting: the sample deck is reproduced exactly by the sample code; E310/E365/E455 messages exist in aermap source 24142; DatumTransformer, utm_*, srtm_tiles_for_bbox, flag texts match terrain_utils.
- ensemble.md: run_design/collect_plotfiles signatures, constants (SCHEMA_VERSION 2, 200-char limit, file names) match.
- benchmarks.md/README performance paragraph: CLI flags, files, polling behaviour (subprocess.run with timeout) and the quoted ranges agree with each other; the measurements themselves were not re-run.
