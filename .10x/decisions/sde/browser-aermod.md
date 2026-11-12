# SDE — browser-aermod (what was built)

- `scripts/build_aermod_wasm.sh` — EPA AERMOD → aermod.js + aermod.wasm in `ghcr.io/r-wasm/flang-wasm` (digest-pinned
  in the workflow). Non-modularized glue, sync instantiation (WASM_ASYNC_COMPILATION=0, INVOKE_RUN=0), 16 MB stack,
  64 MB initial memory, growth to 4 GB, NODEFS + PROXYFS. WASM_DEBUG=1 adds names/assertions.
  - Deviation 1: v26135 uses gfortran-only DSIND/DCOSD/DTAND → perl rewrite to F2023 SIND/COSD/TAND (13 lines).
  - Deviation 2: Flang lowers `_FortranAioInquireLogical` with an i32 keyword hash (runtime: u64); wasm-ld turns
    it into a trapping stub (the spike's "unreachable"). Each file goes through LLVM IR; calls are renamed to
    `scripts/wasm/inquire_shim.c`, which restores the hash. Build fails on any other signature mismatch.
- `scripts/wasm/run_aermod_node.cjs` — runs the build under Node; a wrapper named `aermod` lets the real-AERMOD
  tests drive it.
- `src/pyaermod/wasm_runner.py` — finds the build (path, $PYAERMOD_AERMOD_WASM, `aermod_wasm` package), loads it
  per run, mounts Pyodide's top-level dirs via PROXYFS at the same paths, runs main.
- `runner.py` — under emscripten: executable = aermod.js; run() calls wasm_runner (no timeout); start() raises
  NotImplementedError; directory lock skipped (Pyodide's fcntl has no flock — found in the browser test).
- `geospatial.py` — no longer calls `matplotlib.use("Agg")` at import (it hid plt.show() in notebooks, desktop
  Jupyter too); contours use an off-screen `Figure`.
- `scripts/wasm/make_aermod_wasm_wheel.py` (stdlib-only wheel), `make_lite_notebooks.py` (2 notebooks →
  docs/lite/content), `build_lite_site.sh`, `pyodide_smoke.mjs`; `docs/lite/requirements.txt` pins JupyterLite 0.8.7
  (Pyodide 314.0.6).
- Workflows: `wasm_aermod.yml` (push/PR/dispatch/workflow_call); `docs.yml` calls it and builds `_site/lite`.
- Docs: `docs/browser.md`, nav entry, link from index.

Tech debt: the IR rename and SIND rewrite are workarounds for compiler gaps; revisit when r-wasm Flang fixes
InquireLogical lowering. Site is ~70 MB (JupyterLab assets); Pyodide loads from jsDelivr.
