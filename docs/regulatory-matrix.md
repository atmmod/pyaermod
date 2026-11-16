# Regulatory Compliance Matrix

pyaermod configurations vs. common regulatory guidance.  Use this as a
checklist when building a modeling protocol — the profile API
(`pyaermod.regulatory`) automates most of these.

## EPA Appendix W (40 CFR 51, 2017 revision)

| Requirement | pyaermod setting |
|---|---|
| DFAULT option in MODELOPT | `ControlPathway.regulatory_default=True` |
| Elevated terrain | `ControlPathway.terrain_type = TerrainType.ELEVATED` |
| Rural/urban dispersion | `ControlPathway.urban_option` per source if urban |
| LOWWIND | not available under DFAULT: the CO LOW_WIND card (`low_wind_option`) and the `LOW_WIND` MODELOPT token need ALPHA (AERMOD E133), and the old `LOWWIND1`/`LOWWIND2`/`LOWWIND3` tokens are no longer MODELOPT options (E203) |
| NO2 chemistry | OLM or PVMRM (set via `ChemistryOptions`) — GRSM and PVMRM2 remain BETA through 2023 |
| Stack-tip downwash | on by default; `NOSTD` in `ControlPathway.extra_model_options` is dropped under DFAULT (AERMOD W206), and the profiles remove it |
| ALPHA / BETA / experimental options | refused under DFAULT (E204): keep `alpha`, `beta` and `psd_credit` False and leave `FASTAREA`, `FASTALL`, `SCIM`, `NOURBTRAN` and the other refused tokens out of `extra_model_options`; `SCREEN` and `NOCHKD` are dropped with W206 (full list: `pyaermod.pathways.DFAULT_MODELOPT_CONFLICTS`) |

Apply with:

```python
from pyaermod import EPA_APPENDIX_W_2017
changes = EPA_APPENDIX_W_2017.apply(project)
warnings = EPA_APPENDIX_W_2017.check(project)
```

## EPA Appendix W (2023 updates)

Same base constraints as 2017. Two new NO2 chemistry methods
(**PVMRM2**, **GRSM**) are available in AERMOD v23132/v24142 but
remain **BETA** (AERMOD v26135 removes the BETA flag from GRSM, which is
still a non-DFAULT option) — they require case-by-case EPA concurrence before
use in a regulatory submittal. `EPA_APPENDIX_W_2023` therefore keeps
only OLM and PVMRM in its `allow_chemistry_methods` tuple; the BETA
set is listed separately in `EPA_APPENDIX_W_2023_BETA_METHODS` for
users with explicit approval.

Other 2023 updates:

- ADJ_U* friction-velocity adjustment is permitted for stable
  conditions with agency review.

Use `EPA_APPENDIX_W_2023` for this profile.

## Screening-level analyses

For scoping runs before a full regulatory submittal:

```python
from pyaermod import SCREENING_PROFILE
SCREENING_PROFILE.apply(project)
```

Screening profile forbids all non-default options, including LOWWIND3.
Tighten to a formal profile before submittal.

## Per-state/agency notes

pyaermod doesn't currently ship state-specific profiles. Build your
own by subclassing `RegulatoryProfile`:

```python
from pyaermod import RegulatoryProfile

CARB_DRAFT_2024 = RegulatoryProfile(
    name="CARB-Draft-2024",
    description="California draft 2024 modeling guidance",
    regulatory_default=True,
    terrain_type="ELEVATED",
    allow_chemistry_methods=("OLM", "PVMRM", "PVMRM2", "GRSM"),  # BETA incl.
    # MODELOPT tokens, as ControlPathway writes them from alpha, beta,
    # psd_credit, terrain_type, chemistry and extra_model_options. The
    # default is every token DFAULT refuses or drops.
    forbid_model_options=("NOSTD", "NOCHKD", "SCREEN", "BETA", "ALPHA"),
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
