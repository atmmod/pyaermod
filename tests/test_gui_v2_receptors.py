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
from pyaermod.gui_v2.session import Session


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
        assert _all_rows(Session().receptor_entries()) == []

    def test_after_add(self):
        s = Session()
        keys = [
            s.add_receptor(_new_receptor("CartesianGrid")),
            s.add_receptor(_new_receptor("PolarGrid")),
            s.add_receptor(_new_receptor("DiscreteReceptor")),
            s.add_receptor(_new_receptor("DiscreteReceptor")),
        ]
        rows = _all_rows(s.receptor_entries())
        assert [r["kind"] for r in rows] == [
            "CartesianGrid", "PolarGrid", "DiscreteReceptor", "DiscreteReceptor"]
        # Rows carry the session's keys; discrete receptors are numbered
        # within their kind.
        assert [r["key"] for r in rows] == keys
        assert [r["label"] for r in rows[2:]] == ["DISC0", "DISC1"]
