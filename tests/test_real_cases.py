"""
Integration tests for pyaermod parsers against real EPA AERMOD v24142 test case files.

These tests validate that the output_parser and postfile parsers work correctly
on real AERMOD output files, not just synthetic data. The test data directory
(test_cases/aermet_24142_aermod_24142/) contains ~4.8GB of files and is NOT
committed to git.

Tests are skipped when the test data directory is not present.
"""

from pathlib import Path

import numpy as np
import pytest

from pyaermod.output_parser import parse_aermod_output
from pyaermod.postfile import read_postfile

# Root path to EPA test case data
TEST_DATA_ROOT = (
    Path(__file__).resolve().parent.parent
    / "test_cases"
    / "aermet_24142_aermod_24142"
)
OUTPUTS = TEST_DATA_ROOT / "Outputs"
POSTFILES = TEST_DATA_ROOT / "postfiles"
PLOTFILES = TEST_DATA_ROOT / "plotfiles"

# Skip all tests in this module if test data is missing
pytestmark = pytest.mark.skipif(
    not TEST_DATA_ROOT.exists(),
    reason=f"EPA test case directory not found: {TEST_DATA_ROOT}",
)

# --------------------------------------------------------------------------
# Representative file lists for parametrized tests
# --------------------------------------------------------------------------

SUM_FILES = [
    "AERTEST.SUM",
    "ALLSRCS.SUM",
    "LOVETT.SUM",
    "HRDOW.SUM",
    "OPENPITS.SUM",
    "MCR.SUM",
]

OUT_FILES = [
    "aertest.out",
    "allsrcs.out",
    "lovett.out",
    "hrdow.out",
]

STANDARD_POSTFILES = [
    "AERTEST_01H.PST",
    "ALLSRCS_STACK_01H.PST",
    "ALLSRCS_OPENPIT_01H.PST",
    "LOVETT_24H.PST",
    "OPENPITS_PITGAS_01H.PST",
    "NO2_ARM2_PPB_01H.PST",
    "HRDOW_STACK1_01H.PST",
    "FLATELEV_ELEV_STK_01H.PST",
    "Test1_Base_cart_3cond_SNC.PST",
    "Test3_Base_cart_3cond_SNC_bar.PST",
    "Test4_Base_cart_3cond_SNC_dep.PST",
    "MCR_01H.PST",
]

STANDARD_PLOTFILES = [
    "AERTEST_01H.PLT",
    "LOVETT_01H.PLT",
    "MCR_01H.PLT",
    "NO2_ARM2_PPB_01H.PLT",
    "OPENPITS_PITGAS_01H.PLT",
]


# ==========================================================================
# A. Output parser — .SUM files (EPA VALUE IS format)
# ==========================================================================


class TestOutputParserRealSUM:
    """Test output_parser against real .SUM files."""

    @pytest.mark.parametrize("filename", SUM_FILES)
    def test_sum_parses_without_error(self, filename):
        path = OUTPUTS / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        results = parse_aermod_output(str(path))
        assert results is not None
        assert results.run_info is not None
        assert results.run_info.version == "24142"
        assert len(results.concentrations) >= 1

    def test_aertest_sum_concentrations(self):
        path = OUTPUTS / "AERTEST.SUM"
        if not path.exists():
            pytest.skip("AERTEST.SUM not found")
        results = parse_aermod_output(str(path))

        assert results.run_info.pollutant_id == "SO2"
        assert results.run_info.num_sources == 1
        assert results.run_info.num_receptors == 144

        # All 5 averaging periods should be found
        expected_periods = {"1HR", "3HR", "8HR", "24HR", "PERIOD"}
        assert expected_periods.issubset(set(results.concentrations.keys()))

        # Known max values from the AERTEST test case
        assert results.concentrations["PERIOD"].max_value == pytest.approx(24.85173, abs=1e-3)
        assert results.concentrations["1HR"].max_value == pytest.approx(753.65603, abs=1e-3)
        assert results.concentrations["3HR"].max_value == pytest.approx(329.96015, abs=1e-3)
        assert results.concentrations["8HR"].max_value == pytest.approx(264.11481, abs=1e-3)
        assert results.concentrations["24HR"].max_value == pytest.approx(88.89517, abs=1e-3)

    def test_lovett_sum_elevated_terrain(self):
        path = OUTPUTS / "LOVETT.SUM"
        if not path.exists():
            pytest.skip("LOVETT.SUM not found")
        results = parse_aermod_output(str(path))

        assert len(results.concentrations) >= 1
        assert "PERIOD" in results.concentrations
        assert results.concentrations["PERIOD"].max_value == pytest.approx(4.27442, abs=1e-3)


# ==========================================================================
# B. Output parser — .out files (documents known limitations)
# ==========================================================================


class TestOutputParserRealOUT:
    """Test output_parser against real .out files."""

    @pytest.mark.parametrize("filename", OUT_FILES)
    def test_out_parses_without_error(self, filename):
        path = OUTPUTS / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        results = parse_aermod_output(str(path))
        assert results is not None
        assert results.run_info is not None
        assert results.run_info.version == "24142"

    def test_aertest_out_sources_receptors_empty(self):
        """Documents known limitation: real .out files use different section
        headers than the parser expects, so sources/receptors are empty."""
        path = OUTPUTS / "aertest.out"
        if not path.exists():
            pytest.skip("aertest.out not found")
        results = parse_aermod_output(str(path))

        # Known limitation: parser looks for "*** SOURCE LOCATIONS ***" but
        # real files use "*** POINT SOURCE DATA ***" etc.
        assert len(results.sources) == 0
        assert len(results.receptors) == 0

    def test_aertest_out_has_value_is_concentrations(self):
        """.out files also contain VALUE IS sections for summary results."""
        path = OUTPUTS / "aertest.out"
        if not path.exists():
            pytest.skip("aertest.out not found")
        results = parse_aermod_output(str(path))

        assert "PERIOD" in results.concentrations
        assert results.concentrations["PERIOD"].max_value == pytest.approx(24.85173, abs=1e-3)


# ==========================================================================
# C. Postfile parser — real .PST postfiles
# ==========================================================================


class TestPostfileParserRealPST:
    """Test postfile parser against real .PST files."""

    @pytest.mark.parametrize("filename", STANDARD_POSTFILES)
    def test_pst_parses_without_error(self, filename):
        path = POSTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_postfile(str(path))

        assert result is not None
        assert not result.data.empty
        assert result.header.version == "24142"
        # All concentrations should be non-negative and finite
        assert (result.data["concentration"] >= 0).all()
        assert np.isfinite(result.data["x"]).all()
        assert np.isfinite(result.data["y"]).all()

    def test_aertest_pst_structure(self):
        path = POSTFILES / "AERTEST_01H.PST"
        if not path.exists():
            pytest.skip("AERTEST_01H.PST not found")
        result = read_postfile(str(path))

        assert result.header.averaging_period == "1-HR"
        assert result.header.source_group == "ALL"

        # 144 receptors x 96 hours = 13824 rows
        assert result.data.groupby(["x", "y"]).ngroups == 144
        assert len(result.data) == 13824

        # Required columns
        required = {"x", "y", "concentration", "zelev", "zhill", "zflag", "ave", "grp", "date"}
        assert required.issubset(set(result.data.columns))

    def test_aertest_pst_known_max(self):
        """Cross-validate: PST max should match SUM 1-HR max."""
        path = POSTFILES / "AERTEST_01H.PST"
        if not path.exists():
            pytest.skip("AERTEST_01H.PST not found")
        result = read_postfile(str(path))

        assert result.max_concentration == pytest.approx(753.65603, rel=1e-3)

    def test_aertest_pst_timestep_query(self):
        path = POSTFILES / "AERTEST_01H.PST"
        if not path.exists():
            pytest.skip("AERTEST_01H.PST not found")
        result = read_postfile(str(path))

        ts = result.get_timestep("88030101")
        assert len(ts) == 144  # one row per receptor

    def test_testgas_pst_deposition(self):
        """TESTGAS uses FORMAT: (5(1X,F13.5),...) — deposition with 5 wide columns."""
        path = POSTFILES / "TESTGAS_01H.PST"
        if not path.exists():
            pytest.skip("TESTGAS_01H.PST not found")
        result = read_postfile(str(path))

        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns
        assert result.data["dry_depo"].max() > 0
        assert result.data["wet_depo"].max() > 0
        assert result.max_concentration > 0

    def test_testprt2_pst_deposition(self):
        """TESTPRT2 uses FORMAT: (2(1X,F13.5),3(1X,E13.6),...) — mixed repeat groups.
        This was previously broken because the FORMAT regex only captured the first
        group count (2), not the total (2+3=5)."""
        path = POSTFILES / "TESTPRT2_01H.PST"
        if not path.exists():
            pytest.skip("TESTPRT2_01H.PST not found")
        result = read_postfile(str(path))

        assert "dry_depo" in result.data.columns
        assert "wet_depo" in result.data.columns
        assert (result.data["concentration"] >= 0).all()

    def test_lovett_pst_terrain(self):
        path = POSTFILES / "LOVETT_24H.PST"
        if not path.exists():
            pytest.skip("LOVETT_24H.PST not found")
        result = read_postfile(str(path))

        assert result.header.averaging_period == "24-HR"
        assert result.data.groupby(["x", "y"]).ngroups == 11
        # Elevated terrain — receptors have non-zero zelev
        assert result.data["zelev"].max() > 200

    def test_openpits_pst_source_group(self):
        path = POSTFILES / "OPENPITS_PITGAS_01H.PST"
        if not path.exists():
            pytest.skip("OPENPITS_PITGAS_01H.PST not found")
        result = read_postfile(str(path))

        assert result.header.source_group == "PITGAS"
        assert result.data.groupby(["x", "y"]).ngroups == 8


# ==========================================================================
# D. Plotfile parser — real .PLT files
# ==========================================================================


class TestPlotfileParserRealPLT:
    """Test postfile parser against real .PLT plotfiles."""

    @pytest.mark.parametrize("filename", STANDARD_PLOTFILES)
    def test_plt_parses_without_error(self, filename):
        path = PLOTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        result = read_postfile(str(path))

        assert result is not None
        assert not result.data.empty
        assert result.header.version == "24142"
        assert (result.data["concentration"] >= 0).all()

    def test_aertest_plt_structure(self):
        path = PLOTFILES / "AERTEST_01H.PLT"
        if not path.exists():
            pytest.skip("AERTEST_01H.PLT not found")
        result = read_postfile(str(path))

        assert "rank" in result.data.columns
        assert len(result.data) == 144
        assert (result.data["rank"] == "1ST").all()

        # Dates should be 8-digit strings, not rank values
        assert result.data["date"].str.match(r"^\d{8}$").all()

    def test_aertest_plt_max_matches_pst(self):
        """Cross-validate: PLT max should match PST max."""
        plt_path = PLOTFILES / "AERTEST_01H.PLT"
        pst_path = POSTFILES / "AERTEST_01H.PST"
        if not plt_path.exists() or not pst_path.exists():
            pytest.skip("AERTEST files not found")

        plt_result = read_postfile(str(plt_path))
        pst_result = read_postfile(str(pst_path))

        assert plt_result.max_concentration == pytest.approx(
            pst_result.max_concentration, rel=1e-3
        )


# ==========================================================================
# E. Cross-validation — multi-file consistency
# ==========================================================================


class TestCrossValidation:
    """Cross-validate results across .SUM, .PST, and .PLT files."""

    def test_aertest_max_consistent_across_formats(self):
        """The 1-HR max from SUM, PST, and PLT should all agree."""
        sum_path = OUTPUTS / "AERTEST.SUM"
        pst_path = POSTFILES / "AERTEST_01H.PST"
        plt_path = PLOTFILES / "AERTEST_01H.PLT"
        for p in [sum_path, pst_path, plt_path]:
            if not p.exists():
                pytest.skip(f"{p.name} not found")

        sum_results = parse_aermod_output(str(sum_path))
        pst_result = read_postfile(str(pst_path))
        plt_result = read_postfile(str(plt_path))

        sum_max = sum_results.concentrations["1HR"].max_value
        pst_max = pst_result.max_concentration
        plt_max = plt_result.max_concentration

        assert sum_max == pytest.approx(pst_max, rel=1e-3)
        assert sum_max == pytest.approx(plt_max, rel=1e-3)

    def test_lovett_max_consistent(self):
        """The 24-HR max from SUM and PST should agree."""
        sum_path = OUTPUTS / "LOVETT.SUM"
        pst_path = POSTFILES / "LOVETT_24H.PST"
        for p in [sum_path, pst_path]:
            if not p.exists():
                pytest.skip(f"{p.name} not found")

        sum_results = parse_aermod_output(str(sum_path))
        pst_result = read_postfile(str(pst_path))

        sum_max = sum_results.concentrations["24HR"].max_value
        pst_max = pst_result.max_concentration

        assert sum_max == pytest.approx(pst_max, rel=1e-3)
