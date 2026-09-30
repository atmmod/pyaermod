#!/usr/bin/env bash
#
# Re-record the AERMAP runs in this directory (see README.md).
#
# Usage:  tests/fixtures/aermap_runner/regenerate.sh [path/to/aermap]
#
# Each case directory holds the deck, aermap.inp. The script runs that deck
# beside synth.dem (the planar DEM of tests/test_real_aermap.py) in a
# scratch directory, then copies back what AERMAP produced: aermap.out, its
# stdout (stdout.txt), its exit code (exit_code.txt) and the RECEPTOR and
# SOURCLOC files when it wrote them.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE="${1:-$(command -v aermap || true)}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermap not found: pass its path or put it on PATH" >&2
    exit 1
fi

for case in success domain_error_e310 old_writer_setup_errors; do
    work="$(mktemp -d)"
    cp "$HERE/$case/aermap.inp" "$HERE/synth.dem" "$work/"
    status=0
    (cd "$work" && "$EXE" aermap.inp > stdout.txt 2> stderr.txt) || status=$?
    cp "$work/aermap.out" "$work/stdout.txt" "$HERE/$case/"
    echo "$status" > "$HERE/$case/exit_code.txt"
    rm -f "$HERE/$case/aermap_receptors.out" "$HERE/$case/aermap_sources.out"
    for f in aermap_receptors.out aermap_sources.out; do
        if [ -e "$work/$f" ]; then cp "$work/$f" "$HERE/$case/"; fi
    done
    if [ -s "$work/stderr.txt" ]; then
        echo "$case: AERMAP wrote to stderr:" >&2
        cat "$work/stderr.txt" >&2
    fi
    echo "$case: exit code $status, $(wc -l < "$HERE/$case/aermap.out") lines of aermap.out"
    rm -rf "$work"
done
