"""Write the JupyterLite site's notebooks into docs/lite/content/.

The notebooks are kept as this script rather than as .ipynb files so that
a review sees their code as code. Run it after changing them:

    python scripts/wasm/make_lite_notebooks.py
"""

import json
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[2] / "docs" / "lite" / "content"

DISCLAIMER = (
    "> **Not for regulatory use.** AERMOD here is EPA's public-domain source compiled to "
    "WebAssembly by pyaermod, not EPA's executable. Every change to it is checked against "
    "EPA's published AERTEST results (see the second notebook), but use EPA's executable "
    "for permit or compliance modeling.\n"
)

INSTALL = (
    "# Installs into this browser tab only; takes a few seconds the first time.\n"
    "%pip install -q pyaermod aermod_wasm matplotlib"
)


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def notebook(cells):
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python (Pyodide)", "language": "python", "name": "python"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


RUN_IN_BROWSER = notebook([
    md("""
# Run AERMOD in your browser

This notebook builds an AERMOD input file with pyaermod, runs AERMOD on it and maps the
result, all inside this browser tab: nothing is installed on your computer and nothing is
sent to a server.

""" + DISCLAIMER),
    code(INSTALL),
    md("""
## 1. Describe the model run

One 50 m stack, a 4 km square grid of receptors, and four days of meteorology from
Albany, NY (March 1988), the data EPA ships with its AERMOD test cases. The files are in
the `data` folder beside this notebook.
"""),
    code("""
from pyaermod import (
    AERMODProject, CartesianGrid, ControlPathway, MeteorologyPathway, OutputPathway,
    PointSource, PollutantType, ReceptorPathway, SourcePathway, TerrainType,
)

control = ControlPathway(
    title_one="pyaermod in the browser",
    title_two="One stack, four days of Albany 1988 met",
    pollutant_id=PollutantType.OTHER,
    averaging_periods=["1", "24", "PERIOD"],
    terrain_type=TerrainType.FLAT,
)

sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1",
    x_coord=0.0, y_coord=0.0, base_elevation=0.0,
    stack_height=50.0,     # m
    stack_temp=400.0,      # K
    exit_velocity=15.0,    # m/s
    stack_diameter=2.0,    # m
    emission_rate=1.0,     # g/s
))

receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    x_min=-2000, x_max=2000, y_min=-2000, y_max=2000, spacing=100,
))

meteorology = MeteorologyPathway(
    surface_file="data/AERMET2.SFC",
    profile_file="data/AERMET2.PFL",
    surface_station_id=14735,
    upper_air_station_id=14735,
    data_start_year=1988,
    profile_base_elevation=0.0,
)

output = OutputPathway(
    receptor_table=True,
    max_table=True,
    summary_file="browser_demo.sum",
    period_plot_files="browser_demo",   # a PLOTFILE per averaging period
)

project = AERMODProject(control=control, sources=sources, receptors=receptors,
                        meteorology=meteorology, output=output)
project.write("browser_demo.inp")
# The deck, without the grid's 82 lines of zero elevations:
print("\\n".join(line for line in project.to_aermod_input().splitlines()
                if " ELEV " not in line and " HILL " not in line))
"""),
    md("""
## 2. Run AERMOD

`AERMODRunner` finds the WebAssembly build of AERMOD that `aermod_wasm` installed. The run
takes a few seconds; the page cannot respond until it finishes.
"""),
    code("""
from pyaermod import AERMODRunner

result = AERMODRunner().run("browser_demo.inp")
print(result)
print(f"{result.warning_count} warning(s), {result.fatal_count} fatal error(s)")
"""),
    md("## 3. Read and map the results"),
    code("""
from pyaermod import read_plotfile

plot_names = output.period_plot_file_names(control.averaging_periods)
grid = read_plotfile(plot_names["PERIOD"]).to_dataframe()
peak = grid.loc[grid["AVERAGE_CONC"].idxmax()]
print(f"Highest 4-day average: {peak['AVERAGE_CONC']:.3g} ug/m3 at ({peak['X']:.0f}, {peak['Y']:.0f}) m")
grid.head()
"""),
    code("""
import matplotlib.pyplot as plt
import numpy as np

pivot = grid.pivot_table(index="Y", columns="X", values="AVERAGE_CONC")
fig, ax = plt.subplots(figsize=(7, 6))
levels = np.linspace(0, pivot.values.max(), 12)
filled = ax.contourf(pivot.columns, pivot.index, pivot.values, levels=levels, cmap="YlOrBr")
ax.plot(0, 0, marker="^", color="black", markersize=9, label="STACK1")
fig.colorbar(filled, ax=ax, label="4-day average concentration (ug/m3)")
ax.set_xlabel("x (m)")
ax.set_ylabel("y (m)")
ax.set_aspect("equal")
ax.legend(loc="upper right")
ax.set_title("Period average, STACK1")
plt.show()
"""),
    md("""
## 4. Try something

Change the stack height, exit velocity or emission rate in step 1, then run steps 1 to 3
again. Doubling the emission rate doubles every concentration; a taller stack lowers the
peak and moves it downwind.

The files AERMOD wrote (`browser_demo.out`, the `.plt` plot files) are in the file browser
on the left. Right-click one to download it.
"""),
])


REPRODUCE_AERTEST = notebook([
    md("""
# Reproduce EPA's AERTEST in the browser

EPA tests every AERMOD release on a set of example problems and publishes the results.
This notebook runs the first of them, AERTEST (a stack with building downwash and four
days of Albany, NY meteorology), with the WebAssembly AERMOD and compares its 1-hour
concentrations with EPA's, receptor by receptor.

pyaermod's continuous integration runs the same comparison on every change to the
WebAssembly build and fails if any receptor differs by more than 0.01 %.

""" + DISCLAIMER),
    code(INSTALL),
    code("""
import re
from pathlib import Path

# EPA's deck reads ../meteorology/ and writes ../plotfiles/ and ../Outputs/;
# here everything is in data/.
deck = Path("data/aertest.inp").read_text()
deck = re.sub(r"\\.\\./(meteorology|Outputs|plotfiles|postfiles)/", "", deck, flags=re.I)
deck = deck.replace("aermet2.sfc", "AERMET2.SFC").replace("aermet2.pfl", "AERMET2.PFL")
Path("data/aertest_here.inp").write_text(deck)
print(f"data/aertest_here.inp: {len(deck.splitlines())} lines")
"""),
    code("""
from pyaermod import AERMODRunner

result = AERMODRunner().run("data/aertest_here.inp")
print(result)
"""),
    code("""
import pandas as pd
from pyaermod import read_plotfile

def by_receptor(path):
    plot = read_plotfile(path)
    df = plot.to_dataframe()
    return df.set_index(["X", "Y"])[plot.concentration_column]

ours = by_receptor("data/AERTEST_01H.PLT")
epa = by_receptor("data/EPA_AERTEST_01H.PLT")
compare = pd.DataFrame({"browser": ours, "EPA": epa})
compare["relative difference"] = (compare["browser"] - compare["EPA"]).abs() / compare["EPA"].abs()
print(f"{len(compare)} receptors; largest relative difference {compare['relative difference'].max():.2e}")
compare.sort_values("EPA", ascending=False).head(10)
"""),
    code("""
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(5, 5))
ax.scatter(compare["EPA"], compare["browser"], s=12)
top = compare[["EPA", "browser"]].values.max() * 1.05
ax.plot([0, top], [0, top], color="grey", linewidth=1)
ax.set_xlabel("EPA's published 1-hour concentration (ug/m3)")
ax.set_ylabel("This browser's (ug/m3)")
ax.set_title("AERTEST, 144 receptors")
ax.set_aspect("equal")
plt.show()
"""),
])


def main():
    CONTENT.mkdir(parents=True, exist_ok=True)
    for name, nb in [("01_run_aermod_in_your_browser.ipynb", RUN_IN_BROWSER),
                     ("02_reproduce_epa_aertest.ipynb", REPRODUCE_AERTEST)]:
        path = CONTENT / name
        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
