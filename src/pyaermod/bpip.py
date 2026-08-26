"""
PyAERMOD BPIP Module - Building Profile Input Program Calculations

Computes direction-dependent building dimensions for AERMOD's PRIME
downwash algorithm. AERMOD requires 36 values (one per 10° wind sector)
for each building parameter: BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ.

This module provides:
  - Building: rectangular building geometry definition
  - BPIPCalculator: direction-dependent projection engine
  - BPIPResult: container for the 36-value arrays

The geometry here is verified against EPA's own BPIP-PRIME Fortran
(``bpipprime.zip`` on SCRAM), which reproduces EPA's shipped reference
output for all eight of its example cases. See
``tests/test_bpip_known_answers.py``.

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

#: Multipliers defining the GEP structure influence zone, in units of
#: ``L`` (the lesser of building height and projected building width).
#: A stack outside this zone gets no downwash for that wind direction --
#: BPIP writes zeros for all five parameters. Fitted against EPA's
#: BPIP-PRIME over 504 stack/direction combinations, where the observed
#: boundaries fall at exactly 5.000 L and 2.000 L.
SIZ_DOWNWIND_L = 5.0
SIZ_UPWIND_L = 2.0
SIZ_LATERAL_L = 0.5


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
        rotation_rad = math.radians(wind_direction_deg)

        xs: List[float] = []
        ys: List[float] = []
        for cx, cy in self.building.corners:
            rx, ry = self._rotate_point(
                cx - self.stack_x, cy - self.stack_y, rotation_rad
            )
            xs.append(rx)
            ys.append(ry)

        cross_lo, cross_hi = min(xs), max(xs)
        along_lo, along_hi = min(ys), max(ys)

        buildwid = cross_hi - cross_lo
        buildlen = along_hi - along_lo
        height = self.building.get_effective_height()

        if self.influence_test and not self._in_influence_zone(
            height, buildwid, cross_lo, cross_hi, along_lo, along_hi
        ):
            return {"buildhgt": 0.0, "buildwid": 0.0, "buildlen": 0.0,
                    "xbadj": 0.0, "ybadj": 0.0}

        return {
            "buildhgt": height,
            "buildwid": buildwid,
            "buildlen": buildlen,
            "xbadj": along_lo,
            "ybadj": -(cross_hi + cross_lo) / 2.0,
        }

    @staticmethod
    def _in_influence_zone(
        height: float, buildwid: float,
        cross_lo: float, cross_hi: float,
        along_lo: float, along_hi: float,
    ) -> bool:
        """True when the stack (at the origin) is in the GEP influence zone.

        ``L`` is the lesser of the building height and its projected
        width. The stack must lie within ``5 L`` downwind of the
        building's downwind face, ``2 L`` upwind of its upwind face, and
        ``0.5 L`` beyond either edge of the projected width.
        """
        scale = min(height, buildwid)
        if scale <= 0.0:
            return False
        downwind = -along_hi          # how far past the downwind face
        upwind = along_lo             # how far short of the upwind face
        lateral = max(cross_lo, -cross_hi, 0.0)
        tol = 1e-9
        return (
            downwind <= SIZ_DOWNWIND_L * scale + tol
            and upwind <= SIZ_UPWIND_L * scale + tol
            and lateral <= SIZ_LATERAL_L * scale + tol
        )

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
