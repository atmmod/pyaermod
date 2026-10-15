"""
Air-toxics screening with a unit emission rate (chi/Q) and GIS export.

Runs one stack at 1 g/s, so every concentration AERMOD reports is a dispersion
factor chi/Q in (ug/m3)/(g/s). Scales the annual and 1-hour fields to several toxics'
emission rates, compares the maxima with illustrative screening levels, and exports
the fields as GeoTIFF, GeoJSON and KMZ (UTM zone 18N, near LOVETT's New York site).
"""

import os
from pathlib import Path

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "10_unit_emission_air_toxics"
WORK.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from pyaermod import (  # noqa: E402
    AERMODProject,
    CartesianGrid,
    ContourGenerator,
    ContourPolygon,
    ControlPathway,
    CoordinateTransformer,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
    Validator,
    export_concentration_geotiff,
    export_concentration_shapefile,
    latlon_to_utm,
    parse_aermod_output,
    read_plotfile,
    run_aermod,
    to_kmz,
)

# Emission rates (g/s) and screening levels (ug/m3) -- ILLUSTRATIVE numbers only;
# substitute your agency's annual and short-term guideline concentrations.
TOXICS = {  # name: (rate g/s, annual level, 1-hr level)
    "Benzene": (0.40, 0.15, 30.0),
    "Formaldehyde": (0.10, 0.10, 50.0),
    "Toluene": (2.0, 5000.0, 30000.0),
    "Hydrogen chloride": (0.50, 20.0, 2000.0),
    "Nickel": (0.002, 0.005, 0.2),
}

# --- Site: place the stack by lat/lon and model in UTM 18N metres
x0, y0, zone, hemi = latlon_to_utm(41.256, -73.986)
x0, y0 = round(x0), round(y0)
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK", x_coord=x0, y_coord=y0,
    stack_height=30.0, stack_temp=400.0,      # m, K
    exit_velocity=12.0, stack_diameter=1.0,   # m/s, m
    emission_rate=1.0,                        # unit rate: output is chi/Q
))
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    x0 - 2000, x0 + 2000, y0 - 2000, y0 + 2000, spacing=100))
project = AERMODProject(
    control=ControlPathway(
        title_one="Use case 10: unit-emission chi/Q for air toxics",
        pollutant_id="OTHER", averaging_periods=["1", "ANNUAL"],
        terrain_type="ELEVATED",   # all elevations 0 m; run AERMAP for real terrain
    ),
    sources=sources, receptors=receptors,
    meteorology=MeteorologyPathway(
        surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
        profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
        surface_station_id=14735, upper_air_station_id=14735,
        data_start_year=1988, profile_base_elevation=1.8,
    ),
    # PLOTFILEs chiq_01H.plt / chiq_ANNUAL.plt hold the value at every receptor
    output=OutputPathway(receptor_table_rank=1, max_table_rank=1, period_plot_files="chiq"),
)

# --- Validate, write, run, parse
check = Validator.validate(project, check_files=True)
print(check)
if not check.is_valid:
    raise SystemExit(1)
project.write(WORK / "unit.inp")
run = run_aermod(WORK / "unit.inp", timeout=1800)
if not run.success:
    raise SystemExit(f"AERMOD failed: {run.error_message}")

# chi/Q in (ug/m3)/(g/s) at every receptor; the 1-hr file is each receptor's highest
grids = {}
for period in ("ANNUAL", "01H"):
    pf = read_plotfile(WORK / f"chiq_{period}.plt")
    grids[period] = pf.to_dataframe().rename(
        columns={"X": "x", "Y": "y", pf.concentration_column: "concentration"})
annual, hour1 = grids["ANNUAL"], grids["01H"]
summary = parse_aermod_output(run.output_file)  # AERMOD's own maxima, as a cross-check
for period, df in (("ANNUAL", annual), ("1HR", hour1)):
    m = summary.get_max_concentration(period)
    print(f"Max {period} chi/Q {df.concentration.max():.4g} (ug/m3)/(g/s) at "
          f"({m['x']:.0f}, {m['y']:.0f}); AERMOD summary {m['value']:.4g}")

# --- Scale chi/Q by each emission rate and compare with the screening levels
rows = []
for name, (rate, ann_lvl, hr_lvl) in TOXICS.items():
    annual[name] = annual.concentration * rate
    ann_max, hr_max = annual[name].max(), hour1.concentration.max() * rate
    rows.append((name, ann_max / ann_lvl, hr_max / hr_lvl))
    print(f"{name:18s} annual max {ann_max:9.4g} ug/m3 ({ann_max / ann_lvl:.2g} x level)"
          f"   1-hr max {hr_max:9.4g} ug/m3 ({hr_max / hr_lvl:.2g} x level)")

# --- GIS export (UTM 18N): rasters of chi/Q, scaled points, Google Earth contours
files = [
    export_concentration_geotiff(annual, WORK / "chiq_annual.tif", utm_zone=zone),
    export_concentration_geotiff(hour1, WORK / "chiq_1hr.tif", utm_zone=zone),
    export_concentration_shapefile(annual, WORK / "toxics_annual.geojson", utm_zone=zone,
                                   as_contours=False, driver="GeoJSON"),
]
levels = [0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]  # chi/Q contours
cmap = plt.get_cmap("YlOrRd", len(levels))
top = annual.concentration.max()
polys = ContourGenerator(CoordinateTransformer(zone, hemi)).generate_contours_latlon(
    annual, levels=[v for v in levels if v < top] + [top])
contours = [ContourPolygon(r.level_min, list(p.exterior.coords), f">= {r.level_min:g}")
            for r in polys.itertuples()
            for p in getattr(r.geometry, "geoms", [r.geometry])]
# One KML colour (aabbggrr) per contour level, lowest first, as on the map
kml = ["b0" + "".join(f"{round(255 * c):02x}" for c in cmap(levels.index(lv))[2::-1])
       for lv in sorted({c.level for c in contours})]
files.append(to_kmz(WORK / "chiq_annual.kmz", sources=sources.sources, contours=contours,
                    utm_zone=zone, palette=kml, title="Annual chi/Q, (ug/m3)/(g/s)"))
print("GIS files:", ", ".join(f.name for f in files))

# --- Figure: annual chi/Q map + scaled maxima relative to the screening levels
fig, (ax, bx) = plt.subplots(1, 2, figsize=(9, 6.5), gridspec_kw={"width_ratios": [1.3, 1]})
xs, ys = np.sort(annual.x.unique()), np.sort(annual.y.unique())
grid = annual.pivot(index="y", columns="x", values="concentration").loc[ys, xs]
cf = ax.contourf(xs / 1000, ys / 1000, grid, levels=levels, cmap=cmap, extend="both")
best = annual.loc[annual.concentration.idxmax()]
ax.plot(best.x / 1000, best.y / 1000, "*", color="w", ms=13, mec="k",
        label=f"max {best.concentration:.2f} (µg/m³)/(g/s)")
ax.plot(x0 / 1000, y0 / 1000, "k^", ms=9, label="STACK (1 g/s)")
ax.set(aspect="equal", xlabel="UTM 18N easting (km)", ylabel="UTM 18N northing (km)",
       title="Annual-average χ/Q")
ax.ticklabel_format(useOffset=False)
ax.legend(loc="lower left", fontsize=8)
fig.colorbar(cf, ax=ax, orientation="horizontal", pad=0.12,
             label="Annual χ/Q ((µg/m³)/(g/s))")

names = [r[0] for r in rows]
pos = np.arange(len(rows))
bx.barh(pos - 0.2, [r[1] for r in rows], 0.4, color="#fdae61", label="annual max / level")
bx.barh(pos + 0.2, [r[2] for r in rows], 0.4, color="#d7191c", label="1-hr max / level")
bx.axvline(1.0, color="k", ls="--", lw=1.2, label="screening level")
bx.set_yticks(pos, names)
bx.invert_yaxis()
bx.set_xscale("log")
for k, r in enumerate(rows):
    for dy, v in ((-0.2, r[1]), (0.2, r[2])):
        bx.text(v * 1.15, k + dy, f"{v:.2g}", va="center", fontsize=7)
bx.set_xlim(right=10)
bx.set(xlabel="Scaled max ÷ illustrative screening level (–)")
bx.legend(fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
fig.suptitle("Unit-emission (1 g/s) dispersion factor and scaled air-toxics maxima, "
             "LOVETT 1988 met", fontsize=11)
fig.tight_layout()
fig.savefig(WORK / "10_unit_emission_air_toxics.png", dpi=130)
print(f"Figure: {WORK / '10_unit_emission_air_toxics.png'}")
