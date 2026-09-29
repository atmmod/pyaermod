"""End-to-end journeys for the NiceGUI app (PLAN-gui.md, tiers T2 and T3)."""

import pytest

# Plain asserts in the helper modules get pytest's detailed messages. This
# must run before they are imported, and the package is imported first.
pytest.register_assert_rewrite(
    "tests.e2e.harness", "tests.e2e.pages", "tests.e2e.reference")
