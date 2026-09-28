"""Runstream lines the reader keeps verbatim because it has no model for them.

:mod:`pyaermod.input_reader` turns the keywords it understands into fields
on the :class:`~pyaermod.input_generator.AERMODProject`. Every other line
of a deck -- a keyword the reader has no structure for, a form of a known
keyword it does not model (a ``BACKGRND`` hourly file, an ``EVENTFIL``
with an output option), or a whole ``EV`` pathway -- is recorded here as
an :class:`UnparsedLine` so that nothing is dropped on the floor:

* the reader logs one warning per pathway and keyword saying how many
  lines were kept this way;
* the writer puts the lines back into the pathway they came from, just
  before its ``FINISHED`` marker, unless asked not to
  (``AERMODProject.to_aermod_input(preserve_unparsed=False)``).

The lines are re-emitted with the keyword spelled out even when the
source deck left the keyword columns blank (AERMOD lets a line inherit
the previous keyword), so they stay valid wherever the writer places
them. Field text is kept as written -- ``36*50.`` stays ``36*50.`` and
filenames keep their case -- because AERMOD reads it from the deck, not
from pyaermod's model of it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

#: Pathway codes in the order AERMOD requires them.
PATHWAY_ORDER: Tuple[str, ...] = ("CO", "SO", "RE", "ME", "OU", "EV")

#: Comment AERMOD skips (``**`` in the pathway columns) written above a
#: group of preserved lines so a reader of the deck knows where they came from.
PRESERVED_BANNER = (
    "** Lines kept verbatim from the source deck; pyaermod has no model for them."
)


@dataclass
class UnparsedLine:
    """One runstream line the reader could not represent structurally.

    Attributes
    ----------
    pathway : str
        Two-letter pathway code the line sits in (``CO``, ``SO``, ...).
    keyword : str
        The keyword AERMOD would dispatch the line on, upper-cased. For a
        continuation line this is the inherited keyword, not the first
        token of the line.
    fields : list of str
        The data fields as written, with any leading pathway code and
        the keyword removed. Repeat shorthand (``36*50.``) is *not*
        expanded here.
    lineno : int
        1-based line number in the source text.
    raw : str
        The source line with trailing whitespace stripped.
    """

    pathway: str
    keyword: str
    fields: List[str] = field(default_factory=list)
    lineno: int = 0
    raw: str = ""

    def to_aermod_line(self) -> str:
        """The line as the writer re-emits it.

        AERMOD reads the keyword from columns 4-11 and the data from
        column 13 on (setup.f DEFINE), so a keyword shorter than eight
        characters is padded: ``XBADJ  STACK1`` would otherwise be read
        as the keyword ``XBADJ  S`` (E105).
        """
        return f"   {self.keyword:<8}  " + "  ".join(self.fields) if self.fields \
            else f"   {self.keyword}"


def unparsed_summary(lines: Iterable[UnparsedLine]) -> Dict[Tuple[str, str], int]:
    """Count preserved lines per ``(pathway, keyword)``, in deck order."""
    counts: Counter = Counter((ln.pathway, ln.keyword) for ln in lines)
    return dict(sorted(
        counts.items(),
        key=lambda item: (PATHWAY_ORDER.index(item[0][0])
                          if item[0][0] in PATHWAY_ORDER else len(PATHWAY_ORDER),
                          item[0][1]),
    ))


def preserved_block(pathway: str, lines: Iterable[UnparsedLine]) -> List[str]:
    """The deck lines that put ``pathway``'s preserved lines back.

    Empty when there is nothing to put back; otherwise a banner comment
    followed by one line per :class:`UnparsedLine`, in source order.
    """
    mine = sorted((ln for ln in lines if ln.pathway == pathway),
                  key=lambda ln: ln.lineno)
    if not mine:
        return []
    return [PRESERVED_BANNER, *(ln.to_aermod_line() for ln in mine)]


__all__ = [
    "PATHWAY_ORDER",
    "PRESERVED_BANNER",
    "UnparsedLine",
    "preserved_block",
    "unparsed_summary",
]
