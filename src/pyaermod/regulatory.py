"""
PyAERMOD regulatory-profile presets.

Codifies the "AERMOD as-used by regulators" configurations so users
don't have to remember the set of ControlPathway flags that make a
run compliant with a given agency's guidance.

Each `RegulatoryProfile` is a bundle of settings + a validator list.
Applying a profile to a project:

    from pyaermod import EPAReg2024Profile
    EPAReg2024Profile.apply(project)

leaves the project in a compliant state or raises if the pre-existing
configuration conflicts with the profile.

Profiles here are informed by:
- 40 CFR 51 Appendix W ("Guideline on Air Quality Models"), 2017 update
  and subsequent EPA memoranda on LOWWIND3 and ADJ_U*.
- AERMOD v22112 / v23132 User Guide MODELOPT defaults.

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


@dataclass
class RegulatoryProfile:
    """A named bundle of AERMOD regulatory settings.

    Attributes
    ----------
    name : str
        Short identifier (e.g. "EPA-2017-AppendixW", "CARB-2024").
    description : str
        One-paragraph summary.
    regulatory_default : bool
        Whether to require DFAULT in MODELOPT.
    terrain_type : str
        Required TerrainType value ("ELEVATED" / "FLAT"). Profiles usually
        mandate "ELEVATED" since it subsumes flat cases (AERMOD also
        accepts the short form "ELEV").
    allowed_low_wind : tuple of str
        Which LOWWIND options are acceptable.  Appendix W (2017) allows
        LOWWIND3 for specific documented cases.
    allow_chemistry_methods : tuple of str
        Names of ChemistryMethod enum values that are acceptable for
        regulatory NO2 modeling (typically OLM, PVMRM, GRSM).
    forbid_nondefault_flags : tuple of str
        Attribute names on ControlPathway that must NOT be truthy.
    notes : list of str
        Free-form explanatory text.
    """
    name: str
    description: str
    regulatory_default: bool = True
    terrain_type: str = "ELEVATED"
    allowed_low_wind: tuple = ("LOWWIND3",)
    allow_chemistry_methods: tuple = ("OLM", "PVMRM", "GRSM")
    forbid_nondefault_flags: tuple = (
        "flat_terrain",  # FLAT is a non-default in DFAULT mode
        "no_stack_tip_downwash",
        "use_lowwind1",
        "use_lowwind2",
        "beta_options",
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
        for attr in self.forbid_nondefault_flags:
            if getattr(ctrl, attr, None):
                setattr(ctrl, attr, False)
                changes.append(f"disabled non-default {attr}")

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

        for attr in self.forbid_nondefault_flags:
            if getattr(ctrl, attr, None):
                warnings.append(
                    f"{self.name}: non-default option '{attr}' is set — "
                    "regulatory profile forbids it"
                )

        lwo = getattr(ctrl, "low_wind_option", None)
        if lwo and lwo not in self.allowed_low_wind:
            warnings.append(
                f"{self.name}: low_wind_option='{lwo}' is not in allowed "
                f"set {self.allowed_low_wind}"
            )

        # Chemistry method
        chem = getattr(ctrl, "chemistry", None)
        if chem is not None:
            method_name = (
                chem.method.value if hasattr(chem.method, "value") else chem.method
            )
            if method_name not in self.allow_chemistry_methods:
                warnings.append(
                    f"{self.name}: chemistry method '{method_name}' is not in "
                    f"allowed set {self.allow_chemistry_methods}"
                )

        return warnings


# ---------------------------------------------------------------------------
# Predefined profiles
# ---------------------------------------------------------------------------

EPA_APPENDIX_W_2017 = RegulatoryProfile(
    name="EPA-AppendixW-2017",
    description=(
        "EPA 40 CFR 51 Appendix W (Guideline on Air Quality Models), "
        "January 17, 2017 revision. Requires DFAULT + ELEV terrain, "
        "permits LOWWIND3 and ADJ_U* only for documented cases."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allowed_low_wind=("LOWWIND3",),
    allow_chemistry_methods=("OLM", "PVMRM", "GRSM"),
    notes=[
        "See 82 FR 5182 (2017). Use of BETA options requires agency "
        "concurrence and is not permitted under DFAULT.",
    ],
)


EPA_APPENDIX_W_2023 = RegulatoryProfile(
    name="EPA-AppendixW-2023",
    description=(
        "EPA Appendix W with 2023 ALPHA/BETA formal acceptance of "
        "GRSM for NO2, PVMRM2 for certain cases. Same base constraints "
        "as the 2017 revision."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allowed_low_wind=("LOWWIND3",),
    allow_chemistry_methods=("OLM", "PVMRM", "PVMRM2", "GRSM"),
    notes=[
        "Profile reflects EPA memoranda through 2023. Always confirm "
        "against current Appendix W before submittal.",
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
    allowed_low_wind=(),  # no low-wind tweaks for screening
    allow_chemistry_methods=("OLM", "PVMRM", "GRSM"),
)


ALL_PROFILES = {
    EPA_APPENDIX_W_2017.name: EPA_APPENDIX_W_2017,
    EPA_APPENDIX_W_2023.name: EPA_APPENDIX_W_2023,
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
    "SCREENING_PROFILE",
    "RegulatoryProfile",
    "get_profile",
]
