"""
PyAERMOD regulatory-profile presets.

Codifies the "AERMOD as-used by regulators" configurations so users
don't have to remember the set of ControlPathway flags that make a
run compliant with a given agency's guidance.

Each `RegulatoryProfile` is a bundle of settings and lints. Applying a
profile to a project:

    from pyaermod import EPA_APPENDIX_W_2024
    changes = EPA_APPENDIX_W_2024.apply(project)   # what it changed
    findings = EPA_APPENDIX_W_2024.check(project)  # what still conflicts
    notes = EPA_APPENDIX_W_2024.advisories(project)

`apply` never raises; `check` lists what remains.

Sources:
- 40 CFR 51 Appendix W ("Guideline on Air Quality Models"): the 2017
  revision (82 FR 5182, effective 2017-05-22) and the 2024 revision
  (89 FR 95034, effective 2025-03-21). There was no 2023 revision.
- The AERMOD User's Guide (EPA-454/B-26-001, v26135), sections 3.2.2,
  3.2.3 and 3.2.5, and the MODELOPT checks in AERMOD's ``coset.f``
  (v23132, v24142, v26135).

What the profiles cannot see: ADJ_U* is chosen in AERMET and read by
AERMOD from the surface file's header. It has been a regulatory option
since the 2017 rule, except with site-specific turbulence data, where
it needs approval as an alternative model (Appendix W, Addendum A,
A.1(b)(2)(ii); AERMOD stops with E401 under DFAULT).

NOTE: This module encodes *defaults and lints* — final regulatory
acceptance is always the agency's call. Consider the output advisory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

_TERRAIN_ALIASES = {
    "ELEV": {"ELEV", "ELEVATED"},
    "ELEVATED": {"ELEV", "ELEVATED"},
    "FLAT": {"FLAT"},
    "FLATSRCS": {"FLATSRCS"},
}


def _terrain_matches(current: str, expected: str) -> bool:
    """Return True if `current` satisfies the profile's `expected` value.

    AERMOD accepts both "ELEV" and "ELEVATED" for the same model
    option, so we treat them as equivalent.
    """
    return current.upper() in _TERRAIN_ALIASES.get(expected.upper(), {expected.upper()})


#: Names ``forbid_nondefault_flags`` used before it named real switches:
#: none was a ControlPathway attribute, so they never matched anything.
_LEGACY_FLAG_NAMES = {
    "flat_terrain": "FLAT",
    "no_stack_tip_downwash": "NOSTD",
    "use_lowwind1": "LOWWIND1",
    "use_lowwind2": "LOWWIND2",
    "use_lowwind3": "LOWWIND3",
    "beta_options": "beta",
}

_FLAT_TERRAINS = {"FLAT", "FLATSRCS"}


def _terrain_name(ctrl: Any) -> str:
    return str(getattr(ctrl.terrain_type, "value", ctrl.terrain_type)).upper()


class _NondefaultOption:
    """One ``forbid_nondefault_flags`` entry, resolved to the switch that
    puts it on MODELOPT: a boolean ControlPathway field, or a token in
    ``extra_model_options`` (FLAT also via ``terrain_type``)."""

    def __init__(self, entry: str):
        self.name = _LEGACY_FLAG_NAMES.get(entry, entry)

    def _field(self, ctrl: Any) -> bool:
        return isinstance(getattr(ctrl, self.name, None), bool)

    @property
    def label(self) -> str:
        return f"MODELOPT {self.name.upper().replace('_', '')}"

    def is_set(self, ctrl: Any) -> bool:
        if self._field(ctrl):
            return bool(getattr(ctrl, self.name))
        token = self.name.upper()
        extra = {str(o).upper() for o in getattr(ctrl, "extra_model_options", None) or []}
        if token == "FLAT":
            return bool(extra & _FLAT_TERRAINS) or _terrain_name(ctrl) in _FLAT_TERRAINS
        return token in extra

    def clear(self, ctrl: Any, terrain: str) -> None:
        if self._field(ctrl):
            setattr(ctrl, self.name, False)
            return
        token = self.name.upper()
        drop = _FLAT_TERRAINS if token == "FLAT" else {token}
        ctrl.extra_model_options = [o for o in getattr(ctrl, "extra_model_options", None) or []
                                    if str(o).upper() not in drop]
        if token == "FLAT" and _terrain_name(ctrl) in _FLAT_TERRAINS:
            ctrl.terrain_type = terrain if terrain.upper() not in _FLAT_TERRAINS else "ELEV"


@dataclass
class RegulatoryProfile:
    """A named bundle of AERMOD regulatory settings.

    Attributes
    ----------
    name : str
        Short identifier (e.g. "EPA-AppendixW-2024").
    description : str
        One-paragraph summary.
    regulatory_default : bool
        Whether to require DFAULT in MODELOPT.
    terrain_type : str
        Required TerrainType value ("ELEVATED" / "FLAT"). Profiles usually
        mandate "ELEVATED" since it subsumes flat cases (AERMOD also
        accepts the short form "ELEV").
    allowed_low_wind : tuple of str
        ``low_wind_option`` values the profile accepts. Empty in every
        profile here: ``CO LOW_WIND`` is an ALPHA option, which AERMOD
        refuses beside DFAULT (E133, E204), and no revision of Appendix W
        names a low-wind option. LOWWIND1, 2 and 3 were BETA options
        removed in AERMOD v18081; the 2017 rule declined to adopt
        LOWWIND3.
    allow_chemistry_methods : tuple of str
        Names of ChemistryMethod enum values the profile accepts for NO2
        (Appendix W 4.2.3.4): ARM2 is Tier 2; OLM, PVMRM and, from the
        2024 revision, GRSM are Tier 3. No chemistry is Tier 1.
    tier3_chemistry_methods : tuple of str
        Methods for which :meth:`advisories` recalls the Tier 3
        consultation of Appendix W 4.2.3.4(e).
    forbid_nondefault_flags : tuple of str
        Non-default options the profile forbids. Each entry is a boolean
        ControlPathway field (``alpha``, ``beta``, ``psd_credit``) or a
        MODELOPT token looked for in ``extra_model_options`` (``NOSTD``,
        ``FASTAREA``, ...; ``FLAT`` also matches a FLAT/FLATSRCS
        ``terrain_type``). The older names ``flat_terrain``,
        ``no_stack_tip_downwash``, ``use_lowwind1``/``2``/``3`` and
        ``beta_options`` are read as ``FLAT``, ``NOSTD``,
        ``LOWWIND1``/``2``/``3`` and ``beta``.
    notes : list of str
        Free-form explanatory text.
    """
    name: str
    description: str
    regulatory_default: bool = True
    terrain_type: str = "ELEVATED"
    allowed_low_wind: tuple = ()
    allow_chemistry_methods: tuple = ("ARM2", "OLM", "PVMRM", "GRSM")
    tier3_chemistry_methods: tuple = ("OLM", "PVMRM", "GRSM")
    forbid_nondefault_flags: tuple = (
        "flat_terrain",  # FLAT is a non-default in DFAULT mode
        "no_stack_tip_downwash",
        "use_lowwind1",
        "use_lowwind2",
        "beta_options",
        "alpha",  # AERMOD refuses ALPHA beside DFAULT (E204)
    )
    notes: List[str] = field(default_factory=list)

    # --- application --------------------------------------------------

    def apply(self, project: Any) -> List[str]:
        """Apply the profile's settings to a project in-place.

        Returns the list of changes made, each as a human-readable string.
        Does NOT raise — use `check()` afterwards if you want strictness.
        """
        changes: List[str] = []
        ctrl = project.control

        if ctrl.regulatory_default != self.regulatory_default:
            ctrl.regulatory_default = self.regulatory_default
            changes.append(f"regulatory_default -> {self.regulatory_default}")

        # Terrain: only override if user has a conflicting setting
        current_terrain = (
            ctrl.terrain_type.value
            if hasattr(ctrl.terrain_type, "value")
            else ctrl.terrain_type
        )
        if not _terrain_matches(current_terrain, self.terrain_type):
            ctrl.terrain_type = self.terrain_type
            changes.append(f"terrain_type {current_terrain} -> {self.terrain_type}")

        # Forbid non-default flags
        for entry in self.forbid_nondefault_flags:
            option = _NondefaultOption(entry)
            if option.is_set(ctrl):
                option.clear(ctrl, self.terrain_type)
                changes.append(f"disabled non-default {entry} ({option.label})")

        lwo = getattr(ctrl, "low_wind_option", None)
        if lwo and lwo not in self.allowed_low_wind:
            ctrl.low_wind_option = None
            changes.append(f"removed low_wind_option '{lwo}' (CO LOW_WIND)")

        return changes

    # --- lint ---------------------------------------------------------

    def check(self, project: Any) -> List[str]:
        """Return a list of regulatory lint warnings for the project.

        Unlike `apply`, this does not mutate the project. Use to audit
        a project before submission without changing it.
        """
        warnings: List[str] = []
        ctrl = project.control

        if ctrl.regulatory_default != self.regulatory_default:
            warnings.append(
                f"{self.name}: regulatory_default={ctrl.regulatory_default} "
                f"but profile requires {self.regulatory_default}"
            )

        current_terrain = (
            ctrl.terrain_type.value
            if hasattr(ctrl.terrain_type, "value")
            else ctrl.terrain_type
        )
        if not _terrain_matches(current_terrain, self.terrain_type):
            warnings.append(
                f"{self.name}: terrain_type='{current_terrain}' but profile "
                f"expects '{self.terrain_type}'"
            )

        for entry in self.forbid_nondefault_flags:
            option = _NondefaultOption(entry)
            if option.is_set(ctrl):
                warnings.append(
                    f"{self.name}: non-default option '{entry}' ({option.label}) is "
                    "set — regulatory profile forbids it"
                )

        lwo = getattr(ctrl, "low_wind_option", None)
        if lwo and lwo not in self.allowed_low_wind:
            warnings.append(
                f"{self.name}: low_wind_option='{lwo}' is set, and the "
                "profile accepts "
                + (f"only {self.allowed_low_wind}" if self.allowed_low_wind
                   else "none: CO LOW_WIND is an ALPHA option, which AERMOD "
                        "refuses with DFAULT")
            )

        # Chemistry method
        method_name = self._chemistry_method(project)
        if method_name is not None and method_name not in self.allow_chemistry_methods:
            warnings.append(
                f"{self.name}: chemistry method '{method_name}' is not in "
                f"allowed set {self.allow_chemistry_methods}"
            )

        return warnings

    def _chemistry_method(self, project: Any) -> str | None:
        chem = getattr(project.control, "chemistry", None)
        if chem is None:
            return None
        return str(getattr(chem.method, "value", chem.method))

    def advisories(self, project: Any) -> List[str]:
        """Notes on what the project's options ask of the applicant.

        These are not conflicts and are not in :meth:`check`. A Tier 3
        NO2 method (``tier3_chemistry_methods``) that the profile accepts
        gives one note: Appendix W 4.2.3.4(e) says its use "shall occur in
        consultation with the EPA Regional Office in addition to the
        appropriate reviewing authority".
        """
        method = self._chemistry_method(project)
        if (method in self.tier3_chemistry_methods
                and method in self.allow_chemistry_methods):
            return [
                f"{self.name}: {method} is a Tier 3 NO2 screening technique; "
                "its use needs consultation with the EPA Regional Office and "
                "the appropriate reviewing authority (Appendix W 4.2.3.4(e))"
            ]
        return []


# ---------------------------------------------------------------------------
# Predefined profiles
# ---------------------------------------------------------------------------

_TIER_NOTE = (
    "NO2 (Appendix W 4.2.3.4): no chemistry is Tier 1, ARM2 is Tier 2 "
    "(national default ratios 0.5 to 0.9) and {tier3} are Tier 3. All three "
    "tiers are screening techniques used in agreement with the reviewing "
    "authority; Tier 3 also needs consultation with the EPA Regional Office."
)

_ADJ_U_NOTE = (
    "ADJ_U* is an AERMET option, regulatory since the 2017 rule except with "
    "site-specific turbulence data (Addendum A, A.1(b)(2)(ii)). A profile "
    "cannot see it: AERMOD reads it from the surface file."
)

EPA_APPENDIX_W_2017 = RegulatoryProfile(
    name="EPA-AppendixW-2017",
    description=(
        "40 CFR 51 Appendix W (Guideline on Air Quality Models), the 2017 "
        "revision: 82 FR 5182, January 17, 2017, effective May 22, 2017. "
        "DFAULT and elevated terrain, no ALPHA or BETA option, no low-wind "
        "option. NO2: ARM2 (Tier 2), OLM and PVMRM (Tier 3)."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allow_chemistry_methods=("ARM2", "OLM", "PVMRM"),
    notes=[
        _TIER_NOTE.format(tier3="OLM and PVMRM"),
        "GRSM is not in this revision: AERMOD first carried it in v21112, "
        "as an ALPHA option.",
        "The 2017 rule did not adopt LOWWIND3 (a BETA option, removed from "
        "AERMOD in v18081).",
        _ADJ_U_NOTE,
    ],
)


EPA_APPENDIX_W_2023 = RegulatoryProfile(
    name="EPA-AppendixW-2023",
    description=(
        "The 2017 revision of Appendix W as applied with AERMOD v23132. "
        "Appendix W had no 2023 revision: the rule in force in 2023 was the "
        "2017 one, and the revision proposed that year (88 FR 72826) became "
        "the 2024 rule. Same content as EPA-AppendixW-2017. GRSM was a BETA "
        "option in v22112 and v23132, which AERMOD refuses with DFAULT "
        "(E199, E204), so it is not accepted here. For the rule now in "
        "force use EPA-AppendixW-2024."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allow_chemistry_methods=("ARM2", "OLM", "PVMRM"),
    notes=[
        _TIER_NOTE.format(tier3="OLM and PVMRM"),
        "GRSM: ALPHA in v21112, BETA in v22112 and v23132, regulatory from "
        "v24142 under the 2024 rule.",
        _ADJ_U_NOTE,
    ],
)

#: NO2 methods that were BETA options in AERMOD v23132, the model version
#: :data:`EPA_APPENDIX_W_2023` describes. They are regulatory from v24142.
EPA_APPENDIX_W_2023_BETA_METHODS: tuple = ("GRSM",)


EPA_APPENDIX_W_2024 = RegulatoryProfile(
    name="EPA-AppendixW-2024",
    description=(
        "40 CFR 51 Appendix W, the 2024 revision: 89 FR 95034, November 29, "
        "2024, effective March 21, 2025 (90 FR 8254), with AERMOD v24142 or "
        "later. The 2017 content plus GRSM as a Tier 3 NO2 technique. DFAULT "
        "and elevated terrain, no ALPHA or BETA option, no low-wind option."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allow_chemistry_methods=("ARM2", "OLM", "PVMRM", "GRSM"),
    notes=[
        _TIER_NOTE.format(tier3="OLM, PVMRM and GRSM"),
        "GRSM, the RLINE source type and COARE in AERMET are regulatory "
        "from v24142. RLINEXT, LOW_WIND, TTRM and TTRM2 remain ALPHA options.",
        _ADJ_U_NOTE,
    ],
)


SCREENING_PROFILE = RegulatoryProfile(
    name="Screening",
    description=(
        "Conservative screening configuration: DFAULT + ELEV terrain, "
        "no non-default options, basic chemistry. Suitable for scoping "
        "runs; tighten to a named profile before final submittal."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allow_chemistry_methods=("ARM2", "OLM", "PVMRM", "GRSM"),
)


ALL_PROFILES = {
    EPA_APPENDIX_W_2017.name: EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023.name: EPA_APPENDIX_W_2023,
    EPA_APPENDIX_W_2024.name: EPA_APPENDIX_W_2024,
    SCREENING_PROFILE.name: SCREENING_PROFILE,
}


def get_profile(name: str) -> RegulatoryProfile:
    """Look up a profile by name. Raises KeyError if not known."""
    if name not in ALL_PROFILES:
        raise KeyError(
            f"unknown regulatory profile '{name}'; "
            f"known profiles: {list(ALL_PROFILES)}"
        )
    return ALL_PROFILES[name]


__all__ = [
    "ALL_PROFILES",
    "EPA_APPENDIX_W_2017",
    "EPA_APPENDIX_W_2023",
    "EPA_APPENDIX_W_2023_BETA_METHODS",
    "EPA_APPENDIX_W_2024",
    "SCREENING_PROFILE",
    "RegulatoryProfile",
    "get_profile",
]
