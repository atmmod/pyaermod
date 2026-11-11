# DevOps decisions

- [DISCOVERED] Workflows: tests (3.11-3.13 matrix, ruff, mypy gate, coverage), docs (mkdocs + JupyterLite site under /lite, GitHub Pages), wasm_aermod (builds AERMOD wasm, runs real-AERMOD tests and Pyodide smoke under Node), publish (PyPI, waits on gui_install_smoke), real_* binary workflows, epa_parity, keyword_oracle, benchmarks.
- [DISCOVERED] JupyterLite pinned: jupyterlite-core==0.8.7, jupyterlite-pyodide-kernel==0.8.7 (docs/lite/requirements.txt).
