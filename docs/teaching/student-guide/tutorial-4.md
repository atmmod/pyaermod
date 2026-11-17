# 7. Tutorial 4 — Area Sources: Modeling a Facility with Fugitive Emissions

**Goal:** Model a construction site with three types of area sources —
a rectangular stockpile, a circular staging area, and an irregular polygon
site boundary — alongside a point source (generator exhaust).

**Time:** 25--30 minutes

**What you'll learn:**
- The difference between point source and area source emission rates
- How to add rectangular, circular, and polygonal area sources in the GUI
- How to combine point and area sources in one model
- How source groups let you analyze contributions separately

## Conceptual Background

Not all emissions come from smokestacks. Many facilities also have **fugitive
emissions** — pollutants that escape from ground-level or low-height sources
rather than through a defined stack. Examples include:

| Source | Why It Emits |
|---|---|
| Dirt stockpile | Wind blows dust off exposed surfaces |
| Parking lot | Vehicle exhaust, tire/brake wear, re-entrained road dust |
| Construction site | Earth-moving equipment, exposed soil |
| Tank farm | Vapors escape through tank vents and seals |
| Landfill | Gases seep through the surface over a large area |

These sources are modeled as **area sources** in AERMOD. The key difference
from point sources is how emission rates are specified:

- **Point source**: total mass emitted per second (**g/s**)
- **Area source**: mass emitted per second *per unit area* (**g/s/m2**)

Because area sources spread emissions over a large surface, the per-square-meter
rate is typically a very small number (e.g., 0.0001 g/s/m2).

> **Example calculation:**
> A 100 m x 50 m stockpile emits 0.5 g/s total.
> Area = 100 x 50 = 5,000 m2.
> Emission rate = 0.5 / 5,000 = **0.0001 g/s/m2**.

## Step 1: Set Up the Project

1. Launch the GUI (`pyaermod-app`).
2. On the **Project** step:
   - **Title (line 1):** `Tutorial 4 - Area Source Facility`
   - **Title (line 2):** `Construction site with mixed source types`
   - **Pollutant:** `PM10`
   - **Averaging periods:** Select `24` and `ANNUAL`
   - **Terrain:** `Flat (FLAT)`, with **Regulatory default options (DFAULT)**
     unticked

## Step 2: Add a Point Source (Generator)

1. Click **Sources** in the step list.
2. Set **Type** to `PointSource` and click **Add**.
3. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `GENSET` | Diesel generator exhaust |
   | X coord (m) | `500050` | UTM meters |
   | Y coord (m) | `3870050` | UTM meters |
   | Base elevation (m), under **Advanced** | `0` | |
   | Stack height (m) | `5` | Short exhaust stack |
   | Stack temp (K) | `700` | Diesel exhaust is very hot (K) |
   | Exit velocity (m/s) | `10` | |
   | Stack diameter (m) | `0.3` | Small pipe |
   | Emission rate (g/s) | `0.3` | 0.3 g/s of PM10 |

4. Click **Save**.

> **Why start with the point source?** It gives you a reference marker in the
> plan view. You'll place the area sources around it.

## Step 3: Add a Rectangular Area Source (Stockpile)

1. Set **Type** to `AreaSource` and click **Add**.
2. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `PILE1` | Dirt/gravel stockpile |
   | X coord (m) | `500000` | Southwest corner X |
   | Y coord (m) | `3870000` | Southwest corner Y |
   | Base elevation (m), under **Advanced** | `0` | |
   | Release height (m) | `2.0` | Dust lifts off ~2 m above the pile surface |
   | Initial lateral dimension (m) | `100.0` | Xinit, the X side: 100 m in the X direction |
   | Initial vertical dimension (m) | `50.0` | Yinit, the Y side: 50 m in the Y direction |
   | Angle (deg) | `0` | Aligned with the grid (no rotation) |
   | Emission rate (g/(s·m²)) | `0.000100` | 0.0001 g/s/m2 (see calculation above) |

3. Click **Save**.

> **Understanding the dimensions:** AERMOD places a rectangular area source by
> its *southwest corner* and gives it *full side lengths*: Xinit is the length
> of the X side and Yinit the length of the Y side (`SRCPARAM`, soset.f APARM).
> A rotation angle turns the rectangle clockwise about that corner, not about
> its centre. Enter the actual dimensions, not half of them.

## Step 4: Add a Circular Area Source (Staging Area)

1. Set **Type** to `AreaCircSource` and click **Add**.
2. Fill in the form:

   | Parameter | Value | What It Represents |
   |---|---|---|
   | Source ID | `STAGING` | Equipment staging / laydown area |
   | X coord (m) | `500200` | Center of the circle |
   | Y coord (m) | `3870100` | |
   | Base elevation (m), under **Advanced** | `0` | |
   | Release height (m) | `1.0` | Low-level dust from vehicle traffic |
   | Radius (m) | `60` | 60 m radius circle |
   | Num vertices, under **Advanced** | `20` | How many sides to approximate the circle |
   | Emission rate (g/(s·m²)) | `0.000050` | Lower rate — less disturbed surface |

3. Click **Save**.

> **Num Vertices:** AERMOD approximates circles as polygons. 20 vertices gives
> a smooth-enough circle for most purposes. More vertices is more accurate but
> takes slightly longer to compute.

## Step 5: Add a Polygonal Area Source (Site Boundary)

1. Set **Type** to `AreaPolySource` and click **Add**.
2. Fill in the form:

   | Parameter | Value |
   |---|---|
   | Source ID | `SITEBND` |
   | Base elevation (m), under **Advanced** | `0` |
   | Release height (m) | `0.5` |
   | Emission rate (g/(s·m²)) | `0.000020` |

3. In **Vertices (m)**, replace the placeholder with the five corners of the
   irregular site boundary, one `x, y` pair per line:

   ```
   499900, 3869900
   500350, 3869900
   500400, 3870100
   500300, 3870250
   499900, 3870200
   ```

4. Click **Save**.

> **Vertex order matters:** The vertices should trace the outline of the area
> in order (clockwise or counterclockwise). AERMOD closes the polygon
> automatically — you don't need to repeat the first vertex.

## Step 6: Set Up Receptors

1. Click **Receptors** in the step list.
2. Set **Type** to `CartesianGrid`, click **Add**, and enter:

   | Parameter | Value |
   |---|---|
   | X init (m) | `499500` |
   | X num | `27` |
   | X delta (m) | `50` |
   | Y init (m) | `3869500` |
   | Y num | `25` |
   | Y delta (m) | `50` |

3. Click **Save**. The grid runs from 499500 to 500800 east and from 3869500
   to 3870700 north: 27 x 25 = 675 receptors covering the site and a buffer
   zone around it.

## Step 7: Meteorology and Preview

1. Click **Meteorology** and enter the paths to your `.sfc` and `.pfl` files
   in **Surface file** and **Profile file** (or placeholder names for now).
2. Click **Review & Run** to preview the generated input file.

In the **Deck preview**, look for the `SO` pathway.
You should see four sources — one POINT and three area types:

```
   LOCATION  GENSET   POINT   500050.0000 3870050.0000     0.00
   LOCATION  PILE1    AREA     500000.0000 3870000.0000     0.00
   LOCATION  STAGING  AREACIRC  500200.0000 3870100.0000     0.00
   LOCATION  SITEBND  AREAPOLY  499900.0000 3869900.0000     0.00
```

Notice how each source type generates different `SRCPARAM` lines:
- **POINT**: emission rate, stack height, temperature, velocity, diameter
- **AREA**: emission rate, release height, X side length, Y side length (then
  an optional angle and initial vertical spread Szinit)
- **AREACIRC**: emission rate, release height, radius, number of vertices
- **AREAPOLY**: emission rate, release height, number of vertices (the
  corners follow on an `AREAVERT` line)

## Step 8: Interpret Area Source Results (After Running)

When you eventually run this model, look for these patterns in the Results
step's concentration map:

- **The generator (point source)** produces a concentrated plume downwind of
  the stack — a narrow elongated shape.
- **The stockpile (rectangular area)** produces a broader, lower-concentration
  pattern centered on the pile. Concentrations are highest at the downwind
  edge of the pile.
- **The site boundary (polygon)** produces the most diffuse pattern — low
  concentrations spread over a wide area.
- **Combined impact** is highest where plumes from multiple sources overlap.

## Checkpoint

At this point you should understand:

- [x] Area source emission rates are per unit area (g/s/m2), not total (g/s)
- [x] Rectangular area sources are placed by their southwest corner and
  defined by full side lengths, not half-widths
- [x] Circular sources are approximated by polygons (Num Vertices)
- [x] Polygon sources are defined by a list of corner coordinates
- [x] Different source types produce different spatial patterns in results
