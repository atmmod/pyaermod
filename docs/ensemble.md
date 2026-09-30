# Ensembles: many AERMOD runs from one design

`pyaermod.ensemble` runs a designed set of AERMOD runs, such as one run
per particle size bin, met set and source configuration, and keeps the
books on them. You give it the design as a list of rows and a function
that builds the project for one row. It then does four things:

- It runs every row in its own directory, several at a time.
- It names each run by a hash of what defines it.
- It records each run in a manifest as the run finishes.
- It picks up where it stopped when you run the same design again.

`collect_plotfiles` then reads the PLOTFILEs of every finished run into
one table.

```python
from pyaermod.ensemble import collect_plotfiles, run_design

rows = [
    {"diameter_um": d, "density": rho}
    for d in (2.5, 5.0, 10.0, 20.0)
    for rho in (1.0, 2.65)
]

def build(factors):
    project = make_base_project()          # your own AERMODProject
    project.sources.sources[0].particle_deposition = ParticleDepositionParams(
        [factors["diameter_um"]], [1.0], [factors["density"]])
    project.output.plot_file = "pit.plt"
    return project

if __name__ == "__main__":                 # required on macOS and Windows
    result = run_design(rows, build, "study/runs", n_workers=4,
                        executable="bin/aermod")
    print(result.n_run, "runs made,", result.n_skipped, "already done,",
          result.n_failed, "failed")
    table = collect_plotfiles("study/runs")   # also writes plotfiles.csv/.npz
```

## Why one directory per run

AERMOD reads its deck from `aermod.inp` in its working directory and
writes its output files wherever the deck says. This causes two problems
when decks share a directory:

- **They overwrite each other's results.** Two decks that name the same
  PLOTFILE overwrite each other. EPA's own decks name outputs such as
  `../plotfiles/SURFCOAL_01H.PLT`, so decks that share such a path clash
  even from different directories.
- **They run one at a time.** `AERMODRunner` locks the working directory
  for the length of a run, so that two runs do not both use its
  `aermod.inp`. Decks in one directory therefore run one after another,
  whatever `n_workers` is. Two 16-second runs in one directory on two
  workers took 35 s, one starting as the other ended.

`run_design` gives every run the directory `root/runs/<run ID>`. It
rewrites every output file name in the deck to a bare name inside that
directory (`rewrite_output_names`), so `../shared/pit.plt` becomes
`pit.plt`. The keywords covered are PLOTFILE, POSTFILE, SUMMFILE,
MAXIFILE, RANKFILE, SEASONHR, EVALFILE, TOXXFILE, MAXDAILY, MXDYBYYR,
MAXDCONT, EVENTFIL, SAVEFILE, MULTYEAR and the SCIMBYHR summary files.

It also links the surface and profile met files into the directory, and
the deck names them without a directory. This has three benefits:

- The deck does not depend on where the met files live.
- The deck stays within AERMOD's 200-character limit on a file name
  (`ILEN_FLD` in `modules.f`). With v26135, a 201-character `SURFFILE`
  path fails with E291 "Filename specified is too long" and then E500.
- The deck text stays the same on every machine.

Where links cannot be made, the met files are copied. Other files AERMOD
reads, such as `INITFILE`, `HOUREMIS` and background or ozone files, are
not moved. Give them as absolute paths.

## Run IDs

A run's ID is the SHA-256 of the canonical JSON of four things:

- the row's factors;
- the SHA-256 of the AERMOD binary;
- the SHA-256 of the surface and profile met files;
- `SCHEMA_VERSION`, now 1.

The payload looks like this:

```json
{"binary_sha256":"…","factors":{"density":1.0,"diameter_um":2.5},
 "met_sha256":{"profile":"…","surface":"…"},"schema_version":1}
```

`canonical_json` sorts keys, writes no whitespace, and writes floats in
their shortest round-trip form (so `1.0` and `1` are different factors).
It also writes:

- an enum as its value;
- a dataclass, such as `ParticleDepositionParams`, as its fields plus
  `"_type"`;
- NumPy scalars and arrays as plain numbers and lists.

It refuses NaN, infinities and dict keys that are not strings, so an ID
never depends on how Python happened to print something.

The ID does not depend on paths, dates or the machine. What follows from
that:

- **A new binary or an edited met file** gives new IDs, so its runs go to
  new directories and the old runs are kept.
- **Two rows with the same factors** are an error, because they would be
  the same run.
- **A factor is anything that defines the run.** Put the met set or the
  source configuration in the row, even when `build_fn` reads it from
  elsewhere.
- **Fixed parts of the deck are not in the ID.** A change to `build_fn`
  keeps a row's ID. Resume notices the change from the deck text (see
  below).

Each run directory holds `factors.json`, the payload its ID hashes.

## The manifest

`root/manifest.json` is an `EnsembleManifest`: a
`runner_utils.RunManifest` whose entries are `EnsembleManifestEntry`, a
subclass of `RunManifestEntry`, keyed by run ID. It is written in one
step (a temporary file and a rename), so a killed process never leaves
half a manifest. A plain `RunManifest.load` still reads it.

Before any run starts, every run of the design gets an entry with status
`pending`. Each entry is updated, and the file saved, as its run finishes.
`manifest.csv`, one row per run with the factors as `factor.<name>`
columns, is written at the end.

| Field | What it holds |
|---|---|
| `run_id`, `run_dir`, `input_file` | The ID, `runs/<ID>` and `runs/<ID>/run.inp`, relative to the root |
| `status` | `pending`, `success` or `failed`, by the runner's rule: AERMOD's `*** AERMOD Finishes Successfully ***` and no fatal errors |
| `factors`, `schema_version` | The row, as canonical JSON would write it |
| `input_sha256` | The SHA-256 of the deck as written |
| `binary`, `binary_sha256`, `aermod_version` | The binary's path and SHA-256, and the version in the `.out` banner (`26135`) |
| `met_files`, `met_sha256` | The source path and SHA-256 of each met file |
| `outputs` | The output file names by keyword, such as `{"PLOTFILE": ["pit.plt"]}` |
| `git_commit`, `git_dirty`, `pyaermod_version` | pyaermod's commit, when it runs from a git checkout, and whether its tracked files differed from it |
| `runtime_seconds`, `started`, `finished` | The run's wall time and local start and end times |
| `return_code`, `warning_count`, `fatal_count`, `warnings`, `error_message` | AERMOD's exit code and message summary |

## Resuming

Run the same design again with the same root. A run is skipped only when
all of these hold:

1. Its entry says `success` for the same deck text (`input_sha256`).
2. The deck on disk is that deck.
3. Its `.out` has AERMOD's success banner and AERMOD's copy of that deck
   at the top. This is the rule `runner_utils.resume_batch` applies.
4. Its PLOTFILEs and POSTFILEs are still there.

Every other run is made again. That covers:

- a run that failed;
- a run that was killed, whose entry is still `pending`;
- a run whose `build_fn` now writes a different deck;
- a run whose files were removed.

Before a run is made again, the outputs of the earlier attempt are
deleted, so a run that fails early cannot leave old results behind. Pass
`resume=False` to make every run again.

So if an ensemble is interrupted, with Ctrl-C, a killed job or a reboot,
run the same script again. The runs that finished are skipped and the
others are made.

## Collecting the PLOTFILEs

`collect_plotfiles(root)` returns a pandas DataFrame with one row per
receptor of each PLOTFILE of each successful run. It reads the files
with `aermod_outputs.read_plotfile`.

- **Columns.** The first three are `run_id`, `plotfile` (the file name)
  and `receptor` (the row's position in its file, from 0). After them
  come AERMOD's own columns in lower case with underscores: `x`, `y`,
  `average_conc`, `total_depo`, `dry_depo`, `wet_depo`, `zelev`, `zhill`,
  `zflag`, `ave`, `grp`, `num_hrs` (PERIOD files), `rank` and
  `date_conc` (short-term files), and `net_id`.
- **Missing columns.** A column that one file lacks is empty in that
  file's rows.
- **Factors.** The factors are not repeated in this table. Join on
  `run_id` with `result.to_dataframe()` or the manifest's
  `to_dataframe()`.
- **Files written.** The table is also written as `plotfiles.csv` and
  `plotfiles.npz` under the root (`out_stem=` changes the name, and
  `None` writes neither). The `.npz` holds one array per column, text as
  NumPy unicode arrays, so `numpy.load` reads it without
  `allow_pickle`. No new dependency is needed.

## Parallel runs and their speed-up

`n_workers` runs go at a time, each in a worker process. `n_workers=1`
runs them one after another in the calling process. On macOS and
Windows the workers are started with `spawn`, so the calling script must
use the `if __name__ == "__main__":` guard (see `AERMODRunner.run_batch`
in [Common errors](common-errors.md)).

`DesignResult` reports two times:

- `elapsed_seconds`, the wall time of the call;
- `run_seconds`, the sum of the runs' own wall times.

Their ratio, `concurrency`, is how many runs were in progress on
average. It is not the speed-up over running one at a time: runs that
share a machine slow each other down, so each run's own time is longer
than it would be alone. To measure the speed-up, time the same design
with `n_workers=1`.

On 2026-09-30 we measured this for WP-D5's acceptance on a 12-core Apple
M2 Pro, with a gfortran 15.2 `-O2 -fbounds-check` build of AERMOD v26135:

- **The design.** Four single-bin OPENPIT runs on EPA's Cordero Mine
  met: 720 hours, with `NOCHKD` because the days alternate. Each run had
  8,064 polar receptors.
- **Timing.** The runs took 60.0 to 60.6 s each alone. The whole design
  took 240.9 s with `n_workers=1` and 64.6 s with `n_workers=4`, a
  speed-up of 3.7. Each run took about 62 s on four workers, and
  `concurrency` was 3.85.
- **No overwrites.** Each run's PLOTFILE data rows were identical in the
  two roots.
- **Resume.** A four-run design on two workers was sent SIGINT after two
  runs finished. The manifest then showed two `success` and two
  `pending`. Run again on four workers, it made only the two pending
  runs.
