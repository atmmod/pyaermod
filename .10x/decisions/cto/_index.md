# CTO decisions

- [DISCOVERED] pyaermod is a Python 3.11+ library wrapping EPA AERMOD and its preprocessors (AERMET, AERMAP, AERSURFACE, BPIP, AERSCREEN). Core deps: numpy, pandas. Optional extras: viz, geo, terrain, met, hpc, cad, gui, gui-desktop.
- [DISCOVERED] GUI: NiceGUI 3 app (`pyaermod.gui_v2`), served by a local Python process (`pyaermod-app`), optionally in a pywebview window (`pyaermod-desktop`).
- [DISCOVERED] PyInstaller desktop bundles were dropped in #60 (Nov 2026) because unsigned macOS bundles were blocked by Gatekeeper; GUI ships via PyPI (and conda-forge, recipe pending).
- [DISCOVERED] #61 compiled AERMOD 26135 to WebAssembly (LLVM Flang from r-wasm + Emscripten) and ships it in a JupyterLite site under the docs (`/lite/`). Results match EPA AERTEST exactly at 144 receptors.

## Active features
- browser-gui (see browser-gui.md)
