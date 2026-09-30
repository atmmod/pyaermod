"""
The blank project the GUI starts from.

In WP-G2 the per-tab ``AppState`` that used to live here was replaced by
:class:`pyaermod.gui_v2.session.Session`, which owns the project, its
file, the unsaved-changes flag and the run history, and tells the pages
what changed. :func:`_empty_project` stays here because
``scripts/record_aermod_fixtures.py`` builds the recorded AERMOD decks
from it: the end-to-end journeys' fake AERMOD checks that the GUI writes
exactly those decks, so this function's body must not change casually:
a change that alters the deck means recording the scenarios again with
the real binary (WP-G3 did, when the plot files and POSTFILEs the
Results step reads became the default).
"""

from __future__ import annotations

from ..input_generator import (
    AERMODProject,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)


def _empty_project() -> AERMODProject:
    """Return a blank AERMODProject suitable as a starting point."""
    return AERMODProject(
        control=ControlPathway(
            title_one="Untitled run",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["1", "ANNUAL"],
        ),
        sources=SourcePathway(sources=[]),
        receptors=ReceptorPathway(),
        meteorology=MeteorologyPathway(
            surface_file="", profile_file="",
        ),
        # A plot file and a POSTFILE for every averaging period, which the
        # Results step reads (pages/output.py, PERIOD_FILE_STEM).
        output=OutputPathway(period_plot_files="pyaermod", period_postfiles="pyaermod"),
    )


__all__ = ["_empty_project"]
