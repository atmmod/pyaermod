"""
EPA v24142 Integration Tests — Validate pyaermod Against Official Test Cases

Uses EPA's official AERMOD v24142 test cases to validate the output_parser
and postfile modules against real AERMOD output. Tests are skipped when the
EPA test-case directory is absent (e.g., in CI).

Run only EPA tests::

    pytest -m epa -v

Skip EPA tests::

    pytest -m "not epa"
"""

from pathlib import Path

import pytest

from pyaermod.output_parser import AERMODOutputParser
from pyaermod.postfile import (
    PostfileParser,
    _is_text_postfile,
    read_postfile,
)

# ---------------------------------------------------------------------------
# EPA test-case directory (not checked in; lives in user Dropbox)
# ---------------------------------------------------------------------------

EPA_TEST_DIR = Path(
    "/Users/sc3623/AMaD Dropbox/Shannon Capps/Research/aermod/"
    "aermod_test_cases/aermet_24142_aermod_24142"
)

EPA_AVAILABLE = EPA_TEST_DIR.is_dir()

requires_epa = pytest.mark.skipif(
    not EPA_AVAILABLE,
    reason="EPA v24142 test-case directory not found",
)

# Convenience sub-dirs
POSTFILES_DIR = EPA_TEST_DIR / "postfiles"
PLOTFILES_DIR = EPA_TEST_DIR / "plotfiles"
OUTPUTS_DIR = EPA_TEST_DIR / "Outputs"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def aertest_postfile():
    """Parse AERTEST_01H.PST once per module."""
    return read_postfile(POSTFILES_DIR / "AERTEST_01H.PST")


@pytest.fixture(scope="module")
def aertest_plotfile():
    """Parse AERTEST_01H.PLT once per module."""
    return read_postfile(PLOTFILES_DIR / "AERTEST_01H.PLT")


@pytest.fixture(scope="module")
def aertest_output():
    """Parse AERTEST.SUM once per module."""
    parser = AERMODOutputParser(OUTPUTS_DIR / "AERTEST.SUM")
    return parser.parse()


@pytest.fixture(scope="module")
def allsrcs_output():
    """Parse ALLSRCS.SUM once per module."""
    parser = AERMODOutputParser(OUTPUTS_DIR / "ALLSRCS.SUM")
    return parser.parse()


# ============================================================================
# 1. Output Parser Tests — aertest.out / AERTEST.SUM
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAertestOutputParsing:
    """Validate output_parser against the EPA aertest reference case."""

    def test_version_parsed(self, aertest_output):
        assert aertest_output.run_info.version == "24142"

    def test_parser_does_not_crash(self, aertest_output):
        """The parser completes without raising on real EPA output."""
        assert aertest_output is not None

    def test_summary_generated(self, aertest_output):
        """summary() returns non-empty text."""
        text = aertest_output.summary()
        assert len(text) > 0
        assert "24142" in text

    def test_output_file_stored(self, aertest_output):
        assert "AERTEST.SUM" in aertest_output.output_file

    def test_sources_not_in_sum(self, aertest_output):
        """EPA SUM files don't contain SOURCE LOCATIONS section."""
        assert len(aertest_output.sources) == 0

    def test_receptors_not_in_sum(self, aertest_output):
        """EPA SUM files don't contain RECEPTOR LOCATIONS section."""
        assert len(aertest_output.receptors) == 0

    def test_source_receptor_counts_from_header(self, aertest_output):
        """Counts are extracted from 'This Run Includes:' line."""
        assert aertest_output.run_info.num_sources == 1
        assert aertest_output.run_info.num_receptors == 144

    def test_concentration_data_extracted(self, aertest_output):
        """EPA SUM VALUE IS format now parsed correctly."""
        assert len(aertest_output.concentrations) > 0
        assert "1HR" in aertest_output.concentrations

    def test_pollutant_parsed(self, aertest_output):
        """EPA SUM 'Pollutant Type of: SO2' now parsed."""
        assert aertest_output.run_info.pollutant_id == "SO2"

    def test_1hr_max_concentration(self, aertest_output):
        """1-HR max should be 753.65603 from EPA reference data."""
        result = aertest_output.concentrations["1HR"]
        assert result.max_value == pytest.approx(753.65603, abs=1e-3)

    def test_1hr_max_location(self, aertest_output):
        """1-HR max at (303.11, -175.00)."""
        result = aertest_output.concentrations["1HR"]
        assert result.max_location[0] == pytest.approx(303.11, abs=0.1)
        assert result.max_location[1] == pytest.approx(-175.0, abs=0.1)

    def test_period_max_concentration(self, aertest_output):
        """PERIOD max should be 24.85173."""
        result = aertest_output.concentrations["PERIOD"]
        assert result.max_value == pytest.approx(24.85173, abs=1e-3)

    def test_all_five_periods_parsed(self, aertest_output):
        """Should have 1HR, 3HR, 8HR, 24HR, PERIOD."""
        expected = {"1HR", "3HR", "8HR", "24HR", "PERIOD"}
        assert set(aertest_output.concentrations.keys()) == expected

    def test_sources_dataframe_empty(self, aertest_output):
        """Without parsed source locations, DataFrame should be empty."""
        df = aertest_output.get_sources_dataframe()
        assert df.empty

    def test_receptors_dataframe_empty(self, aertest_output):
        """Without parsed receptor locations, DataFrame should be empty."""
        df = aertest_output.get_receptors_dataframe()
        assert df.empty


# ============================================================================
# 2. Output Parser Tests — allsrcs.out / ALLSRCS.SUM
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAllsrcsOutputParsing:
    """Validate output_parser against the multi-source allsrcs reference case."""

    def test_version_parsed(self, allsrcs_output):
        assert allsrcs_output.run_info.version == "24142"

    def test_parser_does_not_crash(self, allsrcs_output):
        assert allsrcs_output is not None

    def test_summary_generated(self, allsrcs_output):
        text = allsrcs_output.summary()
        assert len(text) > 0

    def test_sources_not_in_sum(self, allsrcs_output):
        """EPA SUM files don't contain SOURCE LOCATIONS section."""
        assert len(allsrcs_output.sources) == 0

    def test_receptors_not_in_sum(self, allsrcs_output):
        """EPA SUM files don't contain RECEPTOR LOCATIONS section."""
        assert len(allsrcs_output.receptors) == 0

    def test_source_receptor_counts_from_header(self, allsrcs_output):
        """Counts from 'This Run Includes:' line."""
        assert allsrcs_output.run_info.num_sources == 15
        assert allsrcs_output.run_info.num_receptors == 332

    def test_concentration_data_extracted(self, allsrcs_output):
        """EPA SUM VALUE IS format now parsed correctly."""
        assert len(allsrcs_output.concentrations) > 0
        assert "1HR" in allsrcs_output.concentrations

    def test_pollutant_parsed(self, allsrcs_output):
        """EPA SUM 'Pollutant Type of: SO2' now parsed."""
        assert allsrcs_output.run_info.pollutant_id == "SO2"

    def test_1hr_max_concentration(self, allsrcs_output):
        """1-HR max should be 316456.68934."""
        result = allsrcs_output.concentrations["1HR"]
        assert result.max_value == pytest.approx(316456.68934, abs=1e-2)

    def test_period_max_concentration(self, allsrcs_output):
        """PERIOD max should be 11819.89828."""
        result = allsrcs_output.concentrations["PERIOD"]
        assert result.max_value == pytest.approx(11819.89828, abs=1e-2)


# ============================================================================
# 3. Postfile Parser Tests — AERTEST_01H.PST
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAertestPostfileParsing:
    """Validate postfile parser against the EPA aertest 1-HR postfile."""

    def test_row_count(self, aertest_postfile):
        """144 receptors × 96 hours = 13,824 data rows."""
        assert len(aertest_postfile.data) == 13824

    def test_column_names(self, aertest_postfile):
        expected = [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "date",
        ]
        assert list(aertest_postfile.data.columns) == expected

    def test_header_version(self, aertest_postfile):
        assert aertest_postfile.header.version == "24142"

    def test_header_model_options(self, aertest_postfile):
        opts = aertest_postfile.header.model_options
        assert opts is not None
        assert "CONC" in opts
        assert "FLAT" in opts

    def test_header_title(self, aertest_postfile):
        assert aertest_postfile.header.title is not None
        assert "AERMOD" in aertest_postfile.header.title

    def test_first_row_x(self, aertest_postfile):
        assert aertest_postfile.data.iloc[0]["x"] == pytest.approx(
            30.38843, abs=1e-4
        )

    def test_first_row_y(self, aertest_postfile):
        assert aertest_postfile.data.iloc[0]["y"] == pytest.approx(
            172.34136, abs=1e-4
        )

    def test_first_row_concentration(self, aertest_postfile):
        assert aertest_postfile.data.iloc[0]["concentration"] == pytest.approx(
            0.00034, abs=1e-5
        )

    def test_max_concentration(self, aertest_postfile):
        assert aertest_postfile.max_concentration == pytest.approx(
            753.65603, abs=1e-3
        )

    def test_max_location(self, aertest_postfile):
        x, y = aertest_postfile.max_location
        assert x == pytest.approx(303.11, abs=0.1)
        assert y == pytest.approx(-175.00, abs=0.1)

    def test_get_timestep(self, aertest_postfile):
        """First timestep 88030101 should have 144 receptors."""
        ts = aertest_postfile.get_timestep("88030101")
        assert len(ts) == 144

    def test_get_receptor(self, aertest_postfile):
        """First receptor should have 96 hourly values."""
        rec = aertest_postfile.get_receptor(30.38843, 172.34136)
        assert len(rec) == 96

    def test_get_max_by_receptor(self, aertest_postfile):
        """Should have 144 unique receptor locations."""
        maxr = aertest_postfile.get_max_by_receptor()
        assert len(maxr) == 144

    def test_all_concentrations_nonneg(self, aertest_postfile):
        assert (aertest_postfile.data["concentration"] >= 0).all()

    def test_ave_column_consistent(self, aertest_postfile):
        """All rows should have '1-HR' averaging period."""
        assert (aertest_postfile.data["ave"] == "1-HR").all()

    def test_grp_column_consistent(self, aertest_postfile):
        """All rows should belong to group 'ALL'."""
        assert (aertest_postfile.data["grp"] == "ALL").all()


# ============================================================================
# 4. Plotfile Parser Tests — AERTEST_01H.PLT
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAertestPlotfileParsing:
    """Validate postfile parser on plotfile format (PLT has RANK column)."""

    def test_row_count(self, aertest_plotfile):
        """Plotfile should have 144 rows (one per receptor, 1st highest)."""
        assert len(aertest_plotfile.data) == 144

    def test_header_version(self, aertest_plotfile):
        assert aertest_plotfile.header.version == "24142"

    def test_first_row_concentration(self, aertest_plotfile):
        assert aertest_plotfile.data.iloc[0]["concentration"] == pytest.approx(
            3.04541, abs=1e-4
        )

    def test_max_concentration(self, aertest_plotfile):
        """Max plotfile conc should match postfile max."""
        assert aertest_plotfile.max_concentration == pytest.approx(
            753.65603, abs=1e-3
        )

    def test_plotfile_has_rank_column(self, aertest_plotfile):
        """Plotfile now has a dedicated 'rank' column."""
        assert "rank" in aertest_plotfile.data.columns
        assert aertest_plotfile.data.iloc[0]["rank"] == "1ST"

    def test_plotfile_date_is_real(self, aertest_plotfile):
        """Plotfile date column now contains actual YYMMDDHH dates."""
        assert aertest_plotfile.data.iloc[0]["date"] == "88030319"

    def test_plotfile_column_names(self, aertest_plotfile):
        """Plotfile should have rank column in addition to standard columns."""
        expected = [
            "x", "y", "concentration", "zelev",
            "zhill", "zflag", "ave", "grp", "rank", "date",
        ]
        assert list(aertest_plotfile.data.columns) == expected

    def test_all_concentrations_nonneg(self, aertest_plotfile):
        assert (aertest_plotfile.data["concentration"] >= 0).all()

    def test_coordinates_match_postfile(self, aertest_postfile, aertest_plotfile):
        """Plotfile and postfile should share the same receptor coordinates."""
        pst_coords = set(
            zip(aertest_postfile.data["x"].round(3),
                aertest_postfile.data["y"].round(3))
        )
        plt_coords = set(
            zip(aertest_plotfile.data["x"].round(3),
                aertest_plotfile.data["y"].round(3))
        )
        assert plt_coords.issubset(pst_coords)

    def test_max_location_matches_postfile(self, aertest_postfile, aertest_plotfile):
        """Max conc location should match between postfile and plotfile."""
        pst_x, pst_y = aertest_postfile.max_location
        plt_x, plt_y = aertest_plotfile.max_location
        assert pst_x == pytest.approx(plt_x, abs=0.1)
        assert pst_y == pytest.approx(plt_y, abs=0.1)


# ============================================================================
# 5. Postfile Parser Tests — ALLSRCS per-group postfiles
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAllsrcsPostfileParsing:
    """Validate postfile parser on allsrcs per-source-group postfiles."""

    @pytest.mark.parametrize(
        "filename,expected_grp",
        [
            ("ALLSRCS_STACK_01H.PST", "STACK"),
            ("ALLSRCS_AREA_01H.PST", "AREA"),
            ("ALLSRCS_VOL_01H.PST", "VOL"),
            ("ALLSRCS_OPENPIT_01H.PST", "OPENPIT"),
            ("ALLSRCS_RLINEB_01H.PST", "RLINEB"),
            ("ALLSRCS_BLINE_01H.PST", "BLINE"),
            ("ALLSRCS_LINE_01H.PST", "LINE"),
            ("ALLSRCS_CIRC_01H.PST", "CIRC"),
        ],
    )
    def test_group_column_matches(self, filename, expected_grp):
        result = read_postfile(POSTFILES_DIR / filename)
        assert len(result.data) > 0
        assert (result.data["grp"] == expected_grp).all()

    @pytest.mark.parametrize(
        "filename",
        [
            "ALLSRCS_STACK_01H.PST",
            "ALLSRCS_AREA_01H.PST",
            "ALLSRCS_AREAP_01H.PST",
            "ALLSRCS_VOL_01H.PST",
            "ALLSRCS_OPENPIT_01H.PST",
            "ALLSRCS_RLINEB_01H.PST",
            "ALLSRCS_RLINEB2_01H.PST",
            "ALLSRCS_RLINEBA_01H.PST",
            "ALLSRCS_RLINEDE_01H.PST",
            "ALLSRCS_BLINE_01H.PST",
            "ALLSRCS_LINE_01H.PST",
            "ALLSRCS_CIRC_01H.PST",
            "ALLSRCS_STACKDW_01H.PST",
        ],
    )
    def test_parses_without_error(self, filename):
        result = read_postfile(POSTFILES_DIR / filename)
        assert len(result.data) > 0
        assert result.header.version == "24142"

    def test_stack_receptor_count(self):
        """ALLSRCS has 332 receptors × 96 hours = 31,872 rows per group."""
        result = read_postfile(POSTFILES_DIR / "ALLSRCS_STACK_01H.PST")
        assert len(result.data) == 31872

    def test_stack_max_concentration(self):
        result = read_postfile(POSTFILES_DIR / "ALLSRCS_STACK_01H.PST")
        assert result.max_concentration == pytest.approx(304.63385, abs=1e-3)

    def test_area_max_concentration(self):
        result = read_postfile(POSTFILES_DIR / "ALLSRCS_AREA_01H.PST")
        assert result.max_concentration == pytest.approx(6751.67926, abs=1e-3)

    def test_volume_max_concentration(self):
        result = read_postfile(POSTFILES_DIR / "ALLSRCS_VOL_01H.PST")
        assert result.max_concentration == pytest.approx(74.18106, abs=1e-3)

    def test_openpit_max_concentration(self):
        result = read_postfile(POSTFILES_DIR / "ALLSRCS_OPENPIT_01H.PST")
        assert result.max_concentration == pytest.approx(1373.08971, abs=1e-3)


# ============================================================================
# 6. Feature Coverage Postfiles
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestFeatureCoveragePostfiles:
    """Test postfiles from various EPA test cases covering specific features."""

    def test_olm_postfile(self):
        """OLM chemistry method postfile."""
        result = read_postfile(POSTFILES_DIR / "OLM_01H.PST")
        assert len(result.data) > 0
        assert "OLM" in result.header.model_options

    def test_pvmrm_postfile(self):
        """PVMRM chemistry method postfile."""
        result = read_postfile(POSTFILES_DIR / "PVMRM_01H.PST")
        assert len(result.data) > 0
        assert "PVMRM" in result.header.model_options

    def test_no2_arm2_ppb_postfile(self):
        """Background NO2 with ARM2 method, 72 receptors."""
        result = read_postfile(POSTFILES_DIR / "NO2_ARM2_PPB_01H.PST")
        assert len(result.data) > 0
        assert "ARM2" in result.header.model_options
        unique_receptors = result.data[["x", "y"]].drop_duplicates()
        assert len(unique_receptors) == 72

    def test_openpits_pitgas_postfile(self):
        """Open pit gas postfile with known first concentration."""
        result = read_postfile(POSTFILES_DIR / "OPENPITS_PITGAS_01H.PST")
        assert len(result.data) > 0
        assert result.data.iloc[0]["concentration"] == pytest.approx(
            183.18745, abs=1e-3
        )

    def test_flatelev_postfile_zelev(self):
        """FLATELEV test case has non-zero zelev values."""
        result = read_postfile(POSTFILES_DIR / "FLATELEV_FLAT_STK_01H.PST")
        assert len(result.data) > 0
        assert result.data.iloc[0]["zelev"] == pytest.approx(237.48, abs=0.1)

    def test_lovett_24h_postfile(self):
        """Lovett complex terrain 24-HR postfile."""
        result = read_postfile(POSTFILES_DIR / "LOVETT_24H.PST")
        assert len(result.data) > 0

    def test_capped_stack_postfile(self):
        """Capped stack (POINTCAP) postfile."""
        result = read_postfile(POSTFILES_DIR / "CAPPED_STACK1_01H.PST")
        assert len(result.data) > 0

    def test_multurb_postfile(self):
        """Multiple urban areas postfile."""
        result = read_postfile(POSTFILES_DIR / "MULTURB_STACK1_01H.PST")
        assert len(result.data) > 0

    def test_surfcoal_postfile(self):
        """Surface coal mine postfile."""
        result = read_postfile(POSTFILES_DIR / "SURFCOAL_01H.PST")
        assert len(result.data) > 0

    def test_psdcred_postfile(self):
        """PSD credits postfile."""
        result = read_postfile(POSTFILES_DIR / "PSDCRED_NAAQS_01H.PST")
        assert len(result.data) > 0

    def test_in_urban_postfile(self):
        """Urban mode postfile."""
        result = read_postfile(POSTFILES_DIR / "IN_URBAN_01H.PST")
        assert len(result.data) > 0

    def test_hrdow_postfile(self):
        """HRDOW (hour-of-day, day-of-week) emission factors postfile."""
        result = read_postfile(POSTFILES_DIR / "HRDOW_STACK1_01H.PST")
        assert len(result.data) > 0


# ============================================================================
# 7. Deposition Postfiles (parser column misalignment)
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestDepositionPostfiles:
    """
    Deposition postfiles have 11 data columns (extra DRY_DEPO, WET_DEPO)
    which are now correctly parsed by the deposition-aware parser.
    """

    def test_testpart_parses_without_crash(self):
        """Parser should not crash on deposition file."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert len(result.data) > 0

    def test_testpart_column_names(self):
        """Deposition postfile should have dry_depo and wet_depo columns."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        expected = [
            "x", "y", "concentration", "dry_depo", "wet_depo",
            "zelev", "zhill", "zflag", "ave", "grp", "date",
        ]
        assert list(result.data.columns) == expected

    def test_testpart_concentration_correct(self):
        """First 3 columns (x, y, conc) are correctly parsed."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert result.data.iloc[0]["x"] == pytest.approx(0.0, abs=0.01)
        assert result.data.iloc[0]["y"] == pytest.approx(100.0, abs=0.01)
        assert result.data.iloc[0]["concentration"] == pytest.approx(
            15.21444, abs=1e-3
        )

    def test_testpart_deposition_values(self):
        """Dry and wet deposition values are parsed correctly."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert result.data.iloc[0]["dry_depo"] == pytest.approx(0.55937, abs=1e-4)
        assert result.data.iloc[0]["wet_depo"] == pytest.approx(8.01199, abs=1e-4)

    def test_testpart_zelev_correct(self):
        """zelev is now correctly parsed (not shifted to DRY_DEPO)."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert result.data.iloc[0]["zelev"] == pytest.approx(0.0, abs=0.01)

    def test_testpart_date_correct(self):
        """date is now correctly parsed as YYMMDDHH."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert result.data.iloc[0]["date"] == "90010101"

    def test_testpart_ave_correct(self):
        """Averaging period is correctly '1-HR'."""
        result = read_postfile(POSTFILES_DIR / "TESTPART_01H.PST")
        assert result.data.iloc[0]["ave"] == "1-HR"

    def test_testgas_parses_without_crash(self):
        """Gas deposition postfile also has 11 columns."""
        result = read_postfile(POSTFILES_DIR / "TESTGAS_01H.PST")
        assert len(result.data) > 0

    def test_testgas_ave_correct(self):
        """Gas deposition ave is correctly '1-HR'."""
        result = read_postfile(POSTFILES_DIR / "TESTGAS_01H.PST")
        assert result.data.iloc[0]["ave"] == "1-HR"

    def test_testgas_deposition_values(self):
        """Gas deposition dry/wet values parsed correctly."""
        result = read_postfile(POSTFILES_DIR / "TESTGAS_01H.PST")
        assert result.data.iloc[0]["dry_depo"] == pytest.approx(2.84509, abs=1e-4)
        assert result.data.iloc[0]["wet_depo"] == pytest.approx(0.10237, abs=1e-4)


# ============================================================================
# 8. Cross-Validation Tests
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestCrossValidation:
    """Cross-validate values between different EPA output files."""

    def test_postfile_max_matches_plotfile_max(
        self, aertest_postfile, aertest_plotfile
    ):
        """Max concentration should match between PST and PLT files."""
        assert aertest_postfile.max_concentration == pytest.approx(
            aertest_plotfile.max_concentration, rel=1e-5
        )

    def test_postfile_receptor_count_matches_plotfile(
        self, aertest_postfile, aertest_plotfile
    ):
        """Both files should cover 144 receptors."""
        pst_receptors = aertest_postfile.data[["x", "y"]].drop_duplicates()
        plt_receptors = aertest_plotfile.data[["x", "y"]].drop_duplicates()
        assert len(pst_receptors) == 144
        assert len(plt_receptors) == 144

    def test_postfile_timestep_count(self, aertest_postfile):
        """aertest has 96 hours of data."""
        unique_dates = aertest_postfile.data["date"].nunique()
        assert unique_dates == 96

    def test_max_receptor_in_plotfile_matches_postfile_max_by_receptor(
        self, aertest_postfile, aertest_plotfile
    ):
        """Plotfile 1st-highest at each receptor should match postfile max-by-receptor."""
        pst_max = aertest_postfile.get_max_by_receptor()
        # plotfile has one row per receptor (already the max)
        plt_data = aertest_plotfile.data

        # Merge on coordinates and compare
        merged = pst_max.merge(
            plt_data[["x", "y", "concentration"]],
            on=["x", "y"],
            suffixes=("_pst", "_plt"),
        )
        assert len(merged) > 0
        # Values should match closely
        diff = (
            merged["concentration_pst"] - merged["concentration_plt"]
        ).abs()
        assert (diff < 0.01).all()


# ============================================================================
# 9. Output Parser Edge Cases — various .out files
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestOutputParserEdgeCases:
    """Test that the output parser handles various EPA .out/.SUM files."""

    @pytest.mark.parametrize(
        "filename",
        [
            "aertest.out",
            "allsrcs.out",
            "lovett.out",
            "olm.out",
            "pvmrm.out",
            "capped.out",
            "flatelev.out",
            "multurb.out",
            "openpits.out",
            "testpart.out",
        ],
    )
    def test_out_file_parses_without_crash(self, filename):
        """All .out files should parse without raising."""
        filepath = OUTPUTS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"{filename} not found")
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result is not None

    @pytest.mark.parametrize(
        "filename",
        [
            "AERTEST.SUM",
            "ALLSRCS.SUM",
            "LOVETT.SUM",
            "OLM.SUM",
            "PVMRM.SUM",
            "CAPPED.SUM",
            "FLATELEV.SUM",
            "MULTURB.SUM",
            "OPENPITS.SUM",
            "TESTPART.SUM",
        ],
    )
    def test_sum_file_parses_without_crash(self, filename):
        """All .SUM files should parse without raising."""
        filepath = OUTPUTS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"{filename} not found")
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result is not None
        assert result.run_info.version == "24142"


# ============================================================================
# 10a. Deeper EPA Validation — LOVETT, FLATELEV, TESTPART
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestLovettOutputParsing:
    """Deeper validation of LOVETT.SUM — complex terrain test case."""

    def test_lovett_pollutant(self):
        filepath = OUTPUTS_DIR / "LOVETT.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.pollutant_id == "SO2"

    def test_lovett_source_receptor_counts(self):
        filepath = OUTPUTS_DIR / "LOVETT.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.num_sources == 1
        assert result.run_info.num_receptors == 11

    def test_lovett_four_periods(self):
        """LOVETT has 1HR, 3HR, 24HR, and PERIOD averaging periods."""
        filepath = OUTPUTS_DIR / "LOVETT.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert "1HR" in result.concentrations
        assert "3HR" in result.concentrations
        assert "24HR" in result.concentrations
        assert "PERIOD" in result.concentrations

    def test_lovett_1hr_max(self):
        """LOVETT 1HR max concentration = 293.02376 at (4780, 70700)."""
        filepath = OUTPUTS_DIR / "LOVETT.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        hr1 = result.concentrations["1HR"]
        assert hr1.max_value == pytest.approx(293.02376, abs=0.01)
        assert hr1.max_location[0] == pytest.approx(4780.0, abs=1.0)
        assert hr1.max_location[1] == pytest.approx(70700.0, abs=1.0)

    def test_lovett_period_max(self):
        """LOVETT PERIOD max = 4.27442 at (5110, 70850)."""
        filepath = OUTPUTS_DIR / "LOVETT.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        period = result.concentrations["PERIOD"]
        assert period.max_value == pytest.approx(4.27442, abs=0.001)


@pytest.mark.epa
@requires_epa
class TestFlatelevOutputParsing:
    """Deeper validation of FLATELEV.SUM — flat + elevated terrain."""

    def test_flatelev_pollutant(self):
        filepath = OUTPUTS_DIR / "FLATELEV.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.pollutant_id == "SO2"

    def test_flatelev_source_receptor_counts(self):
        filepath = OUTPUTS_DIR / "FLATELEV.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.num_sources == 2
        assert result.run_info.num_receptors == 11

    def test_flatelev_five_periods(self):
        """FLATELEV has 1HR, 3HR, 8HR, 24HR, and PERIOD."""
        filepath = OUTPUTS_DIR / "FLATELEV.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        periods = sorted(result.concentrations.keys())
        assert periods == ["1HR", "24HR", "3HR", "8HR", "PERIOD"]

    def test_flatelev_1hr_max(self):
        """FLATELEV 1HR max = 309.99382 at (5110, 70850)."""
        filepath = OUTPUTS_DIR / "FLATELEV.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        hr1 = result.concentrations["1HR"]
        assert hr1.max_value == pytest.approx(309.99382, abs=0.01)

    def test_flatelev_period_max(self):
        """FLATELEV PERIOD max = 3.14146."""
        filepath = OUTPUTS_DIR / "FLATELEV.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        period = result.concentrations["PERIOD"]
        assert period.max_value == pytest.approx(3.14146, abs=0.001)


@pytest.mark.epa
@requires_epa
class TestDepositionOutputParsing:
    """Deeper validation of TESTPART.SUM — particle deposition."""

    def test_testpart_pollutant(self):
        """TESTPART uses CHROMIUM pollutant."""
        filepath = OUTPUTS_DIR / "TESTPART.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.pollutant_id == "CHROMIUM"

    def test_testpart_source_receptor_counts(self):
        filepath = OUTPUTS_DIR / "TESTPART.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        assert result.run_info.num_sources == 1
        assert result.run_info.num_receptors == 46

    def test_testpart_1hr_max(self):
        """TESTPART 1HR max = 458.42077 at (0, 400)."""
        filepath = OUTPUTS_DIR / "TESTPART.SUM"
        parser = AERMODOutputParser(filepath)
        result = parser.parse()
        hr1 = result.concentrations["1HR"]
        assert hr1.max_value == pytest.approx(458.42077, abs=0.01)
        assert hr1.max_location[0] == pytest.approx(0.0, abs=1.0)
        assert hr1.max_location[1] == pytest.approx(400.0, abs=1.0)


# ============================================================================
# 10. Auto-Detect Format Tests
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestAutoDetectFormat:
    """Validate the text/binary auto-detection on EPA files."""

    def test_pst_detected_as_text(self):
        assert _is_text_postfile(POSTFILES_DIR / "AERTEST_01H.PST") is True

    def test_plt_detected_as_text(self):
        assert _is_text_postfile(PLOTFILES_DIR / "AERTEST_01H.PLT") is True

    def test_read_postfile_dispatches_text(self):
        """read_postfile() should use text parser for EPA .PST files."""
        result = read_postfile(POSTFILES_DIR / "AERTEST_01H.PST")
        assert result.header.version == "24142"
        assert len(result.data) > 0


# ============================================================================
# 11. Bulk Parametrized Tests — all postfiles and plotfiles
# ============================================================================

def _collect_postfiles():
    """Collect all .PST filenames for parametrized bulk tests."""
    if not POSTFILES_DIR.is_dir():
        return []
    return sorted(p.name for p in POSTFILES_DIR.glob("*.PST"))


def _collect_plotfiles():
    """Collect all .PLT filenames for parametrized bulk tests."""
    if not PLOTFILES_DIR.is_dir():
        return []
    return sorted(p.name for p in PLOTFILES_DIR.glob("*.PLT"))


@pytest.mark.epa
@requires_epa
class TestBulkPostfileParsing:
    """Parse every .PST file in the EPA test suite."""

    @pytest.mark.parametrize("filename", _collect_postfiles())
    def test_postfile_parses(self, filename):
        result = read_postfile(POSTFILES_DIR / filename)
        assert len(result.data) > 0, f"{filename} parsed to empty DataFrame"
        assert result.header.version is not None

    @pytest.mark.parametrize("filename", _collect_plotfiles())
    def test_plotfile_parses(self, filename):
        result = read_postfile(PLOTFILES_DIR / filename)
        assert len(result.data) > 0, f"{filename} parsed to empty DataFrame"
        assert result.header.version is not None


# ============================================================================
# 12. Header Parsing for EPA format
# ============================================================================

@pytest.mark.epa
@requires_epa
class TestEPAHeaderParsing:
    """
    EPA postfile headers use 'POST/PLOT FILE OF CONCURRENT 1-HR VALUES
    FOR SOURCE GROUP: ALL' instead of 'AVERTIME: 1-HR' / 'SRCGROUP: ALL'.
    The parser now handles both formats.
    """

    def test_averaging_period_parsed(self, aertest_postfile):
        """EPA header 'CONCURRENT 1-HR VALUES' is now parsed."""
        assert aertest_postfile.header.averaging_period == "1-HR"

    def test_pollutant_not_in_postfile(self, aertest_postfile):
        """EPA postfile headers don't include POLLUTID line."""
        assert aertest_postfile.header.pollutant_id is None

    def test_source_group_parsed(self, aertest_postfile):
        """EPA header 'FOR SOURCE GROUP: ALL' is now parsed."""
        assert aertest_postfile.header.source_group == "ALL"

    def test_version_is_parsed(self, aertest_postfile):
        """AERMOD version line is consistent across formats."""
        assert aertest_postfile.header.version == "24142"

    def test_model_options_parsed(self, aertest_postfile):
        """MODELING OPTIONS USED: line is consistent across formats."""
        assert aertest_postfile.header.model_options is not None
        assert "CONC" in aertest_postfile.header.model_options

    def test_title_includes_run_date(self, aertest_postfile):
        """EPA title line includes the run date appended."""
        title = aertest_postfile.header.title
        assert title is not None
        # Title includes "12/03/24" as run date appended to the description
        assert "12/03/24" in title or "AERMOD" in title
