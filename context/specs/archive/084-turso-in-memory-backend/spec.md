# 084 — Re-platform the in-memory backend onto Turso

- **Status:** landed 2026-07-25 (`b16c38b`, one landing with spec 085;
  review minors `8fcd590`) — born 2026-07-25 from ADR 028. Landed
  **with** the ADR 027 contract flip: once delete can never be
  permanent, a backend without trash cannot delete at all, so the
  bespoke no-trash `memory.py` left in the same commit that flipped
  the contract, keeping the landing green. Awaiting the backward-flow
  mining pass, then deletion.
- **Evidence:**
  `context/decisions/028-turso-in-memory-backend.md`;
  `context/decisions/027-delete-never-destroys-sweep-only-destruction.md`
  (pin 5); `context/research/2026-07-25-turso-in-memory-backend.md`
  (the validation gate's six items).
- **Depends on:** nothing open — the database backend's verb surface
  (specs 072/081/082/083) is landed.

## Problem

ADR 027 makes recoverable delete universal; `memory.py` cannot
express it and would need the tree's hardest semantics duplicated by
hand to comply. ADR 028 resolves the fork: retire the bespoke
backend and serve the in-memory role with `DatabaseStorage` over
Turso (`sqlite+aioturso:///:memory:`), one implementation carrying
every verb. This spec executes that swap.

## Decisions this spec owns

1. **The validation gate runs first and is its own landing.** A
   scripted probe (kept in the repo, runnable on demand) plus a full
   conformance-suite run on `sqlite+aioturso:///:memory:` settles
   the six memo items: `BEGIN IMMEDIATE` under the writer listener,
   pooled `:memory:` semantics (which pool class the dialect needs,
   and whether access serializes), pragma/`file_settings` handling,
   `insertmanyvalues` values, suite wall-clock before/after, and
   divergence triage. **Gate outcome decides the arm:** pass →
   Turso; blocker → the fallback arm
   (`sqlite+aiosqlite:///:memory:` + `StaticPool`) lands under the
   identical architecture, upstream issues are filed, and the Turso
   swap becomes a follow-up story. Everything below is arm-agnostic
   except the dependency line.
2. **Dependency and wiring.** `pyturso[sqlalchemy]` joins project
   dependencies (fallback arm: no new dependency). The default
   in-memory storage — wherever `MemoryStorage` is constructed today
   (dev default, test fixtures) — becomes a `DatabaseStorage` on the
   in-memory URL. Profile resolution stays sqlite-family; a
   turso-stamped `DialectProfile` variant is added only for verified
   divergence, expected only in `file_settings` (an in-memory
   database wants no WAL or page-size pragmas — likely a shared
   need with the fallback arm).
3. **The bespoke implementation is deleted; the names survive as
   thin subclasses.** The 842-line dict-based backend, its direct
   tests, and its conformance carve-outs go. In their place, two
   construction-only subclasses (decided 2026-07-25, Clay in
   session): `TursoStorage(DatabaseStorage)` pins the Turso dialect
   and URL construction; `InMemoryStorage(TursoStorage)` pins
   `:memory:` and its pool posture — keeping the `VFS()` default
   readable and existing call sites compiling. On the fallback arm,
   `TursoStorage` is *not* created (no named class over an engine
   that failed its gate); `InMemoryStorage` subclasses
   `DatabaseStorage` directly over aiosqlite until Turso clears.
   The `@needs("restore")` / `@needs("sweep")` gates retire — the
   in-memory leg now declares `DatabaseStorage`'s landed capability
   set, so the trash-arc conformance families run on it beside
   sqlite-file and the four engine legs. `grep` and `mkedge` remain
   classified stubs on that set, so their conformance rows now skip
   on the in-memory leg until those passes land.
4. **"Memory parity" language retires with the backend.** Docstrings
   that cite the memory backend as the semantic reference
   (`topology.py`'s "mirroring the memory backend's ladder",
   "memory parity hard-deletes", and kin) are reworded to name the
   conformance contract itself as the authority. No behavior
   changes — this is the reference role formally moving to the
   suite.
5. **Concurrency posture is documented where it bites.** If the gate
   finds that the in-memory pool serializes access
   (single-connection `:memory:`), that property is recorded in the
   storage docstring and the seam-based concurrency tests keep
   running on the engine legs where rivals are real, not on the
   in-memory leg.

## Acceptance criteria

- Gate report recorded in the spec directory (or its landing
  commit): all six items answered, arm chosen explicitly.
- Full `tests/` suite green with the in-memory leg on the chosen
  arm; the four Docker engine legs unchanged; `ruff` and `ty` at
  zero; coverage held.
- Trash-arc conformance families (delete-to-trash naming and
  truncation, trash-path reporting, restore both address forms,
  sweep retention/skips/idempotence) pass on the in-memory leg with
  the same observable results as sqlite-file.
- No reference to the old dict-based implementation remains
  (`InMemoryStorage` now names the thin subclass); no `unsupported`
  arm for restore/sweep remains reachable anywhere.
- Suite wall-clock delta reported in the landing note; a regression
  beyond ~2× on the in-memory leg is a gate finding to raise, not
  silently accept.

## Non-goals

- The ADR 027 contract flip — `permanent` removal, chain-inside
  refusal, sweep's purge arm (spec 085).
- Turso's remote-sync dialects (`turso_sync`) or any networked use.
- Replacing file-based sqlite dev databases or any server-engine
  leg; multi-process in-memory serving (ADR 028 pin 4).
