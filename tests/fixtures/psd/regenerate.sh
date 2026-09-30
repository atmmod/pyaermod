#!/usr/bin/env bash
#
# Re-record the AERMOD run in this directory (see README.md).
#
# Usage:  tests/fixtures/psd/regenerate.sh [path/to/aermod]
#
# Runs aermod.inp with the Albany met files from tests/fixtures/epa_official/
# in a scratch directory, then copies back aermod.out and PDEP.DAT, the
# DEBUGOPT DEPOS file that lists each size category's settling velocity.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MET="$HERE/../epa_official"
EXE="${1:-$(command -v aermod || true)}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermod not found: pass its path or put it on PATH" >&2
    echo "(build it with scripts/build_aermod.sh)" >&2
    exit 1
fi

work="$(mktemp -d)"
cp "$HERE/aermod.inp" "$MET/AERMET2.SFC" "$MET/AERMET2.PFL" "$work/"
(cd "$work" && "$EXE" > stdout.txt 2> stderr.txt)
cp "$work/aermod.out" "$work/PDEP.DAT" "$HERE/"
if [ -s "$work/stderr.txt" ]; then
    echo "AERMOD wrote to stderr:" >&2
    cat "$work/stderr.txt" >&2
fi
grep -q "AERMOD Finishes Successfully" "$HERE/aermod.out"
echo "$(grep -c METHOD_1 "$HERE/PDEP.DAT") settling velocities in PDEP.DAT"
rm -rf "$work"
