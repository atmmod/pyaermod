"""Fugitive PM10 emissions: area, polygon and volume sources.

An aggregate yard with an irregular storage pile (AREAPOLY), a rotated
laydown pad (AREA) and an unpaved haul road modelled as a string of VOLUME
sources (EPA 2012 haul-road guidance).
The script maps the highest 24-hour PM10 concentration with the footprints drawn.
"""

import os
from itertools import pairwise
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Polygon

from pyaermod import (
    AERMODProject,
    AreaPolySource,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    Validator,
    VolumeSource,
    parse_aermod_output,
    read_plotfile,
    run_aermod,
)
from pyaermod.footprints import source_footprint

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "04_fugitive_sources"
WORK.mkdir(parents=True, exist_ok=True)

sources = SourcePathway()

# Irregular storage pile: AREAPOLY rates are per unit area (g/s/m^2)
pile_xy = [(-40, -20), (10, -35), (45, -5), (35, 30), (-10, 40), (-45, 15)]
x, y = np.array(pile_xy, dtype=float).T
pile_area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))  # m^2
sources.add_source(AreaPolySource(
    source_id="PILE", vertices=pile_xy,
    release_height=4.0,                    # m, about half the pile height
    emission_rate=0.08 / pile_area,        # 0.08 g/s wind erosion + handling
))
# Laydown pad, 60 m x 30 m, rotated 20 deg clockwise about its SW corner: AREA
sources.add_source(AreaSource(
    source_id="PAD", x_coord=-170.0, y_coord=50.0,
    initial_lateral_dimension=60.0, initial_vertical_dimension=30.0, angle=20.0,
    release_height=1.0, emission_rate=0.02 / (60.0 * 30.0),       # 0.02 g/s
))

# Unpaved haul road as adjacent VOLUME sources (EPA 2012 haul road guidance):
# 4 m trucks -> plume top 1.7*4 = 6.8 m; release height 3.4 m, sigma-z0 = 6.8/2.15;
# 8 m road + 6 m -> 14 m plume width = volume spacing, sigma-y0 = 14/2.15.
ROAD = [(-330.0, -230.0), (-120.0, -80.0), (60.0, -80.0)]   # gate -> pile, m
WIDTH, ROAD_TOTAL = 14.0, 0.25            # m; g/s for the whole road (watered)
centres = []
for (x0, y0), (x1, y1) in pairwise(ROAD):
    n = int(np.hypot(x1 - x0, y1 - y0) // WIDTH)
    centres += [(x0 + (i + 0.5) / n * (x1 - x0), y0 + (i + 0.5) / n * (y1 - y0)) for i in range(n)]
for i, (vx, vy) in enumerate(centres, start=1):
    sources.add_source(VolumeSource(
        source_id=f"RD{i:03d}", x_coord=vx, y_coord=vy,
        release_height=3.4, initial_lateral_dimension=WIDTH / 2.15,
        initial_vertical_dimension=6.8 / 2.15, emission_rate=ROAD_TOTAL / len(centres),
    ))
print(f"Pile area {pile_area:.0f} m^2; haul road = {len(centres)} volume sources")

receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(-450, 300, -330, 300, spacing=30))

project = AERMODProject(
    control=ControlPathway(title_one="Use case 04: fugitive PM10", pollutant_id=PollutantType.PM10,
                           averaging_periods=["24"],
                           terrain_type="ELEV"),  # flat ground: all elevations 0 m
    sources=sources,
    receptors=receptors,
    meteorology=MeteorologyPathway(
        surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
        profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
        surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
        profile_base_elevation=1.8,   # m, as in EPA's LOVETT test deck
    ),
    # PLOTFILE ranks need a RECTABLE at least that deep; SECOND gives H2H too
    output=OutputPathway(receptor_table=True, receptor_table_rank=2,
                         plot_file="pm10_24hr.plt", plot_file_averaging="24"),
)

check = Validator.validate(project)
if not check.is_valid:
    raise SystemExit(str(check))
project.write(WORK / "fugitive.inp")
run = run_aermod(WORK / "fugitive.inp")
if not run.success:
    raise SystemExit(f"AERMOD failed: {run.error_message}")

results = parse_aermod_output(run.output_file)
table = results.concentrations["24HR"].data
print("AERMOD version:", results.run_info.version)
for _, row in table.sort_values("rank").groupby("rank").head(1).iterrows():
    print(f"24-hr PM10 rank {int(row['rank'])}: {row['concentration']:.1f} ug/m^3 "
          f"at ({row['x']:.0f}, {row['y']:.0f})")

# Every receptor's highest 24-hr value comes from the PLOTFILE
plotfile = read_plotfile(WORK / "pm10_24hr.plt")
df = plotfile.to_dataframe().rename(columns={plotfile.concentration_column: "conc"})

# --- Figure: H1H 24-hr PM10 with source footprints ---------------------------
levels = [0, 25, 50, 75, 100, 150, 200, 250, 300, 400]  # ug/m^3
fig, ax = plt.subplots(figsize=(9, 6.5), constrained_layout=True)
cf = ax.tricontourf(df["X"], df["Y"], df["conc"], levels=levels, cmap="YlOrRd",
                    norm=BoundaryNorm(levels, 256), extend="max")
# 150 ug/m^3 is the 24-hr PM10 NAAQS level (its form is the H2H per year, so H1H is conservative)
naaqs = ax.tricontour(df["X"], df["Y"], df["conc"], levels=[150], colors="black", linestyles="--")
ax.clabel(naaqs, fmt="150 \u00b5g/m\u00b3", fontsize=8)
for src in sources.sources:
    if isinstance(src, VolumeSource):
        continue
    ring = source_footprint(src).parts[0]
    ax.add_patch(Polygon(ring, closed=True, fill=False, ec="black", lw=1.4))
    ax.annotate(src.source_id, ring[0], xytext=(-4, 4), textcoords="offset points",
                ha="right", fontsize=9, fontweight="bold")
cx, cy = zip(*centres)
ax.plot(cx, cy, "s", ms=4, mfc="none", mec="black", mew=0.8,
        label=f"Haul road ({len(centres)} VOLUME sources)")
i = df["conc"].idxmax()
ax.plot(df.at[i, "X"], df.at[i, "Y"], "x", color="navy", ms=10, mew=2.5,
        label=f"Maximum {df['conc'].max():.0f} µg/m³")
ax.set(xlim=(-450, 300), ylim=(-330, 300), aspect="equal",
       xlabel="Easting from site origin (m)", ylabel="Northing from site origin (m)",
       title="PM10 24-hr average, 1st-highest (H1H), LOVETT 1988 met")
ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
fig.colorbar(cf, ax=ax, shrink=0.8, ticks=levels, label="Highest 24-hr PM10 (µg/m³)")
fig.savefig(WORK / "04_fugitive_sources.png", dpi=130)
print("Figure:", WORK / "04_fugitive_sources.png")
