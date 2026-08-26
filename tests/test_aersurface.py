"""Tests for the AERSURFACE control-file builder.

Every keyword asserted here appears in EPA's own published example deck
(``RDU_Example_2021.inp``); the format is checked end-to-end against the
real binary in ``tests/test_real_aersurface.py``.
"""

from __future__ import annotations

import pytest

from pyaermod import AERSURFACEConfig
from pyaermod.aersurface import DEFAULT_SEASONS, SEASON_NAMES


@pytest.fixture
def base_cfg():
    return AERSURFACEConfig(
        title="Salem AERSURFACE",
        site_id="SALEM",
        latitude=44.92,
        longitude=-123.04,
        land_cover_file="/data/nlcd/NLCD_2019_LC.tiff",
        nlcd_year=2019,
    )


class TestValidation:
    def test_default_construction_valid(self, base_cfg):
        assert base_cfg.datum == "NAD83"
        assert base_cfg.moisture == "AVERAGE"
        assert base_cfg.frequency == "MONTHLY"
        assert base_cfg.zo_method == "ZORAD"
        assert base_cfg.sectors is None  # one sector covering the compass

    def test_invalid_latitude(self):
        with pytest.raises(ValueError, match="latitude"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=95.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019,
            )

    def test_invalid_longitude(self):
        with pytest.raises(ValueError, match="longitude"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=200.0,
                land_cover_file="/x", nlcd_year=2019,
            )

    def test_invalid_nlcd_year(self):
        with pytest.raises(ValueError, match="nlcd_year"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=1985,
            )

    def test_invalid_datum(self):
        with pytest.raises(ValueError, match="datum"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019, datum="WGS84",
            )

    def test_invalid_moisture(self):
        with pytest.raises(ValueError, match="moisture"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019, moisture="DAMP",
            )

    def test_invalid_frequency(self):
        with pytest.raises(ValueError, match="frequency"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019, frequency="HOURLY",
            )

    def test_invalid_zo_method(self):
        with pytest.raises(ValueError, match="zo_method"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019, zo_method="ZOAVG",
            )

    def test_negative_radius(self):
        with pytest.raises(ValueError, match="zo_radius_km"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019, zo_radius_km=-1.0,
            )

    def test_invalid_sector_angle(self):
        with pytest.raises(ValueError, match="sector angles"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019,
                sectors=[(10.0, 400.0, "AP")],
            )

    def test_invalid_sector_type(self):
        with pytest.raises(ValueError, match="sector type"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019,
                sectors=[(10.0, 90.0, "AIRPORT")],
            )

    def test_seasons_must_cover_every_month_once(self):
        with pytest.raises(ValueError, match="each month"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019,
                seasons={"SUMMER": (6, 7, 8)},
            )

    def test_unknown_season_name_rejected(self):
        with pytest.raises(ValueError, match="season names"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2019,
                seasons={"MONSOON": tuple(range(1, 13))},
            )

    def test_ancillary_year_without_a_product_is_rejected(self):
        # NLCD 1992 and 2013 have no canopy / impervious companion.
        with pytest.raises(ValueError, match="canopy_year"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                land_cover_file="/x", nlcd_year=2013,
                canopy_file="/canopy.tiff",
            )

    def test_default_seasons_cover_the_year(self):
        months = sorted(m for ms in DEFAULT_SEASONS.values() for m in ms)
        assert months == list(range(1, 13))
        assert set(DEFAULT_SEASONS) <= set(SEASON_NAMES)


class TestDeckGeneration:
    def test_pathway_structure(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        lines = [ln.rstrip() for ln in deck.splitlines()]
        assert lines[0] == "CO STARTING"
        assert "CO FINISHED" in lines
        assert "OU STARTING" in lines
        assert lines[-1] == "OU FINISHED"
        assert lines.index("CO FINISHED") < lines.index("OU STARTING")

    def test_minimal_deck_keywords(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        assert "   TITLEONE  Salem AERSURFACE" in deck
        assert "   OPTIONS   PRIMARY  ZORAD" in deck
        assert "   CENTERLL  44.920000  -123.040000  NAD83" in deck
        assert '   DATAFILE  NLCD2019  "/data/nlcd/NLCD_2019_LC.tiff"' in deck
        assert "   ZORADIUS  1" in deck
        assert "   CLIMATE   AVERAGE  SNOW  NONARID" in deck
        assert "   RUNORNOT  RUN" in deck

    def test_title_two_only_when_set(self, base_cfg):
        assert "TITLETWO" not in base_cfg.to_aersurface_input()
        base_cfg.title_two = "second line"
        assert "   TITLETWO  second line" in base_cfg.to_aersurface_input()

    def test_climate_flags(self, base_cfg):
        base_cfg.arid = True
        base_cfg.snow = False
        base_cfg.moisture = "DRY"
        assert "   CLIMATE   DRY  NOSNOW  ARID" in base_cfg.to_aersurface_input()

    def test_uniform_sector_is_one_full_circle(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        assert "   FREQ_SECT  MONTHLY  1  VARYAP" in deck
        assert "   SECTOR  1  0.00  360.00  NONAP" in deck

    def test_airport_flag_sets_the_default_sector(self, base_cfg):
        base_cfg.airport = True
        assert "   SECTOR  1  0.00  360.00  AP" in base_cfg.to_aersurface_input()

    def test_explicit_sectors_are_numbered_in_order(self, base_cfg):
        base_cfg.sectors = [(30.0, 60.0, "NONAP"), (60.0, 225.0, "AP"),
                            (225.0, 30.0, "NONAP")]
        deck = base_cfg.to_aersurface_input()
        assert "   FREQ_SECT  MONTHLY  3  VARYAP" in deck
        assert "   SECTOR  1  30.00  60.00  NONAP" in deck
        assert "   SECTOR  2  60.00  225.00  AP" in deck
        assert "   SECTOR  3  225.00  30.00  NONAP" in deck

    def test_default_seasons_are_written(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        assert "   SEASON  WINTERNS  12 1 2" in deck
        assert "   SEASON  SUMMER  6 7 8" in deck
        assert "WINTERWS" not in deck  # no continuous snow cover by default

    def test_continuous_snow_months_use_winterws(self, base_cfg):
        base_cfg.seasons = {
            "WINTERNS": (12, 2, 3), "WINTERWS": (1,), "SPRING": (4, 5),
            "SUMMER": (6, 7, 8), "AUTUMN": (9, 10, 11),
        }
        deck = base_cfg.to_aersurface_input()
        assert "   SEASON  WINTERWS  1" in deck
        assert "   SEASON  WINTERNS  12 2 3" in deck

    def test_annual_frequency_writes_no_seasons(self, base_cfg):
        base_cfg.frequency = "ANNUAL"
        deck = base_cfg.to_aersurface_input()
        assert "   FREQ_SECT  ANNUAL  1  VARYAP" in deck
        assert "SEASON" not in deck

    def test_ancillary_rasters(self, base_cfg):
        base_cfg.canopy_file = "canopy.tiff"
        base_cfg.impervious_file = "imperv.tiff"
        deck = base_cfg.to_aersurface_input()
        assert '   DATAFILE  CNPY2019  "canopy.tiff"' in deck
        assert '   DATAFILE  MPRV2019  "imperv.tiff"' in deck

    def test_ancillary_year_override(self, base_cfg):
        base_cfg.canopy_file = "canopy.tiff"
        base_cfg.canopy_year = 2016
        assert '   DATAFILE  CNPY2016  "canopy.tiff"' in (
            base_cfg.to_aersurface_input()
        )

    def test_output_files(self, base_cfg):
        base_cfg.sfcchar_file = "sfc.txt"
        base_cfg.land_cover_grid_file = "lc_grid.txt"
        base_cfg.canopy_grid_file = "can_grid.txt"
        base_cfg.impervious_grid_file = "imp_grid.txt"
        deck = base_cfg.to_aersurface_input()
        assert '   SFCCHAR    "sfc.txt"' in deck
        assert '   NLCDGRID   "lc_grid.txt"' in deck
        assert '   CNPYGRID   "can_grid.txt"' in deck
        assert '   MPRVGRID   "imp_grid.txt"' in deck

    def test_grid_outputs_omitted_when_unset(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        for keyword in ("NLCDGRID", "CNPYGRID", "MPRVGRID"):
            assert keyword not in deck

    def test_debug_options(self, base_cfg):
        base_cfg.debug_options = ["GRID", "TIFF"]
        assert "   DEBUGOPT  GRID  TIFF" in base_cfg.to_aersurface_input()

    def test_run_or_not(self, base_cfg):
        base_cfg.run = False
        assert "   RUNORNOT  NOT" in base_cfg.to_aersurface_input()

    def test_extra_lines_land_in_the_right_pathway(self, base_cfg):
        base_cfg.extra_co_lines = ["   ANEM_HGT  10.0"]
        base_cfg.extra_ou_lines = ["** a comment"]
        deck = base_cfg.to_aersurface_input()
        co = deck[: deck.index("CO FINISHED")]
        ou = deck[deck.index("OU STARTING"):]
        assert "   ANEM_HGT  10.0" in co
        assert "** a comment" in ou

    def test_deck_ends_with_newline(self, base_cfg):
        assert base_cfg.to_aersurface_input().endswith("\n")

    def test_no_invented_keywords_survive(self, base_cfg):
        """The previous format's keywords must not reappear.

        None of these exist in AERSURFACE; a deck containing them made
        the real binary abort in its control-file parser.
        """
        deck = base_cfg.to_aersurface_input()
        for invented in ("TITLE  ", "LOCATION  ", "NLCDFILE", "NLCDYEAR",
                         "ARID  ", "AIRPORT  ", "SNOW_TEMPER",
                         "RADIUS_ROUGHNESS", "RADIUS_ALBEDO_BOWEN",
                         "SECTORS_LIST", "MOISTURE  ", "SNOW_COVER",
                         "OUTPATH"):
            assert invented not in deck, invented
