"""G5: the vertex editor must read the space-separated pairs AERMOD's own AREAVERT uses."""

from pyaermod.gui_v2._form import _parse_pairs
from pyaermod.input_generator import AreaPolySource


def test_space_separated_vertices_are_read():
    assert _parse_pairs("100 200\n300 400\n300 500") == [(100.0, 200.0), (300.0, 400.0), (300.0, 500.0)]


def test_the_decks_own_vertex_text_round_trips_through_the_editor():
    src = AreaPolySource(source_id="A", vertices=[(0, 0), (10, 0), (10, 10)], emission_rate=1,
                         release_height=2)
    (line,) = [ln for ln in src.to_aermod_input().splitlines() if "AREAVERT" in ln]
    nums = line.split()[2:]                      # x1 y1 x2 y2 ... as the deck writes them
    text = "\n".join(f"{nums[i]} {nums[i + 1]}" for i in range(0, len(nums), 2))
    assert _parse_pairs(text) == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
