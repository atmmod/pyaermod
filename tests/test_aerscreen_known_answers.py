"""Known-answer tests for the AERSCREEN restart-file format.

EPA ships 22 AERSCREEN runs in ``aerscreen_test_cases.zip``: every
source type, with and without downwash, terrain, NO2 chemistry and the
u* adjustment. The ``.inp`` of each is the restart file AERSCREEN wrote
at the end of the run -- the ``**`` header ``readinp`` reads back, on
top of the AERMOD deck of the final stage. Those files, with trailing
whitespace stripped, are vendored under ``tests/fixtures/epa_aerscreen``
(public domain, U.S. Government work) along with their ``.OUT`` files
and the small auxiliary inputs they name.

Each deck is parsed with :meth:`AERSCREENConfig.from_aerscreen_input`
and written back with :meth:`AERSCREENConfig.to_aerscreen_input`; the
header must come back **byte for byte**, every block of every deck.
That pins the column layout of ``makeinput``'s FORMATs, the Fortran
E/F/I editing, the carried-through values (stack flow rate, the
dominant sector's surface characteristics, the AERMAP elevation) and
the CO pathway keywords. A one-character slip in any FORMAT fails here
without a binary.

The ``.OUT`` files pin :func:`parse_aerscreen_output` the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyaermod.aerscreen import (
    AERSCREENConfig,
    AERSCREENSourceType,
    parse_aerscreen_output,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "epa_aerscreen"
DECKS = sorted(FIXTURES.rglob("*.inp"))
OUTPUTS = sorted(p for p in FIXTURES.rglob("*") if p.suffix.lower() == ".out"
                 and p.name.lower().startswith("aerscreen"))

# The two lines of the header that record the last AERMOD run rather
# than the configuration; readinp skips them and so does the writer.
_RUN_NOTES = re.compile(r"^\*\* Temporal sector|^\*\*\s+(PROBE|FLOWSECTOR|REFINE) STAGE")


def _ids(paths):
    return [str(p.relative_to(FIXTURES)) for p in paths]


def reference_header(text: str) -> list[str]:
    """EPA's header up to CO FINISHED, minus the run notes."""
    lines = text.split("\n")
    lines = lines[: lines.index("CO FINISHED") + 1]
    return _collapse_blanks(ln for ln in lines if not _RUN_NOTES.match(ln))


def _collapse_blanks(lines) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if ln == "" and out and out[-1] == "":
            continue
        out.append(ln)
    return out


def test_fixture_set_is_complete():
    """Every EPA case is here; a missing file would silently shrink the pin."""
    assert len(DECKS) == 22, _ids(DECKS)
    assert len(OUTPUTS) == 22, _ids(OUTPUTS)
    types = {AERSCREENConfig.from_aerscreen_input(
        d.read_text(encoding="latin-1")).source_type for d in DECKS}
    assert types == {
        AERSCREENSourceType.POINT, AERSCREENSourceType.POINTCAP,
        AERSCREENSourceType.POINTHOR, AERSCREENSourceType.FLARE,
        AERSCREENSourceType.VOLUME, AERSCREENSourceType.AREA,
        AERSCREENSourceType.AREACIRC,
    }


@pytest.mark.parametrize("deck", DECKS, ids=_ids(DECKS))
def test_header_round_trips_byte_for_byte(deck):
    text = deck.read_text(encoding="latin-1")
    cfg = AERSCREENConfig.from_aerscreen_input(text)
    expected = reference_header(text)
    actual = _collapse_blanks(cfg.to_aerscreen_input().rstrip("\n").split("\n"))
    assert actual == expected, (
        "restart header differs from EPA's; first difference:\n"
        + next(
            (
                f"  line {i}:\n    EPA:      {e!r}\n    pyaermod: {a!r}"
                for i, (e, a) in enumerate(zip(expected, actual), start=1)
                if e != a
            ),
            f"  lengths differ: EPA {len(expected)}, pyaermod {len(actual)}",
        )
    )


@pytest.mark.parametrize("deck", DECKS, ids=_ids(DECKS))
def test_parsed_deck_answers_every_prompt(deck):
    """The parsed configuration must also produce a full answer sequence.

    A deck that parses but cannot be answered would run only through
    the restart path; both paths are what the runner offers.
    """
    cfg = AERSCREENConfig.from_aerscreen_input(deck.read_text(encoding="latin-1"))
    answers = cfg.to_stdin_answers()
    assert answers[0] == cfg.title
    assert answers[1] == "M"
    assert answers[2] == cfg.source_type.prompt_letter
    assert answers[-1] == ""                       # <Enter> starts the run
    assert all(len(a) <= 250 for a in answers)


class TestPinnedValues:
    """Spot checks of what the parser understood, against EPA's decks."""

    def load(self, rel: str) -> AERSCREENConfig:
        return AERSCREENConfig.from_aerscreen_input(
            (FIXTURES / rel).read_text(encoding="latin-1")
        )

    def test_point_flat_no_downwash(self):
        cfg = self.load("point/AERSCREEN_FLAT_NODW.inp")
        assert cfg.source_type is AERSCREENSourceType.POINT
        assert cfg.title == "POINT, FLAT, NO DOWNWASH"
        assert (cfg.emission_rate, cfg.stack_height, cfg.stack_temp,
                cfg.exit_velocity, cfg.stack_diameter) == (1.0, 61.0, 415.0, 11.0, 5.0)
        assert not cfg.downwash and cfg.bpip_file == "BUILDING.INP"
        assert cfg.surface_file == "season_3.out" and cfg.surface_code == 9
        assert cfg.discrete_receptor_file == "discrete_rec.txt"
        assert cfg.probe_distance == 10000.0 and cfg.source_elevation == 25.0
        assert cfg.ambient_distance == 50.0 and not cfg.urban
        assert cfg.output_file == "AERSCREEN_FLAT_NODW.OUT"
        assert not cfg.terrain and cfg.datum == "NAD83" and cfg.utm_zone == 17

    def test_point_flat_downwash_with_fumigation(self):
        cfg = self.load("point/AERSCREEN_FLAT_DW.inp")
        assert cfg.downwash and cfg.bpip_file == "BUILDING.INP"
        assert cfg.fumigation and cfg.shoreline_fumigation
        assert cfg.shoreline_distance == 500.0 and cfg.shoreline_direction == 30.0
        assert cfg.debug

    def test_capped_stack_with_single_building(self):
        cfg = self.load("point_cap/AERSCREEN_FLAT_DW.inp")
        assert cfg.source_type is AERSCREENSourceType.POINTCAP
        assert cfg.downwash and cfg.bpip_file is None
        assert (cfg.building_height, cfg.building_length, cfg.building_width,
                cfg.building_angle, cfg.stack_direction, cfg.stack_distance
                ) == (4.3, 13.7, 9.1, 0.0, 90.0, 9.1)
        assert cfg.surface_code == 0 and cfg.albedo == 0.16

    def test_horizontal_stack_urban_aermet_tables(self):
        cfg = self.load("point_horiz/AERSCREEN_FLAT_NODW.inp")
        assert cfg.source_type is AERSCREENSourceType.POINTHOR
        assert cfg.urban and cfg.population == 100000.0
        assert cfg.land_use == 7 and cfg.climate == 1 and cfg.surface_code == 7
        assert cfg.min_wind_speed == 0.4

    def test_flare(self):
        cfg = self.load("flare/AERSCREEN_FLAT_NODW.inp")
        assert cfg.source_type is AERSCREENSourceType.FLARE
        assert cfg.flare_heat_release == 1.0e7 and cfg.flare_heat_loss == 0.45
        assert cfg.stack_height == 100.0
        assert cfg.effective_release_height == pytest.approx(
            100.0 + 4.56e-3 * 1.0e7 ** 0.478)

    def test_volume(self):
        cfg = self.load("volume/AERSCREEN_FLAT.inp")
        assert cfg.source_type is AERSCREENSourceType.VOLUME
        assert (cfg.stack_height, cfg.lateral_dimension, cfg.vertical_dimension
                ) == (1.0, 20.0, 0.93)
        assert cfg.land_use == 2 and cfg.climate == 1
        assert not cfg.fumigation_allowed

    def test_area_with_adjusted_ustar(self):
        plain = self.load("area/aerscreen_area.inp")
        ustar = self.load("area/aerscreen_area_ustar.inp")
        assert plain.source_type is AERSCREENSourceType.AREA
        assert (plain.area_length, plain.area_width, plain.vertical_dimension
                ) == (152.4, 76.2, 0.09)
        assert not plain.use_adju and ustar.use_adju
        assert plain.probe_distance == 7000.0 and plain.debug

    def test_circular_area_with_discrete_receptors(self):
        cfg = self.load("circle/AERSCREEN_FLAT.inp")
        assert cfg.source_type is AERSCREENSourceType.AREACIRC
        assert cfg.radius == 50.0 and cfg.discrete_receptor_file == "discrete.txt"
        assert cfg.anemometer_height == 7.9

    def test_no2_chemistry(self):
        olm = self.load("point_no2/aerscreen_olm.inp")
        assert olm.no2_method == "OLM"
        assert olm.no2_stack_ratio == 0.1
        assert olm.ozone_concentration == 40.0 and olm.ozone_units == "PPB"
        assert "   MODELOPT CONC SCREEN  FLAT  OLM" in olm.to_aerscreen_input()

    def test_epa_pvmrm_deck_is_the_olm_deck(self):
        """EPA's ``aerscreen_pvmrm.inp`` is a byte-for-byte copy of the OLM
        deck (its ``.out`` was made in 2021 with AERMOD 21112 and never
        re-run), so it cannot reproduce its own reference and the
        real-binary tests leave it out. Pin that, so the exclusion is
        revisited if EPA ships a real one."""
        olm = (FIXTURES / "point_no2/aerscreen_olm.inp").read_bytes()
        pvmrm = (FIXTURES / "point_no2/aerscreen_pvmrm.inp").read_bytes()
        assert olm == pvmrm
        assert self.load("point_no2/aerscreen_pvmrm.inp").no2_method == "OLM"
        assert "PVMRM" in (FIXTURES / "point_no2/aerscreen_pvmrm.out").read_text(
            encoding="latin-1")

    def test_terrain_with_aermap_elevation(self):
        cfg = self.load("flare/aerscreen_terr_nodw.inp")
        assert cfg.terrain and cfg.aermap_elevation
        assert cfg.source_elevation == 2.98          # what AERMAP found
        assert (cfg.utm_easting, cfg.utm_northing, cfg.utm_zone, cfg.datum
                ) == (370354.0, 4119742.0, 18, "NAD83")
        assert cfg.to_stdin_answers().count("UTM") == 1

    def test_terrain_with_user_elevation(self):
        cfg = self.load("point/AERSCREEN_TERR_NODW.inp")
        assert cfg.terrain and not cfg.aermap_elevation
        assert cfg.source_elevation == 25.0


class TestOutputParser:
    @pytest.mark.parametrize("out", OUTPUTS, ids=_ids(OUTPUTS))
    def test_every_reference_output_parses(self, out):
        summary = parse_aerscreen_output(out)
        assert summary.version.startswith("AERSCREEN 21112 / AERMOD ")
        assert summary.maximum.conc_1hr > 0
        assert summary.maximum.distance > 0
        assert len(summary.distances) == len(summary.concentrations) > 10
        assert summary.distances == sorted(summary.distances)
        # The overall maximum comes from the refined receptors, which
        # can sit between the automated distances; it is never below.
        assert max(summary.concentrations) <= summary.maximum.conc_1hr * 1.001

    def test_point_flat_no_downwash_values(self):
        s = parse_aerscreen_output(FIXTURES / "point/AERSCREEN_FLAT_NODW.OUT")
        assert s.title == "POINT, FLAT, NO DOWNWASH"
        m = s.maximum
        assert (m.conc_1hr, m.conc_3hr, m.conc_8hr, m.conc_24hr, m.conc_annual
                ) == (1.913, 1.913, 1.722, 1.148, 0.1913)
        assert m.distance == 1610.0
        b = s.ambient_boundary
        assert b is not None
        assert (b.conc_1hr, b.conc_annual, b.distance) == (0.5736, 0.05736, 50.0)
        assert s.distances[0] == 50.0 and s.concentrations[0] == 0.5736
        assert s.distances[-1] == 10000.0 and s.concentrations[-1] == 0.7059

    def test_text_is_accepted_too(self):
        text = (FIXTURES / "volume/AERSCREEN_FLAT.OUT").read_text(encoding="latin-1")
        assert parse_aerscreen_output(text).title == "VOLUME, FLAT"

    def test_missing_summary_is_an_error(self):
        with pytest.raises(ValueError, match="MAXIMUM IMPACT SUMMARY"):
            parse_aerscreen_output("nothing here\n")
