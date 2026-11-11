#!/usr/bin/env bash
# build_lite_site.sh — Build the JupyterLite site that runs pyaermod and AERMOD in the browser
#
# The documentation workflow (.github/workflows/docs.yml) puts the result
# under /lite/ of the GitHub Pages site. It holds:
#   - JupyterLite with the Pyodide kernel (Python compiled to WebAssembly);
#   - wheels for pyaermod (built from this checkout) and aermod_wasm (the
#     WebAssembly AERMOD from scripts/build_aermod_wasm.sh), which the
#     notebooks install with %pip from the site itself;
#   - the notebooks in docs/lite/content/ (written by make_lite_notebooks.py)
#     and, in their data/ folder, EPA's AERTEST deck, its met files and EPA's
#     published 1-hour plotfile, copied from tests/fixtures/epa_official/.
#
# Usage: build_lite_site.sh <WebAssembly AERMOD build dir> <output dir>
# Needs: python with `build`, jupyterlite-core and jupyterlite-pyodide-kernel.

set -euo pipefail

WASM="${1:?usage: build_lite_site.sh <wasm build dir> <output dir>}"
OUT="${2:?usage: build_lite_site.sh <wasm build dir> <output dir>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
WASM="$(cd "$WASM" && pwd)"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
PYTHON="${PYTHON:-python}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

"$PYTHON" -m build --wheel --outdir "$WORK/wheels" "$REPO"
"$PYTHON" "$SCRIPT_DIR/make_aermod_wasm_wheel.py" "$WASM" "$WORK/wheels"

cp -R "$REPO/docs/lite/content" "$WORK/content"
mkdir -p "$WORK/content/data"
FIXT="$REPO/tests/fixtures/epa_official"
cp "$FIXT/aertest.inp" "$FIXT/AERMET2.SFC" "$FIXT/AERMET2.PFL" "$WORK/content/data/"
cp "$FIXT/AERTEST_01H.PLT" "$WORK/content/data/EPA_AERTEST_01H.PLT"

wheels=()
for w in "$WORK"/wheels/*.whl; do wheels+=(--piplite-wheels "$w"); done

cd "$WORK"
jupyter lite build --contents content --output-dir "$OUT" "${wheels[@]}"
echo "JupyterLite site in $OUT"
