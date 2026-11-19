"""G9: downloading a run file must not hold the event loop while the file is read and hashed."""

import asyncio
import hashlib
import time

import pytest

pytest.importorskip("nicegui", minversion="3.4.0")

from . import test_gui_v2_smoke as smoke
from .test_gui_v2_results import REFERENCE_PERIODS, _download, _open_albany, _run_in

gui = smoke.gui
recorded_aermod = smoke.recorded_aermod
pytestmark = smoke.pytestmark


@pytest.mark.asyncio
async def test_a_download_does_not_freeze_every_tab(gui, recorded_aermod, tmp_path, monkeypatch):
    recorded_aermod("albany_success")
    await _open_albany(gui, tmp_path, REFERENCE_PERIODS)
    await _run_in(gui, tmp_path / "run", outcome="Succeeded in", shows="Run 1 succeeded")
    await gui.user.should_see("Downloads")

    real = hashlib.sha256
    calls = []

    def slow_sha256(*args, **kwargs):          # stands for hashing a multi-GB POSTFILE
        calls.append(1)
        time.sleep(0.5)
        return real(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", slow_sha256)

    gaps = []

    async def heartbeat():
        last = time.perf_counter()
        while True:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.05)               # the heartbeat is running before the click
    try:
        await _download(gui, "Download AERMOD output (.out)")
    finally:
        await asyncio.sleep(0.02)           # one more beat, to record a gap that ended after the click
        task.cancel()
    assert calls, "the download never hashed"
    assert max(gaps) < 0.25, f"the event loop was blocked for {max(gaps):.2f} s by one download"
