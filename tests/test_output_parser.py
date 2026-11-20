"""
Unit tests for PyAERMOD output parser

Tests the dataclasses, the AERMODResults methods, and the parser on
recorded AERMOD runs (tests/fixtures) and on short strings in AERMOD's
own layout.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pyaermod.output_parser import (
    AERMODOutputParser,
    AERMODResults,
    ConcentrationResult,
    ModelRunInfo,
    ReceptorInfo,
    SourceSummary,
    parse_aermod_output,
    quick_summary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_run_info():
    return ModelRunInfo(
        version="24142",
        jobname="TEST_RUN",
        pollutant_id="SO2",
        averaging_periods=["ANNUAL", "24HR"],
        terrain_type="FLAT",
        num_sources=2,
        num_receptors=100,
    )


@pytest.fixture
def sample_sources():
    return [
        SourceSummary("STACK1", "POINT", 0.0, 0.0, 10.0,
                       stack_height=50.0, emission_rate=1.5),
        SourceSummary("STACK2", "POINT", 100.0, 0.0, 10.0,
                       stack_height=30.0, emission_rate=0.8),
    ]


@pytest.fixture
def sample_receptors():
    recs = []
    for x in range(-200, 201, 100):
        for y in range(-200, 201, 100):
            recs.append(ReceptorInfo(x_coord=float(x), y_coord=float(y)))
    return recs


@pytest.fixture
def sample_concentration_data():
    """Create synthetic concentration grid"""
    rows = []
    for x in range(-200, 201, 100):
        for y in range(-200, 201, 100):
            dist = np.sqrt(x**2 + y**2) + 1
            conc = 10.0 / dist * 100
            rows.append({"x": float(x), "y": float(y), "concentration": conc})
    return pd.DataFrame(rows)


@pytest.fixture
def sample_results(sample_run_info, sample_sources, sample_receptors,
                   sample_concentration_data):
    df = sample_concentration_data
    max_idx = df["concentration"].idxmax()
    max_val = df.loc[max_idx, "concentration"]
    max_x = df.loc[max_idx, "x"]
    max_y = df.loc[max_idx, "y"]

    conc_result = ConcentrationResult(
        averaging_period="ANNUAL",
        data=df,
        max_value=max_val,
        max_location=(max_x, max_y),
    )

    return AERMODResults(
        run_info=sample_run_info,
        sources=sample_sources,
        receptors=sample_receptors,
        concentrations={"ANNUAL": conc_result},
        output_file="test.out",
    )


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestModelRunInfo:
    """Test ModelRunInfo dataclass"""

    def test_defaults(self):
        info = ModelRunInfo(version="24142", jobname="TEST")
        assert info.version == "24142"
        assert info.model_options == []
        assert info.num_sources == 0

    def test_full_info(self, sample_run_info):
        assert sample_run_info.pollutant_id == "SO2"
        assert "ANNUAL" in sample_run_info.averaging_periods


class TestSourceSummary:
    """Test SourceSummary dataclass"""

    def test_point_source(self):
        src = SourceSummary("S1", "POINT", 100.0, 200.0, 10.0,
                            stack_height=50.0, emission_rate=1.5)
        assert src.source_id == "S1"
        assert src.source_type == "POINT"
        assert src.stack_height == 50.0

    def test_area_source_minimal(self):
        src = SourceSummary("A1", "AREA", 0.0, 0.0, 0.0)
        assert src.stack_height is None
        assert src.emission_rate is None


class TestReceptorInfo:
    """Test ReceptorInfo dataclass"""

    def test_defaults(self):
        rec = ReceptorInfo(x_coord=100.0, y_coord=200.0)
        assert rec.z_elev == 0.0
        assert rec.z_hill == 0.0
        assert rec.z_flag == 0.0
        assert rec.receptor_id is None

    def test_with_elevations(self):
        rec = ReceptorInfo(100.0, 200.0, z_elev=50.0, z_hill=80.0)
        assert rec.z_elev == 50.0
        assert rec.z_hill == 80.0


class TestConcentrationResult:
    """Test ConcentrationResult dataclass"""

    def test_basic(self, sample_concentration_data):
        df = sample_concentration_data
        result = ConcentrationResult(
            averaging_period="ANNUAL",
            data=df,
            max_value=df["concentration"].max(),
            max_location=(0.0, 0.0),
        )
        assert result.averaging_period == "ANNUAL"
        assert result.units == "ug/m^3"
        assert len(result.data) == len(df)


# ---------------------------------------------------------------------------
# AERMODResults tests
# ---------------------------------------------------------------------------

class TestAERMODResults:
    """Test AERMODResults methods"""

    def test_get_concentrations(self, sample_results):
        df = sample_results.get_concentrations("ANNUAL")
        assert "x" in df.columns
        assert "y" in df.columns
        assert "concentration" in df.columns
        assert len(df) > 0

    def test_get_concentrations_missing_period(self, sample_results):
        # Returns None for missing periods instead of raising
        assert sample_results.get_concentrations("24HR") is None

    def test_get_max_concentration(self, sample_results):
        max_info = sample_results.get_max_concentration("ANNUAL")
        assert "value" in max_info
        assert "x" in max_info
        assert "y" in max_info
        assert "units" in max_info
        assert max_info["value"] > 0

    def test_get_max_concentration_missing_period(self, sample_results):
        assert sample_results.get_max_concentration("1HR") is None

    def test_get_concentration_at_point(self, sample_results):
        """Test querying concentration at a known receptor"""
        conc = sample_results.get_concentration_at_point(0.0, 0.0, "ANNUAL", tolerance=1.0)
        assert conc is not None
        assert conc > 0

    def test_get_concentration_at_point_no_match(self, sample_results):
        """Test querying at a location far from any receptor"""
        conc = sample_results.get_concentration_at_point(99999.0, 99999.0, "ANNUAL", tolerance=1.0)
        assert conc is None

    def test_get_sources_dataframe(self, sample_results):
        df = sample_results.get_sources_dataframe()
        assert len(df) == 2
        assert "source_id" in df.columns
        assert "x" in df.columns
        assert "stack_height" in df.columns

    def test_get_sources_dataframe_empty(self):
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "EMPTY"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="empty.out",
        )
        df = results.get_sources_dataframe()
        assert len(df) == 0

    def test_get_receptors_dataframe(self, sample_results):
        df = sample_results.get_receptors_dataframe()
        assert len(df) == len(sample_results.receptors)
        assert "x" in df.columns
        assert "z_elev" in df.columns

    def test_summary(self, sample_results):
        summary = sample_results.summary()
        assert "AERMOD Results Summary" in summary
        assert "TEST_RUN" in summary
        assert "SO2" in summary
        assert "ANNUAL" in summary

    def test_export_to_csv(self, sample_results, tmp_path):
        sample_results.export_to_csv(str(tmp_path), prefix="test")
        assert (tmp_path / "test_sources.csv").exists()
        assert (tmp_path / "test_receptors.csv").exists()
        assert (tmp_path / "test_concentrations_ANNUAL.csv").exists()


# ---------------------------------------------------------------------------
# Parser tests on recorded AERMOD runs
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
# AVERTIME 1 ANNUAL, SO2, one POINT source (see fixtures/output_parser/README.md)
FULL_YEAR = FIXTURES / "output_parser" / "full_year" / "aermod.out"
# An open pit with seven discrete Cartesian receptors
WASHOUT = FIXTURES / "fortran_exponents" / "washout" / "aermod.out"
# A run AERMOD stopped in setup: no source tables, no results
SETUP_ERROR = FIXTURES / "runner" / "setup_error_e500" / "aermod.out"


class TestAERMODOutputParser:
    """Test the parser's steps on a recorded run"""

    def test_parser_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            AERMODOutputParser("/nonexistent/path.out")

    def test_parse_header(self):
        parser = AERMODOutputParser(str(FULL_YEAR))
        parser._parse_header()

        assert parser.run_info is not None
        assert parser.run_info.version == "26135"
        # AERMOD prints no job name; the banner carries the title.
        assert parser.run_info.jobname == "Unknown"
        assert parser.run_info.title == "Albany stack over a repeated year of met data"
        assert parser.run_info.run_date == "09/29/26"
        assert parser.run_info.run_time == "19:00:00"

    def test_parse_sources(self):
        parser = AERMODOutputParser(str(FULL_YEAR))
        parser.run_info = ModelRunInfo("26135", "TEST")
        parser._parse_sources()

        assert len(parser.sources) == 1
        assert parser.sources[0].source_id == "STACK1"
        assert parser.sources[0].source_type == "POINT"

    def test_parse_receptors(self):
        parser = AERMODOutputParser(str(WASHOUT))
        parser.run_info = ModelRunInfo("26135", "TEST")
        parser._parse_receptors()

        # (   1732.0,    1000.0, ...);  (   5196.2,    3000.0, ...);
        assert len(parser.receptors) == 7
        assert parser.receptors[0].x_coord == 1732.0
        assert parser.receptors[1].y_coord == 3000.0

    def test_parse_concentrations(self):
        parser = AERMODOutputParser(str(FULL_YEAR))
        parser._parse_concentration_results()

        assert "ANNUAL" in parser.concentrations
        result = parser.concentrations["ANNUAL"]
        assert result.max_value == pytest.approx(5.42148)
        assert len(result.data) == 10

    def test_full_parse(self):
        results = parse_aermod_output(str(FULL_YEAR))
        assert results.run_info.title == "Albany stack over a repeated year of met data"
        assert len(results.sources) == 1
        assert results.run_info.num_receptors == 72
        assert "ANNUAL" in results.concentrations
        assert len(parse_aermod_output(str(WASHOUT)).receptors) == 7


class TestConvenienceFunctions:
    """Test module-level convenience functions"""

    def test_quick_summary(self):
        summary = quick_summary(str(FULL_YEAR))
        assert "AERMOD Results Summary" in summary
        assert "Albany stack over a repeated year of met data" in summary


# ---------------------------------------------------------------------------
# Additional coverage tests: warnings in output, empty/malformed files
# ---------------------------------------------------------------------------

class TestParserWithWarnings:
    """Test that the parser handles output files containing warning lines."""

    def test_parse_with_warning_lines(self):
        """Parser should still extract results when warnings are present."""
        # FULL_YEAR lists four warnings, among them
        # "CO W361  7  COCARD: Multiyear PERIOD/ANNUAL values for NO2/SO2 ..."
        assert "WARNING MESSAGES" in FULL_YEAR.read_text()
        results = parse_aermod_output(str(FULL_YEAR))
        assert results.run_info.version == "26135"
        assert len(results.sources) == 1
        assert "ANNUAL" in results.concentrations
        assert results.concentrations["ANNUAL"].max_value == pytest.approx(5.42148)

    def test_warning_lines_dont_corrupt_source_parsing(self):
        """Warning lines should not be parsed as sources."""
        parser = AERMODOutputParser(str(FULL_YEAR))
        parser.run_info = ModelRunInfo("26135", "TEST")
        parser._parse_sources()

        # Only STACK1 should be parsed, not the WARNING lines
        assert len(parser.sources) == 1
        assert parser.sources[0].source_id == "STACK1"


_FIXTURES = Path(__file__).parent / "fixtures"


class TestNothingParsedWarning:
    """A file that yields no source, receptor or result table says so."""

    def test_a_file_that_is_not_an_aermod_report_warns(self, tmp_path):
        """For example the wrong file, or text in a layout AERMOD does not write."""
        outfile = tmp_path / "other.out"
        outfile.write_text(
            " *** ANNUAL RESULTS ***\n\n"
            "   X-COORD       Y-COORD    CONC (UG/M3)\n"
            "      0.00         0.00         5.2341\n"
        )
        with pytest.warns(UserWarning, match="not an AERMOD main output") as caught:
            results = parse_aermod_output(outfile)
        assert results.concentrations == {} and results.sources == []
        assert caught[0].filename == __file__  # the caller's line

    def test_another_programs_output_warns(self):
        with pytest.warns(UserWarning, match="not an AERMOD main output"):
            parse_aermod_output(_FIXTURES / "aermap_runner/success/aermap.out")

    def test_an_aermod_run_that_stopped_in_setup_says_so(self):
        with pytest.warns(UserWarning, match="stopped before it wrote them"):
            parse_aermod_output(_FIXTURES / "runner/setup_error_e500/aermod.out")

    def test_a_complete_run_does_not_warn(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            results = parse_aermod_output(_FIXTURES / "output_parser/full_year/aermod.out")
        assert results.concentrations


class TestEmptyAndMalformedOutput:
    """Test parser behavior with empty or malformed output files."""

    def test_empty_file(self, tmp_path):
        """An empty output file should parse without crashing."""
        outfile = tmp_path / "empty.out"
        outfile.write_text("")

        parser = AERMODOutputParser(str(outfile))
        results = parser.parse()

        assert results.run_info is not None
        assert results.run_info.version == "Unknown"
        assert results.run_info.jobname == "Unknown"
        assert len(results.sources) == 0
        assert len(results.receptors) == 0
        assert len(results.concentrations) == 0

    def test_file_with_only_whitespace(self, tmp_path):
        """A whitespace-only output file should parse without crashing."""
        outfile = tmp_path / "blank.out"
        outfile.write_text("   \n\n   \n")

        parser = AERMODOutputParser(str(outfile))
        results = parser.parse()

        assert results.run_info.version == "Unknown"
        assert len(results.concentrations) == 0

    def test_no_concentration_results_section(self):
        """File with no results section should have empty concentrations."""
        parser = AERMODOutputParser(str(SETUP_ERROR))
        parser._parse_concentration_results()

        assert len(parser.concentrations) == 0

    def test_from_file_classmethod(self):
        """AERMODResults.from_file() should work the same as parse_aermod_output()."""
        results = AERMODResults.from_file(str(FULL_YEAR))
        assert results.run_info.title == "Albany stack over a repeated year of met data"
        assert "ANNUAL" in results.concentrations

    def test_get_receptors_dataframe_empty(self):
        """get_receptors_dataframe() on empty receptors returns empty DataFrame."""
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "EMPTY"),
            sources=[],
            receptors=[],
            concentrations={},
            output_file="empty.out",
        )
        df = results.get_receptors_dataframe()
        assert len(df) == 0


# ---------------------------------------------------------------------------
# Output parser edge case tests (Phase 2d)
# ---------------------------------------------------------------------------

# Synthetic EPA SUM-style output with multiple averaging periods and dates
EPA_STYLE_OUTPUT = """\
*** AERMOD - VERSION 24142 ***

  Pollutant Type of: SO2

**Model Calculates  2 Short Term Average(s) of:   1-HR  24-HR
    and Calculates ANNUAL Averages

                       METEOROLOGICAL DATA PROCESSED BETWEEN START DATE: 1988   1  1  1
                                                           AND END DATE: 1988  12 31 24

  This Run Includes:   3 Source(s);   1 Source Group(s); and   50 Receptor(s)

*** THE SUMMARY OF HIGHEST ANNUAL RESULTS ***

   ALL   1ST HIGHEST VALUE IS  24.85173 AT (  433.01,  -250.00,  0.00,  0.00,  0.00)
   ALL   2ND HIGHEST VALUE IS  20.00000 AT (  500.00,  -100.00,  0.00,  0.00,  0.00)

*** THE SUMMARY OF HIGHEST 1-HR RESULTS ***

   ALL   HIGH  1ST HIGH VALUE IS  753.65603  ON 88030111: AT (  303.11,  -175.00,  0.00,  0.00,  0.00)
   ALL   HIGH  2ND HIGH VALUE IS  600.00000  ON 88061205: AT (  200.00,   100.00,  0.00,  0.00,  0.00)

*** THE SUMMARY OF HIGHEST 24-HR RESULTS ***

   ALL   HIGH  1ST HIGH VALUE IS  120.50000  ON 88030124: AT (  400.00,  -200.00,  0.00,  0.00,  0.00)
"""


class TestOutputParserEdgeCases:
    """Test output_parser edge cases for uncovered lines."""

    def test_parse_multiple_averaging_periods(self, tmp_path):
        """Multiple averaging periods (ANNUAL + 1HR + 24HR) all parsed."""
        outfile = tmp_path / "multi_period.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        results = parser.parse()

        assert "ANNUAL" in results.concentrations
        assert "1HR" in results.concentrations
        assert "24HR" in results.concentrations

    def test_modeling_period_dates(self, tmp_path):
        """START DATE / END DATE extraction from the met-data lines."""
        outfile = tmp_path / "dates.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        parser._parse_header()

        assert parser.run_info.start_date == "1988/01/01"
        assert parser.run_info.end_date == "1988/12/31"

    def test_epa_value_is_format_synthetic(self, tmp_path):
        """EPA VALUE IS format parsed — both with and without ON date."""
        outfile = tmp_path / "value_is.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        results = parser.parse()

        # ANNUAL has VALUE IS without ON date
        annual = results.concentrations["ANNUAL"]
        assert annual.max_value == pytest.approx(24.85173, abs=1e-4)
        assert annual.max_location[0] == pytest.approx(433.01, abs=0.01)
        assert len(annual.data) == 2

        # 1HR has VALUE IS with ON date
        hr1 = results.concentrations["1HR"]
        assert hr1.max_value == pytest.approx(753.65603, abs=1e-4)
        assert len(hr1.data) == 2

    def test_summary_with_run_date(self):
        """Summary includes the run date of the page banner."""
        results = parse_aermod_output(str(FULL_YEAR))
        summary = results.summary()
        assert "Run Date: 09/29/26" in summary

    def test_source_receptor_counts_from_epa(self, tmp_path):
        """Source/receptor counts extracted from EPA 'This Run Includes' line."""
        outfile = tmp_path / "counts.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        parser._parse_header()

        assert parser.run_info.num_sources == 3
        assert parser.run_info.num_receptors == 50

    def test_epa_pollutant_type_parsed(self, tmp_path):
        """Pollutant Type of: SO2 extracted from EPA format."""
        outfile = tmp_path / "pollutant.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        parser._parse_header()

        assert parser.run_info.pollutant_id == "SO2"

    def test_averaging_periods_parsed(self, tmp_path):
        """The "Model Calculates" lines populate averaging_periods."""
        outfile = tmp_path / "avgtime.out"
        outfile.write_text(EPA_STYLE_OUTPUT)
        parser = AERMODOutputParser(str(outfile))
        parser._parse_header()

        assert "1-HR" in parser.run_info.averaging_periods
        assert "24-HR" in parser.run_info.averaging_periods
        assert "ANNUAL" in parser.run_info.averaging_periods


# ===========================================================================
# EPA Source Parsing — synthetic unit tests for _parse_sources_epa()
# ===========================================================================

EPA_SOURCE_SECTIONS = """\
*** AERMOD - VERSION 24142 ***

*** POINT SOURCE DATA ***

           SOURCE       NO.        EMISSION         X             Y       BASE       STACK     STACK     EXIT      STACK
            ID        PART.         RATE                                  ELEV.      HGT.      TEMP.     VEL.     DIAM.
          --------    ------    ----------    -------    -------    -------    -------    -------    ------    ------
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
          STACK1          0     1.50000E+00      0.00       0.00     10.00     50.00    400.00     15.00      2.00
          STACK2          0     8.00000E-01    100.00       0.00    105.00     30.00    350.00     10.00      1.50

*** VOLUME SOURCE DATA ***

           SOURCE       NO.        EMISSION         X             Y       BASE
            ID        PART.         RATE                                  ELEV.
          --------    ------    ----------    -------    -------    -------
- - - - - - - - - - - - - - - - - - - - - - - - - - -
          VOL1            0     5.00000E-01    200.00     200.00    110.00

*** AREA SOURCE DATA ***

           SOURCE       NO.        EMISSION         X             Y       BASE
            ID        PART.         RATE                                  ELEV.
          --------    ------    ----------    -------    -------    -------
- - - - - - - - - - - - - - - - - - - - - - - - - - -
          AREA1           0     1.00000E-03    300.00     300.00    100.00
"""

EPA_SOURCE_WITH_PAGE_BREAK = """\
*** AERMOD - VERSION 24142 ***

*** POINT SOURCE DATA ***

           SOURCE       NO.        EMISSION         X             Y       BASE       STACK     STACK     EXIT      STACK
            ID        PART.         RATE                                  ELEV.      HGT.      TEMP.     VEL.     DIAM.
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -
          STK1            0     1.00000E+00      0.00       0.00    100.00     50.00    400.00     15.00      2.00
*** AERMOD - VERSION 24142 ***   *** Page break mid-section ***
          STK2            0     2.00000E+00      0.00       0.00    100.00     30.00    350.00     10.00      1.50
"""

EPA_SOURCE_WITH_MODELOPTS = """\
*** AERMOD - VERSION 24142 ***

*** POINT SOURCE DATA ***

           SOURCE       NO.        EMISSION         X             Y       BASE       STACK     STACK     EXIT      STACK
            ID        PART.         RATE                                  ELEV.      HGT.      TEMP.     VEL.     DIAM.
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -
          STK1            0     1.00000E+00      0.00       0.00    100.00     50.00    400.00     15.00      2.00
 MODELOPTs:    NonDFAULT  CONC  FLAT  RURAL                                                     PAGE   3
          STK2            0     2.00000E+00      0.00       0.00    100.00     30.00    350.00     10.00      1.50
"""


class TestEPASourceParsing:
    """Unit tests for _parse_sources_epa() and _parse_epa_source_section()."""

    def test_epa_point_sources_parsed(self, tmp_path):
        outfile = tmp_path / "epa_sources.out"
        outfile.write_text(EPA_SOURCE_SECTIONS)
        results = parse_aermod_output(str(outfile))

        point_sources = [s for s in results.sources if s.source_type == "POINT"]
        assert len(point_sources) == 2
        assert point_sources[0].source_id == "STACK1"
        assert point_sources[0].emission_rate == pytest.approx(1.5)
        assert point_sources[0].x_coord == pytest.approx(0.0)
        assert point_sources[0].y_coord == pytest.approx(0.0)
        assert point_sources[0].base_elevation == pytest.approx(10.0)
        assert point_sources[0].stack_height == pytest.approx(50.0)
        assert point_sources[0].stack_temp == pytest.approx(400.0)
        assert point_sources[0].exit_velocity == pytest.approx(15.0)
        assert point_sources[0].stack_diameter == pytest.approx(2.0)

    def test_epa_volume_source_parsed(self, tmp_path):
        outfile = tmp_path / "epa_sources.out"
        outfile.write_text(EPA_SOURCE_SECTIONS)
        results = parse_aermod_output(str(outfile))

        vol_sources = [s for s in results.sources if s.source_type == "VOLUME"]
        assert len(vol_sources) == 1
        assert vol_sources[0].source_id == "VOL1"
        assert vol_sources[0].emission_rate == pytest.approx(0.5)
        assert vol_sources[0].base_elevation == pytest.approx(110.0)
        # Volume sources should not have stack params
        assert vol_sources[0].stack_height is None

    def test_epa_area_source_parsed(self, tmp_path):
        outfile = tmp_path / "epa_sources.out"
        outfile.write_text(EPA_SOURCE_SECTIONS)
        results = parse_aermod_output(str(outfile))

        area_sources = [s for s in results.sources if s.source_type == "AREA"]
        assert len(area_sources) == 1
        assert area_sources[0].source_id == "AREA1"

    def test_epa_source_total_count(self, tmp_path):
        outfile = tmp_path / "epa_sources.out"
        outfile.write_text(EPA_SOURCE_SECTIONS)
        results = parse_aermod_output(str(outfile))

        assert len(results.sources) == 4  # 2 POINT + 1 VOL + 1 AREA

    def test_epa_source_emission_rate_scientific(self, tmp_path):
        """Scientific notation emission rates parsed correctly."""
        outfile = tmp_path / "epa_sources.out"
        outfile.write_text(EPA_SOURCE_SECTIONS)
        results = parse_aermod_output(str(outfile))

        stack2 = next(s for s in results.sources if s.source_id == "STACK2")
        assert stack2.emission_rate == pytest.approx(0.8)
        assert stack2.base_elevation == pytest.approx(105.0)

    def test_epa_source_page_header_break(self, tmp_path):
        """*** AERMOD mid-section causes parsing to stop for that section."""
        outfile = tmp_path / "page_break.out"
        outfile.write_text(EPA_SOURCE_WITH_PAGE_BREAK)
        results = parse_aermod_output(str(outfile))

        # Only STK1 should be parsed; STK2 is after the page break
        assert len(results.sources) == 1
        assert results.sources[0].source_id == "STK1"

    def test_epa_source_modelopts_skip(self, tmp_path):
        """MODELOPTs/PAGE lines mid-section are skipped, data continues."""
        outfile = tmp_path / "modelopts.out"
        outfile.write_text(EPA_SOURCE_WITH_MODELOPTS)
        results = parse_aermod_output(str(outfile))

        # Both STK1 and STK2 should be parsed
        assert len(results.sources) == 2
        ids = {s.source_id for s in results.sources}
        assert ids == {"STK1", "STK2"}


# ===========================================================================
# EPA Receptor Parsing — synthetic unit tests for _parse_receptors_epa()
# ===========================================================================

EPA_RECEPTOR_SECTIONS = """\
*** AERMOD - VERSION 24142 ***

*** DISCRETE CARTESIAN RECEPTORS ***
                                         (X-COORD, Y-COORD, ZELEV, ZHILL, ZFLAG)
                                                         (METERS)

     (   3500.0,  67750.0,  237.5,  239.3,    0.0);  (  3600.0,  69700.0,  319.3,  330.7,    0.0);
     (   4520.0,  69780.0,  296.7,  296.7,    1.5);
"""

EPA_RECEPTOR_XY_ONLY = """\
*** AERMOD - VERSION 24142 ***

*** DISCRETE CARTESIAN RECEPTORS ***

     (   100.0,   200.0);
"""


class TestEPAReceptorParsing:
    """Unit tests for _parse_receptors_epa()."""

    def test_epa_discrete_receptors_parsed(self, tmp_path):
        outfile = tmp_path / "epa_recepts.out"
        outfile.write_text(EPA_RECEPTOR_SECTIONS)
        results = parse_aermod_output(str(outfile))

        assert len(results.receptors) == 3

    def test_epa_receptor_coordinates(self, tmp_path):
        outfile = tmp_path / "epa_recepts.out"
        outfile.write_text(EPA_RECEPTOR_SECTIONS)
        results = parse_aermod_output(str(outfile))

        r0 = results.receptors[0]
        assert r0.x_coord == pytest.approx(3500.0)
        assert r0.y_coord == pytest.approx(67750.0)
        assert r0.z_elev == pytest.approx(237.5)
        assert r0.z_hill == pytest.approx(239.3)
        assert r0.z_flag == pytest.approx(0.0)

    def test_epa_receptor_with_zflag(self, tmp_path):
        outfile = tmp_path / "epa_recepts.out"
        outfile.write_text(EPA_RECEPTOR_SECTIONS)
        results = parse_aermod_output(str(outfile))

        # Third receptor has z_flag=1.5
        r2 = results.receptors[2]
        assert r2.z_flag == pytest.approx(1.5)

    def test_epa_receptor_only_xy(self, tmp_path):
        """Receptor with only x, y — elevations default to 0.0."""
        outfile = tmp_path / "epa_recepts_xy.out"
        outfile.write_text(EPA_RECEPTOR_XY_ONLY)
        results = parse_aermod_output(str(outfile))

        assert len(results.receptors) == 1
        r0 = results.receptors[0]
        assert r0.x_coord == pytest.approx(100.0)
        assert r0.y_coord == pytest.approx(200.0)
        assert r0.z_elev == pytest.approx(0.0)
        assert r0.z_hill == pytest.approx(0.0)


# ===========================================================================
# EPA VALUE IS edge cases
# ===========================================================================

EPA_VALUE_IS_MALFORMED = """\
*** AERMOD - VERSION 24142 ***

*** THE SUMMARY OF HIGHEST ANNUAL RESULTS ***

   ALL   1ST HIGHEST VALUE IS  NOT_A_NUMBER AT (  433.01,  -250.00,  0.00,  0.00,  0.00)
   ALL   2ND HIGHEST VALUE IS  20.00000 AT (  500.00,  -100.00,  0.00,  0.00,  0.00)
"""

EPA_VALUE_IS_ALL_BAD = """\
*** AERMOD - VERSION 24142 ***

*** THE SUMMARY OF HIGHEST ANNUAL RESULTS ***

   ALL   1ST HIGHEST VALUE IS  INVALID AT (  433.01,  -250.00,  0.00,  0.00,  0.00)
   ALL   2ND HIGHEST VALUE IS  ALSO_BAD AT (  500.00,  -100.00,  0.00,  0.00,  0.00)
"""


class TestEPAValueIsEdgeCases:
    """Test VALUE IS format with malformed concentration values."""

    def test_epa_value_is_malformed_skipped(self, tmp_path):
        """Non-numeric VALUE IS entries are skipped; valid ones still parsed."""
        outfile = tmp_path / "malformed.out"
        outfile.write_text(EPA_VALUE_IS_MALFORMED)
        results = parse_aermod_output(str(outfile))

        assert "ANNUAL" in results.concentrations
        assert len(results.concentrations["ANNUAL"].data) == 1
        assert results.concentrations["ANNUAL"].max_value == pytest.approx(20.0)

    def test_epa_value_is_all_malformed_returns_none(self, tmp_path):
        """When all VALUE IS entries are malformed, section is absent."""
        outfile = tmp_path / "all_bad.out"
        outfile.write_text(EPA_VALUE_IS_ALL_BAD)
        results = parse_aermod_output(str(outfile))

        assert "ANNUAL" not in results.concentrations

