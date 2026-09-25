"""End-to-end AERSCREEN tests against EPA's own reference runs.

pyaermod's earlier AERSCREEN module wrote a deck AERSCREEN never read.
These tests are the check that was missing: every EPA test case is
driven through a locally built AERSCREEN by
:class:`~pyaermod.aerscreen_runner.AERSCREENRunner`, both by typing the
prompt answers and by handing it the restart file, and the ``.OUT`` it
produces is compared with the one EPA ships, line by line, timestamps
aside.

Requires, all built by the scripts in ``scripts/``:

* ``aerscreen`` and ``makemet`` on PATH (``scripts/build_aerscreen.sh``)
* ``aermod`` (``scripts/build_aermod.sh``) and, for the downwash cases,
  ``bpipprm`` (``scripts/build_bpip.sh``); the terrain cases also need
  ``aermap``
* EPA's test cases unpacked under ``test_cases/aerscreen_test_cases``
  (``scripts/build_aerscreen.sh --with-testcase``; the archive is
  46 MB, mostly terrain rasters, so it is not vendored)

Everything skips, saying why, when any of that is absent. The archive
also carries EPA's ``.inp`` decks, but the vendored copies in
``tests/fixtures/epa_aerscreen`` are the ones used, so that the format
pin in ``test_aerscreen_known_answers.py`` and these runs read the same
bytes.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

from pyaermod.aerscreen import AERSCREENConfig, parse_aerscreen_output
from pyaermod.aerscreen_runner import AERSCREENRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "epa_aerscreen"
TESTCASE_DIR = Path(
    os.environ.get(
        "PYAERMOD_AERSCREEN_TESTCASE",
        REPO_ROOT / "test_cases" / "aerscreen_test_cases",
    )
)

BINARIES = {name: shutil.which(name)
            for name in ("aerscreen", "makemet", "aermod", "bpipprm", "aermap")}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        BINARIES["aerscreen"] is None or BINARIES["makemet"] is None,
        reason="aerscreen/makemet not on PATH; build with scripts/build_aerscreen.sh",
    ),
    pytest.mark.skipif(
        BINARIES["aermod"] is None,
        reason="aermod not on PATH; build with scripts/build_aermod.sh",
    ),
    pytest.mark.skipif(
        not (TESTCASE_DIR / "point").is_dir(),
        reason=(
            f"EPA AERSCREEN test cases not under {TESTCASE_DIR} "
            "(scripts/build_aerscreen.sh --with-testcase)"
        ),
    ),
]

# (case directory, deck stem) for every EPA run. The reference output is
# <stem>.OUT or <stem>.out beside the deck.
FLAT_CASES = [
    ("point", "AERSCREEN_FLAT_NODW"),
    ("point", "AERSCREEN_FLAT_DW"),
    ("point_cap", "AERSCREEN_FLAT_NODW"),
    ("point_cap", "AERSCREEN_FLAT_DW"),
    ("point_horiz", "AERSCREEN_FLAT_NODW"),
    ("point_horiz", "AERSCREEN_FLAT_DW"),
    ("point_no2", "aerscreen_olm"),
    # point_no2/aerscreen_pvmrm.inp is a copy of the OLM deck and its
    # .out dates from AERMOD 21112; see test_aerscreen_known_answers.
    ("flare", "AERSCREEN_FLAT_NODW"),
    ("volume", "AERSCREEN_FLAT"),
    ("area", "aerscreen_area"),
    ("area", "aerscreen_area_ustar"),
    ("circle", "AERSCREEN_FLAT"),
]
TERRAIN_CASES = [
    ("point", "AERSCREEN_TERR_NODW"),
    ("point", "aerscreen_terr_dw"),
    ("point_cap", "AERSCREEN_TERR_NODW"),
    ("point_cap", "aerscreen_terr_dw"),
    ("point_horiz", "AERSCREEN_TERR_NODW"),
    ("point_horiz", "aerscreen_terr_dw"),
    ("flare", "aerscreen_terr_nodw"),
    ("volume", "aerscreen_terr"),
    ("circle", "aerscreen_terr"),
]

_TIMESTAMP = re.compile(
    r"\d{2}/\d{2}/\d{2}|\d{2}:\d{2}:\d{2}"
)
#: A path token: the .OUT echoes the DEM files as they were listed in
#: DEMlist.txt, which in EPA's runs is a Windows relative path
#: (``NED_32948525\NED_32948525.tif``); the runner stages them flat.
_PATH_TOKEN = re.compile(r"\S*[\\/](\S+)")


def _case_id(case):
    return f"{case[0]}/{case[1]}"


def load_case(case_dir: str, stem: str) -> tuple[AERSCREENConfig, Path, Path]:
    """The configuration of an EPA run, pointed at the files it names."""
    deck = FIXTURES / case_dir / f"{stem}.inp"
    cfg = AERSCREENConfig.from_aerscreen_input(deck.read_text(encoding="latin-1"))
    src = TESTCASE_DIR / case_dir
    if cfg.surface_file:
        cfg.surface_file = str(_find(src, cfg.surface_file))
    if cfg.discrete_receptor_file:
        cfg.discrete_receptor_file = str(_find(src, cfg.discrete_receptor_file))
    if cfg.bpip_file:
        cfg.bpip_file = str(_find(src, cfg.bpip_file))
    if cfg.terrain:
        cfg.dem_files, cfg.dem_type = _dems_from_demlist(src)
        cfg.nad_grid_dir = str(src)
    reference = next(p for p in src.iterdir()
                     if p.name.lower() == f"{stem}.out".lower())
    return cfg, src, reference


def _find(directory: Path, name: str) -> Path:
    """EPA's decks name files in a case that the archive spells differently."""
    for p in directory.iterdir():
        if p.name.lower() == name.lower():
            return p
    raise FileNotFoundError(f"{name} not in {directory}")


def _dems_from_demlist(directory: Path) -> tuple[list[str], str]:
    """The DEM files EPA's Windows-flavoured demlist.txt lists."""
    lines = (directory / "demlist.txt").read_text(encoding="latin-1").splitlines()
    dem_type = "NED" if lines[0].strip().upper().startswith("N") else "DEM"
    dems = []
    for ln in lines[1:]:
        ln = ln.strip()
        if not ln or ln.upper().startswith("NADGRIDS") or ln.startswith("-"):
            continue
        # Spelled for Windows: ``BC\aerscrn28.DEM`` names the archive's
        # ``bc/aerscrn28.DEM``, so each component is matched by case.
        path = directory
        for part in ln.split()[0].replace("\\", "/").split("/"):
            path = _find(path, part)
        dems.append(str(path))
    return dems, dem_type


def normalise(text: str, *, restart_title: bool = False) -> list[str]:
    """An AERSCREEN .OUT with its run date and time blanked and file
    paths reduced to their basenames.

    ``restart_title`` applies what AERSCREEN's restart reader does to
    the title -- it keeps it only up to the first comma, upper-cased --
    so a restart run can be compared with EPA's prompt-driven one.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for ln in lines:
        ln = _TIMESTAMP.sub("##", ln.rstrip())
        ln = _PATH_TOKEN.sub(r"\1", ln)
        if restart_title and ln.startswith(" TITLE:"):
            ln = " TITLE: " + ln[7:].split(",")[0].strip().upper()
        out.append(ln)
    while out and not out[-1]:
        out.pop()
    return out


#: Relative tolerance for a printed number that differs from EPA's. The
#: outputs are printed to four significant figures; a value that lands on
#: a rounding boundary can print one unit in the last place apart between
#: EPA's Intel/Windows build and gfortran/Linux (0.05% of the value).
NUMERIC_RTOL = 5e-4

_TOKEN = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:E[-+]?\d+)?")


def _tokens_agree(expected: str, actual: str) -> bool:
    """Two lines whose only differences are last-digit ones."""
    e_parts = _TOKEN.split(expected)
    a_parts = _TOKEN.split(actual)
    e_nums = _TOKEN.findall(expected)
    a_nums = _TOKEN.findall(actual)
    if e_parts != a_parts or len(e_nums) != len(a_nums):
        return False
    for x, y in zip(e_nums, a_nums):
        if x == y:
            continue
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False
        if abs(fx - fy) > NUMERIC_RTOL * max(abs(fx), abs(fy), 1e-30):
            return False
    return True


def assert_same_output(produced: Path, reference: Path, *,
                       restart_title: bool = False) -> list[tuple[int, str, str]]:
    """The produced .OUT must be EPA's, line for line.

    Returns the lines that differ only in the last printed digit of a
    number (see :data:`NUMERIC_RTOL`); any other difference fails.
    """
    expected = normalise(reference.read_text(encoding="latin-1"),
                         restart_title=restart_title)
    actual = normalise(produced.read_text(encoding="latin-1"),
                       restart_title=restart_title)
    assert len(actual) == len(expected), (
        f"{produced.name} has {len(actual)} lines, EPA's {reference.name} "
        f"{len(expected)}"
    )
    rounding: list[tuple[int, str, str]] = []
    for i, (e, a) in enumerate(zip(expected, actual), start=1):
        if e == a:
            continue
        assert _tokens_agree(e, a), (
            f"{produced.name} differs from EPA's {reference.name}; first "
            f"difference:\n  line {i}:\n    EPA:      {e!r}\n    pyaermod: {a!r}"
        )
        rounding.append((i, e, a))
    return rounding


def run_case(case, tmp_path, mode):
    cfg, _src, reference = load_case(*case)
    if cfg.downwash and BINARIES["bpipprm"] is None:
        pytest.skip("bpipprm not on PATH; build with scripts/build_bpip.sh")
    if cfg.terrain and BINARIES["aermap"] is None:
        pytest.skip("aermap not on PATH; build with scripts/build_aermod.sh")
    work = tmp_path / mode
    result = AERSCREENRunner().run(cfg, working_dir=work, timeout=3600, mode=mode)
    log = Path(result.log_file).read_text(errors="replace") if result.log_file else ""
    assert result.success, (
        f"AERSCREEN did not finish ({result.error_message}, rc={result.return_code})\n"
        f"stdout tail:\n{(result.stdout or '')[-3000:]}\n"
        f"stderr tail:\n{(result.stderr or '')[-1500:]}\n"
        f"log tail:\n{log[-3000:]}"
    )
    assert result.output_file is not None
    return cfg, result, reference


@pytest.mark.parametrize("case", FLAT_CASES, ids=_case_id)
def test_prompt_answers_reproduce_epa_output(case, tmp_path):
    """Typing the answers reproduces EPA's .OUT for every flat case."""
    _cfg, result, reference = run_case(case, tmp_path, "prompts")
    rounding = assert_same_output(Path(result.output_file), reference)
    # Rounding differences are reported, not hidden; more than a couple
    # of lines would mean something systematic.
    assert len(rounding) <= 2, rounding


@pytest.mark.parametrize("case", FLAT_CASES, ids=_case_id)
def test_restart_file_reproduces_epa_output(case, tmp_path):
    """Handing AERSCREEN pyaermod's restart file does the same."""
    cfg, result, reference = run_case(case, tmp_path, "restart")
    assert_same_output(Path(result.output_file), reference, restart_title=True)
    # And what AERSCREEN wrote back is what pyaermod wrote it (the
    # title aside, which its reader cuts at the first comma).
    assert result.restart_file is not None
    written = AERSCREENConfig.from_aerscreen_input(
        Path(result.restart_file).read_text(encoding="latin-1"))
    assert written.title == cfg.title.split(",")[0].strip().upper()
    written.title = cfg.title
    assert written.to_aerscreen_input() == cfg.to_aerscreen_input()


@pytest.mark.parametrize("case", TERRAIN_CASES, ids=_case_id)
def test_terrain_cases_reproduce_epa_output(case, tmp_path):
    """The terrain cases run AERMAP over EPA's NED / DEM rasters."""
    _cfg, result, reference = run_case(case, tmp_path, "prompts")
    rounding = assert_same_output(Path(result.output_file), reference)
    assert len(rounding) <= 2, rounding


def test_summary_matches_reference_parse(tmp_path):
    """The runner's parsed summary is the reference's, to the digit."""
    _cfg, result, reference = run_case(("point", "AERSCREEN_FLAT_NODW"),
                                       tmp_path, "prompts")
    assert result.summary is not None
    assert result.summary == parse_aerscreen_output(reference)
    assert result.summary.maximum.conc_1hr == 1.913
    assert result.summary.maximum.distance == 1610.0


def test_validation_error_is_reported_not_hidden(tmp_path):
    """A restart file AERSCREEN rejects must come back as a failure.

    AERSCREEN exits 0 after logging the problem, so the runner reads
    its verdict from the log rather than the exit code.
    """
    cfg, _src, _ref = load_case("point", "AERSCREEN_FLAT_NODW")
    cfg.surface_file = None
    cfg.albedo, cfg.bowen_ratio, cfg.roughness_length = 0.16, 0.8, 0.1
    cfg.discrete_receptor_file = None
    cfg.bpip_file = None
    work = tmp_path / "bad"
    result = AERSCREENRunner().run(cfg, working_dir=work, timeout=600, mode="restart")
    assert result.success
    # Now break the file after staging: a surface file that does not exist.
    text = (work / "aerscreen.inp").read_text()
    broken = text.replace('    0    0   0.1600', '    9    0   0.1600').replace(
        '"NA"', '"missing.out"')
    assert broken != text
    (work / "aerscreen.inp").write_text(broken)
    runner = AERSCREENRunner()
    runner.stage = lambda config, w, mode: w / "aerscreen.inp"  # type: ignore[method-assign]
    bad = runner.run(cfg, working_dir=work, timeout=600, mode="restart")
    assert not bad.success
    assert "did not finish" in (bad.error_message or "")
