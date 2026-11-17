# SDE: docs PR B (concise docs with screenshots)

Approved design (2026-11-16): screenshots, shorter GUI guide and quickstart, student-guide split, docs-examples test.
The student-guide split shipped in #68 (pushed there because of the stop hook).

## Done in this PR
- scripts/docs_screenshots.py: pyaermod-app via tests/e2e harness + page objects + reference scenario (albany_success replay); browser app via app_dev_server. 13 PNGs (~500 kB), palette-quantized, header/notifications hidden, blank margins trimmed.
- tests/test_docs_images.py: every referenced image exists; every screenshot is used.
- GUI guide: 7 screenshots, ~13% shorter (badges, checklist, Project prose condensed; History removed; editor-widget table moved to CONTRIBUTING; KMZ needs pyproj).
- browser.md: 2 app screenshots. Student guide: layout (setup), Tutorial 1 (5 shots), Tutorial 3 (3 shots), captions say "EPA's Albany example"; PDF embeds images (41 pages, 785 kB).
- quickstart: 2,535 -> 1,115 words; figure from use case 1; recipes/keywords/features linked to owners; "Reading an existing deck" section.
- tests/test_docs_examples.py: runs Python blocks of quickstart + student guide; `<!-- docs-example: skip (reason) -->` markers; mutation-checked.

## Not done (follow-up)
- Single install page: the GUI guide's Install section is the owner and the quickstart now links it; README/index/desktop/teaching still carry their own install lines.
- architecture.md (stale proposal) -> CONTRIBUTING; keyword audit/validation into a Validation nav section.
- Tutorials 2 and 4 have no screenshots (same screens as 1 and 3; area-source shot would need a new scenario).
