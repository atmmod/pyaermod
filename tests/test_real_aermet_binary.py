"""
End-to-end smoke test against the real AERMET binary.

Skips if ``aermet`` isn't on PATH. Parallel to test_real_aermod.py
and test_real_aermap.py (which test AERMOD / AERMAP binaries).

Companion to test_real_aermet.py, which tests .SFC / .PFL parsers
against vendored AERMET output files. This file tests the *runner
dispatch* — that a Python-generated Stage 1 deck is ingested by the
real Fortran binary without the pyaermod wrapper hanging or crashing.

Why we don't require a successful Stage 1 run: AERMET needs real
ISHD surface + FSL upper-air files to produce valid output, and
vendoring real met data isn't feasible in CI. The placeholder input
will be rejected by AERMET's data parser, which is expected — we
only assert the wrapper returned a concrete AERMETRunResult.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod.aermet import AERMETStage1, AERMETStation, UpperAirStation
from pyaermod.aermet_runner import AERMETRunner, run_aermet_pipeline

pytestmark = pytest.mark.skipif(
    shutil.which("aermet") is None,
    reason="AERMET binary not found on PATH",
)


def _minimal_stage1(tmp_path: Path) -> AERMETStage1:
    sfc = tmp_path / "surface.isd"
    sfc.write_text("placeholder\n")
    ua = tmp_path / "upper.fsl"
    ua.write_text("placeholder\n")
    return AERMETStage1(
        job_id="SMOKE",
        surface_station=AERMETStation(
            station_id="94847", station_name="TEST_SFC",
            latitude=42.36, longitude=-71.01, time_zone=-5,
            anemometer_height=10.0, elevation=20.0,
        ),
        surface_data_file=str(sfc),
        upper_air_station=UpperAirStation(
            station_id="74494", station_name="TEST_UA",
            latitude=42.36, longitude=-71.01,
        ),
        upper_air_data_file=str(ua),
        start_date="2020/01/01",
        end_date="2020/01/02",
    )


def test_aermet_runner_executable_introspection():
    """Runner finds the binary and exposes its path."""
    runner = AERMETRunner()
    assert runner.executable is not None
    assert runner.executable.exists()


def test_aermet_binary_runs_stage1(tmp_path):
    """A Stage 1 deck targeting placeholder inputs must dispatch to
    AERMET. The run itself will likely fail (placeholder data isn't
    valid ISHD/FSL) but the wrapper must return a concrete result."""
    stage1 = _minimal_stage1(tmp_path)
    deck_path = tmp_path / "stage1.inp"
    deck_path.write_text(stage1.to_aermet_input(), encoding="utf-8")

    runner = AERMETRunner()
    result = runner.run_stage(1, deck_path, working_dir=tmp_path, timeout=60)

    assert result is not None
    assert result.stage == 1
    assert result.input_file == str(deck_path)
    # Runner must report a concrete return code (0 or non-zero); not
    # None, which would mean timeout.
    assert result.return_code is not None


def test_aermet_pipeline_dispatches_all_three_stages(tmp_path):
    """run_aermet_pipeline writes each stage's deck + dispatches."""
    from pyaermod.aermet import AERMETStage2, AERMETStage3

    stage1 = _minimal_stage1(tmp_path)
    stage2 = AERMETStage2(
        surface_extract="stage1.ext",
        start_date="2020/01/01",
        end_date="2020/01/02",
    )
    stage3 = AERMETStage3(
        merge_file="stage2.mrg",
        start_date="2020/01/01",
        end_date="2020/01/02",
    )
    results = run_aermet_pipeline(
        stage1, stage2, stage3,
        working_dir=tmp_path,
        stop_on_failure=False,  # don't abort on placeholder-data failures
        timeout=60,
    )
    assert len(results) == 3
    for n in (1, 2, 3):
        assert (tmp_path / f"stage{n}.inp").exists()
