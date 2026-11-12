# ADR-001: Browser GUI as a static shell over a Pyodide worker and a JSON API

**Status:** Accepted
**Date:** 2026-11-12
**Feature:** browser-gui
**Author:** 10x-Team (Architect + Staff Engineer)

## Context
The NiceGUI GUI needs a Python server. Signed desktop bundles were abandoned (#60). AERMOD 26135 runs as WebAssembly in Pyodide (#61), with `AERMODRunner.run()` working unchanged there, but `start()` (threads/processes) does not. NiceGUI cannot run in Pyodide (FastAPI + socket.io server). The library rule "the GUI is a thin layer over the library" (PLAN-gui.md decision 2) must hold for any new GUI. GitHub Pages is not cross-origin isolated, so SharedArrayBuffer-based interrupts are unavailable.

## Decision
- A new UI-free module `pyaermod.browser` exposes the GUI's operations as functions taking and returning JSON-serialisable values (schema, load/dump, import_deck, apply_terrain, check, deck, plan_view, run, file). It is tested under CPython and imported unchanged under Pyodide.
- Readiness-checklist logic moves from `gui_v2/pages/run.py` to `gui_v2/readiness.py` and is imported by both GUIs.
- A static shell (`site/app/`: HTML, ES modules, no framework, no bundler) renders forms from `schema()` and talks to a dedicated Web Worker over a request-id RPC. The worker hosts Pyodide 314.0.6 and installs the pyaermod and aermod_wasm wheels from site-relative URLs.
- Cancel = terminate the worker and start a new one; the shell holds the authoritative project JSON and uploaded files.
- The shell's transport is an interface (`postMessage` to a worker in production; HTTP to a CPython dev bridge in tests), so journeys can run without the wasm build.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Voici / ipywidgets dashboard | Reuses JupyterLite build; least code | Widget-grade UX; awkward multi-step flow; cancel = kernel restart with notebook semantics | UX ceiling too low for 13 source classes |
| stlite / Panel in Pyodide | Python-only UI | Pins its own Pyodide, may conflict with the AERMOD-wasm build; project left Streamlit in v2.0 | Version coupling risk |
| Hosted NiceGUI server | Real EPA binary; existing GUI | Hosting cost and ops; multi-user isolation (review found shared recent-files); not zero-install for offline use | Ongoing ops burden on maintainer |
| JS framework (React/Vue) with bundler | Rich components | Adds a Node toolchain to a Python project; harder for maintainers | Not justified for form-driven UI |

## Consequences
### Positive
- No install, no signing, no server; deploys with the existing docs workflow.
- Project JSON shared with the pip GUI; validation and deck writing have one implementation.
- The page stays responsive during runs; Cancel actually stops AERMOD.
### Negative
- A second UI to maintain (JS). Mitigated by schema-driven forms and a small shell.
- Not EPA's executable: not for regulatory use.
- First load downloads Pyodide + numpy + pandas + matplotlib (tens of MB) from jsDelivr.
### Risks
- CDN unavailability: clear error with a link to the pip GUI; self-hosting Pyodide later.
- Memory on large grids: pre-run size warning.
- Drift between the two GUIs: shared `readiness.py`, shared project JSON, parity tests.

## Dependencies
- Depends on #61's wasm build, `wasm_runner`, `project_io`, `_fields` metadata.
- Constrains phase 2: AERMAP/AERMET-wasm plug in as further `pyaermod.browser` functions.
