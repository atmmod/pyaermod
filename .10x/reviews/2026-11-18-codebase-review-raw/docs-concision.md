# docs-concision: editing plan for README, docs/, CONTRIBUTING, RELEASING, CHANGELOG and public docstrings

Scope read: README.md, CONTRIBUTING.md, RELEASING.md, mkdocs.yml, docs/index, quickstart, gui-guide, common-errors,
refinery-assignments (all), keyword-audit (head, tail, samples), tutorial-5 (all), student-guide setup/concepts/index/
next-steps/tutorial-2,3 (parts), use-cases (head), ensemble (head), install, desktop, browser (parts), regulatory-matrix
(parts), validation (head), aermet-tuning-guide (head), CHANGELOG structure (headings, 2.2.0 intro). Not read in full:
psd.md, aermap-troubleshooting.md, design-value-validation.md, benchmarks.md, tutorial-1/4, glossary, the use-cases and
ensemble bodies, keyword-audit lines 160-440 (keyword lists), CHANGELOG bodies. Line counts below are `wc -l` at HEAD 794fe60.
Test coverage of docs: `tests/test_docs_examples.py` runs the python blocks of quickstart.md and docs/teaching/student-guide/*.md
in order in ONE namespace per page. README.md, refinery-assignments.md, use-cases.md (it includes scripts from
examples/) and every other page are not run. Any cut in quickstart.md or a student-guide page must keep names that later blocks use.

Earlier reviews: no item of .10x/reviews/2026-11-11 or 2026-11-17 concerns docs concision; not re-checked.

## A. Wrong or contradictory statements found on the way (fix first; few lines each)

### D1 [DOCS] [high] Docs say AERMET's METPREP stage is "Stage 3" and that "current AERMET has no Stage 2"; AERMET's own source calls it stage 2
- Where: docs/teaching/student-guide/tutorial-5.md:16,45-63,95-98,207,407-413; docs/teaching/refinery-assignments.md:37,159-174,250-251 (Tutorial 6 Step 3 "Stage 2");
  docs/aermet-tuning-guide.md:23-41 (says "METPREP (AERMET's 'stage 2')" -- correct, so the two pages disagree);
  src/pyaermod/aermet.py:554-558 (docstring of AERMETStage3: "AERMET calls it stage 2"; deck comment at aermet.py:723 "Stage 3 ... (AERMET stage 2, METPREP)").
- What: aermet/aermet_source_code_24142/mod_main1.f90:56-58 documents `lstage`: "which stage, 1 or 2, or both, is run". So AERMET 24142 has Stage 1 and Stage 2 (METPREP); there is no Stage 3. The pages a student reads say the opposite and tell them to "skip Step 3, Stage 2" (refinery:159-165).
- Evidence: VERIFIED for AERMET 24142 source (26135 source not in the tree; aermet-tuning-guide already says 26135 behaves the same, not re-checked).
- Fix: use "Stage 1" and "Stage 2 (METPREP)" everywhere; say once, where `AERMETStage3` first appears, "the class keeps its old name, AERMETStage3". Delete refinery:159-174 (a Stage 2 that does not exist) and tutorial-5:60-63, 95-98. Keep file names `aermet_stage3.inp` only if code writes them; otherwise rename to `aermet_metprep.inp` in the text.

### D2 [DOCS] [high] common-errors "Cryptic Fortran crashes" table lists messages that are not in AERMOD's source
- Where: docs/common-errors.md:221-228.
- What: `** FATAL ** negative U*`, `** FATAL ** bad mixing height`, `*** ERROR *** XY array out of bounds`, `*** ERROR *** pollutant not recognized` -- grep of aermod/*.f (-i "negative u\*|bad mixing|out of bounds|not recognized|XY array") finds none (only a prime.f debug print "z out of bounds"). AERMOD reports Exxx/Wxxx codes. The causes in column 2 are also unsourced.
- Evidence: VERIFIED by grep over the v26135 source.
- Fix: delete the table (8 lines) or replace each row with a real code from the source and its Fortran routine.

### D3 [DOCS] [medium] common-errors cites a source line that moved, and two causes with no source
- Where: common-errors.md:13 ("`validator.py` line ~195"), :202-207 ("stack height at or above GEP -- AERMOD models no downwash": plausible, no routine cited), :215-219 ("AERMOD can't compute momentum flux" for exit_velocity=0).
- What: a line number in prose rots; the validator message itself says "AERMOD will model as neutral" (validator_advanced.py:80), which contradicts the page's "NaNs" claim. One of the two is wrong or unsourced.
- Fix: delete the "Where" line; for the NaN entry quote the validator's wording or cite `calc1.f`/`arise.f`, else mark it PLAUSIBLE or cut it.

### D4 [DOCS] [medium] regulatory-matrix contradicts itself and the Fortran on GRSM
- Where: docs/regulatory-matrix.md:15 ("GRSM and PVMRM2 remain BETA through 2023") vs :31 (says v26135 removes the BETA flag from GRSM); :27-30.
- What: coset.f:1837-1849 (v26135) has the GRSM BETA/DFAULT checks commented out ("D182_Remove_BETA_flag_GRSM_RLINE_COARE_WSP"), so GRSM is accepted under DFAULT. Line 15 still says it is BETA. src/pyaermod/regulatory.py:223 already has the right sentence.
- Evidence: VERIFIED for GRSM in v26135 coset.f; PVMRM2 not checked (PLAUSIBLE that it is unchanged).
- Fix: rewrite line 15 to "OLM, PVMRM, ARM2 or GRSM (GRSM was BETA before v26135)"; one sentence in :27-30.

### D5 [DOCS] [medium] concepts.md describes AERMOD as Gaussian in both directions and quotes an old PM2.5 level
- Where: docs/teaching/student-guide/concepts.md:26-33 and :125.
- What: "models the spreading pollutant cloud as a bell-shaped (Gaussian) distribution in both the horizontal and vertical" -- AERMOD's convective vertical distribution is not Gaussian (PLAUSIBLE: bi-Gaussian pdf; not verified in aermod.f, cite `calc1.f`/`pcalc.f` if kept). Line 125 asks about "12 ug/m3" annual PM2.5; the page's own NAAQS table in refinery-assignments.md:1325 says 9.0.
- Fix: "a steady-state plume model: Gaussian in the horizontal, and in the vertical in stable and neutral hours" (or drop the second bullet), and use 9 ug/m3 or drop the number.

### D6 [DOCS] [medium] Houston surface-parameter values contradict the page's own reference table
- Where: refinery-assignments.md:197-210 (industrial Bowen 0.3-0.8, roughness 0.4-0.6, albedo 0.14-0.18) vs :1341 ("Industrial/port: Bowen 0.8-1.5, roughness 0.50-1.00, albedo 0.18"); also :212-222 "Key differences" compares to "0.15-0.35 / 0.5-1.5" of Tutorial 5.
- Fix: delete the "Land Use Surface Parameters" table (1334-1347, 14 lines); it is not used by anything and disagrees. If kept, make the tutorial row match.

### D7 [DOCS] [medium] Unsourced causal claims in the tutorials
- Where: tutorial-2.md:109-110 ("effective stack height is the single most important factor"); concepts.md:96 ("two most important factors"); tutorial-5.md:262-263 ("suburban values ... conservative and widely used in regulatory work"); tutorial-5.md:398-400 (nighttime maxima from "high Monin-Obukhov length": stable L is small and positive); refinery:366 ("EPA requires terrain processing for virtually all analyses"), :686 ("Tall stack -- regulatory requirement for FCC units"), :559-561 ("ELEVATED version will typically produce slightly higher maximum"), :1088-1092.
- Fix: cut the sentence, or reword as what the exercise shows ("In this exercise ..."). The Monin-Obukhov sentence should read "a small positive length".

### D8 [DOCS] [medium] validation.md header is stale and leaks a build path
- Where: docs/validation.md:5-17 ("pyaermod | 2.0.0", commit df9b346, "/tmp/aermod_build/..." path, generated 2026-08-24, "in 286.4s").
- What: README.md:204 and the release notes claim validation of the current code; the report says it was produced by pyaermod 2.0.0. Either regenerate or say "generated for 2.0.0, rerun for each release".
- Fix: in scripts/run_epa_parity.py (the generator), print the version of the run, drop the absolute path; regenerate before release. See also D20 for shrinking the table.

### D9 [DOCS] [low] Stale or misleading small items
- README.md:177 and docs/index.md:61 cite "version 2.2.0" while the release is 2.3.0 -- correct per RELEASING step 3 only until the 2.3.0 DOI is recorded; add that DOI before announcing.
- README.md:128-151 "Project Structure" lists 13 modules; src/pyaermod has 51 .py files; "docs/ # Architecture and quickstart guides".
- install.md troubleshooting row about "pyaermod 2.2.0, whose pyaermod-app reads no options" (one row, 2 lines) is only useful to 2.2.0 users; keep one more release, then remove.
- docs/design-value-validation.md:83 "is worth noting because" is filler; delete the clause.
- tutorial-5.md:96-97 "AERMET (11 and later)": AERMET version 11 is not defined anywhere else; say "current AERMET (24142, 26135)".

## B. Docstrings of public names (pyaermod.__all__: 269 names)

Checked by script: first line, blank line after it, length. Only the items below failed.

### D10 [DOCS] [medium] AERMETStage3 docstring contradicts the docs (see D1)
- Where: src/pyaermod/aermet.py:553-559.
- Fix: "AERMET Stage 2 (METPREP): merge the Stage 1 data and compute the boundary-layer parameters, writing AERMOD's .SFC and .PFL. The class is named `AERMETStage3` for backward compatibility." (the sentence is there; it is the docs that must follow, and aermet.py:723's comment "Stage 3 Input (AERMET stage 2, METPREP)" is the string written into decks -- leave unless tests pin it.)

### D11 [DOCS] [low] Four classes open with a keyword line, not a summary
- Where: SidewashPointSource (sources.py, "``LOCATION srcid SWPOINT ...``: a sidewash point source."), HourlyEmissionFile ("``HOUREMIS filename srcid|range|ALL ...``: sources whose ..."), MaxDailyContribution ("``OU MAXDCONT ...`` or ..."), NOxBackground ("NOx background for GRSM (CO NOXVALUE / ... /" wraps onto line 2).
- What: mkdocstrings and `help()` show the first line as the summary; these are card syntax. Also three design-value functions (`no2_1hr_design_value`, `so2_1hr_design_value`, `o3_8hr_design_value`) wrap their summary onto line 2 with no blank line.
- Fix: one-sentence summary first ("A sidewash point source (SO SWPOINT).", "Sources whose hourly emission rates AERMOD reads from a file (SO HOUREMIS).", "Source-group contributions to the ranked daily maxima (OU MAXDCONT).", "NOx background for the GRSM chemistry option."), then the card syntax as paragraph two. Design values: "NO2 1-hour design value in ppb." then the method.

### D12 [DOCS] [low] RunManifestEntry has no docstring (its signature becomes the summary); run_design's is 71 lines
- Where: runner_utils.py RunManifestEntry (the signature `RunManifestEntry(input_file: 'str', status: ...` is what `inspect.getdoc` returns, 144 chars); ensemble.py run_design docstring (71 lines).
- Fix: one-line docstring for RunManifestEntry. For run_design keep the Args and Returns and move the 3-step "how" prose (about 35 lines) to docs/ensemble.md "Why one directory per run" and "Resuming", which already say it; leave a 6-line summary plus a link. Lines removed from source: about 30. Other long ones (AERSCREENConfig 97, UnformattedPostfileParser 88, AERSURFACEConfig 67 lines) are field lists and are fine; UnformattedPostfileParser's record-layout prose could move to docs/api/postfile or keyword page (about 20 lines) -- optional.

## C. Per-page plan

### README.md (204 lines; purpose: the repo landing page, all three audiences; target 110)
- Cut 100-126 "Features" (27 lines) to 6 lines or nothing: it is the same list as docs/index.md:10-20 and as docs/api/index.md. Keep one copy, on index.md; README links to it. CONTRIBUTING step 7 (line 195) says to update the source-type list in README and index: after this change only index.md.
- Cut 128-151 "Project Structure" (24 lines): stale (D9) and duplicated by docs/architecture.md. Replace by "src/pyaermod/ is the package; see [How pyaermod is organised]".
- Cut 189-200 "Performance" (12 lines): benchmark numbers belong on docs/benchmarks.md; README keeps one sentence ("A run through pyaermod adds 1 to 20 ms over calling AERMOD directly") and the link. Also "Performance" after "License" is out of order.
- Move 169-183 "Citing" to one place (CITATION.cff is the machine copy). README keeps the 3-line citation; docs/index.md drops its copy, and RELEASING step 3 has one file less to edit (line 114-115). Saves 15 lines on index.
- Tighten the worst passages:
  1. "PyAERMOD automates input file generation, model execution, output parsing, and result visualization — replacing manual text-file editing with a type-safe Python API." -> "PyAERMOD writes AERMOD input files from Python, runs AERMOD, reads its output and plots it." ("type-safe": the dataclasses are not checked by a type checker at runtime; mypy has a baseline of errors, mypy-baseline.txt.)
  2. "Try it without installing anything: ... Both build an AERMOD project with pyaermod, run AERMOD and show the results inside your web browser. The AERMOD there is EPA's source compiled to WebAssembly: fine for learning, not for regulatory work." -> "The browser app and notebooks run pyaermod and AERMOD (EPA's source compiled to WebAssembly) in your browser; for learning, not for regulatory work. [More]".
  3. Disclaimer (204): 120 words in one paragraph; split to "pyaermod runs the AERMOD you give it; every concentration comes from AERMOD." / "The browser build is not for regulatory use." / "Validated against AERMOD v26135 (link); v24142 still supported. Check results against EPA test cases for your use."
  4. "Keep the quotes: zsh, the default shell on macOS, otherwise reads the square brackets as a file pattern. AERMOD itself is installed separately." -> already in install.md; keep as a 1-line comment in the code block (`# quotes needed in zsh`).
  5. Requirements (153-157) repeats Installation line 19 and "AERMOD executable" in 28; delete.
- Undefined at first use: OLM, PVMRM, ARM2, GRSM (line 108; define once or link to use-cases job 6), POSTFILE (84), AERMET Stage 1 / METPREP (113), "PLOTFILE" (109).
- Inconsistent: `terrain_type=TerrainType.FLAT` (README:47) vs `terrain_type="FLAT"` (quickstart:37); import from `pyaermod.input_generator` (README) vs `pyaermod` (quickstart). Use the enum and `from pyaermod import ...` in both. README's code is not run by test_docs_examples.py: add "README.md" to PAGES (two python blocks need `<!-- docs-example: skip -->`).
- Unverified "AERMOD does X": none beyond README:204 "a gfortran build driven by pyaermod reproduces EPA's AERTEST plotfile bit-for-bit" (sourced by validation page, fine).

### docs/index.md (70; purpose: site home, all; target 40)
- Cut "Features" (10-20, 11 lines; README keeps the one-line version, or this keeps it and README drops it -- choose index) -- recommended: index keeps a 6-line "What it does"; README links.
- Cut "Requirements" (48-52) and "Citing PyAERMOD" (54-66, 13 lines) -> one line "Citing: see README / CITATION.cff". License (68-70): footer-level; delete.
- Ordering: "Getting Started" lists five links with " -- " descriptions; fine. Put "Install" before the list.
- "Getting Started" and "Practitioner guides" use " -- " (double hyphen) as dashes; rest of the site mixes "--" and "—". Pick one (em dash is used in README/gui-guide).

### docs/install.md (122; fine; target 115)
- One row of the troubleshooting table is 2.2.0-only (see D9). Nothing else.

### docs/quickstart.md (375; purpose: first run in Python for the modeller; target 230)
Test impact: every python block runs in one namespace; the blocks after the first reuse `output`, `control`, `project`, `results` only via skipped blocks, so the cuts below are safe if block 1 stays intact and `project` stays defined for the Validation block.
- Cut 3-13 "Installation" (11 lines) to "Install pyaermod ([Install](install.md)); AERMOD is a separate program from EPA SCRAM." The same install lines appear in README:22-25, index:40-43, gui-guide:23, setup.md:3.1, use-cases:30.
- Cut 152-222 "Multiple Sources", "Polar Grid", "Building Downwash" (71 lines): job 2 (use-cases.md:108) is "several stacks, source groups and a polar grid" and job 3 is downwash with BPIP-PRIME, both complete and run against AERMOD. Replace with 4 lines linking to jobs 2 and 3. Lines removed: about 65. (Keep the sentence "Building downwash (PRIME) is also supported on AreaSource and VolumeSource" in api/sources docs.)
- Cut 256-283 "Source Groups" (28 lines) the same way (job 2), but keep the 4-line note at 280-283 ("source_groups=['BOILERS']... SO E140 on a group card among the source cards") since it is the only place it is stated: move it into the job 2 "Adapting it" tip.
- Keep "Background Concentrations" (224-254) but move to use-cases as a tip or an api/sources example: use-cases.md does not mention BackgroundConcentration (grep count 0). It is the only quickstart section that is not covered elsewhere. Alternative: keep it here and cut nothing else of it.
- Merge 341-363 "More recipes" and 365-375 "Next Steps": both end with lists of links to jobs, the GUI, API and examples (about 20 lines saved).
- Move 302-314 "Validation" before the run (it is what write() does; the reader needs it before AERMOD) and 316-339 "Reading an existing deck" up: a modeller who knows AERMOD usually starts from an existing .inp. Order: example, validate, run, parse, plot, read an existing deck, links.
- Tighten:
  1. "Create a complete AERMOD input file in just a few lines:" -> "Write an AERMOD input file:" ("just a few lines": 55 lines).
  2. "That's it! You now have a valid AERMOD input file." -> "`project.write()` has validated the project and written `my_first_run.inp`."
  3. "`get_concentrations` returns the rows of AERMOD's summary tables, the highest ten or so receptors, not the whole grid. The value at every receptor is in the PLOTFILEs that `period_plot_files` asked for:" -> "`get_concentrations` returns the rows of the `.out` summary tables (the highest receptors), not the whole grid. For every receptor, read the PLOTFILE:" ("ten or so" is not stated by a source; the count is the RECTABLE rank.)
  4. "Without `plotfile=`, `plot_contours` can only contour the summary table's few rows, and warns that it is doing so." -> "Without `plotfile=`, `plot_contours` contours only the summary table's rows and warns."
  5. "`read_aermod_input` reads an AERMOD `.inp` deck into the same objects, so an existing run can be changed and written again. A line pyaermod does not model (EMISFACT, INCLUDED, SITEDATA, EVALCART, DISCPOLR, a malformed line of a known keyword) is kept verbatim in ..." -> split the parenthesis (it is the keyword audit's "Stored only, by design" list; link to it) and cut to: "Lines pyaermod does not model are kept in `project.unparsed_lines` and written back by `project.write()` (see [keyword audit](keyword-audit-v26135.md)); pass `preserve_unparsed=False` to drop them."
- Undefined at first use: UTM (line 44), PRIME and BPIP (220-222), SCRAM (13), EMISFACT (239), HOUREMIS (356), EVENT (358), POSTFILE (285), PLOTFILE (75), SEASON/MONTH/HROFDY.
- Terms: page title "PyAERMOD Quick Start Guide", nav "Quick Start", file quickstart.md, README "Quick Start Guide" -> use "Quick start" in all.
- "AERMOD does X": line 282 "AERMOD stops with SO E140 on a group card among the source cards": check against soset.f before keeping (PLAUSIBLE; not verified here). Line 283 "Naming ALL adds nothing" fine.

### docs/gui-guide.md (387; purpose: reference for the GUI, modeller and student; target 320)
- Cut 20-28 "Install" (9 lines) to a link (install.md); keep the one-line `pyaermod-app`. 30-47 "Launch": keep, it is the only place for `--host`.
- Cut 367-380 "Tips" (14 lines): bullet 1 repeats "Sessions and browser tabs" (95-101), bullet 3 repeats "Run options" (284-288), bullet 4 repeats the Python path in install/next-steps. Keep bullet 2 (working directory is kept) and move it to "Run options".
- Cut 382-387 "Reporting issues" or share with desktop.md:146-152 (both say the same): one page, linked from the other; or move to the repository README.
- Merge 14-18 (browser version) with the same note in browser.md:15 and README.md: one sentence + link.
- Tighten:
  1. "The same codebase runs in two modes: - **Browser tab** via `pyaermod-app` — the NiceGUI server runs on loopback. Best for development, multi-user / server deployments, and remote access." -> "`pyaermod-app` serves the GUI to a browser tab; `pyaermod-desktop` shows the same app in a native window ([Desktop Window](desktop.md))." "Best for ... multi-user" conflicts with line 41-47 ("reads and writes files and runs AERMOD as the user who started it, for anyone who can reach it").
  2. "Each step's badge reads **not started**, **error**, **warning** or **complete**, from the validator's findings for the part of the project that step edits (for Review & Run and Results, from the latest run that was not cancelled)." -> "A step's badge (not started, error, warning, complete) comes from the validator's findings for the part of the project the step edits; for Review & Run and Results, from the latest run that was not cancelled."
  3. "Saving refuses a project its file could not be reopened with ("Save failed: ..." names the field)." -> "Save refuses a project that could not be reopened, naming the field ("Save failed: ...")."
  4. Meteorology paragraph 204-215 (12 lines) packs five behaviours; cut the E480 sentence (it is on the Project, Review & Run and common-errors pages: three copies) to a link.
  5. "Besides the validator's errors and a project that cannot be written as a deck, the checklist catches what would make AERMOD itself stop: ..." (263-270): list the four items as bullets; it is a list in prose.
- Undefined at first use: NAAQS (line 81, expanded nowhere on the page), UTM (the page never says GUI coordinates are UTM; setup.md:3.4 and refinery do), KMZ, DFAULT, URBANOPT, STARTEND, SURFDATA/UAIRDATA/PROFBASE (216), E480 (dup in 3 places), E500.
- Terms: "deck" (here) vs "input file" (student guide, tutorials 1-2) -- see table.

### docs/common-errors.md (323; purpose: look-up for a modeller; target 250)
- D2, D3 above (delete 8-line table; remove locator).
- Order: three groups are mixed: (a) pyaermod input checks 7-127, (b) AERMOD runtime 129-228, (c) runner/batch 230-313. Within (a), six long deposition/open-pit entries (22-127, 105 lines) come before the two most common (E101, E480, E500) at 131-161. Put "AERMOD runtime failures" first (E101, E480, E500 are what users hit and what the GUI links to) and the open-pit/particle entries last.
- Cut/shrink:
  - 44-66 "Open pit: an AREA source used for a pit" (23 lines) -> 10 lines: Cause (flat release, no settling, receptors over the footprint modelled), what OPENPIT adds (escape fraction, effective area, skipped receptors; cite the three routines once), Fix. The ESCAPE formula can stay; the list of subroutine names `OPARM`, `PDEPTH`, `PTFRAC`, `PITEFF` in the middle is a developer's note (move to a code comment in validator.py).
  - 81-100 "aerodynamic diameters beside a density above 1" (20 lines): psd.md:37-103 ("What AERMOD does with the diameter") is the home; keep Cause/Fix in 6 lines and link. Drop "Earlier pyaermod releases wrote this by default ..." (history; belongs to CHANGELOG, which has it).
  - 169-194 "working directory ... already holds another deck named aermod.inp" (26 lines) -> 12: the Windows copy-and-sha256 paragraph (185-194) is runner internals; move to the AERMODRunner docstring or runner API page.
  - 282-313 "Pairing results with decks" and "Resuming an interrupted batch" (32 lines) are run_batch / resume_batch semantics, not errors; they belong in the `run_batch` docstring and docs/ensemble.md:182 "Resuming". Replace by 3 lines and links. "(earlier versions returned the list in finishing order)" is history.
  - 243-256 SIGTERM and timeouts: keep, trim "(a closed terminal, Task Manager, a restarted GUI server)".
- "Before you file a bug" (315-323): fine, keep; step 4 `run_all_qaqc(surface_records)` has no import line.
- Tighten:
  1. "AERMOD's error messages are terse and its crashes are cryptic. This page lists the failures pyaermod users hit most often, what causes them, and which pyaermod helper catches them earlier." -> "Failures seen most often, their causes, and the pyaermod check that catches each before the run."
  2. "- **Cause:** AERMOD does not model an `OPENPIT` source at receptors that lie strictly inside the pit; it skips them and leaves 0 for that source there (`calc1.f` PITCALC). AERMOD raises no error or warning code for them. It only lists each one, with `OPENPIT` in the distance column, in the input summary's table headed ..." -> "AERMOD skips receptors strictly inside an OPENPIT and reports 0 for that source (`calc1.f` PITCALC), with no message code; it lists them only in the .out's 'calculations may not be performed' table (`inpsum.f` CHKREC)."
  3. "- **Cause:** missing input or met file. / **Fix:** run `Validator.validate(project, check_files=True)` — catches this in-process." ok; keep.
  4. "`ControlPathway` defaults to `RUN`; if you see `NOT` somewhere, that's why." (165-167) -> "RUNORNOT NOT makes AERMOD check the input and stop; `ControlPathway` defaults to RUN."
  5. "Immediate crash, ERRMSG.TMP has `E101`" -> E101 is "missing input or met file"? That cause is not sourced; grep `E101` in the Fortran before keeping (not checked here; PLAUSIBLE).
- "AERMOD does X" claims with a routine cited (good): PITCALC, CHKREC, VDP1, SRCQA. Without: 202-207 and 215-219 (D3).

### docs/use-cases.md (321; purpose: ten runnable jobs; all audiences; target 285)
- The table at 11-22 (third column "Main pyaermod pieces") and each section's "What it shows:" paragraph list the same classes with links: drop the table's third column (or the paragraphs). About 10 lines per section x 10 = the paragraphs are the longer ones; keep the paragraphs, delete the third column.
- "Before you start" (24-82, 59 lines): item 1 install (7 lines) is install.md; item 2 AERMOD on PATH (14 lines) is install.md "AERMOD and the other EPA programs"; keep items 3-4 (met data, running). Saves about 15 lines.
- Filler: "**When you need it:** You are permitting or screening ..." is good, but sentences like "Pull just those files out of the archive:" -> delete.
- Tip lists ("Adapting it") run to 4-5 long bullets, some >300 characters (line 98-103 for job 1); split the numbers paragraph (98) from the tips and cut the W206 bullet, already in common-errors.md:115-127.
- Not tested by test_docs_examples.py (code is included from examples/use_cases); a separate test runs those scripts? (not checked).

### docs/ensemble.md (318; purpose: reference for run_design; modeller; target 270)
- 246-281 "Parallel runs and their speed-up" (36 lines) duplicates docs/benchmarks.md "Batch throughput" and README "Performance": keep one number and link.
- 40-102 "Why one directory per run" (62 lines): the two-problem explanation can be 25 lines; the EPA-deck path example and the 16-second measurement are anecdote. Keep the keyword list (rewrite_output_names).
- The docstring of run_design repeats 182-212 "Resuming" and 103-155 "Run IDs" (D12): the docstring should shrink, not the page.
- Opening: "keeps the books on them" -> "records them"; "It then does four things:" followed by four bullets is fine.

### docs/keyword-audit-v26135.md (638; purpose: which AERMOD keywords pyaermod reads/writes; modeller and contributor; target 430)
- Cut 80-150 (four paragraphs "Reader completeness tranche 1..4", 71 lines) to a 12-line table "Keywords handled, by pathway". It is project history ("this branch", "WP-5, claude/wp5-ev-me-ou-keywords"); branch names are meaningless to a reader. The summary table (68-77) already gives the counts. Also contradicts itself: "Handled keywords now total 91 of 115" (line ~109) vs "Every one of the 115 dispatched keywords is recognised and tested; 105 have a field" (78-84).
- Cut 389-399 "Handled + untested" (11 lines): says "None remaining ..." then lists what was untested before. Delete.
- Cut 464-536 "Round-trip guarantee" (73 lines) to about 30: keep the two suites and their pass counts (53/53 parse, 49 accepted + 4 chained MULTYEAR); delete the paragraph about "the first sweep of that acceptance test ... 28 of 53 written decks were rejected" (11 lines, history, in CHANGELOG 2.2.0), the "Tranche 4 adds three suites" paragraph (14 lines) and both "Probe decks ..." paragraphs (19 lines), which are an index of scripts/oracle_decks that belongs in scripts/oracle_decks/README.
- Cut 538-638 "Discrepancies and follow-ups" (100 lines, items 1-11, almost all "Resolved"/"closed by tranche N") to the three still-open lines at 631-638 ("Still lossy on rewrite" + `deposition_method` deprecation) -> 15 lines. Items 1-9 are in CHANGELOG 2.2.0 "Fixed"; moving the text there loses nothing.
- Tighten the head (1-66): "Source of truth" and the grep recipe (13-24) are for contributors; keep, but the 8-line comment about SBARSRCGRP could be 2 lines. "**Validator.**" (47-66, 20 lines) lists validator function names per keyword: move to docs/architecture.md or drop; the reader asked "is keyword X supported", not how the validator is organised.
- Page title carries "v26135" in the filename and nav; the page says "kept for v24142"? Not verified. Rename the nav label to "Keyword Audit" and keep the file name, so links survive.

### docs/regulatory-matrix.md (97; fine except D4; target 90)
- "Per-state/agency notes" (57-78) unverified claims about states not read in full; flag for a source check.

### docs/validation.md (220; generated; target 90)
- 142-row table (about 135 lines): print only the summary, the count, the cases with slope != 1.000000 (e.g. RLINEBA 0.999992, Test4 0.999998) and where the full table is kept (CSV artifact). Change the generator (scripts/run_epa_parity.py), not the page by hand.
- D8: version, path.

### docs/desktop.md (152; purpose: install and use the native window; student/modeller; target 90)
- Cut 117-145 "Desktop downloads discontinued" (29 lines): history of v1.9.0/v2.0.0 downloads and macOS Gatekeeper steps for apps that are no longer built; replace with 2 lines ("Releases up to v2.0.0 had stand-alone downloads; they are no longer built; install with pip") or move to release-notes.
- Cut 58-76 "What it does" (19 lines): the four steps are the gui-guide's seven-step table. Link.
- Cut 96-115 "AERMOD binary" (gui-guide:49-56 says the same) and "Web mode" (gui-guide 30-47 "Launch"): replace with a link.
- Cut 146-152 "Reporting issues" (shared with gui-guide:382).

### docs/browser.md (144; target 118)
- Move 118-144 "Build the site yourself" (27 lines) to CONTRIBUTING.md (contributors only) or docs/architecture.md; the reader of "Run in your browser" is audience (b).

### docs/architecture.md (70; keep; target 70 + 30)
- Receives CONTRIBUTING.md's "Project Layout", "Key Patterns" and "How the GUI's editors are built" (about 45 lines), which are architecture, so CONTRIBUTING gets shorter without losing them.

### CONTRIBUTING.md (210; purpose: contributor workflow; target 165)
- 77-104 and 52-75: "Running Tests" gives `make` targets, then the raw `pytest` commands that the make targets wrap, then coverage. Keep the make block and two pytest lines (single file, `-k`); cut the four-line slow-tests and e2e variants into the Makefile help.
- Cut 115-130 "Project Layout" + "Key Patterns" (16 lines) -> architecture.md (already says it).
- Cut 163-190 "How the GUI's editors are built" (28 lines) -> architecture.md.
- Cut 3-4 ("Thank you for your interest ... This guide covers ...") -> nothing.
- Tighten: "Please include: Python version and OS ..." (Reporting Issues) duplicates gui-guide:382 and desktop:146; keep here, link from there. Step 7 of "Adding a New Source Type" ("Add it to the source-type lists in README.md and docs/index.md") changes to index.md only.

### RELEASING.md (176; purpose: maintainer checklist; target 145)
- 20-30: the v2.2.0 incident story (Zenodo list stale) is history; keep "press Sync now" and drop "For v2.2.0 this happened: ...".
- 43-46: "For v2.2.0 the section already exists with a YYYY-MM-DD placeholder; replace ..." is version-specific; delete.
- 48-49 "docs/release-notes/vX.Y.Z.md: ... (v2.2.0's are written; check them against the final changelog)" -> "(check against the changelog)".
- 130-141 "Important" repeats 2 (no manual twine) and 100-105; keep two bullets.
- 163-176 "Compiling AERMOD/AERMAP (optional)" duplicates setup.md Option A and scripts/build_aermod.sh --help; keep 3 lines.
- If CHANGELOG is split (below), RELEASING step 2 (rename [Unreleased]) does not change; add one line: "when a minor version is released, move the previous minor's section to CHANGELOG-archive.md" only if that policy is chosen.

### docs/teaching/student-guide/setup.md (211; student; target 150)
- 3.1 (14-33) duplicates install.md and README; the student needs "pip install "pyaermod[gui]"; pyaermod info"; 8 lines. The zsh note appears here, in README, install.md, quickstart, teaching/README (5 times): keep install.md and README.
- 3.2 "Install the AERMOD and AERMET Executables" (35-164, 130 lines): Option A (build from source) is the only walkthrough and install.md links to it, so it stays, but trim: the build-record paragraph (123-131, "SHA-256 ... keep it with your results") and "To keep a second AERMOD ... AERMOD_EXE_NAME" (133-136) are for modellers, not first-year students; link to scripts/build_aermod.sh --help. "Verifying your installation" (166-181) repeats 3.2's checks and 3.1; delete.
- 3.4 "GUI Layout" (200-211+) duplicates gui-guide "Layout" (58-84): keep the numbered list of steps (students need it), link the rest.
- "The GUI calls an AERMOD input file a **deck**, the modelers' word for it." is the definition of "deck" for the whole student guide, but tutorials 1-2 say "input file" and the glossary has no "deck" entry: add "Deck" to glossary.md and use "input file (deck)" at first use in tutorial-1.
- tutorial-3.md:24-34 "Step 1: Verify AERMOD Is Installed" repeats setup.md 3.2 verification: shrink to a link.

### docs/teaching/student-guide/tutorial-5.md (413; student; target 300)
- D1, D7. Cut 60-63 and 95-98 (the Stage 2 story, twice).
- 31-58 "Conceptual Background" + diagram (28 lines): concepts.md:94-111 already says AERMOD needs .sfc/.pfl from AERMET; keep the 6-line diagram and one paragraph.
- 138-143 "Data Format options" (6 lines) lists four formats of which only ISHD is used; keep ISHD, link aermet-tuning-guide.md "Input data sources supported" (8-21) for the rest. Note aermet-tuning-guide lists ISD/ISD-Lite, ASOS, IGRA, MMIF -- names differ from this list (HUSWO, SCRAM, SAMSON): check which AERMETStage1 accepts (not verified).
- 195-203 "What Stage 1's Input File Contains" (9 lines) duplicates the "Check yourself" box in refinery:154-157; keep here, cut there.
- 357-365 troubleshooting bullets (9 lines): the three quoted messages ("File not found", "Missing data exceeds threshold", "Upper air sounding missing") are not AERMET message texts (not found in aermet source: not grepped here, PLAUSIBLE); replace with "read the MESSAGES file; E codes are explained in aermet-tuning-guide 'Common AERMET failures'".
- 380-400 "Understanding What AERMET Produced" (21 lines): fix the Monin-Obukhov sentence (D7) or cut; 402-413 "Checkpoint" restates the objectives at the top: delete one of the two.
- Tighten:
  1. "AERMET is the preprocessor that transforms raw weather station observations into these two files. Current AERMET (versions 24142 and 26135) runs in two stages, each from its own input file:" -> "AERMET turns raw station observations into these two files in two runs, Stage 1 and Stage 2 (METPREP), each from its own input file."
  2. "**Purpose:** This is the most important stage. Stage 3 (AERMET's METPREP) reads Stage 1's quality-assured files, merges them, and computes the **planetary boundary layer parameters** that AERMOD needs: ..." -> "METPREP merges Stage 1's quality-assured data and computes the boundary-layer parameters AERMOD reads (friction velocity, Monin-Obukhov length, mixing height)." ("most important stage" is opinion.)
  3. "**When in doubt:** Use the suburban values above. They're conservative and widely used in regulatory work." -> delete (D7).
  4. "AERMET reads the input file named after the command (not from `<` redirection)." -> "Give the input file as an argument: `aermet file.inp`."
  5. "**Prerequisites:** - PyAERMOD generates AERMET *input files*, but to actually process them you need the `aermet` executable installed on your computer. - **macOS/Linux:** ..." -> two lines and the link to setup.md 3.2 (it is repeated at 331-333).
- Undefined at first use: WBAN, ISHD (line 73 refinery, 113/120 here: "NOAA Integrated Surface Hourly Data" defined in the table, acronym not), QAOUT, METPREP (46, defined by context), ICAO, Bowen ratio (defined 230 after use at 224), UTC.
- Students are told "no programming experience", then edit Python lists of twelve numbers: fine, said at 7-10.

### docs/teaching/refinery-assignments.md (1347; purpose: three advanced tutorials with grading; student/instructor; target 950)
Tests: none run these code blocks (tutorial 6, 7, 8 python). Add the page to PAGES or at least run the aermet block (same code as tutorial-5, so a copy-paste drift risk).
- Tutorial 6 duplicates Tutorial 5 (the student guide): lines 109-260 (150 lines) re-explain stations, Stage 1 and Stage 3 code that is identical but for numbers. Replace with: a table of Houston values (stations, dates, files) + the 12-month parameter table + "run the Tutorial 5 script with these values". Saves about 70 lines. The "Key differences from the suburban defaults" box (212-222) stays (it is the teaching point) but see D6, D7.
- Cut 39-55 "Background: Why Houston?" (17 lines) to 5: a list of four meteorological features, two of which (sea breeze, humid) are used later in Discussion Question 3.
- Cut 75-79 and 91-94 "Why Hobby / Why Lake Charles" (9 lines): "~200 km east" is repeated three times (94, 1301). Keep one sentence each.
- Cut 159-174 Stage 2 (D1; 16 lines).
- Tutorial 7: cut 321-368 "Conceptual Background" and "Why Bother Near Houston?" (48 lines) to 15: the ASCII diagram (342-354) shows nothing the three-item list above it does not; the bullets "Elevated receptors ... Depressed receptors ... channeling effects" are unsourced (D7). aermap-troubleshooting.md "Hill-height diagnostics" and the student guide cover z_hill.
- Cut 395-406 "Option A -- PyAERMOD's built-in downloader (if available)": "if available" hedges a class (`DEMDownloader`) the docs elsewhere use (use-cases job 8). Either show the 6-line call or delete; "Your instructor may provide a script" gives the student nothing.
- Cut 432-446 FCCSTK table duplicated in Tutorial 8 Source 1 (Y 3291700 vs 3291750, base elevation 0 vs 5.0: the two tables disagree on one coordinate and on the elevation; that is a copy error, not a design). Say "add FCCSTK as in Tutorial 8 Step 2".
- Tutorial 8 Step 2 (672-886, 215 lines, ten tables with a "Rationale" column that repeats the value): replace with one 10-row table (id, type, x, y, height or release height, temp, velocity, diameter or dimensions, rate) of about 20 lines plus five 3-line notes (FCC plume rise; flare simplification; area emission rate = rate x area, with the two worked calculations at 797-801 and 840-842; volume sigma-y = width/4.3 and sigma-z = height/2.15; fugitives). Saves about 150 lines. Students then copy a table into the GUI, which is what they do anyway. If the per-source tables are wanted for grading, keep them in a collapsible `??? note` block.
- Cut 1225-1245 "Report Template" (21 lines): it repeats "Technical report (3-5 pages) including: ..." in Assignment Deliverables (1269-1275) and the rubric. Merge into one list. Saves about 20.
- Cut "Checkpoint" boxes (296-303, 580-587; 8 lines each): they repeat "What you'll learn" at the top of each tutorial (33-37, 314-319). Keep one.
- Cut 1294-1302 stations table (duplicates 62-94 and 1298-1302) and 1320-1332 NAAQS table (13 lines; duplicates regulatory-matrix/GUI "Comparison with the NAAQS"; the page's 196 ug/m3 and 9.0 PM2.5 must be kept in sync with three other places) -> link; 1334-1347 land-use table (D6).
- Tighten:
  1. "Advanced tutorials for PyAERMOD: from meteorological preprocessing through terrain processing to a complete oil refinery dispersion model. These three tutorials build on [Tutorials 1--5] and assume you are comfortable with ..." -> "Tutorials 6-8: AERMET for Houston, AERMAP terrain, and a ten-source refinery model. They assume Tutorials 1-5."
  2. "The fluid catalytic cracking (FCC) unit is the largest single SO2 source at most refineries. The regenerator burns coke off the catalyst, releasing SO2, CO, and particulate matter through a tall stack." -> "The FCC (fluid catalytic cracking) regenerator is usually a refinery's largest SO2 source." ("at most refineries" unsourced; "tall stack -- regulatory requirement" is D7).
  3. "> **Intuition:** The FCC stack is the "big gun" of the refinery. Its tall stack and hot exhaust give it substantial plume rise (the effective release height could be 120--180 m), so peak ground-level impacts will be 1--3 km downwind despite the high emission rate." -> "Plume rise from the tall, hot stack may put the effective release height at 120-180 m, so expect the peak 1-3 km downwind." (numbers are unsourced estimates; say "check against your results").
  4. "Repeat the model run with one change at a time to understand how each factor affects the results. This is the heart of engineering analysis." -> "Change one thing per run:".
  5. "Real air has background SO2 from regional sources (power plants, shipping, other refineries). Add a background concentration: / The GUI cannot enter a background concentration; add it ..." -> "The GUI cannot enter a background concentration (SO2 from regional sources); add one from Python:".
- Undefined at first use: WBAN, ISHD, FSL (155-156), KHOU/KIAH (ICAO), NAD83, UTM zone, FCC, NOx, VOC, H2S, API separator, FGD, bpd/kbpd, PM2.5 (page starts with SO2), "Bowen ratio" (defined in tutorial 5, which a student may skip).
- Terms: "Stage 3" vs METPREP (D1); "ELEVATED" (prose) vs `Elevated (ELEV)` (GUI label) vs ELEV (keyword) -- say once "Elevated (ELEV) terrain"; "ug/m3" here vs "µg/m³" in use-cases and in the GUI.
- The page is both a lab handout and a rubric; an instructor's rubric and deliverables (1247-1288, 42 lines) could live in a separate page (`refinery-assignments-grading.md`) so students who only want the tutorials do not scroll 1,300 lines; optional.

### docs/teaching/README.md (35) and student-guide/index.md (21)
- teaching/README.md is in the nav as "README"; rename to "Course plan" or merge its two parts: the prerequisites list duplicates setup.md; the week table goes to the student-guide index. Delete the page and the nav entry: saves 35 lines and one nav item. It repeats the zsh note and the three SCRAM links.
- student-guide/index.md: the H1 "Introduction to Air Dispersion Modeling with PyAERMOD" and nav label "Overview" differ; page H1s carry numbers ("8. Tutorial 5 ...", "3. Setting Up") that nav labels drop ("Tutorial 5: AERMET"): decide one.

### CHANGELOG.md (3421 lines) -- archive? Yes
Structure at HEAD: Unreleased (empty, 8-9), 2.3.0 lines 10-274 (265), 2.2.0 lines 275-3079 (2,805 lines: Added 316-971, Changed 972-1498, Fixed 1506-2886, then Upgrade notes 2911-3079), 2.0.0 and older 3080-3421 (342). 2.2.0 is one development cycle that was never released as 2.1.0, so its section is a development log of 150-odd PRs; users need the upgrade notes (2911-3079), not 1,380 lines of "Fixed".
- Proposal: move versions before the current minor line (2.2.0 and older, 3,147 lines) to `CHANGELOG-archive.md`, leave a pointer line at the bottom of CHANGELOG.md ("Older releases: CHANGELOG-archive.md"). The archive keeps Keep-a-Changelog headings unchanged, so nothing is lost. A further step (optional, saves about 2,000 lines in the archive too): in the archive, replace 2.2.0's Added/Changed/Fixed bodies by the 25-line intro (275-300) and the five "Upgrade notes" subsections, because docs/release-notes/v2.2.0.md (159 lines) already is the user-facing summary. Do that only after the maintainer agrees: it deletes per-PR detail that git history and the PR list also hold.
- Effects: (1) Keep-a-Changelog readers: the standard says nothing about a single file; the intro ("The format is based on Keep a Changelog") stays. Add the pointer under the last version, and link to the archive in the header. (2) pyproject.toml:39 `Changelog = .../CHANGELOG.md` still correct. (3) MANIFEST.in:3 `include CHANGELOG.md` -> add `include CHANGELOG-archive.md`. (4) RELEASING.md step 2 (lines 43-47) only touches `## [Unreleased]`: unchanged; add one sentence on the archive rule (e.g. "when releasing X.Y.0, move the sections before (X.Y-1).0 to the archive"). (5) docs/release-notes/v2.2.0.md:149,159 say "See CHANGELOG.md for the complete list": change to "CHANGELOG-archive.md". (6) CONTRIBUTING.md:196 "CHANGELOG.md updated under [Unreleased]": unchanged. (7) No test reads CHANGELOG (grep: only a docstring in tests/test_api_core.py:10). (8) GitHub renders both files; the docs site does not publish CHANGELOG.md, so no mkdocs nav change.
- Independent of the move: 2.3.0's own entries (10-274) include "Fixed" items about code from the unreleased 2.2.0 development, e.g. entries that name features first added in the same cycle; skim for entries that describe a defect and a fix inside the same unreleased window and merge them. Not done here.

### mkdocs.yml nav (propose only changes that clearly help)
Before: top tabs Home, Install, Quick Start, Run in Your Browser, Ten Common AERMOD Jobs, GUI User Guide, Desktop Window, Guides (6), Teaching, Validation, Release Notes, How pyaermod Is Organised, API Reference. "Validation" appears twice (top-level section with four pages, and a sub-section of API Reference with regulatory pages) and "Validation Report" is a page inside "Validation".
After:
1. Rename the API Reference sub-section "Validation" to "Checks and regulatory" (it holds validator, validator_advanced, regulatory) and the last one (regulatory_parity, epa_sources) to "EPA parity"; the two sections of the same name in different tabs confuse search and the sidebar. 1 line each.
2. Move "Desktop Window" under "GUI User Guide" as a sub-page (GUI User Guide -> Guide, Desktop Window) so the top bar loses a tab; desktop.md is 150 lines about an alternate way to launch the same app.
3. Move "How pyaermod Is Organised" next to API Reference ("Reference: How it is organised, API") and delete the teaching "README" nav item (see above). Both helped by the page cuts.
4. Do NOT add CONTRIBUTING/RELEASING to the site nav; the repo root files are the maintainer's source (CONTRIBUTING.md is linked from docs/install.md "For development").
Net: two fewer top-level tabs and no duplicate names.

## D. Term table: variants and the one to use

| Concept | Variants found (count/pages) | Use |
|---|---|---|
| AERMOD input file | "input file" (52; student guide, tutorials, quickstart), "deck" (222; gui-guide, common-errors, keyword audit, runner), ".inp" (73), "runstream" (9; aermet-tuning, keyword audit), `aermod.inp` (the name the runner stages) | "input file (.inp)" in student material and the quickstart; "deck" in reference pages, defined once at first use of each page ("the input file, or deck"); "runstream" only when quoting AERMOD's own terms; add "Deck" to glossary.md |
| AERMET METPREP stage | "Stage 3" (13), "METPREP" (27), "Stage 2" (4; "no Stage 2"), "AERMET stage 2" (aermet.py, tuning guide) | "Stage 2 (METPREP)" (D1); class name `AERMETStage3` mentioned once as legacy |
| Meteorology files | "surface file" (21) / ".sfc" (54) / "surface met" ; "profile file" (12) / ".pfl" (40) ; "met files" (24), "met data" (19), "meteorological data" (15), "meteorology files" (2) ; `.SFC` upper case in use-cases and AERMET pages | "surface file (`.sfc`)" and "profile file (`.pfl`)" at first use, "met files" after; lower-case extensions as the files are written; "met data" for the data; delete "meteorology files" |
| Per-receptor output | "plot file" (GUI, gui-guide), "PLOTFILE" (52; keyword), "plotfile" (52; `read_plotfile`, `plotfile=`) | "plot file" in prose, `PLOTFILE` for the keyword and in code; same for "POSTFILE" (55, no prose variant "postfile" except code) |
| GUI steps | "step" (gui-guide, tutorials), "Review & Run" (25) vs "Review and Run" (2: refinery, tutorial-3 heading "Step 3: Review and Run"), "Run AERMOD" (button, 21), "Results step" (16) vs no "Results Viewer"/"page" (none found, good) | "step"; "Review & Run" (the GUI label); "Run AERMOD" for the button only |
| Quick start | "Quick Start" (nav, README link, 4), "Quickstart" (file and titles, 3), "Quick Start Guide" | "Quick start" |
| Units | "ug/m3" (13; tutorials, refinery), "µg/m³" (16; use-cases, GUI), "ug/m^3" (1), "g/s/m2" (9) vs "g/(s·m²)" (GUI label) | "µg/m³" and "g/(s·m²)" |
| Tutorial naming | "Tutorial 5" (student guide), "Tutorial 6-8" (refinery, a different file), page H1 "8. Tutorial 5 —" vs nav "Tutorial 5: AERMET" | one pattern: nav label = H1 without the section number |
| Terrain | "Elevated (ELEV)" (GUI label), "ELEVATED" (enum), "ELEV" (keyword), "elevated terrain" | "elevated terrain" in prose, the GUI label when naming the control |
| The package | "PyAERMOD" (README, site name, GUI), "pyaermod" (code, architecture, install) | "pyaermod" for the package/command, "PyAERMOD" only as the project name at a page's start; today the same sentence uses both (gui-guide:3 vs 37) |
| AERMOD outputs file | ".out file", "`.OUT`" (common-errors:240), "`.out`" | `.out` |
| Dashes | " -- " (index.md, quickstart, keyword audit), "—" (README, gui-guide, tutorials) | "—" in prose; "--" only in code |

## E. Undefined acronyms/jargon at first use (not already listed per page)
OLM, PVMRM, ARM2, GRSM (README:108); NAAQS (gui-guide:81, quickstart); UTM (quickstart:44); PRIME, BPIP (quickstart:220); SCRAM (README:157, quickstart:13); POSTFILE/PLOTFILE (README:84, 109; quickstart:75, 285); DFAULT, URBANOPT, STARTEND, SURFDATA, UAIRDATA, PROFBASE (gui-guide:137-221); WBAN, ISHD, FSL, ICAO, NAD83 (refinery:66-156, 429); FCC, FGD, VOC, H2S, kbpd (refinery); HUSWO, SAMSON (tutorial-5:141-143: "SCRAM" is both the EPA site and a data format there). Glossary (40 lines) lacks: deck/input file, METPREP, plot file, design value, WBAN, ISHD, UTM, DFAULT, PRIME.

## F. Stock phrasing and filler
grep for "comprehensive, seamless, powerful, robust, simply, in order to, leverage, easily, straightforward": 0 hits across README, docs, CONTRIBUTING, RELEASING. Remaining: "worth noting" (design-value-validation:83), "just a few lines" (quickstart:17), "That's it!" (quickstart:90), "the 'big gun' of the refinery" (refinery:692), "classic refinery pollutant" (635), "This is the heart of engineering analysis" (1170), "invaluable" (891), "a challenging and instructive location" (54), "This is the most important stage" (tutorial-5:207), "Thank you for your interest" (CONTRIBUTING:3), "type-safe" (README:9), "Best for development, multi-user / server deployments" (gui-guide:7), "stay usable", "ensure" x2. Each is a one-line edit; none changes content.

## G. Plan ordered by reader benefit per line changed
1. D1-D7 (about 40 lines touched; removes wrong statements): AERMET stage naming, delete fictional Fortran message table, GRSM line, 12 ug/m3, land-use table, unsourced claims.
2. CHANGELOG split: one file move, 3,147 lines out of the file a reader opens (plus pointer, MANIFEST.in line, two release-notes lines).
3. keyword-audit history cuts: about 200 lines removed, no keyword information lost (lines 80-150, 389-399, 464-536 trimmed, 538-638 trimmed).
4. README and index de-duplication (Features, Project Structure, Performance, Citing, Requirements): about 110 lines removed across the two, landing pages shorter.
5. quickstart "Common Patterns" replaced by links to jobs 2-3 + reorder (about 135 lines removed, test-covered blocks).
6. refinery Step 2 source tables to one table, T6 to "as in Tutorial 5", T7 background, Report Template, reference tables (about 380 lines removed).
7. validation.md generator prints only exceptions (about 130 lines).
8. common-errors reorder and trims (about 75 lines) and the deletions of history paragraphs.
9. desktop.md and gui-guide cuts (about 125 lines), browser "Build the site yourself" move (27).
10. student-guide setup/tutorial-3/tutorial-5 cuts (about 180 lines).
11. CONTRIBUTING/RELEASING trims (50 lines), architecture receives 45.
12. Nav renames (4 lines), teaching/README removal (35 lines).
13. Docstring edits D10-D12 (about 40 lines changed, 30 removed).
14. Terms table sweeps (mechanical, about 150 single-word edits; do last, after the cuts, so fewer lines have to be edited).

Expected lines removed (deleted or moved out of the reader's path), excluding CHANGELOG: refinery 380, keyword-audit 200, quickstart 135, validation 130, tutorial-5 110, README 95, gui-guide 65, desktop 62, setup+tutorial-3 70, common-errors 75, use-cases 35, ensemble 45, browser 27, index 30, CONTRIBUTING 45, RELEASING 30, teaching/README 35, aermap-troubleshooting 30 (not read in full, estimate), docstrings 30 = about 1,630 lines. Plus 3,147 lines moved from CHANGELOG.md to the archive. Sum 1,630 deleted + 3,147 moved; the docs set goes from about 7,200 lines to about 5,600 (and CHANGELOG from 3,421 to 274).
Not looked at: psd.md, aermap-troubleshooting.md, design-value-validation.md, benchmarks.md, aermet-tuning-guide (beyond head), tutorial-1/4, glossary, docs/lite, docs/release-notes, api/index.md, bodies of use-cases/ensemble; estimates for those are guesses.
