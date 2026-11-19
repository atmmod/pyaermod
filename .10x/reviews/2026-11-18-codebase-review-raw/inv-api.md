# inv-api: public API vs API docs inventory (read-only, HEAD of claude/codebase-review-2026-11-18)

Method: ast-based scripts in scratchpad/repro/inv-api/ (inv.py, docimports.py). Facts only.

## 1. Inventory
- src/pyaermod/__init__.py:48-58 `__all__` = __version__, __author__, __email__, __license__, __url__, get_version, print_info, api, plus api.__all__.
- src/pyaermod/api.py:352-447 static `__all__`: 245 names. api.py:449-467 optional extends (HAS_GEOSPATIAL: 9 names; HAS_TERRAIN: 7 names).
- Modules in src/pyaermod/: 60 .py files (top level, incl. private _fields, _fortran, _optional). gui_v2/: __init__, __main__, _form, _layout, _live, _native, app, desktop, files, plan_view, project_io, readiness, results_map, run_results, session, state, steps; pages/: __init__, meteorology, output, project, receptors, results, run, sources.
- docs/api/: 43 files (index.md + 42 module pages).
- mkdocs.yml:71-126 API Reference nav: 42 module pages + Overview (api/index.md).

## 2-3. Mismatches
- Modules with NO docs/api page (top-level, non-underscore): api (facade; covered only by docs/api/index.md), browser, epa_testcases, footprints, versions (exports VALIDATED_AERMOD_VERSIONS / VALIDATED_AERMET_VERSIONS, api.py:354), wasm_runner.
  Private, so excluded by mkdocstrings filter: _fields, _fortran, _optional.
- gui_v2 submodules (app, desktop, project_io, etc.) have no own pages; only docs/api/gui_v2.md (nav mkdocs.yml:126).
- Docs/api pages pointing at non-existent modules: none. Every docs/api/*.md has a src module of the same name.
- Nav targets (mkdocs.yml) that do not exist under docs/: none found (script checked every `*.md` target).
- docs/api pages not in nav: none. All 42 module pages are in nav.
- docs/api/index.md internal links: all resolve.
- Names in docs/api/index.md that do not exist in code: none for identifiers (CORE_NAMES api.py:477, API_VERSION api.py:504, AERMETRunner.run_stage aermet_runner.py:253, Validator.validate validator.py:114, regulatory apply/check regulatory.py:92,125, AERMETStage2 in __all__). Non-code tokens in index.md that look like names but are extras/CLI words: `all`, `geo`, `gui`, `hpc`, `met`, `viz` (extras, pyproject.toml:44-110 — all exist); `gui-desktop` extra exists; `validate`, `run`, `parse`, `plotfile`, `profile` are CLI subcommands (cli.py:231-258; `plotfile`/`profile` exist). `gui_v2` is a package (exists).
- Count/claim mismatches in docs/api/index.md:
  - index.md:15 says "All 13 source dataclasses" for sources; sources.py defines 14 source classes (StreetCanyon sources.py:1043, RLineSource :1104, RLineExtSource :1192, BuoyLineSource :1349, OpenPitSource :1462, PointSource :386, PointCapSource :508, PointHorSource :520, SidewashPointSource :530, AreaSource :581, AreaCircSource :702, AreaPolySource :778, VolumeSource :869, LineSource :959).
  - index.md:124-126 says CORE_NAMES covers "the runner and CLI"; CORE_NAMES (api.py:477-503) contains no CLI name (grep: 0 hits for "cli").
  - index.md:126 "~30 names": actual count 31 (api.py:477-503).
  - index.md:126-129 and 120-129 say guarantee holds "across every 1.x release"; API_VERSION is "2.0" (api.py:504) and package is 2.3.0 (__init__.py:32). Not a name mismatch; a version-wording item.
- Names in `__all__` not defined or bound anywhere in src: none. All 245 static names and 16 optional names are bound in api.py namespace (imports or definitions).
- `__all__` names not importable-looking: none found.

## 4. pyaermod imports in docs/**/*.md and README.md
- 94 imported names in ~20 python fenced blocks checked (README.md:37-42, 74-75, 87; docs/quickstart.md; docs/aermap-troubleshooting.md; docs/aermet-tuning-guide.md; docs/common-errors.md; docs/ensemble.md; docs/psd.md; docs/regulatory-matrix.md; docs/teaching/refinery-assignments.md; docs/teaching/student-guide/tutorial-5.md; docs/api/index.md).
- Result: 0 missing modules, 0 missing names.
- Spot-checked definitions: psd.py:367 LognormalCDF, :487 SizeDistribution, :764 bins_from_cut_points; gui_v2/project_io.py:504 save_project, :572 load_project; terrain.py:435 AERMAPRunner, :636 AERMAPOutputParser, :830 TerrainProcessor; terrain_utils.py:173 mosaic_dem_tiles, :202 reproject_dem, :286 hill_height_diagnostics.
- Caveat: the check treats any top-level binding in a module (including its own imports) as existing, and for `from pyaermod import X` checks against api.py bindings, not strictly api.__all__. So a name imported but not exported would pass. Not tested for that.

## Not looked at
- Did not verify docstrings or signatures; did not run any doc code; did not check docs/teaching/practice or non-python code blocks beyond the ones matched.
- Did not verify CORE_NAMES claim that "three NO2 chemistry presets" are NO2-specific.
