# SDE — gui-docs-macos-signing (what was built)

## Workstream A — docs and packaging
- `gui_v2.main(argv)`: `--host/--port/--no-browser`; clear ImportError without nicegui. Tests in `test_gui_v2_smoke.py`.
- `[all]` extra gains `pywebview`; `min-constraints.txt` pin; `test_packaging.py` pins the extras/conda contract.
- Dockerfile, conda recipe → NiceGUI app and real entry points.
- Teaching guide + refinery assignments rewritten against the real UI (large diff; several Streamlit-only features
  became short scripts — see the table in the agent report / PR description). Solution scripts use `project_io`.
- `met_qaqc.py`: behaviour-neutral SIM102 fix so current ruff is clean.

## Workstream B — signing
- Spec: onedir on macOS, identity from `MACOS_SIGN_IDENTITY`, `packaging/entitlements.plist` (empty by design),
  version from `pyproject.toml`.
- Workflow: secrets check → keychain import → build → verify (incl. per-file Team ID) → launch once → ditto zip →
  notarytool → staple → spctl → cleanup. Release without secrets fails the macOS job.
- `packaging/desktop_entry.py`: `multiprocessing.freeze_support()` (fixes self-relaunch chain).
- `docs/desktop.md`, `RELEASING.md` section 4.

## Deviations from spec / ADR
- CI launches the bundle once (ADR said CI launches nothing) — kept: it is the only automatic check that the
  empty entitlements work under a real Team ID.
- `pyaermod-app` gained CLI flags (needed by the Dockerfile).

## Debt / follow-ups
- `docs/teaching/student-guide.pdf` is stale (built from the old guide).
- No Intel macOS build; no Windows Authenticode signing.
- Developer ID intermediate cert may need importing on the runner if codesign reports "unable to build chain".

## Redirect 2026-11-10 (ADR-002) — Workstream B reversed
- Removed: `packaging/`, `build_desktop.yml`, RELEASING signing section, signing tests. `docs/desktop.md` now
  covers the pip-installed window only. `tests/test_gui_v2_packaging.py` pins that no bundle pipeline returns.
- Added: `pyaermod gui`, `python -m pyaermod.gui_v2`, one-line install hints (SystemExit, conda-aware),
  port-in-use message, `scripts/gui_install_smoke.py`, `gui_install.yml` + reusable `gui_install_smoke.yml`,
  publish gate, v1 `conda-recipe/recipe.yaml` (`pyaermod` + `pyaermod-gui`), SPDX license metadata.
- Deviation: `pyaermod-gui` has no pywebview dependency (no macOS build on conda-forge).
- Debt: recipe targets 2.2.0 sdist but its tests need the next release; workflows unproven on GitHub.
