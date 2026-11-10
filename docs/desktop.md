# Desktop Window

`pyaermod-desktop` opens the PyAERMOD GUI in a native window instead of
a browser tab. It is the same NiceGUI app as `pyaermod-app`, shown in a
[pywebview](https://pywebview.flowrl.com/) window, and it is installed
with pip like the rest of the package.

## Install and start

```bash
pip install "pyaermod[gui-desktop]"
pyaermod-desktop
```

The `gui-desktop` extra adds pywebview to what `pyaermod[gui]` installs.
For other ways to install the GUI, see the
[installation section of the GUI guide](gui-guide.md#install).

- **Windows**: pywebview uses the Edge WebView2 runtime, which is part
  of Windows 11 and of an up-to-date Windows 10. Nothing else to
  install.
- **macOS**: pywebview uses the system WebKit. Nothing else to install.
- **Linux**: pip does not install a window backend, so add one of the
  two below.

### Linux: choose GTK or Qt

On Linux pywebview needs either GTK or Qt, and installs neither by
default. Its
[installation page](https://pywebview.flowrl.com/guide/installation.html)
has the current details; in short:

- **Qt**, entirely from pip. This installs PyQt6 and PyQt6-WebEngine:

  ```bash
  pip install "pywebview[qt]"
  ```

- **GTK**, with WebKitGTK (WebKit2 2.22 or later). On Debian and Ubuntu
  the system packages are:

  ```bash
  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
  ```

  These belong to the system Python. A virtual environment sees them
  only if it was created with `--system-site-packages`; otherwise
  install PyGObject into the environment with
  `pip install "pywebview[gtk]"`, which compiles it and so needs a C
  compiler and the GObject development packages (see the
  [PyGObject documentation](https://pygobject.gnome.org/getting_started.html),
  also for other distributions). The `gir1.2-*` packages are needed
  either way.

If no backend is found, `pyaermod-desktop` stops with pywebview's error
naming GTK and Qt. The browser mode (`pyaermod-app`) needs none of this.

## What it does

The command starts the NiceGUI server on a free loopback port in the
background and opens a window on it. It opens to the **Project** step,
with the seven steps of the [GUI User Guide](gui-guide.md) listed on the
left:

1. On **Project**, name the run and choose the pollutant and averaging
   periods, **Open** a saved `.json` project, or **Import deck** an
   existing AERMOD `.inp` file
2. Build the run on **Sources**, **Receptors**, **Meteorology** and
   **Output**
3. **Review & Run** lists what still blocks the run, previews the deck
   and runs the AERMOD binary (which must be on the system PATH) with a
   progress bar and Cancel
4. **Results** shows the maxima for each averaging period, every summary
   table, the concentration map, the NAAQS comparison, the downloads and
   the run history

## What differs from the browser

The desktop window is the same GUI, with native dialogs where the
browser would upload or download a file:

- **Open** and **Import deck** use a native file dialog, and the file is
  read from where it is. A deck imported this way brings the met files
  and other input files found beside it, with their full paths.
- **Save as** asks where to save through a native save dialog, after
  which **Save** writes back to that file.
- The met file fields on the Meteorology step have a **Browse...**
  button.
- The project's recent files (opened or saved by path, and imported
  decks) are listed on the Project step.

Reloading the window keeps the project. Closing the window stops the
server; unsaved changes are lost, so save first. Any AERMOD run still in
progress is stopped when the window closes.

## AERMOD binary

PyAERMOD does **not** ship the AERMOD Fortran binary. Install
[AERMOD from EPA SCRAM](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/)
separately and ensure `aermod` is on your system `PATH`. When the
executable isn't found, the Review & Run step's readiness checklist
says "No 'aermod' binary on PATH. Install AERMOD and re-launch." and
the Run AERMOD button stays disabled.

## Web mode

The same app also runs in a browser tab, which suits multi-user and
server deployments:

```bash
pip install "pyaermod[gui]"
pyaermod-app
```

Opens a browser tab pointed at `http://127.0.0.1:8080`.

## Desktop downloads discontinued

Releases from v1.9 up to v2.2.0 have stand-alone desktop apps attached
on the [releases page](https://github.com/atmmod/pyaermod/releases)
(for Windows, Apple-silicon macOS and Linux). They are no longer built:
later releases attach none, and the ones already published get no
fixes. The supported way to install the GUI is pip, as above, or conda
(see the [installation section of the GUI guide](gui-guide.md#install)).

Those downloads are unsigned. On macOS, Gatekeeper blocks them ("Apple
could not verify..." or "... is damaged and can't be opened"). If you
still have one and want to run it, do either of these once, after
moving the app to Applications:

- In a terminal, remove the quarantine mark the browser put on the
  download:

  ```bash
  xattr -dr com.apple.quarantine /Applications/pyaermod-desktop.app
  ```

- Or try to open the app, dismiss the warning, then open **System
  Settings → Privacy & Security**, scroll to the message about
  `pyaermod-desktop` and choose **Open Anyway**.

Only do this for a file downloaded from the project's own releases
page.

## Reporting issues

The desktop window is a thin pywebview wrapper around the same NiceGUI
app, so most bug reports apply equally to both modes. File issues at
<https://github.com/atmmod/pyaermod/issues> with the OS, the PyAERMOD
version (`pip show pyaermod`) and, on Linux, whether pywebview is using
GTK or Qt.
