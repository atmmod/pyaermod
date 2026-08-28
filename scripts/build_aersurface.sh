#!/usr/bin/env bash
# build_aersurface.sh — Compile EPA AERSURFACE from Fortran source
#
# AERSURFACE derives the surface characteristics (albedo, Bowen ratio,
# surface roughness) that AERMET Stage 3 consumes, from NLCD land-cover
# rasters. pyaermod builds its control file (pyaermod.aersurface); this
# script provides the binary that consumes it, so
# tests/test_real_aersurface.py can check the deck end to end against
# EPA's own reference output rather than against pyaermod's idea of it.
#
# EPA AERSURFACE source code is public domain (U.S. Government work).
# Archive locations come from pyaermod.epa_sources.
#
# Prerequisites:
#   macOS:  brew install gcc   (provides gfortran)
#   Ubuntu: sudo apt-get install gfortran
#
# Usage:
#   ./scripts/build_aersurface.sh                 # build the binary
#   ./scripts/build_aersurface.sh --with-testcase # also unpack EPA's
#                                                 # RDU test case
# Output:
#   ./bin/aersurface
#   ./test_cases/aersurface_testcase/   (with --with-testcase; ~30 MB)
#
# Note: AERSURFACE reads its control file from the first command-line
# argument, or from ./aersurface.inp when given none. pyaermod's runner
# uses the second convention.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$REPO_ROOT/bin"
TESTCASE_DIR="$REPO_ROOT/test_cases"

FC="${FC:-gfortran}"
FFLAGS="${FFLAGS:--fbounds-check -Wuninitialized -O2 -std=legacy}"
SRC_URL="${AERSURFACE_URL:-https://gaftp.epa.gov/Air/aqmg/SCRAM/models/related/aersurface/aersurface_source.zip}"
TC_URL="${AERSURFACE_TESTCASE_URL:-https://gaftp.epa.gov/Air/aqmg/SCRAM/models/related/aersurface/aersurface_testcase.zip}"

WITH_TESTCASE=0
[ "${1:-}" = "--with-testcase" ] && WITH_TESTCASE=1

echo "============================================"
echo "  AERSURFACE Build Script"
echo "  Compiler: $FC"
echo "  Flags:    $FFLAGS"
echo "============================================"

if ! command -v "$FC" >/dev/null 2>&1; then
    echo "ERROR: $FC not found."
    case "$(uname -s)" in
        Darwin) echo "Install with:  brew install gcc" ;;
        *)      echo "Install with:  sudo apt-get install gfortran" ;;
    esac
    exit 1
fi

mkdir -p "$BIN_DIR"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ZIP="$WORK/aersurface_source.zip"
if [ -n "${AERSURFACE_ZIP:-}" ] && [ -f "$AERSURFACE_ZIP" ]; then
    echo "Using local archive: $AERSURFACE_ZIP"
    cp "$AERSURFACE_ZIP" "$ZIP"
else
    "$SCRIPT_DIR/fetch_epa_source.sh" "$SRC_URL" "$ZIP"
fi

unzip -qo "$ZIP" -d "$WORK/src"
# EPA archives extract read-only; make them writable before compiling.
chmod -R u+w "$WORK/src"

SRCDIR="$(dirname "$(find "$WORK/src" -iname 'aersurface.f' | head -1)")"
if [ ! -d "$SRCDIR" ]; then
    echo "ERROR: aersurface.f not found in $SRC_URL"
    exit 1
fi
echo "Source: $(basename "$SRCDIR")"
cd "$SRCDIR"

# Module compile order, from EPA's own gfortran-compile.bat. Fortran
# modules must be compiled before the units that USE them, so this list
# is an ordering constraint, not a file glob.
MODULES=(
    mod_StartVars mod_Constants mod_UserParams mod_FileUnits
    mod_ErrorHandling mod_Geographic mod_ProcCtrlFile mod_LandCoverParams
    mod_Tifftags mod_TiffParams mod_InitTiffParams mod_GetData
    mod_AvgParams mod_SfcChars
)
OBJECTS=()
for m in "${MODULES[@]}" aersurface; do
    # EPA's archive spells mod_Tifftags with a lowercase 't' while the
    # .bat says mod_TiffTags; match case-insensitively.
    f="$(find . -maxdepth 1 -iname "${m}.f" | head -1)"
    if [ -z "$f" ]; then
        echo "ERROR: source file for ${m} not found"
        exit 1
    fi
    echo "  compiling $(basename "$f")"
    "$FC" -c $FFLAGS "$f"
    OBJECTS+=("$(basename "${f%.*}").o")
done

"$FC" -o "$BIN_DIR/aersurface" -O2 "${OBJECTS[@]}"
echo "  -> $BIN_DIR/aersurface"

# NADCON datum-shift grids (conus/alaska/hawaii/prvi .las/.los). AERSURFACE
# reads these from its working directory and fails with "NAD Grid Files
# Missing" for any NAD27 run without them, so install them beside the
# binary where AERSURFACERunner can find and stage them.
grids=0
for grid in "$SRCDIR"/*.las "$SRCDIR"/*.los; do
    [ -f "$grid" ] || continue
    cp "$grid" "$BIN_DIR/"
    grids=$((grids + 1))
done
echo "  -> $grids NADCON grid file(s) in $BIN_DIR (needed for datum NAD27)"

if [ "$WITH_TESTCASE" = "1" ]; then
    mkdir -p "$TESTCASE_DIR"
    TCZIP="$WORK/aersurface_testcase.zip"
    if [ -n "${AERSURFACE_TESTCASE_ZIP:-}" ] && [ -f "$AERSURFACE_TESTCASE_ZIP" ]; then
        cp "$AERSURFACE_TESTCASE_ZIP" "$TCZIP"
    else
        "$SCRIPT_DIR/fetch_epa_source.sh" "$TC_URL" "$TCZIP"
    fi
    unzip -qo "$TCZIP" -d "$TESTCASE_DIR"
    chmod -R u+w "$TESTCASE_DIR/aersurface_testcase"
    echo "  -> $TESTCASE_DIR/aersurface_testcase"
fi

echo "============================================"
echo "  Build complete!"
echo "  Binary: $BIN_DIR/aersurface"
echo
echo "  Add to PATH:  export PATH=\"$BIN_DIR:\$PATH\""
echo "  Then:         pytest tests/test_real_aersurface.py"
echo "============================================"
