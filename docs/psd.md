# Particle size distributions for Method 1 deposition

AERMOD's Method 1 particle deposition describes a source's particles as a
list of size categories. Three `SO` cards carry the list, one value per
category:

| Card | Meaning | What AERMOD checks (v26135 `soset.f`) |
|---|---|---|
| `PARTDIAM` | Diameter of the category, microns | Above 0.001 and at most 1000 (E335) |
| `MASSFRAX` | Fraction of the source's mass in the category | Each 0 to 1 (E332); a warning when they do not sum to 1 within 2% (W330) |
| `PARTDENS` | Particle density, g/cm³ | Above 0 (E334); a warning at or below 0.1 (W334) |

`pyaermod.psd` builds those lists from the way size data usually arrive,
cumulative mass fractions at a few cut points or a lognormal fit, and
returns the `ParticleDepositionParams` that a source's
`particle_deposition` field takes.

```python
from pyaermod.psd import bins_from_cut_points
from pyaermod.sources import AreaSource

# AP-42 section 13.2.4 (aggregate handling): particle size multiplier k
# for the mass below 2.5, 5, 10, 15 and 30 microns (aerodynamic).
k = {2.5: 0.053, 5: 0.20, 10: 0.35, 15: 0.48, 30: 0.74}
edges = [0.5, 1, 1.6, 2.5, 3.5, 5, 7, 10, 12.5, 15, 20, 25, 30]

dist = bins_from_cut_points(k, edges)
dist.mass_fractions            # 12 fractions that sum to 1
dist.fraction_at_or_above(10)  # 0.527

source = AreaSource(
    source_id="PILE", x_coord=0.0, y_coord=0.0, emission_rate=1.0e-5,
    particle_deposition=dist.to_deposition_params(density=1.0),
)
```

## What AERMOD does with the diameter

`VDP1` in `soset.f` turns each category into a gravitational settling
velocity by Stokes' law with a Cunningham slip factor:

```
SCF = 1 + 2 xmfp (1.257 + 0.4 exp(-0.55 d / xmfp)) / d
Vg  = max(0, rho - 1.2e-3) g d² SCF / (18 × 1.81e-4)
```

with `d` in cm, `xmfp = 6.5e-6` cm, `rho` from `PARTDENS` in g/cm³ and
`g = 9.80616` m/s². The diameter on `PARTDIAM` is therefore the
*physical* (Stokes) diameter of a particle of density `PARTDENS`.
`psd.settling_velocity(d, rho)` repeats the calculation;
`tests/fixtures/psd/` holds a real AERMOD v26135 run whose
`DEBUGOPT DEPOS` output it matches, category by category, to the six
digits AERMOD prints.

Size data from emission factors and impactors are *aerodynamic*
diameters: the diameter of a unit-density sphere that settles at the same
speed. There are two ways to give them to AERMOD, and they settle the
same:

1. **Aerodynamic diameters with `PARTDENS 1.0`.** This is what
   `to_deposition_params()` does by default.
2. **Stokes diameters with the real density.**
   `to_deposition_params(density=2.65, stokes=True)` converts each
   diameter with `aerodynamic_to_stokes`, which solves AERMOD's own
   settling equation, so that `(d_s, 2.65)` settles exactly like
   `(d_a, 1.0)`.

The textbook conversion `d_s = d_a / sqrt(rho)` (`slip=False`) ignores
the slip factor. The smaller Stokes diameter slips more than the
aerodynamic one, so AERMOD settles it too fast. In the recorded run, at a
density of 2.65:

| Aerodynamic diameter (µm) | `aerodynamic_to_stokes` | `d_a / sqrt(rho)` |
|---|---|---|
| 0.78 | same `Vg` as `(0.78, 1.0)` | 11% faster |
| 11.3 | same | 1.0% faster |
| 68.9 | same | 0.2% faster |

Two cautions:

- Only gravitational settling is matched. AERMOD's Brownian diffusion
  term depends on the physical diameter, so the two ways deposit fine
  particles at different rates, as real particles of those sizes would.
- Writing an aerodynamic diameter with a density above 1 (without
  `stokes=True`) models a *larger* particle: the same diameter at 2.65
  g/cm³ settles 2.65 times faster in AERMOD.

## Representative diameter of a bin

A bin from `d1` to `d2` goes to AERMOD as one diameter:

- **Mean-mass** (the default, `representative="mean_mass"`):
  `((d1³ + d1² d2 + d1 d2² + d2³) / 4)^(1/3)`, the cube root of the mean
  of `d³` across the bin. From the edges 0, 1, 2.5, 5 and 10 microns it
  gives 0.63, 1.85, 3.88 and 7.77 microns, the diameters of EPA's
  `surfcoal` test deck.
- **Settling-equivalent** (`representative="settling_equivalent"`):
  `sqrt((d2² − d1²) / (2 ln(d2/d1)))`, the diameter whose `d²`, and so
  whose Stokes settling velocity, is the mean over a bin whose mass is
  spread uniformly in `ln d`. It needs `d1 > 0`.

```python
from pyaermod.psd import SizeDistribution

surfcoal = SizeDistribution(edges=(0, 1, 2.5, 5, 10),
                            mass_fractions=(0.03, 0.07, 0.20, 0.70))
[round(d, 2) for d in surfcoal.diameters()]   # [0.63, 1.85, 3.88, 7.77]
```

## Building distributions

### From cut points

`bins_from_cut_points(cut_points, edges, lower=None, anchor=None)` takes
the cumulative mass below each cut point, in any consistent units (AP-42's
`k` values work as they are). Between cut points the cumulative mass is
linear in `ln d`. Below the first cut point the mass is spread
log-linearly down to `lower` (the first edge by default), where it is 0;
nothing is modelled below `lower`, and nothing above the largest cut
point.

### From a lognormal

`bins_from_lognormal(mmd, gsd, edges, anchor=None)` bins a lognormal mass
distribution with mass median diameter `mmd` and geometric standard
deviation `gsd`, truncated to the edges. The mass left out of the bins
is reported as `truncated_below` and `truncated_above`, fractions of the
whole distribution, and the rest is renormalised to sum to 1. How an
emission rate treats the mass below the first edge is set by the anchor,
below.

### From any cumulative distribution

`bins_from_cdf(cdf, edges, anchor=None)` accepts a `LogLinearCDF`, a
`LognormalCDF` or any object with the same interface: a call `F(d)`
that does not decrease with `d`, plus `lower_limit` and `upper_limit`
(its values towards 0 and infinity).

## The emission rate and the anchor

`MASSFRAX` must sum to 1, but an emission factor refers to the mass below
a stated size, such as PM30. When the bins reach beyond that size (a
tail from 30 to 50 microns, say), or stop short of it, the modelled mass
differs from the emission factor's. `anchor` names the size the emission
rate refers to, and **multiplying the anchor emission rate by
`anchor_ratio`** gives the emission rate that goes with the fractions.

`anchor_ratio` is the mass in the bins divided by the mass between the
*first edge* and the anchor. With the anchor inside the edges, the
modelled mass below the anchor therefore equals the anchor's emission
rate. The two ends are treated differently:

- **Below the first edge.** Mass the distribution has there (a lognormal
  truncated at 0.5 microns, or cut points with `lower` below the first
  edge) is not in the anchor's mass either, so the anchor's whole rate is
  spread over the bins: that fine mass is reassigned, not lost. This is
  what makes a distribution's modelled mass below 30 microns
  equal the AP-42 PM30 emission.
- **Above the last edge.** When the bins stop short of the anchor, the
  mass between the last edge and the anchor is part of the anchor's mass
  but not of the bins, so it is lost and `anchor_ratio` falls below 1.
  AP-42 13.2.4's k-values on bins that stop at 15 microns give
  `anchor_ratio` 0.48/0.74 = 0.649 with the default anchor, 30 microns.

`truncated_below` and `truncated_above` report both, as fractions of the
whole distribution, whatever the anchor.

```python
# Cumulative mass relative to PM30, with 25% more mass between 30 and 50 um.
dist = bins_from_cut_points({2.5: 0.03, 10: 0.30, 30: 1.0, 50: 1.25},
                            edges=[0.5, 2.5, 10, 20, 30, 40, 50], anchor=30)
dist.anchor_ratio      # 1.25
q_pm30 = 2.0e-5        # g/(s m²), from the emission factor
q_model = q_pm30 * dist.anchor_ratio
```

## Method 1 or Method 2

AERMOD's User's Guide recommends Method 1 when a significant fraction of
the mass, more than about 10%, is in particles of 10 microns or more.
`dist.fraction_at_or_above(10)` gives that fraction, provided 10 microns
is a bin edge.

## Options of `to_deposition_params`

| Argument | Default | Effect |
|---|---|---|
| `density` | 1.0 | `PARTDENS` for every bin |
| `representative` | `"mean_mass"` | Or `"settling_equivalent"` |
| `stokes` | `False` | Convert to Stokes diameters for `density` |
| `slip` | `True` | With `stokes`, solve AERMOD's settling equation; `False` uses `d_a / sqrt(rho)` |
| `drop_empty` | `False` | Leave out bins with no mass (AERMOD accepts a 0 fraction) |

It raises `ValueError` for a density at or below 0 (E334) or a diameter
AERMOD would reject (E335). The diameter is checked as the source writer
will print it, to four significant digits, because that is the number
`INPPDM` reads: a mean-mass diameter of 0.00100006 microns is written as
0.001 and rejected, and 1000.04 is written as 1000 and accepted.

The source writer puts `PARTDIAM` and `PARTDENS` on the card to four
significant digits and `MASSFRAX` to six decimal places, so the deck
AERMOD reads rounds the diameters (a settling velocity changes by up to
about 0.1%; 0.07% for the AP-42 example above) and the written fractions
sum to 1 within 5e-7 per bin.

See the [API reference](api/psd.md) for every function.
