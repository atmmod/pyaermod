# Desktop App

Starting in **v1.9**, pyaermod ships pre-built desktop binaries for
Windows, macOS, and Linux. They wrap the NiceGUI app inside a native
[pywebview](https://pywebview.flowrl.com/) window — no terminal, no
Python install required for end users.

## Download

Pre-built binaries are attached to each [GitHub Release](https://github.com/atmmod/pyaermod/releases).
Look for assets named:

- ``pyaermod-desktop.exe`` — Windows, 64-bit (x64). A single executable,
  not zipped.
- ``pyaermod-desktop-macos.zip`` — macOS on Apple silicon (arm64) only.
  Unzips to ``pyaermod-desktop.app``.
- ``pyaermod-desktop`` — Linux x86_64. A single executable, not
  archived.

There is no Intel Mac build. On an Intel Mac (or any other system
without a pre-built binary), install the same app with pip and start it
from a terminal:

```bash
pip install "pyaermod[gui-desktop]"
pyaermod-desktop
```

## Run

- **Windows**: double-click ``pyaermod-desktop.exe``
- **macOS**: unzip, drag ``pyaermod-desktop.app`` to Applications and
  double-click it. If macOS refuses to open it, see
  [macOS: signing and Gatekeeper](#macos-signing-and-gatekeeper).
- **Linux**: the download is not marked executable, so
  ``chmod +x pyaermod-desktop`` once, then ``./pyaermod-desktop`` from a
  shell

## macOS: signing and Gatekeeper

macOS builds attached to releases after 2.2.0 are signed with a
Developer ID certificate and notarized by Apple, so they open with a
double-click like any other downloaded app.

The macOS builds of v2.2.0 and earlier are not signed or notarized, and
Gatekeeper blocks them ("Apple could not verify..." or "... is damaged
and can't be opened"). To run one of those builds, do either of these
once, after moving the app to Applications:

- In a terminal, remove the quarantine mark the browser put on the
  download:

  ```bash
  xattr -dr com.apple.quarantine /Applications/pyaermod-desktop.app
  ```

- Or try to open the app, dismiss the warning, then open **System
  Settings → Privacy & Security**, scroll to the message about
  ``pyaermod-desktop`` and choose **Open Anyway**.

Only do this for a build downloaded from the project's
[releases page](https://github.com/atmmod/pyaermod/releases). A bundle
you [build from source](#build-from-source) yourself is not quarantined
and needs neither step on the Mac that built it.

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
pip install -e ".[gui-desktop]" "pyinstaller>=6.0"
pyinstaller packaging/pyaermod_desktop.spec --clean --noconfirm
```

The built binary lands in ``dist/``. The same spec works on all three
OSes: a single-file ``.exe`` on Windows, a single-file ELF on Linux, and
a ``.app`` bundle on macOS, built for the architecture of the Python
that runs PyInstaller. The macOS bundle is ad-hoc signed unless
``MACOS_SIGN_IDENTITY`` names a Developer ID identity in your keychain;
[RELEASING.md](https://github.com/atmmod/pyaermod/blob/main/RELEASING.md)
describes how the release builds are signed and notarized.

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
