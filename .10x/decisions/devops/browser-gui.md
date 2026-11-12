# DevOps: browser-gui
- Build: scripts/wasm/build_lite_site.sh builds /lite and /app from the same two wheels; PYODIDE_VERSION (default 314.0.6) is the single pin for both.
- CI: wasm_aermod.yml (paths now include webapp/**, browser.py, gui_v2/**) runs the Pyodide smoke (AERTEST + browser API) and test_b02 on the release build; tests.yml e2e job runs test_b01 (no wasm needed).
- Deploy: docs.yml (paths now include webapp/**) publishes _site/app with the docs on push to main. No new workflow, no secrets.
- Rollback: revert the merge; the next docs deploy removes /app. /lite and the pip GUI are unaffected.
- Open items: pin Playwright in the wasm step; docs.yml PR runs share the `pages` concurrency group (pre-existing, from the earlier review).
