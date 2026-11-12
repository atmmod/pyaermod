# Staff engineer decisions

- [DISCOVERED] Standards: ruff + pre-commit, mypy ratchet gate (mypy-baseline.txt), 95% coverage gate, Keep-a-Changelog CHANGELOG.md, docs move with code, commit messages explain why.
- [DISCOVERED] "GUI is a thin layer over the library" (PLAN-gui.md decision 2): GUI never writes AERMOD keywords or parses output itself.
- [DISCOVERED] Tests: ~140 test files; GUI journeys under tests/e2e with Playwright against recorded AERMOD runs; real-binary tests gated by workflows (real_aermod.yml, wasm_aermod.yml).

- browser-gui (see browser-gui.md, ADR-001)
