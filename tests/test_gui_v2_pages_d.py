"""Smoke tests for the v1.9-D pages (Output, Run, Results).

The render functions themselves are exercised in NiceGUI's test runner
end-to-end; these unit tests cover importability and module structure.
"""

from __future__ import annotations

import pytest


def test_output_render_callable():
    pytest.importorskip("nicegui")
    from pyaermod.gui_v2.pages.output import render
    assert callable(render)


def test_run_render_callable():
    pytest.importorskip("nicegui")
    from pyaermod.gui_v2.pages.run import _aermod_available, render
    assert callable(render)
    assert isinstance(_aermod_available(), bool)


def test_results_render_callable():
    pytest.importorskip("nicegui")
    from pyaermod.gui_v2.pages.results import render
    assert callable(render)
