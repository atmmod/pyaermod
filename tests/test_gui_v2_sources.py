"""Tests for the v2 Sources tab logic.

The NiceGUI render path itself is exercised end-to-end during manual
QA; here we cover the pure-Python helpers (source-type registry,
default instantiation, summary row builder, type-string dispatch).
"""

from __future__ import annotations

import dataclasses
import typing
from typing import List, Optional, Tuple, Union

import pytest

from pyaermod.gui_v2._form import is_numeric as _is_numeric
from pyaermod.gui_v2._form import (
    is_numeric_or_numeric_list as _is_numeric_or_numeric_list,
)
from pyaermod.gui_v2._form import is_optional_numeric as _is_optional_numeric
from pyaermod.gui_v2._form import resolve_annotation as _resolve_annotation
from pyaermod.gui_v2.pages.sources import (
    _DEFAULTS,
    _SOURCE_TYPES,
    _new_source,
    _summary_row,
)
from pyaermod.input_generator import DepositionMethod
from pyaermod.pathways import ChemistryOptions


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
    """``is_numeric`` must be true only for int/float (optionally | None).

    It used to be a substring test, which handed ``List[Tuple[float, float]]``
    (polygon vertices) and ``Optional[Tuple[DepositionMethod, float]]`` to
    ``ui.number`` — the first crashed the editor dialog, the second let the
    user write a float into a tuple-typed field.
    """

    @pytest.mark.parametrize("ann,expected", [
        ("float",                                     True),
        ("int",                                       True),
        ("Optional[float]",                           True),
        ("Optional[int]",                             True),
        ("Union[int, None]",                          True),
        ("float | None",                              True),
        ("typing.Optional[float]",                    True),
        ("List[float]",                               False),
        ("List[Tuple[float, float]]",                 False),
        ("Optional[Tuple[DepositionMethod, float]]",  False),
        ("Optional[Union[float, List[float]]]",       False),
        ("Optional[str]",                             False),
        ("str",                                       False),
        ("bool",                                      False),
        ("not an annotation[",                        False),
    ])
    def test_is_numeric_string_annotations(self, ann, expected):
        assert _is_numeric(ann) is expected

    @pytest.mark.parametrize("tp,expected", [
        (float,                                      True),
        (int,                                        True),
        (Optional[int],                              True),
        (Optional[float],                            True),
        (List[Tuple[float, float]],                  False),
        (Optional[Tuple[DepositionMethod, float]],   False),
        (Optional[Union[float, List[float]]],        False),
        (str,                                        False),
        (bool,                                       False),
    ])
    def test_is_numeric_resolved_types(self, tp, expected):
        assert _is_numeric(tp) is expected

    def test_is_optional_numeric(self):
        assert _is_optional_numeric("Optional[float]")
        assert _is_optional_numeric("Optional[int]")
        assert _is_optional_numeric(Optional[int])
        assert not _is_optional_numeric("Optional[str]")
        assert not _is_optional_numeric("float")
        assert not _is_optional_numeric(int)
        assert not _is_optional_numeric("Optional[Tuple[DepositionMethod, float]]")

    def test_real_source_fields_resolve_correctly(self):
        """The shapes that bit, taken from the real dataclass annotations."""
        poly = _new_source("AreaPolySource")
        meta = {f.name: f for f in dataclasses.fields(poly)}
        assert not _is_numeric(_resolve_annotation(poly, meta["vertices"]))
        assert not _is_numeric(_resolve_annotation(poly, meta["deposition_method"]))
        assert _is_numeric(_resolve_annotation(poly, meta["release_height"]))
        assert _is_numeric(_resolve_annotation(poly, meta["emission_rate"]))
        point = _new_source("PointSource")
        pmeta = {f.name: f for f in dataclasses.fields(point)}
        assert _is_numeric(_resolve_annotation(point, pmeta["stack_height"]))
        assert not _is_numeric(_resolve_annotation(point, pmeta["source_id"]))


class TestScalarOrListDispatch:
    """``is_numeric_or_numeric_list`` picks out the building-downwash shape.

    ``Optional[Union[float, List[float]]]`` is neither numeric (the union
    holds a list) nor a plain ``List[...]``, so it fell through every branch
    of ``emit_field`` into the read-only-label escape hatch and building
    dimensions became untypeable. The predicate demands *both* a numeric
    scalar and a numeric list so it stays disjoint from ``is_numeric``
    (plain ``float``) and from the list branches (plain ``List[float]``,
    ``List[Tuple[float, float]]``).
    """

    @pytest.mark.parametrize("ann,expected", [
        ("Optional[Union[float, List[float]]]",              True),
        ("Union[float, List[float], None]",                  True),
        ("Union[float, List[float]]",                        True),
        ("Optional[Union[int, list[int]]]",                  True),
        ("float | List[float] | None",                       True),
        ("typing.Optional[typing.Union[float, typing.List[float]]]", True),
        # Disjoint from the branches that already worked
        ("float",                                            False),
        ("Optional[float]",                                  False),
        ("List[float]",                                      False),
        ("List[Tuple[float, float]]",                        False),
        ("Optional[Union[float, List[Tuple[float, float]]]]", False),
        ("Optional[Union[str, List[str]]]",                  False),
        ("Optional[Union[float, List[str]]]",                False),
        ("Optional[Tuple[DepositionMethod, float]]",         False),
        ("str",                                              False),
        ("bool",                                             False),
        ("not an annotation[",                               False),
    ])
    def test_string_annotations(self, ann, expected):
        assert _is_numeric_or_numeric_list(ann) is expected

    @pytest.mark.parametrize("tp,expected", [
        (Optional[Union[float, List[float]]],        True),
        (Union[float, List[float]],                  True),
        (Optional[Union[int, List[int]]],            True),
        (float,                                      False),
        (Optional[float],                            False),
        (List[float],                                False),
        (List[Tuple[float, float]],                  False),
        (Optional[Tuple[DepositionMethod, float]],   False),
        (Optional[Union[str, List[str]]],            False),
        (str,                                        False),
        (bool,                                       False),
    ])
    def test_resolved_types(self, tp, expected):
        assert _is_numeric_or_numeric_list(tp) is expected

    @pytest.mark.parametrize("type_name", ["PointSource", "VolumeSource", "AreaSource"])
    def test_real_building_fields_on_every_source_that_has_them(self, type_name):
        src = _new_source(type_name)
        meta = {f.name: f for f in dataclasses.fields(src)}
        for name in ("building_height", "building_width", "building_length",
                     "building_x_offset", "building_y_offset"):
            ann = _resolve_annotation(src, meta[name])
            assert _is_numeric_or_numeric_list(ann), name
            # ...and the numeric branch still (correctly) declines them,
            # so the two predicates never both claim a field.
            assert not _is_numeric(ann), name

    def test_never_overlaps_the_numeric_branch_on_a_real_source(self):
        """No field on any source type satisfies both predicates."""
        for cls in _SOURCE_TYPES.values():
            hints = typing.get_type_hints(cls)
            for f in dataclasses.fields(cls):
                ann = hints.get(f.name, f.type)
                assert not (_is_numeric(ann) and _is_numeric_or_numeric_list(ann)), (
                    f"{cls.__name__}.{f.name}"
                )


class TestForwardRefFallback:
    """``_form._type_hints`` falls back to {} on an unresolvable forward ref.

    ``pathways.ChemistryOptions.olm_groups`` is annotated
    ``List[SourceGroupDefinition]`` with the name imported only under
    ``if TYPE_CHECKING``, so ``typing.get_type_hints`` raises ``NameError``
    at runtime. The form must degrade to the raw string annotation, which
    the structural parsers handle, rather than propagate the error.
    """

    def test_get_type_hints_really_raises_name_error(self):
        with pytest.raises(NameError):
            typing.get_type_hints(ChemistryOptions)

    def test_resolve_annotation_falls_back_to_the_raw_string(self):
        opts = ChemistryOptions()
        meta = {f.name: f for f in dataclasses.fields(opts)}
        ann = _resolve_annotation(opts, meta["olm_groups"])
        assert ann == "List[SourceGroupDefinition]"
        # Neither numeric predicate claims it, so emit_field routes it by
        # its ``List[`` type string as before.
        assert not _is_numeric(ann)
        assert not _is_numeric_or_numeric_list(ann)

    def test_sibling_fields_of_the_same_class_still_resolve(self):
        """The {} fallback is per class, so every field uses the string path."""
        opts = ChemistryOptions()
        meta = {f.name: f for f in dataclasses.fields(opts)}
        assert _is_numeric(_resolve_annotation(opts, meta["default_no2_ratio"]))


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
