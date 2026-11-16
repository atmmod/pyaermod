# GUI docs and macOS signing — design

**Date:** 2026-11-10 · **Feature slug:** `gui-docs-macos-signing` · **Approved by maintainer:** yes (has Apple Developer Program membership)

## Problem

1. Users conclude the PyPI release has no GUI. It does (2.2.0 wheel ships all of `pyaermod.gui_v2`, the
   `pyaermod-app` / `pyaermod-desktop` scripts and the `gui` / `gui-desktop` extras). The impression comes from
   Streamlit-era material that survived the v2.0 removal of `pyaermod.gui`, and from a raw
   `ModuleNotFoundError: nicegui` when `pyaermod-app` runs without the extra.
2. The macOS desktop app is only ad-hoc signed and not notarized, so Gatekeeper blocks it. The PyInstaller spec
   wraps a onefile EXE in a `.app`, which cannot be notarized.

## Scope

### A. Docs and packaging (no credentials)
- `docs/teaching/student-guide.md`, `docs/teaching/refinery-assignments.md`: port 8501 → `http://127.0.0.1:8080`;
  Streamlit page names → the real steps (Project, Sources, Receptors, Meteorology, Output, Review & Run, Results).
- `docs/teaching/solutions/test_gui_integration.py`: stop importing the removed `pyaermod.gui`.
- `Dockerfile`: launch the NiceGUI app instead of Streamlit.
- `conda-recipe/meta.yaml` (+ its README): entry points match `pyproject.toml`.
- `pyproject.toml`: `all` extra gains `pywebview`; README / `docs/index.md` wording stays true.
- `pyaermod-app` without `nicegui`: exit with an install hint (`pip install "pyaermod[gui]"`), with a test.

### B. macOS signing
- `packaging/pyaermod_desktop.spec`: onedir (`COLLECT` + `BUNDLE`) on macOS; identity from `MACOS_SIGN_IDENTITY`
  (unset → ad-hoc, as today); `packaging/entitlements.plist`; bundle version from the package version; fix the
  stale `gui-modern-desktop` comment.
- `.github/workflows/build_desktop.yml` macOS job: import cert into a temp keychain → build → verify signature →
  `ditto` zip → `notarytool submit --wait` → staple → re-zip → `spctl` check → delete keychain. All signing steps
  are skipped, with a visible warning, when the secrets are absent.
- `docs/desktop.md`: correct asset names and architecture (arm64 only); Gatekeeper workaround for v2.2.0 and
  older builds.
- `RELEASING.md`: secret setup, signing checks, certificate renewal.

## Out of scope
Intel/universal2 macOS build; Windows Authenticode signing; Linux packaging changes.

## Secrets (maintainer adds)
`MACOS_CERT_P12_BASE64`, `MACOS_CERT_PASSWORD`, `MACOS_SIGN_IDENTITY`, `APPLE_API_KEY_P8_BASE64`,
`APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID`.

## Testing
- ruff + full pytest locally (CI gates both, coverage ≥ 95%).
- `tests/test_gui_v2_packaging.py` extended to pin onedir, entitlements and the signing steps.
- Local PyInstaller build of the `.app` (ad-hoc) to confirm the onedir bundle launches, if feasible.
- Real Developer ID signing + notarization can only be verified in CI once the secrets exist.
