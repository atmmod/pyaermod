# Browser AERMOD on GitHub Pages — design

**Date:** 2026-11-10 · **Branch:** feat/browser-aermod · **Approved by maintainer:** 2026-11-10

## Goal
A visitor to https://atmmod.github.io/pyaermod/lite/ can, with nothing installed, build an AERMOD deck with
pyaermod, run real AERMOD, and parse/plot the results — all client-side.

## Decisions (maintainer)
- Scope: full — real AERMOD runs in the browser (not just deck generation).
- Interface: JupyterLite (Pyodide kernel) with example notebooks. No hand-built form page.

## Components
1. **WASM AERMOD** — EPA AERMOD source compiled with r-wasm patched LLVM Flang 23 + Emscripten 5.0.7
   (`ghcr.io/r-wasm/flang-wasm:main`) to `aermod.js` + `aermod.wasm`. Non-modularized, sync instantiation,
   MEMFS, `callMain`. Fresh instance per run (Fortran globals are not reset); compiled module cached.
2. **`pyaermod.wasm_runner`** — used by `AERMODRunner` when `sys.platform == "emscripten"`. Copies deck and
   referenced met/input files into the module FS, runs main, copies outputs back. Native path unchanged.
3. **JupyterLite build** in `docs.yml` → `_site/lite/`: pyaermod wheel from the checkout, WASM AERMOD, a
   bundled EPA test-case met set, 2–3 notebooks. Docs home links "Try it in your browser".
4. **CI** — workflow builds WASM AERMOD in the container (source via `scripts/fetch_epa_source.sh`), runs a
   parity check under Node against native gfortran results on EPA test cases, uploads the artifact.
5. **Labeling** — unofficial WebAssembly build of EPA AERMOD vNNNNN; teaching/exploration; not regulatory.

## Gate
Task 1 is a feasibility spike: compile + reproduce one EPA test case under Node. Fail → stop, report.

## Error handling
- Runner returns the same `AERMODResult` shape as native; AERMOD non-zero exit / missing output surfaces as
  the existing failure fields with stdout/stderr captured from Emscripten `print`/`printErr`.
- If the WASM files are missing in Pyodide, raise a clear error naming what is missing.

## Testing
- Unit tests for wasm_runner with a fake JS module (no browser needed) to keep 95% coverage.
- Node parity script on EPA test cases (CI).
- Manual/Playwright smoke of the deployed lite site (browser pane).

## Out of scope
AERMET/AERMAP in WASM, the NiceGUI app in the browser, terrain downloads (CORS).
