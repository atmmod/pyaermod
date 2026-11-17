# 5. Tutorial 2 — Comparing Stack Heights

**Goal:** Create two versions of the same facility — one with a 20 m stack and
one with a 60 m stack — to understand how stack height affects ground-level
concentrations.

**Time:** 15--20 minutes

**What you'll learn:**
- How stack height controls plume rise and ground-level impact
- How to save and reopen project files to create scenario variants
- How to read an AERMOD input file and spot key differences

## Conceptual Background

Imagine two identical factories, both emitting 2 g/s of SO2. The only
difference is the smokestack:

- **Factory A:** 20 m stack (about 6 stories tall)
- **Factory B:** 60 m stack (about 20 stories tall)

Which factory will cause higher ground-level concentrations? Intuitively,
Factory A — its emissions are released closer to the ground, so they have
less distance to dilute before reaching people.

But *how much* of a difference does it make? That's exactly what AERMOD
calculates.

## Step 1: Build the Base Scenario

Follow the same steps as Tutorial 1, but with these settings:

**Project:**
- Title (line 1): `Tutorial 2 - Stack Height Comparison (20m)`
- Pollutant: `SO2`
- Averaging periods: `1`, `24`, and `ANNUAL`
- Terrain: `Flat (FLAT)`, with **Regulatory default options (DFAULT)** unticked

**Source (`PointSource`):**
- Source ID: `STACK1`
- Stack height (m): `20`
- Stack temp (K): `420`
- Exit velocity (m/s): `15`
- Stack diameter (m): `2`
- Emission rate (g/s): `2.0`

**Receptors (`CartesianGrid`):**
- 4 km x 4 km area centered on the source, 100 m spacing
  (X num and Y num `41`, X delta and Y delta `100`)

**Meteorology:**
- Surface file: `met_data.sfc`
- Profile file: `met_data.pfl`

## Step 2: Save the Project

1. Go back to the **Project** step.
2. Click **Save as...**, enter the filename `tutorial2_20m.json` and click
   **Save**. Your browser downloads the project as a JSON file.

## Step 3: Download the 20 m Input File

1. Go to **Review & Run**.
2. Click **Download deck**. Rename the downloaded file `stack_20m.inp`.

## Step 4: Create the 60 m Variant

1. Go to **Sources**.
2. Click the **Edit** button on the `STACK1` row of the table.
3. Change **Stack height (m)** to `60` and click **Save**. Everything else
   stays the same.
4. On the **Project** step, update the title to
   `Tutorial 2 - Stack Height Comparison (60m)`.
5. Save this project as `tutorial2_60m.json` (**Save as...**).
6. Download the input file and rename it `stack_60m.inp`.

## Step 5: Compare the Input Files

Open both `.inp` files in a text editor and find the `SRCPARAM` line of the
`SO` pathway:

**20 m stack:**
```
   SRCPARAM  STACK1     2.000000    20.00   420.00    15.00     2.00
```

**60 m stack:**
```
   SRCPARAM  STACK1     2.000000    60.00   420.00    15.00     2.00
```

The only difference is the second number (stack height); the title line
differs too. Everything else is
identical, making this a controlled experiment.

## What to Expect When You Run These (Tutorial 3)

When you eventually run both files through AERMOD with real meteorological data:

- The **20 m stack** will produce **higher** maximum ground-level concentrations,
  especially close to the source (within 500 m).
- The **60 m stack** will produce **lower** maximum concentrations because the
  plume is released higher and has more room to dilute.
- The **location** of the maximum concentration will also shift — taller stacks
  push the peak concentration **farther downwind** because the plume takes
  longer to mix down to ground level.

This is a fundamental principle in air quality engineering: **effective stack
height is the single most important factor for ground-level concentrations**
from a point source.

## Checkpoint

At this point you should understand:

- [x] Taller stacks reduce ground-level concentrations
- [x] Taller stacks push the peak concentration farther downwind
- [x] Saving the project under a new name (**Save as...**) lets you create
  scenario variants; **Open...** brings one back
- [x] The `SRCPARAM` line of the `SO` pathway contains all point source
  parameters
