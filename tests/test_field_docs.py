"""Every quantity a user types into a source, receptor or met form has units and help.

The GUI's forms read both from the dataclass field metadata
(``pyaermod._fields.described``); a new numeric field without them would
show as a bare name.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from pyaermod._fields import help_of, units_of
from pyaermod.input_generator import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    PointCapSource,
    PointHorSource,
    PointSource,
    PolarGrid,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    VolumeSource,
)
from pyaermod.pathways import OutputPathway

CLASSES = [
    PointSource, PointCapSource, PointHorSource, SidewashPointSource, VolumeSource,
    AreaSource, AreaCircSource, AreaPolySource, LineSource, RLineSource, RLineExtSource,
    BuoyLineSource, BuoyLineSegment, OpenPitSource,
    CartesianGrid, PolarGrid, DiscreteReceptor, MeteorologyPathway, OutputPathway,
]


def _is_number(tp) -> bool:
    args = [a for a in typing.get_args(tp) if a is not type(None)] or [tp]
    return all(a in (int, float) for a in args) and bool(args)


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_numbers_have_units_and_help(cls):
    hints = typing.get_type_hints(cls)
    missing = [f.name for f in dataclasses.fields(cls)
               if _is_number(hints[f.name]) and (units_of(f) is None or not help_of(f))]
    assert not missing, f"{cls.__name__} fields without units or help: {missing}"


@pytest.mark.parametrize(("cls", "name", "units"), [
    (PointSource, "stack_temp", "K"),
    (PointSource, "emission_rate", "g/s"),
    (AreaSource, "emission_rate", "g/(s·m²)"),
    (LineSource, "emission_rate", "g/(s·m²)"),
    (RLineSource, "emission_rate", "g/(s·m²)"),
    (RLineExtSource, "emission_rate", "g/(s·m)"),
    (PolarGrid, "dir_delta", "deg"),
    (PolarGrid, "dist_num", ""),
])
def test_units_follow_aermod(cls, name, units):
    # soset.f: LPARM and RLPARM read an emission rate per unit area (RLINE
    # multiplies it by the width); RLINEXT's Qemis is per unit length.
    fmeta = {f.name: f for f in dataclasses.fields(cls)}[name]
    assert units_of(fmeta) == units


def test_area_sides_are_lengths_not_half_widths():
    fields = {f.name: f for f in dataclasses.fields(AreaSource)}
    assert help_of(fields["initial_lateral_dimension"]).startswith("Xinit: length")
    assert help_of(fields["initial_vertical_dimension"]).startswith("Yinit: length")


def test_metadata_leaves_defaults_alone():
    src = PointSource("S1", 1.0, 2.0)
    assert (src.stack_height, src.stack_temp, src.emission_rate) == (0.0, 293.15, 1.0)
    assert MeteorologyPathway("a.sfc", "a.pfl").data_start_year == 2020
