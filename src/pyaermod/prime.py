"""
PyAERMOD PRIME downwash helpers.

Utilities on top of bpip.py for building-interaction modeling:

- `gep_stack_height`: EPA Good Engineering Practice stack height per
  40 CFR 51.100(ii). Stacks shorter than GEP are subject to building
  downwash; stacks at GEP or above are exempt.

- `cavity_length`: Snyder (1981) / EPA PRIME cavity length estimate
  used to decide whether a receptor falls inside the wake cavity.

- `in_cavity_region`: True if a stack at (sx, sy, stack_height) is
  inside the building cavity for a given wind direction.

- `apply_bpip_to_project`: compute BPIP 36-sector arrays for each
  point source in an AERMODProject and populate the source fields.

- `suggest_downwash_config`: given a project, warn about sources that
  (a) are nominally "downwashed" but stack height > GEP, or (b) are
  below GEP but have no building data set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from .bpip import BPIPCalculator, BPIPResult, Building

# ---------------------------------------------------------------------------
# GEP stack-height rule
# ---------------------------------------------------------------------------

GEP_FLOOR_M = 65.0  # 40 CFR 51.100(ii) — GEP is at least 65 m


def gep_stack_height(building_height: float,
                     lesser_dim: float) -> float:
    """Return GEP stack height in meters.

    `lesser_dim` is the lesser of building height or projected building
    width (also called "L"). Formula: max(65, BH + 1.5 * L).

    For a complex building, use the *maximum* BH + 1.5 L across all
    relevant wind sectors, or call `gep_from_building` below.
    """
    if building_height < 0 or lesser_dim < 0:
        raise ValueError("building_height and lesser_dim must be >= 0")
    return max(GEP_FLOOR_M, building_height + 1.5 * lesser_dim)


def gep_from_building(building: Building,
                      stack_x: float,
                      stack_y: float) -> float:
    """Compute GEP stack height from a Building + stack location.

    Uses `BPIPCalculator.calculate_all` to obtain the 36-sector projected
    widths, then returns max(65, BH + 1.5 * L) where L is the *largest*
    of (building height, max projected width across sectors).
    """
    bh = building.get_effective_height()
    calc = BPIPCalculator(building=building, stack_x=stack_x, stack_y=stack_y)
    result = calc.calculate_all()
    max_width = max(result.buildwid) if result.buildwid else 0.0
    L = min(bh, max_width) if max_width > 0 else bh
    return gep_stack_height(bh, L)


# ---------------------------------------------------------------------------
# Cavity / wake region (simplified Snyder / PRIME)
# ---------------------------------------------------------------------------

def cavity_length(building_height: float, building_width: float) -> float:
    """Simplified PRIME cavity length, meters.

    PRIME uses Lc = A * H * (W/H)^0.3 / (1 + B * (W/H)) with A=1.8, B=0.24
    for a rectangular building with height H and width W (across-wind).
    This is an approximation sufficient for *screening*; AERMOD's PRIME
    module does the rigorous computation at runtime.
    """
    if building_height <= 0 or building_width <= 0:
        return 0.0
    ratio = building_width / building_height
    A, B = 1.8, 0.24
    return A * building_height * (ratio ** 0.3) / (1.0 + B * ratio)


def in_cavity_region(stack_x: float, stack_y: float, stack_height: float,
                     building: Building,
                     wind_direction_deg: float) -> bool:
    """True if the stack sits inside the projected wake cavity.

    Uses the building centroid + 36-sector width to estimate the
    downwind cavity extent. A stack whose (horizontal distance from
    building) < cavity_length AND whose height < building_height is
    "in cavity".
    """
    cx, cy = building.get_centroid()
    bh = building.get_effective_height()
    if stack_height >= bh:
        return False

    # Distance from stack to building centroid along the wind vector
    wind_rad = math.radians(270.0 - wind_direction_deg)  # met -> math
    dx = stack_x - cx
    dy = stack_y - cy
    # Downwind distance: projection of (stack - centroid) onto wind vector
    downwind = dx * math.cos(wind_rad) + dy * math.sin(wind_rad)
    if downwind <= 0:
        return False  # upwind of building — no cavity impact

    calc = BPIPCalculator(building=building, stack_x=stack_x, stack_y=stack_y)
    params = calc._calculate_for_direction(wind_direction_deg)
    width = params.get("buildwid", 0.0)
    Lc = cavity_length(bh, width)
    return downwind < Lc


# ---------------------------------------------------------------------------
# Project-level convenience
# ---------------------------------------------------------------------------

@dataclass
class DownwashAssessment:
    """Result of evaluating a point source against nearby buildings."""
    source_id: str
    stack_height_m: float
    gep_height_m: float
    is_below_gep: bool
    affected_by_building: Optional[str]
    note: str = ""


def assess_source_downwash(point_source: Any,
                           buildings: Iterable[Building]) -> DownwashAssessment:
    """Evaluate one PointSource against a collection of Buildings.

    Returns a DownwashAssessment capturing the GEP stack height, whether
    the source is below it, and which building (if any) most likely
    influences the plume.
    """
    sx = point_source.x_coord
    sy = point_source.y_coord
    sh = point_source.stack_height

    # Distance & GEP from nearest-5L building
    nearest: Optional[Tuple[float, Building, float]] = None
    for b in buildings:
        cx, cy = b.get_centroid()
        d = math.hypot(sx - cx, sy - cy)
        bh = b.get_effective_height()
        # 5L rule: if stack within 5 * (lesser dim) we consider it affected
        calc = BPIPCalculator(building=b, stack_x=sx, stack_y=sy)
        max_w = max(calc.calculate_all().buildwid) if b.height > 0 else 0.0
        L = min(bh, max_w) if max_w > 0 else bh
        if d <= 5 * L and (nearest is None or d < nearest[0]):
            nearest = (d, b, gep_from_building(b, sx, sy))

    if nearest is None:
        gep = GEP_FLOOR_M
        return DownwashAssessment(
            source_id=point_source.source_id,
            stack_height_m=sh,
            gep_height_m=gep,
            is_below_gep=sh < gep,
            affected_by_building=None,
            note="no building within 5L; downwash not expected",
        )

    _, bldg, gep = nearest
    return DownwashAssessment(
        source_id=point_source.source_id,
        stack_height_m=sh,
        gep_height_m=gep,
        is_below_gep=sh < gep,
        affected_by_building=bldg.building_id,
        note=("stack below GEP — downwash must be modeled"
              if sh < gep else
              "stack at/above GEP — exempt from downwash per GEP rule"),
    )


def apply_bpip_to_project(project: Any,
                          buildings: List[Building],
                          *,
                          only_below_gep: bool = True) -> List[DownwashAssessment]:
    """Compute BPIP arrays for every PointSource in the project.

    For each source, pick the single building with the largest
    interaction (shortest distance within 5L), run BPIPCalculator,
    and assign the 36-value arrays to the source.

    When `only_below_gep=True` (default), sources already at or above
    GEP height are left alone (per EPA guidance, they're exempt).

    Returns the list of DownwashAssessments, one per source.
    """
    assessments: List[DownwashAssessment] = []
    point_sources = [
        s for s in getattr(project.sources, "sources", [])
        if type(s).__name__ == "PointSource"
    ]
    for src in point_sources:
        assess = assess_source_downwash(src, buildings)
        assessments.append(assess)
        if only_below_gep and not assess.is_below_gep:
            continue
        if assess.affected_by_building is None:
            continue
        building = next(
            b for b in buildings if b.building_id == assess.affected_by_building
        )
        calc = BPIPCalculator(
            building=building, stack_x=src.x_coord, stack_y=src.y_coord
        )
        result = calc.calculate_all()
        src.building_height = list(result.buildhgt)
        src.building_width = list(result.buildwid)
        src.building_length = list(result.buildlen)
        src.building_x_offset = list(result.xbadj)
        src.building_y_offset = list(result.ybadj)
    return assessments


def suggest_downwash_config(project: Any,
                            buildings: List[Building]) -> List[str]:
    """Return human-readable warnings about the project's downwash setup.

    Flags:
    - Source below GEP with no building data assigned.
    - Source at/above GEP with building arrays set (wasted work).
    - Mixed array lengths (must be 36).
    """
    warnings: List[str] = []
    for src in getattr(project.sources, "sources", []):
        if type(src).__name__ != "PointSource":
            continue
        assess = assess_source_downwash(src, buildings)
        bh = getattr(src, "building_height", None)
        has_bldg_data = isinstance(bh, list) and len(bh) == 36

        if assess.is_below_gep and not has_bldg_data:
            warnings.append(
                f"{src.source_id}: stack ({src.stack_height} m) is below GEP "
                f"({assess.gep_height_m:.1f} m) but no 36-sector building "
                f"data set; downwash effects will be missed."
            )
        elif (not assess.is_below_gep) and has_bldg_data:
            warnings.append(
                f"{src.source_id}: stack at/above GEP but building data is set; "
                f"AERMOD will still apply downwash — consider removing to "
                f"reduce runtime, or leave if conservatism is desired."
            )

        # Length sanity
        for field_name in ("building_height", "building_width", "building_length",
                           "building_x_offset", "building_y_offset"):
            val = getattr(src, field_name, None)
            if isinstance(val, list) and len(val) != 36:
                warnings.append(
                    f"{src.source_id}: {field_name} has {len(val)} values "
                    "(expected 36)."
                )
    return warnings


__all__ = [
    "GEP_FLOOR_M",
    "gep_stack_height",
    "gep_from_building",
    "cavity_length",
    "in_cavity_region",
    "DownwashAssessment",
    "assess_source_downwash",
    "apply_bpip_to_project",
    "suggest_downwash_config",
]
