"""
JSON save/load for the project a GUI v2 :class:`~pyaermod.gui_v2.session.Session` edits.

UI-framework-agnostic: the legacy Streamlit ``ProjectSerializer`` is
tightly coupled to ``st.session_state`` and lives in :mod:`pyaermod.gui`.
This module is the headless equivalent — both GUIs can converge on it
once Streamlit is deprecated in v2.0.

Format
------

Top-level JSON dict::

    {
      "pyaermod_version": "1.9.0",
      "save_format_version": 1,
      "project": <AERMODProject as dataclass-asdict tree, with _type tags>
    }

Source / receptor lists carry per-element ``_type`` discriminators so
the loader can dispatch to the right dataclass on read-back. Enums are
encoded as ``{"_enum": "EnumClass.MEMBER"}``.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import Any, Type, Union

from ..input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PointCapSource,
    PointHorSource,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    SourcePathway,
    VolumeSource,
)

SAVE_FORMAT_VERSION = 1


_SOURCE_TYPES: dict[str, Type] = {
    "PointSource": PointSource,
    "AreaSource": AreaSource,
    "AreaCircSource": AreaCircSource,
    "AreaPolySource": AreaPolySource,
    "VolumeSource": VolumeSource,
    "LineSource": LineSource,
    "RLineSource": RLineSource,
    "RLineExtSource": RLineExtSource,
    "BuoyLineSource": BuoyLineSource,
    "OpenPitSource": OpenPitSource,
    "PointCapSource": PointCapSource,
    "PointHorSource": PointHorSource,
    "SidewashPointSource": SidewashPointSource,
}

_RECEPTOR_TYPES: dict[str, Type] = {
    "CartesianGrid": CartesianGrid,
    "PolarGrid": PolarGrid,
    "DiscreteReceptor": DiscreteReceptor,
}


# ---------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------

class _Encoder(json.JSONEncoder):
    """JSON encoder for dataclasses, Enums, and numpy scalars."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return {"_enum": f"{type(obj).__name__}.{obj.name}"}
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            d = dataclasses.asdict(obj)
            d["_type"] = type(obj).__name__
            return d
        try:  # numpy scalars when the user mixed numpy values into the project
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _project_to_jsonable(project: AERMODProject) -> dict:
    """Convert an AERMODProject to a JSON-serializable dict tree.

    Adds ``_type`` discriminators for source / receptor list elements
    so the loader can dispatch on read.
    """
    d = json.loads(json.dumps(project, cls=_Encoder))
    # The default asdict path drops _type for *list elements* — we need
    # the discriminator on each source / receptor entry. Re-attach it
    # by walking the original project tree.
    if project.sources is not None and project.sources.sources:
        d["sources"]["sources"] = [
            {**dataclasses.asdict(s), "_type": type(s).__name__}
            for s in project.sources.sources
        ]
    if project.receptors is not None:
        for fname in ("cartesian_grids", "polar_grids", "discrete_receptors"):
            arr = getattr(project.receptors, fname, None)
            if arr:
                d["receptors"][fname] = [
                    {**dataclasses.asdict(r), "_type": type(r).__name__}
                    for r in arr
                ]
    return d


# ---------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------

def _strip(obj: Any) -> Any:
    """Drop _type / _enum tags before passing kwargs to a dataclass ctor."""
    if isinstance(obj, dict):
        if "_enum" in obj:
            return obj  # leave for resolve_enums; not a kwargs payload
        return {k: _strip(v) for k, v in obj.items() if k != "_type"}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _resolve_enums(obj: Any, enum_lookup: dict[str, Type[Enum]]) -> Any:
    if isinstance(obj, dict):
        if "_enum" in obj:
            cls_name, member = obj["_enum"].split(".", 1)
            cls = enum_lookup.get(cls_name)
            if cls is None:
                return obj  # unknown enum; pass through
            return cls[member]
        return {k: _resolve_enums(v, enum_lookup) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_enums(v, enum_lookup) for v in obj]
    return obj


def _build_dataclass(cls: Type, payload: dict) -> Any:
    """Instantiate a dataclass from a payload dict, ignoring unknown keys."""
    valid = set(cls.__dataclass_fields__.keys())
    kwargs = {k: v for k, v in payload.items() if k in valid}
    return cls(**kwargs)


def _enum_lookup() -> dict[str, Type[Enum]]:
    """Build the enum-class registry used during deserialization."""
    from ..input_generator import (
        ChemistryMethod,
        DepositionMethod,
        PollutantType,
        SourceType,
        TerrainType,
    )
    return {
        "PollutantType": PollutantType,
        "SourceType": SourceType,
        "TerrainType": TerrainType,
        "ChemistryMethod": ChemistryMethod,
        "DepositionMethod": DepositionMethod,
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def project_to_json(project: AERMODProject) -> str:
    """Return ``project`` as the JSON text :func:`save_project` writes."""
    from .. import __version__

    payload = {
        "pyaermod_version": __version__,
        "save_format_version": SAVE_FORMAT_VERSION,
        "project": _project_to_jsonable(project),
    }
    return json.dumps(payload, indent=2)


def save_project(
    project: AERMODProject, path: Union[str, Path],
) -> Path:
    """Write ``project`` to ``path`` as JSON. Returns the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(project_to_json(project), encoding="utf-8")
    return out


def _mapping(value: Any, what: str, origin: str) -> dict:
    """``value`` if it is a JSON object (``None`` reads as empty), else ValueError."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            f"{origin}: {what} must be a JSON object, not {type(value).__name__}"
        )
    return value


def _items(value: Any, what: str, origin: str) -> list:
    """``value`` if it is a JSON list of objects (``None`` reads as empty)."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            f"{origin}: {what} must be a JSON list, not {type(value).__name__}"
        )
    for i, item in enumerate(value):
        _mapping(item, f"{what}[{i}]", origin)
    return value


def project_from_json(text: Union[str, bytes], *, origin: str = "<text>") -> AERMODProject:
    """Read an AERMODProject from JSON text written by :func:`project_to_json`.

    Tolerates older save formats by reading what's there and filling
    missing fields with dataclass defaults. Every problem with the text
    itself -- invalid JSON, a document of the wrong shape, a newer save
    format -- raises :class:`ValueError` whose message starts with
    ``origin`` (a file name, or ``"<text>"``).
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{origin}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict) or "project" not in raw:
        raise ValueError(f"{origin}: not a pyaermod project file")
    sfv = raw.get("save_format_version")
    if sfv is not None and not isinstance(sfv, int):
        raise ValueError(f"{origin}: save_format_version={sfv!r} is not a number")
    if sfv is not None and sfv > SAVE_FORMAT_VERSION:
        raise ValueError(
            f"{origin}: save_format_version={sfv} is newer than this build "
            f"supports (max {SAVE_FORMAT_VERSION}). Upgrade pyaermod."
        )
    project_raw = _mapping(raw["project"], "project", origin)
    enums = _enum_lookup()
    project_dict = _resolve_enums(project_raw, enums)

    def pathway(name: str) -> dict:
        return _mapping(project_dict.get(name), f"project.{name}", origin)

    def build(cls: Type, payload: dict, what: str) -> Any:
        # A missing required field or a value the dataclass rejects is a
        # problem with the file, not with the caller.
        try:
            return _build_dataclass(cls, _strip(payload))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{origin}: {what}: {exc}") from exc

    # Check the shape of every pathway before building any of them.
    control_d, src_payload, rec_payload, met_d, out_d = (
        pathway(n) for n in ("control", "sources", "receptors", "meteorology", "output")
    )
    src_items = _items(src_payload.get("sources"), "project.sources.sources", origin)
    rec_items = {
        field: _items(rec_payload.get(field), f"project.receptors.{field}", origin)
        for field in ("cartesian_grids", "polar_grids", "discrete_receptors")
    }

    # Pathways
    control = build(ControlPathway, control_d, "project.control")

    sources_list = []
    for i, s in enumerate(src_items):
        cls = _SOURCE_TYPES.get(s.get("_type", ""))
        if cls is None:
            continue
        sources_list.append(build(cls, s, f"project.sources.sources[{i}]"))
    sources = SourcePathway(sources=sources_list)

    def receptors_of(field: str, cls: Type) -> list:
        return [build(cls, g, f"project.receptors.{field}[{i}]")
                for i, g in enumerate(rec_items[field])
                if g.get("_type") == cls.__name__]

    receptors = ReceptorPathway(
        cartesian_grids=receptors_of("cartesian_grids", CartesianGrid),
        polar_grids=receptors_of("polar_grids", PolarGrid),
        discrete_receptors=receptors_of("discrete_receptors", DiscreteReceptor),
    )

    meteorology = build(MeteorologyPathway, met_d, "project.meteorology")
    output = build(OutputPathway, out_d, "project.output")

    return AERMODProject(
        control=control, sources=sources, receptors=receptors,
        meteorology=meteorology, output=output,
    )


def load_project(path: Union[str, Path]) -> AERMODProject:
    """Read an AERMODProject from a JSON file written by :func:`save_project`."""
    return project_from_json(Path(path).read_text(encoding="utf-8"), origin=str(path))


__all__ = [
    "SAVE_FORMAT_VERSION",
    "load_project",
    "project_from_json",
    "project_to_json",
    "save_project",
]
