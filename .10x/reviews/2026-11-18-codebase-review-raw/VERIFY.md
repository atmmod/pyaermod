# Verifier brief (stage 4)

Read <scratch>/BRIEF.md first: the same rules apply (READ-ONLY on <repo>; python is <scratch>/venv/bin/python, Python 3.15, CI uses 3.11-3.13).
You are an independent verifier. Reviewers wrote findings into <scratch>/findings/<name>.md with repro scripts in <scratch>/repro/<name>/. Your job is to try to REFUTE each
high and medium BUG finding assigned to you (skip low, CONCISION, DOCS and POLICY items unless told otherwise). Do not trust the reviewer's script: read the code
yourself, and where the claim is about what AERMOD does, read the Fortran in <repo>/aermod/ yourself and cite file + routine + line.
A real AERMOD binary is at <repo>/bin/aermod if present (check its version with strings | grep -E '24142|26135'); you may run small decks through it in your own directory.

For each finding give a verdict:
- CONFIRMED: you reproduced it. Write a pytest test that FAILS at HEAD and will pass once the bug is fixed, asserting the correct behaviour (not the reviewer's
  proposed implementation). Put tests in <scratch>/verify/<your-name>/test_<area>.py, written in the style of the repo's tests (imports from pyaermod, plain pytest, tmp_path),
  so they can be moved into tests/ unchanged. Run them and confirm they fail for the right reason.
- REFUTED: say exactly why (the code path is unreachable, the Fortran says otherwise, the reviewer's input was itself invalid...).
- PARTLY: what is true and what is not.
- CANNOT-VERIFY: what would be needed.
Also flag: a proposed fix that would break something else or change public behaviour users may rely on; a finding whose correct behaviour is a judgement call for the maintainer.

Write <scratch>/verify/<your-name>/verdicts.md: one section per finding ID with verdict, evidence (commands run, Fortran citations), the test name, and a note on the fix's blast radius.
Reply with at most 20 lines: a table of ID -> verdict, then anything the orchestrator must decide.
