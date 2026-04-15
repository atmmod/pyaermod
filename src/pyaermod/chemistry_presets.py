"""
Chemistry / deposition presets and utilities.

Built on top of `input_generator.ChemistryOptions` / `ChemistryMethod`
and the deposition dataclasses. Provides:

- Ready-made `ChemistryOptions` bundles for the common NO2 modeling
  setups (OLM / PVMRM / PVMRM2 / GRSM) with sensible defaults.
- Deposition velocity tables / presets for SO2, NOx, PM2.5, PM10, Hg.
- `suggest_chemistry_for` — heuristic for picking a chemistry method
  given a project's pollutant and source count.
- `deposition_diagnostics` — flags mismatched dry/wet / gas/particle
  configurations on a project's sources.

These are intentionally small, explicit dataclasses rather than a
plugin system — regulatory protocols change and every project lists
the exact chemistry configuration in its modeling plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .input_generator import (
    ChemistryMethod,
    ChemistryOptions,
    DepositionMethod,
    GasDepositionParams,
    OzoneData,
    ParticleDepositionParams,
    PollutantType,
)

# ---------------------------------------------------------------------------
# Chemistry presets
# ---------------------------------------------------------------------------

def olm_preset(
    *,
    ozone_ppb: Optional[float] = None,
    ozone_file: Optional[str] = None,
    in_stack_no2_ratio: float = 0.1,
) -> ChemistryOptions:
    """OLM (Ozone-Limiting Method) configuration.

    Typical use: secondary NO2 modeling when only a single background
    ozone value or hourly ozone record is available.

    Either `ozone_ppb` (uniform) or `ozone_file` must be provided.
    """
    if ozone_ppb is None and not ozone_file:
        raise ValueError("OLM requires either ozone_ppb or ozone_file")
    oz = OzoneData(
        ozone_file=ozone_file,
        uniform_value=ozone_ppb if ozone_file is None else None,
    )
    return ChemistryOptions(
        method=ChemistryMethod.OLM,
        ozone_data=oz,
        default_no2_ratio=in_stack_no2_ratio,
    )


def pvmrm_preset(
    *,
    ozone_ppb: Optional[float] = None,
    ozone_file: Optional[str] = None,
    in_stack_no2_ratio: float = 0.1,
) -> ChemistryOptions:
    """PVMRM (Plume Volume Molar Ratio Method) configuration.

    Preferred over OLM when multiple sources need to compete for a
    shared oxidant pool. Same ozone-data requirements as OLM.
    """
    if ozone_ppb is None and not ozone_file:
        raise ValueError("PVMRM requires either ozone_ppb or ozone_file")
    oz = OzoneData(
        ozone_file=ozone_file,
        uniform_value=ozone_ppb if ozone_file is None else None,
    )
    return ChemistryOptions(
        method=ChemistryMethod.PVMRM,
        ozone_data=oz,
        default_no2_ratio=in_stack_no2_ratio,
    )


def arm2_preset(in_stack_no2_ratio: float = 0.1) -> ChemistryOptions:
    """ARM2 (Ambient Ratio Method 2) configuration.

    Default-case NO2 fallback when no ozone data is available. Uses
    AERMOD's built-in NO2/NOx ratio curve. Not accepted by Appendix W
    for new submittals.
    """
    return ChemistryOptions(
        method=ChemistryMethod.ARM2,
        default_no2_ratio=in_stack_no2_ratio,
    )


def grsm_preset(
    *,
    ozone_file: Optional[str] = None,
    ozone_ppb: Optional[float] = None,
    nox_background_file: Optional[str] = None,
    in_stack_no2_ratio: float = 0.1,
) -> ChemistryOptions:
    """GRSM (Generic Reaction Set Method) configuration.

    Appropriate for multi-source NOx modeling with background ozone +
    optionally a NOx background file. Preferred over OLM/PVMRM in
    Appendix W 2023 where documented.
    """
    if ozone_ppb is None and not ozone_file:
        raise ValueError("GRSM requires either ozone_ppb or ozone_file")
    oz = OzoneData(
        ozone_file=ozone_file,
        uniform_value=ozone_ppb if ozone_file is None else None,
    )
    return ChemistryOptions(
        method=ChemistryMethod.GRSM,
        ozone_data=oz,
        default_no2_ratio=in_stack_no2_ratio,
        nox_file=nox_background_file,
    )


def suggest_chemistry_for(
    pollutant: PollutantType,
    n_sources: int,
    has_ozone_data: bool,
    has_nox_background: bool = False,
) -> str:
    """Return the short name of the recommended chemistry method.

    Decision logic:
    - Only NO2 needs secondary-formation chemistry. Other pollutants
      return "NONE".
    - With ozone AND >= 5 sources -> PVMRM.
    - With ozone AND NOx background -> GRSM.
    - With ozone AND few sources -> OLM.
    - Without ozone data -> ARM2 (fallback; not Appendix-W-compliant).
    """
    if pollutant is not PollutantType.NO2:
        return "NONE"
    if not has_ozone_data:
        return "ARM2"
    if has_nox_background:
        return "GRSM"
    if n_sources >= 5:
        return "PVMRM"
    return "OLM"


# ---------------------------------------------------------------------------
# Deposition velocity / scavenging presets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PollutantDepositionDefaults:
    """Per-pollutant deposition-parameter defaults (typical literature)."""
    pollutant: str
    gas: Optional[GasDepositionParams] = None
    particle: Optional[ParticleDepositionParams] = None
    method: DepositionMethod = DepositionMethod.GASDEPVD
    notes: str = ""


def _gas(diffusivity: float, alpha_r: float, reactivity: float,
         henry: Optional[float] = None, vd: Optional[float] = None) -> GasDepositionParams:
    """Build GasDepositionParams with AERMOD GASDEPOS keyword fields.

    Maps to the AERMOD parameters:
      diffusivity (cm^2/s), alpha_r (dimensionless), reactivity (dimensionless),
      henry_constant (M/atm) or dry_dep_velocity (cm/s).
    """
    return GasDepositionParams(
        diffusivity=diffusivity,
        alpha_r=alpha_r,
        reactivity=reactivity,
        henry_constant=henry,
        dry_dep_velocity=vd,
    )


def _particle(diameters_um: List[float], mass_fractions: List[float],
              densities: List[float]) -> ParticleDepositionParams:
    """Build ParticleDepositionParams with PARTDIAM/MASSFRAX/PARTDENS fields."""
    return ParticleDepositionParams(
        diameters=list(diameters_um),
        mass_fractions=list(mass_fractions),
        densities=list(densities),
    )


# Very approximate literature-based defaults — a real modeling protocol
# should cite measured / recommended values for the pollutant and
# surface type. These are intended as "sensible starting point."
DEPOSITION_DEFAULTS: Dict[str, PollutantDepositionDefaults] = {
    "SO2":  PollutantDepositionDefaults(
        pollutant="SO2",
        gas=_gas(diffusivity=0.126, alpha_r=10.0, reactivity=8.0, henry=1.2e-3, vd=0.5),
        method=DepositionMethod.GASDEPVD,
        notes="Vd ~ 0.5 cm/s typical for grassland / cropland",
    ),
    "NOX":  PollutantDepositionDefaults(
        pollutant="NOX",
        gas=_gas(diffusivity=0.136, alpha_r=1.0, reactivity=1.0, henry=1.9e-3, vd=0.3),
    ),
    "NO2":  PollutantDepositionDefaults(
        pollutant="NO2",
        gas=_gas(diffusivity=0.136, alpha_r=1.0, reactivity=1.0, henry=1.0e-2, vd=0.2),
    ),
    "HG":   PollutantDepositionDefaults(
        pollutant="HG",
        gas=_gas(diffusivity=0.068, alpha_r=0.0, reactivity=0.0, henry=0.3, vd=0.03),
        method=DepositionMethod.GASDEPVD,
        notes="Elemental Hg; divalent Hg(II) deposits ~30x faster",
    ),
    "PM25": PollutantDepositionDefaults(
        pollutant="PM25",
        particle=_particle(diameters_um=[1.0], mass_fractions=[1.0], densities=[1.5]),
    ),
    "PM10": PollutantDepositionDefaults(
        pollutant="PM10",
        particle=_particle(diameters_um=[2.0, 5.0, 10.0],
                           mass_fractions=[0.3, 0.4, 0.3],
                           densities=[1.5, 2.0, 2.5]),
    ),
}


def deposition_defaults_for(pollutant: str) -> PollutantDepositionDefaults:
    """Look up canonical deposition defaults by pollutant name."""
    key = pollutant.upper()
    if key not in DEPOSITION_DEFAULTS:
        raise KeyError(
            f"no deposition defaults for '{pollutant}'; "
            f"available: {list(DEPOSITION_DEFAULTS)}"
        )
    return DEPOSITION_DEFAULTS[key]


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def deposition_diagnostics(project: Any) -> List[str]:
    """Return warning strings about inconsistent deposition setup.

    Flags:
    - Sources with deposition_method set but no gas/particle params.
    - Sources with both gas AND particle params (only one makes sense).
    - CONTROL's `calculate_dry_deposition=True` but zero sources have
      gas or particle params set.
    """
    warns: List[str] = []
    ctrl = getattr(project, "control", None)
    sources = getattr(project.sources, "sources", []) if getattr(project, "sources", None) else []

    any_gas = False
    any_particle = False
    for src in sources:
        dep_method = getattr(src, "deposition_method", None)
        gas = getattr(src, "gas_deposition", None)
        particle = getattr(src, "particle_deposition", None)
        sid = getattr(src, "source_id", "?")
        if dep_method is not None and gas is None and particle is None:
            warns.append(
                f"{sid}: deposition_method={dep_method} but no gas_deposition "
                f"or particle_deposition parameters"
            )
        if gas is not None and particle is not None:
            warns.append(
                f"{sid}: both gas_deposition and particle_deposition set "
                "(use exactly one per source)"
            )
        if gas is not None:
            any_gas = True
        if particle is not None:
            any_particle = True

    if ctrl is not None:
        ddry = getattr(ctrl, "calculate_dry_deposition", False)
        dwet = getattr(ctrl, "calculate_wet_deposition", False)
        if (ddry or dwet) and not (any_gas or any_particle):
            warns.append(
                "CONTROL requests dry/wet deposition but no source has "
                "deposition parameters set"
            )
    return warns


__all__ = [
    "DEPOSITION_DEFAULTS",
    "PollutantDepositionDefaults",
    "arm2_preset",
    "deposition_defaults_for",
    "deposition_diagnostics",
    "grsm_preset",
    "olm_preset",
    "pvmrm_preset",
    "suggest_chemistry_for",
]
