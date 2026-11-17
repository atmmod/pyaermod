# Air Dispersion Modeling and Key Concepts

## 1. What Is Air Dispersion Modeling?

When a factory, power plant, or vehicle emits pollutants into the air, those
pollutants don't stay in one place. Wind carries them downwind, and turbulence
spreads them out in all directions. An **air dispersion model** is a computer
program that predicts *where* those pollutants go and *how concentrated* they
are at ground level.

### Why Does It Matter?

- **Protecting public health.** Regulatory agencies (like the U.S. EPA) use
  dispersion models to decide whether a proposed factory will cause air quality
  problems in nearby neighborhoods.
- **Designing better facilities.** Engineers use models to determine how tall a
  smokestack needs to be, or whether adding a scrubber will bring concentrations
  below safe limits.
- **Emergency planning.** If there's an accidental release of a toxic gas,
  models help predict which areas might be affected.

### What Is AERMOD?

**AERMOD** (AMS/EPA Regulatory Model) is the U.S. EPA's preferred model for
near-field (< 50 km) regulatory air quality assessments. It has been the
standard since 2005 and is used worldwide.

AERMOD is a **steady-state Gaussian plume model**, which means:

- **Steady-state**: it assumes meteorological conditions are constant during
  each hour of simulation.
- **Gaussian plume**: it models the spreading pollutant cloud as a bell-shaped
  (Gaussian) distribution in both the horizontal and vertical directions.

PyAERMOD is a Python wrapper that lets you set up, run, and analyze AERMOD
models through a graphical interface or Python code, instead of editing text
files by hand.

## 2. Key Concepts

Before diving into the tutorials, here are the core ideas you'll need.

### 2.1 Emission Sources

An **emission source** is anything that releases pollutants into the air.
AERMOD supports several types:

| Source Type | Real-World Example |
|---|---|
| **Point** | Smokestack, exhaust vent |
| **Area** | Storage pile, parking lot, landfill |
| **Volume** | Conveyor transfer point, building vent |
| **Line** | Roadway, railway, pipeline |
| **Open Pit** | Quarry, surface mine |

For these tutorials, we'll focus on **point sources** (smokestacks) because
they're the most common and the easiest to understand.

#### Key Point Source Parameters

- **Stack height** (meters): How tall the smokestack is. Taller stacks release
  pollutants higher up, giving them more time to dilute before reaching the
  ground.
- **Stack diameter** (meters): The inner diameter of the stack opening.
- **Exit velocity** (m/s): How fast the exhaust gas leaves the stack. Faster
  gas shoots the plume higher (this is called **momentum rise**).
- **Exit temperature** (Kelvin): Hot exhaust gas is buoyant — it rises because
  it's lighter than the surrounding air. This is called **buoyancy rise**. The
  combination of momentum and buoyancy rise is called **plume rise**.
- **Emission rate** (g/s): The mass of pollutant released per second.

> **Intuition:** Imagine holding a lit candle. The hot smoke rises (buoyancy).
> If you blow on it, the smoke bends sideways (wind). If you raise the candle
> overhead, the smoke takes longer to reach the floor (stack height). These are
> the same physics AERMOD captures mathematically.

### 2.2 Receptors

**Receptors** are the locations where AERMOD calculates the ground-level
pollutant concentration. Think of them as virtual air quality monitors placed
across a map.

Common receptor layouts:

- **Cartesian grid**: A regular rectangular grid of points (like graph paper
  laid over a map). You specify the boundaries and spacing. A 2 km x 2 km
  area with 100 m spacing gives 441 receptors.
- **Polar grid**: Rings of points radiating out from a central location (like a
  dartboard). Useful for studying how concentration changes with distance from
  a source.
- **Discrete receptors**: Individual points at specific locations of interest
  (a school, a hospital, a property boundary).

### 2.3 Meteorology

Wind and atmospheric stability are the two most important factors controlling
dispersion:

- **Wind speed and direction** determine where the plume goes.
- **Atmospheric stability** determines how much the plume spreads:
  - **Unstable** (sunny daytime): strong vertical mixing, plume spreads
    rapidly, concentrations drop quickly with distance.
  - **Stable** (clear nighttime): weak mixing, plume stays narrow and compact,
    can travel far with less dilution.
  - **Neutral** (overcast, windy): moderate mixing.

AERMOD uses **hourly meteorological data** — typically one to five years of
observations from a nearby weather station, preprocessed by the AERMET
program into `.sfc` (surface) and `.pfl` (profile) files. For tutorials 1
and 2 you won't need actual met data because we'll only generate the input
file. Tutorial 3 shows how to connect real meteorological files.

### 2.4 What AERMOD Produces

For each receptor, AERMOD calculates the **pollutant concentration** (typically
in micrograms per cubic meter, ug/m3) for each hour of the simulation. It then
computes summary statistics:

- **Annual average** — the mean concentration over all hours. Compared to the
  annual NAAQS (National Ambient Air Quality Standard).
- **24-hour average** — the highest 24-hour average over the simulation period.
- **1-hour average** — the highest single-hour concentration.

The results let you answer questions like: *"Will this factory cause the
annual PM2.5 concentration at the nearest school to exceed 12 ug/m3?"*

### 2.5 The Modeling Workflow

Every AERMOD analysis follows this sequence:

```
Define the problem
       |
       v
Set up sources, receptors, and meteorology
       |
       v
Generate the AERMOD input file (.inp)
       |
       v
Run AERMOD  -->  Output file (.out)
       |
       v
Analyze results (tables, maps, compliance checks)
```

The PyAERMOD GUI walks you through each of these steps in order.
