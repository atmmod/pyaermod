"""The Results step (WP-G5), tier T1: pages rendered in-process.

Every run here is a recording of the real AERMOD binary replayed by the
end-to-end fake (``tests/fixtures/gui/aermod_recordings``), started from
the Run step as a user would. The assertions read what the page shows:
labels, table rows, the map's accessible name and the files the browser
receives. The numbers expected are AERMOD's own, from the recording's
summary tables (``tests/e2e/reference.py``).
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from . import test_gui_v2_smoke as smoke

# The in-process GUI harness of the smoke tests, shared.
gui = smoke.gui
recorded_aermod = smoke.recorded_aermod
_cheap_garbage_collection = smoke._cheap_garbage_collection
GuiSession = smoke.GuiSession
_agrees, _by_id = smoke._agrees, smoke._by_id
_title_input, _value_becomes = smoke._title_input, smoke._value_becomes

ui = pytest.importorskip("nicegui").ui

from pyaermod.gui_v2.project_io import save_project  # noqa: E402

from .e2e.reference import MAX_LOCATION, MAXIMA  # noqa: E402
from .test_gui_v2_session import _albany_project  # noqa: E402

REFERENCE_PERIODS = ["1", "3", "24", "PERIOD"]
E480_PERIODS = ["1", "ANNUAL"]
# AERMOD's summary tables of the albany_success recording, as printed.
PRINTED = {"1-HR": "76.07952", "3-HR": "59.57654", "24-HR": "16.85665", "PERIOD": "5.40459"}


async def _open_albany(gui: GuiSession, tmp_path, periods):
    path = save_project(_albany_project(periods, "AERMET2.SFC"), tmp_path / "albany.json")
    session = await gui.open()
    session.open_json(path)
    await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
    return session


async def _run_in(gui: GuiSession, work_dir, *, outcome: str, shows: str = "") -> None:
    """Run AERMOD in ``work_dir`` from the Run step; wait for ``outcome``
    there and for ``shows`` on Results (rebuilt a moment later)."""
    box = _by_id(gui.user.find(kind=ui.input, content="Working directory").elements,
                 newest=True)
    with gui.user:
        box.value = str(work_dir)
    gui.user.find(kind=ui.button, content="Run AERMOD").click()
    await gui.user.should_see(outcome, retries=100)
    if shows:
        await gui.user.should_see(shows, retries=100)


def _one(gui: GuiSession, **kw):
    return _by_id(gui.user.find(**kw).elements, newest=True)


def _maxima(gui: GuiSession):
    return {r["period"]: r for r in _one(gui, kind=ui.table, marker="results-maxima").rows}


def _no_element(gui: GuiSession, **kw) -> bool:
    with gui.user:
        from nicegui import ElementFilter
        return not list(ElementFilter(local_scope=False, **kw))


async def _download(gui: GuiSession, label: str) -> bytes:
    gui.user.find(kind=ui.button, content=label).click()
    return (await gui.user.download.next()).content


class TestSuccessfulRun:
    @pytest.mark.asyncio
    async def test_maxima_and_locations_are_aermods(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        work_dir = tmp_path / "run"
        await _run_in(gui, work_dir, outcome="Run succeeded", shows="Run 1 succeeded")
        gui.user.find(kind=ui.tab, content="Results").click()
        await gui.user.should_see("Run 1 succeeded")
        await gui.user.should_see(
            "AERMOD finished successfully with 0 fatal errors and 6 warnings.")
        await gui.user.should_see(f"Working directory: {work_dir}")
        await gui.user.should_see("Output file: pyaermod_gui.out")
        await gui.user.should_see("Maximum for each averaging period")
        rows = _maxima(gui)
        assert list(rows) == ["1-HR", "3-HR", "24-HR", "PERIOD"]
        for label, printed in PRINTED.items():
            row = rows[label]
            # Exactly the text AERMOD printed, which is the reference value.
            assert row["value"] == printed
            key = label.replace("-", "") if label != "PERIOD" else label
            assert _agrees(row["value"], MAXIMA[key])
            assert (row["x"], row["y"]) == ("519.62", "-300.00")
            assert (float(row["x"]), float(row["y"])) == pytest.approx(MAX_LOCATION)
            assert row["units"] == "µg/m³" and row["group"] == "ALL"
            # One card per period, with the same value.
            await gui.user.should_see(printed)
        assert rows["1-HR"]["date"] == "88030111"
        assert rows["PERIOD"]["table"] == "THE SUMMARY OF MAXIMUM PERIOD ( 96 HRS) RESULTS"

    @pytest.mark.asyncio
    async def test_every_rank_is_in_a_table_per_period(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        await _run_in(gui, tmp_path / "run", outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Summary tables")
        tables = gui.user.find(kind=ui.table, marker="results-table").elements
        assert len(tables) == 4
        by_name = {t.props["aria-label"]: t for t in tables}
        one = by_name["Concentration, 1-HR: THE SUMMARY OF HIGHEST 1-HR RESULTS"]
        assert [r["rank"] for r in one.rows] == list(range(1, 11))
        # HIGH 2ND HIGH VALUE IS 59.73798 ON 88030113: AT ( 433.01, -250.00, ...
        assert (one.rows[1]["value"], one.rows[1]["date"], one.rows[1]["x"],
                one.rows[1]["y"]) == ("59.73798", "88030113", "433.01", "-250.00")
        day = by_name["Concentration, 24-HR: THE SUMMARY OF HIGHEST 24-HR RESULTS"]
        # Four days of met data: ranks 5 to 10 are empty (0.00000 ON 00000000).
        assert day.rows[4]["value"] == "0.00000" and day.rows[4]["date"] == "00000000"

    @pytest.mark.asyncio
    async def test_map_is_drawn_from_the_plot_files(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        await _run_in(gui, tmp_path / "run", outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Concentration map")
        image = _one(gui, kind=ui.image, marker="results-map")
        alt = image.props["alt"]
        assert alt.startswith("Concentration map of the 1ST highest 1-HR values")
        assert "pyaermod_gui_01H.PLT: 360 receptors, highest 76.07952" in alt
        assert "at (519.62, -300.00)" in alt
        # The map is drawn in the background, a moment after the page.
        await _value_becomes(lambda: _one(gui, kind=ui.image, marker="results-map").source[:22],
                             "data:image/png;base64,")
        await gui.user.should_see("Drawn from pyaermod_gui_01H.PLT; the tables hold the values.")

        choose = _one(gui, kind=ui.select, content="Map shows")
        assert len(choose.options) == 4
        with gui.user:
            choose.value = 3                                # PERIOD
        await gui.user.should_see("Drawn from pyaermod_gui_PER.PLT; the tables hold the values.")
        alt = _one(gui, kind=ui.image, marker="results-map").props["alt"]
        assert "PERIOD average values" in alt and "highest 5.40459" in alt

    @pytest.mark.asyncio
    async def test_so2_is_compared_with_its_naaqs(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        await _run_in(gui, tmp_path / "run", outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Comparison with the NAAQS")
        [row] = _one(gui, kind=ui.table, marker="results-naaqs").rows
        assert row["standard"] == "SO2 1-hour (99th percentile of daily max)"
        assert row["level"] == "196.4 µg/m³ (75 ppb)"
        assert row["value"] == "76.07952 µg/m³" and row["at"] == "(519.62, -300.00)"
        # Four days of met and no POSTFILE: a screen against the maximum.
        assert row["basis"] == "screening"
        assert row["verdict"] == "Below the NAAQS (so is any design value)"

    @pytest.mark.asyncio
    async def test_downloads_are_the_files_on_disk(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        work_dir = tmp_path / "run"
        await _run_in(gui, work_dir, outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Downloads")
        assert await _download(gui, "Download deck") == (work_dir / "pyaermod_gui.inp").read_bytes()
        out = await _download(gui, "Download AERMOD output (.out)")
        assert out == (work_dir / "pyaermod_gui.out").read_bytes()
        assert b"AERMOD Finishes Successfully" in out
        plot = await _download(gui, "Download plot file pyaermod_gui_24H.PLT")
        assert plot == (work_dir / "pyaermod_gui_24H.PLT").read_bytes()

    @pytest.mark.asyncio
    async def test_kmz_needs_a_utm_zone_and_holds_the_run(self, gui, recorded_aermod, tmp_path):
        pytest.importorskip("pyproj")
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        await _run_in(gui, tmp_path / "run", outcome="Run succeeded", shows="Run 1 succeeded")
        gui.user.find(kind=ui.button, content="Download KMZ").click()
        await gui.user.should_see("Enter the UTM zone of the model's x and y")
        zone = _one(gui, kind=ui.number, content="UTM zone of the coordinates")
        with gui.user:
            zone.value = 18
        data = await _download(gui, "Download KMZ")
        kml = zipfile.ZipFile(io.BytesIO(data)).read("doc.kml").decode()
        assert "Run 1: 1ST highest 1-HR values, source group ALL" in kml
        assert "STACK1" in kml
        assert kml.count("<Placemark>") == 1 + 360
        assert "Concentration: 76.08" in kml


class TestFailedRun:
    @pytest.mark.asyncio
    async def test_a_failed_run_says_so_and_shows_no_values(self, gui, recorded_aermod, tmp_path):
        gui.expect_error_log("AERMOD run failed: E480")
        recorded_aermod("albany_e480")
        await _open_albany(gui, tmp_path, E480_PERIODS)
        work_dir = tmp_path / "run"
        await _run_in(gui, work_dir, outcome="Run reported FATAL", shows="Run 1 failed")
        await gui.user.should_see("Run 1 failed")
        await gui.user.should_see("AERMOD stopped with 1 fatal error and 5 warnings.")
        await gui.user.should_see(
            "E480 MAIN: Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave NUMYRS=0")
        await gui.user.should_see("No results are shown for a failed run")
        assert _no_element(gui, kind=ui.table, marker="results-maxima")
        assert _no_element(gui, kind=ui.image, marker="results-map")
        assert _no_element(gui, kind=ui.table, marker="results-naaqs")
        await gui.user.should_not_see("Download plot file")
        await gui.user.should_not_see("Download KMZ")
        # The deck and AERMOD's own report, to find out why.
        assert await _download(gui, "Download deck") == (work_dir / "pyaermod_gui.inp").read_bytes()
        out = await _download(gui, "Download AERMOD output (.out)")
        assert b"AERMOD Finishes UN-successfully" in out


class TestRunHistory:
    @pytest.mark.asyncio
    async def test_the_newest_run_is_shown_and_an_earlier_one_can_be_reopened(
            self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        first, second = tmp_path / "first", tmp_path / "second"
        await _run_in(gui, first, outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Run 1 succeeded")
        await _run_in(gui, second, outcome="Run succeeded", shows="Run 2 succeeded")
        await gui.user.should_see("Run 2 succeeded")
        await gui.user.should_see(f"Working directory: {second}")
        history = _one(gui, kind=ui.select, content="Run shown")
        assert [re.sub(r"\d\d:\d\d:\d\d", "hh:mm:ss", v) for v in history.options.values()] == [
            "Run 2, finished hh:mm:ss: succeeded", "Run 1, finished hh:mm:ss: succeeded"]
        with gui.user:
            history.value = 1
        await gui.user.should_see("Run 1 succeeded")
        await gui.user.should_see(f"Working directory: {first}")
        await gui.user.should_not_see("Run 2 succeeded")
        assert _maxima(gui)["1-HR"]["value"] == "76.07952"
        # A new run shows itself again.
        await _run_in(gui, tmp_path / "third", outcome="Run succeeded", shows="Run 3 succeeded")
        await gui.user.should_see("Run 3 succeeded")

    @pytest.mark.asyncio
    async def test_a_run_whose_files_were_overwritten_keeps_its_values(
            self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        work_dir = tmp_path / "run"
        await _run_in(gui, work_dir, outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Run 1 succeeded")
        await _run_in(gui, work_dir, outcome="Run succeeded", shows="Run 2 succeeded")
        await gui.user.should_see("Run 2 succeeded")
        with gui.user:
            _one(gui, kind=ui.select, content="Run shown").value = 1
        await gui.user.should_see("Run 1 succeeded")
        await gui.user.should_see("Run 2 wrote into the same working directory after this run")
        assert _maxima(gui)["3-HR"]["value"] == "59.57654"
        deck = _one(gui, kind=ui.button, content="Download deck")
        assert not deck.enabled

    @pytest.mark.asyncio
    async def test_before_any_run(self, gui):
        await gui.open()
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")
        await gui.user.should_see(kind=ui.button, content="Go to Run")


class TestReload:
    @pytest.mark.asyncio
    async def test_a_reload_shows_the_same_run(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
        await _run_in(gui, tmp_path / "run", outcome="Run succeeded", shows="Run 1 succeeded")
        await gui.user.should_see("Run 1 succeeded")
        await gui.open()
        await gui.user.should_see("Run 1 succeeded")
        assert _maxima(gui)["24-HR"]["value"] == "16.85665"
        assert "highest 76.07952" in _one(gui, kind=ui.image, marker="results-map").props["alt"]



class TestImportedAertest:
    """EPA's AERTEST deck: a 1-hour POSTFILE, so a design value can be computed."""

    @pytest.mark.asyncio
    async def test_postfile_gives_a_design_value_and_a_download(self, gui, recorded_aermod,
                                                                 tmp_path):
        from pyaermod.input_reader import read_aermod_input

        from .e2e.reference import AERTEST_RECORDING

        recorded_aermod("aertest")
        project = read_aermod_input(AERTEST_RECORDING / "aertest.inp")
        path = save_project(project, tmp_path / "aertest.json")
        session = await gui.open()
        session.open_json(path)
        await _value_becomes(lambda: _title_input(gui).value, project.control.title_one)
        work_dir = tmp_path / "run"
        await _run_in(gui, work_dir, outcome="Run succeeded", shows="Run 1 succeeded")
        rows = _maxima(gui)
        # AERTEST.SUM: 1-HR 753.65603 at (303.11, -175.00); PERIOD 24.85173.
        assert (rows["1-HR"]["value"], rows["1-HR"]["x"], rows["1-HR"]["y"]) == (
            "753.65603", "303.11", "-175.00")
        assert rows["PERIOD"]["value"] == "24.85173"
        [check] = _one(gui, kind=ui.table, marker="results-naaqs").rows
        assert check["basis"] == "design value"
        assert check["how"].startswith("design value computed by pyaermod from AERTEST_01H.PST")
        # Four days: the 99th percentile of four daily maxima is the highest.
        assert check["value"] == "753.65603 µg/m³"
        assert check["verdict"] == "Above the NAAQS"
        data = await _download(gui, "Download POSTFILE AERTEST_01H.PST")
        assert data == (work_dir / "AERTEST_01H.PST").read_bytes()
        alt = _one(gui, kind=ui.image, marker="results-map").props["alt"]
        assert "AERTEST_01H.PLT: 144 receptors, highest 753.65603" in alt
