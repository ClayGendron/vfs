# 074 — tasks

Ordered; each task leaves the tree green (suite + ruff + ty).

1. [x] Schema: drop `meta.revision_counter` and `gram_epochs.watermark`,
   add `chunks.encoded`; update `rows.py` docstrings; fix
   `engine.py` first-touch insert (root mints revision 1); update
   `tests/test_rows.py`.
2. [x] `writes.py`: delete `allocate_revisions`; stage revisions as
   create=1 / guarded=base+1; rewrite `_apply`'s preamble and the bump
   statement to SQL-side increment. (Three-candidate synthesis: three
   agents re-implemented the file from the same brief; the final file
   merges their unanimous core with the cleanest structural choices.)
3. [x] `writes.py`: rework `_update_materials` (unguarded SET-side
   increment; read-back stamps clobber rows) and `_upsert_layer`
   (clobber SET revision = target+1, RETURNING revision); bump values
   get their own conditional read-back after the bump statement
   (plan.md's original wording was unexecutable — see plan.md §2).
4. [x] `memory.py`: remove the global counter; mirror per-entry
   semantics across write/edit/mkdir/mkedge/copy/move/bumps.
5. [x] Traits: `protocol.py` declared values + both backends →
   `per_entry64`.
6. [x] Tests: replace counter tests with per-entry semantics tests;
   audit conformance suite for cross-entry ordering assertions (one
   found: the copy test — rewritten to fresh-rows-carry-1).
7. [x] Statement-count pins (create=5, overwrite=5) in
   `TestWriteMechanics::test_write_statement_counts_are_pinned`.
8. [x] Docs: refresh root `write-pipeline.md` diagram and the
   `writes.py` module docstring.
9. [x] Full-suite + lint/type pass; grep `src/ tests/` for
   `allocate_revisions|revision_counter|watermark` → only the
   unrelated `grep_staleness` trait value remains (the grep pass
   owns any rename).
