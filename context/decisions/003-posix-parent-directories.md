# 003. Mutations Follow POSIX: No Implicit Parent Directories — Auto-Creation Is an Explicit Flag

- **Status:** accepted
- **Date:** 2026-07-07
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

The pre-refactor write path materialized every missing ancestor
directory implicitly: writing `/a/b/c.txt` into an empty namespace
minted `/a` and `/a/b` as a side effect. The v2 design carried that
assumption forward as prose — "storage keeps the namespace *connected*:
writes materialize every ancestor directory" — and leaned on it in the
mount-site check's single-stat argument. No v2 backend has implemented
it yet, which makes this the last cheap moment to choose.

Two facts forced the question:

- **POSIX never auto-creates parents on file writes.** Verified by
  experiment (bash, 2026-07-07): `>`-redirect, `touch`, `tee`, and
  `cp` all fail `ENOENT` into a missing parent chain; `mkdir` without
  `-p` fails the same way; ancestor creation is exclusively
  `mkdir -p`'s job, and even `-p` forgives only existing
  *directories*, never a file in the chain (`ENOTDIR`) or a file at
  the site (`EEXIST`).
- **Implicit materialization hides caller mistakes.** A typo'd write
  (`/porjects/notes.md`) silently mints a phantom hierarchy instead of
  failing loud. For agent callers especially, a namespace that invents
  directories on demand converts one wrong path into permanent wrong
  *structure* that every later `ls`/`glob` faithfully reports.

The tension: agent ergonomics favor fewer round-trips (no
`mkdir`-then-`write` busywork), which is what the implicit design
optimized for.

## Options considered

- **Keep implicit materialization** (the carried-forward default) —
  pros: one call does everything; no `ENOENT` busywork for agents.
  Cons: diverges from POSIX so every filesystem intuition misleads;
  typos mint structure silently; "did I mean to create that tree?" is
  unanswerable after the fact; the caller never states intent.
- **POSIX-strict, no escape hatch** — pros: maximal predictability.
  Cons: forces a `mkdir -p` + `write` pair on every fresh tree — real
  friction for the batch-entry shape, where one entry list may fan out
  into many new directories.
- **POSIX-strict default, explicit opt-in flag** (chosen) — pros:
  defaults match every POSIX intuition and fail loud on typos; intent
  travels with the call (`parents=True` *says* "I mean to create the
  chain"); `pathlib` already standardized the exact vocabulary
  (`mkdir(parents=..., exist_ok=...)`), so the flags read as prior
  art, not invention. Cons: two knobs on the mutation surface; the
  flag must thread through the router chokepoints, the storage
  protocol, and the wire contract.

## Decision

Mutations that mint a new path follow POSIX by default, with
auto-creation as an explicit argument — never a side effect.

Settled details:

- **Default (strict):** the full parent chain must already exist as
  directories. A missing ancestor classifies `not_found` (ENOENT),
  naming the first missing ancestor. An ancestor that exists as a
  non-directory classifies `wrong_kind` (ENOTDIR) — that rule is
  unconditional, no flag relaxes it, matching `mkdir -p f/sub`.
- **Opt-in:** `parents: bool = False` on the verbs that mint paths —
  `write` and `mkdir` first; `move`/`copy` destinations adopt the same
  flag when their wiring lands. `parents=True` creates missing
  ancestors exactly as `mkdir -p` does.
- **`mkdir` idempotency is its own flag:** `exist_ok: bool = False`,
  pathlib-shaped. Strict `mkdir` on an occupied site classifies
  `exists` (EEXIST) whether the occupant is file or directory;
  `exist_ok=True` forgives an existing *directory* only — a file at
  the site stays `exists`, mirroring `mkdir -p` on a file.
- **Writing onto a directory stays `wrong_kind`** (EISDIR) regardless
  of flags — overwrite governs files only.
- **Connectedness survives as a storage invariant.** Ancestors either
  pre-exist (strict) or are minted by the flag (opt-in) — either way,
  a stored descendant always implies its stored ancestor directories.
  The mount-site check's single-stat argument
  (`StorageBackend.is_path_writable`) still holds; what changes is
  that ancestor creation is now the *caller's stated intent*, never
  the backend's guess.
- **Mounts are unaffected.** A mount may still attach at a sparse
  point (`/a/b/c` over empty storage): its ancestors are spine
  directories synthesized from the mount table, not stored rows —
  namespace connectedness there is the router's, not storage's.

## Consequences

- **Easier:** every POSIX intuition transfers — agents and humans can
  reason from `bash` behavior; path typos fail loud at the write
  instead of silently minting structure; error kinds map one-to-one
  onto errno (`not_found`/ENOENT, `wrong_kind`/ENOTDIR + EISDIR,
  `exists`/EEXIST), which the wire contract inherits for free.
- **Harder:** fresh-tree writes need `parents=True` or a prior
  `mkdir`; the flag threads through the router chokepoints, the
  `SupportsMutation` protocol signatures, and the MCP tool schemas;
  batch entry writes need a decision on whether `parents` is per-call
  or per-entry (per-call is the working assumption).
- **Committed to:** the strict default is the contract — a backend
  that materializes ancestors without the flag is out of spec, and the
  backend port's tests must pin both modes plus the unconditional
  `wrong_kind` ancestor rule. Prose that still describes implicit
  materialization ("writes materialize every ancestor directory") is
  superseded by this record and should be cleaned up as the mutation
  wiring lands.

Executes through the mutation-wiring story on the database backend
port (unnumbered at time of writing). Refines the write semantics
assumed by story 043 (entry authoring) and the connectedness prose
around `StorageBackend.is_path_writable`.
