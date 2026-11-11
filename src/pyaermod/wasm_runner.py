"""
Run AERMOD compiled to WebAssembly, inside Pyodide.

pyaermod's in-browser build (JupyterLite on the documentation site) has no
AERMOD executable to start: a browser cannot run one. It runs EPA's AERMOD
compiled to WebAssembly instead (``scripts/build_aermod_wasm.sh``): a glue
script, ``aermod.js``, and the model, ``aermod.wasm``.

:class:`~pyaermod.runner.AERMODRunner` uses this module when Python runs
under Pyodide (``sys.platform == "emscripten"``) and its executable is an
``aermod.js``. Everything else about a run stays the same: the runner links
the deck to ``aermod.inp``, AERMOD reads and writes files in the working
directory, and the runner renames and parses its outputs.

AERMOD's WebAssembly module has a filesystem of its own. Each run mounts
Pyodide's filesystem into it (Emscripten's PROXYFS) at the same paths, so the
deck, its met files at relative or absolute paths, and the files AERMOD
writes are all the ones Python sees.

Each run loads a fresh instance of the module: AERMOD's Fortran keeps state
in module variables that nothing resets between runs. The glue and the wasm
bytes are read once and kept.

The build is not EPA's executable. Results can differ from EPA's in the last
digits; the parity check in ``.github/workflows/wasm_aermod.yml`` measures
how much. It is for teaching and exploration, not for regulatory use.
"""

import os
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Dict, List, Optional, TextIO, Tuple, Union

#: True when Python runs under Pyodide (in a browser, or in Node).
IS_EMSCRIPTEN = sys.platform == "emscripten"

#: Environment variable naming the directory that holds aermod.js and
#: aermod.wasm, or the aermod.js file itself.
ENV_VAR = "PYAERMOD_AERMOD_WASM"

#: The package the JupyterLite site installs to provide the build.
WASM_PACKAGE = "aermod_wasm"

# Top-level directories of Pyodide's filesystem that are never mounted into
# AERMOD's: device and process files, and Python's own installation.
_NOT_MOUNTED = frozenset({"dev", "proc", "sys", "lib", "bin", "usr", "etc"})

# Evaluated once; called with the glue source, the wasm bytes, Pyodide's FS,
# the directories to mount, the working directory and two line callbacks.
# Returns AERMOD's exit status.
_LOADER_JS = r"""
(function (glue, wasmBinary, pyFS, mounts, cwd, out, err) {
  let ready = false;
  let exitCode = null;
  const Module = {
    noInitialRun: true,
    wasmBinary: wasmBinary,
    print: out,
    printErr: err,
    onRuntimeInitialized: () => { ready = true; },
    onExit: (code) => { exitCode = code; },
    quit: (status, toThrow) => { exitCode = status; throw toThrow; },
  };
  // Only the glue's Node code paths use these; a browser never takes them.
  const req = (typeof require === 'function') ? require : globalThis.require;
  const load = new Function('Module', 'require', '__dirname', glue + '\nreturn Module;');
  const M = load(Module, req, globalThis.__dirname || '/');
  if (!ready) {
    throw new Error('aermod.js did not initialise synchronously; it was not built ' +
                    'by scripts/build_aermod_wasm.sh');
  }
  for (const dir of mounts) {
    try { M.FS.mkdirTree(dir); } catch (e) { /* exists */ }
    M.FS.mount(M.PROXYFS, { root: dir, fs: pyFS }, dir);
  }
  M.FS.chdir(cwd);
  try {
    const ret = M.callMain([]);
    if (exitCode === null && typeof ret === 'number') exitCode = ret;
  } catch (e) {
    if (e && e.name === 'ExitStatus') { exitCode = e.status; } else { throw e; }
  }
  return exitCode === null ? 0 : exitCode;
})
"""

# (glue path) -> (glue source, wasm bytes)
_cache: Dict[str, Tuple[str, bytes]] = {}
_loader = None


class WasmAERMODNotFound(FileNotFoundError):
    """No WebAssembly build of AERMOD where pyaermod looks for one."""


def find_wasm_aermod(path: Optional[Union[str, Path]] = None) -> Path:
    """The ``aermod.js`` of a WebAssembly AERMOD build.

    Looks, in order, at ``path`` (the ``aermod.js`` file or the directory
    holding it), the directory or file named by the ``PYAERMOD_AERMOD_WASM``
    environment variable, and the ``aermod_wasm`` package that the
    JupyterLite site installs. ``aermod.wasm`` must sit beside ``aermod.js``.

    Raises:
        WasmAERMODNotFound: when none of them holds a build.
    """
    candidates: List[Tuple[str, Path]] = []
    if path is not None:
        candidates.append(("the path given", Path(path)))
    env = os.environ.get(ENV_VAR)
    if env:
        candidates.append((f"${ENV_VAR}", Path(env)))
    spec = find_spec(WASM_PACKAGE)
    if spec is not None and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            candidates.append((f"the {WASM_PACKAGE} package", Path(location)))

    looked: List[str] = []
    for source, candidate in candidates:
        js = candidate / "aermod.js" if candidate.is_dir() else candidate
        if js.name.endswith(".js") and js.is_file() and js.with_suffix(".wasm").is_file():
            return js
        looked.append(f"{source} ({candidate})")

    where = "; ".join(looked) if looked else (
        f"no path given, ${ENV_VAR} is not set and the {WASM_PACKAGE} package is not installed"
    )
    raise WasmAERMODNotFound(
        "No WebAssembly build of AERMOD (aermod.js beside aermod.wasm) was found: "
        f"{where}. In JupyterLite, run `%pip install {WASM_PACKAGE}`; elsewhere, build "
        "one with scripts/build_aermod_wasm.sh."
    )


def is_wasm_executable(executable: Union[str, Path]) -> bool:
    """Whether ``executable`` is a WebAssembly build's glue, ``*.js``."""
    return Path(executable).suffix.lower() == ".js"


def _read_build(js: Path) -> Tuple[str, bytes]:
    key = str(js)
    if key not in _cache:
        _cache[key] = (js.read_text(encoding="utf-8"), js.with_suffix(".wasm").read_bytes())
    return _cache[key]


def _mount_points(pyfs, cwd: Path) -> List[str]:
    """Pyodide's top-level directories that AERMOD's filesystem mirrors."""
    names = [str(n) for n in pyfs.readdir("/")]
    mounts = [f"/{n}" for n in names if n not in (".", "..") and n not in _NOT_MOUNTED
              and pyfs.isDir(pyfs.stat(f"/{n}").mode)]
    top = f"/{cwd.parts[1]}" if len(cwd.parts) > 1 else None
    if top and top not in mounts:
        mounts.append(top)
    return sorted(mounts)


def _line_writer(stream: Optional[TextIO], fallback: TextIO) -> Callable[[str], None]:
    target = stream if stream is not None else fallback

    def write(line: str) -> None:
        target.write(f"{line}\n")
    return write


def run(executable: Union[str, Path], working_dir: Union[str, Path], *,
        stdout: Optional[TextIO] = None, stderr: Optional[TextIO] = None) -> int:
    """Run the WebAssembly AERMOD in ``working_dir`` and return its exit status.

    AERMOD reads ``working_dir/aermod.inp`` and writes its outputs there, as
    the native executable does. Its console output goes to ``stdout`` and
    ``stderr`` (Python's own when ``None``). The run blocks until AERMOD
    ends: WebAssembly cannot be interrupted, so there is no timeout.

    Raises:
        RuntimeError: outside Pyodide.
    """
    if not IS_EMSCRIPTEN:
        raise RuntimeError(
            "The WebAssembly build of AERMOD runs only under Pyodide; "
            "use the native AERMOD executable here"
        )
    global _loader
    import pyodide_js  # type: ignore[import-not-found]
    from pyodide.code import run_js  # type: ignore[import-not-found]
    from pyodide.ffi import create_proxy, to_js  # type: ignore[import-not-found]

    if _loader is None:
        _loader = run_js(_LOADER_JS)

    glue, wasm = _read_build(Path(executable))
    cwd = Path(working_dir).resolve()
    pyfs = pyodide_js.FS
    out = create_proxy(_line_writer(stdout, sys.stdout))
    err = create_proxy(_line_writer(stderr, sys.stderr))
    try:
        code = _loader(glue, to_js(wasm), pyfs, to_js(_mount_points(pyfs, cwd)),
                       str(cwd), out, err)
    finally:
        out.destroy()
        err.destroy()
    return int(code)
