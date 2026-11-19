# Slice D review: runners (slice-d)

Files read in full: runner.py, runner_utils.py, wasm_runner.py, aermet_runner.py, aerscreen_runner.py, aersurface_runner.py, versions.py.
Repro scripts: scratchpad/repro/slice-d/r1.py..r5.py (run with the scratchpad venv).
Not looked at: aermap runner, the GUI's use of AERMODRun, real binaries (none run), Windows (no Windows host: msvcrt/TerminateProcess findings are READ), Pyodide (no Pyodide host: wasm findings are READ).

## Status of earlier open items (11-11 review, Low "Runner" line)
- lock/link left held when _stage fails: STILL PRESENT, and worse than recorded (D1).
- wasm crash loses partial .out: FIXED. runner.py:442-454 catches the trap, writes it to stderr, returncode=1, and run() then calls `_collect`, which renames and parses the partial .out; 478-483 forces success=False.
- explicit wasm path silently ignored when missing: FIXED. wasm_runner.py:110-113 makes an explicit path the only candidate; 132 raises WasmAERMODNotFound; runner.py:338-339 routes through it.
- wasm cache keyed only on path: STILL PRESENT (D6).
- run_batch fails under Pyodide even with n_workers=1: STILL PRESENT (D7).
- Success detection (AERMOD exits 0 after fatal errors): AERMOD runner OK (runner.py:706-712 requires rc 0, .out written this run, "AERMOD Finishes Successfully" banner, zero fatal count; stale outputs are deleted first at 638-641). AERMET OK (aermet_runner.py:342: rc 0 + FINISHED SUCCESSFULLY on screen + error_count 0). AERSCREEN weak (D3). AERSURFACE weak (D4).

## Bugs

### D1 [BUG] [medium] run() lets staging/capture failures escape, leaks the lock and aermod.inp, and the retained exception deadlocks the next run
- Where: runner.py:413-436 (run), 569-588 (_stage), 629-656 (_prepare); background path is fine (1251-1307).
- What: `_stage` = `_claim` (takes the flock) + `_prepare`. If `_prepare` raises (stale `<stem>.out` that cannot be unlinked: permissions, or a directory; failed symlink and failed copy fallback), `staged` never reaches `run()`, so `_unstage` never runs: the flock stays held by the abandoned handle and any aermod.inp link/copy and `.pyaermod-aermod-inp.sha256` marker stays. Separately the two `open(... .subproc.stdout/.stderr)` calls at 435-436 sit outside the `try`, so a failure there skips `_unstage` too (and a failure on the second open leaks the first handle). The documented contract of run() is "returns an AERMODRunResult"; here it raises.
- Evidence: VERIFIED. r1.py: a directory named `a.out` in the work dir -> `run()` raises PermissionError; with the exception object kept (`except Exception as e: held = e`, as a GUI or batch loop that collects errors does) the traceback keeps the frame, so the lock handle is not garbage-collected, and a second `run()` of any deck in that directory blocks (did not return in 5 s). Without a retained exception CPython's refcounting closes the handle and releases the flock, which is why this looked harmless. r2.py: a directory named `a.subproc.stdout` -> `run()` raises IsADirectoryError and `aermod.inp` symlink is left behind.
- Fix: in `_stage`, wrap `_prepare` in try/except BaseException that calls `_unstage(staged)` (or `_release_dir_lock` when nothing was made) and re-raises or returns a failed AERMODRunResult; in run() move the stdout/stderr opens inside the `try` (or into an ExitStack as `_execute` does). About 8 lines.

### D2 [BUG] [medium, Windows] msvcrt.locking(LK_LOCK) gives up after about 10 s, so a queued run raises instead of waiting
- Where: runner.py:1413-1415 (`_acquire_dir_lock`).
- What: the comment says "blocking LK_LOCK", but CPython/MSVC's LK_LOCK retries once a second for 10 attempts, then raises OSError (EDEADLOCK). A second run in the same working directory behind a run longer than 10 s therefore fails on Windows. The docstring ("Blocks until the lock is available") and the concurrency design (run_batch of decks sharing a dir, parameter_sweep, which docstring says serialise) rely on unbounded blocking. The `except Exception: close; raise` at 1421-1424 then propagates it out of `run()` (see D1) or, in the background path, turns into a failed result.
- Evidence: READ (documented msvcrt behaviour; no Windows host here). Not covered by tests (test_runner_concurrency.py skips on Windows).
- Fix: loop `while True: try: msvcrt.locking(fd, LK_NBLCK, 1); break; except OSError: time.sleep(0.1)`.

### D3 [BUG] [medium] AERSCREEN: success is judged from files an earlier run left behind
- Where: aerscreen_runner.py:405-420 and stage() 269-278 (nothing deletes the old log/output before the run).
- What: `finished` is read from `aerscreen.log` / `<stem>.log` and success needs only `returncode == 0 and finished and output_path is not None`. The runner never removes the previous run's `aerscreen.log`, `AERSCREEN.OUT` (or named output) before starting. In a reused working directory, a run that stops early (AERSCREEN's exit code is 0 after validation errors, per the comment at 414) reports success from the old log and old output, and then `parse_aerscreen_output` parses the old result. The AERMOD runner already solved this (runner.py:631-641 deletes stale outputs in _prepare); the module docstring says "use one per run" but nothing enforces it, and the GUI/CLI reuse directories.
- Evidence: VERIFIED against the runner logic with stand-in binaries (r4.py: first run with a stand-in that writes the log and output, second run with a stand-in that prints an error and writes nothing -> second result `success=True, error_message=None`). Whether real AERSCREEN truncates its log before it can fail is not checked (PLAUSIBLE).
- Fix: before the run, unlink the output, log, `<stem>.log`, max_conc file (via `_written_file`), or accept a file only if `_files_written(work, before)` lists it (the `before` snapshot is already taken at 366). Use the same rule for the restart/max_conc paths.

### D4 [BUG] [medium] AERSURFACE: success is "exit 0 and no 'FATAL' in stdout"
- Where: aersurface_runner.py:200-201.
- What: no positive completion test and no output check. A run that exits 0 after an error not worded "FATAL" (ERROR, an unreadable raster, a bad deck that AERSURFACE reports on stderr) is reported as success; so is a run that wrote nothing. stderr is not examined at all. tests/test_aersurface_runner.py:54-60 shows a stand-in that prints nothing and writes nothing counts as success. Conversely any stdout line that merely contains "fatal" (for example a message-summary line "0 FATAL") would fail a good run (PLAUSIBLE: no recorded AERSURFACE stdout fixture exists to check).
- Evidence: READ. The config already knows the file it asks for: `AERSURFACEConfig.sfcchar_file` (aersurface.py:457).
- Fix: require that `config.sfcchar_file` exists and is in `_files_written(work, before)` (fresh, like AERMOD's rule) in addition to rc 0; keep the FATAL scan as an extra veto and scan stderr too. Record a real run's stdout banner (scripts/record_* exist for AERMOD) and test for it.

### D5 [BUG] [medium] A timeout kills only the direct child; AERSCREEN's AERMOD/MAKEMET/AERMAP children keep running
- Where: aerscreen_runner.py:379-399 (also aermet_runner.py:290-306, aersurface_runner.py:174-192, runner.py:456-464 for symmetry; only AERSCREEN has real children).
- What: `subprocess.run(timeout=)` kills the process it started, not its descendants. AERSCREEN runs `aermod`, `makemet`, `bpipprm`, `aermap` through the shell (module docstring 11-15), so after a timeout the orphaned AERMOD keeps writing into the work dir (and holds CPU for up to the model's runtime) while the caller already got "timed out" and may reuse the directory.
- Evidence: VERIFIED mechanism: r3.py uses a stand-in `aermet` that backgrounds `sleep 30`; after `run_stage(timeout=1)` returns, the child is still alive. For AERSCREEN this is READ (same call, and the children are real).
- Fix: on POSIX start with `start_new_session=True` and on TimeoutExpired `os.killpg(proc.pid, SIGKILL)` (use Popen + wait instead of subprocess.run); on Windows `CREATE_NEW_PROCESS_GROUP` + `taskkill /T`. Best done once in the shared helper proposed in C2.

### D6 [BUG] [low] wasm build cache is keyed only on the glue path
- Where: wasm_runner.py:89, 144-148.
- What: `_cache[str(js)]` never notices a replaced `aermod.js`/`aermod.wasm` at the same path (a rebuild, or `%pip install -U aermod_wasm` in a live JupyterLite kernel): the old module keeps running until the kernel restarts. Two spellings of one path also load the wasm twice (tens of MB).
- Evidence: READ; still present from 11-11.
- Fix: key on `(js.resolve(), js.stat().st_mtime_ns, wasm.stat().st_size)`. 3 lines.

### D7 [BUG] [low] run_batch / parameter_sweep cannot work under Pyodide, even with n_workers=1
- Where: runner.py:952-953 (ProcessPoolExecutor unconditionally), 1827 (BatchRunner calls it).
- What: Pyodide has no processes. `start()` guards this (549-553) and `run()` has a wasm branch, but `run_batch` has no guard and no inline path, though ensemble.run_design documents `n_workers=1` as "every deck in this process".
- Evidence: READ (no Pyodide host).
- Fix: `if n_workers == 1 or wasm_runner.IS_EMSCRIPTEN:` loop `self.run(inp, timeout=timeout)` in this process, honouring stop_on_error, and share the per-result logging with the pool path. About +15 lines, and it also saves the pool start-up for one-deck batches.

### D8 [BUG] [low] AERMET: stale MESSAGES/REPORT files and silent deck overwrite
- Where: aermet_runner.py:316-323, 242-247, 280-287.
- What: (a) the MESSAGES file and REPORT file named in the deck are read if they exist, with no check they were written by this run. A run that dies before opening them re-reports the previous run's messages (a false error list) and previous counts; because `error_count` prefers the summary count (194), a stale `E 0` can also hide an error printed on the screen. Success still needs the fresh screen banner, so the effect is wrong diagnostics and occasionally wrong `error_count`, not a false success. (b) `_deck_argument` copies a deck from outside the work dir to `work/<name>` with `copy2`, silently replacing a different file of that name already there (for example `stage1.inp` written by run_aermet_pipeline). (c) No lock and per-stage capture names (`stage{N}.subproc.stdout`), so two concurrent runs in one work dir clobber each other and `_files_written` credits one run with the other's files. (d) `run_stage` raises for a missing deck (270) and `_deck_argument` ValueError (250) where the AERMOD runner returns a failed result; the stdout/stderr opens at 286-287 leak the first handle if the second fails.
- Evidence: READ.
- Fix: filter reads with `name in _files_written(work, before)`; refuse or rename when the target exists and differs; document one dir per run (or reuse `_acquire_dir_lock`).

### D9 [BUG] [low] Timeouts discard the partial stdout/stderr and return code, in all four runners
- Where: runner.py:751-782 (`_timed_out`), aermet_runner.py:298-306, aerscreen_runner.py:389-399, aersurface_runner.py:182-192.
- What: the capture files are already on disk when the timeout fires, but the timeout result carries `stdout=None`, `stderr=None` (and AERMET/AERSCREEN/AERSURFACE also skip `output_files`). The last lines of output are exactly what says where a long run stuck. For AERMOD the .out is kept (good) but its message summary is not read. The timeout message also embeds `{e}`, the full command line with absolute paths (aermet/aerscreen/aersurface).
- Evidence: READ.
- Fix: read the captures in the shared helper (C2) on every exit path.

### D10 [BUG] [low] AERMODRunner sets the level on, and adds a handler to, the shared module logger
- Where: runner.py:318-330.
- What: `logging.getLogger(__name__)` is "pyaermod.runner", shared by every AERMODRunner. Each constructor calls `setLevel`, so `run_aermod()` (log_level="WARNING") or the batch worker lowers the level for an already-created INFO runner in the same process, and the library adds its own StreamHandler (duplicate lines when the application also configures logging, since records still propagate). The other three runners use a per-class logger name and add no handler.
- Evidence: READ.
- Fix: `logging.getLogger(f"{__name__}.AERMODRunner")`, drop the handler (libraries should not add one); keep `setLevel` only when the caller passes a level. Check tests/test_runner_status.py first for log-capture assumptions.

### D11 [BUG] [low] Background stdout reader stops draining on a sink error
- Where: runner.py:1345-1365.
- What: if `sink.write` raises OSError (disk full, directory removed), the reader exits; AERMOD's stdout pipe then fills and AERMOD blocks until the timeout (default 1 h), with progress frozen. 
- Evidence: READ.
- Fix: on OSError from the sink, keep reading and discard (`sink = None`) so progress and the process continue.

### D12 [BUG] [low] .subproc.stdout/.stderr files are never cleaned; a comment promises attributes that do not exist
- Where: runner.py:430-436, 1254-1255; comment 470-474 (`AERMODRunResult via stdout_file / stderr_file`).
- What: every run leaves `<stem>.subproc.stdout/.stderr` beside the deck (AERMOD can write 100s of MB per the comment at 419-424), and `result.stdout` is cut to the last 1 MB; the "path is preserved on the AERMODRunResult" comment is false (no such fields in AERMODRunResult). Callers cannot find the full log except by guessing the name. The same files are left by the other three runners.
- Evidence: READ.
- Fix: either add `stdout_file`/`stderr_file` to the result (then the comment is true), or delete the files after reading when the result is successful and small.

### D13 [BUG] [low] _error_context reads the whole .out into memory and can quote an unrelated line
- Where: runner.py:866-884.
- What: `f.read()` of a possibly multi-hundred-MB .out (run with no banner and rc 0, i.e. a cut-off run), then reports the first line containing "ERROR"/"FATAL" in upper case, which can be the deck echo (`OU ... ERRORFIL`, a title containing "ERROR") rather than a message. `_read_summary_text` already provides a bounded tail.
- Evidence: READ.
- Fix: scan `_read_summary_text(out)` instead and prefer the parsed messages. Low urgency: only reached when there is neither a parsed fatal nor a signal.

### D14 [BUG] [low] A run that finished before cancel() took effect is reported cancelled/failed
- Where: runner.py:1292-1293, 706-712.
- What: `cancelled=self._cancel_at is not None`; if AERMOD completed successfully in the window between `cancel()` setting `_cancel_at` and the SIGTERM landing (or while the run thread was between `proc.wait` and `_collect`), the result is `success=False, cancelled=True` although the .out is complete. Harmless for users who asked to cancel; mention only because the GUI shows "cancelled" for results that are good.
- Evidence: READ.
- Fix: set `cancelled = cancel requested and returncode != 0` or leave as is and document.

## Concision

### C1 executable discovery is written four times (about 50 lines saved)
- Where: runner.py:332-364 (33 lines), aermet_runner.py:217-230 (14), aerscreen_runner.py:169-196 (28, with `_optional`), aersurface_runner.py:77-91 (15).
- What: each is "explicit path must exist, else try `shutil.which` over three or four spellings, else FileNotFoundError". Differences: AERSCREEN resolves the path; AERMOD's message has install hints and `platform.system()` (the `system` variable and the `platform` import exist only for that message).
- Change: `runner_utils.find_executable(path, names, label, *, resolve=False, hint="") -> Path` (about 15 lines) and one-line calls. Behaviour unchanged if the AERMOD hint text is passed as `hint`. Tests: tests/test_runner.py, test_aermet_runner.py, test_aerscreen_runner.py, test_aersurface_runner.py (not-found messages). Note runner_utils imports from runner today, so put the helper in a new leaf module (see C5) to avoid a cycle.

### C2 the "capture to files, run, handle timeout, read capped" block is written four times (about 60-75 lines saved)
- Where: aermet_runner.py:281-314, aerscreen_runner.py:367-406, aersurface_runner.py:162-199, runner.py:419-476.
- What: identical steps: open two files, `subprocess.run(... stdout=fh, stderr=fh, timeout)`, build a timeout result, close in `finally`, `_read_capped` both. The three non-AERMOD copies are nearly line for line (AERSCREEN adds `env=` and `input=`).
- Change: `run_captured(cmd, cwd, stem, timeout, *, env=None, input=None) -> Tuple[Optional[CompletedProcess], str, str]` returning `None` for the process on timeout, with the opens inside the try, partial output read on every path. This is also the single place to fix D1 (second half), D5 and D9. Tests: the three *_runner test files plus test_runner_pipe.py. The AERMOD run() would call it only for the non-wasm branch.

### C3 three result dataclasses repeat the same ten fields (about 20 lines)
- Where: aermet_runner.py:155-184, aerscreen_runner.py:113-130, aersurface_runner.py:38-54 (and AERMODRunResult for success/input_file/return_code/runtime/stdout/stderr/error_message/start/end).
- What: success, input_file, return_code, runtime_seconds, stdout, stderr, output_files, error_message, start_time, end_time. AERMET and AERSURFACE use `output_files: List[str] = None` + `__post_init__` (aersurface_runner.py:47, 52-54; aermet_runner.py:172, 182-184), which AERSCREEN's `field(default_factory=list)` replaces with no change in behaviour.
- Change: minimum safe step: replace the two `= None` + `__post_init__` hacks with `field(default_factory=list)` (about 8 lines, no API change). A shared base dataclass would also work but changes positional order for AERMET (`stage` sits between), so keep keyword-only users in mind (grep before doing it).

### C4 runner.py has four unrelated jobs in 1,912 lines; clean split points
- 30-226 (about 200 lines): AERMOD message parsing (`AERMODMessage`, `_read_message_summary`, `parse_aermod_messages`, `_severity_count`), already imported on its own by runner_utils.py:28 and by tests.
- 1046-1387 (about 340 lines): AERMODRun, AERMODProgress, `parse_progress_line`, `stop_active_runs`, atexit hook.
- 1587-1828 (about 240 lines): sweep labels, `SweepResults`, `BatchRunner`.
- 1389-1450 (60 lines): lock helpers, with `_Staged`, `_sha256`, `_is_runner_copy` (1464-1503).
- 1853-1912 (60 lines): the `if __name__ == "__main__"` demo; undocumented (grep finds no doc or script that runs `python -m pyaermod.runner`) and superseded by cli.py (cli.py:99). Delete (60 lines).
- Long functions that split cleanly: `run()` 366-511 (146 lines) into `_run_wasm(...)` (442-454, which also removes the nested try) and the capture step (see C2); `run_batch` 888-998 (the nested `_collect` and the "after a stop" loop could be one method returning `results_by_index`).
- How: keep `pyaermod.runner` re-exporting every moved name so `from pyaermod.runner import ...` (api.py:268, ensemble.py:78, tests) is unchanged, but tests that patch `pyaermod.runner.<x>` by string need checking (`grep -rn "pyaermod.runner\." tests`). Net line change about zero; the payoff is readability and removing the runner_utils -> runner import direction.

### C5 aermet/aerscreen/aersurface import private helpers from runner.py
- Where: aermet_runner.py:55, aerscreen_runner.py:60, aersurface_runner.py:35 (`_dir_state`, `_files_written`, `_read_capped`), terrain.py:522 (`_read_capped`).
- What: four modules depend on underscore names of the AERMOD runner. Moving `_read_capped`, `_FileState`, `_dir_state`, `_files_written` (runner.py:1525-1584, 1567-1584, about 60 lines) and the new C1/C2 helpers to one leaf module (for instance `_proc.py`) lets runner.py re-import them and removes the cross-dependency. No behaviour change; tests import `_read_capped` from pyaermod.runner (test_runner_pipe.py:19), which the re-export keeps working.

### C6 NADCON grid staging exists twice
- Where: aerscreen_runner.py:286-305 and aersurface_runner.py:93-119.
- What: both copy `*.las`/`*.los` into the work dir; AERSURFACE matches `*.la[s]` (case-sensitive; equivalent to `*.las`), AERSCREEN uses `suffix.lower()`, so an upper-case `CONUS.LAS` is staged by one and ignored by the other.
- Change: one `stage_nadcon_grids(src_dir, work) -> int` helper with the case-insensitive match (about 12 lines saved, and fixes the inconsistency).

### C7 AERMOD's `_stage` wrapper, `_claim`, `_prepare`, `_unstage` indirection
- Where: runner.py:569-588.
- What: `_stage` exists only for run(); `_execute` uses `_claim` and `_prepare` separately. Once D1 is fixed `_stage` is the right place for the try/except, so keep it; no removal recommended. Listed so nobody deletes it.

## Dead code (grep of src/ and tests/ done)
- runner_utils.py:39 `_AERMOD_FATAL` regex: defined, never used anywhere in src/ or tests/. Delete (1 line, and `re` is still used by `_AERMET_ERR_LINE`).
- runner.py:1128 `_stop_active_runs = atexit.register(...)`: only a test reads it (tests/test_runner_background.py:294 calls `runner_module._stop_active_runs()`), where `stop_active_runs()` would do. Keep the register, drop the assignment and fix the test, or leave: trivial.
- `ERRMSGInfo.has_fatal` (runner_utils.py:50-52): used only by a test; harmless public surface, not worth removing.
- `stdin_text(mode)` raising ValueError for any other mode (aerscreen_runner.py:218) is reachable only through `run(mode=...)`; fine.
- versions.py: `is_validated_aermet_version` is used only by its own test and `__all__` (public API, keep). Nothing else dead in versions.py or wasm_runner.py.
- runner.py:1000-1043 `validate_input` is used by the `__main__` demo and tests only (grep: no src caller besides it). It is public API (README/docs do not mention it); if the `__main__` block goes, it has no internal caller. Not a removal candidate without a deprecation decision; also note that it checks plain substrings (`'CO STARTING' in content`), so a commented-out line satisfies it. I checked whether multiple spaces should be accepted: they should not (setup.f DEFINE puts the pathway and keyword at fixed columns), so that is not a bug.

## Checked and fine
- AERMOD `_read_message_summary` banner/summary logic and `_collect` success rule; stale-output deletion in `_prepare`; `_claim` refusing another deck named aermod.inp.
- AERMODRun lifecycle: cancel before start returns without staging (1264-1266, one lock hold from the cancel check to Popen); cancel after start terminates, escalates to kill after CANCEL_GRACE_SECONDS; `finally: _kill()` always waits for the process (no zombie); the reader thread is joined; the atexit hook kills live runs. `cancel()` calls `terminate()` outside the lock, but Popen.terminate re-polls first so it cannot signal a recycled pid.
- run(): subprocess.run kills AERMOD on KeyboardInterrupt too (no orphan for AERMOD itself).
- Paths with spaces: all runners pass argument lists, never a shell string; the AERSCREEN BPIP wrapper quotes `"{real}"`, `"$1"`, `"$@"`. One residual: AERSCREEN prepends the work dir to PATH with `os.pathsep`, which breaks if the work dir itself contains `:` (POSIX) or `;` (Windows) (aerscreen_runner.py:362). Low, not worth a fix beyond a clear error.
- Encoding: AERMOD outputs are read as latin-1 everywhere that matters; captured stdout/stderr are read as UTF-8 with replacement (`_read_capped`), which only affects non-ASCII console text.
- Windows signals: `_describe_signal` handles only negative POSIX return codes; a Windows crash shows as a large positive code and falls to the generic "failed with return code N" message. Cosmetic.
