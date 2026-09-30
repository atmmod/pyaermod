# AERMAP Troubleshooting

AERMAP is the terrain preprocessor for AERMOD. It reads DEM data,
snaps each source and receptor to the DEM grid, and writes elevation
(`zelev`) and hill-height (`zhill`) values AERMOD uses for terrain
effects.

This guide covers the common things that go wrong and how to use
pyaermod's `terrain_utils` helpers to diagnose them.

## Writing and running an AERMAP deck

`AERMAPProject.to_aermap_input` writes the runstream of EPA's AERMAP
24142, the current release (AERMAP has no 26135 release). The deck has
the pathways in the order AERMAP requires, CO, SO, RE, OU, and looks
like this for one receptor, a 3 × 2 grid and one stack:

```text
CO STARTING
   TITLEONE  pyaermod AERMAP runner recording
   DATATYPE  DEM
   DATAFILE  synth.dem
   DOMAINXY  500050.00 4000050.00 13 500550.00 4000550.00 13
   ANCHORXY  500000.00 4000000.00 500000.00 4000000.00 13 1
   TERRHGTS  EXTRACT
   RUNORNOT  RUN
CO FINISHED

SO STARTING
   LOCATION  STACK1       POINT      500200.00   4000300.00
SO FINISHED

RE STARTING
   DISCCART     500100.00   4000100.00
   GRIDCART  GRID     STA
   GRIDCART  GRID     XYINC     500100.00     3     100.00    4000200.00     2     100.00
   GRIDCART  GRID     END
RE FINISHED

OU STARTING
   RECEPTOR  aermap_receptors.out
   SOURCLOC  aermap_sources.out
OU FINISHED
```

```python
from pyaermod.aermap import AERMAPProject, AERMAPReceptor, AERMAPSource
from pyaermod.terrain import AERMAPRunner

project = AERMAPProject(
    title_one="pyaermod AERMAP runner recording",
    dem_files=["synth.dem"], dem_format="DEM",
    anchor_x=500000.0, anchor_y=4000000.0, utm_zone=13, datum="NAD27",
    grid_receptor=True, grid_x_init=500100.0, grid_y_init=4000200.0,
    grid_x_num=3, grid_y_num=2, grid_spacing=100.0,
    domain_x_min=500050.0, domain_y_min=4000050.0,
    domain_x_max=500550.0, domain_y_max=4000550.0,
)
project.add_receptor(AERMAPReceptor("R1", 500100.0, 4000100.0))
project.add_source(AERMAPSource("STACK1", 500200.0, 4000300.0))
project.write("aermap.inp")

result = AERMAPRunner().run("aermap.inp")
if not result.success:
    raise RuntimeError(result.error_message)
```

What the fields mean:

- **Anchor.** `ANCHORXY` ties the user point (`anchor_x`, `anchor_y`)
  to a UTM point (`anchor_utm_x`, `anchor_utm_y`) in `utm_zone`. The
  UTM point defaults to the anchor itself, which says the receptor and
  source coordinates are already UTM. `datum` is written as AERMAP's
  code: `"NAD27"` 1, `"WGS72"` 2, `"WGS84"` 3, `"NAD83"` 4, or an
  integer from 0 to 7.
- **Domain.** `DOMAINXY` is written when all four `domain_*` corners
  are set, in UTM metres. AERMAP then searches only this area for hill
  heights, so the domain must take in every terrain feature that rises
  above a 10% slope from any receptor (the rule in `sub_calchc.f`);
  otherwise the hill heights come out too low, with no warning. The
  whole area must also lie inside the DEM files, or AERMAP stops with
  `E310 Domain Coordinate is NOT Inside a DEM File`. Leave the corners
  unset to let AERMAP search the full extent of the DEM files, which is
  the safe choice and what `from_aermod_project` and `TerrainProcessor`
  do by default.
- **Datum shifts.** When the DEM files' datum differs from `datum`,
  AERMAP converts between them with the NADCON grid files (`conus.las`,
  `conus.los` and the others EPA ships with AERMAP) and stops with
  `E365 NAD Conversion Grid Files (*.las; *.los) Not Found` when it
  cannot find them. Set `nad_grids_dir` to the directory that holds
  them (written as `NADGRIDS`), or put them in the working directory.
  USGS native `.dem` files (`dem_format="DEM"`) are usually NAD27, so
  with them use `datum="NAD27"` (or `0`, no shift) unless you supply
  the NADCON files.
- **Terrain heights.** `terrain_type="EXTRACT"` (the default) takes the
  elevations from the DEM, and the deck leaves out any elevation you
  set. `"PROVIDED"` keeps the elevations you give, which every receptor
  and source must then carry, and has AERMAP compute only the
  receptors' hill heights; AERMAP writes no source file under
  `PROVIDED`, so the deck asks for none. `"FLAT"` is not an AERMAP
  option: a flat run needs no AERMAP, only `TerrainType.FLAT` in the
  AERMOD deck.
- **Formats.** `dem_format` is `"NED"` for GeoTIFF or `"DEM"` for the
  USGS native format.
- **Source types.** `AERMAPSource.source_type` is one of AERMAP's
  types: `POINT`, `POINTCAP`, `POINTHOR`, `VOLUME`, `AREA`, `AREAPOLY`,
  `AREACIRC` and `OPENPIT` sit at (`x_coord`, `y_coord`); `RLINE` and
  `BUOYLINE` also need `x_end`, `y_end`, and AERMAP takes their
  elevation at the midpoint; `LINE` also needs its `width`, and AERMAP
  takes its elevation at the south-west corner of its equivalent area
  (`SOLOCA` in `aermap.f`).
- **Receptor networks.** `grids` takes AERMOD `CartesianGrid` and
  `PolarGrid` objects, each written as a `GRIDCART` or `GRIDPOLR` block
  under its own `grid_name` (1 to 8 characters, unique). A polar grid
  centred on a source (`origin_source_id`) is written with that
  source's coordinates. The older `grid_receptor` fields still write one
  grid named `GRID`.
- **No IDs, no message file.** AERMAP has no receptor IDs, so
  `AERMAPReceptor.receptor_id` is not written, and it always writes its
  messages to `<input stem>.out` beside the input file.

A path with a space is written in double quotes. AERMAP reads at most
200 characters per field, so a longer path raises `ValueError`; move
the file or use a relative path.

### From an AERMOD project

`AERMAPProject.from_aermod_project(project, dem_files, ...)` and
`TerrainProcessor.process(project, ...)` write every source, every
Cartesian and polar grid and every discrete receptor of an
`AERMODProject`, and `process` fills in each one's elevation from
AERMAP's output: each source's `base_elevation` (and each BUOYLINE
segment's), each grid's `grid_elevations`/`grid_hills` or
`elevations`/`hills` (matched by grid name), and each discrete
receptor's `z_elev`/`z_hill`. Each source is written as the AERMAP type
that gets its elevation where AERMOD expects it: the AERMOD type itself
where AERMAP has it, `SWPOINT` as `POINT`, `RLINEXT` as `RLINE`, an
`AREAPOLY` at its first vertex and each BUOYLINE segment under its own
ID. A source AERMAP cannot place raises `ValueError`.

The AERMOD coordinates are read as UTM in `utm_zone`. No domain is
written unless you ask for one with `buffer=` (`from_aermod_project`)
or `domain_buffer=` (`TerrainProcessor`), in metres around the
project's extent; see **Domain** above for what a domain cuts off.
`nad_grids_dir=` is passed on as `NADGRIDS`.

### Did the run work?

AERMAP exits with code 0 even when fatal errors stop it, and a run that
fails after setup can still leave empty `RECEPTOR` and `SOURCLOC` files
behind. `AERMAPRunner` therefore reads AERMAP's verdict from
`<input stem>.out`: `result.success` is true only when that file ends
with `*** AERMAP Finishes Successfully ***` and its final message
summary counts no fatal error. On a failure, `result.error_message`
names AERMAP's first fatal error, for example

```text
OU E310 line 29 CHKEXT: Domain Coordinate is NOT Inside a DEM File. Pt.= 1 (and 3 more fatal error(s))
```

and `result.fatal_errors`, `result.fatal_count`,
`result.warning_count` and `result.message_file` carry the rest.
`TerrainProcessor.process` raises `RuntimeError` with that message.

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

After running AERMAP, scan its receptor file (`OU RECEPTOR`) for
anomalies:

```python
from pyaermod import AERMAPOutputParser, hill_height_diagnostics
receptors = AERMAPOutputParser.parse_receptor_output("aermap_receptors.out")
flags = hill_height_diagnostics(list(receptors.itertuples()))
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
| All `zhill` values = 0 | AERMAP didn't pick up the terrain file — check the CO pathway's `DATAFILE` paths and `DATATYPE` |
| `result.success` is false with `E310` | the `DOMAINXY` area reaches past the DEM files — fetch more tiles or shrink the domain |
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
