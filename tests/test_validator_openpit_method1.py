"""The validator's OPENPIT, Method 1 and DFAULT/FLAT rules, pinned to AERMOD.

Every rule here is read off AERMOD v26135's Fortran (the line numbers
refer to ``aermod_source_v26135``) and checked against real runs of that
program: ``tests/fixtures/validator_openpit/`` holds the decks and the
``aermod.out`` AERMOD wrote for each (see its README). The parity tests
read each deck back, validate it, and require pyaermod to name exactly the
message codes AERMOD raised; the rule tests pin each boundary.

- soset.f OPARM, lines 3530-3595: OPENPIT ``SRCPARAM`` limits (W320),
  negative values (E209), aspect ratio (W392), release height above the
  effective depth (E322).
- calc1.f PITCALC, lines 4859-4892: receptors inside the pit are skipped.
- soset.f SRCQA, lines 1211-1231: category counts (E240) and the
  mass-fraction sum within 2% (W330); the categories have no fixed limit.
- soset.f INPPDM 4920-4922 (E335), INPPHI 5048-5050 (E332), INPPDN
  5168-5173 (E334, W334).
- coset.f MODOPT, lines 1622-1683: DFAULT overrides FLAT (W206).
"""

import re
from collections import Counter
from pathlib import Path

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PolarGrid,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
)
from pyaermod.input_reader import read_aermod_input
from pyaermod.runner import parse_aermod_messages
from pyaermod.sources import ParticleDepositionParams
from pyaermod.validator import ValidationResult, Validator

FIXTURES = Path(__file__).parent / "fixtures" / "validator_openpit"

#: The AERMOD message codes this package's rules stand for.
RULE_CODES = {"W206", "E209", "E240", "W320", "E322", "E332", "E334",
              "W334", "E335", "W330", "W392"}

_CODE = re.compile(r"\(AERMOD ([EW]\d{3})\)")


def _codes(result: ValidationResult) -> Counter:
    """The AERMOD codes pyaermod's findings name, counted."""
    return Counter(m for e in result.errors for m in _CODE.findall(e.message))


def _findings(result, code, pathway=None):
    return [e for e in result.errors
            if f"(AERMOD {code})" in e.message
            and (pathway is None or e.pathway == pathway)]


def _project(sources, receptors=None, **control):
    control.setdefault("regulatory_default", False)
    return AERMODProject(
        control=ControlPathway(title_one="d2", pollutant_id="PM10",
                               averaging_periods=["1", "PERIOD"],
                               calculate_dry_deposition=True, **control),
        sources=SourcePathway(sources=list(sources)),
        receptors=receptors or ReceptorPathway(
            discrete_receptors=[DiscreteReceptor(1000.0, 1000.0)]),
        meteorology=MeteorologyPathway(surface_file="AERMET2.SFC",
                                       profile_file="AERMET2.PFL"),
        output=OutputPathway(),
    )


def _pit(**kw):
    geom = dict(source_id="PIT", x_coord=-300.0, y_coord=-200.0,
                emission_rate=1e-5, release_height=0.0,
                x_dimension=600.0, y_dimension=400.0, pit_volume=2.4e7)
    # _project turns DDEP on, and a source without particle categories or
    # gas deposition parameters is then E242 (soset.f SRCQA; the validator
    # says so). The recorded decks give each pit these five categories.
    geom.setdefault("particle_deposition", _pm([1, 2.5, 5, 10, 20]))
    geom.update(kw)
    return OpenPitSource(**geom)


def _pm(diameters, fractions=None, densities=None):
    n = len(diameters)
    return ParticleDepositionParams(
        diameters=list(diameters),
        mass_fractions=list(fractions) if fractions is not None else [1.0 / n] * n,
        densities=list(densities) if densities is not None else [2.65] * n,
    )


# ---------------------------------------------------------------------------
# Parity with the recorded AERMOD runs
# ---------------------------------------------------------------------------

def _aermod_rule_codes(case):
    return {m.code for m in parse_aermod_messages(FIXTURES / case / "aermod.out")
            if m.code in RULE_CODES}


#: Every recorded case. The recordings are force-added past .gitignore's
#: ``*.inp``/``*.out``; a checkout without them must fail here rather than
#: turn the parity test into an empty, skipped parametrize.
CASES = sorted(p.name for p in FIXTURES.iterdir() if (p / "aermod.inp").is_file())


def test_every_recorded_case_is_present():
    assert CASES == ["bins25", "dfault_elev", "dfault_flat", "dfault_flatsrcs",
                     "inpit", "inpit_rotated", "method1", "openpit_errors",
                     "openpit_limits", "openpit_tiny_dimension"]
    for case in CASES:
        assert (FIXTURES / case / "aermod.out").is_file(), case


@pytest.mark.parametrize("case", CASES)
def test_validator_names_the_codes_aermod_raised(case):
    """Reading each recorded deck back, the validator raises exactly the
    rule codes AERMOD v26135 raised for it, and no others."""
    result = Validator.validate(read_aermod_input(FIXTURES / case / "aermod.inp"))
    assert set(_codes(result)) & RULE_CODES == _aermod_rule_codes(case)


def test_recorded_runs_are_what_the_rules_claim():
    """Guard the fixtures themselves: the runs that should fail did, and
    the rest (warnings only) ran to completion."""
    for case in ("method1", "openpit_errors", "openpit_tiny_dimension"):
        text = (FIXTURES / case / "aermod.out").read_text()
        assert "AERMOD Finishes UN-successfully" in text, case
    for case in ("openpit_limits", "inpit", "inpit_rotated", "bins25",
                 "dfault_flat", "dfault_flatsrcs", "dfault_elev"):
        text = (FIXTURES / case / "aermod.out").read_text()
        assert "*** AERMOD Finishes Successfully ***" in text, case


# ---------------------------------------------------------------------------
# E322: release height above the effective depth (soset.f 3591-3595)
# ---------------------------------------------------------------------------

class TestE322ReleaseHeightAboveDepth:

    def test_is_an_error(self):
        # Deff = 1e6 / (100 * 100) = 100 m; soset.f 3591-3592: IF (AHS .GT. EFFDEP)
        result = Validator.validate(_project([_pit(
            release_height=100.1, x_dimension=100.0, y_dimension=100.0, pit_volume=1e6)]))
        [finding] = _findings(result, "E322")
        assert finding.severity == "error"
        assert finding.field == "release_height"
        assert not result.is_valid

    def test_equal_to_the_depth_is_accepted(self):
        # The recorded PEQ source: Hs = Deff = 100 m, no E322.
        result = Validator.validate(_project([_pit(
            release_height=100.0, x_dimension=100.0, y_dimension=100.0, pit_volume=1e6)]))
        assert not _findings(result, "E322")

    def test_write_refuses_the_deck(self, tmp_path):
        # The audit's D_hs_gt_depth deck: 150 m release in a 100 m-deep pit,
        # which AERMOD refused at setup while pyaermod only warned.
        project = _project([_pit(release_height=150.0,
                                 particle_deposition=_pm([1, 2.5, 5, 10, 20]))])
        with pytest.raises(ValueError, match="E322"):
            project.write(tmp_path / "aermod.inp")

    def test_uses_the_substituted_dimension(self):
        # OPARM raises XINIT = 0 to 1e-5 m before computing Deff, so a zero
        # width gives a very deep pit rather than a zero-depth one.
        result = Validator.validate(_project([_pit(x_dimension=0.0, release_height=50.0)]))
        assert not _findings(result, "E322")

    def test_depth_follows_the_substitution_below_1e_5_m(self):
        # The recorded openpit_tiny_dimension run: soset.f 3549-3553 raises
        # XINIT = 5e-6 m to 1e-5 m, then 3591 computes Deff = 1e-3 / (1e-5 *
        # 100) = 1 m, so Hs = 1.5 m is E322. The raw width would give 2 m.
        result = Validator.validate(_project([_pit(
            x_dimension=5e-6, y_dimension=100.0, pit_volume=1e-3, release_height=1.5)]))
        [finding] = _findings(result, "E322")
        assert "= 1.00 m" in finding.message
        assert Counter(_codes(result)) == Counter({"W320": 1, "W392": 1, "E322": 1})


# ---------------------------------------------------------------------------
# W320 / E209 / W392: OPENPIT SRCPARAM limits (soset.f 3530-3588)
# ---------------------------------------------------------------------------

class TestOpenPitParameterLimits:

    def _w320(self, **kw):
        return _findings(Validator.validate(_project([_pit(**kw)])), "W320")

    def test_zero_emission_rate_warns(self):
        # soset.f 3530-3533
        [w] = self._w320(emission_rate=0.0)
        assert w.field == "emission_rate" and w.severity == "warning"

    def test_release_height_above_200_m_warns(self):
        # soset.f 3538-3540 (the E324 branch at 3541 is unreachable); a 300 m-deep pit keeps E322 out of the way
        [w] = self._w320(release_height=210.0, x_dimension=100.0,
                         y_dimension=100.0, pit_volume=3e6)
        assert w.field == "release_height"
        assert not self._w320(release_height=200.0, x_dimension=100.0,
                              y_dimension=100.0, pit_volume=3e6)

    @pytest.mark.parametrize("field_name", ["x_dimension", "y_dimension"])
    def test_dimension_above_2000_m_warns(self, field_name):
        # soset.f 3554-3556 (XINIT) and 3567-3569 (YINIT)
        other = "y_dimension" if field_name == "x_dimension" else "x_dimension"
        [w] = self._w320(**{field_name: 2100.0, other: 300.0, "pit_volume": 6.3e7})
        assert w.field == field_name
        assert not self._w320(**{field_name: 2000.0, other: 300.0, "pit_volume": 6.3e7})

    @pytest.mark.parametrize("value", [0.0, 5e-6])
    def test_dimension_below_1e_5_m_warns_rather_than_fails(self, value):
        # soset.f 3549-3553: W320, then XINIT = 1.0D-5; the recorded PX0 source
        # (XINIT = 0) ran to completion.
        result = Validator.validate(_project([_pit(x_dimension=value)]))
        [w] = _findings(result, "W320")
        assert w.field == "x_dimension" and w.severity == "warning"
        assert _findings(result, "W392")  # 100 / 1e-5 is far above 10
        assert result.is_valid

    @pytest.mark.parametrize("field_name", ["x_dimension", "y_dimension"])
    def test_negative_dimension_is_e209(self, field_name):
        # soset.f 3546-3548 and 3559-3561
        result = Validator.validate(_project([_pit(**{field_name: -100.0})]))
        [e] = _findings(result, "E209")
        assert e.field == field_name and e.severity == "error"

    def test_negative_release_height_is_e209(self):
        # soset.f 3535-3537
        result = Validator.validate(_project([_pit(release_height=-1.0)]))
        [e] = _findings(result, "E209")
        assert e.field == "release_height"

    @pytest.mark.parametrize("volume", [0.0, -1.0])
    def test_volume_at_or_below_zero_is_e209(self, volume):
        # soset.f 3577-3581
        result = Validator.validate(_project([_pit(pit_volume=volume)]))
        [e] = _findings(result, "E209")
        assert e.field == "pit_volume"

    @pytest.mark.parametrize("angle, warns", [(190.0, True), (-181.0, True),
                                              (180.0, False), (-180.0, False)])
    def test_angle_beyond_180_warns(self, angle, warns):
        # soset.f 3572-3575: DABS(AANGLE) .GT. 180
        found = [w for w in self._w320(angle=angle) if w.field == "angle"]
        assert bool(found) is warns

    @pytest.mark.parametrize("x_dim, warns", [(1200.0, True), (1000.0, False)])
    def test_aspect_ratio_above_10_warns(self, x_dim, warns):
        # soset.f 3584-3588: W392 when either ratio .GT. 10
        result = Validator.validate(_project([_pit(x_dimension=x_dim, y_dimension=100.0,
                                                   pit_volume=1.2e7)]))
        assert bool(_findings(result, "W392")) is warns

    def test_a_valid_pit_raises_nothing(self):
        result = Validator.validate(_project([_pit()]))
        assert not [e for e in result.errors if e.pathway == "OpenPitSource(PIT)"]


# ---------------------------------------------------------------------------
# Receptors inside the pit (calc1.f 4859-4892)
# ---------------------------------------------------------------------------

def _period_table(case):
    """(x, y) -> PERIOD concentration from a recorded run's discrete table."""
    text = (FIXTURES / case / "aermod.out").read_text()
    block = text.split("*** THE PERIOD", 1)[1].split("*** AERMOD - VERSION", 1)[0]
    values = {}
    for line in block.splitlines():
        for x, y, conc in re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)", line):
            values[(float(x), float(y))] = float(conc)
    return values


def _inside_warning(result, source_id="PIT"):
    return [e for e in result.errors
            if e.pathway == f"OpenPitSource({source_id})" and e.field == "receptors"]


class TestReceptorsInsideThePit:

    @pytest.mark.parametrize("case", ["inpit", "inpit_rotated"])
    def test_flags_exactly_the_receptors_aermod_zeroed(self, case):
        # PITCALC skips a receptor PNPOLY puts strictly inside (INOUT > 0);
        # one on the edge or a vertex (INOUT = 0) is modelled.
        table = _period_table(case)
        zeroed = sorted(p for p, conc in table.items() if conc == 0.0)
        assert len(zeroed) == 2 and len(table) > len(zeroed)
        # AERMOD's own list: inpsum.f CHKREC names each receptor PNPOLY puts
        # inside the pit, with OPENPIT in the distance column (FORMAT 9004).
        listed = sorted((float(x), float(y)) for x, y in re.findall(
            r"^\s+PIT\s+(-?\d+\.\d)\s+(-?\d+\.\d)\s+OPENPIT\s*$",
            (FIXTURES / case / "aermod.out").read_text(), re.MULTILINE))
        assert listed == zeroed
        result = Validator.validate(read_aermod_input(FIXTURES / case / "aermod.inp"))
        [warning] = _inside_warning(result)
        assert warning.severity == "warning"
        assert warning.message.startswith(f"{len(zeroed)} receptor(s) lie inside the pit")
        for x, y in zeroed:
            assert f"({x:.1f}, {y:.1f})" in warning.message

    def test_counts_the_grid_nodes_inside(self):
        # The audit's 21 x 21, 100 m grid around a 600 x 400 m pit: AERMOD
        # reported 0 at exactly the 5 x 3 interior nodes (E_25bins).
        grid = CartesianGrid(grid_name="G1", x_init=-1000, x_num=21, x_delta=100,
                             y_init=-1000, y_num=21, y_delta=100)
        result = Validator.validate(_project([_pit()], ReceptorPathway(cartesian_grids=[grid])))
        [warning] = _inside_warning(result)
        assert warning.message.startswith("15 receptor(s)")
        assert "and 12 more" in warning.message

    def test_edge_and_vertex_receptors_are_not_flagged(self):
        receptors = ReceptorPathway(discrete_receptors=[
            DiscreteReceptor(300.0, 0.0), DiscreteReceptor(-300.0, -200.0),
            DiscreteReceptor(301.0, 0.0)])
        assert not _inside_warning(Validator.validate(_project([_pit()], receptors)))

    def test_rotated_pit_bounding_box_corners_are_not_flagged(self):
        # The inpit_rotated pit (30 degrees about its SW corner, soset.f
        # 3604-3623) spans x 0-720, y -300-346; (20, -250) and (700, 300) lie
        # in that box but outside the pit, so PNPOLY puts them outside and
        # PITCALC models them (calc1.f 4858-4860). Only (400, 100) is inside.
        pit = _pit(x_coord=0.0, y_coord=0.0, angle=30.0)
        receptors = ReceptorPathway(discrete_receptors=[
            DiscreteReceptor(20.0, -250.0), DiscreteReceptor(700.0, 300.0),
            DiscreteReceptor(400.0, 100.0)])
        [warning] = _inside_warning(Validator.validate(_project([pit], receptors)))
        assert warning.message.startswith("1 receptor(s) lie inside the pit: (400.0, 100.0);")

    def test_polar_grid_centred_on_the_pit(self):
        # GRIDPOLR ORIG PIT centres the rings on the pit's SW corner
        # (reset.f 1147-1148, 1485-1486); the 100 m ring at 45 degrees lands inside.
        polar = PolarGrid(grid_name="P1", origin_source_id="PIT",
                          dist_init=100.0, dist_num=1, dist_delta=100.0,
                          dir_init=45.0, dir_num=4, dir_delta=90.0)
        result = Validator.validate(_project([_pit()], ReceptorPathway(polar_grids=[polar])))
        [warning] = _inside_warning(result)
        assert warning.message.startswith("1 receptor(s)")
        assert "(-229.3, -129.3)" in warning.message

    def test_polar_grid_on_explicit_origin(self):
        polar = PolarGrid(grid_name="P1", x_origin=0.0, y_origin=0.0,
                          dist_init=50.0, dist_num=2, dist_delta=1000.0,
                          dir_init=0.0, dir_num=4, dir_delta=90.0)
        result = Validator.validate(_project([_pit()], ReceptorPathway(polar_grids=[polar])))
        [warning] = _inside_warning(result)
        assert warning.message.startswith("4 receptor(s)")

    def test_polar_grid_on_an_unknown_source_is_left_to_aermod(self):
        polar = PolarGrid(grid_name="P1", origin_source_id="NOSUCH",
                          dist_init=10.0, dist_num=1, dist_delta=10.0,
                          dir_init=0.0, dir_num=1, dir_delta=10.0)
        result = Validator.validate(_project([_pit()], ReceptorPathway(polar_grids=[polar])))
        assert not _inside_warning(result)

    def test_distant_grid_costs_nothing_and_flags_nothing(self):
        far = CartesianGrid(grid_name="FAR", x_init=10_000, x_num=300, x_delta=10,
                            y_init=-1000, y_num=300, y_delta=10)
        result = Validator.validate(_project([_pit()], ReceptorPathway(cartesian_grids=[far])))
        assert not _inside_warning(result)

    def test_negative_dimensions_skip_the_check(self):
        result = Validator.validate(_project([_pit(x_dimension=-600.0)]))
        assert not _inside_warning(result)


# ---------------------------------------------------------------------------
# Method 1 particle arrays: PARTDIAM / MASSFRAX / PARTDENS
# ---------------------------------------------------------------------------

class TestMethod1ParticleArrays:

    def _result(self, pm):
        return Validator.validate(_project([_pit(particle_deposition=pm)]))

    def test_twenty_five_categories_validate(self, tmp_path):
        # No fixed category limit: soset.f allocates NPDMAX to the deck's own
        # count (the "shouldn't occur" E290 branches at 1232-1237, 4929-4933),
        # and the recorded bins25 deck ran to completion.
        pm = _pm([0.5 + i for i in range(25)])
        project = _project([_pit(particle_deposition=pm)])
        result = Validator.validate(project)
        assert result.is_valid
        assert not [e for e in result.errors if "particle_deposition" in e.field]
        project.write(tmp_path / "aermod.inp")
        assert "24.5" in (tmp_path / "aermod.inp").read_text()

    def test_the_recorded_25_category_deck_validates(self):
        result = Validator.validate(read_aermod_input(FIXTURES / "bins25" / "aermod.inp"))
        assert result.is_valid

    @pytest.mark.parametrize("diameter, bad", [(0.001, True), (0.0011, False),
                                               (1000.0, False), (1001.0, True),
                                               (0.0, True), (-1.0, True)])
    def test_e335_diameter_range(self, diameter, bad):
        # soset.f 4920-4922: DNUM .LE. 0.001 .OR. DNUM .GT. 1000.0
        result = self._result(_pm([diameter, 10.0]))
        assert bool(_findings(result, "E335")) is bad

    @pytest.mark.parametrize("diameter, written, bad", [
        (1000.4, "1000", False),   # recorded method1: 1000 accepted
        (1000.5, "1000", False),
        (0.0010004, "0.001", True),  # recorded method1: 0.001 is E335
    ])
    def test_e335_checks_the_diameter_as_written(self, tmp_path, diameter, written, bad):
        # The writer puts PARTDIAM to 4 significant figures, and INPPDM tests
        # the number in the deck, not the one in Python.
        project = _project([_pit(particle_deposition=_pm([diameter, 5.0]))])
        assert f"PARTDIAM  PIT      {written}  5\n" in project.to_aermod_input(validate=False)
        assert bool(_findings(Validator.validate(project), "E335")) is bad

    @pytest.mark.parametrize("fractions, bad", [([1.1, -0.1], True), ([1.0, 0.0], False),
                                                ([0.5, 0.5], False)])
    def test_e332_each_fraction_in_0_to_1(self, fractions, bad):
        # soset.f 5048-5050: DNUM .LT. 0 .OR. DNUM .GT. 1
        result = self._result(_pm([1.0, 2.0], fractions))
        found = _findings(result, "E332")
        assert bool(found) is bad
        if bad:
            assert found[0].severity == "error"

    @pytest.mark.parametrize("fractions, warns", [
        ([0.49, 0.49], False),    # sum 0.98: SRCQA tests .LT. 0.98
        ([0.51, 0.51], False),    # sum 1.02: .GT. 1.02
        ([0.4925, 0.4925], False),  # 0.985: warned under the old 1% rule
        ([0.475, 0.5], True),     # 0.975, the recorded S4
        ([0.521, 0.5], True),     # 1.021, the recorded S5
    ])
    def test_w330_sum_within_two_percent(self, fractions, warns):
        # soset.f 1221-1231: ATOT .LT. 0.98 .OR. ATOT .GT. 1.02
        result = self._result(_pm([1.0, 2.0], fractions))
        found = [e for e in result.errors if e.field == "particle_deposition.mass_fractions"]
        assert bool(found) is warns
        if warns:
            [w] = found
            assert w.severity == "warning" and "(AERMOD W330)" in w.message

    def test_e334_density_at_or_below_zero(self):
        # soset.f 5168-5170
        [e] = _findings(self._result(_pm([1.0, 2.0], densities=[0.0, 2.65])), "E334")
        assert e.severity == "error"

    @pytest.mark.parametrize("density, warns", [(0.1, True), (0.05, True), (0.11, False),
                                                # written as 0.1 (4 significant
                                                # figures), which W334 flags
                                                (0.10004, True)])
    def test_w334_density_at_or_below_0_1(self, density, warns):
        # soset.f 5171-5173: ELSE IF (DNUM .LE. 0.1D0) -> W334
        result = self._result(_pm([1.0, 2.0], densities=[density, 2.65]))
        found = _findings(result, "W334")
        assert bool(found) is warns
        assert result.is_valid

    def test_w330_sums_the_fractions_as_written(self):
        # MASSFRAX is written to 6 decimals: 0.4899996 twice sums to
        # 0.9799992 in Python but reads back as 0.49 + 0.49 = 0.98, which
        # SRCQA (soset.f 1222) does not warn about.
        result = self._result(_pm([1.0, 2.0], [0.4899996, 0.4899996]))
        assert not _findings(result, "W330")

    def test_e240_category_counts_disagree(self):
        # soset.f 1216-1219
        pm = ParticleDepositionParams(diameters=[1, 2, 3], mass_fractions=[0.5, 0.5],
                                      densities=[2.65, 2.65, 2.65])
        [e] = _findings(self._result(pm), "E240")
        assert e.severity == "error"


# ---------------------------------------------------------------------------
# W206: DFAULT overrides FLAT (coset.f 1622-1683)
# ---------------------------------------------------------------------------

class TestDfaultWithFlat:

    def _w206(self, **control):
        return _findings(Validator.validate(_project([_pit()], **control)), "W206")

    def test_default_control_pathway_warns(self):
        # coset.f 1622-1683. ControlPathway defaults to FLAT with regulatory_default=True, which
        # writes MODELOPT ... FLAT DFAULT: AERMOD runs it in ELEV (dfault_flat).
        [w] = _findings(Validator.validate(AERMODProject(
            control=ControlPathway(title_one="x"),
            sources=SourcePathway(sources=[_pit()]),
            receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(1e3, 1e3)]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )), "W206")
        assert w.severity == "warning" and w.pathway == "ControlPathway"
        # The warning is about the deck pyaermod writes: read_aermod_input
        # maps a MODELOPT with no terrain token to FLAT, and the writer
        # then writes FLAT DFAULT, which AERMOD itself would not see.
        assert "pyaermod writes FLAT with DFAULT" in w.message

    def test_flatsrcs_warns(self):
        # FLAT ELEV DFAULT: the FLAT token still draws W206 (dfault_flatsrcs)
        assert self._w206(regulatory_default=True, terrain_type=TerrainType.FLATSRCS)

    def test_flat_in_extra_options_warns(self):
        assert self._w206(regulatory_default=True, terrain_type=TerrainType.ELEVATED,
                          extra_model_options=["FLAT"])

    def test_elevated_does_not_warn(self):
        # dfault_elev: MODELOPT CONC ELEV DFAULT raises no W206
        assert not self._w206(regulatory_default=True, terrain_type=TerrainType.ELEVATED)

    def test_non_default_flat_does_not_warn(self):
        assert not self._w206(regulatory_default=False, terrain_type=TerrainType.FLAT)
