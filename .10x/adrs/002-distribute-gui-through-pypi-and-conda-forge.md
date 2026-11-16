# ADR-002: Distribute the GUI through PyPI and conda-forge only; stop building desktop bundles

**Status:** Accepted
**Date:** 2026-11-10
**Feature:** gui-docs-macos-signing
**Author:** 10x-Team (Architect + Staff Engineer)
**Supersedes:** ADR-001

## Context
ADR-001 kept the PyInstaller desktop bundles and added Developer ID signing and notarization for macOS.
The maintainer then decided against shipping downloadable desktop apps at all and asked for a conda-forge
package and a robust PyPI installation of the GUI instead. The 2.2.0 wheel already contains `gui_v2`, the
console scripts and the `gui` / `gui-desktop` extras; what was missing was proof that a clean install works
and a conda route.

## Decision
- Remove the PyInstaller spec, entry script, entitlements file and `build_desktop.yml`. No release carries
  desktop binaries. The `pyaermod-desktop` command and the `gui-desktop` extra stay (pip-installed pywebview).
- PyPI: the GUI is installed with `pip install "pyaermod[gui]"` (also pipx / uv). A smoke script installs the
  built wheel into a clean environment and starts the GUI; CI runs it, and `publish.yml` runs it before upload.
- conda-forge: a recipe under `conda-recipe/` with two outputs, `pyaermod` (core) and `pyaermod-gui`
  (core + NiceGUI), because conda has no extras. It targets a published PyPI sdist and is submitted through
  conda-forge/staged-recipes by the maintainer.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|-------------|------|------|---------|
| Keep signed/notarized bundles (ADR-001) | Double-click install | Apple secrets, per-OS build upkeep, no Windows signing | Maintainer chose to drop it |
| Single conda package with GUI deps always installed | One name | Forces NiceGUI on library-only users | Mirrors the PyPI extra poorly |
| PyPI only | Nothing to submit | Conda users (GDAL stack) left to mix pip into conda envs | Audience largely uses conda |

## Consequences

### Positive
- No signing secrets, no notarization, no per-platform binary builds.
- The install path users follow is the one CI exercises.

### Negative
- Users need a Python environment; there is no double-click app.
- The 2.2.0 release still has unsigned desktop assets attached until the maintainer removes them.

### Risks
- conda-forge review may ask for recipe changes; the feedstock then needs a maintainer.
- A GUI dependency missing from conda-forge would block the `pyaermod-gui` output.

## Dependencies
- The conda recipe can only point at a version already on PyPI.
- Constrains future work: any return to desktop binaries needs a new ADR.
