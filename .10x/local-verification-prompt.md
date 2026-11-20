# Local verification prompt (needs the AERMOD binaries and EPA Fortran)

Paste the block below into a Claude Code session started in the local pyaermod checkout, where `aermod/` (EPA Fortran,
v24142), the v26135 source copy, the AERMOD binaries and `test_cases/` exist. It covers what the cloud session could
not check.

```
You are verifying work done in a cloud session on atmmod/pyaermod that had no AERMOD binary, no EPA Fortran and no
test_cases/. Read .10x/handoff.md on origin/claude/codebase-review-2026-11-18-4uyhje first. Work on a fresh branch
from origin/main after `git fetch`. PRs #80 (regulatory text, validator follow-ups) and #82 (follow-ups) may or may
not be merged yet: check with `gh pr view 80` and `gh pr view 82`, and if one is still open, check out its branch
for the items that concern it.

Rules: never guess what AERMOD does. Quote the Fortran routine and line numbers, or show the AERMOD message from a
real run. Do not change anything that alters computed design values (quarterly PM2.5 means, PM10 N+1 rank, running
8-hour ozone, 150 vs 155). Never mention private research in the public repo. Run `ruff check src/ tests/` before
any push. Open a PR only for a confirmed defect, with a test that failed before the fix.

Report a verdict for each item: CONFIRMED, REFUTED (with the fix) or COULD NOT CHECK (with the reason).

1. CO LOW_WIND, validator.py `_validate_low_wind` and `LOW_WIND_FIELDS` (PR #80).
   Read coset.f SUBROUTINE LOW_WND in v24142 and v26135.
   a. Is PBAL (or PBALANCE) accepted only as the seventh field, or in any position after SVmin? The validator
      treats a non-numeric token in fields 1 to 6 as E208 and requires PBAL in field 7.
   b. Are the accepted ranges SVmin 0.01-1.001, WSmin 0.01-1.001, FRANmax 0-1, SWmin 0-3, BigT 0.5-48,
      FRANmin 0-1 with FRANmin <= FRANmax (E426)? Are the bounds inclusive?
   c. Is more than seven fields E202, and a bad seventh field E203?
   d. Run four decks through AERMOD v24142 and v26135 with MODELOPT ALPHA: `LOW_WIND 0.3 0.5`,
      `LOW_WIND 0.3 PBAL`, `LOW_WIND 1.001`, `LOW_WIND 0.3 0.5 0.5 0.02 24 0.8`. Record each message code and
      compare with what `Validator.validate` says for the same `low_wind_option`.

2. E336 (PR #80). Run an OLM deck with no NO2STACK and no NO2RATIO for one source through both binaries and
   confirm E336. Confirm TTRM and TTRM2 behave the same, since the validator applies the check to
   NO2STACK_METHODS = OLM, PVMRM, GRSM, TTRM, TTRM2.

3. W325 (PR #80). Run a POINT source with exit velocity -1.0 and confirm W325 and a completed run. Confirm that
   POINTCAP and POINTHOR go through the same PPARM check.

4. Several urban areas (PR #80). With two URBANOPT cards, run a deck where one urban source has no area ID on
   URBANSRC, and record the message. The validator now makes `is_urban=True` without `urban_area_name` an error
   in that case.

5. GRSM with DFAULT. Run a GRSM deck with DFAULT through v24142 and v26135 and confirm no E199 or E204, as the
   `EPA_APPENDIX_W_2024` profile assumes. If a v23132 binary exists, confirm it refuses the same deck.

6. Binary-backed tests. With AERMOD on PATH, run the full suite including the tests CI skips (the `aermod-runs`
   job, tests/regulatory, anything marked for a real binary, and `-m slow` once). Run it with v24142 on PATH and
   again with v26135. List every failure with its cause.

7. tests/regulatory/test_event_rewrite.py failed once locally with v24142 on PATH. Reproduce it on origin/main,
   find the root cause, and say whether it is a product bug, a version difference the test should account for,
   or an environment problem. Compare with v26135 (see the branch skip-eventfil-test-unless-26135 for context).

8. GeoJSON export CRS. In an environment with geopandas 0.14.x, export sources and receptors to GeoJSON with a
   UTM zone set and check the coordinates and CRS written (RFC 7946 expects WGS84 longitude and latitude).
   Compare with the current geopandas release. Report the versions tested.

9. mypy baseline. In a Python 3.12 environment matching CI (`pip install -e ".[dev]"` plus what the CI job
   installs), run `python scripts/mypy_gate.py` and, if the count is below the number in mypy-baseline.txt, run
   `python scripts/mypy_gate.py --update` and open a small PR. Do not update from any other Python version.

10. Desktop window (needs a display). Start `pyaermod-desktop`, change a field so the project is modified, and
    close the window. Does anything ask before the change is lost? PR #78 added a browser "Leave site?" question
    that was not exercised in pywebview. If nothing asks, docs/desktop.md is right as it stands; if it does ask,
    correct that page.

11. Housekeeping only reachable locally: `git worktree prune`, then list local branches already merged into
    origin/main (`git branch --merged origin/main`) including backup/codebase-review-local, and ask before
    deleting any.

Finish with a table of the eleven verdicts and append it to .10x/handoff.md on
claude/codebase-review-2026-11-18-4uyhje.
```
