# 002. A Database Backend Builds Its Engine or Borrows Sessions — Never Holds an Engine It Didn't Make

- **Status:** accepted
- **Date:** 2026-07-05
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

The pre-refactor constructor (`base.py`, carried into
`backends/database.py`) accepted `engine`, `session_factory`, or both,
and inferred lifecycle from which kwarg happened to arrive. Three costs,
all felt in production and notebooks:

- **Ambiguous ownership.** A backend handed a live engine had to guess
  whether to dispose it. The router guessed too: `close()` and
  `remove_mount` reached into a child's private `_engine` and disposed
  it — even when the caller shared that engine with the rest of an
  application. Pass `session_factory` alone and `_engine` was `None`,
  so disposal silently skipped the pool entirely: a leak on one path, a
  trespass on the other.
- **Loop poisoning in notebooks.** SQLAlchemy async engines bind their
  pooled connections to the loop of first *await*, not construction.
  The documented flow — create an engine in a cell, construct the
  backend around it, "invoke `setup()` once after construction" — made
  `await dbfs.setup()` on the Jupyter kernel loop the natural move.
  Mount that backend into the sync client (private loop on a daemon
  thread) and every op hits asyncpg's "attached to a different loop."
  One innocent await anywhere in the engine's life broke everything
  after it.
- **The database backend port is imminent** (ADR 001's committed
  seam), and every constructor it lands fossilizes the shape. ADR 001's
  `SupportsClose` says "a backend that owns an engine exposes
  `async close()`" without defining *owns*. This ADR defines it.

Two real deployment shapes exist and both must stay first-class: a
standalone backend (notebooks, pipelines, the sync client) where the
backend is the only thing touching the database, and an embedded
backend inside a web app that already owns an engine, a pool, and a
session pattern — where creating a second connection stack is waste.

## Options considered

- **Keep the three-way constructor** (`engine` | `session_factory` |
  both) — pros: no migration; covers every wiring in principle. Cons:
  ownership is inferred, not stated; the disposal leak/trespass pair is
  structural; the live-engine path is exactly the one that poisons
  notebook loops.
- **Live engine plus an ownership flag** (`owns_engine: bool`) — pros:
  explicit-ish; one constructor. Cons: the flag is an identity claim
  enforced by nothing (the same defect ADR 001 retired in
  `storage: bool`); the caller can lie or forget, and the loop-poisoning
  path survives untouched.
- **Exactly two constructions, ownership follows construction**
  (chosen) — pros: no flag, no inference — the construction *is* the
  ownership mode; the standalone path is inert until first use, which
  makes the sync-client/notebook loop contract structural; the embedded
  path reuses the app's stack without duplicating it. Cons: "I already
  have an engine object" callers must wrap it in a sessionmaker
  themselves — one line, and doing so states the ownership they mean.

## Decision

A database backend is constructed in exactly one of two ways, validated
as a loud XOR at construction. The bare `engine=` kwarg is removed.

- **Built (owned).** The backend takes connection config (URL plus
  pool/engine options), calls `create_async_engine` itself, and builds
  its own internal sessionmaker (`expire_on_commit=False` and whatever
  else its ops require). It implements `SupportsClose`, and `close()`
  disposes the engine. Because `create_async_engine` binds nothing
  until the first await, the constructed backend is inert: safe to
  build in a notebook cell, hand to the sync client, and have
  first-touch land on the client's private loop. This is the default
  path — the one notebooks, pipelines, and quickstarts show.
- **Borrowed (injected sessions).** The backend takes a session
  factory from an application that already owns its database
  connectivity. It never sees the engine and never creates one;
  `close()` releases backend-internal state only and does not touch
  the pool. Lifecycle belongs entirely to the app. Intended for
  single-loop, in-process web apps.

The rule that replaces all inference: **you own what you build.**

Settled details:

- **The injected factory yields fresh, independent sessions.** ADR 001
  §D5 stands: each op opens its own session, commits, and closes —
  backend-internal, invisible to the router. A factory that returns the
  app's live request-scoped session is a contract violation: the
  backend would commit the app's transaction mid-request. Joining an
  external transaction is out of scope; if ever wanted, it is ADR 001's
  designed protocol entry point, not a smuggled session.
- **Dialect-dependent work moves out of `__init__`.** A borrowed
  backend cannot know its dialect until the first session exists
  (`session.bind.dialect`). Parameter budgets, dialect sniffing, and
  one-shot initialization (`create_all`, metadata root) all defer to an
  idempotent first-touch path. There is no separate `setup()` the
  caller must remember to await — mount time already exercises the
  backend (the mountability probe calls `stat`), so first touch runs on
  the mounting loop by construction.
- **`SupportsClose`'s "owns" is now defined:** built → dispose;
  borrowed → don't. Both modes may implement `close()`; only the built
  mode touches the pool.

## Consequences

- **Easier:** the sync-client/notebook contract becomes structural —
  a built backend has nothing loop-bound until the client's own loop
  touches it, so the old cross-loop failure has no sequence of
  innocent cells that produces it; web apps embed the backend without
  a second connection stack; disposal is delegated to the one object
  that knows the answer, ending the leak/trespass pair.
- **Harder:** callers holding only a live engine must wrap it in a
  sessionmaker to use the borrowed path; borrowed backends cannot make
  construction-time dialect decisions, so anything dialect-keyed must
  tolerate deferral to first use.
- **Committed to:** the borrowed path is single-loop by intent — its
  documentation carries one blunt line: *in notebooks and sync-client
  pipelines, use the built path.* The design makes the right
  combination the obvious default rather than making the wrong one
  impossible.
- **Committed to:** ops never join an external transaction. The web
  app's request transaction and the backend's op transactions are
  separate by design.

Executes through the database backend port story (unnumbered at time
of writing; the first story to land a constructor against ADR 001's
protocol seam). Refines ADR 001's `SupportsClose`.

**Consequence note (056, 2026-07-07):** with storage mounts, nothing
exercises a backend at bind — `bind` probes the *owning* entry's
storage for the site, never the incoming backend.  First touch,
dialect decisions, and any session handshake happen at the first
routed op, by design; `close()` disposes each distinct `owned` backend
through `SupportsClose`, identity-deduped.
