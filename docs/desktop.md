# Desktop App

Starting in **v1.9**, pyaermod ships pre-built desktop binaries for
Windows, macOS, and Linux. They wrap the NiceGUI app inside a native
[pywebview](https://pywebview.flowrl.com/) window — no terminal, no
Python install required for end users.

## Download

Pre-built binaries are attached to each [GitHub Release](https://github.com/atmmod/pyaermod/releases).
Look for assets named:

- ``pyaermod-desktop-windows-x64.zip`` — Windows 10/11, 64-bit
- ``pyaermod-desktop-macos.zip`` — macOS 12+ universal
- ``pyaermod-desktop-linux-x64.tar.gz`` — Linux x86_64 (any glibc-compatible distro)

## Run

After unzipping:

- **Windows**: double-click ``pyaermod-desktop.exe``
- **macOS**: drag ``pyaermod-desktop.app`` to Applications and double-click
- **Linux**: ``./pyaermod-desktop`` from a shell

The app starts the NiceGUI server on a free loopback port in the
background and opens a window on it. It opens to the **Project** step,
with the seven steps of the [GUI User Guide](gui-guide.md) listed on the
left:

1. On **Project**, name the run and choose the pollutant and averaging
   periods, **Open** a saved ``.json`` project, or **Import deck** an
   existing AERMOD ``.inp`` file
2. Build the run on **Sources**, **Receptors**, **Meteorology** and
   **Output**
3. **Review & Run** lists what still blocks the run, previews the deck
   and runs the AERMOD binary (which must be on the system PATH) with a
   progress bar and Cancel
4. **Results** shows the maxima for each averaging period, every summary
   table, the concentration map, the NAAQS comparison, the downloads and
   the run history

## What differs from the browser

The desktop app is the same GUI, with native dialogs where the browser
would upload or download a file:

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
progress is stopped when the app exits.

## Build from source

If you want to roll your own bundle (e.g. for an offline air-gapped
network, or an older OS that the pre-built binaries don't support):

```bash
git clone https://github.com/atmmod/pyaermod
cd pyaermod
pip install -e ".[gui-desktop]" pyinstaller>=6.0
pyinstaller packaging/pyaermod_desktop.spec --clean --noconfirm
```

The built binary lands in ``dist/``. Same spec works on all three OSes;
PyInstaller picks per-platform defaults at build time (single-file
``.exe`` on Windows, single-file ELF on Linux, ``.app`` bundle on macOS).

## AERMOD binary

The desktop bundle does **not** ship the AERMOD Fortran binary. Install
[AERMOD from EPA SCRAM](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/)
separately and ensure ``aermod`` is on your system ``PATH``. When the
executable isn't found, the Review & Run step's readiness checklist
says "No 'aermod' binary on PATH. Install AERMOD and re-launch." and
the Run AERMOD button stays disabled.

## Web mode

The same NiceGUI app can also run as a normal web app, useful for
multi-user / server deployments:

```bash
pip install pyaermod[gui]
pyaermod-app
```

Opens a browser tab pointed at ``http://127.0.0.1:8080``.

## Reporting issues

The desktop bundle is a thin pywebview wrapper around the same NiceGUI
app — most bug reports apply equally to web mode and desktop mode.
File issues at <https://github.com/atmmod/pyaermod/issues> with the OS
+ bundle version (visible in the title bar).
