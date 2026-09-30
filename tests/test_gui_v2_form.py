"""Which widget each dataclass field gets, and how it is labelled (tier T0).

The widgets themselves are exercised through the pages in
``test_gui_v2_smoke.py``; this pins the dispatch for every field of
every type the GUI edits.
"""

from __future__ import annotations

import dataclasses

import pytest

from pyaermod.gui_v2._form import (
    BOOL,
    FLOAT,
    INT,
    NUMBER_LIST,
    PATH,
    READ_ONLY,
    SCALAR_OR_LIST,
    STR_LIST,
    TEXT,
    VERTICES,
    field_kind,
    field_label,
    is_integer,
)
from pyaermod.gui_v2.pages.receptors import _new_receptor
from pyaermod.gui_v2.pages.sources import _SOURCE_TYPES, _new_source
from pyaermod.input_generator import MeteorologyPathway, OutputPathway
from pyaermod.pathways import ChemistryOptions


def _kind(obj, name):
    return field_kind(obj, {f.name: f for f in dataclasses.fields(obj)}[name])


@pytest.mark.parametrize(("obj", "name", "kind"), [
    (_new_source("PointSource"), "source_id", TEXT),
    (_new_source("PointSource"), "stack_height", FLOAT),
    (_new_source("PointSource"), "is_urban", BOOL),
    (_new_source("PointSource"), "building_height", SCALAR_OR_LIST),
    (_new_source("PointSource"), "source_groups", STR_LIST),
    (_new_source("PointSource"), "no2_ratio", FLOAT),
    (_new_source("PointSource"), "gas_deposition", READ_ONLY),
    (_new_source("PointSource"), "deposition_method", READ_ONLY),
    (_new_source("AreaPolySource"), "vertices", VERTICES),
    (_new_source("AreaCircSource"), "num_vertices", INT),
    (_new_source("BuoyLineSource"), "line_segments", READ_ONLY),
    (_new_source("RLineExtSource"), "vegetative_barriers", READ_ONLY),
    (_new_receptor("CartesianGrid"), "x_num", INT),
    (_new_receptor("CartesianGrid"), "x_points", NUMBER_LIST),
    (_new_receptor("CartesianGrid"), "grid_elevations", READ_ONLY),
    (_new_receptor("PolarGrid"), "dir_num", INT),
    (MeteorologyPathway("", ""), "surface_file", PATH),
    (MeteorologyPathway("", ""), "data_start_year", INT),
    (MeteorologyPathway("", ""), "start_year", INT),
    (MeteorologyPathway("", ""), "wind_speed_categories", NUMBER_LIST),
    (OutputPathway(), "summary_file", PATH),
    (OutputPathway(), "postfile", PATH),
    (OutputPathway(), "plot_file_groups", READ_ONLY),       # List[Tuple[str, str, str]]
    (OutputPathway(), "maxi_files", READ_ONLY),             # List[MaxiFile]
    (OutputPathway(), "no_header", STR_LIST),
    (OutputPathway(), "receptor_table_rank", INT),
    (ChemistryOptions(), "olm_groups", READ_ONLY),          # unresolvable forward ref
    (ChemistryOptions(), "default_no2_ratio", FLOAT),
])
def test_field_kinds(obj, name, kind):
    assert _kind(obj, name) == kind


@pytest.mark.parametrize("type_name", list(_SOURCE_TYPES))
def test_no_source_list_of_objects_gets_a_text_box(type_name):
    """Only lists of text, numbers or x, y pairs have an editor."""
    src = _new_source(type_name)
    for f in dataclasses.fields(src):
        kind = field_kind(src, f)
        if kind in (STR_LIST, NUMBER_LIST, VERTICES):
            assert "List[" in str(f.type), f.name


@pytest.mark.parametrize(("annotation", "expected"), [
    ("int", True), ("Optional[int]", True), ("float", False), ("Optional[float]", False),
    ("Union[int, float]", False), (int, True), (float, False),
])
def test_is_integer(annotation, expected):
    assert is_integer(annotation) is expected


def test_labels_carry_units():
    fields = {f.name: f for f in dataclasses.fields(_new_source("PointSource"))}
    assert field_label(fields["stack_temp"]) == "Stack temp (K)"
    assert field_label(fields["exit_velocity"]) == "Exit velocity (m/s)"
    assert field_label(fields["source_id"]) == "Source ID"
    grid = {f.name: f for f in dataclasses.fields(_new_receptor("PolarGrid"))}
    assert field_label(grid["dist_num"]) == "Dist num"             # a count: no unit
    assert field_label(grid["dir_delta"]) == "Dir delta (deg)"
