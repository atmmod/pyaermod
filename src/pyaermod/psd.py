"""Particle size distributions for AERMOD's Method 1 particle deposition.

AERMOD's Method 1 takes a source's particle size distribution as three
parallel lists on the ``SO`` pathway: ``PARTDIAM`` (one diameter per size
category, microns), ``MASSFRAX`` (the mass fraction in each category) and
``PARTDENS`` (the particle density of each category, g/cm^3). This module
builds those lists from the way size data usually arrive: cumulative mass
fractions at a few cut points (AP-42's particle size multipliers, for
example) or a lognormal mass distribution. It returns the
:class:`~pyaermod.sources.ParticleDepositionParams` a source's
``particle_deposition`` field takes.

What AERMOD does with the three lists (v26135 Fortran, ``soset.f``)
-------------------------------------------------------------------
* ``VDP1`` computes each category's gravitational settling velocity from
  its diameter and density by Stokes' law with a Cunningham slip factor
  (:func:`settling_velocity` repeats it). The diameter AERMOD reads is
  therefore the *physical* (Stokes) diameter of a particle of density
  ``PARTDENS``. Size data measured as aerodynamic diameters go in either
  as they are with ``PARTDENS 1.0``, or converted to Stokes diameters
  with :func:`aerodynamic_to_stokes` and paired with the real density;
  both give AERMOD the same settling velocity.
* ``SRCQA`` warns (W330) when the mass fractions do not sum to 1 within
  2 per cent. ``INPPHI`` rejects a fraction outside 0-1 (E332), ``INPPDM``
  a diameter at or below 0.001 or above 1000 microns (E335), and
  ``INPPDN`` a density at or below 0 (E334; W334 at or below 0.1).

Conventions
-----------
Every diameter this module takes or returns is in microns. Distributions
are held in *aerodynamic* diameter; bin edges, cut points and lognormal
medians are aerodynamic. :meth:`SizeDistribution.to_deposition_params`
converts to Stokes diameters only when asked.

A bin's representative diameter is, by default, the mean-mass diameter
``((d1^3 + d1^2 d2 + d1 d2^2 + d2^3)/4)^(1/3)`` (:func:`mean_mass_diameter`),
which reproduces the 0.63, 1.85, 3.88 and 7.77 micron diameters of EPA's
``surfcoal`` test deck from the edges 0, 1, 2.5, 5 and 10 microns. The
alternative is the settling-equivalent diameter
``sqrt((d2^2 - d1^2) / (2 ln(d2/d1)))`` (:func:`settling_equivalent_diameter`).

Examples
--------
AP-42 section 13.2.4 (aggregate handling) gives particle size multipliers
k of 0.053, 0.20, 0.35, 0.48 and 0.74 for the mass below 2.5, 5, 10, 15
and 30 microns. With the mass below 2.5 microns spread log-linearly down
to 0.5 microns:

>>> from pyaermod.psd import bins_from_cut_points
>>> dist = bins_from_cut_points(
...     {2.5: 0.053, 5: 0.20, 10: 0.35, 15: 0.48, 30: 0.74},
...     edges=[0.5, 1, 1.6, 2.5, 3.5, 5, 7, 10, 12.5, 15, 20, 25, 30],
... )
>>> round(dist.mass_fractions[0], 4)
0.0308
>>> round(dist.fraction_at_or_above(10), 3)
0.527
>>> params = dist.to_deposition_params(density=1.0)
>>> [round(d, 2) for d in params.diameters[:3]]
[0.78, 1.32, 2.08]
"""

from __future__ import annotations

import bisect
import math
import types
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

from .sources import ParticleDepositionParams

__all__ = [
    "AERMOD_MAX_DIAMETER",
    "AERMOD_MIN_DIAMETER",
    "CumulativeMassDistribution",
    "LogLinearCDF",
    "LognormalCDF",
    "SizeDistribution",
    "aerodynamic_to_stokes",
    "bins_from_cdf",
    "bins_from_cut_points",
    "bins_from_lognormal",
    "cunningham_slip_factor",
    "mean_mass_diameter",
    "settling_equivalent_diameter",
    "settling_velocity",
    "stokes_to_aerodynamic",
]

#: ``INPPDM`` (soset.f) rejects a diameter at or below this value (E335).
AERMOD_MIN_DIAMETER = 0.001
#: ``INPPDM`` (soset.f) rejects a diameter above this value (E335).
AERMOD_MAX_DIAMETER = 1000.0


def _as_written(value: float) -> float:
    """``value`` as the source writer puts it on ``PARTDIAM`` (``sources.py``, ``.4g``)."""
    return float(f"{value:.4g}")

# Constants of soset.f subroutine VDP1 (AERMOD v26135) and G of modules.f.
_A1, _A2, _A3 = 1.257, 0.4, 0.55
_XMFP_CM = 6.5e-6        # mean free path of air, cm
_VCON = 1.81e-4          # dynamic viscosity of air, g/(cm s)
_RHOAIR = 1.2e-3         # density of air, g/cm^3
_G = 9.80616             # m/s^2

_REPRESENTATIVES = ("mean_mass", "settling_equivalent")


# ============================================================================
# Representative diameters
# ============================================================================

def _check_bin(lower: float, upper: float) -> None:
    if not (math.isfinite(lower) and math.isfinite(upper)):
        raise ValueError(f"bin edges must be finite, got {lower!r} and {upper!r}")
    if lower < 0 or upper <= lower:
        raise ValueError(f"a bin needs 0 <= lower < upper, got {lower!r} and {upper!r}")


def mean_mass_diameter(lower: float, upper: float) -> float:
    """Mean-mass diameter of the bin ``[lower, upper]`` (microns).

    ``((d1^3 + d1^2 d2 + d1 d2^2 + d2^3) / 4)^(1/3)``: the cube root of the
    mean of ``d^3`` for diameters spread uniformly across the bin, which is
    the diameter of the particle of average mass. From the edges 0, 1, 2.5,
    5 and 10 microns it gives the 0.63, 1.85, 3.88 and 7.77 microns of
    EPA's ``surfcoal`` test deck. ``lower`` may be 0.
    """
    _check_bin(lower, upper)
    a, b = lower, upper
    return float(((a**3 + a * a * b + a * b * b + b**3) / 4.0) ** (1.0 / 3.0))


def settling_equivalent_diameter(lower: float, upper: float) -> float:
    """Settling-equivalent diameter of the bin ``[lower, upper]`` (microns).

    ``sqrt((d2^2 - d1^2) / (2 ln(d2/d1)))``: the diameter whose ``d^2`` (and
    so whose Stokes settling velocity, slip aside) equals the mass-weighted
    mean over a bin whose mass is spread uniformly in ``ln d``. ``lower``
    must be above 0, because the log-uniform spread is undefined there.
    """
    _check_bin(lower, upper)
    if lower <= 0:
        raise ValueError("the settling-equivalent diameter needs a lower edge above 0")
    return math.sqrt((upper**2 - lower**2) / (2.0 * math.log(upper / lower)))


# ============================================================================
# AERMOD's settling velocity and the aerodynamic <-> Stokes conversion
# ============================================================================

def cunningham_slip_factor(diameter: float) -> float:
    """AERMOD's Cunningham slip correction for a particle of ``diameter`` microns.

    ``1 + 2 xmfp (a1 + a2 exp(-a3 d/xmfp)) / d`` with ``d`` in cm,
    ``xmfp = 6.5e-6`` cm, ``a1 = 1.257``, ``a2 = 0.4`` and ``a3 = 0.55``,
    exactly as ``soset.f`` subroutine ``VDP1`` computes ``SCF``.
    """
    if not diameter > 0:
        raise ValueError(f"diameter must be above 0, got {diameter!r}")
    dcm = 1.0e-4 * diameter
    return 1.0 + 2.0 * _XMFP_CM * (_A1 + _A2 * math.exp(-_A3 * dcm / _XMFP_CM)) / dcm


def settling_velocity(diameter: float, density: float) -> float:
    """AERMOD's gravitational settling velocity (m/s) for one size category.

    ``max(0, rho - rhoair) g d^2 SCF / (18 mu)`` with ``d`` in cm, ``rho``
    in g/cm^3, ``rhoair = 1.2e-3`` g/cm^3, ``mu = 1.81e-4`` g/(cm s) and
    ``g = 9.80616`` m/s^2, as ``soset.f`` subroutine ``VDP1`` computes
    ``AVGRAV``. ``diameter`` is the value on the ``PARTDIAM`` card and
    ``density`` the value on ``PARTDENS``. It agrees with the ``Vg`` column
    AERMOD v26135 writes under ``DEBUGOPT DEPOS`` to the six digits AERMOD
    prints (``tests/fixtures/psd/``).
    """
    if not density > 0:
        raise ValueError(f"density must be above 0, got {density!r}")
    dcm = 1.0e-4 * diameter
    return (max(0.0, density - _RHOAIR) * _G * dcm**2
            * cunningham_slip_factor(diameter) / (18.0 * _VCON))


def _d2_scf(d: float) -> float:
    return d * d * cunningham_slip_factor(d)


def _solve_d2_scf(target: float, guess: float) -> float:
    """The diameter ``d`` with ``d^2 SCF(d) == target``; ``d^2 SCF`` rises with ``d``."""
    lo, hi = guess, guess
    while _d2_scf(lo) > target:
        lo *= 0.5
    while _d2_scf(hi) < target:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _d2_scf(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-15 * hi:
            break
    return 0.5 * (lo + hi)


def _check_conversion(diameter: float, density: float) -> None:
    if not (math.isfinite(diameter) and diameter > 0):
        raise ValueError(f"diameter must be above 0, got {diameter!r}")
    if not (math.isfinite(density) and density > _RHOAIR):
        raise ValueError(
            f"density must be above AERMOD's air density {_RHOAIR} g/cm^3, got {density!r}"
        )


def aerodynamic_to_stokes(aerodynamic_diameter: float, density: float, *,
                          slip: bool = True) -> float:
    """Stokes (physical) diameter that AERMOD settles like ``aerodynamic_diameter``.

    Parameters
    ----------
    aerodynamic_diameter : float
        Aerodynamic diameter (microns): the diameter of the unit-density
        sphere that settles at the same speed.
    density : float
        Particle density (g/cm^3), the value that will go on ``PARTDENS``.
    slip : bool
        With ``True`` (the default) the result solves AERMOD's own settling
        equation, so ``(result, density)`` on the ``PARTDIAM``/``PARTDENS``
        cards gives the same settling velocity as ``(aerodynamic_diameter,
        1.0)``: ``(rho - rhoair) d^2 SCF(d) = (1 - rhoair) d_a^2 SCF(d_a)``
        with :func:`cunningham_slip_factor`. With ``False`` it is the
        textbook ``d_a / sqrt(rho)``, which ignores the slip factor and
        AERMOD's air-density term. The smaller Stokes diameter slips more,
        so AERMOD settles it faster than the aerodynamic size says: at
        density 2.65, 11% faster at 0.78 microns, 1% at 11 and 0.2% at 69
        (``tests/fixtures/psd/``).

    Notes
    -----
    Only gravitational settling is matched. AERMOD's Brownian diffusion
    term depends on the physical diameter, so ``(d_s, rho)`` and
    ``(d_a, 1.0)`` still deposit fine particles at different rates, as
    real particles of those sizes would.
    """
    _check_conversion(aerodynamic_diameter, density)
    if density == 1.0:
        return float(aerodynamic_diameter)
    if not slip:
        return aerodynamic_diameter / math.sqrt(density)
    target = (1.0 - _RHOAIR) / (density - _RHOAIR) * _d2_scf(aerodynamic_diameter)
    return _solve_d2_scf(target, aerodynamic_diameter / math.sqrt(density))


def stokes_to_aerodynamic(stokes_diameter: float, density: float, *,
                          slip: bool = True) -> float:
    """Aerodynamic diameter of a particle of ``stokes_diameter`` microns and ``density``.

    The inverse of :func:`aerodynamic_to_stokes`, with the same meaning of
    ``slip``: with ``True`` AERMOD settles ``(stokes_diameter, density)``
    and ``(result, 1.0)`` at the same speed; with ``False`` the result is
    ``d_s sqrt(rho)``.
    """
    _check_conversion(stokes_diameter, density)
    if density == 1.0:
        return float(stokes_diameter)
    if not slip:
        return stokes_diameter * math.sqrt(density)
    target = (density - _RHOAIR) / (1.0 - _RHOAIR) * _d2_scf(stokes_diameter)
    return _solve_d2_scf(target, stokes_diameter * math.sqrt(density))


# ============================================================================
# Cumulative mass distributions
# ============================================================================

class CumulativeMassDistribution(Protocol):
    """A cumulative mass distribution ``F(d)``: the mass below diameter ``d``.

    ``F`` must not decrease with ``d``. ``lower_limit`` and ``upper_limit``
    are its values as ``d`` goes to 0 and to infinity; any consistent units
    of mass will do, because :func:`bins_from_cdf` normalises.
    """

    @property
    def lower_limit(self) -> float: ...

    @property
    def upper_limit(self) -> float: ...

    def __call__(self, diameter: float) -> float: ...


@dataclass(frozen=True)
class LogLinearCDF:
    """Cumulative mass linear in ``ln d`` between knots.

    ``knots`` maps a diameter (microns, above 0) to the cumulative mass
    below it. Between two knots ``F`` is interpolated linearly in the
    logarithm of the diameter; below the first knot it equals the first
    knot's value and above the last knot the last knot's value, so no mass
    lies outside the knots.

    >>> F = LogLinearCDF({0.5: 0.0, 2.5: 0.2, 10: 1.0})
    >>> round(F(5.0), 6)
    0.6
    """

    # Equality and the hash use the sorted (_d, _f) tuples: the knots are
    # stored read-only as a mappingproxy, which cannot be hashed.
    knots: Mapping[float, float] = field(compare=False)
    _d: Tuple[float, ...] = field(init=False, repr=False)
    _f: Tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        items = sorted((float(d), float(f)) for d, f in self.knots.items())
        if len(items) < 2:
            raise ValueError("a log-linear CDF needs at least two knots")
        ds = tuple(d for d, _ in items)
        fs = tuple(f for _, f in items)
        if not all(math.isfinite(d) and d > 0 for d in ds):
            raise ValueError(f"knot diameters must be finite and above 0, got {ds}")
        if not all(math.isfinite(f) for f in fs):
            raise ValueError(f"knot values must be finite, got {fs}")
        if any(b < a for a, b in pairwise(fs)):
            raise ValueError(f"cumulative values must not decrease with diameter, got {fs}")
        object.__setattr__(self, "knots", types.MappingProxyType(dict(items)))
        object.__setattr__(self, "_d", ds)
        object.__setattr__(self, "_f", fs)

    @property
    def lower_limit(self) -> float:
        """``F`` below the first knot."""
        return self._f[0]

    @property
    def upper_limit(self) -> float:
        """``F`` above the last knot."""
        return self._f[-1]

    def __call__(self, diameter: float) -> float:
        if not diameter >= 0:
            raise ValueError(f"diameter must be 0 or above, got {diameter!r}")
        ds, fs = self._d, self._f
        if diameter <= ds[0]:
            return fs[0]
        if diameter >= ds[-1]:
            return fs[-1]
        i = bisect.bisect_right(ds, diameter)
        d1, d2, f1, f2 = ds[i - 1], ds[i], fs[i - 1], fs[i]
        return f1 + (f2 - f1) * math.log(diameter / d1) / math.log(d2 / d1)


@dataclass(frozen=True)
class LognormalCDF:
    """Lognormal cumulative mass: ``Phi(ln(d / mmd) / ln(gsd))``.

    Parameters
    ----------
    mass_median_diameter : float
        Mass median diameter (microns).
    geometric_std : float
        Geometric standard deviation, above 1.
    """

    mass_median_diameter: float
    geometric_std: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mass_median_diameter) and self.mass_median_diameter > 0):
            raise ValueError(
                f"mass_median_diameter must be above 0, got {self.mass_median_diameter!r}"
            )
        if not (math.isfinite(self.geometric_std) and self.geometric_std > 1):
            raise ValueError(f"geometric_std must be above 1, got {self.geometric_std!r}")

    @property
    def lower_limit(self) -> float:
        return 0.0

    @property
    def upper_limit(self) -> float:
        return 1.0

    def __call__(self, diameter: float) -> float:
        if not diameter >= 0:
            raise ValueError(f"diameter must be 0 or above, got {diameter!r}")
        if diameter == 0:
            return 0.0
        z = math.log(diameter / self.mass_median_diameter) / math.log(self.geometric_std)
        return 0.5 * math.erfc(-z / math.sqrt(2.0))


# ============================================================================
# Binned distributions
# ============================================================================

def _check_edges(edges: Iterable[float]) -> Tuple[float, ...]:
    e = tuple(float(x) for x in edges)
    if len(e) < 2:
        raise ValueError("a size distribution needs at least two bin edges")
    if not all(math.isfinite(x) for x in e) or e[0] < 0:
        raise ValueError(f"bin edges must be finite and 0 or above, got {e}")
    if any(b <= a for a, b in pairwise(e)):
        raise ValueError(f"bin edges must increase strictly, got {e}")
    return e


@dataclass(frozen=True)
class SizeDistribution:
    """Mass fractions in aerodynamic-diameter bins.

    Parameters
    ----------
    edges : sequence of float
        Bin edges (microns, aerodynamic), strictly increasing, one more
        than there are bins. The first edge may be 0.
    mass_fractions : sequence of float
        Fraction of the modelled mass in each bin; each 0 or above and
        summing to 1 within 1e-9.
    anchor_ratio : float
        The mass in the bins divided by the mass between the first edge
        and the anchor size (for AP-42 factors the largest size the factor
        covers, such as 30 microns for PM30). Multiply the anchor's
        emission rate by ``anchor_ratio`` to get the rate that goes with
        these fractions. With the anchor inside the edges, the modelled
        mass below the anchor then equals the anchor's rate (for PM30, the
        mass below 30 um equals the AP-42 PM30 emission):
        the share of the anchor's mass that lay below the first edge is
        not lost but spread over the bins. Mass between the last edge and
        an anchor beyond it *is* lost, and lowers the ratio. 1 when the
        last edge is the anchor.
    truncated_below, truncated_above : float
        Fractions of the whole distribution that lie below the first edge
        and above the last edge, and so are not modelled.
    """

    edges: Tuple[float, ...]
    mass_fractions: Tuple[float, ...]
    anchor_ratio: float = 1.0
    truncated_below: float = 0.0
    truncated_above: float = 0.0

    def __post_init__(self) -> None:
        edges = _check_edges(self.edges)
        fractions = tuple(float(f) for f in self.mass_fractions)
        if len(fractions) != len(edges) - 1:
            raise ValueError(
                f"{len(edges)} edges make {len(edges) - 1} bins, "
                f"but {len(fractions)} mass fractions were given"
            )
        if not all(math.isfinite(f) and f >= 0 for f in fractions):
            raise ValueError(f"mass fractions must be finite and 0 or above, got {fractions}")
        total = math.fsum(fractions)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"mass fractions must sum to 1, they sum to {total!r}")
        for name in ("anchor_ratio", "truncated_below", "truncated_above"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise ValueError(f"{name} must be finite and 0 or above, got {value!r}")
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "mass_fractions", fractions)

    @property
    def bins(self) -> List[Tuple[float, float, float]]:
        """``(lower, upper, mass_fraction)`` for every bin."""
        return [(a, b, f) for (a, b), f in zip(pairwise(self.edges), self.mass_fractions)]

    def diameters(self, representative: str = "mean_mass") -> List[float]:
        """Representative aerodynamic diameter of every bin (microns).

        ``representative`` is ``"mean_mass"`` (:func:`mean_mass_diameter`)
        or ``"settling_equivalent"`` (:func:`settling_equivalent_diameter`).
        """
        if representative == "mean_mass":
            rule = mean_mass_diameter
        elif representative == "settling_equivalent":
            rule = settling_equivalent_diameter
        else:
            raise ValueError(
                f"representative must be one of {_REPRESENTATIVES}, got {representative!r}"
            )
        return [rule(a, b) for a, b in pairwise(self.edges)]

    def fraction_at_or_above(self, diameter: float) -> float:
        """Fraction of the modelled mass in bins at or above ``diameter``.

        ``diameter`` must be a bin edge, or lie outside the edges, so that
        no bin is split. AERMOD's User's Guide recommends Method 1 when
        more than about 10 per cent of the mass is at or above 10 microns.
        """
        if diameter <= self.edges[0]:
            return 1.0
        if diameter >= self.edges[-1]:
            return 0.0
        if diameter not in self.edges:
            raise ValueError(
                f"{diameter!r} microns falls inside a bin; it must be one of the edges {self.edges}"
            )
        i = self.edges.index(diameter)
        return math.fsum(self.mass_fractions[i:])

    def to_deposition_params(self, density: float = 1.0, *,
                             representative: str = "mean_mass",
                             stokes: bool = False,
                             slip: bool = True,
                             drop_empty: bool = False) -> ParticleDepositionParams:
        """Build the ``PARTDIAM``/``MASSFRAX``/``PARTDENS`` lists for a source.

        Parameters
        ----------
        density : float
            Particle density (g/cm^3) for every bin.
        representative : str
            ``"mean_mass"`` or ``"settling_equivalent"``; see :meth:`diameters`.
        stokes : bool
            ``False`` (the default) writes the aerodynamic diameters with
            ``density``: with the default ``density=1.0`` AERMOD then
            settles each bin as its aerodynamic size says. ``True``
            converts each diameter with :func:`aerodynamic_to_stokes` for
            ``density``, so the physical particles of that density settle
            at the same speed.
        slip : bool
            Passed to :func:`aerodynamic_to_stokes` when ``stokes`` is set.
        drop_empty : bool
            Leave out bins whose mass fraction is 0. AERMOD accepts them
            (E332 allows 0), and keeping them keeps every source on the
            same bins.

        Raises
        ------
        ValueError
            If a diameter, rounded to the four significant digits the
            source writer puts on ``PARTDIAM``, falls outside AERMOD's
            accepted range, above 0.001 and up to 1000 microns (E335), or
            ``density`` is not above 0 (E334). The diameters returned are
            not rounded.
        """
        if not (math.isfinite(density) and density > 0):
            raise ValueError(f"density must be above 0 (AERMOD E334), got {density!r}")
        diameters = self.diameters(representative)
        if stokes:
            diameters = [aerodynamic_to_stokes(d, density, slip=slip) for d in diameters]
        keep = [i for i, f in enumerate(self.mass_fractions) if f > 0 or not drop_empty]
        diameters = [diameters[i] for i in keep]
        # INPPDM checks the number on the card, so check the diameter as
        # the source writer rounds it: 0.00100006 is written as 0.001.
        bad = [d for d in diameters
               if not AERMOD_MIN_DIAMETER < _as_written(d) <= AERMOD_MAX_DIAMETER]
        if bad:
            raise ValueError(
                f"AERMOD accepts diameters above {AERMOD_MIN_DIAMETER} and up to "
                f"{AERMOD_MAX_DIAMETER} microns (E335), got {bad}, written as "
                f"{[_as_written(d) for d in bad]}"
            )
        fractions = [self.mass_fractions[i] for i in keep]
        return ParticleDepositionParams(
            diameters=diameters,
            mass_fractions=fractions,
            densities=[float(density)] * len(keep),
        )


def bins_from_cdf(cdf: CumulativeMassDistribution, edges: Sequence[float], *,
                  anchor: Optional[float] = None) -> SizeDistribution:
    """Mass fractions of ``cdf`` in the bins ``edges``.

    The mass below the first edge and above the last is dropped
    (``truncated_below`` and ``truncated_above`` report it as fractions of
    the whole distribution) and the rest is renormalised to sum to 1.

    Parameters
    ----------
    cdf : CumulativeMassDistribution
        :class:`LogLinearCDF`, :class:`LognormalCDF` or anything with the
        same interface.
    edges : sequence of float
        Bin edges (microns, aerodynamic), strictly increasing.
    anchor : float, optional
        The diameter the emission rate's mass refers to (30 for a PM30
        rate). ``anchor_ratio`` of the result is the mass between the
        first edge and the last divided by the mass between the first edge
        and ``anchor``; the mass below the first edge is in neither, so
        the anchor's rate is spread over the bins (see
        :class:`SizeDistribution`). Defaults to the last edge, giving 1.
    """
    e = _check_edges(edges)
    f = [cdf(x) for x in e]
    raw = [b - a for a, b in pairwise(f)]
    if any(r < 0 for r in raw):
        raise ValueError("the cumulative distribution decreases across the bins")
    total = math.fsum(raw)
    if not total > 0:
        raise ValueError(f"the distribution has no mass between {e[0]} and {e[-1]} microns")
    anchor_d = e[-1] if anchor is None else float(anchor)
    anchor_mass = cdf(anchor_d) - f[0]
    if not anchor_mass > 0:
        raise ValueError(f"the distribution has no mass between {e[0]} and the anchor {anchor_d}")
    whole = cdf.upper_limit - cdf.lower_limit
    return SizeDistribution(
        edges=e,
        mass_fractions=tuple(r / total for r in raw),
        anchor_ratio=total / anchor_mass,
        truncated_below=(f[0] - cdf.lower_limit) / whole,
        truncated_above=(cdf.upper_limit - f[-1]) / whole,
    )


def bins_from_cut_points(cut_points: Mapping[float, float], edges: Sequence[float], *,
                         lower: Optional[float] = None,
                         anchor: Optional[float] = None) -> SizeDistribution:
    """Bins from cumulative mass at cut points, log-linear in between.

    Parameters
    ----------
    cut_points : mapping of float to float
        Diameter (microns, aerodynamic) to the cumulative mass below it, in
        any consistent units: AP-42's particle size multipliers ``k`` work
        as they are.
    edges : sequence of float
        Bin edges (microns, aerodynamic), strictly increasing.
    lower : float, optional
        The diameter below which there is no mass (``F(lower) = 0``); the
        mass of the first cut point is spread log-linearly down to it.
        Defaults to the first edge, which must then be above 0. Every cut
        point must lie above it.
    anchor : float, optional
        The diameter the emission rate refers to; defaults to the largest
        cut point. See :func:`bins_from_cdf`. Mass above the largest cut
        point is not modelled, so bins above it get 0.
    """
    e = _check_edges(edges)
    low = e[0] if lower is None else float(lower)
    if not low > 0:
        raise ValueError("log-linear interpolation needs a lower diameter above 0; pass lower=")
    if not cut_points:
        raise ValueError("at least one cut point is needed")
    if any(float(d) <= low for d in cut_points):
        raise ValueError(f"every cut point must lie above the lower diameter {low}")
    knots = {low: 0.0, **{float(d): float(v) for d, v in cut_points.items()}}
    top = max(float(d) for d in cut_points)
    return bins_from_cdf(LogLinearCDF(knots), e, anchor=top if anchor is None else anchor)


def bins_from_lognormal(mass_median_diameter: float, geometric_std: float,
                        edges: Sequence[float], *,
                        anchor: Optional[float] = None) -> SizeDistribution:
    """Bins from a lognormal mass distribution truncated to the edges.

    Mass below the first edge and above the last is left out of the bins
    and reported in ``truncated_below`` and ``truncated_above``, as
    fractions of the whole lognormal; the rest is renormalised to sum
    to 1. ``anchor`` is as in :func:`bins_from_cdf`: the anchor's mass is
    counted from the first edge, so an anchor emission rate times
    ``anchor_ratio`` puts all of that rate in the bins, including the
    share the lognormal had below the first edge.
    """
    return bins_from_cdf(LognormalCDF(mass_median_diameter, geometric_std), edges, anchor=anchor)
