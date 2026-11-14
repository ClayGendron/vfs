# Whether the session twin leaves the sync facade

A placeholder memo: it holds a question, what is known, and the experiment that answers it, and it decides nothing. Decision 4 of [close leaves no SQLite side files](../specifications/active/2026-11-12-close-leaves-no-sqlite-side-files.md) raised it, and the builder of that spec wrote it on 2026-11-13, the day of the build and before the code review. That landing grows `src/vfs/sync.py` by 12 lines and raises its held entry in `MODULE_LINE_BASELINE` from 1,086 to 1,098 without moving lines out, and the gate closes a raise only by a link to the spec or placeholder memo that carries the module's reduction (decision 7 of [the gate's spec](../specifications/archive/2026-11-07-the-gate-and-the-review-read-the-layer-map-and-the-size-baseline.md)). This memo carries that reduction for `sync.py`. It is linked from the answer to that module's raise in the Disposition of the close spec's code review, `context/reviews/2026-11-13-close-leaves-no-sqlite-side-files-code-review.md`, which is written after this memo. No spec waits on this memo. The spec that will use its answer is the one that lowers or removes the `sync.py` entry, which is not yet written. The research will have one 45-minute box. There is no studies folder yet, and no intention: no caller's experience changes with where the twin lives, as long as `from vfs import Session` and `vfs.sync.Session` keep working.

Labels: EXECUTED means a command ran for this memo and the claim reports its output. READ means read in a file cited by path, in the working tree over `732425ea` with the close spec built. INFERRED means this memo's reasoning from the two.

## The question

Should `Session`, the synchronous twin of the router's session, leave `sync.py` for a module of its own, so that `sync.py` falls under the 1,000-line ceiling and its held entry is removed? If so, where does the new module sit, so that the facade and the twin do not import each other in both directions and the foreign-loop warning still names the caller's line?

## What is known today

1. EXECUTED on 2026-11-13: `wc -l src/vfs/sync.py` prints 1,098. READ: its entry in `tests/lint/allowlist.py` is 1,098, and `MODULE_LINE_CEILING` in `tests/lint/test_code_shape.py` is 1,000. A module at or under the ceiling needs no entry.
2. READ: the twin is one banner group of `sync.py`, "The session twin", lines 729 to 1078: the class `Session`, its lifecycle, one forwarding twin per verb and management method of `AsyncSession`, and its own `_result`. That is 350 lines; at `5d47a21a`, before the close spec's 12 lines above it, the same group was lines 717 to 1066.
3. INFERRED from item 2: moving the group whole would leave `sync.py` at about 748 lines, under the ceiling, and its entry would be removed, not lowered.
4. READ: `Session` reaches the facade in two places and no other. Its constructor reads the facade's router, `AsyncSession(fs._fs, authority)`, and its `_result` (line 1074) answers the closed fact itself and otherwise calls `self._facade._result(op, call, ...)`. It holds two slots, `_facade` and `_session`.
5. READ: the two classes name each other. `VirtualFileSystem.session` (line 268) builds `Session(self, authority)` and is annotated to return `Session`, and `Session.__init__` is annotated against `VirtualFileSystem`. A twin in a separate top-level module would therefore be imported by `vfs.sync` at run time and would name `vfs.sync` at least for its types, an import in both directions, unless `vfs.sync` becomes a package that holds both.
6. READ: `_caller_stacklevel` (line 1091) finds the caller's line by skipping every frame whose module name equals this module's own. A twin moved to another module would be the first frame outside it, so the once-per-facade foreign-loop warning raised through a session verb would point at the twin's line, not the caller's. READ: `tests/test_sync.py` pins the warning's file for facade calls (`first[0].filename == __file__`, lines 748 to 761).
7. READ: `LAYERS` in `tests/lint/test_code_shape.py` gives `vfs.sync` a rung of its own, above `vfs.session` and beneath `vfs`. A new top-level module names its rung in the landing that adds it; a module inside a `vfs.sync` package is placed by that prefix and names none.
8. EXECUTED: a search of `src`, `tests`, `docs` and `README.md` for `vfs.sync` names seven files: `src/vfs/__init__.py`, which exports `Session` and `VirtualFileSystem` from it; `src/vfs/offload.py`, in a docstring only; `tests/test_sync.py` and `tests/storage/database/test_statistics.py`, which import the module; `tests/lint/test_code_shape.py` and `tests/lint/allowlist.py`, which name its rung and its entry; and `docs/reference/sync.md`, which says the two classes are in module `vfs.sync`. READ: `test_sync.py` patches the module's `_wait` and `test_statistics.py` patches `all_tasks` on the module's `asyncio`, each by module attribute.
9. READ, from the close spec's decision 4 and its second spec review's finding L1: past the loop runner the module is forwarding twins whose signatures mirror their originals line for line; seven of them, 42 lines, are split only by a trailing comma. Collapsing them would not reach the ceiling and would break the mirror, so it is not a reduction this memo carries.

## The experiment that answers it

The research is done when each item below has a labelled result. It runs on a plain copy of the tree after the close spec has landed, never on the working tree.

1. Two shapes, built in the copy. In the first, `vfs.sync` becomes a package whose `__init__` exports both names, with the facade and the twin in a module each. In the second, the twin is a new top-level module with a rung of its own in `LAYERS`. For each: `wc -l` of every module that results; the faults `tests/lint/test_code_shape.py` reports for the ladder and the size gate; and what `ty check` says of the two classes naming each other.
2. For each shape, the line the foreign-loop warning names when the first blocking call on a facade is a session verb, with `_caller_stacklevel` as it is and with it skipping both modules; and the count of failing nodes of `tests/test_sync.py`.
3. For each shape, the number of files of item 8 whose imports or patch targets change, and whether `docs/reference/sync.md` and its fences still pass `uv run pytest docs README.md -p no:cov -n 0`.
4. What the following spec needs from this memo: the two shapes side by side on the counts of items 1 to 3. The choice between them is that spec's.

## One line

`Session` is 350 of `sync.py`'s 1,098 lines and touches the facade through its router and one hop; the research is to move it in a copy, as a package member and as a top-level module, and count what each leaves.
