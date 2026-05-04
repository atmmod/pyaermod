"""
Results tab.

Surfaces the most-recent run's outputs:

- Run summary (success, return code, runtime)
- Parsed .OUT file (sources / averaging periods / max concentrations)
- POSTFILE viewer (if any .PST files in the working dir)

State source: :class:`AppState.last_run_dir`. If empty (no run yet),
the page shows a placeholder.

Heavy data analysis (contour plots, animations) lives in
:mod:`pyaermod.advanced_viz` — the Results tab is a quick triage view,
not a replacement for that module.
"""

from __future__ import annotations

from pathlib import Path

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Results").classes("text-h6")

    if state.last_run_dir is None:
        ui.label(
            "No run yet. Use the Run tab to dispatch AERMOD.",
        ).classes("text-grey q-mt-sm")
        return

    wd = state.last_run_dir
    ui.label(f"Last run directory: {wd}").classes("text-body1")

    # ---- .OUT file summary ------------------------------------------
    out_files = list(wd.glob("*.out")) + list(wd.glob("*.OUT"))
    if not out_files:
        ui.label("(no .OUT file found in working directory)").classes(
            "text-grey q-mt-sm",
        )
        return

    out_path = max(out_files, key=lambda p: p.stat().st_mtime)
    ui.label(f"Output file: {out_path.name}").classes("text-subtitle1 q-mt-md")

    try:
        from ...output_parser import AERMODOutputParser
        parser = AERMODOutputParser(out_path)
        results = parser.parse()
    except Exception as exc:
        ui.label(f"Could not parse {out_path.name}: {exc}").classes(
            "text-negative",
        )
        return

    # Run info block
    info = results.run_info
    if info is not None:
        with ui.card().classes("q-mt-sm"):
            ui.markdown(
                f"**Title:** {info.title or '(none)'}  \n"
                f"**Pollutant:** {info.pollutant or '(none)'}  \n"
                f"**Sources:** {len(results.sources)}  \n"
                f"**Receptors:** {len(results.receptors)}",
            )

    # Source summary table
    if results.sources:
        ui.label("Sources").classes("text-subtitle1 q-mt-md")
        rows = [
            {
                "id": s.source_id,
                "type": s.source_type,
                "Q": s.emission_rate,
            }
            for s in results.sources
        ]
        ui.table(
            columns=[
                {"name": "id",   "label": "ID",   "field": "id"},
                {"name": "type", "label": "Type", "field": "type"},
                {"name": "Q",    "label": "Q (g/s)", "field": "Q"},
            ],
            rows=rows, row_key="id",
        ).classes("w-full")

    # Concentration block
    if results.concentrations:
        ui.label("Max concentrations").classes("text-subtitle1 q-mt-md")
        rows = [
            {
                "period":   c.averaging_period,
                "value":    f"{c.max_value:.4g}",
                "x":        c.max_x,
                "y":        c.max_y,
                "group":    c.source_group,
            }
            for c in results.concentrations
        ]
        ui.table(
            columns=[
                {"name": "period", "label": "Period", "field": "period"},
                {"name": "value",  "label": "Max",    "field": "value"},
                {"name": "x",      "label": "X",      "field": "x"},
                {"name": "y",      "label": "Y",      "field": "y"},
                {"name": "group",  "label": "Group",  "field": "group"},
            ],
            rows=rows, row_key="period",
        ).classes("w-full")

    # POSTFILE list
    psts = list(wd.glob("*.PST")) + list((wd / "postfiles").glob("*.PST"))
    if psts:
        ui.label("POSTFILE outputs").classes("text-subtitle1 q-mt-md")
        for p in sorted(psts):
            size_kb = p.stat().st_size / 1024
            ui.label(f"{p.name}  ({size_kb:.1f} KiB)").classes(
                "text-body2 text-grey",
            )


__all__ = ["render"]


def _ensure_path(p) -> Path:
    """Coerce ``p`` to a Path. Currently unused but kept for v1.9-D
    follow-ups (POSTFILE viewer)."""
    return Path(p) if not isinstance(p, Path) else p
