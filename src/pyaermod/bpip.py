"""
PyAERMOD BPIP Module - Building Profile Input Program Calculations

Computes direction-dependent building dimensions for AERMOD's PRIME
downwash algorithm. AERMOD requires 36 values (one per 10° wind sector)
for each building parameter: BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ.

This module provides:
  - Building: rectangular building geometry definition
  - BPIPCalculator: direction-dependent projection engine
  - BPIPResult: container for the 36-value arrays

Reference: EPA BPIP User's Guide, AERMOD Implementation Guide (Section 3.3)
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Building:
    """
    Rectangular building footprint for BPIP calculations.

    Parameters
    ----------
    building_id : str
        Identifier for this building (e.g., "BLDG1").
    corners : list of (float, float)
        Four (x, y) corner coordinates defining the rectangular footprint,
        in the same coordinate system as sources/receptors (typically UTM meters).
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
        if len(self.corners) != 4:
            raise ValueError(
                f"Building requires exactly 4 corners, got {len(self.corners)}"
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
            Area of the quadrilateral in square meters.
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
    4. Computes XBADJ/YBADJ offsets from the projected building centroid

    Parameters
    ----------
    building : Building
        The building geometry.
    stack_x : float
        X-coordinate of the affected stack.
    stack_y : float
        Y-coordinate of the affected stack.
    """

    def __init__(self, building: Building, stack_x: float, stack_y: float):
        self.building = building
        self.stack_x = stack_x
        self.stack_y = stack_y

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
        """
        Calculate building parameters for a single wind direction.

        The wind direction is in degrees clockwise from north (meteorological
        convention). We rotate the coordinate system so the wind blows
        along the +Y axis, then compute projected width (X-extent) and
        length (Y-extent).

        Parameters
        ----------
        wind_direction_deg : float
            Wind direction in degrees (0-360, clockwise from north).

        Returns
        -------
        dict with keys: buildhgt, buildwid, buildlen, xbadj, ybadj
        """
        # Convert wind direction to rotation angle
        # Wind from direction D means wind blows FROM D degrees.
        # To align wind with +Y axis, rotate by -D degrees.
        # Meteorological degrees are clockwise from north, but math rotation
        # is counterclockwise, so we rotate by +D in math convention.
        rotation_rad = math.radians(wind_direction_deg)

        # Translate corners so stack is at origin, then rotate
        rotated_corners = []
        for cx, cy in self.building.corners:
            tx = cx - self.stack_x
            ty = cy - self.stack_y
            rx, ry = self._rotate_point(tx, ty, -rotation_rad)
            rotated_corners.append((rx, ry))

        # Projected width = extent perpendicular to wind (X-direction)
        xs = [c[0] for c in rotated_corners]
        ys = [c[1] for c in rotated_corners]

        buildwid = max(xs) - min(xs)
        buildlen = max(ys) - min(ys)

        # Building centroid in rotated frame
        cx_rot = sum(xs) / len(xs)
        cy_rot = sum(ys) / len(ys)

        # XBADJ: offset of building center from stack perpendicular to wind
        # YBADJ: offset of building center from stack along wind
        # In the rotated frame, stack is at origin, so offsets are just
        # the centroid coordinates. Positive XBADJ = building center to the
        # right of stack (looking downwind), positive YBADJ = downwind.
        xbadj = cx_rot
        ybadj = cy_rot

        return {
            "buildhgt": self.building.get_effective_height(),
            "buildwid": buildwid,
            "buildlen": buildlen,
            "xbadj": xbadj,
            "ybadj": ybadj,
        }

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
