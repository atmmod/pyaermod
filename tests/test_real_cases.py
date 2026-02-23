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

    def test_aertest_out_sources_parsed(self):
        """EPA .out files use per-type section headers like
        '*** POINT SOURCE DATA ***' which the parser now handles."""
        path = OUTPUTS / "aertest.out"
        if not path.exists():
            pytest.skip("aertest.out not found")
        results = parse_aermod_output(str(path))

        # AERTEST has 1 point source (STACK1)
        assert len(results.sources) >= 1
        assert results.sources[0].source_type == "POINT"
        assert results.sources[0].source_id == "STACK1"

    def test_aertest_out_gridded_receptors(self):
        """AERTEST uses a gridded polar receptor network — discrete receptor
        parsing won't find individual receptors, but num_receptors from the
        header should still be 144."""
        path = OUTPUTS / "aertest.out"
        if not path.exists():
            pytest.skip("aertest.out not found")
        results = parse_aermod_output(str(path))

        # Gridded polar receptors aren't individually listed as discrete tuples
        assert len(results.receptors) == 0
        # But the header "This Run Includes: ... 144 Receptor(s)" should be preserved
        assert results.run_info.num_receptors == 144

    def test_lovett_out_discrete_receptors_parsed(self):
        """LOVETT uses discrete cartesian receptors with parenthesized tuples."""
        path = OUTPUTS / "lovett.out"
        if not path.exists():
            pytest.skip("lovett.out not found")
        results = parse_aermod_output(str(path))

        # LOVETT has 11 discrete cartesian receptors
        assert len(results.receptors) == 11
        # First receptor: (3500.0, 67750.0, 237.5, 239.3, 0.0)
        r0 = results.receptors[0]
        assert r0.x_coord == pytest.approx(3500.0)
        assert r0.y_coord == pytest.approx(67750.0)
        assert r0.z_elev == pytest.approx(237.5)

    def test_allsrcs_out_multiple_source_types(self):
        """ALLSRCS has point, area, volume, openpit sources."""
        path = OUTPUTS / "allsrcs.out"
        if not path.exists():
            pytest.skip("allsrcs.out not found")
        results = parse_aermod_output(str(path))

        source_types = {s.source_type for s in results.sources}
        # Should have at least POINT and one other type
        assert len(results.sources) >= 2
        assert "POINT" in source_types

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

    def test_deposition_plt_has_rank(self):
        """Deposition PLT files (TESTGAS, TESTPRT2, TESTPART) should have
        rank column now that the combined deposition+plotfile path is fixed."""
        for filename in ["TESTGAS_01H.PLT", "TESTPRT2_01H.PLT", "TESTPART_01H.PLT"]:
            path = PLOTFILES / filename
            if not path.exists():
                pytest.skip(f"{filename} not found")
            result = read_postfile(str(path))

            assert "rank" in result.data.columns, (
                f"{filename}: missing rank column"
            )
            assert "dry_depo" in result.data.columns, (
                f"{filename}: missing dry_depo column"
            )
            assert "wet_depo" in result.data.columns, (
                f"{filename}: missing wet_depo column"
            )
            # Rank should be "1ST" for first-highest PLT files
            assert (result.data["rank"] == "1ST").all(), (
                f"{filename}: unexpected rank values"
            )
            # Dates should be 8-digit strings
            assert result.data["date"].str.match(r"^\d{8}$").all(), (
                f"{filename}: date format incorrect"
            )

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


# ==========================================================================
# F. Full PST sweep — parse every .PST file without error
# ==========================================================================


def _all_pst_files():
    """Collect every .PST file in the postfiles directory."""
    if not POSTFILES.is_dir():
        return []
    return sorted(p.name for p in POSTFILES.glob("*.PST"))


def _all_plt_files():
    """Collect every .PLT file in the plotfiles directory."""
    if not PLOTFILES.is_dir():
        return []
    return sorted(p.name for p in PLOTFILES.glob("*.PLT"))


class TestFullPSTSweep:
    """Parse ALL 108 .PST files to catch edge-case format variations."""

    @pytest.mark.parametrize("filename", _all_pst_files())
    def test_pst_parses_and_validates(self, filename):
        path = POSTFILES / filename
        result = read_postfile(str(path))

        assert not result.data.empty, f"{filename} parsed to empty DataFrame"
        assert result.header.version == "24142"

        # Basic data integrity checks
        assert (result.data["concentration"] >= 0).all(), (
            f"{filename}: negative concentrations found"
        )
        assert np.isfinite(result.data["x"]).all(), (
            f"{filename}: non-finite x coordinates"
        )
        assert np.isfinite(result.data["y"]).all(), (
            f"{filename}: non-finite y coordinates"
        )

        # Must have at least one unique receptor
        n_receptors = result.data.groupby(["x", "y"]).ngroups
        assert n_receptors >= 1, f"{filename}: no receptors found"

        # Header must have an averaging period
        assert result.header.averaging_period is not None, (
            f"{filename}: no averaging period in header"
        )


class TestFullPLTSweep:
    """Parse ALL .PLT plotfiles to catch edge-case format variations."""

    @pytest.mark.parametrize("filename", _all_plt_files())
    def test_plt_parses_and_validates(self, filename):
        path = PLOTFILES / filename
        result = read_postfile(str(path))

        assert not result.data.empty, f"{filename} parsed to empty DataFrame"
        assert result.header.version == "24142"

        assert (result.data["concentration"] >= 0).all(), (
            f"{filename}: negative concentrations found"
        )

        # Not all PLT files have a rank column:
        # - Deposition PLTs (TESTPRT2, TESTGAS, etc.) use _is_deposition path,
        #   which gives dry_depo/wet_depo instead of rank.
        # - PERIOD/ANNUAL PLTs ("PLOT FILE OF PERIOD/ANNUAL VALUES AVERAGED")
        #   don't have rank — they report averaged values, not "Nth highest".
        # - PSDCREDIT PLTs ("PLOT FILE OF 1ST-HIGHEST MAX DAILY") use a
        #   multi-year format the parser doesn't fully handle yet.
        # Only "PLOT FILE OF HIGH" PLTs are expected to have rank.
        has_rank = "rank" in result.data.columns
        has_depo = "dry_depo" in result.data.columns
        # At minimum, every PLT should parse some data
        assert len(result.data) >= 1
        # If we got rank, verify it's a valid value
        if has_rank:
            assert result.data["rank"].notna().all()
        # If we got deposition columns, verify they're non-negative
        if has_depo:
            assert (result.data["dry_depo"] >= 0).all()
            assert (result.data["wet_depo"] >= 0).all()


# ==========================================================================
# G. R-script comparison — replicate EPA read_POS.fun logic in Python
# ==========================================================================

# The EPA R script Process_AERMOD_test_cases_output.R parses .PST files
# using read_POS.fun (skip 8 header lines, read fixed-width columns).
# The deposition variant read_POS_TESTDEP.fun is used for 5 specific cases.
#
# This test class replicates that R logic in pure Python and compares
# row counts, receptor counts, and max concentrations against pyaermod's
# PostfileParser output.

# Cases the R script treats as deposition (uses read_POS_TESTDEP.fun)
_DEPOSITION_CASES = {
    "TESTGAS_01H.PST",
    "TESTGAS2_01H.PST",
    "TESTPART_01H.PST",
    "TESTPRT2_01H.PST",
    "TESTPRT2_MON.PST",
}


def _r_style_parse(filepath):
    """
    Replicate EPA read_POS.fun / read_POS_TESTDEP.fun logic:
    - Skip 8 header lines (lines starting with '*' plus separator lines)
    - Parse remaining lines by whitespace-splitting
    - Standard: 10 fields (X Y CONC ZELEV ZHILL ZFLAG AVE GRP DATE NETID)
    - Deposition: 12 fields (X Y CONC DRY WET ZELEV ZHILL ZFLAG AVE GRP DATE NETID)

    Returns (n_rows, n_receptors, max_conc, is_deposition).
    """
    is_dep = filepath.name in _DEPOSITION_CASES
    rows = []
    receptor_set = set()

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        # Skip header lines (those starting with '*')
        for line in f:
            if not line.startswith("*"):
                # First non-header line is data
                parts = line.split()
                if parts:
                    rows.append(parts)
                break

        # Read remaining data lines
        for line in f:
            parts = line.split()
            if parts:
                rows.append(parts)

    if not rows:
        return 0, 0, 0.0, is_dep

    max_conc = 0.0
    for parts in rows:
        try:
            x = float(parts[0])
            y = float(parts[1])
            conc = float(parts[2])
            receptor_set.add((x, y))
            if conc > max_conc:
                max_conc = conc
        except (ValueError, IndexError):
            continue

    return len(rows), len(receptor_set), max_conc, is_dep


# Subset of representative files for the R comparison
_R_COMPARISON_FILES = [
    "AERTEST_01H.PST",
    "ALLSRCS_STACK_01H.PST",
    "ALLSRCS_AREA_01H.PST",
    "ALLSRCS_VOL_01H.PST",
    "LOVETT_24H.PST",
    "MCR_01H.PST",
    "OPENPITS_PITGAS_01H.PST",
    "HRDOW_STACK1_01H.PST",
    "TESTGAS_01H.PST",
    "TESTGAS2_01H.PST",
    "TESTPART_01H.PST",
    "TESTPRT2_01H.PST",
    "NO2_ARM2_PPB_01H.PST",
    "NO2_PVMRM_UGM3_01H.PST",
    "SURFCOAL_01H.PST",
    "BLP_URBAN_2S26_01H.PST",
    "CAPPED_STACK1_01H.PST",
    "Test1_Base_cart_3cond_SNC.PST",
]


class TestRScriptComparison:
    """Compare pyaermod parser output against EPA R-script-equivalent parsing."""

    @pytest.mark.parametrize("filename", _R_COMPARISON_FILES)
    def test_row_count_matches_r(self, filename):
        """pyaermod row count must equal R-style row count (skip 8 headers)."""
        path = POSTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")

        r_nrows, _r_nrecep, _r_max, _r_is_dep = _r_style_parse(path)
        py_result = read_postfile(str(path))

        assert len(py_result.data) == r_nrows, (
            f"{filename}: pyaermod={len(py_result.data)} rows, R-style={r_nrows} rows"
        )

    @pytest.mark.parametrize("filename", _R_COMPARISON_FILES)
    def test_receptor_count_matches_r(self, filename):
        """pyaermod receptor count must equal R-style receptor count."""
        path = POSTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")

        _r_nrows, r_nrecep, _r_max, _r_is_dep = _r_style_parse(path)
        py_result = read_postfile(str(path))

        py_nrecep = py_result.data.groupby(["x", "y"]).ngroups
        assert py_nrecep == r_nrecep, (
            f"{filename}: pyaermod={py_nrecep} receptors, R-style={r_nrecep}"
        )

    @pytest.mark.parametrize("filename", _R_COMPARISON_FILES)
    def test_max_concentration_matches_r(self, filename):
        """pyaermod max concentration must match R-style max (column 3)."""
        path = POSTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")

        _r_nrows, _r_nrecep, r_max, _r_is_dep = _r_style_parse(path)
        py_result = read_postfile(str(path))

        assert py_result.max_concentration == pytest.approx(r_max, rel=1e-6), (
            f"{filename}: pyaermod={py_result.max_concentration}, R-style={r_max}"
        )

    @pytest.mark.parametrize("filename", _R_COMPARISON_FILES)
    def test_deposition_detection_matches_r(self, filename):
        """Files the R script treats as deposition must have dry_depo/wet_depo columns."""
        path = POSTFILES / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")

        _r_nrows, _r_nrecep, _r_max, r_is_dep = _r_style_parse(path)
        py_result = read_postfile(str(path))

        if r_is_dep:
            assert "dry_depo" in py_result.data.columns, (
                f"{filename}: R treats as deposition but pyaermod missing dry_depo column"
            )
            assert "wet_depo" in py_result.data.columns, (
                f"{filename}: R treats as deposition but pyaermod missing wet_depo column"
            )
        else:
            assert "dry_depo" not in py_result.data.columns, (
                f"{filename}: R treats as standard but pyaermod has dry_depo column"
            )
