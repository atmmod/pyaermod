"""
Unit tests for PyAERMOD output parser

Since we don't have a real AERMOD output file, we test the dataclasses,
the AERMODResults methods, and parser behavior with synthetic data.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
import os
from pyaermod.output_parser import (
    ModelRunInfo,
    SourceSummary,
    ReceptorInfo,
    ConcentrationResult,
    AERMODOutputParser,
    AERMODResults,
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
        with pytest.raises(ValueError, match="not found"):
            sample_results.get_concentrations("24HR")

    def test_get_max_concentration(self, sample_results):
        max_info = sample_results.get_max_concentration("ANNUAL")
        assert "value" in max_info
        assert "x" in max_info
        assert "y" in max_info
        assert "units" in max_info
        assert max_info["value"] > 0

    def test_get_max_concentration_missing_period(self, sample_results):
        with pytest.raises(ValueError, match="not found"):
            sample_results.get_max_concentration("1HR")

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
# Parser tests (with minimal synthetic output file)
# ---------------------------------------------------------------------------

MINIMAL_OUTPUT = """\
*** AERMOD - VERSION 24142 ***

Jobname: SYNTH_TEST
Run Date: 01-15-26
Run Time: 10:30:00

** Model Setup Options Selected **

*** SOURCE LOCATIONS ***

   SOURCE   TYPE       X-COORD      Y-COORD    BASE_ELEV
   STACK1   POINT      0.00         0.00        10.00

*** RECEPTOR LOCATIONS ***

   X-COORD      Y-COORD
   100.00       200.00
   300.00       400.00

*** ANNUAL RESULTS ***

   100.00    200.00    5.432
   300.00    400.00    2.876
"""


class TestAERMODOutputParser:
    """Test parser with synthetic output"""

    def test_parser_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            AERMODOutputParser("/nonexistent/path.out")

    def test_parse_header(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        parser = AERMODOutputParser(str(outfile))
        parser._parse_header()

        assert parser.run_info is not None
        assert parser.run_info.version == "24142"
        assert parser.run_info.jobname == "SYNTH_TEST"
        assert parser.run_info.run_date == "01-15-26"
        assert parser.run_info.run_time == "10:30:00"

    def test_parse_sources(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        parser = AERMODOutputParser(str(outfile))
        parser.run_info = ModelRunInfo("24142", "TEST")
        parser._parse_sources()

        assert len(parser.sources) == 1
        assert parser.sources[0].source_id == "STACK1"
        assert parser.sources[0].source_type == "POINT"

    def test_parse_receptors(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        parser = AERMODOutputParser(str(outfile))
        parser.run_info = ModelRunInfo("24142", "TEST")
        parser._parse_receptors()

        assert len(parser.receptors) == 2
        assert parser.receptors[0].x_coord == 100.0
        assert parser.receptors[1].y_coord == 400.0

    def test_parse_concentrations(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        parser = AERMODOutputParser(str(outfile))
        parser._parse_concentration_results()

        assert "ANNUAL" in parser.concentrations
        result = parser.concentrations["ANNUAL"]
        assert result.max_value == pytest.approx(5.432)
        assert len(result.data) == 2

    def test_full_parse(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        results = parse_aermod_output(str(outfile))
        assert results.run_info.jobname == "SYNTH_TEST"
        assert len(results.sources) == 1
        assert len(results.receptors) == 2
        assert "ANNUAL" in results.concentrations


class TestConvenienceFunctions:
    """Test module-level convenience functions"""

    def test_quick_summary(self, tmp_path):
        outfile = tmp_path / "test.out"
        outfile.write_text(MINIMAL_OUTPUT)

        summary = quick_summary(str(outfile))
        assert "AERMOD Results Summary" in summary
        assert "SYNTH_TEST" in summary
