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
# It also builds the browser GUI (webapp/) beside it, into <app dir>
# (default: an `app` folder next to <output dir>, so _site/lite gets
# _site/app): the page, the same two wheels, the sample met files named in
# webapp/samples.json, and a config.json naming the Pyodide to load.
#
# Usage: build_lite_site.sh <WebAssembly AERMOD build dir> <output dir> [<app dir>]
# Needs: python with `build`, jupyterlite-core and jupyterlite-pyodide-kernel.
# Environment: PYODIDE_VERSION (default 314.0.6, the Pyodide that
# jupyterlite-pyodide-kernel 0.8.7 loads, so both pages run the same Python).

set -euo pipefail

WASM="${1:?usage: build_lite_site.sh <wasm build dir> <output dir>}"
OUT="${2:?usage: build_lite_site.sh <wasm build dir> <output dir>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
WASM="$(cd "$WASM" && pwd)"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
APP="${3:-$(dirname "$OUT")/app}"
PYTHON="${PYTHON:-python}"
PYODIDE_VERSION="${PYODIDE_VERSION:-314.0.6}"

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

(cd "$WORK" && jupyter lite build --contents content --output-dir "$OUT" "${wheels[@]}")
echo "JupyterLite site in $OUT"

# The browser GUI. Every file it loads comes from this folder except
# Pyodide and its packages (numpy, pandas, matplotlib), which come from the
# jsDelivr CDN at the pinned version, as for the JupyterLite site.
rm -rf "$APP" && mkdir -p "$APP/wheels"
cp "$REPO"/webapp/*.html "$REPO"/webapp/*.js "$REPO"/webapp/*.css "$APP/"
cp "$WORK"/wheels/*.whl "$APP/wheels/"
"$PYTHON" - "$REPO" "$APP" "$PYODIDE_VERSION" <<'PY'
import json, shutil, sys
from pathlib import Path

repo, app, version = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
samples = json.loads((repo / "webapp" / "samples.json").read_text())
for sample in samples:
    source = repo / sample.pop("source")      # where the files are in this repository
    for f in sample["files"]:
        target = app / f["url"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source / f["name"], target)
wheels = sorted(f"wheels/{w.name}" for w in (app / "wheels").glob("*.whl"))
names = [w.split("/")[-1].split("-")[0] for w in wheels]
if sorted(names) != ["aermod_wasm", "pyaermod"]:
    sys.exit(f"expected the pyaermod and aermod_wasm wheels, found {names}")
config = {"backend": "worker",
          "pyodide": f"https://cdn.jsdelivr.net/pyodide/v{version}/full/",
          "wheels": wheels, "samples": samples}
(app / "config.json").write_text(json.dumps(config, indent=2))
PY
echo "Browser GUI in $APP"
