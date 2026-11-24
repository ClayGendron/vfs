# The vector leg leaves the database storage

A draft, written on 2026-11-24 from the code review of the second landing of `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md`, which raised the held line count of `backend.py`. It is not reviewed, and nothing is built.

## The outcome wanted

`src/vfs/storage/backends/database/backend.py` falls back under the count it was held at before the record place was added, by moving out a concern that is not the storage's: the choice and the embedding of a ranked search's vector leg.

## Builds on

The line allowlist in `tests/lint/allowlist.py`, under which a listed module that grows fails and one that shrinks lowers its entry, and the ownership lens of the code review, which asks a raised entry to be given back. `agents/2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md` raised the entry from 1,509 to 1,546 within its Scope's estimate. The record place raised it from 1,546 to 1,565: an import, `DatabaseStorage.record_place` and the docstring that spec's "What the docs must say" requires.

## The problem

Read, at `3c805d1`.

- **The vector leg is the host's state, read through the storage.** `_vector_leg_for`, `_ann_indexed` and `_embed_query` in `backend.py` are about 82 lines.
  - **What they read from the host:** the embedder, the stored embedding identity and whether it is stale, the profile, the native embedding config and the pgvector version.
  - **What they read from the storage:** its query-vector cache and its search wall.
  - **Who calls them:** `search` alone, once.
  - **Their output:** a `VectorLeg` or the records that say why the lexical leg answered alone.
- **No other verb reads them.** Moving them changes no statement and no answer.
- **Tests reach the leg through the storage.** `tests/storage/database/test_vector_leg.py` calls `storage._vector_leg_for` directly and patches it (lines 175, 182, 293 to 312, and `_ann_indexed` at 316 and `_embed_query` at 336), so a move edits those tests' handles and nothing they assert.

## Decisions

1. **The leg becomes a module of its own.** `src/vfs/storage/backends/database/vector_leg.py` holds the three functions, taking the engine host, the query-vector cache and the search wall. `search` calls it in one line.
2. **The cache stays the storage's.** The cache is per storage today. The host is shared by nothing else yet, so its home is not changed here.
3. **The allowlist entry for `backend.py` falls by what leaves.** It falls to at most 1,546, the count before the record place.

## Tests

- `tests/storage/database/test_vector_leg.py` reaches the leg through the new module.
- Every assertion is unchanged.
- The counted statement tests of `search` pass unchanged.

## Scope

In: `backend.py`, `vector_leg.py` (new), `tests/storage/database/test_vector_leg.py`, `tests/lint/allowlist.py`, and `tests/lint/test_code_shape.py` if the new module needs a rung.

Out: every behaviour of `search`.

## Not checked

Nothing was run. The count of lines that leave is read from the file, not measured after a move. The store's landing of the kernel-records spec is drafted to add about 5 more lines to `backend.py`; that figure is read from its branch and is not on `dev`.

## Choices to confirm

- Whether the leg belongs on `EngineHost` as methods instead of in a module of its own.
- Whether the query-vector cache moves with it.

## One line

The vector leg's choice and embedding move out of `DatabaseStorage`, so `backend.py` gives back the lines the record place added.
