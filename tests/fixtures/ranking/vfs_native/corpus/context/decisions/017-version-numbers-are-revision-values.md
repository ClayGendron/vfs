# 017. Version Numbers Are Revision Values — One Per-Entry Sequence

- **Status:** accepted
- **Date:** 2026-07-18
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay proposed unifying the two sequences in the
  2026-07-18 model session; the assistant's prior-art assessment split
  the proposal — unify the number, decline the change journal and the
  `action` field — and Clay adopted that split same session)

## Context

An entry carries two per-entry monotone numbers with different jobs.
`revision` (ADR 013) is the concurrency and change token: the
lost-update guard in every material UPDATE, the observation snapshot
coordinate, the parent namespace-change bump. `version_number` (the
`versions` table key, spec 072 §9 / the W3 memo section) labels
retrievable content history: stored payload rows reconstructable per
version. Under the 2026-07-13 W3 inversion, version rows are minted
inside the write transaction as full snapshots, diffs deferred to the
batch pack verb.

Left separate, the sequences cost real work at the wire-up point: the
write path holds the entry's revision (fetched by the plan) but would
need a per-entry `max(version_number)` lookup — or the dormant
`entries.version_number` column — to label the version row it mints in
the same transaction, against the 10,000-entry-batch ETL contract.
Spec 074 parked "unify `versions.version_number` with `revision`" as a
possible alignment; spec 076's model split re-raised it when
`Entry.create_version` was dropped (no pipeline caller holds an
`Entry` at minting time — versioning is a storage-side effect of
write/edit).

The full unification proposal — every revision tick mints a version
row, non-content changes included, with an `action` field explaining
why — was assessed against the reference set and declined in part:

- The revision design's own basis (Linux `i_version`, 9P `qid.vers`,
  the NFSv4 change attribute — `research/2026-07-13-database-storage-
  write-pipeline.md` W2) is token-not-history; `i_version` skips
  increments nobody queried, so there is nothing to retrieve at an old
  value by construction.
- The roster separates the instruments: git records no rename events
  at all (rename detection is diff-time heuristic); Jackrabbit Oak
  splits DocumentNodeStore revisions (MVCC, GC'd) from the JCR version
  store; ZFS splits transaction groups from snapshots. CouchDB — the
  known system that merged its token (`_rev`) with retrievable
  history — documents permanently that old revisions must not be
  treated as history because compaction discards them.
- A row per action is a change-log table by another name, and the
  2026-07-17 session decision recorded in ADR 013 is explicit:
  "`updated_at` is the mount-wide change cursor. No change-log table."
  For directories it also collides with ADR 013 pin 5's direction that
  stored parent bumps leave the write path entirely.

What survives the assessment is the labeling half: one number, minted
rows only for content.

## Options considered

- **(a) Separate sequences (status quo)** — versions keep a dense
  private ordinal. Dense-range reconstruction and numbering-based gap
  detection; but the write path pays a per-entry current-version
  lookup (or maintains the dormant `entries.version_number` column) on
  every content write, and two per-entry monotone numbers coexist with
  no consumer needing them to differ.
- **(b) Full unification — version rows for every revision tick, with
  an `action` discriminator** — one retrievable history of everything.
  Rejected: it is the declined change-log table; it inverts the
  token-not-history basis of ADR 013; no roster precedent merges the
  instruments successfully; it adds inserts to paths that are today a
  single column increment; and directories cannot follow (pin 5), so
  the unification would be partial anyway.
- **(c) Label unification — `version_number` is the owner's revision
  at mint time; rows minted for content writes only (chosen)** — one
  sequence, zero extra lookups at write time, numbering gaps where
  non-content changes ticked the revision. Requires reconstruction to
  walk stored rows in order rather than a dense numeric range.

## Decision

We choose (c). Five pins:

1. **A version row's `version_number` is the owner entry's revision
   stamped in the same write transaction.** No separate version
   counter exists anywhere — no `max(version_number)` lookup, no
   per-entry allocation state. The first version of a file is
   labeled 1 (creation mints revision 1), and a version row's label
   always equals a stat's revision immediately after the write.
2. **Version rows are minted for material content writes only.**
   `write`, `edit`, and future content-writing verbs mint one; moves,
   metadata writes, and parent bumps tick the revision and mint
   nothing. Numbering gaps in a file's version chain are therefore
   expected and informative — a gap means non-content changes happened
   between two versions — never an error. There is no `action` field
   and no journaling of non-content events (the no-change-log decision
   stands).
3. **Reconstruction is order-based, never dense-range.** To
   reconstruct version V: among stored rows with label ≤ V, walk from
   the nearest snapshot forward in label order, applying each diff to
   the previous row's content; a row labeled V must exist. Integrity
   is the content-hash verification (W3 amendment 2: a mismatch
   classifies as dedicated corruption, distinct from not_found) — a
   lost intermediate row surfaces as a failed hash or a failed diff
   application, not as a numbering discontinuity. Forward diffs
   transform the *previous stored row's* content, whatever its label
   distance.
4. **Snapshot cadence counts stored rows, not label arithmetic.** The
   pack verb's snapshot-every-N interval (W3: interval 10 is the
   packed form's parameter) is measured in chain length — rows since
   the last snapshot — since `label % N` is meaningless over gapped
   labels. The write path itself always snapshots (W3 inversion,
   unchanged).
5. **The `entries.version_number` column is dropped** (greenfield, no
   migration). The current version label of a file *is* its revision;
   a separate cache column would be derived state with no reader.
   Directories are untouched by this record: revision only, no version
   rows, per ADR 013.

## Consequences

- **Easier:** the write path labels version rows with a value it
  already holds — bulk version minting is one more executemany with
  zero additional reads at any batch size; one per-entry sequence to
  reason about; the dormant entries column and its drift-test
  exemption go; a version chain's gaps double as a free record that
  something non-content happened, without storing anything.
- **Harder:** reconstruction and the pack verb must be order-based and
  gap-tolerant; numbering-continuity checks are no longer an available
  integrity signal — the content-hash check carries that weight alone
  (and stays mandatory on both write and read, W3 amendment 1);
  version labels are not consecutive, so any consumer rendering "v1,
  v2, v3" must render the stored labels, not ordinals.
- **Committed to:** the write-wiring spec mints snapshot version rows
  labeled by the staged revision inside the write transaction; the
  pack verb consumes and preserves gapped labels; `Version.reconstruct`
  in the live tree is order-based ahead of the wiring so the model
  never encodes the dense assumption.

## Naming addendum (same session)

With one sequence there is one name, and it is **`version`** — chosen
by Clay, and the better-precedented name for the token itself: the
systems the revision design was based on call theirs `i_version` and
`qid.vers`, and JPA/Hibernate's optimistic-lock field (`@Version`, the
same guard job) is the industry convention. "Version" is also how
agents and people already think about history. Four naming pins:

1. **The per-entry value is `version` everywhere** — the entries-table
   column, `StagedEntry.version`/`base_version`, the observation
   field, the write-path guard, the memory backend, and the trait key
   (`version_encoding: per_entry64`). The word "revision" leaves the
   live tree; ADRs 013/017 stand as written (point-in-time records).
2. **`Entry` carries no version field.** The value is minted and
   guarded storage-side and reported on observations; a caller cannot
   author one, and nothing reads it before `StagedEntry` (verified —
   every write-path use was the SQL column, never the model field).
   Like the row ids, it is persistence bookkeeping the domain model
   never holds. Amends ADR 015 pin 1's field inventory.
3. **`Observation` carries one field, `version`, not two.** A stat's
   `version` is the entry's current value; a version row's `version`
   is its label — the same sequence, so the two old mirrors
   (`revision`, `version_number`) collapse into one, owned by
   `Version.number` in the mirror-drift map.
4. **`Version`'s discriminator field is `number`** (`version.version`
   stutters). Its column stays `version_number` — self-describing in
   bare SQL, and adjacent to Oracle's reserved word NUMBER — mapped by
   a declared per-model rename in `rows.py`.

Evidence: `research/2026-07-13-database-storage-write-pipeline.md`
(W2 revision basis; W3 version chain and its 2026-07-13 inversion,
amendments 1–2); `research/2026-07-17-write-path-prior-art-and-
scaling.md` (§4 cold-counter law; the no-change-log resolution);
`context/decisions/013-per-entry-revisions.md` (pins 1, 4, 5 — the
revision semantics this record builds on). Resolves the alignment
parked in spec 074; amends spec 076's `Version.reconstruct` contract
from dense-range to order-based. Does not supersede any numbered ADR.
