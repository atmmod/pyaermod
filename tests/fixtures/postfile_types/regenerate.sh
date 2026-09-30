#!/usr/bin/env bash
#
# Re-record the AERMOD runs in this directory (see README.md).
#
# Usage:  tests/fixtures/postfile_types/regenerate.sh [path/to/aermod]
#
# One case directory per set of output types on MODELOPT. The script
# writes each case's deck (aermod.inp), runs it in a scratch directory with
# the four Houston hours beside it, and copies back the POSTFILEs and the
# PLOTFILE AERMOD wrote. Nothing in a case directory is edited by hand.
# Three more cases (EXTRA_CASES) change one thing in the deck: two write
# their files with OU NOHEADER ALL, and one runs four hours of 2005 from
# Providence, so that the dates have a year below 10.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE="${1:-$(command -v aermod || true)}"
if [ -z "$EXE" ] || [ ! -x "$EXE" ]; then
    echo "aermod not found: pass its path or put it on PATH" >&2
    echo "(build it with scripts/build_aermod.sh)" >&2
    exit 1
fi

# case directory -> output types as written on MODELOPT
CASES=(
    "conc:CONC"
    "depos:DEPOS"
    "ddep:DDEP"
    "wdep:WDEP"
    "conc_depos:CONC DEPOS"
    "conc_ddep:CONC DDEP"
    "conc_wdep:CONC WDEP"
    "depos_ddep:DEPOS DDEP"
    "depos_wdep:DEPOS WDEP"
    "ddep_wdep:DDEP WDEP"
    "conc_depos_ddep:CONC DEPOS DDEP"
    "conc_depos_wdep:CONC DEPOS WDEP"
    "conc_ddep_wdep:CONC DDEP WDEP"
    "depos_ddep_wdep:DEPOS DDEP WDEP"
    "conc_depos_ddep_wdep:CONC DEPOS DDEP WDEP"
    "wdep_ddep_conc_keyword_order:WDEP DDEP CONC"
)

# case directory -> output types -> variant
EXTRA_CASES=(
    "noheader_conc:CONC:noheader"
    "noheader_conc_ddep:CONC DDEP:noheader"
    "year_2005:CONC DDEP:pvd2005"
)

# write_deck TYPES [VARIANT]
write_deck() {
    local sfc=HOUSTON_0228.SFC pfl=HOUSTON_0228.PFL
    local surf="12960  1996" uair="3937  1996" startend="96 02 28 11 96 02 28 14"
    local rec1="-50.0  -150.0" rec2="-130.0  -400.0" rec3="-270.0  -750.0"
    local noheader=""
    case "${2:-}" in
        noheader) noheader=$'\n   NOHEADER  ALL' ;;
        pvd2005)
            sfc=PVD_0101.SFC; pfl=PVD_0101.PFL
            surf="14765  2005"; uair="14684  2005"; startend="05 01 01 11 05 01 01 14"
            # downwind of the 294-333 degree winds
            rec1="140.0  -120.0"; rec2="350.0  -300.0"; rec3="600.0  -500.0" ;;
    esac
    cat <<EOT
CO STARTING
   TITLEONE  POSTFILE output types: $1
   MODELOPT  DFAULT $1
   AVERTIME  1  PERIOD
   POLLUTID  PM10
   RUNORNOT  RUN
CO FINISHED
SO STARTING
   LOCATION  STK1  POINT  0.0  0.0  0.0
   SRCPARAM  STK1  10.0  10.0  300.0  5.0  1.0
   PARTDIAM  STK1  2.0  10.0  30.0
   MASSFRAX  STK1  0.3  0.4  0.3
   PARTDENS  STK1  2.65  2.65  2.65
   SRCGROUP  ALL
   SRCGROUP  STK  STK1
SO FINISHED
RE STARTING
   DISCCART  $rec1  0.0  0.0
   DISCCART  $rec2  0.0  0.0
   DISCCART  $rec3  0.0  0.0
RE FINISHED
ME STARTING
   SURFFILE  $sfc
   PROFFILE  $pfl
   SURFDATA  $surf
   UAIRDATA  $uair
   PROFBASE  0.0  METERS
   STARTEND  $startend
ME FINISHED
OU STARTING
   RECTABLE  1  FIRST$noheader
   POSTFILE  1  ALL  PLOT  post_1h.pst
   POSTFILE  1  STK  UNFORM  post_1h.bin
   PLOTFILE  1  ALL  FIRST  high_1h.plt
   POSTFILE  PERIOD  ALL  PLOT  post_per.pst
   POSTFILE  PERIOD  STK  UNFORM  post_per.bin
OU FINISHED
EOT
}

for entry in "${CASES[@]}" "${EXTRA_CASES[@]}"; do
    IFS=: read -r case types variant <<< "$entry"
    mkdir -p "$HERE/$case"
    write_deck "$types" "$variant" > "$HERE/$case/aermod.inp"
    work="$(mktemp -d)"
    cp "$HERE/$case/aermod.inp" "$HERE"/HOUSTON_0228.* "$HERE"/PVD_0101.* "$work/"
    (cd "$work" && "$EXE" > stdout.txt 2>&1) || true
    if ! grep -q "AERMOD Finishes Successfully" "$work/aermod.out"; then
        echo "$case: AERMOD did not finish successfully" >&2
        exit 1
    fi
    cp "$work/post_1h.pst" "$work/post_1h.bin" "$work/high_1h.plt" \
       "$work/post_per.pst" "$work/post_per.bin" "$HERE/$case/"
    echo "$case ($types): $(wc -c < "$HERE/$case/post_1h.bin") bytes of post_1h.bin"
    rm -rf "$work"
done
