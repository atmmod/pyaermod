#!/usr/bin/env python3
"""A fake ``aermod`` that replays a recording of the real binary.

The end-to-end fixture installs this script as ``aermod`` in a temporary
``bin`` directory at the front of the GUI server's ``PATH`` (tier T2).
It behaves like the real binary did when the recording was made
(``scripts/record_aermod_fixtures.py``): it reads ``./aermod.inp``, prints
the recorded stdout line by line, writes the recorded output files into
its working directory (the ``.out`` file as ``aermod.out``, as AERMOD
does) and exits with the recorded exit code, which is 0 even for runs
AERMOD aborted.

Before replaying, it checks that the deck it was given is the deck that
was recorded, so a GUI regression in deck writing fails the journey
instead of being answered with somebody else's results. The comparison
ignores ``TITLEONE`` and ``TITLETWO``, comments and blank lines, compares
met file paths (``SURFFILE``, ``PROFFILE``) by base name, and compares
numeric tokens by value, so ``14735.0`` equals ``14735``. On a mismatch
it prints a diff to stderr and exits with code 2.

Environment:

``PYAERMOD_E2E_RECORDING``
    The recording directory, or its name under ``PYAERMOD_E2E_RECORDINGS``
    (default: ``tests/fixtures/gui/aermod_recordings`` in this checkout).
``PYAERMOD_E2E_DELAY``
    Seconds to wait between stdout lines (default 0). The slow run of
    journey J9 is ``albany_*`` replayed with a delay.
``PYAERMOD_E2E_FAKE_LOG``
    Optional file to which the fake appends one JSON object per event
    (``start`` with its pid, ``deck_mismatch`` with the diff, ``finish``).
    The fixture reads it to fail a test whose deck did not match and to
    check that a cancelled run left no process behind.
"""

from __future__ import annotations

import difflib
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

IGNORED_KEYWORDS = {"TITLEONE", "TITLETWO"}
MET_PATH_KEYWORDS = {"SURFFILE", "PROFFILE"}
PATHWAYS = {"CO", "SO", "RE", "ME", "OU", "EV"}
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$")
DEFAULT_ROOT = (Path(__file__).resolve().parent.parent
                / "fixtures" / "gui" / "aermod_recordings")


def _canonical_token(token: str) -> str:
    if _NUMBER.match(token):
        value = float(token.replace("d", "e").replace("D", "e"))
        return repr(value + 0.0)          # + 0.0 folds -0.0 into 0.0
    return token


def _base_name(path: str) -> str:
    return re.split(r"[\\/]", path.strip('"'))[-1]


def normalize_deck(text: str) -> List[str]:
    """The deck as a list of comparable lines (see the module docstring)."""
    lines: List[str] = []
    for raw in text.splitlines():
        tokens = raw.split()
        if not tokens or tokens[0].startswith("**"):
            continue
        # EPA decks may repeat the pathway before a keyword ("SO BUILDHGT").
        if (tokens[0] in PATHWAYS and len(tokens) > 1
                and tokens[1] not in ("STARTING", "FINISHED")):
            tokens = tokens[1:]
        keyword = tokens[0].upper()
        if keyword in IGNORED_KEYWORDS:
            continue
        if keyword in MET_PATH_KEYWORDS and len(tokens) > 1:
            tokens = [tokens[0], _base_name(" ".join(tokens[1:]))]
        lines.append(" ".join(_canonical_token(t) for t in tokens))
    return lines


def deck_diff(recorded: str, given: str, *, recorded_name: str,
              given_name: str) -> str:
    """A unified diff of the normalized decks; empty when they match."""
    return "\n".join(difflib.unified_diff(
        normalize_deck(recorded), normalize_deck(given),
        fromfile=recorded_name, tofile=given_name, lineterm="",
    ))


def resolve_recording(value: Optional[str]) -> Path:
    if not value:
        raise LookupError("PYAERMOD_E2E_RECORDING is not set")
    path = Path(value)
    if path.is_dir():
        return path
    root = Path(os.environ.get("PYAERMOD_E2E_RECORDINGS") or DEFAULT_ROOT)
    if (root / value).is_dir():
        return root / value
    raise LookupError(f"no recording {value!r} (looked in {root})")


def _log(event: str, **data) -> None:
    log = os.environ.get("PYAERMOD_E2E_FAKE_LOG")
    if not log:
        return
    record = {"event": event, "pid": os.getpid(), "time": time.time(), **data}
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def main(argv: List[str]) -> int:
    try:
        recording = resolve_recording(os.environ.get("PYAERMOD_E2E_RECORDING"))
    except LookupError as exc:
        print(f"fake aermod: {exc}", file=sys.stderr)
        return 2
    manifest = json.loads((recording / "manifest.json").read_text("utf-8"))
    # AERMOD reads aermod.inp and writes aermod.out unless it is given
    # other names on its command line.
    deck_name = argv[1] if len(argv) > 1 else "aermod.inp"
    out_name = argv[2] if len(argv) > 2 else "aermod.out"
    _log("start", cwd=os.getcwd(), recording=recording.name, deck=deck_name)

    deck = Path(deck_name)
    if not deck.exists():
        print(f"fake aermod: {deck_name} not found in {os.getcwd()}",
              file=sys.stderr)
        _log("deck_mismatch", diff=f"{deck_name} not found")
        return 2
    diff = deck_diff(
        (recording / manifest["deck"]).read_text("latin-1"),
        deck.read_text("latin-1"),
        recorded_name=f"{recording.name}/{manifest['deck']}",
        given_name=f"./{deck_name}",
    )
    if diff:
        print(f"fake aermod: the deck differs from recording "
              f"{recording.name!r}:\n{diff}", file=sys.stderr)
        _log("deck_mismatch", recording=recording.name, diff=diff)
        return 2

    delay = float(os.environ.get("PYAERMOD_E2E_DELAY") or 0)
    stdout = (recording / manifest["stdout"]).read_bytes()
    for i, line in enumerate(stdout.splitlines(keepends=True)):
        if i and delay:
            time.sleep(delay)
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    stderr = recording / manifest.get("stderr", "stderr.txt")
    if stderr.exists():
        sys.stderr.buffer.write(stderr.read_bytes())
        sys.stderr.buffer.flush()

    for src in sorted((recording / "outputs").iterdir()):
        name, data = src.name, src.read_bytes()
        if name.endswith(".gz"):          # stored compressed, see the recorder
            name, data = name[:-3], gzip.decompress(data)
        Path(out_name if name == "aermod.out" else name).write_bytes(data)
    code = int(manifest["exit_code"])
    _log("finish", exit_code=code)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
