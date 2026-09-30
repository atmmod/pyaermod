# PyAERMOD — GUI Redesign Plan with End-to-End Tests (for agents)

**Repository:** https://github.com/atmmod/pyaermod (main @ `cf46dff`)
**Prepared:** 2026-09-28
**Scope:** `src/pyaermod/gui_v2/`, its tests, the run-status logic in `src/pyaermod/runner.py`, and the GUI's documentation, packaging and CI.

## Status

| Package | State | Notes |
|---|---|---|
| WP-G0 | Done | `make test-gui-e2e` runs the journeys against recorded AERMOD runs in about 100 s. Every known gap listed below is reached on the current GUI. |
| WP-G1 | Done | `AERMODRunner` requires AERMOD's completion banner and zero fatal errors, and results carry the parsed messages. Defect D1 is fixed: both J2 run tests now assert the failed status outright. |
| WP-G2 | Done | `gui_v2/session.py` holds a UI-free `Session`, and every step is rebuilt from it through `gui_v2/_live.py`. Defects D2, D3 and D4 are fixed and Save As no longer writes to `/tmp`. J3, J4, J8 and J1's `test_j01_results_follow_the_latest_run` pass; so does J7's `test_j07_empty_state_message_follows_the_list`, whose WP-G3 gap the live Sources and Receptors sections closed as a side effect, and J7's `test_j07_integer_fields_show_and_write_integers`, whose WP-G3 gap closed when the deck began to be written from the project as its file reads back. T2 gives 32 passed and 10 xfailed. The reload decision is recorded under "Target design". D2 itself is fixed and pinned by `test_j01_results_follow_the_latest_run`. The D2-tagged gap left at `test_j01_build_and_run.py:50` is reached only after both the WP-G3 gap at `:38` and the WP-G4 gap at `:45` are removed; whichever of WP-G3 and WP-G4 lands second removes it (a failure there would then no longer be D2). Project files are now read by type (every nested object rebuilt, every value checked), and T0 plus T1 for `gui_v2` run in about 10 s. |
| WP-G3 | Done | A step list with badges from `Validator` (`gui_v2/steps.py`), a header with the project's name, "(modified)", a readiness line and Save, a shared page template (`gui_v2/_layout.py`), averaging periods and model options on the Project step, a plan view (`gui_v2/plan_view.py`, drawn from the new `pyaermod.footprints`) on Sources and Receptors, 25-row pages in their tables, and a confirmation before New or Open discards changes. `_form.py` gives int fields integer boxes, labels units and help from the new field metadata, keeps a required number when its box is emptied and shows lists without an editor read-only. The Output step writes a plot file and a POSTFILE for every averaging period by default; the Albany recordings were made again. J1's averaging-period gap and J7's plan-view and badge gaps are closed; J1 now stops at WP-G4's message summary. `tests/e2e/test_layout.py` finds no control outside the window on any step at 1280 x 900 or 390 x 844. T2 gives 36 passed and 8 xfailed, every remaining gap WP-G4's, WP-G5's, WP-G6's or D2's. See "Notes from WP-G3". |
| WP-G4 to WP-G7 | Not started | WP-G4, WP-G5 and WP-G6 may start alongside WP-G3. |

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
- A browser reload must never silently lose work.

  **Reload decision (WP-G2, 2026-09-29).** Each browser tab keeps its `Session` as a live object in `app.storage.tab` (NiceGUI's in-memory per-tab store), and a reload restores the project and the last run (J8 pins both). The unsaved-changes warning (the fallback) is not used.

  - *Which session a page gets* (`app._session_for`). A tab's own session is reused on reload. A session found under another tab id is adopted only when no page built on it is still alive, and forked (a deep copy with its runs) otherwise. A page counts as alive from when it is built until NiceGUI deletes its client, about `reconnect_timeout` (3 s) after its socket closes, so a lingering page keeps its claim. Liveness does not come from `tab_id`: NiceGUI clears it on disconnect, and while a synchronous run blocks the loop a duplicate's handshake and the original's disconnect can arrive in either order. When unsure the rule forks, which loses nothing.
  - *Evidence* (NiceGUI 3.17.1, Playwright Chromium, spikes under `scratchpad/spikes/reload/`). A reload keeps the tab id, the title, the sources, the "(modified)" marker and the last run's status; the rebuild after the handshake took 55 to 70 ms. A duplicated tab gets a new tab id and a fork. The observer count returns to one live page's worth after `reconnect_timeout`. In a hidden pywebview 6.2.1 window run like `desktop.py`, every reload arrived under a new tab id with the storage copied; under the owner rule the page builds were "created, forked, forked" with the typed title preserved. Opening a project costs under 1 ms for the Albany scenario and 14 ms for 200 sources and 2000 discrete receptors; a fork (deep copy) 9 ms at that size.
  - *Why not the warning.* `beforeunload` cannot tell a reload from a close, so it would prompt on every reload; choosing "Stay on page" leaves NiceGUI's `__nicegui_tab_closed` flag set, so a later "Duplicate tab" would share the session; and WKWebView never fires it.
  - *Known limits.* Closing the tab or stopping the server discards unsaved changes, because tab storage lives in memory. NiceGUI frees a tab's storage `app.storage.max_tab_storage_age` (30 days) after the storage last changed; every page writes a last-used time into its tab's storage when it is built and, at most once a minute, as its session changes, so a session in use is kept and an abandoned one, or the original left behind by a fork, is freed 30 days after its last use. A desktop reload forks the session. Redis-backed tab storage (`NICEGUI_REDIS_URL`) cannot hold a live session and is not supported; the shell logs a warning when it is set. Handling the desktop window's close (pywebview's `window.events.closing`, whose handler can return `False` to cancel it) is a WP-G7 follow-up. Because a reload now rebuilds every step from the session, the page's build time grows with the project: with N discrete receptors a reload took 0.9 s at N = 2000 and 12.8 s at N = 12000, and switching to Receptors 0.9 s and 6.0 s (the Session itself opens 2000 receptors in 14 ms). The unpaginated Sources and Receptors tables are the cost; WP-G3 paginates them.

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

## Notes from WP-G2

- The Run page still checks for the `aermod` binary when the page is built, as before. WP-G4 decides whether the Run button checks again when clicked; `test_runner_exception_is_reported` relies on today's behaviour.
- On macOS a fresh `HOME` makes matplotlib rebuild its font cache, which can take longer than the harness's 60 s server start timeout. Run the journeys with `MPLCONFIGDIR=<a warmed cache directory>`; the harness passes the variable to the server. A lasting fix is `env.setdefault("MPLCONFIGDIR", ...)` in `tests/e2e/harness.py`, which belongs to WP-G0, so it is only flagged here.
- A WKWebView (desktop) reload arrives under a new tab id and forks the session; see the reload decision.
- The source and receptor editors work on drafts: Save hands the draft to the session, Close discards it. Table rows are addressed by the session's stable keys (`"s3"`, `"r7"`), never by list index or source id, and an event for a key that no longer exists does nothing.
- Every dialog is created in the page's static dialog container (`page_dialogs` in `app.py`), never inside a live section, and carries a marker: `open-dialog`, `save-as-dialog` or `editor-dialog`. Editor dialogs delete themselves when closed. T1 tests find dialogs, tables (`sources-table`, `receptors-table`) and the Project buttons (`project-new`, `project-open`, `project-save`, `project-save-as`) by marker.
- A `live()` builder must not call a `Session` method that emits events, or its section refreshes forever, and must not call `live()` itself (it raises).
- A `live()` section whose builder raises is logged and shows "This part of the page could not be shown" with the error in place; the rest of the page is still built, and the section is rebuilt on the next change. Because the session survives a reload, one bad value used to break every reload of the tab.
- Project files are read by type: `project_io` checks each value against the dataclass annotation of the field it fills and rebuilds nested dataclasses, so a file that loads is one the pages and the deck writer can use. Every deck under `tests/fixtures/` survives a save and an open field for field (`TestEverythingRoundTrips`).
- Number fields have no display `format`: `ui.number` rewrites its value to the format on blur and the binding writes it back, which rounded 1.5e-6 to 0.0. `_form.py` belongs to WP-G3, which may add a display format only if it keeps the stored value exact.
- The shell runs on NiceGUI 3.0, the package's floor: `Client.is_deleted` only exists from 3.13, so `app._is_deleted` falls back to the private flag. `tests/test_gui_v2_shell.py` covers `_session_for` without the >=3.4 test harness, so the minimum-dependencies leg runs it.
- Out of WP-G2's file ownership: `packaging/desktop_entry.py` and the `ENTRY` in `packaging/pyaermod_desktop.spec`. The bundle ran `gui_v2/desktop.py` as its entry script, whose relative imports fail as `__main__`. The bundle was not built here; J10 in WP-G7 verifies it, and the WP-G2 PR description lists it as an out-of-scope fix.
- T1 speed: the `gui` fixture polls bindings and `should_see` every 10 ms and freezes the imported objects out of NiceGUI's per-test `gc.collect()`. Without that, the in-process GUI tests took about 30 s.
- mypy: WP-G2 removes two errors on this machine (69 to 67, Python 3.11; its count matched CI's baseline of 69 before the change). `mypy-baseline.txt` stays at 69, because the baseline is only meaningful measured on CI's Python 3.12 leg (`.github/workflows/tests.yml`); lower it with `scripts/mypy_gate.py --update` once that leg reports 67.
- Saving refuses what opening would refuse: `project_to_json` checks the encoded project with the loader before anything is written, so every Save path raises `ValueError` naming the field (the project stays modified, no file or download is produced), and the Project page reports "Save failed: ...". Numbers that are NaN or infinite are refused on both sides. The form helper can still put such values into the model; see the WP-G3 note.
- Open has no `accept=.json` filter: QUploader drops a filtered-out file without any event the page could report, and a project whose name lost its extension must still open. The loader refuses a file that is not a project by name.
- `clean_file_name` replaces the characters browsers rewrite in a download's name (`"*:<>?|` and control characters) with `_`, so the header names the file the browser saved.
- Harness leftovers for a WP-G0 or WP-G3 follow-up: `journey.server_side_files` (`tests/e2e/harness.py`, swept in `tests/e2e/conftest.py`) no longer has a writer since Save As stopped writing to `/tmp`; remove it together with the `MPLCONFIGDIR` fix above.
- Out of WP-G2's file ownership, to list in the WP-G2 PR description: the `_form.py` change (the `on_change` hook and the removed `format="%.4f"`, WP-G3's file) and the packaging entry-point fix (for WP-G7/J10), besides the `tests/e2e/pages.py` workarounds the WP-G0 comment deferred to WP-G2.
- `Session.import_inp()`, listed under "Target design", is not implemented here: the file-ownership table gives the import methods on `Session` to WP-G6, which adds it with `gui_v2/files.py`.
- Whole numbers: the loader turns a whole float in an `int` field (`2020.0`, as `ui.number` stores it) into the integer and refuses a fraction (`start_year must be a whole number, not 12.5`); it refuses any whole number beyond `2**53` in size, because NiceGUI's orjson cannot send one beyond 64 bits and the tab froze on every reload. Saving writes the project as the loader reads it back (`project_io.check_project`), and `Session.start_run` writes the deck from that same checked copy, so STARTEND and SURFDATA get integers and a value a file could not hold is refused by field name before any run. The session's own project keeps the floats; the widget fix is WP-G3's (below).
- Cancelling Open while a file is still being sent makes NiceGUI 3.17's upload route let Starlette's `ClientDisconnect` escape, and uvicorn logged "Exception in ASGI application" with a traceback. The project is untouched, so `build_and_run` installs a filter on the `uvicorn.error` logger that drops exactly that record: a `ClientDisconnect` raised through `nicegui/elements/upload.py`, possibly inside a one-member exception group. `test_j04_cancelling_open_mid_upload_keeps_the_project` throttles the upload through CDP, cancels it and checks the server log; it fails without the filter.
- `save_project` builds the text first (a refused project creates no directory), writes it beside the target and moves it over the target with `os.replace`, keeping an existing file's mode. A failed write leaves the earlier file whole.
- WP-G3 requirements found in the WP-G2 review:
  - Integer fields need integer widgets (`ui.number(precision=0)`, or a binding that stores `int`): the number boxes store `2020.0` in `start_year` and every other `int` field. The deck and the saved file are repaired on the way out, but the in-memory project, and anything reading it directly (validation, the future plan view), still sees floats.
  - `_form` must not write `None` into a number field that is not `Optional` (an emptied `ui.number` gives `None`), and must not use the free-text list area for `List[<dataclass>]` or `List[Tuple[str, ...]]` fields (`BuoyLineSource.line_segments`, `OutputPathway.maxi_files`, `rank_files`, `plot_file_groups`); show those read-only until they have a proper editor. Saving refuses such a project today, which is safe but late.
  - Paginate or virtualise the Sources and Receptors tables, with a T1 or e2e timing check at about 10k receptors (see the known limits of the reload decision).
  - New and Open discard a modified project and its run history without asking. Add a confirmation when `session.dirty` is true (built in `page_dialogs`), and update the page objects' `new` and `open_file` to answer it.
- WP-G4: `Session.start_run` is synchronous and emits `run_started` and `run_finished` on the caller's thread. A background run must marshal `_emit` onto NiceGUI's loop, and New or Open during a run needs a policy. `cancel_run()` raises `NotImplementedError` while a run is in progress. While a run blocks the loop, every other tab of the server freezes too (a second tab's step click took 5 s during a 3 s fake run); J9 should also check that a second tab stays responsive during a run. Double-clicking Run AERMOD today runs AERMOD twice in the same working directory (the second click is queued behind the blocking first run and overwrites its outputs); the background run must disable the button, or ignore `start_run`, while `session.run_in_progress` is set, and J9 should check that a double-click starts exactly one AERMOD process.

## Notes from WP-G3

- **Navigation.** The step list is a vertical `ui.tabs` in a left drawer (a drawer behind the header's "Steps" button below 1024 px). Tab and panel names are the step ids of `steps.STEP_IDS` (`"project"`, `"sources"`, `"receptors"`, `"meteorology"`, `"output"`, `"run"`, `"results"`); a tab's accessible name is "<label>, <badge>" ("Sources, complete") and a panel's is the step's label. The step shown last is kept in tab storage (`current_step`), so a reload returns to it.
- **goto wiring.** The shell passes `goto(step_id)` to every page whose `render()` names a `goto` parameter, and `actions` (the shared `FileActions`) to one that names `actions`; it inspects each signature (`app._call_render`), so a page from WP-G4, WP-G5 or WP-G6 needs only to accept `goto: Optional[Goto] = None` (`gui_v2._layout.Goto`) to get it, and the integrator has nothing to wire. `goto` raises `ValueError` for an unknown id.
- **Validation.** The shell calls `session.validate(check_files=True)` when the page is built and 0.15 s after the last of a burst of `project_changed` / `project_replaced` events (`app._keep_validated`); the badges and the readiness line follow `validation_changed` and `run_finished`. WP-G4's checklist can read `session.validation` and subscribe to `validation_changed` instead of validating itself; `steps.problems_by_step()` groups the messages by the step that fixes them, which is what a checklist item's link needs. Review & Run's badge follows the latest run and Results' the latest run AERMOD completed; WP-G4 and WP-G5 may refine `steps.step_statuses` for their steps.
- **Page objects.** `RunPage.NAME` is now "Review & Run". `App.step_tab` matches a step by the start of its accessible name, `open_step` opens the drawer when the list is folded away, and returns the panel by its name. Form fields are found by their words with the units optional (`pages._label`). Row buttons are "Edit <name>" and "Delete <name>". `ProjectPage.new` and `open_file` answer "Discard unsaved changes?" when it is asked. `OutputPage.expect_output_type` reads the read-only "Output quantities" box, because what AERMOD computes is now a model option on the Project step. WP-G4 edits `RunPage` in the same file: keep this package's `NAME`.
- **Recordings.** `_empty_project()` now sets `OutputPathway.period_plot_files` and `period_postfiles` to `"pyaermod"`, so the default deck gains `PLOTFILE <ave> ALL [FIRST] pyaermod_<ave>.plt` and `POSTFILE <ave> ALL PLOT pyaermod_<ave>.pst` for each period. `albany_success`, `albany_e480` and `missing_met` were recorded again with `scripts/record_aermod_fixtures.py` and a v26135 binary built by `scripts/build_aermod.sh` (gfortran 15.2, macOS arm64); a fresh recording reproduces them byte for byte apart from timestamps. `aertest` is unchanged: its deck comes from the imported file, not from `_empty_project()`. If WP-G6's import starts from `_empty_project()` and keeps its output pathway, the imported deck gains these lines and `aertest` must be recorded again; the integrator checks this when merging WP-G6.
- **For WP-G5.** The plot files are in every Albany recording's `outputs/` (`pyaermod_01H.plt`, `pyaermod_03H.plt`, `pyaermod_24H.plt`, `pyaermod_PERIOD.plt` for `albany_success`); `OutputPathway.period_plot_file_names(periods)` and `period_postfile_names(periods)` give their names for a project. The failed runs' plot files are empty.
- **The D2 gap** at `test_j01_build_and_run.py:49` stays: it is reached only once WP-G4's gap at `:44` is removed, and WP-G4 merges after WP-G3, so WP-G4 (or the integrator) removes it.
- **Long tables.** The tables send one page of 25 rows; `TestLongTables` opens a saved project with 10,001 receptors and requires a reload to build in under 5 s (before, 12,000 receptors took 12.8 s). The plan view draws at most `plan_view.MAX_POINTS` (20,000) receptor marks and names sources and grids on the plot only when there are at most 40.
- **Widths.** The shell caps every field in a step at `min(100%, 100vw - 3rem)`, so a page from another package that fixes a width (`w-96`, as `pages/run.py` does today) still fits a phone, also inside a `q-gutter` row, whose negative margin makes `100%` too wide. On a phone the closed drawer is not rendered until it first opens and is hidden from the accessibility tree after it closes: a page object that needs a step tab there must open the drawer first, as `App.open_step` does. `test_layout.py` checks every step at both sizes; a page added later is covered as soon as it is a step.
- **Form helper.** No display `format` was added: none keeps the stored value exact through `ui.number`'s blur rewrite. Integer boxes round a typed fraction to the nearest integer. `List[<dataclass>]` and `List[Tuple[...]]` fields other than polygon vertices show "N items" read-only; each needs its own editor, which no package owns yet.
- **mypy.** 67 errors on this machine (Python 3.11) before and after; `mypy-baseline.txt` stays at 69.
- **Library changes,** each with its own tests: `pyaermod._fields` (units and help as field metadata, on every source, receptor, meteorology and output field), `pyaermod.footprints`, `naaqs.naaqs_averaging_periods`, and `OutputPathway.period_plot_files` / `period_postfiles` (passed the run's periods by `AERMODProject.to_aermod_input`; the validator counts them as PLOTFILE and POSTFILE output).
- **Out of WP-G3's file ownership,** to list in the PR description: the library modules above; `gui_v2/state.py` (`_empty_project`, WP-G2's); the three Albany recordings and their README under `tests/fixtures/gui/` and the new `tests/e2e/test_layout.py` (WP-G0's directories); and the module docstrings of `test_j01_build_and_run.py`, `test_j09_progress_and_cancel.py` and `reference.py`, which described the averaging-period gap (no journey body changed except the removed `known_gap` wrappers).
- Still open from the WP-G2 notes: the `MPLCONFIGDIR` default and `journey.server_side_files` in `tests/e2e/harness.py` (WP-G0's).
