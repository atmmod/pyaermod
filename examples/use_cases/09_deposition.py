"""Particle dry and wet deposition from a point source.

A 30 m stack emits PM in three size classes (PARTDIAM / MASSFRAX / PARTDENS, AERMOD's
Method 1); AERMOD calculates concentration plus dry (DDEP) and wet (WDEP) deposition for
a year. Uses EPA's HOUSTON_ADJU met (1996): LOVETT.SFC has no precipitation (every hour
is missing), and wet deposition needs it. Writes 09_deposition.png: annual dry vs wet maps.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from pyaermod import (
    AERMODProject,
    AERMODRunner,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    Validator,
    parse_aermod_output,
    read_plotfile,
)

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds HOUSTON_ADJU.SFC / .PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "09_deposition"
WORK.mkdir(parents=True, exist_ok=True)

Q = 2.0   # g/s of PM, all three size classes together

# 1. Source with Method 1 particle deposition inputs (one entry per size class).
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="KILN", x_coord=0.0, y_coord=0.0,
    stack_height=30.0,     # m
    stack_temp=350.0,      # K
    exit_velocity=10.0,    # m/s
    stack_diameter=1.5,    # m
    emission_rate=Q,
    particle_deposition=ParticleDepositionParams(
        diameters=[1.0, 5.0, 15.0],          # µm
        mass_fractions=[0.30, 0.45, 0.25],   # must sum to 1
        densities=[2.0, 2.0, 2.0],           # g/cm3
    ),
))

# 2. CONC + DDEP + WDEP. Method 1 particle deposition is allowed under DFAULT, and
#    DFAULT means elevated terrain, so the flat site is ELEV with every height 0.
#    Dry and wet plume depletion are on by default once a source has deposition inputs.
control = ControlPathway(
    title_one="Particle dry and wet deposition from a 30 m stack",
    pollutant_id=PollutantType.PM10,
    averaging_periods=["ANNUAL"],
    terrain_type=TerrainType.ELEVATED,
    calculate_concentration=True,      # CONC, ug/m3
    calculate_dry_deposition=True,     # DDEP, g/m2 over the period
    calculate_wet_deposition=True,     # WDEP, g/m2 over the period
)
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(-2500, 2500, -2500, 2500, spacing=100.0))
met = MeteorologyPathway(
    surface_file=str((MET_DIR / "HOUSTON_ADJU.SFC").resolve()),
    profile_file=str((MET_DIR / "HOUSTON_ADJU.PFL").resolve()),
    surface_station_id=722430, upper_air_station_id=3937, data_start_year=1996,
    profile_base_elevation=0.0,   # m MSL, as in EPA's testprt2.inp
)
# The ANNUAL plot file holds one column per quantity: CONC, DRY DEPO, WET DEPO.
output = OutputPathway(plot_file="dep_annual.plt", plot_file_averaging="ANNUAL")
project = AERMODProject(control, sources, receptors, met, output)

# 3. Validate, write, run, parse.
check = Validator.validate(project)
print(check)
if not check.is_valid:
    raise SystemExit(1)
inp = project.write(WORK / "deposition.inp")
run = AERMODRunner().run(inp, working_dir=WORK)
if not run.success:
    raise SystemExit(f"AERMOD failed: {run.error_message}")
results = parse_aermod_output(run.output_file)
print(f"AERMOD {results.run_info.version}: {run.output_file}")

plot = read_plotfile(WORK / "dep_annual.plt").to_dataframe().sort_values(["Y", "X"])
print("Plot file columns:", list(plot.columns[:5]))
conc = results.concentrations["ANNUAL"]
print(f"Annual concentration max {conc.max_value:.3f} {conc.units} at ({conc.max_location[0]:.0f}, "
      f"{conc.max_location[1]:.0f}) m")
emitted = Q * 8784 * 3600   # g over the 1996 met year (8784 hours)
cell = 100.0 * 100.0        # m2 per receptor
for kind, column in (("DDEP", "DRY_DEPO"), ("WDEP", "WET_DEPO")):
    table = results.deposition[kind]["ANNUAL"]
    within = plot[column].sum() * cell
    x, y = table.max_location
    print(f"{kind} max {table.max_value:.4f} {table.units} at ({x:.0f}, {y:.0f}) m; "
          f"{within / 1000:.0f} kg in the 5 km x 5 km grid = {100 * within / emitted:.1f}% of the emissions")

# 4. Figure: annual dry and wet deposition on one log scale.
xs, ys = np.unique(plot["X"]), np.unique(plot["Y"])
X, Y = np.meshgrid(xs / 1000, ys / 1000)   # km
vmax = plot[["DRY_DEPO", "WET_DEPO"]].to_numpy().max()
levels = np.geomspace(vmax / 1000, vmax, 13)

fig, axes = plt.subplots(1, 2, figsize=(9, 6.5), sharey=True, constrained_layout=True)
for ax, (column, label) in zip(axes, (("DRY_DEPO", "Dry (DDEP)"), ("WET_DEPO", "Wet (WDEP)"))):
    dep = plot[column].to_numpy().reshape(len(ys), len(xs))
    cs = ax.contourf(X, Y, np.clip(dep, levels[0] / 10, None), levels=levels,
                     norm=LogNorm(levels[0], vmax), cmap="viridis", extend="min")
    ax.plot(0, 0, "^", ms=10, mfc="white", mec="black", label="Stack (30 m)")
    ax.set_title(f"{label}: max {dep.max():.3f} g/m²/yr")
    ax.set_xlabel("Easting (km)")
    ax.set_aspect("equal")
    ax.legend(loc="lower left", fontsize=8)
axes[0].set_ylabel("Northing (km)")
cb = fig.colorbar(cs, ax=axes, orientation="horizontal", shrink=0.7, format="%g",
                  label="Annual deposition (g/m²/yr)")
cb.set_ticks([t for t in (0.003, 0.01, 0.03, 0.1, 0.3, 1, 3) if levels[0] <= t <= vmax])
fig.suptitle(f"PM deposition, {Q:g} g/s from a 30 m stack (1, 5, 15 µm), HOUSTON 1996 met")
fig.savefig(WORK / "09_deposition.png", dpi=130)
print("Figure:", WORK / "09_deposition.png")
