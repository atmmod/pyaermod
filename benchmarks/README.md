# PyAERMOD Performance Benchmarks

Simple performance benchmarks for core PyAERMOD operations. Uses `time.perf_counter()` with no external dependencies.

## Running Benchmarks

Each benchmark is a standalone script:

```bash
python benchmarks/bench_input_gen.py
python benchmarks/bench_output_parse.py
python benchmarks/bench_postfile.py
```

Or run all at once:

```bash
python -m benchmarks.bench_input_gen && \
python -m benchmarks.bench_output_parse && \
python -m benchmarks.bench_postfile
```

## Benchmarks

### Input Generation (`bench_input_gen.py`)

Measures `AERMODProject.to_aermod_input()` speed for varying source counts (1–1000) across PointSource, AreaSource, and VolumeSource types. Each configuration is run 100 iterations.

### Output Parsing (`bench_output_parse.py`)

Measures `AERMODOutputParser.parse()` speed for synthetic `.out` files with 100–5000 receptors. Each configuration is run 10 iterations.

### POSTFILE Parsing (`bench_postfile.py`)

Compares text (formatted) vs binary (unformatted) POSTFILE parsing via `read_postfile()` for various receptor × timestep combinations. Reports the speed ratio between formats.
