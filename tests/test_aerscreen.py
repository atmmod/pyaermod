"""Tests for the AERSCREEN deck builder."""

from __future__ import annotations

import pytest

from pyaermod import AERSCREENConfig, AERSCREENSourceType


def _point():
    return AERSCREENConfig(
        title="Stack screening",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=10.0,
        stack_height=30.0,
        stack_diameter=2.0,
        stack_temp=425.0,
        exit_velocity=15.0,
    )


class TestValidation:
    def test_valid_point(self):
        cfg = _point()
        assert cfg.source_type == AERSCREENSourceType.POINT

    def test_string_source_type_coerced(self):
        cfg = AERSCREENConfig(
            title="t", source_type="point", emission_rate=1.0,
            stack_height=10.0, stack_diameter=1.0, stack_temp=400.0,
            exit_velocity=10.0,
        )
        assert cfg.source_type == AERSCREENSourceType.POINT

    def test_zero_emission_rate_raises(self):
        with pytest.raises(ValueError, match="emission_rate"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=0.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
            )

    def test_point_requires_stack_height(self):
        with pytest.raises(ValueError, match="stack_height"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_diameter=1.0, stack_temp=400.0,
                exit_velocity=10.0,
            )

    def test_point_requires_stack_diameter(self):
        with pytest.raises(ValueError, match="stack_diameter"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_temp=400.0,
                exit_velocity=10.0,
            )

    def test_point_requires_exit_velocity(self):
        with pytest.raises(ValueError, match="exit_velocity"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0,
            )

    def test_flare_requires_heat_release(self):
        with pytest.raises(ValueError, match="flare_heat_release"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.FLARE,
                emission_rate=1.0, stack_height=10.0,
            )

    def test_area_requires_dimensions(self):
        with pytest.raises(ValueError, match="area_length"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.AREA,
                emission_rate=1.0,
            )
        with pytest.raises(ValueError, match="area_width"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.AREA,
                emission_rate=1.0, area_length=50.0,
            )

    def test_volume_requires_all_dimensions(self):
        with pytest.raises(ValueError, match="initial_sigma_z"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.VOLUME,
                emission_rate=1.0,
            )

    def test_temp_min_lt_max(self):
        with pytest.raises(ValueError, match="temp_min_k"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                temp_min_k=350.0, temp_max_k=300.0,
            )

    def test_invalid_landuse_code(self):
        with pytest.raises(ValueError, match="Auer"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                dominant_landuse=20,
            )

    def test_downwash_requires_building_dimensions(self):
        with pytest.raises(ValueError, match="building_height"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                downwash=True,
            )

    def test_terrain_requires_lat_lon(self):
        with pytest.raises(ValueError, match="lat and lon"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                terrain=True,
            )

    def test_distances_must_be_auto_or_list(self):
        with pytest.raises(ValueError, match="distances string"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                distances="LOTS",
            )

    def test_negative_distance_rejected(self):
        with pytest.raises(ValueError, match="distances must be > 0"):
            AERSCREENConfig(
                title="t", source_type=AERSCREENSourceType.POINT,
                emission_rate=1.0, stack_height=10.0, stack_diameter=1.0,
                stack_temp=400.0, exit_velocity=10.0,
                distances=[100.0, -50.0],
            )


class TestDeckGeneration:
    def test_minimal_point_deck(self):
        deck = _point().to_aerscreen_input()
        assert "TITLE: Stack screening" in deck
        assert "SOURCE_TYPE: POINT" in deck
        assert "EMISSION_RATE: 10.0" in deck
        assert "STACK_HEIGHT: 30.0" in deck
        assert "STACK_DIAMETER: 2.0" in deck
        assert "STACK_TEMP: 425.0" in deck
        assert "EXIT_VELOCITY: 15.0" in deck
        assert "URBAN_RURAL: R" in deck
        assert "DOWNWASH: N" in deck
        assert "TERRAIN: N" in deck
        assert "FUMIGATION: N" in deck
        assert "DISTANCES: AUTO" in deck

    def test_ambient_temp_keyword(self):
        cfg = _point()
        cfg.stack_temp = None
        deck = cfg.to_aerscreen_input()
        assert "STACK_TEMP: AMBIENT" in deck

    def test_flare_deck(self):
        cfg = AERSCREENConfig(
            title="flare", source_type=AERSCREENSourceType.FLARE,
            emission_rate=2.0, stack_height=20.0, flare_heat_release=1e7,
        )
        deck = cfg.to_aerscreen_input()
        assert "SOURCE_TYPE: FLARE" in deck
        assert "FLARE_HEAT_RELEASE: 10000000.0" in deck
        # Stack diameter / velocity should not appear
        assert "STACK_DIAMETER" not in deck
        assert "EXIT_VELOCITY" not in deck

    def test_area_deck(self):
        cfg = AERSCREENConfig(
            title="area", source_type=AERSCREENSourceType.AREA,
            emission_rate=0.1, stack_height=2.0,
            area_length=100.0, area_width=50.0,
        )
        deck = cfg.to_aerscreen_input()
        assert "SOURCE_TYPE: AREA" in deck
        assert "AREA_LENGTH: 100.0" in deck
        assert "AREA_WIDTH: 50.0" in deck
        assert "RELEASE_HEIGHT: 2.0" in deck

    def test_volume_deck(self):
        cfg = AERSCREENConfig(
            title="vol", source_type=AERSCREENSourceType.VOLUME,
            emission_rate=0.5, stack_height=5.0,
            initial_sigma_z=2.0, lateral_dim=10.0, vertical_dim=4.0,
        )
        deck = cfg.to_aerscreen_input()
        assert "SOURCE_TYPE: VOLUME" in deck
        assert "INITIAL_SIGMA_Z: 2.0" in deck
        assert "LATERAL_DIM: 10.0" in deck
        assert "VERTICAL_DIM: 4.0" in deck

    def test_urban_emits_population(self):
        cfg = _point()
        cfg.urban = True
        cfg.population = 250_000
        deck = cfg.to_aerscreen_input()
        assert "URBAN_RURAL: U" in deck
        assert "POPULATION: 250000" in deck

    def test_rural_omits_population(self):
        deck = _point().to_aerscreen_input()
        assert "POPULATION:" not in deck

    def test_downwash_emits_building_block(self):
        cfg = _point()
        cfg.downwash = True
        cfg.building_height = 25.0
        cfg.building_length = 50.0
        cfg.building_width = 30.0
        cfg.building_angle = 45.0
        deck = cfg.to_aerscreen_input()
        assert "DOWNWASH: Y" in deck
        assert "BUILDING_HEIGHT: 25.0" in deck
        assert "BUILDING_ANGLE: 45.0" in deck

    def test_terrain_block_with_file(self, tmp_path):
        dem = tmp_path / "dem.txt"
        dem.write_text("placeholder")
        cfg = _point()
        cfg.terrain = True
        cfg.lat = 42.36
        cfg.lon = -71.06
        cfg.terrain_file = str(dem)
        deck = cfg.to_aerscreen_input()
        assert "TERRAIN: Y" in deck
        assert "LAT: 42.36" in deck
        assert "LON: -71.06" in deck
        assert f"TERRAIN_FILE: {dem}" in deck

    def test_explicit_distances(self):
        cfg = _point()
        cfg.distances = [100.0, 250.0, 500.0, 1000.0]
        deck = cfg.to_aerscreen_input()
        assert "DISTANCES: 100 250 500 1000" in deck

    def test_extra_lines_appended(self):
        cfg = _point()
        cfg.extra_lines = ["DEBUG: Y", "** custom"]
        deck = cfg.to_aerscreen_input()
        assert "DEBUG: Y" in deck
        assert "** custom" in deck

    def test_deck_ends_with_newline(self):
        deck = _point().to_aerscreen_input()
        assert deck.endswith("\n")

    def test_use_adju_flag(self):
        cfg = _point()
        cfg.use_adju = True
        deck = cfg.to_aerscreen_input()
        assert "USE_ADJU: Y" in deck

    def test_landuse_code_emitted(self):
        cfg = _point()
        cfg.dominant_landuse = 7
        deck = cfg.to_aerscreen_input()
        assert "DOMINANT_LU: 7" in deck
