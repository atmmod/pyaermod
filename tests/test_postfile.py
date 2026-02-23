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


# ===========================================================================
# Binary Deposition helpers + tests
# ===========================================================================

def _build_binary_deposition_record(kurdat, ianhrs, grpid, concs, dry_deps, wet_deps):
    """
    Build a Fortran unformatted record with deposition data.

    AERMOD writes deposition records as contiguous blocks:
    [CONC_1..CONC_N, DRY_1..DRY_N, WET_1..WET_N]
    """
    grpid_bytes = grpid.ljust(8)[:8].encode("ascii")
    payload = struct.pack("<i", kurdat)
    payload += struct.pack("<i", ianhrs)
    payload += grpid_bytes
    for c in concs:
        payload += struct.pack("<d", c)
    for d in dry_deps:
        payload += struct.pack("<d", d)
    for w in wet_deps:
        payload += struct.pack("<d", w)
    rec_len = len(payload)
    return struct.pack("<i", rec_len) + payload + struct.pack("<i", rec_len)


class TestBinaryDepositionPostfile:
    """Test binary POSTFILE parsing with deposition data (3×N floats)."""

    def test_explicit_deposition_flag(self, tmp_path):
        """has_deposition=True parses 3N floats into conc/dry/wet columns."""
        filepath = tmp_path / "dep.bin"
        data = _build_binary_deposition_record(
            26010101, 1, "ALL",
            [10.0, 20.0],        # concentrations
            [0.5, 1.0],          # dry deposition
            [2.0, 3.0],          # wet deposition
        )
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath, has_deposition=True)
        result = parser.parse()

        assert len(result.data) == 2
        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns
        assert result.data.iloc[0]["concentration"] == pytest.approx(10.0)
        assert result.data.iloc[0]["dry_depo"] == pytest.approx(0.5)
        assert result.data.iloc[0]["wet_depo"] == pytest.approx(2.0)
        assert result.data.iloc[1]["concentration"] == pytest.approx(20.0)
        assert result.data.iloc[1]["dry_depo"] == pytest.approx(1.0)
        assert result.data.iloc[1]["wet_depo"] == pytest.approx(3.0)

    def test_auto_detect_deposition(self, tmp_path):
        """Auto-detect deposition when num_receptors given and 3N floats."""
        filepath = tmp_path / "auto_dep.bin"
        data = _build_binary_deposition_record(
            26010101, 1, "ALL",
            [5.0, 6.0, 7.0],    # 3 receptors
            [0.1, 0.2, 0.3],
            [1.1, 1.2, 1.3],
        )
        filepath.write_bytes(data)

        # 9 floats with num_receptors=3 → auto-detect deposition
        parser = UnformattedPostfileParser(
            filepath, num_receptors=3, has_deposition=None
        )
        result = parser.parse()

        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns
        assert len(result.data) == 3
        assert result.data.iloc[2]["concentration"] == pytest.approx(7.0)
        assert result.data.iloc[2]["dry_depo"] == pytest.approx(0.3)
        assert result.data.iloc[2]["wet_depo"] == pytest.approx(1.3)

    def test_deposition_multiple_timesteps(self, tmp_path):
        """Multiple deposition records parsed correctly."""
        filepath = tmp_path / "multi_dep.bin"
        data = _build_binary_deposition_record(
            26010101, 1, "ALL",
            [10.0, 20.0], [0.5, 1.0], [2.0, 3.0],
        )
        data += _build_binary_deposition_record(
            26010102, 1, "ALL",
            [15.0, 25.0], [0.7, 1.2], [2.5, 3.5],
        )
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath, has_deposition=True)
        result = parser.parse()

        assert len(result.data) == 4  # 2 timesteps × 2 receptors
        ts2 = result.data[result.data["date"] == "26010102"]
        assert len(ts2) == 2
        assert ts2.iloc[0]["concentration"] == pytest.approx(15.0)
        assert ts2.iloc[1]["dry_depo"] == pytest.approx(1.2)
        assert ts2.iloc[1]["wet_depo"] == pytest.approx(3.5)

    def test_read_postfile_deposition_passthrough(self, tmp_path):
        """read_postfile passes has_deposition to binary parser."""
        filepath = tmp_path / "pass.bin"
        data = _build_binary_deposition_record(
            26010101, 1, "GRP1",
            [100.0], [5.0], [10.0],
        )
        filepath.write_bytes(data)

        result = read_postfile(filepath, has_deposition=True)
        assert "dry_depo" in result.data.columns
        assert result.data.iloc[0]["dry_depo"] == pytest.approx(5.0)
        assert result.header.source_group == "GRP1"

    def test_deposition_empty_file(self, tmp_path):
        """Empty file with has_deposition=True has correct columns."""
        filepath = tmp_path / "empty_dep.bin"
        filepath.write_bytes(b"")

        parser = UnformattedPostfileParser(filepath, has_deposition=True)
        result = parser.parse()

        assert result.data.empty
        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns
        assert "concentration" in result.data.columns

    def test_deposition_header_populated(self, tmp_path):
        """Header gets averaging_period/source_group from first depo record."""
        filepath = tmp_path / "header_dep.bin"
        data = _build_binary_deposition_record(
            26010124, 24, "STACKS",
            [50.0], [2.0], [8.0],
        )
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath, has_deposition=True)
        result = parser.parse()

        assert result.header.averaging_period == "24-HR"
        assert result.header.source_group == "STACKS"
        assert result.header.version is None

    def test_deposition_not_divisible_by_3_raises(self, tmp_path):
        """has_deposition=True with non-3N floats raises ValueError."""
        filepath = tmp_path / "bad_dep.bin"
        # Build a record with only 2 floats (not divisible by 3)
        data = _build_binary_record(26010101, 1, "ALL", [10.0, 20.0])
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath, has_deposition=True)
        with pytest.raises(ValueError, match="not divisible by 3"):
            parser.parse()

    def test_deposition_num_receptors_mismatch_raises(self, tmp_path):
        """Explicit num_receptors conflicts with deposition record size."""
        filepath = tmp_path / "mismatch_dep.bin"
        # 3 concs + 3 dry + 3 wet = 9 floats → 3 receptors
        data = _build_binary_deposition_record(
            26010101, 1, "ALL",
            [1.0, 2.0, 3.0], [0.1, 0.2, 0.3], [0.4, 0.5, 0.6],
        )
        filepath.write_bytes(data)

        # But claim 5 receptors
        parser = UnformattedPostfileParser(
            filepath, num_receptors=5, has_deposition=True
        )
        with pytest.raises(ValueError, match="receptors"):
            parser.parse()


class TestTextPostfileEdgeCases:
    """Test text POSTFILE edge cases (lines 343, 390-391, 494, 529-530)."""

    def test_data_line_too_few_parts(self, tmp_path):
        """Line with <9 parts returns None → skipped (covers line 343)."""
        content = """\
* AERMOD ( 24142 ): Edge Case
* MODELING OPTIONS USED: CONC FLAT
* AVERTIME: 1-HR
* POLLUTID: SO2
* SRCGROUP: ALL
*         X             Y      AVERAGE CONC   ZELEV  ZHILL  ZFLAG    AVE     GRP       DATE
   500.00      500.00      1.23456E+01    0.00    0.00    0.00   1-HR    ALL    26010101
   too few parts here
   600.00      500.00      8.76543E+00    0.00    0.00    0.00   1-HR    ALL    26010101
"""
        filepath = tmp_path / "few_parts.pst"
        filepath.write_text(content)
        result = read_postfile(filepath)
        # The malformed line is skipped, only 2 valid data rows
        assert len(result.data) == 2

    def test_malformed_float_in_data_line(self, tmp_path):
        """Non-numeric in float position returns None (covers lines 390-391)."""
        content = """\
* AERMOD ( 24142 ): Malformed
* MODELING OPTIONS USED: CONC FLAT
* AVERTIME: 1-HR
* POLLUTID: SO2
* SRCGROUP: ALL
*         X             Y      AVERAGE CONC   ZELEV  ZHILL  ZFLAG    AVE     GRP       DATE
   500.00      500.00      1.23456E+01    0.00    0.00    0.00   1-HR    ALL    26010101
   abc.xx      500.00      BADVALUE       0.00    0.00    0.00   1-HR    ALL    26010101
   600.00      500.00      8.76543E+00    0.00    0.00    0.00   1-HR    ALL    26010101
"""
        filepath = tmp_path / "bad_float.pst"
        filepath.write_text(content)
        result = read_postfile(filepath)
        # The malformed line is skipped
        assert len(result.data) == 2

    def test_binary_other_averaging_period(self, tmp_path):
        """Averaging period not 1 or 24 → e.g. '3-HR' (covers line 494)."""
        filepath = tmp_path / "3hr.pst"
        data = _build_binary_record(26010103, 3, "ALL", [10.0, 20.0])
        filepath.write_bytes(data)
        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()
        assert result.header.averaging_period == "3-HR"

    def test_binary_conc_only_num_receptors_mismatch(self, tmp_path):
        """Conc-only mode: num_receptors given but record has different count."""
        filepath = tmp_path / "mismatch_conc.pst"
        # Record has 3 floats (concentrations only)
        data = _build_binary_record(26010101, 1, "ALL", [1.0, 2.0, 3.0])
        filepath.write_bytes(data)
        # Claim 5 receptors, but 3 floats (not deposition since has_deposition=False)
        parser = UnformattedPostfileParser(
            filepath, num_receptors=5, has_deposition=False
        )
        with pytest.raises(ValueError, match="Expected"):
            parser.parse()


class TestBinaryEdgeCases:
    """Test binary POSTFILE edge cases for robust error handling."""

    def test_truncated_record_payload(self, tmp_path):
        """Payload shorter than rec_len → graceful empty result."""
        filepath = tmp_path / "truncated.bin"
        # Write a leading marker claiming 100 bytes but only 10 bytes of payload
        data = struct.pack("<i", 100) + b"\x00" * 10
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()
        assert result.data.empty

    def test_missing_trailing_marker(self, tmp_path):
        """No trailing 4 bytes → graceful empty result."""
        filepath = tmp_path / "no_trail.bin"
        # Build valid payload but cut off the trailing marker
        grpid_bytes = b"ALL     "
        payload = struct.pack("<i", 26010101) + struct.pack("<i", 1) + grpid_bytes
        payload += struct.pack("<d", 10.0)
        rec_len = len(payload)
        # Only write leading marker + payload, NO trailing marker
        data = struct.pack("<i", rec_len) + payload
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()
        assert result.data.empty

    def test_mismatched_record_markers(self, tmp_path):
        """Leading ≠ trailing record marker → ValueError."""
        filepath = tmp_path / "mismatch.bin"
        grpid_bytes = b"ALL     "
        payload = struct.pack("<i", 26010101) + struct.pack("<i", 1) + grpid_bytes
        payload += struct.pack("<d", 10.0)
        rec_len = len(payload)
        # Write leading marker, payload, then WRONG trailing marker
        data = struct.pack("<i", rec_len) + payload + struct.pack("<i", rec_len + 99)
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        with pytest.raises(ValueError, match="mismatch"):
            parser.parse()

    def test_payload_too_short_for_header(self, tmp_path):
        """Payload < 16 bytes (can't hold KURDAT+IANHRS+GRPID) → empty."""
        filepath = tmp_path / "tiny.bin"
        # 8 bytes of payload (only KURDAT + IANHRS, no GRPID)
        payload = struct.pack("<i", 26010101) + struct.pack("<i", 1)
        rec_len = len(payload)
        data = struct.pack("<i", rec_len) + payload + struct.pack("<i", rec_len)
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        result = parser.parse()
        assert result.data.empty

    def test_receptor_count_mismatch_raises(self, tmp_path):
        """Second record has different float count → ValueError."""
        filepath = tmp_path / "count_change.bin"
        # Record 1: 3 receptors
        data = _build_binary_record(26010101, 1, "ALL", [1.0, 2.0, 3.0])
        # Record 2: 2 receptors (should fail)
        data += _build_binary_record(26010102, 1, "ALL", [4.0, 5.0])
        filepath.write_bytes(data)

        parser = UnformattedPostfileParser(filepath)
        with pytest.raises(ValueError, match="Expected"):
            parser.parse()


# ===========================================================================
# Synthetic Deposition Format (12-column)
# ===========================================================================

SAMPLE_DEPOSITION_POSTFILE = """\
* AERMOD ( 24142 ): Deposition Test Case
* MODELING OPTIONS USED: NonDFAULT CONC DDEP WDEP FLAT DRYDPLT WETDPLT
* FORMAT: (5(1X,F13.5),3(1X,F8.2),2A,A8,2X,A6,2X,A5)
* POST/PLOT FILE OF CONCURRENT 1-HR VALUES FOR SOURCE GROUP: ALL
*         X             Y      AVERAGE CONC    DRY DEPO    WET DEPO  ZELEV  ZHILL  ZFLAG    AVE     GRP       DATE
      0.00000     100.00000      15.21444       0.55937       8.01199    0.00    0.00    0.00   1-HR    ALL    90010101
    100.00000     100.00000      10.50000       0.30000       5.20000    0.00    0.00    0.00   1-HR    ALL    90010101
      0.00000     200.00000       8.75000       0.25000       3.10000   10.00    5.00    0.00   1-HR    ALL    90010101
"""


@pytest.fixture
def deposition_postfile(tmp_path):
    """Write synthetic deposition POSTFILE to temp file."""
    filepath = tmp_path / "deposition.pst"
    filepath.write_text(SAMPLE_DEPOSITION_POSTFILE)
    return filepath


class TestDepositionPostfileParser:
    """Test parsing of deposition-format postfiles (5 float columns)."""

    def test_deposition_detected_from_format_line(self, deposition_postfile):
        """FORMAT: (5(1X,F13.5)... sets _is_deposition flag."""
        parser = PostfileParser(deposition_postfile)
        result = parser.parse()
        assert parser._is_deposition is True
        assert parser._is_plotfile is False
        assert len(result.data) == 3

    def test_deposition_column_names(self, deposition_postfile):
        """Deposition postfile has dry_depo and wet_depo columns."""
        result = read_postfile(deposition_postfile)
        expected = [
            "x", "y", "concentration", "dry_depo", "wet_depo",
            "zelev", "zhill", "zflag", "ave", "grp", "date",
        ]
        assert list(result.data.columns) == expected

    def test_deposition_xy_correct(self, deposition_postfile):
        """X and Y coordinates are parsed correctly."""
        result = read_postfile(deposition_postfile)
        assert result.data.iloc[0]["x"] == pytest.approx(0.0, abs=0.01)
        assert result.data.iloc[0]["y"] == pytest.approx(100.0, abs=0.01)

    def test_deposition_concentration_correct(self, deposition_postfile):
        """Concentration values parsed correctly."""
        result = read_postfile(deposition_postfile)
        assert result.data.iloc[0]["concentration"] == pytest.approx(15.21444, abs=1e-4)

    def test_deposition_dry_wet_values(self, deposition_postfile):
        """Dry and wet deposition columns have correct values."""
        result = read_postfile(deposition_postfile)
        assert result.data.iloc[0]["dry_depo"] == pytest.approx(0.55937, abs=1e-4)
        assert result.data.iloc[0]["wet_depo"] == pytest.approx(8.01199, abs=1e-4)

    def test_deposition_zelev_not_shifted(self, deposition_postfile):
        """zelev correctly parsed (not shifted to dry_depo column)."""
        result = read_postfile(deposition_postfile)
        assert result.data.iloc[0]["zelev"] == pytest.approx(0.0, abs=0.01)
        # Third row has non-zero zelev
        assert result.data.iloc[2]["zelev"] == pytest.approx(10.0, abs=0.01)

    def test_deposition_ave_grp_date(self, deposition_postfile):
        """Ave, grp, and date columns correctly parsed."""
        result = read_postfile(deposition_postfile)
        assert result.data.iloc[0]["ave"] == "1-HR"
        assert result.data.iloc[0]["grp"] == "ALL"
        assert result.data.iloc[0]["date"] == "90010101"

    def test_deposition_header_parsed(self, deposition_postfile):
        """EPA header format parsed for deposition files."""
        result = read_postfile(deposition_postfile)
        assert result.header.averaging_period == "1-HR"
        assert result.header.source_group == "ALL"
        assert result.header.version == "24142"

    def test_deposition_max_concentration(self, deposition_postfile):
        """Max concentration works with deposition format."""
        result = read_postfile(deposition_postfile)
        assert result.max_concentration == pytest.approx(15.21444, abs=1e-4)

    def test_deposition_empty_data(self, tmp_path):
        """Empty deposition file creates correct column structure."""
        content = """\
* AERMOD ( 24142 ): Empty Deposition
* MODELING OPTIONS USED: CONC DDEP WDEP FLAT
* FORMAT: (5(1X,F13.5),3(1X,F8.2),2A,A8,2X,A6,2X,A5)
"""
        filepath = tmp_path / "empty_dep.pst"
        filepath.write_text(content)
        result = read_postfile(filepath)
        assert result.data.empty
        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns


# ===========================================================================
# Synthetic Plotfile Format (with RANK column)
# ===========================================================================

SAMPLE_PLOTFILE = """\
* AERMOD ( 24142 ): Plotfile Test Case
* MODELING OPTIONS USED: CONC FLAT
* PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL
*         X             Y      AVERAGE CONC   ZELEV  ZHILL  ZFLAG    AVE     GRP     RANK   NETID       DATE(CONC)
   500.00000     500.00000      12.34560    0.00    0.00    0.00   1-HR    ALL       1ST    GC001    26010101
   600.00000     500.00000       8.76543    0.00    0.00    0.00   1-HR    ALL       1ST    GC001    26010102
   700.00000     500.00000       5.43210   10.00    5.00    0.00   1-HR    ALL       1ST    GC002    26010103
"""


@pytest.fixture
def plotfile(tmp_path):
    """Write synthetic plotfile to temp file."""
    filepath = tmp_path / "sample.plt"
    filepath.write_text(SAMPLE_PLOTFILE)
    return filepath


class TestPlotfileParser:
    """Test parsing of plotfile-format files (with RANK column)."""

    def test_plotfile_detected_from_header(self, plotfile):
        """'PLOT FILE OF HIGH' sets _is_plotfile flag."""
        parser = PostfileParser(plotfile)
        result = parser.parse()
        assert parser._is_plotfile is True
        assert parser._is_deposition is False
        assert len(result.data) == 3

    def test_plotfile_column_names(self, plotfile):
        """Plotfile has rank column in addition to standard columns."""
        result = read_postfile(plotfile)
        expected = [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "rank", "date",
        ]
        assert list(result.data.columns) == expected

    def test_plotfile_rank_column(self, plotfile):
        """Rank column has correct values."""
        result = read_postfile(plotfile)
        assert result.data.iloc[0]["rank"] == "1ST"
        assert (result.data["rank"] == "1ST").all()

    def test_plotfile_date_is_real(self, plotfile):
        """Date column has YYMMDDHH dates, not rank values."""
        result = read_postfile(plotfile)
        assert result.data.iloc[0]["date"] == "26010101"
        assert result.data.iloc[1]["date"] == "26010102"
        assert result.data.iloc[2]["date"] == "26010103"

    def test_plotfile_concentration_correct(self, plotfile):
        """Concentration values parsed correctly."""
        result = read_postfile(plotfile)
        assert result.data.iloc[0]["concentration"] == pytest.approx(12.3456, abs=1e-4)

    def test_plotfile_zelev_correct(self, plotfile):
        """Zelev values parsed correctly (not shifted)."""
        result = read_postfile(plotfile)
        assert result.data.iloc[0]["zelev"] == pytest.approx(0.0, abs=0.01)
        assert result.data.iloc[2]["zelev"] == pytest.approx(10.0, abs=0.01)

    def test_plotfile_header_parsed(self, plotfile):
        """EPA plotfile header parsed correctly."""
        result = read_postfile(plotfile)
        assert result.header.averaging_period == "1-HR"
        assert result.header.source_group == "ALL"
        assert result.header.version == "24142"

    def test_plotfile_max_concentration(self, plotfile):
        """Max concentration works with plotfile format."""
        result = read_postfile(plotfile)
        assert result.max_concentration == pytest.approx(12.3456, abs=1e-4)

    def test_plotfile_empty_data(self, tmp_path):
        """Empty plotfile creates correct column structure with rank."""
        content = """\
* AERMOD ( 24142 ): Empty Plotfile
* MODELING OPTIONS USED: CONC FLAT
* PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL
"""
        filepath = tmp_path / "empty.plt"
        filepath.write_text(content)
        result = read_postfile(filepath)
        assert result.data.empty
        assert "rank" in result.data.columns

    def test_standard_postfile_no_rank(self, sample_postfile):
        """Standard postfile does NOT have rank column (backward compat)."""
        result = read_postfile(sample_postfile)
        assert "rank" not in result.data.columns
        assert list(result.data.columns) == [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "date",
        ]


# ===========================================================================
# TestEPAHeaderFormat
# ===========================================================================

class TestEPAHeaderFormat:
    """Test EPA header format parsing (POST/PLOT FILE OF CONCURRENT...)."""

    def test_epa_postfile_header(self, tmp_path):
        """EPA postfile header with averaging period and source group."""
        content = """\
* AERMOD ( 24142 ): Some Test Case
* MODELING OPTIONS USED: CONC FLAT
* POST/PLOT FILE OF CONCURRENT 1-HR VALUES FOR SOURCE GROUP: ALL
* FORMAT: (3(1X,F13.5),3(1X,F8.2),2A,A8,2X,A6,2X,A5)
"""
        filepath = tmp_path / "epa_header.pst"
        filepath.write_text(content)
        result = read_postfile(filepath)
        assert result.header.averaging_period == "1-HR"
        assert result.header.source_group == "ALL"

    def test_epa_24hr_header(self, tmp_path):
        """EPA header with 24-HR averaging period."""
        content = """\
* AERMOD ( 24142 ): 24-HR Test
* MODELING OPTIONS USED: CONC FLAT
* POST/PLOT FILE OF CONCURRENT 24-HR VALUES FOR SOURCE GROUP: STACKS
* FORMAT: (3(1X,F13.5),3(1X,F8.2),2A,A8,2X,A6,2X,A5)
"""
        filepath = tmp_path / "24hr.pst"
        filepath.write_text(content)
        result = read_postfile(filepath)
        assert result.header.averaging_period == "24-HR"
        assert result.header.source_group == "STACKS"

    def test_pyaermod_header_still_works(self, sample_postfile):
        """Synthetic pyaermod format (AVERTIME/SRCGROUP) still parsed."""
        result = read_postfile(sample_postfile)
        assert result.header.averaging_period == "1-HR"
        assert result.header.source_group == "ALL"
        assert result.header.pollutant_id == "SO2"


# ===========================================================================
# TestDepositionPlotfilePostfile — combined deposition + plotfile branch
# ===========================================================================

# 13 fields: X Y CONC DRY WET ZELEV ZHILL ZFLAG AVE GRP RANK NETID DATE
SAMPLE_DEPOSITION_PLOTFILE = """\
* AERMOD ( 24142 ): Deposition Plotfile Test
* MODELING OPTIONS USED: NonDFAULT CONC DDEP WDEP FLAT DRYDPLT WETDPLT
* PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL
* FORMAT: (5(1X,F13.5),3(1X,F8.2),3X,A5,2X,A8,2X,A5,5X,A8,2X,I8)
*         X             Y      AVERAGE CONC    DRY DEPO    WET DEPO  ZELEV  ZHILL  ZFLAG    AVE     GRP     RANK   NETID       DATE
* ____________  ____________  ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________  ________
      0.00000     100.00000      15.21444       0.55937       8.01199    0.00    0.00    0.00    1-HR  ALL         1ST    GC001    90010101
    100.00000     100.00000      10.50000       0.30000       5.20000    0.00    0.00    0.00    1-HR  ALL         1ST    GC001    90010102
      0.00000     200.00000       8.75000       0.25000       3.10000   10.00    5.00    0.00    1-HR  ALL         1ST    GC002    90010103
"""

# Blank NETID variant — 12 whitespace-split fields instead of 13
SAMPLE_DEPOSITION_PLOTFILE_BLANK_NETID = """\
* AERMOD ( 24142 ): Deposition Plotfile Blank NETID
* MODELING OPTIONS USED: NonDFAULT CONC DDEP WDEP FLAT DRYDPLT WETDPLT
* PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL
* FORMAT: (5(1X,F13.5),3(1X,F8.2),3X,A5,2X,A8,2X,A5,5X,A8,2X,I8)
*         X             Y      AVERAGE CONC    DRY DEPO    WET DEPO  ZELEV  ZHILL  ZFLAG    AVE     GRP     RANK               DATE
* ____________  ____________  ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________
      0.00000     100.00000      15.21444       0.55937       8.01199    0.00    0.00    0.00    1-HR  ALL         1ST               90010101
    100.00000     200.00000      10.50000       0.30000       5.20000    5.00    3.00    0.00    1-HR  ALL         1ST               90010102
"""


class TestDepositionPlotfilePostfile:
    """Tests for the combined deposition + plotfile parsing branch."""

    def test_deposition_plotfile_flags_detected(self, tmp_path):
        """Both _is_deposition and _is_plotfile should be True."""
        filepath = tmp_path / "dep_plt.plt"
        filepath.write_text(SAMPLE_DEPOSITION_PLOTFILE)
        parser = PostfileParser(filepath)
        parser.parse()

        assert parser._is_deposition is True
        assert parser._is_plotfile is True

    def test_deposition_plotfile_columns(self, tmp_path):
        """Result has concentration, dry_depo, wet_depo, AND rank columns."""
        filepath = tmp_path / "dep_plt.plt"
        filepath.write_text(SAMPLE_DEPOSITION_PLOTFILE)
        result = read_postfile(filepath)

        expected_cols = {
            "x", "y", "concentration", "dry_depo", "wet_depo",
            "zelev", "zhill", "zflag", "ave", "grp", "rank", "date",
        }
        assert expected_cols.issubset(set(result.data.columns))

    def test_deposition_plotfile_values(self, tmp_path):
        """Verify row 0 values are correctly parsed."""
        filepath = tmp_path / "dep_plt.plt"
        filepath.write_text(SAMPLE_DEPOSITION_PLOTFILE)
        result = read_postfile(filepath)

        row0 = result.data.iloc[0]
        assert row0["x"] == pytest.approx(0.0)
        assert row0["y"] == pytest.approx(100.0)
        assert row0["concentration"] == pytest.approx(15.21444)
        assert row0["dry_depo"] == pytest.approx(0.55937)
        assert row0["wet_depo"] == pytest.approx(8.01199)
        assert row0["rank"] == "1ST"
        assert row0["date"] == "90010101"

    def test_deposition_plotfile_blank_netid(self, tmp_path):
        """When NETID is blank, date is still correctly extracted via parts[-1]."""
        filepath = tmp_path / "dep_plt_blank.plt"
        filepath.write_text(SAMPLE_DEPOSITION_PLOTFILE_BLANK_NETID)
        result = read_postfile(filepath)

        assert len(result.data) == 2
        assert result.data.iloc[0]["date"] == "90010101"
        assert result.data.iloc[1]["date"] == "90010102"
        assert (result.data["rank"] == "1ST").all()
        # Elevation values on row 1
        assert result.data.iloc[1]["zelev"] == pytest.approx(5.0)

    def test_deposition_plotfile_empty_has_correct_columns(self, tmp_path):
        """Header-only deposition plotfile produces empty df with correct columns."""
        content = """\
* AERMOD ( 24142 ): Empty Deposition Plotfile
* MODELING OPTIONS USED: CONC DDEP WDEP FLAT
* PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL
* FORMAT: (5(1X,F13.5),3(1X,F8.2),3X,A5,2X,A8,2X,A5,5X,A8,2X,I8)
"""
        filepath = tmp_path / "empty_dep_plt.plt"
        filepath.write_text(content)
        result = read_postfile(filepath)

        assert result.data.empty
        assert "rank" in result.data.columns
        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
