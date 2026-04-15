"""Tests for AERMETRunner + run_aermet_pipeline."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage2,
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

@pytest.fixture
def fake_aermet_exe(tmp_path):
    """Create a fake AERMET binary that echoes its stdin and exits 0."""
    if platform.system() == "Windows":
        exe = tmp_path / "aermet.bat"
        exe.write_text("@echo off\nexit /b 0\n")
    else:
        exe = tmp_path / "aermet"
        # Copy stdin to a log file so the runner has something to find.
        exe.write_text(
            "#!/bin/bash\n"
            "cat > aermet.log\n"
            "echo 'AERMET completed successfully'\n"
            "exit 0\n"
        )
        exe.chmod(0o755)
    return exe


@pytest.fixture
def fake_failing_aermet(tmp_path):
    """Fake AERMET that exits non-zero."""
    exe = tmp_path / "aermet_fail"
    exe.write_text("#!/bin/bash\necho 'FATAL ERROR: bad inputs'\nexit 2\n")
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
        latitude=40.0, longitude=-95.0,
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

class TestRunStage:
    def test_success_with_fake_exe(self, fake_aermet_exe, tmp_path):
        runner = AERMETRunner(executable_path=fake_aermet_exe)
        deck = tmp_path / "stage1.inp"
        deck.write_text("JOB\n  MESSAGES 2 out.msg\n")
        result = runner.run_stage(1, deck, working_dir=tmp_path)
        assert result.success
        assert result.stage == 1
        assert result.return_code == 0
        assert "completed successfully" in (result.stdout or "")

    def test_failure_reported(self, fake_failing_aermet, tmp_path):
        runner = AERMETRunner(executable_path=fake_failing_aermet)
        deck = tmp_path / "s1.inp"
        deck.write_text("bad input\n")
        result = runner.run_stage(1, deck, working_dir=tmp_path)
        assert not result.success
        assert result.return_code == 2
        assert "FATAL" in (result.stdout or "")


# ---------------------------------------------------------------------------
# Full three-stage pipeline
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_pipeline_runs_all_three_stages(self, fake_aermet_exe, tmp_path):
        s1 = _stage1_config(tmp_path)
        s2 = AERMETStage2(
            surface_extract="stage1.ext",
            start_date="2020/01/01", end_date="2020/12/31",
        )
        s3 = AERMETStage3(
            merge_file="stage2.mrg",
            start_date="2020/01/01", end_date="2020/12/31",
        )
        results = run_aermet_pipeline(
            s1, s2, s3,
            working_dir=tmp_path,
            executable_path=fake_aermet_exe,
        )
        assert len(results) == 3
        assert all(r.success for r in results)
        # Each stage writes its own deck
        for n in (1, 2, 3):
            assert (tmp_path / f"stage{n}.inp").exists()

    def test_stop_on_failure_skips_remaining(self, fake_failing_aermet, tmp_path):
        s1 = _stage1_config(tmp_path)
        s2 = AERMETStage2()
        s3 = AERMETStage3()
        results = run_aermet_pipeline(
            s1, s2, s3,
            working_dir=tmp_path,
            executable_path=fake_failing_aermet,
            stop_on_failure=True,
        )
        assert len(results) == 1
        assert not results[0].success

    def test_continue_on_failure_runs_all(self, fake_failing_aermet, tmp_path):
        s1 = _stage1_config(tmp_path)
        s2 = AERMETStage2()
        s3 = AERMETStage3()
        results = run_aermet_pipeline(
            s1, s2, s3,
            working_dir=tmp_path,
            executable_path=fake_failing_aermet,
            stop_on_failure=False,
        )
        assert len(results) == 3
        assert not any(r.success for r in results)


# ---------------------------------------------------------------------------
# Stage deck content smoke tests (these exercise .to_aermet_input())
# ---------------------------------------------------------------------------

class TestStageDecks:
    def test_stage1_deck_has_job_pathway(self, tmp_path):
        s1 = _stage1_config(tmp_path)
        text = s1.to_aermet_input()
        assert "JOB" in text
        assert "UPPERAIR" in text
        assert "SURFACE" in text

    def test_stage2_deck_has_merge(self):
        s2 = AERMETStage2(
            surface_extract="stage1.ext",
            start_date="2020/01/01", end_date="2020/12/31",
        )
        text = s2.to_aermet_input()
        assert "MERGE" in text
