# Architect — gui-docs-macos-signing

See spec `.10x/specs/2026-11-10-gui-docs-and-macos-signing-design.md` and ADR-001.

- Two independent workstreams with disjoint files, run by parallel agents:
  - **A (docs/packaging):** teaching docs, teaching solution script, Dockerfile, conda recipe, `pyproject.toml`
    `all` extra, README / `docs/index.md`, `src/pyaermod/gui_v2/__init__.py` install hint + test.
  - **B (signing):** `packaging/pyaermod_desktop.spec`, `packaging/entitlements.plist`,
    `.github/workflows/build_desktop.yml`, `tests/test_gui_v2_packaging.py`, `docs/desktop.md`, `RELEASING.md`.
- `CHANGELOG.md` is written once by the orchestrator after both finish.
- Failure mode to preserve: with no signing secrets the workflow must still produce an (ad-hoc) macOS artifact.
