"""Receptors tab — placeholder until v1.9-C."""

from __future__ import annotations

from ..state import AppState


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Receptors").classes("text-h6")
    n_cart = len(state.project.receptors.cartesian_grids)
    n_pol = len(state.project.receptors.polar_grids)
    n_disc = len(state.project.receptors.discrete_receptors)
    ui.label(
        f"This tab will be ported in v1.9-C. "
        f"Current project: {n_cart} Cartesian grid(s), "
        f"{n_pol} polar grid(s), {n_disc} discrete receptor(s)."
    ).classes("text-body1 q-mt-sm")
