# Senior engineer: browser-gui implementation approach

- T1: tokenizer in input_reader._split_blocks uses runstream_fields for the data part (TITLEONE/TITLETWO keep plain split so their text is unchanged). New pathways.runstream_field(value) quotes a value containing blanks; every writer site that emits a file name uses it; UnparsedLine.to_aermod_line quotes fields with blanks. Sandbox code is unchanged but now sees unquoted paths. Tests: quoted escape refused; "My Met/a.sfc" and ERRORFIL "My Dir/err.out" round-trip byte-equal in the field.
- T2: int(float(tok)) for numeric station ids and years; anything else -> the line kept in unparsed_lines with a warning; MeteorologyPathway must tolerate a missing station id (check the field default first).
- T3/T4: wasm_runner and runner._run_once paths; tests with fake JS module objects (existing test_wasm_runner pattern).
- T5: move pure functions (review, ChecklistItem, _step_for_*, output_folders, _met_files) to readiness.py; pages/run.py re-imports names so tests and callers keep working.
- T6-T8: one module, src/pyaermod/browser.py; envelope helper `_call(fn)`; working dir default /home/pyodide/work under Pyodide, a tempdir under CPython (parameter for tests).
- T9: site/app/{index.html, app.css, app.js, rpc.js, forms.js, worker.js}; DOM via createElement/textContent; worker loads pyodide from jsDelivr 314.0.6 and installs wheels listed in site/app/wheels.json (written by the build).
- Tricky parts: list-valued fields (AREAPOLY vertices) -> textarea "x,y per line"; enums from schema; results contour SVG from results_map (matplotlib in Pyodide).
