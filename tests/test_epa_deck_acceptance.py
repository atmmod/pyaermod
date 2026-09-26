"""AERMOD's own setup pass accepts what pyaermod writes for EPA's decks.

The round-trip suite (``tests/test_epa_deck_roundtrip.py``) shows the
reader and writer agree with each other. This one asks the program that
matters: every deck in EPA's v26135 archive is parsed, written back by
pyaermod, and run through AERMOD with ``RUNORNOT NOT`` in a copy of the
archive's ``inputs/`` tree (so INCLUDED files, hourly emissions and
background files resolve as EPA laid them out). The written deck must
produce exactly the fatal-error set the original produces in the same
place, which is empty for 49 decks. The other four are the 1987-1990
years of the MULTYEAR PM10 chain, whose MULTYEAR line names the previous
year's save file as its init file: without a full run of the year before,
EPA's own deck reports CO E500 there, and so must ours.

Alongside, the writer forms this branch changed are checked on minimal
decks the way ``tests/test_source_deck_acceptance.py`` checks source
types: the polar and Cartesian grid layouts, MAXIFILE, URBANOPT, the
ELEV terrain token, STARTEND with hours.

Needs ``aermod`` on PATH (``scripts/build_aermod.sh``) and, for the
archive sweep, the EPA test cases under ``test_cases/``. Marked slow:
the sweep runs AERMOD 106 times.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pyaermod.epa_testcases import find_epa_testcase_set
from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MaxiFile,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
    UrbanArea,
)
from pyaermod.input_reader import parse_aermod_input

AERMOD_EXE = shutil.which("aermod")
ROOT = Path(__file__).resolve().parent.parent
MET_DIR = ROOT / "test_cases" / "aermet26135_aermod26135" / "meteorology"
SURFACE = MET_DIR / "aermet2.sfc"
PROFILE = MET_DIR / "aermet2.pfl"
_SET = find_epa_testcase_set(ROOT / "test_cases")
_INPUTS = _SET.inputs if _SET and _SET.inputs.is_dir() else None
_DECKS = sorted(_INPUTS.glob("*.inp")) if _INPUTS else []

_FATAL_RE = re.compile(r"^\s*(CO|SO|RE|ME|OU|EV|MX)\s+E(\d{3})\s+(.*)$", re.MULTILINE)


def run_setup_check(deck: str, work: Path) -> list[str]:
    """Run AERMOD's setup pass on a minimal deck; return its fatal lines.

    Same harness as tests/test_source_deck_acceptance.py (the tests
    directory is not a package, so it is repeated rather than imported).
    """
    for met in (SURFACE, PROFILE):
        shutil.copy(met, work / met.name)
    (work / "aermod.inp").write_text(deck)
    subprocess.run([AERMOD_EXE], cwd=str(work), capture_output=True, timeout=300)
    out_path = work / "aermod.out"
    if not out_path.is_file():
        return ["AERMOD produced no aermod.out"]
    text = out_path.read_text(encoding="latin-1", errors="replace")
    block = text.split("FATAL ERROR MESSAGES")
    if len(block) < 2:
        return []
    return [f"{path} E{code} {msg.strip()}" for path, code, msg in _FATAL_RE.findall(block[1])]

pytestmark = pytest.mark.skipif(
    AERMOD_EXE is None,
    reason="aermod not on PATH; build with scripts/build_aermod.sh",
)


def _setup_errors(deck_text: str, work_inputs: Path) -> set[tuple[str, str]]:
    """Fatal (pathway, code) pairs AERMOD's setup pass reports for a deck."""
    deck_text = re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", deck_text, flags=re.IGNORECASE)
    (work_inputs / "aermod.inp").write_text(deck_text, encoding="latin-1")
    (work_inputs / "aermod.out").unlink(missing_ok=True)
    subprocess.run([AERMOD_EXE], cwd=str(work_inputs), capture_output=True, timeout=600)
    out = work_inputs / "aermod.out"
    if not out.is_file():
        return {("??", "no aermod.out")}
    text = out.read_text(encoding="latin-1", errors="replace")
    parts = text.split("FATAL ERROR MESSAGES")
    if len(parts) < 2:
        return set()
    return {(path, f"E{code}") for path, code, _ in _FATAL_RE.findall(parts[1])}


@pytest.mark.slow
@pytest.mark.skipif(not _DECKS, reason="EPA test-case archive not unpacked under test_cases/")
@pytest.mark.parametrize("deck", _DECKS, ids=[p.name for p in _DECKS])
def test_written_epa_deck_passes_setup_like_the_original(deck, tmp_path):
    work = tmp_path / "inputs"
    work.mkdir()
    for extra in _INPUTS.iterdir():
        if extra.suffix.lower() != ".inp" and extra.is_file():
            shutil.copy(extra, work / extra.name)
    (tmp_path / "meteorology").symlink_to(_SET.path / "meteorology")
    for name in ("Outputs", "postfiles", "plotfiles"):
        (tmp_path / name).mkdir()

    text = deck.read_text(encoding="latin-1")
    written = parse_aermod_input(text).to_aermod_input(validate=False)
    original_errors = _setup_errors(text, work)
    written_errors = _setup_errors(written, work)
    assert written_errors == original_errors, (
        f"{deck.name}: AERMOD reports {sorted(written_errors)} for the written "
        f"deck but {sorted(original_errors)} for EPA's\n\n{written}"
    )
    if original_errors:
        # Only the chained MULTYEAR years may fail, and only on the
        # missing save file of the year before.
        assert original_errors == {("CO", "E500")}, deck.name
        assert "MULTYEAR" in text.upper(), deck.name


# ---------------------------------------------------------------------
# Writer forms this branch changed, on minimal decks
# ---------------------------------------------------------------------

_met_ok = pytest.mark.skipif(
    not (SURFACE.is_file() and PROFILE.is_file()),
    reason=f"EPA meteorology not under {MET_DIR}",
)


def _project(control=None, receptors=None, output=None, meteorology=None) -> AERMODProject:
    return AERMODProject(
        control=control or ControlPathway(title_one="acceptance"),
        sources=SourcePathway(sources=[PointSource(
            "SRC1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
            stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0,
        )]),
        receptors=receptors or ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(500.0, 500.0)]),
        meteorology=meteorology or MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988,
        ),
        output=output or OutputPathway(),
    )


CASES = [
    ("polar-generated", _project(receptors=ReceptorPathway(polar_grids=[
        PolarGrid(grid_name="POL1", dist_init=100.0, dist_num=5, dist_delta=100.0,
                  dir_init=0.0, dir_num=36, dir_delta=10.0)]))),
    ("polar-explicit", _project(receptors=ReceptorPathway(polar_grids=[
        PolarGrid(grid_name="POL2", origin_source_id="SRC1", distances=[100.0, 250.0, 1000.0],
                  directions=[0.0, 90.0, 180.0, 270.0])]))),
    ("cartesian-points", _project(receptors=ReceptorPathway(cartesian_grids=[
        CartesianGrid(grid_name="CAR1", x_points=[-1000.0, -500.0, 500.0, 1000.0],
                      y_points=[-1000.0, 0.0, 1000.0])]))),
    ("cartesian-elev-rows", _project(
        control=ControlPathway(title_one="acceptance", terrain_type=TerrainType.ELEVATED),
        receptors=ReceptorPathway(cartesian_grids=[
            CartesianGrid(grid_name="CAR2", x_init=0.0, x_num=3, x_delta=100.0,
                          y_init=0.0, y_num=2, y_delta=100.0,
                          grid_elevations=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                          grid_hills=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])]))),
    ("maxifile", _project(
        control=ControlPathway(title_one="acceptance", averaging_periods=["1", "24"]),
        output=OutputPathway(maxi_files=[MaxiFile("1", "ALL", 30.0, "maxi01.dat"),
                                         MaxiFile("24", "ALL", 12.5, "maxi24.dat", 45)]))),
    ("urban-one-area", _project(control=ControlPathway(
        title_one="acceptance", urban_option="Albany", urban_population=250000.0))),
    ("urban-several-areas", _project(control=ControlPathway(
        title_one="acceptance",
        urban_areas=[UrbanArea(250000.0, "URB1", "Albany", 1.0), UrbanArea(500000.0, "URB2")]))),
    ("elevated-terrain-token", _project(
        control=ControlPathway(title_one="acceptance", terrain_type=TerrainType.ELEVATED),
        receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 500.0, 10.0, 12.0)]))),
    ("flatsrcs-terrain-token", _project(
        control=ControlPathway(title_one="acceptance", terrain_type=TerrainType.FLATSRCS),
        receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 500.0, 10.0, 12.0)]))),
    ("startend-with-hours", _project(
        control=ControlPathway(title_one="acceptance", averaging_periods=["1", "24"]),
        meteorology=MeteorologyPathway(
        surface_file=SURFACE.name, profile_file=PROFILE.name,
        surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
        start_year=1988, start_month=1, start_day=1, start_hour=1,
        end_year=1988, end_month=1, end_day=31, end_hour=24))),
]


@_met_ok
@pytest.mark.parametrize("label,project", CASES, ids=[c[0] for c in CASES])
def test_writer_forms_pass_aermod_setup(label, project, tmp_path):
    deck = project.to_aermod_input(validate=False)
    if label == "urban-several-areas":
        # AERMOD needs every area to own a source (soset.f SRCQA, E318)
        # and no source in two areas (E302): a second stack for URB2.
        deck = deck.replace(
            "   SRCGROUP  ALL",
            "   LOCATION  SRC2  POINT  100.0  100.0  0.0\n"
            "   SRCPARAM  SRC2  10.0  50.0  400.0  15.0  2.0\n"
            "   URBANSRC  URB1  SRC1\n   URBANSRC  URB2  SRC2\n   SRCGROUP  ALL")
    elif label == "urban-one-area":
        deck = deck.replace("   SRCGROUP  ALL", "   URBANSRC  SRC1\n   SRCGROUP  ALL")
    errors = run_setup_check(deck, tmp_path)
    assert not errors, (
        f"AERMOD rejected the {label} deck:\n  " + "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    )


@_met_ok
def test_preserved_lines_are_accepted_where_the_writer_puts_them(tmp_path):
    """The re-emission rules (ELEVUNIT first, SO lines before SRCGROUP,
    the rest before FINISHED) hold up in AERMOD on a deck that uses
    keywords from every pathway the reader has no model for."""
    project = _project()
    base = project.to_aermod_input(validate=False)
    deck = (base
            .replace("CO FINISHED", "   ERRORFIL  errors.out\n   DEBUGOPT  MODEL\nCO FINISHED")
            .replace("SO STARTING", "SO STARTING\n   ELEVUNIT  METERS")
            .replace("   SRCGROUP  ALL", "   EMISFACT  SRC1  SEASON  1.0  1.0  1.0  1.0\n   SRCGROUP  ALL")
            .replace("RE FINISHED", "   DISCPOLR  SRC1  100.  45.\nRE FINISHED")
            .replace("ME FINISHED", "   SITEDATA  99999  1988  ALBANY\nME FINISHED")
            .replace("OU FINISHED", "   SEASONHR  ALL  seasonhr.dat\nOU FINISHED"))
    written = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert "ELEVUNIT" in written and "SEASONHR" in written and "DISCPOLR" in written
    errors = run_setup_check(written, tmp_path)
    assert not errors, "\n  ".join(errors) + f"\n\ndeck:\n{written}"
