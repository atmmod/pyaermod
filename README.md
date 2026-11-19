# pyaermod

[![Tests](https://github.com/atmmod/pyaermod/actions/workflows/tests.yml/badge.svg)](https://github.com/atmmod/pyaermod/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

pyaermod writes AERMOD input files from Python, runs AERMOD, reads its
output and plots it.

**Try it without installing anything:** [open the app](https://atmmod.github.io/pyaermod/app/)
(the GUI's seven steps) or [the notebooks](https://atmmod.github.io/pyaermod/lite/lab/index.html?path=01_run_aermod_in_your_browser.ipynb).
They run pyaermod and AERMOD (EPA's source compiled to WebAssembly) in your
browser, for learning and not for regulatory work.
[More](https://atmmod.github.io/pyaermod/browser/).

## Installation

```bash
pip install pyaermod               # the library: numpy and pandas
pip install "pyaermod[all]"        # with plotting, GIS export and the GUI (quotes needed in zsh)
pipx install "pyaermod[gui]"       # just the GUI, then run: pyaermod-app
```

pyaermod needs Python 3.11 or later and an AERMOD executable from
[EPA SCRAM](https://www.epa.gov/scram) (EPA's Support Center for Regulatory
Atmospheric Modeling). [Install](https://atmmod.github.io/pyaermod/install/)
has every option and what to do when an install fails.

## Quick start

```python
from pyaermod import (
    AERMODProject, ControlPathway, SourcePathway, ReceptorPathway,
    MeteorologyPathway, OutputPathway, PointSource, CartesianGrid,
    PollutantType, TerrainType,
)

control = ControlPathway(
    title_one="My Facility",
    pollutant_id=PollutantType.PM25,
    averaging_periods=["ANNUAL", "24"],
    terrain_type=TerrainType.FLAT,
)

sources = SourcePathway()
sources.add_source(PointSource(
    source_id="STACK1", x_coord=500.0, y_coord=500.0,
    base_elevation=10.0, stack_height=50.0, stack_temp=400.0,
    exit_velocity=15.0, stack_diameter=2.0, emission_rate=1.5,
))

receptors = ReceptorPathway()
receptors.add_cartesian_grid(CartesianGrid.from_bounds(
    x_min=0, x_max=2000, y_min=0, y_max=2000, spacing=100,
))

meteorology = MeteorologyPathway(
    surface_file="met_data.sfc", profile_file="met_data.pfl",
)
output = OutputPathway(receptor_table=True, max_table=True)

project = AERMODProject(control, sources, receptors, meteorology, output)
project.write("facility.inp")      # validates the project first
```

<!-- docs-example: skip (runs AERMOD) -->
```python
from pyaermod import run_aermod, parse_aermod_output

result = run_aermod("facility.inp")
results = parse_aermod_output(result.output_file)
print(results.get_concentrations("ANNUAL"))
print(results.summary())
```

The [quick start](https://atmmod.github.io/pyaermod/quickstart/) goes on
to the plot files, plots and design values.

## Documentation

- [Quick start](https://atmmod.github.io/pyaermod/quickstart/)
- [Ten common AERMOD jobs](https://atmmod.github.io/pyaermod/use-cases/): what pyaermod supports (13 source types, deposition, NO2 chemistry, AERMET and AERMAP) as runnable scripts
- [GUI user guide](https://atmmod.github.io/pyaermod/gui-guide/)
- [How pyaermod is organised](https://atmmod.github.io/pyaermod/architecture/)
- [API reference](https://atmmod.github.io/pyaermod/api/)
- [Examples](https://github.com/atmmod/pyaermod/tree/main/examples)

A run through pyaermod adds 1 to 20 ms over calling AERMOD directly; see
[the benchmarks](https://atmmod.github.io/pyaermod/benchmarks/).

## Citing

If pyaermod contributes to published work, please cite the archival release.
[`CITATION.cff`](https://github.com/atmmod/pyaermod/blob/main/CITATION.cff)
carries the metadata (GitHub's "Cite this repository" button renders it as
APA or BibTeX):

> Capps, S. (2026). *PyAERMOD: Python wrapper for EPA's AERMOD air
> dispersion model* [Computer software].
> https://doi.org/10.5281/zenodo.23512926

That DOI always resolves to the latest release; each release also has its
own version DOI, listed in `CITATION.cff`. A journal article describing
pyaermod and its validation is in preparation for the *Journal of the Air &
Waste Management Association*; once it is published, citing the article is
preferred.

## License

MIT

## Disclaimer

pyaermod runs the AERMOD you give it; every concentration comes from AERMOD,
not from pyaermod.

The browser app and notebooks run EPA's source compiled to WebAssembly, which
is not for regulatory use.

pyaermod is validated against EPA AERMOD v26135 and AERMET v26135 (EPA
reference archives of 2026-07-09): a gfortran build driven by pyaermod
reproduces EPA's AERTEST plotfile bit-for-bit and every POSTFILE in EPA's test
suite within EPA's own tolerance (see
[the validation report](https://atmmod.github.io/pyaermod/validation/)).
v24142 remains supported for cross-version regression. Check results against
EPA test cases for your use.
