# 014. Trash Namespace: Normal-FS Parity, Not a Reserved Scope

- **Status:** accepted
- **Date:** 2026-07-18
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay chose normal-fs parity in the 2026-07-18
  session, after the guard-removal fork was presented with its
  consequences; research and this record followed same session)

## Context

Spec 072 §9 pinned trash as backend-internal state: trashed rows'
path caches rewritten under a reserved `/.vfs/trash/...` prefix that
ingress never admits, an unconditional read filter so "no verb ever
surfaces a trashed row" (`descent.py` `trash_filters`), and a plan-time
write refusal (`writes.py` `outside_trash`). Error shapes were pinned
to conceal trash structure entirely.

The 2026-07-18 review of the write pipeline surfaced the question: on
every desktop OS, trash is an ordinary directory plus a convention —
browsable, restorable by move, writable — and the reserved model is
stricter than anything in the reviewed field
(`research/2026-07-18-trash-namespace-parity.md`). Two findings frame
the choice:

- **Hiding is done by the path rewrite, not the filter.** Delete
  reparents and rewrites the row's path in one transaction (ADR 004),
  so the pjdfstest contract — a deleted file's *original* path
  classifies `not_found` through every read verb — survives with the
  filters gone. The filters only conceal the trash-side paths.
- **The precedent pool splits on writability, not visibility.**
  freedesktop/macOS enforce nothing (ordinary directory; cleanup
  tolerates foreign state); Windows enforces via ACLs only; JuiceFS —
  the one fs-layer-enforced trash — ships *visible*-but-immutable,
  and its sweeper's parse-bucket-names-as-timestamps assumption is
  safe only because that closed world makes foreign rows impossible
  (memo §3, file:line). Nobody ships an invisible trash.

Delete, restore, and the reclamation sweep are unimplemented stubs
(`backend.py`), so the model change re-scopes future verbs rather than
rewriting shipped ones.

## Options considered

- **(a) Reserved invisible scope (status quo, spec 072 §9)** — maximal
  concealment and a closed world for the sweeper; but the strictest
  model in the field, costs a second scope concept on every read path,
  and hides state agents could usefully inspect and repair.
- **(b) Remove the write gate only** — incoherent: `_fetch_committed`
  still filters trash, so writes there misfire against the unique
  index behind a phantom-parent view, and anything that lands is
  unreadable forever (a write-only hole). Rejected outright.
- **(c) JuiceFS-shape: visible but immutable** — browsable trash,
  every mutation inside refused, restore root-only; preserves the
  closed-world sweeper invariant. A coherent middle, but it keeps
  trash-specific refusal logic on every mutating verb and diverges
  from the desktop model users know.
- **(d) Normal-fs parity (chosen)** — trash is an ordinary subtree
  under the existing meta scope; delete/restore/sweep are conventions
  atop plain namespace verbs, and cleanup adopts the desktop stance of
  tolerating foreign state.

## Decision

We choose (d). Six pins:

1. **One scope, not two.** The trash-specific read exclusion
   (`trash_filters` and its uses in reads, writes, and descent) is
   retired. `/.vfs/trash` inherits the meta scope exactly: hidden from
   default-scope enumeration because `/.vfs` is, served in full when
   directly anchored. No verb treats trash specially on the read side.
2. **Writes into trash are ordinary writes.** The `outside_trash`
   plan gate is retired and ingress admits trash-prefixed paths under
   the ordinary path grammar. Create, mkdir, edit, move-into, and
   move-out-of trash follow the standard gates (parent rule, key
   budget, kind checks) with no trash-specific arm.
3. **Delete semantics are unchanged in shape.** Delete remains a
   same-transaction reparent into time-bucketed nodes under
   `/.vfs/trash`, rewriting descendant path caches. The
   original-path `not_found` contract is delivered by the rewrite
   alone and remains a harness row for the delete spec.
4. **Restore is a verb over metadata, move is always available.**
   The restore verb consumes `original_parent_id`/`original_name`
   row columns; on a row without restore metadata (user-authored in
   trash) it classifies `invalid`. Restore-by-move — the desktop
   gesture — works on any trash row as a plain `move`, target-exists
   classifying `conflict`.
5. **The sweep tolerates foreign state, loudly.** Reclamation remains
   an explicit idempotent verb (no background work, ADR 013 pin 5).
   It destroys expired bucket subtrees wholesale — *including*
   user-authored rows inside them, the documented macOS-purge
   contract — and skips, never destroys, unrecognized rows directly
   under `/.vfs/trash` (the JuiceFS skip precedent). Every skip is
   surfaced in the sweep's result, not just logged.
6. **Structure concealment ends.** Trash buckets, ULID in-bucket
   names, and restore metadata are observable; error shapes may name
   trash paths. The concealment guarantees and their tests
   (`test_backends_database.py` trash-invisibility family) are
   deliberately dropped, not weakened in place.

## Consequences

- **Easier:** one namespace scope instead of two — `liveness_filters`
  reduces to the meta rule and the write path loses a gate; the
  "routed list-the-trash/restore namespace" spec 072 deferred as a
  follow-up story arrives free (browse via `ls`, restore via `move`);
  agents can inspect, repair, and empty trash with ordinary verbs;
  descent stops maintaining a filtered parallel view of ancestry.
- **Harder:** the sweep can destroy user-authored data (aged buckets)
  — a contract to document and test, impossible by construction under
  (a)/(c); sweep and restore must tolerate rows that violate bucket
  discipline instead of assuming a closed world; the trash-side
  posture of enumeration, grep, and graph verbs is re-derived from
  meta-scope rules and needs test rows; the concealment test family is
  rewritten to pin visibility instead.
- **Committed to:** spec 075 executes the re-scope in the live tree
  (filters, gates, ingress, tests, docstrings); the future delete/
  restore/sweep spec implements the verbs against pins 3–5; the memory
  backend, when it grows delete, mirrors the same observable contract.

Evidence: `research/2026-07-18-trash-namespace-parity.md` (all
sections); `research/2026-07-13-database-storage-write-pipeline.md`
W6 (trash-reparent resolution — reparent shape unaffected);
`context/decisions/004-stable-node-identity.md` (path rewrite on
reparent). Supersedes the spec 072 §9 pins "trash is backend-internal
state", "ingress never admits", and "no verb ever surfaces a trashed
row"; does not supersede 072's delete-transaction shape, bucket
scheme, ULID in-bucket naming, or identity-based restore metadata.
Does not supersede any numbered ADR.
