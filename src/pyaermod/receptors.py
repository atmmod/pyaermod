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
        lines = [
            f"   GRIDCART  {self.grid_name:<8} STA",
            f"                       XYINC  "
            f"{self.x_init:10.2f} {self.x_num:5d} {self.x_delta:8.2f}  "
            f"{self.y_init:10.2f} {self.y_num:5d} {self.y_delta:8.2f}",
        ]

        # Per-receptor elevations (from AERMAP output)
        if self.grid_elevations is not None:
            for row_idx, row in enumerate(self.grid_elevations):
                # AERMOD format: 6 values per line, F8.1
                for chunk_start in range(0, len(row), 6):
                    chunk = row[chunk_start : chunk_start + 6]
                    val_str = " ".join(f"{v:8.1f}" for v in chunk)
                    lines.append(
                        f"   GRIDCART  {self.grid_name:<8} ELEV  "
                        f"{row_idx + 1:5d}  {val_str}"
                    )

        # Per-receptor hill heights (from AERMAP output)
        if self.grid_hills is not None:
            for row_idx, row in enumerate(self.grid_hills):
                for chunk_start in range(0, len(row), 6):
                    chunk = row[chunk_start : chunk_start + 6]
                    val_str = " ".join(f"{v:8.1f}" for v in chunk)
                    lines.append(
                        f"   GRIDCART  {self.grid_name:<8} HILL  "
                        f"{row_idx + 1:5d}  {val_str}"
                    )

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

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text.

        AERMOD requires GRIDPOLR blocks wrapped in STA/END.
        """
        lines = [
            f"   GRIDPOLR  {self.grid_name:<8} STA",
            f"   GRIDPOLR  {self.grid_name:<8} ORIG  "
            f"{self.x_origin:10.2f} {self.y_origin:10.2f}",
            f"   GRIDPOLR  {self.grid_name:<8} DIST  "
            f"{self.dist_init:10.2f} {self.dist_num:5d} {self.dist_delta:8.2f}",
            f"   GRIDPOLR  {self.grid_name:<8} GDIR  "
            f"{self.dir_init:6.1f} {self.dir_num:5d} {self.dir_delta:6.1f}",
            f"   GRIDPOLR  {self.grid_name:<8} END",
        ]
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
