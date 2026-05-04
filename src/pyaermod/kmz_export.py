"""
Hand-rolled KMZ exporter for AERMOD project + results visualization
in Google Earth.

Zero new dependencies — KMZ is a frozen OGC spec (a zipped KML XML
document), and we emit only the small subset needed for sources,
receptors, and concentration contours. Pyproj is used optionally to
re-project UTM source/receptor coordinates to WGS84 lon/lat, but only
when the caller specifies a CRS; lon/lat input passes through.

Public entry point::

    from pyaermod import to_kmz

    to_kmz(
        output_path="myrun.kmz",
        sources=project.sources.sources,        # AERMOD source list
        receptors=results.receptors,            # iterable of (x, y, conc)
        contours=[...],                         # optional
        utm_zone=18,                            # if x/y are UTM meters
        northern_hemisphere=True,
        title="My AERMOD run",
    )

The resulting .kmz drops into Google Earth via File > Open.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

# Optional: pyproj is in the `geo` / `viz` extras; only needed if the
# caller asks for UTM -> lon/lat reprojection.
try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False


@dataclass
class ContourPolygon:
    """One contour level rendered as a closed polygon in lon/lat."""
    level: float
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    label: str = ""


# Default ABGR style colors per contour level (low->high).
# KML uses AABBGGRR hex. Using a perceptually-ordered palette
# (cyan -> green -> yellow -> orange -> red -> magenta).
_DEFAULT_PALETTE = [
    "80ffff00",  # cyan
    "8000ff00",  # green
    "8000ffff",  # yellow
    "800080ff",  # orange
    "800000ff",  # red
    "80ff00ff",  # magenta
]


def _build_transformer(utm_zone: int, northern: bool):
    """Return a pyproj Transformer from UTM(zone) -> WGS84 lon/lat."""
    if not HAS_PYPROJ:
        raise ImportError(
            "pyproj is required to reproject UTM coordinates. "
            "Install with `pip install pyaermod[geo]`."
        )
    epsg = 32600 + utm_zone if northern else 32700 + utm_zone
    return Transformer.from_crs(epsg, 4326, always_xy=True)


def _to_lonlat(
    xs: Sequence[float], ys: Sequence[float],
    *, utm_zone: Optional[int], northern_hemisphere: bool,
) -> List[Tuple[float, float]]:
    """Convert a coordinate batch to (lon, lat). Pass-through if no zone."""
    if utm_zone is None:
        return list(zip(xs, ys, strict=False))
    tx = _build_transformer(utm_zone, northern_hemisphere)
    lons, lats = tx.transform(list(xs), list(ys))
    return list(zip(lons, lats, strict=False))


# ---------------------------------------------------------------------
# KML element builders
# ---------------------------------------------------------------------

_KML_NS = "http://www.opengis.net/kml/2.2"


def _kml_root() -> ET.Element:
    ET.register_namespace("", _KML_NS)
    root = ET.Element("kml", attrib={"xmlns": _KML_NS})
    return root


def _add_style(doc: ET.Element, style_id: str, color: str,
               line_width: float = 2.0, fill: bool = True) -> None:
    style = ET.SubElement(doc, "Style", attrib={"id": style_id})
    line = ET.SubElement(style, "LineStyle")
    ET.SubElement(line, "color").text = color
    ET.SubElement(line, "width").text = str(line_width)
    poly = ET.SubElement(style, "PolyStyle")
    ET.SubElement(poly, "color").text = color
    ET.SubElement(poly, "fill").text = "1" if fill else "0"
    ET.SubElement(poly, "outline").text = "1"


def _placemark_point(parent: ET.Element, name: str,
                     lon: float, lat: float,
                     description: str = "") -> None:
    pm = ET.SubElement(parent, "Placemark")
    ET.SubElement(pm, "name").text = name
    if description:
        ET.SubElement(pm, "description").text = description
    pt = ET.SubElement(pm, "Point")
    ET.SubElement(pt, "coordinates").text = f"{lon},{lat},0"


def _placemark_polygon(parent: ET.Element, name: str,
                       coords: Sequence[Tuple[float, float]],
                       style_id: str,
                       description: str = "") -> None:
    pm = ET.SubElement(parent, "Placemark")
    ET.SubElement(pm, "name").text = name
    if description:
        ET.SubElement(pm, "description").text = description
    ET.SubElement(pm, "styleUrl").text = f"#{style_id}"
    poly = ET.SubElement(pm, "Polygon")
    outer = ET.SubElement(poly, "outerBoundaryIs")
    ring = ET.SubElement(outer, "LinearRing")
    # Close the ring if the caller didn't.
    coord_list = list(coords)
    if coord_list and coord_list[0] != coord_list[-1]:
        coord_list.append(coord_list[0])
    ET.SubElement(ring, "coordinates").text = " ".join(
        f"{lon},{lat},0" for lon, lat in coord_list
    )


def _placemark_line(parent: ET.Element, name: str,
                    coords: Sequence[Tuple[float, float]],
                    style_id: str) -> None:
    pm = ET.SubElement(parent, "Placemark")
    ET.SubElement(pm, "name").text = name
    ET.SubElement(pm, "styleUrl").text = f"#{style_id}"
    line = ET.SubElement(pm, "LineString")
    ET.SubElement(line, "coordinates").text = " ".join(
        f"{lon},{lat},0" for lon, lat in coords
    )


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def to_kmz(
    output_path: Union[str, Path],
    *,
    sources: Optional[Iterable] = None,
    receptors: Optional[Iterable[Tuple[float, float, float]]] = None,
    contours: Optional[Iterable[ContourPolygon]] = None,
    utm_zone: Optional[int] = None,
    northern_hemisphere: bool = True,
    title: str = "AERMOD scenario",
    palette: Optional[Sequence[str]] = None,
) -> Path:
    """Serialize an AERMOD scenario to a Google-Earth-compatible KMZ.

    Parameters
    ----------
    output_path
        Path to the .kmz file to create. Parent directories are created
        automatically.
    sources
        Iterable of AERMOD source dataclass instances. Each source must
        expose ``source_id`` and either ``(x_coord, y_coord)`` (point /
        volume) or ``vertices`` (area-poly) attributes. Source types
        that don't expose recognized geometry attributes are skipped.
    receptors
        Iterable of ``(x, y, concentration)`` tuples. The concentration
        is rendered as a popup description in Google Earth.
    contours
        Iterable of :class:`ContourPolygon`. Coordinates must already
        be lon/lat (no projection applied to contours — caller is
        expected to project them via ``geospatial.generate_contours``).
    utm_zone
        Optional UTM zone for sources/receptors. If supplied, all
        source + receptor coordinates are reprojected from UTM to
        WGS84 lon/lat. Requires ``pyproj``.
    northern_hemisphere
        Whether the UTM zone is northern (default) or southern.
    title
        Document title written to the KMZ.
    palette
        Optional list of KML AABBGGRR color codes for contour levels.
        Defaults to a 6-level cyan-to-magenta palette; cycles when
        more levels are present.

    Returns
    -------
    The output path as a :class:`Path`.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    palette = list(palette) if palette else _DEFAULT_PALETTE

    root = _kml_root()
    doc = ET.SubElement(root, "Document")
    ET.SubElement(doc, "name").text = title

    # Pre-define styles for source/receptor folders
    _add_style(doc, "source-point", "ff00ffff", line_width=2.0, fill=False)
    _add_style(doc, "source-poly",  "5500ffff", line_width=2.0, fill=True)
    _add_style(doc, "source-line",  "ff00ffff", line_width=3.0, fill=False)
    _add_style(doc, "receptor",     "ff00ff00", line_width=1.0, fill=False)
    for i, color in enumerate(palette):
        _add_style(doc, f"contour-{i}", color, line_width=1.5, fill=True)

    # --- Sources folder ---
    if sources:
        src_folder = ET.SubElement(doc, "Folder")
        ET.SubElement(src_folder, "name").text = "Sources"
        for src in sources:
            sid = getattr(src, "source_id", "src")
            # Try point geometry first
            x = getattr(src, "x_coord", None)
            y = getattr(src, "y_coord", None)
            verts = getattr(src, "vertices", None)
            if verts:
                lonlat = _to_lonlat(
                    [v[0] for v in verts], [v[1] for v in verts],
                    utm_zone=utm_zone,
                    northern_hemisphere=northern_hemisphere,
                )
                _placemark_polygon(
                    src_folder, sid, lonlat, "source-poly",
                    description=type(src).__name__,
                )
            elif x is not None and y is not None:
                lonlat = _to_lonlat([x], [y],
                                    utm_zone=utm_zone,
                                    northern_hemisphere=northern_hemisphere)
                _placemark_point(
                    src_folder, sid, lonlat[0][0], lonlat[0][1],
                    description=type(src).__name__,
                )

    # --- Receptors folder ---
    if receptors:
        rcv_folder = ET.SubElement(doc, "Folder")
        ET.SubElement(rcv_folder, "name").text = "Receptors"
        rcv_list = list(receptors)
        if rcv_list:
            xs = [r[0] for r in rcv_list]
            ys = [r[1] for r in rcv_list]
            lonlat = _to_lonlat(xs, ys, utm_zone=utm_zone,
                                northern_hemisphere=northern_hemisphere)
            for (lon, lat), (_, _, conc) in zip(
                lonlat, rcv_list, strict=False
            ):
                _placemark_point(
                    rcv_folder, "",  # leave name blank to declutter
                    lon, lat,
                    description=f"Concentration: {conc:.4g}",
                )

    # --- Contours folder ---
    if contours:
        ct_folder = ET.SubElement(doc, "Folder")
        ET.SubElement(ct_folder, "name").text = "Contours"
        ct_list = sorted(contours, key=lambda c: c.level)
        for i, contour in enumerate(ct_list):
            style = f"contour-{i % len(palette)}"
            label = contour.label or f"{contour.level:g}"
            _placemark_polygon(
                ct_folder, label, contour.coordinates, style,
                description=f"Contour level: {contour.level}",
            )

    # Serialize and zip.
    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", buf.getvalue())
    return output_path


__all__ = [
    "ContourPolygon",
    "to_kmz",
]
