"""Every AERSURFACE configuration must produce a deck AERSURFACE accepts.

``tests/test_real_aersurface.py`` proves one configuration end to end --
EPA's RDU case, reproduced byte-identically. That is a strong result for
a single point in the parameter space and says nothing about the rest of
it, which is where the deck builder had four more defects: SEASONAL
frequency emitted a keyword AERSURFACE rejects, ZOEFF omitted the
anemometer height it requires, ARID with the default SNOW is an invalid
combination, and sectors with a gap were accepted here and refused
there.

The oracle is AERSURFACE's own setup pass (``RUNORNOT NOT``), which
parses and cross-checks the whole control file. It needs the raster
files to *exist* but never reads them, so ten-byte placeholders do --
no 30 MB test-case archive, and the whole sweep runs in well under a
second. That makes it cheap enough to cover the parameter space on
every run rather than one case occasionally.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pyaermod.aersurface import AERSURFACEConfig

AERSURFACE_EXE = shutil.which("aersurface")

pytestmark = pytest.mark.skipif(
    AERSURFACE_EXE is None,
    reason="aersurface not on PATH; build with scripts/build_aersurface.sh",
)

# "CO E290     5 DATAFILE   File does not exist   missing_lc.tiff"
_MESSAGE_RE = re.compile(
    r"^(CO|OU)\s+([EW])(\d+)\s+(\d+)\s+(\S+)\s+(.*?)\s{2,}", re.MULTILINE
)


def setup_errors(config: AERSURFACEConfig, work: Path) -> list[str]:
    """Run AERSURFACE's setup pass; return its error lines."""
    for name in (config.land_cover_file, config.canopy_file,
                 config.impervious_file):
        if name:
            (work / name).write_text("placeholder")
    config.run = False  # RUNORNOT NOT: check the deck, process nothing
    (work / "aersurface.inp").write_text(config.to_aersurface_input())
    subprocess.run(
        [AERSURFACE_EXE], cwd=str(work), capture_output=True, timeout=120
    )
    out_path = work / "aersurface.out"
    if not out_path.is_file():
        return ["AERSURFACE produced no aersurface.out"]
    text = out_path.read_text(encoding="latin-1", errors="replace")
    return [
        f"{path} {kind}{code} {module}: {message.strip()}"
        for path, kind, code, _line, module, message
        in _MESSAGE_RE.findall(text)
        if kind == "E"
    ]


def base_config(**overrides) -> AERSURFACEConfig:
    settings = dict(
        title="deck acceptance", site_id="S",
        latitude=35.8923, longitude=-78.7819,
        land_cover_file="lc.tiff", nlcd_year=2021,
        canopy_file="can.tiff", impervious_file="imp.tiff",
        sfcchar_file="sfc.txt",
    )
    settings.update(overrides)
    return AERSURFACEConfig(**settings)


# Each entry is a configuration that must be *accepted*. Combinations
# AERSURFACE forbids are asserted separately, below.
ACCEPTED = [
    ("default", {}),
    ("frequency-annual", dict(frequency="ANNUAL")),
    ("frequency-seasonal", dict(frequency="SEASONAL")),
    ("frequency-monthly", dict(frequency="MONTHLY")),
    ("zo-method-zorad", dict(zo_method="ZORAD")),
    ("zo-method-zoeff", dict(zo_method="ZOEFF", anemometer_height_m=10.0)),
    ("site-primary", dict(site_type="PRIMARY")),
    ("site-secondary", dict(site_type="SECONDARY")),
    ("moisture-wet", dict(moisture="WET")),
    ("moisture-dry", dict(moisture="DRY")),
    ("no-snow", dict(snow=False)),
    ("arid-without-snow", dict(arid=True, snow=False)),
    ("airport", dict(airport=True)),
    ("no-ancillary-rasters", dict(canopy_file=None, impervious_file=None)),
    ("three-sectors", dict(sectors=[(30.0, 60.0, "NONAP"),
                                    (60.0, 225.0, "AP"),
                                    (225.0, 30.0, "NONAP")])),
    ("twelve-sectors", dict(sectors=[
        (i * 30.0, (i + 1) * 30.0 % 360.0, "NONAP") for i in range(12)
    ])),
    ("grid-outputs", dict(land_cover_grid_file="lc_grid.txt",
                          canopy_grid_file="can_grid.txt",
                          impervious_grid_file="imp_grid.txt",
                          debug_options=["GRID", "TIFF"])),
    ("custom-seasons", dict(seasons={"WINTERNS": (12, 2, 3), "WINTERWS": (1,),
                                     "SPRING": (4, 5), "SUMMER": (6, 7, 8),
                                     "AUTUMN": (9, 10, 11)})),
    ("small-radius", dict(zo_radius_km=0.5)),
    ("title-two", dict(title_two="second line")),
    ("nlcd-1992", dict(nlcd_year=1992, canopy_file=None,
                       impervious_file=None)),
    ("nlcd-2013", dict(nlcd_year=2013, canopy_file=None,
                       impervious_file=None)),
]
ACCEPTED += [
    (f"nlcd-{year}", dict(nlcd_year=year, canopy_year=year,
                          impervious_year=year))
    for year in (2001, 2006, 2011, 2016, 2019, 2021)
]


@pytest.mark.parametrize(
    "label,overrides", ACCEPTED, ids=[c[0] for c in ACCEPTED]
)
def test_configuration_passes_aersurface_setup(label, overrides, tmp_path):
    config = base_config(**overrides)
    errors = setup_errors(config, tmp_path)
    assert not errors, (
        f"AERSURFACE rejected the {label} deck:\n  " + "\n  ".join(errors)
        + f"\n\ndeck:\n{config.to_aersurface_input()}"
    )


def test_the_check_can_actually_fail(tmp_path):
    """Guard against the sweep passing because nothing is being checked."""
    config = base_config()
    config.run = False
    deck = config.to_aersurface_input().replace(
        "   ZORADIUS", "   ZORADIUS  99  bogus extra field\n**"
    )
    (tmp_path / "lc.tiff").write_text("placeholder")
    (tmp_path / "aersurface.inp").write_text(deck)
    subprocess.run(
        [AERSURFACE_EXE], cwd=str(tmp_path), capture_output=True, timeout=120
    )
    text = (tmp_path / "aersurface.out").read_text(errors="replace")
    assert "UN-successfully" in text, (
        "AERSURFACE accepted a deliberately malformed deck"
    )


# ---------------------------------------------------------------------
# Combinations AERSURFACE forbids: rejected here, before it sees them
# ---------------------------------------------------------------------

class TestForbiddenCombinations:
    """Each of these produced a deck AERSURFACE refuses.

    Catching them at construction turns a Fortran error table into a
    Python message that names the fix.
    """

    def test_zoeff_requires_an_anemometer_height(self):
        with pytest.raises(ValueError, match="anemometer_height_m"):
            base_config(zo_method="ZOEFF")

    def test_arid_conflicts_with_snow(self):
        with pytest.raises(ValueError, match=r"arid=True conflicts with snow"):
            base_config(arid=True, snow=True)

    def test_sectors_must_tile_the_compass(self):
        with pytest.raises(ValueError, match="gap or overlap"):
            base_config(sectors=[(0.0, 90.0, "AP"), (180.0, 270.0, "AP")])

    def test_seasonal_frequency_rejects_explicit_seasons(self):
        with pytest.raises(ValueError, match="SEASONAL"):
            base_config(frequency="SEASONAL",
                        seasons={"WINTERNS": (12, 1, 2), "SPRING": (3, 4, 5),
                                 "SUMMER": (6, 7, 8), "AUTUMN": (9, 10, 11)})

    @staticmethod
    def _season_keywords(deck: str) -> list[str]:
        # Match the keyword, not the substring: "FREQ_SECT  SEASONAL"
        # contains "SEASON".
        return [ln for ln in deck.splitlines() if ln.strip().startswith("SEASON ")]

    def test_seasonal_frequency_omits_the_season_keyword(self):
        # AERSURFACE: "SEASON Keyword Only Valid with ANNUAL and MONTHLY".
        assert self._season_keywords(
            base_config(frequency="SEASONAL").to_aersurface_input()
        ) == []
        assert self._season_keywords(
            base_config(frequency="MONTHLY").to_aersurface_input()
        )
