# Developer shortcuts. These mirror what CI runs (.github/workflows/tests.yml);
# if you change a command here, change it there too.
#
#   make test        core suite with whatever extras are installed
#   make test-full   install `.[dev,all]` (needs GDAL, see CONTRIBUTING.md)
#                    then run the whole suite, slow tests included, with coverage
#   make lint        ruff check src/ tests/
#   make typecheck   mypy ratchet gate (scripts/mypy_gate.py vs mypy-baseline.txt)

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip
# Same pin as .github/workflows/tests.yml so local and CI mypy counts agree
# (mypy-baseline.txt is authoritative for the `.[dev,all]` environment).
MYPY_VERSION ?= 2.3.1

.PHONY: help install install-full test test-full test-binaries lint typecheck benchmark clean

help:
	@echo "make test        - core suite (-m 'not slow', coverage per pytest.ini)"
	@echo "make test-full   - pip install -e '.[dev,all]' then the full suite incl. slow tests"
	@echo "make test-binaries - full suite with ./bin on PATH (real EPA binaries)"
	@echo "make lint        - ruff check src/ tests/"
	@echo "make typecheck   - mypy ratchet gate (fails only if the error count grows)"
	@echo "make benchmark   - benchmarks/run_benchmarks.py -> benchmark_results.json"
	@echo "make clean       - remove caches and coverage artifacts"

install:
	$(PIP) install -e ".[dev]"

install-full:
	$(PIP) install -e ".[dev,all]"

test:
	$(PYTHON) -m pytest -q -p no:cacheprovider

test-full: install-full
	$(PYTHON) -m pytest -o addopts="" -q -p no:cacheprovider --strict-markers --tb=short \
	    --cov=pyaermod --cov-config=.coveragerc --cov-report=term-missing:skip-covered

# Everything test-full runs, plus the tests that need a real EPA binary
# (the EPA parity suite, the bit-exact AERTEST regression, the CLI run
# smoke tests). Those SKIP silently when nothing named `aermod` is on
# PATH, so a green `make test-full` says nothing about them -- build the
# binaries first with `scripts/build_aermod.sh` and use this target,
# which puts ./bin on PATH for you.
test-binaries: install-full
	@test -x bin/aermod || { \
	    echo "bin/aermod not found -- run scripts/build_aermod.sh first"; \
	    exit 1; \
	}
	PATH="$(CURDIR)/bin:$$PATH" $(PYTHON) -m pytest -o addopts="" -q \
	    -p no:cacheprovider --strict-markers --tb=short

lint:
	$(PYTHON) -m ruff check src/ tests/

# The install is skipped when the pinned mypy is already there, so a local
# `make typecheck` costs no network round-trip. `mypy --version` prints
# "mypy 2.3.1 (compiled: yes)", hence the two patterns; a missing mypy makes
# the command fail and the empty output falls through to the install. This is
# the one place the Makefile deliberately differs from tests.yml: the CI
# runner has no mypy (it is not in the [dev] extra), so the guard would never
# hit there and the end state is the same either way.
typecheck:
	@case "$$($(PYTHON) -m mypy --version 2>/dev/null)" in \
	    "mypy $(MYPY_VERSION)"|"mypy $(MYPY_VERSION) "*) ;; \
	    *) $(PIP) install --quiet "mypy==$(MYPY_VERSION)" ;; \
	esac
	$(PYTHON) scripts/mypy_gate.py

benchmark:
	$(PYTHON) benchmarks/run_benchmarks.py --output benchmark_results.json

clean:
	rm -rf .pytest_cache .mypy_cache .hypothesis htmlcov coverage.xml .coverage build dist
