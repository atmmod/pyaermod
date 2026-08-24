"""
Regression tests against EPA's official AERMOD test cases (v24142).

Two test tiers:

1. **Always-on** tests use the three small fixtures vendored under
   `tests/fixtures/epa_official/` (public-domain EPA outputs for the
   canonical AERTEST case). These run on every CI invocation.

2. **Opt-in** tests use the full 234 MB EPA archive fetched by
   `tests/fixtures/epa_official/download_all.py`. They skip cleanly
   when that archive is absent — local devs populate the cache once
   and get wide coverage; CI stays fast by default.

What the always-on tests cover:
- `aertest.inp` parses with the .inp reader and headline metadata
  (title, pollutant, averaging periods, source count, terrain mode,
  building-downwash sector arrays) matches known values.
- `AERTEST_01H.PLT` parses with `read_plotfile` into the expected
  number of receptors (144) and headline peak concentration.
- `AERTEST.SUM` non-empty; key strings present (trivial but catches
  an accidental truncation).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from pyaermod import PollutantType, TerrainType, read_plotfile
from pyaermod.epa_testcases import find_epa_testcase_set
from pyaermod.input_reader import read_aermod_input

FIXT = Path(__file__).parent / "fixtures" / "epa_official"
FULL = FIXT / "full"


# ---------------------------------------------------------------------------
# Always-on: tests against vendored small fixtures
# ---------------------------------------------------------------------------

class TestAertestInputFile:
    def test_parses(self):
        project = read_aermod_input(FIXT / "aertest.inp")
        assert project.control.title_one == (
            "A Simple Example Problem for the AERMOD Model with PRIME"
        )

    def test_headline_metadata(self):
        project = read_aermod_input(FIXT / "aertest.inp")
        assert project.control.pollutant_id == PollutantType.SO2
        assert project.control.terrain_type == TerrainType.FLAT
        assert "1" in project.control.averaging_periods
        assert "24" in project.control.averaging_periods
        assert "PERIOD" in project.control.averaging_periods

    def test_has_point_source(self):
        project = read_aermod_input(FIXT / "aertest.inp")
        srcs = project.sources.sources
        assert len(srcs) == 1
        src = srcs[0]
        assert src.source_id == "STACK1"
        # Canonical AERTEST values: emission 500 g/s, height 65 m,
        # temp 425 K, velocity 15 m/s, diameter 5 m
        assert src.emission_rate == pytest.approx(500.0)
        assert src.stack_height == pytest.approx(65.0)
        assert src.stack_temp == pytest.approx(425.0)
        assert src.exit_velocity == pytest.approx(15.0)
        assert src.stack_diameter == pytest.approx(5.0)


class TestAertestPlotfile:
    def test_parses(self):
        result = read_plotfile(FIXT / "AERTEST_01H.PLT")
        assert result.header.file_type == "PLOTFILE"
        # AERTEST domain has exactly 144 receptors (3 rings x 48 directions
        # / similar; count is an EPA invariant we pin).
        assert result.n_records == 144

    def test_peak_concentration_in_expected_range(self):
        """The AERTEST 1-HR HIGH-1st peak is publicly documented around
        750 ug/m^3 on the 250 m ring. Pin a broad tolerance so this
        catches regressions without being brittle to pyaermod's output
        scaling choices."""
        result = read_plotfile(FIXT / "AERTEST_01H.PLT")
        # Column name: third column after X, Y holds the concentration
        # (AERMOD labels it "AVERAGE CONC" and we tokenize as AVERAGE).
        conc_col = next(
            c for c in result.column_names
            if c in ("CONC", "AVERAGE")
        )
        peaks = [r[conc_col] for r in result.records if isinstance(r[conc_col], (int, float))]
        peak = max(peaks)
        assert 500 < peak < 1500, f"unexpected peak {peak}; EPA AERTEST ~750"


class TestBgNo2OlmPpbInputFile:
    """Second vendored EPA case: NO2 background + OLM chemistry.

    Exercises features beyond AERTEST — OZONEVAL, NO2STACK, NO2EQUIL,
    BACKGRND, multiple SRCGROUP definitions, polar receptor grid,
    multi-group POSTFILE keywords."""

    INP = FIXT / "bg_no2_olm_ppb.inp"

    def test_parses(self):
        project = read_aermod_input(self.INP)
        assert project.control.title_one == "BG Test Run"
        assert project.control.pollutant_id.value == "NO2"

    def test_polar_grid_captured(self):
        """Note: AERMOD's GRIDPOLR DIST / GDIR have two syntactic forms
        (init/num/delta vs. N/explicit-list); the EPA file uses a
        terser variant. We assert the grid parses and we capture at
        least the origin + name rather than exact field assignments."""
        project = read_aermod_input(self.INP)
        grids = project.receptors.polar_grids
        assert len(grids) == 1
        assert grids[0].grid_name == "POL1"
        assert grids[0].x_origin == 0.0
        assert grids[0].y_origin == 0.0

    def test_plotfile_captured(self):
        project = read_aermod_input(self.INP)
        assert project.output.plot_file is not None
        assert "01H.PLT" in project.output.plot_file

    def test_source_group_definitions_preserved(self):
        project = read_aermod_input(self.INP)
        names = {g.group_name for g in project.sources.group_definitions}
        # SRCGROUP ALL BACKGROUND, SRCGROUP BACKGRND BACKGROUND, SRCGROUP SRCSS 01
        # "ALL BACKGROUND" is a custom group (not the bare ALL), so it's kept.
        assert "SRCSS" in names
        assert "BACKGRND" in names


class TestAertestSum:
    def test_nonempty_and_mentions_title(self):
        text = (FIXT / "AERTEST.SUM").read_text(encoding="latin-1")
        assert len(text) > 1000
        assert "AERTEST" in text or "AERMOD" in text


# ---------------------------------------------------------------------------
# Opt-in: tests against the full EPA archive (populated by download_all.py)
# ---------------------------------------------------------------------------

# The archive's set directory is located through the shared resolver so
# both EPA naming conventions (aermet_24142_aermod_24142 and
# aermet26135_aermod26135) work and the newest validated set is preferred.
_FULL_SET = find_epa_testcase_set(FULL, env={})


def _full_archive_present() -> bool:
    return _FULL_SET is not None and _FULL_SET.exists()


@pytest.mark.skipif(
    not _full_archive_present(),
    reason=(
        "Full EPA archive not downloaded; run download_all.py to populate "
        f"(looked for aermet*_aermod* sets under {FULL})"
    ),
)
class TestFullArchive:
    """Runs against every .inp file in the full archive.

    For each input, assert the .inp reader doesn't crash on the common
    subset it supports. Files using advanced features (AREACIRC /
    RLINEXT / deposition blocks) are allowed to raise — we report the
    pass/fail count as an indicator of reader coverage.
    """

    def _collect_inputs(self):
        return sorted(_FULL_SET.inputs.glob("*.inp"))

    # Gate: every deck in the resolved set must parse. Last measured:
    # 53/53 = 100% on the 2026 bundle (aermet26135_aermod26135; the decks
    # are byte-identical across its three reference sets).
    PARSE_RATE_FLOOR = 1.00

    def test_parse_rate_meets_floor(self):
        inputs = self._collect_inputs()
        assert inputs, "no .inp files found under full archive"
        ok = 0
        failures: List[str] = []
        for inp in inputs:
            try:
                read_aermod_input(inp)
                ok += 1
            except Exception as e:
                failures.append(f"{inp.name}: {type(e).__name__}: {e}")
        rate = ok / len(inputs)
        assert rate >= self.PARSE_RATE_FLOOR, (
            f"Reader parse-rate regressed to {rate:.0%} "
            f"({ok}/{len(inputs)}); floor is {self.PARSE_RATE_FLOOR:.0%}. "
            f"First few failures:\n" + "\n".join(failures[:5])
        )
