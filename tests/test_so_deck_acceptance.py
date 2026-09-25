"""Every SO-pathway form added for source construction must pass AERMOD's
setup pass.

Tranche 2 of the reader work (AREAPOLY / BUOYLINE / RLINEXT construction,
the OLM, PSD and unit keywords, the RLINE barrier family, GASDEPOS as
AERMOD reads it, and the corrected URBANOPT / URBANSRC forms) was written
from ``soset.f`` and ``coset.f``; this is the check that the writer
reproduces the field layouts those routines parse. Each case builds one
project, writes it, and runs the binary with ``RUNORNOT NOT``; a fatal
setup error fails the case with AERMOD's own message.

Shares the harness of :mod:`tests.test_source_deck_acceptance`, and skips
with it when the binary or EPA's meteorology is missing.
"""

from __future__ import annotations

import re

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DiscreteReceptor,
    EmissionUnits,
    MeteorologyPathway,
    OutputPathway,
    OzoneData,
    ReceptorPathway,
    SolidBarrier,
    SolidBarrierSegment,
    SourceGroupDefinition,
    SourcePathway,
    VegetativeBarrier,
)
from pyaermod.sources import (
    AreaPolySource,
    BuoyLineSegment,
    BuoyLineSource,
    GasDepositionParams,
    PointSource,
    RLineExtSource,
    RLineSource,
)

from .test_source_deck_acceptance import (
    PROFILE,
    SURFACE,
    pytestmark,  # the binary/meteorology skip conditions
    run_setup_check,
)


def _stack(sid="SRC1", **kw):
    return PointSource(sid, 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
                       stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0, **kw)


def _rlinext(sid="ROAD1", **kw):
    return RLineExtSource(sid, 0.0, -100.0, 1.0, 0.0, 100.0, 1.0,
                          emission_rate=1.0, road_width=3.6, init_sigma_z=2.0, **kw)


def _control(**kw):
    kw.setdefault("title_one", "SO keyword acceptance")
    kw.setdefault("averaging_periods", ["1"])
    kw.setdefault("pollutant_id", "SO2")
    return ControlPathway(**kw)


def _alpha_flat(**kw):
    return _control(alpha=True, regulatory_default=False, **kw)


def _gasdep(**kw):
    """A gas dry-deposition run: AERMOD's SOCARD wants GDSEASON and
    GDLANUSE (or GASDEPVD) beside GASDEPOS, else E244 "Source parameters
    are missing or incomplete for DRYDEP" (EPA's testgas deck has both)."""
    kw.setdefault("calculate_dry_deposition", True)
    return _alpha_flat(gas_deposition_seasons=[4, 4, 4, 5, 1, 1, 1, 1, 1, 2, 3, 3],
                       gas_deposition_land_use=[4] * 36, **kw)


def _olm(**kw):
    return _control(
        pollutant_id="NO2", regulatory_default=False,
        chemistry=ChemistryOptions(
            method=ChemistryMethod.OLM, default_no2_ratio=0.1,
            ozone_data=OzoneData(uniform_value=40.0, uniform_units="PPB"), **kw),
    )


def _buoyline(group_id, seg_ids, y0=0.0):
    return BuoyLineSource(
        group_id, 100.0, 10.0, 8.0, 5.0, 12.0, 30.0,
        line_segments=[
            BuoyLineSegment(sid, 0.0, y0 + 100.0 * i, 100.0, y0 + 50.0 + 100.0 * i,
                            emission_rate=1.0, release_height=10.0)
            for i, sid in enumerate(seg_ids)
        ],
    )


# (label, control, sources) -- what the writer can now express
CASES = [
    ("areapoly-szinit", _control(), SourcePathway(sources=[AreaPolySource(
        "AREAP", vertices=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0),
                           (0.0, 20.0), (-10.0, 20.0), (-10.0, 10.0), (-10.0, 0.0)],
        release_height=1.0, emission_rate=1e-3, initial_vertical_dimension=2.0)])),
    # "ALL" is AERMOD's implicit single group: eight-field BLPINPUT, no BLPGROUP
    ("buoyline-implicit-all", _control(), SourcePathway(sources=[
        _buoyline("ALL", ["BLINE1", "BLINE2", "BLINE3"])])),
    ("buoyline-two-groups", _control(), SourcePathway(sources=[
        _buoyline("GRP1", ["L1A", "L1B"]), _buoyline("GRP2", ["L2A"], y0=1000.0)])),
    ("rlinext-elevation-two-barriers-depression", _alpha_flat(), SourcePathway(sources=[
        _rlinext(base_elevation=12.5, barrier_height_1=10.0, barrier_dcl_1=10.0,
                 barrier_height_2=6.0, barrier_dcl_2=-8.0,
                 depression_depth=-12.5, depression_wtop=50.0, depression_wbottom=25.0)])),
    ("rlinext-vbarrier-two", _alpha_flat(), SourcePathway(sources=[
        _rlinext(vegetative_barriers=[VegetativeBarrier(5.0, 5.0, 8.0, 6.0, 1.0),
                                      VegetativeBarrier(4.0, 4.0, -8.0, 5.0, 1.2)])])),
    ("sbarrier", _alpha_flat(), SourcePathway(
        sources=[_rlinext()],
        solid_barriers=[SolidBarrier("WALL1", [
            SolidBarrierSegment(-50.0, 10.0, 50.0, 10.0, 4.0),
            SolidBarrierSegment(50.0, 10.0, 60.0, 30.0, 4.0)])])),
    ("rlemconv", _control(regulatory_default=False), SourcePathway(
        sources=[RLineSource("ROAD1", 0.0, -100.0, 0.0, 100.0, emission_rate=3600.0,
                             initial_lateral_dimension=10.0)],
        rline_moves_units=True)),
    ("olmgroup-all-bare", _olm(olm_groups=[SourceGroupDefinition("ALL")]),
     SourcePathway(sources=[_stack("STK1"), _stack("STK2")])),
    ("olmgroup-range-and-no2ratio", _olm(olm_groups=[
        SourceGroupDefinition("OLM1", ["STK1-STK2"]), SourceGroupDefinition("OLM2", ["STK3"])]),
     SourcePathway(sources=[_stack("STK1", no2_ratio=0.2), _stack("STK2", no2_ratio=0.3),
                            _stack("STK3")])),
    ("psdgroup", _control(pollutant_id="NO2", regulatory_default=False, alpha=True,
                          beta=True, psd_credit=True,
                          chemistry=ChemistryOptions(
                              method=ChemistryMethod.PVMRM, default_no2_ratio=0.1,
                              ozone_data=OzoneData(uniform_value=40.0, uniform_units="PPB"))),
     SourcePathway(sources=[_stack("STK1"), _stack("STK2"), _stack("STK3")],
                   psd_groups=[SourceGroupDefinition("INCRCONS", ["STK1"]),
                               SourceGroupDefinition("RETRBASE", ["STK2"]),
                               SourceGroupDefinition("NONRBASE", ["STK3"])])),
    ("emisunit", _control(), SourcePathway(
        sources=[_stack()],
        emission_units=EmissionUnits(1.0e3, "GRAMS/SEC", "MILLIGRAMS/M**3"))),
    ("concunit-depounit", _gasdep(calculate_wet_deposition=True),
     SourcePathway(
        sources=[_stack(gas_deposition=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0))],
        concentration_units=EmissionUnits(1.0e6, "GRAMS/SEC", "MICROGRAMS/M**3"),
        deposition_units=EmissionUnits(3.6e9, "GRAM/SEC", "MICROGRAMS/M**2"))),
    ("gasdepos-epa-testgas", _gasdep(pollutant_id="OTHER"),
     SourcePathway(sources=[_stack(gas_deposition=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0))])),
    ("gasdepos-zero-lookup", _gasdep(pollutant_id="SO2"),
     SourcePathway(sources=[_stack(gas_deposition=GasDepositionParams(0.0, 0.0, 0.0, 0.0))])),
    ("urbanopt-urbansrc", _control(urban_option="METRO1", urban_population=700000.0),
     SourcePathway(sources=[_stack("STK1", is_urban=True), _stack("STK2")])),
    ("urbanopt-roughness", _control(urban_option="METRO1", urban_population=700000.0,
                                    urban_roughness=1.0, regulatory_default=False),
     SourcePathway(sources=[_stack("STK1", is_urban=True, urban_area_name="METRO1")])),
    ("buoyline-urban", _control(urban_option="INDY", urban_population=700000.0),
     SourcePathway(sources=[BuoyLineSource(
         "ALL", 648.0, 30.0, 150.0, 2.0, 37.5, 400.0, is_urban=True,
         line_segments=[BuoyLineSegment("2S26", 200.0, 700.0, 800.0, 600.0,
                                        emission_rate=100.0, release_height=30.0)])])),
]


def build_project(control, sources):
    return AERMODProject(
        control=control, sources=sources,
        receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 500.0)]),
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
        ),
        output=OutputPathway(),
    )


def setup_deck(control, sources) -> str:
    deck = build_project(control, sources).to_aermod_input()
    return re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", deck)


@pytest.mark.parametrize("label,control,sources", CASES, ids=[c[0] for c in CASES])
def test_so_keyword_deck_passes_aermod_setup(label, control, sources, tmp_path):
    deck = setup_deck(control, sources)
    errors = run_setup_check(deck, tmp_path)
    assert not errors, (
        f"AERMOD rejected the {label} deck:\n  " + "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    )


@pytest.mark.parametrize("label,mutate", [
    # The pre-2.1 URBANSRC "srcid name" form: the name is an undefined source (E300).
    ("urbansrc-with-area-name", lambda d: d.replace("   URBANSRC  STK1", "   URBANSRC  STK1  METRO1")),
    # The pre-2.1 URBANOPT "name population" form: E208 on the population field.
    ("urbanopt-name-first", lambda d: re.sub(r"URBANOPT\s+700000\.0\s+METRO1", "URBANOPT  METRO1  700000.0", d)),
])
def test_old_urban_forms_are_still_rejected(label, mutate, tmp_path):
    """The forms the writer used to emit must fail, or the cases above prove nothing."""
    deck = setup_deck(*next(c for c in CASES if c[0] == "urbanopt-urbansrc")[1:])
    broken = mutate(deck)
    assert broken != deck, "failed to corrupt the deck"
    assert run_setup_check(broken, tmp_path), f"AERMOD accepted the {label} form:\n{broken}"


def test_srcgroup_with_psdcredit_is_rejected(tmp_path):
    """PSDCREDIT forbids SRCGROUP (E105), which is why the writer swaps it for PSDGROUP."""
    control, sources = next(c for c in CASES if c[0] == "psdgroup")[1:]
    deck = setup_deck(control, sources).replace("SO FINISHED", "   SRCGROUP  ALL\nSO FINISHED")
    errors = run_setup_check(deck, tmp_path)
    assert any("E105" in e for e in errors), errors
