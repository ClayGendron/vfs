# 079 — Guarded updates attribute success from the statement, not the post-image

- **Status:** landed 2026-07-23. Regression pin ran red on real MSSQL at
  READ COMMITTED against the shipped code, green after; all four Docker
  legs pass. Execution record and pin amendments in `plan.md`.
- **Amendment (2026-07-23):** pin 2's premise that `dialect.update_returning`
  suffices for the set-based arm is false on SQLite — it declares the
  flag yet rejects SQLAlchemy's column-aliased `(VALUES ...) AS name (...)`
  join source. SQLAlchemy models no capability for that, so the arm is
  additionally gated by a declared `DialectProfile.values_join` bit
  (true: postgresql, mssql), per the house rule that a profile field
  covers exactly what SQLAlchemy takes no position on. Pin 3 gained an
  aggregate fast rung above the per-row floor: where
  `dialect.supports_sane_multi_rowcount` holds, one guarded executemany
  under a savepoint proves all-matched by aggregate count, and only a
  mismatch re-drives per-row.
- **Evidence:** `context/open-questions.md` — "Guarded-update read-back
  infers success from the post-image". Prior art verified first-hand in
  SQLAlchemy, jackrabbit-oak, and juicefs; cited per pin below.
- **Depends on:** spec 078 (the `persistence` rename) landed
  2026-07-22 — this spec is written in that vocabulary.

## Problem

`_update_materials` distrusts per-driver executemany rowcounts, which is
correct — pyodbc, the MSSQL driver, declares
`supports_sane_multi_rowcount = False`
(`sqlalchemy/lib/sqlalchemy/connectors/pyodbc.py:39`), and asyncpg does
the same (`dialects/postgresql/asyncpg.py:1083`). But the substitute it
chose — re-reading the rows and inferring success from the post-image
(`writes.py:529`) — cannot distinguish *our* write from a rival's,
because versions are per-entry counters that any writer advances by one.

**The failure, in statement order, on an engine at READ COMMITTED:**

1. `_fetch_committed` reads version N; staging mints `base=N,
   version=N+1`.
2. A rival commits from the same base. The row is now at N+1, holding
   the rival's material.
3. Our guarded `UPDATE ... WHERE version = N` matches zero rows and
   raises nothing.
4. The read-back observes N+1, compares it to our intended
   `staged.version` of N+1, and concludes we won.
5. `_replace_content` deletes the rival's content row and inserts our
   body. The batch commits and reports success.

Two properties make this worse than the entry's original framing:

- **It needs no precise interleave.** The trigger is one rival
  committing anywhere in the window the guard exists to police, with a
  single increment — the *common* conflict, not the edge. The check
  catches only the rarer two-plus-increment and deletion cases, so its
  detection is inverted from likelihood.
- **The result is a torn row, not a lost update.** The entry row keeps
  the rival's `content_hash`, `size_bytes`, `mime_type`, `owner_id`,
  `updated_at`; the content table holds our body. `content_hash` no
  longer hashes the content — a corrupted invariant that survives the
  transaction and is invisible to every later reader.

**Exposure.** Engines whose op sessions run at READ COMMITTED: the MSSQL
profile and the GENERIC floor, which carry no `op_isolation` pin
(`dialects.py:94-108`). *Not* Postgres (pinned REPEATABLE READ,
`dialects.py:90`, rivals surface as 40001) and *not* SQLite (single
writer; `BEGIN IMMEDIATE` precedes the snapshot read, `engine.py:358`).
Both exposed profiles are declared production surfaces.

**The canon attributes from the statement, never from a re-read.** No
system examined infers success from a post-image:

- **SQLAlchemy** refuses executemany outright when a version guard must
  be verified — `orm/persistence.py:843`:
  `allow_executemany = not return_defaults and not needs_version_id` —
  then drives rows individually checking per-statement `rowcount`
  (`:877-907`) and raises `StaleDataError` on mismatch (`:950-956`).
  Where even rowcount is unreliable it *warns* that "versioning cannot
  be verified" (`:958-963`) rather than guessing.
- **jackrabbit-oak's RDB store** — the closest architectural cousin,
  batching conditional updates over a generic-JDBC floor spanning
  DB2/Oracle/MSSQL/Postgres — issues
  `update ... where ID = ? and MODCOUNT = ?`
  (`RDBDocumentStoreJDBC.java:340`) and attributes from JDBC per-element
  batch counts (`:406-411`), single-row path at `:128-132`.
- **juicefs** converts zero affected-rows into a retryable `EBUSY`
  (`pkg/meta/sql.go:1926-1931`, classified at `:1198-1202`).

## Scope

Replace post-image inference with statement-native attribution, and
delete the read-back's role as success oracle. The guarded arm learns
which rows *its own statement* touched.

**Untouched:** the unguarded (`"absorb"`) arm's SQL-side
`version = version + 1`, last-writer-wins by design; the insert pass and
both arbitration modes; `_replace_content` and `_bump_parents`; the
staging plan; the results envelope and every `Observation`.

## Pins

1. **Capability-driven, not hardcoded.** The strategy is selected from
   what SQLAlchemy already models on the live dialect —
   `dialect.update_returning` and `dialect.supports_sane_rowcount` —
   never from a `DialectProfile` constant. Per CLAUDE.md, a profile
   field is justified only for a decision SQLAlchemy takes no position
   on; it takes a position on both of these.
2. **Preferred arm — RETURNING.** Where `dialect.update_returning` is
   true (Postgres `postgresql/base.py:3478`, SQLite
   `sqlite/base.py:2125`, MSSQL `mssql/base.py:3085`, which compiles it
   as `OUTPUT inserted.*`), the guarded update runs set-based over a
   `VALUES` join and returns the `entry_id` of every row it actually
   matched. Success is exactly membership in the returned set; a staged
   entry absent from it lost arbitration and classifies `conflict`.
3. **Floor arm — per-row with sane rowcount.** Where RETURNING is
   unavailable but `dialect.supports_sane_rowcount` holds, execute the
   guarded update one row at a time and attribute from each statement's
   own `rowcount`; zero means conflict. This is SQLAlchemy's own choice
   in the same situation, and it is bounded — one row per statement, so
   the no-unbounded-statement rule is satisfied trivially.
4. **Neither available — classify, do not guess.** If a dialect offers
   neither RETURNING nor sane single-row rowcount, the guarded arm
   raises a classified error rather than proceeding on an unverifiable
   write. Silent best-effort is what this spec exists to remove.
5. **Chunking is preserved on the RETURNING arm.** The `VALUES` join
   carries one tuple per staged entry and is chunked by
   `membership_budget(profile, parameter_budget)` exactly as today's
   membership predicates are; results merge across chunks. A 10,000-
   entry batch stays batch-native with per-row attribution.
6. **The read-back is deleted, not repurposed.** `writes.py:522-525`
   goes. Its one legitimate remaining job — letting an `"absorb"` entry
   learn the version the database assigned it — moves onto the
   unguarded arm, which can return it directly on the RETURNING arm or
   read only its own ids on the floor arm. No statement re-reads a row
   to decide whether the preceding statement worked.
7. **Docstring correction.** `_update_materials`' claim that the
   read-back "attributes conflicts portably instead of trusting
   per-driver executemany rowcounts" (`writes.py:499-502`) is false as
   written — it attributes them *unsoundly*. The rewritten docstring
   states the ladder and why each rung is chosen.

## Acceptance criteria

- **The regression test, and the reason this spec exists:** two
  concurrent writers against the same entry at READ COMMITTED, the rival
  committing between the snapshot read and the guarded update, with the
  rival advancing the version by exactly one. The batch must fail with
  `conflict`; the entry row and the content row must agree afterwards
  (`content_hash` hashes the stored content). Run on an engine that
  reaches READ COMMITTED naturally — the MSSQL profile or the GENERIC
  floor, **not** Postgres, which would have to force isolation
  artificially and would prove nothing about the shipped pin.
- No code path concludes a guarded update succeeded without evidence
  from the statement that performed it; `grep` shows no re-read of
  `entry.c.version` in `_update_materials`.
- Statement count and parameter count stay bounded on the RETURNING arm
  at a 10,000-entry batch; the floor arm's per-row cost is measured and
  recorded in `plan.md` rather than assumed negligible.
- Behavior unchanged where no conflict occurs: identical observations,
  identical versions, identical `Observation.status` values.
- Suite green; `ruff`/`ty` at zero.

## Alternatives considered

- **Per-write token (writer id or ULID stamp) compared alongside the
  version.** Sound, and idiomatic after ADR 019, but it keeps the
  re-read and adds a column to carry information the statement can
  already report. Promote to primary only if pin 2's set-based
  RETURNING proves unusable on a tuned profile — e.g. an MSSQL `OUTPUT`
  restriction in the presence of triggers.
- **Return the pre-image instead of the post-image.** Fixes soundness
  but still spends a second statement to learn what the first one knew.
- **Pin isolation on the exposed engines** (mirror the Postgres
  REPEATABLE READ pin for MSSQL and GENERIC). Narrows the window rather
  than attributing correctly, and pins isolation for every op to fix one
  arm. Worth doing on its own merits; not a substitute.
- **Lock the update targets in the snapshot read** (`FOR UPDATE` /
  `UPDLOCK`). Correct, but converts an optimistic pipeline into a
  pessimistic one and holds locks across the whole staging pass.
- **Prove it unreachable.** Considered and rejected: the statement-order
  argument above establishes reachability without a test.

## Ordering

Stage 1: the RETURNING arm plus capability selection, with the
regression test written first and failing. Stage 2: the floor arm and
the classify-rather-than-guess rung. Stage 3: delete the read-back,
rewrite the docstring, and move the `"absorb"` version learning.
`plan.md` at execution time per house convention.
