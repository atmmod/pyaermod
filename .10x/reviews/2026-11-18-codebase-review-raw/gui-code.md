# gui-code: review of src/pyaermod/gui_v2 (HEAD 794fe60)

Read in full: session.py, app.py, _live.py, _layout.py, _form.py, state.py, steps.py, readiness.py,
plan_view.py, project_io.py, run_results.py, results_map.py, files.py, _native.py, desktop.py,
pages/{project,sources,receptors,meteorology,output,run,results}.py. Skimmed __init__.py (CLI) and
PLAN-gui.md (status, target design, reload decision). Repro scripts: scratchpad/repro/gui-code/.
Not looked at: tests/e2e bodies, docs, browser.py/webapp (other reviewers), live browser behaviour.

## Status of earlier items (2026-11-11 review, GUI rows)
- H1 plan_view._ticks infinite loop: FIXED (index-based loop, MAX_TICKS, MAX_COORDINATE; h1_and_parse.py
  returns at once for 1e18 and +-1e300). But see G2: the same "freeze every user" class remains via grid size.
- Run N's Results reading run N+1's files: STILL PRESENT (G4, now verified).
- Session.fork drops the in-progress run: STILL PRESENT (G7).
- Import deck / reopen recent without the unsaved-changes prompt: STILL PRESENT (G1).
- recent_files.json shared across users in --host mode: STILL PRESENT (G13).
- mkdtemp run dirs never removed: STILL PRESENT (G8).
- Downloads read whole files on the event loop: STILL PRESENT (G9).
- Project JSON uploads skip the deck sandbox: STILL PRESENT (G12).
- PR70 verification item 9 (lower-bound caption for every pollutant): FIXED in gui_v2 (run_results.naaqs_caption adds it only when a row is a lower bound).

## Bugs and GUI defects, by user impact

### G1 [BUG] [high] Import deck, Read deck and Recent files replace the project, and stop a running AERMOD, without asking
- Where: src/pyaermod/gui_v2/files.py:287-341 (`_import_path`, `_on_upload`, `_reopen`)
- What: New and Open go through `FileActions._asked_before_replacing` (pages/project.py:100-119). The three
  import paths and the recent-files buttons call `session.import_inp` / `session.open_json` directly.
  `Session._replaced` (session.py:476-498) also calls `_abandon_run`, so one click on a recent file, or
  choosing a deck, discards unsaved edits and the run history and kills a run in progress, with no prompt.
- Evidence: READ. No call to `_asked_before_replacing` or `confirm` in files.py.
- Fix: give `import_controls` the page's `FileActions` (app.py already builds one per page and passes
  `actions` to project.render) and wrap the replace in `actions._asked_before_replacing(what, do)`;
  for an upload, read and check first (as `_on_upload` in project.py does with a scratch Session) so a
  bad deck never asks.

### G2 [BUG] [high] A large receptor grid (one typo in x_num/y_num or dist_num/dir_num) freezes the server for every user
- Where: plan_view.py:146-161 `_receptor_items` -> footprints.receptor_points (expands every point);
  called from _layout.py:156-158 on the event loop, once per plan view (Sources and Receptors each have one),
  on every sources/receptors change and on every page build/reload.
- What: the plan view materialises nx*ny (or rings*radials) points before thinning to MAX_POINTS. Cost is
  linear, ~0.5 us/point plus ~100 bytes/point: x_num=y_num=3000 takes 4.5 s per plan view (9 s per edit);
  30000 x 30000 (one extra zero) is ~9e8 points, minutes of blocked loop and tens of GB of memory (OOM).
  Because the session survives reloads in tab storage, reloading rebuilds the plan view and freezes again:
  the user cannot get back in to fix the typo. The validator already flags >100,000 receptors, but the
  plan view is drawn regardless.
- Evidence: VERIFIED for 1e6 and 9e6 points (repro/gui-code/perf_biggrid.py: 0.53 s, 4.52 s, linear).
  The 9e8 case is extrapolated, not run.
- Fix: count arithmetically (`x_num*y_num`, `dist_num*dir_num`) and, above MAX_POINTS, sample the grid
  by stride over `x_values()`/`y_values()` (or rings/angles) instead of expanding it; or draw only the
  grid's outline with "N receptors" in its title. Optionally render the two plan views from one cached
  SVG per change (they are identical).

### G3 [BUG] [medium] Header and Meteorology badge say "Not ready" while Review & Run says "Nothing blocks the run" (and the reverse)
- Where: readiness.py:267 (`Validator.validate(project)`, no check_files) vs session.py:800-805 and
  app.py:200 (`validate(check_files=True)`, which resolves relative met paths against the server's cwd,
  validator.py:2078-2088).
- What: with an absolute surface file that exists and a profile file that does not, the header reads
  "Not ready to run: 1 problem in Meteorology" and the badge is red, but the checklist is empty and the
  Run button is enabled; AERMOD then fails in setup (E500). Conversely, a relative met path that exists in
  the chosen working directory (an imported EPA deck run in its own folder) is "file not found" in the
  header while the run works.
- Evidence: VERIFIED (repro/gui-code/header_vs_checklist.py: header "Not ready to run: 1 problem in
  Meteorology", badge error, `review(...).ready == True`, no blocking items).
- Fix: one working-directory-aware file check used by both: in `review`, block on a met file that is not a
  file where AERMOD will open it (resolve as `surface_file_path(met, working_dir)` does, for both files);
  in `Session.validate`, replace Validator's cwd-based `check_files` met check with the same resolution.

### G4 [BUG] [medium] A run's Results can show the next run's deck, .out and plot files when the working directory is reused, under a note saying the values were read "when this run finished"
- Where: session.py:916-917 (deck written before the runner's directory lock), runner.py:629-641
  (`_prepare` deletes the previous `pyaermod_gui.out`), run_results.py:627-685 (`build_view` reads deck,
  .out, PLT/PST by path), run_results.py:799-813 (`watch` starts the build in a thread at RUN_FINISHED),
  pages/results.py:194-198 (the note).
- What: RUN_FINISHED re-enables Run at once (pages/run.py:372-374). If the view thread for run N has not
  hashed/parsed its files when run N+1 starts in the same directory, run N's view gets run N+1's deck, a
  missing or new .out, and run N+1's plot files (the mtime filter `since=started_at(N)` accepts them).
  If no Results page was alive at RUN_FINISHED (tab reloading or closed), the view is built only when
  Results is next shown, possibly after run N+1, deterministically wrong. The stale-file check
  (`RunFile.read`) cannot catch it: the checksum is taken from the wrong file. Two tabs (or a forked tab,
  whose `run_options` copy the working dir) running in one directory also overwrite each other's
  `pyaermod_gui.inp` before the lock is taken.
- Evidence: VERIFIED mechanism (repro/gui-code/workdir_reuse.py: run 1's view built after run 2 started
  holds "RUN TWO" in its deck). The GUI timing window was READ, not reproduced in a browser.
- Fix (smallest): in `pages/run._start`, before `start_run`, await `run_results.prepare(r)` for every
  finished run of the session whose `work_dir` is the same; and build the view eagerly in `Session._finish_run`
  callers regardless of whether a Results page exists (move `watch` from pages/results.render to app.index).
  Write the deck after taking the lock, or name it per run (`pyaermod_gui_run{N}.inp`), so another
  session's run in the same dir cannot replace it.

### G5 [GUI] [medium] Vertex and number-list editors silently drop lines they cannot parse, including AERMOD's own space-separated format
- Where: _form.py:455-476 (`_parse_pairs`, `_parse_numbers`), used by _form.py:552-575
- What: `"100 200"` (how AREAVERT writes vertices) and `"1,5"` are dropped without a word. The textarea
  still shows what the user typed, the model holds fewer (or zero) vertices, the plan view shows nothing,
  and the validator then says "must have at least 3 vertices".
- Evidence: VERIFIED (repro/gui-code/h1_and_parse.py: `_parse_pairs("100 200\n300 400\n300 500") == []`,
  `_parse_numbers("1,5\n2") == [2.0]`).
- Fix: split pairs on commas, semicolons or whitespace (`re.split(r"[,;\s]+", s)`), and show a validation
  message on the textarea naming the line numbers that were not read instead of suppressing ValueError.

### G6 [GUI] [medium] Source and receptor editors close on a click outside or Esc and discard every edit without asking
- Where: pages/sources.py:242-265, pages/receptors.py:134-154 (`ui.dialog()` without `persistent`)
- What: the editor works on a deep-copied draft; Quasar closes a non-persistent dialog on backdrop click
  and Esc, and `on_value_change` then deletes it. A 20-field source typed in and lost to a stray click.
- Evidence: READ (Quasar QDialog default behaviour; no `persistent` prop anywhere in gui_v2).
- Fix: `.props("persistent")` on both editor dialogs (Close stays the explicit discard), or confirm on
  close when the draft differs from the original.

### G7 [BUG] [medium] Session.fork drops the in-progress run: a desktop reload during a run orphans AERMOD
- Where: session.py:1045-1056; app.py:116-138
- What: PLAN-gui.md records that a desktop (pywebview) reload always arrives under a new tab id while the
  old page lingers, so it forks. The fork has `run_in_progress=None` and no `_run_handle`: the new page
  shows no progress, offers no Cancel, enables Run, and the run's result is recorded only in the orphaned
  session that no page shows. Starting another run in the same directory blocks on the runner's lock
  ("Starting AERMOD ...") until the orphan ends. A duplicated browser tab gets the same view (the
  original tab keeps the run, which is defensible there).
- Evidence: READ.
- Fix: when forking a session with a run in progress for a desktop reload (no other live owner after the
  linger, or always), hand the run over: move `run_in_progress`, `_run_handle`, `_run_serial`,
  `_pending_progress` to the fork and bump the original's serial; or, simpler, adopt instead of fork when
  the only other owner is disconnected (`client.has_socket_connection` false).

### G8 [BUG] [medium] Temporary run directories are never removed, and POSTFILEs are on by default
- Where: session.py:913-915 (`tempfile.mkdtemp`), state.py:51-53 (period_postfiles on by default)
- What: every run with a blank working directory leaves deck, .out, PLT and one POSTFILE per period in
  /tmp; nothing removes them on New/Open, when the run leaves the history, or at shutdown. The Output step
  itself warns a POSTFILE can be several GB, so a long-running server fills its disk.
- Evidence: READ (no rmtree/cleanup anywhere in gui_v2).
- Fix: record temp dirs the session created (a flag on RunRecord); remove them when the record leaves
  `session.runs` (in `_replaced`) and in the shutdown hook, after the view has been built.

### G9 [BUG] [medium] Downloads read and hash whole files on the event loop; KMZ export too
- Where: pages/results.py:589-595 -> run_results.py:165-176; pages/results.py:619-638 -> _kmz_bytes
- What: a multi-GB POSTFILE is read into memory and SHA-256'd on the loop, then sent as bytes: every tab
  stalls for seconds and memory spikes by the file size.
- Evidence: READ.
- Fix: make `fetch` async: `await run.io_bound(file.verify)` (chunked hash, as `RunFile.of` already does)
  then `ui.download(file.path, file.name)` so NiceGUI streams from disk; run `_kmz_bytes` through
  `run.io_bound`.

### G10 [GUI] [medium] NAAQS verdict "Below the NAAQS" does not say it is the modelled concentration without background
- Where: run_results.py:477-487 (verdicts), 491-503 (caption); pages/results.py:472-500
- What: for a project with no BACKGRND the table states "Below the NAAQS" for the modelled design value
  alone; NAAQS compliance is judged on modelled plus background. Nothing on the step mentions background.
- Evidence: READ (no "background" in any Results text).
- Fix: when the project has no `sources.background`, word the verdict "Modelled value below the NAAQS
  (no background added)" or add one caption sentence; when it has one, say AERMOD's values include it.

### G11 [BUG] [low] OLMGroup problems: the badge marks Sources, the checklist links to Project
- Where: readiness.py:88-101 (`_step_for_pathway`, substring rules) vs steps.py:71-103 (`step_of`, table)
- What: two mappings from validator pathway to step disagree for "OLMGroup(...)" (validator emits it),
  and for unknown heads ("run" vs "project").
- Evidence: VERIFIED (repro/gui-code/steps_vs_checklist.py).
- Fix: delete `_step_for_pathway`; use `steps.step_of(pathway)` mapping "run" to "project" (see C1).

### G12 [BUG] [low] Uploaded project files skip the sandbox uploaded decks get
- Where: session.py:542-570 (`open_json`), pages/project.py:133-155
- What: an uploaded deck may not name files outside its folder (`read_aermod_input(sandbox=True)`), but an
  uploaded project JSON can name any absolute output path (OU PLOTFILE/POSTFILE/SUMMFILE ...) that the run
  then writes, and `period_plot_files`/`period_postfiles` stems (GUI-only fields the deck sandbox never
  sees) can contain "../". Under the documented --host trust model this is low, but the asymmetry is real.
- Evidence: READ (input_reader._validate_paths_within exists and takes a project and a base).
- Fix: for uploads (bytes), call `_validate_paths_within(project, <empty temp dir>)` plus a check of the two
  stems, and show the same DeckImportError-style message.

### G13 [BUG] [low] Recent files are one list for every user of a --host server
- Where: files.py:148-153
- What: users see and can reopen each other's server-side paths. STILL PRESENT.
- Fix: in --host mode (host not loopback), keep the list in `app.storage.user` or disable it.

### G14 [GUI] [low] "Deck file path" refuses ~ and relative paths with an AERMOD-specific reason
- Where: files.py:318-325 reuses `file_problem` (files.py:82-103)
- What: the deck is read by Python, which can expand ~, but the field says "AERMOD does not expand ~" and
  for a relative path "a relative one is read from the run's working directory"; the `.expanduser()` on
  line 324 is unreachable.
- Fix: a deck-path check that expands ~ and resolves relative to the server's cwd, or drop `expanduser`.

### G15 [BUG] [low] Uploads have no size limit, are read whole into memory and a project is parsed twice on the loop
- Where: pages/project.py:86-89, 139-159; files.py:359-361, 303-304
- What: choosing a multi-GB file by mistake in Open/Import loads it into memory and json-parses it (twice
  for a project: scratch Session at 143, again at 159) on the event loop.
- Fix: `ui.upload(max_file_size=...)` (e.g. 200 MB) with `on_rejected` notifying; keep the project parsed
  by the scratch session (`self.session` can take it via a small `Session.replace_project(project, name)`).

### G16 [BUG] [low] Map contour check is O(n^2) for receptors on one line
- Where: results_map.py:30-39 `_can_contour`
- What: returns early only on a non-collinear triple; a fence line of 10,000 discrete receptors does
  ~5e7 Python iterations (in a worker thread, so slow map, not a frozen loop). READ.
- Fix: O(n): take p0, the first point distinct from it p1, return True at the first k with
  cross(p1-p0, pk-p0) != 0.

### G17 [GUI] [low] Browser "Save as" marks the project saved before the browser has saved anything
- Where: session.py:682-695, pages/project.py:202-215
- What: `save_as_download` clears "(modified)" when the bytes are handed to `ui.download`; if the browser's
  save prompt is cancelled the project reads as saved, and closing the tab then loses it without warning.
- Fix: word the notification "Download started" and keep this documented; there is no download receipt.

## Concision and clarity (behaviour identical)

### C1 [CONCISION] [low] One pathway-to-step mapping
- readiness.py:88-101 `_step_for_pathway` -> `steps.step_of` (map "run" to "project"); ~14 lines,
  also fixes G11. Covered by tests/test_gui_v2_run.py (one test calls `_step_for_pathway`), test_gui_v2_steps.py.

### C2 [CONCISION] [low] pages/run.py re-export block
- pages/run.py:42-66 re-exports 24 readiness names with `noqa: F401`; `_add`, `_home_met_files`,
  `_met_files`, `_missing_output_folders`, `_ordered`, `_relative_met_files`, `MISSING_OUTPUT_FOLDER`,
  `RELATIVE_OUTPUT` are used nowhere through `pages.run` (grep of tests/ and browser.py). Drop them:
  ~8 lines. Tests: test_gui_v2_run.py.

### C3 [CONCISION] [low] Dead and duplicated helpers
- _layout.py:31-32 and 161-162 (`no_goto`, `required_goto`): unused anywhere; ~6 lines with `__all__`.
- pages/results.py:75-76 `_OUTPUT_TYPES` duplicates run_results.OUTPUT_TYPES (212-213).
- pages/results.py:172-177 `_gone` duplicates app.py:98-107 `_is_deleted`; move one copy to _live.py.
- run_results.py:825-829 (`overwritten_by.same`) duplicates `_same_file` at 287-291 in the same module.
- run_results.py:369-372 `_years_in` re-implements output_parser `_YEARS_HEADING`, already imported by
  `table_qualifier` (110). Together ~20 lines. Tests: test_gui_v2_results.py, test_gui_v2_run_results.py.

### C4 [CONCISION] [low] app._call_render signature sniffing
- app.py:219-228 uses `inspect.signature` so "a page from another work package that does not take them
  yet still builds". All seven pages are in-tree; give every `render` the same keyword-only signature
  (`dialogs, goto=None, actions=None`, unused ones `del`'d as sources/receptors already do) and call it
  directly: ~10 lines and the `inspect` import. Tests: test_gui_v2_shell.py, app smoke.

### C5 [CONCISION] [medium] Sources and Receptors share one editor dialog and one paged table
- pages/sources.py:242-307 and pages/receptors.py:134-198 are the same code: dialog with title, editor_body,
  Close/Save (add vs update, "was removed" warning), `on_value_change` delete; a live table with
  ROW_ACTIONS_SLOT, edit/delete events, Pager controls and the empty message. A `_layout.editor_dialog(dialogs,
  title, draft, save: Callable[[], bool], gone: str)` and `_layout.item_table(session, part, rows_fn, columns,
  noun, empty_text, on_edit, on_delete)` save ~40 lines and make G6's fix one line.
  Tests: test_gui_v2_sources.py, test_gui_v2_receptors.py, e2e J7.

### C6 [CONCISION] [medium] _form.py's string-annotation parser is never reached by any form the GUI shows
- _form.py:103-164 (`_wrapper_name`, `_is_numeric_list_node`, `_leaf_names`, `_numeric_info_str`),
  202-214, 229-230, 300-313 (`_str_kind`), 319-320, 326-332, 350-358: ~120 lines that run only when
  `typing.get_type_hints` fails. It fails only for ChemistryOptions, which no step renders; every source,
  receptor, MeteorologyPathway, OutputPathway and BuoyLineSegment resolves (repro/gui-code/hints.py). If a
  fallback is wanted, resolve with project_io's namespace (`project_io._types().hints(cls)`, which already
  handles ChemistryOptions) and drop the parser. Requires removing the string-form parametrisations in
  tests/test_gui_v2_form.py:84 and tests/test_gui_v2_sources.py:107-182; rendered behaviour unchanged.

### C7 [CONCISION] [low] Message table as ui.table
- pages/run.py:432-455 builds a raw <table> with one element per cell; AERMOD lists up to 999 warnings
  (aermod.f SUMTBL, 4165-4199), i.e. ~13k elements rebuilt on every RUN_STARTED/RUN_FINISHED and page build.
  `ui.table(columns, rows, pagination=25)` with a body-cell slot for the help link: ~10 lines shorter.
  Tests: test_gui_v2_run.py, e2e J2.

### C8 [CONCISION] [low] Enum name/value helpers
- pages/project.py:407-428: four functions of one pattern -> `_enum_name(v)` and `_enum_value(cls, name)`;
  ~8 lines. Tests: test_gui_v2_pages_d.py.

### C9 [CONCISION] [low] session.py responsibilities and WP markers
- ~15 lines of `# WP-G6` / `# --- end WP-G6` / `# WP-G4` markers (221, 276, 288, 305, 364-365, 400, 407,
  482-484, 489, 572, 657, 1054-1055, 1059, 1099) record history PLAN-gui.md already has; delete them.
- Deck import (DeckImport/DeckImportError/MET_FILE_FIELDS/_MET_KEYWORDS 221-276, import_inp/_read_deck
  572-657, helpers 1059-1099; ~180 lines) can move to gui_v2/deck_import.py, with `Session.import_inp`
  a 10-line method calling it: same behaviour, session.py down to project/keys/runs. Re-export the
  names from session.py so imports keep working. Tests: test_gui_v2_import.py, test_gui_v2_session.py.
