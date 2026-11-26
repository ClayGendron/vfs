# Study: Every mutation mints a version row, the undo the README promises

## Verdict

Overtaken. The write half (the mint) is in the tree in `src/vfs/storage/backends/database/versions.py`, called from `writes.py`; the read half (`versions(path)`, `read(path, version=N)`) is roadmap story K8, built from spec 180's read slice; the roadmap's own true-up story R7 names spec 161 as dropped (READ context/standards/roadmap.md:966). Its retention item (age-based deletion of version rows) is contradicted by the later ruling to keep the full history and pack it, so nothing of this spec survives as its own unit.

Recommended disposition: drop the folder; carry the three facts listed under "Notes for the conversion" into the conversion of spec 180 (K8).

## Against the tree

- The mint is built: `mint_versions` keeps the replaced body as a snapshot row (`is_snapshot` true, text in `content`, bytes in `data`), the replaced version as `version_number`, hash, size and lines measured from the body, actor, provenance, source identity and grant revision, and one `vfs_version_subjects` row per subject. READ src/vfs/storage/backends/database/versions.py:1-34, :66-80, :177-198.
- The mint is wired into the write path: imported at READ src/vfs/storage/backends/database/writes.py:90 and called at :438 with the plan's authority.
- The tree covers more cases than seed item 1: an arbitration clobber of a rival's row also mints, and a body replaced by an identical body mints nothing. READ src/vfs/storage/backends/database/versions.py:4-14.
- Bulk minting is paged: text rows by the dialect parameter budget through `bulk_insert`, bytes rows by `BLOB_PAGE_BYTES`, reads by `membership` chunks. READ src/vfs/storage/backends/database/versions.py:24-31, :41-45; `rows_per_statement` READ src/vfs/storage/backends/database/dialects.py:799.
- A mint label test exists: `test_a_mint_proves_its_label_in_two_statements`. READ tests/storage/database/test_writes.py:1799.
- No read side exists: `read` takes `path`, `observations`, `columns`, `authority` and no `version=`. READ src/vfs/base.py:904-915. No `versions` verb is defined in `src/vfs` (EXECUTED: grep for `def versions` returned nothing).
- The only reader of `vfs_versions` outside the mint is the purge, which deletes a purged entry's rows. READ src/vfs/storage/backends/database/trash.py:606.
- No version-retention setting exists; `trash_days` is the only retention setting. READ src/vfs/storage/backends/database/backend.py:156-194; src/vfs/storage/backends/memory.py:47.
- `models/versioning.py` and its `unidiff` import remain, still with no caller on the write path; `unidiff>=0.7` is still a core dependency. READ src/vfs/models/versioning.py:20-21; pyproject.toml:38. Spec 180 now owns their fate: pack's planner lives in `models/versioning.py`. READ context/specifications/active/180-history-pack-on-reindex-and-the-bounded-sweep/spec.md:6, :40-41.
- Spec 162, whose slice B the seed defers the mint to, was committed 2026-10-12 (`7d0bc3c`) though still under `active/`. READ context/specifications/active/162-trash-as-a-tombstone-on-the-row/spec.md:3.
- The problem statement is half true at HEAD: overwrites are no longer lost (INFERRED from the mint above), but nothing reads them back, which is K8's stated why. READ context/standards/roadmap.md:36, :197.

## Where the roadmap places it

- R7 (gate b), criterion 2: "Spec 161 is dropped (its write half landed with the tombstone mint; its read half is K8)". READ context/standards/roadmap.md:966.
- The roadmap's counts list 161 among three overtaken specs. READ context/standards/roadmap.md:106, :897.
- K8, gate f, "The history read side: `versions(path)` and `read(version=)` · spec 180 (read slice)", depends on K1 and K4. READ context/standards/roadmap.md:195-202.
- Section 15 puts `pack`, the bounded `sweep` and the garbage gauge at 0.2 because "the full history is kept", and `versions(since=, actor=)` at 0.2. READ context/standards/roadmap.md:1044, :1046.

## Units proposed

None. The read side is K8, converted from spec 180's read slice, not from this folder (INFERRED from roadmap.md:195 and :966). Proposing a unit here would duplicate K8.

## Open choices, each verified

- Seed item 4 marker: a `versions` read verb, a `version=` parameter on `read`, or both. No lean in the spec. Verification already-ruled: K8 takes both, `versions(path)` and `read(path, version=N)` (READ context/standards/roadmap.md:195-199), and the verb's name `versions` is Decided 2026-11-15 (READ context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:87-89).
- Seed item 5: retention as a storage setting with an age-based chunked `DELETE ... WHERE created_at < cutoff` on both version tables. Lean stated as the seed's semantics. Verification fails: the later design keeps the full history and shrinks it by packing cold rows, "No version is ever deleted" (READ context/specifications/active/180-history-pack-on-reindex-and-the-bounded-sweep/spec.md:13), age-keyed work is rejected there as proportional to all history (READ same file:62), Decided 2026-11-15 keeps the newest old version whole under pack (READ the 2026-11-15 ruling:87-89), and the roadmap defers the sweep with "the full history is kept" (READ context/standards/roadmap.md:1044). The only version deletion at HEAD is the trash purge of a purged entry (READ src/vfs/storage/backends/database/trash.py:606).
- Seed item 2: the label is the replaced row's version (row N is the body at version N), amending ADR 017 pin 1. Verification holds: the tree records the replaced version as the row's number (READ src/vfs/storage/backends/database/versions.py:76-79, :177) and spec 180's terms define a version row the same way (READ spec 180 spec.md:21). The ADRs were retired 2026-10-30, so no amendment record is owed (READ context/standards/roadmap.md:106).
- Seed item 1, "a create mints nothing". Verification needs-a-ruling, surfaced by K8: K8 criterion 3 asks that the v1 row of every entry carry the creator's actor, with a `created_by` column on the entry row as the alternative, which is D36, a lean ("The version row") not marked Decided (READ context/standards/roadmap.md:200, :1108). The tree mints nothing on create (READ src/vfs/storage/backends/database/versions.py:11). Needs a ruling: creation attribution in a v1 version row minted on create, or in a `created_by` column on the entry row. This belongs to K8's conversion, not to this folder.
- Fate of `models/versioning.py` and `unidiff` (owed to the seed's research pass). Verification already-ruled in substance: spec 180 makes them pack's planner and diff law (READ spec 180 spec.md:6, :40, :140), with its own marker on Python law first versus a Rust kernel first, which is spec 180's choice to carry.

## What is stale

- "the write-replace mint is built by spec 162 slice B (2026-10-11, uncommitted, awaiting ... review)": committed 2026-10-12 as `7d0bc3c` (READ context/specifications/active/162-trash-as-a-tombstone-on-the-row/spec.md:3).
- "`read_revision` (`revision.py` L46-60, which `writes.py` does not call today)": the mint imports and uses `read_revision` (READ src/vfs/storage/backends/database/versions.py:45).
- "the trash purge in `topology.py` L713-715 (the only code that touches version rows today)": the purge lives in `trash.py` (READ src/vfs/storage/backends/database/trash.py:606), and `versions.py` now writes the rows.
- "`read` has no `version=` today (`base.py` L858-865)": still true, but the signature is at `base.py:904-915` (READ).
- "`trash_days` (`backend.py` L186-220)": the parameter is at `backend.py:156`, stored at :194 (READ).
- `vfs_versions` at "`models/rows.py` L515-536": the table name is declared at `rows.py:543` (READ src/vfs/models/rows.py:543).
- "153 softens the README until this lands" and the README lines L55, L87: the README's mutate row now reads "`delete` is reversible through the trash and `restore`" (READ README.md:72); no "can be undone" sentence was found (EXECUTED: grep for "undone|reversible|versioned" in README.md returned only line 72).
- ADR 017, 064 and 074 as authorities ("Bound by", "Depends on", "to be ratified by an ADR"): the decision records were retired 2026-10-30 (commit `3667fec2`) (READ context/standards/roadmap.md:106).
- "`Version.create`'s diff arm (`models/version.py` L112-155)": `models/version.py` imports `create_version` and `reconstruct_version` at :43-44 and documents the provider at :157 (READ); spec 180 records `Version.create` has no caller (READ spec 180 spec.md:41).
- Spec 161's own scope (read verb, retention, the ADR): read side moved to K8/spec 180; retention replaced by pack and the full history; ADR no longer a record type (READ roadmap.md:195, :1044, :106).

## Notes for the conversion

- No nine-section spec is written from this folder; R7 criterion 2 drops it (READ context/standards/roadmap.md:966).
- Three facts to carry into spec 180's read-slice conversion (K8): the mint already skips identical replacements and mints on arbitration clobbers, so `versions(path)` can show gaps in labels (READ versions.py:4-14; INFERRED); the seed's acceptance check "write then write leaves one row with `version_number == 1`, actor the writer" is a good K8 criterion; and seed item 3's statement count bound for a 10,000-file overwrite is the shape of a test the mint should already carry, which K8's scale criterion can cite (READ roadmap.md:201).
- D36 must be ruled before K8 can be built as written, because it decides whether "a create mints nothing" still holds (READ roadmap.md:200, :1108).
