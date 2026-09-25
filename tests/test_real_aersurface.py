"""End-to-end AERSURFACE test against EPA's own reference output.

pyaermod builds AERSURFACE control files but, until this test existed,
nothing had ever fed one to AERSURFACE. It turned out the generated
deck used keywords AERSURFACE has never had (``TITLE``, ``LOCATION``,
``NLCDFILE``, ...) and crashed the real binary in its control-file
parser. A deck-builder can only be checked against the program that
consumes the deck.

So this test does the whole loop: build the deck for EPA's published RDU
test case with :class:`~pyaermod.aersurface.AERSURFACEConfig`, run it
through :class:`~pyaermod.aersurface_runner.AERSURFACERunner`, and
compare the surface-characteristics table against the one EPA ships.
Agreement is exact -- same NLCD rasters in, same numbers out.

Requires:

* ``aersurface`` on PATH (``scripts/build_aersurface.sh``)
* EPA's RDU test case unpacked under ``test_cases/aersurface_testcase``
  (``scripts/build_aersurface.sh --with-testcase``); the rasters are
  ~30 MB, so they are not vendored.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from pyaermod.aersurface import AERSURFACEConfig
from pyaermod.aersurface_runner import AERSURFACERunner

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTCASE_DIR = Path(
    os.environ.get(
        "PYAERMOD_AERSURFACE_TESTCASE",
        REPO_ROOT / "test_cases" / "aersurface_testcase",
    )
)

AERSURFACE_EXE = shutil.which("aersurface")

RASTERS = (
    "RDU_2021_NLCD_LC.tiff",
    "RDU_2021_NLCD_Can.tiff",
    "RDU_2021_NLCD_Imp.tiff",
)
REFERENCE_SFC = "rdu_2021_lc_can_imp_zorad_sfc.txt"


def _testcase_ready() -> bool:
    return TESTCASE_DIR.is_dir() and all(
        (TESTCASE_DIR / name).is_file() for name in (*RASTERS, REFERENCE_SFC)
    )


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        AERSURFACE_EXE is None,
        reason="aersurface not on PATH; build with scripts/build_aersurface.sh",
    ),
    pytest.mark.skipif(
        not _testcase_ready(),
        reason=(
            f"EPA AERSURFACE test case not under {TESTCASE_DIR} "
            "(scripts/build_aersurface.sh --with-testcase)"
        ),
    ),
]


def rdu_config(sfcchar_file: str = "out_sfc.txt") -> AERSURFACEConfig:
    """The configuration EPA's ``RDU_Example_2021.inp`` describes."""
    return AERSURFACEConfig(
        title="Sample AERSURFACE Control File",
        title_two="RDU - Met Tower, 2021 NLCD",
        site_id="RDU",
        latitude=35.8923,
        longitude=-78.7819,
        land_cover_file="RDU_2021_NLCD_LC.tiff",
        nlcd_year=2021,
        canopy_file="RDU_2021_NLCD_Can.tiff",
        impervious_file="RDU_2021_NLCD_Imp.tiff",
        zo_radius_km=1.0,
        moisture="AVERAGE",
        snow=True,
        arid=False,
        frequency="MONTHLY",
        sectors=[(30.0, 60.0, "NONAP"),
                 (60.0, 225.0, "AP"),
                 (225.0, 30.0, "NONAP")],
        seasons={
            "WINTERNS": (12, 2, 3),
            "WINTERWS": (1,),
            "SPRING": (4, 5),
            "SUMMER": (6, 7, 8),
            "AUTUMN": (9, 10, 11),
        },
        sfcchar_file=sfcchar_file,
    )


@pytest.fixture(scope="module")
def rdu_run(tmp_path_factory):
    """Run EPA's RDU case once through pyaermod's own deck."""
    work = tmp_path_factory.mktemp("aersurface_rdu")
    for name in RASTERS:
        shutil.copy(TESTCASE_DIR / name, work / name)
    result = AERSURFACERunner().run(
        rdu_config(), working_dir=str(work), timeout=1800,
    )
    return result, work


def test_run_succeeds(rdu_run):
    """The generated deck must be one AERSURFACE actually accepts.

    Before the deck format was corrected this failed with return code 2
    and a Fortran bounds error inside mod_ProcCtrlFile: the deck had no
    pathway structure at all, so the parser walked off its PATHWY array.
    """
    result, work = rdu_run
    stderr = (work / "aersurface.subproc.stderr")
    detail = stderr.read_text(errors="replace")[:2000] if stderr.is_file() else ""
    assert result.success, (
        f"AERSURFACE rejected pyaermod's deck (rc={result.return_code}).\n"
        f"deck:\n{(work / 'aersurface.inp').read_text()}\n"
        f"stderr:\n{detail}"
    )


def test_surface_characteristics_match_epa_reference(rdu_run):
    """The albedo / Bowen / roughness table must equal EPA's, exactly."""
    _result, work = rdu_run
    produced = work / "out_sfc.txt"
    assert produced.is_file(), (
        f"no surface-characteristics file produced; work dir holds "
        f"{sorted(p.name for p in work.iterdir())}"
    )

    def body(path: Path) -> list[str]:
        # Drop the two-line banner: it carries the run date and time.
        lines = path.read_text(encoding="latin-1").replace("\r\n", "\n")
        return lines.split("\n")[2:]

    expected = body(TESTCASE_DIR / REFERENCE_SFC)
    actual = body(produced)
    assert actual == expected, (
        "surface characteristics differ from EPA's reference; first "
        "difference:\n"
        + next(
            (
                f"  line {i}:\n    EPA:      {e!r}\n    pyaermod: {a!r}"
                for i, (e, a) in enumerate(zip(expected, actual), start=3)
                if e != a
            ),
            f"  lengths differ: EPA {len(expected)}, pyaermod {len(actual)}",
        )
    )


def test_reference_table_is_not_trivially_empty(rdu_run):
    """Guard the comparison above against passing on two empty files."""
    reference = (TESTCASE_DIR / REFERENCE_SFC).read_text(encoding="latin-1")
    # Twelve monthly rows per sector, three sectors.
    assert reference.count("\n") > 30, reference[:400]
    assert "1.0" in reference or "0." in reference


def test_deck_matches_epa_keyword_structure():
    """The rendered deck must use AERSURFACE's real pathway keywords.

    Cheap enough to run without the binary reachable, and it pins the
    exact regression: every keyword below appears in EPA's own
    RDU_Example_2021.inp, and none of the previous format's did.
    """
    deck = rdu_config().to_aersurface_input()
    for keyword in ("CO STARTING", "CO FINISHED", "OU STARTING",
                    "OU FINISHED", "TITLEONE", "TITLETWO", "OPTIONS",
                    "CENTERLL", "DATAFILE  NLCD2021", "DATAFILE  CNPY2021",
                    "DATAFILE  MPRV2021", "ZORADIUS", "CLIMATE",
                    "FREQ_SECT", "SECTOR  1", "SEASON  WINTERWS",
                    "RUNORNOT  RUN", "SFCCHAR"):
        assert keyword in deck, f"{keyword!r} missing from:\n{deck}"
    for invented in ("TITLE  ", "LOCATION  ", "NLCDFILE", "NLCDYEAR",
                     "SNOW_TEMPER", "SECTORS_LIST", "OUTPATH"):
        assert invented not in deck, (
            f"{invented!r} is not an AERSURFACE keyword but is in the deck"
        )
