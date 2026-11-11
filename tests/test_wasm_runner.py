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


# ---------------------------------------------------------------------------
# AERMODRunner under Pyodide
# ---------------------------------------------------------------------------

def test_runner_finds_and_runs_the_webassembly_build(tmp_path, fake_pyodide, monkeypatch):
    js = _make_build(tmp_path / "build")
    monkeypatch.setenv(wasm_runner.ENV_VAR, str(js))
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
