"""An EVENT deck rewritten by pyaermod drives AERMOD to the same events.

AERMOD writes the event deck itself when a main run has ``EVENTFIL``;
``tests/fixtures/epa_official/events_generated.inp`` is the one AERMOD
v26135 wrote for ``scripts/oracle_decks/29_event_main.inp`` (EVENTOUT
SOCONT, four events over the vendored AERMET2 meteorology). This test
runs that deck as AERMOD wrote it and again after
``parse_aermod_input`` -> ``to_aermod_input``, and requires every event's
group value and every source contribution to agree to the last printed
digit. A field the EV reader dropped or the writer misplaced would move
an event to another hour, receptor or group and show up here.

Needs ``aermod`` on PATH; the meteorology is vendored. Marked slow like
the rest of this directory.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pyaermod.aermod_outputs import read_event_output
from pyaermod.input_reader import parse_aermod_input

AERMOD_EXE = shutil.which("aermod")
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "epa_official"
DECK = FIXTURES / "events_generated.inp"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(AERMOD_EXE is None, reason="aermod not on PATH; build with scripts/build_aermod.sh"),
]

_FATAL_RE = re.compile(r"^\s*(CO|SO|ME|OU|EV|MX)\s+E(\d{3})\s+(.*)$", re.MULTILINE)


def _run(deck_text: str, work: Path):
    work.mkdir()
    for met in ("AERMET2.SFC", "AERMET2.PFL"):
        shutil.copy(FIXTURES / met, work / met)
    (work / "aermod.inp").write_text(deck_text)
    subprocess.run([AERMOD_EXE], cwd=str(work), capture_output=True, timeout=600)
    out = work / "aermod.out"
    assert out.is_file(), "AERMOD produced no aermod.out"
    text = out.read_text(encoding="latin-1", errors="replace")
    block = text.split("FATAL ERROR MESSAGES")
    fatal = _FATAL_RE.findall(block[1]) if len(block) > 1 else []
    assert not fatal, fatal
    return read_event_output(out)


def test_rewritten_event_deck_reproduces_every_contribution(tmp_path):
    text = DECK.read_text()
    reference = _run(text, tmp_path / "epa")
    assert [e.event_name for e in reference] == ["H001H01001", "H001H01002", "H001H24001", "H001H24002"]

    project = parse_aermod_input(text)
    written = project.to_aermod_input(validate=True)
    candidate = _run(written, tmp_path / "pyaermod")

    assert [(e.event_name, e.averaging_period, e.end_date, e.group_id) for e in candidate] == \
        [(e.event_name, e.averaging_period, e.end_date, e.group_id) for e in reference]
    for ref, cand in zip(reference, candidate):
        assert (cand.x, cand.y, cand.z_elev, cand.z_flag) == (ref.x, ref.y, ref.z_elev, ref.z_flag)
        assert cand.group_value == ref.group_value, ref.event_name
        assert cand.contributions == ref.contributions, ref.event_name
        # ... and the concentration the EVENTPER card carried is the one
        # the event run reproduces (AERMOD checks this itself).
        event = next(e for e in project.events.events if e.event_name == ref.event_name)
        assert cand.group_value == pytest.approx(event.original_conc, abs=5e-6)
