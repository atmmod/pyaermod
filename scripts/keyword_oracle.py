#!/usr/bin/env python
"""
Print what AERMOD's own source and binary say about a set of keywords.

Reader and writer support for a runstream keyword must come from the
program that defines it, not from memory of the User's Guide. This
script is the oracle: given EPA's Fortran source tree it prints, for
each keyword, the dispatch branch that recognises it and the full body
of the subroutine that parses its fields; given a compiled binary it
runs probe decks through AERMOD and prints the setup-pass messages and
the head of every file the run produced. Both outputs are meant to be
read from a CI log (``.github/workflows/keyword_oracle.yml``), where EPA's
servers are reachable when a development sandbox's are not.

Usage::

    keyword_oracle.py source <aermod-source-dir> KEYWORD [KEYWORD ...]
    keyword_oracle.py decks  <deck-dir> KEYWORD [KEYWORD ...]
    keyword_oracle.py run    <aermod-exe> <deck-dir> <met-dir> [--full]

``source`` scans coset.f, soset.f, reset.f, meset.f, ouset.f and
evset.f. ``decks`` prints every deck under a directory that uses one of
the keywords, in full. ``run`` executes each ``*.inp`` in a directory
in its own scratch copy with the meteorology alongside; decks are run
as written (a ``RUNORNOT NOT`` deck is a setup pass only).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List

SETUP_FILES = ("coset.f", "soset.f", "reset.f", "meset.f", "ouset.f", "evset.f")

# Fixed-form comment: column 1 is C, c, ! or *.
_COMMENT_RE = re.compile(r"^[Cc!*]")
_CALL_RE = re.compile(r"\bCALL\s+([A-Z0-9_]+)", re.IGNORECASE)
_SUB_RE = re.compile(r"^\s+SUBROUTINE\s+([A-Z0-9_]+)", re.IGNORECASE)
_END_RE = re.compile(r"^\s+END(\s+SUBROUTINE\b.*)?\s*$", re.IGNORECASE)


def _code(line: str) -> bool:
    return not _COMMENT_RE.match(line)


def _dispatch_branches(lines: List[str], keyword: str) -> List[range]:
    """Line ranges of ``IF (KEYWRD .EQ. 'keyword') ... `` branches."""
    pat = re.compile(
        r"KEYWRD\s*\.EQ\.\s*'" + re.escape(keyword) + r"'", re.IGNORECASE
    )
    out: List[range] = []
    for i, line in enumerate(lines):
        if not _code(line) or not pat.search(line):
            continue
        # The branch runs to the next ELSE IF / ELSE / END IF at the
        # *same* nesting level; the body itself opens IF blocks (the
        # repeat-keyword guard) whose ELSE must not end the scan.
        depth = 0
        j = i + 1
        while j < len(lines):
            probe = lines[j]
            if _code(probe):
                if re.match(r"^\s+IF\b.*\bTHEN\s*$", probe, re.IGNORECASE):
                    depth += 1
                elif re.match(r"^\s+END\s*IF\b", probe, re.IGNORECASE):
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0 and re.match(
                    r"^\s+ELSE\b", probe, re.IGNORECASE
                ):
                    break
            j += 1
        out.append(range(i, j))
    return out


def _subroutine_body(lines: List[str], name: str) -> List[str]:
    start = None
    for i, line in enumerate(lines):
        m = _SUB_RE.match(line)
        if m and m.group(1).upper() == name.upper():
            start = i
            break
    if start is None:
        return []
    for j in range(start + 1, len(lines)):
        if _code(lines[j]) and _END_RE.match(lines[j]):
            return lines[start:j + 1]
    return lines[start:]


def cmd_source(src_dir: Path, keywords: Iterable[str]) -> int:
    texts = {}
    for fname in SETUP_FILES:
        path = src_dir / fname
        if path.is_file():
            texts[fname] = path.read_text(encoding="latin-1").splitlines()
    if not texts:
        print(f"no setup sources under {src_dir}", file=sys.stderr)
        return 1
    for kw in keywords:
        kw = kw.upper()
        print(f"\n{'=' * 78}\n=== KEYWORD {kw}\n{'=' * 78}")
        found = False
        for fname, lines in texts.items():
            for rng in _dispatch_branches(lines, kw):
                found = True
                print(f"--- {fname} dispatch, lines {rng.start + 1}-{rng.stop}")
                called: List[str] = []
                for i in rng:
                    print(f"{i + 1:6d}: {lines[i]}")
                    if _code(lines[i]):
                        called += _CALL_RE.findall(lines[i])
                for sub in dict.fromkeys(called):
                    body = _subroutine_body(lines, sub)
                    where = fname
                    if not body:
                        for other, olines in texts.items():
                            body = _subroutine_body(olines, sub)
                            if body:
                                where = other
                                break
                    if not body:
                        print(f"--- SUBROUTINE {sub}: not found in setup sources")
                        continue
                    print(f"--- SUBROUTINE {sub} ({where}, {len(body)} lines)")
                    print("\n".join(body))
        if not found:
            print(f"--- no dispatch branch for {kw} in {sorted(texts)}")
    return 0


def cmd_decks(deck_dir: Path, keywords: Iterable[str]) -> int:
    kws = [k.upper() for k in keywords]
    pat = re.compile(r"^\s*(?:CO|SO|RE|ME|OU|EV)?\s*(" + "|".join(map(re.escape, kws)) + r")\b",
                     re.IGNORECASE)
    decks = sorted(deck_dir.rglob("*.inp"))
    print(f"scanning {len(decks)} decks under {deck_dir} for {kws}")
    hits = {}
    for deck in decks:
        lines = deck.read_text(encoding="latin-1").splitlines()
        used = sorted({
            pat.match(line).group(1).upper() for line in lines if pat.match(line)
        })
        if used:
            hits[deck] = used
    print("\n--- decks using the keywords")
    for deck, used in hits.items():
        print(f"{deck.name}: {' '.join(used)}")
    for deck in hits:
        print(f"\n{'=' * 78}\n=== DECK {deck.name}\n{'=' * 78}")
        print(deck.read_text(encoding="latin-1").rstrip())
    return 0


_MSG_HEAD = re.compile(r"\*\*\* Message Summary", re.IGNORECASE)


def cmd_run(exe: Path, deck_dir: Path, met_dir: Path, full: bool = False) -> int:
    decks = sorted(deck_dir.glob("*.inp"))
    root = Path(tempfile.mkdtemp(prefix="oracle-"))
    print(f"running {len(decks)} decks with {exe} in {root}")
    for deck in decks:
        work = root / deck.stem
        work.mkdir()
        for met in met_dir.iterdir():
            if met.is_file():
                shutil.copy(met, work / met.name)
        # A deck may depend on files staged beside it (an INITFILE written
        # by an earlier deck, a background file); copy non-.inp siblings.
        for extra in deck_dir.iterdir():
            if extra.is_file() and extra.suffix.lower() != ".inp":
                shutil.copy(extra, work / extra.name)
        # Decks run in name order in the *same* directory so that a
        # later deck can INITFILE from an earlier deck's SAVEFILE.
        shared = root / "shared"
        shared.mkdir(exist_ok=True)
        for item in work.iterdir():
            shutil.copy(item, shared / item.name)
        shutil.copy(deck, shared / "aermod.inp")
        before = {p.name for p in shared.iterdir()}
        print(f"\n{'=' * 78}\n=== RUN {deck.name}\n{'=' * 78}")
        proc = subprocess.run(
            [str(exe)], cwd=str(shared), capture_output=True, text=True,
            timeout=1800,
        )
        print(f"exit status {proc.returncode}")
        if proc.stdout.strip():
            print("--- stdout (tail)")
            print("\n".join(proc.stdout.splitlines()[-15:]))
        out = shared / "aermod.out"
        if out.is_file():
            text = out.read_text(encoding="latin-1", errors="replace")
            if full:
                print("--- aermod.out")
                print(text)
            else:
                m = _MSG_HEAD.search(text)
                print("--- aermod.out message summary")
                print(text[m.start():m.start() + 6000] if m else text[:4000])
                # Also echo the runstream image, where AERMOD flags bad lines.
                print("--- aermod.out header (first 120 lines)")
                print("\n".join(text.splitlines()[:120]))
        after = {p.name for p in shared.iterdir()}
        for name in sorted(after - before):
            path = shared / name
            if name == "aermod.out":
                continue
            data = path.read_text(encoding="latin-1", errors="replace").splitlines()
            print(f"--- produced {name}: {len(data)} lines, {path.stat().st_size} bytes")
            print("\n".join(data[:25]))
            if len(data) > 25:
                print("...")
                print("\n".join(data[-3:]))
        # Keep aermod.out from polluting the next run's "produced" list.
        for name in ("aermod.out",):
            (shared / name).unlink(missing_ok=True)
    return 0


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "source":
        return cmd_source(Path(argv[2]), argv[3:])
    if cmd == "decks":
        return cmd_decks(Path(argv[2]), argv[3:])
    if cmd == "run":
        full = "--full" in argv
        args = [a for a in argv[2:] if a != "--full"]
        return cmd_run(
            Path(args[0]).resolve(), Path(args[1]), Path(args[2]), full=full,
        )
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
