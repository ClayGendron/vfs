# 075 — plan

Approach: retire the trash scope from the innermost chokepoint outward
(`descent.py`), let the removals ripple through the read and write
builders, then rewrite the two trash test families to pin the parity
posture. No schema change, no new statements — every touched query
simply loses predicates. One landing, tree green throughout.

## 1. `descent.py` — the scope leaves the chokepoint

- Delete `trash_filters` and `in_trash`.
- `liveness_filters` reduces to the meta rule alone: empty filter list
  when `include_meta`, the two meta-exclusion predicates otherwise.
- `classify_misses` drops `*trash_filters(entry)` from the ancestor
  query and the "carries the trash scope too" docstring paragraph.
- `TRASH_ROOT` stays — recomment as the conventional location the
  future delete spec targets, not a reserved/never-admitted prefix.
- Module docstring rewritten: one-scope model (meta hidden by default,
  served when anchored), and the "trashed ancestor reads as missing"
  paragraph replaced — hiding at original paths is the reparent's path
  rewrite (ADR 004), not a filter.

## 2. Read side (`reads.py`)

- `_mappings_by_path` drops `*trash_filters(entry)`; the import goes.
  Point reads, `ls`/`tree`/`glob` anchors, and their `in_meta`
  bypasses now serve trash-side paths like any other meta path — no
  code change beyond the predicate removal.

## 3. Write side (`writes.py`, `staging.py`)

- `_fetch_committed` drops `*trash_filters(entry)`; the import goes.
  The committed snapshot now sees trash rows, so writes there gate
  against real state instead of a phantom-parent view.
- `WritePlan.outside_trash` is deleted with its call sites: the
  `put_file` guard, the `put_dir` guard, and the `mkdir_rows` early
  return. No `invalid`-for-trash arm remains reachable.
- Docstrings: `writes.py` module docstring is trash-clean already;
  `staging.py` loses the gate's docstring with the gate.

## 4. Comment residue

- `dialects.py` `_FILTER_BIND_RESERVE` comment: "trash/liveness
  filters" → the liveness filter.
- `rows.py` restore-metadata comment stands — it describes the
  identity-based restore columns (unchanged by ADR 014 pin 4), not a
  reserved prefix.

## 5. Tests (`test_backends_database.py`)

- `TestNamespaceScopes` — the four concealment tests are rewritten,
  none deleted silently:
  - trash-invisible-from-meta-anchor → `ls /.vfs` lists `trash`
    beside `docs`; `tree /.vfs` includes the trash subtree.
  - trashed-path-not_found-through-every-verb → the same path serves
    through `read`/`stat`/`ls`/`tree` when directly anchored.
  - descent-never-surfaces → descent through a trash-side FILE
    classifies `wrong_kind` naming it, the standard ladder.
  - uniform-regardless-of-bucket-existence → misses under a real
    bucket and a missing bucket classify at their own first failing
    component, identical in shape to any other meta path.
  - The default-scope hiding and meta-anchor tests stand unchanged.
- `TestTrashWriteRefusal` becomes `TestTrashWritability`:
  - Batch write of `/.vfs/trash/2026-07-18-10/x.txt` with
    `parents=True` succeeds, mints the bucket chain, reads back
    byte-identical; `stat` and an anchored `ls` of the bucket serve it.
  - `mkdir` and `edit` under trash take the ordinary paths, including
    error arms: `exists` on a taken path, `wrong_kind` through a file
    ancestor, `not_found` parent-rule refusal without `parents`.
  - The meta-paths-still-write test stands.
- `ruff` and `ty` at zero; full `tests/` suite green.

## 6. Spec bookkeeping

- The delete-spec harness rows (spec §5) are already recorded in the
  spec itself; nothing lands in code for pins 3–5.
