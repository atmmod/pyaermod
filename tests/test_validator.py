"""
Unit tests for PyAERMOD Configuration Validator

Tests validation logic for all pathways and cross-field checks.
"""

import pytest
from pyaermod_input_generator import (
    ControlPathway,
    SourcePathway,
    PointSource,
    AreaSource,
    AreaCircSource,
    AreaPolySource,
    VolumeSource,
    LineSource,
    RLineSource,
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
from pyaermod_validator import Validator, ValidationResult, ValidationError


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
