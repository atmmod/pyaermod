# 9. What's Next?

Now that you've completed all five tutorials, here are some directions to
explore:

## Advanced Tutorials: Houston Refinery Modeling (Tutorials 6--8)

The **[Houston Refinery Modeling Assignments](../refinery-assignments.md)**
extend this guide with three advanced tutorials that take you through a
realistic industrial modeling project:

- **Tutorial 6** — Process meteorological data with AERMET for a specific
  Gulf Coast location (Houston Ship Channel), with site-appropriate surface
  parameters for a coastal/industrial area.
- **Tutorial 7** — Use AERMAP to process digital elevation data and assign
  terrain elevations to all receptors and sources, even in a relatively
  flat area like Houston.
- **Tutorial 8** — Build a complete AERMOD model for a simplified 150,000
  barrel-per-day petroleum refinery with 10 emission sources (point, area,
  and volume), multi-scale receptors, source groups, regulatory compliance
  analysis, and sensitivity studies. Includes a technical report assignment.

These tutorials build directly on the skills from Tutorials 1--5 and
include assignment deliverables and a grading rubric suitable for a
university course.

## Multiple Sources and Source Groups

Add several stacks and area sources to the same project and see how their
plumes overlap. Use **source groups** (on the Sources step, each source's
**Source groups** field under **Advanced**, one group name per line) to
separate contributions from different parts of a facility — for example,
"STACKS" vs. "FUGITIVE" — and compare their relative impact.

## Terrain Effects

Change **Terrain** on the Project step from Flat to Elevated. Elevated terrain can
significantly increase concentrations on hilltops that are close to the
effective plume height. This requires terrain elevation data processed by
AERMAP.

## Background Concentrations

Real-world air quality is never zero — there's always some background
pollution from regional sources, traffic, and natural sources. AERMOD can add
a background concentration to its predictions. The GUI cannot enter one yet;
set it from Python (see Notebook 07) and open the saved project in the GUI.

## The Python API

Once you're comfortable with the GUI concepts, try the Jupyter notebooks in
`examples/notebooks/` to do the same work with Python code. The Python API
gives you more flexibility for parameter sweeps, batch runs, and custom
analysis.

## Useful References

- [AERMOD User's Guide (EPA)](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models#aermod) —
  The official 300+ page reference for all AERMOD options.
- [AERMOD Model Formulation Document (EPA)](https://www.epa.gov/scram) —
  The mathematical basis behind the model.
- [AERMET User's Guide (EPA)](https://www.epa.gov/scram) —
  Detailed documentation of all AERMET options and data formats.
- [40 CFR Part 51, Appendix W](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-51/appendix-Appendix%20W%20to%20Part%2051) —
  EPA's Guideline on Air Quality Models (the regulatory framework for when
  and how to use AERMOD).
