"""
PyAERMOD BPIP Module - Building Profile Input Program Calculations

Computes direction-dependent building dimensions for AERMOD's PRIME
downwash algorithm. AERMOD requires 36 values (one per 10° wind sector)
for each building parameter: BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ.

This module provides:
  - Building: rectangular building geometry definition
  - BPIPCalculator: direction-dependent projection engine
  - BPIPResult: container for the 36-value arrays

This is verified against EPA's own BPIP-PRIME Fortran
(``bpipprime.zip`` on SCRAM), which reproduces EPA's shipped reference
output for all eight of its example cases. Within the scope below the
agreement is exact -- every direction, to the 0.005 that BPIP's F8.2
output can express. See ``tests/test_bpip_known_answers.py``.

Two things here are not pure projection geometry, and both come
straight from ``Bpipprm.for`` rather than from first principles:

* the two influence tests (:meth:`BPIPCalculator._in_downwash_zone` and
  :meth:`BPIPCalculator._in_gep_zone`), which differ from each other; and
* the GEP clamp -- when a direction's wake-effect height would exceed
  the stack's GEP stack height, BPIP reports the GEP-controlling
  structure's height and width instead of that direction's projection.
  This produces a flat cap across a run of directions that depends on
  the *stack position*, not on the footprint alone.

**Scope.** This module covers a *single* building with a single tier.
EPA BPIP additionally combines multiple structures and tiers, choosing
the controlling combination per wind direction, and reports GEP stack
heights. For a regulatory submittal, run EPA's BPIP-PRIME and use its
output; this module is for building decks, screening and
what-if geometry work.

Reference: EPA BPIP User's Guide, AERMOD Implementation Guide (Section 3.3)
"""

import math
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# BPIP applies two different influence tests, and conflating them gets
# both wrong. Both are transcribed from EPA's ``Bpipprm.for``.
#
# The *downwash* test (the ``DO 300`` loop) decides whether a direction
# gets downwash parameters at all: the stack must be within half an
# ``L`` of either edge of the projected width, and no more than ``2 L``
# upwind of the building's near face. Note there is no downwind limit --
# BPIP computes ``CYMX = YMAX + 5 L`` and then never tests against it.
SIZ_LATERAL_L = 0.5
SIZ_UPWIND_L = 2.0

# The *GEP* test (the ``DO 100`` quarter-degree sweep) is stricter, and
# only decides which directions contribute to the GEP stack height: the
# stack must be within the projected width proper, downwind of the near
# face, and within ``5 L`` of one of the faces (``DISLIN``).
SIZ_DOWNWIND_L = 5.0

#: The GEP stack height is ``H + 1.5 L``. BPIP evaluates it on a
#: quarter-degree sweep (``DO 100 D = 1, 1440`` in ``Bpipprm.for``),
#: which is far finer than the 36 directions it reports, so the
#: controlling width is usually not one of the reported widths.
GEP_WAKE_FACTOR = 1.5
GEP_SWEEP_STEPS = 1440


@dataclass
class Building:
    """
    Rectangular building footprint for BPIP calculations.

    Parameters
    ----------
    building_id : str
        Identifier for this building (e.g., "BLDG1").
    corners : list of (float, float)
        Corner coordinates of the footprint polygon, in the same
        coordinate system as sources/receptors (typically UTM meters).
        Three or more; EPA's own test cases include a six-corner L-shape.
    height : float
        Building height in meters (above ground level).
    tiers : list of (float, float), optional
        Multi-tier definition as (tier_height, coverage_fraction) pairs.
        Each tier_height must exceed the base height. Coverage fraction
        is the proportion of the footprint covered by that tier (0-1).
        If omitted, the building is treated as a single-tier structure.
    """
    building_id: str
    corners: List[Tuple[float, float]]
    height: float
    tiers: Optional[List[Tuple[float, float]]] = None

    def __post_init__(self):
        if len(self.corners) < 3:
            raise ValueError(
                f"Building requires at least 3 corners, got {len(self.corners)}"
            )
        if self.height <= 0:
            raise ValueError(
                f"Building height must be positive, got {self.height}"
            )
        if self.tiers is not None:
            for tier_height, fraction in self.tiers:
                if tier_height <= self.height:
                    raise ValueError(
                        f"Tier height ({tier_height}) must exceed base height ({self.height})"
                    )
                if not (0.0 < fraction <= 1.0):
                    raise ValueError(
                        f"Coverage fraction must be in (0, 1], got {fraction}"
                    )

    def get_effective_height(self) -> float:
        """
        Effective building height for downwash calculations.

        For single-tier buildings, returns the base height.
        For multi-tier, returns the coverage-fraction-weighted average
        of all tier heights plus the base contribution.
        """
        if self.tiers is None or len(self.tiers) == 0:
            return self.height

        total_fraction = sum(f for _, f in self.tiers)
        base_fraction = max(0.0, 1.0 - total_fraction)

        weighted = self.height * base_fraction
        for tier_height, fraction in self.tiers:
            weighted += tier_height * fraction

        return weighted

    def get_footprint_area(self) -> float:
        """
        Compute footprint area using the shoelace formula.

        Returns
        -------
        float
            Area of the footprint polygon in square meters.
        """
        n = len(self.corners)
        area = 0.0
        for i in range(n):
            x1, y1 = self.corners[i]
            x2, y2 = self.corners[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def get_centroid(self) -> Tuple[float, float]:
        """
        Compute centroid (average of corner coordinates).

        Returns
        -------
        tuple of (float, float)
            (x, y) centroid coordinates.
        """
        cx = sum(x for x, _ in self.corners) / len(self.corners)
        cy = sum(y for _, y in self.corners) / len(self.corners)
        return (cx, cy)


@dataclass
class BPIPResult:
    """
    Container for 36 direction-dependent building parameters.

    Each list contains exactly 36 values corresponding to wind directions
    10°, 20°, ..., 360° (measured clockwise from north).
    """
    buildhgt: List[float] = field(default_factory=list)
    buildwid: List[float] = field(default_factory=list)
    buildlen: List[float] = field(default_factory=list)
    xbadj: List[float] = field(default_factory=list)
    ybadj: List[float] = field(default_factory=list)


class BPIPCalculator:
    """
    Computes direction-dependent building dimensions for AERMOD PRIME.

    For each of 36 wind directions (10° increments), the algorithm:

    1. Translates building corners so the stack is at the origin
    2. Rotates corners to align the wind direction with the +Y axis
    3. Computes projected width (perpendicular to wind) and length (along wind)
    4. Computes XBADJ (along-flow coordinate of the upwind face) and
       YBADJ (negated crosswind midpoint of the projection)
    5. Zeroes all five values when the stack is outside the GEP
       structure influence zone

    Parameters
    ----------
    building : Building
        The building geometry.
    stack_x : float
        X-coordinate of the affected stack.
    stack_y : float
        Y-coordinate of the affected stack.
    influence_test : bool, keyword-only, default True
        Apply the GEP structure influence zone test. Set False only to
        inspect raw projected geometry; a deck built with it off will
        apply downwash where EPA BPIP applies none.
    """

    def __init__(self, building: Building, stack_x: float, stack_y: float,
                 *, influence_test: bool = True):
        self.building = building
        self.stack_x = stack_x
        self.stack_y = stack_y
        self.influence_test = influence_test
        self._gep_cache: Optional[Tuple[float, float, float]] = None
        self._gep_done = False
        if building.tiers:
            warnings.warn(
                f"Building {building.building_id!r} declares tiers; this "
                "module collapses them to one coverage-weighted height. "
                "EPA BPIP instead evaluates each tier and picks the "
                "controlling one per wind direction, so multi-tier "
                "results here are an approximation -- run EPA BPIP-PRIME "
                "for a regulatory submittal.",
                stacklevel=2,
            )

    @staticmethod
    def _rotate_point(x: float, y: float, angle_rad: float) -> Tuple[float, float]:
        """
        Rotate point (x, y) counterclockwise by angle_rad.

        Parameters
        ----------
        x, y : float
            Point coordinates.
        angle_rad : float
            Rotation angle in radians (positive = counterclockwise).

        Returns
        -------
        tuple of (float, float)
            Rotated (x', y') coordinates.
        """
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        xr = x * cos_a - y * sin_a
        yr = x * sin_a + y * cos_a
        return (xr, yr)

    def _calculate_for_direction(self, wind_direction_deg: float) -> dict:
        """Calculate building parameters for a single wind direction.

        The footprint is translated so the stack sits at the origin and
        rotated by ``+wind_direction_deg`` so the flow runs along the
        ``+y`` axis. In that frame BPIP defines:

        - ``BUILDWID`` -- the crosswind extent of the projected footprint;
        - ``BUILDLEN`` -- the along-flow extent;
        - ``XBADJ``    -- the along-flow coordinate of the projected
          building's *upwind face*, i.e. ``min(y)``. Not the centroid:
          for a stack at the building's centre this is
          ``-BUILDLEN / 2``, not zero;
        - ``YBADJ``    -- the negated crosswind midpoint of the
          projection, ``-(max(x) + min(x)) / 2``.

        When the stack falls outside the GEP structure influence zone
        all five values are zero, which is how BPIP reports "this
        building does not cause downwash here". Emitting real dimensions
        instead would make AERMOD apply downwash the regulation does not.

        Parameters
        ----------
        wind_direction_deg : float
            Wind direction in degrees (0-360, clockwise from north).

        Returns
        -------
        dict with keys: buildhgt, buildwid, buildlen, xbadj, ybadj
        """
        corners = self._projection(wind_direction_deg)
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]

        cross_lo, cross_hi = min(xs), max(xs)
        along_lo, along_hi = min(ys), max(ys)

        buildwid = cross_hi - cross_lo
        buildlen = along_hi - along_lo
        height = self.building.get_effective_height()

        if self.influence_test:
            # BPIP gates the whole downwash calculation on GEPIN, which is
            # set only for a stack that fell inside the structure's GEP
            # 5L area at some direction during the GEP sweep. A stack
            # that is never within 5L of the building gets zeros for
            # every direction, however the wind blows.
            gep = self._gep()
            if gep is None or not self._in_downwash_zone(corners, height):
                return {"buildhgt": 0.0, "buildwid": 0.0, "buildlen": 0.0,
                        "xbadj": 0.0, "ybadj": 0.0}
            wake = height + GEP_WAKE_FACTOR * min(height, buildwid)
            if gep[0] < wake:
                # This direction's wake would reach above the stack's GEP
                # stack height, so BPIP reports the GEP-controlling
                # structure instead (MXBWH in Bpipprm.for). Length and
                # the offsets stay as projected -- only the height and
                # width are substituted.
                height, buildwid = gep[1], gep[2]

        return {
            "buildhgt": height,
            "buildwid": buildwid,
            "buildlen": buildlen,
            "xbadj": along_lo,
            "ybadj": -(cross_hi + cross_lo) / 2.0,
        }

    @staticmethod
    def _downwind_of_side_within(
        x1: float, y1: float, x2: float, y2: float,
        reach: float, sx: float, sy: float,
    ) -> bool:
        """``DISLIN``: is the stack directly downwind of this side, within ``reach``?

        The stack must lie between the side's crosswind endpoints -- so
        it is genuinely behind *that* face, not past its end -- and the
        along-flow gap from the side to the stack must be between zero
        and ``reach``.
        """
        if sx < min(x1, x2) or sx > max(x1, x2):
            return False
        if x1 == x2:
            # A side seen edge-on: only a stack exactly in line with it
            # is downwind of it at all.
            if sx != x1:
                return False
            return any(0.0 <= sy - y <= reach for y in (y1, y2))
        y_on_side = y2 + (sx - x2) * (y1 - y2) / (x1 - x2)
        return 0.0 <= sy - y_on_side <= reach

    @staticmethod
    def _in_downwash_zone(
        corners: List[Tuple[float, float]], height: float,
    ) -> bool:
        """True when this direction gets downwash parameters at all.

        ``corners`` are translated so the stack is the origin and rotated
        so the flow runs along ``+y``; the building therefore sits at
        negative ``y`` when it is upwind of the stack.
        """
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        scale = min(height, max(xs) - min(xs))
        if scale <= 0.0:
            return False
        tol = 1e-9
        within_width = (
            min(xs) - SIZ_LATERAL_L * scale - tol
            <= 0.0
            <= max(xs) + SIZ_LATERAL_L * scale + tol
        )
        not_too_far_upwind = min(ys) - SIZ_UPWIND_L * scale - tol <= 0.0
        return within_width and not_too_far_upwind

    @classmethod
    def _in_gep_zone(
        cls, corners: List[Tuple[float, float]], height: float,
    ) -> bool:
        """True when this direction contributes to the GEP stack height."""
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        if not (min(xs) <= 0.0 <= max(xs)):
            return False
        if min(ys) > 0.0:
            return False
        reach = SIZ_DOWNWIND_L * min(height, max(xs) - min(xs))
        if reach <= 0.0:
            return False
        n = len(corners)
        return any(
            cls._downwind_of_side_within(
                *corners[i], *corners[(i + 1) % n], reach, 0.0, 0.0
            )
            for i in range(n)
        )

    def _projection(self, wind_direction_deg: float) -> List[Tuple[float, float]]:
        """Footprint corners with the stack at the origin, flow along +y."""
        rotation_rad = math.radians(wind_direction_deg)
        return [
            self._rotate_point(
                cx - self.stack_x, cy - self.stack_y, rotation_rad
            )
            for cx, cy in self.building.corners
        ]

    def _gep(self) -> Optional[Tuple[float, float, float]]:
        """``(GEP stack height, controlling height, controlling width)``.

        BPIP sweeps every quarter degree and keeps the direction with the
        greatest wake-effect height ``H + 1.5 L``; ties go to the
        *smaller* projected width (``GPC`` in ``Bpipprm.for``). Only
        directions where the stack is in the influence zone count.

        Returns None when no direction influences the stack.
        """
        if self._gep_done:
            return self._gep_cache
        height = self.building.get_effective_height()
        best: Optional[Tuple[float, float, float]] = None
        for step in range(1, GEP_SWEEP_STEPS + 1):
            corners = self._projection(step * 360.0 / GEP_SWEEP_STEPS)
            if not self._in_gep_zone(corners, height):
                continue
            xs = [c[0] for c in corners]
            width = max(xs) - min(xs)
            wake = height + GEP_WAKE_FACTOR * min(height, width)
            if best is None or wake > best[0] + 1e-9:
                best = (wake, height, width)
            elif abs(wake - best[0]) <= 1e-9 and width < best[2]:
                best = (best[0], best[1], width)
        self._gep_cache = best
        self._gep_done = True
        return best

    def calculate_all(self) -> BPIPResult:
        """
        Calculate building parameters for all 36 wind directions.

        Directions are 10°, 20°, ..., 360° (AERMOD convention).

        Returns
        -------
        BPIPResult
            Contains 36-value arrays for each building parameter.
        """
        result = BPIPResult()

        for i in range(36):
            wind_dir = (i + 1) * 10.0  # 10, 20, ..., 360
            params = self._calculate_for_direction(wind_dir)

            result.buildhgt.append(params["buildhgt"])
            result.buildwid.append(params["buildwid"])
            result.buildlen.append(params["buildlen"])
            result.xbadj.append(params["xbadj"])
            result.ybadj.append(params["ybadj"])

        return result
