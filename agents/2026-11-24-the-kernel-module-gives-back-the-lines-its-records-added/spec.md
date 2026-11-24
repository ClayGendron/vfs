# The kernel module gives back the lines its records added

A draft, written on 2026-11-24 from the code review of the fourth landing of `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md`, which raised the held line count of `src/vfs/base.py`. It is not reviewed, and nothing is built.

## The outcome wanted

`src/vfs/base.py` falls back to about 3,192 lines, the count it was held at before the writer and the sweep were added, by moving out code that is not the kernel's routing: the sweep of the kernel's records with its warning, and two pure folds over a `Result`.

## Builds on

The line allowlist in `tests/lint/allowlist.py`, under which a listed module that grows fails and one that shrinks lowers its entry, and the ownership lens of the code review, which asks a raised entry to be given back. The records spec's Scope says "`base.py` is held at 3,090 lines and grows by the store's construction and its close, so its entry is raised by that count". Its third landing holds the entry at 3,192, after moving the choice of the place and the durable-mount question into `store_for_root` in `vfs.kernel_store.store`. Its fourth raises it to 3,222: 3 lines for the close's docstring, which the Scope covers, and 27 for the pass that `sweep` awaits, which the Scope lists among the landing's files and its count does not cover.

## The problem

Read, at `9fe95e5` on `the-kernel-writes-records-behind-and-sweeps-them`.

- **The sweep of the records is the store's work, judged in the kernel.** `AsyncVirtualFileSystem.sweep` awaits `KernelStore.sweep()`, catches `KernelStoreUnavailable` and builds the warning its result carries, in 9 lines. `record_after` already does the same for a commit inside the store, and returns the warning.
- **Two folds over a `Result` sit in the kernel.** `_with_skips` and `_cap_rows`, under the "merging" banner, are static methods that read no attribute of the kernel, about 22 lines with their docstrings. They are called from the fan-out and from `glob`.
- **What stays.** `_is_the_roots_trash` reads the mount table, which is the kernel's, and so does the sweep docstring the records spec's "What the docs must say" requires.

## Decisions

1. **The store's package sweeps beside the trash and returns its warning.** A function beside `store_for_root`, `sweep_after(store) -> ResultError | None`, runs one pass and returns the warning, as `record_after` does for a commit. `sweep` calls it in one line and appends what it returns.
2. **The folds move to `vfs.results`.** `_with_skips` and `_cap_rows` become functions of `vfs.results`, where `Result.merge` already lives.
3. **The allowlist entry for `base.py` falls by what leaves.**

## Tests

- The sweep's tests in `tests/kernel_store/test_sweep.py` and `tests/base/test_kernel_store.py` pass unchanged, and one test of `sweep_after` pins that a failed pass is returned and never raised.
- The fan-out and `glob` tests pass unchanged.

## Scope

In: `src/vfs/base.py`, `src/vfs/kernel_store/store.py`, `src/vfs/results/envelope.py` or a module beside it, their tests, `tests/lint/allowlist.py`, and `documentation/maintainers/kernel-store.md` for the new function.

Out: every behaviour of `sweep`, the fan-out and `glob`.

## Not checked

Nothing was run. The lines that leave are read from the file, about 29 of the 30, and are not measured after a move.

## Choices to confirm

- Whether decision 1 is a function of the package, as `store_for_root` is, or a member of the store, which the records spec's decision 22 lists as all of it.
- Whether the folds belong in `vfs.results` or in `vfs.fanout`.

## One line

The sweep's warning moves into the store's package and two folds into `vfs.results`, so `base.py` gives back the lines the writer and the sweep added.
