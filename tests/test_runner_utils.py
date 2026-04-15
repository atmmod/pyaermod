"""Tests for runner_utils."""

from __future__ import annotations

import json
import logging

import pytest

from pyaermod.runner_utils import (
    HAS_TQDM,
    LoggingProgress,
    NoOpProgress,
    RunManifest,
    RunManifestEntry,
    TqdmProgress,
    extract_errmsg,
    generate_slurm_script,
    resume_batch,
    summarize_failure,
    tail_output,
)


# ---------------------------------------------------------------------------
# ERRMSG / failure summary
# ---------------------------------------------------------------------------

class TestErrMsg:
    def test_missing_file_returns_none(self, tmp_path):
        assert extract_errmsg(tmp_path / "nope") is None

    def test_parses_messages_and_codes(self, tmp_path):
        p = tmp_path / "ERRMSG.TMP"
        p.write_text("E101 ** FATAL ** missing met file\nE202 warning\n\n")
        info = extract_errmsg(p)
        assert info is not None
        assert "E101" in info.error_codes
        assert "E202" in info.error_codes
        assert info.has_fatal

    def test_tail_output(self, tmp_path):
        p = tmp_path / "run.out"
        p.write_text("\n".join(f"line{i}" for i in range(50)))
        tail = tail_output(p, n_lines=5)
        assert tail[-1] == "line49" and len(tail) == 5


class TestSummarizeFailure:
    def test_combines_errmsg_and_out(self, tmp_path):
        (tmp_path / "ERRMSG.TMP").write_text("E123 fatal\n")
        (tmp_path / "run.out").write_text("ok\nE999 ** FATAL ** bad\nbye\n")
        summary = summarize_failure("run.inp", tmp_path)
        assert "E123" in summary or "fatal" in summary.lower()
        assert "bye" in summary


# ---------------------------------------------------------------------------
# Progress reporters
# ---------------------------------------------------------------------------

class TestProgress:
    def test_noop_progress_smoke(self):
        p = NoOpProgress()
        p.start(10, "x"); p.update(1); p.finish()

    def test_logging_progress_emits_info(self, caplog):
        p = LoggingProgress(logger=logging.getLogger("testprogress"))
        with caplog.at_level(logging.INFO, logger="testprogress"):
            p.start(3, "run")
            p.update(1)
            p.update(2)
            p.finish()
        msgs = [r.message for r in caplog.records]
        assert any("0/3" in m for m in msgs)
        assert any("3/3" in m for m in msgs)

    @pytest.mark.skipif(not HAS_TQDM, reason="tqdm not installed")
    def test_tqdm_progress_runs(self):
        p = TqdmProgress()
        p.start(5, "x"); p.update(2, "halfway"); p.finish()


# ---------------------------------------------------------------------------
# Resume batch
# ---------------------------------------------------------------------------

class TestResumeBatch:
    def test_no_outputs_all_todo(self, tmp_path):
        inp1 = tmp_path / "a.inp"; inp1.touch()
        inp2 = tmp_path / "b.inp"; inp2.touch()
        split = resume_batch([inp1, inp2], tmp_path / "out")
        assert split["done"] == [] and len(split["todo"]) == 2

    def test_existing_success_marker_moves_to_done(self, tmp_path):
        inp = tmp_path / "a.inp"; inp.touch()
        out_dir = tmp_path / "out"; out_dir.mkdir()
        (out_dir / "a.out").write_text("stuff\nAERMOD FINISHES SUCCESSFULLY\n")
        split = resume_batch([inp], out_dir)
        assert split["done"] == [inp] and split["todo"] == []

    def test_output_without_marker_still_todo(self, tmp_path):
        inp = tmp_path / "a.inp"; inp.touch()
        out_dir = tmp_path / "out"; out_dir.mkdir()
        (out_dir / "a.out").write_text("incomplete run")
        split = resume_batch([inp], out_dir)
        assert split["todo"] == [inp]


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

class TestRunManifest:
    def test_mark_and_save(self, tmp_path):
        m = RunManifest.load(tmp_path / "m.json")
        m.mark("a.inp", "success", runtime_seconds=12.3)
        m.mark("b.inp", "failed", error_message="timeout")
        loaded = RunManifest.load(tmp_path / "m.json")
        assert loaded.entries["a.inp"].status == "success"
        assert loaded.entries["b.inp"].error_message == "timeout"

    def test_summary_counts(self, tmp_path):
        m = RunManifest.load(tmp_path / "m.json")
        m.mark("1", "success"); m.mark("2", "success"); m.mark("3", "failed")
        s = m.summary()
        assert s["success"] == 2 and s["failed"] == 1

    def test_pending_list(self, tmp_path):
        m = RunManifest.load(tmp_path / "m.json")
        m.mark("a", "success"); m.mark("b", "failed"); m.mark("c", "pending")
        assert set(m.pending()) == {"b", "c"}


# ---------------------------------------------------------------------------
# SLURM script
# ---------------------------------------------------------------------------

class TestSlurm:
    def test_generates_script_and_list(self, tmp_path):
        inputs = [tmp_path / f"run_{i}.inp" for i in range(3)]
        for p in inputs: p.touch()
        script = generate_slurm_script(
            inputs,
            output_dir=tmp_path / "out",
            script_path=tmp_path / "submit.sh",
            input_list_path=tmp_path / "inputs.lst",
            max_concurrent=2,
        )
        text = script.read_text()
        assert "#SBATCH --array=0-2%2" in text
        assert "aermod" in text
        # List file has 3 lines, one per input
        lst = (tmp_path / "inputs.lst").read_text().splitlines()
        assert len(lst) == 3

    def test_empty_inputs_raises(self, tmp_path):
        with pytest.raises(ValueError):
            generate_slurm_script(
                [], output_dir=tmp_path,
                script_path=tmp_path / "s.sh",
                input_list_path=tmp_path / "l",
            )
