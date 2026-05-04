# GUI User Guide

PyAERMOD ships an interactive GUI built on [NiceGUI](https://nicegui.io).
The same codebase runs in two modes:

- **Browser tab** via `pyaermod-app` — the NiceGUI server runs on
  loopback. Best for development, multi-user / server deployments,
  and remote access.
- **Native desktop window** via `pyaermod-desktop` — wraps the same
  app in a [pywebview](https://pywebview.flowrl.com/) shell. Best for
  end users who want a one-click app with no terminal.

Pre-built single-file desktop binaries for Windows, macOS, and Linux
are attached to each [GitHub Release](https://github.com/atmmod/pyaermod/releases).
See [Desktop App](desktop.md) for download instructions.

## Install

```bash
pip install pyaermod[gui]          # NiceGUI, browser mode
pip install pyaermod[gui-desktop]  # + pywebview, native window mode
```

## Launch

```bash
pyaermod-app           # opens a browser tab at http://127.0.0.1:8080
pyaermod-desktop       # opens a native OS window
```

Both modes share the same seven-tab layout:

| Tab | Purpose |
|---|---|
| **Project** | File menu (new / open / save / save as) and run-level metadata (title, pollutant) |
| **Sources** | Add / edit / delete any of the 10 AERMOD source types |
| **Receptors** | Cartesian grid, polar grid, and discrete receptor lists |
| **Meteorology** | Surface + profile file paths, anemometer height, date range |
| **Output** | Output pathway: summary, plot, post, max files |
| **Run** | Dispatch AERMOD against the current project |
| **Results** | Parsed `.OUT` summary, source list, max concentrations, POSTFILE listing |

The Project tab's "Save" button writes a JSON file you can re-open later;
the format is documented in `pyaermod.gui_v2.project_io`.

## AERMOD binary

The Run tab calls the `aermod` binary on your `PATH`. Install AERMOD
from [EPA SCRAM](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/)
separately. The Run tab surfaces a clear "no AERMOD binary" banner
when the executable isn't found.

## Source forms

The Sources tab uses a generic dataclass-field walker — every source
type's editor is auto-generated from its dataclass definition. Adding
new source types in the future requires no GUI work.

| Field annotation | Widget |
|---|---|
| `str` | text input |
| `float` / `int` | numeric input |
| `bool` | checkbox |
| `Optional[<numeric>]` | clearable numeric |
| `List[Tuple[float, float]]` | textarea (one `x, y` per line) |
| `List[str]` | textarea (one entry per line) |

For fields the form helper doesn't model (Enums, nested deposition
dataclasses), the value is shown read-only with the recommendation to
edit via Python directly.

## Tips

- Save your project to JSON at every checkpoint — open files reload
  cleanly across pyaermod versions thanks to the `save_format_version`
  field.
- The Run tab leaves the working directory in place after a run; the
  Results tab reads from it. Use the working-directory input to point
  at any prior run's directory to inspect old results.
- For headless / scripted workflows, build `AERMODProject` instances
  in Python directly — the GUI is purely an authoring layer on top of
  the same dataclasses.

## History

PyAERMOD 1.x shipped a Streamlit GUI alongside the NiceGUI app. The
Streamlit GUI was deprecated in v1.9 and **removed in v2.0**. If you
need the legacy interface, pin to `pyaermod==1.9.x`.

## Reporting issues

File issues at <https://github.com/atmmod/pyaermod/issues> with the
OS, install method (`pip` vs. desktop bundle), and a minimum
reproducer (a saved `.json` project is ideal).
