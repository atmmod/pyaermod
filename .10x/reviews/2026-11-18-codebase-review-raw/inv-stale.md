# inv-stale: stale and redundant tracked files and references (HEAD 794fe60, branch claude/codebase-review-2026-11-18)

Method: `git ls-files` (1077 tracked files). Path-reference scan of tracked md/yml/toml/py/sh/Makefile for repo paths; `make` targets referenced in tracked files; mkdocstrings `:::` directives (45) and dotted `pyaermod.*` names in docs/examples/benchmarks (65) resolved by importing the editable install; every `from pyaermod... import` in 312 tracked .py/.ipynb files under examples/, benchmarks/, tests/, docs/, scripts/, src/ resolved. Nothing was edited or deleted. Deletion candidates are listed with evidence only.

## Item 1: top-level files

### INV-01 [CONCISION] [medium] requirements.txt is unreferenced and its floors disagree with pyproject
- Where: requirements.txt:2-8 (numpy>=1.20.0, pandas>=1.3.0, matplotlib>=3.3.0, scipy>=1.7.0, folium>=0.12.0); pyproject.toml:30-31 (numpy>=1.24.0, pandas>=2.0.0), :46-47 and :74 (matplotlib>=3.7.0), :47 (scipy>=1.10.0), folium>=0.14.0 in viz.
- What: no tracked file refers to `requirements.txt` at top level (git grep finds only docs/requirements.txt and docs/lite/requirements.txt, which are separate). Last changed in the initial commit d1c05b6 (2026-02-04). It has no nicegui and its floors are older than the package's own.
- Evidence: READ + git grep. Candidate for deletion; not proposed.
- Fix: listed only.

### INV-02 [DOCS] [medium] PLAN-code.md is a stale snapshot, referenced only by PLAN-gui.md
- Where: PLAN-code.md:3-4 ("main @ cafa7e2, v2.0.0 on PyPI", "Prepared: 2026-09-25"); PLAN-code.md:26 ("CI-measured baseline of 71"); PLAN-gui.md:144 (cites it as the standing rules).
- What: the document describes v2.0.0-era state; the project is at 2.3.0. No code, workflow, test or script refers to it. Its only live content is the standing rules at PLAN-code.md:16 (mypy baseline measured on the CI 3.12 leg, etc.), which PLAN-gui.md:144 relies on.
- Evidence: READ; `git grep 'PLAN-code'` shows PLAN-gui.md:144, PLAN-code.md:16 only outside itself. Last commit 1f36f86 (2026-09-25).
- Fix: listed only. Candidate to archive, or to move its rules into CONTRIBUTING.md.

### INV-03 [DOCS] [medium] PLAN-gui.md still lists finished or removed items as open
- Where: PLAN-gui.md:40 (`tests/test_gui_apptest.py` "still targets the Streamlit GUI", CONTRIBUTING "still tells contributors to edit gui.py"); PLAN-gui.md:159 (step 4: "Delete tests/test_gui_apptest.py"); PLAN-gui.md:234 (step 2: replace CONTRIBUTING `gui.py` steps); PLAN-gui.md:19 (WP-G7 "Remaining: ... J10 (the desktop bundle smoke step in `build_desktop.yml`)"); PLAN-gui.md:235 (WP-G7 item 3 struck through as "Dropped: the bundle is no longer built"); PLAN-gui.md:299 (`packaging/desktop_entry.py`, `packaging/pyaermod_desktop.spec`).
- What: `tests/test_gui_apptest.py` is not tracked. CONTRIBUTING.md:138 already points to `_SOURCE_TYPES` in src/pyaermod/gui_v2/pages/sources.py:49, and CONTRIBUTING has no `gui.py` text. `.github/workflows/build_desktop.yml` and the `packaging/` directory are not tracked. PLAN-gui.md:19 says J10 remains while line 235 says it was dropped.
- Evidence: READ; `git ls-files | grep -E 'test_gui_apptest|gui\.py$'` returns nothing; `git ls-files .github/workflows` has no build_desktop.yml.
- Fix: plan-doc edits only (or archive PLAN-gui.md).

### INV-04 [DOCS] [medium] three different mypy baseline numbers across tracked files
- Where: mypy-baseline.txt:1 = `60`; PLAN-gui.md:301, 330, 392 ("`mypy-baseline.txt` stays at 69"); PLAN-code.md:26 ("CI-measured baseline of 71").
- What: the gate (scripts/mypy_gate.py, tests/test_mypy_gate.py:12,64) reads the file, so the file value (60) governs CI. The file was last set in 60b0526 (2026-10-20, v2.2.0 prep). The two plan documents quote other values. Not a code bug; the plan prose is stale.
- Evidence: READ + `git log -- mypy-baseline.txt`.
- Fix: update or drop the numbers in the two plan docs.

### INV-05 [DOCS] [medium] citation text says version 2.2.0 while package and CITATION.cff say 2.3.0
- Where: README.md:177 and docs/index.md:61 ("(version 2.2.0)", DOI 10.5281/zenodo.23512927); CITATION.cff:30 (`version: 2.3.0`), :31 (`date-released: "2026-11-18"`), :32 (`doi: 10.5281/zenodo.23512927  # v2.2.0`).
- What: CITATION.cff:8-13 documents that the release commit keeps the previous DOI as a placeholder until Zenodo mints the new one, so the DOI mismatch is by design. The human-readable version string in README and docs/index is not covered by that rule and says 2.2.0. docs/install.md:110 says 2.2.0 on purpose (old-version message).
- Evidence: READ.
- Fix: change the two version strings to 2.3.0 when the DOI is pasted in; or leave the placeholder and note it.

### INV-06 [DOCS] [low] Dockerfile comment is wrong about setup.py
- Where: Dockerfile:33 ("setup.py reads README.md"); setup.py:1-9 is a shim: `setup()` with no arguments.
- What: setup.py reads nothing. Copying it is harmless but the comment is false. pyproject.toml carries `readme = "README.md"` (pyproject.toml:11).
- Evidence: READ.
- Fix: correct the comment (or drop setup.py from the COPY line if the build works without it; not verified).

### INV-07 [DOCS] [low] setup.py vs pyproject.toml: no conflicting settings
- Where: setup.py:1-9; pyproject.toml:9 (version), :14 (requires-python), :28-31 (dependencies), :46-88 (extras), :117-120 (scripts).
- What: setup.py defines no metadata, so nothing can disagree. Every other source agrees with pyproject: version 2.3.0 (see INV-09); entry points (conda-recipe/recipe.yaml:26-29 lists the same three pyaermod, pyaermod-app, pyaermod-desktop); runtime deps (recipe.yaml:37-38 numpy>=1.24.0, pandas>=2.0.0; run_constraints nicegui>=3.0, matplotlib-base>=3.7.0, pywebview>=5.0); python floor 3.11 (recipe `python_min`); the pyaermod-gui conda package mirrors the `gui` extra. min-constraints.txt pins satisfy every floor (checked against pyproject; enforced by tests/test_packaging.py `test_all_floors_have_a_min_constraint`).
- Evidence: READ.

### INV-08 [DOCS] [low] MANIFEST.in: no entry names a missing file; sdist omits most test fixtures
- Where: MANIFEST.in:1-5 (LICENSE, README.md, CHANGELOG.md, CONTRIBUTING.md, pyproject.toml exist), :8 `recursive-include tests *.py`, :9 `recursive-include docs *.md *.yml`, :10 `recursive-include examples *.py *.ipynb`, :12-16 `prune`, :17 CITATION.cff (exists).
- What: every named file exists. But the tests rule takes only *.py: 481 tracked non-.py files under tests/ (fixtures, json, inp, README.md) are not in an sdist. Likewise docs images, PDFs and .txt are excluded. Whether the sdist should run the suite is a decision, not a defect; the tests in tests/ read these fixtures.
- Evidence: `git ls-files tests | grep -v '\.py$' | wc -l` = 481.

## Item 2: references to missing files, modules, targets, scripts

No stale `gui.py`, `pyaermod.gui`, `streamlit` import or `test_gui_apptest` reference in code, tests, workflows, Makefile, CONTRIBUTING, RELEASING, README or docs. The hits are historical text in CHANGELOG.md (lines 267, 271, 1355, 1361, 3087-3194, 3328), .10x/ and PLAN-gui.md (INV-03), plus tests/test_packaging.py:175 which asserts streamlit is absent.

### INV-09 [DOCS] [low] Missing-path references that are not in git (all gitignored or generated; listed for completeness)
- `test_cases/` (.gitignore:88): .github/workflows/keyword_oracle.yml:137, docs/keyword-audit-v26135.md:41, scripts/run_epa_parity.py:24, src/pyaermod/regulatory_parity.py:6, tests/test_real_aerscreen.py:17, tests/test_real_aersurface.py:19, .github/workflows/epa_parity.yml:28.
- `aermet_test_cases/` (.gitignore:106): .github/workflows/epa_parity.yml:392.
- `aermod/`, `aermap/` (.gitignore:71-72): .github/workflows/real_aermet.yml:79 (comment).
- `bin/*` (.gitignore:82): Makefile:53-59 (guarded by `test -x`), docs and scripts; expected build outputs.
- Generated: tests/fixtures/epa_official/full (docs/README and download_all.py), tests/fixtures/aermap_runner/regenerate.sh "path/to/aermap" (placeholder).
- Evidence: git check-ignore; READ.

### INV-10 [DOCS] [low] Other stale path strings in tracked code/docs
- tests/test_aermet_coverage.py:2 "Additional coverage tests for pyaermod/aermet.py" (path is src/pyaermod/aermet.py).
- tests/test_ensemble.py:1316, tests/test_mypy_gate.py:24,26,44: `src/x.py`, `src/pyaermod/a.py`, `src/pyaermod/b.py` are fixture strings in mocked output, not missing files.
- scripts/patches/aerscreen_<version>.patch (scripts/build_aerscreen.sh:46): glob matches scripts/patches/aerscreen_21112.patch; not missing.
- scripts/oracle_decks/13-18 (docs/keyword-audit-v26135.md:106, CHANGELOG.md:486): range; decks exist.
- benchmarks/README.md:9-14 lists three bench scripts and the run_benchmarks/compare_benchmarks pair; bench_aermod_runs.py (referenced at docs/benchmarks.md:6) is not listed there. Minor.

### Makefile targets
- Every make target named in tracked files exists in Makefile: test, test-full, test-binaries, test-gui-e2e, test-gui-e2e-real, lint, typecheck, benchmark, clean (tests.yml, CONTRIBUTING, docs, RELEASING). No missing target.
- Console scripts named in docs/CI: pyaermod, pyaermod-app, pyaermod-desktop, and `pyaermod gui` (cli.py:222). `pyaermod-gui` appears only as the conda package name (conda-recipe/README.md:17), not as a command.

## Item 3: skipped and removed-code tests

### INV-11 [DOCS] [low] No test file is skipped unconditionally; no test exercises removed code
- Module-level skips are all conditional: pytestmark skipif on binary/data presence in tests/regulatory/test_epa_known_answers.py:45, tests/test_aersurface_deck_acceptance.py:33, tests/test_bpip_known_answers.py:39, tests/test_build_scripts.py:46, tests/test_epa_deck_acceptance.py:101, tests/test_gui_v2_smoke.py:77 (Windows), tests/test_real_aermap.py:30, tests/test_real_aermet.py:32, tests/test_real_aermet_binary.py:43, tests/test_real_aermod.py:66, tests/test_real_aermod_source_writers.py:52, tests/test_real_ensemble.py:39, tests/test_runner_background.py:28 (Windows); allow_module_level skips at tests/regulatory/test_epa_aermod_suite.py:42 and tests/regulatory/test_epa_rewritten_so.py:52 (conditional on missing_reason()).
- No `pytest.skip`/`pytestmark = ...skip` with an unconditional condition found. Streamlit/gui.py: no test imports them (tests/test_packaging.py:175 only asserts "streamlit" is absent).
- All 312 files' `from pyaermod...` imports resolve (INV-12 below), so no test imports a removed name.
- Evidence: git grep + READ.

## Item 4: version strings

| Location | Value | Agrees with 2.3.0? |
|---|---|---|
| pyproject.toml:9 | version = "2.3.0" | yes (authoritative) |
| setup.py | no version | n/a (shim) |
| src/pyaermod/__init__.py:32 | __version__ = "2.3.0" | yes |
| CITATION.cff:30 | version: 2.3.0 | yes; doi still v2.2.0 by design (INV-05) |
| CITATION.cff:31 | date-released 2026-11-18 | yes |
| conda-recipe/recipe.yaml:5 | context version "2.3.0" | yes; sha256 for the 2.3.0 sdist (recipe.yaml:12-13 url/sha256) is unverified: dist/ holds only pyaermod-1.5.0 |
| CHANGELOG.md:10 | [2.3.0] - 2026-11-18 | yes |
| docs/release-notes/v2.3.0.md, mkdocs.yml:68 | v2.3.0 | yes |
| README.md:177, docs/index.md:61 | (version 2.2.0) | NO (INV-05) |
| docs/install.md:110 | "That is pyaermod 2.2.0" | intentional |
| CHANGELOG.md:8 | [Unreleased] | empty section, fine |

Tests enforce the first three: tests/test_citation.py:58-63 (CFF version and pyproject version equal __version__), tests/test_packaging.py:99-100 (recipe version equals pyproject version).

## Item 5: examples/ and benchmarks/ imports

### INV-12 [DOCS] [low] No import in examples/, benchmarks/, tests/, docs/, scripts/ or src/ names a missing pyaermod symbol
- 312 tracked .py and .ipynb files (code cells only) parsed with `ast`; every `from pyaermod[.x] import name` resolved by importing the editable install (venv, sourced from <repo>/src). Dotted `pyaermod.*` attribute references in examples/, benchmarks/, docs/ (65 unique) all resolve except `pyaermod.git` (a URL fragment, CONTRIBUTING.md:10, docs/install.md:116) and `pyaermod.gui_v2.state.AppState` (historical note, docs/release-notes/v2.2.0.md:140; CHANGELOG.md:2905), both intentional.
- 45 mkdocstrings `:::` directives in docs/api/*.md all resolve.
- Evidence: VERIFIED by script (repro/inv-stale/imports.py; dotted names by an inline importlib check).

## Additional observations
- mkdocs.yml: all 76 .md nav targets exist under docs/.
- Dockerfile:51 CMD uses `pyaermod-app --host 0.0.0.0 --port 8080 --no-browser`; the options exist (src/pyaermod/gui_v2/__init__.py:103, :113). Not run.
- Not examined: .10x/ (internal review tooling), CHANGELOG body beyond the grep hits, notebook outputs, webapp/ JS, test bodies beyond the skip and import checks, the EPA Fortran tree.

Scripts used (scratch only): <scratch>/repro/inv-stale/{paths.py,targeted.py,imports.py}
