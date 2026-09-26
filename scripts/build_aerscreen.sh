#!/usr/bin/env bash
# build_aerscreen.sh — Compile EPA AERSCREEN and MAKEMET from Fortran source
#
# AERSCREEN is EPA's screening front-end to AERMOD. It is interactive: it
# reads an ordered sequence of answers on stdin, generates screening
# meteorology with MAKEMET, and runs AERMOD (and BPIP-PRIME and AERMAP
# when asked to) as external programs. pyaermod drives it through
# pyaermod.aerscreen_runner; this script provides the binary so
# tests/test_real_aerscreen.py can check pyaermod's answer sequence and
# restart-file writer against EPA's own reference runs.
#
# EPA AERSCREEN and MAKEMET source code is public domain (U.S. Government
# work). Archive locations come from pyaermod.epa_sources.
#
# Prerequisites:
#   macOS:  brew install gcc   (provides gfortran)
#   Ubuntu: sudo apt-get install gfortran
#   plus bin/aermod (scripts/build_aermod.sh) and, for building-downwash
#   or terrain runs, bin/bpipprm (scripts/build_bpip.sh) and bin/aermap.
#
# Usage:
#   ./scripts/build_aerscreen.sh                 # build the binaries
#   ./scripts/build_aerscreen.sh --with-testcase # also unpack EPA's test
#                                                # cases (46 MB archive)
# Output:
#   ./bin/aerscreen
#   ./bin/makemet
#   ./test_cases/aerscreen_test_cases/   (with --with-testcase)
#
# Why EPA's source needs a patch before gfortran will build it:
#
#   1. Every prompt FORMAT ends in the Intel/Microsoft "\" edit
#      descriptor (suppress the newline so the cursor waits after the
#      prompt). gfortran does not accept it, not even with -fdec; its
#      equivalent is "$", which -std=legacy allows. 74 FORMAT statements
#      and two inline character-literal formats are translated.
#   2. AERSCREEN opens files under names that differ in case from the
#      names it asked AERMOD and AERMAP to write ("aerscreen.plt" in
#      the OPEN, "AERSCREEN.PLT" in the deck; "AERMOD.OUT" in the OPEN
#      where Linux AERMOD writes "aermod.out"). Harmless on Windows,
#      fatal on a case-sensitive filesystem.
#   3. The NAD-grid directory used for terrain runs is assembled with
#      "\" as the path separator. "/" works on both platforms.
#
#   The patch is scripts/patches/aerscreen_<version>.patch and is applied
#   with plain patch(1) after the DOS line endings are stripped, so a
#   source drift on EPA's side fails here, loudly, instead of producing
#   a binary that behaves differently from the one that was validated.
#
# AERSCREEN 21112 is the current SCRAM release (MCB #7, April 2021).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$REPO_ROOT/bin"
TESTCASE_DIR="$REPO_ROOT/test_cases"

FC="${FC:-gfortran}"
FFLAGS="${FFLAGS:--O2 -std=legacy}"
SCRAM="https://gaftp.epa.gov/Air/aqmg/SCRAM/models/screening/aerscreen"
SRC_URL="${AERSCREEN_URL:-$SCRAM/aerscreen_code.zip}"
MAKEMET_URL="${MAKEMET_URL:-$SCRAM/makemet_code.zip}"
TC_URL="${AERSCREEN_TESTCASE_URL:-$SCRAM/aerscreen_test_cases.zip}"
PATCHED_VERSION="21112"

WITH_TESTCASE=0
[ "${1:-}" = "--with-testcase" ] && WITH_TESTCASE=1

echo "============================================"
echo "  AERSCREEN + MAKEMET Build Script"
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
command -v patch >/dev/null 2>&1 || { echo "ERROR: patch(1) not found"; exit 1; }

mkdir -p "$BIN_DIR"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# fetch <url> <dest> [<local-archive-env-value>]
fetch() {
    if [ -n "${3:-}" ] && [ -f "$3" ]; then
        echo "Using local archive: $3"
        cp "$3" "$2"
    else
        "$SCRIPT_DIR/fetch_epa_source.sh" "$1" "$2"
    fi
}

fetch "$SRC_URL" "$WORK/aerscreen_code.zip" "${AERSCREEN_ZIP:-}"
fetch "$MAKEMET_URL" "$WORK/makemet_code.zip" "${MAKEMET_ZIP:-}"
unzip -qo "$WORK/aerscreen_code.zip" -d "$WORK/aerscreen"
unzip -qo "$WORK/makemet_code.zip" -d "$WORK/makemet"
# EPA archives extract read-only; make them writable before touching them.
chmod -R u+w "$WORK/aerscreen" "$WORK/makemet"

SRC="$(find "$WORK/aerscreen" -iname 'aerscreen*.for' -o -iname 'aerscreen*.f' | head -1)"
MSRC="$(find "$WORK/makemet" -iname 'makemet*.for' -o -iname 'makemet*.f' | head -1)"
[ -n "$SRC" ]  || { echo "ERROR: AERSCREEN.FOR not found in $SRC_URL"; exit 1; }
[ -n "$MSRC" ] || { echo "ERROR: MAKEMET.FOR not found in $MAKEMET_URL"; exit 1; }

# The version is the versn parameter in the source, e.g. versn='21112'.
# Older values survive in comment lines, so only statement lines count.
VERSION="$(grep -vE '^[cC!*]' "$SRC" | grep -oE "versn *= *'[0-9]{5}'" | tail -1 | grep -oE '[0-9]{5}' || true)"
echo "AERSCREEN source version: ${VERSION:-unknown} ($(basename "$SRC"))"
PATCH="$SCRIPT_DIR/patches/aerscreen_${PATCHED_VERSION}.patch"
if [ "$VERSION" != "$PATCHED_VERSION" ]; then
    echo "WARNING: the gfortran patch was written against AERSCREEN $PATCHED_VERSION;"
    echo "         this archive holds ${VERSION:-an unknown version}. Applying it anyway."
fi

# Strip the DOS line endings and any Ctrl-Z end-of-file marker (see
# build_bpip.sh), then apply the patch. --forward makes an already
# patched file a no-op rather than a reversed patch; any other mismatch
# is fatal.
tr -d '\032\r' < "$SRC" > "$WORK/aerscreen.f"
echo "Applying $(basename "$PATCH") ..."
patch --forward --batch "$WORK/aerscreen.f" "$PATCH"
tr -d '\032\r' < "$MSRC" > "$WORK/makemet.f"

# Compile inside the scratch directory: gfortran drops the .mod file of
# AERSCREEN's module in the current directory.
echo "Compiling aerscreen ..."
( cd "$WORK" && "$FC" $FFLAGS -o "$BIN_DIR/aerscreen" aerscreen.f )
echo "Compiling makemet ..."
( cd "$WORK" && "$FC" $FFLAGS -o "$BIN_DIR/makemet" makemet.f )

# Prove the build works before declaring success: give AERSCREEN a
# restart file (the ** header its own runs write, here with user-defined
# surface characteristics so nothing else is needed), accept it, and
# take option 9 on the validation page, which stops AERSCREEN cleanly
# without running MAKEMET or AERMOD. That exercises the restart reader,
# the data validation and the patched prompt formats.
RUNDIR="$WORK/check"
mkdir -p "$RUNDIR"
cat > "$RUNDIR/aerscreen.inp" <<'DECK'
** STACK DATA         Rate    Height     Temp.  Velocity     Diam.     Flow
**              0.1000E+01   61.0000  415.0000   11.0000    5.0000   457647.

** BUILDING DATA   BPIP    Height  Max dim.  Min dim.   Orient.   Direct.    Offset
**                  N      0.0000    0.0000    0.0000    0.0000    0.0000    0.0000

** MAKEMET DATA    MinT    MaxT Speed   AnemHt Surf Clim  Albedo   Bowen  Length  SC FILE
**               250.00  310.00   0.5   10.000    0    0   0.1600   0.4500   0.0540  "NA"

** ADJUST U*      N

** TERRAIN DATA   Terrain    UTM East   UTM North  Zone  Nada     Probe     PROFBASE  Use AERMAP elev
**                   N            0.0         0.0     0     0       5000.0           0.00         N

** DISCRETE RECEPTORS  Discflag   Receptor file
**                      N        "NA"

** UNITS/POPULATION   Units   R/U  Population      Amb. dist.   Flagpole    Flagpole height
**                      M     R            0.           1.000       N         0.00

** FUMIGATION        Inversion Break-up  Shoreline  Distance    Direct  Run AERSCREEN
**                         N                  N         0.00      0.0     Y

** DEBUG OPTION      Debug
**                     N

** OUTPUT FILE "AERSCREEN.OUT"

CO STARTING
   TITLEONE build_aerscreen.sh smoke test
   MODELOPT CONC SCREEN  FLAT
   AVERTIME 1
   POLLUTID OTHER
   RUNORNOT RUN
CO FINISHED
DECK
( cd "$RUNDIR" && printf 'Y\n9\n' | "$BIN_DIR/aerscreen" > run.txt 2>&1 || true )
if grep -q "AERSCREEN ${VERSION:-}" "$RUNDIR/aerscreen.log" \
   && grep -q "Stopping AERSCREEN by user action" "$RUNDIR/aerscreen.log"; then
    echo "Smoke test: AERSCREEN ${VERSION:-} read a restart file and stopped on request. OK"
    echo "  ($(wc -l < "$RUNDIR/run.txt") lines on stdout/stderr, $(grep -c 'Enter\|choice\|Hit <Enter>' "$RUNDIR/run.txt") prompt lines)"
else
    echo "ERROR: built binary did not get through its restart-file validation:"
    echo "--- stdout/stderr:"; cat -A "$RUNDIR/run.txt" | head -40
    echo "--- aerscreen.log:"; cat "$RUNDIR/aerscreen.log" 2>/dev/null || true
    exit 1
fi

if [ "$WITH_TESTCASE" = "1" ]; then
    mkdir -p "$TESTCASE_DIR"
    fetch "$TC_URL" "$WORK/aerscreen_test_cases.zip" "${AERSCREEN_TESTCASE_ZIP:-}"
    unzip -qo "$WORK/aerscreen_test_cases.zip" -d "$TESTCASE_DIR/aerscreen_test_cases"
    chmod -R u+w "$TESTCASE_DIR/aerscreen_test_cases"
    echo "  -> $TESTCASE_DIR/aerscreen_test_cases"
fi

echo "============================================"
echo "  Build complete!"
echo "  Binaries: $BIN_DIR/aerscreen, $BIN_DIR/makemet"
echo
echo "  Add to PATH:  export PATH=\"$BIN_DIR:\$PATH\""
echo "  Then:         pytest tests/test_real_aerscreen.py"
echo "============================================"
