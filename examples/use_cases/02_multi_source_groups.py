"""
Facility with several stacks: source groups and a polar grid.

Two boiler stacks and two process vents, grouped with SRCGROUP into BOILERS,
PROCESS and ALL, modelled on a polar receptor grid centred on the facility.
Maps each group's annual PM10 and compares the groups' maxima.
"""

import os
from pathlib import Path

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "02_multi_source_groups"
WORK.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

from pyaermod import (  # noqa: E402
    AERMODProject,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    Validator,
    read_plotfile,
    run_aermod,
)

control = ControlPathway(
    title_one="Use case 2: facility with source groups",
    pollutant_id=PollutantType.PM10,
    averaging_periods=["ANNUAL"],
    terrain_type=TerrainType.FLAT,
    regulatory_default=False,   # FLAT needs non-DFAULT (see use case 1)
)

# Four stacks around a facility centred on (0, 0):
# (id, x m, y m, height m, exit temp K, exit velocity m/s, diameter m, PM10 g/s)
STACKS = [
    ("BOIL1", -60.0, 40.0, 45.0, 450.0, 15.0, 2.0, 1.2),
    ("BOIL2", -20.0, 40.0, 45.0, 450.0, 15.0, 2.0, 1.2),
    ("DRYER", 50.0, -30.0, 18.0, 340.0, 10.0, 1.0, 0.5),
    ("KILN", 80.0, 10.0, 25.0, 380.0, 12.0, 1.2, 0.8),
]
sources = SourcePathway()
for sid, x, y, h, t, v, d, q in STACKS:
    sources.add_source(PointSource(source_id=sid, x_coord=x, y_coord=y, stack_height=h,
                                   stack_temp=t, exit_velocity=v, stack_diameter=d,
                                   emission_rate=q))

# Source groups (SRCGROUP). AERMOD reports every result per group; ALL (every
# source) is written automatically, so only the subsets are defined here.
GROUPS = {"BOILERS": ["BOIL1", "BOIL2"], "PROCESS": ["DRYER", "KILN"]}
for name, members in GROUPS.items():
    sources.add_group(SourceGroupDefinition(name, members))

# Polar grid: 36 radials every 10 deg, 20 rings from 100 m to 3 km.
receptors = ReceptorPathway()
receptors.add_polar_grid(PolarGrid(
    grid_name="FENCE", x_origin=0.0, y_origin=0.0,
    dist_init=100.0, dist_num=20, dist_delta=150.0,
    dir_init=10.0, dir_num=36, dir_delta=10.0,
))

meteorology = MeteorologyPathway(
    surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
    profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
    surface_station_id=14735, upper_air_station_id=14735,
    data_start_year=1988, profile_base_elevation=1.8,   # m MSL
)

# One annual PLOTFILE per group: (averaging period, group, file name).
group_names = [*GROUPS, "ALL"]
output = OutputPathway(
    receptor_table=True, receptor_table_rank=2, max_table=True,
    plot_file_groups=[("ANNUAL", g, f"{g.lower()}_annual.plt") for g in group_names],
)

project = AERMODProject(control=control, sources=sources, receptors=receptors,
                        meteorology=meteorology, output=output)
check = Validator.validate(project, check_files=True)
print(check)
if not check.is_valid:
    raise SystemExit(1)

result = run_aermod(project.write(WORK / "02_multi_source_groups.inp"))
if not result.success:
    raise SystemExit(f"AERMOD failed: {result.error_message}")
print(f"AERMOD finished in {result.runtime_seconds:.1f} s")

# Read each group's annual concentration at every polar receptor.
frames = {}
for g in group_names:
    plot = read_plotfile(WORK / f"{g.lower()}_annual.plt")
    df = plot.to_dataframe()
    frames[g] = df.assign(CONC=df[plot.concentration_column])
    peak = frames[g].loc[frames[g]["CONC"].idxmax()]
    print(f"{g:8s} annual max {peak['CONC']:.3f} ug/m3 at "
          f"({peak['X']:.0f}, {peak['Y']:.0f}) m")

# Each group's share at the receptor where ALL peaks (the groups add up to ALL).
top = frames["ALL"].loc[frames["ALL"]["CONC"].idxmax(), ["X", "Y"]]
for g in GROUPS:
    at = frames[g].set_index(["X", "Y"]).loc[tuple(top), "CONC"]
    print(f"  {g} at the ALL maximum: {at:.3f} ug/m3")

# Three maps on one logarithmic colour scale (so the small BOILERS share still
# shows), with the polar receptors as dots, and a bar chart of the maxima.
fig, axd = plt.subplot_mosaic([group_names, ["bar"] * 3], figsize=(9, 6.5),
                              height_ratios=[1.8, 1], constrained_layout=True)
vmax = max(f["CONC"].max() for f in frames.values())
levels = np.geomspace(vmax / 100, vmax, 11)
colors = {"BOILERS": "#d55e00", "PROCESS": "#0072b2", "ALL": "0.35"}
for g in group_names:
    ax, df = axd[g], frames[g]
    cs = ax.tricontourf(df["X"], df["Y"], df["CONC"], levels=levels, cmap="viridis",
                        norm=LogNorm(), extend="min")
    ax.plot(df["X"], df["Y"], ".", ms=1, color="white", alpha=0.5)
    for sid, x, y, *_ in STACKS:
        group = next(n for n, m in GROUPS.items() if sid in m)
        ax.plot(x, y, "^", ms=6, mec="black",
                mfc=colors[group] if g in (group, "ALL") else "white")
    ax.set(title=f"{g}: annual PM$_{{10}}$", xlim=(-1200, 1200), ylim=(-1200, 1200),
           xlabel="Easting (m)", aspect="equal")
axd[group_names[0]].set_ylabel("Northing (m)")
fig.colorbar(cs, ax=[axd[g] for g in group_names], format="%.2g", shrink=0.9,
             label="Annual PM$_{10}$ (µg/m³)")

bar = axd["bar"]
maxima = [frames[g]["CONC"].max() for g in group_names]
bar.barh(group_names, maxima, color=[colors[g] for g in group_names])
bar.bar_label(bar.containers[0], fmt=" %.3f µg/m³")
bar.set(title="Highest annual PM$_{10}$ at any receptor, by source group",
        xlabel="Concentration (µg/m³)", xlim=(0, 1.25 * vmax))
bar.invert_yaxis()
fig.suptitle("Source-group contributions: 4 stacks, polar receptor grid, LOVETT 1988 met")
fig.savefig(WORK / "02_multi_source_groups.png", dpi=130)
print(f"Figure: {WORK / '02_multi_source_groups.png'}")
