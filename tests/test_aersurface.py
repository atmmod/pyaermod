"""Tests for the AERSURFACE input deck builder."""

from __future__ import annotations

import pytest

from pyaermod import AERSURFACEConfig


@pytest.fixture
def base_cfg():
    return AERSURFACEConfig(
        title="Salem AERSURFACE",
        site_id="SALEM",
        latitude=44.92,
        longitude=-123.04,
        utc_offset=-8,
        nlcd_file="/data/nlcd/NLCD_2019.img",
        nlcd_year=2019,
        snow_regime="CONTINENTAL_WARM",
    )


class TestValidation:
    def test_default_construction_valid(self, base_cfg):
        # Defaults: AVERAGE moisture all 12 months, no snow cover, uniform sector
        assert len(base_cfg.moisture_per_month) == 12
        assert all(s == "N" for s in base_cfg.snow_cover_per_month)
        assert base_cfg.sectors is None  # uniform

    def test_invalid_latitude(self):
        with pytest.raises(ValueError, match="latitude"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=95.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
            )

    def test_invalid_longitude(self):
        with pytest.raises(ValueError, match="longitude"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=200.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
            )

    def test_invalid_nlcd_year(self):
        with pytest.raises(ValueError, match="nlcd_year"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=1985,
            )

    def test_invalid_snow_regime(self):
        with pytest.raises(ValueError, match="snow_regime"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                snow_regime="TROPICAL",
            )

    def test_moisture_length_mismatch(self):
        with pytest.raises(ValueError, match="moisture_per_month"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                moisture_per_month=["AVERAGE"] * 11,
            )

    def test_moisture_invalid_value(self):
        with pytest.raises(ValueError, match="moisture_per_month entries"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                moisture_per_month=["DAMP"] * 12,
            )

    def test_snow_cover_length_mismatch(self):
        with pytest.raises(ValueError, match="snow_cover_per_month"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                snow_cover_per_month=["N", "Y"],
            )

    def test_snow_cover_invalid_value(self):
        with pytest.raises(ValueError):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                snow_cover_per_month=["maybe"] * 12,
            )

    def test_negative_radius(self):
        with pytest.raises(ValueError, match="radius_roughness_km"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                radius_roughness_km=-1.0,
            )

    def test_invalid_sector_angle(self):
        with pytest.raises(ValueError, match="sector angles"):
            AERSURFACEConfig(
                title="t", site_id="S", latitude=0.0, longitude=0.0,
                utc_offset=0, nlcd_file="/x", nlcd_year=2019,
                sectors=[10.0, 360.0],  # 360 is out of [0, 360)
            )


class TestDeckGeneration:
    def test_minimal_deck_round_trip(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        assert "TITLE  Salem AERSURFACE" in deck
        assert "LOCATION  SALEM  44.92000  -123.04000  -8" in deck
        assert "NLCDFILE  /data/nlcd/NLCD_2019.img" in deck
        assert "NLCDYEAR  2019" in deck
        assert "ARID  N" in deck
        assert "AIRPORT  N" in deck
        assert "SNOW_TEMPER  CONTINENTAL_WARM" in deck
        assert "SECTORS_LIST  UNIFORM" in deck
        assert "OUTPATH  ." in deck
        # 12 month rows
        assert deck.count("AVERAGE") == 12
        assert deck.count("MOISTURE  ") == 1

    def test_arid_and_airport_flags(self, base_cfg):
        base_cfg.arid = True
        base_cfg.airport = True
        deck = base_cfg.to_aersurface_input()
        assert "ARID  Y" in deck
        assert "AIRPORT  Y" in deck

    def test_explicit_sectors(self, base_cfg):
        base_cfg.sectors = [0.0, 90.0, 180.0, 270.0]
        deck = base_cfg.to_aersurface_input()
        assert "SECTORS_LIST  0 90 180 270" in deck

    def test_per_month_moisture_pattern(self, base_cfg):
        # Wet winter, dry summer
        base_cfg.moisture_per_month = (
            ["WET"] * 3 + ["AVERAGE"] * 3 + ["DRY"] * 3 + ["AVERAGE"] * 3
        )
        deck = base_cfg.to_aersurface_input()
        # Three of each: WET, DRY, plus the standard AVERAGE
        line = next(ln for ln in deck.splitlines() if ln.startswith("MOISTURE"))
        assert line.count("WET") == 3
        assert line.count("DRY") == 3
        assert line.count("AVERAGE") == 6

    def test_snow_cover_per_month(self, base_cfg):
        base_cfg.snow_cover_per_month = (
            ["Y"] * 3 + ["N"] * 6 + ["Y"] * 3
        )
        deck = base_cfg.to_aersurface_input()
        line = next(ln for ln in deck.splitlines() if ln.startswith("SNOW_COVER"))
        # Strip the keyword to count only month-column tokens
        tokens = line.replace("SNOW_COVER", "").split()
        assert tokens == ["Y"] * 3 + ["N"] * 6 + ["Y"] * 3

    def test_extra_lines_appended(self, base_cfg):
        base_cfg.extra_lines = ["DEBUG  Y", "** custom comment"]
        deck = base_cfg.to_aersurface_input()
        assert "DEBUG  Y" in deck
        assert "** custom comment" in deck

    def test_radius_overrides(self, base_cfg):
        base_cfg.radius_roughness_km = 0.5
        base_cfg.radius_albedo_bowen_km = 5.0
        deck = base_cfg.to_aersurface_input()
        assert "RADIUS_ROUGHNESS  0.5" in deck
        assert "RADIUS_ALBEDO_BOWEN  5.0" in deck

    def test_deck_ends_with_newline(self, base_cfg):
        deck = base_cfg.to_aersurface_input()
        assert deck.endswith("\n")
