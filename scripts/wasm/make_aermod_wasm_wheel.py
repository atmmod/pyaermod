"""Package a WebAssembly AERMOD build as the ``aermod_wasm`` wheel.

The JupyterLite site installs this wheel (``%pip install aermod_wasm``) so
that :func:`pyaermod.wasm_runner.find_wasm_aermod` finds the build in the
browser. The wheel holds ``aermod.js``, ``aermod.wasm`` and ``BUILD.txt``
from ``scripts/build_aermod_wasm.sh``; its version is AERMOD's.

It is written directly (a wheel is a zip file with three metadata files),
so building it needs nothing beyond the standard library.

Usage: python make_aermod_wasm_wheel.py <build dir> <output dir>
"""

import base64
import hashlib
import re
import sys
import zipfile
from pathlib import Path

NAME = "aermod_wasm"

INIT = '''"""EPA AERMOD {version}, compiled to WebAssembly for pyaermod in the browser.

An unofficial build of EPA's public-domain AERMOD source, made with LLVM
Flang and Emscripten by pyaermod's scripts/build_aermod_wasm.sh. It is for
teaching and exploration, not for regulatory modeling: use EPA's executable
for that. BUILD.txt records the compiler versions, flags and checksums.

pyaermod's AERMODRunner finds this build by itself under Pyodide.
"""

from pathlib import Path

__version__ = "{wheel_version}"
AERMOD_VERSION = "{version}"


def glue_path() -> Path:
    """The build's aermod.js; aermod.wasm sits beside it."""
    return Path(__file__).with_name("aermod.js")
'''


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def make_wheel(build: Path, out: Path) -> Path:
    build_txt = (build / "BUILD.txt").read_text(encoding="utf-8")
    match = re.search(r"AERMOD version:\s*(\d+)", build_txt)
    if not match:
        raise SystemExit(f"no 'AERMOD version: NNNNN' line in {build / 'BUILD.txt'}")
    version = match.group(1)
    wheel_version = f"{version}.0"
    dist_info = f"{NAME}-{wheel_version}.dist-info"

    files = {
        f"{NAME}/__init__.py": INIT.format(version=version, wheel_version=wheel_version).encode(),
        f"{NAME}/aermod.js": (build / "aermod.js").read_bytes(),
        f"{NAME}/aermod.wasm": (build / "aermod.wasm").read_bytes(),
        f"{NAME}/BUILD.txt": build_txt.encode(),
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\n"
            f"Name: {NAME}\n"
            f"Version: {wheel_version}\n"
            f"Summary: EPA AERMOD {version} compiled to WebAssembly, for pyaermod under Pyodide "
            "(unofficial; not for regulatory use)\n"
            "License: Public Domain (EPA AERMOD source)\n"
            "Requires-Python: >=3.11\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: pyaermod make_aermod_wasm_wheel.py\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ).encode(),
    }
    record = [_record_line(name, data) for name, data in files.items()]
    record.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode()

    out.mkdir(parents=True, exist_ok=True)
    wheel = out / f"{NAME}-{wheel_version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return wheel


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(make_wheel(Path(sys.argv[1]), Path(sys.argv[2])))
