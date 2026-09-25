"""
Unit tests for PyAERMOD Configuration Validator

Tests validation logic for all pathways and cross-field checks.
"""

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DepositionMethod,
    DiscreteReceptor,
    EvalFile,
    EventLocation,
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    LineSource,
    MaxiFile,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    PolarGrid,
    PollutantType,
    RankFile,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    ScimOptions,
    SeasonHourFile,
    SourceGroupDefinition,
    SourcePathway,
    StreetCanyon,
    TerrainType,
    ToxxFile,
    VolumeSource,
)
from pyaermod.validator import ValidationError, ValidationResult, Validator

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
        assert any("half_life" in e.field and e.severity == "error" for e in result.errors)

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
        """Zero exit velocity is valid (passive stack); advanced validator
        may emit a *warning* but there should be no error-severity finding."""
        result = Validator.validate(self._project_with_point(exit_velocity=0.0))
        vel_errors = [
            e for e in result.errors
            if "exit_velocity" in e.field and e.severity == "error"
        ]
        assert len(vel_errors) == 0

    def test_negative_emission_rate(self):
        result = Validator.validate(self._project_with_point(emission_rate=-0.1))
        assert any("emission_rate" in e.field for e in result.errors)

    def test_zero_emission_rate_ok(self):
        """Zero emission is valid (placeholder source); advanced validator
        emits a warning but no error."""
        result = Validator.validate(self._project_with_point(emission_rate=0.0))
        er_errors = [
            e for e in result.errors
            if "emission_rate" in e.field and e.severity == "error"
        ]
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
# Street canyon validation
# ---------------------------------------------------------------------------

class TestStreetCanyonValidation:

    def _project_with_rline_canyon(self, building_height, street_width):
        sources = SourcePathway()
        sources.add_source(RLineSource(
            source_id="HWY1", x_start=0, y_start=0,
            x_end=1000, y_end=0, emission_rate=0.002,
            street_canyon=StreetCanyon(
                building_height=building_height,
                street_width=street_width,
            ),
        ))
        return _make_valid_project(sources=sources)

    def test_valid_canyon(self):
        result = Validator.validate(self._project_with_rline_canyon(20.0, 15.0))
        assert not any("street_canyon" in e.field for e in result.errors)

    def test_invalid_building_height(self):
        result = Validator.validate(self._project_with_rline_canyon(-5.0, 15.0))
        assert any("building_height" in e.field for e in result.errors)

    def test_invalid_street_width(self):
        result = Validator.validate(self._project_with_rline_canyon(20.0, 0.0))
        assert any("street_width" in e.field for e in result.errors)

    def test_rlinext_canyon_validation(self):
        sources = SourcePathway()
        sources.add_source(RLineExtSource(
            source_id="REXT1",
            x_start=0, y_start=0, z_start=1.5,
            x_end=500, y_end=0, z_end=1.5,
            street_canyon=StreetCanyon(building_height=-1.0, street_width=20.0),
        ))
        result = Validator.validate(_make_valid_project(sources=sources))
        assert any("building_height" in e.field for e in result.errors)


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
        sectors = [BackgroundSector(i, i*30.0) for i in range(13)]
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(sectors=sectors, sector_values={(1, "ANNUAL"): 5.0})
        ))
        bg_errors = [e for e in result.errors if "sectors" in e.field and "12" in e.message]
        assert len(bg_errors) >= 1

    def test_invalid_sector_direction(self):
        sectors = [BackgroundSector(1, -10.0)]
        result = Validator.validate(self._project_with_background(
            BackgroundConcentration(sectors=sectors, sector_values={(1, "ANNUAL"): 5.0})
        ))
        bg_errors = [e for e in result.errors if "start_direction" in e.message]
        assert len(bg_errors) >= 1

    def test_invalid_sector_id_in_values(self):
        sectors = [BackgroundSector(1, 0.0)]
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
        # GASDEPOS is an ALPHA keyword (E198), and ALPHA excludes DFAULT.
        control = ControlPathway(
            title_one="Test", pollutant_id="OTHER",
            averaging_periods=["ANNUAL"],
            calculate_dry_deposition=dep_enabled,
            alpha=True, regulatory_default=False,
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
                diffusivity=0.22, diffusivity_water=1.8e-5,
                cuticular_resistance=732.0, henry_constant=0.011,
            ),
        ))
        dep_errors = [e for e in result.errors
                      if "deposition" in e.field.lower() or "gas_deposition" in e.field]
        assert len(dep_errors) == 0

    def test_epa_testgas_values_are_accepted(self):
        """EPA's testgas deck: Da Dw rcl Henry = 0.08962 1.04E-5 2.51E4 557.0.

        The previous validator read the third field as a 0-1 reactivity
        and rejected AERMOD's own reference deck (audit follow-up 7).
        """
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0),
        ))
        assert not [e for e in result.errors if "gas_deposition" in e.field], result

    def test_gas_dep_no_modelopt_warning(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=0.22, diffusivity_water=1.8e-5,
                cuticular_resistance=732.0, henry_constant=0.011,
            ),
            dep_enabled=False,
        ))
        warnings = [e for e in result.errors
                    if "deposition" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1

    def test_gas_dep_invalid_diffusivity(self):
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(
                diffusivity=-0.1, diffusivity_water=1.8e-5,
                cuticular_resistance=732.0, henry_constant=0.011,
            ),
        ))
        errors = [e for e in result.errors if "diffusivity" in e.field]
        assert len(errors) >= 1

    @pytest.mark.parametrize("field_name", [
        "diffusivity", "diffusivity_water", "cuticular_resistance", "henry_constant",
    ])
    def test_gas_dep_zero_field_rejected_for_unknown_pollutant(self, field_name):
        """A 0 is E380 unless AERMOD has a built-in value for the pollutant."""
        kwargs = dict(diffusivity=0.22, diffusivity_water=1.8e-5,
                      cuticular_resistance=732.0, henry_constant=0.011)
        kwargs[field_name] = 0.0
        result = Validator.validate(self._project_with_deposition(
            gas_dep=GasDepositionParams(**kwargs),
        ))
        assert [e for e in result.errors if e.field == f"gas_deposition.{field_name}"]

    def test_gas_dep_zero_field_allowed_for_lookup_pollutant(self):
        """soset.f GASDEP substitutes its own value for a 0 field when the
        pollutant is HG0, HGII, TCDD, BAP, SO2 or NO2 (warning W473)."""
        project = self._project_with_deposition(
            gas_dep=GasDepositionParams(0.0, 0.0, 0.0, 0.0),
        )
        project.control.pollutant_id = "SO2"
        result = Validator.validate(project)
        assert not [e for e in result.errors if "gas_deposition" in e.field], result

    def test_gas_dep_requires_alpha(self):
        project = self._project_with_deposition(
            gas_dep=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0),
        )
        project.control.alpha = False
        result = Validator.validate(project)
        assert any("E198" in e.message for e in result.errors
                   if e.field == "gas_deposition"), result

    def test_gas_dep_conflicts_with_gasdepvd(self):
        project = self._project_with_deposition(
            gas_dep=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0),
        )
        project.control.gas_deposition_velocity = 0.01
        result = Validator.validate(project)
        assert any("E195" in e.message for e in result.errors
                   if e.field == "gas_deposition"), result

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
    """The EV pathway as evset.f checks it (EVPER, EVLOC, OEVENT, EVCARD)."""

    @staticmethod
    def _control(**kw):
        kw.setdefault("title_one", "Test")
        kw.setdefault("averaging_periods", ["1", "24"])
        kw.setdefault("eventfil", "events.inp")
        return ControlPathway(**kw)

    @staticmethod
    def _event(name="EVT01", **kw):
        kw.setdefault("averaging_period", 1)
        kw.setdefault("date", "88030214")
        kw.setdefault("location", EventLocation(500.0, 500.0))
        return EventPeriod(name, **kw)

    def _errors(self, events, control=None, **kw):
        project = _make_valid_project(control=control or self._control(), **kw)
        project.events = EventPathway(events=events)
        result = Validator.validate(project)
        return [e for e in result.errors if "EventPathway" in e.pathway]

    def test_valid_events(self):
        assert self._errors([self._event(), self._event("EVT02", averaging_period=24,
                                                        source_group="ALL")]) == []

    def test_empty_events_list(self):
        errors = [e for e in self._errors([]) if "no event periods" in e.message]
        assert len(errors) >= 1

    def test_event_name_longer_than_evname(self):
        # EVNAME is CHARACTER*10; AERMOD's own H001H01001 uses all ten.
        assert self._errors([self._event("H001H01001")]) == []
        errors = [e for e in self._errors([self._event("ELEVENCHARS")])
                  if "exceeds 10" in e.message]
        assert len(errors) >= 1

    def test_duplicate_event_names(self):
        errors = [e for e in self._errors([self._event(), self._event()])
                  if "duplicate" in e.message]
        assert len(errors) >= 1

    @pytest.mark.parametrize("date", ["2024010", "2401AB01", "202401011"])
    def test_invalid_date_format(self, date):
        errors = [e for e in self._errors([self._event(date=date)]) if "YYMMDDHH" in e.message]
        assert len(errors) >= 1

    def test_averaging_period_must_be_on_avertime_and_at_most_24(self):
        errors = self._errors([self._event(averaging_period=3)])
        assert any("not on AVERTIME" in e.message for e in errors)
        errors = self._errors([self._event(averaging_period=720)],
                              control=self._control(averaging_periods=["1", "MONTH", "720"]))
        assert any("24 hours or less" in e.message for e in errors)

    def test_source_group_must_be_defined(self):
        errors = self._errors([self._event(source_group="G9")])
        assert any("not defined" in e.message for e in errors)
        sources = SourcePathway(sources=[PointSource("STK1", 0, 0, stack_height=30.0,
                                                     stack_diameter=1.5, stack_temp=400.0,
                                                     exit_velocity=10.0, emission_rate=1.0)],
                                group_definitions=[SourceGroupDefinition("G9", ["STK1"])])
        assert self._errors([self._event(source_group="G9")], sources=sources) == []

    def test_every_event_needs_a_location(self):
        errors = [e for e in self._errors([self._event(location=None)]) if "EVENTLOC" in e.message]
        assert len(errors) == 1

    def test_event_output_option(self):
        project = _make_valid_project(control=self._control(),
                                      output=OutputPathway(event_output="VERBOSE"))
        project.events = EventPathway(events=[self._event()])
        result = Validator.validate(project)
        assert any("EVENTOUT" in e.message for e in result.errors)
        project.output.event_output = "SOCONT"
        assert not [e for e in Validator.validate(project).errors if "EVENTOUT" in e.message]

    def test_missing_eventfil_warning(self):
        project = _make_valid_project(control=self._control(eventfil=None))
        project.events = EventPathway(events=[self._event()])
        result = Validator.validate(project)
        warnings = [e for e in result.errors
                    if "eventfil" in e.field and e.severity == "warning"]
        assert len(warnings) >= 1
        # An event deck itself carries no EVENTFIL and needs no receptors.
        project.event_processing = True
        project.receptors = ReceptorPathway()
        result = Validator.validate(project)
        assert not [e for e in result.errors if "eventfil" in e.field]
        assert not [e for e in result.errors if e.pathway == "ReceptorPathway"]

    def test_event_run_without_events(self):
        project = _make_valid_project(control=self._control())
        project.event_processing = True
        result = Validator.validate(project)
        assert any("no events" in e.message for e in result.errors)


class TestMeteorologyOptionsValidation:
    """meset.f DAYRNG / NUMYR / WSCATS / SCIMIT / TURBOPT (probes 26-27)."""

    def _errors(self, control=None, **met_kw):
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl", **met_kw)
        kw = {"meteorology": met}
        if control is not None:
            kw["control"] = control
        result = Validator.validate(_make_valid_project(**kw))
        return [e.message for e in result.errors if e.pathway == "MeteorologyPathway"]

    def test_dayrange_field_forms(self):
        assert self._errors(day_ranges=["50", "50-60", "3/15", "3/15-4/30"]) == []
        assert any("Julian" in m for m in self._errors(day_ranges=["March"]))
        assert any("Julian" in m for m in self._errors(day_ranges=["3/15/1988"]))

    def test_dayrange_and_scim_exclude_each_other(self):
        control = ControlPathway(title_one="t", averaging_periods=["ANNUAL"], extra_model_options=["SCIM"])
        assert any("E154" in m for m in self._errors(control, day_ranges=["50"]))

    def test_numyears_positive_integer(self):
        assert self._errors(num_years=5) == []
        assert any("positive integer" in m for m in self._errors(num_years=0))

    def test_windcats_count_range_and_order(self):
        assert self._errors(wind_speed_categories=[1.54, 3.09, 5.14, 8.23, 10.8]) == []
        assert any("exactly 5" in m for m in self._errors(wind_speed_categories=[1.54, 3.09]))
        assert any("1-20" in m for m in self._errors(wind_speed_categories=[0.5, 3.09, 5.14, 8.23, 10.8]))
        assert any("increase" in m for m in self._errors(wind_speed_categories=[3.09, 1.54, 5.14, 8.23, 10.8]))

    def test_scimbyhr_needs_scim_and_valid_hours(self):
        assert any("MODELOPT SCIM" in m for m in self._errors(scim=ScimOptions(1, 25)))
        control = ControlPathway(title_one="t", averaging_periods=["ANNUAL"], extra_model_options=["SCIM"])
        assert self._errors(control, scim=ScimOptions(1, 25)) == []
        assert any("1-24" in m for m in self._errors(control, scim=ScimOptions(25, 25)))
        assert any("at least 1" in m for m in self._errors(control, scim=ScimOptions(1, 0)))

    def test_turbulence_option_must_be_one_of_the_nine(self):
        assert self._errors(turbulence_option="NOSWCO") == []
        assert any("NOTURB" in m for m in self._errors(turbulence_option="NOTURBULENCE"))


class TestOutputFileValidation:
    """ouset.f NOHEADER / OURANK / OUSEAS / OUEVAL / OUTOXX and OUTQA (probes 28-28c)."""

    def _errors(self, control=None, sources=None, **out_kw):
        kw = {"output": OutputPathway(**out_kw)}
        if control is not None:
            kw["control"] = control
        if sources is not None:
            kw["sources"] = sources
        result = Validator.validate(_make_valid_project(**kw))
        return [e.message for e in result.errors if e.pathway == "OutputPathway" and e.severity == "error"]

    def test_noheader_names_types_in_use(self):
        assert self._errors(no_header=["ALL"]) == []
        assert any("E164" in m for m in self._errors(no_header=["MAXIFILE"]))
        assert self._errors(no_header=["MAXIFILE"],
                            maxi_files=[MaxiFile("ANNUAL", "ALL", 1.0, "m.dat")]) == []
        assert any("not an output file type" in m for m in self._errors(no_header=["SUMMFILE"]))

    def test_rankfile_period_and_repeats(self):
        control = ControlPathway(title_one="t", averaging_periods=["1", "24"])
        assert self._errors(control, rank_files=[RankFile("1", 10, "r.rnk"), RankFile("24", 10, "s.rnk")]) == []
        assert any("AVERTIME" in m for m in self._errors(control, rank_files=[RankFile("3", 10, "r.rnk")]))
        assert any("E211" in m for m in self._errors(
            control, rank_files=[RankFile("1", 10, "r.rnk"), RankFile("1", 5, "s.rnk")]))

    def test_seasonhr_group_and_scim(self):
        assert self._errors(season_hour_files=[SeasonHourFile("ALL", "s.dat")]) == []
        assert any("not defined" in m for m in self._errors(season_hour_files=[SeasonHourFile("G9", "s.dat")]))
        control = ControlPathway(title_one="t", averaging_periods=["ANNUAL"], extra_model_options=["SCIM"])
        assert any("E154" in m for m in self._errors(control, season_hour_files=[SeasonHourFile("ALL", "s.dat")]))

    def test_evalfile_source_must_exist(self):
        assert self._errors(eval_files=[EvalFile("STK1", "e.dat")]) == []
        assert any("not defined" in m for m in self._errors(eval_files=[EvalFile("STK9", "e.dat")]))

    def test_toxxfile_period(self):
        control = ControlPathway(title_one="t", averaging_periods=["1", "24"])
        assert self._errors(control, toxx_files=[ToxxFile("1", 1.0, "t.dat")]) == []
        assert any("AVERTIME" in m for m in self._errors(control, toxx_files=[ToxxFile("3", 1.0, "t.dat")]))
        result = Validator.validate(_make_valid_project(
            control=control, output=OutputPathway(toxx_files=[ToxxFile("24", 1.0, "t.dat")])))
        assert any("W296" in e.message and e.severity == "warning" for e in result.errors)


# ---------------------------------------------------------------------------
# Parametrized validation tests
# ---------------------------------------------------------------------------


class TestParametrizedValidation:
    """Parametrized tests for common validation patterns across source types."""

    # -- PointSource field validation --

    @pytest.mark.parametrize(
        "field_name,value,should_error",
        [
            ("stack_height", -1.0, True),
            ("stack_height", 0.0, True),
            ("stack_height", 1.0, False),
            ("stack_diameter", -1.0, True),
            ("stack_diameter", 0.0, True),
            ("stack_diameter", 1.0, False),
            ("stack_temp", -1.0, True),
            ("stack_temp", 0.0, True),
            ("stack_temp", 300.0, False),
            ("exit_velocity", -1.0, True),
            ("exit_velocity", 0.0, False),
            ("exit_velocity", 10.0, False),
            ("emission_rate", -1.0, True),
            ("emission_rate", 0.0, False),
            ("emission_rate", 1.0, False),
        ],
        ids=[
            "stack_height_negative",
            "stack_height_zero",
            "stack_height_positive",
            "stack_diameter_negative",
            "stack_diameter_zero",
            "stack_diameter_positive",
            "stack_temp_negative",
            "stack_temp_zero",
            "stack_temp_positive",
            "exit_velocity_negative",
            "exit_velocity_zero",
            "exit_velocity_positive",
            "emission_rate_negative",
            "emission_rate_zero",
            "emission_rate_positive",
        ],
    )
    def test_point_source_field_validation(self, field_name, value, should_error):
        """Validate individual PointSource numeric fields."""
        defaults = dict(
            source_id="STK1",
            x_coord=500.0,
            y_coord=500.0,
            stack_height=30.0,
            stack_diameter=1.5,
            stack_temp=400.0,
            exit_velocity=10.0,
            emission_rate=1.0,
        )
        defaults[field_name] = value
        sources = SourcePathway()
        sources.add_source(PointSource(**defaults))
        project = _make_valid_project(sources=sources)
        result = Validator.validate(project)
        field_errors = [
            e
            for e in result.errors
            if field_name in e.field and e.severity == "error"
        ]
        if should_error:
            assert len(field_errors) >= 1, (
                f"Expected validation error for {field_name}={value}"
            )
        else:
            assert len(field_errors) == 0, (
                f"Unexpected validation error for {field_name}={value}: {field_errors}"
            )

    # -- Emission rate validation across multiple source types --

    @pytest.mark.parametrize(
        "source_cls,base_kwargs,emission_value,should_error",
        [
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 10.0,
                    "initial_vertical_dimension": 10.0,
                },
                -1.0,
                True,
            ),
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 10.0,
                    "initial_vertical_dimension": 10.0,
                },
                0.0,
                False,
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 5.0,
                    "initial_vertical_dimension": 5.0,
                },
                -1.0,
                True,
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 5.0,
                    "initial_vertical_dimension": 5.0,
                },
                0.0,
                False,
            ),
            (
                LineSource,
                {
                    "source_id": "L1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "initial_lateral_dimension": 1.0,
                },
                -1.0,
                True,
            ),
            (
                LineSource,
                {
                    "source_id": "L1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "initial_lateral_dimension": 1.0,
                },
                0.0,
                False,
            ),
            (
                AreaCircSource,
                {
                    "source_id": "C1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "radius": 50.0,
                },
                -1.0,
                True,
            ),
            (
                AreaCircSource,
                {
                    "source_id": "C1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "radius": 50.0,
                },
                0.0,
                False,
            ),
            (
                AreaPolySource,
                {
                    "source_id": "P1",
                    "vertices": [(0, 0), (100, 0), (100, 100), (0, 100)],
                },
                -1.0,
                True,
            ),
            (
                AreaPolySource,
                {
                    "source_id": "P1",
                    "vertices": [(0, 0), (100, 0), (100, 100), (0, 100)],
                },
                0.0,
                False,
            ),
            (
                OpenPitSource,
                {
                    "source_id": "OP1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "x_dimension": 100.0,
                    "y_dimension": 100.0,
                    "pit_volume": 100000.0,
                },
                -1.0,
                True,
            ),
            (
                OpenPitSource,
                {
                    "source_id": "OP1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "x_dimension": 100.0,
                    "y_dimension": 100.0,
                    "pit_volume": 100000.0,
                },
                0.0,
                False,
            ),
            (
                RLineExtSource,
                {
                    "source_id": "RX1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "z_start": 0.5,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "z_end": 0.5,
                    "road_width": 30.0,
                },
                -1.0,
                True,
            ),
            (
                RLineExtSource,
                {
                    "source_id": "RX1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "z_start": 0.5,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "z_end": 0.5,
                    "road_width": 30.0,
                },
                0.0,
                False,
            ),
        ],
        ids=[
            "AreaSource_negative",
            "AreaSource_zero",
            "VolumeSource_negative",
            "VolumeSource_zero",
            "LineSource_negative",
            "LineSource_zero",
            "AreaCircSource_negative",
            "AreaCircSource_zero",
            "AreaPolySource_negative",
            "AreaPolySource_zero",
            "OpenPitSource_negative",
            "OpenPitSource_zero",
            "RLineExtSource_negative",
            "RLineExtSource_zero",
        ],
    )
    def test_emission_rate_across_source_types(
        self, source_cls, base_kwargs, emission_value, should_error
    ):
        """Negative emission_rate must error; zero emission_rate is valid (placeholder)."""
        kwargs = {**base_kwargs, "emission_rate": emission_value}
        sources = SourcePathway()
        sources.add_source(source_cls(**kwargs))
        project = _make_valid_project(sources=sources)
        result = Validator.validate(project)
        er_errors = [
            e
            for e in result.errors
            if "emission_rate" in e.field and e.severity == "error"
        ]
        if should_error:
            assert len(er_errors) >= 1, (
                f"Expected emission_rate error for {source_cls.__name__} "
                f"with value {emission_value}"
            )
        else:
            assert len(er_errors) == 0, (
                f"Unexpected emission_rate error for {source_cls.__name__} "
                f"with value {emission_value}: {er_errors}"
            )

    # -- Release height validation across source types that have it --

    @pytest.mark.parametrize(
        "source_cls,base_kwargs",
        [
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 10.0,
                    "initial_vertical_dimension": 10.0,
                    "emission_rate": 1.0,
                },
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "initial_lateral_dimension": 5.0,
                    "initial_vertical_dimension": 5.0,
                    "emission_rate": 1.0,
                },
            ),
            (
                AreaCircSource,
                {
                    "source_id": "C1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "radius": 50.0,
                    "emission_rate": 1.0,
                },
            ),
            (
                AreaPolySource,
                {
                    "source_id": "P1",
                    "vertices": [(0, 0), (100, 0), (100, 100), (0, 100)],
                    "emission_rate": 1.0,
                },
            ),
            (
                LineSource,
                {
                    "source_id": "L1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "emission_rate": 1.0,
                    "initial_lateral_dimension": 1.0,
                },
            ),
            (
                OpenPitSource,
                {
                    "source_id": "OP1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "x_dimension": 100.0,
                    "y_dimension": 100.0,
                    "pit_volume": 100000.0,
                    "emission_rate": 0.01,
                },
            ),
        ],
        ids=[
            "AreaSource",
            "VolumeSource",
            "AreaCircSource",
            "AreaPolySource",
            "LineSource",
            "OpenPitSource",
        ],
    )
    def test_negative_release_height_across_source_types(
        self, source_cls, base_kwargs
    ):
        """Negative release_height must produce a validation error."""
        kwargs = {**base_kwargs, "release_height": -1.0}
        sources = SourcePathway()
        sources.add_source(source_cls(**kwargs))
        project = _make_valid_project(sources=sources)
        result = Validator.validate(project)
        rh_errors = [
            e
            for e in result.errors
            if "release_height" in e.field and e.severity == "error"
        ]
        assert len(rh_errors) >= 1, (
            f"Expected release_height error for {source_cls.__name__}"
        )


# ============================================================================
# AERMOD's own cross-checks for the restart, background and design-value
# keywords (coset.f E150/E195/E198/E602/E605/E171/E222/E227, ouset.f
# E153/E162/E163/E272/E273/E290)
# ============================================================================

def _errors(project, field_substring):
    result = Validator.validate(project, advanced=False)
    return [e for e in result.errors if field_substring in e.field and e.severity == "error"]


class TestRestartValidation:
    def test_multiyear_with_savefile_or_initfile_is_rejected(self):
        from pyaermod.input_generator import InitFile, MultiYear, SaveFile
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.PM10,
                                 multiyear=MultiYear("y.sav"), save_file=SaveFile("s.sav"),
                                 init_file=InitFile("i.sav"))
        project = _make_valid_project(control=control)
        assert _errors(project, "save_file") and _errors(project, "init_file")

    def test_multiyear_alone_is_accepted_for_pm10(self):
        from pyaermod.input_generator import MultiYear
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.PM10,
                                 multiyear=MultiYear("y.sav", "x.sav"))
        assert not _errors(_make_valid_project(control=control), "multiyear")

    def test_multiyear_pollutant_restriction(self):
        from pyaermod.input_generator import MultiYear
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.CO,
                                 multiyear=MultiYear("y.sav"))
        assert _errors(_make_valid_project(control=control), "multiyear")


class TestGasDepositionDefaultValidation:
    def _control(self, **kwargs):
        return ControlPathway(title_one="t", pollutant_id=PollutantType.SO2, **kwargs)

    def test_needs_alpha(self):
        from pyaermod.input_generator import GasDepositionDefaults
        c = self._control(gas_deposition_defaults=GasDepositionDefaults(0.5, 0.5, 0.5))
        assert _errors(_make_valid_project(control=c), "gas_deposition_defaults")
        c = self._control(alpha=True, regulatory_default=False,
                          gas_deposition_defaults=GasDepositionDefaults(0.5, 0.5, 0.5))
        assert not _errors(_make_valid_project(control=c), "gas_deposition")

    def test_gasdepvd_excludes_seasons_and_land_use(self):
        c = self._control(alpha=True, regulatory_default=False, gas_deposition_velocity=0.01,
                          gas_deposition_seasons=[1] * 12, gas_deposition_land_use=[1] * 36)
        p = _make_valid_project(control=c)
        assert _errors(p, "gas_deposition_seasons") and _errors(p, "gas_deposition_land_use")

    def test_season_and_land_use_counts_and_ranges(self):
        c = self._control(alpha=True, regulatory_default=False,
                          gas_deposition_seasons=[1] * 11, gas_deposition_land_use=[10] * 36)
        p = _make_valid_project(control=c)
        assert any("12 values" in e.message for e in _errors(p, "gas_deposition_seasons"))
        assert any("1..9" in e.message for e in _errors(p, "gas_deposition_land_use"))


class TestBackgroundKeywordValidation:
    def _project(self, chemistry):
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.NO2,
                                 averaging_periods=["1"], chemistry=chemistry)
        return _make_valid_project(control=control)

    def test_nox_keywords_need_grsm(self):
        from pyaermod.input_generator import ChemistryMethod, ChemistryOptions, NOxBackground, OzoneData
        chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=OzoneData(uniform_value=40.0),
                                nox_background=NOxBackground(value=10.0))
        assert _errors(self._project(chem), "nox_background")

    def test_value_and_profile_conflict(self):
        from pyaermod.input_generator import (
            ChemistryMethod,
            ChemistryOptions,
            NOxBackground,
            OzoneData,
            TemporalValues,
        )
        chem = ChemistryOptions(method=ChemistryMethod.GRSM, ozone_data=OzoneData(uniform_value=40.0),
                                nox_background=NOxBackground(value=10.0, varying=TemporalValues("ANNUAL", [1.0])))
        assert any("E605" in e.message for e in _errors(self._project(chem), "nox_background"))

    def test_sector_form_without_sectors(self):
        from pyaermod.input_generator import BackgroundSpec, ChemistryMethod, ChemistryOptions, NOxBackground, OzoneData
        chem = ChemistryOptions(method=ChemistryMethod.GRSM, ozone_data=OzoneData(uniform_value=40.0),
                                nox_background=NOxBackground(by_sector={1: BackgroundSpec(value=1.0)}))
        assert any("E171" in e.message for e in _errors(self._project(chem), "nox_background"))
        chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=OzoneData(sector_values={1: 40.0}))
        assert any("E171" in e.message for e in _errors(self._project(chem), "sector_values"))

    def test_sector_geometry(self):
        from pyaermod.input_generator import BackgroundSpec, ChemistryMethod, ChemistryOptions, OzoneData
        oz = OzoneData(sectors=[0.0, 20.0], by_sector={1: BackgroundSpec(value=40.0), 2: BackgroundSpec(value=40.0)})
        chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=oz)
        assert any("30 degrees" in e.message for e in _errors(self._project(chem), "sectors"))
        oz = OzoneData(sectors=[0.0, 180.0], by_sector={3: BackgroundSpec(value=40.0)})
        chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=oz)
        assert any("not one of the 2" in e.message for e in _errors(self._project(chem), "by_sector[3]"))

    def test_units_and_profile_length(self):
        from pyaermod.input_generator import ChemistryMethod, ChemistryOptions, OzoneData, TemporalValues
        oz = OzoneData(uniform_value=40.0, uniform_units="PPT", varying=TemporalValues("SEASON", [1.0]))
        chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=oz)
        errs = _errors(self._project(chem), "ozone_data")
        assert any("PPT" in e.message for e in errs)
        assert any("SEASON needs 4 values" in e.message for e in errs)

    def test_well_formed_grsm_background_passes(self):
        from pyaermod.input_generator import (
            BackgroundSpec,
            ChemistryMethod,
            ChemistryOptions,
            NOxBackground,
            OzoneData,
            TemporalValues,
        )
        chem = ChemistryOptions(
            method=ChemistryMethod.GRSM,
            ozone_data=OzoneData(sectors=[0.0, 180.0], units="PPB",
                                 by_sector={1: BackgroundSpec(value=40.0, value_units="PPB"),
                                            2: BackgroundSpec(varying=TemporalValues("SEASON", [1, 2, 3, 4]))}),
            nox_background=NOxBackground(hourly_file="nox.dat", file_units="PPB", file_format="FREE"),
        )
        result = Validator.validate(self._project(chem), advanced=False)
        assert not [e for e in result.errors if e.severity == "error"], str(result)


class TestDesignValueOutputValidation:
    def _project(self, output, pollutant=PollutantType.SO2, periods=("1",), **control_kwargs):
        control = ControlPathway(title_one="t", pollutant_id=pollutant,
                                 averaging_periods=list(periods), **control_kwargs)
        return _make_valid_project(control=control, output=output)

    def test_naaqs_processing_rules(self):
        c = ControlPathway(title_one="t", pollutant_id=PollutantType.SO2, averaging_periods=["1"])
        assert Validator.naaqs_processing(c) == "1-hour"
        c.averaging_periods = ["1", "ANNUAL"]
        assert Validator.naaqs_processing(c) == "1-hour"
        c.averaging_periods = ["1", "24"]
        assert Validator.naaqs_processing(c) is None
        c = ControlPathway(title_one="t", pollutant_id=PollutantType.PM25, averaging_periods=["24", "ANNUAL"])
        assert Validator.naaqs_processing(c) == "24-hour"
        c.averaging_periods = ["24", "PERIOD"]
        assert Validator.naaqs_processing(c) is None

    def test_max_daily_needs_naaqs_processing(self):
        from pyaermod.input_generator import MaxDailyFile
        out = OutputPathway(max_daily_files=[MaxDailyFile("ALL", "md.dat")])
        assert not _errors(self._project(out), "max_daily")
        assert _errors(self._project(out, periods=("1", "24")), "max_daily")
        assert _errors(self._project(out, pollutant=PollutantType.CO), "max_daily")

    def test_maxdcont_rank_range(self):
        from pyaermod.input_generator import MaxDailyContribution
        out = OutputPathway(receptor_table_rank=4,
                            max_daily_contributions=[MaxDailyContribution("ALL", 8, "f", lower_rank=8)])
        assert any("E290" in e.message for e in _errors(self._project(out), "max_daily_contributions"))
        out.receptor_table_rank = 8
        assert not _errors(self._project(out), "max_daily_contributions")
        out.max_daily_contributions = [MaxDailyContribution("ALL", 8, "f", lower_rank=4)]
        assert any("E272" in e.message for e in _errors(self._project(out), "max_daily_contributions"))

    def test_thresh_form_needs_room_beyond_the_design_rank(self):
        from pyaermod.input_generator import MaxDailyContribution
        out = OutputPathway(receptor_table_rank=8,
                            max_daily_contributions=[MaxDailyContribution("ALL", 4, "f", threshold=196.0)])
        assert any("E273" in e.message for e in _errors(self._project(out), "max_daily_contributions"))
        out.receptor_table_rank = 9
        assert not _errors(self._project(out), "max_daily_contributions")
        # NO2 and PM2.5 need more than 12.
        out.receptor_table_rank = 12
        assert _errors(self._project(out, pollutant=PollutantType.NO2), "max_daily_contributions")

    def test_maxdcont_excludes_restart(self):
        from pyaermod.input_generator import MaxDailyContribution, SaveFile
        out = OutputPathway(receptor_table_rank=4,
                            max_daily_contributions=[MaxDailyContribution("ALL", 4, "f", lower_rank=4)])
        errs = _errors(self._project(out, save_file=SaveFile("s.sav")), "max_daily_contributions")
        assert any("E153" in e.message for e in errs)

    def test_fileform_value(self):
        assert _errors(self._project(OutputPathway(file_format="BIN")), "file_format")
        assert not _errors(self._project(OutputPathway(file_format="EXP")), "file_format")


class TestBackgroundValidationEdges:
    def _project(self, chemistry):
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.NO2,
                                 averaging_periods=["1"], chemistry=chemistry)
        return _make_valid_project(control=control)

    def test_unknown_temporal_flag_and_bad_units(self):
        from pyaermod.input_generator import (
            ChemistryMethod,
            ChemistryOptions,
            NOxBackground,
            OzoneData,
            TemporalValues,
        )
        chem = ChemistryOptions(
            method=ChemistryMethod.GRSM,
            ozone_data=OzoneData(uniform_value=40.0, units="PPT"),
            nox_background=NOxBackground(varying=TemporalValues("WEEKLY", [1.0]), units="MG/M3"),
        )
        errs = _errors(self._project(chem), "")
        assert any("unknown temporal flag 'WEEKLY'" in e.message for e in errs)
        assert any(e.field == "ozone_data.units" for e in errs)
        assert any(e.field == "nox_background.units" for e in errs)

    def test_sector_count_and_range(self):
        from pyaermod.input_generator import BackgroundSpec, ChemistryMethod, ChemistryOptions, OzoneData
        chem = ChemistryOptions(method=ChemistryMethod.OLM,
                                ozone_data=OzoneData(sectors=[0.0], by_sector={1: BackgroundSpec(value=40.0)}))
        assert any("2 to 6" in e.message for e in _errors(self._project(chem), "sectors"))
        chem = ChemistryOptions(method=ChemistryMethod.OLM,
                                ozone_data=OzoneData(sectors=[-10.0, 180.0], by_sector={1: BackgroundSpec(value=40.0)}))
        assert any("0..360" in e.message for e in _errors(self._project(chem), "sectors"))


class TestRestartAndGasDepositionEdges:
    def test_empty_multiyear_save_file(self):
        from pyaermod.input_generator import MultiYear
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.PM10, multiyear=MultiYear(""))
        assert _errors(_make_valid_project(control=control), "multiyear.save_file")

    def test_non_positive_deposition_velocity(self):
        control = ControlPathway(title_one="t", pollutant_id=PollutantType.SO2, alpha=True,
                                 regulatory_default=False, gas_deposition_velocity=0.0)
        assert any("> 0" in e.message for e in _errors(_make_valid_project(control=control), "gas_deposition_velocity"))
