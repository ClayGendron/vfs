# 114 — Engine-leg harness reentrancy: per-run table namespaces

- **Status: all slices landed 2026-08-18.** §1: both
  `_server_storage` fixtures mint `vfs_<uuid4-hex10>` per run, pass
  it to `DatabaseStorage(table_name=...)`, and invert the lifecycle —
  no setup drop, teardown drops exactly the minted metadata after
  close (advisory-lock isolation follows free: the key derives from
  the table name). §2: the traps were three, not two — the audit
  cast SQL became `{content}` templates formatted from the minted
  content table; the four rival handles in `test_races.py` join the
  namespace via the new `_sibling` helper; and the encoded-kind
  index reflection (found while in the file) hardcoded `"vfs"` /
  `"ix_vfs_encoded_kind"` *and* reflected after teardown — it now
  reflects the minted names inside the namespace's lifetime. The
  conformance module docstring's drop-before-run posture rewritten
  to match. §3: reentrancy posture recorded in the db_test skill
  and `docker/README.md` (concurrent runs supported; crashed-run
  `vfs_*` residue cleared by `compose down`). §4: the lead's
  collision shape replayed against the new fixture on a shared
  sqlite file — run A survives run B's full lifecycle, namespaces
  disjoint — and the live gate: two concurrent `pytest -m postgres`
  processes against one engine, both green at 209 (the exact shape
  that produced the review's spurious red). All four legs green
  sequentially at their prior counts (Postgres 209, MySQL 210,
  MSSQL 211, Oracle 208); zero relations left on the server after
  teardown; full 3.13 CI leg green.
  **Mined 2026-08-19:** the reentrancy posture flowed to `standards/testing.md` (per-run `vfs_<hex>` namespaces, minted names everywhere); the db_test skill and `docker/README.md` were updated at landing. No ADR — harness only. Folder stays as the historical record.
- **Drafted 2026-08-18.**
  Born from the remediation-landing review
  (`../../../research/2026-08-18-remediation-landing-review.md`),
  lead L4 — confirmed minor. A run-1 verifier hit the failure live
  (`relation "vfs" does not exist` mid-write, gone on retry) while
  review agents shared the standing Docker stack; the run-2 skeptic
  reproduced the collision deterministically and surveyed every
  fixture.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** test-harness only. No production code changes; no
  behavior change for a serialized run. The goal is that two
  concurrent test runs (or review agents) sharing one live engine
  never tear each other down.
- **Depends on:** nothing in the active line.
- **Relates to:** the db_test skill and `docker/README.md` (their
  concurrency posture should state whatever this spec lands), the
  code_review workflow (whose agents are the most frequent
  concurrent consumers of a shared stack), spec 113 (touches the
  same conformance file — land in either order, the seams are
  disjoint).

## Intent

**Both engine-leg fixture families are non-reentrant by
construction.** `tests/storage/database/test_races.py::
_server_storage` and `tests/storage/test_conformance.py::
_server_storage` — the only consumers of `VFS_TEST_<ENGINE>_URL` —
unconditionally `drop_all` the fixed `table_name="vfs"` metadata
against the shared server at setup, and every `DatabaseStorage` they
open (plus the extra rival instances in `test_races.py`) defaults to
the same `"vfs"` namespace. Two concurrent runs against the same
engine URL deterministically collide: run B's setup drops run A's
tables mid-flight, and run A fails with `vfs.unavailable` /
"no such table" errors. Demonstrated on a shared sqlite file
database; observed live on Postgres during the review.

Bounding the severity: CI is safe (each engine is its own serialized
matrix job on its own runner), a single local run is safe, and the
failure mode is loud spurious reds — never a silent pass. What it
costs is exactly the workflow this project runs daily: concurrent
review agents sharing the standing `db_test` stack, and any two
terminals running the same leg.

Laws that bind the work:

1. **Isolation by namespace, not by luck.** Each harness run mints
   its own table namespace; concurrent runs against one engine URL
   are fully independent — tables, advisory locks, teardown.
2. **Teardown drops what setup minted, nothing else.** The fixed
   `drop_all`-at-setup pattern inverts: setup creates the minted
   namespace, teardown drops it. A crashed run may leave its minted
   tables behind; that is acceptable residue on an ephemeral-data
   stack (the containers are tmpfs), never a correctness issue.
3. **The sqlite legs are untouched.** Memory and file-backed sqlite
   runs are per-process already; only the `VFS_TEST_<ENGINE>_URL`
   fixtures change.

## Shape

- **§1 Minted names.** Both `_server_storage` fixtures mint a
  per-run table name (short, collision-safe — e.g. seeded from the
  ULID module the codebase already carries) and pass it both to
  `build_vfs_tables` for setup/teardown and to every
  `DatabaseStorage(table_name=...)` they construct. Advisory-lock
  isolation follows for free: `advisory_key` derives from
  `table_name`.
- **§2 The two known traps** (from the skeptic's survey, both must
  land with §1 or the fix is worse than the disease):
  - the three raw-SQL content audits in the conformance file
    hardcode `FROM vfs_content` — they interpolate the minted name;
  - the rival `DatabaseStorage` instances `test_races.py` opens
    beside the fixture must receive the same minted name, or the
    races silently stop racing the fixture's tables.
- **§3 The record.** The db_test skill and `docker/README.md` state
  the new posture: engine legs are reentrant; concurrent runs are
  supported; leftover `vfs_*` namespaces on a long-lived stack are
  residue a fresh `compose down` clears.
- **§4 The gate.** Two concurrent executions of the same engine leg
  against one live engine, both green — the shape that failed during
  the review. One engine is sufficient as the demonstration venue
  (Postgres, where the collision was observed); the mechanism is
  engine-independent.

## Slices

- **A.** §1–§2 with the sqlite-file collision repro shown fixed and
  the full conformance + races legs green on sqlite.
- **B.** §3–§4: the concurrent-run gate on live Postgres, docs
  trued, spec status updated.

## Open questions

- **The cheap alternative** — documenting a single-runner-per-engine
  constraint at both fixtures and in the db_test skill instead of
  minting names — was considered and not chosen as the default: the
  constraint is invisible exactly when it bites (concurrent review
  agents), and the minted-name fix is small. If slice A uncovers
  hidden fixed-name couplings beyond §2's two, revisit.
