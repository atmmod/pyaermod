"""Building downwash with BPIP-PRIME.

A 30 m stack stands beside a 22 m warehouse, well below Good Engineering
Practice (GEP) height. pyaermod's BPIP module computes the 36 direction-specific
building dimensions; AERMOD is run with and without them and the maximum
1-hour concentrations are mapped side by side, with the building drawn.
"""

import copy
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pyaermod import (
    AERMODProject,
    Building,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
    Validator,
    parse_aermod_output,
    read_plotfile,
    run_aermod,
)
from pyaermod.prime import gep_from_building

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "03_building_downwash"
WORK.mkdir(parents=True, exist_ok=True)

# --- Building and stack (local coordinates, m) ------------------------------
warehouse = Building(
    building_id="WAREHSE",
    corners=[(-60.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-60.0, 20.0)],  # 80 m x 40 m
    height=22.0,                                                            # m
)
stack = PointSource(
    source_id="STACK1", x_coord=30.0, y_coord=0.0,  # 10 m east of the east wall
    stack_height=30.0,     # m, below GEP
    stack_temp=420.0,      # K
    exit_velocity=12.0,    # m/s
    stack_diameter=1.2,    # m
    emission_rate=1.0,     # g/s (unit emission rate)
)
print(f"GEP stack height: {gep_from_building(warehouse, stack.x_coord, stack.y_coord):.1f} m "
      f"(stack is {stack.stack_height:.0f} m)")

# Direction-specific BUILDHGT/BUILDWID/BUILDLEN/XBADJ/YBADJ from BPIP
downwashed = copy.deepcopy(stack)
downwashed.set_building_from_bpip(warehouse)
print("BUILDWID 90/180/270/360 deg:",
      [round(downwashed.building_width[i], 1) for i in (8, 17, 26, 35)])


def build_project(src, title, plot_file):
    sources = SourcePathway()
    sources.add_source(src)
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(-500, 500, -500, 500, spacing=20))
    return AERMODProject(
        control=ControlPathway(title_one=title, pollutant_id="OTHER",
                               averaging_periods=["1"],
                               terrain_type="ELEV"),  # flat ground: all elevations 0 m
        sources=sources,
        receptors=receptors,
        meteorology=MeteorologyPathway(
            surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
            profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
            surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
            profile_base_elevation=1.8,   # m, as in EPA's LOVETT test deck
        ),
        output=OutputPathway(receptor_table=True, receptor_table_rank=1,  # PLOTFILE FIRST needs RECTABLE
                             plot_file=plot_file, plot_file_averaging="1"),
    )


frames = {}
for label, src, name in [("No downwash", stack, "no_downwash"),
                         ("BPIP-PRIME downwash", downwashed, "downwash")]:
    project = build_project(src, f"Use case 03: {label}", f"{name}_1hr.plt")
    check = Validator.validate(project)
    if not check.is_valid:
        raise SystemExit(str(check))
    project.write(WORK / f"{name}.inp")
    run = run_aermod(WORK / f"{name}.inp")
    if not run.success:
        raise SystemExit(f"AERMOD failed for {name}: {run.error_message}")
    mx = parse_aermod_output(run.output_file).get_max_concentration("1HR")
    print(f"{label:>20}: 1-hr H1H max {mx['value']:7.2f} ug/m^3 at ({mx['x']:.0f}, {mx['y']:.0f})")
    # The .out holds only the summary tables; the PLOTFILE has every receptor
    plt_file = read_plotfile(WORK / f"{name}_1hr.plt")
    frames[label] = plt_file.to_dataframe().rename(columns={plt_file.concentration_column: "conc"})
print("AERMOD version:", parse_aermod_output(run.output_file).run_info.version)

# --- Figure: H1H 1-hr maps on one colour scale, building drawn ---------------
levels = np.arange(0, max(df["conc"].max() for df in frames.values()) + 10, 10)  # ug/m^3
fig, axes = plt.subplots(1, 2, figsize=(9, 5.8), sharey=True, constrained_layout=True)
for ax, (label, df) in zip(axes, frames.items()):
    cf = ax.tricontourf(df["X"], df["Y"], df["conc"], levels=levels, cmap="viridis")
    bx, by = zip(*[*warehouse.corners, warehouse.corners[0]])
    ax.fill(bx, by, facecolor="white", edgecolor="black", lw=1.2, alpha=0.85, label="Building (22 m)")
    ax.plot(stack.x_coord, stack.y_coord, "r^", ms=9, mec="black", label="Stack (30 m)")
    i = df["conc"].idxmax()
    ax.plot(df.at[i, "X"], df.at[i, "Y"], "wx", ms=10, mew=2.5, label="Maximum")
    ax.set_title(f"{label}\n1-hr H1H, max {df['conc'].max():.1f} \u00b5g/m\u00b3", fontsize=11)
    ax.set_xlabel("Easting from site origin (m)")
    ax.set_aspect("equal")
    ax.set_xlim(-300, 300)
    ax.set_ylim(-300, 300)
axes[0].set_ylabel("Northing from site origin (m)")
axes[1].legend(loc="lower right", fontsize=8, framealpha=0.9)
fig.colorbar(cf, ax=axes, orientation="horizontal", shrink=0.7,
             label="Highest (H1H) 1-hr concentration, \u00b5g/m\u00b3 per g/s emitted (LOVETT 1988 met)")
fig.savefig(WORK / "03_building_downwash.png", dpi=130)
print("Figure:", WORK / "03_building_downwash.png")
