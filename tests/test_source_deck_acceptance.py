"""Every source type must produce a deck AERMOD accepts.

pyaermod exposes ten source types. Their writers were only ever checked
against pyaermod's own reader, so three of them emitted decks the real
AERMOD rejects outright -- an AREAPOLY missing its vertex count and
anchored on the polygon centroid instead of its first vertex, a
BUOYLINE whose BLPINPUT named no group, and an RLINEXT without the
ALPHA option AERMOD demands for it.

The check here is AERMOD's own setup pass (``RUNORNOT NOT``), which
parses the runstream, cross-checks keywords and reports fatal errors
without running the model. It needs the binary but no model run, so it
is fast enough to cover every source type on every commit.

Build AERMOD with ``scripts/build_aermod.sh``; these tests skip when it
is not on PATH.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.sources import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    LineSource,
    OpenPitSource,
    PointSource,
    RLineExtSource,
    RLineSource,
    VolumeSource,
)

AERMOD_EXE = shutil.which("aermod")
REPO_ROOT = Path(__file__).resolve().parent.parent
MET_DIR = (
    REPO_ROOT / "test_cases" / "aermet26135_aermod26135" / "meteorology"
)
SURFACE = MET_DIR / "aermet2.sfc"
PROFILE = MET_DIR / "aermet2.pfl"

pytestmark = [
    pytest.mark.skipif(
        AERMOD_EXE is None,
        reason="aermod not on PATH; build with scripts/build_aermod.sh",
    ),
    pytest.mark.skipif(
        not (SURFACE.is_file() and PROFILE.is_file()),
        reason=f"EPA meteorology not under {MET_DIR}",
    ),
]

# (label, source, needs_alpha)
SOURCE_CASES = [
    ("point", PointSource(
        "SRC1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
        stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0,
    ), False),
    ("area", AreaSource(
        "SRC1", 0.0, 0.0, release_height=5.0,
        initial_lateral_dimension=50.0, initial_vertical_dimension=60.0,
        emission_rate=1e-4,
    ), False),
    ("areacirc", AreaCircSource(
        "SRC1", 0.0, 0.0, release_height=5.0, radius=40.0,
        num_vertices=20, emission_rate=1e-4,
    ), False),
    ("areapoly", AreaPolySource(
        "SRC1", vertices=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        release_height=5.0, emission_rate=1e-4,
    ), False),
    ("volume", VolumeSource(
        "SRC1", 0.0, 0.0, release_height=10.0,
        initial_lateral_dimension=5.0, initial_vertical_dimension=4.0,
        emission_rate=2.0,
    ), False),
    ("line", LineSource(
        "SRC1", 0.0, 0.0, 100.0, 50.0, release_height=3.0,
        initial_lateral_dimension=8.0, emission_rate=0.5,
    ), False),
    ("rline", RLineSource(
        "SRC1", 0.0, 0.0, 100.0, 50.0, release_height=1.3,
        initial_lateral_dimension=10.0, initial_vertical_dimension=2.0,
        emission_rate=0.5,
    ), False),
    ("rlinext", RLineExtSource(
        "SRC1", 0.0, 0.0, 1.0, 100.0, 50.0, 2.0,
        emission_rate=0.5, road_width=10.0,
    ), True),
    ("buoyline", BuoyLineSource(
        "SRC1", 100.0, 10.0, 8.0, 5.0, 12.0, 30.0,
        line_segments=[
            BuoyLineSegment("SEG1", 0.0, 0.0, 100.0, 50.0, emission_rate=1.0)
        ],
    ), False),
    ("openpit", OpenPitSource(
        "SRC1", 0.0, 0.0, release_height=0.0, x_dimension=100.0,
        y_dimension=80.0, pit_volume=50000.0, emission_rate=1e-4,
    ), False),
]

# AERMOD stamps fatal errors as "<PATH> E<nnn>" in the message block.
_FATAL_RE = re.compile(r"^\s*(CO|SO|RE|ME|OU)\s+E(\d{3})\s+(.*)$", re.MULTILINE)


def build_deck(source, *, needs_alpha: bool) -> str:
    """A minimal single-source deck, set to check setup and stop."""
    project = AERMODProject(
        control=ControlPathway(
            title_one=f"deck acceptance: {type(source).__name__}",
            # RLINEXT is gated behind ALPHA, which DFAULT forbids.
            alpha=needs_alpha,
            regulatory_default=not needs_alpha,
        ),
        sources=SourcePathway(sources=[source]),
        receptors=ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(500.0, 500.0)]
        ),
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988,
        ),
        output=OutputPathway(),
    )
    deck = project.to_aermod_input()
    if "RUNORNOT" in deck:
        return re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", deck)
    return deck.replace("CO FINISHED", "   RUNORNOT NOT\nCO FINISHED")


def run_setup_check(deck: str, work: Path) -> list[str]:
    """Run AERMOD's setup pass; return its fatal error lines."""
    for met in (SURFACE, PROFILE):
        shutil.copy(met, work / met.name)
    (work / "aermod.inp").write_text(deck)
    subprocess.run(
        [AERMOD_EXE], cwd=str(work), capture_output=True, timeout=300,
    )
    out_path = work / "aermod.out"
    if not out_path.is_file():
        return ["AERMOD produced no aermod.out"]
    text = out_path.read_text(encoding="latin-1", errors="replace")
    block = text.split("FATAL ERROR MESSAGES")
    if len(block) < 2:
        return []
    return [
        f"{path} E{code} {msg.strip()}"
        for path, code, msg in _FATAL_RE.findall(block[1])
    ]


@pytest.mark.parametrize(
    "label,source,needs_alpha", SOURCE_CASES, ids=[c[0] for c in SOURCE_CASES]
)
def test_generated_deck_passes_aermod_setup(label, source, needs_alpha,
                                            tmp_path):
    deck = build_deck(source, needs_alpha=needs_alpha)
    errors = run_setup_check(deck, tmp_path)
    assert not errors, (
        f"AERMOD rejected the {label} deck:\n  "
        + "\n  ".join(errors)
        + f"\n\ndeck:\n{deck}"
    )


def test_every_source_type_is_covered():
    """The case list must not quietly fall behind pyaermod's source types."""
    import pyaermod.sources as sources_module

    exported = {
        name for name in dir(sources_module)
        if name.endswith("Source") and not name.startswith("_")
    }
    covered = {type(source).__name__ for _, source, _ in SOURCE_CASES}
    missing = exported - covered
    assert not missing, (
        f"source types with no deck-acceptance case: {sorted(missing)}"
    )


# ---------------------------------------------------------------------
# OU pathway: the output keywords have field-count-sensitive syntax
# ---------------------------------------------------------------------

OUTPUT_CASES = [
    ("period-files", OutputPathway(
        summary_file="s.dat", plot_file="p.dat", postfile="q.dat",
    )),
    ("short-term-files", OutputPathway(
        plot_file="p.dat", plot_file_averaging="1",
        postfile="q.dat", postfile_averaging="24",
    )),
    ("rank-one", OutputPathway(
        receptor_table_rank=1, plot_file="p.dat", plot_file_averaging="1",
    )),
    ("unformatted-post", OutputPathway(
        postfile="q.dat", postfile_averaging="1", postfile_format="UNFORM",
    )),
    ("tables-only", OutputPathway(
        receptor_table=True, receptor_table_rank=4,
        max_table=True, max_table_rank=20,
    )),
]


@pytest.mark.parametrize(
    "label,output", OUTPUT_CASES, ids=[c[0] for c in OUTPUT_CASES]
)
def test_output_pathway_deck_passes_aermod_setup(label, output, tmp_path):
    """PLOTFILE / POSTFILE / RECTABLE syntax varies with the period.

    PLOTFILE takes a rank for short-term averages and none for
    PERIOD/ANNUAL, POSTFILE takes a format keyword that must be PLOT or
    UNFORM, and a bare rank on RECTABLE selects only that rank rather
    than the range up to it. AERMOD counts fields, so each of these is a
    fatal error rather than something it shrugs off.
    """
    project = AERMODProject(
        control=ControlPathway(
            title_one=f"output acceptance: {label}",
            averaging_periods=["1", "24", "ANNUAL"],
        ),
        sources=SourcePathway(sources=[SOURCE_CASES[0][1]]),
        receptors=ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(500.0, 500.0)]
        ),
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988,
        ),
        output=output,
    )
    deck = re.sub(
        r"RUNORNOT\s+\w+", "RUNORNOT NOT", project.to_aermod_input()
    )
    errors = run_setup_check(deck, tmp_path)
    assert not errors, (
        f"AERMOD rejected the {label} output deck:\n  "
        + "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    )


def test_the_check_can_actually_fail(tmp_path):
    """Guard the assertion above against silently passing on everything.

    A deck with a deliberately broken SRCPARAM must be reported, or the
    parametrized tests prove nothing.
    """
    deck = build_deck(SOURCE_CASES[0][1], needs_alpha=False)
    broken = re.sub(r"SRCPARAM\s+SRC1.*", "   SRCPARAM  SRC1", deck)
    assert broken != deck, "failed to corrupt the deck"
    assert run_setup_check(broken, tmp_path), (
        "AERMOD reported no fatal error for a deck with an empty SRCPARAM"
    )
