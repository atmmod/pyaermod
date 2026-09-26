# Benchmarks

Two questions a reader of the manuscript will ask about a wrapper: what
does driving AERMOD through pyaermod cost over calling the binary
directly, and how far does pyaermod's batch API scale on one machine?
Both are measured by `benchmarks/bench_aermod_runs.py` on EPA's own
`aertest` test case with an AERMOD v26135 binary compiled from EPA's
source, and both were run twice for this page: on a GitHub Actions
runner by the `Benchmarks` workflow's manual dispatch, and in the Linux
container the release branch was prepared in. Every number below is
from one of those two runs; the command that produced it is at the end.

## What is measured

**Single-run overhead.** One AERMOD run of `aertest.inp` (a point source
with PRIME downwash, 144 receptors, four days of meteorology) is timed
two ways in the same directory, interleaved for 50 repeats:

- *direct*: `subprocess.run([aermod, "aertest.inp", "aertest_direct.out"], cwd=dir)`
  with stdout and stderr discarded, the cheapest possible invocation;
- *pyaermod*: `AERMODRunner(executable_path=aermod).run("aertest.inp", working_dir=dir)`,
  which links the deck to `aermod.inp`, takes the directory lock,
  redirects the binary's output to files, runs it with a timeout, renames
  the outputs and returns an `AERMODRunResult`.

The medians and quartiles of each are reported; the difference of the
medians is the per-run overhead.

**Batch throughput.** 32 staged copies of the case (one directory each,
because the runner locks its working directory) are run through
`AERMODRunner.run_batch(files, n_workers=w)` at `w` = 1, 2, 4 and the
machine's core count (4 on both machines, so three points), reported as
runs per minute and as the speed-up over one worker.

## Results

### Machines

| | GitHub Actions (CI) | Release container |
|---|---|---|
| CPU | Intel Xeon Platinum 8573C, 4 CPUs | Intel Xeon @ 2.80 GHz, 4 CPUs |
| OS | Linux 6.17 (Azure), glibc 2.39 | Linux 6.18, glibc 2.39 |
| Python | 3.12.14 | 3.11.15 |
| AERMOD | 26135, `scripts/build_aermod.sh`, gfortran (Ubuntu 24.04) | 26135, `scripts/build_aermod.sh`, gfortran 13.3.0 |
| Test case | `aertest` from EPA's `aermod_test_cases.zip`, set `aermet26135_aermod26135` | the same deck, vendored under `tests/fixtures/epa_official` |
| Run | [`Benchmarks` run 36208104513](https://github.com/atmmod/pyaermod/actions/runs/36208104513), job `aermod-runs`, 2026-09-26 | `python benchmarks/run_benchmarks.py --aermod`, 2026-09-26, commit e55dab9 plus this branch |

### Single-run overhead (50 repeats, milliseconds)

| | CI: direct | CI: pyaermod | Container: direct | Container: pyaermod |
|---|---:|---:|---:|---:|
| median | 95.3 | 115.3 | 114.2 | 115.5 |
| p25 – p75 | 94.7 – 95.7 | 115.3 – 115.4 | 111.9 – 116.6 | 115.3 – 165.6 |
| min – max | | | 109.8 – 159.3 | 115.0 – 219.2 |
| mean | | | 115.7 | 140.6 |
| **overhead (median)** | | **20.0 ms (21 %)** | | **1.4 ms (1.2 %)** |

The CI log prints medians and quartiles only; the container's full
distribution is in its JSON output.

The two overheads disagree because the runner's wall time is not the
binary's wall time plus a fixed cost. On both machines the pyaermod
median sits at 115.3 to 115.5 ms with a very tight interquartile range,
while the direct call takes 95 ms on the CI runner and 114 ms in the
container. That fixed value is CPython's doing, not AERMOD's: the runner
calls `subprocess.run(..., timeout=...)` with the output redirected to
files, and with no pipes to select on, `Popen.wait(timeout)` polls the
child with sleeps of 0.5, 1, 2, 4, 8, 16 and 32 ms and then 50 ms per
poll. A child that exits after 95 ms is noticed at the poll at about
113.5 ms; one that exits after 114 ms is noticed at about 163.5 ms,
which is the container's 165 ms upper quartile and the 215 ms maximum.
Repeating the direct call in the container with `timeout=600` added
reproduces the effect exactly (median 114.8 ms, p25 to p75 114.5 to
115.0 ms, maximum 165 ms, against 111.6 ms and 110.4 to 116.2 ms
without a timeout), and the invocation form, the directory lock, the
symlink and the output capture make no measurable difference.

So the cost of pyaermod's own work around a run (the lock, the symlink,
two redirected output files, three renames, reading the captured output)
is below the resolution of this measurement, about a millisecond, and
the overhead a caller sees is the latency of the polling wait: up to
50 ms per run, and on average 20 ms for a run of this length. It matters
only for runs that finish in well under a second; a typical regulatory
run of a year of meteorology takes minutes, where 20 ms is noise. The
follow-up it points at is a wait that does not poll (a blocking
`os.waitpid` guarded by a timer, or `communicate()` on a pipe drained
to a file), which is a change to `pyaermod.runner` outside the scope of
the release that recorded this.

### Batch throughput (32 runs)

| workers | CI: seconds | CI: runs/min | CI: speed-up | Container: seconds | Container: runs/min | Container: speed-up |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3.69 | 520.0 | 1.00× | 4.37 | 439.4 | 1.00× |
| 2 | 1.85 | 1037.1 | 1.99× | 2.34 | 820.1 | 1.87× |
| 4 | 1.36 | 1414.1 | 2.72× | 1.40 | 1370.5 | 3.12× |

Two workers double the throughput on both machines; four workers give
2.7× on the CI runner and 3.1× in the container. Both machines expose
four CPUs, and the shortfall at four workers is the usual one for four
processes on four shared cores (the parent's process pool and the
runner's per-run file work also take turns on them). The throughput at
one worker is a little below the single-run rate because each batch run
goes through the process pool and the polling wait described above; the
figures are what `run_batch` delivers, not what the binary could.

## Reproducing

From a clean checkout of the release tag, with `gfortran` installed:

```bash
scripts/build_aermod.sh aermod                     # -> bin/aermod from EPA's current source
python benchmarks/run_benchmarks.py --aermod --require-aermod \
    --aermod-repeats 50 --aermod-batch-runs 32 --aermod-workers 1,2,4,auto \
    --output benchmark_results.json
```

Without an unpacked EPA reference set under `test_cases/` the case is the
vendored copy of `aertest`, which is the same deck; with one, the deck
and meteorology are taken from it (the CI run above did that, unpacking
only `aertest.inp`, `aermet2.sfc`, `aermet2.pfl` and the reference
POSTFILE from EPA's archive). The `aermod` section of the JSON records
the machine, CPU count, AERMOD version, case and both measurements in
full. On GitHub, *Actions → Benchmarks → Run workflow* with
"aermod_runs" ticked runs the same thing on a fresh runner and prints
the report in the job summary.

The input-generation and parser benchmarks that gate every pull request
(`benchmarks/README.md`) are unchanged by this and need no binary.
