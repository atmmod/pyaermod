"""Known-answer tests for :mod:`pyaermod.bpip` against EPA's BPIP-PRIME.

``pyaermod.bpip`` is a reimplementation, not a wrapper, so unlike the
AERMOD path it has no parity evidence by construction. These tests
supply it: they run EPA's own BPIP-PRIME Fortran and compare its
``SO BUILDHGT / BUILDWID / BUILDLEN / XBADJ / YBADJ`` output, direction
by direction, against what :class:`~pyaermod.bpip.BPIPCalculator`
computes for the same geometry.

Build the reference with ``scripts/build_bpip.sh`` (it lands in
``./bin``); everything here skips when ``bpipprm`` is not on PATH.

BPIP prints its downwash tables with ``F8.2``, so two implementations
that agree exactly still differ by up to 0.005 in the printed value.
That, and nothing looser, is the tolerance used below.

Scope note: :mod:`pyaermod.bpip` models a single single-tier building.
EPA BPIP also combines multiple structures and tiers per direction, so
those cases are out of scope here and for the module -- see its
docstring.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from pyaermod.bpip import BPIPCalculator, Building

BPIP_EXE = shutil.which("bpipprm")

pytestmark = pytest.mark.skipif(
    BPIP_EXE is None,
    reason="bpipprm not on PATH; build it with scripts/build_bpip.sh",
)

# BPIP writes the downwash tables with F8.2.
PRINT_TOL = 0.005 + 1e-9

PARAMS = (
    ("BUILDHGT", "buildhgt"),
    ("BUILDWID", "buildwid"),
    ("BUILDLEN", "buildlen"),
    ("XBADJ", "xbadj"),
    ("YBADJ", "ybadj"),
)


def run_reference(corners, height, stack_xy, stack_height=None):
    """Run EPA BPIP-PRIME on one building and one stack.

    EPA's source has its OPEN statements commented out, so unit 10 is
    read from ``./fort.10`` and the output tables land in ``./fort.12``.
    """
    sx, sy = stack_xy
    stack_height = stack_height if stack_height is not None else height * 1.5
    lines = [
        "'pyaermod known-answer case'",
        "'P'",
        "'METERS' 1.00",
        "'UTMN' 0.0",
        "1",
        "'BLD1' 1 0.00",
        f"{len(corners)} {height:.2f}",
        *[f" {x:.2f} {y:.2f}" for x, y in corners],
        "1",
        f"'STK' 0.00 {stack_height:.2f} {sx:.2f} {sy:.2f}",
    ]
    with tempfile.TemporaryDirectory() as work:
        Path(work, "fort.10").write_text("\n".join(lines) + "\n")
        subprocess.run([BPIP_EXE], cwd=work, capture_output=True, timeout=120)
        out = Path(work, "fort.12").read_text(encoding="latin-1")
    ref = {}
    for key, _ in PARAMS:
        values: list[float] = []
        for m in re.finditer(rf"SO {key}\s+STK\s+(.*)", out):
            values += [float(v) for v in m.group(1).split()]
        ref[key] = values
    return ref


def compare(corners, height, stack_xy, stack_height=None):
    """Return (n_compared, disagreements) for one geometry."""
    ref = run_reference(corners, height, stack_xy, stack_height)
    assert len(ref["BUILDHGT"]) == 36, (
        f"BPIP produced {len(ref['BUILDHGT'])} directions, not 36"
    )
    mine = BPIPCalculator(
        Building("BLD1", list(corners), height), *stack_xy
    ).calculate_all()

    bad = []
    for i in range(36):
        epa_live = ref["BUILDHGT"][i] > 0
        mine_live = mine.buildhgt[i] > 0
        if epa_live != mine_live:
            bad.append(
                f"dir {(i + 1) * 10}deg: EPA "
                f"{'applies' if epa_live else 'suppresses'} downwash, "
                f"pyaermod {'applies' if mine_live else 'suppresses'} it"
            )
            continue
        if not epa_live:
            continue
        for key, attr in PARAMS:
            d = abs(ref[key][i] - getattr(mine, attr)[i])
            if d > PRINT_TOL:
                bad.append(
                    f"dir {(i + 1) * 10}deg {key}: EPA {ref[key][i]}, "
                    f"pyaermod {getattr(mine, attr)[i]:.5f} (diff {d:.4f})"
                )
    return 36, bad


# ---------------------------------------------------------------------
# Exact agreement on the shapes a real deck contains
# ---------------------------------------------------------------------

RECTANGLE = [(-10.0, -20.0), (-10.0, 80.0), (40.0, 80.0), (40.0, -20.0)]
SQUARE = [(-15.0, -15.0), (15.0, -15.0), (15.0, 15.0), (-15.0, 15.0)]
# EPA BPIP User's Guide test case #1 -- six corners, which the old
# four-corners-only Building() could not represent at all.
L_SHAPE = [(-10.0, -20.0), (-10.0, 80.0), (40.0, 80.0),
           (40.0, 30.0), (90.0, 30.0), (90.0, -20.0)]

STACKS = [
    (15.0, 30.0),     # inside the footprint
    (45.0, 10.0),     # just outside one face
    (-30.0, 30.0),    # off the other side
    (15.0, 110.0),    # beyond one end
    (70.0, 70.0),     # off a corner
]


@pytest.mark.parametrize("stack", STACKS, ids=lambda s: f"{s[0]:g}_{s[1]:g}")
@pytest.mark.parametrize(
    "corners,height",
    [(RECTANGLE, 13.0), (SQUARE, 25.0), (L_SHAPE, 20.0)],
    ids=["rectangle", "square", "L-shape"],
)
def test_matches_epa_bpip(corners, height, stack):
    _, bad = compare(corners, height, stack)
    assert not bad, "disagrees with EPA BPIP-PRIME:\n  " + "\n  ".join(bad)


def test_l_shape_is_epa_test_case_one_geometry():
    """The six-corner footprint must actually be accepted.

    ``Building`` used to require exactly four corners, which rejected
    EPA's own first example. If that regressed, every L-shape case above
    would error rather than compare.
    """
    bld = Building("L", L_SHAPE, 20.0)
    assert len(bld.corners) == 6
    assert bld.get_footprint_area() == pytest.approx(50 * 100 + 50 * 50)


# ---------------------------------------------------------------------
# The influence zone
# ---------------------------------------------------------------------

def test_distant_stack_gets_no_downwash():
    """A stack far from the building must produce zeros, as EPA does.

    This is the failure that matters most: reporting real dimensions
    here makes AERMOD apply building downwash where the GEP influence
    zone says there is none.
    """
    ref = run_reference(RECTANGLE, 13.0, (400.0, 400.0))
    assert all(v == 0.0 for v in ref["BUILDHGT"]), "EPA reference changed"
    mine = BPIPCalculator(
        Building("BLD1", RECTANGLE, 13.0), 400.0, 400.0
    ).calculate_all()
    for attr in ("buildhgt", "buildwid", "buildlen", "xbadj", "ybadj"):
        assert all(v == 0.0 for v in getattr(mine, attr)), attr


def test_influence_test_can_be_disabled():
    """``influence_test=False`` returns raw geometry, for inspection."""
    raw = BPIPCalculator(
        Building("BLD1", RECTANGLE, 13.0), 400.0, 400.0, influence_test=False,
    ).calculate_all()
    assert all(v == pytest.approx(13.0) for v in raw.buildhgt)
    assert min(raw.buildwid) > 0.0


# ---------------------------------------------------------------------
# The conventions that were wrong before
# ---------------------------------------------------------------------

def test_xbadj_is_the_upwind_face_not_the_centroid():
    """For a stack at the building's centre XBADJ is -BUILDLEN/2.

    It was previously the projected centroid, which is zero here -- a
    silent, plausible-looking error of half the building length.
    """
    res = BPIPCalculator(Building("B", SQUARE, 25.0), 0.0, 0.0).calculate_all()
    for i in range(36):
        assert res.xbadj[i] == pytest.approx(-res.buildlen[i] / 2.0, abs=1e-9)
        assert res.ybadj[i] == pytest.approx(0.0, abs=1e-9)


def test_rotation_direction_is_visible_on_an_asymmetric_footprint():
    """A rectangle's projection hides a rotation-sign error; this doesn't.

    BUILDWID and BUILDLEN of an axis-aligned rectangle are symmetric in
    the wind direction, so the old code's inverted rotation produced the
    right widths and the wrong offsets. An asymmetric footprint makes
    the sign observable, which is why the reference comparison uses one.
    """
    corners = [(0.0, 0.0), (5.0, 70.0), (45.0, 55.0), (30.0, -5.0)]
    res = BPIPCalculator(Building("B", corners, 22.0), 50.0, 20.0)
    forward = res.calculate_all()
    mirrored = [
        BPIPCalculator(Building("B", corners, 22.0), 50.0, 20.0)
        ._calculate_for_direction(-(i + 1) * 10.0)["ybadj"]
        for i in range(36)
    ]
    assert forward.ybadj != pytest.approx(mirrored, abs=1e-6)


# ---------------------------------------------------------------------
# Broad sweep
# ---------------------------------------------------------------------

@pytest.mark.slow
def test_agreement_over_a_sweep_of_rotated_rectangles():
    """Rotated rectangles at many stack positions, against the reference.

    A rate rather than an all-or-nothing assertion, because a handful of
    directions land exactly on an influence-zone boundary where EPA's
    rounding and ours can fall either side. The floor is set well above
    what a real convention error could survive: reverting any one of the
    rotation sign, the XBADJ definition or the YBADJ definition drops
    this below 50%.
    """
    total = 0
    disagreements = 0
    for k in range(24):
        # Deterministic spread; no RNG, so a failure is reproducible.
        w = 20.0 + 5.0 * (k % 7)
        length = 25.0 + 7.0 * (k % 5)
        theta = math.radians(7.5 * k)
        height = 10.0 + 2.0 * (k % 11)
        corners = [
            (round(x * math.cos(theta) - y * math.sin(theta), 2),
             round(x * math.sin(theta) + y * math.cos(theta), 2))
            for x, y in ((-w / 2, -length / 2), (w / 2, -length / 2),
                         (w / 2, length / 2), (-w / 2, length / 2))
        ]
        stack = (round(-90.0 + 13.0 * k, 2), round(80.0 - 11.0 * k, 2))
        n, bad = compare(corners, height, stack)
        total += n
        disagreements += len(bad)
    rate = 1.0 - disagreements / total
    assert rate >= 0.98, (
        f"only {rate:.3%} of {total} direction comparisons matched EPA "
        f"BPIP-PRIME ({disagreements} disagreements)"
    )
