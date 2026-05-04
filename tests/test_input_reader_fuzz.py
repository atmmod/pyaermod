"""Fuzz tests: malformed .inp must fail predictably, not crash with
random TypeError / IndexError / KeyError.

The contract: parse_aermod_input either returns an AERMODProject (best-
effort partial parse) OR raises ValueError. Anything else (TypeError,
IndexError, KeyError, AttributeError, UnicodeDecodeError, etc.) is a
bug — it means a hostile or corrupt input could produce an unhandled
exception type that callers can't catch generically.

These tests run hypothesis strategies that mutate valid AERMOD input
in plausible-but-wrong ways to surface unhandled exception types.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyaermod.input_reader import parse_aermod_input

_VALID_BASE = """\
CO STARTING
   TITLEONE  fuzz base
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0  0
   SRCPARAM  S1  1  10  400  5  1
SO FINISHED
RE STARTING
   DISCCART  0  0  0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
OU FINISHED
"""


_SETTINGS = settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.mark.slow
@_SETTINGS
@given(st.text(max_size=200))
def test_pure_garbage_either_parses_or_value_error(text):
    """Random text input. Either parses (unlikely) or raises ValueError —
    nothing else."""
    try:
        parse_aermod_input(text)
    except ValueError:
        pass  # expected for garbage
    except (TypeError, IndexError, KeyError, AttributeError) as e:
        pytest.fail(f"Unhandled exception type {type(e).__name__}: {e}")


@pytest.mark.slow
@_SETTINGS
@given(
    st.integers(min_value=0, max_value=len(_VALID_BASE)),
    st.integers(min_value=0, max_value=len(_VALID_BASE)),
)
def test_truncated_input_predictable(start, end):
    """Random truncations of a valid input must raise ValueError or
    parse, never an unhandled exception type."""
    if start > end:
        start, end = end, start
    truncated = _VALID_BASE[start:end]
    try:
        parse_aermod_input(truncated)
    except ValueError:
        pass
    except (TypeError, IndexError, KeyError, AttributeError) as e:
        pytest.fail(
            f"Truncation [{start}:{end}] raised {type(e).__name__}: {e}"
        )


@pytest.mark.slow
@_SETTINGS
@given(
    st.lists(
        st.sampled_from([
            "CO STARTING", "CO FINISHED",
            "SO STARTING", "SO FINISHED",
            "RE STARTING", "RE FINISHED",
            "ME STARTING", "ME FINISHED",
            "OU STARTING", "OU FINISHED",
        ]),
        min_size=0, max_size=10,
    ),
)
def test_random_pathway_marker_sequence(markers):
    """Random orderings of pathway markers must raise ValueError, not
    something else."""
    text = "\n".join(markers)
    try:
        parse_aermod_input(text)
    except ValueError:
        pass
    except (TypeError, IndexError, KeyError, AttributeError) as e:
        pytest.fail(f"Markers={markers} -> {type(e).__name__}: {e}")


@pytest.mark.slow
@_SETTINGS
@given(
    st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd"),
                                   whitelist_characters=" "),
            min_size=1, max_size=20,
        ),
        min_size=0, max_size=8,
    ),
)
def test_random_so_block_lines(extra_lines):
    """Inject random gibberish lines into the SO block; reader must
    parse what it can OR raise ValueError, not crash with a
    KeyError/IndexError on a missing token."""
    extra = "\n".join(f"   {line}" for line in extra_lines)
    text = _VALID_BASE.replace(
        "SO STARTING", f"SO STARTING\n{extra}",
    )
    try:
        parse_aermod_input(text)
    except ValueError:
        pass
    except (TypeError, IndexError, KeyError, AttributeError) as e:
        pytest.fail(
            f"Extra SO lines {extra_lines!r} raised {type(e).__name__}: {e}"
        )


@pytest.mark.slow
@_SETTINGS
@given(
    st.text(min_size=1, max_size=80,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))),
)
def test_random_title(title):
    """Arbitrary TITLEONE text — even with weird whitespace — must round-
    trip into project.control.title_one (or fail with ValueError on
    structural break)."""
    text = _VALID_BASE.replace("TITLEONE  fuzz base",
                                f"TITLEONE  {title}")
    try:
        project = parse_aermod_input(text)
        # If it parsed, every non-whitespace token from the input title
        # must appear in the parsed title (the writer space-joins tokens
        # so NBSP and other whitespace types collapse to a single space).
        for tok in title.split():
            assert tok in project.control.title_one, (
                f"token {tok!r} dropped from title round-trip "
                f"(got {project.control.title_one!r})"
            )
    except ValueError:
        pass
    except (TypeError, IndexError, KeyError, AttributeError) as e:
        pytest.fail(
            f"Title {title!r} raised {type(e).__name__}: {e}"
        )
