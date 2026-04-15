"""Verify the shipped user-facing docs exist and are non-trivial."""

from __future__ import annotations

from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).parent.parent / "docs"

REQUIRED_DOCS = [
    "quickstart.md",
    "gui-guide.md",
    "architecture.md",
    "aermet-tuning-guide.md",
    "aermap-troubleshooting.md",
    "common-errors.md",
    "regulatory-matrix.md",
    "index.md",
]


@pytest.mark.parametrize("name", REQUIRED_DOCS)
def test_doc_exists_and_is_non_trivial(name):
    path = DOCS_DIR / name
    assert path.exists(), f"missing doc: {name}"
    text = path.read_text(encoding="utf-8")
    # Arbitrary floor — each doc should be at least a few paragraphs
    assert len(text) > 800, f"{name} looks thin ({len(text)} chars)"
    assert text.startswith("#"), f"{name} should start with a top-level header"


def test_index_links_to_practitioner_guides():
    text = (DOCS_DIR / "index.md").read_text()
    for name in ("aermet-tuning-guide.md", "aermap-troubleshooting.md",
                 "common-errors.md", "regulatory-matrix.md"):
        assert name in text, f"index.md missing link to {name}"
