"""
PyAERMOD AERMAP Input Generator

Generates AERMAP input files for terrain preprocessing.
AERMAP is the EPA's terrain preprocessor for AERMOD.

AERMAP reads Digital Elevation Model (DEM) data and calculates:
- Receptor elevations
- Hill heights (for terrain-following calculations)
- Source elevations
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class AERMAPDomain:
    """Domain definition for AERMAP processing"""
    # Anchor point (SW corner)
    anchor_x: float  # UTM Easting
    anchor_y: float  # UTM Northing

    # Domain size
    num_x_points: int
    num_y_points: int
    spacing: float  # meters

    # DEM files
    dem_files: List[str] = field(default_factory=list)

    # UTM zone and datum
    utm_zone: int = 16
    datum: str = "NAD83"  # or "NAD27", "WGS84"


@dataclass
class AERMAPReceptor:
    """Receptor definition for AERMAP"""
    receptor_id: str
    x_coord: float
    y_coord: float
    elevation: Optional[float] = None  # If None, AERMAP will calculate from DEM


@dataclass
class AERMAPSource:
    """Source definition for AERMAP"""
    source_id: str
    x_coord: float
    y_coord: float
    elevation: Optional[float] = None  # If None, AERMAP will calculate from DEM


@dataclass
class AERMAPProject:
    """
    AERMAP project configuration

    Generates terrain elevations for receptors and sources.
    """

    # Job control
    job_id: str = "AERMAP"
    title_one: str = "AERMAP Terrain Processing"
    title_two: Optional[str] = None

    # Terrain data
    dem_files: List[str] = field(default_factory=list)
    dem_format: str = "NED"  # or "SRTM", "GTOPO30"

    # Domain settings
    anchor_x: Optional[float] = None
    anchor_y: Optional[float] = None
    utm_zone: int = 16
    datum: str = "NAD83"

    # Terrain type
    terrain_type: str = "FLAT"  # or "ELEVATED"

    # Receptors and sources
    receptors: List[AERMAPReceptor] = field(default_factory=list)
    sources: List[AERMAPSource] = field(default_factory=list)

    # Grid receptors (alternative to discrete receptors)
    grid_receptor: bool = False
    grid_x_init: float = 0.0
    grid_y_init: float = 0.0
    grid_x_num: int = 10
    grid_y_num: int = 10
    grid_spacing: float = 100.0

    # Output files
    receptor_output: str = "aermap_receptors.out"
    source_output: str = "aermap_sources.out"
    message_file: str = "aermap.msg"

    @classmethod
    def from_aermod_project(
        cls,
        aermod_project,
        dem_files: List[str],
        utm_zone: int = 16,
        datum: str = "NAD83",
        buffer: float = 1000.0,
    ) -> "AERMAPProject":
        """Create an AERMAPProject from an AERMODProject.

        Extracts source and receptor locations and builds corresponding
        AERMAP input for terrain elevation processing.

        Parameters
        ----------
        aermod_project : AERMODProject
        dem_files : list of str
            DEM file paths.
        utm_zone : int
        datum : str
        buffer : float
            Buffer in meters around domain extents.

        Returns
        -------
        AERMAPProject
        """
        all_x, all_y = [], []
        for src in aermod_project.sources.sources:
            if hasattr(src, "x_coord"):
                all_x.append(src.x_coord)
                all_y.append(src.y_coord)
            elif hasattr(src, "x_start"):
                all_x.extend([src.x_start, src.x_end])
                all_y.extend([src.y_start, src.y_end])

        for grid in aermod_project.receptors.cartesian_grids:
            all_x.extend([
                grid.x_init,
                grid.x_init + (grid.x_num - 1) * grid.x_delta,
            ])
            all_y.extend([
                grid.y_init,
                grid.y_init + (grid.y_num - 1) * grid.y_delta,
            ])

        for rec in aermod_project.receptors.discrete_receptors:
            all_x.append(rec.x_coord)
            all_y.append(rec.y_coord)

        if not all_x:
            raise ValueError("No source or receptor coordinates found in project")

        aermap = cls(
            title_one=f"AERMAP for {aermod_project.control.title_one}",
            dem_files=dem_files,
            dem_format="NED",
            anchor_x=min(all_x) - buffer,
            anchor_y=min(all_y) - buffer,
            utm_zone=utm_zone,
            datum=datum,
            terrain_type="ELEVATED",
        )

        for src in aermod_project.sources.sources:
            if hasattr(src, "x_coord"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_coord, src.y_coord))
            elif hasattr(src, "x_start"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_start, src.y_start))

        for grid in aermod_project.receptors.cartesian_grids:
            aermap.grid_receptor = True
            aermap.grid_x_init = grid.x_init
            aermap.grid_y_init = grid.y_init
            aermap.grid_x_num = grid.x_num
            aermap.grid_y_num = grid.y_num
            aermap.grid_spacing = grid.x_delta
            break

        for i, rec in enumerate(aermod_project.receptors.discrete_receptors):
            aermap.add_receptor(AERMAPReceptor(f"R{i + 1:04d}", rec.x_coord, rec.y_coord))

        return aermap

    def add_receptor(self, receptor: AERMAPReceptor):
        """Add a discrete receptor"""
        self.receptors.append(receptor)

    def add_source(self, source: AERMAPSource):
        """Add a source"""
        self.sources.append(source)

    def to_aermap_input(self) -> str:
        """Generate AERMAP input file"""
        lines = []

        # Header
        lines.append("** AERMAP Input File")
        lines.append(f"** {self.title_one}")
        if self.title_two:
            lines.append(f"** {self.title_two}")
        lines.append("**")
        lines.append("")

        # CO (Control) pathway
        lines.append("CO STARTING")
        lines.append(f"   TITLEONE  {self.title_one}")
        if self.title_two:
            lines.append(f"   TITLETWO  {self.title_two}")
        lines.append(f"   DATATYPE  {self.dem_format}")
        lines.append(f"   TERRHGTS  {self.terrain_type}")
        if self.anchor_x is not None and self.anchor_y is not None:
            lines.append(f"   DOMAINXY  {self.anchor_x:.2f} {self.anchor_y:.2f} " +
                        f"{self.utm_zone} {self.datum}")
        else:
            raise ValueError("anchor_x and anchor_y must be provided for AERMAP domain definition")
        lines.append("")

        # DEM files
        for dem_file in self.dem_files:
            lines.append(f"   DATAFILE  {dem_file}")
        lines.append("")

        lines.append("CO FINISHED")
        lines.append("")

        # RE (Receptor) pathway
        if self.receptors or self.grid_receptor:
            lines.append("RE STARTING")

            # Discrete receptors
            for rec in self.receptors:
                if rec.elevation is not None:
                    lines.append(f"   DISCCART  {rec.receptor_id:<8} " +
                               f"{rec.x_coord:12.2f} {rec.y_coord:12.2f} {rec.elevation:8.2f}")
                else:
                    lines.append(f"   DISCCART  {rec.receptor_id:<8} " +
                               f"{rec.x_coord:12.2f} {rec.y_coord:12.2f}")

            # Grid receptors
            if self.grid_receptor:
                lines.append("   GRIDCART  GRID     XYINC  " +
                           f"{self.grid_x_init:10.2f} {self.grid_x_num:5d} {self.grid_spacing:8.2f}  " +
                           f"{self.grid_y_init:10.2f} {self.grid_y_num:5d} {self.grid_spacing:8.2f}")

            lines.append("")
            lines.append(f"   RECOUTPUT {self.receptor_output}")
            lines.append("")
            lines.append("RE FINISHED")
            lines.append("")

        # SO (Source) pathway
        if self.sources:
            lines.append("SO STARTING")

            for src in self.sources:
                if src.elevation is not None:
                    lines.append(f"   LOCATION  {src.source_id:<8} POINT   " +
                               f"{src.x_coord:12.2f} {src.y_coord:12.2f} {src.elevation:8.2f}")
                else:
                    lines.append(f"   LOCATION  {src.source_id:<8} POINT   " +
                               f"{src.x_coord:12.2f} {src.y_coord:12.2f}")

            lines.append("")
            lines.append(f"   SRCOUTPUT {self.source_output}")
            lines.append("")
            lines.append("SO FINISHED")
            lines.append("")

        # OU (Output) pathway
        lines.append("OU STARTING")
        lines.append(f"   MSGOUTPUT {self.message_file}")
        lines.append("OU FINISHED")
        lines.append("")

        return "\n".join(lines)

    def write(self, filename: str):
        """Write AERMAP input file"""
        content = self.to_aermap_input()
        with open(filename, 'w') as f:
            f.write(content)
        return filename


def create_grid_receptors_for_aermap(x_min: float, x_max: float,
                                      y_min: float, y_max: float,
                                      spacing: float) -> Tuple[float, float, int, int]:
    """
    Helper function to calculate grid parameters for AERMAP

    Args:
        x_min, x_max: X coordinate range
        y_min, y_max: Y coordinate range
        spacing: Grid spacing in meters

    Returns:
        Tuple of (x_init, y_init, x_num, y_num)
    """
    x_num = int((x_max - x_min) / spacing) + 1
    y_num = int((y_max - y_min) / spacing) + 1

    return x_min, y_min, x_num, y_num


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMAP Input Generator")
    print("=" * 70)
    print()

    # Example 1: Discrete receptors
    print("Example 1: Discrete Receptors")
    print("-" * 70)

    project1 = AERMAPProject(
        job_id="DISCRETE_EXAMPLE",
        title_one="Discrete Receptor Terrain Processing",
        dem_files=["n41w088.dem", "n41w089.dem"],
        dem_format="NED",
        anchor_x=400000.0,
        anchor_y=4650000.0,
        utm_zone=16,
        datum="NAD83",
        terrain_type="ELEVATED"
    )

    # Add some receptors
    project1.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
    project1.add_receptor(AERMAPReceptor("R002", 402000.0, 4651000.0))
    project1.add_receptor(AERMAPReceptor("R003", 403000.0, 4651000.0))

    # Add sources
    project1.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0))

    filename1 = project1.write("aermap_discrete.inp")
    print(f"✓ Created: {filename1}")
    print(f"  Receptors: {len(project1.receptors)}")
    print(f"  Sources: {len(project1.sources)}")
    print()

    # Example 2: Grid receptors
    print("Example 2: Grid Receptors")
    print("-" * 70)

    project2 = AERMAPProject(
        job_id="GRID_EXAMPLE",
        title_one="Grid Receptor Terrain Processing",
        dem_files=["n41w088.dem"],
        dem_format="NED",
        anchor_x=400000.0,
        anchor_y=4650000.0,
        utm_zone=16,
        datum="NAD83",
        terrain_type="ELEVATED",
        grid_receptor=True,
        grid_x_init=400000.0,
        grid_y_init=4650000.0,
        grid_x_num=41,
        grid_y_num=41,
        grid_spacing=100.0
    )

    project2.add_source(AERMAPSource("STACK1", 402000.0, 4652000.0))

    filename2 = project2.write("aermap_grid.inp")
    print(f"✓ Created: {filename2}")
    print(f"  Grid: {project2.grid_x_num} × {project2.grid_y_num}")
    print(f"  Spacing: {project2.grid_spacing} m")
    print()

    print("=" * 70)
    print("To run AERMAP:")
    print("  aermap < aermap_discrete.inp")
    print("  aermap < aermap_grid.inp")
    print()
    print("AERMAP outputs:")
    print("  - Receptor file with elevations and hill heights")
    print("  - Source file with base elevations")
    print("  - Message file with processing log")
    print()
    print("Note: You need DEM files covering your domain!")
    print("  Download from: https://www.usgs.gov/national-map-viewer")
    print()
