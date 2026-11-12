# SRE: browser-gui
- No server to keep up: GitHub Pages serves static files; availability = Pages + jsDelivr.
- SLO (informal): the page loads and runs AERTEST in a current Chromium; checked on every change to the relevant paths by wasm_aermod.yml.
- Monitoring: none in production (no telemetry by design: nothing leaves the browser). Signal = CI on change + user issues.
- Runbook:
  - "The app could not start": jsDelivr down or blocked (school networks) -> users install the pip GUI; long term, self-host Pyodide under /app.
  - Run never ends / tab memory grows: large grid x long met; use Cancel; advise smaller domains (pre-run warning is open debt).
  - Saved project will not open: page offers it as a download; fix the file or report the error text.
- Escalation: GitHub issues on atmmod/pyaermod.
