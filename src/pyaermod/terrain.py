"""
PyAERMOD Terrain Processing Pipeline

Downloads DEM data from USGS, runs AERMAP terrain preprocessor,
parses output, and updates receptor/source elevations.

Requires: pip install pyaermod[terrain]
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple, Union

from ._optional import optional_import, require

requests = optional_import("requests")
HAS_REQUESTS = requests is not None


def _require_requests():
    require(requests, "requests", pip_extra="terrain")


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


# ============================================================================
# AERMAP'S VERDICT
# ============================================================================
#
# AERMAP ends with a bare STOP, so it exits with code 0 whether or not it
# worked: a deck with 12 fatal setup errors and a domain outside the DEM
# (E310, which still leaves empty RECEPTOR and SOURCLOC files behind) both
# exit 0. Its verdict is in the message file, <input stem>.out, which the
# main program of aermap.f (AERMAP 24142) ends with one of
#
#     *** AERMAP Finishes Successfully ***
#     *** AERMAP Finishes UN-successfully ***
#
# after a "Message Summary For AERMAP Execution" whose "A Total of N Fatal
# Error Message(s)" counts every error of the run. A run with setup
# messages also has an earlier "Message Summary For AERMAP Setup" and a
# "*** SETUP Finishes ... ***" line, so only the last summary is read.
# SUMTBL writes each message as FORMAT(1X,A2,1X,A1,A3,I8,1X,A6,':',A50,1X,A12):
# pathway, severity, number, line, routine, text and detail. The
# recordings in tests/fixtures/aermap_runner/ show all of this.

_AERMAP_SUMMARY_HEADING = re.compile(r"\*\*\* Message Summary", re.IGNORECASE)
_AERMAP_BANNER = re.compile(
    r"^[ \t]*\*\*\*[ \t]*AERMAP Finishes (?P<verdict>Successfully|UN-successfully)[ \t]*\*\*\*[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AERMAP_TOTAL = re.compile(
    r"^[ \t]*A Total of[ \t]+(\d+)[ \t]+(Fatal Error|Warning) Message",
    re.IGNORECASE | re.MULTILINE,
)
_AERMAP_MESSAGE = re.compile(
    r"^ (?P<pathway>.{2}) (?P<code>[EW]\d{3})(?P<line>[ \d]{7}\d) "
    r"(?P<module>.{6}):(?P<body>.*?)\s*$"
)


class _AERMAPVerdict(NamedTuple):
    finished_successfully: bool
    fatal_count: Optional[int]
    warning_count: Optional[int]
    fatal_errors: List[str]


def _read_aermap_verdict(out_file: Path) -> _AERMAPVerdict:
    """Read the completion banner and the final message summary of an AERMAP ``.out`` file."""
    text = out_file.read_bytes().decode("latin-1").replace("\r\n", "\n")
    headings = list(_AERMAP_SUMMARY_HEADING.finditer(text))
    region = text[headings[-1].start():] if headings else ""
    banner = _AERMAP_BANNER.search(region)
    finished = banner is not None and banner.group("verdict").lower() == "successfully"
    if banner:
        region = region[:banner.start()]
    counts = {m.group(2).lower(): int(m.group(1)) for m in _AERMAP_TOTAL.finditer(region)}
    fatal_errors = []
    for raw in region.splitlines():
        m = _AERMAP_MESSAGE.match(raw)
        if m is None or not m.group("code").startswith("E"):
            continue
        body = m.group("body")
        # A50, 1X, A12: the text and the detail sit at fixed columns.
        text_part, detail = body[:50].strip(), body[51:].strip()
        message = f"{m.group('pathway').strip()} {m.group('code')} line {m.group('line').strip()} "
        message += f"{m.group('module').strip()}: {text_part}"
        fatal_errors.append(f"{message} {detail}" if detail else message)
    return _AERMAPVerdict(
        finished_successfully=finished,
        fatal_count=counts.get("fatal error"),
        warning_count=counts.get("warning"),
        fatal_errors=fatal_errors,
    )


@dataclass
class AERMAPRunResult:
    """Result from an AERMAP execution.

    ``success`` is AERMAP's own verdict: exit code 0, the message file
    ``<input stem>.out`` present, its ``*** AERMAP Finishes Successfully
    ***`` line, and no fatal error in its final message summary. AERMAP
    exits with code 0 after a fatal error, so the exit code alone says
    nothing. ``message_file`` is the path of that ``.out`` file,
    ``fatal_count`` and ``warning_count`` are AERMAP's own totals, and
    ``fatal_errors`` lists its fatal errors, such as ``"OU E310 line 29
    CHKEXT: Domain Coordinate is NOT Inside a DEM File. Pt.= 1"``.
    """
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

    finished_successfully: Optional[bool] = None
    fatal_count: Optional[int] = None
    warning_count: Optional[int] = None
    fatal_errors: List[str] = field(default_factory=list)

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

        # AERMAP expects the full input filename (with extension) as its
        # argument, e.g. ``aermap myrun.inp``. Passing the bare stem makes
        # AERMAP fail to locate the runstream and exit without processing
        # (it still returns code 0), so the run silently produces no output.
        input_name = input_path.name
        # A message file left by an earlier run must not supply this run's
        # verdict. AERMAP replaces the file anyway when it starts.
        out_file = work_dir / f"{input_path.stem}.out"
        out_file.unlink(missing_ok=True)
        start_time = datetime.now()

        # Pipe-safe stdout/stderr (file redirect, not OS pipes); see
        # runner.AERMODRunner.run for the rationale.
        from .runner import _read_capped
        stdout_fh = stderr_fh = None
        stdout_path = stderr_path = None
        if capture_output:
            stdout_path = work_dir / f"{input_name}.subproc.stdout"
            stderr_path = work_dir / f"{input_name}.subproc.stderr"
            stdout_fh = open(stdout_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            stderr_fh = open(stderr_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

        try:
            try:
                result = subprocess.run(
                    [str(self.executable), input_name],
                    cwd=str(work_dir),
                    stdout=stdout_fh, stderr=stderr_fh,
                    text=True,
                    timeout=timeout,
                    check=False,
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
        finally:
            if stdout_fh is not None:
                stdout_fh.close()
            if stderr_fh is not None:
                stderr_fh.close()

        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()
        captured_out = _read_capped(stdout_path) if stdout_path else None
        captured_err = _read_capped(stderr_path) if stderr_path else None

        # AERMAP names its message file after the input file it was given
        # (``run.inp`` -> ``run.out``) and exits 0 even after a fatal error;
        # see the comment above _read_aermap_verdict.
        verdict = None
        read_error = None
        if out_file.exists():
            try:
                verdict = _read_aermap_verdict(out_file)
            except OSError as exc:
                read_error = f"could not read {out_file}: {exc}"

        success = (
            result.returncode == 0
            and verdict is not None
            and verdict.finished_successfully
            and not verdict.fatal_count
            and not verdict.fatal_errors
        )

        error_message = None
        if not success:
            error_message = self._failure_reason(result.returncode, out_file, verdict, read_error)
            self.logger.error(f"AERMAP run failed: {error_message}")

        return AERMAPRunResult(
            success=success,
            input_file=str(input_path),
            return_code=result.returncode,
            runtime_seconds=runtime,
            message_file=str(out_file) if out_file.exists() else None,
            stdout=captured_out,
            stderr=captured_err,
            error_message=error_message,
            finished_successfully=verdict.finished_successfully if verdict else None,
            fatal_count=verdict.fatal_count if verdict else None,
            warning_count=verdict.warning_count if verdict else None,
            fatal_errors=verdict.fatal_errors if verdict else [],
        )

    @staticmethod
    def _failure_reason(
        return_code: int,
        out_file: Path,
        verdict: Optional[_AERMAPVerdict],
        read_error: Optional[str],
    ) -> str:
        """Explain a failed run, naming AERMAP's first fatal error when there is one."""
        if verdict is not None and verdict.fatal_errors:
            reason = verdict.fatal_errors[0]
            total = max(verdict.fatal_count or 0, len(verdict.fatal_errors))
            if total > 1:
                reason += f" (and {total - 1} more fatal error(s))"
        elif verdict is not None and verdict.fatal_count:
            reason = f"AERMAP reported {verdict.fatal_count} fatal error(s) in {out_file.name}"
        elif read_error is not None:
            reason = f"AERMAP's verdict is unknown: {read_error}"
        elif verdict is None:
            reason = f"AERMAP wrote no message file {out_file.name}"
        elif not verdict.finished_successfully:
            reason = f"{out_file.name} lacks AERMAP's '*** AERMAP Finishes Successfully ***' line"
        else:
            return f"AERMAP exited with code {return_code}"
        if return_code != 0:
            reason += f"; exit code {return_code}"
        return reason


# ============================================================================
# AERMAP OUTPUT PARSER
# ============================================================================


class AERMAPOutputParser:
    """Parse AERMAP receptor and source output files.

    Output format verified against AERMAP Fortran source code (v24142).
    """

    @staticmethod
    def parse_receptor_output(filepath: Union[str, Path]) -> "pd.DataFrame":  # noqa: F821
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
        _grid_x_num = None
        _grid_y_num = None
        grid_x_delta = None
        grid_y_delta = None

        with open(filepath) as f:
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
                        _grid_x_num = int(parts[idx + 2])
                        grid_x_delta = float(parts[idx + 3])
                        grid_y_init = float(parts[idx + 4])
                        _grid_y_num = int(parts[idx + 5])
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
    def parse_source_output(filepath: Union[str, Path]) -> "pd.DataFrame":  # noqa: F821
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
        with open(filepath) as f:
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

        The same as ``AERMAPProject.from_aermod_project`` with a 1 km
        buffer: the AERMOD coordinates are read as UTM coordinates in
        ``utm_zone``, and the AERMAP domain is their extent widened by
        1 km on every side, which the DEM files must cover.

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
        from pyaermod.aermap import AERMAPProject

        return AERMAPProject.from_aermod_project(
            aermod_project, dem_files, utm_zone=utm_zone, datum=datum, buffer=1000.0,
        )

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
            self._update_grid_receptor_elevations(project, rec_df)

        # Parse source elevations if available
        src_output = work_dir / aermap_project.source_output
        if hasattr(aermap_project, "source_output") and src_output.exists():
            src_df = parser.parse_source_output(src_output)
            self.logger.info(f"Parsed {len(src_df)} source elevations")
            self._update_source_elevations(project, src_df)

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

    def _update_grid_receptor_elevations(self, project, rec_df):
        """Update CartesianGrid receptors with parsed AERMAP elevation data.

        Maps AERMAP receptor output (x, y, zelev, zhill) back to
        CartesianGrid objects by computing expected grid coordinates
        and populating grid_elevations and grid_hills 2D arrays.

        Parameters
        ----------
        project : AERMODProject
        rec_df : pandas.DataFrame
            AERMAP receptor output with columns: x, y, zelev, zhill.
        """
        if rec_df.empty:
            return

        for grid in project.receptors.cartesian_grids:
            # Compute expected x/y coordinates for this grid
            x_coords = [grid.x_init + i * grid.x_delta for i in range(grid.x_num)]
            y_coords = [grid.y_init + j * grid.y_delta for j in range(grid.y_num)]

            elevations = []
            hills = []
            has_data = False

            for _j, y_val in enumerate(y_coords):
                elev_row = []
                hill_row = []
                for _i, x_val in enumerate(x_coords):
                    match = rec_df[
                        (abs(rec_df["x"] - x_val) < 0.5) &
                        (abs(rec_df["y"] - y_val) < 0.5)
                    ]
                    if not match.empty:
                        elev_row.append(float(match.iloc[0]["zelev"]))
                        hill_row.append(float(match.iloc[0]["zhill"]))
                        has_data = True
                    else:
                        elev_row.append(0.0)
                        hill_row.append(0.0)
                elevations.append(elev_row)
                hills.append(hill_row)

            if has_data:
                grid.grid_elevations = elevations
                grid.grid_hills = hills

    def _update_source_elevations(self, project, src_df):
        """Update source base elevations from AERMAP source output.

        Parameters
        ----------
        project : AERMODProject
        src_df : pandas.DataFrame
            AERMAP source output with columns: source_id, zelev
            (at minimum).
        """
        if src_df.empty:
            return

        from pyaermod.input_generator import BuoyLineSource

        for source in project.sources.sources:
            if isinstance(source, BuoyLineSource):
                for seg in source.line_segments:
                    match = src_df[src_df["source_id"].str.strip() == seg.source_id.strip()]
                    if not match.empty:
                        source.base_elevation = float(match.iloc[0]["zelev"])
            else:
                match = src_df[src_df["source_id"].str.strip() == source.source_id.strip()]
                if not match.empty:
                    source.base_elevation = float(match.iloc[0]["zelev"])


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
