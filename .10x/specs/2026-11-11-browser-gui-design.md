# Browser GUI (phase 1): design

**Feature slug:** `browser-gui`
**Date:** 2026-11-11
**Status:** approved in brainstorming (approach A, architecture, scope); awaiting spec review

## Problem

The pyaermod GUI (`gui_v2`, NiceGUI) needs a local Python process. The signed desktop bundles that once avoided that were dropped in #60 because unsigned macOS bundles were blocked by Gatekeeper. Since #61 AERMOD 26135 runs as WebAssembly inside Pyodide, but only from JupyterLite notebooks. Students and occasional users need a GUI that opens from a URL, installs nothing, and needs no signed app.

## Goal

A seven-step AERMOD GUI served as static files from the documentation site at `/app/`, running pyaermod and AERMOD-wasm in the browser. Not for regulatory use.

## Non-goals (phase 1)

- AERMET, AERMAP, BPIP, AERSURFACE, AERSCREEN in the browser (AERMAP-wasm with GeoTIFF upload, then AERMET, are phase 2, separate spec).
- KMZ/GeoTIFF export (pyproj and rasterio are not part of the pinned Pyodide distribution used here).
- Background runs, run history beyond the current tab, multi-user features.
- Changing the pip GUI's behaviour, except moving its readiness-checklist logic into a shared UI-free module.

## Users and success criteria

- A student opens `/app/`, builds a one-stack project on the bundled Albany met, runs AERMOD and sees maxima and a contour map, in a current Chromium, Firefox or Safari, with nothing installed.
- A project saved by `pyaermod-app` opens unchanged in `/app/`, and a project saved by `/app/` opens unchanged in `pyaermod-app`.
- EPA's AERTEST run through `pyaermod.browser.run` matches EPA's published 1-hour values at all 144 receptors within 0.01 % (the existing wasm acceptance).
- The page stays responsive during a run, and Cancel ends the run within 2 s.

## Architecture

```
/app/index.html, app.js, app.css     static shell (ES modules, no framework, no build step)
        | postMessage, JSON only, request ids
/app/worker.js                        Web Worker
        loads Pyodide 314.0.6 (same pin as /lite/)
        micropip.install(site-relative URLs of the two wheels in /app/wheels/), never by name
        import pyaermod.browser
```

### `pyaermod.browser` (new, UI-free, runs under CPython and Pyodide)

All inputs and outputs are JSON-serialisable. Errors are returned as `{"ok": false, "error": {"kind", "message", "step"}}`, never raised across the boundary.

| Function | Contract | Built on |
|---|---|---|
| `schema()` | Form schema per class in `gui_v2/pages/sources.py::_SOURCE_TYPES`, the receptor classes and the pathway dataclasses: field name, JSON type, unit, help, default, enum choices, required | `_fields.described` metadata, dataclass fields |
| `new_project()` | Empty project JSON (same as the pip GUI's New) | `gui_v2/state._empty_project`, `project_io.project_to_json` |
| `load(text)` | Checked project JSON, or error naming the bad field | `project_io.project_from_json` |
| `import_deck(text, files)` | Project JSON plus import notice (unparsed lines, files referenced but not supplied) | `read_aermod_input(..., sandbox=True)` on an in-memory directory |
| `apply_terrain(project, name, text)` | Project with receptor (and source) elevations and hill heights set from an AERMAP receptor/source output file or a CSV `x,y,elev,hill`; returns counts matched and unmatched | `terrain.AERMAPOutputParser`; CSV matched to receptors by coordinates within 0.01 m |
| `check(project, met)` | Readiness checklist: items naming their step, plus warnings (e.g. ANNUAL with less than a year of met) | new `gui_v2/readiness.py`, moved out of `pages/run.py` and imported by both GUIs |
| `deck(project)` | Deck text | `AERMODProject` writer |
| `plan_view(project)` | SVG | `gui_v2/plan_view.plan_view_svg` |
| `run(project, met)` | Run summary: status, AERMOD message table, maxima per averaging period, summary tables, contour SVG per plot file, list of output files | `AERMODRunner.run()` (wasm), `AERMODOutputParser`, `gui_v2/run_results.view_of`, `results_map` |
| `file(name)` | Bytes of an output file of the last run, for download | — |

Met files (`met`) are names of files the worker has written into its in-memory working directory: bundled samples or uploads.

### Worker (`worker.js`)

- One request at a time, by id. A run is a single synchronous call inside the worker.
- **Cancel** terminates the worker and starts a new one. The shell keeps the authoritative project JSON and uploaded files (in IndexedDB), so it can restore state into the new worker.
- If Pyodide or a wheel fails to load: one message, a retry button, and a link to the pip GUI.

### Shell (`app.js`)

- The seven steps and their order match the pip GUI: Project, Sources, Receptors, Meteorology, Output, Review & Run, Results.
- Forms are generated from `schema()`, so adding a source type in Python needs no JavaScript change.
- Project JSON is autosaved to `localStorage` (a convenience only, in try/catch). **Save** downloads `.json`, **Open** uploads it, **Import deck** uploads `.inp` plus any files it names.
- Meteorology offers bundled samples (Albany 1988-03, EPA AERTEST `AERMET2.SFC/.PFL`; Houston 1996-02-26 to 29 from `tests/fixtures/deposition_met/`) or upload of `.SFC` and `.PFL`.
- The Receptors step accepts terrain uploads (AERMAP receptor output or CSV) when the terrain type is ELEVATED.
- A banner on every step says: "AERMOD compiled to WebAssembly by pyaermod. Not EPA's executable; not for regulatory use."
- A pre-run warning appears when receptors × met hours exceeds a threshold. The threshold will be measured on the AERTEST build and recorded in the SDE notes.

### Build and deploy

`scripts/wasm/build_lite_site.sh` gains an `/app/` stage. It copies `site/app/` (new, holding the shell sources) and the two wheels it already builds, plus the sample met. `docs.yml` publishes `/app/` alongside `/lite/`, with no new workflow.

## Library fixes included (from `.10x/reviews/2026-11-11-codebase-review.md`)

1. **H4:** the sandbox resolves paths with AERMOD's quoting rules (quotes stripped), so `"../x"` is refused.
2. Quoted filenames containing spaces survive read → write, including in unparsed lines.
3. `SURFDATA` with a float-formatted or alphanumeric station ID is read as AERMOD reads it, not raised.
4. `wasm_runner.find_wasm_aermod(path)` raises when an explicit path holds no build.
5. A wasm trap keeps AERMOD's partial `.out` (collected, renamed, returned).

Each comes with a test that fails without the fix.

## Error handling

- Python exceptions inside `pyaermod.browser` become structured errors naming a step where one applies. The shell shows them inline on that step.
- An AERMOD fatal error is reported as a failed run with AERMOD's message table, as in the pip GUI (no values shown).
- A JS-side worker crash (`error` event): the shell marks the run failed, restarts the worker and restores state.

## Testing

| Tier | Content | Runs in |
|---|---|---|
| T-unit (CPython) | `schema()` covers every `_SOURCE_TYPES` class and every field has a JSON type. Project JSON round-trips with files saved by `gui_v2`'s `project_io.save_project` (a new committed fixture `tests/fixtures/gui/projects/albany_one_stack.json`, plus projects generated in the test). `check()` gives the same items as the pip GUI's Review & Run for the same projects. `apply_terrain` against AERMAP fixtures and CSV. `run()` result shaping with a recorded run (as `tests/e2e` does). Each library fix. | `tests.yml` |
| T-pyodide | `pyodide_smoke.mjs` extended: install both wheels, `browser.run()` on AERTEST, compare maxima with EPA's values | `wasm_aermod.yml` |
| T-browser | Playwright against the built `/app/` served locally: one-stack project on Albany runs and shows maxima; Cancel mid-run returns control within 2 s; a `gui_v2` project opens; deck import plus AERMAP receptor file sets elevations | `wasm_aermod.yml` |

## Risks

- **UI volume for 13 source classes.** Mitigated by schema-driven forms. Source types whose fields are lists (AREAPOLY vertices, RLINEXT) need a list editor; if that proves costly they ship read-only (import only) in phase 1, and the SDE notes say so.
- **Browser memory and time.** No timeout is possible inside a run; Cancel (worker termination) is the only stop. A pre-run size warning covers this.
- **CDN dependency.** Pyodide loads from jsDelivr, as `/lite/` does today. Self-hosting Pyodide is a possible later hardening step, not phase 1.
- **Supply chain.** Wheels are installed from site-relative URLs only, with PyPI fallback impossible by construction (no package names passed to micropip).

## Deliverables

- `src/pyaermod/browser.py`, `src/pyaermod/gui_v2/readiness.py`
- `site/app/` (index.html, app.js, app.css, worker.js)
- the `/app/` stage of `scripts/wasm/build_lite_site.sh`
- tests as above
- `docs/browser.md` section "The GUI in your browser", a link from `docs/gui-guide.md`, and a CHANGELOG entry
