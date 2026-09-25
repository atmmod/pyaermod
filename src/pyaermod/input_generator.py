"""
PyAERMOD Input File Generator

Generates AERMOD-compatible input files from Python objects.
Based on AERMOD version 26135 keyword specifications (validated against 26135
and 24142; see :mod:`pyaermod.versions`).

.. note::

   As of v1.6.0 the dataclasses that used to live in this single file
   have been split into focused submodules:

   * :mod:`pyaermod.pathways` -- enums, chemistry options, Control / Met /
     Output / Event pathways
   * :mod:`pyaermod.sources` -- deposition helpers, building-downwash
     helpers, all source dataclasses, SourcePathway
   * :mod:`pyaermod.receptors` -- CartesianGrid, PolarGrid,
     DiscreteReceptor, ReceptorPathway

   This module re-exports every public name so that existing imports
   (``from pyaermod.input_generator import X``) continue to work
   unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

# ---- Re-export everything from the new submodules --------------------------
from .pathways import (  # noqa: F401  -- re-exports
    BackgroundSpec,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    EventPathway,
    EventPeriod,
    GasDepositionDefaults,
    InitFile,
    MaxDailyContribution,
    MaxDailyFile,
    MaxiFile,
    MeteorologyPathway,
    MultiYear,
    NOxBackground,
    OutputPathway,
    OzoneData,
    PollutantType,
    SaveFile,
    SourceType,
    TemporalValues,
    TerrainType,
    UrbanArea,
)
from .receptors import (  # noqa: F401  -- re-exports
    CartesianGrid,
    DiscreteReceptor,
    PolarGrid,
    ReceptorPathway,
)
from .sources import (  # noqa: F401  -- re-exports
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    DepositionMethod,
    EmissionUnits,
    GasDepositionParams,
    LineSource,
    OpenPitSource,
    ParticleDepositionParams,
    PointSource,
    RLineExtSource,
    RLineSource,
    SolidBarrier,
    SolidBarrierSegment,
    SourceGroupDefinition,
    SourcePathway,
    StreetCanyon,
    VegetativeBarrier,
    VolumeSource,
    _building_downwash_lines,
    _deposition_to_aermod_lines,
    _format_building_keyword,
    _set_building_from_bpip,
)
from .unparsed import UnparsedLine, preserved_block

# ============================================================================
# MAIN PROJECT CLASS
# ============================================================================

# Keywords a pathway's preserved lines must precede. SRCGROUP (and the
# other group keywords) look their members up among the sources defined
# so far (soset.f, E300), so a LOCATION or INCLUDED kept verbatim has to
# come before the groups the writer generates.
_PRESERVE_BEFORE = {"SO": ("SRCGROUP", "OLMGROUP", "PSDGROUP")}

# Keywords AERMOD requires as the first card of their pathway (soset.f /
# reset.f, E152); a preserved one goes straight after ``<code> STARTING``.
_PRESERVE_FIRST = ("ELEVUNIT",)


def _with_preserved(code: str, text: str, kept: List[UnparsedLine]) -> str:
    """Splice ``code``'s preserved lines into its pathway text.

    A keyword in :data:`_PRESERVE_FIRST` goes right after the STARTING
    line. The rest go in front of the first keyword listed in
    :data:`_PRESERVE_BEFORE` for the pathway, or just before
    ``<code> FINISHED``.
    """
    mine = [ln for ln in kept if ln.pathway == code]
    first = [ln for ln in mine if ln.keyword in _PRESERVE_FIRST]
    rest = preserved_block(code, [ln for ln in mine if ln.keyword not in _PRESERVE_FIRST])
    if not first and not rest:
        return text
    lines = text.split("\n")
    if first:
        start = next(i for i, line in enumerate(lines)
                     if line.strip().upper() == f"{code} STARTING")
        lines[start + 1:start + 1] = [ln.to_aermod_line() for ln in first]
    if rest:
        idx = max(i for i, line in enumerate(lines)
                  if line.strip().upper() == f"{code} FINISHED")
        for i, line in enumerate(lines):
            toks = line.split()
            if toks and toks[0].upper() in _PRESERVE_BEFORE.get(code, ()):
                idx = i
                break
        lines[idx:idx] = rest
    return "\n".join(lines)


@dataclass
class AERMODProject:
    """
    Complete AERMOD project

    Combines all pathways into a single input file.
    """
    control: ControlPathway
    sources: SourcePathway
    receptors: ReceptorPathway
    meteorology: MeteorologyPathway
    output: OutputPathway
    events: Optional[EventPathway] = None

    # Lines of a deck read by pyaermod.input_reader that have no field
    # on this model (see pyaermod.unparsed). The writer puts them back
    # into their pathway so a rewritten deck keeps them; a project built
    # in Python has none.
    unparsed_lines: List[UnparsedLine] = field(default_factory=list)

    def to_aermod_input(self,
                        validate: bool = True,
                        check_files: bool = False,
                        preserve_unparsed: bool = True) -> str:
        """
        Generate complete AERMOD input file.

        Parameters
        ----------
        validate : bool
            If True (default in pyaermod 2.0+), run the configuration
            validator before generating output. Raises ``ValueError`` on
            validation errors (warnings are allowed). Pass
            ``validate=False`` to skip validation entirely.
        check_files : bool
            If True (and validate is True), also verify that meteorology
            files exist on disk.
        preserve_unparsed : bool
            If True (default), every :attr:`unparsed_lines` entry is
            written back into its pathway, just before the pathway's
            ``FINISHED`` line, under a ``**`` comment banner. Pass
            ``False`` to write only what the model represents.
        """
        if validate:
            from pyaermod.validator import Validator
            result = Validator.validate(self, check_files=check_files)
            if not result.is_valid:
                raise ValueError(str(result))

        # Pass chemistry options to SO pathway for OLMGROUP emission
        chemistry = getattr(self.control, "chemistry", None)

        pathways = [
            ("CO", self.control.to_aermod_input()),
            ("SO", self.sources.to_aermod_input(
                chemistry=chemistry,
                psd_credit=getattr(self.control, "psd_credit", False),
            )),
            ("RE", self.receptors.to_aermod_input()),
            ("ME", self.meteorology.to_aermod_input()),
            ("OU", self.output.to_aermod_input()),
        ]
        kept = self.unparsed_lines if preserve_unparsed else []
        sections = [_with_preserved(code, text, kept) for code, text in pathways]
        ev_lines = preserved_block("EV", kept)
        if ev_lines:
            # The reader keeps an inline EV pathway whole; AERMOD wants
            # it last, after OU.
            sections.append("\n".join(["EV STARTING", *ev_lines, "EV FINISHED"]))
        return "\n\n".join(sections)

    def write(self, filename: Union[str, Path],
              event_filename: Optional[Union[str, Path]] = None,
              validate: bool = True,
              check_files: bool = False):
        """Write input file to disk.

        Parameters
        ----------
        filename : str or Path
            Path for the main AERMOD input file.
        event_filename : str or Path, optional
            Path for the event file. Required if events are defined.
        validate : bool
            Forwarded to :meth:`to_aermod_input`. Default True
            (pyaermod 2.0+). Pass ``validate=False`` to skip.
        check_files : bool
            Forwarded to :meth:`to_aermod_input`.
        """
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # write() called without specifying `validate` is the most
        # common path; pass through so the deprecation warning surfaces
        # at the user's call site rather than inside our writer.
        with open(output_path, 'w') as f:
            f.write(self.to_aermod_input(validate=validate,
                                         check_files=check_files))

        if self.events and event_filename:
            event_path = Path(event_filename)
            with open(event_path, 'w') as f:
                f.write(self.events.to_aermod_input())

        return output_path


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def create_example_project() -> AERMODProject:
    """Create an example AERMOD project"""

    # Control pathway
    control = ControlPathway(
        title_one="Example AERMOD Project",
        title_two="Generated by pyaermod",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24", "1"],
        terrain_type=TerrainType.FLAT
    )

    # Sources
    sources = SourcePathway()

    stack1 = PointSource(
        source_id="STACK1",
        x_coord=500.0,
        y_coord=500.0,
        base_elevation=10.0,
        stack_height=50.0,
        stack_temp=400.0,  # Kelvin
        exit_velocity=15.0,  # m/s
        stack_diameter=2.0,  # m
        emission_rate=1.5,  # g/s
        source_groups=["ALL"]
    )
    sources.add_source(stack1)

    # Receptors - Cartesian grid
    receptors = ReceptorPathway()

    grid = CartesianGrid.from_bounds(
        x_min=0.0,
        x_max=2000.0,
        y_min=0.0,
        y_max=2000.0,
        spacing=100.0
    )
    receptors.add_cartesian_grid(grid)

    # Meteorology
    meteorology = MeteorologyPathway(
        surface_file="example.sfc",
        profile_file="example.pfl",
        start_year=2023,
        start_month=1,
        start_day=1,
        end_year=2023,
        end_month=12,
        end_day=31
    )

    # Output
    output = OutputPathway(
        receptor_table=True,
        receptor_table_rank=10,
        max_table=True,
        summary_file="example.sum"
    )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )


if __name__ == "__main__":
    # Create example project
    project = create_example_project()

    # Print to console
    print(project.to_aermod_input())

    # Or write to file
    # project.write("example.inp")
