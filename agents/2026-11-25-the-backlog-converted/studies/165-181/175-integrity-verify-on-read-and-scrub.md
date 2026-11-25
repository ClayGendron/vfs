# Study: integrity, verify on read, the hash on write, and a report-only scrub

Spec folder: `context/specifications/active/175-integrity-verify-on-read-and-scrub/` (`spec.md`, `tasks.md`; no `plan.md`). Studied at HEAD `3166469` on 2026-11-25, one docs-only commit after the named `0ed462f` (EXECUTED, `git log --oneline -3`). Labels: EXECUTED (a command ran here), READ (read at path:line), INFERRED (reasoning).

## Verdict

Partly landed, and live at gate b for the rest. In the tree: the threshold's move to the models layer and a per-call offload rule for the write path, both from the archived spec `2026-11-07-storage-measures-every-body-it-stores.md`, though that rule is one hop per call, not the hop per blob page that §1.3 plans (READ, `src/vfs/models/version.py:60`, `src/vfs/storage/backends/database/writes.py:144-176`). Not in the tree: the `content_digest` hash law, the integrity kind, verify on read, `content_hash` on written rows, the edit's pre-image check and the mint's recorded-hash rule (slices A's remainder, B and C). Overtaken: slice D, `scrub`, which the active placeholder spec `2026-11-15-lint-finds-what-is-broken-in-a-mount-and-changes-nothing.md` replaces by the byte layer of a `lint` verb (READ, that spec's decision 1: "no `scrub` verb is added").

## Against the tree

The problem statement holds at HEAD. EXECUTED, a probe on a SQLite file through `AsyncVirtualFileSystem` and `DatabaseStorage` (scratchpad `175/probe.py`): a write's observation carries `{path, kind, size_bytes, version, status}` and no `content_hash`; after `UPDATE vfs_content SET content='ROTTEN'` a `read` returns `success=True` with `ROTTEN`; an `edit` of that rotten body succeeds; after the `vfs_content` row is deleted a `read` returns `success=True`, `content=None`; an `edit` of that file answers `vfs.wrong_kind`, "no editable content". These are rows 1, 7, 8, 10 and 11 of spec §0, all still true.

Hash law (§1.1): not built. `measure_text` and `measure_bytes` each call `hashlib.sha256` (READ, `src/vfs/models/version.py:79`, `:84`), and `Version.reconstruct` calls it a third time (READ, `version.py:223`). No `content_digest` exists (EXECUTED, grep over `src/vfs`).

Threshold home (§1.2): landed. `MEASURE_OFFLOAD_BYTES: Final = 100_000` is in `models/version.py:60`, exported from `vfs.models` (READ, `src/vfs/models/__init__.py:25`), and `base.py` imports it (READ, `src/vfs/base.py:51`, used at `:333` in `_authored_entry`, `:323`).

Offload rule (§1.3): partly landed in another form. `measured_entries` hashes every body of a write call inline when the call's bodies total under the threshold, and otherwise every body of the call in one `call_offloaded` hop (READ, `writes.py:152-170`). The archived spec's decision 3 chose that one-hop form and said spec 175 "then replaces `measured_entries`' hop with `measure_all`" (READ, `context/specifications/archive/2026-11-07-storage-measures-every-body-it-stores.md:3`, decision 3). No `measure_all` exists; `call_offloaded` lives in `src/vfs/offload.py:146` and `byte_chunked` in `src/vfs/batching.py:65` (EXECUTED, grep). The kernel rulings spec names this gap: "Spec 175's hop arithmetic and roadmap story K3's fourth criterion, which describe a rule the tree did not build: spec 175's conversion" (READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:144`).

The kind (§2): not built. `ErrorKind` has `unavailable`, `unavailable.backend` and `unavailable.schema` (READ, `src/vfs/results/kinds.py:92-94`) and no integrity child (EXECUTED, grep).

Verify on read (§3): not built. `read_rows` (READ, `src/vfs/storage/backends/database/reads.py:155`) and `_point_rows` (`reads.py:817`) observe rows with no hash comparison; the SQLite bytes cast the spec builds on exists (`profile.content_bytes`, READ, `reads.py:696`, `dialects.py:439`, `:503`).

Write side (§4): not built. `_finish` builds staged observations without `content_hash` (READ, `writes.py:347-390`); `final_rows` selects `path, kind, version, size_bytes` only (READ, `src/vfs/storage/backends/database/serialized.py:283-288`); `StagedEntry` has `base_version`, `base_size_bytes` and `base_content` but no `base_content_hash` (READ, `src/vfs/storage/backends/database/staging.py:78-80`); `_version_row` measures the pre-image it reads and stores that hash (READ, `src/vfs/storage/backends/database/versions.py:159-179`); `edited_entry` answers `wrong_kind` for absent content and validates inline (READ, `src/vfs/storage/editing.py:27-45`). `Observation` already declares a `content_hash` field (READ, `src/vfs/models/entry.py:456`), so slice C adds no model field.

Copy (§4.5): the tree's `_copy_bodies` reads each body into Python with the row's version and hash, redrives on a changed pair, and inserts the body verbatim under the new id with the source's recorded hash (READ, `src/vfs/storage/backends/database/topology.py:533-580`). A source with no body row yields a copy with a hash and no body, the same fault (INFERRED from `:559-562`).

`scrub` (§5): not built; `"scrub"` is not in `Op` (READ, `src/vfs/ops.py:36-61`).

SQL Server isolation (§3.3's premise): the MSSQL profile still pins no `op_isolation` (READ, `dialects.py:426-427`, set only for Postgres and MariaDB at `:534`, `:605`), and no code reads `READ_COMMITTED_SNAPSHOT` (EXECUTED, grep). The active spec `2026-11-15-on-sql-server-a-read-never-waits-on-a-write.md` refuses a SQL Server database with that setting off at first touch (READ, its decision 2); once it lands, every engine vfs serves gives a plain read a statement-consistent snapshot, and the torn join §3.3 infers on SQL Server cannot occur (INFERRED from SQL Server's documented read-committed-snapshot behaviour, which that spec relies on).

## Where the roadmap places it

Story K3, "Integrity: verify on read, hash on every written row · spec 175 A–C · M · gate b", depends on K1 for the kind (READ, `context/standards/roadmap.md:152-158`). Its four criteria: a raw rewrite reads as `vfs.unavailable.integrity` with `success is False` on every leg; a fault is reported only when two reads agree, "the second read is exactly one extra statement"; every row `write`, `edit`, `copy` or `move` returns carries `content_hash`; hashing is offloaded per call with `len(byte_chunked(items, BLOB_PAGE_BYTES))` hops above the threshold (READ, `roadmap.md:155-158`).

Slice D is cut to 0.2: "`scrub` (spec 175 D) | 0.2 | Report-only; nobody is asking yet" (READ, `roadmap.md:1045`). The `lint` placeholder spec has no roadmap story (EXECUTED, grep of `roadmap.md` for `lint`).

State row: "verify `content_hash` on read | missing (probe 2 live)" (READ, `roadmap.md:124`). Consumers: K6, the ranged read, depends on K3 (READ, `roadmap.md:180`); K10, the session's read stamps, depends on K3 for the hash on every row (READ, `roadmap.md:215`); H4's resume checks a re-read's `content_hash` (READ, `roadmap.md:325`).

Rulings that bind it. Decided 2026-11-15 (D8, `roadmap.md:1080`; kernel rulings spec decision 9, `:79-81`): the child kind `vfs.unavailable.integrity`, never retryable; the 100,000-byte threshold stays; a failed check never locks a file. Decision 9's repair rule: the check refuses only where a call must hand out or build on the damaged body, `read` first; which other verbs read a body (`edit`, `copy`, a cross-mount `move`, `grep`) and what each answers is decided at this conversion; a `write` over the file succeeds and heals it; `stat`, listings, `delete`, `move` and `restore` work as on any file; a prior version is readable once the history read lands; and "K3 does not land with a path on which a damaged file can be neither read, rewritten nor removed". Decided 2026-11-15 (D58, `roadmap.md:1130`): accepting a body as found is a separate, explicit repair act only the system actor can run; it writes a new version; never automatic. Decided 2026-11-15 (D59, `roadmap.md:1131`): a salvage read `read(verify=False)`, open to anyone who may read the file, succeeds with a warning. Decided 2026-11-15 (decision 5, `:63-65`, and the table at `:107`): a scrub key does not ride `next_after`; it gets a field of its own.

## Units proposed

Slice D becomes no unit here: the byte layer of `lint` carries it, and the `lint` placeholder spec is completed on its own track (READ, that spec's decision 8 and Scope). The remaining slices land apart as three units.

Unit 1. Slug: a read refuses a body that fails its recorded hash. Title: "`read` checks every body it serves against its recorded hash and refuses a mismatched, missing or unhashed body with `vfs.unavailable.integrity`, unless the caller asks for the salvage read". Gate b. Depends on K1 (D8, decided) and D59. Sources: §1.1, §1.3, §2, §3, §7, criteria 1-13. Content: `content_digest`; one shared hashing helper over the landed per-call rule (see open choice 6); the kind and its `data` record; `BodyCheck` with confirm-by-redrive; `read(verify=False)` with its warning; `IntegrityContract` planters on every conformance leg. Rewrite depth: amend.

Unit 2. Slug: every written row reports its hash and no verb launders a damaged body. Title: "Every row `write`, `edit`, `copy` and `move` returns carries `content_hash`; `edit` refuses a damaged pre-image with `vfs.unavailable.integrity`; an overwrite of a damaged body succeeds with a warning and its version row keeps the recorded hash". Gate b. Depends on unit 1 (the kind, the helper, `BodyCheck`); shares `edit_rows`, `_finish` and `_fetch_committed` with spec 174 (K2), so it builds after or rebases onto K2 (INFERRED; both edit `writes.py`). Sources: §4, criteria 14-17. Rewrite depth: amend.

Unit 3. Slug: the system actor accepts a damaged body as found. Title: "Only the system actor can accept a body that fails its hash as it stands, which writes a new version whose `content_hash` is the body's own, so history records the acceptance". Gate b (D58 names K3). Depends on units 1 and 2, D58. Sources: none in the spec; the content is D58's ruled wording and decision 9's repair rule. Rewrite depth: rewrite. Its spelling (a verb or an argument of an existing verb) needs a ruling (open choice 10).

## Open choices, each verified

1. §1.2 marker, keep 100,000 bytes or re-measure on x86. Lean: keep. Verification: already ruled, D8 (decided 2026-11-15, "the threshold stays", `roadmap.md:1080`) and kernel rulings decision 9.

2. §2 marker, the kind: child `vfs.unavailable.integrity`, top-level `vfs.integrity`, or plain `unavailable`. Lean: the child. Verification: already ruled, D8 and decision 9 ("the child kind `vfs.unavailable.integrity`, never retryable").

3. §4.4 marker, an overwrite of a damaged body: succeed with a warning and store the recorded hash on the version row (lean), refuse until a separate repair act runs, or store the measured hash. Verification: already ruled in its main part, decision 9 ("a `write` over the file succeeds and heals it ... becomes its decision"); refusing would lock the file, which decision 9 forbids. The detail that the version row keeps the recorded hash, so damage stays visible to `lint` and the history read, holds; precedent: D58's ruled principle that an acceptance is recorded in history (`roadmap.md:1130`) and the lint spec's decision 5 that a damaged body is never recomputed away.

4. §6 marker, `grep` text: leave `grep` unverified with `read` as the verified door (lean), or hash each candidate body in grep's verify batch. Verification: needs a ruling. Decision 9 assigns `grep`'s answer to this conversion without choosing. Against the lean: ZFS and btrfs verify a block's checksum on every read, so `grep` over a damaged file fails there (prior art read in the lint memo's study 01, `context/research/2026-11-15-a-lint-verb-that-finds-integrity-issues.md:47-49`). For the lean: grep is among the three in four calls that are reads (AGENTS.md, reference deployment), and a hash per candidate adds a full sha256 pass beside the regex. Needs a ruling: grep serves lines from unverified bodies (a hit is a pointer to `read`), or grep hashes each candidate and drops or flags a damaged one. `glean` named in §6 is not a verb (READ, `ops.py:36-61`).

5. Rebase note for spec 178, the ranged read: a range covering the whole body is checked and a partial range is served unchecked with an `info` note (lean), or every ranged read fetches and hashes the whole body, or per-page hashes stored beside the body. Verification: holds. The second option fails against K6 criterion 1, which allows at most 4,096 body bytes fetched for a 4,096-byte range (READ, `roadmap.md:181`); the third is a schema change no ruling asks for. Precedent: K6 criterion 1 itself; otherwise none found, resting on the rule that a read costs what it returns (AGENTS.md, "Per verb call"). The choice belongs to spec 178's conversion; unit 1 states only that a ranged read is outside its check.

6. §1.3 fork, the hop shape: one hop per blob page, gathered in parallel (spec), or one hop for every body of the call (landed). Verification: holds-amended. Amended text: "Every hash this spec adds goes through one shared helper that applies the landed rule: inline while the call's bodies total under `MEASURE_OFFLOAD_BYTES`, otherwise one `call_offloaded` hop for the whole call; per-page parallel hops are the named future direction if a measurement shows one worker thread is the bottleneck." Precedent: the landed write path (READ, `writes.py:152-170`) and its spec's decision 3. Both forms bound the loop's time per call; the one-hop form uses one pool thread per call, which at the reference deployment's 20 calls a second leaves the pool shared across calls (INFERRED). Roadmap K3 criterion 4 is then corrected to "exactly one offload call", which the kernel rulings spec leaves to this conversion (READ, `:144`).

7. §3.3, confirm by redrive. Lean: a fault is believed only when two reads in two transactions agree on the same row version. Verification: holds-amended. The law stands: roadmap K3 criterion 2 requires it (READ, `roadmap.md:156`) and the lint spec's decision 6 states the same rule for a walk. Two amendments: its stated cause changes, because once the SQL Server spec requires `READ_COMMITTED_SNAPSHOT` on, no engine tears a single join, so the second read guards against a body rewritten out of band between the snapshot and the hash, not an engine tear; and the count follows K3 criterion 2, "the second read is exactly one extra data statement", the redrive's repeated rights checks counted apart.

8. §4.5, `copy` of a damaged source. The spec's position: copy does not hash and carries the source's recorded hash, so the copy is equally detectable. Verification: holds. Precedent: the landed `_copy_bodies` already copies the body verbatim under the source's recorded hash and guards on the `(version, content_hash)` pair (READ, `topology.py:546-562`); the copy hands nothing to the caller, so decision 9's "hand out" does not reach it, and the copy launders nothing (INFERRED). A cross-mount `copy` or `move` is a read plus a write by spec 160's design, so its read meets unit 1's check and refuses (INFERRED); unit 1 states it.

9. §5, `scrub` as its own verb, its key on spec 176's field. Verification: already ruled. Decided 2026-11-15 in the lint spec's decision 1: one verb, `lint`, whose byte layer runs only when asked, "no `scrub` verb is added"; and decision 5 of the kernel rulings spec: a key that is not a path gets its own field.

10. D58's spelling. The choice: a system-actor-only verb of its own, or an explicit argument on an existing verb (for example a `write` that takes the body as found). Verification: needs a ruling. D58 fixes who, what it writes and that it is never automatic, not the public name (READ, `roadmap.md:1130`); the lint spec's decision 5 puts repair "asked for apart" but names no verb.

11. D59's salvage read. Verification: already ruled, D59 (decided 2026-11-15, `read(verify=False)`, open to anyone who may read the file, succeeds with a warning).

## What is stale

- Status line "Not started": slice A's §1.2 and a one-hop form of §1.3 landed with `2026-11-07-storage-measures-every-body-it-stores.md` (READ, `version.py:60`, `writes.py:144`).
- ADR 087, 080 and 057 are cited as the decisions; the ADRs were retired on 2026-10-30. The decisions are D8, D58, D59 and kernel rulings decisions 5 and 9; the "ADR amendments this spec needs" section has no target.
- Commit `ba77449` and its probe: the base is HEAD `3166469`; the probe was re-run here (EXECUTED).
- `storage/backends/database/offload.py` (`:79`): the module is `src/vfs/offload.py`, `call_offloaded` at `:146` (EXECUTED, grep).
- `byte_chunked` at `dialects.py:727`: it is `src/vfs/batching.py:65` (READ).
- `MEASURE_OFFLOAD_BYTES` at `base.py:137`: it is `models/version.py:60`; `_authored_entry` is `base.py:323` (READ).
- The write path's hashing: storage now measures every written body itself, so each body is hashed twice, router and storage (READ, the archived spec's decision 4; `writes.py:144`).
- Line numbers in `reads.py`: `read_rows` `:155` (spec `:149`), `_point_rows` `:817` (`:558`), `_screen` `:913` (`:678`), `_entry_projection` `:1139` (`:900`), `content_for_entries` `:682` (`:478`) (EXECUTED, grep).
- Line numbers in `writes.py`: `edit_rows` `:275` (`:226`), `_fetch_committed` `:314` (`:284`), `_finish` `:347` (`:315`) (EXECUTED, grep).
- `StagedEntry` already holds `base_content` and `base_size_bytes` (READ, `staging.py:79-80`); only `base_content_hash` and `base_metrics` are new.
- `checks.subtrees` is `rights.py:792` (`:730`); `descendant_filter` is `descent.py:193` (`:198`); `_gate` is `backend.py:1280` (`:1559`); `_drift_warning` is `edges.py:564` (`:536`) (EXECUTED, grep). These matter only to the overtaken slice D.
- `reindex` and `SupportsReindex`: the passes are `rebuild` and `refresh`, `SupportsRebuild` at `src/vfs/storage/protocol.py:478` (READ); §5.7's comparison names a verb that no longer exists.
- `sweep`: renamed `destroy` from the deletes spec's landing (kernel rulings decision 3).
- `glean`: no such verb (READ, `ops.py:36-61`).
- `scrub` and its resumption key on spec 176's field: replaced by `lint` (lint spec decision 1) and a field of its own (decision 5); the listing key is `next_after`, typed as a path (D6, `roadmap.md:1078`).
- §3.6 "spec 161's read side, folded into spec 180": the history verb is `versions` (kernel rulings decision 11), roadmap K8; `pack` "on reindex" names a pass now split into `rebuild` and `refresh` (decision 11).
- §3.3's SQL Server premise: the active SQL Server spec requires `READ_COMMITTED_SNAPSHOT` on (its decision 2), not yet built (EXECUTED, grep).
- Membership budgets quoted in §5.6 still hold: Oracle 1,000, SQL Server 2,000 (READ, `dialects.py:639`, `:568`).
- The Owner line carries a name; the nine-section shape has no such line.

## Notes for the conversion

The roadmap decisions needed are D8, D58 and D59; D6 and decision 5 matter only to the overtaken slice D. Decision 9's repair rule binds each unit: write one criterion per verb (`read`, `edit`, `copy`, cross-mount `move`, `grep`, `write`, `stat`, `ls`, `delete`, `move`, `restore`) on a damaged file, so the spec shows that no path locks the file.

Unit 1 keeps the spec's refusal order: rows refused for kind or permission are refused before any hash, so a caller who may not read a row learns nothing of its integrity (spec §3.1 step 2). The salvage read returns the body with an `integrity` warning at `Severity.warning`, the same `data` record, and is judged at the same `read` rung (D59).

The `data` record's `reason` values `mismatch`, `missing` and `unhashed` stand: `vfs_entries.content_hash` is nullable (READ, `src/vfs/models/rows.py:436`), and since the 2026-11-07 spec storage writes a hash for every file, so a `NULL` is out-of-band damage (INFERRED). `vfs_versions.content_hash` is `NOT NULL` (READ, `rows.py:548`), so `unhashed` never applies to a version row.

The healthy-path counts in criteria 9 and 14 (one data statement for a read; 6 and 8 statements for a create and an overwrite) must be re-pinned at HEAD before they are restated; the probe here did not count statements.

The rebase notes for specs 167, 171 and 172 stand in substance (EIO in the shell, `isError` with no retry in MCP, `EIO` in the guest, `content_hash` in every mutating tool's structured content); they cite ADR 087 and are restated without it.

One line: verify on read and the hash on every written row are still missing and gate b, the threshold's move already landed, `scrub` is now `lint`'s byte layer, and the conversion yields three units, with `grep`'s answer and the spelling of the system actor's accept act left to a ruling.
