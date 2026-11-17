# How pyaermod is organised

pyaermod is a Python layer over EPA's AERMOD programs. It writes their
input files, runs them, and reads what they write. Every concentration
comes from AERMOD itself; pyaermod does not reimplement the model. This
page is a map of the code for contributors; the
[API Reference](api/index.md) documents each module.

## From a project to results

```text
AERMODProject ──write()──▶ deck (.inp) ──AERMODRunner──▶ AERMOD ──▶ .out, plot files, POSTFILEs
      ▲                         │                                          │
read_aermod_input ◀─────────────┘                    output_parser, aermod_outputs, postfile
      │                                                                    │
   Validator                                          design_values, naaqs, visualization
```

- **The project model** is a tree of dataclasses, one per AERMOD pathway:
  `ControlPathway`, `SourcePathway`, `ReceptorPathway`,
  `MeteorologyPathway`, `OutputPathway` and `EventPathway` (in
  `pathways`, `sources` and `receptors`), held by `AERMODProject`
  (`input_generator`). Each writes its own runstream lines. Field units and
  help text are declared on the dataclass fields (`_fields.described`),
  which is what the GUIs show beside each input.
- **Reading a deck** (`input_reader`) parses a runstream the way
  AERMOD's `setup.f` does and rebuilds the same objects. A line pyaermod
  does not model is kept in `AERMODProject.unparsed_lines` (`unparsed`)
  and written back, so a deck survives a read and a write; the keyword
  audit lists what each AERMOD keyword becomes.
- **Validation** (`validator`, `validator_advanced`, `regulatory`) checks a
  project against AERMOD's rules before anything is written;
  `AERMODProject.write()` refuses a project with errors.
- **Running** (`runner`) stages the deck as `aermod.inp` in a working
  directory, runs AERMOD, and reads its verdict from the `.out` file, not
  its exit code, which is 0 even after a fatal error. `ensemble` runs
  many cases, each in its own directory, with a manifest for resuming.
- **Reading results**: `output_parser` reads the `.out` summary tables;
  `aermod_outputs` the plot files and AERMOD's other output files;
  `postfile` text and binary POSTFILEs. `design_values` and `naaqs` turn
  them into NAAQS design values; `visualization`, `geospatial` and
  `kmz_export` map and export them.
- **The other EPA programs** each have a module that writes its input and
  one that runs it: AERMET (`aermet`, `aermet_runner`), AERMAP (`aermap`,
  `terrain`), AERSURFACE, AERSCREEN and BPIP-PRIME (`bpip`).

## The graphical interfaces

- **`pyaermod-app`** (`gui_v2`) is a NiceGUI application. A UI-free
  `Session` (`gui_v2/session.py`) holds the project, its file and the
  run history and announces every change; each step's page is rebuilt from
  the session. The Review & Run checklist (`gui_v2/readiness.py`) and the
  project file format (`gui_v2/project_io.py`) have no UI either.
  `pyaermod-desktop` shows the same app in a pywebview window.
- **The browser app** (`webapp/`) is a static page. pyaermod runs inside it
  under Pyodide in a Web Worker, and every operation goes through one JSON
  entry point, `pyaermod.browser.call`, which reuses the session's
  checklist, file format and results code. AERMOD there is EPA's source
  compiled to WebAssembly (`scripts/build_aermod_wasm.sh`), run by
  `wasm_runner` through the same `AERMODRunner`. The JupyterLite notebooks
  use the same build.

## Tests

The tests run in three tiers. Unit and integration tests need no AERMOD
binary. The GUI journeys (`tests/e2e`) drive both GUIs in Chromium with
AERMOD replayed from recorded runs. The real-binary and EPA-parity
workflows compare pyaermod's runs with EPA's published results; the
[validation report](validation.md) has the evidence. `CONTRIBUTING.md`
in the repository says how to run each.
