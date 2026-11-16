# QA — browser-aermod

- Unit: tests/test_wasm_runner.py (19) with faked Pyodide modules; runner tests unaffected (190 pass).
- CI (wasm_aermod.yml, run 43065753004): build OK; tests/test_real_aermod.py 8 passed against the wasm build
  (AERTEST within rtol 1e-4 at 144 receptors; E480/E500/E322/E140 status detection); SIGTERM test deselected
  (native-process only). Pyodide-under-Node smoke: worst rel diff 0.000, 0.4 s.
- Browser (local JupyterLite, Pyodide 314.0.6): notebook 1 runs, peak 0.139 at (400,-200) = native 26135;
  contour renders. Notebook 2: 144 receptors, rel diff 0 vs EPA.
- Bugs found and fixed by the browser test: fcntl.flock missing in Pyodide; geospatial forced Agg.
- Not verified: docs.yml as modified (runs on PR / main only); deployed Pages site; Firefox/Safari; large runs
  (memory growth beyond 64 MB not exercised).
