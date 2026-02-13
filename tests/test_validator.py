"""
Unit tests for PyAERMOD Configuration Validator

Tests validation logic for all pathways and cross-field checks.
"""

import pytest
from pyaermod.input_generator import (
    BackgroundConcentration,
    BackgroundSector,
    ControlPathway,
    DepositionMethod,
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    ParticleDepositionParams,
    SourcePathway,
    PointSource,
    AreaSource,
    AreaCircSource,
    AreaPolySource,
    VolumeSource,
    LineSource,
    RLineSource,
    RLineExtSource,
    BuoyLineSource,
    BuoyLineSegment,
    OpenPitSource,
    ReceptorPathway,
    CartesianGrid,
    PolarGrid,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    AERMODProject,
    PollutantType,
    TerrainType,
)
from pyaermod.validator import Validator, ValidationResult, ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_project(**overrides):
    """Build a minimal valid AERMODProject. Override any pathway via kwargs."""
    control = overrides.get("control", ControlPathway(
        title_one="Test Project",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL"],
    ))
    sources = overrides.get("sources", SourcePathway())
    if "sources" not in overrides:
        sources.add_source(PointSource(
            source_id="STK1",
            x_coord=500.0, y_coord=500.0,
            stack_height=30.0, stack_diameter=1.5,
            stack_temp=400.0, exit_velocity=10.0,
            emission_rate=1.0,
        ))
    receptors = overrides.get("receptors", ReceptorPathway(
        cartesian_grids=[CartesianGrid()],
    ))
    meteorology = overrides.get("meteorology", MeteorologyPathway(
        surface_file="test.sfc",
        profile_file="test.pfl",
    ))
    output = overrides.get("output", OutputPathway())
    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
    )


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------

class TestValidationResult:
    """Test the ValidationResult container."""

    def test_empty_result_is_valid(self):
        r = ValidationResult()
        assert r.is_valid
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_error_makes_invalid(self):
        r = ValidationResult(errors=[
            ValidationError("X", "y", "bad", severity="error"),
        ])
        assert not r.is_valid
        assert r.error_count == 1

    def test_warning_stays_valid(self):
        r = ValidationResult(errors=[
            ValidationError("X", "y", "watch out", severity="warning"),
        ])
        assert r.is_valid
        assert r.warning_count == 1

    def test_str_representation(self):
        r = ValidationResult(errors=[
            ValidationError("A", "b", "msg"),
        ])
        s = str(r)
        assert "1 error(s)" in s
        assert "A.b" in s

    def test_str_no_errors(self):
        assert "passed" in str(ValidationResult())


# ---------------------------------------------------------------------------
# Full project: valid baseline
# ---------------------------------------------------------------------------

class TestValidProject:
    """A well-formed project should produce zero errors."""

    def test_valid_project_passes(self):
        project = _make_valid_project()
        result = Validator.validate(project)
        assert result.is_valid, str(result)
        assert result.error_count == 0


# ---------------------------------------------------------------------------
# Control pathway validation
# ---------------------------------------------------------------------------

class TestControlValidation:

    def test_empty_title(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="", averaging_periods=["ANNUAL"]),
        )
        result = Validator.validate(project)
        assert not result.is_valid
        assert any("title_one" in e.field for e in result.errors)

    def test_no_averaging_periods(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", averaging_periods=[]),
        )
        result = Validator.validate(project)
        assert not result.is_valid
        assert any("averaging_periods" in e.field for e in result.errors)

    def test_invalid_averaging_period(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", averaging_periods=["ANNUAL", "99"]),
        )
        result = Validator.validate(project)
        assert not result.is_valid
        assert any("99" in e.message for e in result.errors)

    def test_valid_averaging_periods(self):
        """All standard periods should pass."""
        for period in ["1", "2", "3", "4", "6", "8", "12", "24", "MONTH", "ANNUAL", "PERIOD"]:
            project = _make_valid_project(
                control=ControlPathway(title_one="T", averaging_periods=[period]),
            )
            result = Validator.validate(project)
            errs = [e for e in result.errors if "averaging_periods" in e.field]
            assert len(errs) == 0, f"period '{period}' should be valid"

    def test_invalid_pollutant(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", pollutant_id="BADPOLL"),
        )
        result = Validator.validate(project)
        assert not result.is_valid
        assert any("pollutant" in e.field for e in result.errors)

    def test_enum_pollutant_accepted(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", pollutant_id=PollutantType.NO2),
        )
        result = Validator.validate(project)
        pollutant_errors = [e for e in result.errors if "pollutant" in e.field]
        assert len(pollutant_errors) == 0

    def test_invalid_elevation_units(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", elevation_units="FURLONGS"),
        )
        result = Validator.validate(project)
        assert any("elevation_units" in e.field for e in result.errors)

    def test_both_halflife_and_decay(self):
        project = _make_valid_project(
            control=ControlPathway(
                title_one="T", half_life=2.0, decay_coefficient=0.001,
            ),
        )
        result = Validator.validate(project)
        assert any("half_life" in e.field for e in result.errors)

    def test_negative_half_life(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", half_life=-1.0),
        )
        result = Validator.validate(project)
        assert any("half_life" in e.field and "error" == e.severity for e in result.errors)

    def test_negative_decay_coefficient(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="T", decay_coefficient=-0.01),
        )
        result = Validator.validate(project)
        assert any("decay_coefficient" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# Point source validation
# ---------------------------------------------------------------------------

class TestPointSourceValidation:

    def _project_with_point(self, **kwargs):
        defaults = dict(
            source_id="STK1", x_coord=500.0, y_coord=500.0,
            stack_height=30.0, stack_diameter=1.5,
            stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(PointSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_zero_stack_height(self):
        result = Validator.validate(self._project_with_point(stack_height=0.0))
        assert any("stack_height" in e.field for e in result.errors)

    def test_negative_stack_height(self):
        result = Validator.validate(self._project_with_point(stack_height=-5.0))
        assert any("stack_height" in e.field for e in result.errors)

    def test_zero_stack_diameter(self):
        result = Validator.validate(self._project_with_point(stack_diameter=0.0))
        assert any("stack_diameter" in e.field for e in result.errors)

    def test_zero_stack_temp(self):
        result = Validator.validate(self._project_with_point(stack_temp=0.0))
        assert any("stack_temp" in e.field for e in result.errors)

    def test_negative_exit_velocity(self):
        result = Validator.validate(self._project_with_point(exit_velocity=-1.0))
        assert any("exit_velocity" in e.field for e in result.errors)

    def test_zero_exit_velocity_ok(self):
        """Zero exit velocity is valid (passive stack)."""
        result = Validator.validate(self._project_with_point(exit_velocity=0.0))
        vel_errors = [e for e in result.errors if "exit_velocity" in e.field]
        assert len(vel_errors) == 0

    def test_negative_emission_rate(self):
        result = Validator.validate(self._project_with_point(emission_rate=-0.1))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_zero_emission_rate_ok(self):
        """Zero emission is valid (placeholder source)."""
        result = Validator.validate(self._project_with_point(emission_rate=0.0))
        er_errors = [e for e in result.errors if "emission_rate" in e.field]
        assert len(er_errors) == 0

    def test_building_array_wrong_length(self):
        result = Validator.validate(self._project_with_point(
            building_height=[10.0] * 35,
        ))
        assert any("building_height" in e.field for e in result.errors)

    def test_building_array_correct_length(self):
        result = Validator.validate(self._project_with_point(
            building_height=[20.0] * 36,
            building_width=[15.0] * 36,
            building_length=[25.0] * 36,
            building_x_offset=[0.0] * 36,
            building_y_offset=[0.0] * 36,
        ))
        bldg_errors = [e for e in result.errors if "building_" in e.field and e.severity == "error"]
        assert len(bldg_errors) == 0

    def test_building_height_warning(self):
        """Building height >= stack height produces warning, not error."""
        result = Validator.validate(self._project_with_point(
            stack_height=20.0, building_height=25.0,
        ))
        warnings = [e for e in result.errors
                    if "building_height" in e.field and e.severity == "warning"]
        assert len(warnings) == 1

    def test_building_height_list_warning(self):
        """Max of 36-value array >= stack height triggers warning."""
        heights = [15.0] * 35 + [35.0]  # max = 35, stack = 30
        result = Validator.validate(self._project_with_point(
            stack_height=30.0, building_height=heights,
        ))
        warnings = [e for e in result.errors
                    if "building_height" in e.field and e.severity == "warning"]
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Duplicate source IDs
# ---------------------------------------------------------------------------

class TestDuplicateSourceIDs:

    def test_duplicate_ids_flagged(self):
        sources = SourcePathway()
        for _ in range(2):
            sources.add_source(PointSource(
                source_id="DUP", x_coord=0, y_coord=0,
                stack_height=10.0, stack_diameter=1.0,
                stack_temp=300.0,
            ))
        project = _make_valid_project(sources=sources)
        result = Validator.validate(project)
        assert any("duplicate" in e.message for e in result.errors)


# ---------------------------------------------------------------------------
# Area source validation
# ---------------------------------------------------------------------------

class TestAreaSourceValidation:

    def _project_with_area(self, **kwargs):
        defaults = dict(
            source_id="AREA1", x_coord=0.0, y_coord=0.0,
            initial_lateral_dimension=10.0, initial_vertical_dimension=10.0,
            emission_rate=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(AreaSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_zero_lateral_dim(self):
        result = Validator.validate(self._project_with_area(initial_lateral_dimension=0.0))
        assert any("initial_lateral_dimension" in e.field for e in result.errors)

    def test_zero_vertical_dim(self):
        result = Validator.validate(self._project_with_area(initial_vertical_dimension=0.0))
        assert any("initial_vertical_dimension" in e.field for e in result.errors)

    def test_negative_emission_rate(self):
        result = Validator.validate(self._project_with_area(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_negative_release_height(self):
        result = Validator.validate(self._project_with_area(release_height=-1.0))
        assert any("release_height" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# AreaCircSource validation
# ---------------------------------------------------------------------------

class TestAreaCircSourceValidation:

    def _project_with_circ(self, **kwargs):
        defaults = dict(
            source_id="CIRC1", x_coord=0.0, y_coord=0.0,
            radius=50.0, emission_rate=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(AreaCircSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_zero_radius(self):
        result = Validator.validate(self._project_with_circ(radius=0.0))
        assert any("radius" in e.field for e in result.errors)

    def test_too_few_vertices(self):
        result = Validator.validate(self._project_with_circ(num_vertices=2))
        assert any("num_vertices" in e.field for e in result.errors)

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_circ(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_negative_release_height(self):
        result = Validator.validate(self._project_with_circ(release_height=-1.0))
        assert any("release_height" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# AreaPolySource validation
# ---------------------------------------------------------------------------

class TestAreaPolySourceValidation:

    def _project_with_poly(self, **kwargs):
        defaults = dict(
            source_id="POLY1",
            vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
            emission_rate=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(AreaPolySource(**defaults))
        return _make_valid_project(sources=sources)

    def test_too_few_vertices(self):
        result = Validator.validate(self._project_with_poly(vertices=[(0, 0), (1, 1)]))
        assert any("vertices" in e.field for e in result.errors)

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_poly(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# Volume source validation
# ---------------------------------------------------------------------------

class TestVolumeSourceValidation:

    def _project_with_volume(self, **kwargs):
        defaults = dict(
            source_id="VOL1", x_coord=0.0, y_coord=0.0,
            initial_lateral_dimension=5.0, initial_vertical_dimension=5.0,
            emission_rate=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(VolumeSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_zero_lateral_dim(self):
        result = Validator.validate(self._project_with_volume(initial_lateral_dimension=0.0))
        assert any("initial_lateral_dimension" in e.field for e in result.errors)

    def test_zero_vertical_dim(self):
        result = Validator.validate(self._project_with_volume(initial_vertical_dimension=0.0))
        assert any("initial_vertical_dimension" in e.field for e in result.errors)

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_volume(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_negative_release_height(self):
        result = Validator.validate(self._project_with_volume(release_height=-1.0))
        assert any("release_height" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# Line source validation
# ---------------------------------------------------------------------------

class TestLineSourceValidation:

    def _project_with_line(self, cls=LineSource, **kwargs):
        defaults = dict(
            source_id="LINE1",
            x_start=0.0, y_start=0.0, x_end=100.0, y_end=0.0,
            emission_rate=1.0, initial_lateral_dimension=1.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(cls(**defaults))
        return _make_valid_project(sources=sources)

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_line(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_negative_release_height(self):
        result = Validator.validate(self._project_with_line(release_height=-1.0))
        assert any("release_height" in e.field for e in result.errors)

    def test_zero_lateral_dim(self):
        result = Validator.validate(self._project_with_line(initial_lateral_dimension=0.0))
        assert any("initial_lateral_dimension" in e.field for e in result.errors)

    def test_zero_length_line(self):
        result = Validator.validate(self._project_with_line(
            x_start=50.0, y_start=50.0, x_end=50.0, y_end=50.0,
        ))
        assert any("zero-length" in e.message for e in result.errors)

    def test_rline_same_checks(self):
        result = Validator.validate(self._project_with_line(
            cls=RLineSource, emission_rate=-1.0,
            initial_vertical_dimension=1.5,
        ))
        assert any("emission_rate" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# Urban source / URBANOPT cross-field
# ---------------------------------------------------------------------------

class TestUrbanCrossValidation:

    def test_urban_source_without_urbanopt(self):
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30.0, stack_diameter=1.0, stack_temp=400.0,
            exit_velocity=10.0, is_urban=True, urban_area_name="CITY",
        ))
        control = ControlPathway(title_one="T")
        project = _make_valid_project(control=control, sources=sources)
        result = Validator.validate(project)
        assert any("urban_option" in e.field for e in result.errors)

    def test_urban_source_with_urbanopt(self):
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30.0, stack_diameter=1.0, stack_temp=400.0,
            exit_velocity=10.0, is_urban=True, urban_area_name="CITY",
        ))
        control = ControlPathway(title_one="T", urban_option="CITY")
        project = _make_valid_project(control=control, sources=sources)
        result = Validator.validate(project)
        urban_errors = [e for e in result.errors if "urban_option" in e.field]
        assert len(urban_errors) == 0


# ---------------------------------------------------------------------------
# No sources
# ---------------------------------------------------------------------------

class TestNoSources:

    def test_empty_source_pathway(self):
        project = _make_valid_project(sources=SourcePathway())
        result = Validator.validate(project)
        assert any("at least one source" in e.message for e in result.errors)


# ---------------------------------------------------------------------------
# Receptor validation
# ---------------------------------------------------------------------------

class TestReceptorValidation:

    def test_no_receptors(self):
        project = _make_valid_project(receptors=ReceptorPathway())
        result = Validator.validate(project)
        assert any("at least one receptor" in e.message for e in result.errors)

    def test_discrete_receptor_counts(self):
        """A single discrete receptor satisfies the requirement."""
        project = _make_valid_project(receptors=ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(x_coord=0, y_coord=0)],
        ))
        result = Validator.validate(project)
        rec_errors = [e for e in result.errors if "receptor" in e.message.lower()]
        assert len(rec_errors) == 0

    def test_invalid_cartesian_grid(self):
        project = _make_valid_project(receptors=ReceptorPathway(
            cartesian_grids=[CartesianGrid(x_num=0)],
        ))
        result = Validator.validate(project)
        assert any("x_num" in e.field for e in result.errors)

    def test_invalid_polar_grid(self):
        project = _make_valid_project(receptors=ReceptorPathway(
            polar_grids=[PolarGrid(dist_delta=0)],
        ))
        result = Validator.validate(project)
        assert any("dist_delta" in e.field for e in result.errors)

    def test_invalid_elevation_units(self):
        project = _make_valid_project(receptors=ReceptorPathway(
            cartesian_grids=[CartesianGrid()],
            elevation_units="CUBITS",
        ))
        result = Validator.validate(project)
        assert any("elevation_units" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# Meteorology validation
# ---------------------------------------------------------------------------

class TestMeteorologyValidation:

    def test_empty_surface_file(self):
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file="", profile_file="test.pfl",
        ))
        result = Validator.validate(project)
        assert any("surface_file" in e.field for e in result.errors)

    def test_empty_profile_file(self):
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file="test.sfc", profile_file="",
        ))
        result = Validator.validate(project)
        assert any("profile_file" in e.field for e in result.errors)

    def test_partial_date_range(self):
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
            start_year=2023, start_month=1,
            # Missing start_day, end_*
        ))
        result = Validator.validate(project)
        assert any("partial date range" in e.message for e in result.errors)

    def test_complete_date_range_ok(self):
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
            start_year=2023, start_month=1, start_day=1,
            end_year=2023, end_month=12, end_day=31,
        ))
        result = Validator.validate(project)
        date_errors = [e for e in result.errors if "date" in e.message]
        assert len(date_errors) == 0

    def test_file_check_missing(self, tmp_path):
        """check_files=True should flag non-existent files."""
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file=str(tmp_path / "no_such.sfc"),
            profile_file=str(tmp_path / "no_such.pfl"),
        ))
        result = Validator.validate(project, check_files=True)
        assert any("file not found" in e.message for e in result.errors)

    def test_file_check_existing(self, tmp_path):
        """Existing files should not produce errors."""
        sfc = tmp_path / "real.sfc"
        pfl = tmp_path / "real.pfl"
        sfc.write_text("data")
        pfl.write_text("data")
        project = _make_valid_project(meteorology=MeteorologyPathway(
            surface_file=str(sfc), profile_file=str(pfl),
        ))
        result = Validator.validate(project, check_files=True)
        file_errors = [e for e in result.errors if "file not found" in e.message]
        assert len(file_errors) == 0


# ---------------------------------------------------------------------------
# Output pathway validation
# ---------------------------------------------------------------------------

class TestOutputValidation:

    def test_zero_receptor_table_rank(self):
        project = _make_valid_project(output=OutputPathway(
            receptor_table=True, receptor_table_rank=0,
        ))
        result = Validator.validate(project)
        assert any("receptor_table_rank" in e.field for e in result.errors)

    def test_zero_max_table_rank(self):
        project = _make_valid_project(output=OutputPathway(
            max_table=True, max_table_rank=0,
        ))
        result = Validator.validate(project)
        assert any("max_table_rank" in e.field for e in result.errors)

    def test_disabled_table_zero_rank_ok(self):
        """Rank doesn't matter when table is disabled."""
        project = _make_valid_project(output=OutputPathway(
            receptor_table=False, receptor_table_rank=0,
            max_table=False, max_table_rank=0,
        ))
        result = Validator.validate(project)
        rank_errors = [e for e in result.errors if "rank" in e.field]
        assert len(rank_errors) == 0


# ---------------------------------------------------------------------------
# RLineExtSource validation
# ---------------------------------------------------------------------------

class TestRLineExtSourceValidation:

    def _project_with_rlinext(self, **kwargs):
        defaults = dict(
            source_id="RLX1",
            x_start=0.0, y_start=0.0, z_start=0.5,
            x_end=100.0, y_end=0.0, z_end=0.5,
            emission_rate=0.001, dcl=0.0,
            road_width=30.0, init_sigma_z=1.5,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(RLineExtSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_valid_rlinext(self):
        result = Validator.validate(self._project_with_rlinext())
        src_errors = [e for e in result.errors if "RLX1" in e.pathway and e.severity == "error"]
        assert len(src_errors) == 0

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_rlinext(emission_rate=-0.1))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_zero_road_width(self):
        result = Validator.validate(self._project_with_rlinext(road_width=0.0))
        assert any("road_width" in e.field for e in result.errors)

    def test_negative_init_sigma_z(self):
        result = Validator.validate(self._project_with_rlinext(init_sigma_z=-1.0))
        assert any("init_sigma_z" in e.field for e in result.errors)

    def test_zero_length_line(self):
        result = Validator.validate(self._project_with_rlinext(
            x_start=50.0, y_start=50.0, x_end=50.0, y_end=50.0,
        ))
        assert any("zero-length" in e.message for e in result.errors)

    def test_barrier_negative_height(self):
        result = Validator.validate(self._project_with_rlinext(
            barrier_height_1=-5.0, barrier_dcl_1=10.0,
        ))
        assert any("barrier" in e.field.lower() for e in result.errors)

    def test_depression_positive_depth(self):
        result = Validator.validate(self._project_with_rlinext(
            depression_depth=5.0, depression_wtop=20.0, depression_wbottom=10.0,
        ))
        assert any("depression_depth" in e.field for e in result.errors)

    def test_depression_wbottom_exceeds_wtop(self):
        result = Validator.validate(self._project_with_rlinext(
            depression_depth=-3.0, depression_wtop=10.0, depression_wbottom=15.0,
        ))
        assert any("depression_wbottom" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# BuoyLineSource validation
# ---------------------------------------------------------------------------

class TestBuoyLineSourceValidation:

    def _project_with_buoyline(self, segments=None, **kwargs):
        if segments is None:
            segments = [
                BuoyLineSegment("BL01", 0, 0, 100, 0, emission_rate=1.0, release_height=10.0),
            ]
        defaults = dict(
            source_id="BLP1",
            avg_line_length=100.0,
            avg_building_height=15.0,
            avg_building_width=20.0,
            avg_line_width=5.0,
            avg_building_separation=10.0,
            avg_buoyancy_parameter=0.5,
            line_segments=segments,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(BuoyLineSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_valid_buoyline(self):
        result = Validator.validate(self._project_with_buoyline())
        src_errors = [e for e in result.errors if "BLP1" in e.pathway and e.severity == "error"]
        assert len(src_errors) == 0

    def test_zero_buoyancy_parameter(self):
        result = Validator.validate(self._project_with_buoyline(avg_buoyancy_parameter=0.0))
        assert any("avg_buoyancy_parameter" in e.field for e in result.errors)

    def test_zero_line_length(self):
        result = Validator.validate(self._project_with_buoyline(avg_line_length=0.0))
        assert any("avg_line_length" in e.field for e in result.errors)

    def test_zero_building_height(self):
        result = Validator.validate(self._project_with_buoyline(avg_building_height=0.0))
        assert any("avg_building_height" in e.field for e in result.errors)

    def test_no_segments(self):
        result = Validator.validate(self._project_with_buoyline(segments=[]))
        assert any("segment" in e.message.lower() for e in result.errors)

    def test_segment_negative_emission(self):
        segs = [BuoyLineSegment("BL01", 0, 0, 100, 0, emission_rate=-1.0)]
        result = Validator.validate(self._project_with_buoyline(segments=segs))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_segment_excessive_release_height(self):
        segs = [BuoyLineSegment("BL01", 0, 0, 100, 0, release_height=5000.0)]
        result = Validator.validate(self._project_with_buoyline(segments=segs))
        assert any("release_height" in e.field for e in result.errors)


# ---------------------------------------------------------------------------
# OpenPitSource validation
# ---------------------------------------------------------------------------

class TestOpenPitSourceValidation:

    def _project_with_openpit(self, **kwargs):
        defaults = dict(
            source_id="PIT1",
            x_coord=0.0, y_coord=0.0,
            emission_rate=0.01, release_height=0.0,
            x_dimension=100.0, y_dimension=100.0,
            pit_volume=100000.0,
        )
        defaults.update(kwargs)
        sources = SourcePathway()
        sources.add_source(OpenPitSource(**defaults))
        return _make_valid_project(sources=sources)

    def test_valid_openpit(self):
        result = Validator.validate(self._project_with_openpit())
        src_errors = [e for e in result.errors if "PIT1" in e.pathway and e.severity == "error"]
        assert len(src_errors) == 0

    def test_negative_emission(self):
        result = Validator.validate(self._project_with_openpit(emission_rate=-1.0))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_negative_release_height(self):
        result = Validator.validate(self._project_with_openpit(release_height=-1.0))
        assert any("release_height" in e.field for e in result.errors)

    def test_zero_x_dimension(self):
        result = Validator.validate(self._project_with_openpit(x_dimension=0.0))
        assert any("x_dimension" in e.field for e in result.errors)

    def test_zero_y_dimension(self):
        result = Validator.validate(self._project_with_openpit(y_dimension=0.0))
        assert any("y_dimension" in e.field for e in result.errors)

    def test_zero_volume(self):
        result = Validator.validate(self._project_with_openpit(pit_volume=0.0))
        assert any("pit_volume" in e.field for e in result.errors)

    def test_release_height_exceeds_depth_warning(self):
        # Volume=100000, x_dim=100, y_dim=100 → depth=10
        # release_height=15 exceeds depth → should produce warning
        result = Validator.validate(self._project_with_openpit(
            release_height=15.0, pit_volume=100000.0,
            x_dimension=100.0, y_dimension=100.0,
        ))
        warnings = [e for e in result.errors
                    if "release_height" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1

    def test_extreme_aspect_ratio_warning(self):
        result = Validator.validate(self._project_with_openpit(
            x_dimension=1000.0, y_dimension=10.0,
        ))
        warnings = [e for e in result.errors if e.severity == "warning" and "aspect" in e.message.lower()]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# Background Concentration Validation
# ---------------------------------------------------------------------------

class TestBackgroundValidation:
    """Test background concentration validation."""

    def _project_with_background(self, bg):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=500.0, y_coord=500.0,
            stack_height=30.0, stack_diameter=1.5,
            stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0,
        ))
        sp.background = bg
        return _make_valid_project(sources=sp)

    def test_valid_uniform_background(self):
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(uniform_value=5.0)
        ))
        bg_errors = [e for e in result.errors if "BackgroundConcentration" in e.pathway]
        assert len(bg_errors) == 0

    def test_negative_uniform_value(self):
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(uniform_value=-1.0)
        ))
        bg_errors = [e for e in result.errors if "uniform_value" in e.field]
        assert len(bg_errors) >= 1

    def test_invalid_averaging_period(self):
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(period_values={"ANNUAL": 5.0, "INVALID": 3.0})
        ))
        bg_errors = [e for e in result.errors if "period_values" in e.field]
        assert len(bg_errors) >= 1

    def test_negative_period_value(self):
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(period_values={"ANNUAL": -2.0})
        ))
        bg_errors = [e for e in result.errors if "period_values" in e.field]
        assert len(bg_errors) >= 1

    def test_too_many_sectors(self):
        sectors = [BackgroundSector(i, i*30.0, (i+1)*30.0) for i in range(13)]
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(sectors=sectors, sector_values={(1, "ANNUAL"): 5.0})
        ))
        bg_errors = [e for e in result.errors if "sectors" in e.field and "12" in e.message]
        assert len(bg_errors) >= 1

    def test_invalid_sector_direction(self):
        sectors = [BackgroundSector(1, -10.0, 90.0)]
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(sectors=sectors, sector_values={(1, "ANNUAL"): 5.0})
        ))
        bg_errors = [e for e in result.errors if "start_direction" in e.message]
        assert len(bg_errors) >= 1

    def test_invalid_sector_id_in_values(self):
        sectors = [BackgroundSector(1, 0.0, 180.0)]
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(
                sectors=sectors,
                sector_values={(1, "ANNUAL"): 5.0, (99, "ANNUAL"): 3.0},
            )
        ))
        bg_errors = [e for e in result.errors if "sector_id 99" in e.message]
        assert len(bg_errors) >= 1


# ---------------------------------------------------------------------------
# Deposition Validation
# ---------------------------------------------------------------------------

class TestDepositionValidation:
    """Test deposition parameter validation."""

    def _project_with_deposition(self, gas_dep=None, particle_dep=None,
                                  dep_method=None, dep_enabled=True):
        control = ControlPathway(
            title_one="Test", pollutant_id="OTHER",
            averaging_periods=["ANNUAL"],
            calculate_dry_deposition=dep_enabled,
        )
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=500.0, y_coord=500.0,
            stack_height=30.0, stack_diameter=1.5,
            stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0,
            gas_deposition=gas_dep,
            particle_deposition=particle_dep,
            deposition_method=dep_method,
        ))
        return _make_valid_project(control=control, sources=sp)

    def test_valid_gas_deposition(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=0.5, henry_constant=0.011,
            ),
        ))
        dep_errors = [e for e in result.errors
                      if "deposition" in e.field.lower() or "gas_deposition" in e.field]
        assert len(dep_errors) == 0

    def test_gas_dep_no_modelopt_warning(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=0.5, henry_constant=0.011,
            ),
            dep_enabled=False,
        ))
        warnings = [e for e in result.errors
                    if "deposition" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1

    def test_gas_dep_invalid_diffusivity(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=-0.1, alpha_r=1000.0,
                reactivity=0.5, henry_constant=0.011,
            ),
        ))
        errors = [e for e in result.errors if "diffusivity" in e.field]
        assert len(errors) >= 1

    def test_gas_dep_invalid_reactivity(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=1.5, henry_constant=0.011,
            ),
        ))
        errors = [e for e in result.errors if "reactivity" in e.field]
        assert len(errors) >= 1

    def test_gas_dep_missing_henry_and_vd(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=0.5,
            ),
        ))
        errors = [e for e in result.errors if "henry" in e.message.lower() or "dep_velocity" in e.message.lower()]
        assert len(errors) >= 1

    def test_valid_particle_deposition(self):
        result = Validator.validate(self._project_with_deposition(
            particle_dep=ParticleDepositionParams(
                diameters=[1.0, 5.0, 10.0],
                mass_fractions=[0.3, 0.5, 0.2],
                densities=[2.5, 2.5, 2.5],
            ),
        ))
        dep_errors = [e for e in result.errors
                      if "particle_deposition" in e.field]
        assert len(dep_errors) == 0

    def test_particle_mismatched_lengths(self):
        result = Validator.validate(self._project_with_deposition(
            particle_dep=ParticleDepositionParams(
                diameters=[1.0, 5.0],
                mass_fractions=[0.5, 0.5],
                densities=[2.5],  # wrong length
            ),
        ))
        errors = [e for e in result.errors if "same length" in e.message]
        assert len(errors) >= 1

    def test_particle_too_many_categories(self):
        result = Validator.validate(self._project_with_deposition(
            particle_dep=ParticleDepositionParams(
                diameters=list(range(1, 22)),
                mass_fractions=[1.0/21]*21,
                densities=[2.5]*21,
            ),
        ))
        errors = [e for e in result.errors if "20" in e.message]
        assert len(errors) >= 1

    def test_particle_fractions_not_summing(self):
        result = Validator.validate(self._project_with_deposition(
            particle_dep=ParticleDepositionParams(
                diameters=[1.0, 5.0],
                mass_fractions=[0.3, 0.3],  # sums to 0.6
                densities=[2.5, 2.5],
            ),
        ))
        warnings = [e for e in result.errors
                    if "mass_fractions" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1

    def test_particle_negative_diameter(self):
        result = Validator.validate(self._project_with_deposition(
            particle_dep=ParticleDepositionParams(
                diameters=[-1.0, 5.0],
                mass_fractions=[0.5, 0.5],
                densities=[2.5, 2.5],
            ),
        ))
        errors = [e for e in result.errors if "diameters" in e.field and "must be > 0" in e.message]
        assert len(errors) >= 1

    def test_invalid_output_type(self):
        project = _make_valid_project(
            output=OutputPathway(output_type="INVALID"),
        )
        result = Validator.validate(project)
        errors = [e for e in result.errors if "output_type" in e.field]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Event Processing Validation
# ---------------------------------------------------------------------------

class TestEventValidation:
    """Test event processing validation."""

    def _project_with_events(self, events, eventfil="events.inp"):
        control = ControlPathway(
            title_one="Test", pollutant_id="OTHER",
            averaging_periods=["ANNUAL"],
            eventfil=eventfil,
        )
        return _make_valid_project(
            control=control,
            **{"events": EventPathway(events=events)} if events else {},
        )

    def test_valid_events(self):
        project = _make_valid_project(
            control=ControlPathway(
                title_one="Test", eventfil="events.inp",
            ),
        )
        project.events = EventPathway(events=[
            EventPeriod("EVT01", "24010101", "24010124"),
        ])
        result = Validator.validate(project)
        ev_errors = [e for e in result.errors if "EventPathway" in e.pathway]
        assert len(ev_errors) == 0

    def test_empty_events_list(self):
        project = _make_valid_project()
        project.events = EventPathway(events=[])
        result = Validator.validate(project)
        errors = [e for e in result.errors if "no event periods" in e.message]
        assert len(errors) >= 1

    def test_event_name_too_long(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
        )
        project.events = EventPathway(events=[
            EventPeriod("TOOLONGNAME", "24010101", "24010124"),
        ])
        result = Validator.validate(project)
        errors = [e for e in result.errors if "exceeds 8" in e.message]
        assert len(errors) >= 1

    def test_duplicate_event_names(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
        )
        project.events = EventPathway(events=[
            EventPeriod("EVT01", "24010101", "24010124"),
            EventPeriod("EVT01", "24020101", "24020224"),
        ])
        result = Validator.validate(project)
        errors = [e for e in result.errors if "duplicate" in e.message]
        assert len(errors) >= 1

    def test_invalid_date_format(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
        )
        project.events = EventPathway(events=[
            EventPeriod("EVT01", "2024010", "24010124"),  # 7 digits
        ])
        result = Validator.validate(project)
        errors = [e for e in result.errors if "YYMMDDHH" in e.message]
        assert len(errors) >= 1

    def test_non_digit_date(self):
        project = _make_valid_project(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
        )
        project.events = EventPathway(events=[
            EventPeriod("EVT01", "2401AB01", "24010124"),
        ])
        result = Validator.validate(project)
        errors = [e for e in result.errors if "YYMMDDHH" in e.message]
        assert len(errors) >= 1

    def test_missing_eventfil_warning(self):
        project = _make_valid_project()
        project.events = EventPathway(events=[
            EventPeriod("EVT01", "24010101", "24010124"),
        ])
        result = Validator.validate(project)
        warnings = [e for e in result.errors
                    if "eventfil" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1
