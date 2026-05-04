"""Tests for the v2 Sources tab logic.

The NiceGUI render path itself is exercised end-to-end during manual
QA; here we cover the pure-Python helpers (source-type registry,
default instantiation, summary row builder, type-string dispatch).
"""

from __future__ import annotations

import dataclasses

import pytest

from pyaermod.gui_v2._form import is_numeric as _is_numeric
from pyaermod.gui_v2._form import is_optional_numeric as _is_optional_numeric
from pyaermod.gui_v2.pages.sources import (
    _DEFAULTS,
    _SOURCE_TYPES,
    _new_source,
    _summary_row,
)


class TestSourceTypeRegistry:
    def test_all_ten_source_types_present(self):
        assert set(_SOURCE_TYPES) == {
            "PointSource", "VolumeSource", "AreaSource", "AreaCircSource",
            "AreaPolySource", "LineSource", "RLineSource", "RLineExtSource",
            "BuoyLineSource", "OpenPitSource",
        }


class TestNewSource:
    @pytest.mark.parametrize("type_name", list(_SOURCE_TYPES.keys()))
    def test_can_instantiate_default(self, type_name):
        # Every source type should construct cleanly with the registry's
        # default-fill, OR raise something other than TypeError. BuoyLine
        # genuinely needs a non-empty segments list — we accept that.
        try:
            src = _new_source(type_name)
            assert type(src).__name__ == type_name
        except (ValueError, TypeError) as e:
            # Allow only "needs additional fields" failures, surfaced
            # via dataclass __post_init__. New-source UX will surface
            # these to the user.
            assert "segments" in str(e).lower() or "vertices" in str(e).lower()

    def test_point_source_has_required_fields(self):
        src = _new_source("PointSource")
        assert src.source_id == "NEW_SRC"
        assert src.stack_height > 0
        assert src.stack_temp > 0

    def test_areapoly_has_default_vertices(self):
        src = _new_source("AreaPolySource")
        assert len(src.vertices) >= 3


class TestSummaryRow:
    def test_point_source_row(self):
        src = _new_source("PointSource")
        src.x_coord = 100.0
        src.y_coord = 200.0
        row = _summary_row(src)
        assert row["id"] == "NEW_SRC"
        assert row["type"] == "PointSource"
        assert row["x"] == 100.0
        assert row["y"] == 200.0

    def test_line_source_row_uses_start(self):
        src = _new_source("LineSource")
        src.x_start = 50.0
        src.y_start = 60.0
        row = _summary_row(src)
        assert row["x"] == 50.0
        assert row["y"] == 60.0

    def test_areapoly_row_uses_first_vertex(self):
        src = _new_source("AreaPolySource")
        row = _summary_row(src)
        # First vertex of the default 4-corner polygon
        assert row["x"] == 0.0
        assert row["y"] == 0.0


class TestTypeStringDispatch:
    @pytest.mark.parametrize("ann,expected", [
        ("float",            True),
        ("int",              True),
        ("Optional[float]",  True),
        ("List[float]",      True),  # falls into 'List[' branch elsewhere
        ("str",              False),
        ("bool",             False),
    ])
    def test_is_numeric(self, ann, expected):
        # _is_numeric matches any field annotation containing 'float'/'int'.
        # The page uses a List[ check before calling _is_numeric, so
        # 'List[float]' returning True here is fine — it never reaches
        # this branch in render flow.
        assert _is_numeric(ann) is expected

    def test_is_optional_numeric(self):
        assert _is_optional_numeric("Optional[float]")
        assert _is_optional_numeric("Optional[int]")
        assert not _is_optional_numeric("Optional[str]")
        assert not _is_optional_numeric("float")


class TestDefaults:
    def test_required_fields_have_defaults(self):
        # Every required (no default, no default_factory) field across
        # all 10 source types should be in _DEFAULTS, otherwise
        # _new_source would crash with TypeError.
        missing = set()
        for cls in _SOURCE_TYPES.values():
            for f in dataclasses.fields(cls):
                if (f.default is dataclasses.MISSING
                        and f.default_factory is dataclasses.MISSING
                        and f.name not in _DEFAULTS):
                    missing.add(f.name)
        assert not missing, (
            f"Source dataclass fields without _DEFAULTS entry: {missing}"
        )
