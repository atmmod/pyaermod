# Handoff

From: SDE (Phase 4 complete)
To: QA + Security (Phase 5)

Built: see .10x/decisions/sde/browser-gui.md. Review targets: src/pyaermod/browser.py, webapp/*.js, scripts/wasm/app_dev_server.py, input_reader quoting/sandbox changes, wasm_runner/runner changes, build_lite_site.sh /app stage, workflows.
To test: full suite; journeys tests/e2e/test_b01 (local), test_b02 + pyodide smoke (CI only).
Known unverified here: anything that needs Pyodide or the wasm build.
