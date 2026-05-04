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

The app opens to the **Project** tab. From there:

1. Edit project metadata or **Open** an existing ``.json`` project
2. Switch to **Sources**, **Receptors**, **Meteorology**, **Output** tabs to build the configuration
3. **Run** dispatches the AERMOD binary (must be on the system PATH)
4. **Results** displays parsed ``.OUT`` summary + POSTFILE listings

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
separately and ensure ``aermod`` is on your system ``PATH``. The Run
tab surfaces a clear "no AERMOD binary" banner when the executable
isn't found.

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
