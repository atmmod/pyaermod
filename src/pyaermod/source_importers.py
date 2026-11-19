"""
Source importers from GIS / CAD formats.

Permit consultants typically receive site plans as Esri shapefiles
(.shp) from GIS staff and AutoCAD drawings (.dxf) from civil and
mechanical engineers. This module turns either into pyaermod source
dataclasses, ready to drop into a :class:`SourcePathway`.

Two importers are exposed:

- :func:`from_shapefile` — depends on the ``geo`` extra (geopandas).
- :func:`from_dxf` — depends on the ``cad`` extra (ezdxf), which is
  lightweight (~5 MB, MIT-licensed, pure Python).

The mapping from geometry to source type follows EPA convention:

==============================  ==============================
Geometry                        Default pyaermod source type
==============================  ==============================
Point / Point Z                 :class:`PointSource`
Polygon / Polygon Z             :class:`AreaPolySource`
LineString / LineString Z       :class:`LineSource`
==============================  ==============================

Caller can override the default via ``source_type=`` to map every
imported feature to a specific class (e.g. ``RLineSource`` instead
of ``LineSource`` for roadway centerlines). Per-feature attribute
columns (emission_rate, stack_height, etc.) are looked up by name
on each feature; missing columns fall back to the keyword defaults
on the dataclass.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Type, Union

from .input_generator import (
    AreaPolySource,
    LineSource,
    PointSource,
    VolumeSource,
)

# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

# Geometry-type → default source class mapping.
_GEOM_TO_SRC = {
    "Point": PointSource,
    "Polygon": AreaPolySource,
    "MultiPolygon": AreaPolySource,
    "LineString": LineSource,
    "MultiLineString": LineSource,
}


#: Esri shapefiles keep at most this many characters of a column name.
_DBF_NAME_LIMIT = 10


def _is_null(v: Any) -> bool:
    """True for None and for pandas/numpy nulls (NaN, NA, NaT)."""
    if v is None:
        return True
    try:
        import pandas as pd
        return bool(pd.isna(v))
    except (TypeError, ValueError, ImportError):
        return False


def _fields_of(classes: Iterable[Type]) -> set:
    out: set = set()
    for c in classes:
        out |= set(getattr(c, "__dataclass_fields__", {}))
    return out


def _truncated_name_map(columns: Iterable[str], fields: set,
                        explicit: dict) -> Dict[str, str]:
    """Map shapefile columns that are 10-character truncations to the field.

    ``emission_r`` -> ``emission_rate``, ``stack_heig`` -> ``stack_height``.
    Only a column that is not already a field name or in ``explicit``, and
    that is the 10-character prefix of exactly one field, is mapped.
    """
    out: Dict[str, str] = {}
    for col in columns:
        if col in fields or col in explicit or len(col) != _DBF_NAME_LIMIT:
            continue
        hits = {f for f in fields
                if len(f) > _DBF_NAME_LIMIT and f[:_DBF_NAME_LIMIT].lower() == col.lower()}
        if len(hits) == 1:
            out[col] = hits.pop()
    return out


def _kwargs_from_record(
    record: dict, src_class: Type, *, attribute_map: Optional[dict] = None,
) -> dict:
    """Filter a record dict down to keyword args the source class accepts."""
    attribute_map = attribute_map or {}
    valid_fields = set(getattr(src_class, "__dataclass_fields__", {}).keys())
    out = {}
    for k, v in record.items():
        # Allow caller-supplied attribute renames (e.g. {"H": "stack_height"}).
        target = attribute_map.get(k, k)
        if target in valid_fields and not _is_null(v):
            out[target] = v
    return out


def _make_point(record, geom, src_id_field: str,
                source_type: Type, attribute_map: Optional[dict]) -> Any:
    """Build a point-like source from a geometry + record."""
    sid = str(record.get(src_id_field, f"SRC{record.get('_index', 0):04d}"))
    kw = _kwargs_from_record(record, source_type, attribute_map=attribute_map)
    kw.setdefault("source_id", sid)
    kw.setdefault("x_coord", float(geom.x))
    kw.setdefault("y_coord", float(geom.y))
    return source_type(**kw)


def _make_polygon(record, geom, src_id_field: str,
                  source_type: Type,
                  attribute_map: Optional[dict]) -> Any:
    sid = str(record.get(src_id_field, f"SRC{record.get('_index', 0):04d}"))
    kw = _kwargs_from_record(record, source_type, attribute_map=attribute_map)
    kw.setdefault("source_id", sid)
    # AERMOD AreaPoly takes vertices as [(x, y), ...]; drop any z, drop
    # the closing repeat coord (AERMOD wants the open ring).
    coords = list(geom.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    kw["vertices"] = [(float(x), float(y)) for x, y, *_ in coords]
    return source_type(**kw)


def _make_line(record, geom, src_id_field: str,
               source_type: Type, attribute_map: Optional[dict]) -> Any:
    sid = str(record.get(src_id_field, f"SRC{record.get('_index', 0):04d}"))
    kw = _kwargs_from_record(record, source_type, attribute_map=attribute_map)
    kw.setdefault("source_id", sid)
    coords = list(geom.coords)
    # Both LineSource and RLineSource take start + end coordinates of
    # a single segment; for multi-segment polylines we use the first
    # and last vertices. Callers needing per-segment fidelity should
    # split the polyline upstream.
    if len(coords) > 2:
        warnings.warn(
            f"source {sid}: a line with {len(coords)} vertices is imported as "
            "one straight segment from its first to its last vertex; split "
            "the polyline into one feature per segment to keep its shape.",
            stacklevel=2,
        )
    x0, y0 = coords[0][0], coords[0][1]
    xn, yn = coords[-1][0], coords[-1][1]
    kw.setdefault("x_start", float(x0))
    kw.setdefault("y_start", float(y0))
    kw.setdefault("x_end", float(xn))
    kw.setdefault("y_end", float(yn))
    return source_type(**kw)


def _dispatch(geom, record: dict, *,
              src_id_field: str,
              source_type: Optional[Type],
              attribute_map: Optional[dict]) -> Optional[Any]:
    """Pick the right factory for one (geom, record) pair."""
    geom_type = geom.geom_type
    cls = source_type or _GEOM_TO_SRC.get(geom_type)
    if cls is None:
        return None
    if geom_type == "Point":
        return _make_point(record, geom, src_id_field, cls, attribute_map)
    if geom_type in ("Polygon",):
        return _make_polygon(record, geom, src_id_field, cls, attribute_map)
    if geom_type in ("MultiPolygon",):
        # First polygon only; users with multipolygon inputs should
        # explode upstream.
        first = next(iter(geom.geoms))
        return _make_polygon(record, first, src_id_field, cls, attribute_map)
    if geom_type in ("LineString",):
        return _make_line(record, geom, src_id_field, cls, attribute_map)
    if geom_type == "MultiLineString":
        first = next(iter(geom.geoms))
        return _make_line(record, first, src_id_field, cls, attribute_map)
    return None


# ---------------------------------------------------------------------
# SHP importer
# ---------------------------------------------------------------------

def from_shapefile(
    path: Union[str, Path],
    *,
    src_id_field: str = "source_id",
    source_type: Optional[Type] = None,
    attribute_map: Optional[dict] = None,
    layer: Optional[str] = None,
) -> List:
    """Import sources from an Esri shapefile (or any geopandas-readable file).

    Parameters
    ----------
    path
        Path to the .shp (or .gpkg / .geojson / etc.). Anything
        ``geopandas.read_file`` accepts.
    src_id_field
        Attribute column to use for the source_id. Falls back to
        ``"SRC0001"``-style synthesized IDs when missing.
    source_type
        Override default geometry → source class mapping. For example
        pass ``RLineSource`` to mark all imported lines as roadways.
    attribute_map
        Optional mapping of {shapefile_attribute: source_field}, e.g.
        ``{"H_M": "stack_height", "Q": "emission_rate"}``.
    layer
        For multi-layer formats (e.g. GPKG), the layer name to read.

    Returns
    -------
    list of source dataclass instances ready for SourcePathway(sources=[...]).

    Esri shapefiles keep only the first 10 characters of a column name, so
    ``emission_rate`` comes back as ``emission_r``; such a column is matched
    to the field it is the 10-character start of. A warning lists the
    columns that matched no source field (and so were ignored), and any
    ``attribute_map`` column or ``src_id_field`` the layer does not have. A
    null in a field's column leaves that field at the source default, with a
    warning.

    Raises
    ------
    ImportError
        If geopandas is not installed (pip install pyaermod[geo]).
    ValueError
        If the layer is in a geographic (longitude/latitude) coordinate
        system: AERMOD needs metres, so reproject it to a projected CRS
        (UTM, say) first.
    """
    try:
        import geopandas as gpd
    except ImportError as e:
        raise ImportError(
            "geopandas is required to import shapefiles. "
            "Install with `pip install pyaermod[geo]`."
        ) from e

    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.is_geographic:
        raise ValueError(
            f"{path} is in a geographic coordinate system ({gdf.crs}): its "
            "coordinates are degrees of longitude and latitude, but AERMOD "
            "needs metres. Reproject the layer to a projected CRS (for "
            "example UTM) before importing, e.g. gdf.to_crs(epsg=...)."
        )
    columns = [c for c in gdf.columns if c != gdf.geometry.name]
    classes = [source_type] if source_type else sorted(
        {_GEOM_TO_SRC[g] for g in gdf.geom_type if g in _GEOM_TO_SRC},
        key=lambda c: c.__name__)
    fields = _fields_of(classes)
    explicit = dict(attribute_map or {})
    attribute_map = {**_truncated_name_map(columns, fields, explicit), **explicit}

    missing_mapped = sorted(c for c in explicit if c not in columns)
    if missing_mapped:
        warnings.warn(
            f"attribute_map names column(s) {missing_mapped} that the layer "
            f"does not have (it has {columns}).", stacklevel=2)
    if src_id_field not in columns:
        warnings.warn(
            f"the layer has no {src_id_field!r} column, so source IDs are "
            "made up (SRC0000, SRC0001, ...); pass src_id_field= to use a "
            "column of the layer.", stacklevel=2)
    ignored = [c for c in columns
               if c != src_id_field and attribute_map.get(c, c) not in fields]
    if ignored:
        warnings.warn(
            f"column(s) {ignored} match no field of "
            f"{', '.join(c.__name__ for c in classes)} and were ignored; "
            "use attribute_map= to map them (shapefile column names are cut "
            "to 10 characters).", stacklevel=2)
    nulls = {c: int(gdf[c].isna().sum()) for c in columns
             if attribute_map.get(c, c) in fields and gdf[c].isna().any()}
    if nulls:
        warnings.warn(
            "null value(s) in " + ", ".join(f"{c} ({n})" for c, n in nulls.items())
            + "; those sources keep the field's default value.", stacklevel=2)

    sources = []
    for i, row in gdf.iterrows():
        record = {k: row[k] for k in columns}
        record["_index"] = i
        s = _dispatch(
            row.geometry, record,
            src_id_field=src_id_field,
            source_type=source_type,
            attribute_map=attribute_map,
        )
        if s is not None:
            sources.append(s)
    return sources


# ---------------------------------------------------------------------
# DXF importer
# ---------------------------------------------------------------------

def from_dxf(
    path: Union[str, Path],
    *,
    layer: Optional[str] = None,
    src_id_prefix: str = "DXF",
    source_type: Optional[Type] = None,
    z_as_height: bool = False,
) -> List:
    """Import sources from an AutoCAD DXF file.

    Maps DXF geometry to pyaermod sources::

        POINT      -> PointSource (or VolumeSource when source_type passed)
        LWPOLYLINE -> AreaPolySource (closed) or LineSource (open)
        POLYLINE   -> same as LWPOLYLINE
        LINE       -> LineSource
        CIRCLE     -> AreaPolySource (16-vertex polygon of the circle's area)

    Parameters
    ----------
    path
        Path to the .dxf file.
    layer
        Restrict import to entities on a single named DXF layer.
    src_id_prefix
        Prefix for synthesized source IDs (DXF doesn't natively
        carry source_id-like attributes).
    source_type
        Override default geometry → source class mapping.
    z_as_height
        When True, treat each entity's z elevation (or polyline's
        const_z) as ``stack_height`` / ``release_height``. Useful
        when CAD models encode building rooftop emission heights.

    Returns
    -------
    list of source dataclass instances.

    Raises
    ------
    ImportError
        If ezdxf is not installed (pip install pyaermod[cad]).
    """
    try:
        import ezdxf
    except ImportError as e:
        raise ImportError(
            "ezdxf is required to import DXF files. "
            "Install with `pip install pyaermod[cad]`."
        ) from e

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    sources: List = []
    counter = 0

    def _next_sid() -> str:
        nonlocal counter
        counter += 1
        return f"{src_id_prefix}{counter:04d}"

    for ent in msp:
        if layer and ent.dxf.layer != layer:
            continue
        kind = ent.dxftype()
        if kind == "POINT":
            cls = source_type or PointSource
            kw = {
                "source_id": _next_sid(),
                "x_coord": float(ent.dxf.location.x),
                "y_coord": float(ent.dxf.location.y),
            }
            _with_height(cls, kw, z_as_height, ent.dxf.location.z)
            sources.append(_safe_construct(cls, kw))
        elif kind == "LINE":
            cls = source_type or LineSource
            kw = {
                "source_id": _next_sid(),
                "x_start": float(ent.dxf.start.x),
                "y_start": float(ent.dxf.start.y),
                "x_end":   float(ent.dxf.end.x),
                "y_end":   float(ent.dxf.end.y),
            }
            _with_height(cls, kw, z_as_height, ent.dxf.start.z)
            sources.append(_safe_construct(cls, kw))
        elif kind in ("LWPOLYLINE", "POLYLINE"):
            verts = _polyline_vertices(ent)
            if not verts:
                continue
            closed = _polyline_is_closed(ent)
            if closed:
                cls = source_type or AreaPolySource
                # Drop closing dup if present
                if verts[0] == verts[-1]:
                    verts = verts[:-1]
                kw = {"source_id": _next_sid(),
                      "vertices": [(float(x), float(y)) for x, y in verts]}
                _with_height(cls, kw, z_as_height, _polyline_z(ent))
                sources.append(_safe_construct(cls, kw))
            else:
                cls = source_type or LineSource
                if len(verts) > 2:
                    warnings.warn(
                        f"a polyline with {len(verts)} vertices is imported "
                        "as one straight segment from its first to its last "
                        "vertex; split it into one LINE per segment to keep "
                        "its shape.", stacklevel=2)
                kw = {
                    "source_id": _next_sid(),
                    "x_start": float(verts[0][0]),
                    "y_start": float(verts[0][1]),
                    "x_end":   float(verts[-1][0]),
                    "y_end":   float(verts[-1][1]),
                }
                _with_height(cls, kw, z_as_height, _polyline_z(ent))
                sources.append(_safe_construct(cls, kw))
        elif kind == "CIRCLE":
            cls = source_type or AreaPolySource
            verts = _circle_to_polygon(
                cx=float(ent.dxf.center.x),
                cy=float(ent.dxf.center.y),
                r=float(ent.dxf.radius),
                n=16,
                equal_area=True,
            )
            kw = {"source_id": _next_sid(), "vertices": verts}
            _with_height(cls, kw, z_as_height, ent.dxf.center.z)
            sources.append(_safe_construct(cls, kw))
        # Other DXF types (TEXT, INSERT, etc.) ignored.
    return sources


def _with_height(cls: Type, kw: dict, z_as_height: bool, z: Any) -> dict:
    """Set the release height from a CAD z value when asked to."""
    if z_as_height and z is not None:
        for name in ("stack_height", "release_height"):
            if name in cls.__dataclass_fields__:
                kw[name] = float(z)
                break
    return kw


def _safe_construct(cls: Type, kwargs: dict) -> Any:
    """Construct a dataclass with required-field defaults filled in.

    Some pyaermod source classes require fields the GIS feed doesn't
    carry (emission_rate, stack_temp, ...). We pre-populate sentinels
    that pass __post_init__ validation; the user is expected to
    override them after import. Sentinel values are deliberately
    obvious (1.0 emission, 1.0 m stack diameter etc.) so a missed
    override produces an unrealistic but-not-crashing scenario.
    """
    sentinels = {
        "emission_rate": 1.0,
        "stack_height": 10.0,
        "stack_temp": 400.0,
        "exit_velocity": 10.0,
        "stack_diameter": 1.0,
        "release_height": 2.0,
    }
    valid_fields = cls.__dataclass_fields__
    for k, v in sentinels.items():
        if k in valid_fields and k not in kwargs:
            kwargs[k] = v
    return cls(**kwargs)


def _polyline_vertices(ent) -> List[tuple]:
    """Robust vertex extraction across LWPOLYLINE / POLYLINE."""
    if ent.dxftype() == "LWPOLYLINE":
        return [(p[0], p[1]) for p in ent.get_points()]
    # legacy POLYLINE
    out = []
    for v in ent.vertices:
        loc = v.dxf.location
        out.append((loc.x, loc.y))
    return out


def _polyline_is_closed(ent) -> bool:
    """Detect both LWPOLYLINE flag-1 and POLYLINE.is_closed."""
    if ent.dxftype() == "LWPOLYLINE":
        return bool(getattr(ent, "closed", False) or ent.dxf.flags & 1)
    return bool(getattr(ent, "is_closed", False))


def _polyline_z(ent) -> Optional[float]:
    """The z of a polyline: its elevation, or its first vertex's z."""
    try:
        elevation = ent.dxf.elevation
        # LWPOLYLINE stores a float, POLYLINE a (0, 0, z) vector.
        return float(elevation if isinstance(elevation, (int, float)) else elevation[2])
    except (AttributeError, IndexError, TypeError):
        pass
    try:
        return float(ent.vertices[0].dxf.location.z)
    except (AttributeError, IndexError, TypeError):
        return None


def _circle_to_polygon(cx: float, cy: float, r: float, n: int = 16,
                       equal_area: bool = False) -> list:
    """Discretize a circle into an n-vertex polygon (counter-clockwise).

    With ``equal_area`` the vertices sit on the circle of radius
    ``r * sqrt(2 pi / (n sin(2 pi / n)))``, so the polygon has the circle's
    area (as AERMOD's own AREACIRC polygon does); a polygon inscribed in
    the circle has only 97% of it for n = 16, and an area source's
    emission is per unit area.
    """
    if equal_area:
        r = r * math.sqrt(2 * math.pi / (n * math.sin(2 * math.pi / n)))
    return [
        (cx + r * math.cos(2 * math.pi * i / n),
         cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


# Re-export VolumeSource so users following docstrings have an import
# anchor (used as an alternate target for POINT geometry mappings).
__all__ = [
    "VolumeSource",
    "from_dxf",
    "from_shapefile",
]
