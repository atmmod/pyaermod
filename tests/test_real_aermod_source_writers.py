"""The source writers' decks, run through a real AERMOD binary.

Skips unless ``aermod`` is on PATH (as tests/test_real_aermod.py does).
Each case is an acceptance check of the demonstration study's WP-D3:

* two OPENPIT sources in one group through their ``source_groups``: the
  writer used to put ``SRCGROUP`` among the source cards, and v26135
  stopped setup with ``SO E140`` (invalid order of keyword), and one
  naming group ``ALL`` wrote ``SRCGROUP ALL srcid``, ``SO E203``.

The met data are EPA's AERMET2 files in tests/fixtures/epa_official/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod import AERMODRunner
from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    ReceptorPathway,
    SourcePathway,
)

FIXT = Path(__file__).parent / "fixtures" / "epa_official"

pytestmark = pytest.mark.skipif(shutil.which("aermod") is None,
                                reason="AERMOD binary not found on PATH")


def _run(work: Path, name: str, sources: SourcePathway):
    for met in ("AERMET2.SFC", "AERMET2.PFL"):
        if not (work / met).exists():
            shutil.copy(FIXT / met, work / met)
    project = AERMODProject(
        control=ControlPathway(title_one=name, pollutant_id="PM10",
                               averaging_periods=["1", "PERIOD"]),
        sources=sources,
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
            grid_name="G1", x_init=-1500, x_num=16, x_delta=200,
            y_init=-1500, y_num=16, y_delta=200)]),
        meteorology=MeteorologyPathway(
            surface_file="AERMET2.SFC", profile_file="AERMET2.PFL",
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988, profile_base_elevation=0.0),
        output=OutputPathway(plot_file=f"{name}.plt", plot_file_averaging="PERIOD"),
    )
    project.write(work / f"{name}.inp")
    result = AERMODRunner(log_level="ERROR").run(str(work / f"{name}.inp"),
                                                 working_dir=str(work), timeout=300)
    return result, work / f"{name}.plt"


def _plot_rows(path: Path):
    return [ln.split()[:3] for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("*")]


def _codes(result):
    return {m.code for m in result.messages}


def _pit(**kw):
    return OpenPitSource("PIT", -300.0, -200.0, emission_rate=1e-5, x_dimension=600.0,
                         y_dimension=400.0, pit_volume=2.4e7, **kw)


def test_two_sources_grouped_by_source_groups_run(tmp_path):
    pit2 = OpenPitSource("PIT2", 500.0, 500.0, emission_rate=1e-5, x_dimension=200.0,
                         y_dimension=200.0, pit_volume=2e6, source_groups=["PITS"])
    result, _ = _run(tmp_path, "grp", SourcePathway(sources=[_pit(source_groups=["PITS"]), pit2]))
    assert result.success, result.error_message
    assert "E140" not in _codes(result)
    out = Path(result.output_file).read_text()
    assert any(ln.split()[:3] == ["PITS", "PIT", ","] and "PIT2" in ln for ln in out.splitlines())


def test_a_source_in_group_all_runs(tmp_path):
    """``source_groups=["ALL", ...]`` used to write ``SRCGROUP ALL PIT``,
    SO E203 even with one source."""
    result, _ = _run(tmp_path, "all", SourcePathway(sources=[_pit(source_groups=["ALL", "PITS"])]))
    assert result.success, result.error_message
    assert not {c for c in _codes(result) if c.startswith("E")}
