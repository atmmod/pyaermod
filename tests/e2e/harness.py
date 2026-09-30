"""Machinery behind the GUI journeys: server, browser errors, screenshots, gaps.

The fixtures in ``conftest.py`` wire these together; journeys only see the
page objects in ``pages.py``, ``step`` and ``known_gap``.

Tiers (PLAN-gui.md, "Test strategy"):

* **T2** (default): the GUI server finds ``fake_aermod.py`` as ``aermod``
  on its ``PATH``, replaying the recording a test names with
  ``@pytest.mark.aermod_recording(...)``.
* **T3** (``PYAERMOD_E2E_REAL=1``): the server finds the real ``aermod``
  already on ``PATH``; recordings are ignored.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import site
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import expect
except ImportError:  # pragma: no cover - conftest skips collection then
    class PlaywrightTimeoutError(Exception):  # type: ignore[no-redef]
        """Stand-in so this module imports without Playwright."""

    expect = None  # type: ignore[assignment]

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
RECORDINGS = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings"
EPA_FIXTURES = REPO / "tests" / "fixtures" / "epa_official"
ARTIFACTS = REPO / "test-artifacts" / "gui"
FAKE_AERMOD = Path(__file__).with_name("fake_aermod.py")

REAL_AERMOD = os.environ.get("PYAERMOD_E2E_REAL") == "1"
TIER = "T3" if REAL_AERMOD else "T2"

# Ordinary steps get Playwright's usual patience. Steps inside a known gap
# are expected to fail, so they give up quickly to keep the suite fast.
STEP_TIMEOUT_MS = 10_000
EXPECT_TIMEOUT_MS = 5_000
GAP_TIMEOUT_MS = 1_500
SERVER_START_TIMEOUT_S = 60

TRACEBACK = "Traceback (most recent call last):"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def install_fake_aermod(bin_dir: Path) -> Path:
    """Install ``fake_aermod.py`` as an executable ``aermod`` in ``bin_dir``.

    The copy's shebang names this interpreter, so the fake runs under the
    Python that runs the tests whatever ``python3`` is on ``PATH``.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    body = FAKE_AERMOD.read_text(encoding="utf-8").split("\n", 1)[1]
    target = bin_dir / "aermod"
    target.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    target.chmod(0o755)
    return target


def process_running(pid: int) -> bool:
    """True if ``pid`` is a live process (a zombie counts as finished)."""
    if Path("/proc/self/status").exists():
        try:
            text = Path(f"/proc/{pid}/status").read_text()
        except OSError:
            return False
        state = re.search(r"^State:\s+(\S)", text, re.M)
        return bool(state) and state.group(1) != "Z"
    try:  # no /proc (macOS): signal 0 only asks whether the pid exists
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class GuiServer:
    """One GUI server process, started fresh for one journey."""

    def __init__(self, root: Path, *, recording: Optional[str], delay: float):
        self.root = root
        self.home = root / "home"
        self.cwd = root / "server"
        self.tmp = root / "tmp"
        self.bin = root / "bin"
        self.log_path = root / "server.log"
        self.fake_log = root / "fake_aermod.jsonl"
        self.recording = recording
        self.delay = delay
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: Optional[subprocess.Popen] = None

    # -- lifecycle ---------------------------------------------------------
    def _env(self) -> dict:
        # NiceGUI switches to its own test mode when it sees
        # PYTEST_CURRENT_TEST; the server must run as a user would start it.
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
        env["PYTHONPATH"] = os.pathsep.join(
            [str(SRC)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []),
        )
        # A fresh home, but the same user site-packages: Python derives
        # that directory from HOME unless PYTHONUSERBASE says otherwise.
        env.setdefault("PYTHONUSERBASE", site.getuserbase())
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["TMPDIR"] = str(self.tmp)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYAERMOD_E2E_FAKE_LOG"] = str(self.fake_log)
        for var in ("PYAERMOD_E2E_RECORDING", "PYAERMOD_E2E_DELAY"):
            env.pop(var, None)
        if not REAL_AERMOD:
            install_fake_aermod(self.bin)
            env["PATH"] = os.pathsep.join([str(self.bin), env.get("PATH", "")])
            if self.recording:
                env["PYAERMOD_E2E_RECORDING"] = str(RECORDINGS / self.recording)
            env["PYAERMOD_E2E_DELAY"] = str(self.delay)
        return env

    def start(self) -> GuiServer:
        return self.launch().wait_ready()

    def launch(self) -> GuiServer:
        """Start the process without waiting for it to listen."""
        for d in (self.home, self.cwd, self.tmp):
            d.mkdir(parents=True, exist_ok=True)
        code = (
            "from pyaermod.gui_v2.app import build_and_run; "
            f"build_and_run(show=False, port={self.port})"
        )
        log = open(self.log_path, "wb")  # noqa: SIM115 -- lives with the process
        kwargs = {}
        if os.name == "posix":
            # Own process group, so stop() also reaches an AERMOD child.
            kwargs["start_new_session"] = True
        self.proc = subprocess.Popen(
            [sys.executable, "-c", code], cwd=self.cwd, env=self._env(),
            stdout=log, stderr=subprocess.STDOUT, **kwargs,
        )
        log.close()
        return self

    def wait_ready(self) -> GuiServer:
        assert self.proc is not None, "launch() first"
        deadline = time.monotonic() + SERVER_START_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"GUI server exited with code {self.proc.returncode} "
                    f"before listening:\n{self.log_text()}",
                )
            with contextlib.suppress(OSError):
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return self
            time.sleep(0.05)
        self.stop()
        raise RuntimeError(f"GUI server did not listen within "
                           f"{SERVER_START_TIMEOUT_S} s:\n{self.log_text()}")

    def stop(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        self._signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._signal(getattr(signal, "SIGKILL", signal.SIGTERM))
            proc.wait(timeout=10)

    def _signal(self, sig) -> None:
        assert self.proc is not None
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, sig)
        else:  # pragma: no cover - Windows
            self.proc.terminate()

    # -- what the server said ---------------------------------------------
    def log_text(self) -> str:
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def log_size(self) -> int:
        return len(self.log_text())

    def tracebacks(self, start: int = 0, end: Optional[int] = None) -> List[str]:
        """Each traceback in the log between two offsets, with its last line."""
        text = self.log_text()[start:end]
        found = []
        for chunk in text.split(TRACEBACK)[1:]:
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            # The exception line is the first unindented line after the frames.
            tail = next((ln for ln in lines if not ln.startswith(" ")), "")
            found.append(tail)
        return found

    def fake_events(self, kind: Optional[str] = None) -> List[dict]:
        if not self.fake_log.exists():
            return []
        events = [json.loads(ln) for ln in
                  self.fake_log.read_text(encoding="utf-8").splitlines() if ln]
        return [e for e in events if kind is None or e["event"] == kind]


@dataclass
class GapHit:
    gap_id: str
    reason: str
    log_offset: int
    browser_errors: int


class Journey:
    """Everything one journey owns: server, page, screenshots and gaps."""

    def __init__(self, *, name: str, server: GuiServer, page, root: Path):
        self.name = name
        self.server = server
        self.page = page
        self.root = root
        self.downloads = root / "downloads"
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.browser_errors: List[str] = []
        self.gap_hit: Optional[GapHit] = None
        self.reported: Set[str] = set()     # hidden problems already failed on
        self.server_side_files: List[Path] = []
        self._in_gap = False
        self._shot = 0
        self.artifacts = ARTIFACTS / re.sub(r"[^\w.-]+", "_", name)
        shutil.rmtree(self.artifacts, ignore_errors=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.watch(page)
        self._use_timeouts(STEP_TIMEOUT_MS, EXPECT_TIMEOUT_MS)

    def watch(self, page) -> None:
        """Fail the journey on ``page``'s JS and console errors (Rule 5).

        The fixture calls it for every further tab the journey opens.
        """
        page.on("pageerror", lambda exc: self.browser_errors.append(
            f"pageerror: {exc}"))
        page.on("console", self._on_console)

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self.browser_errors.append(f"console error: {msg.text}")

    def _use_timeouts(self, step_ms: int, expect_ms: int) -> None:
        self.page.set_default_timeout(step_ms)
        if expect is not None:
            expect.set_options(timeout=expect_ms)

    # -- screenshots ------------------------------------------------------
    def step(self, name: str, page=None) -> Path:
        """Save a full-page screenshot as ``NN_<name>.png`` for this journey.

        Of the journey's page, or of ``page`` (another tab it opened).
        """
        self._shot += 1
        slug = re.sub(r"[^\w.-]+", "_", name).strip("_") or "step"
        path = self.artifacts / f"{self._shot:02d}_{slug}.png"
        try:
            (page or self.page).screenshot(path=str(path), full_page=True, timeout=5_000)
        except Exception as exc:
            path.with_suffix(".txt").write_text(f"screenshot failed: {exc}\n")
        return path

    # -- known gaps -------------------------------------------------------
    def known_gap(self, gap_id: str, reason: str) -> KnownGap:
        return KnownGap(self, gap_id, reason)

    # -- teardown ---------------------------------------------------------
    def hidden_problems(self) -> List[str]:
        """Errors the user would not see on the page, collected at the end.

        Tracebacks and browser errors that appear after a known gap was hit
        are attributed to that gap (the journey stopped there). A deck the
        fake AERMOD did not recognise is always a failure.
        """
        problems: List[str] = []
        hit = self.gap_hit
        log_end = hit.log_offset if hit else None
        errors = self.browser_errors[: hit.browser_errors] if hit else self.browser_errors
        for err in errors:
            problems.append(err)
        tracebacks = self.server.tracebacks(0, log_end)
        if tracebacks:
            problems.append(
                f"the server log has {len(tracebacks)} Python traceback(s): "
                + "; ".join(tracebacks),
            )
        for event in self.server.fake_events("deck_mismatch"):
            problems.append(
                "the fake AERMOD refused the deck the GUI wrote "
                f"(recording {event.get('recording')!r}):\n{event.get('diff')}",
            )
        return problems


class KnownGap:
    """``with known_gap("D2", "..."):`` around a step the GUI cannot do yet.

    * The block raises ``AssertionError`` or a Playwright ``TimeoutError``:
      the journey stops here and is reported as xfailed, naming the gap.
    * The block passes: the journey FAILS, because the gap appears fixed and
      the ``known_gap`` must be removed so the journey guards the fix.
    * Any other exception is a real failure and propagates unchanged.

    Timeouts inside the block are short (``GAP_TIMEOUT_MS``). Under
    ``pytest --runxfail`` the original failure propagates instead.
    """

    def __init__(self, journey: Journey, gap_id: str, reason: str):
        self.journey = journey
        self.gap_id = gap_id
        self.reason = reason
        self._log_offset = 0
        self._errors = 0

    @property
    def label(self) -> str:
        return f"{self.gap_id}: {self.reason}"

    def __enter__(self) -> KnownGap:
        j = self.journey
        if j._in_gap:
            raise RuntimeError("known_gap blocks cannot be nested")
        j._in_gap = True
        self._log_offset = j.server.log_size()
        self._errors = len(j.browser_errors)
        j._use_timeouts(GAP_TIMEOUT_MS, GAP_TIMEOUT_MS)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        j = self.journey
        j._in_gap = False
        j._use_timeouts(STEP_TIMEOUT_MS, EXPECT_TIMEOUT_MS)
        if exc_type is None:
            pytest.fail(
                f"known gap {self.label} appears fixed; remove known_gap and "
                "flip the journey", pytrace=False,
            )
        if not issubclass(exc_type, (AssertionError, PlaywrightTimeoutError)):
            return False
        j.gap_hit = GapHit(self.gap_id, self.reason, self._log_offset, self._errors)
        j.step(f"gap_{self.gap_id}")
        first = (str(exc).strip().splitlines() or [exc_type.__name__])[0]
        detail = f"{exc_type.__name__}: {first[:240]}"
        server = j.server.tracebacks(self._log_offset)
        if server:
            detail += f"; server: {server[-1][:200]}"
        # pytest.xfail is looked up at call time: --runxfail replaces it with
        # a no-op, and then the original exception propagates below.
        pytest.xfail(f"{self.label} [{detail}]")
        return False


def deck_written_to(run_dir: Path) -> Path:
    """The deck the GUI wrote into the working directory the test chose."""
    decks = [p for p in run_dir.glob("*.inp") if p.name != "aermod.inp"]
    assert len(decks) == 1, f"expected one deck in {run_dir}, found {decks}"
    return decks[0]
