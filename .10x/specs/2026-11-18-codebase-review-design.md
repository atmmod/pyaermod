# Codebase review and cleanup: design (2026-11-18, main @ 24c5dff)

Slug: `codebase-review`. Approved by the maintainer 2026-11-18, including going through to fix PRs.

## Goals
1. Make the code more concise and clear without removing features.
2. Eliminate bugs.
3. Make both GUIs (`gui_v2/`, and `webapp/` + `browser.py`) work exceptionally well for a user.
4. Refine the docs to match, for concision and clarity.

## Scope
`src/pyaermod/` (35k lines), `gui_v2/` (8k), `webapp/`, `docs/` (7.7k), README, CONTRIBUTING. Tests are read as evidence and
extended; they are not a cleanup target. The open medium and low findings of `.10x/reviews/2026-11-11-codebase-review.md` seed the work.

## Stages and model tiers
| Stage | Tier | Agents | Work |
|---|---|---|---|
| 0 Tooling | none | 0 | ruff, mypy vs baseline, coverage, vulture, radon, strict docs build, GUI journeys: a hotspot map |
| 1 Inventory | Haiku | 3 | public API vs `docs/api/`; stale files; docs links and cross-references |
| 2 Module review | Sonnet | 8 | one per ~4-5k-line slice; bugs (with a repro script) and concision; re-check open 11-11 findings |
| 3 GUI + architecture | Opus | 3 | gui_v2 code; live walkthrough of both GUIs; cross-module duplication and the two largest modules |
| 4 Verification | Sonnet / Opus | 3-4 | a different agent reproduces each bug as a failing test; Opus for Fortran or regulatory semantics |
| 5 Docs | Sonnet | 2 | docs vs code accuracy; a concision plan |
| 6 Synthesis | orchestrator | - | adjudicate, rank, write `.10x/reviews/2026-11-18-codebase-review.md` |

Review agents are read-only on the checkout; repro scripts go to the session scratchpad.

## Fix phase
PRs in order: bugs (failing test first), behaviour-preserving simplifications, GUI, docs. One writer per set of files, each in
its own worktree. Sonnet for mechanical changes, Opus for `input_reader.py` and `validator.py` refactors.

## Gates for every PR
Default suite green, coverage >= 95%, mypy baseline not raised, `ruff check src/ tests/` clean, GUI journeys J1-J9 green,
EPA parity where touched, `pyaermod.__all__` unchanged, CHANGELOG and affected docs updated in the same PR.

## Held for the maintainer
Findings that turn on regulatory policy or a default (for example Ts <= 0, the 100,000-receptor limit, rounding before a NAAQS
comparison) are reported with evidence and not changed without a decision.

## Out of scope
New features; the private research study; EPA Fortran sources.
