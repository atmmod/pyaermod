"""Tests for the GUI v2 AppState (UI-framework-agnostic)."""

from __future__ import annotations

from pathlib import Path

from pyaermod.gui_v2.state import AppState, _empty_project


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


class TestAppState:
    def test_starts_clean(self):
        s = AppState()
        assert s.project is not None
        assert s.project_path is None
        assert s.dirty is False

    def test_mark_dirty_clean_round_trip(self):
        s = AppState()
        s.mark_dirty()
        assert s.dirty is True
        s.mark_clean()
        assert s.dirty is False

    def test_reset_drops_path_and_dirty(self):
        s = AppState()
        s.project_path = Path("/tmp/foo.json")
        s.dirty = True
        s.reset()
        assert s.project_path is None
        assert s.dirty is False
        assert s.project.control.title_one == "Untitled run"

    def test_title_includes_filename(self):
        s = AppState()
        s.project_path = Path("/tmp/myproject.json")
        assert "myproject.json" in s.title

    def test_title_marks_dirty(self):
        s = AppState()
        s.project_path = Path("/tmp/x.json")
        s.dirty = True
        assert "(modified)" in s.title

    def test_title_untitled_when_no_path(self):
        s = AppState()
        assert "Untitled" in s.title

    def test_last_run_dir_default_none(self):
        assert AppState().last_run_dir is None
