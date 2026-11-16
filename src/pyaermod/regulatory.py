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

from .pathways import DFAULT_MODELOPT_CONFLICTS

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
        Which ``low_wind_option`` values are acceptable when the profile
        does not require DFAULT. Under DFAULT any CO LOW_WIND card is
        refused, since it needs the ALPHA option (AERMOD E133).
    allow_chemistry_methods : tuple of str
        Names of ChemistryMethod enum values that are acceptable for
        regulatory NO2 modeling (typically OLM, PVMRM, GRSM).
    forbid_model_options : tuple of str
        MODELOPT tokens the project must not write, as
        :meth:`ControlPathway.dfault_conflicts` reports them. Defaults to
        every token DFAULT refuses or drops (``DFAULT_MODELOPT_CONFLICTS``).
    notes : list of str
        Free-form explanatory text.
    """
    name: str
    description: str
    regulatory_default: bool = True
    terrain_type: str = "ELEVATED"
    allowed_low_wind: tuple = ("LOWWIND3",)
    allow_chemistry_methods: tuple = ("OLM", "PVMRM", "GRSM")
    forbid_model_options: tuple = tuple(DFAULT_MODELOPT_CONFLICTS)
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

        # Non-default MODELOPT options. Chemistry methods are left to
        # check(): swapping one NO2 method for another is not a fix
        # pyaermod should make silently.
        forbidden = {opt.upper() for opt in self.forbid_model_options}
        for attr, token in (("alpha", "ALPHA"), ("beta", "BETA"),
                            ("psd_credit", "PSDCREDIT")):
            if token in forbidden and getattr(ctrl, attr):
                setattr(ctrl, attr, False)
                changes.append(f"{attr} -> False (removes {token})")
        kept = [opt for opt in ctrl.extra_model_options
                if str(opt).upper() not in forbidden]
        for opt in ctrl.extra_model_options:
            if str(opt).upper() in forbidden:
                changes.append(f"removed {str(opt).upper()} from extra_model_options")
        ctrl.extra_model_options = kept

        if self.regulatory_default and ctrl.low_wind_option:
            changes.append(f"low_wind_option {ctrl.low_wind_option} -> None")
            ctrl.low_wind_option = None

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
        terrain_ok = _terrain_matches(current_terrain, self.terrain_type)
        if not terrain_ok:
            warnings.append(
                f"{self.name}: terrain_type='{current_terrain}' but profile "
                f"expects '{self.terrain_type}'"
            )

        forbidden = {opt.upper() for opt in self.forbid_model_options}
        extra = {str(opt).upper() for opt in ctrl.extra_model_options}
        for opt, code in ctrl.dfault_conflicts():
            if opt not in forbidden:
                continue
            if opt == "FLAT" and not terrain_ok and "FLAT" not in extra:
                continue  # the terrain_type warning above covers it
            warnings.append(
                f"{self.name}: MODELOPT {opt} is a non-default option "
                f"(AERMOD {code} under DFAULT); the profile forbids it"
            )

        lwo = getattr(ctrl, "low_wind_option", None)
        if lwo and self.regulatory_default:
            warnings.append(
                f"{self.name}: low_wind_option='{lwo}' writes a CO LOW_WIND "
                "card, which needs the ALPHA option (AERMOD E133); DFAULT "
                "refuses ALPHA"
            )
        elif lwo and lwo not in self.allowed_low_wind:
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
        "January 17, 2017 revision. Requires DFAULT + ELEVATED terrain, "
        "permits LOWWIND3 and ADJ_U* only for documented cases. The "
        "only DFAULT-compatible NO2 chemistry methods are OLM and "
        "PVMRM; GRSM was still BETA in 2017."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allowed_low_wind=("LOWWIND3",),
    allow_chemistry_methods=("OLM", "PVMRM"),
    notes=[
        "See 82 FR 5182 (2017). Use of BETA options (GRSM, PVMRM2, "
        "ADJ_U*) requires agency concurrence and is not permitted "
        "under DFAULT.",
    ],
)


EPA_APPENDIX_W_2023 = RegulatoryProfile(
    name="EPA-AppendixW-2023",
    description=(
        "EPA Appendix W as-of 2023: DFAULT + ELEVATED terrain, OLM and "
        "PVMRM still the only formally regulatory-default NO2 chemistry "
        "methods. PVMRM2 and GRSM remain BETA options and require "
        "case-by-case EPA concurrence before use in a regulatory "
        "submittal."
    ),
    regulatory_default=True,
    terrain_type="ELEV",
    allowed_low_wind=("LOWWIND3",),
    # Regulatory-default NO2 chemistry: OLM and PVMRM only. PVMRM2 and
    # GRSM are listed separately in `beta_chemistry_methods` below —
    # users who have agency concurrence can opt in explicitly.
    allow_chemistry_methods=("OLM", "PVMRM"),
    notes=[
        "Profile reflects EPA memoranda through late 2023. PVMRM2 / "
        "GRSM are BETA in AERMOD v23132/v24142 per the 2022/2023 "
        "transmittal memos (v26135 drops the BETA flag for GRSM but it "
        "remains a non-DFAULT option) — neither is DFAULT-compatible. Always "
        "confirm against current Appendix W + the relevant EPA "
        "memorandum before submittal.",
    ],
)

# NO2 chemistry methods that are BETA under EPA Appendix W 2023.
# Use requires explicit agency concurrence; keep these separate from
# the profile's `allow_chemistry_methods` tuple so a project using
# them triggers a lint warning unless the user overrides.
EPA_APPENDIX_W_2023_BETA_METHODS: tuple = ("PVMRM2", "GRSM")


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
