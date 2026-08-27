#!/usr/bin/env bash
# build_aermod.sh — Compile AERMOD, AERMAP and AERMET from Fortran source
#
# EPA source code is public domain (U.S. Government work). Archives are
# downloaded from the locations registered in pyaermod.epa_sources
# (discovered from EPA's SCRAM directory listings, not guessed), unless
# a local source tree is supplied — see the environment overrides below.
#
# The extracted directory name carries EPA's version and changes with
# every release (aermap_source_code_24142 -> aermod_source_v26135), so
# it is derived from the archive rather than hardcoded. A version pin
# here is a build that breaks on EPA's next release.
#
# Prerequisites:
#   macOS:  brew install gcc   (provides gfortran)
#   Ubuntu: sudo apt-get install gfortran
#
# Usage:
#   ./scripts/build_aermod.sh              # build all three
#   ./scripts/build_aermod.sh aermod       # one of: aermod | aermap | aermet
#
# Environment overrides (skip the download):
#   AERMOD_SRC_DIR / AERMAP_SRC_DIR / AERMET_SRC_DIR   local source tree
#   AERMOD_ZIP     / AERMAP_ZIP     / AERMET_ZIP       local archive
#
# Output:
#   ./bin/aermod  ./bin/aermap  ./bin/aermet
#
# Then:  make test-binaries      (puts ./bin on PATH and runs the suite)

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

SCRAM="https://gaftp.epa.gov/Air/aqmg/SCRAM/models"
AERMOD_URL="${AERMOD_URL:-$SCRAM/preferred/aermod/aermod_source.zip}"
AERMAP_URL="${AERMAP_URL:-$SCRAM/related/aermap/aermap_source.zip}"
AERMET_URL="${AERMET_URL:-$SCRAM/met/aermet/aermet_source.zip}"

# Resolve a source tree for $1 (AERMOD/AERMAP/AERMET): honour a local
# override, otherwise fetch and unpack. Echoes the directory holding the
# sources. EPA archives extract read-only, so make them writable —
# gfortran has to write .mod files beside them.
resolve_src() {
    local name="$1" url="$2" marker="$3"
    local dir_var="${name}_SRC_DIR" zip_var="${name}_ZIP"
    local local_dir="${!dir_var:-}" local_zip="${!zip_var:-}"

    if [ -n "$local_dir" ]; then
        echo "$local_dir"
        return 0
    fi

    local work="$WORK_ROOT/$name"
    mkdir -p "$work"
    local zip="$work/src.zip"
    if [ -n "$local_zip" ] && [ -f "$local_zip" ]; then
        cp "$local_zip" "$zip"
    else
        "$SCRIPT_DIR/fetch_epa_source.sh" "$url" "$zip" >&2
    fi
    unzip -qo "$zip" -d "$work/src" >&2
    chmod -R u+w "$work/src"
    local found
    found=$(find "$work/src" -iname "$marker" -maxdepth 3 | head -1)
    if [ -z "$found" ]; then
        echo "ERROR: $marker not found in $url" >&2
        return 1
    fi
    dirname "$found"
}

WORK_ROOT="$(mktemp -d)"
trap 'rm -rf "$WORK_ROOT"' EXIT

# -------------------------------------------------------
# Build AERMOD
# -------------------------------------------------------
build_aermod() {
    echo "Building AERMOD..."
    local SRC_DIR
    SRC_DIR=$(resolve_src AERMOD "$AERMOD_URL" "aermod.f") || return 1
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
    local SRC_DIR
    SRC_DIR=$(resolve_src AERMAP "$AERMAP_URL" "aermap.f") || return 1

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
# Build AERMET
# -------------------------------------------------------
build_aermet() {
    echo "Building AERMET..."
    local SRC_DIR
    SRC_DIR=$(resolve_src AERMET "$AERMET_URL" "aermet.f90") || return 1
    local BUILD_DIR
    BUILD_DIR=$(mktemp -d)
    trap "rm -rf $BUILD_DIR" RETURN

    # AERMET is free-form Fortran 2008, unlike AERMOD/AERMAP. Modules
    # first, and in this order -- each USEs the ones above it.
    local SOURCES=(
        mod_file_units.f90 mod_main1.f90 mod_upperair.f90 mod_surface.f90
        mod_onsite.f90 mod_pbl.f90 mod_read_input.f90 mod_reports.f90
        mod_misc.f90 aermet.f90
    )
    local AERMET_FLAGS="-O2 -std=f2008 -ffree-form"

    cd "$BUILD_DIR"
    for src in "${SOURCES[@]}"; do
        local found
        found=$(find "$SRC_DIR" -maxdepth 1 -iname "$src" | head -1)
        if [ -z "$found" ]; then
            echo "  WARNING: $src not found, skipping"
            continue
        fi
        echo "  Compiling $(basename "$found")"
        "$FC" -c $AERMET_FLAGS "$found"
    done

    echo "  Linking aermet..."
    local OBJECTS=(*.o)
    "$FC" -O2 -o "$BIN_DIR/aermet" "${OBJECTS[@]}"

    cd "$REPO_ROOT"
    echo "  -> $BIN_DIR/aermet"
    echo "  AERMET build successful!"
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
    aermet)
        build_aermet
        ;;
    all)
        build_aermod
        build_aermap
        build_aermet
        ;;
    *)
        echo "Usage: $0 [aermod|aermap|aermet|all]"
        exit 1
        ;;
esac

echo "============================================"
echo "  Build complete!"
echo "  Binaries in: $BIN_DIR/"
ls -lh "$BIN_DIR"/aermod "$BIN_DIR"/aermap "$BIN_DIR"/aermet 2>/dev/null || true
echo
echo "  Add to PATH:  export PATH=\"$BIN_DIR:\$PATH\""
echo "  Then:         make test-binaries"
echo "============================================"
