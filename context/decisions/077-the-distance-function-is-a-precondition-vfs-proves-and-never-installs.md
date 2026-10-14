# 077. The Distance Function Is a Precondition vfs Proves and Never Installs Implicitly; Installing Is an Explicit Verb

- **Status:** accepted 2026-10-12 (Clay, in conversation, on the map of
  the Postgres first touch: "Do it all please, this sounds like the
  right direction"). **Title and decision reconciled 2026-10-13 with
  the landed `install_extensions` verb (`c1900be`):** "never installs"
  means first touch never installs on its own; an operator who calls
  the explicit verb has chosen the install, which is the opt-in the
  decision below always allowed. The file keeps its original slug.
  Refines ADR 059 (every supported dialect has a
  cosine distance function) and ADR 057 (sqlite-vec is a core
  dependency loaded on every connection); nothing is superseded.
- **Date:** 2026-10-12
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay). Claude mapped the first-touch path,
  found the race, drafted the design and this record.
- **Context source:** the Postgres leg of spec 162's review
  (2026-10-12): three first touches failing with a unique violation on
  `pg_extension`; the live tree at `7d0bc3c`.

## Context

ADR 059 made a cosine distance function the fact that admits a dialect
to the ranked verbs: sqlite-vec on SQLite, pgvector on Postgres, the
built-in functions on MariaDB, SQL Server 2025 and Oracle 23ai. The
two extensions reached the engine by different roads. SQLite's rode
every connection (the pool hook loads it; first touch probed it and
refused the mount, naming the fix, when the interpreter could not load
extensions). Postgres's was created by vfs itself: a `CREATE EXTENSION
IF NOT EXISTS vector` DDL event fired inside `create_all` whenever a
mount carried a native vector column.

The Postgres leg exposed two things about that second road. First, it
races: the extension is cluster-wide while mounts are per schema, so
two mounts' first touches on one fresh cluster both run the DDL, and
Postgres's `IF NOT EXISTS` is not atomic — the loser blocks on the
winner's catalog row and then takes a unique violation. Second, and
decisive, it only works where vfs is a superuser. pgvector is not a
trusted extension, so `CREATE EXTENSION vector` needs a superuser —
owning the database is not enough (verified 2026-10-13 against the
extension's control file, which declares no `trusted`, and a fresh
non-superuser owner refused with 42501 "Must be superuser to create
this extension"); on RDS, Cloud SQL and most managed servers an
application role cannot run it at all. The
self-install was a dev-container convenience that fails in
production, which is the posture the project's production stance
forbids.

## Options considered

1. **Keep the self-install and make it race-safe.** Run the DDL under a
   savepoint before `create_all` and swallow the loser's unique
   violation. Closes the race; keeps the privilege assumption.
2. **Require the function; probe and refuse.** Treat pgvector as SQLite
   already treats sqlite-vec: a precondition first touch proves, with a
   refusal that names the one-time fix. vfs runs no extension DDL. The
   dev and CI cluster installs it from an init script at first start.
3. **Option 2, with the probe declared on the profile.** The probe
   statement and the refusal's wording are engine facts SQLAlchemy
   takes no position on, so they belong on `DialectProfile`, and first
   touch runs one generic probe step instead of per-dialect branches.

## Decision

Option 3.

- **The distance function is a precondition.** vfs proves it at first
  touch and never installs it implicitly: no first touch, no
  `create_all` hook, no verb an agent reaches runs extension DDL. The
  one install vfs offers is the explicit verb below, which an operator
  calls on purpose. A mount whose engine lacks the function refuses
  `unavailable` naming the fix, before any DDL runs.
- **The probe is a profile fact.** `DialectProfile.vector_function`
  groups the probe statement, the refusal's detail (`missing`) and the
  optional install statement in one value, so a probe cannot ship
  without a fix to name and an install cannot ship without a probe to
  prove it (grouped 2026-10-13; the three were separate fields at
  acceptance). The probe fails when the engine answers no row or
  raises a permanent error — a raise the retry policy would restart,
  or one that cost the connection, propagates to the caller's retry
  and classifier instead of being read as a missing function (narrowed
  2026-10-13). A scalar answer is the
  function's version, kept on the host (`vector_version`) for the
  tiers that gate on it (pgvector 0.8's iterative scans). SQLite
  declares `SELECT vec_version()`; Postgres declares the `pg_extension`
  catalog read. The engines whose function is built into every
  supported server version, and the generic floor, declare none.
- **Postgres means Postgres with pgvector**, exactly as SQLite means
  SQLite with sqlite-vec. The probe runs on every Postgres mount,
  embedder or not: the dialect's admission to the ranked verbs rests on
  the function being there.
- **Installing is explicit, never implicit** (Clay, 2026-10-12: "we do
  have an option for developers to do that work if they choose from
  the code"). `DatabaseStorage.install_extensions()` is a
  developer-plane verb that runs the profile's install statement —
  pgvector's `CREATE EXTENSION IF NOT EXISTS` — then runs the probe,
  so a success means first touch will not refuse on it. It is opt-in,
  idempotent, runs before first touch, answers `permission_denied`
  (SQLSTATE 42501) for a role that may not install — on Postgres, any
  role that is not a superuser — and succeeds with nothing done where
  the profile declares nothing. First touch never calls it. This is
  the one place vfs installs anything, and it is not the implicit
  install the title forbids: the operator chose it.
- **Dev and CI install it once, outside vfs.** `docker/initdb/postgres/`
  creates the extension when the test container first starts; the
  compose file mounts it. On a user's own server the step is the
  standard pgvector install as a superuser (or a managed provider's
  privileged role), documented in the Postgres how-to.
- **The ANN index DDL stays.** It is per schema, race-free, and needs
  only table rights.

## Consequences

- Production parity: the path a managed-Postgres deployment takes is
  the path the tests take. The extension race cannot recur because
  nobody creates the extension concurrently.
- One first-touch ladder for every engine: file settings, value cap,
  vector probe, verify-or-provision. Two `if profile.name == ...`
  branches left the engine host.
- A Postgres database without pgvector refuses every verb with one
  message that names the fix. Before, it provisioned and then failed
  later, inside the vector leg, with a driver error.
- The test suite pins the probe's two failure shapes on SQLite alone:
  the engine raising (an interpreter without extension loading) and the
  engine answering no row (a profile replaced to return none). The
  Postgres leg proves the real catalog read.
