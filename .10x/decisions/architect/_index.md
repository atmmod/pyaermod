# Architect decisions

- [DISCOVERED] Library layering: pathways/sources/receptors -> input_generator (AERMODProject.write) / input_reader (deck -> project) -> validator -> runner (AERMODRunner, native subprocess or wasm under Pyodide) -> output_parser / postfile -> design_values / naaqs / visualization.
- [DISCOVERED] GUI layering (PLAN-gui.md): UI-free `gui_v2/session.py` Session with observer events; pages are NiceGUI refreshables rebuilt from the session; runs in background via AERMODRunner.start().
- [DISCOVERED] Browser path: `wasm_runner.py` loads aermod.js/aermod.wasm synchronously in Pyodide, mounts Pyodide FS via PROXYFS, runs AERMOD in the cwd; AERMODRunner.run() works unchanged. start() (background) is not available in Pyodide.

## Active features
- browser-gui (see browser-gui.md)
