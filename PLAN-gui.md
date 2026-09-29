# PyAERMOD — GUI Redesign Plan with End-to-End Tests (for agents)

**Repository:** https://github.com/atmmod/pyaermod (main @ `cf46dff`)
**Prepared:** 2026-09-28
**Scope:** `src/pyaermod/gui_v2/`, its tests, the run-status logic in `src/pyaermod/runner.py`, and the GUI's documentation, packaging and CI.

## Status

| Package | State | Notes |
|---|---|---|
| WP-G0 | Done | `make test-gui-e2e` runs the journeys against recorded AERMOD runs in about 100 s. Every known gap listed below is reached on the current GUI. |
| WP-G1 | Done | `AERMODRunner` requires AERMOD's completion banner and zero fatal errors, and results carry the parsed messages. Defect D1 is fixed: both J2 run tests now assert the failed status outright. |
| WP-G2 to WP-G7 | Not started | WP-G2 is next. Its journeys stop at the D2, D3, D4 and WP-G2 gaps (`pytest -rxX` lists them). |

## Why a redesign

A live walkthrough on 2026-09-28 found that the GUI can build a project but cannot carry a user from a run to its results. The walkthrough used NiceGUI 3.17.1, an AERMOD binary built from EPA's v26135 source with `scripts/build_aermod.sh`, and headless Chromium driven by Playwright. All 166 GUI tests passed at the same time. Four defects break the workflow, and each one escaped because the tests checked internal state rather than what a user sees.

| # | Defect | Where | Why the tests missed it |
|---|---|---|---|
| D1 | A run that AERMOD aborts is reported as "Run succeeded." AERMOD exits with code 0 after fatal error E480, and the runner treats "exit code 0 plus an `.out` file" as success. | `runner.py:246` | The fake AERMOD in `test_gui_v2_smoke.py` is hand-written and never models "exit 0 with a fatal error." In addition, `test_real_aermod.py:133` looks for any `FINISHES SUCCESSFULLY`, which also matches the `*** SETUP Finishes Successfully ***` line that failed runs print. |
| D2 | The Results tab never shows results. The shell renders every tab once when the page opens, and nothing re-renders Results after a run. A browser reload creates a fresh `AppState`, so the run is lost as well. | `app.py`, `pages/results.py:30` | `test_run_with_output_renders_results_tab` calls the Results `render()` by hand through `_render_results`, whose docstring acknowledges the limitation. |
| D3 | New and Open replace `state.project`, but every widget stays bound to the old project's objects. The screen keeps showing the old project, and later edits go to a detached object and are lost. | `pages/project.py:51-69` and every `bind_value` call | `test_new_resets_project` asserts on `state.project`, not on the visible title field or tables. |
| D4 | Open crashes on NiceGUI 3.x. The upload handler reads `e.name` and `e.content`, but NiceGUI 3 provides only `e.file`. The uploader also needs a second click on a small cloud icon before anything is sent. | `pages/project.py:64` | `test_open_dialog_appears` stops once the dialog is visible and never uploads a file. |

The walkthrough also found smaller problems:

- Averaging periods and model options cannot be edited. The default `1 ANNUAL` guarantees a fatal error with any met file shorter than a year.
- Integer fields display as `14735.0000`, and the deck is written as `SURFDATA 14735.0 1988.0`.
- The "No sources yet" and "No receptors yet" messages stay visible after an item is added.
- Inputs are 160 px wide, so file paths are cut off.
- Runs block the server's event loop and offer no progress indicator or cancel button.
- Save As writes to a hard-coded `/tmp`, which does not exist on Windows.
- `tests/test_gui_apptest.py` still targets the Streamlit GUI that v2.0 removed, and `CONTRIBUTING.md` still tells contributors to edit `gui.py`.

The library underneath is sound. Once the averaging periods were changed, the deck the GUI wrote ran cleanly, and the parsed maxima matched AERMOD's own summary tables exactly. The redesign therefore concerns the GUI's architecture, workflow and tests, not the modeling core.

## Decisions already made

Agents should not reopen these decisions without the maintainer's agreement.

1. **Keep NiceGUI, both entry points (`pyaermod-app` and `pyaermod-desktop`), and the PyInstaller bundle.** The defects are architectural rather than framework limitations. NiceGUI 3 provides `ui.refreshable`, `ui.stepper`, `ui.plotly`, `ui.leaflet` and `run.io_bound`, which cover everything this plan needs.
2. **The GUI is a thin layer over the library.** Every modeling operation goes through existing public APIs: `AERMODProject`, `Validator`, `read_aermod_input`, `AERMODRunner`, `AERMODOutputParser`, `PostfileParser`, `design_values`, `naaqs`, `met_qaqc` and `kmz_export`. The GUI never writes AERMOD keywords or parses AERMOD output itself. When the GUI needs something the library lacks, the library gains it first, with its own tests.
3. **Tests are written before the redesign and define "done."** The user journeys below are executable specifications. A work package is finished when its journeys pass, not when its code is written.

## Target design

### Architecture: one session, with views derived from it

- Add a UI-free `Session` class in `gui_v2/session.py`. It takes over `AppState`'s role; keep `AppState` as a thin alias only if something outside `gui_v2` needs it. The session owns the project, its file path, the dirty flag, the latest validation result, the run history (a list of run records) and the run in progress.
- The session exposes every user operation as a method: `new()`, `open_json()`, `import_inp()`, `save()`, `save_as()`, `add_source()`, `update_source()`, `delete_source()`, the same three for receptors, `set_control()`, `validate()`, `start_run()` and `cancel_run()`. Each method emits a named change event, such as `project_replaced`, `project_changed`, `run_started`, `run_progress` or `run_finished`, through a small observer list.
- Pages become `@ui.refreshable` functions of the session and subscribe to the events that concern them. For example, `project_replaced` refreshes every page, and `run_finished` refreshes Review & Run and Results. **Rule:** no widget may hold a reference to a project sub-object across a `project_replaced` event. A `bind_value(session.project.control, ...)` call is valid only inside a refreshable that is rebuilt when the project is replaced.
- A browser reload must never silently lose work. The preferred approach is to keep the session per browser tab (for example, keyed through `app.storage.tab`) and restore the project and the last run on reload. If WP-G2 finds that impractical, the fallback is an unsaved-changes warning before unload. WP-G2 records the choice here and pins it with journey J8.

### Workflow layout

- **Navigation.** A left-hand step list with seven steps: Project, Sources, Receptors, Meteorology, Output, Review & Run, and Results. Each step shows a status badge computed from `Validator` (not started, complete, warning or error). Users may move between steps freely; the order is guidance, not a gate.
- **Header.** The header shows the project name, an unsaved-changes marker, a Save button and a one-line readiness summary.
- **Project step.** This step holds the titles, the pollutant, the averaging periods (a multi-select offering the regulatory defaults for the chosen pollutant) and the model options (CONC or DEPOS, FLAT or ELEV, DFAULT, urban). It also holds New, Open, Import deck, Save and Save As.
- **Sources and Receptors steps.** Each shows a table with row actions and an editor with basic and advanced field groups. Labels carry units, help text comes from field metadata, integer fields use integer widgets, and path fields span the full width. The empty-state message appears only while the list is empty. A plan-view plot shows sources and receptors in model coordinates and updates after every change.
- **Meteorology step.** Desktop mode uses a native file dialog through pywebview; browser mode uses a path input that checks the file exists. After a surface file is chosen, the step reads the station IDs, first year and date span from the file and shows the period covered. It warns when ANNUAL is requested with less than a year of data, and it can show a `met_qaqc.run_all_qaqc` summary.
- **Output step.** This step keeps today's fields in clearer groups, and turns on by default the plot files and POSTFILEs that the Results step needs.
- **Review & Run step.** This step shows a validation checklist whose items link to the step that needs attention, and a read-only deck preview with copy and download. The Run button stays disabled while errors remain. Runs execute in the background through `run.io_bound` or an asyncio subprocess, with a progress bar driven by AERMOD's `Now Processing Data For Day No.` lines, a Cancel button and the elapsed time. The final status comes from the parsed `.out` file (see WP-G1). A table lists every error, warning and informational message with its pathway, code, line and text, linking to `docs/common-errors.md` where an entry exists.
- **Results step.** This step refreshes when a run finishes, states which run it shows and whether that run succeeded, and never presents a failed run's numbers as valid. It shows summary cards with the maximum for each averaging period and its location, a table per period, and a concentration map drawn from the plot file. Where the pollutant has a NAAQS, it compares design values through `design_values` and `naaqs`. It offers downloads of the deck, the `.out` file, the plot files and a KMZ, and a run history for reopening earlier runs.

Every control must have an accessible name, either a visible label or an `aria-label`. This is an accessibility requirement and also a testing requirement, because the end-to-end tests locate elements by role and name.

## Test strategy

The tests have four tiers.

| Tier | What it covers | Tooling | Where it runs | Time budget |
|---|---|---|---|---|
| T0 | `Session` operations and events, with no UI | pytest | Default suite, every CI leg | Under 5 s |
| T1 | Pages rendered in-process | `nicegui.testing.User` (the existing harness) | Default suite, every CI leg | Under 15 s |
| T2 | User journeys in a real browser against a real server, with AERMOD replayed from recordings | Playwright with Chromium | New `gui-e2e` job in `tests.yml` (Python 3.12), and `make test-gui-e2e` locally | Under 3 min |
| T3 | The same journeys with a real AERMOD binary | Playwright plus `scripts/build_aermod.sh` | New `gui_e2e_real.yml` workflow modeled on `real_aermod.yml`, run on PRs that touch `gui_v2/`, `runner.py` or `output_parser.py` and weekly | Under 10 min |

### Rules for every GUI test

1. **Assert what the user sees.** Every journey assertion reads rendered text or widget values. Assertions on the session may supplement these but never replace them. Tests may not call a page's `render()` directly. They also may not set up a scenario by mutating the session when a UI path exists; loading a saved project fixture through `Session.open_json` is acceptable.
2. **Locate elements by role and accessible name** (`get_by_role` and `get_by_label` in Playwright, and `marker` or `content` in the `User` harness), never by Quasar CSS classes. If an element cannot be found that way, fix the UI.
3. **Fakes are recordings.** The fake AERMOD replays the stdout, `.out` file, plot files and exit code that the real binary produced. `scripts/record_aermod_fixtures.py` captures them into `tests/fixtures/gui/aermod_recordings/<scenario>/`, alongside a README that names the AERMOD version and build flags. The minimum set of recordings is:
   - a success, using the reference scenario below (`albany_success`);
   - a fatal error that still exits with code 0 (E480, from `1 ANNUAL` with four days of met data; `albany_e480`);
   - a setup error, such as a missing met file (`missing_met`, which stops with fatal error E500 and also exits with code 0);
   - a slow run, in which the fake pauses between progress lines, for testing progress and cancellation. This is an existing recording replayed with a delay between stdout lines (`PYAERMOD_E2E_DELAY`), not a recording of its own.

   WP-G0 also recorded `aertest`, EPA's AERTEST deck imported and written back by the library, for J5. Before replaying, the fake (`tests/e2e/fake_aermod.py`) checks that the deck the GUI wrote is the recorded deck. It ignores `TITLEONE` and `TITLETWO`, compares met file paths by base name and numbers by value, and otherwise prints a diff and exits with code 2, which fails the journey. New tests may not use hand-written `.out` text.
4. **Every step leaves a screenshot.** T2 and T3 save a full-page screenshot at each journey step to `test-artifacts/gui/<journey>/NN_<step>.png`. CI uploads them as an artifact so reviewers can see the GUI on every PR. The screenshots in the GUI guide come from this artifact.
5. **Hidden errors fail the test.** The end-to-end fixture records browser `pageerror` events and console errors, and scans the server log for Python tracebacks when the test ends. Defect D4 appeared only in the server log.
6. **Every journey starts clean,** with a fresh browser context, a fresh server process and its own working directory.

### Infrastructure

- `tests/e2e/conftest.py` starts the app on a free port in a subprocess, with `PATH` pointing at the chosen AERMOD (recorded or real) and a temporary home directory. It waits for the port, yields the base URL, and then stops the server and checks its log. It shares one Chromium instance per session. The environment variable `PYAERMOD_E2E_CHROMIUM` overrides the browser path for containers that ship their own Chromium, because Playwright's pinned browser build may not match. To stay within the time budget, the fixture launches the next journey's server while the current journey runs; each journey still gets a process of its own. A journey names the recording its fake AERMOD replays with `@pytest.mark.aermod_recording("albany_e480", delay=...)`, which tier T3 ignores.
- Register an `e2e` marker in `pytest.ini` and deselect it by default, as `slow` already is. T3 tests skip when no `aermod` binary is on `PATH`, as `test_real_aermod.py` does.
- Add an `e2e` extra to `pyproject.toml` with `playwright>=1.45`. CI installs the browser with `python -m playwright install --with-deps chromium`.
- Put page objects in `tests/e2e/pages.py`, one class per step, so journeys read as user actions and survive layout changes. Layout work edits page objects, not journey bodies.
- Put each journey in its own file (`tests/e2e/test_j01_build_and_run.py` and so on), so parallel work packages change different files.
- Add `make test-gui-e2e` and `make test-gui-e2e-real` targets.

## User journeys (the acceptance specification)

**Reference scenario, "Albany stack."**

- **Meteorology:** `tests/fixtures/epa_official/AERMET2.SFC` and `AERMET2.PFL` (Albany, New York; 1 to 4 March 1988; 96 hours; surface and upper-air station 14735).
- **Source:** one point source, `STACK1`, at (0, 0), emitting 100 g/s from a 65 m stack at 425 K, with an exit velocity of 18 m/s and a diameter of 3 m.
- **Receptors:** polar grid `GRID1` centered at the origin, with 10 rings from 100 m to 1000 m in 100 m steps and 36 radials from 0° in 10° steps.
- **Run options:** pollutant SO2; averaging periods 1, 3, 24 and PERIOD; `MODELOPT CONC FLAT DFAULT`.

On 2026-09-28, a gfortran `-O2` build of v26135 ran this scenario with 0 fatal errors and 6 warnings. It produced maxima of 76.07952 µg/m³ (1-hour), 59.57654 µg/m³ (3-hour), 16.85665 µg/m³ (24-hour) and 5.40459 µg/m³ (PERIOD), all at receptor (519.62, −300.00). WP-G0 reproduced these numbers exactly from the binary, pinned them in `tests/e2e/reference.py`, and recorded the run in `tests/fixtures/gui/aermod_recordings/albany_success/`.

The receptor grid is the GUI's default polar grid, so the user only adds it. The current GUI cannot set averaging periods (WP-G3), and its default is 1 and ANNUAL, which with four days of met data is the E480 scenario of J2. Until WP-G3 lands, J1 therefore stops at a known gap before its run, and the journeys that need a run through the current GUI use the default periods and the `albany_e480` recording.

| ID | Journey | What the user must see | Tiers |
|---|---|---|---|
| J1 | Build the reference scenario from a blank project entirely through the UI, run it and open Results. | The run status reads "Succeeded" with 0 fatal errors. Results shows the four maxima and their location, and the map renders. The downloaded deck matches the deck on disk. | T2, T3 |
| J2 | Build the same scenario with averaging periods 1 and ANNUAL. | Before the run, a warning says ANNUAL needs a full year of met data. If the user runs anyway, the status reads "Failed," the message table lists E480 with its text, and Results does not present concentrations as valid. | T2, T3 |
| J3 | Fill in a project and click New, then edit the new project and save it. | Every step shows the blank project: title, source table, receptor table, met paths and an empty Results step. The unsaved-changes marker clears. Edits made after New appear in the saved file. | T1, T2 |
| J4 | Save As, click New, then Open the saved file through the real upload control. | Every step shows the saved values again, the header shows the file name, and no exception appears in the server log. | T2 |
| J5 | Import `tests/fixtures/epa_official/aertest.inp` with its met files, run it and open Results. | The steps are populated from the deck. The run succeeds, and the 1-hour plot-file values match `AERTEST_01H.PLT` within the tolerance `test_real_aermod.py` uses. | T3 (T2 with a recording) |
| J6 | Open Review & Run on a blank project. | The Run button is disabled. The checklist names the missing source, receptors and met files, and each item links to its step. Fixing each problem clears its item. | T1, T2 |
| J7 | Add, edit and delete sources and receptors of several types. | Table rows, the empty-state message, the plan-view plot and the step badges update after every action. Integer fields show integers, and the deck contains `SURFDATA  14735  1988`. | T1, T2 |
| J8 | Reload the browser in the middle of a project, and again after a run. | The project and the last run are restored, or, if WP-G2 chooses the fallback, an unsaved-changes warning appears before unload. | T2 |
| J9 | Start a long run, watch its progress and cancel it. | Progress advances with AERMOD's day count, and other steps stay usable during the run. Cancel stops the process without leaving an orphaned `aermod`, and the status reads "Cancelled." | T2 (slow recording) |
| J10 | Launch desktop mode. | `pyaermod-desktop` opens a window under xvfb and serves the app. The bundle built by `build_desktop.yml` starts and responds on its port. | `build_desktop.yml` smoke step |

## Work packages

Every work package follows the standing rules in `PLAN-code.md`: tests pin the change, gates pass before merge, documentation moves with the code, and commit messages explain why. In addition:

- Journeys mark each step the current GUI cannot perform as a known gap, rather than marking the whole test `xfail(strict=True)`. The step is wrapped in `with known_gap("D2", "Results tab never refreshes after a run"):`, which names a defect (D1 to D4) or the work package that will deliver the missing feature, for example `known_gap("WP-G4", "no pre-run ANNUAL warning")`. If the block fails with an assertion or a Playwright timeout, the journey stops there and is reported as xfailed with the gap's name and reason, so every step before the gap is still checked. If the block passes, the journey fails with "known gap … appears fixed", which obliges the PR that fixed it to remove the `known_gap`. A failure outside a gap block is a real failure. Steps inside a gap use short timeouts, `tests/e2e/harness.py` implements the mechanism, and `pytest -rxX` lists the gap at which each journey stopped.
- A journey with several independent gaps is split into several tests in the same file, because a known gap stops its test and every gap must be exercised.
- Each PR removes the known gaps it closes, lets those journeys pass, and lists them in its description.
- No PR may add a known gap to a journey or loosen a journey's assertions.
- Each PR description links the screenshot artifact from its CI run.

### WP-G0: Journey harness and failing specifications

This package comes first and blocks every other GUI package except WP-G1.

1. Build the T2 infrastructure described above: the conftest, page objects, marker, extra, Makefile target and CI job with the screenshot upload.
2. Build AERMOD with `scripts/build_aermod.sh`, write `scripts/record_aermod_fixtures.py`, and record the four scenarios. Reproduce the reference scenario's numbers from the binary.
3. Write journeys J1 to J9 against the current GUI. Wrap each step that the current GUI cannot perform in `known_gap(...)`, naming the defect or the work package, as described at the start of "Work packages." Every step before a journey's first gap must pass on the current GUI, which is what proves the harness works. Page objects may be thin now and will be re-pointed when the layout changes; journey bodies should describe user intent and should not need rewriting later.
4. Delete `tests/test_gui_apptest.py`, which tests the removed Streamlit GUI.

**Acceptance:** `make test-gui-e2e` runs the journeys in under three minutes. Each of D1 to D4 has at least one known gap that names it and that the current GUI reaches, and CI uploads the screenshots.

### WP-G1: Honest run status in the library

This package runs in parallel with WP-G0 and touches no GUI code.

1. In `AERMODRunner`, require AERMOD's `AERMOD Finishes Successfully` marker and zero fatal messages in the `.out` file, in addition to exit code 0. Parse the message summary into a new `AERMODRunResult.messages` list (severity, pathway, code, line and text) with counts by severity.
2. Confirm that `BatchRunner` and the command-line runner (`runner.py:737`) inherit the fix.
3. Change `tests/test_real_aermod.py:133` to require `AERMOD FINISHES SUCCESSFULLY`, not any `FINISHES SUCCESSFULLY`.
4. Work oracle-first: test against the E480 and setup-error recordings, and against the real binary in `real_aermod.yml`.
5. Record the change under "Fixed" in `CHANGELOG.md`. It changes behavior for library users whose failed runs were previously counted as successes.

**Acceptance:** the E480 deck yields `success=False` with an E480 entry in `messages`, both from the recording and from the real binary. All existing runner tests pass.

### WP-G2: Session architecture

This package starts after WP-G0. It is the foundation for everything that follows, so it runs alone.

1. Add `gui_v2/session.py` as described under "Target design," and convert the pages to refreshables that subscribe to session events. This fixes D2 and D3.
2. Fix D4 with NiceGUI 3's upload API (`e.file.name` and `await e.file.read()`) and `auto_upload=True`.
3. Make Save As deliver the file through `ui.download` in browser mode and a native save dialog in desktop mode, instead of writing to `/tmp`.
4. Make the reload decision for J8 and record it in this plan.
5. Keep the current tab layout for now so that the diff stays reviewable; the new layout is WP-G3's job.
6. Remove `_render_results` and the state-only assertions from the T1 tests.

**Acceptance:** J3, J4 and J8 pass, and J1's Results step passes with a recorded run (`test_j01_results_follow_the_latest_run`, whose D2 gap WP-G2 removes). No test calls `render()` directly.

### WP-G3: Workflow shell and forms

This package starts after WP-G2.

1. Build the step navigation with badges, the header, a shared page template, responsive widths and correct empty states.
2. Improve the form helper in `_form.py`: integer widgets for integer fields, units and help text, and full-width path fields.
3. Add averaging periods and model options to the Project step, and add the plan-view plot to the Sources and Receptors steps.
4. Update the page objects to match. Do not change journey bodies.

**Acceptance:** J6 and J7 pass, and J1 passes through the new layout. Screenshots at 1280 × 900 and at phone size (390 × 844) show no clipped controls.

### WP-G4: Review & Run

This package starts after WP-G1 and WP-G2 and may run alongside WP-G3, WP-G5 and WP-G6.

1. Add the validation checklist and the deck preview.
2. Detect the met period from the surface file and warn when ANNUAL is requested with less than a year of data.
3. Run AERMOD in the background with progress and cancellation, and show the message table from WP-G1.

**Acceptance:** J2 and J9 pass, and J1's run step passes on T3.

### WP-G5: Results

This package starts after WP-G1 and WP-G2 and may run alongside WP-G3, WP-G4 and WP-G6.

1. Refresh Results when a run finishes, and show which run is displayed and whether it succeeded.
2. Add the summary cards, per-period tables, concentration map and NAAQS comparison.
3. Add the downloads and the run history.

**Acceptance:** J1 and J5 pass on T2 and T3, and every value on the Results step equals AERMOD's own summary tables.

### WP-G6: Import and files

This package starts after WP-G2 and may run alongside WP-G3, WP-G4 and WP-G5.

1. Import `.inp` decks through `read_aermod_input`, using `sandbox=True` for uploaded decks. Show any `unparsed_lines` to the user as a notice.
2. Add met file pickers: a native dialog in desktop mode and a checked path input in browser mode.
3. Add a recent-files list.

**Acceptance:** J5's import step passes. A parametrized T1 test imports every deck in `tests/fixtures/epa_official/`, and each one either populates the project or shows a clear notice, with no exception.

### WP-G7: Documentation, desktop and release notes

This package comes last.

1. Rewrite `docs/gui-guide.md` around the seven steps, using screenshots from the latest end-to-end artifact, and update `docs/desktop.md`.
2. Replace the stale "Adding a New Source Type" steps in `CONTRIBUTING.md`, which still refer to `gui.py`, with the current GUI registry.
3. Add the J10 smoke step to `build_desktop.yml`: launch the built bundle (under xvfb on Linux), wait for its port and fetch `/`.
4. Update `CHANGELOG.md` and draft release notes. Tag a release only when the maintainer approves.

**Acceptance:** `mkdocs build --strict` passes, and J10 passes on Linux, macOS and Windows.

## File ownership

This table lets agents work in parallel without merge conflicts. Where two packages must touch the same file, the later package owns the change and the earlier one leaves a hook.

| Package | Owns | Leaves alone |
|---|---|---|
| WP-G0 | `tests/e2e/`, `tests/fixtures/gui/`, `scripts/record_aermod_fixtures.py`, the `pytest.ini` marker, the `e2e` extra, the Makefile targets, the `gui-e2e` CI job and `gui_e2e_real.yml` | Everything under `src/` |
| WP-G1 | `runner.py`, the runner tests and `tests/test_real_aermod.py` | `gui_v2/` |
| WP-G2 | `gui_v2/session.py`, `state.py`, `app.py`, `pages/project.py`, and the binding code in every page | The page layout |
| WP-G3 | `app.py` (shell), `_form.py`, and `pages/` for Project, Sources, Receptors, Meteorology and Output; `tests/e2e/pages.py` | `pages/run.py` and `pages/results.py` |
| WP-G4 | `pages/run.py` (which may be renamed `review_run.py`) | `pages/results.py` |
| WP-G5 | `pages/results.py` and any new plotting helper under `gui_v2/` | `pages/run.py` |
| WP-G6 | A new `gui_v2/files.py` and the import methods on `Session`; WP-G3 places the Import button | Page layout |
| WP-G7 | `docs/`, `CONTRIBUTING.md`, `build_desktop.yml` and `CHANGELOG.md` | Source code |

## Sequencing

```
WP-G0 ──┐
        ├──> WP-G2 ──┬──> WP-G3 ──┐
WP-G1 ──┘            ├──> WP-G4 ──┤
                     ├──> WP-G5 ──┼──> WP-G7
                     └──> WP-G6 ──┘
```

WP-G1 must merge before WP-G4 and WP-G5, because both display its messages. The plan amounts to eight PRs, of which WP-G0 and WP-G2 are the largest.

## Definition of done

- All ten journeys pass on T2 in the default CI, and J1, J2 and J5 pass on T3.
- No `known_gap` remains in `tests/e2e/`.
- Each of D1 to D4 has a test that fails if the defect is reintroduced.
- The GUI guide's screenshots come from the latest CI artifact.

## Notes from the 2026-09-28 walkthrough

These notes save the next agent time in a fresh container.

- AERMOD builds in about a minute with `apt-get install gfortran` followed by `./scripts/build_aermod.sh aermod`. Put `./bin` on `PATH` before starting the GUI, because the Run page checks for the binary when the page is built.
- If Playwright's pinned browser build is missing but a Chromium is preinstalled, launch with `executable_path` pointing at it rather than running `playwright install`.
- `pytest.ini` adds coverage flags, so run ad hoc selections with `-o addopts=""` when `pytest-cov` is not installed.
- NiceGUI's `ui.upload` does not send a selected file until its upload button is clicked, unless `auto_upload=True` is set.
- The run in the walkthrough finished in 0.1 s, so real-binary journeys are cheap. Their cost is building AERMOD; `real_aermod.yml` already caches the EPA source archive that the build downloads.
- AERMOD also exits with code 0 when a met file is missing: it stops during setup with fatal error E500. Defect D1 therefore covers setup errors as well, and J2 checks both.
- A GUI server started from a test must not inherit `PYTEST_CURRENT_TEST`, or NiceGUI switches to its own test mode and refuses to start. A temporary `HOME` also hides packages installed in the user site-packages unless `PYTHONUSERBASE` is kept. `tests/e2e/harness.py` handles both.
- `AERMODOutputParser` reports an ANNUAL maximum for the reference run, which has no ANNUAL period, because it matches the word ANNUAL in warning W361 and then reads the PERIOD table. The Results step (WP-G5) must not show that entry, and the parser needs its own fix.
