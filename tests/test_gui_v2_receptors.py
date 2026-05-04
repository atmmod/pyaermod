"""Tests for the v2 Receptors tab logic."""

from __future__ import annotations

import dataclasses

import pytest

from pyaermod.gui_v2.pages.receptors import (
    _DEFAULTS,
    _RECEPTOR_TYPES,
    _all_rows,
    _new_receptor,
    _summary_row,
)
from pyaermod.gui_v2.state import AppState


class TestRegistry:
    def test_all_three_types(self):
        assert set(_RECEPTOR_TYPES) == {
            "CartesianGrid", "PolarGrid", "DiscreteReceptor",
        }

    @pytest.mark.parametrize("name", list(_RECEPTOR_TYPES.keys()))
    def test_default_construct(self, name):
        rec = _new_receptor(name)
        assert type(rec).__name__ == name

    def test_required_fields_have_defaults(self):
        missing = set()
        for cls in _RECEPTOR_TYPES.values():
            for f in dataclasses.fields(cls):
                if (f.default is dataclasses.MISSING
                        and f.default_factory is dataclasses.MISSING
                        and f.name not in _DEFAULTS):
                    missing.add(f.name)
        assert not missing, (
            f"Receptor fields without _DEFAULTS entry: {missing}"
        )


class TestSummaryRow:
    def test_cartesian(self):
        rec = _new_receptor("CartesianGrid")
        row = _summary_row(rec, kind="CartesianGrid", idx=0)
        assert row["kind"] == "CartesianGrid"
        assert "x" in row["summary"]

    def test_polar(self):
        rec = _new_receptor("PolarGrid")
        row = _summary_row(rec, kind="PolarGrid", idx=2)
        assert row["kind"] == "PolarGrid"
        assert "dist" in row["summary"]
        assert "dir" in row["summary"]

    def test_discrete(self):
        rec = _new_receptor("DiscreteReceptor")
        row = _summary_row(rec, kind="DiscreteReceptor", idx=5)
        assert row["kind"] == "DiscreteReceptor"
        assert row["label"] == "DISC5"


class TestAllRows:
    def test_empty(self):
        s = AppState()
        assert _all_rows(s) == []

    def test_after_add(self):
        s = AppState()
        s.project.receptors.cartesian_grids.append(
            _new_receptor("CartesianGrid"),
        )
        s.project.receptors.polar_grids.append(_new_receptor("PolarGrid"))
        s.project.receptors.discrete_receptors.append(
            _new_receptor("DiscreteReceptor"),
        )
        rows = _all_rows(s)
        assert len(rows) == 3
        kinds = {r["kind"] for r in rows}
        assert kinds == {"CartesianGrid", "PolarGrid", "DiscreteReceptor"}
