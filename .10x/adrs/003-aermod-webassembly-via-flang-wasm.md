# ADR-003: Run AERMOD in the browser via LLVM Flang → WebAssembly, driven from Pyodide

**Status:** Accepted · **Date:** 2026-11-10 · **Feature:** browser-aermod · **Author:** 10x-Team

## Context
The maintainer wants visitors to run pyaermod — including real AERMOD runs — from the GitHub Pages site.
AERMOD is ~95k lines of fixed-form Fortran 90 (modules, ALLOCATE, file I/O). pyaermod core is numpy+pandas
(available in Pyodide). The NiceGUI GUI needs a Python server and cannot run in Pyodide.

## Decision
Compile AERMOD with r-wasm's patched LLVM Flang (the compiler webR uses) and Emscripten into a
non-modularized `aermod.js`/`aermod.wasm`, instantiated synchronously inside the JupyterLite Pyodide worker.
`pyaermod.wasm_runner` drives it through Emscripten's MEMFS and `callMain`. Delivered as a JupyterLite site
under `/lite/` of the existing mkdocs Pages deployment.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| LFortran WASM backend | Single tool, no Emscripten | Incomplete F90 coverage, untested on codes this size | Too much risk of unfixable gaps |
| f2c + Emscripten | Mature | Fortran 77 only | AERMOD uses F90 modules |
| Server-side runs (Binder, Actions) | Native binary, exact | Not in-page; Binder slow/unreliable; Actions needs auth | Fails "nothing installed, in the page" |
| pyaermod-only lite site (no AERMOD) | Trivial | No real runs | Maintainer chose full scope |
| Async MODULARIZE build + `await` in notebooks | Standard Emscripten pattern | `AERMODRunner.run()` is sync; would fork the API | Sync instantiation in a worker keeps one API |

## Consequences
+ Same pyaermod API runs natively and in the browser; teaching notebooks need no server.
− Numerical results may differ slightly from EPA's gfortran/Intel binaries; must be measured (parity) and
  labeled non-regulatory. − Depends on a third-party compiler fork (r-wasm/llvm-project); pin image digest.
− Download size (wasm + Pyodide) — first load several MB.
**Risks:** Flang may miscompile or lack a runtime feature AERMOD uses (spike gates this); large static
arrays may exceed default wasm memory (ALLOW_MEMORY_GROWTH); sync compile limits apply only on the main
thread (JupyterLite kernel runs in a worker).

## Dependencies
Pyodide/JupyterLite versions; flang-wasm image digest; Emscripten 5.0.7 (must match the runtime's build).
