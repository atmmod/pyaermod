"""G10: with no BACKGRND in the project the NAAQS comparison must say it is the modelled value alone.

The wording is the maintainer's; the test only requires that the NAAQS section says
"background" somewhere (NAAQS compliance is judged on modelled plus background).
"""

import pytest

pytest.importorskip("nicegui", minversion="3.4.0")

from nicegui import ElementFilter, ui

from . import test_gui_v2_smoke as smoke
from .test_gui_v2_results import REFERENCE_PERIODS, _one, _open_albany, _run_in

gui = smoke.gui
recorded_aermod = smoke.recorded_aermod
pytestmark = smoke.pytestmark


@pytest.mark.asyncio
async def test_the_naaqs_comparison_says_no_background_was_added(gui, recorded_aermod, tmp_path):
    recorded_aermod("albany_success")
    session = await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
    assert session.project.sources.background is None
    await _run_in(gui, tmp_path / "run", outcome="Succeeded in", shows="Run 1 succeeded")
    await gui.user.should_see("Comparison with the NAAQS")
    [row] = _one(gui, kind=ui.table, marker="results-naaqs").rows
    texts = [str(v) for v in row.values()]
    with gui.user:
        texts += [getattr(e, "text", "") or "" for e in ElementFilter(kind=ui.label, local_scope=False)]
    assert any("background" in t.lower() for t in texts), "nothing says the verdict leaves background out"
