"""EPA decks rewritten by pyaermod drive AERMOD to the same answers.

The parity harness in ``test_epa_aermod_suite.py`` runs EPA's decks as
shipped. These tests run the decks *after* pyaermod has read and
written them, and score every POSTFILE against EPA's reference, so a
field the reader drops or the writer misplaces shows up as a
concentration difference rather than a diff nobody reads.

Two modes, because the reader is being completed in tranches:

``FULL_REWRITE``
    The whole deck is ``parse_aermod_input`` -> ``to_aermod_input``.
    Only decks whose every pathway survives the round trip are listed;
    the others fail today on receptor and output forms outside this
    tranche (explicit ``GRIDPOLR DIST`` lists, ``ORIG`` by source ID,
    two-field ``DISCCART`` lines, several ``POSTFILE`` lines).
``SO_SPLICE``
    pyaermod's SO pathway is spliced into the original deck in place of
    EPA's. This isolates the source-construction keywords, which is what
    reader tranche 2 changed, for every deck that uses them.

Pass criterion as in the suite: best-fit slope within EPA's own margin
(``DEFAULT_SLOPE_TOLERANCE``). A deck AERMOD refuses fails outright,
with the fatal messages in the assertion.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from pyaermod.input_reader import parse_aermod_input
from pyaermod.regulatory_parity import (
    DEFAULT_SLOPE_TOLERANCE,
    score_postfile_pair,
)
from pyaermod.runner import AERMODRunner

from .conftest import (
    EPA_INPUTS_DIR,
    EPA_MET_DIR,
    EPA_REF_PST_DIR,
    EPA_SET_NAME,
    fixtures_ready,
    missing_reason,
)

if not fixtures_ready():
    pytest.skip(missing_reason(), allow_module_level=True)

pytestmark = pytest.mark.slow

_DECK_TIMEOUT = 600
_FATAL_RE = re.compile(r"^\s*(CO|SO|RE|ME|OU)\s+E(\d{3})\s+(.*)$", re.MULTILINE)

#: Decks whose SO pathway uses the tranche-2 keywords: AREAPOLY/AREAVERT,
#: BUOYLINE/BLPINPUT/BLPGROUP, RLINEXT with RBARRIER/RDEPRESS, OLMGROUP,
#: PSDGROUP, DEPOUNIT, GASDEPOS, URBANSRC.
SO_SPLICE = [
    "allsrcs.inp", "blp_urban.inp",
    "aermod-baldwin45.inp", "aermod-baldwinHoriz.inp", "aermod-baldwinVert.inp",
    "Test1_Base_cart_3cond_SNC.inp", "Test20_Urban_cart_3cond_SNC.inp",
    "Test3_Base_cart_3cond_SNC_bar.inp", "Test4_Base_cart_3cond_SNC_dep.inp",
    "olmgrp.inp", "no2_1yrAK_olmgrp.inp", "psdcred.inp",
    "testgas.inp", "testgas2.inp",
]

#: Decks whose answer depends on a keyword WP-5 gave a field: METHOD_2
#: (testpart, testprt2, openpits), POINTCAP/POINTHOR with an exit velocity
#: of 0.001 m/s (capped), ARMRATIO (the two ARM2 decks), RANKFILE and
#: SEASONHR (flatelev, lovett, mcr, hrdow). Each is fully rewritten.
WP5_REWRITE = [
    "testpart.inp", "testprt2.inp", "openpits.inp", "capped.inp",
    "no2_1yrAK_arm2.inp", "no2_1yrAK_arm2min.inp",
    "flatelev.inp", "lovett.inp", "mcr.inp", "hrdow.inp",
]

#: The subset whose CO, RE, ME and OU pathways also round-trip today.
FULL_REWRITE = [
    "allsrcs.inp", "blp_urban.inp",
    "aermod-baldwin45.inp", "aermod-baldwinHoriz.inp", "aermod-baldwinVert.inp",
    "Test1_Base_cart_3cond_SNC.inp", "Test20_Urban_cart_3cond_SNC.inp",
    "Test3_Base_cart_3cond_SNC_bar.inp", "Test4_Base_cart_3cond_SNC_dep.inp",
    *WP5_REWRITE,
]


def splice_so(original: str, written: str) -> str:
    """The original deck with pyaermod's SO pathway in place of its own."""
    wl = written.splitlines()
    so = wl[wl.index("SO STARTING"):wl.index("SO FINISHED") + 1]
    out, skipping = [], False
    for line in original.splitlines():
        u = line.strip().upper()
        if u.startswith("SO STARTING"):
            out.extend(so)
            skipping = True
            continue
        if u.startswith("SO FINISHED"):
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out) + "\n"


def _stage(work: Path, deck_name: str, deck_text: str) -> Path:
    for sub in ("inputs", "meteorology", "postfiles", "plotfiles", "Outputs", "rdata"):
        (work / sub).mkdir(parents=True)
    for extra in EPA_INPUTS_DIR.iterdir():
        if extra.is_file() and extra.suffix.lower() != ".inp":
            shutil.copy2(extra, work / "inputs" / extra.name)
    for met in EPA_MET_DIR.glob("*"):
        if met.is_file():
            shutil.copy2(met, work / "meteorology" / met.name)
    path = work / "inputs" / deck_name
    path.write_text(deck_text)
    return path


def _fatal_errors(out_path: Path) -> list[str]:
    if not out_path.is_file():
        return ["AERMOD produced no .out file"]
    text = out_path.read_text(encoding="latin-1", errors="replace")
    block = text.split("FATAL ERROR MESSAGES")
    if len(block) < 2:
        return []
    return [f"{p} E{c} {m.strip()}" for p, c, m in _FATAL_RE.findall(block[1])]


def _run_and_score(deck_name: str, deck_text: str, work: Path, aermod_binary) -> None:
    deck_path = _stage(work, deck_name, deck_text)
    runner = AERMODRunner(executable_path=aermod_binary, log_level="WARNING")
    result = runner.run(input_file=deck_path, working_dir=deck_path.parent,
                        timeout=_DECK_TIMEOUT)
    outs = list(deck_path.parent.glob("*.out"))
    fatal = _fatal_errors(outs[0]) if outs else ["AERMOD produced no .out file"]
    assert result.success and not fatal, (
        f"AERMOD rejected the rewritten {deck_name}:\n  " + "\n  ".join(fatal)
        + "\n\nSO pathway:\n" + deck_text[deck_text.find("SO STARTING"):deck_text.find("SO FINISHED") + 11]
    )
    candidates = sorted((work / "postfiles").glob("*.PST"))
    assert candidates, f"{deck_name} produced no POSTFILE"
    scored, fails = 0, []
    for cand in candidates:
        ref = EPA_REF_PST_DIR / cand.name
        if not ref.exists():
            continue
        scored += 1
        score = score_postfile_pair(ref, cand, case=cand.name)
        if not score.passes(DEFAULT_SLOPE_TOLERANCE):
            fails.append(score)
    assert scored, f"{deck_name}: no reference POSTFILE for {[c.name for c in candidates]}"
    assert not fails, (
        f"{deck_name}: {len(fails)} POSTFILE(s) outside EPA tolerance: "
        + "; ".join(f"{s.case} slope={s.slope:.6f} (n={s.n_paired})" for s in fails)
    )


@pytest.mark.parametrize("deck_name", SO_SPLICE, ids=[f"{EPA_SET_NAME}/{d}" for d in SO_SPLICE])
def test_rewritten_so_pathway_reaches_parity(deck_name, aermod_binary, scratch):
    text = (EPA_INPUTS_DIR / deck_name).read_text(encoding="latin-1")
    written = parse_aermod_input(text).to_aermod_input(validate=False)
    _run_and_score(deck_name, splice_so(text, written), scratch / "splice", aermod_binary)


@pytest.mark.parametrize("deck_name", FULL_REWRITE, ids=[f"{EPA_SET_NAME}/{d}" for d in FULL_REWRITE])
def test_fully_rewritten_deck_reaches_parity(deck_name, aermod_binary, scratch):
    text = (EPA_INPUTS_DIR / deck_name).read_text(encoding="latin-1")
    written = parse_aermod_input(text).to_aermod_input(validate=False)
    _run_and_score(deck_name, written, scratch / "full", aermod_binary)
