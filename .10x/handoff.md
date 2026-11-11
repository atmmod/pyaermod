# Handoff

From: Discovery (orchestrator)
To: Review, then Brainstorming for `browser-gui`

The user asked for (1) a code review and (2) a GUI option that does not depend on signed desktop apps.
Note that (2) is partly met already: `pyaermod-app` runs the GUI in a browser tab from a pip install, and the signed-bundle route was abandoned in #60. The open gap, stated in docs/browser.md, is that the GUI needs a Python server; only notebooks run in the browser. The likely target is a zero-install GUI served from the docs site, running pyaermod and AERMOD-wasm in Pyodide. Confirm with the user before designing.
