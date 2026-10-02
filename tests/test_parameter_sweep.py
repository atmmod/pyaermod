"""Tests for BatchRunner.parameter_sweep (formerly a stub)."""

from __future__ import annotations

import hashlib
import platform
import re
from pathlib import Path

import pytest

from pyaermod import (
    AERMODProject,
    BatchRunner,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.runner import AERMODRunner, SweepResults, _set_sweep_parameter, _sweep_labels


@pytest.fixture
def base_project():
    return AERMODProject(
        control=ControlPathway(
            title_one="Sweep Test",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"],
        ),
        sources=SourcePathway(sources=[
            PointSource(
                source_id="S1", x_coord=0.0, y_coord=0.0,
                stack_height=30.0, stack_temp=400.0,
                exit_velocity=10.0, stack_diameter=2.0,
                emission_rate=1.0,
            ),
        ]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


@pytest.fixture
def fake_aermod_exe(tmp_path):
    if platform.system() == "Windows":
        exe = tmp_path / "aermod.bat"
        exe.write_text("@echo off\nexit /b 0\n")
    else:
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
    return exe


# ---------------------------------------------------------------------------
# _set_sweep_parameter
# ---------------------------------------------------------------------------

class TestSetSweepParameter:
    def test_plain_attr_mutates_first_source(self, base_project):
        _set_sweep_parameter(base_project, "emission_rate", 2.5)
        assert base_project.sources.sources[0].emission_rate == 2.5

    def test_source_index_picks_different_source(self, base_project):
        base_project.sources.sources.append(PointSource(
            source_id="S2", x_coord=100, y_coord=0,
            stack_height=30.0, stack_temp=400.0,
            exit_velocity=10.0, stack_diameter=2.0, emission_rate=1.0,
        ))
        _set_sweep_parameter(base_project, "emission_rate", 9.9, source_index=1)
        assert base_project.sources.sources[0].emission_rate == 1.0  # unchanged
        assert base_project.sources.sources[1].emission_rate == 9.9

    def test_dotted_path_mutates_project_root(self, base_project):
        _set_sweep_parameter(base_project, "control.title_one", "Swept")
        assert base_project.control.title_one == "Swept"

    def test_bad_index_raises(self, base_project):
        with pytest.raises(IndexError, match="source_index"):
            _set_sweep_parameter(base_project, "emission_rate", 1.0, source_index=99)

    def test_no_sources_raises(self, base_project):
        base_project.sources.sources = []
        with pytest.raises(ValueError, match="no sources"):
            _set_sweep_parameter(base_project, "emission_rate", 1.0)


# ---------------------------------------------------------------------------
# BatchRunner.parameter_sweep
# ---------------------------------------------------------------------------

class TestParameterSweep:
    def test_writes_one_inp_per_value(self, base_project, fake_aermod_exe, tmp_path):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        # run_batch will spawn subprocesses for each file; use 1 worker
        # so we don't fight the fake-exe over temp dirs.
        results = batch.parameter_sweep(
            base_project,
            parameter_name="emission_rate",
            parameter_values=[0.5, 1.0, 2.0],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # One .inp file per value
        inps = sorted((tmp_path / "sweep").glob("*.inp"))
        assert len(inps) == 3
        # Result map keyed by parameter values
        assert set(results.keys()) == {0.5, 1.0, 2.0}

    def test_each_inp_has_correct_emission_rate(
        self, base_project, fake_aermod_exe, tmp_path,
    ):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        batch.parameter_sweep(
            base_project,
            parameter_name="emission_rate",
            parameter_values=[0.5, 2.5],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # Parse each generated .inp and check the SRCPARAM value
        half = (tmp_path / "sweep" / "run_emission_rate_0.5.inp").read_text()
        two_five = (tmp_path / "sweep" / "run_emission_rate_2.5.inp").read_text()
        # Emission rate appears as the first numeric on SRCPARAM line
        assert "0.500000" in half
        assert "2.500000" in two_five

    def test_dotted_path_sweep(self, base_project, fake_aermod_exe, tmp_path):
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              working_dir=tmp_path)
        batch = BatchRunner(runner)
        batch.parameter_sweep(
            base_project,
            parameter_name="control.title_one",
            parameter_values=["Case A", "Case B"],
            output_dir=tmp_path / "sweep",
            n_workers=1,
        )
        # Filename sanitizer replaces the space
        files = sorted((tmp_path / "sweep").glob("*.inp"))
        assert len(files) == 2
        names = [f.name for f in files]
        assert any("Case_A" in n for n in names)
        assert any("Case_B" in n for n in names)


# ---------------------------------------------------------------------------
# Values that are not plain numbers: size distributions
# ---------------------------------------------------------------------------

def _psds():
    from pyaermod.input_generator import ParticleDepositionParams

    return [ParticleDepositionParams([2.5, 10.0], [0.5, 0.5], [2.6, 2.6]),
            ParticleDepositionParams([5.0, 20.0], [0.3, 0.7], [2.6, 2.6])]


class TestSizeDistributionSweep:
    """A sweep of ``particle_deposition`` over two size
    distributions crashed with ``TypeError: unhashable type:
    'ParticleDepositionParams'`` after every run had finished, and named
    each deck after the value's repr (124 characters, with brackets and
    commas)."""

    def _sweep(self, base_project, fake_aermod_exe, tmp_path, values):
        runner = AERMODRunner(executable_path=fake_aermod_exe, log_level="WARNING")
        return BatchRunner(runner).parameter_sweep(
            base_project, "particle_deposition", values, tmp_path / "sweep", n_workers=1,
        )

    def test_does_not_crash_and_looks_up_by_value(self, base_project, fake_aermod_exe, tmp_path):
        psds = _psds()
        results = self._sweep(base_project, fake_aermod_exe, tmp_path, psds)
        assert len(results) == 2
        assert list(results) == psds
        for psd, (value, result) in zip(psds, results.items()):
            assert value is psd
            assert results[psd] is result
            # An equal but separate object finds the same result
            from pyaermod.input_generator import ParticleDepositionParams
            copy = ParticleDepositionParams(list(psd.diameters), list(psd.mass_fractions),
                                            list(psd.densities))
            assert results[copy] is result
            assert copy in results
        decks = [Path(r.input_file) for r in results.values()]
        assert "PARTDIAM" in decks[0].read_text() and "2.5" in decks[0].read_text()
        assert "20" in decks[1].read_text()

    def test_deck_names_are_short_and_safe(self, base_project, fake_aermod_exe, tmp_path):
        from pyaermod.ensemble import canonical_json

        psds = _psds()
        results = self._sweep(base_project, fake_aermod_exe, tmp_path, psds)
        names = [Path(r.input_file).name for r in results.values()]
        for i, (psd, name) in enumerate(zip(psds, names)):
            digest = hashlib.sha256(canonical_json(psd).encode()).hexdigest()[:12]
            assert name == f"run_particle_deposition_{i:03d}_{digest}.inp"
            assert re.fullmatch(r"[A-Za-z0-9._+-]+", name)

    def test_unknown_value_is_missing(self, base_project, fake_aermod_exe, tmp_path):
        results = self._sweep(base_project, fake_aermod_exe, tmp_path, _psds())
        with pytest.raises(KeyError):
            results["no such value"]
        assert "no such value" not in results


class TestSweepLabels:
    def test_plain_values_keep_their_text(self):
        assert _sweep_labels([0.5, 2, "Case A", True, "a/b"]) == [
            "0.5", "2", "Case_A", "True", "a_b"]

    def test_values_whose_text_collides_are_hashed(self):
        labels = _sweep_labels(["a b", "a_b", "c"])
        assert labels[0].startswith("000_") and labels[1].startswith("001_")
        assert labels[0] != labels[1] and labels[2] == "c"

    def test_case_only_differences_are_hashed(self):
        """Two decks differing in case would be one file on macOS and Windows."""
        labels = _sweep_labels(["Case", "case"])
        assert labels[0].startswith("000_") and labels[1].startswith("001_")

    def test_long_or_empty_text_is_hashed(self):
        labels = _sweep_labels(["x" * 49, ""])
        assert labels[0].startswith("000_") and labels[1].startswith("001_")

    def test_values_json_cannot_hold_are_hashed_by_repr(self):
        label = _sweep_labels([object()])[0]
        assert re.fullmatch(r"000_[0-9a-f]{12}", label)

    def test_numpy_arrays_compare_unequal_instead_of_raising(self):
        import numpy as np

        results = SweepResults([(np.array([1.0, 2.0]), "a"), (np.array([3.0]), "b")])
        assert len(results) == 2
        with pytest.raises(KeyError):
            results[np.array([1.0, 2.0])]
        assert list(results.values()) == ["a", "b"]
        assert "SweepResults" in repr(results)

    def test_items_and_values_are_mapping_views_in_sweep_order(self):
        from collections.abc import ItemsView, KeysView, ValuesView

        results = SweepResults([(2.5, "a"), (0.5, "b")])
        assert isinstance(results.keys(), KeysView) and list(results.keys()) == [2.5, 0.5]
        assert isinstance(results.items(), ItemsView)
        assert list(results.items()) == [(2.5, "a"), (0.5, "b")]
        assert (0.5, "b") in results.items() and (0.5, "a") not in results.items()
        assert isinstance(results.values(), ValuesView) and "b" in results.values()
        assert len(results.items()) == len(results.values()) == 2

    def test_not_a_dict_but_dict_gives_one_back(self):
        results = SweepResults([(2.5, "a"), (0.5, "b")])
        assert not isinstance(results, dict)
        with pytest.raises(TypeError):
            results[2.5] = "c"
        assert dict(results) == {2.5: "a", 0.5: "b"}
        assert results == {2.5: "a", 0.5: "b"}


class TestSweepOutputs:
    def test_equal_values_are_refused(self, base_project, fake_aermod_exe, tmp_path):
        runner = AERMODRunner(executable_path=fake_aermod_exe, log_level="WARNING")
        with pytest.raises(ValueError, match="are equal"):
            BatchRunner(runner).parameter_sweep(
                base_project, "emission_rate", [1, 1.0], tmp_path / "sweep", n_workers=1)
        assert not list((tmp_path / "sweep").glob("*.inp"))

    def test_output_files_whose_names_differ_only_in_directory_are_refused(
            self, base_project, fake_aermod_exe, tmp_path):
        """The sweep writes every output beside the decks, so two outputs
        with one file name in different directories would be one file."""
        base_project.output.plot_file = "annual/result.plt"
        base_project.output.postfile = "hourly/RESULT.plt"
        runner = AERMODRunner(executable_path=fake_aermod_exe, log_level="WARNING")
        with pytest.raises(ValueError, match="would both be written"):
            BatchRunner(runner).parameter_sweep(
                base_project, "emission_rate", [1.0], tmp_path / "sweep", n_workers=1)
        assert not list((tmp_path / "sweep").glob("*.inp"))

    def test_output_files_are_named_per_run(self, base_project, fake_aermod_exe, tmp_path):
        """Two decks naming the same PLOTFILE would overwrite each other's results."""
        base_project.output.plot_file = "../plots/pit.plt"
        base_project.output.postfile = "/elsewhere/pit.pst"
        runner = AERMODRunner(executable_path=fake_aermod_exe, log_level="WARNING")
        BatchRunner(runner).parameter_sweep(
            base_project, "emission_rate", [0.5, 2.5], tmp_path / "sweep", n_workers=1)
        for label in ("0.5", "2.5"):
            deck = (tmp_path / "sweep" / f"run_emission_rate_{label}.inp").read_text()
            assert f"run_emission_rate_{label}_pit.plt" in deck
            assert f"run_emission_rate_{label}_pit.pst" in deck
            assert "../plots" not in deck and "/elsewhere" not in deck
        # the base project is left alone
        assert base_project.output.plot_file == "../plots/pit.plt"
