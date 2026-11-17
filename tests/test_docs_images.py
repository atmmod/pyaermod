"""Every image a documentation page shows exists, and every screenshot is shown.

The GUI screenshots in docs/images/gui and docs/images/app are taken by
scripts/docs_screenshots.py; a page that names one that is not there
would render a broken image, and a screenshot no page shows is dead
weight in the repository.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
SCREENSHOT_DIRS = [DOCS / "images" / "gui", DOCS / "images" / "app"]


def _pages():
    return sorted(DOCS.rglob("*.md"))


def _references():
    for page in _pages():
        for target in IMAGE.findall(page.read_text(encoding="utf-8")):
            if not re.match(r"[a-z]+://", target):
                yield page, (page.parent / target).resolve()


@pytest.mark.parametrize("page,image", list(_references()),
                         ids=lambda v: str(v.relative_to(DOCS)) if isinstance(v, Path) else v)
def test_every_image_a_page_shows_exists(page, image):
    assert image.is_file(), f"{page.relative_to(DOCS)} shows {image}, which does not exist"


def test_every_screenshot_is_shown_somewhere():
    shown = {image for _page, image in _references()}
    unused = [p.relative_to(DOCS) for d in SCREENSHOT_DIRS if d.is_dir()
              for p in sorted(d.glob("*.png")) if p.resolve() not in shown]
    assert not unused, f"screenshots no page shows: {unused}"
