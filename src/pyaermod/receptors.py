"""
PyAERMOD Receptor dataclasses.

Contains CartesianGrid, PolarGrid, DiscreteReceptor, and the
ReceptorPathway collection.

This module is an internal implementation detail.  Public imports should go
through :mod:`pyaermod.input_generator` (the backwards-compatible facade)
or :mod:`pyaermod.api`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


def _num(value: float) -> str:
    """Shortest rendering that reads back to the same value."""
    return f"{value:.10g}"


def _row_lines(keyword: str, grid_name: str, sub: str,
               rows: List[List[float]]) -> List[str]:
    """``KEYWORD name SUB row v1 v2 ...`` lines, six values to a line.

    reset.f (TERHGT / HILHGT / FLGHGT) tags every value with the row in
    the field after the sub-keyword and accumulates over records, so a
    row may span lines.
    """
    out: List[str] = []
    for row_idx, row in enumerate(rows, start=1):
        for start in range(0, len(row), 6):
            vals = " ".join(f"{v:8.1f}" for v in row[start:start + 6])
            out.append(f"   {keyword}  {grid_name:<8} {sub}  {row_idx:5d}  {vals}")
    return out


def _list_lines(keyword: str, grid_name: str, sub: str,
                values: List[float], per_line: int = 10) -> List[str]:
    """``KEYWORD name SUB v1 v2 ...`` lines; AERMOD accumulates over lines."""
    return [
        f"   {keyword}  {grid_name:<8} {sub}  "
        + "  ".join(_num(v) for v in values[start:start + per_line])
        for start in range(0, len(values), per_line)
    ]


@dataclass
class CartesianGrid:
    """
    AERMOD Cartesian receptor grid (GRIDCART)

    Creates a regular rectangular grid of receptors.
    """
    grid_name: str = "GRID1"

    # X-axis definition
    x_init: float = 0.0
    x_num: int = 10
    x_delta: float = 100.0

    # Y-axis definition
    y_init: float = 0.0
    y_num: int = 10
    y_delta: float = 100.0

    # Elevation (optional)
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0

    # Per-receptor grid elevations from AERMAP (optional)
    # 2D arrays [row][col] where row = y-index, col = x-index
    grid_elevations: Optional[List[List[float]]] = None
    grid_hills: Optional[List[List[float]]] = None
    # Per-receptor flagpole heights (GRIDCART FLAG rows), same shape.
    grid_flags: Optional[List[List[float]]] = None

    # Explicit receptor coordinates (GRIDCART XPNTS / YPNTS). When set
    # they replace the x_init/x_num/x_delta (y_...) generator: AERMOD's
    # XYINC and XPNTS/YPNTS forms are exclusive within one network
    # (reset.f RECART, E180), and the writer emits whichever is in force.
    x_points: Optional[List[float]] = None
    y_points: Optional[List[float]] = None

    def x_values(self) -> List[float]:
        """The receptor x coordinates, explicit or generated."""
        if self.x_points is not None:
            return list(self.x_points)
        return [self.x_init + i * self.x_delta for i in range(self.x_num)]

    def y_values(self) -> List[float]:
        """The receptor y coordinates, explicit or generated."""
        if self.y_points is not None:
            return list(self.y_points)
        return [self.y_init + j * self.y_delta for j in range(self.y_num)]

    @property
    def receptor_count(self) -> int:
        return len(self.x_values()) * len(self.y_values())

    @classmethod
    def from_bounds(cls, x_min: float, x_max: float, y_min: float, y_max: float,
                   spacing: float = 100.0, grid_name: str = "GRID1") -> CartesianGrid:
        """Create grid from bounding box and spacing"""
        x_num = int((x_max - x_min) / spacing) + 1
        y_num = int((y_max - y_min) / spacing) + 1

        return cls(
            grid_name=grid_name,
            x_init=x_min,
            x_num=x_num,
            x_delta=spacing,
            y_init=y_min,
            y_num=y_num,
            y_delta=spacing
        )

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text.

        AERMOD requires GRIDCART blocks wrapped in STA/END:
            GRIDCART  name  STA
                            XYINC  ...
            GRIDCART  name  END
        """
        lines = [f"   GRIDCART  {self.grid_name:<8} STA"]
        if self.x_points is not None or self.y_points is not None:
            # Explicit coordinate lists; a missing side falls back to
            # the generator so the network is still complete.
            lines += _list_lines("GRIDCART", self.grid_name, "XPNTS", self.x_values())
            lines += _list_lines("GRIDCART", self.grid_name, "YPNTS", self.y_values())
        else:
            lines.append(
                f"                       XYINC  "
                f"{self.x_init:10.2f} {self.x_num:5d} {self.x_delta:8.2f}  "
                f"{self.y_init:10.2f} {self.y_num:5d} {self.y_delta:8.2f}"
            )
        # Per-receptor elevations / hill heights (from AERMAP) and
        # flagpole heights, one row (y index) per line group.
        if self.grid_elevations is not None:
            lines += _row_lines("GRIDCART", self.grid_name, "ELEV", self.grid_elevations)
        if self.grid_hills is not None:
            lines += _row_lines("GRIDCART", self.grid_name, "HILL", self.grid_hills)
        if self.grid_flags is not None:
            lines += _row_lines("GRIDCART", self.grid_name, "FLAG", self.grid_flags)
        lines.append(f"   GRIDCART  {self.grid_name:<8} END")
        return "\n".join(lines)


@dataclass
class PolarGrid:
    """
    AERMOD polar receptor grid (GRIDPOLR)

    Creates receptors in polar coordinates (distance and direction from origin).
    """
    grid_name: str = "GRID1"

    # Origin
    x_origin: float = 0.0
    y_origin: float = 0.0

    # Distance (radial)
    dist_init: float = 100.0
    dist_num: int = 10
    dist_delta: float = 100.0

    # Direction (degrees from north, clockwise)
    dir_init: float = 0.0
    dir_num: int = 36
    dir_delta: float = 10.0

    # Explicit ring distances (GRIDPOLR DIST is only ever a list in
    # AERMOD: reset.f POLDST reads every field as a distance) and
    # explicit directions (GRIDPOLR DDIR). When set they replace the
    # dist_*/dir_* generators; the generated distances are written out
    # as the list AERMOD expects, and the generated directions as
    # ``GDIR num init delta`` (GENPOL's field order).
    distances: Optional[List[float]] = None
    directions: Optional[List[float]] = None

    # ``GRIDPOLR name ORIG srcid`` centres the network on a source
    # instead of on x_origin/y_origin (POLORG accepts either form).
    origin_source_id: Optional[str] = None

    # Per-receptor elevations, hill heights and flagpole heights
    # (GRIDPOLR ELEV / HILL / FLAG), one row per direction, one value
    # per ring distance.
    elevations: Optional[List[List[float]]] = None
    hills: Optional[List[List[float]]] = None
    flags: Optional[List[List[float]]] = None

    def ring_distances(self) -> List[float]:
        """The ring distances, explicit or generated."""
        if self.distances is not None:
            return list(self.distances)
        return [self.dist_init + k * self.dist_delta for k in range(self.dist_num)]

    def direction_angles(self) -> List[float]:
        """The radial directions in degrees, explicit or generated."""
        if self.directions is not None:
            return list(self.directions)
        return [self.dir_init + m * self.dir_delta for m in range(self.dir_num)]

    @property
    def receptor_count(self) -> int:
        return len(self.ring_distances()) * len(self.direction_angles())

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text.

        AERMOD requires GRIDPOLR blocks wrapped in STA/END. The field
        layouts are those of reset.f: ``ORIG x y`` or ``ORIG srcid``,
        ``DIST d1 d2 ...`` (always a list), ``GDIR num init delta``
        (count first) or ``DDIR a1 a2 ...``. Before pyaermod 2.1 the
        writer emitted ``DIST init num delta`` and ``GDIR init num
        delta``; AERMOD read the former as three rings and the latter
        as zero directions, so the network had no receptors (RE E185).
        """
        name = self.grid_name
        lines = [f"   GRIDPOLR  {name:<8} STA"]
        if self.origin_source_id:
            lines.append(f"   GRIDPOLR  {name:<8} ORIG  {self.origin_source_id}")
        else:
            lines.append(
                f"   GRIDPOLR  {name:<8} ORIG  "
                f"{self.x_origin:10.2f} {self.y_origin:10.2f}"
            )
        lines += _list_lines("GRIDPOLR", name, "DIST", self.ring_distances())
        if self.directions is not None:
            lines += _list_lines("GRIDPOLR", name, "DDIR", self.directions)
        else:
            lines.append(
                f"   GRIDPOLR  {name:<8} GDIR  "
                f"{self.dir_num:d}  {_num(self.dir_init)}  {_num(self.dir_delta)}"
            )
        if self.elevations is not None:
            lines += _row_lines("GRIDPOLR", name, "ELEV", self.elevations)
        if self.hills is not None:
            lines += _row_lines("GRIDPOLR", name, "HILL", self.hills)
        if self.flags is not None:
            lines += _row_lines("GRIDPOLR", name, "FLAG", self.flags)
        lines.append(f"   GRIDPOLR  {name:<8} END")
        return "\n".join(lines)


@dataclass
class DiscreteReceptor:
    """Individual receptor at specific location"""
    x_coord: float
    y_coord: float
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0
    label: str = ""  # Optional user-friendly name (not sent to AERMOD)

    def to_aermod_input(self) -> str:
        """Generate AERMOD DISCCART line"""
        line = (
            f"   DISCCART  {self.x_coord:12.4f} {self.y_coord:12.4f} "
            f"{self.z_elev:8.2f}"
        )
        # Only include z_hill and z_flag for ELEVATED terrain (non-zero values)
        if self.z_hill != 0.0 or self.z_flag != 0.0:
            line += f" {self.z_hill:8.2f} {self.z_flag:8.2f}"
        return line


@dataclass
class ReceptorPathway:
    """Collection of receptor grids and discrete receptors"""
    cartesian_grids: List[CartesianGrid] = field(default_factory=list)
    polar_grids: List[PolarGrid] = field(default_factory=list)
    discrete_receptors: List[DiscreteReceptor] = field(default_factory=list)
    elevation_units: str = "METERS"

    def add_cartesian_grid(self, grid: CartesianGrid):
        """Add Cartesian grid"""
        self.cartesian_grids.append(grid)

    def add_polar_grid(self, grid: PolarGrid):
        """Add polar grid"""
        self.polar_grids.append(grid)

    def add_discrete_receptor(self, receptor: DiscreteReceptor):
        """Add discrete receptor"""
        self.discrete_receptors.append(receptor)

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text"""
        lines = ["RE STARTING"]

        # Elevation units (if not default)
        if self.elevation_units != "METERS":
            lines.append(f"   ELEVUNIT  {self.elevation_units}")

        # Cartesian grids
        for grid in self.cartesian_grids:
            lines.append(grid.to_aermod_input())

        # Polar grids
        for grid in self.polar_grids:
            lines.append(grid.to_aermod_input())

        # Discrete receptors
        for receptor in self.discrete_receptors:
            lines.append(receptor.to_aermod_input())

        lines.append("RE FINISHED")
        return "\n".join(lines)
