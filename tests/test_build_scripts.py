"""The EPA build scripts: where binaries land and the build record they print.

``scripts/build_aermod.sh``, ``build_bpip.sh``, ``build_aersurface.sh`` and
``build_aerscreen.sh`` compile EPA's Fortran. Two things about them are
pinned here:

* ``BIN_DIR`` overrides the output directory (default ``<repo>/bin``), so a
  second build of the same source (a diagnostic variant, another compiler)
  can be made without overwriting the checkout's binaries. A relative
  ``BIN_DIR`` is taken from the directory the script is run in, even though
  the scripts ``cd`` into scratch directories before linking.
* Each binary gets a build record on stdout: its SHA-256, the compiler
  version, and the compile and link flags that were actually passed to the
  compiler (AERMET and the AERSURFACE link do not use ``$FFLAGS``).

The scripts run for real, but against a stand-in compiler: a shell script
that answers ``--version``, logs every invocation, writes empty objects for
``-c`` and a small executable for ``-o``. The executable prints AERMOD's
usage banner under the same rule as ``aermod.f`` (only for one argument, or
three or more), with the version the test sets in ``FAKE_AERMOD_VERSN``
(default 26135; empty means no banner and exit 3), and writes the
``aerscreen.log`` lines ``build_aerscreen.sh``'s smoke test looks for. That keeps these tests to a
second or two with no gfortran and no network; the real compilers run in the
``real_*.yml`` workflows, which call the same scripts.

The scripts are copied into a scratch "repository" so the default
``<repo>/bin`` is a temporary directory, never the checkout's ``bin/``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("unzip") is None,
    reason="the build scripts need bash and unzip",
)

FAKE_VERSION = "GNU Fortran (stand-in) 99.1.0"
AERMOD_DEFAULT_FLAGS = "-O2 -fbounds-check -Wuninitialized"

FAKE_FC = f"""#!/usr/bin/env bash
if [ "${{1:-}}" = "--version" ]; then echo "{FAKE_VERSION}"; exit 0; fi
echo "$*" >> "$FAKEFC_LOG"
out=""; compile=0; srcs=()
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -c) compile=1; shift ;;
        -*) shift ;;
        *)  srcs+=("$1"); shift ;;
    esac
done
if [ "$compile" = 1 ]; then
    for s in "${{srcs[@]}}"; do b="$(basename "$s")"; : > "${{b%.*}}.o"; done
    exit 0
fi
{{
    printf '#!/bin/sh\\n# linked from: %s\\n' "${{srcs[*]}}"
    printf "VERSN='%s'\\n" "${{FAKE_AERMOD_VERSN-26135}}"
    cat <<'EOF'
# aermod.f calls USAGE for one argument, or three or more; with none or two
# it goes to the run. VERSN is CHARACTER*6, hence the padding.
[ -n "$VERSN" ] || exit 3
if [ $# -eq 1 ] || [ $# -ge 3 ]; then
    printf ' Usage: AERMOD %-6s takes either no or one or two parameters.\\n' "$VERSN"
fi
printf 'AERSCREEN 21112\\n Stopping AERSCREEN by user action\\n' > aerscreen.log
EOF
}} > "$out"
chmod +x "$out"
"""


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def _zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return path


def _aerscreen_preimage() -> str:
    """Source text the AERSCREEN gfortran patch applies to.

    Built from the patch's own context and removed lines, so the script's
    ``patch --forward --batch`` step runs for real (at an offset) without
    EPA's 8000-line source in the test tree. ``versn`` makes the version
    detection find 21112, as it does in EPA's file.
    """
    text = (SCRIPTS / "patches" / "aerscreen_21112.patch").read_text()
    lines = ["      versn = '21112'"]
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line[:1] in (" ", "-"):
            lines.append(line[1:])
    return "\n".join(lines) + "\n"


def _module_list(script: str, var: str) -> list[str]:
    body = (SCRIPTS / script).read_text()
    match = re.search(rf"{var}=\((.*?)\)", body, re.DOTALL)
    assert match, f"{var} not found in {script}"
    return match.group(1).split()


class Sandbox:
    """A scratch repository holding copies of the build scripts."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.repo = tmp_path / "repo"
        shutil.copytree(
            SCRIPTS,
            self.repo / "scripts",
            ignore=shutil.ignore_patterns("oracle_decks", "*.py", "__pycache__"),
        )
        self.fc = tmp_path / "fakefc"
        self.fc.write_text(FAKE_FC)
        self.fc.chmod(0o755)
        self.log = tmp_path / "fakefc.log"
        self.inputs = tmp_path / "inputs"
        self.inputs.mkdir()

    # -- per-script inputs -------------------------------------------------

    def env_for(self, script: str) -> dict[str, str]:
        if script == "build_aermod.sh":
            env = {}
            for name, marker in (("AERMOD", "aermod.f"), ("AERMAP", "aermap.f"), ("AERMET", "aermet.f90")):
                src = self.inputs / name.lower()
                src.mkdir(exist_ok=True)
                (src / marker).write_text("      END\n")
                env[f"{name}_SRC_DIR"] = str(src)
            (self.inputs / "aermod" / "modules.f").write_text("      END\n")
            return env
        if script == "build_bpip.sh":
            return {"BPIP_ZIP": str(_zip(self.inputs / "bpip.zip", {"bpipprime/Bpipprm.for": "      END\r\n\x1a"}))}
        if script == "build_aersurface.sh":
            names = [*_module_list(script, "MODULES"), "aersurface"]
            files = {f"aersurface_source/{n}.f": "      END\n" for n in names}
            return {"AERSURFACE_ZIP": str(_zip(self.inputs / "aersurface.zip", files))}
        if script == "build_aerscreen.sh":
            return {
                "AERSCREEN_ZIP": str(_zip(self.inputs / "aerscreen.zip", {"AERSCREEN.FOR": _aerscreen_preimage()})),
                "MAKEMET_ZIP": str(_zip(self.inputs / "makemet.zip", {"MAKEMET.FOR": "      END\n"})),
            }
        raise AssertionError(script)

    def run(self, script: str, *args: str, cwd: Path | None = None, ok: bool = True, **overrides: str | None):
        env = {k: v for k, v in os.environ.items() if k not in _SCRIPT_ENV}
        env.update(self.env_for(script))
        env.update(FC=str(self.fc), FAKEFC_LOG=str(self.log))
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        proc = subprocess.run(
            ["bash", str(self.repo / "scripts" / script), *args],
            cwd=cwd or self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if ok:
            assert proc.returncode == 0, f"{script} failed:\n{proc.stdout}\n{proc.stderr}"
        return proc

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines()


# Variables the scripts read; cleared so the caller's shell cannot leak in.
_SCRIPT_ENV = {
    "BIN_DIR", "AERMOD_EXE_NAME", "FC", "FFLAGS", "FAKE_AERMOD_VERSN",
    "AERMOD_SRC_DIR", "AERMAP_SRC_DIR", "AERMET_SRC_DIR", "AERMOD_ZIP", "AERMAP_ZIP", "AERMET_ZIP",
    "BPIP_ZIP", "AERSURFACE_ZIP", "AERSCREEN_ZIP", "MAKEMET_ZIP",
}  # fmt: skip


def build_records(stdout: str) -> dict[str, dict[str, str]]:
    """Parse the ``Build record: <name>`` blocks a build prints."""
    records: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in stdout.splitlines():
        head = re.match(r"\s*Build record: (\S+)\s*$", line)
        if head:
            current = records.setdefault(head.group(1), {})
            continue
        field = re.match(r"\s{4}(\w+):\s+(.*?)\s*$", line)
        if current is not None and field:
            current[field.group(1)] = field.group(2)
        else:
            current = None
    return records


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# script, arguments, binaries it produces
SCRIPT_CASES = [
    ("build_aermod.sh", ("aermod",), ("aermod",)),
    ("build_aermod.sh", ("all",), ("aermod", "aermap", "aermet")),
    ("build_bpip.sh", (), ("bpipprm",)),
    ("build_aersurface.sh", (), ("aersurface",)),
    ("build_aerscreen.sh", (), ("aerscreen", "makemet")),
]
CASE_IDS = [f"{s.removesuffix('.sh')}-{'-'.join(a) or 'default'}" for s, a, _ in SCRIPT_CASES]


@dataclass
class Build:
    box: Sandbox
    out: Path
    binaries: tuple[str, ...]
    stdout: str

    @property
    def records(self) -> dict[str, dict[str, str]]:
        return build_records(self.stdout)


@pytest.fixture
def box(tmp_path):
    return Sandbox(tmp_path)


@pytest.fixture(scope="module")
def overridden(tmp_path_factory) -> dict[str, Build]:
    """Each script case run once with an absolute BIN_DIR, shared by the tests."""
    builds = {}
    for case_id, (script, args, binaries) in zip(CASE_IDS, SCRIPT_CASES):
        box = Sandbox(tmp_path_factory.mktemp(case_id))
        out = box.root / "scratch" / "bin"
        proc = box.run(script, *args, BIN_DIR=str(out))
        builds[case_id] = Build(box, out, binaries, proc.stdout)
    return builds


# ---------------------------------------------------------------------------
# BIN_DIR
# ---------------------------------------------------------------------------


class TestBinDir:
    @pytest.mark.parametrize(("script", "args", "binaries"), SCRIPT_CASES, ids=CASE_IDS)
    def test_default_is_the_repositorys_bin(self, box, script, args, binaries):
        box.run(script, *args)
        for name in binaries:
            assert (box.repo / "bin" / name).is_file()

    def test_empty_bin_dir_means_the_default(self, box):
        box.run("build_aermod.sh", "aermod", BIN_DIR="")
        assert (box.repo / "bin" / "aermod").is_file()

    @pytest.mark.parametrize("case", CASE_IDS)
    def test_override_puts_every_binary_there_and_none_in_bin(self, overridden, case):
        build = overridden[case]
        for name in build.binaries:
            assert (build.out / name).is_file(), f"{name} not in BIN_DIR"
            assert not (build.box.repo / "bin" / name).exists(), f"{name} also written to <repo>/bin"

    @pytest.mark.parametrize("case", CASE_IDS)
    def test_override_is_reported(self, overridden, case):
        build = overridden[case]
        assert f"Output:   {build.out.resolve()}" in build.stdout

    @pytest.mark.parametrize(("script", "args", "binaries"), SCRIPT_CASES, ids=CASE_IDS)
    def test_relative_override_is_taken_from_the_working_directory(self, box, script, args, binaries):
        # The scripts cd into scratch directories before linking; the
        # relative path must still mean the directory they were run from.
        work = box.root / "work"
        work.mkdir()
        box.run(script, *args, cwd=work, BIN_DIR="rel/bin")
        for name in binaries:
            assert (work / "rel" / "bin" / name).is_file()


# ---------------------------------------------------------------------------
# Build record
# ---------------------------------------------------------------------------


class TestBuildRecord:
    @pytest.mark.parametrize("case", CASE_IDS)
    def test_every_binary_gets_its_sha256_and_compiler(self, overridden, case):
        build = overridden[case]
        records = build.records
        assert set(records) == set(build.binaries)
        for name in build.binaries:
            rec = records[name]
            assert rec["path"] == str((build.out / name).resolve())
            assert rec["sha256"] == sha256(build.out / name)
            assert rec["compiler"] == f"{build.box.fc} ({FAKE_VERSION})"
            assert rec["compile"] and rec["link"]

    def test_aermod_record_carries_the_banner_version_and_default_flags(self, overridden):
        rec = overridden["build_aermod-aermod"].records["aermod"]
        assert rec["version"] == "26135"
        assert rec["compile"] == AERMOD_DEFAULT_FLAGS
        assert rec["link"] == AERMOD_DEFAULT_FLAGS

    def test_fflags_override_is_what_the_record_and_the_compiler_see(self, box):
        rec = build_records(box.run("build_aermod.sh", "aermod", FFLAGS="-O0 -g").stdout)["aermod"]
        assert rec["compile"] == rec["link"] == "-O0 -g"
        calls = box.calls()
        assert calls and all(call.startswith("-c -O0 -g ") for call in calls[:-1])
        assert calls[-1].split()[:4] == ["-o", str(box.repo / "bin" / "aermod"), "-O0", "-g"]

    def test_aermet_reports_its_own_flags_not_fflags(self, box):
        # AERMET ignores FFLAGS; a record that echoed FFLAGS would be wrong.
        rec = build_records(box.run("build_aermod.sh", "aermet", FFLAGS="-O0 -g").stdout)["aermet"]
        assert "version" not in rec
        assert rec["compile"] == "-O2 -std=f2008 -ffree-form"
        assert rec["link"] == "-O2"
        compiles = [c for c in box.calls() if c.startswith("-c ")]
        links = [c for c in box.calls() if not c.startswith("-c ")]
        assert compiles and all(c.startswith("-c -O2 -std=f2008 -ffree-form ") for c in compiles)
        assert len(links) == 1 and links[0].startswith("-O2 -o ")

    def test_aersurface_link_flags_are_reported_separately(self, overridden):
        build = overridden["build_aersurface-default"]
        rec = build.records["aersurface"]
        assert rec["compile"] == "-fbounds-check -Wuninitialized -O2 -std=legacy"
        assert rec["link"] == "-O2"
        link = [c for c in build.box.calls() if not c.startswith("-c ")]
        assert len(link) == 1 and re.match(r"-o \S+/aersurface -O2 ", link[0])

    def test_distinct_binaries_get_distinct_hashes(self, overridden):
        records = overridden["build_aermod-all"].records
        assert len({rec["sha256"] for rec in records.values()}) == 3


class TestAermodVersion:
    """The version line comes from the built binary's banner, whatever it says."""

    @pytest.mark.parametrize("versn", ["24142", "D26135"])
    def test_version_is_read_from_the_banner(self, box, versn):
        # D26135 is EPA's draft form (VERSN is six characters "to
        # accommodate leading qualifier character", modules.f); the record
        # must keep the qualifier, and must not be a hard-coded 26135.
        rec = build_records(box.run("build_aermod.sh", "aermod", FAKE_AERMOD_VERSN=versn).stdout)["aermod"]
        assert rec["version"] == versn

    def test_a_missing_banner_is_reported_not_dropped(self, box):
        proc = box.run("build_aermod.sh", "aermod", FAKE_AERMOD_VERSN="")
        assert build_records(proc.stdout)["aermod"]["version"] == "unknown (banner not found)"
        assert "WARNING:" in proc.stderr and "no version banner" in proc.stderr

    def test_the_stand_in_prints_its_banner_when_aermod_does(self, box, tmp_path):
        # The probe passes exactly one argument because aermod.f prints the
        # banner for one argument or three or more, and not for none or two.
        # A probe that ran the binary with no arguments would find nothing.
        box.run("build_aermod.sh", "aermod")
        exe = box.repo / "bin" / "aermod"
        banner = {n: "Usage: AERMOD 26135  takes" in _run_in(tmp_path, exe, n) for n in range(4)}
        assert banner == {0: False, 1: True, 2: False, 3: True}


def _run_in(tmp_path: Path, exe: str | Path, nargs: int) -> str:
    work = tmp_path / f"probe{nargs}"
    work.mkdir(exist_ok=True)
    # Two arguments are an input and an output file name; other counts
    # start with --help, as the build script's probe does.
    args = ["missing.inp", "missing.out"] if nargs == 2 else ["--help", "b.out", "c"][:nargs]
    proc = subprocess.run(
        [str(exe), *args], cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False
    )
    return proc.stdout + proc.stderr


@pytest.mark.skipif(shutil.which("aermod") is None, reason="needs a real aermod on PATH")
def test_real_aermod_prints_its_banner_under_the_same_rule(tmp_path):
    """The stand-in's argument rule, checked against the real binary."""
    exe = shutil.which("aermod")
    banner = {n: bool(re.search(r"Usage: AERMOD +[A-Z]?\d{5}", _run_in(tmp_path, exe, n))) for n in range(4)}
    assert banner == {0: False, 1: True, 2: False, 3: True}


class TestExeNameAndReplacing:
    def test_exe_name_puts_a_variant_beside_the_regulatory_binary(self, box):
        first = box.run("build_aermod.sh", "aermod")
        regulatory = box.repo / "bin" / "aermod"
        before = sha256(regulatory)
        proc = box.run("build_aermod.sh", "aermod", AERMOD_EXE_NAME="aermod_diag")
        diag = box.repo / "bin" / "aermod_diag"
        assert diag.is_file() and sha256(regulatory) == before
        assert build_records(proc.stdout)["aermod_diag"]["sha256"] == sha256(diag)
        assert "Replacing" not in proc.stdout and "Replacing" not in first.stdout
        assert f'executable_path="{diag}"' in proc.stdout

    @pytest.mark.parametrize("name", ["sub/aermod", "..", "."])
    def test_exe_name_must_be_a_file_name(self, box, name):
        proc = box.run("build_aermod.sh", "aermod", ok=False, AERMOD_EXE_NAME=name)
        assert proc.returncode != 0
        assert "AERMOD_EXE_NAME must be a file name" in proc.stderr
        assert not (box.repo / "bin" / "aermod").exists()

    @pytest.mark.parametrize(("script", "args", "binaries"), SCRIPT_CASES, ids=CASE_IDS)
    def test_a_rebuild_says_what_it_replaces(self, box, script, args, binaries):
        box.run(script, *args)
        # Make each existing binary distinct from what the rebuild writes,
        # so the hash quoted can only be the old file's, taken before the link.
        old = {}
        for name in binaries:
            (box.repo / "bin" / name).write_bytes(f"older {name}\n".encode())
            old[name] = sha256(box.repo / "bin" / name)
        stdout = box.run(script, *args).stdout
        for name in binaries:
            assert f"Replacing {box.repo / 'bin' / name} (sha256 was {old[name]})" in stdout


class TestNextStepHint:
    def test_default_build_points_at_make_test_binaries(self, box):
        assert "Then:         make test-binaries" in box.run("build_aermod.sh", "aermod").stdout

    def test_other_bin_dir_does_not(self, overridden):
        # make test-binaries tests ./bin; after a BIN_DIR build it would
        # run the suite against an older binary or fail to find one.
        stdout = overridden["build_aermod-aermod"].stdout
        out = overridden["build_aermod-aermod"].out.resolve()
        assert "Then:         make test-binaries" not in stdout
        assert f'PATH="{out}:$PATH" python -m pytest' in stdout


class TestParser:
    """build_records must not read fields from outside a record block."""

    def test_stops_at_the_first_line_that_is_not_a_field(self):
        text = "  Build record: x\n    sha256:   ab\n  AERMOD build successful!\n    link:  stray\n"
        assert build_records(text) == {"x": {"sha256": "ab"}}
