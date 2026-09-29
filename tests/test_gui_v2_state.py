"""Tests for the GUI v2 blank project.

The ``AppState`` tests moved to ``tests/test_gui_v2_session.py`` with
the class that replaced it.
"""

from __future__ import annotations

from pyaermod.gui_v2.state import _empty_project


class TestEmptyProject:
    def test_has_all_pathways(self):
        p = _empty_project()
        assert p.control is not None
        assert p.sources is not None
        assert p.receptors is not None
        assert p.meteorology is not None
        assert p.output is not None

    def test_default_title(self):
        p = _empty_project()
        assert p.control.title_one == "Untitled run"

    def test_no_sources_yet(self):
        assert _empty_project().sources.sources == []
