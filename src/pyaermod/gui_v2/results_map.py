"""
The Results step's concentration map, drawn from one plot file.

:func:`concentration_map_png` renders a :class:`~.run_results.PlotField`
(AERMOD's value at every receptor) as filled contours over the receptors,
with the sources of the run and the highest value marked. It uses
matplotlib's object API with the Agg canvas, never ``pyplot``, so it keeps
no global state and is safe to call from any thread.

The colours are one sequential hue, light (low) to dark (high); the map is
a picture of the numbers in the tables beside it, not a replacement for
them.
"""

from __future__ import annotations

import io
import math
from typing import Iterable, Optional, Sequence, Tuple

from .run_results import PlotField

#: A single-hue sequential ramp, light to dark (blue 100 to 700).
_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
_INK = "#2b2b2b"
_MUTED = "#6b6b6b"
_SOURCE = "#b8410b"


def _can_contour(x: Sequence[float], y: Sequence[float]) -> bool:
    if len(x) < 3:
        return False
    x0, y0 = x[0], y[0]
    # Contours need receptors that are not all on one line.
    for i in range(1, len(x)):
        for j in range(i + 1, len(x)):
            cross = (x[i] - x0) * (y[j] - y0) - (y[i] - y0) * (x[j] - x0)
            if abs(cross) > 1e-6:
                return True
    return False


def concentration_map_png(plot: PlotField, *, units: str = "µg/m³",
                          sources: Iterable[Tuple[str, float, float]] = (),
                          width_in: float = 7.0, height_in: float = 5.6,
                          dpi: int = 110) -> bytes:
    """The map of ``plot`` as PNG bytes.

    ``sources`` are ``(id, x, y)`` to mark; the receptor with the highest
    value is ringed and labelled with that value as AERMOD wrote it.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.figure import Figure

    x, y, v = list(plot.x), list(plot.y), list(plot.values)
    fig = Figure(figsize=(width_in, height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(1, 1, 1)
    cmap = LinearSegmentedColormap.from_list("pyaermod_blue", _RAMP)

    top = max(v) if v else 0.0
    mappable = None
    if top > 0 and _can_contour(x, y) and len(set(v)) > 1:
        levels = _levels(top)
        mappable = ax.tricontourf(x, y, v, levels=levels, cmap=cmap, extend="neither")
    ax.scatter(x, y, s=4, color=_MUTED, alpha=0.5, linewidths=0, zorder=3)

    for sid, sx, sy in sources:
        ax.scatter([sx], [sy], marker="^", s=70, color=_SOURCE, edgecolors="white",
                   linewidths=1.5, zorder=5)
        ax.annotate(sid, (sx, sy), xytext=(6, -12), textcoords="offset points",
                    fontsize=8, color=_INK, zorder=6)

    if v:
        px, py, pv = plot.peak
        ax.scatter([px], [py], s=90, facecolors="none", edgecolors=_INK, linewidths=2, zorder=6)
        ax.annotate(f"max {pv:.5f} {units}\nat ({px:.2f}, {py:.2f})", (px, py),
                    xytext=(8, 8), textcoords="offset points", fontsize=8, color=_INK,
                    zorder=7, bbox={"boxstyle": "round,pad=0.25", "fc": "white",
                                    "ec": "#d0d0d0", "lw": 0.8})

    if mappable is not None:
        bar = fig.colorbar(mappable, ax=ax, shrink=0.85, pad=0.02)
        bar.set_label(units, color=_INK)
        bar.outline.set_visible(False)
        bar.ax.tick_params(colors=_MUTED, labelsize=8)

    ax.set_title(plot.title, fontsize=10, color=_INK, loc="left")
    ax.set_xlabel("x (m)", color=_MUTED, fontsize=9)
    ax.set_ylabel("y (m)", color=_MUTED, fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")
    ax.tick_params(colors=_MUTED, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c8c8c8")
    ax.grid(True, color="#ececec", linewidth=0.6, zorder=0)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    return buf.getvalue()


def _levels(top: float, n: int = 8) -> list:
    """Evenly spaced contour levels from 0 to a round number above ``top``."""
    step = top / n
    magnitude = 10 ** math.floor(math.log10(step))
    for nice in (1, 2, 2.5, 5, 10):
        if nice * magnitude >= step:
            step = nice * magnitude
            break
    count = math.ceil(top / step)
    return [i * step for i in range(count + 1)]


def map_description(plot: PlotField, units: str, source_count: int = 0,
                    note: Optional[str] = None) -> str:
    """The map's accessible name: what it shows and its highest value."""
    px, py, pv = plot.peak
    text = (f"Concentration map of the {plot.title} from {plot.file.name}: "
            f"{len(plot.values)} receptors, highest {pv:.5f} {units} at "
            f"({px:.2f}, {py:.2f})")
    if source_count:
        text += f"; {source_count} source{'s' if source_count != 1 else ''} marked"
    return text + (f". {note}" if note else ".")


__all__ = ["concentration_map_png", "map_description"]
