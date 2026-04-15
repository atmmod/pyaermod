# AERMAP Troubleshooting

AERMAP is the terrain preprocessor for AERMOD. It reads DEM data,
snaps each source and receptor to the DEM grid, and writes elevation
(`zelev`) and hill-height (`zhill`) values AERMOD uses for terrain
effects.

This guide covers the common things that go wrong and how to use
pyaermod's `terrain_utils` helpers to diagnose them.

## DEM data sources

| Source | Resolution | Coverage | Where |
|---|---|---|---|
| USGS 3DEP / NED 1/3" | ~10 m | CONUS + Alaska | pyaermod's `DEMDownloader` (see `terrain.py`) |
| SRTM v3.0 1" | ~30 m | global ±60° | `srtm_tiles_for_bbox` in `terrain_utils` |
| Copernicus GLO-30 | ~30 m | global | fetch manually; reproject via `reproject_dem` |
| NED 1/9" | ~3 m | CONUS, select | USGS, not fetched automatically |

## Datum mismatches (the silent killer)

A surprisingly large fraction of "weird receptor elevation" bugs come
from DEM and receptor coordinates being in different datums.

- NAD27 vs. NAD83 shifts are ~50–100 m in CONUS — enough to put
  receptors on the wrong side of a ridge.
- Older 7.5-minute quad DEMs are NAD27; modern 3DEP is NAD83.
- Use `pyaermod.terrain_utils.DatumTransformer` to convert explicitly:

```python
from pyaermod import DatumTransformer
tr = DatumTransformer.nad27_to_nad83()
lon83, lat83 = tr.transform(lon27, lat27)
```

## UTM zone picking

AERMOD expects all inputs in a consistent projected coordinate system
— typically the UTM zone covering the site. Pick with:

```python
from pyaermod import utm_zone_for_lon, utm_epsg
zone = utm_zone_for_lon(-95.0)         # -> 15
epsg = utm_epsg(-95.0, 40.0)           # -> 32615 (WGS84 UTM 15N)
```

If the domain crosses a zone boundary, stick with one zone (the one
containing the sources) rather than the nominal "center" — AERMAP /
AERMOD computations are done in the input CRS, not lat/lon.

## Multi-tile mosaics

NED tiles are 1x1 degree; a typical modeling domain spans several. To
merge:

```python
from pyaermod.terrain_utils import mosaic_dem_tiles, reproject_dem
mosaic = mosaic_dem_tiles(
    ["N34W106.tif", "N35W106.tif", "N34W105.tif", "N35W105.tif"],
    output_path="mosaic.tif",
)
reproject_dem(mosaic, "mosaic_utm.tif", dst_epsg=32613)  # UTM 13N
```

Requires `rasterio`. Cache the mosaic — reprojection is expensive.

## Hill-height diagnostics

After running AERMAP, scan its `RECEPTORS.DAT` / `SOURCES.DAT` output
for anomalies:

```python
from pyaermod import AERMAPOutputParser, hill_height_diagnostics
parsed = AERMAPOutputParser().parse_output("AERMAP.OUT")
flags = hill_height_diagnostics(parsed.receptors)
for f in flags:
    print(f.reason, "at", (f.x, f.y))
```

What `hill_height_diagnostics` flags:

| Flag | Meaning | Typical cause |
|---|---|---|
| `zhill below zelev` | hill height less than ground elevation | DEM read failure / wrong datum |
| `elevation gradient > N m/m` | cliff-sharp change between adjacent receptors | hole in DEM, tile seam |
| `flat-elevation run` | 25+ consecutive receptors at identical elevation | DEM "fill" / placeholder tile |

## Common failure modes

| Symptom | Check |
|---|---|
| "receptor outside DEM bounds" | bbox of receptors vs. DEM extent — fetch more tiles |
| All `zhill` values = 0 | AERMAP didn't pick up terrain file — check CO pathway TERRHGTS path |
| `zhill < zelev` on many receptors | datum mismatch between receptors and DEM |
| Wildly high hill heights | receptor coordinates in feet but treated as meters |

## SRTM fallback outside CONUS

USGS NED only covers the US. Outside that footprint, SRTM 1" is the
workhorse fallback:

```python
from pyaermod import srtm_tiles_for_bbox
tiles = srtm_tiles_for_bbox((-80.0, 25.0, -79.0, 26.0))  # bounds in lon/lat
for t in tiles:
    print(t.tile_name, t.download_url)
```

SRTM downloads typically require NASA EarthData Login; OpenTopography
is an unauthenticated alternative.
