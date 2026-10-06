"""Tests for AERMETRunner + run_aermet_pipeline.

The success rule itself is pinned against recorded real AERMET runs in
tests/test_aermet_status.py; these tests cover the plumbing with small
fake binaries.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage3,
    AERMETStation,
    UpperAirStation,
)
from pyaermod.aermet_runner import (
    AERMETRunner,
    AERMETRunResult,
    run_aermet_pipeline,
)

# ---------------------------------------------------------------------------
# Fake-binary fixtures so tests don't need a real AERMET install
# ---------------------------------------------------------------------------

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the fake aermet binaries are bash scripts",
)


@pytest.fixture
def fake_aermet_exe(tmp_path):
    """A fake AERMET that logs the runstream it was given and prints AERMET's banner."""
    if platform.system() == "Windows":
        exe = tmp_path / "aermet.bat"
        exe.write_text("@echo off\necho  AERMET FINISHED SUCCESSFULLY\nexit /b 0\n")
    else:
        exe = tmp_path / "aermet"
        exe.write_text(
            "#!/bin/bash\n"
            "echo \"$1\" >> aermet.args\n"
            "echo ' AERMET FINISHED SUCCESSFULLY'\n"
            "exit 0\n"
        )
        exe.chmod(0o755)
    return exe


@pytest.fixture
def fake_failing_aermet(tmp_path):
    """A fake AERMET that fails the way AERMET does: exit code 0, unsuccessful banner."""
    exe = tmp_path / "aermet_fail"
    exe.write_text(
        "#!/bin/bash\n"
        "echo ' JOB        E01     CHECK_LINE INVALID KEYWORD: ANEMHGT LINE NUMBER:  17'\n"
        "echo ' AERMET FINISHED UN-SUCCESSFULLY'\n"
        "exit 0\n"
    )
    exe.chmod(0o755)
    return exe


def _stage1_config(tmp_path) -> AERMETStage1:
    """Build a minimal Stage 1 config pointing at temp-file placeholders."""
    surf = AERMETStation(
        station_id="12345", station_name="TEST",
        latitude=40.0, longitude=-95.0, time_zone=-6,
        anemometer_height=10.0, elevation=300.0,
    )
    ua = UpperAirStation(
        station_id="67890", station_name="TEST_UA",
        latitude=40.0, longitude=-95.0, elevation=300.0,
    )
    # Create placeholder data files
    sfc_data = tmp_path / "surface.isd"
    sfc_data.write_text("placeholder\n")
    ua_data = tmp_path / "upper.fsl"
    ua_data.write_text("placeholder\n")
    return AERMETStage1(
        job_id="TEST",
        surface_station=surf, surface_data_file=str(sfc_data),
        upper_air_station=ua, upper_air_data_file=str(ua_data),
        start_date="2020/01/01", end_date="2020/12/31",
    )


# ---------------------------------------------------------------------------
# Executable discovery
# ---------------------------------------------------------------------------

class TestExecutableLookup:
    def test_explicit_path_used(self, fake_aermet_exe):
        runner = AERMETRunner(executable_path=fake_aermet_exe)
        assert runner.executable == fake_aermet_exe

    def test_missing_path_raises(self):
        with pytest.raises(FileNotFoundError):
            AERMETRunner(executable_path="/nonexistent/aermet")


# ---------------------------------------------------------------------------
# Single-stage runs
# ---------------------------------------------------------------------------

@posix_only
class TestRunStage:
    def test_success_with_fake_exe(self, fake_aermet_exe, tmp_path):
        runner = AERMETRunner(executable_path=fake_aermet_exe)
        deck = tmp_path / "stage1.inp"
        deck.write_text("JOB\n   REPORT     s1.out\n   MESSAGES   s1.msg\n")
        result = runner.run_stage(1, deck, working_dir=tmp_path)
        assert result.success
        assert result.stage == 1
        assert result.return_code == 0
        assert "AERMET FINISHED SUCCESSFULLY" in (result.stdout or "")
        # The runstream is AERMET's argument, relative to its working directory.
        assert (tmp_path / "aermet.args").read_text() == "stage1.inp\n"
        assert isinstance(result, AERMETRunResult)
        # Files AERMET did not write are reported as absent, not guessed.
        assert result.report_file is None and result.message_file is None

    def test_deck_in_a_subdirectory_is_named_relative(self, fake_aermet_exe, tmp_path):
        deck = tmp_path / "decks" / "s1.inp"
        deck.parent.mkdir()
        deck.write_text("JOB\n")
        AERMETRunner(executable_path=fake_aermet_exe).run_stage(1, deck, working_dir=tmp_path)
        assert (tmp_path / "aermet.args").read_text() == "decks/s1.inp\n"

    def test_deck_name_too_long_for_aermet(self, fake_aermet_exe, tmp_path):
        deck = tmp_path / ("d" * 150) / ("e" * 150) / "s1.inp"
        deck.parent.mkdir(parents=True)
        deck.write_text("JOB\n")
        with pytest.raises(ValueError, match="up to 300 characters"):
            AERMETRunner(executable_path=fake_aermet_exe).run_stage(1, deck, working_dir=tmp_path)

    def test_failure_reported(self, fake_failing_aermet, tmp_path):
        runner = AERMETRunner(executable_path=fake_failing_aermet)
        deck = tmp_path / "s1.inp"
        deck.write_text("bad input\n")
        result = runner.run_stage(1, deck, working_dir=tmp_path)
        assert not result.success
        assert result.return_code == 0
        assert result.errors[0].code == "E01"
        assert result.error_message.startswith("JOB E01 CHECK_LINE: INVALID KEYWORD: ANEMHGT")

    def test_timeout(self, tmp_path):
        exe = tmp_path / "aermet_slow"
        exe.write_text("#!/bin/bash\nsleep 5\n")
        exe.chmod(0o755)
        deck = tmp_path / "s1.inp"
        deck.write_text("JOB\n")
        result = AERMETRunner(executable_path=exe).run_stage(1, deck, working_dir=tmp_path, timeout=1)
        assert not result.success
        assert result.return_code is None
        assert "timed out after 1s" in result.error_message

    def test_new_file_with_an_mtime_before_the_run_is_listed(self, tmp_path):
        # Linux stamps files from a coarse kernel clock, so a file written a
        # few ms after ``datetime.now()`` can carry an earlier mtime; a file
        # stamped in the past (``touch -t``) is the same case made deterministic.
        exe = tmp_path / "aermet_backdated"
        exe.write_text(
            "#!/bin/bash\n"
            "touch -t 200001010000 TEST.SFC\n"
            "echo ' AERMET FINISHED SUCCESSFULLY'\n"
            "exit 0\n"
        )
        exe.chmod(0o755)
        deck = tmp_path / "s1.inp"
        deck.write_text("JOB\n")
        result = AERMETRunner(executable_path=exe).run_stage(1, deck, working_dir=tmp_path)
        assert result.success
        assert any(p.endswith("TEST.SFC") for p in result.output_files)


# ---------------------------------------------------------------------------
# The pipeline: Stage 1, then METPREP
# ---------------------------------------------------------------------------

@posix_only
class TestPipeline:
    def test_pipeline_runs_stage1_then_metprep(self, fake_aermet_exe, tmp_path):
        s1 = _stage1_config(tmp_path)
        s3 = AERMETStage3(nws_height=10, start_date="2020/01/01", end_date="2020/12/31")
        results = run_aermet_pipeline(
            s1, None, s3,
            working_dir=tmp_path,
            executable_path=fake_aermet_exe,
        )
        assert [r.stage for r in results] == [1, 3]
        assert all(r.success for r in results)
        assert (tmp_path / "stage1.inp").exists()
        assert (tmp_path / "stage3.inp").exists()
        assert not (tmp_path / "stage2.inp").exists()
        # METPREP reads the QAOUT files Stage 1 wrote.
        metprep = (tmp_path / "stage3.inp").read_text()
        assert "QAOUT      stage1_ua.qa" in metprep
        assert "QAOUT      stage1.qa" in metprep

    def test_stop_on_failure_skips_remaining(self, fake_failing_aermet, tmp_path):
        results = run_aermet_pipeline(
            _stage1_config(tmp_path), None, AERMETStage3(nws_height=10),
            working_dir=tmp_path,
            executable_path=fake_failing_aermet,
            stop_on_failure=True,
        )
        assert len(results) == 1
        assert not results[0].success

    def test_continue_on_failure_runs_all(self, fake_failing_aermet, tmp_path):
        results = run_aermet_pipeline(
            _stage1_config(tmp_path), None, AERMETStage3(nws_height=10),
            working_dir=tmp_path,
            executable_path=fake_failing_aermet,
            stop_on_failure=False,
        )
        assert len(results) == 2
        assert not any(r.success for r in results)


# ---------------------------------------------------------------------------
# Stage deck content smoke tests (these exercise .to_aermet_input())
# ---------------------------------------------------------------------------

class TestStageDecks:
    def test_stage1_deck_has_job_pathway(self, tmp_path):
        s1 = _stage1_config(tmp_path)
        lines = [line.strip() for line in s1.to_aermet_input().splitlines()]
        assert "JOB" in lines
        assert "UPPERAIR" in lines
        assert "SURFACE" in lines
