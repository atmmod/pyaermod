"""
Additional coverage tests for output_parser.py.

Targets paths not exercised by test_output_parser.py:
  - AERTEST.SUM (real EPA SUM file) end-to-end parsing
  - POINT source with full stack parameters, AREA source without
  - Discrete receptors with elevation columns
  - Terrain-type detection from model_options
  - num_sources / num_receptors update after parsing
  - Additional averaging periods: 3HR, 8HR, 2HR, 12HR, 4HR, 6HR
  - export_to_csv with no sources / no receptors
  - get_concentration_at_point when averaging period is absent
  - get_sources_dataframe with sources that have no optional params
  - summary() without run_date field
  - Rank column of the summary tables
"""

from pathlib import Path

import pandas as pd
import pytest

from pyaermod.output_parser import (
    AERMODOutputParser,
    AERMODResults,
    ConcentrationResult,
    ModelRunInfo,
    SourceSummary,
    parse_aermod_output,
    quick_summary,
)

# Real EPA AERTEST summary fixture (vendored at tests/fixtures/epa_official/)
FIXTURES = Path(__file__).parent / "fixtures"
AERTEST_SUM = FIXTURES / "epa_official" / "AERTEST.SUM"
# Recorded AERMOD v26135 runs (see the README.md beside each):
# one POINT source (STACK1) and one AREA source (AREA1)
POINT_AND_AREA = FIXTURES / "runner" / "killed_sigterm" / "aermod.out"
# four POINT sources (AERO1, AERO265, STOKES, NAIVE)
FOUR_POINTS = FIXTURES / "psd" / "aermod.out"
# AVERTIME 1 ANNUAL, SO2, ELEV terrain, one POINT source, 72 polar-grid receptors
FULL_YEAR = FIXTURES / "output_parser" / "full_year" / "aermod.out"
# MODELOPT CONC DDEP FLAT
FLAT_RUN = FIXTURES / "output_parser" / "conc_ddep" / "aermod.out"


# ============================================================================
# Real AERTEST.SUM tests
# ============================================================================


class TestAERTESTSUM:
    """Parse the vendored EPA AERTEST.SUM with parse_aermod_output()."""

    def test_parse_runs_without_error(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert results is not None

    def test_version_extracted(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert results.run_info.version == "24142"

    def test_pollutant_is_so2(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert results.run_info.pollutant_id == "SO2"

    def test_source_count_from_run_includes(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert results.run_info.num_sources == 1

    def test_receptor_count_from_run_includes(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert results.run_info.num_receptors == 144

    def test_period_concentrations_present(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert "PERIOD" in results.concentrations

    def test_1hr_concentrations_present(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert "1HR" in results.concentrations

    def test_24hr_concentrations_present(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert "24HR" in results.concentrations

    def test_3hr_concentrations_present(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert "3HR" in results.concentrations

    def test_8hr_concentrations_present(self):
        results = parse_aermod_output(AERTEST_SUM)
        assert "8HR" in results.concentrations

    def test_period_max_value(self):
        """PERIOD max should be 24.85173 per AERTEST.SUM."""
        results = parse_aermod_output(AERTEST_SUM)
        assert results.concentrations["PERIOD"].max_value == pytest.approx(24.85173, abs=1e-3)

    def test_1hr_max_value(self):
        """1-HR max should be 753.65603."""
        results = parse_aermod_output(AERTEST_SUM)
        assert results.concentrations["1HR"].max_value == pytest.approx(753.65603, abs=1e-3)

    def test_24hr_max_value(self):
        """24-HR 1st highest should be 88.89517."""
        results = parse_aermod_output(AERTEST_SUM)
        assert results.concentrations["24HR"].max_value == pytest.approx(88.89517, abs=1e-3)

    def test_get_concentrations_returns_dataframe(self):
        results = parse_aermod_output(AERTEST_SUM)
        df = results.get_concentrations("PERIOD")
        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "concentration" in df.columns

    def test_get_concentrations_returns_copy(self):
        """get_concentrations should return a copy, not the internal data."""
        results = parse_aermod_output(AERTEST_SUM)
        df1 = results.get_concentrations("PERIOD")
        df2 = results.get_concentrations("PERIOD")
        df1["concentration"] = 0.0
        # Modifying df1 should not affect df2
        assert df2["concentration"].max() > 0

    def test_quick_summary_nonempty(self):
        summary = quick_summary(AERTEST_SUM)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_quick_summary_contains_aermod_header(self):
        summary = quick_summary(AERTEST_SUM)
        assert "AERMOD Results Summary" in summary

    def test_quick_summary_contains_pollutant(self):
        summary = quick_summary(AERTEST_SUM)
        assert "SO2" in summary

    def test_summary_contains_at_least_one_period(self):
        results = parse_aermod_output(AERTEST_SUM)
        summary = results.summary()
        # At least one known period should appear in the summary
        assert any(p in summary for p in ("PERIOD", "1HR", "24HR", "3HR", "8HR"))


# ============================================================================
# POINT source with full stack parameters
# ============================================================================

# STACK1   0   0.10000E+03   0.0   0.0   0.0   65.00   425.00   18.00   3.00  NO NO NO
# AREA1    0   0.10000E-03   -250.0   -250.0   0.0   2.00   500.00   500.00   0.00   0.00  NO  NO


class TestPointSourceStackParams:
    """POINT source rows carry the stack parameters; other types do not."""

    def test_stack_height_parsed(self):
        results = parse_aermod_output(str(POINT_AND_AREA))

        stk1 = next(s for s in results.sources if s.source_id == "STACK1")
        assert stk1.stack_height == pytest.approx(65.0)

    def test_stack_temp_parsed(self):
        results = parse_aermod_output(str(POINT_AND_AREA))

        stk1 = next(s for s in results.sources if s.source_id == "STACK1")
        assert stk1.stack_temp == pytest.approx(425.0)

    def test_exit_velocity_parsed(self):
        results = parse_aermod_output(str(POINT_AND_AREA))

        stk1 = next(s for s in results.sources if s.source_id == "STACK1")
        assert stk1.exit_velocity == pytest.approx(18.0)

    def test_stack_diameter_parsed(self):
        results = parse_aermod_output(str(POINT_AND_AREA))

        stk1 = next(s for s in results.sources if s.source_id == "STACK1")
        assert stk1.stack_diameter == pytest.approx(3.0)

    def test_emission_rate_parsed(self):
        results = parse_aermod_output(str(POINT_AND_AREA))

        stk1 = next(s for s in results.sources if s.source_id == "STACK1")
        assert stk1.emission_rate == pytest.approx(100.0)

    def test_second_point_source_params(self):
        # AERO265  16  0.10000E+01  0.0  0.0  0.0  10.00  300.00  1.00  1.00
        results = parse_aermod_output(str(FOUR_POINTS))

        assert [s.source_id for s in results.sources] == ["AERO1", "AERO265", "STOKES", "NAIVE"]
        second = next(s for s in results.sources if s.source_id == "AERO265")
        assert second.stack_height == pytest.approx(10.0)
        assert second.emission_rate == pytest.approx(1.0)

    def test_area_source_no_stack_params(self):
        """An AREA source row has no stack columns; they stay None."""
        results = parse_aermod_output(str(POINT_AND_AREA))

        area1 = next(s for s in results.sources if s.source_id == "AREA1")
        assert area1.source_type == "AREA"
        assert area1.stack_height is None
        assert area1.stack_temp is None
        assert area1.emission_rate == pytest.approx(1.0e-4)

    def test_num_sources_updated_after_parsing(self):
        """run_info.num_sources should be set to len(sources) after _parse_sources."""
        parser = AERMODOutputParser(str(POINT_AND_AREA))
        parser.run_info = ModelRunInfo("26135", "TEST")
        parser._parse_sources()

        assert parser.run_info.num_sources == len(parser.sources)
        assert parser.run_info.num_sources == 2  # STACK1 + AREA1


# ============================================================================
# Discrete receptors with elevation columns
# ============================================================================

# The layout of AERMOD's receptor echo, with elevations and a flagpole height.
RECEPTORS_WITH_ELEVATIONS = """\
*** AERMOD - VERSION 26135  ***

                                             *** DISCRETE CARTESIAN RECEPTORS ***
                                           (X-COORD, Y-COORD, ZELEV, ZHILL, ZFLAG)
                                                           (METERS)

     (    100.0,     200.0,      50.0,      55.0,       0.0);         (    300.0,     400.0,      80.0,      90.0,       1.5);
"""


class TestReceptorsWithElevations:
    """Receptor tuples of five values fill z_elev, z_hill and z_flag."""

    def test_zelev_parsed(self, tmp_path):
        outfile = tmp_path / "recepts.out"
        outfile.write_text(RECEPTORS_WITH_ELEVATIONS)
        results = parse_aermod_output(str(outfile))

        assert results.receptors[0].z_elev == pytest.approx(50.0)

    def test_zhill_parsed(self, tmp_path):
        outfile = tmp_path / "recepts.out"
        outfile.write_text(RECEPTORS_WITH_ELEVATIONS)
        results = parse_aermod_output(str(outfile))

        assert results.receptors[0].z_hill == pytest.approx(55.0)

    def test_zflag_nonzero(self, tmp_path):
        outfile = tmp_path / "recepts.out"
        outfile.write_text(RECEPTORS_WITH_ELEVATIONS)
        results = parse_aermod_output(str(outfile))

        assert results.receptors[1].z_flag == pytest.approx(1.5)

    def test_num_receptors_updated_after_parsing(self, tmp_path):
        """run_info.num_receptors is updated from 0 to 2 after parse."""
        outfile = tmp_path / "recepts.out"
        outfile.write_text(RECEPTORS_WITH_ELEVATIONS)
        parser = AERMODOutputParser(str(outfile))
        parser.run_info = ModelRunInfo("26135", "TEST", num_receptors=0)
        parser._parse_receptors()

        assert parser.run_info.num_receptors == 2

    def test_num_receptors_uses_max(self, tmp_path):
        """If run_info.num_receptors is already higher than parsed count, keep it."""
        outfile = tmp_path / "recepts.out"
        outfile.write_text(RECEPTORS_WITH_ELEVATIONS)
        parser = AERMODOutputParser(str(outfile))
        parser.run_info = ModelRunInfo("26135", "TEST", num_receptors=999)
        parser._parse_receptors()

        # max(2, 999) = 999
        assert len(parser.receptors) == 2
        assert parser.run_info.num_receptors == 999


# ============================================================================
# Terrain type detection from model_options
# ============================================================================


class TestTerrainTypeDetection:
    """Terrain type is inferred from the MODELOPTs line of the page banner."""

    def test_flat_terrain_type_set(self):
        # *** MODELOPTs:    NonDFAULT  CONC  DDEP  FLAT  DRYDPLT  ALPHA  RURAL  SigA&SigW
        parser = AERMODOutputParser(str(FLAT_RUN))
        parser._parse_header()

        assert "FLAT" in parser.run_info.model_options
        assert parser.run_info.terrain_type == "FLAT"

    def test_flat_model_option_present(self):
        parser = AERMODOutputParser(str(FLAT_RUN))
        parser._parse_header()

        assert parser.run_info.model_options == [
            "NonDFAULT", "CONC", "DDEP", "FLAT", "DRYDPLT", "ALPHA", "RURAL", "SigA&SigW"]
        assert parser.run_info.urban_option == "RURAL"

    def test_elevated_terrain_type_set(self):
        # *** MODELOPTs:    RegDFAULT  CONC  ELEV  RURAL  SigA&SigW
        parser = AERMODOutputParser(str(FULL_YEAR))
        parser._parse_header()

        assert "ELEV" in parser.run_info.model_options
        assert parser.run_info.terrain_type == "ELEVATED"


# ============================================================================
# Additional averaging periods: 3HR, 8HR, 2HR, 12HR (EPA VALUE IS format)
# ============================================================================

MULTI_PERIOD_EPA = """\
*** AERMOD - VERSION 24142 ***

*** THE SUMMARY OF HIGHEST 3-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  200.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)
   ALL   HIGH   2ND HIGH VALUE IS  150.0 AT (  300.0,  400.0,  0.0,  0.0,  0.0)

*** THE SUMMARY OF HIGHEST 8-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  90.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)

*** THE SUMMARY OF HIGHEST 2-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  300.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)

*** THE SUMMARY OF HIGHEST 12-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  50.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)
"""

PERIOD_4HR_6HR = """\
*** AERMOD - VERSION 24142 ***

*** THE SUMMARY OF HIGHEST 4-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  180.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)

*** THE SUMMARY OF HIGHEST 6-HR RESULTS ***

   ALL   HIGH   1ST HIGH VALUE IS  130.0 AT (  100.0,  200.0,  0.0,  0.0,  0.0)
"""


class TestAdditionalAveragingPeriods:
    """3HR, 8HR, 2HR, 12HR, 4HR and 6HR periods."""

    def test_3hr_concentrations(self, tmp_path):
        outfile = tmp_path / "multi.out"
        outfile.write_text(MULTI_PERIOD_EPA)
        results = parse_aermod_output(str(outfile))

        assert "3HR" in results.concentrations
        assert results.concentrations["3HR"].max_value == pytest.approx(200.0)

    def test_3hr_has_multiple_rows(self, tmp_path):
        outfile = tmp_path / "multi.out"
        outfile.write_text(MULTI_PERIOD_EPA)
        results = parse_aermod_output(str(outfile))

        assert len(results.concentrations["3HR"].data) == 2

    def test_8hr_concentrations(self, tmp_path):
        outfile = tmp_path / "multi.out"
        outfile.write_text(MULTI_PERIOD_EPA)
        results = parse_aermod_output(str(outfile))

        assert "8HR" in results.concentrations
        assert results.concentrations["8HR"].max_value == pytest.approx(90.0)

    def test_2hr_concentrations(self, tmp_path):
        outfile = tmp_path / "multi.out"
        outfile.write_text(MULTI_PERIOD_EPA)
        results = parse_aermod_output(str(outfile))

        assert "2HR" in results.concentrations
        assert results.concentrations["2HR"].max_value == pytest.approx(300.0)

    def test_12hr_concentrations(self, tmp_path):
        outfile = tmp_path / "multi.out"
        outfile.write_text(MULTI_PERIOD_EPA)
        results = parse_aermod_output(str(outfile))

        assert "12HR" in results.concentrations
        assert results.concentrations["12HR"].max_value == pytest.approx(50.0)

    def test_4hr_concentrations(self, tmp_path):
        outfile = tmp_path / "short.out"
        outfile.write_text(PERIOD_4HR_6HR)
        results = parse_aermod_output(str(outfile))

        assert "4HR" in results.concentrations
        assert results.concentrations["4HR"].max_value == pytest.approx(180.0)

    def test_6hr_concentrations(self, tmp_path):
        outfile = tmp_path / "short.out"
        outfile.write_text(PERIOD_4HR_6HR)
        results = parse_aermod_output(str(outfile))

        assert "6HR" in results.concentrations
        assert results.concentrations["6HR"].max_value == pytest.approx(130.0)


# ============================================================================
# export_to_csv edge cases
# ============================================================================


class TestExportToCSVEdgeCases:
    """export_to_csv branches when sources/receptors are empty."""

    def test_export_no_sources_no_receptors_no_files(self, tmp_path):
        """No CSV files for sources or receptors when lists are empty."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "EMPTY"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="empty.out",
        )
        output_dir = tmp_path / "export_empty"
        results.export_to_csv(str(output_dir), prefix="test")

        assert not (output_dir / "test_sources.csv").exists()
        assert not (output_dir / "test_receptors.csv").exists()

    def test_export_creates_nested_directory(self, tmp_path):
        """export_to_csv creates output_dir recursively if it does not exist."""
        df = pd.DataFrame({"x": [100.0], "y": [200.0], "concentration": [5.0]})
        result = ConcentrationResult(
            averaging_period="ANNUAL",
            data=df,
            max_value=5.0,
            max_location=(100.0, 200.0),
        )
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST"),
            sources=[],
            receptors=[],
            concentrations={"ANNUAL": result},
            output_file="test.out",
        )
        new_dir = tmp_path / "nested" / "subdir"
        results.export_to_csv(str(new_dir), prefix="run1")

        assert (new_dir / "run1_concentrations_ANNUAL.csv").exists()


# ============================================================================
# AERMODResults method edge cases
# ============================================================================


class TestAERMODResultsMethodEdgeCases:
    """Methods that have rarely-reached branches."""

    def test_get_concentration_at_point_missing_period_returns_none(self):
        """Returns None immediately when averaging period is absent."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="empty.out",
        )
        conc = results.get_concentration_at_point(0.0, 0.0, "ANNUAL")
        assert conc is None

    def test_get_sources_dataframe_no_optional_fields(self):
        """Sources without stack_height / emission_rate omit those columns."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST"),
            sources=[SourceSummary("A1", "AREA", 0.0, 0.0, 0.0)],
            receptors=[],
            concentrations={},
            output_file="test.out",
        )
        df = results.get_sources_dataframe()
        assert "stack_height" not in df.columns
        assert "emission_rate" not in df.columns

    def test_get_sources_dataframe_with_emission_no_stack(self):
        """Only emission_rate set → column present, stack_height absent."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST"),
            sources=[SourceSummary("A1", "AREA", 0.0, 0.0, 0.0, emission_rate=1.0)],
            receptors=[],
            concentrations={},
            output_file="test.out",
        )
        df = results.get_sources_dataframe()
        assert "emission_rate" in df.columns
        assert "stack_height" not in df.columns

    def test_summary_no_run_date_omits_run_date_line(self):
        """When run_date is None, 'Run Date' does not appear in summary."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST_NO_DATE"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="test.out",
        )
        summary = results.summary()
        assert "Run Date" not in summary

    def test_summary_with_run_date_included(self):
        """When run_date is set, it appears in summary."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "TEST_DATE", run_date="01-15-26"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="test.out",
        )
        summary = results.summary()
        assert "Run Date: 01-15-26" in summary

    def test_summary_unknown_pollutant_and_terrain(self):
        """None pollutant_id and terrain_type fall back to 'Unknown'."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "NO_META"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="test.out",
        )
        summary = results.summary()
        assert "Unknown" in summary


# ============================================================================
# Rank column of the summary tables
# ============================================================================


class TestConcentrationRankColumn:
    """Each summary row carries its rank (1ST, 2ND, 3RD ...)."""

    # AERTEST.SUM, THE SUMMARY OF HIGHEST 1-HR RESULTS:
    # ALL  HIGH  1ST HIGH VALUE IS  753.65603  ON 88030111: AT ( ...
    #      HIGH  2ND HIGH VALUE IS  421.98845  ON 88030113: AT ( ...
    #      HIGH  3RD HIGH VALUE IS  371.81291  ON 88030116: AT ( ...

    def test_rank_column_present(self):
        results = parse_aermod_output(AERTEST_SUM)

        df = results.concentrations["1HR"].data
        assert "rank" in df.columns

    def test_rank_values_correct(self):
        results = parse_aermod_output(AERTEST_SUM)

        df = results.concentrations["1HR"].data
        assert df["rank"].tolist() == [1, 2, 3]
        max_row = df.loc[df["concentration"].idxmax()]
        assert int(max_row["rank"]) == 1

    def test_three_rows_parsed(self):
        results = parse_aermod_output(AERTEST_SUM)

        assert len(results.concentrations["1HR"].data) == 3


# ============================================================================
# A whole recorded run, end to end
# ============================================================================


class TestFullRunEndToEnd:
    """Every part of a recorded run (full_year) read by parse_aermod_output."""

    def test_pollutant_id(self):
        results = parse_aermod_output(str(FULL_YEAR))

        assert results.run_info.pollutant_id == "SO2"

    def test_averaging_period_parsed(self):
        results = parse_aermod_output(str(FULL_YEAR))

        assert results.run_info.averaging_periods == ["1-HR", "ANNUAL"]

    def test_source_count_from_header_line(self):
        results = parse_aermod_output(str(FULL_YEAR))

        assert results.run_info.num_sources == 1

    def test_one_source_parsed(self):
        results = parse_aermod_output(str(FULL_YEAR))

        assert len(results.sources) == 1

    def test_receptor_count_from_header_line(self):
        # A polar grid is not echoed receptor by receptor; the count is
        # the one of "This Run Includes".
        results = parse_aermod_output(str(FULL_YEAR))

        assert results.receptors == []
        assert results.run_info.num_receptors == 72

    def test_annual_results_parsed(self):
        results = parse_aermod_output(str(FULL_YEAR))

        assert "ANNUAL" in results.concentrations
        assert results.concentrations["ANNUAL"].max_value == pytest.approx(5.42148)

    def test_max_location_correct(self):
        results = parse_aermod_output(str(FULL_YEAR))

        loc = results.concentrations["ANNUAL"].max_location
        assert loc[0] == pytest.approx(519.62)
        assert loc[1] == pytest.approx(-300.0)

    def test_get_max_concentration_dict(self):
        results = parse_aermod_output(str(FULL_YEAR))

        max_info = results.get_max_concentration("ANNUAL")
        assert max_info is not None
        assert max_info["averaging_period"] == "ANNUAL"
        assert max_info["value"] == pytest.approx(5.42148)
        assert max_info["units"] == "ug/m^3"


# ============================================================================
# AERMODResults.from_file with a non-existent file
# ============================================================================


class TestAERMODResultsFromFileMissing:
    """from_file() delegates to AERMODOutputParser which raises FileNotFoundError."""

    def test_from_file_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            AERMODResults.from_file("/nonexistent/path/run.out")
