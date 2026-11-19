# inv-links (saved by orchestrator from the agent's hand-back; 79 md files, 273 targets)

## Broken links
- docs/use-cases.md:22 anchor `#10-air-toxics-screening-with-a-unit-emission-rate-q-and-gis-export` drops the χ; heading at :300 slugs to `...rate-χq-and-gis-export`. Broken on GitHub and mkdocs.
- docs/teaching/refinery-assignments.md:17-19 anchors to tutorial 6/7/8 headings (lines 25, 307, 590) that contain an em dash: resolve on mkdocs, broken on GitHub only.
- No missing files or images. No orphan pages (76 docs pages, all in nav).

## Overlap (headings + spot reads)
- Install: README:17-31, index:38-47, quickstart:3-14, install.md (home), gui-guide:20-29, desktop:8-25, student-guide/setup:13-33.
- AERMOD binary: install:81-99, gui-guide:49-57, desktop:96-104 (near-verbatim), quickstart:13/106/375, setup:34-53, README:157.
- Requirements/Citing/License: README:153-188 vs index:48-70.
- Features/source types: README:100-127 vs index:10-21.
- Quick start: README:32-99 vs quickstart:15-107, 285-301.
- Recipes: quickstart:154-284 vs use-cases:84-179.
- Student guide vs main: next-steps:27-48 vs quickstart:154-179, 224-255; next-steps:35-41 vs use-cases:252-275; tutorial-4:15-42, 77-152 vs use-cases:156-179.
- GUI launch/layout: gui-guide:30-84 vs setup:169-211.
- Issue reporting: gui-guide:382-387 vs desktop:146-152.
- AERMAP errors: aermap-troubleshooting:242-251 vs common-errors:209-214.

## CLI commands in docs
No mismatches. Subcommands validate, run, parse, plotfile, profile (cli.py:219-266) are not shown anywhere in docs.

Not checked: external URLs, notebook contents, code fences beyond CLI lines.
