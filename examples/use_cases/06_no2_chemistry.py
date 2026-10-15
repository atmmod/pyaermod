"""1-hour NO2 from one combustion stack with Tier 2 (ARM2) and Tier 3 (OLM, PVMRM) chemistry.

The same project is run three times, changing only the NO2 conversion method,
and the script prints the highest and 8th-highest daily-maximum 1-hour NO2 for
each, then maps the highest values side by side with a bar chart of both ranks.
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
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
)
from pyaermod.output_parser import parse_aermod_output
from pyaermod.pathways import ChemistryMethod, ChemistryOptions, OzoneData
from pyaermod.runner import run_aermod
from pyaermod.validator import Validator

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "06_no2_chemistry"
WORK.mkdir(parents=True, exist_ok=True)

OZONE_PPB = 40.0      # uniform background ozone for OLM / PVMRM
IN_STACK_RATIO = 0.1  # in-stack NO2/NOx ratio (NO2STACK), typical of a gas-fired boiler
NOX_GS = 40.0         # NOx emission rate, g/s (as NO2)
METHODS = ["ARM2", "OLM", "PVMRM"]


def build_project(method: str) -> AERMODProject:
    # ARM2 scales total NOx by an empirical ratio (0.5-0.9) and takes no ozone
    # or in-stack ratio; AERMOD rejects OZONEVAL/NO2STACK with it (E600).
    tier3 = method != "ARM2"
    chemistry = ChemistryOptions(
        method=ChemistryMethod[method],
        ozone_data=OzoneData(uniform_value=OZONE_PPB, uniform_units="PPB") if tier3 else None,
        default_no2_ratio=IN_STACK_RATIO,
    )
    control = ControlPathway(
        title_one=f"Use case 06: 1-hr NO2 with {method}",
        pollutant_id=PollutantType.NO2,
        averaging_periods=["1"],
        # DFAULT ignores FLAT (W206), so say ELEV; every elevation is 0 m.
        terrain_type=TerrainType.ELEVATED,
        chemistry=chemistry,
    )
    sources = SourcePathway()
    sources.add_source(PointSource(
        source_id="BOILER",
        x_coord=0.0, y_coord=0.0, base_elevation=0.0,
        stack_height=35.0,     # m
        stack_temp=450.0,      # K
        exit_velocity=15.0,    # m/s
        stack_diameter=2.0,    # m
        emission_rate=NOX_GS,  # g/s
    ))
    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(CartesianGrid.from_bounds(
        x_min=-2500, x_max=2500, y_min=-2500, y_max=2500, spacing=125))
    meteorology = MeteorologyPathway(
        surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
        profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
        surface_station_id=14735, upper_air_station_id=14735,
        data_start_year=1988, profile_base_elevation=1.8,
    )
    # RECTABLE 1-8 makes AERMOD tabulate the 1st..8th-highest daily maxima.
    output = OutputPathway(receptor_table=True, receptor_table_rank=8, max_table=True,
                           period_plot_files=f"no2_{method.lower()}")
    return AERMODProject(control=control, sources=sources, receptors=receptors,
                         meteorology=meteorology, output=output)


results, grids = {}, {}
for method in METHODS:
    project = build_project(method)
    check = Validator.validate(project)
    assert check.is_valid, check.errors
    inp = WORK / f"no2_{method.lower()}.inp"
    project.write(inp)
    run = run_aermod(inp)
    assert run.success, run.error_message
    res = parse_aermod_output(run.output_file)
    # For NO2 1-hr under DFAULT AERMOD ranks the daily-maximum 1-hr values.
    ranked = {s.title.split()[4]: s for s in res.summaries if s.averaging_period == "1HR"}
    results[method] = (ranked["1ST-HIGHEST"], ranked["8TH-HIGHEST"])
    grids[method] = read_plotfile(WORK / f"no2_{method.lower()}_01H.plt").to_dataframe()

print(f"AERMOD {res.run_info.version}, NOx {NOX_GS:g} g/s, O3 {OZONE_PPB:g} ppb, NO2/NOx in stack {IN_STACK_RATIO}")
print(f"{'method':<7}{'H1H (ug/m3)':>13}{'H8H (ug/m3)':>13}   at (x, y) m")
for method, (h1, h8) in results.items():
    print(f"{method:<7}{h1.max_value:>13.1f}{h8.max_value:>13.1f}   "
          f"({h1.max_location[0]:.0f}, {h1.max_location[1]:.0f})")

# Three maps on one colour scale, plus a bar chart of H1H and H8H.
fig = plt.figure(figsize=(9, 6.5))
gs = fig.add_gridspec(2, 3, height_ratios=[1.25, 1], hspace=0.45, wspace=0.08)
vmax = max(h1.max_value for h1, _ in results.values())
levels = [vmax * f for f in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)]
for i, method in enumerate(METHODS):
    ax = fig.add_subplot(gs[0, i])
    g = grids[method].pivot(index="Y", columns="X", values="AVERAGE_CONC")
    cs = ax.contourf(g.columns, g.index, g.values, levels=levels, cmap="YlOrRd", extend="min")
    ax.plot(0, 0, "k^", ms=7, label="Stack")
    h1 = results[method][0]
    ax.plot(*h1.max_location, "b*", ms=11, mec="w", label="Max")
    ax.set_title(f"{method}: max {h1.max_value:.0f} µg/m³", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.tick_params(labelsize=8)
    if i == 0:
        ax.set_ylabel("y (m)")
        ax.legend(loc="lower left", fontsize=7)
    else:
        ax.set_yticklabels([])
fig.colorbar(cs, ax=fig.axes, orientation="vertical", fraction=0.025, pad=0.02,
             label="1-hr NO₂ (µg/m³)", format="%.0f")

ax = fig.add_subplot(gs[1, :])
x = range(len(METHODS))
h1s = [results[m][0].max_value for m in METHODS]
h8s = [results[m][1].max_value for m in METHODS]
b1 = ax.bar([i - 0.2 for i in x], h1s, 0.4, color="#d95f02", label="Highest (H1H)")
b8 = ax.bar([i + 0.2 for i in x], h8s, 0.4, color="#7570b3", label="8th-highest (H8H, 98th pct)")
ax.bar_label(b1, fmt="%.0f", fontsize=8)
ax.bar_label(b8, fmt="%.0f", fontsize=8)
ax.axhline(188, color="k", ls="--", lw=1)
ax.text(1.0, 191, "1-hr NO₂ NAAQS, 188 µg/m³", ha="center", va="bottom", fontsize=8)
ax.set_xticks(list(x), [f"{m} ({'Tier 2' if m == 'ARM2' else 'Tier 3'})" for m in METHODS])
ax.set_ylabel("Max daily 1-hr NO₂ (µg/m³)")
ax.set_ylim(0, max(260, max(h1s) * 1.4))
ax.legend(fontsize=8, loc="upper right", ncols=2)
fig.suptitle("1-hr NO₂ by chemistry method: maps show the highest daily maximum (H1H)\n"
             f"{NOX_GS:g} g/s NOx, {OZONE_PPB:g} ppb O₃, LOVETT 1988 met", fontsize=11)

png = WORK / "06_no2_chemistry.png"
fig.savefig(png, dpi=130, bbox_inches="tight")
print(f"Figure: {png}")
