"""H-3: from_shapefile with Esri's 10-character column names, nulls and a lon/lat layer."""

import warnings

import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point  # noqa: E402

from pyaermod.source_importers import from_shapefile  # noqa: E402


def _write(tmp_path, rows, crs="EPSG:32616"):
    gdf = gpd.GeoDataFrame(
        {"source_id": [r["id"] for r in rows],
         "emission_rate": [r["q"] for r in rows],
         "stack_height": [r["h"] for r in rows],
         "stack_temp": [400.0] * len(rows),
         "exit_velocity": [7.0] * len(rows),
         "stack_diameter": [1.5] * len(rows)},
        geometry=[Point(500000 + 10 * i, 3700000) for i in range(len(rows))], crs=crs)
    path = tmp_path / "sources.shp"
    gdf.to_file(path)                    # Esri truncates the names to 10 characters
    return path


def test_truncated_column_names_still_fill_the_fields(tmp_path):
    path = _write(tmp_path, [{"id": "A", "q": 5.0, "h": 25.0}])
    (src,) = from_shapefile(path)
    assert (src.emission_rate, src.stack_height, src.exit_velocity, src.stack_diameter) == (5.0, 25.0, 7.0, 1.5)


def test_a_null_in_a_numeric_column_does_not_become_nan(tmp_path):
    path = _write(tmp_path, [{"id": "A", "q": 5.0, "h": 25.0}, {"id": "B", "q": None, "h": 25.0}])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            sources = from_shapefile(path, attribute_map={"emission_r": "emission_rate"})
        except ValueError:
            return                         # refusing the null is also correct
    assert all(s.emission_rate == s.emission_rate for s in sources), "emission_rate is nan"


def test_a_longitude_latitude_layer_is_not_taken_for_metres(tmp_path):
    path = _write(tmp_path, [{"id": "A", "q": 5.0, "h": 25.0}], crs="EPSG:4326")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            from_shapefile(path)
        except ValueError:
            return
    assert any("crs" in str(w.message).lower() or "degree" in str(w.message).lower()
               or "metre" in str(w.message).lower() for w in caught), "no warning about geographic coordinates"
