# gui-live: hands-on review of both GUIs (NiceGUI gui_v2 and webapp/)

Repro scripts: `S/repro/gui-live/s*.py` (S = the scratchpad dir). Screenshots: `S/repro/gui-live/shots/`.
All runs used the e2e harness (`tests/e2e/harness.GuiServer`, fake AERMOD replaying recordings) imported unchanged.
The webapp was driven through `scripts/wasm/app_dev_server.py` (CPython backend, replayed AERMOD), exactly as test_b01 does; Pyodide/wasm itself was not loaded (no network).

## Baseline
`pytest -m e2e tests/e2e -x`: first attempt ERRORED at test_b01 because Playwright wants `chromium_headless_shell-1255`
and only `-1254` is in ~/Library/Caches/ms-playwright. With the harness's own `PYAERMOD_E2E_CHROMIUM` pointing at the 1254
headless shell: **71 passed, 3 skipped, exit 0** (143 s). (Environment issue, not a GUI defect: the venv's Playwright is newer than the cached browser.)

## Coverage of the brief's items 1-7
1 First run: covered at 1280 and 390 (NiceGUI fully; webapp blank steps at both widths plus import/run/results at 1280).
2 Mistakes: covered (blank/long/spaced/non-ASCII/duplicate IDs, text and blank in number boxes, negative height, missing met file, surface without profile, `~` and relative paths, zero receptors, 30,276-receptor grid, 321-char and non-ASCII titles). Partial STARTEND inconclusive.
3 Work safety: covered (New, Open, Import deck upload, Read deck by path, reload, Back/Forward, close tab, Save As round trip). Reopen-recent read in code only.
4 Running: covered (progress, cancel, double click, run twice, edit during run, failed E480 run, history select). Webapp cancel not driven.
5 Results: covered (cards, tables, map + Map shows, NAAQS, summary tables, downloads, KMZ, history). Map zoom: none exists.
6 Layout/a11y: covered (overflow at both widths, Tab order, Enter, focus, contrast measured, a11y tree). Dark mode: NiceGUI offers none; webapp has prefers-color-scheme CSS, not screenshotted.
7 Console / failed requests: captured in every script: **no console errors, page errors, failed requests or HTTP >= 400, and no server tracebacks** in any NiceGUI or webapp session.
Not looked at: desktop (pywebview) mode, real Pyodide/wasm boot and its loading screen, Output-step mistakes, deposition, KMZ opened in Google Earth, POSTFILE > 100 MB.

Earlier review (2026-11-11, line 18): "Import deck / reopen recent replace the project without the unsaved-changes prompt" — STILL PRESENT (G1). "Run N's Results can read run N+1's files" — now disclosed and downloads disabled (fixed as far as the user sees, s5).

---

### G1 GUI high NiceGUI: Import deck replaces unsaved work without asking (also Read deck and reopen recent)
- Where: src/pyaermod/gui_v2/files.py:287-341 (`_import_path`, `_on_upload`, `_reopen`); New/Open use the confirm at pages/project.py:111
- What: Steps: Open roundtrip.json, change Title (header shows "(modified)"), click Import deck..., pick aertest.inp. The project is replaced at once; title now "A Simple Example Problem...". No question; edits lost. New and Open ask "Discard unsaved changes?" in the same situation, and the webapp asks before Import (app.js:184). Expected: the same confirm as New/Open.
- Evidence: VERIFIED for upload (s4_safety.py, shots/s4_*import_with_unsaved.png); READ for Read deck and recent files (no confirm in `_import_path`/`_reopen`). Documented in gui-guide.md ("replacing it without asking, so save first"), which does not make it safe.
- Fix: route the three entry points through the same `confirm(...)` New/Open use when `session.dirty` or a run is in progress.

### G2 GUI high NiceGUI: closing the tab loses unsaved work with no warning
- Where: app; the only `onbeforeunload` is NiceGUI's own (nicegui.js:395), which never prompts
- What: Steps: change title, add source S1, close the tab, open the URL again. Blank "Untitled run", no sources; the browser never asked. Expected: a beforeunload prompt while the project is modified (and while a run is going).
- Evidence: VERIFIED s4b_close.py (dialogs: [] ; reopened title "Untitled run", sources []). Documented in "Sessions and browser tabs".
- Fix: `ui.add_head_html` a script that sets `window.addEventListener('beforeunload', e => { if (window.__pyaermod_dirty) e.preventDefault(); })`, with the session toggling `__pyaermod_dirty` via `ui.run_javascript` when the modified flag changes.

### G3 GUI high webapp: after a reload the "(modified)" flag is gone, so New/Open/Import discard unsaved work without asking
- Where: webapp/app.js:29 (`dirty: false` at boot), 154 (`discardOk`), store.js saves only the document
- What: Steps: type a title (header "UNSAVED TITLE (modified)"), reload (title kept, header now "UNSAVED TITLE", no "(modified)"), click New: project replaced with "Untitled run", no confirm. Before the reload, New asked.
- Evidence: VERIFIED s9b_dirty.py.
- Fix: store the dirty flag (and fileName) with the document in store.js and restore it in boot.

### G4 GUI high Both GUIs accept source IDs AERMOD cannot read and still say "Ready to run"
- Where: editor (gui_v2 _form.py / webapp forms.js) and validator.py `_validate_source` (no ID-format rule); readiness.py
- What: A PointSource with ID "" (blank), "ABCDEFGHIJKLMNOP" (16 chars) or "A B" saves without comment; header "Ready to run", Run enabled. Deck lines: `LOCATION           POINT ...` (blank ID: AERMOD would read POINT as the ID), `LOCATION  ABCDEFGHIJKLMNOP POINT` (AERMOD E230 "Source ID field is too long (>12)", soset.f:2075, modules.f:2226), `LOCATION  A B      POINT` (shifted fields). The editor's own hint says "up to 12 characters". The webapp shows the blank one as "(no name)".
- Evidence: VERIFIED s3b_ids.py (NiceGUI), s9_webapp.py (webapp); Fortran cited for E230; blank/space outcome PLAUSIBLE (deck is malformed; exact AERMOD message not run).
- Fix: in the validator, error when a source ID is empty, longer than 12 characters, or contains whitespace; the editors then refuse Save with that message at the field.

### G5 GUI high Results never says the project changed since the run it shows (both GUIs)
- Where: gui_v2/pages/results.py; webapp app.js `resultsStep`
- What: NiceGUI: start a run (emission 100 g/s), change STACK1's emission rate to 200 while it runs, open Results: "Run 1 succeeded", 76.07952 µg/m³, nothing says these numbers are for 100 g/s and the project now says 200; header reads "Ready to run". Same after a change made after the run, and in the webapp (rate set to 999 after Run 1: Results unchanged, no note). Results do correctly name the run ("Run 1 succeeded", start/finish, working dir).
- Evidence: VERIFIED s5_running.py (shots/s5_*results_after_change.png), s9_webapp.py (s9_24_results_after_edit.png).
- Fix: keep the deck text (or a hash) the run was started with in the run record; when it differs from the current deck, show a banner on Results and Review & Run: "The project has changed since Run N. These results are for the project as it was; run again to update them."

### G6 GUI high NAAQS row says "design value ... Below the NAAQS" from 4 days of data; the caveat is off-screen
- Where: gui_v2/pages/results.py NAAQS table; run_results.py
- What: Albany run (96 hours), SO2: row reads Compared "design value", Result "Below the NAAQS". The only caveat, "(4 days of hourly values; the NAAQS form needs 3 years)", is in the 7th column; the table is 1635 px wide in a 982 px box at 1280, so the column is scrolled out of view (at 390 only Standard and NAAQS are visible). The caption under it, "A screening comparison uses the highest value...", describes a basis no row uses. The webapp wraps the table so the caveat is visible, but still says "Below the NAAQS".
- Evidence: VERIFIED s2_firstrun.py, s7_results.py (shots/s7_1280_01_naaqs_viewport.png; overflow numbers printed).
- Fix: when the data cover less than the standard's form, make Result read "Not comparable: 4 days of data, the form needs 3 years" (or "Screen only"), put that text in the Result cell, and show the screening caption only when a row is a screen.

### G7 GUI medium Meteorology shows the surface file's station IDs and year but keeps 0 / 0 / 2020, and stays green
- Where: gui_v2/pages/meteorology.py; defaults in state.py `_empty_project`
- What: After entering AERMET2.SFC the step prints "Its header names surface station 14735 and upper-air station 00014735; its data start in 1988", while the fields below still read 0, 0, 2020. Badge "complete", header "Ready to run". AERMOD then warns W530 for SURFDATA and UAIRDATA (meset.f:1980-1993); the year feeds ISYEAR's leap-year logic (meset.f:253-278; consequence PLAUSIBLE). A student following the screen has no prompt to copy them.
- Evidence: VERIFIED s2_firstrun.py (shots/s2_1280_06_met_files_only.png).
- Fix: when the surface file is read and the station fields still hold the defaults, fill them from the header (with a notice), or show "Use these values" and a Meteorology warning on mismatch.

### G8 GUI medium Editor saves invalid values silently; the error appears only on Review & Run
- Where: NiceGUI source editor (_form.py), webapp forms.js
- What: Stack height -5 or a second source "NEG" saves with no message in the dialog or the Sources table; the only signal is a red badge and, on Review & Run, "PointSource NEG stack height must be > 0, got -5.0" / "Source id duplicate source ID 'NEG'". Two identical rows each have an "Edit NEG" button. Expected: the problem shown at the field, Save refused for a duplicate ID.
- Evidence: VERIFIED s3_mistakes.py (shots/s3_05, s3_06, s3_15), s9_webapp.py.
- Fix: validate the edited source on Save (the validator already produces these messages) and show them under the field; refuse a duplicate ID.

### G9 GUI medium NiceGUI: a cleared or non-numeric number field silently keeps the old value
- Where: gui_v2/_form.py number inputs
- What: Clear "Stack height (m)" (or type "abc", which the input drops) and Save: no message, and the deck has 10.00 (the placeholder). The field showed empty. The webapp does this right ("Enter a number.", Save refused, test_b08).
- Evidence: VERIFIED s3b_ids.py (deck SRCPARAM 10.00 after clearing), s3_mistakes.py.
- Fix: treat an empty required number as invalid: red field "Enter a number", Save disabled.

### G10 GUI medium NiceGUI Sources table: a long ID pushes Edit/Delete out of view
- Where: gui_v2/pages/sources.py table
- What: With a 16-character ID in the table, the Actions column is beyond the table's right edge at 1280 (header shows ID...Units only); the user must find the horizontal scroll to edit or delete anything.
- Evidence: VERIFIED shots/s3_09_sources_after_mistakes.png.
- Fix: make Actions the first or a sticky column, or cap/ellipsize the ID column.

### G11 GUI medium NiceGUI contrast below WCAG AA on key messages
- What (measured, text vs background): header title/readiness/Save 3.06:1 (white on rgb 88,152,212, 14-16 px); the E480/ANNUAL warning text 1.70:1 (rgb 242,192,55 on white) — the most important pre-run warning is the least legible text on the page; "Nothing blocks the run." green ~2.6:1; "No run yet..." 2.68:1.
- Evidence: VERIFIED s8_a11y.py (CONTRAST output); shots/s3_11_met_surface_only.png.
- Fix: a darker primary (e.g. #1565C0), warning text in dark amber (#7A5200) with the icon carrying the colour, positive text #1B7F3B, grey text >= #6b6b6b.

### G12 GUI medium NiceGUI Review & Run and Results have no headings for screen readers
- What: Project's panel has h2/h3 headings; Review & Run and Results (the longest page) have none in the accessibility tree: "Results", "Maximum for each averaging period", "Concentration map", "Comparison with the NAAQS", "Downloads" are plain text. Visually their titles are also smaller and indented differently (x=264 vs 272) from the other steps.
- Evidence: VERIFIED a11y snapshot runs/s2_1280/a11y_results.txt (0 headings), s8_a11y.py.
- Fix: render these titles with the same heading helper Project uses (role=heading, aria-level 2/3).

### G13 GUI medium Blank NiceGUI project defaults to ANNUAL, so the first run on short met fails with E480 though the GUI predicted it
- What: Default periods "1, ANNUAL". With any sub-year met file the GUI shows the E480 prediction (as a low-contrast warning, G11) but allows Run; AERMOD then fails (albany_e480). The webapp's blank project uses "1, PERIOD", so the two GUIs also disagree.
- Evidence: VERIFIED s6_failed.py, s9 deck preview (AVERTIME 1 PERIOD).
- Fix: default to 1 and PERIOD in gui_v2 (as webapp does), or make the certain-E480 case a blocking checklist item.

### G14 GUI low Progress row stays "writing the results / Elapsed 0:00" after the run ended
- What: After success or failure, the row still reads "Day 64 of 1988 (4 of 4 days), writing the results  Elapsed 0:00" above "Succeeded in 0.4 s" / "Failed: E480...". The Run log is empty until the run ends.
- Evidence: VERIFIED shots/s2_1280_10_run_done.png, s6 output.
- Fix: remove or freeze the progress row ("Finished: 4 of 4 days") when the status changes; stream the log tail during the run.

### G15 GUI low Checklist wording duplicates field names
- What: "Source id duplicate source ID 'NEG'", "Total receptors total receptors 30276 > 10000; runtime will be large", "PointSource NEG stack height must be > 0, got -5.0".
- Fix: drop the field-name prefix when the message already names it; "Source NEG: stack height must be above 0 m (is -5)".

### G16 GUI low Keyboard and dialog details (NiceGUI)
- What: Enter in an editor field does not save; after the dialog closes focus goes to <body>, not back to Add/Edit; the dialog has no accessible name (a11y_dialog.txt: "- dialog:"); the focus indicator on buttons/tabs is a 22% grey wash, faint on white. Tab order itself is sensible (header Save, one step tab with arrow keys, panel, fields in order).
- Evidence: VERIFIED s8_a11y.py.
- Fix: `aria-labelledby` on the dialog title, return focus to the opener, Enter submits, a 2px outline for :focus-visible.

### G17 GUI low Required profile file has no inline message
- What: Surface given, profile blank: the profile field shows nothing; only the checklist says "Profile file must not be empty". A nonexistent surface path, by contrast, is flagged inline ("No such file on this computer").
- Evidence: VERIFIED shots/s3_11_met_surface_only.png.
- Fix: show "Required" under an empty met field once the other is filled.

### G18 GUI low Results tables and map are static
- What: No column sorting (Max header has no aria-sort) and the map is a PNG with no zoom or hover; at 390 px it is very small. Summary tables are short (10 rows) so paging is not needed.
- Fix: optional; at least a link to open the map PNG full size.

### G19 GUI low Very long titles accepted silently
- What: A 321-character Title (line 1) is accepted with no hint; AERMOD keeps 200 characters (coset.f TITLES, ILEN_FLD=200, modules.f:92).
- Fix: maxlength or a counter on the title fields.

### G20 GUI low Download names do not identify the project or run
- What: Every run downloads as pyaermod_gui.inp / pyaermod_gui.out, so two runs' files collide as "pyaermod_gui (1).out". KMZ is named run1_PERIOD.kmz (good).
- Fix: prefix with the project name and run number.

### G21 GUI low Browser Back leaves the app
- What: Step changes add no history, so Back from any step goes to the previous site (about:blank here); Forward restores the project from the server, so nothing is lost.
- Evidence: VERIFIED s4_safety.py.
- Fix: push a URL fragment per step (#sources) and restore it on popstate.

---

## Five things that work best (do not regress)
1. Readiness: header line ("Not ready to run: 4 problems in Sources, Receptors, Meteorology"), per-step badges in the tab names, checklist with "Go to <step>" links, Run disabled until clear; met file inspection ("AERMET2.SFC holds 1988-03-01 to 1988-03-04") with the E480 prediction and a link to Project; inline "No such file", `~` and relative-path warnings.
2. Running: progress by AERMOD day ("Day 62 of 1988 (2 of 4 days)"), Cancel, double click starts one run (4 starts for 4 runs), a role=status live region, AERMOD message table with "About E480" help links.
3. Failed and superseded runs are honest: "Run 1 failed ... No results are shown for a failed run", fatal errors listed, only deck and .out offered; the run-history select ("Run 2, finished 16:08:44: succeeded") and the note when a later run overwrote a run's files (downloads disabled).
4. Save As / Open round trip is exact (deck and JSON identical after reopen and re-save); New/Open ask "Discard unsaved changes?" with a clear explanation; reload restores project, step and history; in the webapp the project survives a reload (localStorage).
5. Accessible names: every field labelled with units ("Stack height (m)"), tabs named with status ("Sources, complete"), map alt text with the maximum and its location, KMZ refuses without a UTM zone with a specific message, and the webapp's number validation ("Enter a number.", "Not saved: correct Stack height").
No console errors, failed requests or server tracebacks occurred in any session.
