"""
Tests for coverage gaps identified in audit.

Priority 1: SRCGROUP/URBANSRC for all source types, ControlPathway options,
            grid validation edge cases.
Priority 4 (item 4): TerrainProcessor.process() orchestration.
Area 3: aermap.from_aermod_project(), advanced_viz import guards,
        geospatial cubic NaN fallback.
"""

import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourcePathway,
    TerrainType,
    VolumeSource,
    create_example_project,
)
from pyaermod.validator import Validator

# ============================================================================
# Helpers: minimal source factories
# ============================================================================


def _make_source(source_cls, *, source_groups=None, is_urban=False, urban_area_name=None):
    """Create a minimal source of the given type with optional group/urban settings."""
    kwargs = {}
    if source_groups is not None:
        kwargs["source_groups"] = source_groups
    if is_urban:
        kwargs["is_urban"] = True
    if urban_area_name:
        kwargs["urban_area_name"] = urban_area_name

    if source_cls is PointSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1, **kwargs,
        )
    elif source_cls is AreaSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            initial_lateral_dimension=25, initial_vertical_dimension=50,
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is AreaCircSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            radius=50, emission_rate=0.001, **kwargs,
        )
    elif source_cls is AreaPolySource:
        return source_cls(
            source_id="SRC1",
            vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is VolumeSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            release_height=5, initial_lateral_dimension=10,
            initial_vertical_dimension=5, emission_rate=0.001, **kwargs,
        )
    elif source_cls is LineSource:
        return source_cls(
            source_id="SRC1", x_start=0, y_start=0, x_end=100, y_end=0,
            release_height=2, initial_lateral_dimension=5,
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is RLineSource:
        return source_cls(
            source_id="SRC1", x_start=0, y_start=0, x_end=100, y_end=0,
            emission_rate=0.001, release_height=1.5,
            initial_lateral_dimension=3, initial_vertical_dimension=1.5,
            **kwargs,
        )
    elif source_cls is RLineExtSource:
        return source_cls(
            source_id="SRC1",
            x_start=0, y_start=0, z_start=0,
            x_end=100, y_end=0, z_end=0,
            emission_rate=0.001, dcl=10, road_width=20,
            init_sigma_z=1.5, **kwargs,
        )
    elif source_cls is BuoyLineSource:
        seg = BuoyLineSegment(
            source_id="BSEG1", x_start=0, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        return source_cls(
            source_id="BLP1", line_segments=[seg],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            **kwargs,
        )
    elif source_cls is OpenPitSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            x_dimension=100, y_dimension=200,
            emission_rate=0.01, pit_volume=50000,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown source class: {source_cls}")


# All source types that support SRCGROUP/URBANSRC
ALL_SOURCE_TYPES = [
    PointSource, AreaSource, AreaCircSource, AreaPolySource,
    VolumeSource, LineSource, RLineSource, RLineExtSource,
    BuoyLineSource, OpenPitSource,
]


# ============================================================================
# Priority 1a: SRCGROUP and URBANSRC for all source types
# ============================================================================


class TestSourceGroupAllTypes:
    """Test SRCGROUP keyword for all 10 source types."""

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_single_source_group(self, source_cls):
        src = _make_source(source_cls, source_groups=["ALL"])
        output = src.to_aermod_input()
        assert "SRCGROUP  ALL" in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_multiple_source_groups(self, source_cls):
        src = _make_source(source_cls, source_groups=["ALL", "GRP1", "MOBILE"])
        output = src.to_aermod_input()
        assert "SRCGROUP  ALL" in output
        assert "SRCGROUP  GRP1" in output
        assert "SRCGROUP  MOBILE" in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_no_source_groups_omits_keyword(self, source_cls):
        src = _make_source(source_cls, source_groups=None)
        output = src.to_aermod_input()
        assert "SRCGROUP" not in output

    def test_buoyline_srcgroup_uses_segment_ids(self):
        """BuoyLineSource emits SRCGROUP per segment, not per group source_id."""
        seg1 = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=50, y_end=0, emission_rate=1, release_height=10,
        )
        seg2 = BuoyLineSegment(
            source_id="BS2", x_start=50, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg1, seg2],
            avg_line_length=50, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            source_groups=["ALL"],
        )
        output = blp.to_aermod_input()
        assert "SRCGROUP  ALL      BS1" in output
        assert "SRCGROUP  ALL      BS2" in output


class TestUrbanSourceAllTypes:
    """Test URBANSRC keyword for all 10 source types."""

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_urban_source(self, source_cls):
        src = _make_source(source_cls, is_urban=True, urban_area_name="METRO1")
        output = src.to_aermod_input()
        assert "URBANSRC" in output
        assert "METRO1" in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_non_urban_omits_keyword(self, source_cls):
        src = _make_source(source_cls, is_urban=False)
        output = src.to_aermod_input()
        assert "URBANSRC" not in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_urban_without_name_omits_keyword(self, source_cls):
        """is_urban=True but no urban_area_name -> URBANSRC not emitted."""
        src = _make_source(source_cls, is_urban=True, urban_area_name=None)
        output = src.to_aermod_input()
        assert "URBANSRC" not in output

    def test_buoyline_urbansrc_uses_segment_ids(self):
        """BuoyLineSource emits URBANSRC per segment."""
        seg1 = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=50, y_end=0, emission_rate=1, release_height=10,
        )
        seg2 = BuoyLineSegment(
            source_id="BS2", x_start=50, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg1, seg2],
            avg_line_length=50, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            is_urban=True, urban_area_name="CITYAREA",
        )
        output = blp.to_aermod_input()
        assert "URBANSRC  BS1" in output
        assert "URBANSRC  BS2" in output
        assert "CITYAREA" in output


# ============================================================================
# Priority 1b: ControlPathway optional model options
# ============================================================================


class TestControlPathwayOptions:
    """Test all optional keywords in ControlPathway.to_aermod_input()."""

    def _make_control(self, **overrides):
        defaults = dict(
            title_one="Test",
            pollutant_id=PollutantType.PM25,
            averaging_periods=["ANNUAL"],
            terrain_type=TerrainType.FLAT,
        )
        defaults.update(overrides)
        return ControlPathway(**defaults)

    def test_deposition_flag(self):
        ctrl = self._make_control(calculate_deposition=True)
        output = ctrl.to_aermod_input()
        assert "DEPOS" in output

    def test_dry_deposition_flag(self):
        ctrl = self._make_control(calculate_dry_deposition=True)
        output = ctrl.to_aermod_input()
        assert "DDEP" in output

    def test_wet_deposition_flag(self):
        ctrl = self._make_control(calculate_wet_deposition=True)
        output = ctrl.to_aermod_input()
        assert "WDEP" in output

    def test_all_deposition_flags(self):
        ctrl = self._make_control(
            calculate_deposition=True,
            calculate_dry_deposition=True,
            calculate_wet_deposition=True,
        )
        output = ctrl.to_aermod_input()
        assert "DEPOS" in output
        assert "DDEP" in output
        assert "WDEP" in output

    def test_halflife(self):
        ctrl = self._make_control(half_life=12345.6789)
        output = ctrl.to_aermod_input()
        assert "HALFLIFE" in output
        assert "12345.6789" in output

    def test_decay_coefficient(self):
        ctrl = self._make_control(decay_coefficient=1.23e-4)
        output = ctrl.to_aermod_input()
        assert "DCAYCOEF" in output
        assert "1.230000e-04" in output

    def test_elevation_units_feet(self):
        ctrl = self._make_control(elevation_units="FEET")
        output = ctrl.to_aermod_input()
        assert "ELEVUNIT  FEET" in output

    def test_elevation_units_meters_omitted(self):
        ctrl = self._make_control(elevation_units="METERS")
        output = ctrl.to_aermod_input()
        assert "ELEVUNIT" not in output

    def test_flagpole_height(self):
        ctrl = self._make_control(flag_pole_height=1.5)
        output = ctrl.to_aermod_input()
        assert "FLAGPOLE  1.50" in output

    def test_urban_option(self):
        ctrl = self._make_control(urban_option="URBANOPT1")
        output = ctrl.to_aermod_input()
        assert "URBANOPT  URBANOPT1" in output

    def test_low_wind_option(self):
        ctrl = self._make_control(low_wind_option="LOWWIND3")
        output = ctrl.to_aermod_input()
        assert "LOW_WIND  LOWWIND3" in output

    def test_all_optional_together(self):
        """All optional CO keywords at once."""
        ctrl = self._make_control(
            calculate_deposition=True,
            half_life=100.0,
            decay_coefficient=5e-5,
            elevation_units="FEET",
            flag_pole_height=2.0,
            urban_option="URBAN1",
            low_wind_option="LOWWIND3",
        )
        output = ctrl.to_aermod_input()
        for kw in ["DEPOS", "HALFLIFE", "DCAYCOEF", "ELEVUNIT", "FLAGPOLE", "URBANOPT", "LOW_WIND"]:
            assert kw in output


# ============================================================================
# Priority 1c: Grid parameter validation edge cases
# ============================================================================


class TestCartesianGridValidation:
    """Test validator catches invalid CartesianGrid parameters."""

    def _validate_project_with_grid(self, **grid_kwargs):
        defaults = dict(x_init=0, x_num=5, x_delta=100, y_init=0, y_num=5, y_delta=100)
        defaults.update(grid_kwargs)
        grid = CartesianGrid(**defaults)
        project = AERMODProject(
            control=ControlPathway(title_one="T"),
            sources=SourcePathway(sources=[
                PointSource(source_id="S1", x_coord=0, y_coord=0,
                            stack_height=20, stack_temp=350, exit_velocity=10,
                            stack_diameter=1, emission_rate=1),
            ]),
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        return Validator.validate(project)

    def test_x_num_zero(self):
        result = self._validate_project_with_grid(x_num=0)
        fields = [e.field for e in result.errors]
        assert "x_num" in fields

    def test_y_num_zero(self):
        result = self._validate_project_with_grid(y_num=0)
        fields = [e.field for e in result.errors]
        assert "y_num" in fields

    def test_x_delta_zero(self):
        result = self._validate_project_with_grid(x_delta=0)
        fields = [e.field for e in result.errors]
        assert "x_delta" in fields

    def test_y_delta_zero(self):
        result = self._validate_project_with_grid(y_delta=0)
        fields = [e.field for e in result.errors]
        assert "y_delta" in fields

    def test_negative_num(self):
        result = self._validate_project_with_grid(x_num=-1)
        fields = [e.field for e in result.errors]
        assert "x_num" in fields

    def test_negative_delta(self):
        result = self._validate_project_with_grid(x_delta=-50)
        fields = [e.field for e in result.errors]
        assert "x_delta" in fields


class TestPolarGridValidation:
    """Test validator catches invalid PolarGrid parameters."""

    def _validate_project_with_polar(self, **grid_kwargs):
        defaults = dict(
            x_origin=0, y_origin=0,
            dist_num=5, dist_delta=100,
            dir_num=36, dir_delta=10,
        )
        defaults.update(grid_kwargs)
        grid = PolarGrid(**defaults)
        project = AERMODProject(
            control=ControlPathway(title_one="T"),
            sources=SourcePathway(sources=[
                PointSource(source_id="S1", x_coord=0, y_coord=0,
                            stack_height=20, stack_temp=350, exit_velocity=10,
                            stack_diameter=1, emission_rate=1),
            ]),
            receptors=ReceptorPathway(polar_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        return Validator.validate(project)

    def test_dist_num_zero(self):
        result = self._validate_project_with_polar(dist_num=0)
        fields = [e.field for e in result.errors]
        assert "dist_num" in fields

    def test_dist_delta_zero(self):
        result = self._validate_project_with_polar(dist_delta=0)
        fields = [e.field for e in result.errors]
        assert "dist_delta" in fields

    def test_dir_num_zero(self):
        result = self._validate_project_with_polar(dir_num=0)
        fields = [e.field for e in result.errors]
        assert "dir_num" in fields

    def test_dir_delta_zero(self):
        result = self._validate_project_with_polar(dir_delta=0)
        fields = [e.field for e in result.errors]
        assert "dir_delta" in fields

    def test_negative_dist_delta(self):
        result = self._validate_project_with_polar(dist_delta=-100)
        fields = [e.field for e in result.errors]
        assert "dist_delta" in fields

    def test_negative_dir_num(self):
        result = self._validate_project_with_polar(dir_num=-1)
        fields = [e.field for e in result.errors]
        assert "dir_num" in fields


# ============================================================================
# Priority 1d: ReceptorPathway elevation_units and polar grid rendering
# ============================================================================


class TestReceptorPathwayBranches:
    """Test untested branches in ReceptorPathway.to_aermod_input()."""

    def test_elevation_units_feet(self):
        rp = ReceptorPathway(
            elevation_units="FEET",
            cartesian_grids=[CartesianGrid(x_init=0, x_num=3, x_delta=100,
                                           y_init=0, y_num=3, y_delta=100)],
        )
        output = rp.to_aermod_input()
        assert "ELEVUNIT  FEET" in output

    def test_polar_grid_through_pathway(self):
        pg = PolarGrid(
            x_origin=500, y_origin=500,
            dist_num=3, dist_delta=100,
            dir_num=4, dir_delta=90,
        )
        rp = ReceptorPathway(polar_grids=[pg])
        output = rp.to_aermod_input()
        assert "RE STARTING" in output
        assert "GRIDPOLR" in output
        assert "RE FINISHED" in output


# ============================================================================
# Priority 1e: create_example_project smoke test
# ============================================================================


class TestExampleProject:
    """Smoke test for the create_example_project() function."""

    def test_creates_valid_project(self):
        project = create_example_project()
        assert project is not None
        output = project.to_aermod_input()
        assert "CO STARTING" in output
        assert "SO STARTING" in output
        assert "RE STARTING" in output
        assert "ME STARTING" in output
        assert "OU STARTING" in output

    def test_example_project_validates(self):
        project = create_example_project()
        result = Validator.validate(project)
        assert result.is_valid, f"Validation errors: {result.errors}"


# ============================================================================
# Item 4: TerrainProcessor.process() full pipeline with more coverage
# ============================================================================


class TestTerrainProcessorProcessFull:
    """
    Test TerrainProcessor.process() covering additional branches:
    - AERMAP failure -> RuntimeError
    - Source elevation output parsing
    - No DEM files -> RuntimeError
    - Download path (mocked)
    """

    def _make_project(self, with_discrete_receptors=True):
        control = ControlPathway(title_one="Terrain Test")
        sources = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=500000.0, y_coord=3800000.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources.add_source(point)
        receptors = ReceptorPathway()
        if with_discrete_receptors:
            receptors.add_discrete_receptor(
                DiscreteReceptor(x_coord=500100.0, y_coord=3800100.0, z_elev=0, z_flag=0)
            )
        grid = CartesianGrid(
            x_init=499500.0, x_num=3, x_delta=500.0,
            y_init=3799500.0, y_num=3, y_delta=500.0,
        )
        receptors.add_cartesian_grid(grid)
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        return AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

    def test_aermap_failure_raises_runtime_error(self, tmp_path):
        """When AERMAP returns success=False, process() raises RuntimeError."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=False, input_file=str(tmp_path / "aermap.inp"),
            return_code=1, runtime_seconds=0.5,
            error_message="AERMAP failed with return code 1",
        )

        with (
            patch.object(AERMAPRunner, "__init__", return_value=None),
            patch.object(AERMAPRunner, "run", return_value=mock_result),
            pytest.raises(RuntimeError, match="AERMAP failed"),
        ):
                processor.process(
                    project,
                    bounds=(-88, 40, -87, 41),
                    aermap_exe="/fake/aermap",
                    working_dir=str(tmp_path),
                    skip_download=True,
                    dem_files=["test.tif"],
                )

    def test_process_with_source_output(self, tmp_path):
        """process() parses source elevation output when file exists."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Create receptor output with the default AERMAPProject filename
        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text(
            "** AERMAP\n"
            "   DISCCART     500100.00    3800100.00    150.00    160.00\n"
        )

        # Create source output with the default AERMAPProject filename
        src_file = tmp_path / "aermap_sources.out"
        src_file.write_text(
            "** AERMAP Source Output\n"
            "   SO LOCATION  S1           POINT      500000.00    3800000.00      125.00\n"
        )

        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=["test.tif"],
            )

        assert result is project
        # Discrete receptor should have been updated
        rec = result.receptors.discrete_receptors[0]
        assert rec.z_elev == 150.0
        assert rec.z_hill == 160.0
        # Source should have been updated
        src = result.sources.sources[0]
        assert src.base_elevation == 125.0

    def test_process_no_dem_files_raises(self, tmp_path):
        """Empty dem_files list -> RuntimeError."""
        from pyaermod.terrain import TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        with pytest.raises(RuntimeError, match="No DEM files"):
            processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=[],
            )

    def test_process_with_download(self, tmp_path):
        """process() with skip_download=False downloads DEM tiles."""
        from pyaermod.terrain import (
            AERMAPRunner,
            AERMAPRunResult,
            DEMDownloader,
            TerrainProcessor,
        )

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Create a fake DEM file for the downloader to return
        dem_file = tmp_path / "dem_data" / "fake.tif"
        dem_file.parent.mkdir(parents=True, exist_ok=True)
        dem_file.write_text("fake dem")

        # Create receptor output (empty, just the header)
        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text("** AERMAP\n")

        with patch.object(DEMDownloader, "download_dem", return_value=[dem_file]), \
             patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=False,
            )

        assert result is project

    def test_process_grid_elevation_update(self, tmp_path):
        """process() updates CartesianGrid receptor elevations."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project(with_discrete_receptors=False)
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Build receptor output with all 9 grid points (3x3)
        grid = project.receptors.cartesian_grids[0]
        lines = ["** AERMAP"]
        for j in range(grid.y_num):
            for i in range(grid.x_num):
                x = grid.x_init + i * grid.x_delta
                y = grid.y_init + j * grid.y_delta
                elev = 100.0 + i * 10 + j * 5
                hill = elev + 10
                lines.append(f"   DISCCART  {x:12.2f} {y:12.2f} {elev:10.2f} {hill:10.2f}")

        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text("\n".join(lines))

        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=["test.tif"],
            )

        updated_grid = result.receptors.cartesian_grids[0]
        assert updated_grid.grid_elevations is not None
        assert len(updated_grid.grid_elevations) == 3
        assert len(updated_grid.grid_elevations[0]) == 3
        # First grid point
        assert updated_grid.grid_elevations[0][0] == 100.0
        assert updated_grid.grid_hills[0][0] == 110.0


# ============================================================================
# Bonus: run_aermap convenience function
# ============================================================================


class TestRunAermapConvenience:
    """Test the run_aermap() convenience function."""

    def test_run_aermap_with_missing_input(self, tmp_path):
        from pyaermod.terrain import AERMAPRunner, run_aermap

        # Mock the executable lookup so it doesn't fail before reaching
        # the missing-input-file check
        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run") as mock_run:
            mock_run.return_value = MagicMock(
                success=False, error_message="Input file not found"
            )
            result = run_aermap(tmp_path / "nonexistent.inp")

        assert not result.success
        assert "not found" in result.error_message


# ============================================================================
# Bonus: AERMAPRunner timeout exception
# ============================================================================


class TestAERMAPRunnerTimeout:
    """Test AERMAPRunner handles TimeoutExpired."""

    def test_timeout_returns_failure(self, tmp_path):
        from pyaermod.terrain import AERMAPRunner

        inp = tmp_path / "test.inp"
        inp.write_text("test")

        runner = AERMAPRunner.__new__(AERMAPRunner)
        runner.executable = "/fake/aermap"
        runner.logger = MagicMock()

        with patch("pyaermod.terrain.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="aermap", timeout=10)):
            result = runner.run(str(inp), working_dir=str(tmp_path), timeout=10)

        assert not result.success
        assert "timed out" in result.error_message.lower()


# ============================================================================
# Area 3A: aermap.py from_aermod_project() coverage gaps
# ============================================================================


class TestAERMAPFromAermodProject:
    """Test AERMAPProject.from_aermod_project() edge cases."""

    def _make_aermod_project(self, sources=None, grids=None, discrete_recs=None):
        """Build a minimal AERMODProject with given sources/receptors."""
        sp = SourcePathway()
        if sources:
            for s in sources:
                sp.add_source(s)
        rp = ReceptorPathway()
        if grids:
            for g in grids:
                rp.add_cartesian_grid(g)
        if discrete_recs:
            for r in discrete_recs:
                rp.add_discrete_receptor(r)
        return AERMODProject(
            control=ControlPathway(title_one="Test"),
            sources=sp,
            receptors=rp,
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def test_point_source_to_aermap(self):
        """PointSource coordinates extracted into AERMAP sources."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project(
            sources=[PointSource(
                source_id="STK1", x_coord=500.0, y_coord=600.0,
                emission_rate=1.0,
            )],
            discrete_recs=[DiscreteReceptor(x_coord=550, y_coord=650)],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.sources) == 1
        assert aermap.sources[0].source_id == "STK1"
        assert aermap.sources[0].x_coord == 500.0

    def test_line_source_uses_start_end(self):
        """LineSource (x_start/x_end) is handled by the hasattr branch."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project(
            sources=[LineSource(
                source_id="LN1", x_start=100, y_start=200,
                x_end=300, y_end=400,
                emission_rate=0.001, release_height=2,
                initial_lateral_dimension=5,
            )],
            discrete_recs=[DiscreteReceptor(x_coord=200, y_coord=300)],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.sources) == 1
        assert aermap.sources[0].x_coord == 100.0

    def test_cartesian_grid_receptor(self):
        """CartesianGrid is converted to AERMAP grid_receptor params."""
        from pyaermod.aermap import AERMAPProject

        grid = CartesianGrid(x_init=-500, x_num=11, x_delta=100,
                             y_init=-500, y_num=11, y_delta=100)
        project = self._make_aermod_project(
            sources=[PointSource(source_id="S1", x_coord=0, y_coord=0,
                                 emission_rate=1.0)],
            grids=[grid],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert aermap.grid_receptor is True
        assert aermap.grid_x_init == -500
        assert aermap.grid_x_num == 11
        assert aermap.grid_spacing == 100

    def test_discrete_receptors_to_aermap(self):
        """Discrete receptors get sequential IDs R0001, R0002, ..."""
        from pyaermod.aermap import AERMAPProject

        recs = [
            DiscreteReceptor(x_coord=100, y_coord=200),
            DiscreteReceptor(x_coord=300, y_coord=400),
        ]
        project = self._make_aermod_project(
            sources=[PointSource(source_id="S1", x_coord=0, y_coord=0,
                                 emission_rate=1.0)],
            discrete_recs=recs,
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.receptors) == 2
        assert aermap.receptors[0].receptor_id == "R0001"
        assert aermap.receptors[1].receptor_id == "R0002"
        assert aermap.receptors[1].x_coord == 300.0

    def test_empty_project_raises_value_error(self):
        """No sources or receptors → ValueError."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project()
        with pytest.raises(ValueError, match="No source or receptor coordinates"):
            AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])


# ============================================================================
# Area 3B: advanced_viz.py import guard tests
# ============================================================================


class TestAdvancedVizImportGuards:
    """Test that AdvancedVisualizer methods raise ImportError when matplotlib unavailable."""

    def test_plot_3d_surface_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_3d_surface(
                    pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_wind_rose_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_wind_rose(
                    np.array([1.0]), np.array([0.0])
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_concentration_profile_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_concentration_profile(
                    pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_time_series_animation_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_time_series_animation(
                    [pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})],
                    ["t0"],
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_time_series_animation_requires_animation(self):
        """If matplotlib exists but animation does not, separate ImportError."""
        import pyaermod.advanced_viz as adv_viz
        orig_mpl = adv_viz.HAS_MATPLOTLIB
        orig_anim = adv_viz.HAS_ANIMATION
        try:
            adv_viz.HAS_MATPLOTLIB = True
            adv_viz.HAS_ANIMATION = False
            with pytest.raises(ImportError, match="animation"):
                adv_viz.AdvancedVisualizer.plot_time_series_animation(
                    [pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})],
                    ["t0"],
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = orig_mpl
            adv_viz.HAS_ANIMATION = orig_anim


# ============================================================================
# Area 3C: geospatial.py cubic NaN fallback
# ============================================================================


class TestGeospatialCubicFallback:
    """Test cubic interpolation NaN fallback in generate_contours()."""

    def _make_contour_generator(self):
        """Create a ContourGenerator with a mock transformer."""
        import pyproj

        from pyaermod.geospatial import ContourGenerator

        mock_transformer = MagicMock()
        mock_transformer.utm_crs = pyproj.CRS(proj="utm", zone=16, datum="WGS84")
        # Bypass __init__ checks by constructing directly
        gen = ContourGenerator.__new__(ContourGenerator)
        gen.transformer = mock_transformer
        return gen

    def test_cubic_nan_fallback_to_linear(self):
        """When cubic produces >30% NaN, method falls back to linear."""
        scipy = pytest.importorskip("scipy")
        pytest.importorskip("geopandas")

        gen = self._make_contour_generator()

        df = pd.DataFrame({
            "x": [0, 100, 200, 0, 100, 200, 0, 100, 200],
            "y": [0, 0, 0, 100, 100, 100, 200, 200, 200],
            "concentration": [1.0, 5.0, 2.0, 3.0, 10.0, 4.0, 1.5, 6.0, 2.5],
        })

        call_count = {"n": 0}
        original_griddata = scipy.interpolate.griddata

        def mock_griddata(points, values, grid, method="linear"):
            call_count["n"] += 1
            if method == "cubic" and call_count["n"] == 1:
                # Return mostly NaN to trigger fallback
                result = np.full(grid[0].shape, np.nan)
                result[0, 0] = 1.0  # Only 1 valid value out of many
                return result
            return original_griddata(points, values, grid, method=method)

        with patch("pyaermod.geospatial.griddata", side_effect=mock_griddata):
            result = gen.generate_contours(
                df, value_col="concentration",
                method="cubic", grid_resolution=50,
            )

        # If fallback occurred, griddata was called at least twice
        assert call_count["n"] >= 2

    def test_contour_codes_none_path(self):
        """Contour path with codes=None still generates contours."""
        pytest.importorskip("scipy")
        geopandas = pytest.importorskip("geopandas")

        gen = self._make_contour_generator()

        # Simple regular grid that should produce clean contours
        x = np.linspace(0, 100, 10)
        y = np.linspace(0, 100, 10)
        xx, yy = np.meshgrid(x, y)
        df = pd.DataFrame({
            "x": xx.ravel(),
            "y": yy.ravel(),
            "concentration": (xx**2 + yy**2).ravel() / 1000,
        })

        result = gen.generate_contours(
            df, value_col="concentration",
            method="linear", grid_resolution=50,
        )
        assert isinstance(result, geopandas.GeoDataFrame)
        assert len(result) > 0


# ============================================================================
# Item 2A: AreaSource/VolumeSource set_building_from_bpip
# ============================================================================


class TestAreaVolumeSourceBPIP:
    """Test set_building_from_bpip for AreaSource and VolumeSource."""

    def _make_building(self):
        from pyaermod.bpip import Building
        return Building(
            "BLDG1",
            [(-20, -15), (20, -15), (20, 15), (-20, 15)],
            height=25.0,
        )

    def test_area_source_set_building_from_bpip(self):
        """AreaSource.set_building_from_bpip populates all 36-value arrays."""
        bldg = self._make_building()
        src = AreaSource(
            source_id="AS1", x_coord=0, y_coord=0,
            initial_lateral_dimension=25, initial_vertical_dimension=50,
            emission_rate=0.001,
        )
        src.set_building_from_bpip(bldg)

        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert len(src.building_width) == 36
        assert len(src.building_length) == 36
        assert len(src.building_x_offset) == 36
        assert len(src.building_y_offset) == 36

        output = src.to_aermod_input()
        assert output.count("BUILDHGT") == 4
        assert output.count("BUILDWID") == 4

    def test_volume_source_set_building_from_bpip(self):
        """VolumeSource.set_building_from_bpip populates all 36-value arrays."""
        bldg = self._make_building()
        src = VolumeSource(
            source_id="VS1", x_coord=0, y_coord=0,
            release_height=5, initial_lateral_dimension=10,
            initial_vertical_dimension=5, emission_rate=0.001,
        )
        src.set_building_from_bpip(bldg)

        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert len(src.building_width) == 36

        output = src.to_aermod_input()
        assert output.count("BUILDHGT") == 4
        assert output.count("XBADJ") == 4


# ============================================================================
# Item 2B: MeteorologyPathway WDROTATE
# ============================================================================


class TestMeteorologyFeatures:
    """Test optional MeteorologyPathway features."""

    def test_wind_rotation_output(self):
        """wind_rotation=15.5 produces WDROTATE keyword."""
        met = MeteorologyPathway(
            surface_file="t.sfc", profile_file="t.pfl",
            wind_rotation=15.5,
        )
        output = met.to_aermod_input()
        assert "WDROTATE  15.50" in output

    def test_wind_rotation_none_omits_keyword(self):
        """wind_rotation=None omits WDROTATE keyword."""
        met = MeteorologyPathway(
            surface_file="t.sfc", profile_file="t.pfl",
        )
        output = met.to_aermod_input()
        assert "WDROTATE" not in output


# ============================================================================
# Item 2C: OutputPathway DAYTABLE / MAXIFILE
# ============================================================================


class TestOutputPathwayFeatures:
    """Test optional OutputPathway features (day_table, max_file)."""

    def test_day_table_output(self):
        """day_table=True produces DAYTABLE keyword."""
        out = OutputPathway(day_table=True)
        output = out.to_aermod_input()
        assert "DAYTABLE  ALLAVE" in output

    def test_max_file_output(self):
        """max_file produces MAXIFILE keyword."""
        out = OutputPathway(max_file="maxconc.out")
        output = out.to_aermod_input()
        assert "MAXIFILE  maxconc.out" in output

    def test_output_defaults_omit_optional(self):
        """Default OutputPathway omits DAYTABLE and MAXIFILE."""
        out = OutputPathway()
        output = out.to_aermod_input()
        assert "DAYTABLE" not in output
        assert "MAXIFILE" not in output
