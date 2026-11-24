# The kernel module gives back the lines its records added

A draft, written on 2026-11-24 from the code review of the fourth landing of `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md`, which raised the held line count of `src/vfs/base.py`. It is not reviewed, and nothing is built.

## The outcome wanted

`src/vfs/base.py` falls back to at most 3,204 lines, the count it was held at before the writer and the sweep were added, by moving out code that is not the kernel's routing: the sweep of the kernel's records with its warning, the choice of the place the records are kept, and two pure folds over a `Result`.

## Builds on

The line allowlist in `tests/lint/allowlist.py`, under which a listed module that grows fails and one that shrinks lowers its entry, and the ownership lens of the code review, which asks a raised entry to be given back. The records spec's Scope says "`base.py` is held at 3,090 lines and grows by the store's construction and its close, so its entry is raised by that count". Its third landing raised the entry to 3,204. Its fourth raised it to 3,234: 3 lines for the close's docstring, which the Scope covers, and 27 for the pass that `sweep` awaits, which the Scope lists among the landing's files and its count does not cover.

## The problem

Read, at `25d100e` on `the-kernel-writes-records-behind-and-sweeps-them`.

- **The sweep of the records is the store's work, judged in the kernel.** `AsyncVirtualFileSystem.sweep` awaits `KernelStore.sweep()`, catches `KernelStoreUnavailable` and builds the warning its result carries, in 9 lines. `record_after` already does the same for a commit inside the store, and returns the warning.
- **The place is chosen in the kernel.** `_record_place_of` (6 lines with its spacing) reads a storage's `record_place` or falls back to memory. Its callers are the constructor and `_holds_durable_mount`. It reads `SupportsRecordPlace` and `RecordPlace` alone, both of `vfs.storage`, beneath `vfs.kernel_store` on the ladder.
- **Two folds over a `Result` sit in the kernel.** `_with_skips` and `_cap_rows`, under the "merging" banner, are static methods that read no attribute of the kernel, about 22 lines with their docstrings. They are called from the fan-out and from `glob`.
- **What stays.** `_is_the_roots_trash` reads the mount table, and `_holds_durable_mount` reads it too; both are the kernel's.

## Decisions

1. **The store sweeps beside the trash and returns its warning.** A member of `KernelStore`, `sweep_after() -> ResultError | None`, runs one pass and returns the warning, as `record_after` does. `sweep` calls it in one line and appends what it returns.
2. **The place is chosen by the store's package.** `_record_place_of` moves to `vfs.kernel_store` as a function the kernel imports.
3. **The folds move to `vfs.results`.** `_with_skips` and `_cap_rows` become functions of `vfs.results`, where `Result.merge` already lives.
4. **The allowlist entry for `base.py` falls by what leaves**, to at most 3,204.

## Tests

- The sweep's tests in `tests/kernel_store/test_sweep.py` and `tests/base/test_kernel_store.py` pass unchanged, and one test of `sweep_after` pins that a failed pass is returned and never raised.
- The fan-out and `glob` tests pass unchanged.

## Scope

In: `src/vfs/base.py`, `src/vfs/kernel_store/store.py`, `src/vfs/kernel_store/__init__.py`, `src/vfs/results/envelope.py` or a module beside it, their tests, `tests/lint/allowlist.py`, and `documentation/maintainers/kernel-store.md` for the new member.

Out: every behaviour of `sweep`, the fan-out and `glob`.

## Not checked

Nothing was run. The lines that leave are read from the file, not measured after a move. The third landing of the records spec is being revised beside this draft, and its count of `base.py` may change.

## Choices to confirm

- Decision 1 adds a member to the store's interface, which the records spec's decision 22 lists as all of it.
- Whether the folds belong in `vfs.results` or in `vfs.fanout`.

## One line

The sweep's warning moves into the store, the place's choice into its package and two folds into `vfs.results`, so `base.py` gives back the lines the writer and the sweep added.
