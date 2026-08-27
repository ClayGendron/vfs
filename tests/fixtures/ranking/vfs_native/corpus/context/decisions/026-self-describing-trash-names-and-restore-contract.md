# 026. Self-Describing Trash Names and the Restore Contract

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** Clay Gendron
- **Decided by:** AI-with-approval (five-researcher prior-art pass run
  at Clay's request after reviewing the landed delete verb; Clay
  approved the synthesized recommendations in session)

## Context

The landed delete verb (`topology.py`) reparents a trashed row into
an hourly bucket and renames it to its **bare ULID**. ADR 014 made
trash a normal, raw-browsable subtree — and explicitly left spec 072
§9's bare-ULID in-bucket naming standing. Reviewing the landed verb,
Clay raised three concerns: the in-trash name is meaningless to a
browser; an agent has no pinned way to locate and restore the right
row; and same-name deletes needed a checked answer at both collision
sites (in trash, and at restore when the original site is occupied or
its parent is gone).

The prior-art pass
(`research/2026-07-23-trash-prior-art-naming-and-restore.md`) found
the field's fault line: opaque trash names are sound **only behind a
presentation layer** (Windows `$R<token>`, freedesktop's
name-is-never-authoritative rule) — every system whose trash is
browsed raw keeps the original name in the entry (JuiceFS
`<parentIno>-<ino>-<origName>`, HDFS full-path preservation, macOS).
ADR 014 chose raw browsing, so the bare ULID mixes the two camps
incoherently. On restore, the field is unanimous on refusing occupied
targets and disambiguating by deletion time, and splits on missing
parents (recreate vs fail-and-keep).

## Options considered

- **(a) Keep the bare ULID, rely on metadata queries** — the
  Windows/freedesktop camp. Sound only with a mandatory presentation
  layer, which ADR 014's raw-browsable trash deliberately lacks; every
  `ls` of a bucket is unreadable without a join. Rejected.
- **(b) JuiceFS encoding `<parent_id>-<ULID>-<name>`** — proven, and
  prefix-groupable by parent. But the parent id is already an indexed
  column (`original_parent_id`), the ULID alone is unique and
  time-sortable, and the extra fixed segment spends name-budget bytes
  that the readable suffix needs. Rejected as redundant encoding.
- **(c) Name-first `<original_name>-<ULID>`** — sorts buckets by
  name, but truncation on the byte budget would have to cut the
  middle or the unique token; the fixed-width token belongs where
  truncation can never reach it. Rejected.
- **(d) `<ULID>-<original_name>`, name tail truncated to budget
  (chosen)** — unique by prefix, time-sorted listings for free,
  self-describing, extension survives (the Windows lesson: type
  detection keeps working in trash).
- **(e) Flag-don't-move (S3/Drive/ORM soft delete)** — dissolves the
  naming and collision questions but threads `deleted_at IS NULL`
  through every live query and the `(parent_id, name)` unique index.
  Rejected: the physical move keeps hot-path indexes clean; recorded
  so it is not re-litigated.
- **(f) Snapshots instead of trash (Plan 9/ZFS school)** — strictly
  more capable (answers modification recovery too, names never go
  opaque), but whole-namespace snapshots in SQL are real write
  amplification. Rejected for the trash role; trash is framed as
  cheap delete-undo, not time-travel, and a future snapshot/version
  story is a separate concern this ADR does not open.

## Decision

Five pins:

1. **The in-bucket name is `<ULID>-<original_name>`.** The ULID
   prefix alone carries uniqueness and makes bucket listings
   time-ordered; the suffix is the row's pre-delete name, carried for
   browsability (extension included). The whole name truncates at the
   tail to fit `MAX_SEGMENT_LENGTH` (255 bytes, never splitting a
   UTF-8 sequence); truncation costs nothing correctness-wise because
   the ULID is untouchable by position. The freedesktop discipline
   holds: the name is display, `original_name`/`original_parent_id`/
   `deleted_at` columns remain the only authority — nothing ever
   parses the trash name.
2. **Delete reports the trash location.** Each trashed row's
   post-delete trash path is part of the delete result (the
   `resultingItemURL` lesson): the deleting agent learns where its
   file went without a search. Mechanism (observation field vs
   result shape) is the implementing spec's call.
3. **Restore lookup is by original site and deletion time.** The
   supported flow: query trash by original path/parent
   (`original_parent_id`, `original_name` — indexed; *amendment
   2026-07-24: these columns were in fact unindexed at acceptance —
   spec 082 added `ix_<table>_restore`*) and disambiguate
   multiple candidates by `deleted_at`, the field's universal
   disambiguator; the ULID-prefixed trash path is the exact address
   when the caller holds it. The ADR 014 pin 4 restore verb consumes
   this contract.
4. **Restore edge policies.** Occupied original site → refuse
   (`exists`), overwrite only by explicit opt-in — the landed move
   ladder already conforms; never silent-clobber (unanimous in the
   field). Missing original parent → **fail-and-keep** (the JuiceFS
   arm, and what the landed move's destination-parent gate already
   does): the row stays in trash with metadata intact — a failed
   batch never commits, so a failed restore can never strand a row
   with cleared restore columns. Recreate-the-parent-chain (the
   Windows/Finder/trash-cli arm) is a possible additive affordance on
   the restore verb, not pinned here.
5. **Expiry keys off bucket names; policy numbers are open.** The
   ADR 014 pin 5 sweep identifies expired buckets by parsing the
   `<YYYY-MM-DD-HH>` directory name and drops them wholesale
   (JuiceFS's proven O(buckets) primitive); per-row `deleted_at` is
   display and audit, not the expiry index. Retention length, any
   size bound, and eviction observability are deliberately not
   decided here (→ `open-questions.md`).

## Consequences

- **Easier:** `ls` of a bucket is self-describing and time-ordered —
  no join to identify entries; agents get a full locate-and-restore
  story (delete returns the trash path; queries by original site and
  time; refusal semantics already match the landed move ladder);
  type/extension detection keeps working on trashed rows; the two
  rejected schools are on record and stay closed.
- **Harder:** the trash prefix grows from a fixed 26-byte ULID to up
  to 255 bytes, shrinking descendant headroom under the 1,024-byte
  path budget — deep trees are likelier to refuse `unaddressable`
  (the pinned overflow behavior; `permanent=True` remains the
  fallback). Same-named same-hour deletes now share a readable
  suffix and are told apart by ULID prefix and `deleted_at`, which
  listings should surface.
- **Committed to:** `topology.py`'s trash arm adopts the pin-1 name
  and its module contract drops the "name swapped to the entry's
  ULID" wording; the delete result grows the trash location (pin 2);
  the future restore-verb spec implements pins 3–4; the sweep spec
  implements pin 5; tests pin name shape, truncation, budget
  interaction, and the delete-result trash path.

Evidence: `research/2026-07-23-trash-prior-art-naming-and-restore.md`
(all sections); `research/2026-07-18-trash-namespace-parity.md` §3
(JuiceFS contract). Supersedes spec 072 §9's bare-ULID in-bucket
naming — the pin ADR 014 explicitly left standing; refines ADR 014
pins 3–5 (delete shape otherwise unchanged; restore-verb and sweep
contracts sharpened) and supersedes no numbered ADR.
