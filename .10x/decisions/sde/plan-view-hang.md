# SDE: plan-view hang (review finding H1)

**Type:** bug fix, no architectural change (no ADR).

## What was built
- `gui_v2/plan_view.py::_ticks` counts ticks by index (`first + i*step`), stops on overshoot or on a repeated value, and is capped at `MAX_TICKS = 100`. The old accumulating loop never ended when `step` was below the float spacing (1 m at 1e18).
- `plan_view_svg` returns a short SVG naming every source / receptor network with a non-finite coordinate or one beyond `MAX_COORDINATE = 1e8` m, instead of drawing. 1e8 m is ten times the largest UTM northing, so no real projected coordinate is affected; anything larger is a typo the user should see.
- Tests (tests/test_gui_v2_plan_view.py): `_ticks` terminates at 1e20 and +/-1e300; a source at y=1e18 yields the message naming it; NaN/inf coordinates name the source and the discrete receptors; a UTM-scale coordinate still draws. The tests run the call in a daemon thread with a 5 s join, so a regression fails instead of hanging CI.

## What could go wrong (QA/security lens)
- Multi-user server (`--host`): before the fix one user could freeze every session. Now bounded.
- Remaining related risk (review, PLAUSIBLE): `footprints.receptor_points` expands a whole CartesianGrid before thinning; a 10^8-point grid would still stall the loop. Not fixed here.

## Verification
- New tests failed before the fix (3 failures; hung threads grew until killed for lack of memory), pass after.
- `pytest -k "gui_v2 and not ipv6"`: 751 passed, 5 skipped. The IPv6 entry-point test fails identically on unchanged code (container has no IPv6).
- ruff clean; mypy reports no errors in plan_view.py.

## Tech debt
None added.
