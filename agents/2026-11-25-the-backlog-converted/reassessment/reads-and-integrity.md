# Reassessment against dev: 176-the-listing-cursor, 178-the-ranged-read, 175-integrity-verify-on-read-and-scrub

Read on 2026-11-25 against `origin/dev` at `27f3d24d` (EXECUTED, `git rev-parse --short=8 origin/dev`), in a checkout that holds all of dev (EXECUTED, `git rev-list --left-right --count HEAD...origin/dev` prints `15 0`), with the open branches of `agents/2026-11-25-the-backlog-converted/dev-index.md` read by `git show` and `git diff origin/dev...<branch>` and never checked out. The unit map and the three studies were written against `0ed462f`; the two drafts that exist, `agents/2026-11-25-a-read-refuses-a-body-that-fails-its-recorded-hash/spec.md` and `agents/2026-11-25-ls-tree-and-glob-page-on-a-path-key-served-by-a-derived-page-in-the-router/spec.md`, read code at `5b20fd4f`, a docs commit on `0ed462f`'s line that dev does not contain (EXECUTED, `git merge-base --is-ancestor 5b20fd4f origin/dev` fails). Labels: EXECUTED (a command ran), READ (path:line at HEAD, or branch:path:line), INFERRED (reasoning from the two).

In one line: the listing cursor is built on dev except its third unit, which dev already holds as a spec; the ranged read and integrity are still unbuilt on dev and on every open branch, and the roadmap on dev still lists both as missing (READ, `context/standards/roadmap.md:95`).

## 176-1. `ls`, `tree` and `glob` take `after=` and `limit=` and return the last row's path as `Result.next_after`, paged correctly across every mount for every backend

Verdict: built-on-dev.

What covers it. The work directory `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md` landed it as slice A, commit `702d9615`, with the review answered in `2ebca5fe` (EXECUTED, `git log -- src/vfs/cursor.py`); the roadmap marks story K4 built, pull request 35 (READ, `context/standards/roadmap.md:168`).

The arguments are on all four faces: the router's `ls`, `tree` and `glob` (READ, `src/vfs/base.py:847`, `:884`, `:1297`, with `after` and `limit` at `:853-854`, `:888-889`, `:1308-1309`), `AsyncSession` (READ, `src/vfs/session.py:119`, `:134`, `:282`), `VirtualFileSystem` (READ, `src/vfs/sync.py:287-298`, `:301`, `:453`) and the synchronous `Session`, which now lives in its own module (READ, `src/vfs/sync_session.py:98`, `:109`, `:233`). `PARAMS` carries `_AFTER` and `_LIMIT` (READ, `src/vfs/params.py:144-145`, `:171-172`, `:179-180`, `:285-286`).

`Result.next_after: Path | None` is a declared field with its algebra, rebase and overflow rule (READ, `src/vfs/results/envelope.py:352`, `:367`, `:694-739`), and the renderer prints `more: after=<key>` only when it is set (READ, `src/vfs/results/render.py:72`).

The derived page in the router that serves every backend is `Cursor` (READ, `src/vfs/cursor.py:46`, `:110`, `:124`), with the frontier rule `frontier_page` (READ, `src/vfs/results/paging.py:49`, `:101-109`) and `local_after` for the key in a mount's coordinates (READ, `src/vfs/paths.py:368`). The cursor contract runs as a conformance family of 31 tests (READ, `tests/support/cursor_contract.py`; EXECUTED, `grep -c "def test_"`). The landing ruled no kernel default page, so `limit=None` lists every row, and `glob` refuses a page beside `max_count` or `observations` (READ, the work directory's spec, "How the three choices were taken" and "What was built").

What is not in it, and is not this unit: the corrections at a mount point are a separate unbuilt draft on dev, `agents/2026-11-21-a-listing-at-a-mount-point-is-read-again/spec.md` (READ, its line 3, "nothing is built"), and paging was built on the rule as it stands; the pages under `documentation/` that say how a listing pages are a separate unbuilt draft, `agents/2026-11-21-the-docs-say-how-a-listing-pages/spec.md` (READ, its line 3). The fronts (shell, MCP, guests) were left to their own work; the shell's paging is specified on dev in `agents/2026-11-22-shell-file-reads-and-metadata/spec.md` decision 3 (READ).

Draft: discard. The draft at `agents/2026-11-25-ls-tree-and-glob-page-on-a-path-key-served-by-a-derived-page-in-the-router/spec.md` specifies what dev already built, and it states that no statement changes (READ, its flags line), where dev built the native pages too.

Remaining: nothing. New dependencies: none; units that named 176-1 (167-5, 171-1, 179-10, 180-1, 180-5) name the landed work directory instead (INFERRED).

## 176-2. On every engine a listing page costs a fixed number of statements and visits at most `limit + 1` live rows, however many deleted rows share its directory

Verdict: built-on-dev.

What covers it. The same work directory landed it as slice B, commit `f36595fe` (EXECUTED, `git log -- src/vfs/storage/backends/database/keyset.py`). "Every engine" is now SQLite and Postgres, since dev serves those two only (READ, `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`). The native pages are in `ls_rows`, `tree_rows` and `_ls_page` (READ, `src/vfs/storage/backends/database/listings.py:74`, `:142`, `:221`), with the fill rule in `keyset.py` (READ, `src/vfs/storage/backends/database/keyset.py:59`) and the paged branch of `glob_rows` (READ, `src/vfs/storage/backends/database/reads.py:497`). The page seeks two partial indexes over live rows, `ix_vfs_entries_live_children (parent_id, name)` and `ix_vfs_entries_live_path (path)`, both `WHERE deleted_at IS NULL`, and the tombstone index became partial on `deleted_at IS NOT NULL` (READ, `src/vfs/models/rows.py:138-139`, `:441-444`); `SCHEMA_FORMAT_VERSION` is 28 (READ, `rows.py:135`). SQLite is pinned to the live index by `INDEXED BY`, declared as `live_index_hint` (READ, `src/vfs/storage/backends/database/dialects.py:343`, `:409`). The trait is `listing_cursor: keyset` (READ, `src/vfs/storage/protocol.py:86`, `:98`; `src/vfs/storage/backends/database/backend.py:248`).

The index choice the unit map tied to the deletes spec was taken by measurement instead: spec 176's composite indexes were never picked by Postgres 16, and the partial indexes were (READ, `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/research.md`, title line, and the spec's landing notes, choice 2). The deletes spec on the open branch keeps both partial indexes "as they are, with their names and their pins" and adds its generation key beside them (READ, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md:33`, `:146`), so the generation key does not replace the live listing's index as the study foresaw (INFERRED).

Two listings are named in the module docstring as not bounded this way: the trash view's, whose rows are tombstones, and a `tree` under `max_depth` (READ, `listings.py:13-17`). The first is the deletes spec's to state, and it does, as a stated profile with no cap (READ, the deletes branch spec `:304-306`); the second is 176-3.

Draft: none existed.

Remaining: nothing of this unit. The counts were measured on SQLite and Postgres 16.15 only; Postgres 15, 17, 18 and 19 were not run (READ, the landing notes, "Measured"); that is a test-matrix fact, not a unit (INFERRED). New dependencies: none; 176-3 names the landed work directory.

## 176-3. A `tree` with `max_depth` visits at most `max_depth × (limit + 1)` rows a page, because each row stores its depth beside its path

Verdict: specified-on-dev.

What covers it. Dev holds the spec `agents/2026-11-21-a-shallow-tree-page-reads-only-its-depth/spec.md`, a draft "not reviewed, and nothing is built" (READ, its line 3). Its decisions match the unit: a stored `depth` column written wherever `path` is written, including every row a move rewrites and a copy; a partial index `(depth, path) WHERE deleted_at IS NULL`; one stream per depth merged by the frontier rule and chunked by `arm_budget`. The roadmap names it as K4's slice C, left to its own spec (READ, `context/standards/roadmap.md:168`).

Not built. The depth term is still a residual filter on a slash count (READ, `src/vfs/storage/backends/database/listings.py:410-411`, `:577-579`), no `depth` column exists on `vfs_entries` (EXECUTED, `grep -n depth src/vfs/models/rows.py` finds only a comment at `:795`), and no open branch adds one (EXECUTED, the branch diffs against dev name no `depth` column; the deletes and vid branches change `rows.py` for `name_generation` and the vid, READ, the deletes branch spec `:130-150`).

Draft: none existed; dev's own spec replaces any conversion.

What remains: building dev's spec. Its two open items still stand: one statement per depth or one `UNION ALL`, and how the per-depth streams meet the subtree-range draft `agents/2026-11-21-postgres-reads-a-subtree-by-its-range/spec.md`, which is itself unbuilt (READ, its line 3). The gate is still unplaced on the roadmap (READ, `roadmap.md:168` names it a spec of its own and gives no gate).

New dependencies: in place of 176-2, the landed `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md`. The deletes spec on `origin/a-deleted-row-gives-up-its-path` and the vid series (`origin/every-row-carries-a-vid` and its successors) both bump the schema and both rewrite paths on a move (READ, the deletes branch spec `:545`), so whichever lands first sets the schema format the depth column follows, and the depth column's writers must include the deletes spec's revive-free create and its trash-path rows (INFERRED).

## 178-1. Each tuned dialect returns the exact bytes of a body slice, for `data` raw and for `content` as UTF-8, in one statement

Verdict: still-needed, smaller.

Nothing covers it. No `body_slice`, `BodySlice`, `read_range`, `range_start` or `range_length` exists under `src/vfs` (EXECUTED, `grep -rn` over `src/vfs`; the one hit is the compiled `_native.abi3.so`). No open branch adds one (EXECUTED, the branch diffs against dev). The roadmap on dev lists `read(range=)` as not built (READ, `context/standards/roadmap.md:95`), and story K6 is unchanged at gate b (READ, `roadmap.md:186-192`).

Still wanted. Dev's shell spec rides on it: "A prefix read such as `head -c 10 f` rides spec 178's public `read(range=)` when it lands (roadmap K6); until then an open reads the whole body" (READ, `agents/2026-11-22-shell-file-reads-and-metadata/spec.md:15`). The shell review measured the cost today: `head -c 10` on a 5 MiB file is one router read of 5,242,880 bytes (READ, `agents/2026-11-22-shell-review/reviews/verification.md:54`). The shell's own draft range contract, with a SQLite incremental blob reader and a Postgres byte projection, was withdrawn in favour of spec 178's (READ, the shell spec `:5`).

What changed on dev. The tuned dialects are SQLite and Postgres only, with the `GENERIC` floor for every other URL (READ, `src/vfs/storage/backends/database/dialects.py:360`, `:413`, `:449`). The Oracle inline `WITH FUNCTION` slice, its schema-function fallback, the SQL Server and MariaDB slices and their engine legs are moot. What remains is a SQLite slice over `content` cast to bytes (`content_bytes` is declared on SQLite, READ, `dialects.py:329`, `:386`) and over `data`, and a Postgres slice, where `vfs_blobs.data` is already `STORAGE EXTERNAL` so that a `substring` is a ranged fetch (READ, `src/vfs/models/rows.py:862-868`). The text column is `_body_text()` (READ, `rows.py:203`). `dialects.py` is 931 lines and no longer in the size baseline, while `reads.py` is held at 1,164 and `base.py` at 3,090 (EXECUTED, `wc -l`; READ, `tests/lint/allowlist.py:26-30`), so the study's note that all three files are ratcheted is now true of two (INFERRED).

Draft: none existed.

What remains: the whole unit, for SQLite and Postgres, with the `GENERIC` floor declaring no slice. With two engines and no Oracle fork to settle on its own leg, the reason the map gave for landing 178-1 apart from 178-2 (a unit that needs all four engine legs and lands with nothing calling it) is weaker, and 178-1 may fold into 178-2 at K6's size S (INFERRED).

New dependencies: none. The units that named 178-2 (167-8, 179-10) are unchanged.

## 178-2. `read(path, range=(offset, length))` serves the slice cut by the engine, snapped outward to whole characters on text, with `range_start` and `range_length` on the row, and a backend that cannot cut is served the range by the router

Verdict: still-needed.

Nothing covers it. `read` takes `path`, `observations`, `columns` and `authority` and no range on every face: the router (READ, `src/vfs/base.py:802-822`), `AsyncSession` (READ, `src/vfs/session.py:97`), `VirtualFileSystem` (READ, `src/vfs/sync.py:267`), the synchronous `Session` (READ, `src/vfs/sync_session.py:80`), the protocol (READ, `src/vfs/storage/protocol.py:143`) and `DatabaseStorage` (READ, `src/vfs/storage/backends/database/backend.py:259`). `PARAMS["read"]` has no range (READ, `src/vfs/params.py:156-161`). No open branch adds one (EXECUTED).

Still wanted, for the shell's `head` and `sed -n` (READ, roadmap K6 story, `roadmap.md:188`) and as the arguments K9's freeze list documents (READ, `roadmap.md:216`).

What changed on dev, for the amend of the source. The synchronous `Session` moved to `src/vfs/sync_session.py`, so the argument reaches four public faces, the protocol and the backend. The trait vocabulary now has eight keys, `listing_cursor` among them (READ, `protocol.py:78-98`), which is landed precedent for a one-valued trait a backend declares and the router derives for a backend that does not: the `Cursor` cuts a page for a storage without `listing_cursor` (READ, `src/vfs/cursor.py:46`; the landing notes of the listing spec, "What was built"). The router's fallback for a backend with no `read_range` can take the same shape (INFERRED). Spec 179's `features()` is still unbuilt (EXECUTED, no `features` method on `SupportsRead`; READ, `roadmap.md` K7 at gate f). The K6 byte bound against the six-byte text window (study choice 6) is not edited on dev (READ, `roadmap.md:189`, "at most 4,096 body bytes").

Draft: none existed.

What remains: the whole unit, restated for four faces, two engines and the `GENERIC` floor served by the router.

New dependencies: 178-1, as before. Coordination, not dependency: the vid series on `origin/every-row-carries-a-vid`, `origin/write-requires-a-vid`, `origin/edit-requires-a-vid` and `origin/delete-move-and-restore-require-a-vid` changes `reads.py` and the read row (READ, `git diff origin/dev...origin/every-row-carries-a-vid -- src/vfs/storage/backends/database/reads.py` adds `vid_at` and `VidMint`), and the deletes spec on `origin/a-deleted-row-gives-up-its-path` changes the trash view's rows to report their trash path (READ, that branch's spec `:381-393`); a ranged read of a trash row and the row's `vid` beside `range_start` follow whichever lands first (INFERRED). The consumer to name is dev's `agents/2026-11-22-shell-file-reads-and-metadata/spec.md`.

## 178-3. A ranged read of a body whose stored row is missing or whose whole-body slice fails its hash is classified as a whole read is, and a partial slice is treated as the integrity ruling says

Verdict: still-needed.

Nothing covers it: neither the ranged read (178-2) nor the integrity check (175-1) exists on dev or on an open branch (see those sections). The ruling it waits on is still open: roadmap rows D8 and D59 fix the kind and the salvage read and say nothing of a partial slice (READ, `context/standards/roadmap.md:1219`, `:1270`), and the kernel rulings spec rules nothing about a range (EXECUTED in the study; the spec is unchanged on dev, READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`).

Still wanted: K6 depends on K3 on the roadmap (READ, `roadmap.md:188`), and the shell turns an integrity refusal into an I/O error on an open (INFERRED from the shell spec's read-per-open design, `agents/2026-11-22-shell-file-reads-and-metadata/spec.md` decision 1).

Draft: none existed.

What remains: the whole unit, and the ruling (a partial slice served unverified with a note; the whole body hashed in the engine on every ranged read; or per-page hashes). With SQL Server gone, the study's SQL Server isolation premise does not bear on it (INFERRED).

New dependencies: 178-2 and 175-1, as before.

## 175-1. `read` checks every body it serves against its recorded hash and refuses a mismatched, missing or unhashed body with `vfs.unavailable.integrity`, unless the caller asks for the salvage read

Verdict: still-needed.

Nothing covers it. `ErrorKind` still has `unavailable`, `unavailable.backend` and `unavailable.schema` and no integrity child (READ, `src/vfs/results/kinds.py:94-96`), 24 kinds in all (EXECUTED, a count of `vfs.` members). No `unavailable.integrity`, `content_digest` or `verify=` exists under `src/vfs` (EXECUTED, `grep -rn`); the three direct `hashlib.sha256` calls remain (READ, `src/vfs/models/version.py:79`, `:84`, `:223`). `read` takes no `verify` on any face (READ, `src/vfs/base.py:802-822`, `src/vfs/params.py:156-161`). No open branch adds the kind: the vid series edits `kinds.py` only to add `vid` to the `conflict` and `exists` records (READ, `git diff origin/dev...origin/every-row-carries-a-vid -- src/vfs/results/kinds.py`), and no other branch names integrity (EXECUTED). The roadmap on dev lists "the hash check on read" as not built (READ, `roadmap.md:95`) and K3 is unchanged (READ, `roadmap.md:158-164`).

Still wanted: K3 at gate b, rulings D8, D58 and D59 decided (READ, `roadmap.md:1219`, `:1269`, `:1270`).

Draft: amend. The draft at `agents/2026-11-25-a-read-refuses-a-body-that-fails-its-recorded-hash/spec.md` read code at `5b20fd4f`, which is `0ed462f`'s code, and these facts changed on dev:

- Engines. The draft's criterion 38 runs the check on "the Postgres, MariaDB, SQL Server and Oracle legs" (READ, its line 319), its decision 8 argues from Oracle storing an empty string as `NULL` (READ, its line 122), its decision 10 names SQL Server as a cause of a torn join until the SQL Server spec lands (READ, its line 134), and its scale section counts statements at Oracle's floor (READ, its line 250). Dev serves SQLite and Postgres only (READ, `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md`); the legs become SQLite and Postgres, decision 8 keeps its body-key rule on its own merit (a design that reads presence off the body table's key, not off a `NULL` value) with the Oracle reason dropped, and decision 10's causes reduce to the `GENERIC` floor's undeclared isolation and an out-of-band writer caught between its own statements (INFERRED).
- The offload rule already has one owner. Dev factored it into `_measured` (READ, `src/vfs/storage/backends/database/writes.py:1378-1382`), which `measured_entries` calls (READ, `writes.py:143-169`), and edits hop through `call_offloaded` on their own (READ, `writes.py:310`). The draft's decision 2, which says "the offload rule has no owner" and adds `measure_all` to `offload.py`, is reshaped to move or reuse `_measured` (INFERRED).
- Lines drifted. `read_rows` is `reads.py:156` (draft `:155`), `_point_rows` is `reads.py:889` (draft `:817`), the retry seam is `backend.py:1357-1378` (draft `:1374-1388`), the router's `read` is `base.py:802` (draft `:904`), `VirtualFileSystem.read` is `sync.py:267` (draft `:279`), the synchronous `Session.read` is `sync_session.py:80`, the protocol's `read` is `protocol.py:143` (draft `:126`), `PARAMS["read"]` is `params.py:156` (draft `:140`) (READ, each). `reads.py` is held at 1,164 lines and `base.py` at 3,090 (READ, `tests/lint/allowlist.py:26-30`), not the counts the draft plans around (INFERRED, the draft cites the earlier baseline).
- The SQL Server spec it cites (`context/specifications/active/2026-11-15-on-sql-server-a-read-never-waits-on-a-write.md`) is still in `active/` and is moot with SQL Server dropped (INFERRED).

New dependencies: the two named are unchanged (the kernel rulings spec, whose roadmap edits are in the tree, and the archived measure spec). Coordination: the vid series changes `reads.py`, `backend.py` and the read row on every branch of the series (READ, the branch file lists in `dev-index.md` and `git diff --name-only`), and the deletes spec changes what the trash view returns (READ, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md:381-393`); both are reviewed and nearer landing than 175-1, so the amend rebases on them, and the check's rule for the trash view (the draft's decision 7) is restated against trash-path rows (INFERRED).

## 175-2. Every row `write`, `edit`, `copy` and `move` returns carries `content_hash`; `edit` refuses a damaged pre-image with `vfs.unavailable.integrity`; an overwrite of a damaged body succeeds with a warning and its version row keeps the recorded hash

Verdict: still-needed.

Nothing covers it. The re-read after a write selects `path`, `kind`, `version` and `size_bytes` and no hash (READ, `src/vfs/storage/backends/database/serialized.py:282-287`), and `observe_final` builds rows without `content_hash` (READ, `serialized.py:290-302`). On every vid branch `final_rows` adds `entry_id` and still no hash (READ, `origin/every-row-carries-a-vid:src/vfs/storage/backends/database/serialized.py:285-290`, the same on `write-requires-a-vid`, `edit-requires-a-vid`, `delete-move-and-restore-require-a-vid` and `the-kernel-writes-records-behind-and-sweeps-them`). `edited_entry` still answers `wrong_kind`, "no editable content", for absent content and checks no hash (READ, `src/vfs/storage/editing.py:35-40`).

Still wanted: K3 criterion 3 (READ, `roadmap.md:163`). One consumer moved: the session's stamps on dev are now a row's vid, version and hash, and the guard is the vid (READ, `agents/2026-11-22-the-session-remembers-what-it-read/spec.md:56`, `:361-364`), so K10 no longer needs the hash on every written row to guard a change (INFERRED); the shell host still asks every read for `content_hash` to tell two files apart (READ, that spec `:82`).

Draft: none existed.

What remains: the whole unit.

New dependencies: 174-1 is built on dev: an identical write reports `unchanged` and keeps its version (READ, `src/vfs/base.py:952`), landed by `agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md` (READ, `roadmap.md:146-148`, K2 "Built"); name that work directory in place of 174-1. 175-1 stays. The vid series rewrites the same `edit_rows`, `_finish` and `final_rows` paths on `origin/edit-requires-a-vid` and `origin/write-requires-a-vid` (READ, their file lists), and the deletes spec changes `copy` and `move` in `topology.py` (READ, the deletes branch spec `:545`); 175-2 builds after both (INFERRED).

## 175-3. Only the system actor can accept a body that fails its hash as it stands, which writes a new version whose `content_hash` is the body's own, so history records the acceptance

Verdict: still-needed.

Nothing covers it: no accept act, no system-actor-only repair verb or argument, exists on dev or on an open branch (EXECUTED, greps over `src/vfs` and the branch diffs). D58 is decided and unchanged (READ, `roadmap.md:1269`); its spelling, a verb of its own or an argument of an existing verb, is still unruled on dev (EXECUTED, no roadmap row or dev spec names it). The `lint` spec that took `scrub`'s place is still an unbuilt placeholder in `context/specifications/active/2026-11-15-lint-finds-what-is-broken-in-a-mount-and-changes-nothing.md` (READ), and `scrub` stays cut to 0.2 (READ, `roadmap.md:1182`), so slice D is still no unit here.

Draft: none existed.

What remains: the whole unit and the spelling ruling. One fact to weigh in it: the deletes spec on its branch spells a system-actor-gated act as a verb of its own, `destroy`, open to the system actor everywhere and to other callers only where `everyone_level` is `read_write`, and kept out of the `cli` tool (READ, `origin/a-deleted-row-gives-up-its-path:agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md:333-339`, citing D57), which is the nearest precedent on a branch for the spelling of a system-actor-only act (INFERRED).

New dependencies: 175-1 and 175-2, as before. Coordination: the vid series makes every new version carry a vid (READ, `dev-index.md`, the vid branches), so the acceptance's new version is minted through the vid mint once that lands (INFERRED).
