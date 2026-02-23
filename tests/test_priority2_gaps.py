"""
Tests for Priority 2 coverage gaps.

Covers:
- Validator: background sector values, deposition params, RLineExt
  depression/barrier, BuoyLine segment edge cases, source group validation
- Runner: batch exception handling, PATH search success, run success logging,
  _extract_error_message exception paths, validate_input error reading
- Output parser: source/receptor parsing with synthetic data, model options,
  terrain type detection, concentration rank field
"""

import subprocess
from concurrent.futures import Future
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    GasDepositionParams,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    ReceptorPathway,
    RLineExtSource,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VolumeSource,
)
from pyaermod.output_parser import AERMODOutputParser
from pyaermod.runner import AERMODRunResult, AERMODRunner
from pyaermod.validator import Validator


# ============================================================================
# Helper: quickly build a validatable project with a given source
# ============================================================================


def _project_with_source(source, background=None, group_definitions=None):
    sp = SourcePathway(sources=[source], background=background)
    if group_definitions:
        sp.group_definitions = group_definitions
    return AERMODProject(
        control=ControlPathway(title_one="T"),
        sources=sp,
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(x_init=0, x_num=3, x_delta=100,
                          y_init=0, y_num=3, y_delta=100),
        ]),
        meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
        output=OutputPathway(),
    )


def _point():
    return PointSource(
        source_id="S1", x_coord=0, y_coord=0,
        stack_height=20, stack_temp=350, exit_velocity=10,
        stack_diameter=1, emission_rate=1,
    )


# ============================================================================
# Validator: background sector error paths (lines 272, 277)
# ============================================================================


class TestBackgroundSectorValidation:
    """Validator._validate_background: invalid sector_values period and negative value."""

    def test_invalid_averaging_period(self):
        bg = BackgroundConcentration(
            sectors=[BackgroundSector(sector_id=1, start_direction=0, end_direction=90)],
            sector_values={(1, "BOGUS"): 10.0},
        )
        project = _project_with_source(_point(), background=bg)
        result = Validator.validate(project)
        fields = [e.field for e in result.errors]
        assert "sector_values" in fields
        msgs = " ".join(e.message for e in result.errors)
        assert "BOGUS" in msgs

    def test_negative_sector_value(self):
        bg = BackgroundConcentration(
            sectors=[BackgroundSector(sector_id=1, start_direction=0, end_direction=90)],
            sector_values={(1, "ANNUAL"): -5.0},
        )
        project = _project_with_source(_point(), background=bg)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert ">= 0" in msgs


# ============================================================================
# Validator: deposition parameter edge cases (lines 354, 382)
# ============================================================================


class TestDepositionValidation:
    """Validator._validate_deposition: mismatched lengths, negative densities."""

    def test_mismatched_diameters_mass_fractions(self):
        src = PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1,
            particle_deposition=ParticleDepositionParams(
                diameters=[1.0, 2.0],
                mass_fractions=[0.5],  # wrong length
                densities=[1000.0, 1000.0],
            ),
        )
        project = _project_with_source(src)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "same length" in msgs

    def test_mismatched_diameters_densities(self):
        src = PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1,
            particle_deposition=ParticleDepositionParams(
                diameters=[1.0, 2.0],
                mass_fractions=[0.5, 0.5],
                densities=[1000.0],  # wrong length
            ),
        )
        project = _project_with_source(src)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "same length" in msgs

    def test_negative_density(self):
        src = PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1,
            particle_deposition=ParticleDepositionParams(
                diameters=[1.0],
                mass_fractions=[1.0],
                densities=[-500.0],  # negative
            ),
        )
        project = _project_with_source(src)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "densities" in msgs

    def test_negative_diameter(self):
        src = PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1,
            particle_deposition=ParticleDepositionParams(
                diameters=[-1.0],
                mass_fractions=[1.0],
                densities=[1000.0],
            ),
        )
        project = _project_with_source(src)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "diameters" in msgs


# ============================================================================
# Validator: RLineExt depression/barrier (lines 643, 655, 661)
# ============================================================================


class TestRLineExtValidation:
    """Validator._validate_rlinext_source: depression and barrier edge cases."""

    def _rlinext(self, **kwargs):
        defaults = dict(
            source_id="RL1",
            x_start=0, y_start=0, z_start=0,
            x_end=100, y_end=0, z_end=0,
            emission_rate=0.01, dcl=10, road_width=20, init_sigma_z=1.5,
        )
        defaults.update(kwargs)
        return RLineExtSource(**defaults)

    def test_positive_depression_depth_error(self):
        """Depression depth must be <= 0 (negative = below grade)."""
        src = self._rlinext(depression_depth=5.0, depression_wtop=10.0, depression_wbottom=5.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        fields = [e.field for e in result.errors]
        assert "depression_depth" in fields

    def test_negative_depression_wtop_error(self):
        src = self._rlinext(depression_depth=-2.0, depression_wtop=-1.0, depression_wbottom=5.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        fields = [e.field for e in result.errors]
        assert "depression_wtop" in fields

    def test_negative_depression_wbottom_error(self):
        src = self._rlinext(depression_depth=-2.0, depression_wtop=10.0, depression_wbottom=-3.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        fields = [e.field for e in result.errors]
        assert "depression_wbottom" in fields

    def test_wbottom_greater_than_wtop_error(self):
        src = self._rlinext(depression_depth=-2.0, depression_wtop=5.0, depression_wbottom=10.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "depression_wtop" in msgs

    def test_negative_barrier_height_error(self):
        src = self._rlinext(barrier_height_2=-1.0, barrier_dcl_2=5.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        fields = [e.field for e in result.errors]
        assert "barrier_height_2" in fields

    def test_valid_depression_no_errors(self):
        src = self._rlinext(depression_depth=-2.0, depression_wtop=10.0, depression_wbottom=5.0)
        project = _project_with_source(src)
        result = Validator.validate(project)
        dep_errors = [e for e in result.errors if "depression" in e.field]
        assert len(dep_errors) == 0


# ============================================================================
# Validator: BuoyLine segment edge cases (lines 707, 717)
# ============================================================================


class TestBuoyLineSegmentValidation:
    """Validator._validate_buoyline_source: segment release height and zero-length."""

    def test_segment_release_height_above_3000(self):
        seg = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=3500,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
        )
        project = _project_with_source(blp)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "3000" in msgs

    def test_segment_zero_length_line(self):
        seg = BuoyLineSegment(
            source_id="BS1", x_start=50, y_start=50,
            x_end=50, y_end=50, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
        )
        project = _project_with_source(blp)
        result = Validator.validate(project)
        msgs = " ".join(e.message for e in result.errors)
        assert "zero-length" in msgs


# ============================================================================
# Validator: source group validation with BuoyLine (lines 788-789)
# ============================================================================


class TestSourceGroupValidationBuoyLine:
    """Validator._validate_source_groups: BuoyLine segment IDs in group validation."""

    def test_buoyline_segment_ids_in_group(self):
        seg1 = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        seg2 = BuoyLineSegment(
            source_id="BS2", x_start=100, y_start=0,
            x_end=200, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg1, seg2],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
        )
        group = SourceGroupDefinition(
            group_name="BLPGRP",
            member_source_ids=["BS1", "BS2"],
        )
        project = _project_with_source(blp, group_definitions=[group])
        result = Validator.validate(project)
        # BS1/BS2 are valid segment IDs, so no "unknown source" errors expected
        grp_errors = [e for e in result.errors if "BLPGRP" in str(e)]
        assert len(grp_errors) == 0

    def test_buoyline_unknown_member_in_group(self):
        seg = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
        )
        group = SourceGroupDefinition(
            group_name="BLPGRP",
            member_source_ids=["BS1", "UNKNOWN"],
        )
        project = _project_with_source(blp, group_definitions=[group])
        result = Validator.validate(project)
        msgs = " ".join(str(e) for e in result.errors)
        assert "UNKNOWN" in msgs


# ============================================================================
# Runner: batch exception handling (lines 326-337)
# ============================================================================


class TestBatchExceptionHandling:
    """Test run_batch() when a future raises an unexpected exception."""

    def test_future_exception_captured(self, tmp_path):
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")

        # Create a future that raises an exception
        exc_future = Future()
        exc_future.set_exception(RuntimeError("Unexpected crash"))

        mock_executor = MagicMock()
        mock_executor.submit.return_value = exc_future

        with patch("pyaermod.runner.ProcessPoolExecutor") as MockPool, \
             patch("pyaermod.runner.as_completed", return_value=iter([exc_future])):
            MockPool.return_value.__enter__ = MagicMock(return_value=mock_executor)
            MockPool.return_value.__exit__ = MagicMock(return_value=False)

            results = runner.run_batch(["test.inp"], n_workers=1)

        assert len(results) == 1
        assert not results[0].success
        assert "Unexpected crash" in results[0].error_message

    def test_future_exception_with_stop_on_error(self, tmp_path):
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")

        exc_future1 = Future()
        exc_future1.set_exception(RuntimeError("Crash 1"))
        exc_future2 = Future()
        exc_future2.set_exception(RuntimeError("Crash 2"))

        mock_executor = MagicMock()
        mock_executor.submit.side_effect = [exc_future1, exc_future2]

        with patch("pyaermod.runner.ProcessPoolExecutor") as MockPool, \
             patch("pyaermod.runner.as_completed", return_value=iter([exc_future1, exc_future2])):
            MockPool.return_value.__enter__ = MagicMock(return_value=mock_executor)
            MockPool.return_value.__exit__ = MagicMock(return_value=False)

            results = runner.run_batch(
                ["a.inp", "b.inp"], n_workers=1, stop_on_error=True
            )

        # Should have stopped after first exception
        assert len(results) == 1
        assert not results[0].success


# ============================================================================
# Runner: PATH search success (line 100), run success (line 189),
# validate_input error reading (lines 387-388)
# ============================================================================


class TestRunnerPathSearch:
    """Test AERMODRunner finding executable via shutil.which."""

    def test_which_finds_aermod(self, tmp_path):
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        with patch("shutil.which", return_value=str(fake_exe)):
            runner = AERMODRunner()
        assert runner.executable == fake_exe

    def test_run_success_logging(self, tmp_path):
        """Run that produces output file logs success (line 189)."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp = tmp_path / "test.inp"
        inp.write_text("CO STARTING\nCO FINISHED")

        # Create the output file that AERMOD would produce
        out_file = tmp_path / "test.out"
        out_file.write_text("AERMOD output")

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="DEBUG")
        with patch("pyaermod.runner.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = runner.run(str(inp), working_dir=str(tmp_path))

        assert result.success


class TestValidateInputErrorReading:
    """Test validate_input when file reading raises an exception."""

    def test_unreadable_file(self, tmp_path):
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")

        # Create a file that exists but simulate read error
        inp = tmp_path / "test.inp"
        inp.write_text("content")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            is_valid, issues = runner.validate_input(str(inp))

        assert not is_valid
        assert any("Error reading" in i for i in issues)


# ============================================================================
# Output parser: source parsing with synthetic data (lines 252-257)
# ============================================================================


class TestOutputParserSources:
    """Test _parse_sources with synthetic *** SOURCE LOCATIONS *** section."""

    def test_point_source_full_parsing(self, tmp_path):
        content = """\
*** MODEL SETUP OPTIONS ***

   AERMOD Version: 24142

*** SOURCE LOCATIONS ***

   SOURCE    TYPE       X          Y          ELEV     HEIGHT    TEMP      VELOC     DIAM      EMISS
   ------    ----    --------   --------     ------    ------    ------    ------    ------    ------
   STACK1    POINT   500000.0   3800000.0     100.0      50.0     400.0      15.0       2.0      1.5

*** END OF SOURCE LOCATIONS ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert len(results.sources) == 1
        src = results.sources[0]
        assert src.source_id == "STACK1"
        assert src.source_type == "POINT"
        assert src.x_coord == 500000.0
        assert src.stack_height == 50.0
        assert src.emission_rate == 1.5

    def test_non_point_source_basic_parsing(self, tmp_path):
        content = """\
*** SOURCE LOCATIONS ***

   SOURCE    TYPE       X          Y          ELEV
   ------    ----    --------   --------     ------
   AREA1     AREA    500000.0   3800000.0     100.0

*** END ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert len(results.sources) == 1
        assert results.sources[0].source_type == "AREA"
        assert results.sources[0].stack_height is None


# ============================================================================
# Output parser: receptor parsing (lines 284, 303-304)
# ============================================================================


class TestOutputParserReceptors:
    """Test _parse_receptors with synthetic *** RECEPTOR LOCATIONS *** section."""

    def test_receptor_parsing(self, tmp_path):
        content = """\
*** RECEPTOR LOCATIONS ***

   X-COORD       Y-COORD       ZELEV    ZHILL    ZFLAG
   500000.00     3800000.00    100.00   110.00     0.00
   500100.00     3800100.00    105.00   115.00     1.50

*** END ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert len(results.receptors) == 2
        assert results.receptors[0].x_coord == 500000.0
        assert results.receptors[1].z_flag == 1.5

    def test_receptor_malformed_line_skipped(self, tmp_path):
        """Malformed receptor lines should be skipped gracefully."""
        content = """\
*** RECEPTOR LOCATIONS ***

   RECEPTOR       X-COORD       Y-COORD
   500000.00     3800000.00
   NOT_A_NUMBER  BAD_DATA
   500100.00     3800100.00

*** END ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert len(results.receptors) == 2


# ============================================================================
# Output parser: model options and terrain type (lines 160-164, 186, 188)
# ============================================================================


class TestOutputParserModelOptions:
    """Test _parse_run_info model options parsing and terrain type detection."""

    def test_model_options_parsed(self, tmp_path):
        content = (
            "**  Model Setup Options Selected  **\n"
            "   CONC -- Calculate Concentration Values\n"
            "   FLAT -- Use Flat Terrain\n"
            "   DFAULT -- Use Default Options\n"
            "\n"
            "Other content\n"
        )
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert results.run_info is not None
        assert "CONC" in results.run_info.model_options
        assert "FLAT" in results.run_info.model_options

    def test_terrain_type_flat(self, tmp_path):
        content = (
            "**  Model Setup Options Selected  **\n"
            "   FLAT -- Use Flat Terrain\n"
            "\n"
            "Other content\n"
        )
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert results.run_info.terrain_type == "FLAT"

    def test_terrain_type_elevated(self, tmp_path):
        content = (
            "**  Model Setup Options Selected  **\n"
            "   ELEVATED -- Use Elevated Terrain\n"
            "\n"
            "Other content\n"
        )
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert results.run_info.terrain_type == "ELEVATED"


# ============================================================================
# Output parser: concentration results with rank field (lines 388-389)
# ============================================================================


class TestOutputParserRank:
    """Test concentration parsing when rank field is present."""

    def test_concentration_with_rank(self, tmp_path):
        content = """\
*** ANNUAL RESULTS ***

            ** MAXIMUM ANNUAL CONCENTRATION VALUES **

     X          Y         CONC      RANK
   500000.00  3800000.00   50.500    1
   500100.00  3800100.00   30.200    2

*** END ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert "ANNUAL" in results.concentrations
        df = results.concentrations["ANNUAL"].data
        assert len(df) == 2
        assert "rank" in df.columns
        assert df.iloc[0]["rank"] == 1


# ============================================================================
# Output parser: SUM format parsing (lines 460-461)
# ============================================================================


class TestOutputParserSUMFormat:
    """Test SUM-format concentration parsing (VALUE IS ... AT (...) pattern)."""

    def test_sum_format_parsing(self, tmp_path):
        content = """\
*** THE SUMMARY OF HIGHEST 1-HR RESULTS ***

   THE   1ST HIGHEST VALUE IS     753.656 AT (  500100.00,  3800100.00,     0.00,     0.00,     0.00)
   THE   2ND HIGHEST VALUE IS     500.123 AT (  500200.00,  3800200.00,     0.00,     0.00,     0.00)

*** END ***
"""
        out_file = tmp_path / "test.out"
        out_file.write_text(content)
        parser = AERMODOutputParser(str(out_file))
        results = parser.parse()
        assert "1HR" in results.concentrations
        df = results.concentrations["1HR"].data
        assert len(df) == 2
        assert df.iloc[0]["concentration"] == pytest.approx(753.656)


# ============================================================================
# OpenPitSource.effective_depth edge case (line 1226)
# ============================================================================


class TestOpenPitEffectiveDepth:
    """Test OpenPitSource.effective_depth with zero dimensions."""

    def test_effective_depth_normal(self):
        pit = OpenPitSource(
            source_id="PIT1", x_coord=0, y_coord=0,
            x_dimension=100, y_dimension=200,
            pit_volume=50000,
        )
        assert pit.effective_depth == pytest.approx(2.5)  # 50000 / (100*200)

    def test_effective_depth_zero_dimension(self):
        pit = OpenPitSource(
            source_id="PIT1", x_coord=0, y_coord=0,
            x_dimension=0, y_dimension=200,
            pit_volume=50000,
        )
        assert pit.effective_depth == 0.0
