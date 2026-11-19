"""H-1: GEP stack height is Hg = H + 1.5 L, L the lesser of the building's height and projected
width, for a building within 5L of the stack (40 CFR 51.100(ii)), with a 65 m floor.

BPIPCalculator._gep is the quarter-degree sweep verified against EPA's BPIP output; prime's
36-sector shortcut must not exceed it.
"""

import warnings

import pytest

from pyaermod.bpip import BPIPCalculator, Building
from pyaermod.prime import gep_from_building

warnings.simplefilter("ignore")


def _square(height, half=5):
    return Building("B", [(-half, -half), (half, -half), (half, half), (-half, half)], height)


CASES = [
    (_square(60), 12.0, 0.0),             # tall narrow tower, stack 7 m from its face
    (_square(30), 20.0, 0.0),
    (_square(30), 100.0, 0.0),            # stack far outside every influence zone
    (_square(10, half=20), 40.0, 0.0),
]


@pytest.mark.parametrize("building,x,y", CASES)
def test_gep_from_building_matches_the_bpip_sweep_with_the_65_m_floor(building, x, y):
    swept = BPIPCalculator(building=building, stack_x=x, stack_y=y)._gep()
    expected = max(65.0, swept[0]) if swept else 65.0
    assert gep_from_building(building, x, y) == pytest.approx(expected, abs=0.5)


def test_a_tall_narrow_building_cannot_give_l_equal_to_its_height():
    # 10 m wide (14.1 m on the diagonal) and 60 m tall: L <= 14.2, so Hg <= 60 + 1.5 * 14.2 = 81.3 m.
    assert gep_from_building(_square(60), 12.0, 0.0) <= 81.3
