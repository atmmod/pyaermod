# PyAERMOD — Remaining Code Development Plan (for agents)

**Repository:** https://github.com/atmmod/pyaermod (main @ `cafa7e2`, v2.0.0 on PyPI)
**Prepared:** 2026-09-25

## Context and current state

PyAERMOD is a mature, validated Python wrapper for EPA's AERMOD dispersion modeling chain. The non-slow test suite passes (1,794 passed, 99 skipped, 288 deselected in ~27 s). EPA parity evidence stands at 142/142 POSTFILE comparisons against the v26135 reference sets under EPA's ±0.001 slope criterion, with a bit-exact AERTEST regression (144 receptors) and an analytic synthetic-DEM AERMAP regression. The v26135 keyword audit (`docs/keyword-audit-v26135.md`) documents that the reader handles 59 of 115 dispatched keywords; the remainder pass through silently. One acknowledged defect exists: the AERSCREEN deck writer emits a format the interactive program never reads. PR #9 (`plan/phase2-validation`) is a large, unmerged validation branch.

## Standing rules for every work package

Each work package is delivered as one pull request that follows the repository's established practice.

1. **Oracle first.** Build the relevant EPA binary (via `scripts/fetch_epa_source.sh` and the `scripts/build_*.sh` pattern), generate the reference behavior, and only then implement. Never guess at Fortran semantics.
2. **Tests pin the change.** Every fix or feature carries a test that fails without it. When a keyword gains structural support, replace its `test_unhandled_*_keywords_pass_through` entry with a structural assertion, as the audit itself instructs.
3. **Gates before merge.** The full suite is green; the mypy baseline (`mypy-baseline.txt`, measured on the CI 3.12 leg) does not increase; ruff and pre-commit pass; the EPA parity job passes when touched code affects it.
4. **Documentation moves with code.** Update `CHANGELOG.md` (Keep a Changelog format), the keyword audit, and any affected `docs/` page in the same PR.
5. **Commit messages explain the why**, in the style of the existing history (see PR #9's messages for the standard).
6. **Reference sets** resolve through `pyaermod.epa_testcases.find_epa_testcase_set`; honor `$PYAERMOD_EPA_TESTCASES`.

## WP-0: Land PR #9 (`plan/phase2-validation`)

This is the highest-value single action; everything else builds on it.

- Rebase the branch onto main and resolve conflicts (the branch is +5,291/−475 and touches `aersurface.py`, `bpip.py`, `design_values.py`, `input_reader.py`, and many tests).
- Confirm all CI legs pass, including min-deps and the mypy gate (note the branch's own commit about the CI-measured baseline of 71).
- Merge and tag v2.1.0 per `RELEASING.md`.

**Acceptance:** main contains the exact-BPIP sweep tests (6,480 direction comparisons), the AERSURFACE configuration-space tests, the known-answer suites, and the AERSCREEN limitation documentation; CI is green; v2.1.0 is released.

## WP-1: Reader completeness, tranche 1 — regulatory-critical keywords

Implement structural parsing and writing (round-trip, not parse-only) for the audit's "highest value" keywords, in this order:

1. `MULTYEAR`, `SAVEFILE`, `INITFILE` (five EPA decks chain years with these).
2. The NOx background family: `NOXVALUE`, `NOX_FILE`, `NOX_VALS`, `NOX_UNIT`, `NOXSECTR`, plus `O3SECTOR` and `OZONUNIT` (GRSM/TTRM runs).
3. OU design-value keywords: `MAXDAILY`, `MXDYBYYR`, `MAXDCONT`, and `FILEFORM`. Wire these to `design_values.py` and `naaqs.py` so the 1-hour NO2/SO2 NAAQS workflow is expressible end to end.
4. Gas-deposition defaults: `GASDEPDF`, `GASDEPVD`, `GDSEASON`, `GDLANUSE`.

**Acceptance:** each keyword is stored on the `AERMODProject` model, written back correctly, exercised by a reader test and a writer test, and its pass-through test is replaced. Every EPA deck that uses the keyword round-trips with the line preserved semantically.

## WP-2: Reader completeness, tranche 2 — source construction

Close the "recognized but not constructed" gap:

1. `AREAVERT` → construct AREAPOLY sources.
2. `BLPINPUT` and `BLPGROUP` → construct BUOYLINE sources.
3. RLINEXT with per-end z values.
4. `OLMGROUP`, `PSDGROUP`, `NO2RATIO` (group semantics for OLM and PSD-credit runs).
5. `EMISUNIT`, `CONCUNIT`, `DEPOUNIT`.
6. RLINE barrier and depression keywords: `RBARRIER`, `RDEPRESS`, `SBARRIER`, `VBARRIER`, `RLEMCONV`.

**Acceptance:** each constructed source type round-trips parse → write → re-parse to semantic equality on the relevant EPA decks, and the writer's output for those decks drives the real AERMOD binary to parity in the regulatory suite.

## WP-3: Audit discrepancy fixes and the round-trip guarantee

1. Fix the `MAXIFILE` four-field form (`<aveper> <grpid> <thresh> <filename>`) in the reader and the writer together, retiring the pinned discrepancy test.
2. Fix the `GRIDPOLR DIST`/`GDIR` three-token heuristic so an explicit three-distance list with an integer-looking middle value is read correctly.
3. Implement `AERMODProject.unparsed_lines` as the module docstring promises: unknown keywords are collected, reported, and re-emitted (or explicitly flagged) rather than silently dropped.
4. Add a suite-wide round-trip test: all 53 EPA v26135 decks parse → write → re-parse with no loss on handled keywords and every unhandled line accounted for in `unparsed_lines`.

**Acceptance:** the audit's "Discrepancies and follow-ups" section is emptied or reduced to documented design decisions; the round-trip test runs in the default suite.

## WP-4: AERSCREEN rescue

This closes the only acknowledged defect. It may proceed in parallel with WP-1.

1. Patch EPA's `AERSCREEN.FOR` per the documented findings (the missing continuation comma at line 7995 that swallows FORMAT label 5001, and the Intel format extension requiring `-fdec -std=legacy`); add `scripts/build_aerscreen.sh` mirroring the existing build scripts.
2. Replace the incorrect KEY:value writer with the real interface: an ordered sequence of answers on stdin, plus support for the `**`-prefixed header reload format of AERSCREEN's output file.
3. Validate against EPA's `aerscreen_test_cases.zip` with the known-answer pattern PR #9 established for AERSURFACE and BPIP.
4. Correct the module docstring and `docs/` accordingly.

**Acceptance:** `AERSCREENRunner` drives a locally built AERSCREEN binary through at least the EPA test cases with outputs matching EPA's published references; the known-limitation note is replaced by validation evidence.

## WP-5: EV pathway and remaining ME/OU keywords

1. EV pathway: `EVENTLOC`, `EVENTPER`, `EVENTOUT`, and EV `FILEFORM` (the writer already supports EVENT processing, so the reader should reach parity).
2. Remaining ME keywords: `DAYRANGE`, `NUMYEARS`, `WINDCATS`, `SCIMBYHR`, and the turbulence-suppression flags as pass-through-with-storage.
3. Remaining OU keywords: `NOHEADER`, `RANKFILE`, `SEASONHR`, `EVALFILE`, `TOXXFILE`.
4. Regenerate the keyword audit and publish the updated coverage table.

**Acceptance:** the audit reports every v26135 keyword as at least structurally recognized, with any deliberate non-modeling documented.

## WP-6: Release engineering for publication

1. Add `CITATION.cff`; mint a Zenodo DOI on the release tag; confirm the docs site deploys.
2. Run the benchmark workflow and record timings (single-run overhead versus direct binary invocation; parallel batch throughput). These numbers feed the manuscript.
3. Tag v2.2.0 as the archival version the JAWMA paper cites.

**Acceptance:** a citable, DOI-bearing release exists whose validation report, keyword audit, and benchmarks are reproducible from the tag.

## Sequencing and effort

Execute WP-0 immediately. Run WP-1 and WP-4 in parallel (they touch different modules). Follow with WP-2 and WP-3, then WP-5, and finish with WP-6. At the pace the repository's history demonstrates, this is roughly four to six agent PRs over two to three weeks of working sessions.
