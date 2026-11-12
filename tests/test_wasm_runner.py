"""Tests for pyaermod.wasm_runner: the WebAssembly AERMOD under Pyodide.

Pyodide itself is not here, so these stand in fakes for the three modules
the runner imports from it (pyodide_js, pyodide.code, pyodide.ffi). The real
thing runs in .github/workflows/wasm_aermod.yml.
"""

import io
import shutil
import sys
import types
from pathlib import Path

import pytest

from pyaermod import wasm_runner
from pyaermod.runner import AERMODRunner

SUCCESS_OUT = Path(__file__).parent / "fixtures" / "runner" / "success" / "aermod.out"


def _make_build(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "aermod.js").write_text("// glue\n", encoding="utf-8")
    (directory / "aermod.wasm").write_bytes(b"\0asm")
    return directory / "aermod.js"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(wasm_runner.ENV_VAR, raising=False)
    monkeypatch.setattr(wasm_runner, "_cache", {})
    monkeypatch.setattr(wasm_runner, "_loader", None)


# ---------------------------------------------------------------------------
# find_wasm_aermod
# ---------------------------------------------------------------------------

def test_find_accepts_the_directory(tmp_path):
    js = _make_build(tmp_path / "build")
    assert wasm_runner.find_wasm_aermod(tmp_path / "build") == js


def test_find_accepts_the_glue_file(tmp_path):
    js = _make_build(tmp_path / "build")
    assert wasm_runner.find_wasm_aermod(js) == js


def test_find_uses_the_environment_variable(tmp_path, monkeypatch):
    js = _make_build(tmp_path / "build")
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(tmp_path / "build"))
    assert wasm_runner.find_wasm_aermod() == js


def test_find_uses_the_installed_package(tmp_path, monkeypatch):
    package = tmp_path / "site" / wasm_runner.WASM_PACKAGE
    js = _make_build(package)
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    assert wasm_runner.find_wasm_aermod() == js


def test_find_needs_the_wasm_beside_the_glue(tmp_path):
    js = _make_build(tmp_path / "build")
    js.with_suffix(".wasm").unlink()
    with pytest.raises(wasm_runner.WasmAERMODNotFound, match="the path given"):
        wasm_runner.find_wasm_aermod(js)


def test_find_says_where_to_get_a_build(monkeypatch):
    monkeypatch.setattr(wasm_runner, "find_spec", lambda name: None)
    with pytest.raises(wasm_runner.WasmAERMODNotFound) as info:
        wasm_runner.find_wasm_aermod()
    message = str(info.value)
    assert wasm_runner.ENV_VAR in message
    assert "%pip install aermod_wasm" in message
    assert isinstance(info.value, FileNotFoundError)


@pytest.mark.parametrize("name, expected", [
    ("aermod.js", True), ("AERMOD.JS", True), ("aermod", False), ("aermod.exe", False),
])
def test_is_wasm_executable(name, expected):
    assert wasm_runner.is_wasm_executable(name) is expected


def test_run_refuses_outside_pyodide(tmp_path, monkeypatch):
    monkeypatch.setattr(wasm_runner, "IS_EMSCRIPTEN", False)
    with pytest.raises(RuntimeError, match="only under Pyodide"):
        wasm_runner.run(tmp_path / "aermod.js", tmp_path)


# ---------------------------------------------------------------------------
# run(), with Pyodide faked
# ---------------------------------------------------------------------------

class _FakeFS:
    """The parts of Emscripten's FS API that the runner reads."""

    DIR = 0o040000

    def __init__(self, top):
        self.top = top

    def readdir(self, path):
        assert path == "/"
        return [".", "..", *self.top]

    def stat(self, path):
        mode = self.DIR if path.strip("/") != "notadir" else 0o100644
        return types.SimpleNamespace(mode=mode)

    def isDir(self, mode):
        return bool(mode & self.DIR)


class _Proxy:
    def __init__(self, fn):
        self.fn = fn
        self.destroyed = False

    def __call__(self, *args):
        return self.fn(*args)

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def fake_pyodide(monkeypatch):
    """Install fake Pyodide modules; return the record of loader calls."""
    calls = []
    proxies = []

    def loader(glue, wasm, pyfs, mounts, cwd, out, err):
        calls.append({"glue": glue, "wasm": wasm, "mounts": list(mounts), "cwd": cwd})
        out("AERMOD says hello")
        err("and warns")
        # What AERMOD would write in its working directory.
        shutil.copy(SUCCESS_OUT, Path(cwd) / "aermod.out")
        return loader.exit_code
    loader.exit_code = 0

    def create_proxy(fn):
        proxy = _Proxy(fn)
        proxies.append(proxy)
        return proxy

    code = types.ModuleType("pyodide.code")
    code.run_js = lambda source: loader
    ffi = types.ModuleType("pyodide.ffi")
    ffi.create_proxy = create_proxy
    ffi.to_js = lambda value: value
    pyodide = types.ModuleType("pyodide")
    pyodide.code = code
    pyodide.ffi = ffi
    pyodide_js = types.ModuleType("pyodide_js")
    pyodide_js.FS = _FakeFS(["home", "tmp", "dev", "proc", "lib", "drive", "notadir"])

    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.code", code)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    monkeypatch.setitem(sys.modules, "pyodide_js", pyodide_js)
    monkeypatch.setattr(wasm_runner, "IS_EMSCRIPTEN", True)
    return types.SimpleNamespace(calls=calls, proxies=proxies, loader=loader)


def test_run_loads_the_build_and_mounts_pyodides_filesystem(tmp_path, fake_pyodide):
    js = _make_build(tmp_path / "build")
    work = tmp_path / "work"
    work.mkdir()
    out, err = io.StringIO(), io.StringIO()

    code = wasm_runner.run(js, work, stdout=out, stderr=err)

    assert code == 0
    (call,) = fake_pyodide.calls
    assert call["glue"] == "// glue\n"
    assert call["wasm"] == b"\0asm"
    assert call["cwd"] == str(work.resolve())
    top = f"/{work.resolve().parts[1]}"
    # Device, process and Python's own directories stay out; files are not
    # directories; the working directory's top level is always mounted.
    assert set(call["mounts"]) == {"/home", "/tmp", "/drive", top}
    assert out.getvalue() == "AERMOD says hello\n"
    assert err.getvalue() == "and warns\n"
    assert all(p.destroyed for p in fake_pyodide.proxies)


def test_run_reads_the_build_once(tmp_path, fake_pyodide):
    js = _make_build(tmp_path / "build")
    wasm_runner.run(js, tmp_path, stdout=io.StringIO(), stderr=io.StringIO())
    js.write_text("// changed\n", encoding="utf-8")
    wasm_runner.run(js, tmp_path, stdout=io.StringIO(), stderr=io.StringIO())
    assert [c["glue"] for c in fake_pyodide.calls] == ["// glue\n", "// glue\n"]


def test_run_writes_to_pythons_streams_by_default(tmp_path, fake_pyodide, capsys):
    js = _make_build(tmp_path / "build")
    wasm_runner.run(js, tmp_path)
    captured = capsys.readouterr()
    assert "AERMOD says hello" in captured.out
    assert "and warns" in captured.err


def test_run_returns_aermods_exit_status(tmp_path, fake_pyodide):
    js = _make_build(tmp_path / "build")
    fake_pyodide.loader.exit_code = 2
    assert wasm_runner.run(js, tmp_path, stdout=io.StringIO(), stderr=io.StringIO()) == 2


@pytest.mark.parametrize("exit_code, kept", [(0, False), (2, True)])
def test_run_deletes_aermods_scratch_files_when_aermod_ends(tmp_path, fake_pyodide,
                                                            exit_code, kept):
    """EPA's AERMOD deletes ERRMSG.TMP and EVENT.TMP as it ends; Flang's leaves them."""
    js = _make_build(tmp_path / "build")
    work = tmp_path / "work"
    work.mkdir()

    def leaves_scratch(glue, wasm, pyfs, mounts, cwd, out, err):
        for name in ("ERRMSG.TMP", "EVENT.TMP"):
            (Path(cwd) / name).write_text("scratch\n", encoding="utf-8")
        return exit_code
    sys.modules["pyodide.code"].run_js = lambda source: leaves_scratch

    wasm_runner.run(js, work, stdout=io.StringIO(), stderr=io.StringIO())
    # A run that crashed keeps them, as EPA's executable would: AERMOD
    # never reached its last statement.
    assert (work / "ERRMSG.TMP").exists() is kept
    assert (work / "EVENT.TMP").exists() is kept


def test_remove_scratch_files_ignores_files_not_there(tmp_path):
    (tmp_path / "EVENT.TMP").write_text("x", encoding="utf-8")
    assert wasm_runner.remove_scratch_files(tmp_path) == [tmp_path / "EVENT.TMP"]
    assert wasm_runner.remove_scratch_files(tmp_path) == []


# ---------------------------------------------------------------------------
# AERMODRunner under Pyodide
# ---------------------------------------------------------------------------

def test_runner_finds_and_runs_the_webassembly_build(tmp_path, fake_pyodide, monkeypatch):
    js = _make_build(tmp_path / "build")
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(js))
    # Pyodide's fcntl has no flock; the runner must not need it there.
    monkeypatch.setitem(sys.modules, "fcntl", types.ModuleType("fcntl"))
    deck = tmp_path / "work" / "case.inp"
    deck.parent.mkdir()
    deck.write_text("CO STARTING\n", encoding="utf-8")

    runner = AERMODRunner()
    assert runner.executable == js
    result = runner.run(deck)

    assert result.success, result.error_message
    assert result.return_code == 0
    assert Path(result.output_file) == deck.with_suffix(".out")
    assert "AERMOD says hello" in result.stdout
    assert not (deck.parent / "aermod.inp").exists()


def test_runner_reports_a_missing_build(fake_pyodide, monkeypatch):
    monkeypatch.setattr(wasm_runner, "find_spec", lambda name: None)
    with pytest.raises(wasm_runner.WasmAERMODNotFound):
        AERMODRunner()


def test_runner_has_no_background_runs_under_pyodide(tmp_path, fake_pyodide, monkeypatch):
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(_make_build(tmp_path / "build")))
    with pytest.raises(NotImplementedError, match="run\\(\\)"):
        AERMODRunner().start(tmp_path / "case.inp")


# ---------------------------------------------------------------------------
# Review fixes: an explicit path is final; a trap keeps AERMOD's .out
# ---------------------------------------------------------------------------

def test_find_does_not_fall_back_when_the_path_given_holds_no_build(tmp_path, monkeypatch):
    """A typo in an explicit path must not quietly run another build."""
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(_make_build(tmp_path / "other")))
    with pytest.raises(wasm_runner.WasmAERMODNotFound, match="the path given"):
        wasm_runner.find_wasm_aermod(tmp_path / "missing" / "aermod.js")


def test_a_trap_keeps_aermods_partial_output(tmp_path, fake_pyodide, monkeypatch):
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(_make_build(tmp_path / "build")))
    monkeypatch.setitem(sys.modules, "fcntl", types.ModuleType("fcntl"))

    def trapping_loader(glue, wasm, pyfs, mounts, cwd, out, err):
        (Path(cwd) / "aermod.out").write_text("partial output before the trap\n")
        raise RuntimeError("RuntimeError: unreachable")

    sys.modules["pyodide.code"].run_js = lambda source: trapping_loader
    deck = tmp_path / "work" / "case.inp"
    deck.parent.mkdir()
    deck.write_text("CO STARTING\n", encoding="utf-8")

    result = AERMODRunner().run(deck)

    assert not result.success
    assert "unreachable" in (result.error_message or "")
    assert result.output_file and Path(result.output_file) == deck.with_suffix(".out")
    assert deck.with_suffix(".out").read_text().startswith("partial output")


# ---------------------------------------------------------------------------
# Met files without a final line terminator
# ---------------------------------------------------------------------------
# AERMOD BACKSPACEs over the surface file every hour (metext.f). Flang's
# runtime cannot backspace over a last record with no terminator and aborts;
# gfortran reads it. So the runner ends both met files with a newline.

_DECK = """CO STARTING
CO FINISHED
ME STARTING
** SURFFILE  commented.sfc
   SURFFILE  {sfc}
   proffile  {pfl}  FREE
ME FINISHED
"""


def _met_case(tmp_path, sfc="site.sfc", pfl="site.pfl", sfc_text=b"1\n2", pfl_text=b"1\n2"):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "aermod.inp").write_text(_DECK.format(sfc=sfc, pfl=pfl), encoding="utf-8")
    sfc_path = work / sfc.strip('"')
    pfl_path = work / pfl.strip('"')
    sfc_path.parent.mkdir(parents=True, exist_ok=True)
    sfc_path.write_bytes(sfc_text)
    pfl_path.write_bytes(pfl_text)
    return work, sfc_path, pfl_path


def test_run_ends_both_met_files_with_a_newline(tmp_path, fake_pyodide):
    js = _make_build(tmp_path / "build")
    work, sfc, pfl = _met_case(tmp_path)
    wasm_runner.run(js, work, stdout=io.StringIO(), stderr=io.StringIO())
    assert sfc.read_bytes() == b"1\n2\n"
    assert pfl.read_bytes() == b"1\n2\n"


@pytest.mark.parametrize("ending", [b"2\n", b"2\r\n"])
def test_met_files_that_end_a_line_are_left_alone(tmp_path, ending):
    work, sfc, _ = _met_case(tmp_path, sfc_text=b"1\n" + ending)
    wasm_runner.terminate_met_files(work)
    assert sfc.read_bytes() == b"1\n" + ending


def test_met_files_at_quoted_and_relative_paths(tmp_path):
    work, sfc, pfl = _met_case(tmp_path, sfc='"met dir/a site.sfc"', pfl="../other.pfl")
    assert wasm_runner.terminate_met_files(work) == [sfc.resolve(), pfl.resolve()]
    assert sfc.read_bytes().endswith(b"\n") and pfl.read_bytes().endswith(b"\n")


def test_missing_or_empty_met_files_and_no_deck_are_not_an_error(tmp_path):
    work, sfc, pfl = _met_case(tmp_path, sfc_text=b"")
    pfl.unlink()
    assert wasm_runner.terminate_met_files(work) == []
    assert sfc.read_bytes() == b""
    assert wasm_runner.terminate_met_files(tmp_path / "nowhere") == []
