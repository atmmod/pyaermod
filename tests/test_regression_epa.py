"""
EPA-style regression tests.

These pin down pyaermod's externally visible behavior so refactors
don't silently change input-file output or parser behavior:

1. `simple_point.inp.expected` — golden input file.  We build the same
   project programmatically, write it to a temp file, and diff against
   the golden.  Any intentional format change requires regenerating
   the golden.
2. `sample_plotfile.plt` / `sample_maxifile.max` — hand-crafted
   AERMOD-output samples parsed by aermod_outputs, with asserted
   header metadata and row counts.
3. Regulatory check: the golden project must pass
   EPA_APPENDIX_W_2017.check() with zero warnings.
4. Advanced validator: the golden project must have no errors.

Fixtures live under tests/fixtures/epa_style/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import (
    EPA_APPENDIX_W_2017,
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    advanced_validate,
    read_maxifile,
    read_plotfile,
)
from pyaermod.validator import Validator

FIXT = Path(__file__).parent / "fixtures" / "epa_style"


def _canonical_project() -> AERMODProject:
    """Build the project whose text should match simple_point.inp.expected."""
    ctrl = ControlPathway(
        title_one="Regression case: single SO2 point source",
        title_two="AERMOD v23132 regulatory default",
        pollutant_id=PollutantType.SO2,
        averaging_periods=["1", "24", "ANNUAL"],
        terrain_type=TerrainType.ELEVATED,
        regulatory_default=True,
    )
    src = PointSource(
        source_id="STACK1",
        x_coord=0.0, y_coord=0.0,
        stack_height=60.0,
        stack_temp=455.37,
        exit_velocity=12.0,
        stack_diameter=2.0,
        emission_rate=5.0,
    )
    grid = CartesianGrid(
        grid_name="POLGRID",
        x_init=-2000.0, x_num=21, x_delta=200.0,
        y_init=-2000.0, y_num=21, y_delta=200.0,
    )
    met = MeteorologyPathway(
        surface_file="stn.sfc", profile_file="stn.pfl",
        surface_station_id=94847, upper_air_station_id=94847,
        data_start_year=2020,
        profile_base_elevation=265.0,
        start_year=2020, start_month=1, start_day=1,
        end_year=2020, end_month=12, end_day=31,
    )
    out = OutputPathway(receptor_table=True, max_table=True)
    return AERMODProject(
        control=ctrl,
        sources=SourcePathway(sources=[src]),
        receptors=ReceptorPathway(cartesian_grids=[grid]),
        meteorology=met,
        output=out,
    )


# ---------------------------------------------------------------------------
# Golden-file diff
# ---------------------------------------------------------------------------

class TestGoldenInputFile:
    def test_generated_matches_golden(self, tmp_path):
        expected = (FIXT / "simple_point.inp.expected").read_text()
        project = _canonical_project()
        out_path = tmp_path / "gen.inp"
        project.write(str(out_path))
        actual = out_path.read_text()
        assert actual == expected, (
            "Generated input file diverged from golden. If this is "
            "intentional, regenerate tests/fixtures/epa_style/"
            "simple_point.inp.expected and review the diff in the PR."
        )


# ---------------------------------------------------------------------------
# Validation — project must pass base + advanced + regulatory
# ---------------------------------------------------------------------------

class TestGoldenProjectPasses:
    def test_base_validator_no_errors(self):
        project = _canonical_project()
        result = Validator.validate(project)
        assert result.is_valid, f"base validator errors: {result.errors}"

    def test_advanced_validator_no_errors(self):
        project = _canonical_project()
        findings = advanced_validate(project)
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, f"advanced_validate errors: {errors}"

    def test_epa_profile_check_clean(self):
        project = _canonical_project()
        warnings = EPA_APPENDIX_W_2017.check(project)
        assert warnings == [], f"profile warnings: {warnings}"


# ---------------------------------------------------------------------------
# Auxiliary output parser round-trip
# ---------------------------------------------------------------------------

class TestAuxFileRegression:
    def test_plotfile_structure(self):
        res = read_plotfile(FIXT / "sample_plotfile.plt")
        assert res.header.file_type == "PLOTFILE"
        assert res.header.averaging_period == "ANNUAL"
        assert res.header.source_group == "ALL"
        assert res.header.model_version == "23132"
        assert res.n_records == 5
        # Spot-check a known row
        peak = max(res.records, key=lambda r: r["CONC"])
        assert peak["CONC"] == pytest.approx(0.523)
        assert peak["X"] == pytest.approx(1000.0)

    def test_maxifile_structure(self):
        res = read_maxifile(FIXT / "sample_maxifile.max")
        assert res.header.file_type == "MAXIFILE"
        assert res.header.averaging_period == "24-HR"
        assert res.header.rank == 1
        assert res.n_records == 3
        assert res.records[0]["CONC"] == pytest.approx(25.45)

    def test_columns_inferred_for_plotfile(self):
        res = read_plotfile(FIXT / "sample_plotfile.plt")
        assert "X" in res.column_names
        assert "Y" in res.column_names
        assert "CONC" in res.column_names
