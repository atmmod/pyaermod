"""
examples/line_sources.py gives RLINE and LINE rates in AERMOD's units.

The example called the RLINE rate g/s/m and its width a half-lane, while
AERMOD (soset.f RLPARM, LPARM) reads Qemis in g/(s·m²) and multiplies it
by the full width. A deck written with "0.001 g/s/m" and a 3 m width
therefore emitted 0.003 g/s per metre of road instead of 0.001.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "line_sources.py"


@pytest.fixture
def example(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("line_sources_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _srcparam(deck: str, source_id: str):
    for line in deck.splitlines():
        fields = line.split()
        if fields[:2] == ["SRCPARAM", source_id]:
            return [float(v) for v in fields[2:]]
    raise AssertionError(f"no SRCPARAM for {source_id}")


@pytest.mark.parametrize("func, deck, source_id, per_metre, width", [
    ("example_1_single_road", "line_example_1_single_road.inp", "ROAD1", 0.001, 6.0),
    ("example_2_highway_interchange", "line_example_2_interchange.inp", "HWY_N", 0.003, 12.0),
    ("example_2_highway_interchange", "line_example_2_interchange.inp", "ROAD_E", 0.0015, 8.0),
])
def test_rline_rate_times_width_is_the_rate_per_metre(example, tmp_path, func, deck,
                                                      source_id, per_metre, width):
    getattr(example, func)()
    qemis, _height, deck_width, _sigz = _srcparam((tmp_path / deck).read_text(), source_id)
    assert deck_width == pytest.approx(width)
    assert qemis * deck_width == pytest.approx(per_metre, rel=1e-3)


def test_rline_width_field_is_the_full_width():
    from dataclasses import fields

    from pyaermod import RLineSource
    meta = {f.name: f.metadata for f in fields(RLineSource)}
    assert "g/(s·m²)" in str(meta["emission_rate"])
    assert "lane width / 2" not in Path(REPO / "src/pyaermod/sources.py").read_text()
