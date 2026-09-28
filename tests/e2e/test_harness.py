"""Checks of the journey harness itself: the fake AERMOD and ``known_gap``.

None of these needs a browser or a GUI server. They are marked ``e2e`` so
they run with the journeys that depend on them.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import pytest

from pyaermod.runner import AERMODRunner

from .fake_aermod import deck_diff, normalize_deck
from .harness import (
    RECORDINGS,
    REPO,
    KnownGap,
    PlaywrightTimeoutError,
    install_fake_aermod,
)
from .reference import MAX_LOCATION, MAXIMA

pytestmark = pytest.mark.e2e

SUCCESS = RECORDINGS / "albany_success"


# -- deck comparison ----------------------------------------------------------

def test_deck_comparison_ignores_titles_met_directories_and_number_format():
    recorded = (SUCCESS / "aermod.inp").read_text()
    gui = (recorded
           .replace("Albany stack reference scenario", "Anything the user typed")
           .replace("SURFFILE  AERMET2.SFC", "SURFFILE  /data/met/AERMET2.SFC")
           .replace("PROFFILE  AERMET2.PFL", r"PROFFILE  C:\met\AERMET2.PFL")
           .replace("SURFDATA  14735  1988", "SURFDATA  14735.0  1988.0")
           .replace("CO FINISHED", "   TITLETWO  A second line\nCO FINISHED"))
    assert gui != recorded
    assert deck_diff(recorded, gui, recorded_name="a", given_name="b") == ""


def test_deck_comparison_reports_a_real_difference():
    recorded = (SUCCESS / "aermod.inp").read_text()
    gui = recorded.replace("AVERTIME  1 3 24 PERIOD", "AVERTIME  1 ANNUAL")
    diff = deck_diff(recorded, gui, recorded_name="rec", given_name="gui")
    assert "-AVERTIME 1.0 3.0 24.0 PERIOD" in diff
    assert "+AVERTIME 1.0 ANNUAL" in diff


def test_deck_normalisation_drops_pathway_prefixes_and_comments():
    assert normalize_deck("** note\nSO BUILDHGT  STACK1  36*50.\n\n") == [
        "BUILDHGT STACK1 36*50."]
    assert normalize_deck("   LOCATION  S1  POINT  -0.0  1.50") == [
        "LOCATION S1 POINT 0.0 1.5"]


# -- replay -------------------------------------------------------------------

def _run_fake(tmp_path, recording, deck_text, **env):
    fake = install_fake_aermod(tmp_path / "bin")
    work = tmp_path / "work"
    work.mkdir()
    (work / "aermod.inp").write_text(deck_text)
    log = tmp_path / "fake.jsonl"
    full_env = dict(os.environ, PYAERMOD_E2E_RECORDING=str(RECORDINGS / recording),
                    PYAERMOD_E2E_FAKE_LOG=str(log), **env)
    proc = subprocess.run([str(fake)], cwd=work, capture_output=True, env=full_env,
                          timeout=60, check=False)
    events = [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []
    return proc, work, events


def test_fake_replays_stdout_outputs_and_exit_code(tmp_path):
    deck = (SUCCESS / "aermod.inp").read_text().replace("14735", "14735.0")
    proc, work, events = _run_fake(tmp_path, "albany_success", deck)
    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout == (SUCCESS / "stdout.txt").read_bytes()
    assert (work / "aermod.out").read_bytes() == (
        SUCCESS / "outputs" / "aermod.out").read_bytes()
    assert [e["event"] for e in events] == ["start", "finish"]


def test_fake_replays_an_aborted_run_with_exit_code_zero(tmp_path):
    e480 = RECORDINGS / "albany_e480"
    proc, work, _ = _run_fake(tmp_path, "albany_e480", (e480 / "aermod.inp").read_text())
    assert proc.returncode == 0
    assert b"Fatal Error Occurred During Runtime Phase!" in proc.stdout
    assert "E480" in (work / "aermod.out").read_text(encoding="latin-1")


def test_fake_replays_aertest_with_epas_plot_file(tmp_path):
    """Every output comes back under its own name, compressed ones included."""
    aertest = RECORDINGS / "aertest"
    proc, work, _ = _run_fake(tmp_path, "aertest", (aertest / "aermod.inp").read_text())
    assert proc.returncode == 0, proc.stderr.decode()
    manifest = json.loads((aertest / "manifest.json").read_text())
    assert sorted(p.name for p in work.iterdir() if p.name != "aermod.inp") == sorted(
        manifest["outputs"])
    assert (work / "AERTEST_01H.PST").read_bytes() == gzip.decompress(
        (aertest / "outputs" / "AERTEST_01H.PST.gz").read_bytes())
    assert (work / "AERTEST_01H.PLT").read_bytes() == (
        aertest / "outputs" / "AERTEST_01H.PLT").read_bytes()


def test_fake_refuses_a_deck_it_did_not_record(tmp_path):
    deck = (SUCCESS / "aermod.inp").read_text().replace("100.000000", "99.000000")
    proc, work, events = _run_fake(tmp_path, "albany_success", deck)
    assert proc.returncode == 2
    assert b"differs from recording 'albany_success'" in proc.stderr
    assert b"+SRCPARAM STACK1 99.0" in proc.stderr
    assert not (work / "aermod.out").exists()
    assert events[-1]["event"] == "deck_mismatch"


def test_fake_pauses_between_lines(tmp_path):
    deck = (SUCCESS / "aermod.inp").read_text()
    lines = len((SUCCESS / "stdout.txt").read_bytes().splitlines())
    proc, _, events = _run_fake(tmp_path, "albany_success", deck,
                                PYAERMOD_E2E_DELAY="0.05")
    assert proc.returncode == 0
    elapsed = events[-1]["time"] - events[0]["time"]
    assert elapsed >= 0.05 * (lines - 1)


def test_fake_through_the_library_runner_gives_the_reference_maxima(tmp_path):
    """AERMODRunner points aermod.inp at the deck and renames aermod.out."""
    fake = install_fake_aermod(tmp_path / "bin")
    deck = tmp_path / "reference.inp"
    shutil.copy(SUCCESS / "aermod.inp", deck)
    os.environ["PYAERMOD_E2E_RECORDING"] = str(SUCCESS)
    try:
        result = AERMODRunner(executable_path=fake, log_level="ERROR").run(
            deck, working_dir=tmp_path, timeout=60)
    finally:
        del os.environ["PYAERMOD_E2E_RECORDING"]
    assert result.success, result.error_message
    from pyaermod.output_parser import AERMODOutputParser

    parsed = AERMODOutputParser(result.output_file).parse().concentrations
    for period, value in MAXIMA.items():
        assert parsed[period].max_value == pytest.approx(value, abs=5e-6)
        assert tuple(parsed[period].max_location) == pytest.approx(MAX_LOCATION)


# -- recordings -----------------------------------------------------------------

def _recorder():
    name = "record_aermod_fixtures"
    if name not in sys.modules:
        path = REPO / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        # Registered first: its dataclass looks its own module up by name.
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.mark.parametrize("scenario", ["albany_success", "albany_e480",
                                      "missing_met", "aertest"])
def test_recorded_deck_is_what_the_library_writes_today(scenario, tmp_path):
    """A writer change that alters a scenario's deck means: re-record."""
    built = _recorder()._scenarios()[scenario].build_deck(tmp_path)
    recorded = (RECORDINGS / scenario / "aermod.inp").read_text()
    diff = deck_diff(recorded, built, recorded_name=f"{scenario} (recorded)",
                     given_name=f"{scenario} (library today)")
    assert not diff, (
        "the library now writes a different deck for this scenario; re-run "
        f"scripts/record_aermod_fixtures.py --only {scenario}\n{diff}")


@pytest.mark.parametrize("scenario", ["albany_success", "albany_e480",
                                      "missing_met", "aertest"])
def test_recording_manifest_names_version_and_outputs(scenario):
    manifest = json.loads((RECORDINGS / scenario / "manifest.json").read_text())
    assert manifest["aermod_version"] == "26135"
    assert manifest["exit_code"] == 0
    assert "aermod.out" in manifest["outputs"]
    outputs = RECORDINGS / scenario / "outputs"
    for name in manifest["outputs"]:
        stored = f"{name}.gz" if name in manifest["gzipped_outputs"] else name
        assert (outputs / stored).exists(), stored
    # The repository's pre-commit gate refuses files over 500 KB.
    assert all(p.stat().st_size <= 500 * 1024
               for p in (RECORDINGS / scenario).rglob("*") if p.is_file())
    expected = {"albany_success": (0, True), "albany_e480": (1, False),
                "missing_met": (1, False), "aertest": (0, True)}[scenario]
    assert (manifest["fatal_errors"], manifest["finishes_successfully"]) == expected


# -- known gaps -------------------------------------------------------------------

class _Server:
    def log_size(self):
        return 0

    def tracebacks(self, start=0, end=None):
        return []


class _Journey:
    """Just enough of harness.Journey for KnownGap."""

    def __init__(self):
        self.server = _Server()
        self.browser_errors = []
        self.gap_hit = None
        self._in_gap = False
        self.timeouts = []
        self.shots = []

    def _use_timeouts(self, step_ms, expect_ms):
        self.timeouts.append(step_ms)

    def step(self, name):
        self.shots.append(name)


def test_known_gap_that_fails_marks_the_journey_xfailed():
    journey = _Journey()
    with (pytest.raises(pytest.xfail.Exception, match=r"D9: demo gap \[AssertionError"),
          KnownGap(journey, "D9", "demo gap")):
        raise AssertionError("still broken")
    assert journey.gap_hit.gap_id == "D9"
    assert journey.shots == ["gap_D9"]
    assert journey.timeouts[0] < journey.timeouts[-1]   # short inside, restored after


def test_known_gap_accepts_a_playwright_timeout():
    with (pytest.raises(pytest.xfail.Exception, match="TimeoutError"),
          KnownGap(_Journey(), "WP-G9", "no such control")):
        raise PlaywrightTimeoutError("Locator.click: Timeout 1500ms exceeded.")


def test_known_gap_that_passes_fails_the_journey():
    with (pytest.raises(pytest.fail.Exception, match="known gap D9: demo gap appears fixed"),
          KnownGap(_Journey(), "D9", "demo gap")):
        pass


def test_known_gap_lets_other_errors_through():
    journey = _Journey()
    with pytest.raises(ZeroDivisionError), KnownGap(journey, "D9", "demo gap"):
        1 / 0  # noqa: B018
    assert journey.gap_hit is None


def test_known_gaps_do_not_nest():
    journey = _Journey()
    with (pytest.raises(RuntimeError, match="nested"),
          KnownGap(journey, "D8", "outer"), KnownGap(journey, "D9", "inner")):
        pass
