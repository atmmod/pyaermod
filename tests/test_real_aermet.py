"""
Integration tests for pyaermod AERMET parsers against real EPA AERMET v24142 test case files.

These tests validate the .SFC and .PFL parsers on real AERMET output files.
The test data directory (aermet_test_cases/aermet_def_testcases_24142/) is NOT
committed to git.

Tests are skipped when the test data directory is not present.
"""

from pathlib import Path

import numpy as np
import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage3,
    AERMETStation,
    ProfileFileHeader,
    SurfaceFileHeader,
    UpperAirStation,
    read_profile_file,
    read_surface_file,
)

# Root path to AERMET test case data
AERMET_DATA_ROOT = (
    Path(__file__).resolve().parent.parent
    / "aermet_test_cases"
    / "aermet_def_testcases_24142"
)
OUTPUT_FILES = AERMET_DATA_ROOT / "output_files"

# Skip all tests if data missing
pytestmark = pytest.mark.skipif(
    not AERMET_DATA_ROOT.exists(),
    reason=f"AERMET test case directory not found: {AERMET_DATA_ROOT}",
)

# Representative .SFC files for parametrized tests
SFC_FILES = [
    "EX01_MP.SFC",
    "AERMET2.SFC",
    "ANCH-99.SFC",
    "HOUSTON.SFC",
    "LOVETT.SFC",
    "MCR.SFC",
    "SALEM_86-90.SFC",
    "cordero.sfc",
    "case_1_feb.sfc",
    "PVD_2005_1MIN-ASOS_ADJ.SFC",
    "MMIF_AERMET_2018_104_133.SFC",
]

PFL_FILES = [
    "EX01_MP.PFL",
    "AERMET2.PFL",
    "ANCH-99.PFL",
    "HOUSTON.PFL",
    "LOVETT.PFL",
    "MCR.PFL",
    "SALEM_86-90.PFL",
    "cordero.PFL",
]


# ==========================================================================
# A. Surface file (.SFC) parser tests
# ==========================================================================


class TestSurfaceFileParser:
    """Test read_surface_file against real .SFC files."""

    @pytest.mark.parametrize("filename", SFC_FILES)
    def test_sfc_parses_without_error(self, filename):
        path = OUTPUT_FILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_surface_file(str(path))

        assert result is not None
        assert "header" in result
        assert "data" in result
        assert not result["data"].empty
        assert result["header"].version == "24142"

    @pytest.mark.parametrize("filename", SFC_FILES)
    def test_sfc_data_columns_present(self, filename):
        path = OUTPUT_FILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_surface_file(str(path))
        df = result["data"]

        required = {
            "year", "month", "day", "jday", "hour",
            "H", "ustar", "wstar", "VPTG",
            "Zic", "Zim", "L", "z0",
            "BOWEN", "ALBEDO",
            "wind_speed", "wind_dir", "zref_wind",
            "temp", "zref_temp",
        }
        assert required.issubset(set(df.columns))

    def test_ex01_sfc_structure(self):
        """EX01 is 4 days (March 1-4, 1988), 96 hours at 1 height."""
        path = OUTPUT_FILES / "EX01_MP.SFC"
        if not path.exists():
            pytest.skip("EX01_MP.SFC not found")
        result = read_surface_file(str(path))
        hdr = result["header"]
        df = result["data"]

        assert hdr.latitude == pytest.approx(42.75)
        assert hdr.longitude == pytest.approx(-73.8)
        assert hdr.ua_id == "00014735"
        assert hdr.sf_id == "14735"
        assert hdr.os_id == ""
        assert len(df) == 96

        # Month should be March
        assert (df["month"] == 3).all()
        # Year is 88 (two-digit)
        assert (df["year"] == 88).all()

    def test_salem_sfc_multi_year(self):
        """Salem spans 1986-1990 (5 years)."""
        path = OUTPUT_FILES / "SALEM_86-90.SFC"
        if not path.exists():
            pytest.skip("SALEM_86-90.SFC not found")
        result = read_surface_file(str(path))
        df = result["data"]

        assert len(df) == 43824
        assert sorted(df["year"].unique().tolist()) == [86, 87, 88, 89, 90]
        # 12 months each year
        assert set(df["month"].unique()) == set(range(1, 13))

    def test_houston_sfc_full_year(self):
        """Houston is a full year (8784 hours = leap year)."""
        path = OUTPUT_FILES / "HOUSTON.SFC"
        if not path.exists():
            pytest.skip("HOUSTON.SFC not found")
        result = read_surface_file(str(path))
        hdr = result["header"]
        df = result["data"]

        assert hdr.latitude == pytest.approx(29.967)
        assert len(df) == 8784  # leap year

    def test_sfc_wind_speed_physical(self):
        """Wind speed should be non-negative (missing = 999 or 0)."""
        path = OUTPUT_FILES / "ANCH-99.SFC"
        if not path.exists():
            pytest.skip("ANCH-99.SFC not found")
        result = read_surface_file(str(path))
        df = result["data"]

        assert (df["wind_speed"] >= 0).all()
        # Some valid wind data exists
        valid_wind = df[df["wind_speed"] < 900]
        assert len(valid_wind) > 0
        assert valid_wind["wind_speed"].max() < 100  # reasonable upper bound

    def test_sfc_temperature_physical(self):
        """Temperature should be in reasonable range (Kelvin)."""
        path = OUTPUT_FILES / "EX01_MP.SFC"
        if not path.exists():
            pytest.skip("EX01_MP.SFC not found")
        result = read_surface_file(str(path))
        df = result["data"]

        valid_temp = df[df["temp"] > 100]  # filter missing values
        assert len(valid_temp) > 0
        assert valid_temp["temp"].min() > 200  # > -73C
        assert valid_temp["temp"].max() < 350  # < 77C

    def test_lovett_sfc_onsite(self):
        """Lovett has onsite data (OS_ID=LOVETT)."""
        path = OUTPUT_FILES / "LOVETT.SFC"
        if not path.exists():
            pytest.skip("LOVETT.SFC not found")
        result = read_surface_file(str(path))
        hdr = result["header"]

        assert hdr.os_id == "LOVETT"
        assert len(result["data"]) == 8784

    def test_mmif_sfc_extra_options(self):
        """MMIF files have extra options after VERSION."""
        path = OUTPUT_FILES / "MMIF_AERMET_2018_104_133.SFC"
        if not path.exists():
            pytest.skip("MMIF file not found")
        result = read_surface_file(str(path))
        hdr = result["header"]

        assert "CCVR_Sub" in hdr.options
        assert "PROG" in hdr.options


# ==========================================================================
# B. Profile file (.PFL) parser tests
# ==========================================================================


class TestProfileFileParser:
    """Test read_profile_file against real .PFL files."""

    @pytest.mark.parametrize("filename", PFL_FILES)
    def test_pfl_parses_without_error(self, filename):
        path = OUTPUT_FILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_profile_file(str(path))

        assert result is not None
        assert "header" in result
        assert "data" in result
        assert not result["data"].empty
        assert result["header"].num_hours > 0

    @pytest.mark.parametrize("filename", PFL_FILES)
    def test_pfl_data_columns_present(self, filename):
        path = OUTPUT_FILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_profile_file(str(path))
        df = result["data"]

        required = {
            "year", "month", "day", "hour",
            "height", "top_flag",
            "wind_dir", "wind_speed", "temp_diff",
        }
        assert required.issubset(set(df.columns))

    def test_ex01_pfl_structure(self):
        """EX01 has 96 hours, single measurement height."""
        path = OUTPUT_FILES / "EX01_MP.PFL"
        if not path.exists():
            pytest.skip("EX01_MP.PFL not found")
        result = read_profile_file(str(path))
        hdr = result["header"]
        df = result["data"]

        assert hdr.num_hours == 96
        assert hdr.num_levels == 1
        assert hdr.heights == [6.1]
        assert len(df) == 96

    def test_salem_pfl_multi_year(self):
        """Salem PFL should have 5 years of data."""
        path = OUTPUT_FILES / "SALEM_86-90.PFL"
        if not path.exists():
            pytest.skip("SALEM_86-90.PFL not found")
        result = read_profile_file(str(path))
        df = result["data"]

        assert sorted(df["year"].unique().tolist()) == [86, 87, 88, 89, 90]
        assert result["header"].num_hours > 40000

    def test_pfl_wind_speed_physical(self):
        """Wind speed should be non-negative."""
        path = OUTPUT_FILES / "HOUSTON.PFL"
        if not path.exists():
            pytest.skip("HOUSTON.PFL not found")
        result = read_profile_file(str(path))
        df = result["data"]

        assert (df["wind_speed"] >= 0).all()


# ==========================================================================
# C. SFC/PFL cross-consistency
# ==========================================================================


class TestSfcPflConsistency:
    """Verify that SFC and PFL files from the same test case are consistent."""

    def test_ex01_hours_match(self):
        """EX01 SFC and PFL should have the same number of hours."""
        sfc_path = OUTPUT_FILES / "EX01_MP.SFC"
        pfl_path = OUTPUT_FILES / "EX01_MP.PFL"
        if not sfc_path.exists() or not pfl_path.exists():
            pytest.skip("EX01 files not found")

        sfc = read_surface_file(str(sfc_path))
        pfl = read_profile_file(str(pfl_path))

        assert len(sfc["data"]) == pfl["header"].num_hours

    def test_houston_hours_match(self):
        """Houston SFC and PFL should cover same time period."""
        sfc_path = OUTPUT_FILES / "HOUSTON.SFC"
        pfl_path = OUTPUT_FILES / "HOUSTON.PFL"
        if not sfc_path.exists() or not pfl_path.exists():
            pytest.skip("Houston files not found")

        sfc = read_surface_file(str(sfc_path))
        pfl = read_profile_file(str(pfl_path))

        sfc_df = sfc["data"]
        pfl_df = pfl["data"]

        # Same year range
        assert sfc_df["year"].unique().tolist() == pfl_df["year"].unique().tolist()

    def test_lovett_hours_match(self):
        """Lovett SFC row count should equal PFL unique hour count."""
        sfc_path = OUTPUT_FILES / "LOVETT.SFC"
        pfl_path = OUTPUT_FILES / "LOVETT.PFL"
        if not sfc_path.exists() or not pfl_path.exists():
            pytest.skip("Lovett files not found")

        sfc = read_surface_file(str(sfc_path))
        pfl = read_profile_file(str(pfl_path))

        assert len(sfc["data"]) == pfl["header"].num_hours


# ==========================================================================
# D. Input generation validation against real format patterns
# ==========================================================================


class TestAERMETInputGenerationFormat:
    """Verify generated AERMET input keywords match EPA conventions."""

    def test_stage1_has_required_pathways(self):
        """Generated Stage 1 should contain JOB, UPPERAIR, SURFACE pathways."""
        station = AERMETStation(
            station_id="14735", station_name="Albany",
            latitude=42.75, longitude=-73.80, time_zone=-5,
            elevation=83.8
        )
        ua = UpperAirStation(
            station_id="00014735", station_name="Albany UA",
            latitude=42.75, longitude=-73.80
        )
        stage1 = AERMETStage1(
            surface_station=station,
            surface_data_file="S1473588.144",
            surface_format="CD144",
            upper_air_station=ua,
            upper_air_data_file="14735-88.UA",
            start_date="1988/3/1",
            end_date="1988/3/10",
        )
        output = stage1.to_aermet_input()

        # Required pathway keywords
        assert "JOB" in output
        assert "UPPERAIR" in output
        assert "SURFACE" in output
        assert "QA" in output
        assert "REPORT" in output
        assert "XDATES" in output
        assert "LOCATION" in output
        assert "ANEMHGT" in output
        assert "CD144" in output

    def test_stage3_monthly_params_format(self):
        """Generated Stage 3 ALBEDO/BOWEN/ROUGHNESS should have 12 values."""
        stage3 = AERMETStage3(
            latitude=42.75, longitude=-73.80, time_zone=-5,
            albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
            bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
            roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        )
        output = stage3.to_aermet_input()

        # Find ALBEDO line and verify 12 values
        for line in output.split("\n"):
            if "ALBEDO" in line:
                values = line.split()[1:]  # skip keyword
                assert len(values) == 12
                break

        assert "METPREP" in output
        assert "OUTPUT" in output
        assert "PROFILE" in output
