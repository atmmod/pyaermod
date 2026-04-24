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

As of v1.3.0 these checks are **integrated into `Validator.validate()`**
by default — findings land in the returned `ValidationResult.errors`
list with the appropriate severity. Call the standalone
`advanced_validate(project)` only when you need the cross-field
findings in isolation (e.g. for custom reporting).
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from .validator import ValidationError

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
        for i in range(grid.x_num):
            x = grid.x_init + i * grid.x_delta
            for j in range(grid.y_num):
                y = grid.y_init + j * grid.y_delta
                yield (x, y)
    for grid in getattr(receptors, "polar_grids", []) or []:
        # Polar grids rotate around (x_origin, y_origin)
        import math
        for i in range(grid.dir_num):
            theta_deg = grid.dir_init + i * grid.dir_delta
            theta = math.radians(90.0 - theta_deg)  # met -> math
            for j in range(grid.dist_num):
                r = grid.dist_init + j * grid.dist_delta
                yield (grid.x_origin + r * math.cos(theta),
                       grid.y_origin + r * math.sin(theta))
    for r in getattr(receptors, "discrete_receptors", []) or []:
        yield (r.x_coord, r.y_coord)


def _count_receptors(receptors: Any) -> int:
    n = 0
    for grid in getattr(receptors, "cartesian_grids", []) or []:
        n += grid.x_num * grid.y_num
    for grid in getattr(receptors, "polar_grids", []) or []:
        n += grid.dist_num * grid.dir_num
    n += len(getattr(receptors, "discrete_receptors", []) or [])
    return n


def _receptor_bbox(receptors: Any) -> Optional[Tuple[float, float, float, float]]:
    """Return the (xmin, ymin, xmax, ymax) bounding box of every receptor.

    Computed analytically from grid definitions — O(grids + discretes),
    *not* O(x_num × y_num). A 500×500 Cartesian grid (250k receptors)
    contributes exactly 4 corner evaluations.
    """
    import math

    xs: List[float] = []
    ys: List[float] = []

    for grid in getattr(receptors, "cartesian_grids", []) or []:
        # Corners only — grid is axis-aligned so bbox = corners
        x_end = grid.x_init + (grid.x_num - 1) * grid.x_delta
        y_end = grid.y_init + (grid.y_num - 1) * grid.y_delta
        xs.extend([grid.x_init, x_end])
        ys.extend([grid.y_init, y_end])

    for grid in getattr(receptors, "polar_grids", []) or []:
        # Max distance from origin; the bbox is origin ± max_radius in
        # each axis (conservative upper bound).
        max_r = grid.dist_init + (grid.dist_num - 1) * grid.dist_delta
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
]
