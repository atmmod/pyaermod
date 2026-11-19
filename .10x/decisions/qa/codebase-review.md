# codebase-review (2026-11-18)
Report: .10x/reviews/2026-11-18-codebase-review.md. Every high and medium bug outside the live GUI walkthrough was re-verified by a second agent,
which wrote a failing test (about 150 tests in .10x/reviews/2026-11-18-codebase-review-raw/verify/). Those tests are the acceptance tests for the fix PRs;
the "guard" tests in them must keep passing. Gates per PR: default suite, coverage >= 95%, mypy <= 60, ruff, GUI journeys, EPA decks that now write.
Known environmental failures on Python 3.15 / aermod on PATH: two tests, listed in the report.
