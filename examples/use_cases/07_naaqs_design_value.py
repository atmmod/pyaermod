"""
NAAQS compliance: the 1-hour SO2 design value.

Models two SO2 stacks with AERMOD's MAXDAILY output, computes the 99th-percentile
(4th-highest) daily-maximum 1-hour design value at every receptor, adds a monitored
background and compares it with the 75 ppb NAAQS. Writes a design-value map and a
ranked bar chart of the highest receptors to ``07_naaqs_design_value.png``.
"""

import os
import warnings
from pathlib import Path

MET_DIR = Path(os.environ.get("AERMOD_MET_DIR", "met"))   # holds LOVETT.SFC / LOVETT.PFL
WORK = Path(os.environ.get("USE_CASE_OUT", "out")) / "07_naaqs_design_value"
WORK.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from pyaermod import (  # noqa: E402
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    Validator,
    get_naaqs,
    mxdybyyr_design_value,
    naaqs_compliance_report,
    naaqs_output_pathway,
    read_maxdaily,
    read_mxdybyyr,
    run_aermod,
)

BACKGROUND = 20.0  # uniform SO2 background, ug/m3 (~7.6 ppb; use your monitor's design value)

# --- Project: POLLUTID SO2 + AVERTIME 1 switches on AERMOD's SO2 NAAQS processing
control = ControlPathway(
    title_one="Use case 07: 1-hour SO2 design value",
    pollutant_id=PollutantType.SO2,
    averaging_periods=["1"],
    terrain_type="ELEVATED",  # sources and receptors at 0 m, so flat; FLAT is dropped under DFAULT
)
sources = SourcePathway()
sources.add_source(PointSource(       # main boiler stack
    source_id="BOILER", x_coord=0.0, y_coord=0.0,
    stack_height=45.0, stack_temp=420.0,   # m, K
    exit_velocity=15.0, stack_diameter=2.2,  # m/s, m
    emission_rate=40.0,                    # g/s SO2
))
sources.add_source(PointSource(       # smaller process heater
    source_id="HEATER", x_coord=250.0, y_coord=-150.0,
    stack_height=25.0, stack_temp=480.0,
    exit_velocity=10.0, stack_diameter=1.0,
    emission_rate=8.0,
))
receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(-2000, 2000, -2000, 2000, spacing=100))

met = MeteorologyPathway(
    surface_file=str((MET_DIR / "LOVETT.SFC").resolve()),
    profile_file=str((MET_DIR / "LOVETT.PFL").resolve()),
    surface_station_id=14735, upper_air_station_id=14735,
    data_start_year=1988, profile_base_elevation=1.8,  # PROFBASE, m MSL
)
# MAXDAILY (daily max 1-hr series), MXDYBYYR (AERMOD's ranks) and MAXDCONT,
# with the rank (4th highest) taken from 40 CFR 50 Appendix T
output = naaqs_output_pathway("SO2", stem="so2")
project = AERMODProject(control, sources, receptors, met, output)

# --- Validate, write, run
check = Validator.validate(project, check_files=True)
print(check)
if not check.is_valid:
    raise SystemExit(1)
inp = WORK / "so2_dv.inp"
project.write(inp)
run = run_aermod(inp, timeout=1800)
if not run.success:
    raise SystemExit(f"AERMOD failed: {run.error_message}")
print(f"AERMOD finished in {run.runtime_seconds:.0f} s, {run.warning_count} warning(s)")

# --- Design value from the daily-max series. One met year here; a regulatory
# run averages 5 years of NWS data (or 1-3 years of site-specific data).
daily = read_maxdaily(WORK / "so2_maxdaily.dat")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # "defined over 3 years" -- we know we have 1
    report = naaqs_compliance_report("SO2", daily, background=BACKGROUND, n_years=1)
    aermod_dv = mxdybyyr_design_value(read_mxdybyyr(WORK / "so2_mxdybyyr.dat"), rank=4)

std = get_naaqs("SO2", "1-hour")
naaqs = std.level_ugm3            # 75 ppb -> 196.4 ug/m3, the level "exceeds" is checked against
top = report.nlargest(10, "design_value").reset_index(drop=True)
best = top.iloc[0]
print(f"Days in met year: {daily['date'].str[:6].nunique()}")
print(f"Max design value (incl. {BACKGROUND:g} ug/m3 background): "
      f"{best.design_value:.1f} ug/m3 at ({best.x:.0f}, {best.y:.0f}) m")
print(f"  modelled part {best.design_value - BACKGROUND:.1f} ug/m3; AERMOD's own "
      f"4th-high (MXDYBYYR) max {aermod_dv['concentration'].max():.1f} ug/m3")
print(f"NAAQS {std.level:g} {std.units} = {naaqs:.1f} ug/m3; "
      f"{int(report['exceeds'].sum())} of {len(report)} receptors exceed")

# --- Figure: DV map with the NAAQS contour, and the top receptors vs the standard
xs, ys = np.sort(report["x"].unique()), np.sort(report["y"].unique())
grid = report.pivot(index="y", columns="x", values="design_value").loc[ys, xs].to_numpy()
fig, (ax, bx) = plt.subplots(1, 2, figsize=(9, 6.5), gridspec_kw={"width_ratios": [1.5, 1]})
levels = np.arange(BACKGROUND, max(grid.max(), naaqs) + 20, 20)
cf = ax.contourf(xs, ys, grid, levels=levels, cmap="viridis")
ax.contour(xs, ys, grid, levels=[naaqs], colors="red", linewidths=2.2)
ax.plot([], [], "r-", lw=2.2, label=f"NAAQS contour {naaqs:.1f}")
for s in sources.sources:
    ax.plot(s.x_coord, s.y_coord, "w^", ms=9, mec="k")
    ax.annotate(s.source_id, (s.x_coord, s.y_coord), xytext=(-8, 8), ha="right",
                textcoords="offset points", color="w", fontsize=8)
ax.plot(best.x, best.y, "*", color="orange", ms=13, mec="k",
        label=f"max DV {best.design_value:.1f}")
ax.set(aspect="equal", xlabel="Easting (m)", ylabel="Northing (m)")
ax.set_xticks(np.arange(-2000, 2001, 1000))
ax.legend(loc="lower left", fontsize=8)
fig.colorbar(cf, ax=ax, orientation="horizontal", pad=0.1,
             label="SO2 1-hr design value incl. background (µg/m³)")

labels = [f"({r.x:.0f}, {r.y:.0f})" for r in top.itertuples()]
bx.barh(labels, top["design_value"] - BACKGROUND, color="#3b528b", label="AERMOD")
bx.barh(labels, BACKGROUND, left=top["design_value"] - BACKGROUND, color="#bbbbbb",
        label=f"background {BACKGROUND:g}")
bx.axvline(naaqs, color="red", lw=2, label=f"NAAQS {naaqs:.1f}")
bx.invert_yaxis()
bx.set(xlabel="Design value (µg/m³)", ylabel="Top 10 receptors (x, y in m)")
bx.tick_params(axis="y", labelsize=7)
bx.legend(fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
fig.suptitle("SO2 1-hour design value: 4th-highest daily max 1-hr (99th pct), "
             "LOVETT 1988, one year", fontsize=11)
fig.tight_layout()
fig.savefig(WORK / "07_naaqs_design_value.png", dpi=130)
print(f"Figure: {WORK / '07_naaqs_design_value.png'}")
