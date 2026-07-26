# vfs storage-layer ground truth: where a blob sidecar attaches and what it strains

- **Study**: internal, constraint-side — for the 2026-07-25 multimodal
  storage-and-search memo (brief questions 1–6).
- **Date**: 2026-07-25
- **Method**: close reading of the live tree only (`src/`, `tests/`); every
  claim cites file:line. Adversarial by charter — this study exists to kill
  designs that don't survive the real write path, the real sweep, and the
  real dialect floor.

---

## 0. Ground truth that reframes the brief

Three facts about the live tree that the brief's numbered questions assume
away, established up front because everything below leans on them:

1. **The database backend mints no version rows and no chunk rows today.**
   The only statements that touch `tables.versions` and `tables.chunks`
   anywhere in `src/vfs/storage/` are the hard-delete arms of
   `_purge_subtree` (`topology.py:510-511`). `Version.create` is called
   only from models and tests; `backend.py`'s landed-op set has no pack
   verb and grep/mkedge are classified stubs (`backend.py:56-59`). The
   versions/chunks *schema* is live; the versions/chunks *flow* is future
   work. Binary versioning (brief Q4) therefore lands into an unwired
   pipeline — it is constrained by the `Version` model's shape, not by any
   executing write code.
2. **No file entry ever has `content = None` after validation.** The
   after-validator normalizes a non-directory's absent content to the empty
   string (`entry.py:223-224`), then measures it — sha256 of `""`,
   `size_bytes=0`, `lines=0` (`entry.py:226-227`). "This entry carries no
   text because it is media" is unrepresentable in the current model; the
   exclusivity rule (Q5) is not an addition but a carve-out of this
   normalization.
3. **Writes are deliberately not serialized with topology.** Stated twice
   and load-bearing: `_purge_subtree` loops its collect-and-delete because
   "a rival can commit a new child between the collecting select and the
   deletes" (`topology.py:497-499`), and `_TrashChain` calls the concurrent
   mint "the designed benign race" (`topology.py:521-527`). Any
   content-addressed GC design inherits this: the sweep transaction cannot
   assume writes are quiescent.

## 1. The attachment-point map (deliverable a)

What a binary sidecar physically touches, module by module.

### 1.1 Schema — `models/rows.py`

- **New table** in `build_vfs_tables` and a new slot in the `VFSTables`
  NamedTuple (`rows.py:275-290`, `rows.py:485-495`). Precedent for a
  model-less binary table exists: `posting_list` stores `LargeBinary`
  payloads with no domain model (`rows.py:473-483`) — so a hash-keyed blob
  table without a model is stylistically lawful, but see §5.1 on what that
  forfeits.
- **The narrow-row doctrine extends cleanly**: `ENTRY_CONTENT_FIELDS`
  (`rows.py:82-84`) is the declared "fields homed elsewhere" mechanism. An
  entry-keyed blob channel adds a sibling constant (`ENTRY_BLOB_FIELDS` or
  similar) plus a drift-test arm mirroring
  `test_content_table_homes_the_body` (`tests/test_rows.py:73-77`). A
  hash-keyed table adds no Entry field at all (the pointer is the existing
  `content_hash`, `rows.py:347`) and so adds no drift constant.
- **The body column cannot be widened**: `content` is `_body_text()` —
  Text/CLOB/VARCHAR(max)/LONGTEXT with UTF-8 collation pins
  (`rows.py:210-220, 374`). Bytes cannot ride it: the model rejects null
  bytes in text (`entry.py:132-139`, `version.py:61-68`, chunk equivalent
  at `chunk.py:50-55`), and base64-in-text costs ~33% plus double decode.
  The sidecar direction is forced, not chosen.

### 1.2 Model — `models/entry.py`

- `content: str | None` (`entry.py:86`) gains a sibling channel (field or
  not, per keying — §2). The validators that must change:
  `_derive_identity`'s content-vs-kind arbitration (`entry.py:171-191`),
  `_derive_and_measure`'s empty-string normalization and metrics
  (`entry.py:219-227`), and `with_content` (`entry.py:304-327`), which
  bypasses field validation and re-enforces invariants by hand — a second
  channel means a second hand-enforced invariant site.
- `CONTENT_KINDS` (`entry.py:43`) — see §3; it does at least four jobs.
- `Observation._shape_row` nulls `size_bytes` for non-content kinds
  (`entry.py:429-433`). Note: `Observation` has **no `lines` mirror at
  all** (`entry.py:384-397`) — "size_bytes yes, lines no" is already the
  wire shape; only the `entries.lines` column (NOT NULL default 0,
  `rows.py:350`) stores a vacuous 0 for media, indistinguishable from an
  empty text file. Acceptable, but it means `lines=0` is not evidence of
  anything.

### 1.3 Staging — `storage/backends/database/staging.py`

- `StagedEntry.content: str | None` (`staging.py:50`) and
  `refresh_material` (`staging.py:59-77`) carry the body through the plan;
  a blob channel adds a parallel field. `put_file`'s signature
  (`staging.py:178-191`) and `WritePlan.material_of` (`staging.py:122-132`)
  — which feeds the edit path — must learn the second channel, and
  `material_of` must *refuse* to hand media bytes to the edit machinery
  rather than hand them over (§3).
- **Memory posture**: the whole batch's bodies sit in `StagedEntry` rows
  in RAM before any statement runs — plan-then-execute is buy-the-whole-
  batch. At the 10,000-file contract, a per-row media cap of C bytes means
  a worst-case staged batch of 10,000 × C. A 10 MB cap is a 100 GB batch.
  **The per-row size ceiling (brief Q3) and the batch contract multiply;
  they cannot be chosen independently.** Either the cap is small (single-
  digit MB), or the write API for media grows a streaming/sub-batch path
  that the current plan shape does not have.

### 1.4 Write execution — `storage/backends/database/writes.py`

- The one place bytes flow today: `_replace_content` — chunked
  `entry_id IN` delete, then one executemany insert, gated on
  `s.content is not None and s.kind in CONTENT_KINDS` (`writes.py:676-689`).
  An entry-keyed blob pass is a structural twin (`_replace_blobs`); a
  hash-keyed pass is insert-if-absent plus nothing (the pointer is an
  entries column already written by `_entry_values`/`_material_values`,
  `writes.py:720-742`).
- **Idempotent-rewrite hazard**: delete-then-insert rewrites the body row
  even when content is unchanged. Tolerable for text; a no-op overwrite of
  a 500 MB blob rewriting half a gigabyte is not. Skipping on unchanged
  hash requires the committed snapshot to carry `content_hash` — it does
  **not** today (`_fetch_committed` selects entry_id, path, kind, version,
  ext, mime_type only, `writes.py:235-242`). Entry-keyed needs that column
  added; hash-keyed gets the skip for free (same hash → insert-if-absent
  no-ops, pointer write is idempotent).
- **Chunking is parameter-denominated, not byte-denominated**:
  `rows_per_statement` divides the bind budget by row width
  (`dialects.py:261-268`), and `_replace_content` hands SQLAlchemy the
  whole batch in one executemany (`writes.py:689`), trusting its
  parameter-count batching. Neither bounds *payload bytes per statement* —
  the dimension MySQL's `max_allowed_packet` and Oracle's LOB-bind
  behavior actually cap. The blob budget the brief hypothesizes
  (accumulated-payload flush chunking) is a new `DialectProfile` axis plus
  a new chunker beside `chunked`/`rows_per_statement` — it extends the
  established pattern (`dialects.py:229-268`) rather than fighting it, and
  it is justified under the profile doctrine because SQLAlchemy takes no
  position on packet/LOB budgets.
- **Hash-keyed insert-if-absent must follow the arbitration split**:
  `profile.arbitration` is `upsert` only on sqlite/postgresql
  (`dialects.py:84-160`); MySQL is deliberately `catch_retry` because
  `ON DUPLICATE KEY` fires on any unique index (`dialects.py:122-124`).
  So blob dedup inserts ride ON CONFLICT DO NOTHING on two engines and
  savepoint-catch on the rest — and a savepoint rollback on a conflicted
  chunk *re-sends the payload bytes* on the row-wise retry
  (`writes.py:437-448` is the template). Dedup collisions are the common
  case for media (that's the point of dedup), so the catch_retry engines
  pay payload-sized retries precisely when dedup is working. A probe-first
  (`SELECT hash IN (...)` then insert misses) pass shrinks but cannot
  eliminate the race window.

### 1.5 Reads — `storage/backends/database/reads.py`

- The one canonical join is entries⟕content (`rows.py:288-290`), used by
  `_entry_select` only when `content` is in the projection
  (`reads.py:382-389`). An entry-keyed blob adds either a second canonical
  join or a second join method; hash-keyed joins on
  `entries.content_hash = blobs.hash` — a non-identity join key, but LEFT
  and projection-gated, so stat-shaped reads never touch the LOB table
  either way. The projection push-down (`reads.py:68-84`) is the existing
  guard that keeps blob bytes out of listings; it holds unchanged.
- The text-read gate `kind not in CONTENT_KINDS → wrong_kind`
  (`reads.py:253-256`) is where "read a PNG" is currently refused-by-
  accident (a media entry would be kind `file`, pass the gate, and return
  its normalized-empty text). The exclusivity rule must make this gate
  channel-aware, which requires the fetched row to reveal its channel —
  a mime test, or a discriminator the projection always carries.

### 1.6 Topology — `storage/backends/database/topology.py`

- `_purge_subtree` is the **single hard-delete chokepoint** — used by
  permanent delete (`topology.py:173`), sweep (`topology.py:313`), and
  move-over-occupant (`topology.py:866`). Entry-keyed blobs attach as one
  more `DELETE ... WHERE entry_id IN (chunk)` line (`topology.py:508-516`)
  and the whole lifecycle story is finished. Hash-keyed blobs **cannot**
  be deleted there (other entries/versions may reference the hash) — the
  chokepoint stops being sufficient and a GC story becomes mandatory (§2.3).
- `_reparent_to_trash` touches only the entries row (`topology.py:727-748`)
  and restore is the move executor (`topology.py:845-884`) — path rewrites
  plus parent bumps, no content statements. **Trash and restore ride free
  under either keying.** This is the segmentation doctrine paying off:
  bodies out of the narrow row means namespace verbs never touch bodies.
- `_execute_copy` physically duplicates bodies: select content rows,
  re-insert under new ids (`topology.py:956-963`). Entry-keyed media makes
  every copy a byte-copy — a 10k-file media subtree copy moves its whole
  payload through the session inside one serialized topology transaction
  (which also blocks all other topology verbs for the duration,
  `topology.py:456-470`). Hash-keyed copy is free: `content_hash` is
  already in `_SUBTREE_COLUMNS` and already reproduced on the fresh rows
  (`topology.py:98, 941`). **This is the strongest code-grounded argument
  for hash-keying** — not dedup on ingest, but copy cost inside the
  serialized section.
- Note in passing: `_execute_copy` never copies `external_id`
  (`topology.py:905-907, 933-949`). If the oversized-media escape hatch
  (brief Q3) is an `external_id` object-store reference, **a copy of such
  an entry silently drops its bytes pointer**. Any reference-not-bytes
  design must revisit this deliberate omission.

## 2. Entry-keyed vs hash-keyed against the real paths (deliverable b)

### 2.1 Write path

Entry-keyed is a structural clone of `_replace_content`: same gate shape,
same delete-then-insert idempotency under the whole-method retry
discipline (`backend.py:19-25`), same chunking sites — plus the
byte-denominated flush budget both keyings need. Its costs are the
idempotent-rewrite hazard (§1.4) and duplicate bytes across entries.

Hash-keyed writes decompose into insert-if-absent (idempotent, races per
§1.4's arbitration note) plus the pointer, which is a column write the
entries pass already performs. No delete on overwrite — the old blob may
be shared — which is exactly what converts overwrite from "rewrite" to
"maybe-orphan" and creates the GC obligation.

### 2.2 Versioning

The `Version` model enforces snapshot XOR diff (`version.py:78-80`) and
`stored_payload()` raises when both are `None` (`version.py:119-125`).
A hash-reference version row — no payload, lean on the NOT NULL
`content_hash` (`rows.py:388`) — is a **third state the model forbids
today**. Reconstruction re-encodes text and hash-checks it
(`version.py:152-158`); media reconstruction would instead fetch the blob
by hash and compare raw-bytes sha256 — a different code path, not a
parameter. So:

- Entry-keyed media versions = snapshot-only with per-version byte
  duplication (a 10-version 100 MB asset stores 1 GB), or a version-blob
  table keyed `(entry_id, version_number)` — more schema, same
  duplication.
- Hash-keyed media versions = the version row *is* the reference;
  unchanged media across versions costs zero bytes. This requires the
  model change (a third lawful payload state) but no new table.

Because no backend mints version rows yet (§0.1), this choice is
unconstrained by executing code — the memo should treat the Version-model
shape change as the entire cost.

### 2.3 GC and the sweep — the decisive divergence

Entry-keyed: `_purge_subtree` extension, done. Trash rows keep their blob
rows (untouched by reparent); sweep purges them with the bucket. Zero new
concepts.

Hash-keyed: a blob is garbage when nothing references its hash. The
referencing sets, from the live schema: `entries.content_hash`
(`rows.py:347` — and trash rows are ordinary entries rows, so a
`NOT EXISTS` against entries covers trash automatically),
`versions.content_hash` (`rows.py:388`), and — if media derived-text ever
hashes against the blob — `chunks.content_hash` (`rows.py:410`). A
dangling-blob check is therefore two (or three) `NOT EXISTS` probes per
candidate hash, chunked by `membership_budget`.

The race is the killer, and the live tree documents it against itself
(§0.3): writes are not serialized with topology. Between the sweep
transaction's dangling scan and its blob delete, a rival write can (a)
insert a new entry pointing at hash H, or (b) run its own
insert-if-absent for H, observe the existing row, skip the insert — and
then the sweep deletes H, committing a dangling pointer. Git's prune
solves the same shape with an mtime grace window. The SQL analogues, in
descending order of honesty:

1. **Grace window**: blob rows carry `created_at` (and ideally
   `last_referenced_at`); GC only collects blobs older than a window that
   dominates any transaction lifetime. Cheap, portable, and it converts
   the race into a bounded staleness — but "last_referenced_at" must be
   touched by insert-if-absent hits, which is a write on the dedup fast
   path.
2. **Serialize blob writes with sweep**: make the blob insert take the
   per-mount serialization point (`topology.py:456-470`). This repeals the
   designed write/topology concurrency for every media write — a 10k
   media ingest would exclude all deletes/moves for its duration. Against
   the production posture (high-concurrency agents + bulk ETL sharing the
   mount), this is a regression dressed as a fix.
3. **Transactional refcounts**: a counter column maintained by every
   write/purge. Correct, but every dedup hit updates the *same* hot row —
   10,000 files sharing one logo image is 10,000 updates to one row, a
   serialization funnel and a deadlock generator precisely on the
   catch_retry engines (`dialects.py:122-151`), and refcount decrements
   would have to thread through `_purge_subtree`'s retry loop.

The memo should price hash-keying as "content addressing **plus a grace-
window GC verb**" — the sweep verb does not absorb it; a new
`sweep`-adjacent pass (or an arm of sweep that runs after bucket purges)
scans blob candidates. Composition with the 90-day sweep is otherwise
clean: purging a bucket deletes the entries/versions rows, which is what
*makes* blobs dangling; blob GC is downstream of sweep, never inside it.

### 2.4 Verdict shape

Entry-keyed is the extension of the existing segmentation move — every
lifecycle chokepoint already handles it, at the price of byte duplication
on copy and per-version, plus the unchanged-hash rewrite hazard.
Hash-keyed wins copy (inside the serialized section — the strongest
point), versions, and idempotent overwrite, at the price of a mandatory
GC design with a documented race against the tree's own concurrency
doctrine, an arbitration story per dialect, and a model-less table with
no drift guard. A defensible hybrid the memo should weigh: **entry-keyed
now** (all chokepoints close), with the blob table carrying `content_hash`
as a non-key column so a later migration to hash-keying is a data motion,
not a schema break.

## 3. The exclusivity rule: what text XOR media must touch (deliverable c)

`CONTENT_KINDS` (`entry.py:43`) currently does at least four jobs:

| Site | Job | Media wants |
|---|---|---|
| `reads.py:255` | refuse content-read of non-content kinds | refuse *text* read of media, serve bytes |
| `writes.py:684` | route staged content to the content table | route to blob channel instead |
| `editing.py:36-38` | refuse edits on non-content kinds | refuse edits on media unconditionally |
| `entry.py:430-431` | null `size_bytes` on non-content observations | keep `size_bytes` for media |

No single membership set satisfies that column of "wants": if media is a
new kind outside `CONTENT_KINDS`, its `size_bytes` gets nulled and stat
lies; if media stays kind `file` inside it, text reads and edits admit it.
**The set must split** — roughly a text-channel set (read/edit/content-
routing) and a sized set (metrics) — or exclusivity must be carried by a
field/mime discriminator that all four sites consult. The four sites are
the complete storage-side enforcement surface; everything else is the
model's (`editing.py` docstring states the doctrine: the model owns
content invariants, `editing.py:1-8`).

Model-side, the rule lands in three places: `_derive_identity`'s
arbitration table grows a media column (explicit text content + media
mime = contradiction, `entry.py:171-191`); `_derive_and_measure` must
*not* normalize a media entry's absent text to `""`
(`entry.py:223-224` — fact §0.2, the single most load-bearing line);
and metrics split — `size_bytes`/`content_hash` from bytes, `lines`
never computed (`entry.py:118-126` assumes `.encode()` of a str; a bytes
channel hashes raw bytes, which also keeps version-hash semantics
coherent per §2.2). `with_content` needs a bytes twin or a refusal
(`entry.py:304-327`). `Observation.content: str | None`
(`entry.py:389`) stays text-only; the wire-format memo's typed blocks
handle projection.

Storage enforces nothing the model doesn't already state — mirroring
today's division: `_replace_content`'s gate is routing, not validation.

## 4. What pack does with media versions (deliverable d)

Pack is unlanded (§0.1; `rows.py:379-381` describes it prospectively as
"the batch pack verb rewrites cold ranges into snapshot-every-N + forward
diffs"). The versioning provider is irreducibly text-shaped: `difflib`
over `str.splitlines` (`versioning.py:48-67`), `unidiff` replay
(`versioning.py:70-113`), snapshot cadence in `create_version`
(`versioning.py:145-174`). Bytes cannot enter it — not "diffs are poor",
but type-unrepresentable.

Consequences: with entry-keying, media versions are permanently
snapshot-only and pack must **skip media entries entirely** (a
kind/mime/channel filter in its cold-range scan) — packing them would be
a no-op that still pays the scan. With hash-keying, media versions are
already references and pack is vacuous for them by construction — the
cleaner outcome. Either way the memo can record: *pack's contract gains a
clause ("text channel only"), not a binary diff engine.* Binary delta
(xdelta/bsdiff-shaped) is a possible future provider behind
`VersionProvider` pluggability (`versioning.py:1-13`) but nothing in the
live tree asks for it.

## 5. Invariants a blob table could silently break (deliverable e)

1. **The drift test protects only modeled fields.** An entry-keyed blob
   field must join a declared homed-fields constant or
   `test_entries_columns_are_the_resident_fields_plus_row_only` fails
   loudly (`tests/test_rows.py:69-71`) — good. A hash-keyed table has no
   model, so *nothing* pins its columns — the same (deliberate) hole
   `posting_list` lives in. Not a violation, but a forfeited guard the
   memo should name.
2. **`size_bytes` is 32-bit.** `Integer` on entries (`rows.py:351`),
   versions (`rows.py:390`) — an implicit 2 GiB ceiling (2,147,483,647)
   *below* several engines' LOB caps. Either the declared per-row blob
   cap sits comfortably under 2^31 (it should, per §1.3's memory
   multiplication) or these columns migrate to `BigInteger`. A blob
   landing without this decision overflows silently on the first >2 GiB
   write on engines that don't range-check binds.
3. **One-canonical-join**: `content_joined` is *the* join
   (`rows.py:288-290`). Two sidecars = either a three-table canonical
   join (every content-projected read drags a LOB table into the plan on
   every engine, including Oracle where LOB locators change fetch
   behavior) or two joins selected by channel — which requires the
   channel to be knowable *before* the join is built, i.e. from the
   projection/params, not the fetched row. The exclusivity discriminator
   (§3) is what makes the two-join answer well-defined; without it the
   rule quietly becomes "always join both".
4. **Metadata-writes-never-rewrite-content** (`rows.py:334-337`,
   `rows.py:82-84`) survives trash/restore/move untouched (§1.6) but is
   *violated in spirit* by `_replace_content`'s unconditional
   delete-then-insert on unchanged content — invisible at text sizes,
   material at blob sizes (§1.4). The invariant's blob-era phrasing
   should be "an unchanged hash rewrites no blob row", which entry-keying
   must implement and hash-keying gets structurally.
5. **The whole-method retry discipline** (`backend.py:19-25`) demands
   every blob statement be re-runnable from the top: delete-then-insert
   and insert-if-absent qualify; refcount arithmetic does not compose
   with it cleanly (§2.3.3) — one more reason the refcount arm loses.
6. **Chunks as the derived-text home** (brief Q6 seam): `chunks` rows are
   entry-keyed with a NOT NULL text body and an embedding column
   (`rows.py:398-417`) — structurally ready to carry OCR/transcript text
   for a media entry with zero schema change. But `Chunk` requires
   `line_start >= 1` line ranges (`chunk.py:43-44, 67-68`) whose meaning
   for media is undefined (pages? seconds?), and chunk staleness is
   keyed to content rewrites the media entry's *blob* channel performs —
   the `embedding IS NULL` staleness convention (`rows.py:401`) still
   works, but the invalidation trigger must listen to the blob pass, not
   `_replace_content`.

## 6. Answers, compressed against the brief's numbers

- **Q1 (blob home/keying)**: both keyings attach cleanly to the write
  path; they diverge at copy (hash wins decisively, §1.6) and at GC
  (entry wins decisively, §2.3). Entry-keyed-now with a resident hash
  column is the migration-preserving position. `content_hash` exists on
  every referencing table already.
- **Q2 (dialect physics)**: the byte-denominated flush budget is real and
  is a *new axis* — nothing in `dialects.py` or `rows_per_statement`
  measures payload bytes today (§1.4). It is doctrine-compatible: a
  declared `DialectProfile` field for a fact SQLAlchemy doesn't model.
- **Q3 (ceilings/escape hatch)**: the ceiling is coupled to the 10k batch
  by staging memory (cap × 10,000, §1.3) and bounded above by the
  `Integer` metrics columns (2 GiB, §5.2). The `external_id` hatch exists
  but copy drops it (§1.6) — declare-and-defer must at least record that
  seam.
- **Q4 (binary versioning)**: unconstrained by executing code (nothing
  mints versions yet), constrained by the Version model's payload XOR
  (§2.2). Snapshot-only under entry-keying; reference rows under
  hash-keying with a model change. Pack skips media either way (§4).
- **Q5 (exclusivity)**: model-owned, storage-routed — but only after
  `CONTENT_KINDS`' four jobs are split (§3) and the empty-string
  normalization is carved out (§0.2). This is the largest *model* change
  in the story; the storage change is mechanical after it.
- **Q6 (derived text)**: chunks-on-the-media-entry is the zero-schema
  home with two real frictions: line-range semantics and staleness
  wiring to the blob pass (§5.6).
