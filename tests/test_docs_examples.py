"""The Python examples in the quickstart and the student guide run as written.

Each page's ```python blocks run in order in one namespace, in an empty
folder, as a reader would paste them. A block that needs something a test
cannot have (an AERMOD run, its output files, a deck of the reader's own)
is marked in the page, just above it, with an HTML comment that MkDocs
does not show:

    <!-- docs-example: skip (runs AERMOD) -->

Every other block must run. This is how the quickstart's EVENT and
validator examples, which raised TypeError for releases, would have been
caught.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
PAGES = ["quickstart.md", *sorted(
    str(p.relative_to(DOCS)) for p in (DOCS / "teaching" / "student-guide").glob("*.md"))]
BLOCK = re.compile(r"(<!-- docs-example: skip \(([^)]*)\) -->\n)?```python\n(.*?)```", re.S)


def _blocks(page: str):
    text = (DOCS / page).read_text(encoding="utf-8")
    return [(m.group(2), m.group(3)) for m in BLOCK.finditer(text)]


@pytest.mark.parametrize("page", [p for p in PAGES if _blocks(p)])
def test_the_pages_python_examples_run(page, tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.chdir(tmp_path)
    namespace: dict = {"__name__": "__docs_example__"}
    ran = 0
    for index, (skip_reason, code) in enumerate(_blocks(page)):
        if skip_reason is not None:
            continue
        try:
            exec(compile(code, f"{page} block {index + 1}", "exec"), namespace)
        except Exception as exc:  # name the block, not this test's line
            pytest.fail(f"{page}, Python block {index + 1}, raised "
                        f"{type(exc).__name__}: {exc}\n\n{code}")
        ran += 1
    assert ran, f"{page}: every Python block is marked to skip"


def test_skips_say_why():
    for page in PAGES:
        for reason, _code in _blocks(page):
            assert reason is None or reason.strip(), f"{page}: a skip with no reason"
