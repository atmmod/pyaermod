# Recorded AERMOD settling velocities for `pyaermod.psd`

One real AERMOD run. `tests/test_psd.py` reads it to pin
`pyaermod.psd.settling_velocity` against AERMOD's own `VDP1` and to show
that `aerodynamic_to_stokes` gives AERMOD the settling velocity it
promises. None of the files is hand-edited.

- **Program:** AERMOD v26135, EPA's source archive `aermod_source.zip`
  (top-level directory `aermod_source_v26135`).
- **Build:** the `scripts/build_aermod.sh` pattern (`-O2 -fbounds-check
  -Wuninitialized`) with GNU Fortran 15.2.0.
- **Recorded:** 2026-09-29, on macOS arm64.
- **Meteorology:** `../epa_official/AERMET2.SFC` and `AERMET2.PFL`
  (Albany, New York), one hour: 1 March 1988, hour 12. The deck names the
  files without a directory, so a run needs copies beside the deck;
  `regenerate.sh` makes them.

`aermod.inp` has four point sources, each with the same sixteen size
categories (0.0625 of the mass in each). The categories are the
mean-mass diameters of the bins with edges 0.5, 1, 1.6, 2.5, 3.5, 5, 7, 10,
12.5, 15, 20, 25, 30, 40, 50, 62.5 and 75 microns, as
`SizeDistribution.diameters()` computes them, written to six significant
digits.

| Source | `PARTDIAM` | `PARTDENS` |
|---|---|---|
| `AERO1` | the mean-mass (aerodynamic) diameters | 1.0 |
| `AERO265` | the same diameters | 2.65 |
| `STOKES` | `aerodynamic_to_stokes(d, 2.65)` of each | 2.65 |
| `NAIVE` | `aerodynamic_to_stokes(d, 2.65, slip=False)`, that is `d / sqrt(2.65)` | 2.65 |

`CO DEBUGOPT DEPOS` makes AERMOD write `PDEP.DAT`: for each hour, source
(`ISRC`, in deck order) and size category (`ICAT`), the aerodynamic
resistance, the deposition-layer resistance, the gravitational settling
velocity `Vg(i)` (m/s) and the deposition velocity. `Vg` is the
`AVGRAV` that `soset.f` subroutine `VDP1` computed, printed to six
significant digits. `aermod.out` is the run's main output; AERMOD
reports 0 fatal errors and one warning (W403, turbulence data used
without `ADJ_U*`) and `*** AERMOD Finishes Successfully ***`.

What the recording shows:

- `settling_velocity(d, rho)` equals AERMOD's `Vg` for all 64 categories
  to the digits AERMOD prints.
- `STOKES` settles like `AERO1` bin by bin, to the digits AERMOD prints.
- `AERO265` settles 2.652 times faster than `AERO1`: the same diameter
  at a higher density is a different, larger aerodynamic size.
- `NAIVE` settles faster than `AERO1`: by 11% in the 0.78-micron
  category, 1.0% at 11.3 microns and 0.2% at 68.9. `d / sqrt(rho)`
  ignores the slip factor, and the smaller Stokes diameter slips more
  than the aerodynamic one.

Re-record with `tests/fixtures/psd/regenerate.sh path/to/aermod`.
