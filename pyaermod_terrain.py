"""
PyAERMOD Terrain Processing Pipeline

Downloads DEM data from USGS, runs AERMAP terrain preprocessor,
parses output, and updates receptor/source elevations.

Requires: pip install pyaermod[terrain]
"""

import logging
import subprocess
import shutil
import platform
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def _require_requests():
    if not HAS_REQUESTS:
        raise ImportError(
            "requests is required for DEM downloading. "
            "Install with: pip install pyaermod[terrain]"
        )


# ============================================================================
# DEM DOWNLOAD
# ============================================================================


@dataclass
class DEMTileInfo:
    """Metadata for a single DEM tile from USGS."""
    title: str
    download_url: str
    format: str = "GeoTIFF"
    size_bytes: Optional[int] = None
    bounds: Optional[Tuple[float, float, float, float]] = None


class DEMDownloader:
    """Downloads USGS 3DEP (1/3 arc-second NED) elevation data.

    Uses the USGS TNM (The National Map) API to find and download
    DEM tiles covering a bounding box.

    Parameters
    ----------
    cache_dir : Path or str, optional
        Directory to cache downloaded tiles. Defaults to ~/.pyaermod/dem_cache.
    dataset : str
        USGS dataset name.
    """

    TNM_API_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"

    def __init__(
        self,
        cache_dir: Optional[Union[str, Path]] = None,
        dataset: str = "National Elevation Dataset (NED) 1/3 arc-second",
    ):
        _require_requests()
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".pyaermod" / "dem_cache"
        self.dataset = dataset
        self.logger = logging.getLogger(f"{__name__}.DEMDownloader")

    def find_tiles(
        self,
        bounds: Tuple[float, float, float, float],
    ) -> List[DEMTileInfo]:
        """Find DEM tiles covering a bounding box.

        Parameters
        ----------
        bounds : tuple
            (west, south, east, north) in decimal degrees (WGS84).

        Returns
        -------
        list of DEMTileInfo
        """
        west, south, east, north = bounds
        params = {
            "datasets": self.dataset,
            "bbox": f"{west},{south},{east},{north}",
            "prodFormats": "GeoTIFF",
            "max": 50,
        }
        self.logger.info(f"Querying USGS TNM API for tiles covering {bounds}")
        response = requests.get(self.TNM_API_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        tiles = []
        for item in data.get("items", []):
            tile = DEMTileInfo(
                title=item.get("title", "Unknown"),
                download_url=item.get("downloadURL", ""),
                format=item.get("format", "GeoTIFF"),
                size_bytes=item.get("sizeInBytes"),
            )
            if tile.download_url:
                tiles.append(tile)

        self.logger.info(f"Found {len(tiles)} DEM tiles")
        return tiles

    def download_tile(
        self,
        tile: DEMTileInfo,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Download a single DEM tile.

        Parameters
        ----------
        tile : DEMTileInfo
            Tile to download.
        output_dir : Path, optional
            Where to save. Defaults to cache_dir.

        Returns
        -------
        Path to downloaded file.
        """
        output_dir = output_dir or self.cache_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(tile.download_url).name
        output_path = output_dir / filename

        if output_path.exists():
            self.logger.info(f"Using cached tile: {output_path}")
            return output_path

        self.logger.info(f"Downloading: {tile.title} -> {output_path}")
        response = requests.get(tile.download_url, stream=True, timeout=300)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        self.logger.info(f"Downloaded: {output_path} ({output_path.stat().st_size} bytes)")
        return output_path

    def download_dem(
        self,
        bounds: Tuple[float, float, float, float],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> List[Path]:
        """Download all DEM tiles covering a bounding box.

        Parameters
        ----------
        bounds : tuple
            (west, south, east, north) in decimal degrees (WGS84).
        output_dir : Path or str, optional
            Directory to save tiles. Defaults to cache_dir.

        Returns
        -------
        list of Path
        """
        output_path = Path(output_dir) if output_dir else self.cache_dir
        tiles = self.find_tiles(bounds)
        if not tiles:
            self.logger.warning(f"No DEM tiles found for bounds {bounds}")
            return []

        paths = []
        for tile in tiles:
            path = self.download_tile(tile, output_path)
            paths.append(path)

        return paths


# ============================================================================
# AERMAP RUNNER
# ============================================================================


@dataclass
class AERMAPRunResult:
    """Result from an AERMAP execution."""
    success: bool
    input_file: str
    return_code: Optional[int] = None
    runtime_seconds: Optional[float] = None

    receptor_output: Optional[str] = None
    source_output: Optional[str] = None
    message_file: Optional[str] = None

    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        runtime = f"{self.runtime_seconds:.1f}s" if self.runtime_seconds else "N/A"
        return f"AERMAPRunResult({status}, {self.input_file}, runtime={runtime})"


class AERMAPRunner:
    """Execute AERMAP terrain preprocessor from Python.

    Parameters
    ----------
    executable_path : Path or str, optional
        Path to AERMAP executable. If None, searches PATH.
    log_level : str
        Logging level.
    """

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
    ):
        self.executable = self._find_or_set_executable(executable_path)
        self.logger = logging.getLogger(f"{__name__}.AERMAPRunner")
        self.logger.setLevel(getattr(logging, log_level.upper()))

    def _find_or_set_executable(self, path: Optional[Union[str, Path]]) -> Path:
        """Find or validate AERMAP executable."""
        if path:
            exe_path = Path(path)
            if not exe_path.exists():
                raise FileNotFoundError(f"AERMAP executable not found: {path}")
            return exe_path

        exe_names = ["aermap", "AERMAP", "aermap.exe", "AERMAP.EXE"]
        for name in exe_names:
            found = shutil.which(name)
            if found:
                return Path(found)

        raise FileNotFoundError(
            "AERMAP executable not found in PATH. Please either:\n"
            "  1. Add AERMAP to your system PATH, or\n"
            "  2. Specify the path explicitly: AERMAPRunner(executable_path='/path/to/aermap')"
        )

    def run(
        self,
        input_file: Union[str, Path],
        working_dir: Optional[Union[str, Path]] = None,
        timeout: int = 3600,
        capture_output: bool = True,
    ) -> AERMAPRunResult:
        """Execute AERMAP with given input file.

        Parameters
        ----------
        input_file : Path or str
            Path to AERMAP input file.
        working_dir : Path or str, optional
            Working directory. Defaults to input file's parent.
        timeout : int
            Maximum execution time in seconds.
        capture_output : bool
            Whether to capture stdout/stderr.

        Returns
        -------
        AERMAPRunResult
        """
        input_path = Path(input_file).resolve()
        if not input_path.exists():
            return AERMAPRunResult(
                success=False, input_file=str(input_path),
                error_message=f"Input file not found: {input_path}",
            )

        work_dir = Path(working_dir).resolve() if working_dir else input_path.parent
        work_dir.mkdir(parents=True, exist_ok=True)

        input_name = input_path.stem
        start_time = datetime.now()

        try:
            result = subprocess.run(
                [str(self.executable), input_name],
                cwd=str(work_dir),
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=False,
            )
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()
            success = result.returncode == 0

            return AERMAPRunResult(
                success=success,
                input_file=str(input_path),
                return_code=result.returncode,
                runtime_seconds=runtime,
                stdout=result.stdout if capture_output else None,
                stderr=result.stderr if capture_output else None,
                error_message=None if success else f"AERMAP failed with return code {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            return AERMAPRunResult(
                success=False, input_file=str(input_path),
                runtime_seconds=(end_time - start_time).total_seconds(),
                error_message=f"Execution timed out after {timeout} seconds",
            )

        except Exception as e:
            return AERMAPRunResult(
                success=False, input_file=str(input_path),
                error_message=str(e),
            )


# ============================================================================
# AERMAP OUTPUT PARSER
# ============================================================================


class AERMAPOutputParser:
    """Parse AERMAP receptor and source output files.

    Output format verified against AERMAP Fortran source code (v24142).
    """

    @staticmethod
    def parse_receptor_output(filepath: Union[str, Path]) -> "pd.DataFrame":
        """Parse AERMAP receptor output to extract elevations and hill heights.

        Handles both discrete (DISCCART) and grid (GRIDCART ELEV/HILL) formats.

        Parameters
        ----------
        filepath : Path or str
            Path to AERMAP receptor output file.

        Returns
        -------
        pd.DataFrame
            Columns: x, y, zelev, zhill
        """
        import pandas as pd

        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"AERMAP receptor output not found: {filepath}")

        records = []

        # State for parsing GRIDCART sections
        grid_elevs = {}   # row_num -> list of elevs
        grid_hills = {}   # row_num -> list of hills
        grid_x_init = None
        grid_y_init = None
        grid_x_num = None
        grid_y_num = None
        grid_x_delta = None
        grid_y_delta = None

        with open(filepath, "r") as f:
            for line in f:
                stripped = line.strip()

                # Skip comments and blank lines
                if not stripped or stripped.startswith("**"):
                    continue

                # DISCCART format: "   DISCCART  x(F12.2)  y(F12.2)  zelev(F10.2)  zhill(F10.2)"
                if "DISCCART" in stripped and "ELEV" not in stripped:
                    parts = stripped.split()
                    try:
                        idx = parts.index("DISCCART")
                        x = float(parts[idx + 1])
                        y = float(parts[idx + 2])
                        zelev = float(parts[idx + 3])
                        zhill = float(parts[idx + 4]) if len(parts) > idx + 4 else 0.0
                        records.append({"x": x, "y": y, "zelev": zelev, "zhill": zhill})
                    except (ValueError, IndexError):
                        continue

                # GRIDCART XYINC: extract grid parameters
                elif "GRIDCART" in stripped and "XYINC" in stripped:
                    parts = stripped.split()
                    try:
                        idx = parts.index("XYINC")
                        grid_x_init = float(parts[idx + 1])
                        grid_x_num = int(parts[idx + 2])
                        grid_x_delta = float(parts[idx + 3])
                        grid_y_init = float(parts[idx + 4])
                        grid_y_num = int(parts[idx + 5])
                        grid_y_delta = float(parts[idx + 6])
                    except (ValueError, IndexError):
                        continue

                # GRIDCART ELEV rows
                elif "GRIDCART" in stripped and "ELEV" in stripped:
                    parts = stripped.split()
                    try:
                        idx = parts.index("ELEV")
                        row_num = int(parts[idx + 1])
                        values = [float(v) for v in parts[idx + 2:]]
                        if row_num not in grid_elevs:
                            grid_elevs[row_num] = []
                        grid_elevs[row_num].extend(values)
                    except (ValueError, IndexError):
                        continue

                # GRIDCART HILL rows
                elif "GRIDCART" in stripped and "HILL" in stripped:
                    parts = stripped.split()
                    try:
                        idx = parts.index("HILL")
                        row_num = int(parts[idx + 1])
                        values = [float(v) for v in parts[idx + 2:]]
                        if row_num not in grid_hills:
                            grid_hills[row_num] = []
                        grid_hills[row_num].extend(values)
                    except (ValueError, IndexError):
                        continue

        # Convert GRIDCART data to records
        if grid_elevs and grid_x_init is not None:
            for row_num in sorted(grid_elevs.keys()):
                y = grid_y_init + (row_num - 1) * grid_y_delta
                elevs = grid_elevs[row_num]
                hills = grid_hills.get(row_num, [0.0] * len(elevs))
                for col_idx, (zelev, zhill) in enumerate(zip(elevs, hills)):
                    x = grid_x_init + col_idx * grid_x_delta
                    records.append({"x": x, "y": y, "zelev": zelev, "zhill": zhill})

        return pd.DataFrame(records)

    @staticmethod
    def parse_source_output(filepath: Union[str, Path]) -> "pd.DataFrame":
        """Parse AERMAP source output to extract base elevations.

        Format: "SO LOCATION  srcid(A12)  type(A8)  x(F12.2)  y(F12.2)  zelev(F12.2)"

        Parameters
        ----------
        filepath : Path or str
            Path to AERMAP source output file.

        Returns
        -------
        pd.DataFrame
            Columns: source_id, source_type, x, y, zelev
        """
        import pandas as pd

        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"AERMAP source output not found: {filepath}")

        records = []
        with open(filepath, "r") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("**"):
                    continue

                # SO LOCATION format
                if stripped.startswith("SO") and "LOCATION" in stripped:
                    parts = stripped.split()
                    try:
                        idx = parts.index("LOCATION")
                        source_id = parts[idx + 1]
                        source_type = parts[idx + 2]
                        x = float(parts[idx + 3])
                        y = float(parts[idx + 4])
                        zelev = float(parts[idx + 5]) if len(parts) > idx + 5 else 0.0
                        records.append({
                            "source_id": source_id,
                            "source_type": source_type,
                            "x": x, "y": y, "zelev": zelev,
                        })
                    except (ValueError, IndexError):
                        continue

        return pd.DataFrame(records)


# ============================================================================
# TERRAIN PROCESSOR (HIGH-LEVEL PIPELINE)
# ============================================================================


class TerrainProcessor:
    """High-level terrain processing pipeline.

    Coordinates DEM download, AERMAP input generation, execution,
    and elevation updates for an AERMOD project.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(f"{__name__}.TerrainProcessor")

    def create_aermap_project_from_aermod(
        self,
        aermod_project,
        dem_files: List[str],
        utm_zone: int = 16,
        datum: str = "NAD83",
    ):
        """Create an AERMAPProject from an AERMODProject.

        Extracts source and receptor locations from the AERMOD project
        and builds corresponding AERMAP input.

        Parameters
        ----------
        aermod_project : AERMODProject
        dem_files : list of str
        utm_zone : int
        datum : str

        Returns
        -------
        AERMAPProject
        """
        from pyaermod_aermap import AERMAPProject, AERMAPReceptor, AERMAPSource

        # Determine domain bounds from sources and receptors
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

        anchor_x = min(all_x) - 1000  # 1km buffer
        anchor_y = min(all_y) - 1000

        aermap = AERMAPProject(
            title_one=f"AERMAP for {aermod_project.control.title_one}",
            dem_files=dem_files,
            dem_format="NED",
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            utm_zone=utm_zone,
            datum=datum,
            terrain_type="ELEVATED",
        )

        # Add sources
        for src in aermod_project.sources.sources:
            if hasattr(src, "x_coord"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_coord, src.y_coord))
            elif hasattr(src, "x_start"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_start, src.y_start))

        # Add grid receptors (AERMAP supports one grid)
        for grid in aermod_project.receptors.cartesian_grids:
            aermap.grid_receptor = True
            aermap.grid_x_init = grid.x_init
            aermap.grid_y_init = grid.y_init
            aermap.grid_x_num = grid.x_num
            aermap.grid_y_num = grid.y_num
            aermap.grid_spacing = grid.x_delta
            break

        # Add discrete receptors
        for i, rec in enumerate(aermod_project.receptors.discrete_receptors):
            aermap.add_receptor(AERMAPReceptor(f"R{i + 1:04d}", rec.x_coord, rec.y_coord))

        return aermap

    def process(
        self,
        project,
        bounds: Tuple[float, float, float, float],
        aermap_exe: Optional[Union[str, Path]] = None,
        working_dir: Optional[Union[str, Path]] = None,
        utm_zone: int = 16,
        datum: str = "NAD83",
        skip_download: bool = False,
        dem_files: Optional[List[str]] = None,
        timeout: int = 3600,
    ):
        """Run the full terrain processing pipeline.

        Steps:
          1. Download DEM tiles (or use provided files)
          2. Generate AERMAP input from AERMOD project
          3. Run AERMAP
          4. Parse output and update project elevations

        Parameters
        ----------
        project : AERMODProject
        bounds : tuple
            (west, south, east, north) in decimal degrees.
        aermap_exe : Path or str, optional
        working_dir : Path or str, optional
        utm_zone : int
        datum : str
        skip_download : bool
            Skip DEM download (use dem_files instead).
        dem_files : list of str, optional
            Pre-existing DEM files.
        timeout : int
            AERMAP execution timeout in seconds.

        Returns
        -------
        AERMODProject
            Updated project with receptor elevations.
        """
        work_dir = Path(working_dir) if working_dir else Path.cwd() / "aermap_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Download DEM
        if not skip_download:
            self.logger.info("Step 1: Downloading DEM tiles...")
            downloader = DEMDownloader(cache_dir=work_dir / "dem_cache")
            dem_paths = downloader.download_dem(bounds, work_dir / "dem_data")
            dem_files_list = [str(p) for p in dem_paths]
        else:
            if dem_files is None:
                raise ValueError("dem_files required when skip_download=True")
            dem_files_list = list(dem_files)

        if not dem_files_list:
            raise RuntimeError("No DEM files available for AERMAP processing")

        # Step 2: Generate AERMAP input
        self.logger.info("Step 2: Generating AERMAP input...")
        aermap_project = self.create_aermap_project_from_aermod(
            project, dem_files_list, utm_zone, datum,
        )
        aermap_input = work_dir / "aermap.inp"
        aermap_project.write(str(aermap_input))

        # Step 3: Run AERMAP
        self.logger.info("Step 3: Running AERMAP...")
        runner = AERMAPRunner(executable_path=aermap_exe)
        result = runner.run(str(aermap_input), working_dir=str(work_dir), timeout=timeout)

        if not result.success:
            raise RuntimeError(f"AERMAP failed: {result.error_message}")

        # Step 4: Parse output and update elevations
        self.logger.info("Step 4: Parsing AERMAP output...")
        parser = AERMAPOutputParser()
        rec_output = work_dir / aermap_project.receptor_output
        if rec_output.exists():
            rec_df = parser.parse_receptor_output(rec_output)
            self.logger.info(f"Parsed {len(rec_df)} receptor elevations")
            self._update_receptor_elevations(project, rec_df)

        return project

    def _update_receptor_elevations(self, project, rec_df):
        """Update discrete receptors with parsed elevation data."""
        if rec_df.empty:
            return

        for rec in project.receptors.discrete_receptors:
            match = rec_df[
                (abs(rec_df["x"] - rec.x_coord) < 0.5) &
                (abs(rec_df["y"] - rec.y_coord) < 0.5)
            ]
            if not match.empty:
                rec.z_elev = float(match.iloc[0]["zelev"])
                rec.z_hill = float(match.iloc[0]["zhill"])


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def run_aermap(
    input_file: Union[str, Path],
    executable_path: Optional[Union[str, Path]] = None,
    timeout: int = 3600,
) -> AERMAPRunResult:
    """Quick function to run AERMAP.

    Parameters
    ----------
    input_file : Path or str
    executable_path : Path or str, optional
    timeout : int

    Returns
    -------
    AERMAPRunResult
    """
    runner = AERMAPRunner(executable_path=executable_path, log_level="WARNING")
    return runner.run(input_file, timeout=timeout)
