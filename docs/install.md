# Install

pyaermod needs Python 3.11 or later. AERMOD, EPA's dispersion model, is a
separate program; see
[AERMOD and the other EPA programs](#aermod-and-the-other-epa-programs) below.

**Nothing to install:** the [app and notebooks on this site](browser.md)
run pyaermod and AERMOD (compiled to WebAssembly) in your web browser.
They are for learning and teaching, not for regulatory work.

## The library, with pip

Install into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install pyaermod
```

`pyaermod` alone needs only numpy and pandas: it builds decks, runs AERMOD
and reads its output. Extras add the rest:

| Extra | Adds | For |
|---|---|---|
| `viz` | matplotlib, scipy, folium | contour plots and maps |
| `geo` | pyproj, geopandas, rasterio, shapely, scipy | GeoTIFF, GeoPackage, Shapefile and GeoJSON export |
| `terrain`, `met` | requests | downloading DEM tiles and met data |
| `hpc` | tqdm, requests | progress bars for batches and ensembles |
| `cad` | ezdxf | importing source outlines from DXF drawings |
| `gui` | NiceGUI, matplotlib | the graphical interface, `pyaermod-app` |
| `gui-desktop` | the `gui` packages and pywebview | the [desktop window](desktop.md), `pyaermod-desktop` |
| `all` | all of the above | |

```bash
python -m pip install "pyaermod[gui]"
```

Keep the quotes: without them zsh, the default shell on macOS, reads the
square brackets as a file pattern and stops with "no matches found".

## The graphical interface on its own

[pipx](https://pipx.pypa.io/) and [uv](https://docs.astral.sh/uv/) each
install a command-line program into an environment of its own and put
its commands on your `PATH`. Use either:

```bash
pipx install "pyaermod[gui]"
```

```bash
uv tool install "pyaermod[gui]"
```

Then start it with `pyaermod-app`. To upgrade later:
`pipx upgrade pyaermod` or `uv tool upgrade pyaermod`.

The [GUI user guide](gui-guide.md) says how to use it.

## conda

pyaermod is not on conda-forge yet; the recipe is prepared in the
repository's `conda-recipe/` directory. Once the conda-forge package is
published, the GUI will install with:

```bash
conda install -c conda-forge pyaermod-gui
```

`pyaermod-gui` is the conda form of the `gui` extra (conda has no
extras); `pyaermod` alone is the library without the GUI's packages.
Until then, use pip inside a conda environment:

```bash
conda create -n pyaermod python=3.12
conda activate pyaermod
python -m pip install "pyaermod[gui]"
```

## AERMOD and the other EPA programs

pyaermod runs the `aermod` executable it finds on your `PATH` (and
`aermet`, `aermap` and the others when you use them); it does not ship
them.

- **Windows:** EPA publishes executables on
  [SCRAM](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models)
  (EPA's Support Center for Regulatory Atmospheric Modeling).
  Put the folder that holds `aermod.exe` on your `PATH`.
- **macOS and Linux:** EPA publishes source code only.
  `scripts/build_aermod.sh` in the
  [repository](https://github.com/atmmod/pyaermod) downloads it and
  compiles AERMOD, AERMAP and AERMET with gfortran; the
  [student guide's setup page](teaching/student-guide/setup.md#32-install-the-aermod-and-aermet-executables)
  walks through it.

Check with `which aermod` (macOS, Linux) or `where aermod` (Windows), and
with `pyaermod info`, which lists what can run on this computer.

## Troubleshooting

| What you see | What to do |
|---|---|
| `zsh: no matches found: pyaermod[gui]` | Put the package name in quotes: `pip install "pyaermod[gui]"`. |
| `pyaermod-app: command not found` | The environment it was installed into is not active: activate the virtual environment (or conda environment) again. After `pipx install`, run `pipx ensurepath`; after `uv tool install`, run `uv tool update-shell`; then open a new terminal. `python -m pyaermod.gui_v2` starts the same app without the command being on `PATH`. |
| `pyaermod-app needs NiceGUI, which is not installed.` | pyaermod was installed without the extra. Run the command the message gives: `pip install "pyaermod[gui]"`. |
| `Cannot listen on 127.0.0.1 port 8080` | Another program, or another pyaermod window, is using the port. Choose another: `pyaermod-app --port 8081`. |
| No browser tab opens | Open the address the terminal shows (`http://127.0.0.1:8080`). Over SSH there is no browser to open: start with `--no-browser` and forward the port. |
| pip starts compiling packages and fails (`error: subprocess-exited-with-error`, a missing compiler or Rust) | Your Python is newer than the wheels of some dependency. Python 3.11 to 3.14 install without compiling anything; choose one of them, for example `uv tool install --python 3.13 "pyaermod[gui]"`. |
| `pyaermod-app --port 8081` still serves on port 8080, or `--help` starts the app | That is pyaermod 2.2.0, whose `pyaermod-app` reads no options. Upgrade: `python -m pip install --upgrade "pyaermod[gui]"`. `pyaermod gui`, `python -m pyaermod.gui_v2` and the one-line messages above are also newer than 2.2.0. |
| "KMZ export needs pyproj" on the Results step | Only that download needs pyproj: `python -m pip install pyproj` (with pipx: `pipx inject pyaermod pyproj`). Everything else in the GUI works without it. |

## For development

```bash
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod
python -m pip install -e ".[dev,all]"
```

[CONTRIBUTING.md](https://github.com/atmmod/pyaermod/blob/main/CONTRIBUTING.md)
has the tests and checks.
