#!/usr/bin/env bash
#
# Re-record the AERMOD runs in this directory (see README.md).
#
# Usage:  tests/fixtures/runner/regenerate.sh [path/to/aermod] [case ...]
#
# Each case directory holds the deck, aermod.inp, and any .dat file the
# deck names on an INCLUDED record. The script runs that deck
# with the Albany met files from tests/fixtures/epa_official/ in a scratch
# directory, then copies back what AERMOD produced: aermod.out, its
# stdout (stdout.txt) and its exit code (exit_code.txt). With no case
# names it records every case.
#
# killed_sigterm is stopped with SIGTERM $KILL_AFTER seconds (default 1)
# after it starts, so its exit code is the shell's 143 (128 + 15). The
# script refuses the recording if AERMOD had not finished setup by then,
# or had already finished the run.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MET="$HERE/../epa_official"
EXE="${1:-$(command -v aermod || true)}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermod not found: pass its path or put it on PATH" >&2
    echo "(build it with scripts/build_aermod.sh)" >&2
    exit 1
fi
EXE="$(cd "$(dirname "$EXE")" && pwd)/$(basename "$EXE")"
shift || true
CASES=("$@")
if [ ${#CASES[@]} -eq 0 ]; then
    CASES=(success runtime_error_e480 setup_error_e500 setup_error_e322_openpit
           setup_error_e140_srcgroup killed_sigterm success_no_echo success_included)
fi

for case in "${CASES[@]}"; do
    work="$(mktemp -d)"
    cp "$HERE/$case/aermod.inp" "$MET/AERMET2.SFC" "$MET/AERMET2.PFL" "$work/"
    # Files the deck names on INCLUDED records (success_included/grid.dat)
    for inc in "$HERE/$case"/*.dat; do
        [ -e "$inc" ] && cp "$inc" "$work/"
    done
    status=0
    if [ "$case" = killed_sigterm ]; then
        # exec makes the background job AERMOD itself, so $! is its pid.
        (cd "$work" && exec "$EXE" > stdout.txt 2> stderr.txt) &
        pid=$!
        sleep "${KILL_AFTER:-1}"
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" || status=$?
        if ! grep -q "SETUP Finishes Successfully" "$work/aermod.out" \
                || grep -q "AERMOD Finishes" "$work/aermod.out"; then
            echo "$case: the kill did not land between setup and the end of the run;" \
                 "adjust KILL_AFTER (now ${KILL_AFTER:-1} s)" >&2
            rm -rf "$work"
            exit 1
        fi
    else
        (cd "$work" && "$EXE" > stdout.txt 2> stderr.txt) || status=$?
    fi
    cp "$work/aermod.out" "$work/stdout.txt" "$HERE/$case/"
    echo "$status" > "$HERE/$case/exit_code.txt"
    if [ -s "$work/stderr.txt" ]; then
        echo "$case: AERMOD wrote to stderr:" >&2
        cat "$work/stderr.txt" >&2
    fi
    echo "$case: exit code $status, $(wc -l < "$HERE/$case/aermod.out") lines of aermod.out"
    rm -rf "$work"
done
