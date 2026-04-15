"""
PyAERMOD terrain utilities: datums, mosaic, reprojection, diagnostics,
async downloads.

Companion to `terrain.py`. These helpers handle the operational gaps
users hit when building AERMAP inputs for real sites:

- `DatumTransformer`: NAD27 <-> NAD83 <-> WGS84 coordinate conversions
  for legacy DEM data (requires pyproj).
- `SRTMDownloader`: fallback DEM source (SRTM v3.0 1-arc-second) for
  regions outside CONUS where USGS NED isn't available.
- `mosaic_dem_tiles`: merge multiple DEM tiles into a single GeoTIFF
  (requires rasterio).
- `reproject_dem`: reproject a DEM to a target UTM zone or EPSG.
- `async_fetch_tiles`: parallel tile downloads via ThreadPoolExecutor.
- `hill_height_diagnostics`: scan AERMAP output for implausible
  receptor elevations / hill heights.
"""

from __future__ import annotations

import concurrent.futures
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple, Union

try:
    from pyproj import Transformer  # type: ignore
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    import rasterio  # type: ignore
    from rasterio.merge import merge as rio_merge  # type: ignore
    from rasterio.warp import Resampling, calculate_default_transform, reproject  # type: ignore
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


# ---------------------------------------------------------------------------
# Datums
# ---------------------------------------------------------------------------

# Common EPSG codes relevant for U.S. DEM data
EPSG_WGS84 = 4326
EPSG_NAD83 = 4269
EPSG_NAD27 = 4267


def _require_pyproj() -> None:
    if not HAS_PYPROJ:
        raise ImportError(
            "pyproj is required for coordinate-datum transforms. "
            "Install with: pip install pyproj"
        )


class DatumTransformer:
    """Wrap pyproj to convert between common U.S. datums.

    Typical use: older USGS DEMs (especially 7.5-minute quad series)
    are published in NAD27 with coordinates in arc-seconds.  AERMOD
    expects UTM coordinates in a current datum (NAD83 or WGS84).
    """

    def __init__(self, from_epsg: int, to_epsg: int) -> None:
        _require_pyproj()
        self.from_epsg = from_epsg
        self.to_epsg = to_epsg
        self._tr = Transformer.from_crs(
            f"EPSG:{from_epsg}", f"EPSG:{to_epsg}", always_xy=True
        )

    def transform(self, x: float, y: float) -> Tuple[float, float]:
        """Transform a single (x, y) / (lon, lat) pair."""
        return self._tr.transform(x, y)

    def transform_many(self, coords: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
        xs, ys = zip(*coords) if coords else ([], [])
        out_x, out_y = self._tr.transform(list(xs), list(ys))
        return list(zip(out_x, out_y))

    @classmethod
    def nad27_to_nad83(cls) -> "DatumTransformer":
        return cls(EPSG_NAD27, EPSG_NAD83)

    @classmethod
    def nad27_to_wgs84(cls) -> "DatumTransformer":
        return cls(EPSG_NAD27, EPSG_WGS84)

    @classmethod
    def nad83_to_wgs84(cls) -> "DatumTransformer":
        return cls(EPSG_NAD83, EPSG_WGS84)


def utm_zone_for_lon(lon: float) -> int:
    """Return the UTM zone number (1-60) containing a given longitude."""
    if not (-180 <= lon <= 180):
        raise ValueError(f"lon must be in [-180, 180], got {lon}")
    return int(math.floor((lon + 180) / 6)) + 1


def utm_epsg(lon: float, lat: float) -> int:
    """Return the EPSG code for the WGS84 UTM zone covering (lon, lat)."""
    zone = utm_zone_for_lon(lon)
    return 32600 + zone if lat >= 0 else 32700 + zone


# ---------------------------------------------------------------------------
# SRTM fallback downloader (skeleton)
# ---------------------------------------------------------------------------

@dataclass
class SRTMTileInfo:
    """Metadata for a single SRTM v3.0 tile."""
    tile_name: str
    download_url: str
    lat_south: int
    lon_west: int


def srtm_tile_name(lat: float, lon: float) -> str:
    """Compute the SRTM v3.0 1x1-degree tile name for a coordinate.

    Example: (35.5, -105.2) -> 'N35W106'
    """
    lat_f = int(math.floor(lat))
    lon_f = int(math.floor(lon))
    lat_s = f"{'N' if lat_f >= 0 else 'S'}{abs(lat_f):02d}"
    lon_s = f"{'E' if lon_f >= 0 else 'W'}{abs(lon_f):03d}"
    return f"{lat_s}{lon_s}"


def srtm_tiles_for_bbox(
    bounds: Tuple[float, float, float, float],
) -> List[SRTMTileInfo]:
    """Enumerate SRTM tile names covering a (west, south, east, north) bbox.

    The download_url is a canonical USGS EarthData path — most users
    need NASA EarthData Login to actually fetch. For an unauthenticated
    alternative, consider OpenTopography's API.
    """
    west, south, east, north = bounds
    tiles: List[SRTMTileInfo] = []
    for lat_f in range(int(math.floor(south)), int(math.floor(north)) + 1):
        for lon_f in range(int(math.floor(west)), int(math.floor(east)) + 1):
            name = srtm_tile_name(lat_f + 0.5, lon_f + 0.5)
            url = (
                f"https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/"
                f"{name}.SRTMGL1.hgt.zip"
            )
            tiles.append(SRTMTileInfo(
                tile_name=name, download_url=url,
                lat_south=lat_f, lon_west=lon_f,
            ))
    return tiles


# ---------------------------------------------------------------------------
# Mosaic / reproject
# ---------------------------------------------------------------------------

def _require_rasterio() -> None:
    if not HAS_RASTERIO:
        raise ImportError(
            "rasterio is required for DEM mosaic/reproject. "
            "Install with: pip install rasterio"
        )


def mosaic_dem_tiles(
    tile_paths: Iterable[Union[str, Path]],
    output_path: Union[str, Path],
) -> Path:
    """Merge multiple DEM tiles into a single GeoTIFF.

    Writes the mosaic to `output_path` and returns the path.
    """
    _require_rasterio()
    sources = [rasterio.open(str(p)) for p in tile_paths]
    try:
        mosaic, transform = rio_merge(sources)
        profile = sources[0].profile
        profile.update(
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            count=mosaic.shape[0],
        )
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(out_path), "w", **profile) as dst:
            dst.write(mosaic)
        return out_path
    finally:
        for s in sources:
            s.close()


def reproject_dem(
    src_path: Union[str, Path],
    dst_path: Union[str, Path],
    dst_epsg: int,
    resampling: str = "bilinear",
) -> Path:
    """Reproject a DEM to a target EPSG (typically a UTM zone)."""
    _require_rasterio()
    resampler = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }[resampling]
    with rasterio.open(str(src_path)) as src:
        transform, width, height = calculate_default_transform(
            src.crs, f"EPSG:{dst_epsg}",
            src.width, src.height, *src.bounds,
        )
        profile = src.profile.copy()
        profile.update({
            "crs": f"EPSG:{dst_epsg}",
            "transform": transform,
            "width": width,
            "height": height,
        })
        out_path = Path(dst_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(out_path), "w", **profile) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=f"EPSG:{dst_epsg}",
                    resampling=resampler,
                )
    return out_path


# ---------------------------------------------------------------------------
# Async (parallel) tile fetching
# ---------------------------------------------------------------------------

def async_fetch_tiles(
    urls: Sequence[str],
    fetch_fn: Callable[[str], Any],
    max_workers: int = 8,
) -> List[Any]:
    """Run `fetch_fn(url)` in a thread pool and return results in order.

    `fetch_fn` is user-supplied so this module stays network-agnostic
    (tests can pass a pure function; production passes `requests.get`).
    Exceptions are returned in-place (do not raise) so partial failures
    don't lose successful results.
    """
    out: List[Any] = [None] * len(urls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_fn, u): i for i, u in enumerate(urls)}
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            try:
                out[i] = fut.result()
            except Exception as e:  # pragma: no cover
                out[i] = e
    return out


# ---------------------------------------------------------------------------
# Hill-height diagnostics on AERMAP output
# ---------------------------------------------------------------------------

@dataclass
class HillHeightAnomaly:
    """Flagged AERMAP receptor/source elevation record."""
    index: int
    x: float
    y: float
    zelev: float
    zhill: float
    reason: str


def hill_height_diagnostics(
    records: Sequence[Any],
    zelev_attr: str = "zelev",
    zhill_attr: str = "zhill",
    max_gradient_mperm: float = 10.0,
    flat_tolerance_m: float = 0.01,
) -> List[HillHeightAnomaly]:
    """Scan AERMAP-derived receptor/source records for suspicious elevations.

    Flags:
    - zhill < zelev (hill height below ground elevation: impossible)
    - huge receptor-to-receptor elevation gradients (> max_gradient_mperm)
    - large clusters of identical zelev values (flat patch signature of
      DEM stubs or fill — not necessarily wrong but worth surfacing)
    """
    anomalies: List[HillHeightAnomaly] = []
    last_rec = None
    flat_run_start: Optional[int] = None
    flat_value: Optional[float] = None
    flat_count = 0

    for i, r in enumerate(records):
        ze = float(getattr(r, zelev_attr))
        zh = float(getattr(r, zhill_attr))
        x = float(getattr(r, "x", getattr(r, "x_coord", 0.0)))
        y = float(getattr(r, "y", getattr(r, "y_coord", 0.0)))

        if zh + flat_tolerance_m < ze:
            anomalies.append(HillHeightAnomaly(
                index=i, x=x, y=y, zelev=ze, zhill=zh,
                reason=f"zhill ({zh}) below zelev ({ze})",
            ))

        if last_rec is not None:
            lx = float(getattr(last_rec, "x", getattr(last_rec, "x_coord", 0.0)))
            ly = float(getattr(last_rec, "y", getattr(last_rec, "y_coord", 0.0)))
            lz = float(getattr(last_rec, zelev_attr))
            dist = math.hypot(x - lx, y - ly)
            if dist > 0:
                grad = abs(ze - lz) / dist
                if grad > max_gradient_mperm:
                    anomalies.append(HillHeightAnomaly(
                        index=i, x=x, y=y, zelev=ze, zhill=zh,
                        reason=f"elevation gradient {grad:.2f} m/m > "
                               f"{max_gradient_mperm} m/m",
                    ))

        # Flat-patch detection
        if flat_value is None or abs(ze - flat_value) > flat_tolerance_m:
            if flat_count >= 25:
                anomalies.append(HillHeightAnomaly(
                    index=flat_run_start or 0, x=x, y=y,
                    zelev=flat_value or 0, zhill=zh,
                    reason=f"flat-elevation run of length {flat_count}",
                ))
            flat_value = ze
            flat_run_start = i
            flat_count = 1
        else:
            flat_count += 1

        last_rec = r

    if flat_count >= 25:
        anomalies.append(HillHeightAnomaly(
            index=flat_run_start or 0, x=0.0, y=0.0,
            zelev=flat_value or 0, zhill=0.0,
            reason=f"flat-elevation run of length {flat_count}",
        ))

    return anomalies


__all__ = [
    "EPSG_WGS84", "EPSG_NAD83", "EPSG_NAD27",
    "DatumTransformer",
    "utm_zone_for_lon",
    "utm_epsg",
    "SRTMTileInfo",
    "srtm_tile_name",
    "srtm_tiles_for_bbox",
    "mosaic_dem_tiles",
    "reproject_dem",
    "async_fetch_tiles",
    "HillHeightAnomaly",
    "hill_height_diagnostics",
]
