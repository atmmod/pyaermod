# Status

**Phase:** browser-gui Phase 6 complete (delivery prepared; deploy happens on merge to main)
**Branch:** claude/blissful-gauss-6n1wht
**ADR:** ADR-001

| Task | State |
|---|---|
| T1 reader/writer quoting (H4) | done |
| T2 SURFDATA numeric forms | done |
| T3 explicit wasm path | done |
| T4 wasm trap keeps .out | done |
| T5 readiness.py | done |
| T6 browser core | done |
| T7 import_deck/apply_terrain | done |
| T8 run/file | done |
| T9 site/app shell | done |
| T10 bridge + journeys + pyodide smoke | done |
| T11 build stage + docs | done |

Blocker (non-fatal): AERMOD-wasm not buildable/downloadable here; wasm tiers verified in CI.

## Verification
- QA: .10x/reviews/2026-11-12-qa-report.md (CI-only items listed there)
- Security: .10x/reviews/2026-11-12-security-review.md (approved, one accepted risk)

## Release readiness
- Ready to open a PR. Merge gate: wasm_aermod.yml green on the branch (first real Pyodide/wasm run of the app).

## 2026-11-16: docs and release
| Item | State |
|---|---|
| PR A: release-blocking docs fixes + v2.3.0 prep | in review |
| PR B: docs restructure + screenshots (quickstart, GUI guide, student-guide tutorials) | next |
| Regulatory flag checks (code bug) | queued as separate task |

## 2026-11-17: docs PR B
| Item | State |
|---|---|
| #68 (docs fixes, v2.3.0 prep, student-guide split) | merged |
| PR B: screenshots, GUI guide, quickstart, docs-examples test | in review |
| Follow-up: single install page, architecture.md, Validation nav section | next |

## 2026-11-17: review fixes H2, H3, H5, H6 (PR #70)
| Item | State |
|---|---|
| H2/H3/H5/H6 fixes | in PR #70, CI green |
| Code review (10 findings) | verified: 9 confirmed, 1 partly refuted (.10x/reviews/2026-11-17-pr70-review-verification.md) |
| Fixes for confirmed findings | awaiting maintainer go-ahead |
