#!/usr/bin/env bash
#
# Re-record the AERMOD runs in this directory (see README.md).
#
# Usage:  tests/fixtures/runner/regenerate.sh [path/to/aermod]
#
# Each case directory holds the deck, aermod.inp. The script runs that deck
# with the Albany met files from tests/fixtures/epa_official/ in a scratch
# directory, then copies back what AERMOD produced: aermod.out, its
# stdout (stdout.txt) and its exit code (exit_code.txt).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MET="$HERE/../epa_official"
EXE="${1:-$(command -v aermod || true)}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermod not found: pass its path or put it on PATH" >&2
    echo "(build it with scripts/build_aermod.sh)" >&2
    exit 1
fi

for case in success runtime_error_e480 setup_error_e500; do
    work="$(mktemp -d)"
    cp "$HERE/$case/aermod.inp" "$MET/AERMET2.SFC" "$MET/AERMET2.PFL" "$work/"
    status=0
    (cd "$work" && "$EXE" > stdout.txt 2> stderr.txt) || status=$?
    cp "$work/aermod.out" "$work/stdout.txt" "$HERE/$case/"
    echo "$status" > "$HERE/$case/exit_code.txt"
    if [ -s "$work/stderr.txt" ]; then
        echo "$case: AERMOD wrote to stderr:" >&2
        cat "$work/stderr.txt" >&2
    fi
    echo "$case: exit code $status, $(wc -l < "$HERE/$case/aermod.out") lines of aermod.out"
    rm -rf "$work"
done
