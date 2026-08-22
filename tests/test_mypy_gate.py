"""Unit tests for scripts/mypy_gate.py (no mypy invocation needed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
GATE = REPO / "scripts" / "mypy_gate.py"
BASELINE = REPO / "mypy-baseline.txt"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("mypy_gate", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLE = """\
src/pyaermod/a.py:10: error: Incompatible return value type  [return-value]
src/pyaermod/a.py:12: note: See https://mypy.rtfd.io
src/pyaermod/b.py:3:5: error: Name "x" is not defined  [name-defined]
Found 2 errors in 2 files (checked 53 source files)
"""


class TestCountErrors:
    def test_counts_error_lines_not_notes(self, gate):
        assert gate.count_errors(SAMPLE) == 2

    def test_zero_on_success(self, gate):
        assert gate.count_errors("Success: no issues found in 53 source files\n") == 0

    def test_works_without_summary_line(self, gate):
        body = "\n".join(SAMPLE.splitlines()[:-1])
        assert gate.count_errors(body) == 2

    def test_trusts_larger_summary_figure(self, gate):
        # If mypy suppresses duplicate lines, the summary is authoritative.
        text = "src/x.py:1: error: boom  [misc]\nFound 3 errors in 1 file (checked 1 source file)\n"
        assert gate.count_errors(text) == 3


class TestEvaluate:
    def test_increase_fails(self, gate):
        code, msg = gate.evaluate(76, 75)
        assert code == 1 and "+1" in msg

    def test_equal_passes(self, gate):
        code, _ = gate.evaluate(75, 75)
        assert code == 0

    def test_decrease_passes_and_suggests_update(self, gate):
        code, msg = gate.evaluate(70, 75)
        assert code == 0 and "--update" in msg


class TestBaselineFile:
    def test_committed_baseline_is_a_single_integer(self, gate):
        assert BASELINE.exists(), "mypy-baseline.txt must be committed at the repo root"
        assert gate.read_baseline(BASELINE) >= 0

    def test_read_baseline_rejects_garbage(self, gate, tmp_path):
        bad = tmp_path / "b.txt"
        bad.write_text("seventy-five\n")
        with pytest.raises(SystemExit):
            gate.read_baseline(bad)


class TestCliPaths:
    """Drive main() with a stubbed mypy so the CLI paths run without mypy."""

    def _stub(self, gate, monkeypatch, text: str):
        monkeypatch.setattr(gate, "run_mypy", lambda extra: (1 if "error:" in text else 0, text))

    def test_update_writes_baseline(self, gate, monkeypatch, tmp_path, capsys):
        self._stub(gate, monkeypatch, SAMPLE)
        target = tmp_path / "base.txt"
        assert gate.main(["--update", "--baseline-file", str(target), "--quiet"]) == 0
        assert target.read_text().strip() == "2"

    def test_gate_fails_on_increase(self, gate, monkeypatch, tmp_path):
        self._stub(gate, monkeypatch, SAMPLE)
        target = tmp_path / "base.txt"
        target.write_text("1\n")
        assert gate.main(["--baseline-file", str(target), "--quiet"]) == 1

    def test_gate_passes_on_equal_or_lower(self, gate, monkeypatch, tmp_path):
        self._stub(gate, monkeypatch, SAMPLE)
        target = tmp_path / "base.txt"
        target.write_text("2\n")
        assert gate.main(["--baseline-file", str(target), "--quiet"]) == 0
        target.write_text("5\n")
        assert gate.main(["--baseline-file", str(target), "--quiet"]) == 0

    def test_missing_baseline_file_fails_with_hint(self, gate, monkeypatch, tmp_path, capsys):
        self._stub(gate, monkeypatch, SAMPLE)
        assert gate.main(["--baseline-file", str(tmp_path / "nope.txt"), "--quiet"]) == 1
        assert "--update" in capsys.readouterr().out

    def test_mypy_crash_propagates(self, gate, monkeypatch, tmp_path):
        monkeypatch.setattr(gate, "run_mypy", lambda extra: (2, "mypy: error: bad usage\n"))
        target = tmp_path / "base.txt"
        target.write_text("0\n")
        assert gate.main(["--baseline-file", str(target)]) == 2
