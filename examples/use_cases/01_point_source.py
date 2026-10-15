"""
Single stack, flat terrain: annual and 24-hour PM2.5.

One 40 m boiler stack on flat ground, a 4 km x 4 km Cartesian receptor grid and
a year of meteorology (EPA's LOVETT 1988 test data). Writes the AERMOD deck,
runs it, and maps the annual average and the highest 24-hour average.
"""

import os
from pathlib import Path

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "01_point_source"
WORK.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt  # noqa: E402

from pyaermod import (  # noqa: E402
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    Validator,
    parse_aermod_output,
    read_plotfile,
    run_aermod,
)

# CO pathway: job title, pollutant and averaging periods. PM25 makes AERMOD
# average each 24-hour rank over the years of met data (the NAAQS form).
# MODELOPT FLAT only takes effect without DFAULT: under DFAULT AERMOD overrides
# it with ELEV (warning W206), so this flat-terrain run is non-regulatory.
control = ControlPathway(
    title_one="Use case 1: single stack, flat terrain",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type=TerrainType.FLAT,
    regulatory_default=False,
)

# SO pathway: one point source. Units are AERMOD's: m, K, m/s, g/s.
sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1",
    x_coord=0.0, y_coord=0.0,   # m (local UTM-style coordinates)
    stack_height=40.0,          # m above ground
    stack_temp=420.0,           # K exit temperature
    exit_velocity=12.0,         # m/s
    stack_diameter=1.5,         # m
    emission_rate=2.0,          # g/s of primary PM2.5
))

# RE pathway: a 100 m Cartesian grid, 2 km out from the stack in every direction.
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    x_min=-2000.0, x_max=2000.0, y_min=-2000.0, y_max=2000.0, spacing=100.0,
))

# ME pathway: the AERMET surface and profile files plus the station IDs and
# year from their headers, and the profile base elevation (m MSL).
meteorology = MeteorologyPathway(
    surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
    profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
    surface_station_id=14735,
    upper_air_station_id=14735,
    data_start_year=1988,
    profile_base_elevation=1.8,
)

# OU pathway: the summary tables in the .out file, plus one PLOTFILE per
# averaging period (the value at every receptor), which is what the maps need.
output = OutputPathway(
    receptor_table=True, receptor_table_rank=8,
    max_table=True, max_table_rank=10,
    period_plot_files="pm25",
)

project = AERMODProject(control=control, sources=sources, receptors=receptors,
                        meteorology=meteorology, output=output)

# Validate before writing; warnings are allowed, errors stop here.
check = Validator.validate(project, check_files=True)
print(check)
if not check.is_valid:
    raise SystemExit(1)

inp = project.write(WORK / "01_point_source.inp")
result = run_aermod(inp)
if not result.success:
    raise SystemExit(f"AERMOD failed: {result.error_message}")
print(f"AERMOD finished in {result.runtime_seconds:.1f} s "
      f"({result.warning_count} warnings)")

# The .out file's summary tables: one per averaging period and rank. For
# PM2.5 the 24-hour NAAQS design value uses the 8th-highest (98th percentile).
results = parse_aermod_output(result.output_file)
h8h = next(t for t in results.summaries if "8TH-HIGHEST 24-HR" in t.title).max_row
print(f"24-hour H8H: max {h8h['concentration']:.3f} ug/m3 at "
      f"({h8h['x']:.0f}, {h8h['y']:.0f}) m")

# The plot files hold the annual average and the highest 24-hour average at
# every receptor. (The .out summary tables list only the top ten receptors,
# too few to contour, so the maps are drawn from the plot files.)
plot_names = output.period_plot_file_names(control.averaging_periods)
panels = [("ANNUAL", "Annual average"), ("24", "Highest 24-hour average (H1H)")]

fig, axes = plt.subplots(1, 2, figsize=(9, 5.4), constrained_layout=True)
for ax, (period, label) in zip(axes, panels):
    plot = read_plotfile(WORK / plot_names[period])
    df = plot.to_dataframe()
    conc = df[plot.concentration_column]
    peak = df.loc[conc.idxmax()]
    print(f"{label}: max {conc.max():.3f} ug/m3 at "
          f"({peak['X']:.0f}, {peak['Y']:.0f}) m")
    cs = ax.tricontourf(df["X"], df["Y"], conc, levels=12, cmap="viridis")
    ax.plot(0, 0, "^", ms=10, mfc="white", mec="black", label="STACK1")
    ax.plot(peak["X"], peak["Y"], "*", ms=14, mfc="red", mec="black", label="Maximum")
    ax.set(title=label, xlabel="Easting (m)", ylabel="Northing (m)", aspect="equal")
    ax.legend(loc="lower right", fontsize=8)
    fig.colorbar(cs, ax=ax, orientation="horizontal", label="Concentration (µg/m³)")

fig.suptitle("PM$_{2.5}$ from one 40 m stack (2 g/s), flat terrain, LOVETT 1988 met")
fig.savefig(WORK / "01_point_source.png", dpi=130)
print(f"Figure: {WORK / '01_point_source.png'}")
