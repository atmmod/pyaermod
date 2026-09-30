"""The files a deck reads: ``input_files`` and ``anchor_input_files``.

A deck names the files AERMOD reads relative to AERMOD's working
directory, which is usually the deck's own folder. A caller that runs the
project somewhere else (the GUI runs in a working directory of its own)
anchors those names to the deck's folder first. Files AERMOD writes are
never touched: they belong in the run's working directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.input_reader import (
    InputFile,
    anchor_input_files,
    input_files,
    read_aermod_input,
)

EPA = Path(__file__).parent / "fixtures" / "epa_official"

_DECK = """\
CO STARTING
   TITLEONE  input files
   MODELOPT  CONC FLAT DFAULT OLM
   AVERTIME  1
   POLLUTID  NO2
   OZONEFIL  ozone.dat  PPB  (4I2,F8.3)
   ERRORFIL  errors.out
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0  0
   SRCPARAM  S1  1  10  400  5  1
   HOUREMIS  hourly.emi  S1
   BACKGRND  HOURLY  bg.dat
   INCLUDED  "more_sources.dat"
   SRCGROUP  ALL
SO FINISHED
RE STARTING
   INCLUDED  ../shared/receptors.dat
RE FINISHED
ME STARTING
   SURFFILE  met/a.sfc
   PROFFILE  /nowhere/a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
   RECTABLE  ALLAVE  FIRST
   POSTFILE  1  ALL  PLOT  out.pst
OU FINISHED
"""


@pytest.fixture
def deck(tmp_path) -> Path:
    folder = tmp_path / "run"
    (folder / "met").mkdir(parents=True)
    path = folder / "deck.inp"
    path.write_text(_DECK)
    return path


def _keywords(refs):
    return [(r.keyword, r.path) for r in refs]


class TestInputFiles:
    def test_every_file_aermod_reads_and_none_it_writes(self, deck):
        project = read_aermod_input(deck)
        assert _keywords(input_files(project)) == [
            ("ME SURFFILE", "met/a.sfc"),
            ("ME PROFFILE", "/nowhere/a.pfl"),
            ("CO OZONEFIL", "ozone.dat"),
            ("SO HOUREMIS at line 12", "hourly.emi"),
            ("SO BACKGRND at line 13", "bg.dat"),
            ("SO INCLUDED at line 14", "more_sources.dat"),
            ("RE INCLUDED at line 18", "../shared/receptors.dat"),
        ]
        assert all(isinstance(r, InputFile) for r in input_files(project))

    def test_restart_and_sector_files(self, tmp_path):
        text = (EPA / "testpm10_1987.inp").read_text()
        (tmp_path / "d.inp").write_text(text)
        project = read_aermod_input(tmp_path / "d.inp")
        assert ("CO MULTYEAR", "../Outputs/pm10_1986.sav") in _keywords(input_files(project))

    def test_background_values_are_not_files(self, deck):
        deck.write_text(_DECK.replace("BACKGRND  HOURLY  bg.dat", "BACKGRND  ANNUAL  5.0"))
        project = read_aermod_input(deck)
        assert "bg.dat" not in [r.path for r in input_files(project)]


    def test_a_modelled_houremis_card_is_an_input_file(self, deck, tmp_path):
        """#28's SourcePathway.hourly_emissions names a file AERMOD reads."""
        from pyaermod.sources import HourlyEmissionFile

        project = read_aermod_input(deck)
        project.sources.hourly_emissions.append(HourlyEmissionFile("emis/s1.dat", ["S1"]))
        assert ("SO HOUREMIS", "emis/s1.dat") in _keywords(input_files(project))
        emis = deck.parent / "emis"
        emis.mkdir()
        (emis / "s1.dat").write_text("")
        anchored = dict(_keywords(ref for ref, _full in anchor_input_files(project, deck.parent)))
        assert anchored["SO HOUREMIS"] == "emis/s1.dat"
        assert project.sources.hourly_emissions[0].filename == str(emis / "s1.dat")

    def test_the_sandbox_refuses_a_modelled_houremis_file_outside_the_folder(self, deck):
        from pyaermod.input_reader import PathTraversalError, _validate_paths_within
        from pyaermod.sources import HourlyEmissionFile

        deck.write_text(_DECK.replace("../shared/receptors.dat", "receptors.dat")
                        .replace("/nowhere/a.pfl", "a.pfl"))
        project = read_aermod_input(deck)
        project.sources.hourly_emissions.append(HourlyEmissionFile("../s1.dat", ["S1"]))
        with pytest.raises(PathTraversalError) as caught:
            _validate_paths_within(project, deck.parent)
        assert [(v.field, v.path) for v in caught.value.violations] == [
            ("sources.hourly_emissions[0]", "../s1.dat")]


class TestAnchorInputFiles:
    def test_relative_names_found_from_the_deck_folder_become_full_paths(self, deck):
        folder = deck.parent
        for name in ("met/a.sfc", "ozone.dat", "hourly.emi", "more_sources.dat"):
            (folder / name).write_text("x")
        (folder.parent / "shared").mkdir()
        (folder.parent / "shared" / "receptors.dat").write_text("x")
        project = read_aermod_input(deck)

        changed = anchor_input_files(project, folder)

        assert [(r.keyword, full) for r, full in changed] == [
            ("ME SURFFILE", folder / "met" / "a.sfc"),
            ("CO OZONEFIL", folder / "ozone.dat"),
            ("SO HOUREMIS at line 12", folder / "hourly.emi"),
            ("SO INCLUDED at line 14", folder / "more_sources.dat"),
            ("RE INCLUDED at line 18", folder.parent / "shared" / "receptors.dat"),
        ]
        assert project.meteorology.surface_file == str(folder / "met" / "a.sfc")
        assert project.control.chemistry.ozone_data.ozone_file == str(folder / "ozone.dat")
        # Not found: left as written. Absolute: left as written.
        assert project.meteorology.profile_file == "/nowhere/a.pfl"
        # Outputs stay where the run puts them.
        assert project.output.postfile == "out.pst"

        deck_text = project.to_aermod_input(validate=False)
        assert f"HOUREMIS  {folder / 'hourly.emi'}  S1" in deck_text
        assert f"INCLUDED  {folder / 'more_sources.dat'}" in deck_text
        assert "BACKGRND  HOURLY  bg.dat" in deck_text        # not found
        assert "ERRORFIL  errors.out" in deck_text             # an output
        assert f"INCLUDED  {folder.parent / 'shared' / 'receptors.dat'}" in deck_text

    def test_a_full_path_with_blanks_on_a_kept_line_is_quoted(self, tmp_path):
        folder = tmp_path / "my run"
        folder.mkdir()
        (folder / "deck.inp").write_text(_DECK)
        (folder / "hourly.emi").write_text("x")
        project = read_aermod_input(folder / "deck.inp")
        anchor_input_files(project, folder)
        # Quoted, as AERMOD reads a name with blanks (setup.f, DEFINE).
        assert f'HOUREMIS  "{folder / "hourly.emi"}"  S1' in project.to_aermod_input(
            validate=False)
        assert ("SO HOUREMIS at line 12", str(folder / "hourly.emi")) in _keywords(
            input_files(project))

    def test_a_second_call_changes_nothing(self, deck):
        (deck.parent / "ozone.dat").write_text("x")
        project = read_aermod_input(deck)
        assert len(anchor_input_files(project, deck.parent)) == 1
        assert anchor_input_files(project, deck.parent) == []

    def test_a_folder_is_not_a_file(self, deck):
        (deck.parent / "ozone.dat").mkdir()
        project = read_aermod_input(deck)
        assert anchor_input_files(project, deck.parent) == []
        assert project.control.chemistry.ozone_data.ozone_file == "ozone.dat"
