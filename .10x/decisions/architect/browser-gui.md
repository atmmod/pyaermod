# Architect: browser-gui

See ADR-001 and the spec. Components and boundaries:
- `pyaermod.browser` (Python, UI-free): the only API the shell uses. JSON in/out; errors as {"ok": false, "error": {kind, message, step}}.
- `gui_v2/readiness.py`: checklist logic shared by both GUIs.
- `site/app/worker.js`: Pyodide host, request-id RPC, files in an in-memory working dir (`/home/pyodide/work`).
- `site/app/app.js` (+ modules): seven steps, schema-driven forms, transport interface.
- `scripts/wasm/build_lite_site.sh`: `/app/` stage.
Failure modes: CDN/wheel load failure; AERMOD fatal error; wasm trap; worker crash; OOM. Each surfaces in the shell as described in the spec.
Data: project JSON (project_io format) is the single source of truth, held by the shell; the worker is stateless apart from files of the current run.
