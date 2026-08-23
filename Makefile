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

.PHONY: help install install-full test test-full lint typecheck benchmark clean

help:
	@echo "make test        - core suite (-m 'not slow', coverage per pytest.ini)"
	@echo "make test-full   - pip install -e '.[dev,all]' then the full suite incl. slow tests"
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

lint:
	$(PYTHON) -m ruff check src/ tests/

typecheck:
	$(PIP) install --quiet "mypy==$(MYPY_VERSION)"
	$(PYTHON) scripts/mypy_gate.py

benchmark:
	$(PYTHON) benchmarks/run_benchmarks.py --output benchmark_results.json

clean:
	rm -rf .pytest_cache .mypy_cache .hypothesis htmlcov coverage.xml .coverage build dist
