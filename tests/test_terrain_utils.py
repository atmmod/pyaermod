"""Tests for terrain_utils."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyaermod.terrain_utils import (
    HAS_PYPROJ,
    HAS_RASTERIO,
    DatumTransformer,
    HillHeightAnomaly,
    async_fetch_tiles,
    hill_height_diagnostics,
    srtm_tile_name,
    srtm_tiles_for_bbox,
    utm_epsg,
    utm_zone_for_lon,
)


# ---------------------------------------------------------------------------
# UTM helpers (pure math, no deps)
# ---------------------------------------------------------------------------

class TestUTMHelpers:
    def test_zone_at_zero(self):
        assert utm_zone_for_lon(0) == 31
        assert utm_zone_for_lon(-177.0) == 1
        assert utm_zone_for_lon(177.0) == 60

    def test_zone_boundaries(self):
        # -180 is zone 1; 0 is zone 31 (lon/6 + 30 + 1)
        assert utm_zone_for_lon(-180) == 1
        # Zone 30 covers -6° to 0°; zone 31 covers 0° to 6°
        assert utm_zone_for_lon(-5.99) == 30
        assert utm_zone_for_lon(0.01) == 31

    def test_zone_out_of_range_raises(self):
        with pytest.raises(ValueError):
            utm_zone_for_lon(200)

    def test_epsg_north_south(self):
        # Continental US: positive lat -> 326xx; negative -> 327xx
        assert utm_epsg(-95, 40) == 32615
        assert utm_epsg(-95, -40) == 32715


# ---------------------------------------------------------------------------
# SRTM tile naming
# ---------------------------------------------------------------------------

class TestSRTMNames:
    def test_name_formatting(self):
        assert srtm_tile_name(35.5, -105.2) == "N35W106"
        assert srtm_tile_name(-15.1, 120.9) == "S16E120"
        assert srtm_tile_name(0.0, 0.0) == "N00E000"

    def test_bbox_enumeration(self):
        tiles = srtm_tiles_for_bbox((-105.5, 35.5, -104.5, 36.5))
        names = {t.tile_name for t in tiles}
        assert "N35W106" in names and "N36W106" in names and "N35W105" in names
        # Every URL contains the expected path prefix
        for t in tiles:
            assert "SRTMGL1.hgt.zip" in t.download_url


# ---------------------------------------------------------------------------
# Async fetch
# ---------------------------------------------------------------------------

class TestAsyncFetch:
    def test_parallel_returns_in_order(self):
        def fake_fetch(url):
            return f"got:{url}"
        results = async_fetch_tiles(["a", "b", "c"], fake_fetch)
        assert results == ["got:a", "got:b", "got:c"]

    def test_exceptions_returned_not_raised(self):
        def fake_fetch(url):
            if url == "bad":
                raise RuntimeError("nope")
            return url
        results = async_fetch_tiles(["ok", "bad", "ok2"], fake_fetch)
        assert results[0] == "ok"
        assert isinstance(results[1], RuntimeError)
        assert results[2] == "ok2"


# ---------------------------------------------------------------------------
# Hill-height diagnostics
# ---------------------------------------------------------------------------

@dataclass
class _Rec:
    x: float
    y: float
    zelev: float
    zhill: float


class TestHillHeightDiagnostics:
    def test_zhill_below_zelev_flagged(self):
        recs = [_Rec(0, 0, 100.0, 90.0)]
        flags = hill_height_diagnostics(recs)
        assert len(flags) == 1
        assert "below zelev" in flags[0].reason

    def test_valid_records_clean(self):
        recs = [_Rec(i * 100, 0, 100.0, 105.0) for i in range(5)]
        flags = hill_height_diagnostics(recs)
        assert flags == []

    def test_steep_gradient_flagged(self):
        # 100 m rise over 0.5 m distance -> gradient 200 m/m
        recs = [_Rec(0, 0, 100.0, 100.0), _Rec(0.5, 0, 200.0, 200.0)]
        flags = hill_height_diagnostics(recs, max_gradient_mperm=10.0)
        assert any("gradient" in f.reason for f in flags)

    def test_flat_patch_flagged(self):
        recs = [_Rec(i * 10, 0, 500.0, 500.0) for i in range(30)]
        flags = hill_height_diagnostics(recs)
        assert any("flat-elevation" in f.reason for f in flags)


# ---------------------------------------------------------------------------
# Datum transformer (pyproj-dependent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_PYPROJ, reason="pyproj not installed")
class TestDatumTransformer:
    def test_nad83_to_wgs84_minimal_shift(self):
        tr = DatumTransformer.nad83_to_wgs84()
        lon_out, lat_out = tr.transform(-95.0, 40.0)
        # NAD83 and WGS84 are sub-cm apart in CONUS
        assert abs(lon_out - (-95.0)) < 0.001
        assert abs(lat_out - 40.0) < 0.001

    def test_nad27_to_nad83_real_shift(self):
        tr = DatumTransformer.nad27_to_nad83()
        lon_out, lat_out = tr.transform(-95.0, 40.0)
        # NAD27 vs NAD83 shifts ~50-100 m in CONUS; 0.0001 deg ~ 10 m
        shift = abs(lon_out - (-95.0)) + abs(lat_out - 40.0)
        assert shift > 0


# ---------------------------------------------------------------------------
# Mosaic / reproject (rasterio-dependent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_RASTERIO, reason="rasterio not installed")
class TestMosaicReproject:
    def _make_tile(self, path, epsg=4326, value=100):
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        arr = np.full((10, 10), value, dtype="float32")
        tf = from_bounds(-105, 35, -104, 36, 10, 10)
        with rasterio.open(
            str(path), "w",
            driver="GTiff", height=10, width=10, count=1,
            dtype="float32", crs=f"EPSG:{epsg}", transform=tf,
        ) as dst:
            dst.write(arr, 1)

    def test_mosaic_single_tile_roundtrip(self, tmp_path):
        from pyaermod.terrain_utils import mosaic_dem_tiles
        t1 = tmp_path / "t1.tif"
        self._make_tile(t1, value=100)
        out = mosaic_dem_tiles([t1], tmp_path / "mosaic.tif")
        assert out.exists()

    def test_reproject_changes_crs(self, tmp_path):
        from pyaermod.terrain_utils import reproject_dem
        import rasterio
        src = tmp_path / "src.tif"
        self._make_tile(src, epsg=4326)
        out = reproject_dem(src, tmp_path / "utm.tif", dst_epsg=32613)
        with rasterio.open(str(out)) as r:
            assert r.crs.to_epsg() == 32613
