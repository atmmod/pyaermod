"""Elevated and complex terrain: AERMAP elevations and hill heights, ELEV vs FLAT.

Downloads USGS 3DEP 1 arc-second (~30 m) DEM tiles around a 145 m stack on the Hudson
River at Tomkins Cove, NY (site of EPA's Lovett complex-terrain study), runs AERMAP to give
the stack and a 9 km x 9 km receptor grid elevations and hill heights, then runs AERMOD
with TERRAIN ELEV and FLAT. Writes 08_complex_terrain.png: annual SO2 of both runs.
"""

import copy
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, LogNorm
from rasterio.merge import merge

from pyaermod import (
    AERMAPOutputParser,
    AERMODProject,
    AERMODRunner,
    CartesianGrid,
    ControlPathway,
    DEMDownloader,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainProcessor,
    TerrainType,
    Validator,
    hill_height_diagnostics,
    parse_aermod_output,
    read_plotfile,
)

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "08_complex_terrain"
WORK.mkdir(parents=True, exist_ok=True)

# Site: stack on the riverbank at 41.2590 N, 73.9790 W = UTM 18N (NAD83) 585531 E, 4568012 N.
STACK_X, STACK_Y = 585530.0, 4568010.0
UTM_ZONE = 18
HALF = 4500.0      # receptor grid half-width, m
SPACING = 150.0    # receptor spacing, m
BUFFER = 3000.0    # extra terrain AERMAP searches for hill heights, m
# DEM bounding box (west, south, east, north), degrees: grid + buffer, with margin.
BBOX = (-74.08, 41.18, -73.88, 41.34)

# 1. DEM, cached per bounding box. The TNM API lists every dated version of each
#    1x1-degree tile, so keep the newest per tile (its date sorts last). USGS ships
#    LZW-compressed tiles, which AERMAP cannot read (E455, TIFF tag 259), so merge
#    them, crop to the box and write one uncompressed GeoTIFF for AERMAP.
site_dem = WORK / "dem" / ("site_" + "_".join(f"{v:g}" for v in BBOX) + ".tif")
if not site_dem.exists():
    dem = DEMDownloader(cache_dir=WORK / "dem", dataset="National Elevation Dataset (NED) 1 arc-second")
    newest = {}
    for tile in sorted(dem.find_tiles(BBOX), key=lambda t: t.download_url):
        m = re.search(r"_(n\d+w\d+)_\d{8}\.tif$", tile.download_url)
        if m:
            newest[m.group(1)] = tile
    srcs = [rasterio.open(dem.download_tile(t)) for t in newest.values()]
    print("DEM tiles:", ", ".join(Path(s.name).name for s in srcs))
    mosaic, transform = merge(srcs, bounds=BBOX)
    profile = {**srcs[0].profile, "height": mosaic.shape[1], "width": mosaic.shape[2],
               "transform": transform, "compress": None, "tiled": False}
    profile.pop("blockxsize"), profile.pop("blockysize")
    with rasterio.open(site_dem, "w", **profile) as dst:
        dst.write(mosaic)

# 2. The AERMOD project; base and receptor elevations come from AERMAP below.
control = ControlPathway(
    title_one="Complex terrain: 145 m stack in the Hudson Highlands",
    title_two="AERMAP elevations and hill heights from USGS 3DEP",
    pollutant_id=PollutantType.SO2,
    averaging_periods=["1", "ANNUAL"],
    terrain_type=TerrainType.ELEVATED,      # regulatory default (DFAULT)
)
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STK1", x_coord=STACK_X, y_coord=STACK_Y,
    stack_height=145.0,    # m
    stack_temp=382.0,      # K
    exit_velocity=23.1,    # m/s
    stack_diameter=4.5,    # m
    emission_rate=100.0,   # g/s
))
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    STACK_X - HALF, STACK_X + HALF, STACK_Y - HALF, STACK_Y + HALF, spacing=SPACING, grid_name="GRID1"))
met = MeteorologyPathway(
    surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
    profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
    surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
    profile_base_elevation=1.8,   # m MSL, as in EPA's lovett.inp
)
project = AERMODProject(control, sources, receptors, met,
                        OutputPathway(receptor_table_rank=1, period_plot_files="elev"))

# 3. AERMAP: write the deck, run it and copy every elevation into the project.
TerrainProcessor().process(
    project, bounds=BBOX, working_dir=WORK / "aermap", utm_zone=UTM_ZONE, datum="NAD83",
    skip_download=True, dem_files=[str(site_dem.resolve())], domain_buffer=BUFFER,
)
elev = np.array(receptors.cartesian_grids[0].grid_elevations)
hill = np.array(receptors.cartesian_grids[0].grid_hills)
print(f"Stack base {sources.sources[0].base_elevation:.1f} m; receptors {elev.min():.0f}-{elev.max():.0f} m, "
      f"hill heights up to {hill.max():.0f} m")
aermap_rec = AERMAPOutputParser.parse_receptor_output(WORK / "aermap" / "aermap_receptors.out")
flags = hill_height_diagnostics(list(aermap_rec.itertuples()))
print(f"hill_height_diagnostics: {len(flags)} flag(s)", *sorted({f.reason for f in flags}), sep="\n  ")

# 4. The FLAT twin. DFAULT overrides FLAT with ELEV (W206), so it drops DFAULT.
flat = copy.deepcopy(project)
flat.control.terrain_type = TerrainType.FLAT
flat.control.regulatory_default = False
flat.output.period_plot_files = "flat"

runner = AERMODRunner()
results, plots = {}, {}
for name, proj in (("ELEV", project), ("FLAT", flat)):
    check = Validator.validate(proj)
    if not check.is_valid:
        raise SystemExit(str(check))
    inp = proj.write(WORK / f"{name.lower()}.inp")
    run = runner.run(inp, working_dir=WORK)
    if not run.success:
        raise SystemExit(f"AERMOD {name} failed: {run.error_message}")
    results[name] = parse_aermod_output(run.output_file)
    plots[name] = read_plotfile(WORK / f"{name.lower()}_ANNUAL.plt").to_dataframe()

print(f"AERMOD {results['ELEV'].run_info.version}, {len(elev.flat)} receptors")
for name, res in results.items():
    for period in ("1HR", "ANNUAL"):
        m = res.get_max_concentration(period)
        print(f"{name:4s} {period:6s} max {m['value']:8.2f} ug/m3 at ({m['x']:.0f}, {m['y']:.0f}) "
              f"{np.hypot(m['x'] - STACK_X, m['y'] - STACK_Y):.0f} m from the stack")

# 5. Figure: annual average of each run; colour only where it is above 1/30 of the
#    highest, so the hillshade of the AERMAP elevations shows through elsewhere.
xs = receptors.cartesian_grids[0].x_values()
ys = receptors.cartesian_grids[0].y_values()
X, Y = ((np.array(v) - c) / 1000 for v, c in zip(np.meshgrid(xs, ys), (STACK_X, STACK_Y)))  # km
shade = LightSource(azdeg=315, altdeg=40).hillshade(elev, vert_exag=2, dx=SPACING, dy=SPACING)
vmax = max(df["AVERAGE_CONC"].max() for df in plots.values())
levels = np.geomspace(vmax / 30, vmax, 9)

fig, axes = plt.subplots(1, 2, figsize=(9, 6.5), sharey=True, constrained_layout=True)
for ax, name in zip(axes, ("FLAT", "ELEV")):
    conc = plots[name].sort_values(["Y", "X"])["AVERAGE_CONC"].to_numpy().reshape(elev.shape)
    ax.imshow(shade, cmap="gray", origin="lower", extent=(X.min(), X.max(), Y.min(), Y.max()), vmin=-0.3)
    cs = ax.contourf(X, Y, np.clip(conc, levels[0] / 10, None), levels=levels, norm=LogNorm(levels[0], vmax),
                     cmap="YlOrRd", alpha=0.75, extend="max")
    tc = ax.contour(X, Y, elev, levels=[100, 200, 300], colors="k", linewidths=0.6, alpha=0.7)
    ax.clabel(tc, fmt="%d m", fontsize=7)
    m = results[name].get_max_concentration("ANNUAL")
    ax.plot(0, 0, "^", ms=10, mfc="white", mec="black", label="Stack (145 m)")
    ax.plot((m["x"] - STACK_X) / 1000, (m["y"] - STACK_Y) / 1000, "*", ms=15, mfc="cyan", mec="black",
            label=f"Max {m['value']:.2f} µg/m³")
    ax.set_title(f"TERRAIN {name}")
    ax.set_xlabel("Easting from stack (km)")
    ax.set_aspect("equal")
    ax.legend(loc="lower left", fontsize=8)
axes[0].set_ylabel("Northing from stack (km)")
cb = fig.colorbar(cs, ax=axes, orientation="horizontal", shrink=0.7, format="%.2f",
                  label="Annual average SO₂ (µg/m³)")
cb.set_ticks(levels[::2])
fig.suptitle("Annual SO₂ from a 145 m stack, flat vs AERMAP terrain (100 m contours), LOVETT 1988 met")
fig.savefig(WORK / "08_complex_terrain.png", dpi=130)
print("Figure:", WORK / "08_complex_terrain.png")
