# 3. Setting Up PyAERMOD

> **Want to see AERMOD run before you install anything?** Go to
> **https://atmmod.github.io/pyaermod/browser/** and click **Open the
> notebooks**. In a few minutes, inside your web browser, the notebooks
> build a model of one smokestack, run AERMOD and draw a map of the
> concentrations. Nothing is installed on your computer. The notebooks use
> short Python code rather than the GUI, so they do not replace the
> tutorials below. The AERMOD they run is an
> unofficial build of EPA's code, fine for learning but not for regulatory
> work.

## 3.1 Install

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:

```bash
pip install "pyaermod[gui]"
```

This installs the core package plus everything needed for the graphical
interface (NiceGUI and the matplotlib plots the Results step draws).

To verify the install worked:

```bash
pyaermod info
```

You should see the PyAERMOD version and a list of the features that can run
on this computer. (Keep the quotes in the `pip install` command: without them
the default macOS shell, zsh, reads the square brackets as a file pattern.)

## 3.2 Install the AERMOD and AERMET Executables

PyAERMOD is a *wrapper* — it generates input files, launches the model, and
visualizes results, but it does **not** include the AERMOD or AERMET programs
themselves. Those are separate Fortran executables maintained by the U.S. EPA.

**Which executables do you need?**

| Executable | What it does | Which tutorials need it |
|---|---|---|
| `aermod` | Runs the dispersion model | Tutorial 3 (running AERMOD) |
| `aermet` | Preprocesses meteorological data | Tutorial 5 (AERMET processing) |
| `aermap` | Preprocesses terrain elevations | Optional (terrain analysis) |

Tutorials 1–2 only generate input files, so you can **skip this step
initially** and come back when you're ready for Tutorial 3.

If you cannot install programs on your computer (a shared lab computer, for
example), the [browser notebooks](https://atmmod.github.io/pyaermod/lite/lab/index.html?path=01_run_aermod_in_your_browser.ipynb) run AERMOD without these executables.

### Option A: Compile from source (macOS and Linux)

PyAERMOD's build script downloads EPA's public-domain Fortran source and
compiles **all three executables** (AERMOD, AERMAP and AERMET). EPA does not
publish macOS or Linux executables, and PyAERMOD releases do not include any.

**Prerequisites:** You need `gfortran` (the GNU Fortran compiler).

On macOS, install it with [Homebrew](https://brew.sh):

```bash
brew install gcc
```

On Ubuntu/Debian Linux:

```bash
sudo apt-get install gfortran
```

**Build steps:**

```bash
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod
./scripts/build_aermod.sh all
```

This creates executables in the `bin/` directory. Move them to your PATH:

```bash
mkdir -p ~/bin
cp bin/aermod bin/aermap ~/bin/
```

and AERMET the same way:

```bash
cp bin/aermet ~/bin/
```

Then add `~/bin` to your PATH so PyAERMOD can find them. Add this line to
your `~/.zshrc` (or `~/.bashrc` on Linux):

```bash
export PATH="$HOME/bin:$PATH"
```

Then **restart your terminal** (close and reopen it), or run
`source ~/.zshrc` in your current session, and check:

```bash
which aermod
aermod
```

`which` should print the path to `aermod`. Running `aermod` alone prints a
version header and then stops with an error about a missing input file:
**that is normal** and means it is installed.

To build straight into another directory instead of `bin/`, set `BIN_DIR`
(a relative path is taken from the directory you run the script in):

```bash
BIN_DIR=~/bin ./scripts/build_aermod.sh all
```

After each executable the script prints a short build record: its path,
its SHA-256 checksum, the compiler version and the compile and link
flags, and for AERMOD the version number in its banner (26135 for the
current EPA source; "unknown (banner not found)" means the check could
not read it). Keep it with your results if you need to say exactly which
executable produced them.

A build replaces an executable of the same name in that directory (the
script tells you when it does). To keep a second AERMOD, for example one
built from source you have changed, give it another name with
`AERMOD_EXE_NAME=aermod_test` or build it into its own `BIN_DIR`.

### Option B: Windows

The EPA provides official Windows executables:

1. Go to the [EPA SCRAM website](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models).
2. Download the **AERMOD Modeling System** zip file.
3. Extract the zip. Inside you'll find `aermod.exe`, `aermet.exe`, and
   `aermap.exe`.
4. Place them in a folder (e.g., `C:\AERMOD\`) and add that folder to your
   system PATH:
   - Search for **"Environment Variables"** in the Start menu.
   - Under **System variables**, find `Path`, click **Edit**.
   - Click **New** and add `C:\AERMOD\` (or wherever you put the files).
   - Click **OK** to save.
5. Open a **new** Command Prompt and verify:

```
aermod
```

### Verifying your installation

After installing by any method, you can verify everything is set up with:

```bash
pyaermod info       # Should show the PyAERMOD version and feature list
which aermod        # Should print the path to the aermod executable
aermod              # Should print AERMOD version (error about input is OK)
```

> **The GUI's Review & Run step looks for the `aermod` executable on your
> PATH.** If it can't find it, its readiness checklist says "No 'aermod'
> binary on PATH. Install AERMOD and re-launch." and the **Run AERMOD**
> button stays disabled. The GUI has no field for the executable's path:
> put `aermod` on your PATH and start the GUI again.

## 3.3 Launch the GUI

```bash
pyaermod-app
```

Your web browser will open automatically to `http://127.0.0.1:8080`. You'll see
the PyAERMOD interface with a list of steps on the left and the **Project**
step in the main area. (If port 8080 is already in use on your computer, run
`pyaermod-app --port 8081` instead.)

> **Tip:** The GUI runs as a local web app. It never sends your data to the
> internet — everything stays on your computer.

## 3.4 GUI Layout

- **Header (top):** The project's name, a "(modified)" marker while there are
  unsaved changes, a one-line readiness summary ("Ready to run" or "Not ready
  to run: ...") and a **Save** button.
- **Step list (left):** Navigation between the 7 workflow steps. Each step
  carries a badge: not started, complete, warning or error. In a narrow
  window the list is hidden behind the menu button in the header.
- **Main area (center):** The current step — forms, tables, and plots.

The 7 steps, in workflow order:

1. **Project** — open and save project files; titles, pollutant, averaging
   periods, terrain
2. **Sources** — add and edit emission sources
3. **Receptors** — define where concentrations are calculated
4. **Meteorology** — point to weather data files
5. **Output** — choose the files and tables AERMOD writes
6. **Review & Run** — readiness checklist, input-file preview, and the run
7. **Results** — maxima, concentration map, NAAQS comparison, downloads

You can visit the steps in any order. The GUI calls an AERMOD input file a
**deck**, the modelers' word for it.

All coordinates in the GUI are AERMOD's model coordinates: easting and
northing in UTM meters. There is no map to click and no latitude/longitude
setting.

![The GUI when it opens: the header with the readiness line and Save, the step list on the left with a badge per step, and the Project step](../../images/gui/layout.png)
