"""Tests for the AERSURFACE binary runner."""

from __future__ import annotations

import os
import stat

import pytest

from pyaermod import AERSURFACEConfig, AERSURFACERunner


@pytest.fixture
def cfg(tmp_path):
    nlcd = tmp_path / "stub.img"
    nlcd.write_bytes(b"placeholder")
    return AERSURFACEConfig(
        title="UnitTest",
        site_id="UTEST",
        latitude=44.0,
        longitude=-123.0,
        land_cover_file=str(nlcd),
        nlcd_year=2019,
    )


def _fake_aersurface(tmp_path, *, exit_code=0, stdout="OK\n", stderr=""):
    """Create a fake aersurface binary on disk that emits the given streams."""
    fake = tmp_path / "fake_aersurface"
    fake.write_text(
        f'#!/bin/bash\necho -n {stdout!r}\necho -n {stderr!r} >&2\nexit {exit_code}\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return fake


class TestExecutableDiscovery:
    def test_explicit_executable_path(self, tmp_path):
        fake = _fake_aersurface(tmp_path)
        runner = AERSURFACERunner(executable_path=fake)
        assert runner.executable == fake

    def test_explicit_path_must_exist(self):
        with pytest.raises(FileNotFoundError):
            AERSURFACERunner(executable_path="/nonexistent/aersurface")

    def test_path_search_raises_when_missing(self, monkeypatch):
        monkeypatch.setattr(os, "environ", {"PATH": "/nonexistent"})
        with pytest.raises(FileNotFoundError, match="No AERSURFACE executable"):
            AERSURFACERunner()


class TestRun:
    def test_successful_run_writes_deck(self, tmp_path, cfg):
        fake = _fake_aersurface(tmp_path)
        runner = AERSURFACERunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert result.success
        assert result.return_code == 0
        # Deck staged at the expected location.
        assert (work / "aersurface.inp").exists()
        deck_text = (work / "aersurface.inp").read_text()
        assert "TITLEONE  UnitTest" in deck_text

    def test_nonzero_exit_marks_failure(self, tmp_path, cfg):
        fake = _fake_aersurface(tmp_path, exit_code=1, stdout="bad\n")
        runner = AERSURFACERunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert not result.success
        assert result.return_code == 1

    def test_fatal_in_stdout_marks_failure(self, tmp_path, cfg):
        fake = _fake_aersurface(
            tmp_path, exit_code=0,
            stdout="WARNING ... FATAL ERROR: NLCD missing\n",
        )
        runner = AERSURFACERunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert not result.success
        assert "FATAL" in (result.stdout or "")

    def test_run_captures_stdout_stderr(self, tmp_path, cfg):
        fake = _fake_aersurface(
            tmp_path, exit_code=0,
            stdout="processed 12 months\n",
            stderr="info: 1 sector\n",
        )
        runner = AERSURFACERunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert "processed 12 months" in result.stdout
        assert "info: 1 sector" in result.stderr

    def test_output_files_listed(self, tmp_path, cfg):
        # Fake binary that creates a .sfc output file.
        fake = tmp_path / "fake_aersurface"
        fake.write_text(
            "#!/bin/bash\n"
            "touch UTEST.SFC\n"
            "echo done\n"
            "exit 0\n"
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        runner = AERSURFACERunner(executable_path=fake)
        work = tmp_path / "wd"
        result = runner.run(cfg, working_dir=work, timeout=10)
        assert result.success
        assert any(p.endswith("UTEST.SFC") for p in result.output_files)
