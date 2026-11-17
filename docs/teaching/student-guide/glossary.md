# 10. Glossary

| Term | Definition |
|---|---|
| **AERMOD** | AMS/EPA Regulatory Model — the U.S. EPA's preferred near-field dispersion model |
| **AERMET** | AERMOD's meteorological preprocessor; converts raw weather data into `.sfc` and `.pfl` files |
| **AERMAP** | AERMOD's terrain preprocessor; extracts elevation data for receptors and sources |
| **Averaging period** | The time window over which concentrations are averaged (1-hour, 24-hour, annual, etc.) |
| **Base elevation** | The ground-level elevation at the base of a source or receptor (meters above sea level) |
| **Buoyancy rise** | The upward motion of a hot plume due to its lower density relative to ambient air |
| **Cartesian grid** | A rectangular array of evenly spaced receptor points |
| **Concentration** | The amount of pollutant in a given volume of air, typically in ug/m3 |
| **Discrete receptor** | A single receptor placed at a specific location of interest |
| **Effective stack height** | Physical stack height + plume rise; the height at which the plume levels off |
| **Emission rate** | The mass of pollutant released per unit time (g/s for point sources, g/s/m2 for area sources) |
| **Exceedance** | When a predicted concentration is higher than the applicable air quality standard |
| **Exit velocity** | Speed of exhaust gas leaving the stack (m/s) |
| **Gaussian plume** | A mathematical model where pollutant concentration follows a bell curve in both horizontal and vertical cross-sections |
| **Momentum rise** | The upward motion of a plume due to the velocity of the exhaust gas |
| **NAAQS** | National Ambient Air Quality Standards — EPA's health-based concentration limits |
| **Pathway** | One of AERMOD's five input sections: CO (Control), SO (Source), RE (Receptor), ME (Meteorology), OU (Output) |
| **Plume rise** | The total height gain of exhaust gas above the physical stack top, from both buoyancy and momentum |
| **Polar grid** | A set of receptor points arranged in concentric rings at regular angular intervals around a center point |
| **POSTFILE** | An optional AERMOD output file containing concentration values at every receptor for every hour |
| **Receptor** | A location where AERMOD calculates ground-level pollutant concentration |
| **Source group** | A named subset of emission sources whose combined impact is reported separately |
| **Stability** | A measure of atmospheric turbulence: unstable (strong mixing), neutral, or stable (weak mixing) |
| **Steady-state** | An assumption that conditions (wind, stability) are constant during each simulation hour |
| **Albedo** | The fraction of incoming sunlight reflected by the ground surface (0 = absorbs all, 1 = reflects all). Fresh snow ~0.7, dark pavement ~0.1 |
| **Bowen ratio** | Ratio of sensible heat flux to latent heat flux at the surface. High values (dry/urban), low values (moist/vegetated) |
| **Friction velocity** | A measure of wind-driven turbulence near the ground surface (m/s). Higher values mean more mechanical mixing |
| **Fugitive emissions** | Pollutants released from diffuse, ground-level sources (piles, lots, open areas) rather than through defined stacks |
| **Initial side lengths (Xinit, Yinit)** | AERMOD defines a rectangular area source by its southwest corner and the full length of its x and y sides (not half-widths); a rotation turns it clockwise about that corner |
| **ISHD** | Integrated Surface Hourly Data — NOAA's standard format for recent U.S. surface weather observations |
| **Mixing height** | The depth of the atmospheric boundary layer (meters). Pollutants released below this height mix vertically within it |
| **Monin-Obukhov length** | A parameter characterizing atmospheric stability. Negative = unstable (good mixing), positive = stable (poor mixing) |
| **Radiosonde** | An instrument carried aloft by a weather balloon to measure vertical profiles of temperature, humidity, and wind |
| **Roughness length** | Aerodynamic parameter describing how rough the ground surface is to wind flow. Open water ~0.001 m, city center ~1.0 m |
| **Surface characteristics** | Albedo, Bowen ratio, and roughness length — the three land-surface parameters AERMET needs for each month |
| **UTM** | Universal Transverse Mercator — a coordinate system that measures position in meters (easting, northing) within numbered zones |
