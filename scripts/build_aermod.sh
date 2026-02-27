#!/usr/bin/env bash
# build_aermod.sh — Compile AERMOD and AERMAP from Fortran source on macOS/Linux
#
# EPA AERMOD source code is public domain (U.S. Government work).
# Source: https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models
#
# Prerequisites:
#   macOS:  brew install gcc   (provides gfortran)
#   Ubuntu: sudo apt-get install gfortran
#
# Usage:
#   ./scripts/build_aermod.sh              # build both AERMOD and AERMAP
#   ./scripts/build_aermod.sh aermod       # build AERMOD only
#   ./scripts/build_aermod.sh aermap       # build AERMAP only
#
# Output:
#   ./bin/aermod   (or aermod.exe on Windows/Cygwin)
#   ./bin/aermap   (or aermap.exe on Windows/Cygwin)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$REPO_ROOT/bin"

# Compiler settings
FC="${FC:-gfortran}"
FFLAGS="${FFLAGS:--O2 -fbounds-check -Wuninitialized}"

# Detect platform
case "$(uname -s)" in
    Darwin) PLATFORM="macOS" ;;
    Linux)  PLATFORM="Linux" ;;
    *)      PLATFORM="Unknown" ;;
esac

echo "============================================"
echo "  AERMOD/AERMAP Build Script"
echo "  Platform: $PLATFORM ($(uname -m))"
echo "  Compiler: $FC"
echo "  Flags:    $FFLAGS"
echo "============================================"
echo

# Check for gfortran
if ! command -v "$FC" &> /dev/null; then
    echo "ERROR: $FC not found."
    echo
    if [ "$PLATFORM" = "macOS" ]; then
        echo "Install with:  brew install gcc"
    else
        echo "Install with:  sudo apt-get install gfortran"
    fi
    exit 1
fi

echo "Using: $($FC --version | head -1)"
echo

mkdir -p "$BIN_DIR"

# -------------------------------------------------------
# Build AERMOD
# -------------------------------------------------------
build_aermod() {
    local SRC_DIR="$REPO_ROOT/aermod"

    if [ ! -d "$SRC_DIR" ] || [ ! -f "$SRC_DIR/aermod.f" ]; then
        echo "ERROR: AERMOD source not found at $SRC_DIR"
        echo "Download from: https://www.epa.gov/scram"
        return 1
    fi

    echo "Building AERMOD..."
    local BUILD_DIR
    BUILD_DIR=$(mktemp -d)
    trap "rm -rf $BUILD_DIR" RETURN

    # Compile order matters — modules.f must be first
    local SOURCES=(
        modules.f grsm.f aermod.f setup.f coset.f soset.f reset.f
        meset.f ouset.f inpsum.f metext.f iblval.f siggrid.f
        tempgrid.f windgrid.f calc1.f calc2.f prise.f arise.f
        prime.f sigmas.f pitarea.f uninam.f output.f evset.f
        evcalc.f evoutput.f rline.f bline.f
    )

    cd "$BUILD_DIR"

    # Compile each source file
    for src in "${SOURCES[@]}"; do
        if [ ! -f "$SRC_DIR/$src" ]; then
            echo "  WARNING: $src not found, skipping"
            continue
        fi
        echo "  Compiling $src"
        "$FC" -c $FFLAGS "$SRC_DIR/$src"
    done

    # Link
    echo "  Linking aermod..."
    local OBJECTS=(*.o)
    "$FC" -o "$BIN_DIR/aermod" $FFLAGS "${OBJECTS[@]}"

    cd "$REPO_ROOT"
    echo "  -> $BIN_DIR/aermod"
    echo "  AERMOD build successful!"
    echo
}

# -------------------------------------------------------
# Build AERMAP
# -------------------------------------------------------
build_aermap() {
    local SRC_DIR="$REPO_ROOT/aermap/aermap_source_code_24142"

    if [ ! -d "$SRC_DIR" ] || [ ! -f "$SRC_DIR/aermap.f" ]; then
        echo "ERROR: AERMAP source not found at $SRC_DIR"
        echo "Download from: https://www.epa.gov/scram"
        return 1
    fi

    echo "Building AERMAP..."
    local BUILD_DIR
    BUILD_DIR=$(mktemp -d)
    trap "rm -rf $BUILD_DIR" RETURN

    # Compile order — modules first, then main, then subroutines
    local SOURCES=(
        mod_main1.f mod_tifftags.f aermap.f
        sub_calchc.f sub_chkadj.f sub_chkext.f sub_demchk.f
        sub_nedchk.f sub_cnrcnv.f sub_demrec.f sub_demsrc.f
        sub_domcnv.f sub_initer_dem.f sub_initer_ned.f sub_nadcon.f
        sub_reccnv.f sub_recelv.f sub_srccnv.f sub_srcelv.f
        sub_utmgeo.f sub_read_tifftags.f
    )

    cd "$BUILD_DIR"

    for src in "${SOURCES[@]}"; do
        if [ ! -f "$SRC_DIR/$src" ]; then
            echo "  WARNING: $src not found, skipping"
            continue
        fi
        echo "  Compiling $src"
        "$FC" -c $FFLAGS "$SRC_DIR/$src"
    done

    # Link
    echo "  Linking aermap..."
    local OBJECTS=(*.o)
    "$FC" -o "$BIN_DIR/aermap" $FFLAGS "${OBJECTS[@]}"

    cd "$REPO_ROOT"
    echo "  -> $BIN_DIR/aermap"
    echo "  AERMAP build successful!"
    echo
}

# -------------------------------------------------------
# Main
# -------------------------------------------------------
TARGET="${1:-all}"

case "$TARGET" in
    aermod)
        build_aermod
        ;;
    aermap)
        build_aermap
        ;;
    all)
        build_aermod
        build_aermap
        ;;
    *)
        echo "Usage: $0 [aermod|aermap|all]"
        exit 1
        ;;
esac

echo "============================================"
echo "  Build complete!"
echo "  Binaries in: $BIN_DIR/"
ls -lh "$BIN_DIR"/aermod "$BIN_DIR"/aermap 2>/dev/null || true
echo
echo "  Add to PATH:  export PATH=\"$BIN_DIR:\$PATH\""
echo "  Or copy to:   cp $BIN_DIR/aermod /usr/local/bin/"
echo "============================================"
