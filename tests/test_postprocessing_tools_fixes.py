"""Small fixes in receptors, ensemble and the CLI (H-5, H-6, H-9)."""

import copy
import platform

import pytest

from pyaermod import cli
from pyaermod.receptors import CartesianGrid


class TestFromBounds:
    def test_float_truncation_does_not_drop_the_last_row(self):
        g = CartesianGrid.from_bounds(0, 0.3, 0, 0.3, spacing=0.1)
        assert (g.x_num, g.y_num) == (4, 4)

    def test_whole_multiples_are_unchanged(self):
        g = CartesianGrid.from_bounds(0, 1000, 0, 900, spacing=100)
        assert (g.x_num, g.y_num) == (11, 10)

    def test_a_range_that_is_not_a_multiple_stops_at_or_before_the_bound(self):
        g = CartesianGrid.from_bounds(0, 1000, 0, 950, spacing=100)
        assert g.y_num == 10 and g.y_values()[-1] == 900

    @pytest.mark.parametrize("spacing", [0, -5])
    def test_a_spacing_that_is_not_positive_is_refused(self, spacing):
        with pytest.raises(ValueError, match="spacing"):
            CartesianGrid.from_bounds(0, 10, 0, 10, spacing=spacing)

    def test_reversed_bounds_are_refused(self):
        with pytest.raises(ValueError, match="reversed"):
            CartesianGrid.from_bounds(10, 0, 0, 10)


@pytest.mark.skipif(platform.system() == "Windows", reason="the replaying fake aermod is a bash script")
def test_run_design_gives_build_fn_a_private_copy_of_the_factors(tmp_path):
    from tests import test_ensemble as te

    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "aermod"
    exe.write_text(te._REPLAY.format(recordings=te.FIXTURES, bindir=bindir))
    exe.chmod(0o755)

    def build(factors):
        factors["tags"].append("mutated")
        return te.design.build(factors)

    rows = [dict(te.design.ROWS[0], tags=["a"])]
    before = copy.deepcopy(rows)
    result = te.run_design(rows, build, tmp_path / "root", n_workers=1, executable=exe)
    assert rows == before
    (run,) = result.runs.values()
    assert run.factors["tags"] == ["a"]


class TestCliErrors:
    def test_a_missing_deck_is_a_message_not_a_traceback(self, tmp_path, capsys):
        assert cli.main(["validate", str(tmp_path / "missing.inp")]) == 2
        assert "pyaermod: error:" in capsys.readouterr().err

    def test_an_unknown_profile_is_printed_without_the_keyerror_quotes(self, tmp_path, capsys):
        inp = tmp_path / "a.inp"
        inp.write_text("")
        assert cli.main(["profile", str(inp), "--profile", "bogus"]) == 2
        err = capsys.readouterr().err
        assert "Unknown profile" in err or "pyaermod: error:" in err
        assert "KeyError" not in err
