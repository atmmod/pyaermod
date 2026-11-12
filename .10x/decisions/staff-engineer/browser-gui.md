# Staff engineer: browser-gui

- Follow existing conventions: ruff, mypy ratchet (no increase), Keep-a-Changelog, commit messages that explain why, tests that fail without the change.
- `pyaermod.browser` must not import nicegui, threading-dependent code or subprocess at import time; a unit test imports it with nicegui blocked.
- Reuse, do not copy: project_io, plan_view, run_results.view_of, results_map, Validator, AERMAPOutputParser, gui_v2/pages/sources._SOURCE_TYPES.
- JS: plain ES2020 modules, no build step, no third-party JS. Escape all text inserted into the DOM (textContent, never innerHTML with data). SVG from Python is inserted only from the trusted worker.
- Security: wheels by URL only; deck import through sandbox=True; uploaded file names cleaned to a basename.
