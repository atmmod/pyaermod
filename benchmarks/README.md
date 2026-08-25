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

## CI harness (`run_benchmarks.py` + `compare_benchmarks.py`)

`.github/workflows/benchmarks.yml` runs the JSON-emitting harness on every
PR, once for the PR head and once for `origin/main`, then compares the two.

```bash
# Emit benchmark_results.json. Each benchmark is timed over --rounds
# independent rounds and the *minimum* is reported (default 5 rounds).
python benchmarks/run_benchmarks.py --output bench_current.json [--rounds 5] [--quiet]

# Compare against a baseline. Exit 1 on a regression when --fail-on-regression.
python benchmarks/compare_benchmarks.py \
    --baseline bench_base.json --current bench_current.json \
    --threshold 0.25 --min-baseline-ms 5.0 --fail-on-regression
```

### Noise control

Two knobs keep the gate from failing PRs on timing noise:

- **Best-of-N rounds** (`run_benchmarks.py --rounds N`, default 5). Noise
  from GC, scheduler preemption and CPU frequency scaling only ever *adds*
  time, so the minimum over rounds is the least-biased, most repeatable
  estimate of an operation's cost. The chosen `rounds` is recorded in the
  JSON (`"rounds": N`).
- **Noise floor** (`compare_benchmarks.py --min-baseline-ms X`, default
  5.0 ms). A benchmark whose *baseline* is below the floor is reported in an
  `IGNORED` section but never counted as a regression — a sub-millisecond
  parse that moves from 0.17 ms to 0.24 ms (+37%) is noise, not a code
  change. Pass `--min-baseline-ms 0` to disable the floor. The floor is
  applied per benchmark, so a noisy sub-ms entry never masks a real
  regression on a slower one.

## Benchmarks

### Input Generation (`bench_input_gen.py`)

Measures `AERMODProject.to_aermod_input()` speed for varying source counts (1–1000) across PointSource, AreaSource, and VolumeSource types. Each configuration is run 100 iterations.

### Output Parsing (`bench_output_parse.py`)

Measures `AERMODOutputParser.parse()` speed for synthetic `.out` files with 100–5000 receptors. Each configuration is run 10 iterations.

### POSTFILE Parsing (`bench_postfile.py`)

Compares text (formatted) vs binary (unformatted) POSTFILE parsing via `read_postfile()` for various receptor × timestep combinations. Reports the speed ratio between formats.
