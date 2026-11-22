# The sync session twin imports nothing above it

A draft, written on 2026-11-21 from finding M3 of `context/reviews/2026-11-21-a-listing-comes-back-a-page-at-a-time-code-review.md`. It is not reviewed, and nothing is built.

## The outcome wanted

`UPWARD_IMPORT_ALLOWANCE` in `tests/lint/allowlist.py` holds no entry for `("vfs.sync_session", "vfs.sync")`.

## The problem

The listing cursor moved the synchronous `Session` twin out of `src/vfs/sync.py` into `src/vfs/sync_session.py`, to keep `sync.py` under the module size ceiling. The twin's constructor takes the facade it forwards through, typed `VirtualFileSystem`, so `sync_session.py` imports `vfs.sync` under `TYPE_CHECKING`. That edge points up the layer ladder, from `vfs.sync_session` to `vfs.sync`, and the allowlist admits it. `test_the_constructors_and_the_context_managers_are_twins` in `tests/test_sync.py` pins the twin's constructor annotation as the sync family's name of `AsyncSession`'s, `VirtualFileSystem`, so a protocol typed under another name fails that test.

## Decisions

1. **The twin's back-reference is typed by a protocol on a lower rung,** holding the two members the twin reads, the kernel and the facade's verb hop.
2. **The twin test reads the protocol as the facade,** by a mapping beside `FAMILY`, so the twins stay pinned and the edge goes.

## Tests

The layer lint passes with the allowlist entry removed, and the twin test passes.

## One line

The sync session twin types its facade by a protocol below it, and the ladder loses its one new exception.
