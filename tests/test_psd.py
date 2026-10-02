"""Tests for pyaermod.psd: particle size distributions for Method 1 deposition.

The settling-velocity tests read a real AERMOD v26135 run recorded in
``tests/fixtures/psd/`` (see its README.md): ``DEBUGOPT DEPOS`` makes
AERMOD print the settling velocity ``VDP1`` computed for every size
category, so the module's replica and its aerodynamic-to-Stokes
conversion are checked against AERMOD itself.
"""

from __future__ import annotations

import doctest
import math
import re
from itertools import pairwise
from pathlib import Path

import pytest

import pyaermod.psd as psd
from pyaermod.epa_testcases import find_epa_testcase_set
from pyaermod.psd import (
    LogLinearCDF,
    LognormalCDF,
    SizeDistribution,
    aerodynamic_to_stokes,
    bins_from_cdf,
    bins_from_cut_points,
    bins_from_lognormal,
    cunningham_slip_factor,
    mean_mass_diameter,
    settling_equivalent_diameter,
    settling_velocity,
    stokes_to_aerodynamic,
)
from pyaermod.sources import AreaSource, ParticleDepositionParams

FIXTURE = Path(__file__).parent / "fixtures" / "psd"
ROOT = Path(__file__).resolve().parents[1]

# Sixteen aerodynamic bins from 0.5 to 75 um (edges in microns).
EDGES = [0.5, 1, 1.6, 2.5, 3.5, 5, 7, 10, 12.5, 15, 20, 25, 30, 40, 50, 62.5, 75]

# AP-42 section 13.2.4 (aggregate handling and storage piles), Equation 1:
# particle size multiplier k for the mass below each aerodynamic size.
AP42_1324_K = {2.5: 0.053, 5: 0.20, 10: 0.35, 15: 0.48, 30: 0.74}

# On those bins: the mean-mass diameter d_mm, the settling-equivalent
# diameter d_se, and the AP-42 13.2.4 cut-point fractions (of PM30).
EXPECTED_D_MM = [0.78, 1.32, 2.08, 3.03, 4.29, 6.06, 8.59, 11.30, 13.79, 17.62,
                 22.59, 27.58, 35.24, 45.18, 56.48, 68.94]
EXPECTED_D_SE = [0.74, 1.29, 2.03, 2.99, 4.23, 5.97, 8.46, 11.23, 13.73, 17.44,
                 22.45, 27.46, 34.88, 44.91, 56.13, 68.66]
AP42_FRACTIONS = [0.0308, 0.0209, 0.0199, 0.0964, 0.1022, 0.0984, 0.1043, 0.0967,
                  0.0790, 0.1458, 0.1131, 0.0924, 0, 0, 0, 0]

# EPA surfcoal (aermod test cases, inputs/surfcoal.inp):
#   SO PARTDIAM A-Z9999999  7.77  3.88  1.85  0.63
#   SO MASSFRAX A-Z9999999  0.70  0.20  0.07  0.03
SURFCOAL_DIAMETERS = [0.63, 1.85, 3.88, 7.77]
SURFCOAL_FRACTIONS = [0.03, 0.07, 0.20, 0.70]


def _ap42_bins():
    return bins_from_cut_points(AP42_1324_K, EDGES)


# ----------------------------------------------------------------------------
# Representative diameters
# ----------------------------------------------------------------------------

class TestRepresentativeDiameters:
    def test_mean_mass_reproduces_surfcoal(self):
        """Edges 0/1/2.5/5/10 give surfcoal's 0.63/1.85/3.88/7.77 um."""
        edges = [0, 1, 2.5, 5, 10]
        got = [round(mean_mass_diameter(a, b), 2) for a, b in pairwise(edges)]
        assert got == SURFCOAL_DIAMETERS

    def test_mean_mass_is_cube_root_of_mean_cube(self):
        a, b = 2.0, 7.0
        mean_cube = (b**4 - a**4) / (4 * (b - a))
        assert mean_mass_diameter(a, b) == pytest.approx(mean_cube ** (1 / 3), rel=1e-14)

    def test_d_mm_and_d_se_on_sixteen_bins(self):
        dist = SizeDistribution(tuple(EDGES), tuple([1 / 16] * 16))
        assert [round(d, 2) for d in dist.diameters()] == EXPECTED_D_MM
        assert [round(d, 2) for d in dist.diameters("settling_equivalent")] == EXPECTED_D_SE

    def test_settling_equivalent_needs_positive_lower_edge(self):
        with pytest.raises(ValueError, match="above 0"):
            settling_equivalent_diameter(0.0, 1.0)

    @pytest.mark.parametrize("lower, upper", [(1.0, 1.0), (2.0, 1.0), (-1.0, 1.0), (0.0, math.inf)])
    def test_bad_bins_rejected(self, lower, upper):
        with pytest.raises(ValueError):
            mean_mass_diameter(lower, upper)

    def test_unknown_representative_rejected(self):
        dist = SizeDistribution((1.0, 2.0), (1.0,))
        with pytest.raises(ValueError, match="representative"):
            dist.diameters("median")


# ----------------------------------------------------------------------------
# Cumulative distributions and binning
# ----------------------------------------------------------------------------

class TestLogLinearCDF:
    def test_linear_in_log_diameter_between_knots(self):
        F = LogLinearCDF({1.0: 0.0, 100.0: 1.0})
        assert F(10.0) == pytest.approx(0.5, abs=1e-15)
        assert F(math.sqrt(10.0)) == pytest.approx(0.25, abs=1e-15)

    def test_flat_outside_knots(self):
        F = LogLinearCDF({0.5: 0.1, 10: 0.9})
        assert F(0.0) == 0.1
        assert F(0.2) == 0.1
        assert F(50.0) == 0.9
        assert (F.lower_limit, F.upper_limit) == (0.1, 0.9)

    def test_knots_copied_and_read_only(self):
        knots = {1.0: 0.0, 2.0: 1.0}
        F = LogLinearCDF(knots)
        knots[1.5] = 0.9
        assert F(1.5) == pytest.approx(math.log(1.5) / math.log(2.0))
        with pytest.raises(TypeError):
            F.knots[3.0] = 1.0  # type: ignore[index]

    @pytest.mark.parametrize("knots", [
        {1.0: 0.0},
        {0.0: 0.0, 1.0: 1.0},
        {1.0: 0.5, 2.0: 0.4},
        {1.0: 0.0, 2.0: math.nan},
    ])
    def test_bad_knots_rejected(self, knots):
        with pytest.raises(ValueError):
            LogLinearCDF(knots)

    def test_negative_diameter_rejected(self):
        with pytest.raises(ValueError):
            LogLinearCDF({1.0: 0.0, 2.0: 1.0})(-1.0)

    def test_hashable_and_equal_by_knots(self):
        a = LogLinearCDF({1: 0, 2: 1})
        b = LogLinearCDF({2.0: 1.0, 1.0: 0.0})
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b, LogLinearCDF({1: 0, 3: 1})}) == 2


class TestCutPoints:
    def test_reproduces_ap42_fractions(self):
        """AP-42 13.2.4 k-values, log-linear from F(0.5) = 0."""
        dist = _ap42_bins()
        assert [round(f, 4) for f in dist.mass_fractions] == AP42_FRACTIONS

    def test_ap42_mass_at_or_above_10um(self):
        # 52.7% of the mass is at or above 10 um.
        assert round(_ap42_bins().fraction_at_or_above(10), 3) == 0.527

    def test_ap42_is_anchored_to_pm30(self):
        dist = _ap42_bins()
        assert dist.anchor_ratio == pytest.approx(1.0, abs=1e-15)
        assert dist.truncated_below == 0.0
        assert dist.truncated_above == 0.0

    @pytest.mark.parametrize("r, p10, t", [(0.05, 0.2, 0.0), (0.2, 0.6, 0.5), (0.151, 0.473, 0.35)])
    def test_fractions_sum_to_one(self, r, p10, t):
        """Knots of the form F(2.5)=r p10, F(10)=p10, F(30)=1, F(50)=1+t."""
        knots = {2.5: r * p10, 10: p10, 30: 1.0}
        if t:
            knots[50] = 1.0 + t
        dist = bins_from_cut_points(knots, EDGES, anchor=30)
        assert abs(math.fsum(dist.mass_fractions) - 1.0) <= 1e-12
        assert abs(sum(dist.mass_fractions) - 1.0) <= 1e-12
        assert dist.anchor_ratio == pytest.approx(1.0 + t, rel=1e-14)
        # PM10 is p10 of the PM30 anchor, so of the modelled mass p10 / (1 + t).
        assert 1 - dist.fraction_at_or_above(10) == pytest.approx(p10 / (1 + t), rel=1e-12)

    def test_default_anchor_is_largest_cut_point(self):
        dist = bins_from_cut_points({10: 0.5, 30: 1.0, 50: 1.5}, EDGES)
        assert dist.anchor_ratio == pytest.approx(1.0, abs=1e-15)

    def test_explicit_lower_below_first_edge(self):
        dist = bins_from_cut_points({2.5: 0.2, 10: 1.0}, [1.0, 2.5, 10.0], lower=0.5)
        # F(1) = 0.2 ln2/ln5 is below the first edge: left out of the bins and reported.
        below = 0.2 * math.log(2) / math.log(5)
        assert dist.truncated_below == pytest.approx(below, rel=1e-14)
        # The convention: the anchor's mass is counted from the first edge, so
        # the fine mass is reassigned to the bins, not lost (1, not 1 - below).
        assert dist.anchor_ratio == pytest.approx(1.0, abs=1e-15)
        assert dist.anchor_ratio != pytest.approx(1.0 - below, rel=1e-3)
        assert sum(dist.mass_fractions) == pytest.approx(1.0, abs=1e-15)

    def test_truncated_below_is_a_fraction_of_the_whole(self):
        # The whole distribution is 0.8, not 1: truncated_below is F(1) / 0.8.
        dist = bins_from_cut_points({2.5: 0.2, 10: 0.8}, [1.0, 2.5, 10.0], lower=0.5)
        below = 0.2 * math.log(2) / math.log(5)
        assert dist.truncated_below == pytest.approx(below / 0.8, rel=1e-14)
        assert dist.truncated_above == 0.0

    def test_bins_short_of_default_anchor_lose_the_rest(self):
        """AP-42 13.2.4 k-values (whole = 0.74) on bins that stop at 15 um.

        The default anchor is the largest cut point, 30 um, not the last edge:
        the bins hold 0.48 of the 0.74 below 30 um, and the rest is lost.
        """
        dist = bins_from_cut_points(AP42_1324_K, EDGES[:10])
        assert dist.edges[-1] == 15.0
        assert dist.anchor_ratio == pytest.approx(0.48 / 0.74, rel=1e-14)
        assert dist.truncated_above == pytest.approx((0.74 - 0.48) / 0.74, rel=1e-14)
        assert dist.truncated_below == 0.0

    def test_mapped_surfcoal_has_no_mass_at_or_above_10um(self):
        # surfcoal's fractions as cumulative knots, mapped onto the sixteen bins.
        cum = {1: 0.03, 2.5: 0.10, 5: 0.30, 10: 1.0}
        dist = bins_from_cut_points(cum, EDGES)
        assert dist.fraction_at_or_above(10) == 0.0
        assert [round(f, 4) for f in dist.mass_fractions[:7]] == [
            0.0300, 0.0359, 0.0341, 0.0971, 0.1029, 0.3398, 0.3602]

    def test_cut_point_at_or_below_lower_rejected(self):
        with pytest.raises(ValueError, match="above the lower"):
            bins_from_cut_points({0.5: 0.1, 10: 1.0}, EDGES)

    def test_zero_first_edge_needs_lower(self):
        with pytest.raises(ValueError, match="lower"):
            bins_from_cut_points({10: 1.0}, [0.0, 10.0])

    def test_no_cut_points_rejected(self):
        with pytest.raises(ValueError, match="cut point"):
            bins_from_cut_points({}, EDGES)


class TestLognormal:
    def test_truncated_and_renormalised(self):
        mmd, gsd = 15.07, 3.21
        edges = EDGES[:15]  # 0.5 to 50 um
        dist = bins_from_lognormal(mmd, gsd, edges, anchor=30)

        def phi(d):
            return 0.5 * (1 + math.erf(math.log(d / mmd) / math.log(gsd) / math.sqrt(2)))

        assert dist.truncated_below == pytest.approx(phi(0.5), rel=1e-12)
        assert dist.truncated_above == pytest.approx(1 - phi(50), rel=1e-12)
        assert dist.anchor_ratio == pytest.approx(
            (phi(50) - phi(0.5)) / (phi(30) - phi(0.5)), rel=1e-12)
        assert abs(math.fsum(dist.mass_fractions) - 1.0) <= 1e-12
        kept = phi(50) - phi(0.5)
        assert dist.mass_fractions[7] == pytest.approx((phi(12.5) - phi(10)) / kept, rel=1e-12)

    def test_lognormal_fine_mass_is_reassigned_to_the_bins(self):
        """The PM30 rate times anchor_ratio puts all of PM30 in 0.5-30 um.

        The convention is that the mass below the first edge is reassigned,
        not lost: the modelled mass below 30 um equals the PM30 rate, so the
        ratio is 1.17424, not the 1.17140 it would be if the 0.5 um cut
        stayed dropped.
        """
        dist = bins_from_lognormal(15.07, 3.21, EDGES[:15], anchor=30)
        below_30 = math.fsum(dist.mass_fractions[:12])
        assert dist.anchor_ratio * below_30 == pytest.approx(1.0, rel=1e-12)
        assert round(dist.anchor_ratio, 5) == 1.17424
        assert dist.truncated_below > 0.001

    def test_cdf_at_zero_and_median(self):
        F = LognormalCDF(5.0, 2.0)
        assert F(0.0) == 0.0
        assert F(5.0) == pytest.approx(0.5, abs=1e-15)

    @pytest.mark.parametrize("mmd, gsd", [(0.0, 2.0), (-1.0, 2.0), (5.0, 1.0), (5.0, math.nan)])
    def test_bad_parameters_rejected(self, mmd, gsd):
        with pytest.raises(ValueError):
            LognormalCDF(mmd, gsd)

    def test_negative_diameter_rejected(self):
        with pytest.raises(ValueError):
            LognormalCDF(5.0, 2.0)(-0.1)


class TestBinsFromCdf:
    def test_no_mass_in_bins_rejected(self):
        with pytest.raises(ValueError, match="no mass between"):
            bins_from_cdf(LogLinearCDF({1.0: 0.0, 2.0: 1.0}), [5.0, 10.0])

    def test_no_mass_below_anchor_rejected(self):
        with pytest.raises(ValueError, match="anchor"):
            bins_from_cdf(LogLinearCDF({5.0: 0.0, 10.0: 1.0}), [1.0, 20.0], anchor=4.0)

    def test_decreasing_cdf_rejected(self):
        class Bad:
            lower_limit = 0.0
            upper_limit = 1.0

            def __call__(self, d):
                return 1.0 / d

        with pytest.raises(ValueError, match="decreases"):
            bins_from_cdf(Bad(), [1.0, 2.0])


# ----------------------------------------------------------------------------
# SizeDistribution
# ----------------------------------------------------------------------------

class TestSizeDistribution:
    def test_surfcoal_deposition_params(self):
        dist = SizeDistribution((0, 1, 2.5, 5, 10), tuple(SURFCOAL_FRACTIONS))
        params = dist.to_deposition_params()
        assert isinstance(params, ParticleDepositionParams)
        assert [round(d, 2) for d in params.diameters] == SURFCOAL_DIAMETERS
        assert params.mass_fractions == SURFCOAL_FRACTIONS
        assert params.densities == [1.0] * 4

    def test_surfcoal_matches_epa_deck(self):
        """The same numbers as EPA's own deck, when the reference set is present."""
        case_set = find_epa_testcase_set(ROOT / "test_cases")
        if case_set is None or not (case_set.inputs / "surfcoal.inp").exists():
            pytest.skip("EPA test-case set not present")
        text = (case_set.inputs / "surfcoal.inp").read_text()
        diam = re.search(r"^SO PARTDIAM\s+\S+\s+(.+)$", text, re.M)
        frac = re.search(r"^SO MASSFRAX\s+\S+\s+(.+)$", text, re.M)
        assert diam and frac
        epa_d = sorted(float(x) for x in diam.group(1).split())
        epa_f = [float(x) for x in frac.group(1).split()][::-1]
        dist = SizeDistribution((0, 1, 2.5, 5, 10), tuple(epa_f))
        assert [round(d, 2) for d in dist.to_deposition_params().diameters] == epa_d

    def test_deposition_params_write_on_a_source(self):
        params = _ap42_bins().to_deposition_params(density=1.0)
        src = AreaSource(source_id="PIT", x_coord=0.0, y_coord=0.0, emission_rate=1e-5,
                         release_height=0.0, initial_lateral_dimension=100.0,
                         initial_vertical_dimension=50.0, particle_deposition=params)
        text = src.to_aermod_input()
        lines = {ln.split()[0]: ln.split()[2:] for ln in text.splitlines()
                 if ln.split() and ln.split()[0] in ("PARTDIAM", "MASSFRAX", "PARTDENS")}
        assert len(lines["PARTDIAM"]) == len(lines["MASSFRAX"]) == len(lines["PARTDENS"]) == 16
        assert abs(sum(float(x) for x in lines["MASSFRAX"]) - 1.0) < 0.02  # AERMOD W330

    def test_drop_empty(self):
        params = _ap42_bins().to_deposition_params(drop_empty=True)
        assert len(params.diameters) == 12
        assert len(params.mass_fractions) == len(params.densities) == 12
        assert round(params.diameters[-1], 2) == 27.58

    def test_stokes_conversion(self):
        dist = SizeDistribution((1.0, 2.0, 4.0), (0.5, 0.5))
        params = dist.to_deposition_params(density=2.65, stokes=True)
        for d_a, d_s in zip(dist.diameters(), params.diameters):
            assert d_s == pytest.approx(aerodynamic_to_stokes(d_a, 2.65), rel=1e-15)
        assert params.densities == [2.65, 2.65]
        naive = dist.to_deposition_params(density=2.65, stokes=True, slip=False)
        assert naive.diameters[0] == pytest.approx(dist.diameters()[0] / math.sqrt(2.65))

    def test_diameter_outside_aermod_range_rejected(self):
        dist = SizeDistribution((0.0, 0.0015), (1.0,))
        with pytest.raises(ValueError, match="E335"):
            dist.to_deposition_params()
        dist = SizeDistribution((1000.0, 2000.0), (1.0,))
        with pytest.raises(ValueError, match="E335"):
            dist.to_deposition_params()

    def test_diameter_range_is_checked_as_written(self):
        """INPPDM reads the rounded card value (``.4g`` in sources.py)."""
        # 0.00100006 passes as a float but is written 0.001, which AERMOD
        # v26135 rejects with E335.
        dist = SizeDistribution((0.0, 0.0015875, 1.0), (0.5, 0.5))
        assert dist.diameters()[0] > psd.AERMOD_MIN_DIAMETER
        with pytest.raises(ValueError, match=r"E335.*written as \[0\.001\]"):
            dist.to_deposition_params()
        # 1000.04 is written 1000, which AERMOD accepts; the returned
        # diameter itself is not rounded.
        dist = SizeDistribution((1000.0, 1000.08), (1.0,))
        assert dist.diameters()[0] > psd.AERMOD_MAX_DIAMETER
        params = dist.to_deposition_params()
        assert params.diameters == dist.diameters()
        assert "PARTDIAM  S1       1000" in AreaSource(
            source_id="S1", x_coord=0.0, y_coord=0.0, emission_rate=1.0,
            particle_deposition=params).to_aermod_input()

    @pytest.mark.parametrize("density", [0.0, -1.0, math.nan])
    def test_bad_density_rejected(self, density):
        with pytest.raises(ValueError, match="E334"):
            _ap42_bins().to_deposition_params(density=density)

    def test_fraction_at_or_above(self):
        dist = _ap42_bins()
        assert dist.fraction_at_or_above(0.1) == 1.0
        assert dist.fraction_at_or_above(0.5) == 1.0
        assert dist.fraction_at_or_above(75) == 0.0
        assert dist.fraction_at_or_above(30) == 0.0
        with pytest.raises(ValueError, match="inside a bin"):
            dist.fraction_at_or_above(11.0)

    def test_bins_property(self):
        dist = SizeDistribution((1.0, 2.0, 4.0), (0.25, 0.75))
        assert dist.bins == [(1.0, 2.0, 0.25), (2.0, 4.0, 0.75)]

    @pytest.mark.parametrize("edges, fractions, match", [
        ((1.0,), (), "two bin edges"),
        ((2.0, 1.0), (1.0,), "increase"),
        ((-1.0, 1.0), (1.0,), "0 or above"),
        ((1.0, 2.0, 3.0), (1.0,), "3 edges make 2 bins"),
        ((1.0, 2.0), (-1.0,), "0 or above"),
        ((1.0, 2.0, 3.0), (0.5, 0.49), "sum to 1"),
    ])
    def test_bad_distribution_rejected(self, edges, fractions, match):
        with pytest.raises(ValueError, match=match):
            SizeDistribution(edges, fractions)

    def test_bad_anchor_ratio_rejected(self):
        with pytest.raises(ValueError, match="anchor_ratio"):
            SizeDistribution((1.0, 2.0), (1.0,), anchor_ratio=-1.0)

    def test_lists_are_stored_as_tuples(self):
        dist = SizeDistribution([1, 2, 3], [0.5, 0.5])  # type: ignore[arg-type]
        assert dist.edges == (1.0, 2.0, 3.0)
        assert dist.mass_fractions == (0.5, 0.5)


# ----------------------------------------------------------------------------
# AERMOD's settling velocity, from a real run (tests/fixtures/psd/)
# ----------------------------------------------------------------------------

def _deck_categories():
    """{source: (diameters, densities)} from the recorded deck, in deck order."""
    out = {}
    order = []
    for line in (FIXTURE / "aermod.inp").read_text().splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[0] in ("PARTDIAM", "PARTDENS"):
            if parts[1] not in out:
                out[parts[1]] = {}
                order.append(parts[1])
            out[parts[1]][parts[0]] = [float(x) for x in parts[2:]]
    return order, out


def _recorded_vg():
    """{(isrc, icat): Vg} from AERMOD's PDEP.DAT."""
    row = re.compile(r"^\s+\d{8}\s+(\d+)\s+(\d+)\s+METHOD_1\s+\S+\s+\S+\s+(\S+)\s+\S+\s*$")
    vg = {}
    for line in (FIXTURE / "PDEP.DAT").read_text().splitlines():
        m = row.match(line)
        if m:
            vg[(int(m.group(1)), int(m.group(2)))] = float(m.group(3))
    return vg


class TestAgainstAERMOD:
    def test_fixture_is_a_successful_run(self):
        assert "*** AERMOD Finishes Successfully ***" in (FIXTURE / "aermod.out").read_text()
        assert len(_recorded_vg()) == 64

    def test_settling_velocity_matches_aermod_vdp1(self):
        order, cats = _deck_categories()
        vg = _recorded_vg()
        for isrc, sid in enumerate(order, 1):
            for icat, (d, rho) in enumerate(zip(cats[sid]["PARTDIAM"], cats[sid]["PARTDENS"]), 1):
                # AERMOD prints six significant digits.
                assert settling_velocity(d, rho) == pytest.approx(vg[(isrc, icat)], rel=6e-6), \
                    (sid, icat)

    def test_deck_diameters_come_from_this_module(self):
        order, cats = _deck_categories()
        d_a = SizeDistribution(tuple(EDGES), tuple([1 / 16] * 16)).diameters()
        expected = {
            "AERO1": d_a,
            "AERO265": d_a,
            "STOKES": [aerodynamic_to_stokes(d, 2.65) for d in d_a],
            "NAIVE": [aerodynamic_to_stokes(d, 2.65, slip=False) for d in d_a],
        }
        assert order == list(expected)
        for sid, diameters in expected.items():
            assert cats[sid]["PARTDIAM"] == [float(f"{d:.6g}") for d in diameters], sid

    def test_stokes_diameters_settle_like_aerodynamic_ones_in_aermod(self):
        """(aerodynamic_to_stokes(d, 2.65), 2.65) settles like (d, 1.0) in AERMOD."""
        vg = _recorded_vg()
        for icat in range(1, 17):
            assert vg[(3, icat)] == pytest.approx(vg[(1, icat)], rel=1e-5), icat

    def test_naive_conversion_settles_faster_in_aermod(self):
        """d / sqrt(rho) ignores slip: AERMOD settles it 11% fast at 0.78 um."""
        vg = _recorded_vg()
        excess = [vg[(4, i)] / vg[(1, i)] - 1 for i in range(1, 17)]
        assert excess[0] == pytest.approx(0.1115, abs=5e-4)
        assert all(a > b > 0 for a, b in pairwise(excess))

    def test_same_diameter_at_higher_density_settles_faster(self):
        vg = _recorded_vg()
        for icat in range(1, 17):
            assert vg[(2, icat)] / vg[(1, icat)] == pytest.approx(
                (2.65 - 1.2e-3) / (1 - 1.2e-3), rel=1e-5)


class TestConversion:
    @pytest.mark.parametrize("d_a", [0.01, 0.5, 0.78, 5.0, 30.0, 75.0, 500.0])
    @pytest.mark.parametrize("rho", [0.5, 2.65, 5.12])
    def test_round_trip_and_equal_settling(self, d_a, rho):
        d_s = aerodynamic_to_stokes(d_a, rho)
        assert stokes_to_aerodynamic(d_s, rho) == pytest.approx(d_a, rel=1e-12)
        assert settling_velocity(d_s, rho) == pytest.approx(settling_velocity(d_a, 1.0), rel=1e-12)

    def test_unit_density_is_identity(self):
        assert aerodynamic_to_stokes(3.3, 1.0) == 3.3
        assert stokes_to_aerodynamic(3.3, 1.0) == 3.3

    def test_without_slip_is_square_root_rule(self):
        assert aerodynamic_to_stokes(10.0, 4.0, slip=False) == 5.0
        assert stokes_to_aerodynamic(5.0, 4.0, slip=False) == 10.0

    @pytest.mark.parametrize("d, rho", [(0.0, 2.0), (-1.0, 2.0), (1.0, 1.2e-3), (1.0, math.inf)])
    def test_bad_inputs_rejected(self, d, rho):
        with pytest.raises(ValueError):
            aerodynamic_to_stokes(d, rho)
        with pytest.raises(ValueError):
            stokes_to_aerodynamic(d, rho)

    def test_slip_factor_and_velocity_guards(self):
        assert cunningham_slip_factor(1000.0) == pytest.approx(1.0, abs=2e-4)
        with pytest.raises(ValueError):
            cunningham_slip_factor(0.0)
        with pytest.raises(ValueError):
            settling_velocity(1.0, 0.0)
        # AERMOD floors the density difference at 0.
        assert settling_velocity(1.0, 1.0e-3) == 0.0


def test_module_doctests():
    failures, tried = doctest.testmod(psd)
    assert tried > 0
    assert failures == 0
