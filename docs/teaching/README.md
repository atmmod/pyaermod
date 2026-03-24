# Teaching Materials

Student-facing guides for learning atmospheric dispersion modeling with PyAERMOD.

## Contents

- **[student-guide.md](student-guide.md)** — Conceptual introduction to air dispersion modeling and five hands-on tutorials using the PyAERMOD GUI. No coding required. Start here.
- **[refinery-assignments.md](refinery-assignments.md)** — Advanced tutorials (6--8): AERMET for Houston, terrain processing with AERMAP, and a complete oil refinery dispersion model. Builds on the student guide.

## Prerequisites

Students need:

- Python 3.11+ installed
- PyAERMOD with GUI extras: `pip install pyaermod[gui]`
- A web browser (Chrome, Firefox, Safari, or Edge)
- AERMOD executable from [EPA SCRAM](https://www.epa.gov/scram) (needed for Tutorials 3+)
- AERMET executable from [EPA SCRAM](https://www.epa.gov/scram) (needed for Tutorials 5--6)
- AERMAP executable from [EPA SCRAM](https://www.epa.gov/scram) (needed for Tutorial 7)
- Meteorological data files (instructor-provided, needed for Tutorials 5--6)
- DEM elevation data (instructor-provided or downloaded, needed for Tutorial 7)

## Suggested Course Integration

| Week | Activity | Guide Section |
|------|----------|---------------|
| 1 | Read conceptual background | Sections 1--3 |
| 1 | Tutorial 1: Build your first model | Section 4 |
| 2 | Tutorial 2: Compare two scenarios | Section 5 |
| 2--3 | Tutorial 3: Run AERMOD and interpret results | Section 6 |
| 3 | Tutorial 4: Area sources and mixed-source facilities | Section 7 |
| 4 | Tutorial 5: Process meteorological data with AERMET | Section 8 |
| 5 | Tutorial 6: AERMET for Houston, Texas | refinery-assignments.md |
| 5--6 | Tutorial 7: Terrain processing with AERMAP | refinery-assignments.md |
| 6--8 | Tutorial 8: Full Houston refinery model + report | refinery-assignments.md |
