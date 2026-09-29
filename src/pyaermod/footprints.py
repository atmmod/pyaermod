"""
Where sources and receptors lie in the model's plane.

:func:`source_footprint` gives the outline AERMOD itself builds for a
source (a point, a polygon or line segments), and :func:`receptor_points`
the receptor locations a grid or discrete receptor expands to. Both work
in model coordinates (metres, x east, y north) and need no optional
dependency, so a plan-view plot, a domain check or a GIS export can share
them.

The geometry follows AERMOD v26135 rather than the field names:

- ``AREA`` and ``OPENPIT``: ``LOCATION`` is the south-west corner and the
  rectangle's vertices run clockwise from it, ``Yinit`` along the rotated
  north side first, then ``Xinit`` along the rotated east side, rotated
  clockwise by ``Angle`` degrees about that corner (``soset.f`` ARVERT and
  the OPENPIT branch). :class:`~pyaermod.sources.AreaSource` keeps
  ``Xinit`` in ``initial_lateral_dimension`` and ``Yinit`` in
  ``initial_vertical_dimension`` (the order ``SRCPARAM`` writes them); both
  are full side lengths, not half-widths.
- ``AREACIRC``: the ``NVERTS``-sided polygon of the same area as the
  circle, its first vertex due north of the centre (``soset.f`` GENCIR).
- Polar grids: a receptor at distance ``r`` in direction ``theta``
  (degrees clockwise from north) lies at ``(x0 + r sin theta,
  y0 + r cos theta)`` (``reset.f`` SETPOL); ``GRIDPOLR ORIG srcid`` centres
  the grid on that source's ``LOCATION``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

Point = Tuple[float, float]

#: Footprint kinds.
POINT = "point"
POLYGON = "polygon"
LINES = "lines"


@dataclass(frozen=True)
class Footprint:
    """The outline of one source in model coordinates.

    ``kind`` is :data:`POINT` (``parts`` holds one part with one point),
    :data:`POLYGON` (one part: the vertices in order, the first not
    repeated at the end) or :data:`LINES` (one part of two points per line
    segment).
    """

    source_id: str
    kind: str
    parts: Tuple[Tuple[Point, ...], ...]

    def points(self) -> List[Point]:
        """Every vertex of the footprint, part by part."""
        return [p for part in self.parts for p in part]

    def anchor(self) -> Point:
        """A point to label the source at: its location, or its first vertex."""
        return self.parts[0][0]


def _rectangle(x: float, y: float, xinit: float, yinit: float, angle: float) -> Tuple[Point, ...]:
    """soset.f ARVERT: SW corner first, clockwise, rotated about that corner."""
    rad = math.radians(angle)
    s, c = math.sin(rad), math.cos(rad)
    p1 = (x, y)
    p2 = (p1[0] + yinit * s, p1[1] + yinit * c)
    p3 = (p2[0] + xinit * c, p2[1] - xinit * s)
    p4 = (p3[0] - yinit * s, p3[1] - yinit * c)
    return (p1, p2, p3, p4)


def _circle(x: float, y: float, radius: float, sides: int) -> Tuple[Point, ...]:
    """soset.f GENCIR: the equal-area polygon, first vertex due north."""
    sides = max(int(sides), 3)
    increment = 360.0 / sides
    area = math.pi * radius * radius
    triangle = area / sides
    opposite = math.sqrt(triangle * math.tan(math.radians(increment / 2.0)))
    new_radius = opposite / math.sin(math.radians(increment / 2.0))
    return tuple(
        (x + new_radius * math.sin(math.radians(i * increment)),
         y + new_radius * math.cos(math.radians(i * increment)))
        for i in range(sides)
    )


def source_footprint(src: Any) -> Footprint:
    """The outline AERMOD builds for ``src``.

    Raises :class:`TypeError` for an object that is not a source, and
    :class:`ValueError` for a polygon or buoyant line with no vertices.
    """
    from .sources import (
        AreaCircSource,
        AreaPolySource,
        AreaSource,
        BuoyLineSource,
        LineSource,
        OpenPitSource,
        RLineExtSource,
        RLineSource,
    )

    sid = str(getattr(src, "source_id", ""))
    if isinstance(src, AreaSource):
        ring = _rectangle(src.x_coord, src.y_coord, src.initial_lateral_dimension,
                          src.initial_vertical_dimension, src.angle)
        return Footprint(sid, POLYGON, (ring,))
    if isinstance(src, OpenPitSource):
        ring = _rectangle(src.x_coord, src.y_coord, src.x_dimension, src.y_dimension,
                          src.angle)
        return Footprint(sid, POLYGON, (ring,))
    if isinstance(src, AreaCircSource):
        ring = _circle(src.x_coord, src.y_coord, src.radius, src.num_vertices)
        return Footprint(sid, POLYGON, (ring,))
    if isinstance(src, AreaPolySource):
        if not src.vertices:
            raise ValueError(f"{sid}: an AREAPOLY source needs vertices")
        return Footprint(sid, POLYGON, (tuple((float(x), float(y)) for x, y in src.vertices),))
    if isinstance(src, (LineSource, RLineSource, RLineExtSource)):
        return Footprint(sid, LINES, (((src.x_start, src.y_start), (src.x_end, src.y_end)),))
    if isinstance(src, BuoyLineSource):
        if not src.line_segments:
            raise ValueError(f"{sid}: a BUOYLINE source needs line segments")
        return Footprint(sid, LINES, tuple(
            ((seg.x_start, seg.y_start), (seg.x_end, seg.y_end)) for seg in src.line_segments))
    if hasattr(src, "x_coord") and hasattr(src, "y_coord") and hasattr(src, "source_id"):
        # POINT, POINTCAP, POINTHOR, SWPOINT and VOLUME: the location itself.
        return Footprint(sid, POINT, (((src.x_coord, src.y_coord),),))
    raise TypeError(f"not a source: {type(src).__name__}")


def _source_location(source_id: str, sources: Iterable[Any]) -> Optional[Point]:
    """The ``LOCATION`` x, y of the source named ``source_id``."""
    for src in sources:
        if getattr(src, "source_id", None) == source_id:
            return source_footprint(src).anchor()
    return None


def receptor_points(receptor: Any, *, sources: Iterable[Any] = ()) -> List[Point]:
    """Every receptor location ``receptor`` stands for, in model coordinates.

    ``receptor`` is a :class:`~pyaermod.receptors.CartesianGrid`,
    :class:`~pyaermod.receptors.PolarGrid` or
    :class:`~pyaermod.receptors.DiscreteReceptor`. A polar grid centred on
    a source (``origin_source_id``) looks the source up in ``sources``; if
    it is not there the grid is centred on ``x_origin``/``y_origin``.
    """
    from .receptors import CartesianGrid, DiscreteReceptor, PolarGrid

    if isinstance(receptor, CartesianGrid):
        xs = receptor.x_values()
        return [(x, y) for y in receptor.y_values() for x in xs]
    if isinstance(receptor, PolarGrid):
        x0, y0 = receptor.x_origin, receptor.y_origin
        if receptor.origin_source_id:
            found = _source_location(receptor.origin_source_id, sources)
            if found is not None:
                x0, y0 = found
        rings = receptor.ring_distances()
        points = []
        for theta in receptor.direction_angles():
            s, c = math.sin(math.radians(theta)), math.cos(math.radians(theta))
            points.extend((x0 + r * s, y0 + r * c) for r in rings)
        return points
    if isinstance(receptor, DiscreteReceptor):
        return [(receptor.x_coord, receptor.y_coord)]
    raise TypeError(f"not a receptor: {type(receptor).__name__}")


__all__ = ["LINES", "POINT", "POLYGON", "Footprint", "receptor_points", "source_footprint"]
