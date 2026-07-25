# 028. The In-Memory Backend Is the Database Backend over Turso

- **Status:** accepted
- **Date:** 2026-07-25
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay chose the re-platform and the Turso
  engine in session, reviewing the ADR 027 pin-5 execution options;
  feasibility facts gathered same session —
  `research/2026-07-25-turso-in-memory-backend.md`)

## Context

ADR 027 pin 5 makes recoverable delete a universal contract: every
served backend must hold the trash arc (delete-to-trash, restore,
sweep). The bespoke `memory.py` backend holds none of it — deletes
are permanent, restore and sweep classify `unsupported` — so the pin
demands either building the arc there by hand or removing the reason
it is missing.

The hand-rolled path is expensive in exactly the wrong place:
`memory.py` exists as a fast in-process default for dev and tests,
yet it mirrors the database backend's refusal ladders line for line
("memory parity" runs through `topology.py`'s docstrings). Every new
verb is written twice, and the trash arc — bucket minting,
self-describing names, restore resolution, retention sweep — is the
hardest semantics in the tree to keep aligned. Meanwhile the
in-memory role has no requirement the database backend cannot meet,
if an in-process, in-memory SQL engine can carry it.

The feasibility pass (research memo above) found Turso —
`tursodatabase/turso`, the Rust SQLite reimplementation, already a
house reference repo — MIT-licensed, in-process, `:memory:`-capable,
with DB-API 2.0 + asyncio Python bindings (`pyturso`) and a shipped
SQLAlchemy dialect family registered under the `sqlite` name
(`sqlite+aioturso://`), meaning vfs's existing sqlite
`DialectProfile` resolution applies unchanged. `SAVEPOINT` and
`RETURNING` — the two SQL features vfs's write and topology arms
cannot live without — are listed supported. The bindings are
explicitly **beta**, and six validation items are recorded in the
memo (`BEGIN IMMEDIATE`, pooled `:memory:` semantics, pragma
handling, `insertmanyvalues`, suite speed, full-conformance triage).

## Options considered

- **(a) Hand-roll the trash arc in `memory.py`** — keeps the
  zero-dependency default, but duplicates the tree's hardest
  semantics into a second implementation that exists to be fast, and
  doubles the maintenance of every future verb. The "semantic
  reference" framing inverts once the database backend is the richer
  implementation. Rejected.
- **(b) Re-platform onto stock in-memory SQLite
  (`sqlite+aiosqlite:///:memory:`, StaticPool)** — the same
  architectural win with zero new dependencies, available today;
  single-shared-connection pooling is the known cost. Not chosen as
  the target, but **retained as the fallback arm** if Turso's beta
  gate fails.
- **(c) Re-platform onto Turso (`sqlite+aioturso:///:memory:`)
  (chosen)** — same architectural win, plus a maintained asyncio
  driver, a dialect built for async engines, and alignment with a
  reference project the house already studies. Cost: a beta
  dependency, gated by validation before it becomes load-bearing.

## Decision

Four pins:

1. **`memory.py` retires.** The in-memory role — dev default, test
   fixture, zero-infrastructure storage — is served by
   `DatabaseStorage` over an in-process, in-memory SQL engine. One
   storage implementation, one semantics; the conformance suite
   replaces "memory parity" as the contract language, and the
   parity wording in docstrings retires with the backend.
2. **The engine is Turso.** `pyturso[sqlalchemy]`,
   `sqlite+aioturso:///:memory:`. The dialect registers under the
   `sqlite` family, so profile resolution, the serialization arm,
   and budget facts read off the live dialect as they do for sqlite;
   a turso-stamped `DialectProfile` variant is added only where
   verified divergence demands it (expected: `file_settings`, since
   an in-memory database wants no WAL or page-size pragmas).
3. **Adoption is validation-gated, and the gate has a fallback.**
   The six research-memo items are the gate; the decisive check is
   the full conformance suite on the Turso engine. If a blocker
   survives triage, the implementing spec lands option (b) —
   aiosqlite in-memory — under the same architecture, files the
   upstream issues, and Turso is re-attempted as it matures. The
   re-platform decision (pin 1) stands regardless of which engine
   clears the gate first.
4. **Single-process is the declared posture.** An in-memory database
   is per-process by nature, and Turso's own guarantees exclude
   mixed SQLite/Turso multi-process use. The in-memory storage is
   for dev, tests, and embedded single-process serving — production
   multi-process deployments remain on the server engines, per the
   production posture.

## Consequences

- **Easier:** the trash arc — and every verb after it — is written
  once; ADR 027's spec 084 shrinks from "reimplement the hardest
  semantics" to "swap the engine under the existing implementation";
  the conformance suite's `@needs("restore")`/`@needs("sweep")`
  carve-outs retire; dev-default behavior and production behavior
  converge to the same code path, so dev catches real bugs.
- **Harder:** a beta dependency sits under the default dev
  experience (mitigated by the gate and the aiosqlite fallback arm);
  test-suite speed is at risk — dict operations become SQL
  round-trips — and the before/after measurement is a gate item, not
  an afterthought; pooled `:memory:` semantics may serialize
  concurrent access on the in-memory leg (acceptable for its
  declared posture, but it must be verified and documented);
  concurrency seams that relied on the memory backend's determinism
  move to the database backend's seam machinery.
- **Committed to:** spec 084 executes the re-platform behind the
  validation gate (and owns the fallback arm); spec 085 (the ADR 027
  contract flip) then touches a single storage implementation;
  `memory.py`, its tests, and the parity docstring language are
  deleted, not preserved.

Evidence: `research/2026-07-25-turso-in-memory-backend.md` (all
facts and the six-item gate);
`context/decisions/027-delete-never-destroys-sweep-only-destruction.md`
(pin 5, the forcing contract); `COMPAT.md` and
`bindings/python/SQLALCHEMY_DIALECT.md` in the `turso` reference
checkout. Executes ADR 027 pin 5. ADR 001 (storage as a held object
behind the protocol) is untouched — it pins the composition
contract, not `memory.py`'s existence; its "in-memory backend"
mentions are illustrative, and partial backends remain the declared
normal case. Supersedes no numbered ADR.
