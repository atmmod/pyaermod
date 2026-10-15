"""Near-road PM2.5 from a six-lane highway with AERMOD's RLINE source.

A 1 km highway segment is modelled as one RLINE source with an emission rate
computed from traffic volume and a per-vehicle emission factor. The script maps
the annual-average PM2.5 within 300 m of the road and plots its fall-off with
distance along a transect perpendicular to the road.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt

from pyaermod.aermod_outputs import read_plotfile
from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
       MeteorologyPathway,
    OutputPathway,
    PollutantType,
    ReceptorPathway,
    RLineSource,
    SourcePathway,
    TerrainType,
)
from pyaermod.output_parser import parse_aermod_output
from pyaermod.runner import run_aermod
from pyaermod.validator import Validator

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "05_roadway"
WORK.mkdir(parents=True, exist_ok=True)

# Traffic -> RLINE emission rate. RLINE's SRCPARAM rate is per unit AREA of
# road surface, g/(s·m²): AERMOD multiplies it by the road width.
AADT = 100_000          # vehicles/day, both directions
EF_PM25 = 0.010         # g/(vehicle·km), exhaust + brake + tyre wear (illustrative; use MOVES)
ROAD_WIDTH = 24.0       # m, six 3.6 m lanes plus shoulders
per_metre = AADT / 86400 * EF_PM25 / 1000      # g/(s·m) of road length
EMIS = per_metre / ROAD_WIDTH                  # g/(s·m²)

control = ControlPathway(
    title_one="Use case 05: near-road PM2.5 from a highway (RLINE)",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL"],
    terrain_type=TerrainType.ELEVATED,   # DFAULT ignores FLAT (W206); all elevations are 0 m
)

sources = SourcePathway()
sources.add_source(RLineSource(
    source_id="HWY",
    x_start=-500.0, y_start=0.0, x_end=500.0, y_end=0.0,   # 1 km, west to east
    release_height=0.5,                    # m, tailpipe height
    initial_lateral_dimension=ROAD_WIDTH,  # m, full road width (AERMOD's "Width")
    initial_vertical_dimension=1.5,        # m, initial sigma-z from vehicle wakes
    emission_rate=EMIS,                    # g/(s·m²)
))

# Receptors on lines across the road, packed close to it where the gradient is
# steep. RLINE costs far more per receptor than a point source (run time grows
# with receptors x road length x hours), so keep this network lean.
DISTANCES = [15, 20, 30, 40, 50, 75, 100, 150, 200, 300]   # m from centreline
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid(
    grid_name="ROADNET",
    x_points=[-400.0 + 100.0 * i for i in range(9)],
    y_points=sorted([-d for d in DISTANCES] + DISTANCES),
))

meteorology = MeteorologyPathway(
    surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
    profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
    surface_station_id=14735, upper_air_station_id=14735,
    data_start_year=1988, profile_base_elevation=1.8,
)
output = OutputPathway(receptor_table=False, max_table=True, period_plot_files="hwy")

project = AERMODProject(control=control, sources=sources, receptors=receptors,
                        meteorology=meteorology, output=output)
check = Validator.validate(project)
assert check.is_valid, check.errors
inp = WORK / "hwy.inp"
project.write(inp)

run = run_aermod(inp)
assert run.success, run.error_message
res = parse_aermod_output(run.output_file)
top = res.get_max_concentration("ANNUAL")

grid = read_plotfile(WORK / "hwy_ANNUAL.plt").to_dataframe()
line = grid[grid["X"] == 0.0].sort_values("Y")   # the transect across mid-road

print(f"AERMOD {res.run_info.version}; RLINE emission {per_metre:.3e} g/(s·m) = {EMIS:.3e} g/(s·m²)")
print(f"Max annual PM2.5: {top['value']:.3f} ug/m3 at ({top['x']:.0f}, {top['y']:.0f}) m")
for d in (20, 50, 100, 300):
    north = line.loc[line["Y"] == d, "AVERAGE_CONC"].iloc[0]
    south = line.loc[line["Y"] == -d, "AVERAGE_CONC"].iloc[0]
    print(f"  {d:>3} m from centreline: north {north:.3f}, south {south:.3f} ug/m3")

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9, 6.5), gridspec_kw={"width_ratios": [1.6, 1]})
g = grid.pivot(index="Y", columns="X", values="AVERAGE_CONC")
levels = [0.25, 0.375, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 3.5, 4]   # finer where it falls off
cs = ax.contourf(g.columns, g.index, g.values, levels=levels, cmap="viridis", extend="both")
ax.plot(grid["X"], grid["Y"], "w.", ms=2, alpha=0.6)
fig.colorbar(cs, ax=ax, orientation="horizontal", pad=0.12, label="Annual PM₂.₅ (µg/m³)")
ax.axhspan(-ROAD_WIDTH / 2, ROAD_WIDTH / 2, color="0.6", alpha=0.85, label="Highway (RLINE)")
ax.plot(line["X"], line["Y"], "wo", ms=4, mec="k", label="Transect (right panel)")
ax.set_xlabel("x (m)")
ax.set_ylabel("y (m), distance from road centreline")
ax.set_aspect("equal")
ax.legend(loc="upper right", fontsize=8)

for sign, colour, label in ((1, "#1b9e77", "North side"), (-1, "#d95f02", "South side")):
    side = line[line["Y"] * sign > 0]
    ax2.plot(side["Y"].abs(), side["AVERAGE_CONC"], "o-", color=colour, label=label)
ax2.axvline(ROAD_WIDTH / 2, color="0.5", ls=":", label="Road edge")
ax2.set_xlabel("Distance from road centreline (m)")
ax2.set_ylabel("Annual PM₂.₅ (µg/m³)")
ax2.set_xlim(0, 310)
ax2.set_ylim(bottom=0)
ax2.grid(alpha=0.3)
ax2.legend(fontsize=8)
fig.suptitle(f"Annual-average PM₂.₅ near a highway (RLINE, AADT {AADT:,}) — LOVETT 1988 met",
             fontsize=11)
fig.tight_layout()

png = WORK / "05_roadway.png"
fig.savefig(png, dpi=130, bbox_inches="tight")
print(f"Figure: {png}")
