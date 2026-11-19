# codebase-review (2026-11-18)
Review in slices that follow the data flow: deck model (sources, pathways, generator) -> reader -> validator -> runners ->
output parsers -> regulatory post-processing; then met/terrain/geospatial, ensemble/API/CLI, and the two GUIs over a shared Session.
No architectural change is decided here. Any refactor that moves a module boundary gets an ADR before it is coded.
