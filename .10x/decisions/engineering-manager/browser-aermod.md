# Plan — browser-aermod
1. Spike: build image (flang-wasm + emsdk 5.0.7), compile AERMOD, run one EPA test case under Node, diff. GATE.
2. `wasm/Dockerfile` + `scripts/build_aermod_wasm.sh` (reproducible, pinned).
3. `src/pyaermod/wasm_runner.py` + `AERMODRunner` dispatch on emscripten; unit tests with a fake JS module.
4. Node parity script over several EPA test cases; record tolerances.
5. JupyterLite build (`docs/lite/` config, notebooks, bundled met), docs.yml step, docs link + labeling.
6. Workflow `wasm_aermod.yml` building the wasm artifact; docs.yml consumes it.
7. Verify locally in browser pane (jupyter lite serve), ruff, full pytest, mkdocs --strict.
