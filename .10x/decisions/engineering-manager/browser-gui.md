# EM: browser-gui task plan

Constraint found 2026-11-12: this container cannot build or download AERMOD-wasm (no Docker daemon; gaftp.epa.gov and GitHub artifact storage blocked). T-pyodide and the wasm half of T-browser are verified in CI (wasm_aermod.yml) on the pushed branch. Locally, journeys drive the real shell against a CPython dev bridge with recorded AERMOD runs.

| # | Task | Depends | Size |
|---|---|---|---|
| T1 | Reader/writer quoting: quote-aware tokens (quotes stripped, titles exempt), writer quotes fields with blanks, UnparsedLine quoting; sandbox therefore checks the real path (H4) | - | M |
| T2 | SURFDATA/UAIRDATA: read 14735.0 and 1988.0 as AERMOD does; a non-numeric station id is kept verbatim (unparsed) not raised | - | S |
| T3 | find_wasm_aermod(explicit path) raises when the path holds no build | - | S |
| T4 | A wasm trap keeps AERMOD's partial .out | - | S |
| T5 | gui_v2/readiness.py: move checklist logic out of pages/run.py; pip GUI imports it; parity unchanged | - | M |
| T6 | pyaermod.browser core: envelope, schema, new/load/dump, check, deck, plan_view | T5 | M |
| T7 | pyaermod.browser: import_deck, apply_terrain (AERMAP output, CSV) | T1, T6 | M |
| T8 | pyaermod.browser: run, file (results shaping via run_results.view_of) | T4, T6 | M |
| T9 | site/app: worker.js, transport, shell with seven steps, schema forms, met samples/upload, terrain upload, save/open/import, results | T6-T8 | L |
| T10 | Dev bridge (tests/browser_bridge.py) + Playwright journeys; pyodide_smoke extension | T9 | M |
| T11 | build_lite_site.sh /app/ stage, docs/browser.md, gui-guide link, CHANGELOG | T9 | S |
