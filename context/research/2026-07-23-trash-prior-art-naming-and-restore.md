# Trash prior art — in-trash naming, restore flow, and collision semantics

- **Date:** 2026-07-23
- **Status:** verified 2026-07-23 — JuiceFS, Plan 9, agentfs, and MinIO
  sections cited against the local checkouts by the researchers;
  Windows, macOS, freedesktop, HDFS, and cloud sections summarize
  public specifications and upstream source fetched over the web
  (flagged inline where the claim is behavior-observed rather than
  spec-pinned)
- **Method:** five parallel researchers, one per school — Linux
  desktop (freedesktop spec, GIO, trash-cli), macOS, Windows, the
  Plan 9/Unix/snapshot heritage, and storage-layer systems (JuiceFS,
  HDFS, S3/MinIO, Drive/Dropbox, agentfs) — each briefed on the same
  three design questions; synthesized here
- **Question:** the landed delete verb renames a trashed row to its
  bare ULID inside an hourly bucket. Three concerns raised in the
  2026-07-23 session: (1) the in-trash name is meaningless — how do
  users and agents browse trash and know what a file was? (2) how does
  an agent locate the right row to restore, and restore it? (3) what
  happens when two files with the same name are deleted — in trash,
  and again at restore time when the original site is occupied or its
  parent is gone?
- **Prior memo:** `2026-07-18-trash-namespace-parity.md` settled
  *visibility and writability* (trash is a normal subtree — ADR 014).
  This memo covers the complementary axis: *naming, restore, and
  collision semantics*.

## Bottom line

The field splits into three schools — **move the row** (Windows,
freedesktop, macOS, JuiceFS, HDFS), **flag the row** (S3 delete
markers, Drive/Dropbox, ORM `deleted_at`), and **snapshot the world**
(Plan 9 dump, ZFS/NetApp, VMS versioning). Within the move-the-row
school, opaque in-trash names are fully precedented (Windows renames
to random tokens; freedesktop *mandates* that the in-trash name never
be treated as meaningful) — **but only behind a presentation layer**
(Explorer, `trash-list`) that reconstructs the human view from
metadata and that users never bypass. The systems whose trash is
browsed *raw*, as vfs's is (ADR 014), all keep the original name
visible in the entry: JuiceFS (`<parentIno>-<ino>-<origName>`), HDFS
(full original path preserved under the trash root), macOS (original
name, mangled only on collision). vfs's bare-ULID name combines
Windows-camp naming with JuiceFS-camp raw browsing — the mismatch
behind concern (1). The fix the prior art points to is JuiceFS's
shape: a name that is unique *and* self-describing
(`<ULID>-<original_name>`). On restore, the field is unanimous:
refuse an occupied original site by default; disambiguate multiple
candidates by deletion time; and pick an explicit policy for a
missing original parent (recreate-the-chain — Windows, Finder,
trash-cli — or fail-and-keep — JuiceFS). In-trash same-name
collisions are a solved non-problem under any unique-token scheme.

## 1. Windows — the closest cousin to the bare-ULID design

*(Public format documentation and forensic-tool sources; the `$I`
layout is de-facto stable and parsed by rifiuti2/RBCmd.)*

- `\$Recycle.Bin\<SID>\` per volume, per user. Each deletion becomes
  a **pair**: `$R<random6>.<ext>` (the payload, renamed in place) +
  `$I<random6>.<ext>` (a small binary sidecar), joined by the shared
  random token. Same-name collisions are a non-issue by construction
  — ten deleted `report.docx` become ten distinct random tokens.
  This is exactly the ULID move.
- **The extension is deliberately preserved** on both opaque names,
  so type association, icons, and preview work without opening the
  sidecar. An opaque name need not be *fully* opaque.
- The `$I` sidecar holds original full path, original size, and
  deletion FILETIME. Version 1 (Vista–8) fixed the path field at 520
  bytes (MAX_PATH) and had to be revved to a length-prefixed version 2
  (Win10+) to lift the cap — a lesson about hardcoding path-length
  assumptions into a stored format.
- **Explorer never shows the token.** The bin is a shell view that
  reads every `$I` and renders Name / Original Location / Date
  Deleted. The opacity is survivable only because no user browses the
  directory raw.
- **The INFO2 cautionary tale:** pre-Vista Windows kept one
  centralized index file per bin; a single corruption orphaned every
  item's metadata, and every delete contended on the shared file.
  The per-item `$I` redesign fixed both. Per-item restore metadata —
  vfs's row columns — is the modern shape.
- Restore reads the `$I` path and moves back; **original parent gone →
  Explorer recreates the directory chain**; **name occupied → prompt
  (replace / skip / keep-both)**, never a silent overwrite. Eviction:
  per-volume size quota, oldest-first purge; an item larger than the
  whole quota bypasses trash after a prompt.

## 2. freedesktop / Linux — the metadata-projection doctrine

*(Trash Specification v1.0 plus GIO and trash-cli source, fetched
upstream.)*

- `Trash/files/` (payloads) + `Trash/info/` (one `.trashinfo` INI per
  item: `Path=` URL-encoded original, `DeletionDate=` local ISO-8601).
  Spec text: *"A filename in the `$trash/files` directory MUST NEVER
  be used to recover the original filename; use the info file for
  that."* The in-trash name is normatively meaningless — vfs's
  three columns are strictly richer than the sidecar, and indexed.
- In-trash collision handling is a **probe loop**: keep the original
  basename, and on `EEXIST` insert a counter (GIO: `foo.2.txt`;
  trash-cli: `foo_2`, falling to a random suffix past 99), retrying
  `O_EXCL` creates until one lands. A unique-token scheme obviates
  the entire loop.
- **`trash-restore` is the reference agent-facing flow:** filter by
  original path substring → print one row per candidate as
  `index  deletion-date  original-path` (same path deleted twice =
  two rows split by date) → caller picks index/list/range → move
  back, delete the sidecar. **Deletion time is the universal
  disambiguator.**
- Restore policy (restorer.py, verbatim behavior): destination
  occupied → refuse (`IOError`) unless `--overwrite`, and never
  overwrite a directory; **missing parents → `mkdirs` recreates the
  chain silently**. GVFS restore behaves the same.
- Known structural weakness: `files/` and `info/` are updated
  non-transactionally, so crashes orphan sidecars or strand payloads;
  every client carries defensive skip logic. vfs's
  reparent-plus-metadata-in-one-row-update is immune by construction.

## 3. macOS — name-preserving trash, fragile sidecar restore

*(Community/support documentation and forensic writeups; the
`.DS_Store` put-back records are reverse-engineered, corroborated
across independent sources.)*

- `~/.Trash` and per-volume `.Trashes/<uid>`; trashing is a
  same-volume rename. **The original name survives in trash**;
  a same-name collision inserts the wall-clock time into the name
  (`report 3.42.31 PM.txt`), plus an integer if that still collides —
  proof that "unique and readable" is achievable, though Apple's
  disambiguator is lossy and can itself collide, where a ULID cannot.
- "Put Back" metadata (`ptbL`/`ptbN` records — original path and
  name) lives in the **Trash folder's `.DS_Store`**, written only by
  Finder, asynchronously. The documented consequences: `mv`'d and
  API-trashed files have no Put Back; racing multi-file trashes lose
  records; entries purge on reboot. **The whole failure class is
  "restore metadata decoupled from the move"** — vfs writing
  `original_parent_id`/`original_name`/`deleted_at` in the same
  transaction as the reparent is the structural fix, and the landed
  batch-fails-whole rule means a failed restore cannot strand a row
  with cleared metadata.
- The API lesson: because trashing may rename,
  `trashItem(at:resultingItemURL:)` **returns the item's final
  in-trash URL**. The deleting caller learns where its file went
  without a search.
- Put Back recreates a missing parent chain; an occupied target gets
  the standard conflict prompt. iCloud/Photos "Recently Deleted" is
  the contrasting flat-TTL model: 30-day auto-purge, no hierarchy, no
  original-location restore.

## 4. JuiceFS — the near-exact cousin (verified against the local checkout)

The one production SQL/KV-metadata filesystem in the pool, and the
system vfs's landed design already mirrors bucket-for-bucket:

- Trash root `.trash`, buckets named
  `time.Now().UTC().Format("2006-01-02-15")` → `YYYY-MM-DD-HH`,
  identical to vfs's hourly bucket.
- **Trash-entry naming** (`pkg/meta/base.go:3053`,`trashEntry`):
  `"<parentIno>-<ino>-<origName>"`, truncated at MaxName with a
  warning. Unique via the inode it already owns, self-describing via
  the embedded original name, groupable by the parent prefix
  (`find .trash -name '3-*'` = "everything deleted from dir 3").
  A deep `rmr` flattens every node into the bucket, each entry
  carrying its own encoding.
- **Restore** (`cmd/restore.go`): splits the entry name on `-` into
  (parent, inode, name), renames back with
  `RenameNoReplace|RenameRestore`. **Occupied target → `EEXIST`,
  counted as a conflict, row stays in trash** (`cmd/restore.go:144-146`);
  **parent gone → `ENOENT`, counted as failed, row stays in trash** —
  no parent recreation. `--put-back` distinguishes re-nesting inside
  the bucket from moving trees home.
- **Expiry keys off the bucket directory name** (`CleanupTrashBefore`,
  `base.go:3132`): parse each child of `.trash` as `2006-01-02-15`;
  aged buckets are emptied and removed wholesale; unparseable
  children are warned and skipped forever. No per-row timestamp scan
  — the bucket *is* the retention index. This ratifies vfs's hourly
  bucket as the expiry primitive (vfs additionally stores exact
  `deleted_at` per row, which JuiceFS lacks).

## 5. HDFS — the path-preservation school

*(Apache Hadoop `TrashPolicyDefault.java`, fetched from trunk.)*

- Deletion moves to
  `/user/<name>/.Trash/Current/<original-absolute-path>` — the
  **entire original hierarchy is reconstructed under the trash root**,
  so the entry is self-documenting and restore is a plain `mv` back;
  no sidecar, no encoding.
- Collision on the preserved path: append `Time.now()` (epoch ms) and
  retry — a timestamp suffix, the flat-trash disease in miniature.
- Retention: `Current` is renamed to a timestamped checkpoint sibling
  on an interval; the emptier drops whole aged checkpoint directories
  — the same O(buckets) expiry as JuiceFS, achieved by rotating the
  live directory instead of pre-bucketing.

## 6. The snapshot school — Plan 9, ZFS/NetApp, VMS

*(Plan 9 verified against the local checkouts —
`sys/man/1/yesterday`, `rc/bin/yesterday`, `fossil/dump.c`.)*

- **Plan 9 has no trash.** `rm` is permanent; the dump filesystem
  snapshots the whole namespace daily to `/n/dump/YYYY/MMDD/<path>`
  (fossil builds `archive/%d/%02d%02d`; finer-grained snapshots take
  `/snapshot/YYYY/MMDD/HHMM/`). `yesterday(1)` maps a live path to
  its dump path by pure string prefixing; `-c` copies it back.
  Retrieval is **(time, original path)**: names never go opaque and
  collisions are structurally impossible because the namespace is
  preserved, not pooled.
- NetApp `.snapshot/hourly.N/<path>` and ZFS `.zfs/snapshot/<name>/`
  are the production restatement — and they answer *modification*
  recovery ("Tuesday's bytes") as well as deletion, which no trash
  can.
- VMS Files-11 is the fourth shape: versions beside the file
  (`foo.txt;3`), `DELETE` drops only the newest, `PURGE` reaps.
  Disambiguation by monotonic version instead of timestamp.
- The classic-Unix `alias rm='mv … ~/.trash'` culture is the negative
  precedent: a flat pool keyed by name, clobbering same-named files
  or accreting `foo.1`/`foo.2` — the disease unique tokens cure.
  Purdue's `entomb` (syscall-shim trash, ≤24 h retention, `unrm`)
  is the closest classic ancestor: a short-horizon oops-buffer
  explicitly backed by real backups for everything older.

## 7. The flag school — S3, Drive/Dropbox, ORM soft delete, agentfs

- **S3 versioning + delete markers** (MinIO implements natively —
  `xlMetaV2DeleteMarker` in the local checkout): nothing moves;
  delete writes a tombstone version at the same key; restore removes
  the tombstone; lifecycle rules expire non-current versions. No
  naming problem, no collision problem — at the cost of a version
  dimension on every read.
- **Google Drive / Dropbox:** a `trashed` flag; the row keeps its
  name and parents; trash is a query, not a place; restore by file id
  (`files.untrash`); 30-day auto-purge. Drive's `explicitlyTrashed`
  distinguishes direct deletion from trashed-via-ancestor.
- **ORM `deleted_at`:** never moves the row; every live query carries
  `WHERE deleted_at IS NULL`, and the `(parent_id, name)` uniqueness
  constraint must become partial or include `deleted_at` — the flag
  school's collision problem is *live-vs-deleted rows fighting over
  the unique index*, which the physical move sidesteps entirely.
- **agentfs** (local checkout, `SPEC.md`): hard delete plus
  whole-database snapshot/rollback and an append-only audit log — the
  nearest agent-audience peer chose coarse rollback over granular
  trash; no naming precedent to borrow.
- SeaweedFS, OpenDAL, PyFilesystem2, Jackrabbit Oak: grep-confirmed
  **no trash concept** (SeaweedFS's `Trash` hits are macOS FUSE
  passthrough).

## 8. Synthesis — answers to the three questions

**Q1, the meaningless name.** Opaque physical names are sound —
Windows and freedesktop prove it — *if and only if* every browse goes
through a metadata projection. ADR 014 pinned raw browsability, so
vfs sits in the JuiceFS/HDFS/macOS camp, where every shipped system
keeps the original name in the entry. The convergent sweet spot:
**physical move for clean live indexes + a unique-token-prefixed,
name-suffixed in-trash name + metadata columns as the authority.**
The token stays the authority (freedesktop's MUST-NEVER rule still
applies — the readable suffix is display, never parsed truth), and
the extension riding along restores what Windows preserved
deliberately.

**Q2, agent locate-and-restore.** Three convergent mechanisms:
(a) the delete itself returns the in-trash location (Apple's
`resultingItemURL`); (b) listing/query by
(`original_parent_id`/original path, `deleted_at`) — indexed columns
where every filesystem implementation scans sidecars; (c) a restore
addressed by the recorded original site (JuiceFS/Drive restore-by-id)
rather than requiring the caller to reassemble a move. Multiple
candidates for one original path split by `deleted_at`; the ULID is
the exact address when the caller has it.

**Q3, same-name deletes.** In trash: solved — unique tokens make the
freedesktop/macOS probe-and-suffix loops unnecessary; unanimous. At
restore: **refuse an occupied original site by default** (JuiceFS
`RenameNoReplace`, trash-cli `IOError`, Explorer/Finder prompt;
nobody silently overwrites) with an explicit overwrite opt-in — the
landed move ladder's `exists` refusal already matches. Missing
original parent forks the field: recreate-the-chain (Windows, Finder,
trash-cli) vs fail-and-keep (JuiceFS). The landed move's
destination-parent gate is the JuiceFS behavior; recreation is an
additive affordance, not a correctness fix.

**Retention (bonus finding).** Hourly buckets as the expiry key is
proven practice (JuiceFS parses bucket names and drops whole aged
buckets; HDFS drops aged checkpoints); per-row `deleted_at` is
display/audit. Windows adds the other production posture: a declared
size bound with observable oldest-first eviction, plus the
oversized-item bypass. Policy numbers are an open question, not
research.

**The conscious rejections.** The flag school dissolves Q1–Q3 by
construction but taxes every live query and the unique index — the
physical move keeps the hot path clean and pays with exactly the
naming/restore questions this memo answers. The snapshot school is
strictly more capable (delete *and* modification recovery, names
never opaque) but whole-namespace snapshots in SQL are real write
amplification; vfs's trash should be framed as **cheap delete-undo,
not time-travel**, so the hourly buckets are never mistaken for a
snapshot capability.

## Sources

- Local checkouts (verified by researchers): `~/Git/Repos/juicefs`
  (`pkg/meta/base.go` trashEntry/CleanupTrashBefore,
  `cmd/restore.go`), `~/Git/Repos/plan9` and `plan9port`
  (`yesterday` man/rc, `fossil/dump.c`), `~/Git/Repos/agentfs`
  (`SPEC.md`), `~/Git/Repos/minio` (`cmd/xl-storage-format-v2*.go`)
- freedesktop Trash Specification v1.0; GIO `gio/glocalfile.c`;
  trash-cli source (`put/suffix.py`, `restore/restorer.py`,
  `restore/handler.py`)
- Windows `$I`/`$R` format via rifiuti2 technical docs and forensic
  writeups; `SHQueryRecycleBin`; The Old New Thing (quota defaults)
- Apple: `trashItem(at:resultingItemURL:)` docs; openradar #6452;
  `Mac::Finder::DSStore` format notes (`ptbL`/`ptbN`,
  reverse-engineered); Apple Support (Recently Deleted)
- Apache Hadoop `TrashPolicyDefault.java` (trunk); Cloudera HDFS
  trash docs
- Google Drive API (`files.untrash`, `trashed`/`explicitlyTrashed`);
  Dropbox deleted-files/retention docs
- Purdue ECN entomb/unrm docs; NetApp ONTAP snapshot-restore KB;
  OpenVMS DELETE/PURGE references
- Prior vfs context: `2026-07-18-trash-namespace-parity.md`;
  `decisions/014-trash-normal-fs-parity.md`;
  `decisions/019-ulid-referential-identity.md`
