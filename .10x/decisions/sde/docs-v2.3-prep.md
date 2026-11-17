# SDE: docs fixes and v2.3.0 preparation (PR A)

Source: docs audit 2026-11-16 (agent, spot-checked) + GitHub release assets.

## Done
- quickstart: EVENT example (EventPeriod date/averaging_period/location, events= passed) and validator example (result.errors) now run; no "GUI BPIP calculator"; 13 source types; gui_v2/browser; quoted extras; duplicate EV heading and stale test counts removed.
- README (PyPI page): absolute links; browser app; 13 source types; disclaimer no longer claims "official EPA binaries for all calculations".
- index, desktop (bundles only on v1.9.0/v2.0.0 per the releases API; no conda package yet), regulatory-matrix row (NOSTD), teaching README (quoted install, app, practice deck), refinery (pyproj for KMZ), release-notes v2.2.0 install lines, CONTRIBUTING pytest selection.
- student guide: removed "Option A" release binaries (no release ever attached aermod/aermap); build-from-source is Option A; `pyaermod info`; PDF regenerated.
- Anchors fixed (mkdocs ids); practice deck in nav; Desktop Window moved next to the GUI guide.
- CHANGELOG [Unreleased]: duplicate subsections merged (no entry lost); entries added for #66 (RECTABLE) and these docs fixes. docs/release-notes/v2.3.0.md drafted (nav: "draft").
- tests/test_gui_v2_packaging.py: expects v1.9.0/v2.0.0 in the discontinued notice (was 2.2.0, which has no assets).

## Audit item rejected
- "EventPeriod.location is optional" (release notes v2.2.0): the validator requires it (E130), so the notes are right.

## Not in this PR
- regulatory checks reading nonexistent ControlPathway flags: queued as a separate task (needs coset.f oracle).
- Restructuring, trimming, screenshots: PR B.
- Version bump/date: the release commit, per RELEASING.md.
