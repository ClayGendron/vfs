# Test suite, slice by slice, 2026-10-10

Raw material behind the memo
`../../2026-10-10-the-test-suite-slice-by-slice.md`. Five investigations
ran in parallel at commit `76ce536`, one per slice of the 2026-10-08
breakdown, each measuring every strategy before/after on the real tests
(temporary edits restored by copy). One subdirectory per slice.

- `ranking/` — phase timers around one harness test (`profile_phases.py`,
  `profile_glean.py`), the dead-lever probes (`measure_misc.py`), the two
  measured variants of the module (`test_harness_A.py` module-scoped
  corpora, `test_harness_A2.py` one mount per embedder) and their
  `--durations=0` logs against three baselines.
- `conformance/` — a timing plugin (`plugin/`) that wraps first touch,
  `create_all`, every verb and a cursor statement counter; the paired A/B
  drivers (`ab.sh`, `ab2.sh`) and summaries; the measured drop-ins
  (`test_conformance.py.template` = per-session template DB,
  `engine.py.skipcreate` = skip `create_all` when the meta table exists).
- `rights/` — statement-counting plugin, replay/question profilers, the
  edit scripts that produced each measured variant (clauses fold, road
  fold, oracle memo), and suite-wide mount/statement counts
  (`suite_counts.txt`).
- `dbrest/` — mount-open counter and sleep spy (`plug/`), micro-benches for
  open, checkfirst, 10k batch size, pattern fan and `synchronous`, and
  the measured template-URL helper (`database_helpers.template.py`).
- `tail/` — collection and import-time logs, the GC/retention plugin and
  referrer walk that found the `_BULK_STATEMENTS` leak, the phase plugin,
  and the module-scoped-worlds drivers.
- `xdist*.log`, `xdist-scaling*.log` — whole-suite runs under
  `pytest-xdist` (10 workers loaded and quiet, 16, 20, work-stealing) and
  the 1/5/10-worker scaling probe with CPU accounting.

Reproduce a whole-suite xdist run without adding the dependency:

```sh
uv run --with pytest-xdist pytest -q -p no:cov -n auto
```

Slice scripts assume the repo root as cwd and the project venv; most take
no arguments and print to stdout. Variants ending in `.template`,
`.skipcreate`, `_A.py` are drop-in replacements for the file they are
named after and were measured by copying them over it, then restoring.
