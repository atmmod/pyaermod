# Regulatory Compliance Matrix

pyaermod configurations vs. common regulatory guidance.  Use this as a
checklist when building a modeling protocol — the profile API
(`pyaermod.regulatory`) automates most of these.

## EPA Appendix W (40 CFR 51)

Appendix W has two revisions in force since 2017: the 2017 rule
(82 FR 5182, effective May 22, 2017) and the 2024 rule (89 FR 95034,
effective March 21, 2025). There was no 2023 revision. The requirements
below hold under both; the NO2 row is where they differ.

| Requirement | pyaermod setting |
|---|---|
| DFAULT option in MODELOPT | `ControlPathway.regulatory_default=True` |
| Elevated terrain | `ControlPathway.terrain_type = TerrainType.ELEVATED` |
| Rural/urban dispersion | `is_urban=True` on each urban source (URBANSRC); `ControlPathway.urban_areas` (or `urban_option`, the urban area's name) writes URBANOPT |
| Low wind | no option. `CO LOW_WIND` is an ALPHA option, which AERMOD refuses with DFAULT. LOWWIND1, 2 and 3 were BETA options removed in v18081; the 2017 rule declined to adopt LOWWIND3 |
| NO2 (section 4.2.3.4) | Tier 1: no chemistry. Tier 2: ARM2. Tier 3: OLM or PVMRM, and GRSM under the 2024 rule (set via `ChemistryOptions`) |
| Stack-tip downwash | on by default; **don't** add `NOSTD` to `ControlPathway.extra_model_options` |
| ALPHA and BETA options | not permitted under DFAULT (TTRM, TTRM2, RLINEXT and LOW_WIND are ALPHA) |

| Profile | What it is | NO2 methods accepted |
|---|---|---|
| `EPA_APPENDIX_W_2024` | the 2024 rule, with AERMOD v24142 or later | ARM2, OLM, PVMRM, GRSM |
| `EPA_APPENDIX_W_2017` | the 2017 rule | ARM2, OLM, PVMRM |
| `EPA_APPENDIX_W_2023` | the 2017 rule as applied with AERMOD v23132; kept for existing scripts | ARM2, OLM, PVMRM |

Apply with:

```python
from pyaermod import EPA_APPENDIX_W_2024
changes = EPA_APPENDIX_W_2024.apply(project)    # what it changed
findings = EPA_APPENDIX_W_2024.check(project)   # what still conflicts
notes = EPA_APPENDIX_W_2024.advisories(project)
```

`apply` turns on DFAULT, switches off non-default options and removes a
`low_wind_option`. `advisories` returns the Tier 3 note: use of OLM,
PVMRM or GRSM "shall occur in consultation with the EPA Regional Office
in addition to the appropriate reviewing authority" (4.2.3.4(e)). All
three tiers are screening techniques agreed with the reviewing authority.

GRSM entered AERMOD as an ALPHA option in v21112, was a BETA option in
v22112 and v23132 (refused with DFAULT), and is regulatory from v24142.
`EPA_APPENDIX_W_2023_BETA_METHODS` lists it for that reason.

ADJ_U* is chosen in AERMET, not in the AERMOD deck, so no profile checks
it. It has been a regulatory option since the 2017 rule, except with
site-specific turbulence data, where it needs approval as an alternative
model (Appendix W, Addendum A, A.1(b)(2)(ii)).

## Screening-level analyses

For scoping runs before a full regulatory submittal:

```python
from pyaermod import SCREENING_PROFILE
SCREENING_PROFILE.apply(project)
```

The screening profile forbids all non-default options. Tighten to a
formal profile before submittal.

## Per-state/agency notes

pyaermod doesn't ship state-specific profiles. Build your own from
`RegulatoryProfile`:

```python
from pyaermod import RegulatoryProfile

STATE_DRAFT = RegulatoryProfile(
    name="State-Draft",
    description="A state agency's modeling guidance",
    regulatory_default=True,
    terrain_type="ELEVATED",
    allow_chemistry_methods=("ARM2", "OLM", "PVMRM"),
    forbid_nondefault_flags=("FLAT", "NOSTD", "alpha", "beta"),
)
```

## Non-regulatory uses

For research or sensitivity work where DFAULT is not required, set
`regulatory_default=False` explicitly — `advanced_validate` will then
allow non-default options without flagging them.

## What pyaermod does NOT verify

- **Site representativeness** of met data. No automated check for
  distance, land cover similarity, or seasonal coverage.
- **Receptor placement** relative to property boundaries / ambient
  air definitions.
- **Emission rates** vs. permit limits. Presence is checked; values
  are not.
- **Background concentration** source selection. Required set but
  not validated against monitor data.

These are policy / protocol questions your agency contact — not a
Python library — has to answer.
