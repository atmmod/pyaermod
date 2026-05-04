"""Tests for the AERSCREEN binary runner."""

from __future__ import annotations

import os
import stat

import pytest

from pyaermod import AERSCREENConfig, AERSCREENRunner, AERSCREENSourceType


@pytest.fixture
def cfg():
    return AERSCREENConfig(
        title="UnitTest",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=5.0,
        stack_height=10.0,
        stack_diameter=1.0,
        stack_temp=400.0,
        exit_velocity=10.0,
    )


def _fake_aerscreen(tmp_path, *, exit_code=0, stdout="OK\n",
                    stderr="", touch=()):
    fake = tmp_path / "fake_aerscreen"
    touch_block = "\n".join(f"touch {f}" for f in touch)
    fake.write_text(
        "#!/bin/bash\n"
        f"{touch_block}\n"
        f'echo -n {stdout!r}\n'
        f'echo -n {stderr!r} >&2\n'
        f"exit {exit_code}\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return fake


class TestExecutableDiscovery:
    def test_explicit_path_must_exist(self):
        with pytest.raises(FileNotFoundError):
            AERSCREENRunner(executable_path="/nonexistent/aerscreen")

    def test_path_search_raises_when_missing(self, monkeypatch):
        monkeypatch.setattr(os, "environ", {"PATH": "/nonexistent"})
        with pytest.raises(FileNotFoundError, match="No AERSCREEN executable"):
            AERSCREENRunner()

    def test_explicit_path_used(self, tmp_path):
        fake = _fake_aerscreen(tmp_path)
        runner = AERSCREENRunner(executable_path=fake)
        assert runner.executable == fake


class TestRun:
    def test_successful_run_writes_deck(self, tmp_path, cfg):
        fake = _fake_aerscreen(tmp_path)
        runner = AERSCREENRunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert result.success
        assert (work / "aerscreen.inp").exists()
        deck_text = (work / "aerscreen.inp").read_text()
        assert "TITLE: UnitTest" in deck_text
        assert "SOURCE_TYPE: POINT" in deck_text

    def test_nonzero_exit_marks_failure(self, tmp_path, cfg):
        fake = _fake_aerscreen(tmp_path, exit_code=1)
        runner = AERSCREENRunner(executable_path=fake)
        result = runner.run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert not result.success
        assert result.return_code == 1

    def test_fatal_in_stdout_marks_failure(self, tmp_path, cfg):
        fake = _fake_aerscreen(
            tmp_path, exit_code=0,
            stdout="setup ok ... FATAL ERROR: bad params\n",
        )
        runner = AERSCREENRunner(executable_path=fake)
        result = runner.run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert not result.success
        assert "FATAL" in (result.stdout or "")

    def test_run_lists_produced_files(self, tmp_path, cfg):
        fake = _fake_aerscreen(
            tmp_path, exit_code=0,
            touch=("aerscreen.out", "screen.pst"),
        )
        runner = AERSCREENRunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert result.success
        names = [os.path.basename(p) for p in result.output_files]
        assert "aerscreen.out" in names
        assert "screen.pst" in names

    def test_stdout_stderr_captured(self, tmp_path, cfg):
        fake = _fake_aerscreen(
            tmp_path, stdout="processed\n", stderr="warning: ignored\n",
        )
        runner = AERSCREENRunner(executable_path=fake)
        result = runner.run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert "processed" in result.stdout
        assert "warning: ignored" in result.stderr
