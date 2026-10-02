"""The source writers' decks, run through a real AERMOD binary.

Skips unless ``aermod`` is on PATH (as tests/test_real_aermod.py does).
Each case is an acceptance check of a source-writer fix:

* two OPENPIT sources in one group through their ``source_groups``: the
  writer used to put ``SRCGROUP`` among the source cards, and v26135
  stopped setup with ``SO E140`` (invalid order of keyword), and one
  naming group ``ALL`` wrote ``SRCGROUP ALL srcid``, ``SO E203``;
* an AREA source with ``initial_sigma_z``: runs clean, and the value
  reaches AERMOD (the field is Szinit, so the result changes);
* a HOUREMIS file whose every rate equals the SRCPARAM rate reproduces
  the constant-rate run to the plot file's print precision, for OPENPIT
  and AREA sources and for VOLUME, LINE, RLINE and RLINEXT, and AERMOD's
  source table lists each as HOURLY (so the file was read); the AP-42
  wind profile's file runs clean and changes the result, and the
  profile counts the missing hours AERMOD reports.

Groups spelled in mixed case are checked against the group table AERMOD
prints.

The met data are EPA's AERMET2 files in tests/fixtures/epa_official/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod import AERMODRunner
from pyaermod.hourly_emissions import ap42_wind_profile
from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourcePathway,
    VolumeSource,
)

FIXT = Path(__file__).parent / "fixtures" / "epa_official"

pytestmark = pytest.mark.skipif(shutil.which("aermod") is None,
                                reason="AERMOD binary not found on PATH")


def _run(work: Path, name: str, sources: SourcePathway, **control):
    for met in ("AERMET2.SFC", "AERMET2.PFL"):
        if not (work / met).exists():
            shutil.copy(FIXT / met, work / met)
    project = AERMODProject(
        control=ControlPathway(title_one=name, pollutant_id="PM10",
                               averaging_periods=["1", "PERIOD"], **control),
        sources=sources,
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
            grid_name="G1", x_init=-1500, x_num=16, x_delta=200,
            y_init=-1500, y_num=16, y_delta=200)]),
        meteorology=MeteorologyPathway(
            surface_file="AERMET2.SFC", profile_file="AERMET2.PFL",
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988, profile_base_elevation=0.0),
        output=OutputPathway(plot_file=f"{name}.plt", plot_file_averaging="PERIOD"),
    )
    project.write(work / f"{name}.inp")
    result = AERMODRunner(log_level="ERROR").run(str(work / f"{name}.inp"),
                                                 working_dir=str(work), timeout=300)
    return result, work / f"{name}.plt"


def _plot_rows(path: Path):
    return [ln.split()[:3] for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("*")]


def _codes(result):
    return {m.code for m in result.messages}


def _emission_vary(result, source_id: str) -> set:
    """The "EMISSION RATE SCALAR VARY BY" entries of ``source_id``'s rows
    in AERMOD's source data tables: ``HOURLY`` for a source AERMOD reads
    from a HOUREMIS file (inpsum.f PRTSRC)."""
    out = Path(result.output_file).read_text()
    rows = [ln.split() for ln in out.splitlines() if ln.split()[:1] == [source_id]]
    return {tok for toks in rows for tok in toks if tok == "HOURLY"}


def _pit(**kw):
    return OpenPitSource("PIT", -300.0, -200.0, emission_rate=1e-5, x_dimension=600.0,
                         y_dimension=400.0, pit_volume=2.4e7, **kw)


def _area(**kw):
    return AreaSource("A1", -500.0, -500.0, emission_rate=2e-6,
                      initial_lateral_dimension=1000.0, initial_vertical_dimension=1000.0, **kw)


def test_two_sources_grouped_by_source_groups_run(tmp_path):
    pit2 = OpenPitSource("PIT2", 500.0, 500.0, emission_rate=1e-5, x_dimension=200.0,
                         y_dimension=200.0, pit_volume=2e6, source_groups=["PITS"])
    result, _ = _run(tmp_path, "grp", SourcePathway(sources=[_pit(source_groups=["PITS"]), pit2]))
    assert result.success, result.error_message
    assert "E140" not in _codes(result)
    out = Path(result.output_file).read_text()
    assert any(ln.split()[:3] == ["PITS", "PIT", ","] and "PIT2" in ln for ln in out.splitlines())


def _group_table(out: str):
    """The group table AERMOD prints: group ID -> member IDs."""
    groups = {}
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines) if "*** SOURCE IDs DEFINING SOURCE GROUPS ***" in ln)
    for ln in lines[start + 1:]:
        if "***" in ln and groups:
            break
        toks = ln.replace(",", " ").split()
        if len(toks) >= 2 and toks[0] != "SRCGROUP" and not toks[0].startswith("-"):
            groups[toks[0]] = toks[1:]
    return groups


def test_group_names_spelled_differently_are_one_group(tmp_path):
    """``Pit`` on one source and ``PIT`` on another, with ``ROAD`` between:
    written apart, AERMOD files the second card under ROAD (SOGRP takes it
    as a continuation of the group defined last) and says nothing."""
    a1 = AreaSource("A1", 0.0, 0.0, emission_rate=1e-5, initial_lateral_dimension=100.0,
                    initial_vertical_dimension=100.0, source_groups=["Pit", "ROAD"])
    a2 = AreaSource("A2", 300.0, 300.0, emission_rate=1e-5, initial_lateral_dimension=100.0,
                    initial_vertical_dimension=100.0, source_groups=["PIT"])
    result, _ = _run(tmp_path, "case", SourcePathway(sources=[a1, a2]))
    assert result.success, result.error_message
    groups = _group_table(Path(result.output_file).read_text())
    assert groups["PIT"] == ["A1", "A2"]
    assert groups["ROAD"] == ["A1"]


def test_a_source_in_group_all_runs(tmp_path):
    """``source_groups=["ALL", ...]`` used to write ``SRCGROUP ALL PIT``,
    SO E203 even with one source."""
    result, _ = _run(tmp_path, "all", SourcePathway(sources=[_pit(source_groups=["ALL", "PITS"])]))
    assert result.success, result.error_message
    assert not {c for c in _codes(result) if c.startswith("E")}


def test_area_szinit_runs_and_takes_effect(tmp_path):
    sz0, plt0 = _run(tmp_path, "sz0", SourcePathway(sources=[_area()]))
    sz, plt = _run(tmp_path, "sz23", SourcePathway(sources=[_area(initial_sigma_z=23.26)]))
    assert sz0.success and sz.success, (sz0.error_message, sz.error_message)
    assert not {c for c in _codes(sz) if c.startswith("E")}
    peak0 = max(float(r[2]) for r in _plot_rows(plt0))
    peak = max(float(r[2]) for r in _plot_rows(plt))
    assert peak < 0.5 * peak0  # a 23 m initial spread lowers the peak near the area


def test_houremis_at_the_srcparam_rate_reproduces_the_constant_run(tmp_path):
    const, plt_const = _run(tmp_path, "const",
                            SourcePathway(sources=[_pit(), _area(initial_sigma_z=23.26)]))
    w = ap42_wind_profile(FIXT / "AERMET2.SFC")
    so = SourcePathway(sources=[_pit(), _area(initial_sigma_z=23.26)])
    n = len(w.hours)
    so.add_hourly_emissions(tmp_path / "ones.emi", w.hours, {"A1": [2e-6] * n, "PIT": [1e-5] * n},
                            filename="ones.emi")
    hourly, plt_hourly = _run(tmp_path, "ones", so)
    assert const.success and hourly.success, (const.error_message, hourly.error_message)
    # AERMOD read the file for both sources (a deck with no card, or one
    # AERMOD ignored, would also reproduce the constant run) ...
    for source_id in ("A1", "PIT"):
        assert _emission_vary(hourly, source_id) == {"HOURLY"}
        assert _emission_vary(const, source_id) == set()
    # ... and its rates are the SRCPARAM rates.
    assert _plot_rows(plt_hourly) == _plot_rows(plt_const)


def test_houremis_for_volume_and_line_type_sources(tmp_path):
    """HRQREAD reads the same rate-only record for VOLUME, LINE, RLINE and
    RLINEXT sources (RLINEXT needs the ALPHA option, so not DFAULT)."""
    def sources():
        return [VolumeSource("V1", 0.0, 0.0, emission_rate=1.0, release_height=5.0,
                             initial_lateral_dimension=5.0, initial_vertical_dimension=3.0),
                LineSource("L1", -200.0, 0.0, 200.0, 50.0, emission_rate=0.01),
                RLineSource("R1", -300.0, -300.0, 300.0, -250.0, emission_rate=0.001),
                RLineExtSource("X1", -300.0, 300.0, 1.0, 300.0, 350.0, 1.0, emission_rate=0.001)]
    opts = {"alpha": True, "regulatory_default": False}
    const, plt_const = _run(tmp_path, "lconst", SourcePathway(sources=sources()), **opts)
    so = SourcePathway(sources=sources())
    n = len(ap42_wind_profile(FIXT / "AERMET2.SFC").hours)
    rates = {s.source_id: [s.emission_rate] * n for s in so.sources}
    so.add_hourly_emissions(tmp_path / "l.emi", ap42_wind_profile(FIXT / "AERMET2.SFC").hours,
                            rates, filename="l.emi")
    hourly, plt_hourly = _run(tmp_path, "lones", so, **opts)
    assert const.success and hourly.success, (const.error_message, hourly.error_message)
    for source_id in rates:
        assert _emission_vary(hourly, source_id) == {"HOURLY"}
        assert _emission_vary(const, source_id) == set()
    assert len(_plot_rows(plt_hourly)) == 256
    assert _plot_rows(plt_hourly) == _plot_rows(plt_const)


def _missing_hours(result) -> int:
    """AERMOD's own count: "A Total of N Missing Hours Identified"."""
    for ln in Path(result.output_file).read_text().splitlines():
        toks = ln.split()
        if toks[:3] == ["A", "Total", "of"] and toks[4:6] == ["Missing", "Hours"]:
            return int(toks[3])
    raise AssertionError("no missing-hours count in the AERMOD output")


def test_wind_profile_counts_the_missing_hours_aermod_reports(tmp_path):
    """AERMOD skips an hour with any missing field (metext.f CHKMSG), not
    only a missing wind; the profile's count must match AERMOD's."""
    lines = (FIXT / "AERMET2.SFC").read_text().splitlines()
    edits = {2: (16, "999.0"),     # wind direction
             5: (18, "999.0"),     # temperature
             9: (10, "-999."),     # mechanical mixing height
             13: (15, "999.0"),    # wind speed
             20: (15, "0.00")}     # a calm, counted apart
    for i, (field_no, value) in edits.items():
        toks = lines[i].split()
        toks[field_no] = value
        lines[i] = " ".join(toks)
    (tmp_path / "AERMET2.SFC").write_text("\n".join(lines) + "\n")
    w = ap42_wind_profile(tmp_path / "AERMET2.SFC")
    assert w.counts["missing"] == 4 and w.counts["calm"] == 1
    so = SourcePathway(sources=[_area()])
    so.add_hourly_emissions(tmp_path / "m.emi", w.hours, {"A1": w.rates(2e-6)}, filename="m.emi")
    result, _ = _run(tmp_path, "m", so)
    assert result.success, result.error_message
    assert _missing_hours(result) == w.counts["missing"]


def test_houremis_wind_profile_runs(tmp_path):
    w = ap42_wind_profile(FIXT / "AERMET2.SFC")
    so = SourcePathway(sources=[_pit(), _area()])
    so.add_hourly_emissions(tmp_path / "w.emi", w.hours,
                            {"PIT": w.rates(1e-5), "A1": w.rates(2e-6)}, filename="w.emi")
    result, plt = _run(tmp_path, "w", so)
    const, plt_const = _run(tmp_path, "wconst", SourcePathway(sources=[_pit(), _area()]))
    assert result.success and const.success, (result.error_message, const.error_message)
    assert not {c for c in _codes(result) if c.startswith("E")}
    for source_id in ("A1", "PIT"):
        assert _emission_vary(result, source_id) == {"HOURLY"}
    rows, rows_const = _plot_rows(plt), _plot_rows(plt_const)
    assert len(rows) == len(rows_const) == 256
    # The receptors are the same; the hourly factor changes the result.
    assert [r[:2] for r in rows] == [r[:2] for r in rows_const]
    assert rows != rows_const
