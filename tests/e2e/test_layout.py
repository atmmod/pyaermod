"""Every step fits the window, on a desktop (1280 x 900) and on a phone (390 x 844).

PLAN-gui.md, WP-G3 acceptance: no control is cut off at either size. For
every step, with a source and a receptor grid entered, the page must not
scroll sideways, and every button, input, check box and tab on it must lie
within the window (a wide table may scroll inside its own frame). Each
step leaves a screenshot at each size, which is the evidence reviewers
look at.
"""

from __future__ import annotations

import pytest

from .reference import GRID, STACK

pytestmark = pytest.mark.e2e

STEPS = ("Project", "Sources", "Receptors", "Meteorology", "Output", "Review & Run", "Results")

SIZES = {"desktop": {"width": 1280, "height": 900}, "phone": {"width": 390, "height": 844}}

# Controls outside the window, ignoring those inside a table's own
# horizontal scroller and those in a step list folded away off-screen.
_OUTSIDE = """() => {
  const width = document.documentElement.clientWidth;
  const outside = [];
  const controls = 'button, input, textarea, [role=combobox], [role=tab], [role=checkbox]';
  for (const el of document.querySelectorAll(controls)) {
    const box = el.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    if (el.closest('.q-table__middle')) continue;
    if (el.closest('.q-drawer') && box.right <= 0) continue;
    if (box.left < -1 || box.right > width + 1) {
      const name = el.getAttribute('aria-label') || el.innerText || el.getAttribute('name') || el.tagName;
      outside.push(`${name.trim().slice(0, 40)} [${Math.round(box.left)}, ${Math.round(box.right)}]`);
    }
  }
  return {pageWidth: document.documentElement.scrollWidth, width, outside};
}"""


@pytest.mark.parametrize("size", list(SIZES))
def test_every_step_fits_the_window(gui, step, size):
    gui.page.set_viewport_size(SIZES[size])
    gui.open()
    gui.sources.add_point_source(**STACK)
    gui.receptors.add_polar_grid(**GRID)
    problems = []
    for name in STEPS:
        gui.open_step(name)
        step(f"{size}_{name}")
        found = gui.page.evaluate(_OUTSIDE)
        if found["pageWidth"] > found["width"]:
            problems.append(f"{name}: the page is {found['pageWidth']} px wide in a "
                            f"{found['width']} px window")
        problems.extend(f"{name}: {control} lies outside the window"
                        for control in found["outside"])
    assert not problems, "\n".join(problems)
