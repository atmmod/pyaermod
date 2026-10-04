"""pyaermod.ensemble: run IDs, run directories, the manifest, resume, collection.

The runs are replays of real AERMOD v26135 runs of the design in
``tests/fixtures/ensemble/design.py`` (see the README there): the fake
``aermod`` below finds the recording whose deck matches ``aermod.inp``
and writes back AERMOD's stdout, ``aermod.out`` and PLOTFILEs. It also
logs each run it replays, so a test can tell which runs a resumed design
made again, and it can hold a run (sleep) to let a test interrupt the
design part way through.

The same design against the real binary is in
``tests/test_real_ensemble.py``.
"""

from __future__ import annotations

import enum
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pyaermod import ensemble, runner_utils
from pyaermod.aermod_outputs import read_plotfile
from pyaermod.ensemble import (
    DECK_NAME,
    DESIGN_NAME,
    SCHEMA_VERSION,
    EnsembleManifest,
    EnsembleManifestEntry,
    canonical_json,
    collect_plotfiles,
    file_sha256,
    rewrite_output_names,
    run_design,
    run_id,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.runner_utils import RunManifest, RunManifestEntry
from pyaermod.unparsed import UnparsedLine

FIXTURES = Path(__file__).parent / "fixtures" / "ensemble"
_spec = importlib.util.spec_from_file_location("ensemble_design", FIXTURES / "design.py")
design = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(design)

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the replaying fake aermod is a bash script",
)

_REPLAY = """#!/bin/bash
# Replay the recorded AERMOD run whose deck matches aermod.inp.
for case in "{recordings}"/*/; do
    if [ -f "$case/aermod.inp" ] && cmp -s aermod.inp "$case/aermod.inp"; then
        name="$(basename "$case")"
        echo "$name" >> "{bindir}/calls.log"
        if [ -f "{bindir}/hold" ] && grep -qx "$name" "{bindir}/hold"; then sleep 120; fi
        if [ -f "{bindir}/delay" ]; then
            # Count, as each run ends, the runs in progress at that moment
            touch "{bindir}/running.$name"
            sleep "$(cat "{bindir}/delay")"
            ls "{bindir}"/running.* | wc -l >> "{bindir}/overlap.log"
            rm -f "{bindir}/running.$name"
        fi
        cat "$case/stdout.txt"
        cp "$case/aermod.out" aermod.out
        cp "$case"/outputs/* .
        exit "$(cat "$case/exit_code.txt")"
    fi
done
echo "no recording for this deck" >&2
exit 99
"""


@pytest.fixture()
def replay_bin(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "aermod"
    exe.write_text(_REPLAY.format(recordings=FIXTURES, bindir=bindir))
    exe.chmod(0o755)
    return bindir


def _calls(bindir: Path) -> list:
    log = bindir / "calls.log"
    return log.read_text().split() if log.exists() else []


def _met_sha():
    return {
        "surface": file_sha256(design.MET / "AERMET2.SFC"),
        "profile": file_sha256(design.MET / "AERMET2.PFL"),
    }


def _design(replay_bin, root, rows=None, n_workers=4, **kw):
    return run_design(rows if rows is not None else design.ROWS, design.build, root,
                      n_workers=n_workers, executable=replay_bin / "aermod", **kw)


# ---------------------------------------------------------------------------
# Run IDs
# ---------------------------------------------------------------------------

class Colour(enum.Enum):
    RED = "red"


@dataclass
class Pair:
    a: float
    b: list


class TestCanonicalJson:
    def test_sorted_keys_and_no_whitespace(self):
        assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'

    def test_integer_and_float_differ(self):
        assert canonical_json(1) == "1"
        assert canonical_json(1.0) == "1.0"
        assert canonical_json(True) == "true"

    def test_float_is_the_shortest_round_trip(self):
        assert canonical_json(0.1) == "0.1"
        assert canonical_json(2.65) == "2.65"

    def test_text_is_utf8_not_escaped(self):
        assert canonical_json({"d": "µm"}) == '{"d":"µm"}'

    def test_enum_path_dataclass_set_tuple(self):
        assert canonical_json(Colour.RED) == '"red"'
        assert canonical_json(Path("a") / "b.sfc") == '"a/b.sfc"'
        assert canonical_json(Pair(1.5, [2])) == '{"_type":"Pair","a":1.5,"b":[2]}'
        assert canonical_json({3, 1, 2}) == "[1,2,3]"
        assert canonical_json((1, "x")) == '[1,"x"]'

    def test_numpy_values_are_plain_numbers(self):
        assert canonical_json(np.float64(2.5)) == "2.5"
        assert canonical_json(np.int64(3)) == "3"
        assert canonical_json(np.bool_(True)) == "true"
        assert canonical_json(np.array([1.0, 2.0])) == "[1.0,2.0]"

    def test_particle_deposition_params(self):
        from pyaermod.input_generator import ParticleDepositionParams

        text = canonical_json(ParticleDepositionParams([2.5], [1.0], [2.65]))
        assert json.loads(text)["_type"] == "ParticleDepositionParams"
        assert json.loads(text)["diameters"] == [2.5]

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_numbers_raise(self, bad):
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({"x": bad})

    def test_non_string_keys_raise(self):
        with pytest.raises(TypeError, match="string keys"):
            canonical_json({1: "a"})

    def test_other_types_raise(self):
        with pytest.raises(TypeError, match="cannot be written as JSON"):
            canonical_json(object())


class TestRunId:
    def test_is_the_sha256_of_the_documented_payload(self):
        # The scheme is pinned here character by character: changing it
        # must come with a new SCHEMA_VERSION.
        text = ('{"binary_sha256":"b","factors":{"d":2.5,"met":"COR"},'
                '"input_files_sha256":{"HOUREMIS":"h"},'
                '"met_sha256":{"profile":"p","surface":"s"},"schema_version":2}')
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert SCHEMA_VERSION == 2
        assert run_id({"met": "COR", "d": 2.5}, "b", {"surface": "s", "profile": "p"},
                      {"HOUREMIS": "h"}) == expected

    def test_no_other_input_files(self):
        text = ('{"binary_sha256":"b","factors":{},"input_files_sha256":{},'
                '"met_sha256":{},"schema_version":2}')
        assert run_id({}, "b", {}) == hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_factor_order_does_not_matter(self):
        met = {"surface": "s", "profile": "p"}
        assert run_id({"a": 1, "b": 2}, "x", met) == run_id({"b": 2, "a": 1}, "x", met)

    @pytest.mark.parametrize("change", ["factor", "binary", "met", "input", "schema"])
    def test_every_part_changes_the_id(self, change):
        args = dict(factors={"d": 2.5}, binary_sha256="b",
                    met_sha256={"surface": "s", "profile": "p"},
                    input_files_sha256={"HOUREMIS": "h"}, schema_version=2)
        base = run_id(**args)
        if change == "factor":
            args["factors"] = {"d": 10.0}
        elif change == "binary":
            args["binary_sha256"] = "c"
        elif change == "met":
            args["met_sha256"] = {"surface": "s2", "profile": "p"}
        elif change == "input":
            args["input_files_sha256"] = {"HOUREMIS": "h2"}
        else:
            args["schema_version"] = 3
        assert run_id(**args) != base

    def test_file_sha256(self, tmp_path):
        p = tmp_path / "f"
        p.write_bytes(b"abc" * 1000)
        assert file_sha256(p, chunk_size=7) == hashlib.sha256(b"abc" * 1000).hexdigest()


# ---------------------------------------------------------------------------
# Output names
# ---------------------------------------------------------------------------

class TestRewriteOutputNames:
    def _project(self):
        return design.build(design.ROWS[0])

    def test_relative_and_absolute_names_become_bare(self):
        project = self._project()
        names = rewrite_output_names(project)
        assert names == {"PLOTFILE": ["pit.plt", "pit_1h.plt"]}
        assert project.output.plot_file == "pit.plt"
        assert project.output.plot_file_groups == [("1", "ALL", "pit_1h.plt")]
        text = project.to_aermod_input()
        assert "../shared" not in text and "nonexistent-pyaermod-dir" not in text

    def test_prefix(self):
        project = self._project()
        rewrite_output_names(project, prefix="r1_")
        assert project.output.plot_file == "r1_pit.plt"

    def test_windows_paths(self):
        project = self._project()
        project.output.plot_file = r"C:\runs\out\pit.plt"
        rewrite_output_names(project)
        assert project.output.plot_file == "pit.plt"

    def test_every_output_keyword(self):
        from pyaermod.pathways import (
            EvalFile,
            MaxDailyContribution,
            MaxDailyFile,
            MaxiFile,
            MultiYear,
            RankFile,
            SaveFile,
            ScimOptions,
            SeasonHourFile,
            ToxxFile,
        )

        project = self._project()
        out = project.output
        out.summary_file = "../o/s.sum"
        out.postfile = "/x/p.pst"
        out.maxi_files = [MaxiFile("1", "ALL", 10.0, "a/m.max")]
        out.rank_files = [RankFile("1", 10, "a/r.rnk")]
        out.season_hour_files = [SeasonHourFile("ALL", "a/s.shr")]
        out.eval_files = [EvalFile("PIT", "a/e.evl")]
        out.toxx_files = [ToxxFile("1", 1.0, "a/t.tox")]
        out.max_daily_files = [MaxDailyFile("ALL", "a/md.dat")]
        out.max_daily_by_year_files = [MaxDailyFile("ALL", "a/my.dat")]
        out.max_daily_contributions = [MaxDailyContribution("ALL", 1, "a/mc.dat", lower_rank=2)]
        project.control.eventfil = "a/ev.inp"
        project.control.save_file = SaveFile("a/sv1.fil", None, "a/sv2.fil")
        project.control.multiyear = MultiYear(save_file="a/my.sav")
        project.meteorology.scim = ScimOptions(1, 25, surface_summary_file="a/ss.dat",
                                               profile_summary_file="a/ps.dat")
        names = rewrite_output_names(project)
        assert names == {
            "SUMMFILE": ["s.sum"], "PLOTFILE": ["pit.plt", "pit_1h.plt"],
            "POSTFILE": ["p.pst"], "MAXIFILE": ["m.max"], "RANKFILE": ["r.rnk"],
            "SEASONHR": ["s.shr"], "EVALFILE": ["e.evl"], "TOXXFILE": ["t.tox"],
            "MAXDAILY": ["md.dat"], "MXDYBYYR": ["my.dat"], "MAXDCONT": ["mc.dat"],
            "EVENTFIL": ["ev.inp"], "SAVEFILE": ["sv1.fil", "sv2.fil"],
            "MULTYEAR": ["my.sav"], "SCIMBYHR": ["ss.dat", "ps.dat"],
        }
        assert out.rank_files[0].filename == "r.rnk"
        assert project.meteorology.scim.profile_summary_file == "ps.dat"

    def test_lines_kept_verbatim_are_renamed(self):
        """Outputs the model cannot hold stay as UnparsedLines when a deck
        is read; their file names are rewritten too. DEBUGOPT is read into
        ControlPathway.debug_options, whose file names are rewritten in
        place."""
        deck = design.build(design.ROWS[0]).to_aermod_input(validate=False)
        deck = deck.replace("CO FINISHED", (
            "   ERRORFIL  ../logs/errors.lst\n"
            "   DEBUGOPT  MODEL  /tmp/dbg/model.dbg  METEOR\n"
            "CO FINISHED"))
        deck = deck.replace("OU FINISHED", (
            "   POSTFILE  PERIOD  ALL  PLOT  ../shared/post_a.pst\n"
            "   POSTFILE  1  ALL  PLOT  /tmp/shared/post_b.pst\n"
            "   PLOTFILE  1  ALL  8TH  /tmp/shared/pit_1h_h8h.plt\n"
            "   PLOTFILE  PERIOD  ALL  ../shared/unit.plt  41\n"
            "OU FINISHED"))
        project = parse_aermod_input(deck)
        kept = {(u.pathway, u.keyword) for u in project.unparsed_lines}
        assert {("CO", "ERRORFIL"), ("OU", "POSTFILE"), ("OU", "PLOTFILE")} <= kept
        assert ("CO", "DEBUGOPT") not in kept
        assert project.control.debug_options == ["MODEL", "/tmp/dbg/model.dbg", "METEOR"]
        names = rewrite_output_names(project, prefix="r_")
        assert names == {
            "PLOTFILE": ["r_pit.plt", "r_pit_1h.plt", "r_pit_1h_h8h.plt", "r_unit.plt"],
            "POSTFILE": ["r_post_a.pst", "r_post_b.pst"],
            "ERRORFIL": ["r_errors.lst"], "DEBUGOPT": ["r_model.dbg"],
        }
        text = project.to_aermod_input(validate=False)
        assert "PLOTFILE  PERIOD  ALL  r_unit.plt  41" in text
        assert "PLOTFILE  1  ALL  8TH  r_pit_1h_h8h.plt" in text
        assert "POSTFILE  1  ALL  PLOT  r_post_b.pst" in text
        assert "DEBUGOPT  MODEL  r_model.dbg  METEOR" in text
        assert project.control.debug_options == ["MODEL", "r_model.dbg", "METEOR"]
        for gone in ("/tmp/shared", "/tmp/dbg", "../"):
            assert gone not in text

    def test_debug_option_files(self):
        """Every field of ControlPathway.debug_options that is not an
        option name is a file; options are matched in any case, and an
        option without a file name keeps AERMOD's default."""
        project = self._project()
        project.control.debug_options = ["model", "../d/m.dbg", "AREA", "METEOR",
                                         r"C:\d\met.dbg", "DEPOS"]
        names = rewrite_output_names(project)
        assert names["DEBUGOPT"] == ["m.dbg", "met.dbg"]
        assert project.control.debug_options == ["model", "m.dbg", "AREA", "METEOR",
                                                 "met.dbg", "DEPOS"]
        assert "DEBUGOPT  model  m.dbg  AREA  METEOR  met.dbg  DEPOS" in \
            project.to_aermod_input(validate=False)

    def test_a_debug_file_named_like_another_output_raises(self):
        project = self._project()
        project.control.debug_options = ["AREA", "../other/pit.plt"]
        with pytest.raises(ValueError, match="both be written"):
            rewrite_output_names(project)

    @pytest.mark.parametrize(("pathway", "keyword", "fields", "renamed"), [
        ("OU", "PLOTFILE", ["ANNUAL", "ALL", "d/a.plt"], ["ANNUAL", "ALL", "a.plt"]),
        ("OU", "PLOTFILE", ["24", "ALL", "2ND", "d/a.plt", "30"],
         ["24", "ALL", "2ND", "a.plt", "30"]),
        ("OU", "POSTFILE", ["1", "ALL", "UNFORM", "d/p.bin"], ["1", "ALL", "UNFORM", "p.bin"]),
        ("OU", "MAXIFILE", ["1", "ALL", "10.", "d/m.max", "44"],
         ["1", "ALL", "10.", "m.max", "44"]),
        ("OU", "RANKFILE", ["1", "10", "d/r.rnk"], ["1", "10", "r.rnk"]),
        ("OU", "TOXXFILE", ["1", "1.0", "d/t.tox"], ["1", "1.0", "t.tox"]),
        ("OU", "SEASONHR", ["ALL", "d/s.shr"], ["ALL", "s.shr"]),
        ("OU", "EVALFILE", ["PIT", "d/e.evl"], ["PIT", "e.evl"]),
        ("OU", "SUMMFILE", ["d/s.sum"], ["s.sum"]),
        ("OU", "MAXDAILY", ["ALL", "d/md.dat"], ["ALL", "md.dat"]),
        ("OU", "MXDYBYYR", ["ALL", "d/my.dat"], ["ALL", "my.dat"]),
        ("OU", "MAXDCONT", ["ALL", "1", "THRESH", "5.", "d/mc.dat"],
         ["ALL", "1", "THRESH", "5.", "mc.dat"]),
        ("OU", "MAXDCONT", ["ALL", "1", "8", "d/mc.dat"], ["ALL", "1", "8", "mc.dat"]),
        ("CO", "ERRORFIL", [], []),                      # AERMOD's ERRORS.LST
        ("CO", "EVENTFIL", ["d/ev.inp", "SOCONT"], ["ev.inp", "SOCONT"]),
        ("CO", "SAVEFILE", ["d/a.sav", "5", "e/b.sav"], ["a.sav", "5", "b.sav"]),
        ("CO", "MULTYEAR", ["H6H", "d/y2.sav", "d/y1.sav"], ["H6H", "y2.sav", "d/y1.sav"]),
        ("CO", "MULTYEAR", ["d/y2.sav", "d/y1.sav"], ["y2.sav", "d/y1.sav"]),
        ("CO", "DEBUGOPT", ["model", "d/m.dbg", "PRIME", "d/p.dbg"],
         ["model", "m.dbg", "PRIME", "p.dbg"]),
        # Files AERMOD reads are left for run_design to link
        ("SO", "HOUREMIS", ["d/he.dat", "PIT"], ["d/he.dat", "PIT"]),
        ("OU", "NOHEADER", ["ALL"], ["ALL"]),
    ])
    def test_every_verbatim_output_keyword(self, pathway, keyword, fields, renamed):
        project = self._project()
        project.unparsed_lines = [UnparsedLine(pathway, keyword, list(fields))]
        rewrite_output_names(project)
        assert project.unparsed_lines[0].fields == renamed

    def test_names_that_collide_raise(self):
        project = self._project()
        project.output.plot_file_groups = [("1", "ALL", "a/PIT.plt")]
        with pytest.raises(ValueError, match="both be written"):
            rewrite_output_names(project)

    def test_name_without_a_file_part_raises(self):
        project = self._project()
        project.output.plot_file = "out/"
        with pytest.raises(ValueError, match="no file name part"):
            rewrite_output_names(project)

    def test_name_longer_than_aermod_reads_raises(self):
        project = self._project()
        project.output.plot_file = "p" * 201
        with pytest.raises(ValueError, match="200 characters"):
            rewrite_output_names(project)


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------

class TestManifest:
    def test_subclass_entries_round_trip(self, tmp_path):
        m = EnsembleManifest.load(tmp_path / "m.json")
        m.put(EnsembleManifestEntry(input_file="runs/x/run.inp", run_id="x",
                                    factors={"d": 2.5}, warnings=["W403 x"]))
        loaded = EnsembleManifest.load(tmp_path / "m.json")
        entry = loaded.entries["x"]
        assert isinstance(entry, EnsembleManifestEntry)
        assert entry.factors == {"d": 2.5} and entry.warnings == ["W403 x"]

    def test_base_manifest_still_builds_base_entries(self, tmp_path):
        m = RunManifest.load(tmp_path / "m.json")
        m.mark("a.inp", "success")
        assert type(RunManifest.load(tmp_path / "m.json").entries["a.inp"]) is RunManifestEntry

    def test_unknown_keys_are_ignored(self, tmp_path):
        """An ensemble manifest opens as a plain RunManifest, and vice versa."""
        m = EnsembleManifest.load(tmp_path / "m.json")
        m.put(EnsembleManifestEntry(input_file="i", run_id="x", status="success"))
        plain = RunManifest.load(tmp_path / "m.json")
        assert plain.entries["x"].status == "success"
        assert plain.summary()["success"] == 1

    def test_save_replaces_the_file_in_one_step(self, tmp_path, monkeypatch):
        path = tmp_path / "m.json"
        m = RunManifest.load(path)
        m.mark("a", "success")
        before = path.read_text()

        def _fail(*args, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(runner_utils.os, "replace", _fail)
        m.entries["b"] = RunManifestEntry("b")
        with pytest.raises(OSError):
            m.save()
        assert path.read_text() == before
        monkeypatch.undo()
        m.save()
        assert not path.with_name("m.json.tmp").exists()
        assert "b" in json.loads(path.read_text())


# ---------------------------------------------------------------------------
# run_design
# ---------------------------------------------------------------------------

@posix_only
class TestRunDesign:
    def test_four_runs_on_four_workers(self, replay_bin, tmp_path):
        root = tmp_path / "design"
        result = _design(replay_bin, root)
        exe_sha = file_sha256(replay_bin / "aermod")
        expected = [run_id(row, exe_sha, _met_sha()) for row in design.ROWS]
        # Keyed by run ID, in row order, one directory each
        assert list(result) == expected
        assert result.all_succeeded and result.n_run == 4 and result.n_skipped == 0
        assert sorted(p.name for p in (root / "runs").iterdir()) == sorted(expected)
        assert sorted(_calls(replay_bin)) == sorted(r["case"] for r in design.ROWS)
        for row, rid in zip(design.ROWS, expected):
            run = result[rid]
            assert run.run_dir == root.resolve() / "runs" / rid
            assert run.factors == row and run.success and not run.skipped
            assert run.result is not None and run.result.success
            # No overwrites: each run's PLOTFILEs are its own recording's
            for name in ("pit.plt", "pit_1h.plt"):
                assert (run.run_dir / name).read_bytes() == \
                    (FIXTURES / row["case"] / "outputs" / name).read_bytes()
        periods = {(result[rid].run_dir / "pit.plt").read_bytes() for rid in expected}
        assert len(periods) == 4
        # Nothing was written where build() pointed the outputs
        assert not (root / "shared").exists() and not (root / "runs" / "shared").exists()
        assert not Path("/nonexistent-pyaermod-dir").exists()

    def test_run_directory_holds_deck_factors_and_met_links(self, replay_bin, tmp_path):
        result = _design(replay_bin, tmp_path / "d", rows=design.ROWS[:1], n_workers=1)
        run = next(iter(result.values()))
        deck = (run.run_dir / DECK_NAME).read_text()
        assert deck == (FIXTURES / "d2p5_rho1" / "aermod.inp").read_text()
        assert "SURFFILE  AERMET2.SFC" in deck and "PLOTFILE  PERIOD  ALL  pit.plt" in deck
        for name in ("AERMET2.SFC", "AERMET2.PFL"):
            link = run.run_dir / name
            assert link.is_symlink() and link.resolve() == (design.MET / name).resolve()
        payload = json.loads((run.run_dir / "factors.json").read_text())
        assert payload == {
            "binary_sha256": file_sha256(replay_bin / "aermod"),
            "factors": design.ROWS[0], "input_files_sha256": {},
            "met_sha256": _met_sha(), "schema_version": 2,
        }
        text = canonical_json(payload)
        assert hashlib.sha256(text.encode()).hexdigest() == run.run_id

    def test_manifest_records_the_run(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=design.ROWS[:2], n_workers=2)
        data = json.loads((root / "manifest.json").read_text())
        assert list(data) == list(result)
        for rid, raw in data.items():
            run = result[rid]
            assert raw["status"] == "success"
            assert raw["run_id"] == rid and raw["run_dir"] == f"runs/{rid}"
            assert raw["input_file"] == f"runs/{rid}/run.inp"
            assert raw["factors"] == run.factors
            assert raw["input_sha256"] == file_sha256(run.run_dir / DECK_NAME)
            assert raw["binary"] == str((replay_bin / "aermod").resolve())
            assert raw["binary_sha256"] == file_sha256(replay_bin / "aermod")
            assert raw["aermod_version"] == "26135"
            assert raw["met_sha256"] == _met_sha()
            assert raw["met_files"]["surface"] == str((design.MET / "AERMET2.SFC").resolve())
            assert raw["input_files"] == {} and raw["input_files_sha256"] == {}
            assert raw["outputs"] == {"PLOTFILE": ["pit.plt", "pit_1h.plt"]}
            assert raw["schema_version"] == SCHEMA_VERSION
            assert [w.split()[0] for w in raw["warnings"]] == ["W403", "W496"]
            assert raw["warning_count"] == 2 and raw["fatal_count"] == 0
            assert raw["return_code"] == 0 and raw["runtime_seconds"] > 0
            assert raw["started"] and raw["finished"]
            assert raw["pyaermod_version"]
            assert raw["git_commit"] is None or len(raw["git_commit"]) == 40
        csv = pd.read_csv(root / "manifest.csv", index_col="run_id")
        assert list(csv.index) == list(result)
        assert list(csv["factor.case"]) == ["d2p5_rho1", "d10_rho1"]

    def test_second_call_resumes_everything(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        first = _design(replay_bin, root)
        assert len(_calls(replay_bin)) == 4
        again = _design(replay_bin, root)
        assert len(_calls(replay_bin)) == 4  # AERMOD was not run again
        assert list(again) == list(first)
        assert again.n_skipped == 4 and again.n_run == 0 and again.all_succeeded
        assert all(r.result is None for r in again.values())
        assert again.run_seconds == 0.0

    def test_resume_false_runs_everything_again(self, replay_bin, tmp_path):
        _design(replay_bin, tmp_path / "d", rows=design.ROWS[:2], n_workers=1)
        again = _design(replay_bin, tmp_path / "d", rows=design.ROWS[:2], n_workers=1,
                        resume=False)
        assert again.n_run == 2 and len(_calls(replay_bin)) == 4

    def test_resumes_after_an_interrupt(self, replay_bin, tmp_path):
        """Kill the whole design part way through; running it again makes
        only the runs that had not finished."""
        root = tmp_path / "d"
        held = {"d2p5_rho2p65", "d10_rho2p65"}
        (replay_bin / "hold").write_text("\n".join(sorted(held)) + "\n")
        script = tmp_path / "go.py"
        script.write_text(
            "import importlib.util, sys\n"
            "from pyaermod.ensemble import run_design\n"
            f"spec = importlib.util.spec_from_file_location('d', {str(FIXTURES / 'design.py')!r})\n"
            "design = importlib.util.module_from_spec(spec); spec.loader.exec_module(design)\n"
            "if __name__ == '__main__':\n"
            f"    run_design(design.ROWS, design.build, {str(root)!r}, n_workers=4,\n"
            f"               executable={str(replay_bin / 'aermod')!r})\n"
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(
            [str(Path(ensemble.__file__).parent.parent), os.environ.get("PYTHONPATH", "")])}
        proc = subprocess.Popen([sys.executable, str(script)], env=env,
                                start_new_session=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        manifest = root / "manifest.json"
        deadline = time.monotonic() + 120
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    pytest.fail(f"the design ended early: {proc.stderr.read().decode()}")
                if manifest.exists():
                    data = json.loads(manifest.read_text())  # saved by os.replace
                    done = [e for e in data.values() if e["status"] == "success"]
                    if len(done) == 2 and held <= set(_calls(replay_bin)):
                        break
                time.sleep(0.1)
            else:
                pytest.fail("the design did not reach two finished runs")
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        data = json.loads(manifest.read_text())
        assert sorted(e["status"] for e in data.values()) == ["pending", "pending",
                                                              "success", "success"]
        (replay_bin / "hold").unlink()

        result = _design(replay_bin, root)
        calls = _calls(replay_bin)
        for case in ("d2p5_rho1", "d10_rho1"):
            assert calls.count(case) == 1  # finished before the kill, not run again
        for case in held:
            assert calls.count(case) == 2  # killed while running, run again
        assert result.all_succeeded and result.n_skipped == 2 and result.n_run == 2
        by_case = {r.factors["case"]: r for r in result.values()}
        for case in held:
            assert (by_case[case].run_dir / "pit.plt").read_bytes() == \
                (FIXTURES / case / "outputs" / "pit.plt").read_bytes()

    def test_ctrl_c_in_the_caller_keeps_the_finished_runs(self, replay_bin, tmp_path):
        """KeyboardInterrupt while waiting for workers: the manifest already
        holds the run that finished, and the next call resumes from it."""
        root = tmp_path / "d"

        class CtrlC:
            def start(self, total, description=""):
                pass

            def update(self, n=1, message=""):
                raise KeyboardInterrupt

            def finish(self):
                pass

        with pytest.raises(KeyboardInterrupt):
            _design(replay_bin, root, n_workers=2, progress=CtrlC())
        data = json.loads((root / "manifest.json").read_text())
        finished = [rid for rid, e in data.items() if e["status"] == "success"]
        assert len(finished) >= 1
        result = _design(replay_bin, root)
        assert result.all_succeeded
        assert result.n_skipped == len(finished)
        for rid in finished:
            assert result[rid].skipped

    def test_a_different_deck_for_the_same_factors_runs_again(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        rows = design.ROWS[:1]
        first = _design(replay_bin, root, rows=rows, n_workers=1)
        rid = next(iter(first))

        def other_title(factors):
            project = design.build(factors)
            project.control.title_one = "an edited deck"
            return project

        result = run_design(rows, other_title, root, n_workers=1,
                            executable=replay_bin / "aermod")
        assert list(result) == [rid]  # same factors, same run ID
        run = result[rid]
        assert not run.skipped
        assert run.entry.status == "failed"  # the fake has no recording of it
        assert "an edited deck" in (run.run_dir / DECK_NAME).read_text()
        assert not (run.run_dir / "pit.plt").exists()  # the old results went first

    def test_a_missing_plotfile_runs_again(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        first = _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        run = next(iter(first.values()))
        (run.run_dir / "pit_1h.plt").unlink()
        again = _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        assert again.n_run == 1 and again.all_succeeded
        assert (run.run_dir / "pit_1h.plt").exists()

    def test_an_edited_out_file_runs_again(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        first = _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        out = next(iter(first.values())).run_dir / "run.out"
        out.write_text(out.read_text().replace("AERMOD Finishes Successfully", "cut off"))
        assert _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1).n_run == 1

    def test_extras_run(self, replay_bin, tmp_path):
        """HOUREMIS, a second POSTFILE and a 2ND PLOTFILE, all held only as
        lines kept verbatim: the outputs land in the run directory and the
        emission file is hashed and linked."""
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        run = next(iter(result.values()))
        assert run.success, run.entry.error_message
        deck = (run.run_dir / DECK_NAME).read_text()
        assert deck == (FIXTURES / "extras" / "aermod.inp").read_text()
        assert "HOUREMIS  houremis.dat  PIT" in deck
        assert run.entry.outputs == {
            "PLOTFILE": ["pit.plt", "pit_1h.plt", "pit_1h_2nd.plt"],
            "POSTFILE": ["pit_per.pst", "pit_1h.bin"],
        }
        for names in run.entry.outputs.values():
            for name in names:
                assert (run.run_dir / name).read_bytes() == \
                    (FIXTURES / "extras" / "outputs" / name).read_bytes()
        assert run.entry.input_files == {"HOUREMIS": str(design.HOUREMIS.resolve())}
        assert run.entry.input_files_sha256 == {"HOUREMIS": file_sha256(design.HOUREMIS)}
        link = run.run_dir / "houremis.dat"
        assert link.is_symlink() and link.resolve() == design.HOUREMIS.resolve()
        assert run.run_id == run_id(design.EXTRAS_ROW, file_sha256(replay_bin / "aermod"),
                                    _met_sha(), run.entry.input_files_sha256)
        assert not (root / "shared").exists() and not (root / "runs" / "shared").exists()

    @pytest.mark.parametrize("name", ["pit_per.pst", "pit_1h.bin", "pit_1h_2nd.plt"])
    def test_a_missing_postfile_or_verbatim_plotfile_runs_again(self, replay_bin, tmp_path,
                                                                name):
        root = tmp_path / "d"
        first = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        run = next(iter(first.values()))
        (run.run_dir / name).unlink()
        again = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        assert again.n_run == 1 and again.n_skipped == 0 and again.all_succeeded
        assert _calls(replay_bin) == ["extras", "extras"]
        assert (run.run_dir / name).exists()

    def test_an_edited_emission_file_is_a_new_run(self, replay_bin, tmp_path, monkeypatch):
        """Editing the HOUREMIS file the deck names makes a new run, in a
        new directory, even though the deck text is the same."""
        houremis = tmp_path / "in" / "houremis.dat"
        houremis.parent.mkdir()
        houremis.write_text(design.houremis_lines())
        monkeypatch.setattr(design, "HOUREMIS", houremis)
        root = tmp_path / "d"
        first = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        old = next(iter(first.values()))
        houremis.write_text(design.houremis_lines(scale=10.0))
        again = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        new = next(iter(again.values()))
        assert again.n_skipped == 0 and again.n_run == 1 and new.success
        assert new.run_id != old.run_id and old.run_dir.exists()
        assert new.entry.input_files_sha256["HOUREMIS"] == file_sha256(houremis)
        assert new.entry.input_files_sha256 != old.entry.input_files_sha256
        assert (new.run_dir / DECK_NAME).read_text() == (old.run_dir / DECK_NAME).read_text()
        assert json.loads((root / DESIGN_NAME).read_text())["run_ids"] == [new.run_id]
        assert set(collect_plotfiles(root, out_stem=None)["run_id"]) == {new.run_id}

    def test_a_changed_input_hash_under_the_same_id_runs_again(self, replay_bin, tmp_path):
        """_is_done compares the recorded input hashes too, not only the ID."""
        root = tmp_path / "d"
        first = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        rid = next(iter(first))
        manifest = EnsembleManifest.load(root / "manifest.json")
        manifest.entries[rid].input_files_sha256 = {"HOUREMIS": "0" * 64}
        manifest.save()
        again = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        assert again.n_run == 1 and again[rid].entry.input_files_sha256 == \
            {"HOUREMIS": file_sha256(design.HOUREMIS)}

    def test_failed_run(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        rows = [design.ROWS[0], design.FAILING_ROW]
        result = _design(replay_bin, root, rows=rows, n_workers=2)
        assert result.n_failed == 1 and not result.all_succeeded
        failed = next(r for r in result.values() if not r.success)
        assert failed.factors["case"] == "annual_e480"
        assert failed.entry.status == "failed"
        assert failed.entry.error_message.startswith("E480 MAIN:")
        assert failed.entry.fatal_count == 1
        # A failed run is made again on resume; the good one is not
        again = _design(replay_bin, root, rows=rows, n_workers=2)
        assert again.n_run == 1 and again.n_skipped == 1
        assert _calls(replay_bin).count("annual_e480") == 2

    def test_dataframe_rows(self, replay_bin, tmp_path):
        rows = pd.DataFrame(design.ROWS[:2])
        result = _design(replay_bin, tmp_path / "d", rows=rows, n_workers=1)
        df = result.to_dataframe()
        assert list(df.index) == list(result)
        assert list(df["case"]) == ["d2p5_rho1", "d10_rho1"]
        assert list(df["status"]) == ["success", "success"]
        assert not df["skipped"].any()
        assert (df["warning_count"] == 2).all()

    def test_progress_is_reported(self, replay_bin, tmp_path):
        seen = []

        class Recorder:
            def start(self, total, description=""):
                seen.append(("start", total))

            def update(self, n=1, message=""):
                seen.append(("update", n))

            def finish(self):
                seen.append(("finish",))

        _design(replay_bin, tmp_path / "d", rows=design.ROWS[:2], n_workers=1,
                progress=Recorder())
        assert seen == [("start", 2), ("update", 1), ("update", 1), ("finish",)]

    def test_runs_overlap(self, replay_bin, tmp_path):
        """Four one-directory-each runs of 3 s on four workers overlap.

        The fake counts, as each run ends, the runs still in progress, so
        this does not depend on how long the workers take to start.
        """
        (replay_bin / "delay").write_text("3\n")
        result = _design(replay_bin, tmp_path / "d")
        assert result.all_succeeded
        assert result.run_seconds >= 4 * 3.0
        in_progress = [int(n) for n in (replay_bin / "overlap.log").read_text().split()]
        assert len(in_progress) == 4 and max(in_progress) >= 2

    def test_a_worker_that_fails_is_recorded(self, replay_bin, tmp_path):
        exe = replay_bin / "aermod"

        class RemoveBinary:
            """Remove the binary once run_design has hashed it."""

            def start(self, total, description=""):
                exe.unlink()

            def update(self, n=1, message=""):
                pass

            def finish(self):
                pass

        result = _design(replay_bin, tmp_path / "d", rows=design.ROWS[:2], n_workers=2,
                         progress=RemoveBinary())
        assert result.n_failed == 2
        for run in result.values():
            assert run.entry.error_message.startswith("The worker running this deck failed")
            assert "not found" in run.entry.error_message

    def test_mapping_protocol(self, replay_bin, tmp_path):
        result = _design(replay_bin, tmp_path / "d", rows=design.ROWS[:1], n_workers=1)
        rid = next(iter(result))
        assert len(result) == 1 and rid in result and result[rid].deck.name == DECK_NAME


@posix_only
class TestRunDesignRefusals:
    @pytest.fixture()
    def exe(self, tmp_path):
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
        return exe

    def test_duplicate_rows(self, exe, tmp_path):
        with pytest.raises(ValueError, match="same factors"):
            run_design([design.ROWS[0], dict(design.ROWS[0])], design.build,
                       tmp_path / "d", executable=exe)

    def test_reserved_factor_name(self, exe, tmp_path):
        with pytest.raises(ValueError, match="reserved"):
            run_design([{**design.ROWS[0], "status": 1}], design.build,
                       tmp_path / "d", executable=exe)

    def test_rows_must_be_mappings(self, exe, tmp_path):
        with pytest.raises(TypeError, match="not a mapping"):
            run_design([("a", 1)], design.build, tmp_path / "d", executable=exe)

    def test_factor_names_must_be_strings(self, exe, tmp_path):
        with pytest.raises(TypeError, match="not strings"):
            run_design([{1: "a"}], design.build, tmp_path / "d", executable=exe)

    def test_missing_met_file(self, exe, tmp_path):
        def build(factors):
            project = design.build(factors)
            project.meteorology.surface_file = str(tmp_path / "missing.sfc")
            return project

        with pytest.raises(FileNotFoundError, match="surface met file not found"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_relative_met_path_is_taken_from_the_current_directory(
            self, exe, tmp_path, monkeypatch):
        monkeypatch.chdir(design.MET)

        def build(factors):
            project = design.build(factors)
            project.meteorology.surface_file = "AERMET2.SFC"
            return project

        # The fake exits 0 without writing an .out: the run fails, but the
        # met file was found and linked.
        result = run_design(design.ROWS[:1], build, tmp_path / "d", n_workers=1,
                            executable=exe)
        run = next(iter(result.values()))
        assert run.entry.met_files["surface"] == str((design.MET / "AERMET2.SFC").resolve())
        assert (run.run_dir / "AERMET2.SFC").resolve() == (design.MET / "AERMET2.SFC").resolve()

    def test_met_file_named_like_an_output(self, exe, tmp_path):
        def build(factors):
            project = design.build(factors)
            project.output.plot_file = "aermet2.sfc"
            return project

        with pytest.raises(ValueError, match="name of another file"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_output_named_like_a_runner_file(self, exe, tmp_path):
        def build(factors):
            project = design.build(factors)
            project.output.plot_file = "../x/run.out"
            return project

        with pytest.raises(ValueError, match="used in the run directory by the runner"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_met_file_name_longer_than_aermod_reads(self, exe, tmp_path):
        long = tmp_path / ("m" * 201)
        shutil.copy(design.MET / "AERMET2.SFC", long)

        def build(factors):
            project = design.build(factors)
            project.meteorology.surface_file = str(long)
            return project

        with pytest.raises(ValueError, match="200 characters"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_copies_met_file_where_links_fail(self, exe, tmp_path, monkeypatch):
        def no_links(*args, **kw):
            raise OSError("links not allowed")

        monkeypatch.setattr(Path, "symlink_to", no_links)
        monkeypatch.setattr(ensemble.os, "link", no_links)
        result = run_design(design.ROWS[:1], design.build, tmp_path / "d", n_workers=1,
                            executable=exe)
        met = next(iter(result.values())).run_dir / "AERMET2.SFC"
        assert not met.is_symlink()
        assert met.read_bytes() == (design.MET / "AERMET2.SFC").read_bytes()

    def test_every_input_keyword_is_hashed_and_linked(self, exe, tmp_path, monkeypatch):
        from pyaermod.pathways import (
            BackgroundSpec,
            ChemistryMethod,
            ChemistryOptions,
            InitFile,
            MultiYear,
            NOxBackground,
            OzoneData,
        )

        data = tmp_path / "data"
        data.mkdir()
        for name in ("o3.dat", "o3s1.dat", "nox.dat", "noxs1.dat", "init.sav", "y1.sav",
                     "he1.dat", "he2.dat", "bg.dat", "o3u.dat", "inc.dat"):
            (data / name).write_text(name + "\n")
        (data / "sub").mkdir()
        (data / "sub" / "init2.sav").write_text("init2\n")
        monkeypatch.chdir(data)

        def build(factors):
            project = design.build(factors)
            control = project.control
            control.init_file = InitFile("init.sav")          # relative: from the cwd
            control.multiyear = MultiYear("y2.sav", init_file=str(data / "y1.sav"))
            control.chemistry = ChemistryOptions(
                method=ChemistryMethod.GRSM,
                ozone_data=OzoneData(ozone_file=str(data / "o3.dat"),
                                     by_sector={1: BackgroundSpec(hourly_file="o3s1.dat")}),
                nox_background=NOxBackground(
                    hourly_file="nox.dat",
                    by_sector={1: BackgroundSpec(hourly_file="noxs1.dat")}),
            )
            project.unparsed_lines = [
                UnparsedLine("SO", "HOUREMIS", ["he1.dat", "PIT"]),
                UnparsedLine("SO", "HOUREMIS", [str(data / "he1.dat"), "PIT2"]),  # same file
                UnparsedLine("SO", "HOUREMIS", ["he2.dat", "PIT3"]),
                UnparsedLine("SO", "BACKGRND", ["SECT1", "HOURLY", "bg.dat"]),
                UnparsedLine("CO", "OZONEFIL", ["SECT2", "o3u.dat", "PPB"]),
                UnparsedLine("RE", "INCLUDED", ["inc.dat"]),
                UnparsedLine("CO", "INITFILE", []),
                UnparsedLine("CO", "MULTYEAR", ["H6H", "y3.sav", "sub/init2.sav"]),
            ]
            return project

        result = run_design(design.ROWS[:1], build, tmp_path / "d", n_workers=1,
                            executable=exe, validate=False)
        run = next(iter(result.values()))
        roles = {
            "INITFILE": "init.sav", "MULTYEAR": "y1.sav", "OZONEFIL": "o3.dat",
            "OZONEFIL.2": "o3s1.dat", "NOX_FILE": "nox.dat", "NOX_FILE.2": "noxs1.dat",
            "HOUREMIS": "he1.dat", "HOUREMIS.2": "he2.dat", "BACKGRND": "bg.dat",
            "OZONEFIL.3": "o3u.dat", "INCLUDED": "inc.dat", "MULTYEAR.2": "sub/init2.sav",
        }
        assert run.entry.input_files == {r: str(data / n) for r, n in roles.items()}
        assert run.entry.input_files_sha256 == {r: file_sha256(data / n)
                                                for r, n in roles.items()}
        deck = (run.run_dir / DECK_NAME).read_text()
        for line in ("INITFILE  init.sav", "OZONEFIL  o3.dat", "HOUREMIS  he1.dat  PIT2",
                     "BACKGRND  SECT1  HOURLY  bg.dat", "OZONEFIL  SECT2  o3u.dat  PPB",
                     "INCLUDED  inc.dat", "MULTYEAR  H6H  y3.sav  init2.sav"):
            assert line in deck, line
        assert str(data) not in deck
        for name in set(Path(n).name for n in roles.values()):
            assert (run.run_dir / name).resolve() == (data / name).resolve() or \
                (run.run_dir / name).resolve() == (data / "sub" / name).resolve()

    def test_nox_file_shorthand_is_an_input(self, exe, tmp_path):
        """And a bare INITFILE (AERMOD's SAVE.FIL) names no file to link."""
        from pyaermod.pathways import ChemistryMethod, ChemistryOptions, InitFile

        nox = tmp_path / "nox.dat"
        nox.write_text("x\n")

        def build(factors):
            project = design.build(factors)
            project.control.chemistry = ChemistryOptions(method=ChemistryMethod.GRSM,
                                                         nox_file=str(nox))
            project.control.init_file = InitFile()
            return project

        result = run_design(design.ROWS[:1], build, tmp_path / "d", n_workers=1,
                            executable=exe, validate=False)
        assert next(iter(result.values())).entry.input_files == {"NOX_FILE": str(nox)}

    def test_modelled_houremis_is_an_input(self, exe, tmp_path):
        """SourcePathway.hourly_emissions (the HOUREMIS cards the model
        holds) is hashed and linked like a HOUREMIS line kept verbatim."""
        from pyaermod.sources import HourlyEmissionFile

        he = tmp_path / "data" / "pit.emi"
        he.parent.mkdir()
        he.write_text(design.houremis_lines())

        def build(factors):
            project = design.build(factors)
            project.sources.hourly_emissions = [HourlyEmissionFile(str(he), ["PIT"])]
            return project

        result = run_design(design.ROWS[:1], build, tmp_path / "d", n_workers=1,
                            executable=exe)
        run = next(iter(result.values()))
        assert run.entry.input_files == {"HOUREMIS": str(he)}
        assert run.entry.input_files_sha256 == {"HOUREMIS": file_sha256(he)}
        assert "HOUREMIS  pit.emi  PIT" in (run.run_dir / DECK_NAME).read_text()
        assert (run.run_dir / "pit.emi").resolve() == he.resolve()

    def test_missing_input_file(self, exe, tmp_path):
        def build(factors):
            project = design.build(factors)
            project.unparsed_lines = [UnparsedLine("SO", "HOUREMIS", ["gone.dat", "PIT"])]
            return project

        with pytest.raises(FileNotFoundError, match="HOUREMIS file not found"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_two_input_files_with_one_name(self, exe, tmp_path):
        for sub in ("a", "b"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "he.dat").write_text(sub)

        def build(factors):
            project = design.build(factors)
            project.unparsed_lines = [
                UnparsedLine("SO", "HOUREMIS", [str(tmp_path / "a" / "he.dat"), "PIT"]),
                UnparsedLine("SO", "HOUREMIS", [str(tmp_path / "b" / "he.dat"), "PIT2"]),
            ]
            return project

        with pytest.raises(ValueError, match=r"HOUREMIS file 'he\.dat' has the name of another"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_empty_met_file_name(self, exe, tmp_path):
        def build(factors):
            project = design.build(factors)
            project.meteorology.profile_file = ""
            return project

        with pytest.raises(FileNotFoundError, match="profile met file not found"):
            run_design(design.ROWS[:1], build, tmp_path / "d", executable=exe)

    def test_empty_design(self, exe, tmp_path):
        result = run_design([], design.build, tmp_path / "d", executable=exe)
        assert len(result) == 0 and result.concurrency == 0.0
        assert result.to_dataframe().empty
        assert EnsembleManifest.load(tmp_path / "d" / "manifest.json").to_dataframe().empty


# ---------------------------------------------------------------------------
# Debug files (CO DEBUGOPT, ControlPathway.debug_options)
# ---------------------------------------------------------------------------

# Answers any deck as AERMOD answered the recorded run d2p5_rho1: the
# deck's own echo, then the rest of that run's .out, stdout and
# PLOTFILEs. It writes the debug files listed in {bindir}/write, one
# per line, as AERMOD writes only the debug files whose option applies.
_ANSWER = """#!/bin/bash
rec="{recordings}/d2p5_rho1"
n=$(awk 'END {{ print NR }}' "$rec/aermod.inp")
awk 1 aermod.inp > aermod.out
tail -n +$((n + 1)) "$rec/aermod.out" >> aermod.out
cat "$rec/stdout.txt"
cp "$rec"/outputs/* .
basename "$PWD" >> "{bindir}/calls.log"
while read -r f; do [ -n "$f" ] && echo "debug output of $PWD" > "$f"; done < "{bindir}/write"
exit 0
"""

#: The debug options of these tests: AREA with a file outside the run
#: directory, METEOR with an absolute one, and MODEL with a file the
#: fake does not write, as AERMOD does not when DEPOS sends MODEL's
#: output to DEPOS.DBG.
DEBUG_OPTIONS = ["AREA", "../shared/area.dbg", "METEOR", "/nonexistent-pyaermod-dir/met.dbg",
                 "MODEL", "model.dbg"]


@posix_only
class TestDebugFiles:
    @pytest.fixture()
    def answer_bin(self, tmp_path):
        bindir = tmp_path / "bin"
        bindir.mkdir()
        exe = bindir / "aermod"
        exe.write_text(_ANSWER.format(recordings=FIXTURES, bindir=bindir))
        exe.chmod(0o755)
        (bindir / "write").write_text("area.dbg\nmet.dbg\n")
        return bindir

    @staticmethod
    def _build(factors):
        project = design.build(factors)
        project.control.debug_options = list(DEBUG_OPTIONS)
        return project

    def _run(self, bindir, root, n_workers=2):
        return run_design(design.ROWS[:2], self._build, root, n_workers=n_workers,
                          executable=bindir / "aermod")

    def test_each_run_writes_its_own_debug_files(self, answer_bin, tmp_path):
        result = self._run(answer_bin, tmp_path / "d")
        assert result.all_succeeded, [r.entry.error_message for r in result.values()]
        dirs = {r.run_dir for r in result.values()}
        assert len(dirs) == 2
        for run in result.values():
            deck = (run.run_dir / DECK_NAME).read_text()
            assert "DEBUGOPT  AREA  area.dbg  METEOR  met.dbg  MODEL  model.dbg" in deck
            for name in ("area.dbg", "met.dbg"):
                assert (run.run_dir / name).read_text() == f"debug output of {run.run_dir}\n"
            # model.dbg was named but not written, so it is not recorded
            assert run.entry.outputs["DEBUGOPT"] == ["area.dbg", "met.dbg"]
        manifest = EnsembleManifest.load(tmp_path / "d" / "manifest.json")
        assert all(e.outputs["DEBUGOPT"] == ["area.dbg", "met.dbg"]
                   for e in manifest.entries.values())
        assert not (tmp_path / "shared").exists()

    def test_resume_checks_the_debug_files(self, answer_bin, tmp_path):
        root = tmp_path / "d"
        first = self._run(answer_bin, root)
        again = self._run(answer_bin, root)
        assert again.n_skipped == 2 and again.n_run == 0
        victim = next(iter(first.values()))
        (victim.run_dir / "met.dbg").unlink()
        third = self._run(answer_bin, root)
        assert third.n_run == 1 and third[victim.run_id].skipped is False
        assert (victim.run_dir / "met.dbg").exists()
        assert _calls(answer_bin).count(victim.run_id) == 2

    def test_no_debug_file_written(self, answer_bin, tmp_path):
        (answer_bin / "write").write_text("")
        result = self._run(answer_bin, tmp_path / "d", n_workers=1)
        assert result.all_succeeded
        assert all("DEBUGOPT" not in r.entry.outputs for r in result.values())
        assert self._run(answer_bin, tmp_path / "d", n_workers=1).n_skipped == 2

    def test_a_failed_run_keeps_every_name(self, answer_bin, tmp_path):
        """The names stay recorded, so a later attempt removes what a
        failed one left."""
        (answer_bin / "aermod").write_text("#!/bin/bash\necho partial > area.dbg\nexit 1\n")
        result = self._run(answer_bin, tmp_path / "d", n_workers=1)
        for run in result.values():
            assert run.entry.status == "failed"
            assert run.entry.outputs["DEBUGOPT"] == ["area.dbg", "met.dbg", "model.dbg"]


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_git_commit_outside_a_checkout(self, monkeypatch):
        def fail(*args, **kw):
            return subprocess.CompletedProcess(args, 128, "", "not a git repository")

        monkeypatch.setattr(ensemble.subprocess, "run", fail)
        assert ensemble._git_commit() == (None, None)

    def test_git_missing(self, monkeypatch):
        def fail(*args, **kw):
            raise FileNotFoundError("git")

        monkeypatch.setattr(ensemble.subprocess, "run", fail)
        assert ensemble._git_commit() == (None, None)

    def test_git_commit_and_dirty_flag(self, monkeypatch):
        answers = iter([
            subprocess.CompletedProcess([], 0, "__init__.py\n", ""),
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
            subprocess.CompletedProcess([], 0, " M src/x.py\n", ""),
        ])
        monkeypatch.setattr(ensemble.subprocess, "run", lambda *a, **k: next(answers))
        assert ensemble._git_commit() == ("a" * 40, True)

    def test_a_repository_that_is_not_pyaermod_is_not_reported(self, monkeypatch):
        """An installed copy in some project's tree: __init__.py is not tracked there."""
        calls = []

        def run(args, **kw):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, "", "did not match any file")

        monkeypatch.setattr(ensemble.subprocess, "run", run)
        assert ensemble._git_commit() == (None, None)
        assert len(calls) == 1 and "ls-files" in calls[0]

    def test_this_checkout(self):
        commit, dirty = ensemble._git_commit()
        if commit is not None:  # running from a git checkout of pyaermod
            assert len(commit) == 40 and isinstance(dirty, bool)

    def test_head_fails(self, monkeypatch):
        answers = iter([subprocess.CompletedProcess([], 0, "__init__.py\n", ""),
                        subprocess.CompletedProcess([], 128, "", "no HEAD")])
        monkeypatch.setattr(ensemble.subprocess, "run", lambda *a, **k: next(answers))
        assert ensemble._git_commit() == (None, None)

    def test_version_banner(self, tmp_path):
        assert ensemble._aermod_version(FIXTURES / "d10_rho1" / "aermod.out") == "26135"
        (tmp_path / "x.out").write_text("no banner\n")
        assert ensemble._aermod_version(tmp_path / "x.out") is None
        assert ensemble._aermod_version(tmp_path / "missing.out") is None

    def test_version_banner_after_a_long_deck_echo(self, tmp_path):
        # AERMOD echoes the deck before its first banner; a large receptor
        # network puts the banner past any fixed-size head.
        echo = "".join(f"   RE DISCCART  {i:10.2f}  {i:10.2f}\n" for i in range(12_000))
        assert len(echo) > 400_000
        out = tmp_path / "big.out"
        out.write_text(echo + " *** AERMOD - VERSION 26135  ***   *** title ***\n", encoding="latin-1")
        assert ensemble._aermod_version(out) == "26135"


# ---------------------------------------------------------------------------
# collect_plotfiles
# ---------------------------------------------------------------------------

@posix_only
class TestCollectPlotfiles:
    def test_tidy_table_csv_and_npz(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=[*design.ROWS, design.FAILING_ROW])
        table = collect_plotfiles(root)
        good = [rid for rid, r in result.items() if r.success]
        assert len(good) == 4
        # 4 successful runs x 2 PLOTFILEs x 72 receptors; the failed run is left out
        assert len(table) == 4 * 2 * 72
        assert set(table["run_id"]) == set(good)
        assert list(table.columns[:3]) == ["run_id", "plotfile", "receptor"]
        for col in ("x", "y", "average_conc", "dry_depo", "zelev", "zhill", "zflag",
                    "ave", "grp", "num_hrs", "rank", "net_id", "date_conc"):
            assert col in table.columns
        for rid in good:
            for name in ("pit.plt", "pit_1h.plt"):
                rows = table[(table.run_id == rid) & (table.plotfile == name)]
                ref = read_plotfile(result[rid].run_dir / name)
                assert list(rows["receptor"]) == list(range(72))
                assert list(rows["average_conc"]) == ref.values("AVERAGE_CONC")
                assert list(rows["dry_depo"]) == ref.values("DRY_DEPO")
        period = table[table.plotfile == "pit.plt"]
        assert period["num_hrs"].notna().all() and period["rank"].isna().all()

        csv = pd.read_csv(root / "plotfiles.csv")
        assert len(csv) == len(table)
        np.testing.assert_array_equal(csv["dry_depo"].to_numpy(), table["dry_depo"].to_numpy())
        with np.load(root / "plotfiles.npz") as npz:  # no allow_pickle needed
            assert list(npz.files) == list(table.columns)
            np.testing.assert_array_equal(npz["average_conc"], table["average_conc"].to_numpy())
            assert npz["run_id"].dtype.kind == "U"
            assert list(npz["run_id"]) == list(table["run_id"])
            assert set(npz["rank"][:72]) == {""}  # missing text is empty

    def test_run_ids_and_no_files(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=design.ROWS[:2], n_workers=2)
        rid = next(iter(result))
        table = collect_plotfiles(root, run_ids=[rid], out_stem=None)
        assert set(table["run_id"]) == {rid} and len(table) == 2 * 72
        assert not (root / "plotfiles.csv").exists()

    def test_defaults_to_the_latest_design(self, replay_bin, tmp_path):
        """A row dropped from the design stays in the manifest but not in
        the default collection."""
        root = tmp_path / "d"
        both = _design(replay_bin, root, rows=design.ROWS[:2], n_workers=2)
        one = _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        assert len(one.manifest.entries) == 2
        assert json.loads((root / DESIGN_NAME).read_text()) == {
            "schema_version": SCHEMA_VERSION, "run_ids": list(one)}
        assert set(collect_plotfiles(root, out_stem=None)["run_id"]) == set(one)
        assert set(one.collect_plotfiles(out_stem=None)["run_id"]) == set(one)
        everything = collect_plotfiles(root, run_ids=one.manifest.entries, out_stem=None)
        assert set(everything["run_id"]) == set(both)
        # A root written before design.json existed: every successful run
        (root / DESIGN_NAME).unlink()
        assert set(collect_plotfiles(root, out_stem=None)["run_id"]) == set(both)

    def test_verbatim_plotfile_is_collected(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=[design.EXTRAS_ROW], n_workers=1)
        table = result.collect_plotfiles()
        assert sorted(set(table["plotfile"])) == ["pit.plt", "pit_1h.plt", "pit_1h_2nd.plt"]
        second = table[table.plotfile == "pit_1h_2nd.plt"]
        assert len(second) == 72 and set(second["rank"]) == {"2ND"}
        assert (root / "plotfiles.csv").exists()

    def test_out_stem_elsewhere(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        collect_plotfiles(root, out_stem=tmp_path / "results" / "basis")
        assert (tmp_path / "results" / "basis.csv").exists()
        assert (tmp_path / "results" / "basis.npz").exists()

    def test_missing_plotfile_raises(self, replay_bin, tmp_path):
        root = tmp_path / "d"
        result = _design(replay_bin, root, rows=design.ROWS[:1], n_workers=1)
        (next(iter(result.values())).run_dir / "pit.plt").unlink()
        with pytest.raises(FileNotFoundError, match=r"PLOTFILE pit\.plt is missing"):
            collect_plotfiles(root)

    def test_nothing_to_collect(self, tmp_path):
        table = collect_plotfiles(tmp_path)
        assert table.empty and list(table.columns) == ["run_id", "plotfile", "receptor"]
        with np.load(tmp_path / "plotfiles.npz") as npz:
            assert list(npz.files) == ["run_id", "plotfile", "receptor"]
