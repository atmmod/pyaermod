#!/usr/bin/env bash
#
# Re-record the AERMET runs in runs/ (see README.md).
#
# Usage:  tests/fixtures/aermet/regenerate.sh [path/to/aermet]
#
# Writes EX01's decks with pyaermod (ex01_decks.py; set PYTHON to the
# interpreter that has pyaermod installed), runs each case in a scratch
# directory holding EPA's EX01 data files, and copies back what AERMET
# produced: its stdout (stdout.txt), its exit code (exit_code.txt) and the
# REPORT and MESSAGES files the deck names.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE="${1:-$(command -v aermet || true)}"
PYTHON="${PYTHON:-python3}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermet not found: pass its path or put it on PATH" >&2
    echo "(build it with scripts/build_aermod.sh aermet)" >&2
    exit 1
fi
EXE="$(cd "$(dirname "$EXE")" && pwd)/$(basename "$EXE")"

decks="$(mktemp -d)"
trap 'rm -rf "$decks"' EXIT
"$PYTHON" "$HERE/ex01_decks.py" "$decks"
# A user error the writer cannot see: TD-6201 data declared as FSL.
sed 's/14735-88.UA 6201FB/14735-88.UA FSL/' "$decks/stage1.inp" > "$decks/wrong_format.inp"

# record CASE DECK REPORT MESSAGES [PRE_DECK [KEEP...]]: run DECK (after
# PRE_DECK, when given and not empty, in the same directory) and keep its
# stdout, exit code, REPORT and MESSAGES, plus any KEEP files it wrote.
record() {
    local case="$1" deck="$2" report="$3" messages="$4" pre="${5:-}"
    shift 4; if [ "$#" -gt 0 ]; then shift; fi
    local work
    work="$(mktemp -d)"
    cp "$HERE/ex01/14735-88.UA" "$HERE/ex01/S1473588.144" "$work/"
    if [ -n "$pre" ]; then
        cp "$pre" "$work/pre.inp"
        (cd "$work" && "$EXE" pre.inp > /dev/null)
        rm -f "$work/$report" "$work/$messages"
    fi
    mkdir -p "$HERE/runs/$case"
    if [ "$deck" != "$HERE/runs/$case/deck.inp" ]; then cp "$deck" "$HERE/runs/$case/deck.inp"; fi
    cp "$deck" "$work/deck.inp"
    status=0
    (cd "$work" && "$EXE" deck.inp > stdout.txt 2> stderr.txt) || status=$?
    cp "$work/stdout.txt" "$HERE/runs/$case/"
    for f in "$report" "$messages" "$@"; do
        if [ -f "$work/$f" ]; then cp "$work/$f" "$HERE/runs/$case/"; fi
    done
    echo "$status" > "$HERE/runs/$case/exit_code.txt"
    if [ -s "$work/stderr.txt" ]; then
        echo "$case: AERMET wrote to stderr:" >&2
        cat "$work/stderr.txt" >&2
    fi
    echo "$case: exit code $status, $(grep 'AERMET FINISHED' "$work/stdout.txt" | xargs)"
    rm -rf "$work"
}

rm -rf "$HERE/runs/stage1_success" "$HERE/runs/metprep_success" \
    "$HERE/runs/metprep_without_stage1" "$HERE/runs/stage1_wrong_format"
find "$HERE/runs/legacy_stage1" -type f ! -name deck.inp -delete

record stage1_success "$decks/stage1.inp" stage1.out stage1.msg
record metprep_success "$decks/stage3.inp" stage3.out stage3.msg "$decks/stage1.inp" EX01_MP.SFC EX01_MP.PFL
record metprep_without_stage1 "$decks/stage3.inp" stage3.out stage3.msg
record stage1_wrong_format "$decks/wrong_format.inp" stage1.out stage1.msg
# The deck pyaermod's AERMETStage1 wrote for EX01 before the writer was
# rewritten for AERMET 11+ syntax (kept as recorded, not regenerated).
record legacy_stage1 "$HERE/runs/legacy_stage1/deck.inp" stage1.out 2
