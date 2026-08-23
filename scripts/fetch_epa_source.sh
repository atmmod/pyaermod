#!/usr/bin/env bash
#
# Resilient download of an EPA SCRAM source archive (AERMOD / AERMAP / AERMET /
# test cases) for CI.
#
# Why this exists: the EPA gaftp.epa.gov server intermittently rate-limits or
# returns a short non-zip error response. A bare `curl -sSL -o x.zip URL` (no
# --fail) happily saves that error body as "x.zip", and the following `unzip`
# then fails the entire job. Runs would flake red for reasons unrelated to the
# code under test.
#
# This wrapper:
#   * uses `curl --fail` so HTTP >= 400 is an error, not a saved error page;
#   * retries at both the curl and shell level with linear backoff;
#   * validates the result is a real zip (`unzip -t`) before succeeding;
#   * short-circuits if a valid archive is already present (so it composes with
#     actions/cache — a cache hit skips the network entirely);
#   * reports the archive's top-level directory (EPA encodes the version in it,
#     e.g. aermod_source_v26135) on stdout and, when running under GitHub
#     Actions, in the job summary ($GITHUB_STEP_SUMMARY).
#
# Usage:  scripts/fetch_epa_source.sh <url> <output.zip>
# Env:    FETCH_ATTEMPTS (default 6)   FETCH_BACKOFF (default 10, seconds * attempt)

set -euo pipefail

URL="${1:?usage: fetch_epa_source.sh <url> <output.zip>}"
OUT="${2:?usage: fetch_epa_source.sh <url> <output.zip>}"
ATTEMPTS="${FETCH_ATTEMPTS:-6}"
BACKOFF="${FETCH_BACKOFF:-10}"

is_valid_zip() { [ -s "$1" ] && unzip -t -qq "$1" >/dev/null 2>&1; }

# Print (and, in CI, summarise) which EPA source version the archive holds.
# EPA archives extract either into a versioned subdir (AERMOD, AERMAP) or flat
# at the root (AERMET); the derived name is empty in the flat case.
report_archive() {
  local topdir size
  topdir=$(unzip -Z1 "$OUT" | awk -F/ 'NF>1{print $1; exit}')
  size=$(wc -c < "$OUT" | tr -d ' ')
  echo "fetch_epa_source: archive top-level dir: ${topdir:-<flat archive>} (${size} bytes) from ${URL}"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "EPA source: ${topdir:-<flat archive>} from ${URL} (${size} bytes)" >> "$GITHUB_STEP_SUMMARY"
  fi
}

# Reuse an already-valid archive (e.g. restored by actions/cache).
if is_valid_zip "$OUT"; then
  echo "fetch_epa_source: reusing existing valid archive ($(wc -c < "$OUT") bytes): $OUT"
  report_archive
  exit 0
fi

for i in $(seq 1 "$ATTEMPTS"); do
  echo "fetch_epa_source: attempt ${i}/${ATTEMPTS} -> ${URL}"
  if curl -sSL --fail --retry 3 --retry-delay 3 --retry-all-errors \
          --connect-timeout 30 --max-time 600 -o "$OUT" "$URL"; then
    if is_valid_zip "$OUT"; then
      echo "fetch_epa_source: ok ($(wc -c < "$OUT") bytes, valid zip)"
      report_archive
      exit 0
    fi
    echo "fetch_epa_source: downloaded file is not a valid zip (server likely returned an error/rate-limit page)"
  else
    echo "fetch_epa_source: curl failed on attempt ${i}"
  fi
  rm -f "$OUT"
  if [ "$i" -lt "$ATTEMPTS" ]; then
    sleep_for=$(( i * BACKOFF ))
    echo "fetch_epa_source: backing off ${sleep_for}s"
    sleep "$sleep_for"
  fi
done

echo "fetch_epa_source: ERROR — could not fetch a valid zip from ${URL} after ${ATTEMPTS} attempts" >&2
exit 1
