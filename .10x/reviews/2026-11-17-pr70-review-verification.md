# PR #70 code review: verification (2026-11-17)

Scope: the 10 findings of the high-effort code review of PR #70 (branch
claude/blissful-gauss-6n1wht vs main 6e04e58). Roles: QA (reproduction),
Senior Engineer (code reading), Security (sandbox), with EPA's AERMOD v26135
as the oracle: soset.f / meset.f printed by the keyword oracle (run
44170259500) and probe decks 33-33e run through the compiled binary (run
44190240402). Reproduction script: session scratchpad, not committed.

| # | Finding | Verdict | Evidence | Severity |
|---|---|---|---|---|
| 1 | A declared sector without values passes validation | CONFIRMED | repro: no error; probe 33: `SO E238 SRCQA: Not Enough BACKGRND Concentration Values Specified No BG SECT2!` | Medium (fatal at AERMOD setup, not a wrong number) |
| 2 | Non-contiguous sector IDs pass validation | CONFIRMED | repro: no error, writes `BGSECTOR 0.0 180.0` + `SECT5`; soset.f accepts SECT5 only if NUMBGSects >= 5; probe 33b: `E203 BGSECTOR ID` | Medium |
| 3 | Highest-year NO2 annual DV counts partial years | CONFIRMED | repro: full 2019 at 40 + one day of 2020 at 150 gives DV 150, exceeds=True (a full-year DV of 40). Appendix S: an annual DV is valid when >=75% of the year's hours are reported (from search excerpt; eCFR not reachable here) | High (silent, inflated regulatory number) |
| 4 | Verbatim sector background + a new modelled background writes conflicting cards | CONFIRMED | repro writes `BACKGRND ANNUAL 5` before the verbatim `BGSECTOR`/`SECTn` lines; probe 33c: fatal `E203 BGSECTOR ID` | Medium (needs user action after reading such a deck) |
| 5 | PROFBASE: non-numeric crashes; unknown unit read as metres | PARTLY REFUTED | meset.f PRBASE: unit other than METERS/FEET is W203 and the value is used as metres; probe 33e: `ME W203`, base 328.00 m. pyaermod matches AERMOD on units. Non-numeric: AERMOD E208, pyaermod raises ValueError; this line predates the PR (main: `float(toks[0])`) | Low, pre-existing |
| 6 | Validator raises TypeError on non-numeric background values | CONFIRMED | repro: `TypeError: '<' not supported between 'str' and 'int'`; the old code had the same comparison | Low, pre-existing pattern |
| 7 | Flag/count check duplicates _validate_background_spec | CONFIRMED | validator.py `_validate_background_spec` (O3/NOx) and new `_validate_background_profile` | Cleanup |
| 8 | _value_lines duplicates the O3VALUES chunk writer | CONFIRMED | pathways.py `per_line = 12` with `_num`, sources.py `VALUES_PER_LINE = 12` with `.10g` | Cleanup |
| 9 | Lower-bound caption shown for every pollutant | CONFIRMED | caption unconditional in gui_v2/pages/results.py and webapp/app.js | Low (UX) |
| 10 | BGSECTOR lost when no sector line parses | CONFIRMED | repro: `BGSECTOR 0 180` + `BACKGRND SECT1 ANNUAL x5` rewrites as the SECT1 line alone; probe 33d: `E171 Sector ID specified without Sector-varying Option` | Low (deck was already invalid; rewrite changes which error) |

Security: the sector HOURLY file kept verbatim (H3) is checked by
`read_aermod_input(sandbox=True)`: `../../etc/passwd`, quoted or not, raises
PathTraversalError. Before the PR the line was dropped, so the change adds a
checked path, not an unchecked one. No other security impact found.

Recommended for this PR: 3, 1, 2, 4, 10, then 7, 8, 9. Pre-existing, separate:
5 (non-numeric PROFBASE), 6.
