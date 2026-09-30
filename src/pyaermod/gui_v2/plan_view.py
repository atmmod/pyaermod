"""
The plan view: sources and receptors drawn in model coordinates.

:func:`plan_view_svg` turns a project into a self-contained SVG, with no
UI and no JavaScript, so it can be tested alone and costs one string per
change. The geometry is the library's (:mod:`pyaermod.footprints`): the
outline AERMOD builds for each source and every receptor a grid expands
to. x runs east and y north, at one scale on both axes, with gridlines
and ticks in metres.

The SVG is an image with an accessible name ("Plan view of sources and
receptors"); every source and receptor network is a group whose
``<title>`` names it (a tooltip on hover), and sources and grids are
labelled on the plot as long as there are few enough to read.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any, Iterable, List, Sequence, Tuple

from ..footprints import LINES, POINT, POLYGON, receptor_points, source_footprint

#: The plot's accessible name.
PLAN_VIEW_NAME = "Plan view of sources and receptors"

SOURCE_COLOUR = "#c62828"
RECEPTOR_COLOUR = "#1565c0"
GRID_COLOUR = "#e0e0e0"
AXIS_COLOUR = "#616161"

#: Draw at most this many receptor points; beyond it, every n-th one.
MAX_POINTS = 20_000
#: Label sources and receptor networks on the plot only up to this many each.
MAX_LABELS = 40

_WIDTH = 640.0
_MARGIN_LEFT = 64.0
_MARGIN_RIGHT = 16.0
_MARGIN_TOP = 28.0
_MARGIN_BOTTOM = 44.0

Point = Tuple[float, float]


def nice_step(span: float, target: int = 6) -> float:
    """A round tick spacing (1, 2 or 5 times a power of ten) giving about ``target`` ticks."""
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / target
    power = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 5, 10):
        if raw <= factor * power:
            return factor * power
    return 10 * power


def _ticks(lo: float, hi: float) -> List[float]:
    step = nice_step(hi - lo)
    first = math.ceil(lo / step) * step
    ticks = []
    value = first
    while value <= hi + step * 1e-9:
        ticks.append(0.0 if abs(value) < step * 1e-9 else value)
        value += step
    return ticks


def _fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _tick_label(value: float) -> str:
    return f"{value:g}" if abs(value) < 1e6 else f"{value:.3g}"


class _Frame:
    """Maps model coordinates to the SVG's, with one scale for x and y."""

    def __init__(self, points: Sequence[Point]):
        xs = [p[0] for p in points] or [0.0]
        ys = [p[1] for p in points] or [0.0]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        span = max(xmax - xmin, ymax - ymin)
        if span <= 0:
            span = 200.0                  # one point: a 200 m square around it
        pad = 0.08 * span
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        half_x = max(xmax - xmin, span * 0.25) / 2 + pad
        half_y = max(ymax - ymin, span * 0.25) / 2 + pad
        self.x0, self.x1 = cx - half_x, cx + half_x
        self.y0, self.y1 = cy - half_y, cy + half_y
        plot_w = _WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
        self.scale = plot_w / (self.x1 - self.x0)
        plot_h = (self.y1 - self.y0) * self.scale
        self.height = plot_h + _MARGIN_TOP + _MARGIN_BOTTOM
        self.bottom = _MARGIN_TOP + plot_h

    def px(self, x: float, y: float) -> Tuple[str, str]:
        return (_fmt(_MARGIN_LEFT + (x - self.x0) * self.scale),
                _fmt(self.bottom - (y - self.y0) * self.scale))


def _receptor_items(project: Any) -> List[Tuple[str, str, List[Point]]]:
    """(name, description, points) for each receptor network and the discrete set."""
    rp = project.receptors
    sources = project.sources.sources
    items: List[Tuple[str, str, List[Point]]] = []
    for grid in rp.cartesian_grids:
        pts = receptor_points(grid, sources=sources)
        items.append((grid.grid_name, f"Cartesian grid {grid.grid_name}: {len(pts)} receptors", pts))
    for grid in rp.polar_grids:
        pts = receptor_points(grid, sources=sources)
        items.append((grid.grid_name, f"Polar grid {grid.grid_name}: {len(pts)} receptors", pts))
    if rp.discrete_receptors:
        pts = [p for rec in rp.discrete_receptors for p in receptor_points(rec)]
        noun = "receptor" if len(pts) == 1 else "receptors"
        items.append(("", f"{len(pts)} discrete {noun}", pts))
    return items


def _footprints(project: Any) -> List[Any]:
    out = []
    for src in project.sources.sources:
        try:
            out.append(source_footprint(src))
        except (TypeError, ValueError):
            continue                      # a source with no shape yet is left out
    return out


def _summary(n_sources: int, receptor_count: int) -> str:
    if not n_sources and not receptor_count:
        return "Nothing to show yet: add a source or receptors."
    sources = f"{n_sources} source{'' if n_sources == 1 else 's'}"
    receptors = f"{receptor_count} receptor{'' if receptor_count == 1 else 's'}"
    return f"{sources} and {receptors}"


def _thin(points: List[Point], budget: int) -> List[Point]:
    if len(points) <= budget:
        return points
    step = math.ceil(len(points) / budget)
    return points[::step]


def plan_view_svg(project: Any) -> str:
    """The plan view of ``project`` as an SVG document string."""
    footprints = _footprints(project)
    receptors = _receptor_items(project)
    receptor_count = sum(len(pts) for _, _, pts in receptors)
    every_point: List[Point] = [p for fp in footprints for p in fp.points()]
    for _, _, pts in receptors:
        every_point.extend(pts)
    frame = _Frame(every_point)
    summary = _summary(len(footprints), receptor_count)

    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{escape(PLAN_VIEW_NAME)}" viewBox="0 0 {_fmt(_WIDTH)} {_fmt(frame.height)}" '
        f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:70vh;'
        f'font-family:sans-serif;font-size:12px">',
        f"<title>{escape(PLAN_VIEW_NAME)}</title>",
        # On a phone the plot is drawn at about half size: keep its text
        # legible, and drop the summary line, for which there is then no room
        # (it is still the <desc>, and every network's count is in its <title>).
        "<style>@media (max-width: 700px) { text { font-size: 22px; } .summary { display: none; } }"
        "</style>",
        f"<desc>{escape(summary)}</desc>",
    ]
    out.extend(_axes(frame))

    # Receptors first, so sources draw over them.
    budget = MAX_POINTS
    label_grids = len(receptors) <= MAX_LABELS
    for name, description, pts in receptors:
        shown = _thin(pts, max(budget, 1))
        budget = max(budget - len(shown), 0)
        size = 2.2 if len(pts) < 2000 else 1.4
        d = "".join(f"M{x} {y}h0" for x, y in (frame.px(*p) for p in shown))
        out.append(f'<g class="receptors"><title>{escape(description)}</title>'
                   f'<path d="{d}" stroke="{RECEPTOR_COLOUR}" stroke-width="{size}" '
                   f'stroke-linecap="round" fill="none" opacity="0.75"/>')
        if name and label_grids and pts:
            top = max(pts, key=lambda p: (p[1], -p[0]))
            x, y = frame.px(*top)
            out.append(f'<text x="{x}" y="{_fmt(float(y) - 6)}" fill="{RECEPTOR_COLOUR}" '
                       f'text-anchor="middle">{escape(name)}</text>')
        out.append("</g>")

    label_sources = len(footprints) <= MAX_LABELS
    for fp in footprints:
        out.append(f'<g class="source"><title>Source {escape(fp.source_id)}</title>')
        if fp.kind == POINT:
            x, y = frame.px(*fp.anchor())
            out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{SOURCE_COLOUR}" '
                       f'stroke="white" stroke-width="1.5"/>')
        elif fp.kind == POLYGON:
            outline = " ".join(",".join(frame.px(*p)) for p in fp.parts[0])
            out.append(f'<polygon points="{outline}" fill="{SOURCE_COLOUR}" fill-opacity="0.25" '
                       f'stroke="{SOURCE_COLOUR}" stroke-width="1.5"/>')
        elif fp.kind == LINES:
            for part in fp.parts:
                line = " ".join(",".join(frame.px(*p)) for p in part)
                out.append(f'<polyline points="{line}" fill="none" stroke="{SOURCE_COLOUR}" '
                           f'stroke-width="3" stroke-linecap="round"/>')
        if label_sources:
            x, y = frame.px(*fp.anchor())
            out.append(f'<text x="{_fmt(float(x) + 8)}" y="{_fmt(float(y) - 8)}" '
                       f'fill="{SOURCE_COLOUR}" font-weight="bold">{escape(fp.source_id)}</text>')
        out.append("</g>")

    out.extend(_legend(frame, summary, bool(every_point)))
    out.append("</svg>")
    return "".join(out)


def _axes(frame: _Frame) -> Iterable[str]:
    left, right = _MARGIN_LEFT, _WIDTH - _MARGIN_RIGHT
    top, bottom = _MARGIN_TOP, frame.bottom
    yield (f'<rect x="{_fmt(left)}" y="{_fmt(top)}" width="{_fmt(right - left)}" '
           f'height="{_fmt(bottom - top)}" fill="white" stroke="{AXIS_COLOUR}"/>')
    for value in _ticks(frame.x0, frame.x1):
        x, _ = frame.px(value, frame.y0)
        yield (f'<line x1="{x}" y1="{_fmt(top)}" x2="{x}" y2="{_fmt(bottom)}" '
               f'stroke="{GRID_COLOUR}"/>')
        yield (f'<text x="{x}" y="{_fmt(bottom + 16)}" fill="{AXIS_COLOUR}" '
               f'text-anchor="middle">{_tick_label(value)}</text>')
    for value in _ticks(frame.y0, frame.y1):
        _, y = frame.px(frame.x0, value)
        yield (f'<line x1="{_fmt(left)}" y1="{y}" x2="{_fmt(right)}" y2="{y}" '
               f'stroke="{GRID_COLOUR}"/>')
        yield (f'<text x="{_fmt(left - 6)}" y="{_fmt(float(y) + 4)}" fill="{AXIS_COLOUR}" '
               f'text-anchor="end">{_tick_label(value)}</text>')
    yield (f'<text x="{_fmt((left + right) / 2)}" y="{_fmt(bottom + 36)}" fill="{AXIS_COLOUR}" '
           f'text-anchor="middle">x (m)</text>')
    yield (f'<text x="14" y="{_fmt((top + bottom) / 2)}" fill="{AXIS_COLOUR}" '
           f'text-anchor="middle" transform="rotate(-90 14 {_fmt((top + bottom) / 2)})">y (m)</text>')


def _legend(frame: _Frame, summary: str, anything: bool) -> Iterable[str]:
    left = _MARGIN_LEFT
    if not anything:
        yield (f'<text x="{_fmt(_WIDTH / 2)}" y="{_fmt((_MARGIN_TOP + frame.bottom) / 2)}" '
               f'fill="{AXIS_COLOUR}" text-anchor="middle">{escape(summary)}</text>')
        return
    yield (f'<circle cx="{_fmt(left + 6)}" cy="14" r="5" fill="{SOURCE_COLOUR}"/>'
           f'<text x="{_fmt(left + 16)}" y="18" fill="{AXIS_COLOUR}">Sources</text>')
    # Spaced for the larger text a narrow window gets (see plan_view_svg).
    yield (f'<circle cx="{_fmt(left + 136)}" cy="14" r="3" fill="{RECEPTOR_COLOUR}"/>'
           f'<text x="{_fmt(left + 146)}" y="18" fill="{AXIS_COLOUR}">Receptors</text>')
    yield (f'<text class="summary" x="{_fmt(_WIDTH - _MARGIN_RIGHT)}" y="18" '
           f'fill="{AXIS_COLOUR}" text-anchor="end">{escape(summary)}</text>')


__all__ = ["MAX_POINTS", "PLAN_VIEW_NAME", "nice_step", "plan_view_svg"]
