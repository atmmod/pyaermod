# SDE: browser-gui (what was built)

## Built
- Library fixes (T1-T4): quote-aware runstream tokens (quotes kept on the field), `pathways.unquote_path`/`quote_path`, sandbox judges the unquoted path (H4), validator/anchor use them; SURFDATA/UAIRDATA whole numbers; explicit wasm path is final; wasm trap keeps .out.
- T5 `gui_v2/readiness.py` (moved from pages/run.py, re-exported).
- T6-T8 `src/pyaermod/browser.py`: `call(op, json)` envelope; schema, new_project, load, new_item, check (pip GUI checklist + not-uploaded inputs), deck, plan_view, import_deck (inputs flattened to names, outputs sandboxed, deck read from a scratch dir), apply_terrain (AERMAP receptor/source output via TerrainProcessor helpers, CSV), run (Session.start_run synchronous + run_results.view_of), get/put/list/remove_file. Non-finite floats become null at the boundary.
- T9 `webapp/` (index.html, app.css, app.js, forms.js, rpc.js, store.js, worker.js, samples.json): seven steps, schema-driven forms, Worker/HTTP backends, Cancel = worker restart + upload replay, localStorage/IndexedDB persistence.
- T10 `scripts/wasm/app_dev_server.py`; `tests/test_browser.py` (27); `tests/e2e/test_b01_browser_app.py` (11 journeys, CPython backend, replayed AERMOD); `tests/e2e/test_b02_browser_app_wasm.py` (CI only); `pyodide_smoke.mjs` extended.
- T11 `/app/` stage in build_lite_site.sh; wasm_aermod.yml step; docs.yml/wasm paths; docs/browser.md, gui-guide.md; CHANGELOG.

## Deviations from the spec
- Shell sources in `webapp/`, not `site/app/` (`site/` is mkdocs' gitignored output).
- Maps are PNG data URLs (results_map draws PNG), not SVG.
- Quoted file names: the model keeps AERMOD's quotes rather than the writer re-quoting (no change to ~25 writer sites). Code that opens files strips them with `unquote_path`.
- Deck import flattens input paths to names instead of refusing `../` (EPA decks name ../meteorology/...).
- Pre-run size warning (receptors x hours) NOT implemented; left as debt.
- List-valued source fields: AREAPOLY vertices editable ("points"); nested dataclasses (deposition params, BUOYLINE segments, barriers) edit as JSON under Advanced.

## Not verified in this container
- No Docker daemon; gaftp.epa.gov, jsDelivr and GitHub artifact storage blocked. So Pyodide loading, the worker, and AERMOD-wasm runs through pyaermod.browser are verified only by CI (pyodide_smoke.mjs, test_b02).

## Tech debt
- Pre-run size warning.
- HttpBackend Cancel (dev server only) aborts the request but the server finishes the run.
- Pyodide from jsDelivr (no SRI); self-hosting is a later hardening step.
- `pathways` pre-existing ruff UP012 in scripts/wasm/make_aermod_wasm_wheel.py untouched.
