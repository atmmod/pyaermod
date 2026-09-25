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


# ---------------------------------------------------------------------
# CO restart / NOx background / gas-deposition keywords and the OU
# design-value keywords: every form the writer can emit must pass setup
# ---------------------------------------------------------------------

def _control(**kwargs):
    kwargs.setdefault("title_one", "keyword acceptance")
    return ControlPathway(**kwargs)


def _stack():
    return SOURCE_CASES[0][1]


def _keyword_cases():
    from pyaermod.input_generator import (
        BackgroundSpec,
        ChemistryMethod,
        ChemistryOptions,
        GasDepositionDefaults,
        InitFile,
        MaxDailyContribution,
        MaxDailyFile,
        MultiYear,
        NOxBackground,
        OzoneData,
        SaveFile,
        TemporalValues,
    )

    def grsm(nox=None, oz=None):
        return _control(
            pollutant_id="NO2", averaging_periods=["1"], regulatory_default=False,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.GRSM, default_no2_ratio=0.1,
                ozone_data=oz or OzoneData(uniform_value=40.0, uniform_units="PPB"),
                nox_background=nox,
            ),
        )

    # (label, control, output, extra files to stage beside the deck)
    return [
        ("savefile-full", _control(
            averaging_periods=["1", "24"], pollutant_id="SO2",
            save_file=SaveFile("probe.sav", 30, "probe2.sav")), OutputPathway(), {}),
        ("savefile-bare", _control(
            averaging_periods=["1"], pollutant_id="SO2", save_file=SaveFile()),
         OutputPathway(), {}),
        ("initfile-named", _control(
            averaging_periods=["1"], pollutant_id="SO2", init_file=InitFile("probe.sav")),
         OutputPathway(), {"probe.sav": ""}),
        ("multyear-first-year", _control(
            averaging_periods=["24"], pollutant_id="PM10", multiyear=MultiYear("y1.sav")),
         OutputPathway(), {}),
        ("multyear-chained-h6h", _control(
            averaging_periods=["24"], pollutant_id="PM10",
            multiyear=MultiYear("y2.sav", "y1.sav", h6h=True)),
         OutputPathway(), {"y1.sav": ""}),
        ("nox-value-units", grsm(NOxBackground(value=10.0, value_units="PPB")), OutputPathway(), {}),
        ("nox-file-units-format", grsm(NOxBackground(
            hourly_file="nox.dat", file_units="PPB", file_format="FREE")),
         OutputPathway(), {"nox.dat": "99 01 01 01 20.0\n"}),
        ("nox-vals-hrofdy", grsm(NOxBackground(
            varying=TemporalValues("HROFDY", [20.0] * 24), units="UG/M3")), OutputPathway(), {}),
        ("nox-and-o3-sectors", grsm(
            nox=NOxBackground(
                sectors=[0.0, 180.0], units="PPB",
                by_sector={1: BackgroundSpec(value=20.0), 2: BackgroundSpec(
                    varying=TemporalValues("MONTH", [20.0] * 12))}),
            oz=OzoneData(
                sectors=[0.0, 90.0, 180.0, 270.0], units="PPB",
                by_sector={1: BackgroundSpec(value=40.0), 2: BackgroundSpec(value=45.0, value_units="PPB"),
                           3: BackgroundSpec(varying=TemporalValues("SEASON", [40, 50, 60, 45])),
                           4: BackgroundSpec(hourly_file="o3.dat", file_units="PPB")}),
        ), OutputPathway(), {"o3.dat": "99 01 01 01 40.0\n"}),
        ("ozone-file-value-and-format", _control(
            pollutant_id="NO2", averaging_periods=["1"], regulatory_default=False,
            chemistry=ChemistryOptions(method=ChemistryMethod.OLM, default_no2_ratio=0.1, ozone_data=OzoneData(
                uniform_value=40.0, uniform_units="PPB", ozone_file="o3.dat",
                ozone_file_units="PPB", ozone_file_format="(i2,3i3,f9.3)"))),
         OutputPathway(), {"o3.dat": "99  1  1  1   40.000\n"}),
        ("gasdep-defaults", _control(
            averaging_periods=["1"], pollutant_id="SO2", alpha=True, regulatory_default=False,
            calculate_dry_deposition=True,
            gas_deposition_defaults=GasDepositionDefaults(0.5, 0.5, 0.5, "SO2"),
            gas_deposition_seasons=[4, 4, 4, 5, 1, 1, 1, 1, 1, 2, 3, 3],
            gas_deposition_land_use=[4] * 36),
         OutputPathway(), {"__gasdepos__": True}),
        ("gasdep-velocity", _control(
            averaging_periods=["1"], pollutant_id="SO2", alpha=True, regulatory_default=False,
            calculate_dry_deposition=True, gas_deposition_velocity=0.01),
         OutputPathway(), {}),
        ("design-value-rank-form", _control(
            averaging_periods=["1"], pollutant_id="SO2"),
         OutputPathway(receptor_table_rank=4, file_format="EXP",
                       max_daily_files=[MaxDailyFile("ALL", "md.dat")],
                       max_daily_by_year_files=[MaxDailyFile("ALL", "my.dat", 52)],
                       max_daily_contributions=[MaxDailyContribution("ALL", 4, "mdc.dat", lower_rank=4)]),
         {}),
        ("design-value-thresh-form", _control(
            averaging_periods=["1"], pollutant_id="NO2"),
         OutputPathway(receptor_table_rank=13, file_format="FIX",
                       max_daily_contributions=[MaxDailyContribution(
                           "ALL", 8, "mdc.dat", threshold=188.0, file_unit=53)]),
         {}),
    ]


KEYWORD_CASES = _keyword_cases()


@pytest.mark.parametrize(
    "label,control,output,extra", KEYWORD_CASES, ids=[c[0] for c in KEYWORD_CASES]
)
def test_keyword_deck_passes_aermod_setup(label, control, output, extra, tmp_path):
    """Restart, NOx/O3 background, gas-deposition and design-value keywords.

    Each case writes one form the model can express and runs AERMOD's
    setup pass on it. The field layouts came from coset.f and ouset.f
    (scripts/keyword_oracle.py prints them); this is the check that the
    writer reproduces them.
    """
    from pyaermod.sources import GasDepositionParams

    source = _stack()
    if extra.pop("__gasdepos__", False):
        # EPA's testgas deck: benzene diffusivities, cuticular resistance
        # and Henry's law constant (Da, Dw, rcl, Henry). pyaermod's
        # validator now reads the fields as AERMOD does, so this deck is
        # validated like every other one before AERMOD sees it.
        source = PointSource(
            "SRC1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
            stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0,
            gas_deposition=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0),
        )
    for name, content in extra.items():
        (tmp_path / name).write_text(content)
    project = AERMODProject(
        control=control,
        sources=SourcePathway(sources=[source]),
        receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 500.0)]),
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988,
        ),
        output=output,
    )
    deck = re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", project.to_aermod_input())
    errors = run_setup_check(deck, tmp_path)
    assert not errors, (
        f"AERMOD rejected the {label} deck:\n  " + "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    )


def test_keyword_check_can_fail(tmp_path):
    """The old NOXVALUE-for-a-file form must be reported, or the cases prove nothing."""
    control = KEYWORD_CASES[5][1]
    project = AERMODProject(
        control=control, sources=SourcePathway(sources=[_stack()]),
        receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 500.0)]),
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988),
        output=OutputPathway(),
    )
    deck = re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", project.to_aermod_input())
    broken = deck.replace("   NOXVALUE  10  PPB", "   NOXVALUE  nox.dat")
    assert broken != deck
    assert run_setup_check(broken, tmp_path)
