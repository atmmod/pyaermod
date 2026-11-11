#!/usr/bin/env bash
# build_aermod_wasm.sh — Compile EPA AERMOD to WebAssembly (aermod.js + aermod.wasm)
#
# The browser build of pyaermod (JupyterLite on the documentation site) runs
# AERMOD inside the page. This script compiles EPA's Fortran source with the
# LLVM Flang that r-wasm patches to emit wasm32-unknown-emscripten (the
# compiler webR uses) and links it with Emscripten.
#
# It must run where that compiler is installed: inside the r-wasm image,
#
#   docker run --rm --platform linux/amd64 -v "$PWD:/src" -w /src \
#       ghcr.io/r-wasm/flang-wasm@sha256:<digest> \
#       bash scripts/build_aermod_wasm.sh <aermod source dir> <output dir>
#
# The image is amd64 only. On Apple silicon Docker emulates it, which is slow
# and memory hungry; .github/workflows/wasm_aermod.yml builds it natively.
#
# Output (in <output dir>):
#   aermod.js     Emscripten glue, not modularized: evaluate it with a Module
#                 object already defined (see scripts/wasm/run_aermod_node.cjs
#                 and pyaermod.wasm_runner). Instantiation is synchronous when
#                 Module.wasmBinary is given, so Python can drive it without
#                 awaiting a Promise.
#   aermod.wasm   the compiled model
#   BUILD.txt     build record: AERMOD version, compiler versions, flags, SHA-256
#
# Environment:
#   WASM_DEBUG=1  keep function names and turn on Emscripten's runtime checks
#                 (stack overflow, assertions). Slower and larger; for diagnosis.
#   JOBS          parallel compiles (default: number of CPUs)

set -euo pipefail

SRC="${1:?usage: build_aermod_wasm.sh <aermod source dir> <output dir>}"
OUT="${2:?usage: build_aermod_wasm.sh <aermod source dir> <output dir>}"
SRC="$(cd "$SRC" && pwd)"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

FLANG="${FLANG:-/opt/flang/host/bin/flang}"
FORTRAN_RUNTIME="${FORTRAN_RUNTIME:-/opt/flang/wasm/lib/libFortranRuntime.a}"
if ! command -v emcc >/dev/null 2>&1 && [ -f /opt/emsdk/emsdk_env.sh ]; then
    # shellcheck disable=SC1091
    source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
fi
for tool in "$FLANG" emcc; do
    command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: $tool not found (run inside the flang-wasm image)" >&2; exit 1; }
done
[ -f "$FORTRAN_RUNTIME" ] || { echo "ERROR: Fortran runtime not found: $FORTRAN_RUNTIME" >&2; exit 1; }

FFLAGS="--target=wasm32-unknown-emscripten -O2"

# AERMOD keeps large local arrays; gfortran builds get the OS's 8 MB stack,
# Emscripten's default is 64 KB.
LDFLAGS=(
    -O2
    -sSTACK_SIZE=16MB
    -sALLOW_MEMORY_GROWTH=1
    -sMAXIMUM_MEMORY=4GB
    -sFORCE_FILESYSTEM=1
    -sEXIT_RUNTIME=1
    -sINVOKE_RUN=0
    -sWASM_ASYNC_COMPILATION=0
    -sENVIRONMENT=web,worker,node
    -sEXPORTED_RUNTIME_METHODS=FS,callMain,NODEFS,PROXYFS
    -lnodefs.js
    -lproxyfs.js
)
if [ "${WASM_DEBUG:-0}" = "1" ]; then
    LDFLAGS+=(--profiling-funcs -sASSERTIONS=2 -sSTACK_OVERFLOW_CHECK=2)
fi

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
cp "$SRC"/*.f "$BUILD"/
cd "$BUILD"

# EPA's own build order: modules.f and grsm.f define the modules the rest USE.
FIRST=(modules grsm)
REST=(aermod setup coset soset reset meset ouset inpsum metext iblval siggrid
      tempgrid windgrid calc1 calc2 prise arise prime sigmas pitarea uninam
      output evset evcalc evoutput rline bline)

compile() { "$FLANG" $FFLAGS -c "$1.f" -o "$1.o" 2> "$1.log" || { cat "$1.log" >&2; echo "FAILED: $1.f" >&2; return 1; }; }
export -f compile; export FLANG FFLAGS

for f in "${FIRST[@]}"; do compile "$f"; done
printf '%s\n' "${REST[@]}" | xargs -P "${JOBS:-$(nproc 2>/dev/null || echo 2)}" -I{} bash -c 'compile {}'
echo "compiled $(ls ./*.o | wc -l) objects"

objs=()
for f in "${FIRST[@]}" "${REST[@]}"; do objs+=("$f.o"); done
emcc "${objs[@]}" "$FORTRAN_RUNTIME" "${LDFLAGS[@]}" -o "$OUT/aermod.js"

version="$(grep -o "DATA VERSN /'[0-9]*'/" modules.f | grep -o "[0-9][0-9]*" || echo unknown)"
{
    echo "AERMOD version: $version"
    echo "Flang: $("$FLANG" --version | head -1)"
    echo "Emscripten: $(emcc --version | head -1)"
    echo "Compile flags: $FFLAGS"
    echo "Link flags: ${LDFLAGS[*]}"
    (cd "$OUT" && sha256sum aermod.js aermod.wasm)
} > "$OUT/BUILD.txt"
cat "$OUT/BUILD.txt"
