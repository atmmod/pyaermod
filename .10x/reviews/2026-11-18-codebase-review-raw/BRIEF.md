# Shared brief: pyaermod codebase review (read this first)

Repo: <repo> (Python wrapper for EPA AERMOD; src layout, package in src/pyaermod, tests in tests/).
You are one reviewer in a staged review. Goals: (1) find real bugs, (2) find ways to make the code more concise and clear
WITHOUT removing features or changing public API, (3) GUI quality, (4) docs accuracy and concision.

## Rules
- READ-ONLY on the repo: do not edit, create or delete anything under <repo>, and run no git command that changes state.
- Scratch files (repro scripts) go in <scratch>/repro/<your-name>/ only.
- Python for running things: <scratch>/venv/bin/python (editable install of the repo). It may still be installing:
  it is ready when <scratch>/pip.log ends with "exit=0". Read code first; run scripts once it is ready. Do not pip install anything.
- Single tests: <scratch>/venv/bin/python -m pytest -o addopts="" -q -p no:cacheprovider <path>. Do not run the whole suite.
- EPA Fortran source for checking semantics is in <repo>/aermod/ (gitignored). Never guess what AERMOD does:
  cite the Fortran file and routine, or mark the finding PLAUSIBLE.
- Earlier reviews: .10x/reviews/2026-11-11-codebase-review.md (Medium/Low mostly still open) and
  .10x/reviews/2026-11-17-pr70-review-verification.md. For items in your area, state whether each is still present at HEAD. Do not re-report H2/H3/H5/H6 (fixed).
- Do not report style nits ruff would catch, missing docstrings or type hints, or speculative "could be cleaner" without a concrete change.

## Output
Write your findings to <scratch>/findings/<your-name>.md, then reply with at most 15 lines: counts by severity and the top 5 items.
Format per finding:
### <ID> [BUG|CONCISION|GUI|DOCS] [high|medium|low] <one-line title>
- Where: path:line
- What: the defect or the redundancy, concretely
- Evidence: for a bug, the input that fails and what happens vs what should (path of repro script if you ran one; say VERIFIED, READ or PLAUSIBLE).
  For concision: the specific change, approximate lines removed, and which tests cover the code.
- Fix: the smallest correct change
Quality over quantity: a wrong finding costs more than a missed one. Say plainly what you did not look at.
