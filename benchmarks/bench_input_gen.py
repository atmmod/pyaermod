"""Benchmark AERMOD input file generation speed."""
import time

from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
    VolumeSource,
)


def _make_point_sources(n):
    sp = SourcePathway()
    for i in range(n):
        sp.add_source(PointSource(
            source_id=f"S{i:04d}",
            x_coord=100.0 * i,
            y_coord=0.0,
            stack_height=50.0,
            stack_temp=400.0,
            exit_velocity=15.0,
            stack_diameter=2.0,
            emission_rate=1.0,
        ))
    return sp


def _make_area_sources(n):
    sp = SourcePathway()
    for i in range(n):
        sp.add_source(AreaSource(
            source_id=f"A{i:04d}",
            x_coord=100.0 * i,
            y_coord=0.0,
            emission_rate=0.01,
        ))
    return sp


def _make_volume_sources(n):
    sp = SourcePathway()
    for i in range(n):
        sp.add_source(VolumeSource(
            source_id=f"V{i:04d}",
            x_coord=100.0 * i,
            y_coord=0.0,
            emission_rate=1.0,
        ))
    return sp


def _make_project(sources):
    return AERMODProject(
        control=ControlPathway(title_one="Benchmark"),
        sources=sources,
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
        output=OutputPathway(),
    )


def benchmark_input_generation():
    counts = [1, 10, 50, 100, 500, 1000]
    iterations = 100

    for src_name, factory in [
        ("PointSource", _make_point_sources),
        ("AreaSource", _make_area_sources),
        ("VolumeSource", _make_volume_sources),
    ]:
        print(f"\n--- {src_name} ---")
        for n in counts:
            sources = factory(n)
            project = _make_project(sources)

            start = time.perf_counter()
            for _ in range(iterations):
                project.to_aermod_input()
            elapsed = time.perf_counter() - start

            ms_per_call = elapsed / iterations * 1000
            calls_per_sec = iterations / elapsed
            print(f"  {n:5d} sources: {ms_per_call:8.2f} ms/call  ({calls_per_sec:8.0f} calls/sec)")


if __name__ == "__main__":
    print("=== AERMOD Input Generation Benchmarks ===")
    benchmark_input_generation()
