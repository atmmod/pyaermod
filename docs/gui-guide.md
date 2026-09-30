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
| **Run** | Review & Run: what blocks the run, a preview of the deck, and the run itself |
| **Results** | Parsed `.OUT` summary, source list, max concentrations, POSTFILE listing |

The Project tab's "Save as..." button saves the project as a JSON file you
can re-open later with "Open...": in the browser the file arrives as a
download, and in the desktop app (`pyaermod-desktop`) a save dialog asks
where to put it, after which "Save" writes back to that file. The format
is documented in `pyaermod.gui_v2.project_io`.

In the Sources and Receptors editors, "Save" applies your changes and
"Close" discards them; an item you add appears in the table only once
you save it.

Each browser tab keeps its own project: reloading the tab brings back the
project and the last run, but closing the tab or stopping the server
discards unsaved changes, so save before you do.

## Review & Run

The Run tab reviews the project before AERMOD sees it. Its readiness
checklist lists every problem that would stop the run, grouped by the
step that fixes it, with a "Go to" link to that step; **Run AERMOD**
stays disabled until the checklist is empty. A met file given by a
relative path counts as such a problem while the working directory is
blank, because AERMOD opens relative paths from its working directory
and a blank one is a new, empty temporary folder: give the full path or
set the working directory. Warnings that do not stop the run follow
under "Before you run", among them ANNUAL averages with less than a year
of met data, which AERMOD would abort with fatal error E480. Below them
is a read-only preview of the deck the run will use, with Copy and
Download.

AERMOD runs in the background, so the other tabs, and other browser
tabs, stay usable. A progress bar follows AERMOD's day count against the
days in the surface file, next to the elapsed time and a **Cancel**
button. When the run ends the status says Succeeded, Failed or
Cancelled, followed by the number of fatal errors, warnings and
informational messages AERMOD reported and a table of those messages
(severity, pathway, code, input line and text). Codes with an entry in
[Common AERMOD errors](common-errors.md) link to it. New or Open during
a run stops the run, and so does stopping the server.

## AERMOD binary

The Run tab calls the `aermod` binary on your `PATH`. Install AERMOD
from [EPA SCRAM](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/)
separately. When the executable isn't found, the Run tab's checklist
says so and Run AERMOD stays disabled.

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
- The Run tab leaves the working directory in place after a run. The
  Results tab shows the latest run of this session and updates when a
  run finishes; earlier run directories stay on disk but the GUI does
  not reopen them.
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
