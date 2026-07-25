# Turso as the in-memory backend engine — feasibility facts

- **Status:** complete (session-scoped fact-finding, local checkout)
- **Date:** 2026-07-25
- **Owner:** Clay Gendron (gathered by Claude in session)
- **Question:** Can the bespoke `memory.py` backend be retired in favor
  of `DatabaseStorage` over an in-process, in-memory SQL engine —
  specifically Turso (`tursodatabase/turso`)? Prompted by ADR 027
  pin 5: the universal delete-never-destroys contract forces every
  backend to hold the trash arc, and hand-rolling that arc in
  `memory.py` would duplicate the hardest semantics in the tree.

All facts below were read from the local reference checkout
`~/Git/Repos/turso` (read-only prior-art study; no code copied).

## Verified facts

- **License: MIT** (`LICENSE.md`) — permissive, keeps the clone
  lawful under the house license rule.
- **What it is:** a from-scratch SQLite reimplementation in Rust —
  SQLite query language and file format, validated by differential
  testing against SQLite and the SQLite TCL suite (`COMPAT.md`).
- **Maturity: explicitly BETA.** The Python bindings README leads
  with a warning: "This software is in BETA. It may still contain
  bugs and unexpected behavior." (`bindings/python/README.md`).
- **Python bindings: `pyturso`.** DB-API 2.0 (`turso.connect`), a
  native asyncio module (`turso.aio.connect`), `:memory:` databases,
  cross-platform (`bindings/python/README.md`).
- **SQLAlchemy dialect: implemented and shipped.**
  `pyturso[sqlalchemy]` registers three dialects —
  `sqlite+turso://`, **`sqlite+aioturso://`** (async), and
  `sqlite+turso_sync://` (remote sync)
  (`bindings/python/SQLALCHEMY_DIALECT.md`). Registration under the
  `sqlite` dialect family means SQLAlchemy reports
  `dialect.name == "sqlite"` — vfs's existing profile resolution and
  the sqlite `DialectProfile` would apply as-is.
- **SQL surface vfs needs (per `COMPAT.md` statement tables):**
  `SAVEPOINT` / `RELEASE SAVEPOINT` ✅ (required by `begin_nested`
  in `_TrashChain._mint`, provisioning arbitration, and staging);
  `RETURNING` ✅ (required by the guarded-update write arm);
  `BEGIN TRANSACTION` ✅. Query language is "partially supported"
  overall — full statement-by-statement tables in `COMPAT.md`.
- **Multi-process caveat:** "We don't support mixed SQLite and Turso
  in multi-process scenarios" (`COMPAT.md` Guarantees §4). Irrelevant
  for a single-process in-memory role; binding for any idea of
  pointing Turso at shared sqlite files.

## Open validation items (gate for any adopting spec)

1. **`BEGIN IMMEDIATE`** — not listed in the COMPAT statement table
   (only `BEGIN TRANSACTION`). vfs's sqlite serialization arm is a
   begin-listener that issues `BEGIN IMMEDIATE` on writer
   connections (`engine.py`). Verify the statement parses and locks
   as in SQLite, or shim the listener for the turso driver.
2. **`:memory:` across pooled connections** — in SQLite, each
   connection to `:memory:` gets a private database; SQLAlchemy's
   stock answer is `StaticPool` (one shared connection). Verify what
   `sqlite+aioturso:///:memory:` does under the async pool, and what
   pool posture the dialect expects. A single-connection pool would
   serialize all access — acceptable for dev/test, but it must be a
   known property, not a surprise.
3. **PRAGMA `file_settings`** — the sqlite profile applies WAL and
   page-size pragmas at startup; an in-memory database wants neither.
   Verify pragma handling (COMPAT has a PRAGMA section) and whether
   the profile needs a turso-specific `file_settings` variant.
4. **`insertmanyvalues`** — bulk-insert chunking reads
   `dialect.insertmanyvalues_max_parameters` off the live dialect;
   verify the turso dialects inherit sane values from the sqlite
   base dialect.
5. **Suite speed** — the in-memory backend is the default test
   fixture; dict operations become SQL round-trips. Measure the full
   suite before/after; a large regression is a real cost even if
   everything passes.
6. **Beta behavior under the conformance suite** — the decisive
   test: run the entire `tests/` conformance surface on
   `sqlite+aioturso:///:memory:` and triage divergences.

## Fallback

If any item above surfaces a blocker, the same re-platforming works
today over stock `sqlite+aiosqlite:///:memory:` (StaticPool) with
zero new dependencies — the architectural decision (retire
`memory.py`, one storage implementation) does not depend on which
in-process engine wins. Turso can be re-attempted as it matures.
