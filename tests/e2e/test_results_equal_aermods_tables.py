"""Every value on the Results step is AERMOD's own (WP-G5's acceptance).

J1 and J5 check the maxima and the plot file; these journeys read every
row the Results step shows, the "Maximum for each averaging period"
table and each summary table, and compare it with the summary tables of
the ``.out`` file the run left, read here with a few regular expressions
and not with pyaermod, so the parser the GUI uses is not its own oracle.

AERTEST is imported through Import deck, as J5 does, run and opened on
Results (PLAN-gui.md's J5 row); Albany is the reference scenario of J1.
Tier T2 replays the recordings, tier T3 runs the real binary.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, List

import pytest

from .harness import EPA_FIXTURES, deck_written_to
from .reference import (
    AERTEST_MAXIMA,
    AERTEST_RECORDING,
    AVERAGING_PERIODS,
    MAX_LOCATION,
    MAXIMA,
    enter_reference_scenario,
)

pytestmark = pytest.mark.e2e

_TABLE = re.compile(r"\*\*\* THE SUMMARY OF (?:HIGHEST\s+(\d+)-HR|MAXIMUM (PERIOD|ANNUAL))\b")
_ROW = re.compile(
    r"^(?P<group>\S+)?\s+(?:HIGH\s+)?(?P<rank>\d+)(?:ST|ND|RD|TH) HIGH(?:EST)? VALUE IS\s+"
    r"(?P<value>[-\d.]+)(?P<flag>[cmb]?)\s+(?:ON (?P<date>\d{8}):\s*)?"
    r"AT \(\s*(?P<x>[-\d.]+),\s*(?P<y>[-\d.]+),[^)]*\)"
    # An empty rank (fewer values than ranks) names no receptor.
    r"(?:\s+(?P<type>\S+)\s+(?P<grid>\S+))?")


def aermods_tables(out: Path) -> Dict[str, List[dict]]:
    """``{"1-HR": [rows by rank], "PERIOD": [...]}`` from the .out's summary tables."""
    tables: Dict[str, List[dict]] = {}
    current = None
    group = ""
    for line in out.read_text(errors="replace").splitlines():
        heading = _TABLE.search(line)
        if heading:
            current = f"{heading.group(1)}-HR" if heading.group(1) else heading.group(2)
            tables[current] = []
            continue
        if current is None:
            continue
        if line.startswith(" *** RECEPTOR TYPES"):
            current = None
            continue
        row = _ROW.match(line)
        if row is None:
            assert "VALUE IS" not in line, f"unread summary row: {line!r}"
            continue
        group = row["group"] or group
        tables[current].append(dict(
            group=group, rank=row["rank"], value=row["value"], flag=row["flag"],
            date=row["date"] or "", x=f"{float(row['x']):.2f}", y=f"{float(row['y']):.2f}",
            type=row["type"] or "", grid=row["grid"] or ""))
    return tables


def _period_key(label: str) -> str:
    return label.replace("-", "")


def expect_results_equal(gui, out: Path) -> Dict[str, List[dict]]:
    """Every maximum and every rank on Results is the .out's."""
    expected = aermods_tables(out)
    assert expected, f"no summary tables in {out}"

    maxima = {row["Period"]: row for row in gui.results.maxima_rows()}
    assert sorted(maxima) == sorted(expected), (
        f"periods shown {list(maxima)}, the .out has {list(expected)}")
    for period, rows in expected.items():
        top, shown = rows[0], maxima[period]
        assert (shown["Max"], shown["X (m)"], shown["Y (m)"], shown["Date (YYMMDDHH)"],
                shown["Group"]) == (top["value"], top["x"], top["y"], top["date"],
                                    top["group"]), (
            f"{period} maximum shows {shown}, the .out has {top}")
        _expect_note(shown["Note"], top["flag"], f"{period} maximum")

    names = gui.results.summary_table_names()
    assert len(names) == len(expected), names
    for period, rows in expected.items():
        [name] = [n for n in names if re.match(rf"Concentration, {re.escape(period)}: ", n)]
        shown = gui.results.summary_table(name)
        assert len(shown) == len(rows), f"{name}: {len(shown)} rows, the .out has {len(rows)}"
        for got, want in zip(shown, rows):
            assert (got["Rank"], got["Value (µg/m³)"], got["Date (YYMMDDHH)"], got["X (m)"],
                    got["Y (m)"], got["Receptor type"], got["Network"]) == (
                want["rank"], want["value"], want["date"], want["x"], want["y"],
                want["type"], want["grid"]), f"{name} rank {want['rank']}: {got} vs {want}"
            _expect_note(got["Note"], want["flag"], f"{name} rank {want['rank']}")
    return expected


def _expect_note(note: str, flag: str, where: str) -> None:
    """AERMOD's calm/missing flag, explained ("b: includes calm and missing hours")."""
    if flag:
        assert note.startswith(f"{flag}: "), f"{where}: note {note!r}, flag {flag!r}"
    else:
        assert note == "", f"{where}: note {note!r} without a flag"


@pytest.mark.aermod_recording("aertest")
def test_aertest_results_equal_aermods_tables(gui, step, run_dir, tmp_path):
    deck_dir = tmp_path / "aertest"
    deck_dir.mkdir()
    shutil.copy(AERTEST_RECORDING / "aertest.inp", deck_dir)
    for met in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(EPA_FIXTURES / met, deck_dir)

    gui.open()
    gui.project.import_deck(deck_dir / "aertest.inp")
    gui.meteorology.set_met_files(deck_dir / "AERMET2.SFC", deck_dir / "AERMET2.PFL")
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    gui.run.reports_success()

    gui.results.open()
    step("results")
    out = deck_written_to(run_dir).with_suffix(".out")
    tables = expect_results_equal(gui, out)
    assert [len(rows) for rows in tables.values()] == [10, 3, 3, 3, 3]
    shown = {_period_key(r["Period"]): (r["Max"], r["X (m)"], r["Y (m)"])
             for r in gui.results.maxima_rows()}
    assert shown == AERTEST_MAXIMA
    gui.results.expect_map()
    gui.results.expect_naaqs_design_value_from("AERTEST_01H.PST")


@pytest.mark.aermod_recording("albany_success")
def test_albany_results_equal_aermods_tables(gui, step, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    gui.run.reports_success()

    gui.results.open()
    step("results")
    tables = expect_results_equal(gui, deck_written_to(run_dir).with_suffix(".out"))
    assert [len(rows) for rows in tables.values()] == [10, 10, 10, 10]
    gui.results.expect_maxima(MAXIMA, MAX_LOCATION)
