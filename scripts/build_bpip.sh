#!/usr/bin/env bash
# build_bpip.sh — Compile EPA BPIP-PRIME from Fortran source on macOS/Linux
#
# BPIP-PRIME computes the direction-dependent building dimensions
# (BUILDHGT / BUILDWID / BUILDLEN / XBADJ / YBADJ) that AERMOD's PRIME
# downwash algorithm consumes. pyaermod ships a pure-Python
# reimplementation in pyaermod.bpip; this build gives the reference
# implementation to check it against, which is what
# tests/test_bpip_known_answers.py does.
#
# EPA BPIP source code is public domain (U.S. Government work).
# Archive location comes from pyaermod.epa_sources (discovered from the
# SCRAM directory listing, not guessed).
#
# Prerequisites:
#   macOS:  brew install gcc   (provides gfortran)
#   Ubuntu: sudo apt-get install gfortran
#
# Usage:
#   ./scripts/build_bpip.sh
#
# Output:
#   ./bin/bpipprm
#
# Two things about EPA's archive need handling and are the reason this
# script exists rather than a one-line gfortran invocation:
#
#   1. Bpipprm.for is a DOS text file that ends with a literal Ctrl-Z
#      (0x1A) end-of-file marker. gfortran reads it as source and stops
#      with "Non-numeric character in statement label". The CRLF line
#      endings are harmless, but both are stripped here.
#
#   2. The OPEN statements are commented out in EPA's source ("CVRT
#      HARDWIRE OPEN FILES"), so the program reads unit 10 and writes
#      units 12 and 14 with no filenames attached. Under gfortran those
#      become ./fort.10, ./fort.12 and ./fort.14 in the working
#      directory. Run it by copying the .INP to fort.10 in a scratch
#      directory; the .out lands in fort.12 and the .sum in fort.14.
#      Passing filenames on the command line does nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$REPO_ROOT/bin"

FC="${FC:-gfortran}"
FFLAGS="${FFLAGS:--O2 -std=legacy}"
URL="${BPIP_URL:-https://gaftp.epa.gov/Air/aqmg/SCRAM/models/related/bpip/bpipprime.zip}"

echo "============================================"
echo "  BPIP-PRIME Build Script"
echo "  Compiler: $FC"
echo "  Flags:    $FFLAGS"
echo "  Source:   $URL"
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

ZIP="$WORK/bpipprime.zip"
if [ -n "${BPIP_ZIP:-}" ] && [ -f "$BPIP_ZIP" ]; then
    echo "Using local archive: $BPIP_ZIP"
    cp "$BPIP_ZIP" "$ZIP"
else
    "$SCRIPT_DIR/fetch_epa_source.sh" "$URL" "$ZIP"
fi

unzip -qo "$ZIP" -d "$WORK/src"
# EPA archives extract read-only; make them writable before touching them.
chmod -R u+w "$WORK/src"

SRC="$(find "$WORK/src" -iname 'Bpipprm.for' | head -1)"
if [ -z "$SRC" ]; then
    echo "ERROR: Bpipprm.for not found in $URL"
    find "$WORK/src" -maxdepth 2 -type f | head -20
    exit 1
fi

# Strip the DOS EOF marker and CRLFs (see note 1 above).
tr -d '\032\r' < "$SRC" > "$WORK/bpipprm.f"

echo "Compiling $(basename "$SRC") ..."
"$FC" $FFLAGS -o "$BIN_DIR/bpipprm" "$WORK/bpipprm.f"

# Prove the build works before declaring success: run EPA's own first
# example and check it produced the GEP table.
EXAMPLE="$(find "$WORK/src" -iname 'A1P.INP' | head -1)"
if [ -n "$EXAMPLE" ]; then
    RUNDIR="$WORK/check"
    mkdir -p "$RUNDIR"
    cp "$EXAMPLE" "$RUNDIR/fort.10"
    ( cd "$RUNDIR" && "$BIN_DIR/bpipprm" >/dev/null 2>&1 || true )
    if grep -q "SO BUILDHGT" "$RUNDIR/fort.12" 2>/dev/null; then
        echo "Smoke test: EPA example A1P.INP produced BUILDHGT output. OK"
    else
        echo "ERROR: built binary did not produce downwash output for A1P.INP"
        exit 1
    fi
fi

echo "============================================"
echo "  Build complete!"
echo "  Binary: $BIN_DIR/bpipprm"
echo
echo "  Add to PATH:  export PATH=\"$BIN_DIR:\$PATH\""
echo "  Then:         pytest tests/test_bpip_known_answers.py"
echo "============================================"
