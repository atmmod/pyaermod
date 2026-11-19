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
    allowed_low_wind: tuple = ("LOWWIND3",)
    allow_chemistry_methods: tuple = ("OLM", "PVMRM", "GRSM")
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
