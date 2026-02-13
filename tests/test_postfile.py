"""
Unit tests for PyAERMOD POSTFILE parser and OutputPathway POSTFILE keywords.

Tests parsing of AERMOD POSTFILE output files, including header extraction,
data line parsing, result queries, POSTFILE keyword generation in the
OutputPathway, and unformatted (binary) POSTFILE parsing.
"""

import struct
from pathlib import Path

import pandas as pd
import pytest

from pyaermod.input_generator import OutputPathway
from pyaermod.postfile import (
    PostfileHeader,
    PostfileParser,
    PostfileResult,
    UnformattedPostfileParser,
    _is_text_postfile,
    read_postfile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_POSTFILE = """\
* AERMOD ( 24142 ): Example POSTFILE Run
* MODELING OPTIONS USED: CONC FLAT
* AVERTIME: 1-HR
* POLLUTID: SO2
* SRCGROUP: ALL
* POSTFILE OUTPUT FOR SOURCE GROUP: ALL
*         X             Y      AVERAGE CONC   ZELEV  ZHILL  ZFLAG    AVE     GRP       DATE
   500.00      500.00      1.23456E+01    0.00    0.00    0.00   1-HR    ALL    26010101
   600.00      500.00      8.76543E+00    0.00    0.00    0.00   1-HR    ALL    26010101
   700.00      500.00      5.43210E+00    0.00    0.00    0.00   1-HR    ALL    26010101
   500.00      600.00      3.21000E+00    0.00    0.00    0.00   1-HR    ALL    26010101
   600.00      600.00      2.10000E+00    0.00    0.00    0.00   1-HR    ALL    26010101
   500.00      500.00      9.87654E+00    0.00    0.00    0.00   1-HR    ALL    26010102
   600.00      500.00      7.65432E+00    0.00    0.00    0.00   1-HR    ALL    26010102
   700.00      500.00      4.32100E+00    0.00    0.00    0.00   1-HR    ALL    26010102
   500.00      600.00      2.10000E+00    0.00    0.00    0.00   1-HR    ALL    26010102
   600.00      600.00      1.50000E+00    0.00    0.00    0.00   1-HR    ALL    26010102
"""


@pytest.fixture
def sample_postfile(tmp_path):
    """Write sample POSTFILE content to a temp file and return its path."""
    filepath = tmp_path / "sample.pst"
    filepath.write_text(SAMPLE_POSTFILE)
    return filepath


@pytest.fixture
def empty_postfile(tmp_path):
    """Write an empty (header-only) POSTFILE to a temp file."""
    content = """\
* AERMOD ( 24142 ): Empty Run
* MODELING OPTIONS USED: CONC FLAT
* AVERTIME: ANNUAL
* POLLUTID: PM25
* SRCGROUP: ALL
"""
    filepath = tmp_path / "empty.pst"
    filepath.write_text(content)
    return filepath


@pytest.fixture
def parsed_result(sample_postfile):
    """Return a PostfileResult parsed from the sample POSTFILE."""
    parser = PostfileParser(sample_postfile)
    return parser.parse()


# ===========================================================================
# TestPostfileHeader
# ===========================================================================

class TestPostfileHeader:
    """Test parsing of each POSTFILE header field."""

    def test_version_parsed(self, parsed_result):
        """AERMOD version is extracted from the header."""
        assert parsed_result.header.version == "24142"

    def test_title_parsed(self, parsed_result):
        """Run title is extracted from the AERMOD header line."""
        assert parsed_result.header.title == "Example POSTFILE Run"

    def test_model_options_parsed(self, parsed_result):
        """Modeling options string is extracted."""
        assert parsed_result.header.model_options == "CONC FLAT"

    def test_averaging_period_parsed(self, parsed_result):
        """Averaging period is extracted from the AVERTIME header."""
        assert parsed_result.header.averaging_period == "1-HR"

    def test_pollutant_id_parsed(self, parsed_result):
        """Pollutant ID is extracted from the POLLUTID header."""
        assert parsed_result.header.pollutant_id == "SO2"

    def test_source_group_parsed(self, parsed_result):
        """Source group is extracted from the SRCGROUP header."""
        assert parsed_result.header.source_group == "ALL"

    def test_default_header_values(self):
        """PostfileHeader fields default to None."""
        header = PostfileHeader()
        assert header.version is None
        assert header.title is None
        assert header.model_options is None
        assert header.averaging_period is None
        assert header.pollutant_id is None
        assert header.source_group is None


# ===========================================================================
# TestPostfileParser
# ===========================================================================

class TestPostfileParser:
    """Test PostfileParser functionality."""

    def test_parse_basic_postfile(self, sample_postfile):
        """Parser returns a PostfileResult with correct data shape."""
        parser = PostfileParser(sample_postfile)
        result = parser.parse()

        assert isinstance(result, PostfileResult)
        assert len(result.data) == 10
        assert list(result.data.columns) == [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "date",
        ]

    def test_parse_empty_postfile(self, empty_postfile):
        """Parser handles a POSTFILE with headers only (no data lines)."""
        parser = PostfileParser(empty_postfile)
        result = parser.parse()

        assert isinstance(result, PostfileResult)
        assert result.data.empty
        assert result.header.version == "24142"
        assert result.header.pollutant_id == "PM25"

    def test_parse_file_not_found(self, tmp_path):
        """Parser raises FileNotFoundError for a missing file."""
        missing = tmp_path / "does_not_exist.pst"
        with pytest.raises(FileNotFoundError):
            PostfileParser(missing)

    def test_parse_multiple_timesteps(self, parsed_result):
        """Parser captures data across multiple timesteps."""
        dates = parsed_result.data["date"].unique()
        assert len(dates) == 2
        assert "26010101" in dates
        assert "26010102" in dates

    def test_parse_scientific_notation(self, parsed_result):
        """Concentrations in scientific notation are parsed correctly."""
        # First data row: 1.23456E+01 = 12.3456
        first_conc = parsed_result.data.iloc[0]["concentration"]
        assert abs(first_conc - 12.3456) < 1e-4

        # Second data row: 8.76543E+00 = 8.76543
        second_conc = parsed_result.data.iloc[1]["concentration"]
        assert abs(second_conc - 8.76543) < 1e-4


# ===========================================================================
# TestPostfileResult
# ===========================================================================

class TestPostfileResult:
    """Test PostfileResult properties and methods."""

    def test_max_concentration(self, parsed_result):
        """max_concentration returns the global maximum."""
        # 1.23456E+01 = 12.3456 is the largest value
        assert abs(parsed_result.max_concentration - 12.3456) < 1e-4

    def test_max_location(self, parsed_result):
        """max_location returns (x, y) of the maximum concentration."""
        x, y = parsed_result.max_location
        assert abs(x - 500.0) < 1e-2
        assert abs(y - 500.0) < 1e-2

    def test_get_timestep(self, parsed_result):
        """get_timestep returns rows for the specified date."""
        ts1 = parsed_result.get_timestep("26010101")
        assert len(ts1) == 5

        ts2 = parsed_result.get_timestep("26010102")
        assert len(ts2) == 5

        ts_missing = parsed_result.get_timestep("99999999")
        assert ts_missing.empty

    def test_get_receptor(self, parsed_result):
        """get_receptor returns rows matching a receptor location."""
        rows = parsed_result.get_receptor(500.0, 500.0)
        assert len(rows) == 2  # Two timesteps at (500, 500)

        # Check concentrations at that receptor
        concs = sorted(rows["concentration"].tolist(), reverse=True)
        assert abs(concs[0] - 12.3456) < 1e-4
        assert abs(concs[1] - 9.87654) < 1e-4

    def test_get_receptor_with_tolerance(self, parsed_result):
        """get_receptor respects the tolerance parameter."""
        # Tight tolerance should still find exact matches
        rows_tight = parsed_result.get_receptor(500.0, 500.0, tolerance=0.01)
        assert len(rows_tight) == 2

        # Offset beyond tolerance yields no results
        rows_none = parsed_result.get_receptor(505.0, 505.0, tolerance=1.0)
        assert rows_none.empty

    def test_get_max_by_receptor(self, parsed_result):
        """get_max_by_receptor returns max concentration per receptor."""
        max_df = parsed_result.get_max_by_receptor()

        # 5 unique receptor locations
        assert len(max_df) == 5

        # Check that the overall max is present
        overall_max = max_df["concentration"].max()
        assert abs(overall_max - 12.3456) < 1e-4

    def test_to_dataframe(self, parsed_result):
        """to_dataframe returns a copy of the data."""
        df = parsed_result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 10

        # Modifying the copy does not affect the original
        df.iloc[0, df.columns.get_loc("concentration")] = -999.0
        assert parsed_result.data.iloc[0]["concentration"] != -999.0

    def test_empty_result(self, empty_postfile):
        """Properties handle empty data gracefully."""
        parser = PostfileParser(empty_postfile)
        result = parser.parse()

        assert result.max_concentration == 0.0
        assert result.max_location == (0.0, 0.0)
        assert result.get_timestep("26010101").empty
        assert result.get_receptor(0.0, 0.0).empty
        assert result.get_max_by_receptor().empty
        assert result.to_dataframe().empty


# ===========================================================================
# TestReadPostfile
# ===========================================================================

class TestReadPostfile:
    """Test the read_postfile convenience function."""

    def test_convenience_function(self, sample_postfile):
        """read_postfile produces the same result as PostfileParser.parse."""
        result = read_postfile(sample_postfile)

        assert isinstance(result, PostfileResult)
        assert result.header.version == "24142"
        assert len(result.data) == 10
        assert abs(result.max_concentration - 12.3456) < 1e-4


# ===========================================================================
# TestOutputPathwayPostfile
# ===========================================================================

class TestOutputPathwayPostfile:
    """Test POSTFILE keyword generation in OutputPathway."""

    def test_postfile_keyword_generation(self):
        """OutputPathway generates correct POSTFILE keyword line."""
        ou = OutputPathway(
            postfile="output.pst",
            postfile_averaging="1",
            postfile_source_group="ALL",
            postfile_format="PLOT",
        )
        output = ou.to_aermod_input()

        assert "POSTFILE" in output
        assert "1" in output
        assert "ALL" in output
        assert "PLOT" in output
        assert "output.pst" in output

        # POSTFILE line should appear between OU STARTING and OU FINISHED
        lines = output.split("\n")
        postfile_line = [l for l in lines if "POSTFILE" in l]
        assert len(postfile_line) == 1

    def test_postfile_default_values(self):
        """OutputPathway uses defaults when only postfile path is set."""
        ou = OutputPathway(postfile="result.pst")
        output = ou.to_aermod_input()

        # Default averaging is ANNUAL, source_group is ALL, format is PLOT
        assert "POSTFILE" in output
        assert "ANNUAL" in output
        assert "ALL" in output
        assert "PLOT" in output
        assert "result.pst" in output

    def test_no_postfile(self):
        """OutputPathway omits POSTFILE line when postfile is None."""
        ou = OutputPathway()
        output = ou.to_aermod_input()

        assert "POSTFILE" not in output

    def test_postfile_with_other_outputs(self):
        """POSTFILE keyword coexists with other output keywords."""
        ou = OutputPathway(
            receptor_table=True,
            max_table=True,
            summary_file="summary.txt",
            postfile="conc.pst",
            postfile_averaging="24",
            postfile_source_group="STACKS",
            postfile_format="PLOT",
        )
        output = ou.to_aermod_input()

        assert "OU STARTING" in output
        assert "RECTABLE" in output
        assert "MAXTABLE" in output
        assert "SUMMFILE" in output
        assert "POSTFILE" in output
        assert "OU FINISHED" in output


# ===========================================================================
# Binary POSTFILE helpers
# ===========================================================================

def _build_binary_record(kurdat, ianhrs, grpid, concentrations):
    """
    Build a single Fortran unformatted sequential record.

    Parameters
    ----------
    kurdat : int
        Date integer (YYMMDDHH).
    ianhrs : int
        Hours in averaging period.
    grpid : str
        Source group ID (max 8 chars, space-padded).
    concentrations : list of float
        Concentration values (float64) for each receptor.

    Returns
    -------
    bytes
        Complete Fortran record with leading/trailing length markers.
    """
    grpid_bytes = grpid.ljust(8)[:8].encode("ascii")
    payload = struct.pack("<i", kurdat)
    payload += struct.pack("<i", ianhrs)
    payload += grpid_bytes
    for c in concentrations:
        payload += struct.pack("<d", c)
    rec_len = len(payload)
    return struct.pack("<i", rec_len) + payload + struct.pack("<i", rec_len)


@pytest.fixture
def binary_postfile(tmp_path):
    """Create a synthetic binary POSTFILE with 2 timesteps, 3 receptors."""
    filepath = tmp_path / "binary.pst"
    data = b""
    # Timestep 1: 26010101, 1 hour, group ALL, 3 receptor concentrations
    data += _build_binary_record(26010101, 1, "ALL", [10.5, 20.3, 5.1])
    # Timestep 2: 26010102, 1 hour, group ALL, 3 receptor concentrations
    data += _build_binary_record(26010102, 1, "ALL", [8.2, 15.7, 3.9])
    filepath.write_bytes(data)
    return filepath


@pytest.fixture
def binary_postfile_with_coords(tmp_path):
    """Create a synthetic binary POSTFILE with known receptor coordinates."""
    filepath = tmp_path / "binary_coords.pst"
    data = b""
    data += _build_binary_record(26010101, 1, "ALL", [12.0, 24.0])
    filepath.write_bytes(data)
    return filepath


# ===========================================================================
# TestUnformattedPostfileParser
# ===========================================================================

class TestUnformattedPostfileParser:
    """Test UnformattedPostfileParser for binary POSTFILE files."""

    def test_parse_binary_postfile(self, binary_postfile):
        """Parser reads binary records and returns correct data shape."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        assert isinstance(result, PostfileResult)
        # 2 timesteps × 3 receptors = 6 rows
        assert len(result.data) == 6
        assert list(result.data.columns) == [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "date",
        ]

    def test_binary_num_receptors_inference(self, binary_postfile):
        """Parser infers num_receptors from first record size."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        assert parser.num_receptors == 3
        # Each timestep has 3 concentration values
        ts1 = result.get_timestep("26010101")
        assert len(ts1) == 3

    def test_binary_receptor_coords(self, binary_postfile_with_coords):
        """User-supplied receptor coordinates are applied correctly."""
        coords = [(100.0, 200.0), (300.0, 400.0)]
        parser = UnformattedPostfileParser(
            binary_postfile_with_coords,
            receptor_coords=coords,
        )
        result = parser.parse()

        assert len(result.data) == 2
        assert result.data.iloc[0]["x"] == 100.0
        assert result.data.iloc[0]["y"] == 200.0
        assert result.data.iloc[1]["x"] == 300.0
        assert result.data.iloc[1]["y"] == 400.0

    def test_binary_concentration_values(self, binary_postfile):
        """Concentration values are parsed correctly from binary data."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        ts1 = result.get_timestep("26010101")
        concs = ts1["concentration"].tolist()
        assert abs(concs[0] - 10.5) < 1e-10
        assert abs(concs[1] - 20.3) < 1e-10
        assert abs(concs[2] - 5.1) < 1e-10

        ts2 = result.get_timestep("26010102")
        concs2 = ts2["concentration"].tolist()
        assert abs(concs2[0] - 8.2) < 1e-10
        assert abs(concs2[1] - 15.7) < 1e-10
        assert abs(concs2[2] - 3.9) < 1e-10

    def test_binary_date_conversion(self, binary_postfile):
        """KURDAT integers are converted to YYMMDDHH date strings."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        dates = sorted(result.data["date"].unique())
        assert dates == ["26010101", "26010102"]

    def test_binary_multiple_timesteps(self, binary_postfile):
        """Parser handles multiple timesteps in a single file."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        dates = result.data["date"].unique()
        assert len(dates) == 2

    def test_binary_header_populated(self, binary_postfile):
        """Header is populated from first binary record."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        assert result.header.source_group == "ALL"
        assert result.header.averaging_period == "1-HR"
        # These are not available in binary format
        assert result.header.version is None
        assert result.header.title is None
        assert result.header.model_options is None
        assert result.header.pollutant_id is None

    def test_binary_default_coords(self, binary_postfile):
        """Without receptor_coords, index-based coordinates are used."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        ts1 = result.get_timestep("26010101")
        xs = ts1["x"].tolist()
        ys = ts1["y"].tolist()
        assert xs == [0.0, 1.0, 2.0]
        assert ys == [0.0, 0.0, 0.0]

    def test_binary_zelev_zhill_zflag_zero(self, binary_postfile):
        """Binary format sets zelev, zhill, zflag to 0.0."""
        parser = UnformattedPostfileParser(binary_postfile)
        result = parser.parse()

        assert (result.data["zelev"] == 0.0).all()
        assert (result.data["zhill"] == 0.0).all()
        assert (result.data["zflag"] == 0.0).all()

    def test_binary_file_not_found(self, tmp_path):
        """Parser raises FileNotFoundError for missing file."""
        missing = tmp_path / "no_such_file.pst"
        with pytest.raises(FileNotFoundError):
            UnformattedPostfileParser(missing)

    def test_binary_empty_file(self, tmp_path):
        """Parser handles an empty binary file gracefully."""
        filepath = tmp_path / "empty.bin"
        filepath.write_bytes(b"")
        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()

        assert result.data.empty

    def test_binary_24hr_averaging(self, tmp_path):
        """Parser correctly labels 24-HR averaging period."""
        filepath = tmp_path / "24hr.pst"
        data = _build_binary_record(26010124, 24, "STACKS", [100.0, 200.0])
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()

        assert result.header.averaging_period == "24-HR"
        assert result.header.source_group == "STACKS"
        assert result.data.iloc[0]["grp"] == "STACKS"


# ===========================================================================
# TestAutoDetectFormat
# ===========================================================================

class TestAutoDetectFormat:
    """Test format auto-detection and read_postfile dispatch."""

    def test_detect_text_format(self, sample_postfile):
        """Text POSTFILE starting with '*' is detected as text."""
        assert _is_text_postfile(sample_postfile) is True

    def test_detect_binary_format(self, binary_postfile):
        """Binary POSTFILE not starting with '*' is detected as binary."""
        assert _is_text_postfile(binary_postfile) is False

    def test_detect_empty_file(self, tmp_path):
        """Empty file is treated as text format."""
        fp = tmp_path / "empty.pst"
        fp.write_bytes(b"")
        assert _is_text_postfile(fp) is True

    def test_read_postfile_text_dispatch(self, sample_postfile):
        """read_postfile correctly dispatches to text parser."""
        result = read_postfile(sample_postfile)
        assert isinstance(result, PostfileResult)
        assert result.header.version == "24142"
        assert len(result.data) == 10

    def test_read_postfile_binary_dispatch(self, binary_postfile):
        """read_postfile correctly dispatches to binary parser."""
        result = read_postfile(binary_postfile)
        assert isinstance(result, PostfileResult)
        assert len(result.data) == 6
        assert result.header.source_group == "ALL"

    def test_read_postfile_binary_with_coords(self, binary_postfile_with_coords):
        """read_postfile passes receptor_coords to binary parser."""
        coords = [(500.0, 600.0), (700.0, 800.0)]
        result = read_postfile(
            binary_postfile_with_coords,
            receptor_coords=coords,
        )
        assert result.data.iloc[0]["x"] == 500.0
        assert result.data.iloc[0]["y"] == 600.0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
