"""J7: add, edit and delete sources and receptors of several types.

What the user must see (PLAN-gui.md): table rows, the empty-state message,
the plan-view plot and the step badges update after every action; integer
fields show integers, and the deck contains ``SURFDATA  14735  1988``.

The tables already follow every action. The other four behaviours are
independent gaps, so each has its own test.
"""

from __future__ import annotations

import re

import pytest

from .harness import deck_written_to
from .reference import (
    E480_AVERAGING_PERIODS,
    GRID,
    STACK,
    enter_reference_scenario,
)

pytestmark = pytest.mark.e2e


def test_j07_tables_follow_add_edit_and_delete(gui, step):
    gui.open()
    gui.sources.add_point_source(**STACK)
    gui.sources.add_volume_source(id="VOL1", x=100, y=50, release_height=10,
                                  emission_rate=2)
    gui.sources.expect_ids(["STACK1", "VOL1"])
    gui.sources.expect_row("VOL1", kind="VolumeSource", x=100, y=50, emission_rate=2)
    step("two_sources")

    gui.sources.edit_source("STACK1", emission_rate=150, stack_height=70)
    gui.sources.expect_row("STACK1", kind="PointSource", emission_rate=150)
    assert float(gui.sources.editor_value("STACK1", "stack height")) == 70
    gui.sources.delete_source("VOL1")
    gui.sources.expect_ids(["STACK1"])
    step("sources_edited")

    gui.receptors.add_cartesian_grid(name="CART1", x_init=-500, x_num=11,
                                     x_delta=100, y_init=-500, y_num=11,
                                     y_delta=100)
    gui.receptors.add_polar_grid(**GRID)
    gui.receptors.add_discrete_receptor(x=250, y=250)
    gui.receptors.expect_count(3)
    gui.receptors.expect_cartesian_grid("CART1", nx=11, ny=11)
    gui.receptors.expect_polar_grid("GRID1", rings=10, directions=36)
    gui.receptors.expect_discrete_receptor(x=250, y=250)
    step("three_receptors")

    gui.receptors.edit_receptor("GRID1", "PolarGrid", dist_num=12)
    gui.receptors.expect_polar_grid("GRID1", rings=12, directions=36)
    gui.receptors.delete_receptor("CART1")
    gui.receptors.expect_count(2)
    gui.receptors.expect_polar_grid("GRID1", rings=12, directions=36)
    gui.receptors.expect_discrete_receptor(x=250, y=250)
    step("receptors_edited")


def test_j07_empty_state_message_follows_the_list(gui, step, known_gap):
    gui.open()
    gui.sources.expect_empty_state(True)
    gui.sources.add_point_source(**STACK)
    step("one_source")
    with known_gap("WP-G3", "empty-state message persists after an item is added"):
        gui.sources.expect_empty_state(False)
    gui.sources.delete_source("STACK1")
    gui.sources.expect_empty_state(True)

    gui.receptors.expect_empty_state(True)
    gui.receptors.add_polar_grid(**GRID)
    gui.receptors.expect_empty_state(False)
    gui.receptors.delete_receptor("GRID1")
    gui.receptors.expect_empty_state(True)


@pytest.mark.aermod_recording("albany_e480")
def test_j07_integer_fields_show_and_write_integers(gui, step, known_gap, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    deck = deck_written_to(run_dir).read_text(encoding="utf-8")
    surfdata = [ln.strip() for ln in deck.splitlines() if "SURFDATA" in ln]
    step("run_finished")

    with known_gap("WP-G3", "integer fields written as floats"):
        assert re.search(r"^\s*SURFDATA\s+14735\s+1988\s*$", deck, re.M), (
            f"the deck the user gets says {surfdata}")
        gui.meteorology.expect_station_ids("14735", "14735", "1988")


def test_j07_plan_view_follows_the_project(gui, step, known_gap):
    gui.open()
    gui.sources.add_point_source(**STACK)
    step("one_source")
    with known_gap("WP-G3", "no plan-view plot"):
        gui.sources.expect_plan_view_shows("STACK1")
    gui.receptors.add_polar_grid(**GRID)
    gui.receptors.expect_plan_view_shows("STACK1", "GRID1")


def test_j07_step_badges_follow_the_project(gui, step, known_gap):
    gui.open()
    step("blank")
    with known_gap("WP-G3", "no step status badges"):
        gui.expect_step_status("Sources", "not started")
    gui.sources.add_point_source(**STACK)
    gui.expect_step_status("Sources", "complete")
    gui.sources.delete_source("STACK1")
    gui.expect_step_status("Sources", "not started")
