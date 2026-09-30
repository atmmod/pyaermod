"""
Advanced / cross-field AERMOD validation.

The base `Validator` in validator.py catches per-field range violations
(e.g. negative stack height). The checks here look for *combinations*
that commonly cause AERMOD to crash cryptically or produce silently
wrong results:

- Stack-parameter consistency (zero exit velocity with non-ambient temp,
  implausibly small diameter given emission rate, etc.).
- Receptor-grid/domain sanity (extent, density).
- DFAULT vs. non-default model-option consistency.
- Emission-rate plausibility for the declared pollutant.
- Met date range vs. ControlPathway date range.
- ANNUAL averages vs. the period the surface file covers
  (:func:`check_annual_met_coverage`, which reads the file and so is not
  part of ``Validator.validate()``).

As of v1.3.0 these checks are **integrated into `Validator.validate()`**
by default — findings land in the returned `ValidationResult.errors`
list with the appropriate severity. Call the standalone
`advanced_validate(project)` only when you need the cross-field
findings in isolation (e.g. for custom reporting).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Union

from .validator import ValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .aermet import SurfaceFilePeriod

# ---------------------------------------------------------------------------
# Heuristic thresholds
# ---------------------------------------------------------------------------

MIN_PLAUSIBLE_STACK_DIAM_M = 0.01   # 1 cm — anything smaller is data error
MAX_PLAUSIBLE_STACK_DIAM_M = 30.0   # cooling-tower scale cap
MAX_PLAUSIBLE_EXIT_V_MS = 150.0     # ~Mach 0.4; real stacks are <100 m/s
AMBIENT_TEMP_K = 293.15             # nominal near-surface temperature
RECEPTOR_GRID_HARD_LIMIT = 100_000  # AERMOD RECOPT memory limit
RECEPTOR_GRID_WARN_LIMIT = 10_000


# ---------------------------------------------------------------------------
# Stack-parameter consistency
# ---------------------------------------------------------------------------

def _check_point_source(src: Any) -> List[ValidationError]:
    name = f"PointSource({src.source_id})"
    errors: List[ValidationError] = []

    diam = getattr(src, "stack_diameter", None)
    if diam is not None:
        if diam < MIN_PLAUSIBLE_STACK_DIAM_M:
            errors.append(ValidationError(
                name, "stack_diameter",
                f"stack_diameter = {diam} m is below plausible minimum "
                f"{MIN_PLAUSIBLE_STACK_DIAM_M} m; check units (should be meters)",
                severity="warning",
            ))
        elif diam > MAX_PLAUSIBLE_STACK_DIAM_M:
            errors.append(ValidationError(
                name, "stack_diameter",
                f"stack_diameter = {diam} m exceeds plausible maximum "
                f"{MAX_PLAUSIBLE_STACK_DIAM_M} m",
                severity="warning",
            ))

    ve = getattr(src, "exit_velocity", None)
    ts = getattr(src, "stack_temp", None)
    if ve is not None and ts is not None:
        if ve == 0 and ts > AMBIENT_TEMP_K + 50:
            errors.append(ValidationError(
                name, "exit_velocity",
                f"exit_velocity = 0 but stack_temp = {ts} K (>> ambient); "
                "buoyant plume with zero velocity is inconsistent — "
                "AERMOD will model as neutral",
                severity="warning",
            ))
        if ve > MAX_PLAUSIBLE_EXIT_V_MS:
            errors.append(ValidationError(
                name, "exit_velocity",
                f"exit_velocity = {ve} m/s is physically unrealistic "
                f"(max plausible {MAX_PLAUSIBLE_EXIT_V_MS} m/s)",
                severity="warning",
            ))

    er = getattr(src, "emission_rate", None)
    if er is not None and er == 0:
        errors.append(ValidationError(
            name, "emission_rate",
            "emission_rate = 0 — source contributes nothing; "
            "consider omitting this source from the run",
            severity="warning",
        ))

    # Buoyancy flux sanity: if T = ambient and V = 0, plume has no rise;
    # check user didn't miss stack_temp.
    if (ve is None or ve == 0) and (ts is None or abs(ts - AMBIENT_TEMP_K) < 1):
        errors.append(ValidationError(
            name, "stack_temp/exit_velocity",
            "ambient temperature and zero velocity — no plume rise; "
            "verify this is intentional (e.g. fugitive source)",
            severity="warning",
        ))
    return errors


# ---------------------------------------------------------------------------
# Receptor / grid sanity
# ---------------------------------------------------------------------------

def _iter_receptor_coords(receptors: Any):
    """Yield (x, y) for every receptor (grid + discrete)."""
    for grid in getattr(receptors, "cartesian_grids", []) or []:
        for x in _cart_values(grid, "x"):
            for y in _cart_values(grid, "y"):
                yield (x, y)
    for grid in getattr(receptors, "polar_grids", []) or []:
        # Polar grids rotate around (x_origin, y_origin)
        import math
        for theta_deg in _polar_directions(grid):
            theta = math.radians(90.0 - theta_deg)  # met -> math
            for r in _polar_distances(grid):
                yield (grid.x_origin + r * math.cos(theta),
                       grid.y_origin + r * math.sin(theta))
    for r in getattr(receptors, "discrete_receptors", []) or []:
        yield (r.x_coord, r.y_coord)


def _cart_values(grid: Any, axis: str) -> List[float]:
    """Explicit XPNTS/YPNTS list if the grid has one, else the generator."""
    accessor = getattr(grid, f"{axis}_values", None)
    if callable(accessor):
        return list(accessor())
    init, num, delta = (getattr(grid, f"{axis}_{k}") for k in ("init", "num", "delta"))
    return [init + i * delta for i in range(num)]


def _polar_distances(grid: Any) -> List[float]:
    accessor = getattr(grid, "ring_distances", None)
    if callable(accessor):
        return list(accessor())
    return [grid.dist_init + j * grid.dist_delta for j in range(grid.dist_num)]


def _polar_directions(grid: Any) -> List[float]:
    accessor = getattr(grid, "direction_angles", None)
    if callable(accessor):
        return list(accessor())
    return [grid.dir_init + i * grid.dir_delta for i in range(grid.dir_num)]


def _count_receptors(receptors: Any) -> int:
    n = 0
    for grid in getattr(receptors, "cartesian_grids", []) or []:
        n += len(_cart_values(grid, "x")) * len(_cart_values(grid, "y"))
    for grid in getattr(receptors, "polar_grids", []) or []:
        n += len(_polar_distances(grid)) * len(_polar_directions(grid))
    n += len(getattr(receptors, "discrete_receptors", []) or [])
    return n


def _receptor_bbox(receptors: Any) -> Optional[Tuple[float, float, float, float]]:
    """Return the (xmin, ymin, xmax, ymax) bounding box of every receptor.

    Computed analytically from grid definitions — O(grids + discretes),
    *not* O(x_num × y_num). A 500×500 Cartesian grid (250k receptors)
    contributes exactly 4 corner evaluations.
    """

    xs: List[float] = []
    ys: List[float] = []

    for grid in getattr(receptors, "cartesian_grids", []) or []:
        # Corners only — grid is axis-aligned so bbox = corners
        gx = _cart_values(grid, "x")
        gy = _cart_values(grid, "y")
        if gx and gy:
            xs.extend([min(gx), max(gx)])
            ys.extend([min(gy), max(gy)])

    for grid in getattr(receptors, "polar_grids", []) or []:
        # Max distance from origin; the bbox is origin ± max_radius in
        # each axis (conservative upper bound).
        max_r = max(_polar_distances(grid), default=0.0)
        xs.extend([grid.x_origin - max_r, grid.x_origin + max_r])
        ys.extend([grid.y_origin - max_r, grid.y_origin + max_r])

    for r in getattr(receptors, "discrete_receptors", []) or []:
        xs.append(r.x_coord)
        ys.append(r.y_coord)

    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _check_receptors(receptors: Any, sources: Any) -> List[ValidationError]:
    errors: List[ValidationError] = []
    n = _count_receptors(receptors)

    # Fast-path: if we're over the hard limit, record it and return
    # before any further work (bbox, source comparison). Previously
    # the bbox helper materialized all x_num*y_num coords into memory
    # first, which was O(100k+) for the exact projects this check
    # exists to flag.
    if n > RECEPTOR_GRID_HARD_LIMIT:
        errors.append(ValidationError(
            "ReceptorPathway", "total_receptors",
            f"total receptors {n} exceeds AERMOD hard limit "
            f"{RECEPTOR_GRID_HARD_LIMIT}; recompile AERMOD or reduce grid",
            severity="error",
        ))
        return errors
    elif n > RECEPTOR_GRID_WARN_LIMIT:
        errors.append(ValidationError(
            "ReceptorPathway", "total_receptors",
            f"total receptors {n} > {RECEPTOR_GRID_WARN_LIMIT}; runtime "
            "will be large",
            severity="warning",
        ))

    bbox = _receptor_bbox(receptors)
    if bbox is not None and getattr(sources, "sources", None):
        src_xs = [s.x_coord for s in sources.sources if hasattr(s, "x_coord")]
        src_ys = [s.y_coord for s in sources.sources if hasattr(s, "y_coord")]
        if src_xs and src_ys:
            sbbox = (min(src_xs), min(src_ys), max(src_xs), max(src_ys))
            # Warn if source is outside receptor bbox by > 10 km
            if (sbbox[0] < bbox[0] - 10_000 or sbbox[2] > bbox[2] + 10_000 or
                    sbbox[1] < bbox[1] - 10_000 or sbbox[3] > bbox[3] + 10_000):
                errors.append(ValidationError(
                    "ReceptorPathway", "grid_extent",
                    f"sources outside receptor grid by >10 km "
                    f"(src bbox {sbbox} vs receptor bbox {bbox})",
                    severity="warning",
                ))
    return errors


# ---------------------------------------------------------------------------
# DFAULT / NONDFAULT consistency
# ---------------------------------------------------------------------------

# Options that change AERMOD from regulatory-default behavior. If any of
# these are set *and* regulatory_default is True, the model will warn
# (AERMOD itself will in fact abort); we flag it earlier.
NONDEFAULT_OPTION_FLAGS = (
    "use_nondefault",    # explicit override toggle
    "flat_terrain",      # FLAT option is non-default
    "no_stack_tip_downwash",  # NOSTD option
    "use_lowwind1",
    "use_lowwind2",
    "use_lowwind3",
    "use_area_rural",    # ARM mode (regulatory is urban/rural per-source)
    "beta_options",      # BETA experimental options
)


def _check_dfault_consistency(control: Any) -> List[ValidationError]:
    errors: List[ValidationError] = []
    reg = getattr(control, "regulatory_default", True)
    if not reg:
        return errors  # User explicitly chose NONDFAULT — nothing to check

    triggered = []
    for opt in NONDEFAULT_OPTION_FLAGS:
        val = getattr(control, opt, None)
        if val:  # truthy (True, non-empty string, non-empty list)
            triggered.append(opt)
    if triggered:
        errors.append(ValidationError(
            "ControlPathway", "regulatory_default",
            f"regulatory_default=True but non-default options set: "
            f"{triggered}; set regulatory_default=False or remove these",
            severity="error",
        ))
    return errors


# ---------------------------------------------------------------------------
# Met date vs. control averaging sanity
# ---------------------------------------------------------------------------

def _check_met_dates(control: Any, met: Any) -> List[ValidationError]:
    errors: List[ValidationError] = []
    # If the user set explicit met.start/end, require they cover the full
    # year when ANNUAL averaging is requested.
    periods = [str(p).upper() for p in getattr(control, "averaging_periods", [])]
    if "ANNUAL" not in periods:
        return errors

    sy = getattr(met, "start_year", None)
    sm = getattr(met, "start_month", None)
    sd = getattr(met, "start_day", None)
    ey = getattr(met, "end_year", None)
    em = getattr(met, "end_month", None)
    ed = getattr(met, "end_day", None)
    if None in (sy, sm, sd, ey, em, ed):
        return errors  # base validator handles partial-dates error

    if (sy, sm, sd) == (ey, em, ed):
        errors.append(ValidationError(
            "MeteorologyPathway", "date_range",
            f"ANNUAL averaging requested but met range is a single day "
            f"({sy}-{sm:02d}-{sd:02d}); AERMOD will skip ANNUAL output",
            severity="error",
        ))
        return errors

    if (sm, sd) != (1, 1) or (em, ed) != (12, 31):
        errors.append(ValidationError(
            "MeteorologyPathway", "date_range",
            f"ANNUAL averaging requested but met range {sy}-{sm:02d}-{sd:02d} "
            f"to {ey}-{em:02d}-{ed:02d} is not a full calendar year",
            severity="warning",
        ))
    return errors


def surface_file_path(met: Any, base_dir: Union[str, Path, None] = None) -> Optional[Path]:
    """The surface file ``met`` names, resolved as AERMOD would open it.

    AERMOD opens a relative path from its working directory, so a
    relative ``surface_file`` is joined to ``base_dir`` when one is given.
    None when no surface file is set.
    """
    name = (getattr(met, "surface_file", "") or "").strip().strip('"')
    if not name:
        return None
    path = Path(name).expanduser()
    if not path.is_absolute() and base_dir is not None and str(base_dir).strip():
        path = Path(base_dir).expanduser() / path
    return path


def _startend_window(met: Any) -> Optional[Tuple[datetime, datetime]]:
    """STARTEND as (start of its first hour, end of its last day), or None."""
    fields = [getattr(met, f, None) for f in (
        "start_year", "start_month", "start_day", "end_year", "end_month", "end_day")]
    if any(f is None for f in fields):
        return None
    try:
        sy, sm, sd, ey, em, ed = (int(f) for f in fields if f is not None)
        return datetime(sy, sm, sd), datetime(ey, em, ed) + timedelta(days=1)
    except (TypeError, ValueError, OverflowError):
        return None                     # the base validator reports bad dates


def check_annual_met_coverage(project: Any, *, base_dir: Union[str, Path, None] = None,
                              period: Optional[SurfaceFilePeriod] = None,
                              ) -> List[ValidationError]:
    """Warn when ANNUAL is requested with less than a year of met data.

    AERMOD processes every hour and then stops with fatal error E480
    ("Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave") when the data
    hold no complete year (:attr:`~pyaermod.aermet.SurfaceFilePeriod.complete_years`,
    checked against AERMOD v26135). A STARTEND window limits the data to
    the hours inside it.

    Unlike :func:`advanced_validate` this reads the surface file, so
    ``Validator.validate()`` does not call it.

    Parameters
    ----------
    project : AERMODProject
    base_dir : str or Path, optional
        The directory AERMOD will run in, against which a relative
        ``surface_file`` is resolved.
    period : SurfaceFilePeriod, optional
        The file's period, if already read (the GUI caches it); read with
        :func:`~pyaermod.aermet.read_surface_period` otherwise.

    Returns
    -------
    list of ValidationError
        One warning when the data hold no complete year; empty when
        ANNUAL is not requested or the surface file is unset or cannot be
        read (other checks report those).
    """
    periods = [str(p).strip().upper() for p in getattr(project.control, "averaging_periods", [])]
    if "ANNUAL" not in periods:
        return []
    met = project.meteorology
    path = surface_file_path(met, base_dir)
    if period is None:
        if path is None:
            return []
        from .aermet import read_surface_period

        try:
            period = read_surface_period(path)
        except (OSError, ValueError):
            return []
    name = path.name if path is not None else "the surface file"
    covered = period
    window = _startend_window(met)
    if window is not None:
        from dataclasses import replace

        first, last = max(period.first, window[0]), min(period.last, window[1])
        if last <= first:
            return []                   # AERMOD reports a STARTEND outside the data itself
        covered = replace(period, first=first, last=last)
    if covered.complete_years > 0:
        return []
    within = " within STARTEND" if covered is not period else ""
    return [ValidationError(
        "MeteorologyPathway", "surface_file",
        f"ANNUAL averages need at least one full year of met data, but {name} "
        f"holds {period.describe()}{within}; AERMOD would stop with fatal error "
        "E480. Use a year or more of met data, or averaging periods without ANNUAL",
        severity="warning",
    )]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def advanced_validate(project: Any) -> List[ValidationError]:
    """Run all advanced / cross-field checks and return findings.

    Findings include both 'warning' and 'error' severities; merge into
    a base `ValidationResult` via `result.errors.extend(...)`.
    """
    findings: List[ValidationError] = []

    findings.extend(_check_dfault_consistency(project.control))

    for src in getattr(project.sources, "sources", []) or []:
        cls_name = type(src).__name__
        if cls_name == "PointSource":
            findings.extend(_check_point_source(src))

    findings.extend(_check_receptors(project.receptors, project.sources))
    findings.extend(_check_met_dates(project.control, project.meteorology))

    return findings


__all__ = [
    "MAX_PLAUSIBLE_EXIT_V_MS",
    "MAX_PLAUSIBLE_STACK_DIAM_M",
    "MIN_PLAUSIBLE_STACK_DIAM_M",
    "NONDEFAULT_OPTION_FLAGS",
    "RECEPTOR_GRID_HARD_LIMIT",
    "RECEPTOR_GRID_WARN_LIMIT",
    "advanced_validate",
    "check_annual_met_coverage",
    "surface_file_path",
]
