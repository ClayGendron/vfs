# Review: search applies its file filters to rows in hand

Three readings on 2026-11-18 and 2026-11-19. None was given a summary of the work.

| What was read | By | Verdict |
|---|---|---|
| The spec, first draft | A fresh reader | Not yet: the kernel file is held at an exact line count, and the draft did not say what pays for the lines it adds. Eight smaller findings. |
| The spec, amended twice | The same reader | Fit to build. |
| The build, commit `9156c72a` | A fresh reader, with mutants | Does not land yet: one sentence of the new docstring was not true. Three clauses were pinned by no test. |
| The build | A second model | Does not land yet: one more case of a storage defect that was there before, and one cost the build added. |

## Found in the build and fixed

Commits `1bd12ca1` and `1c8577f3`.

| Found | Fix |
|---|---|
| The docstring said a directory row is left out without an error. A directory row at a mount point, or the row of the root, makes the call fail with `invalid`. The failure was there before the build. | The docstring and the spec say what happens. A test pins it. |
| With no filter at all, the kernel read the extension of every row, where it did no work before. 10,000 rows gave 10,000 reads. | With no filter the rows are passed on untouched. A test counts the reads. |
| The filter's `truncated` record could come before the storage's own records with every test passing. | A test asserts the order. |
| The closed check in the new branch could be deleted with every test passing. | A test: a closed kernel given a batch that is not rows answers `backend_unavailable`. |
| "A filter of `ext` alone reads no clock" was not pinned. | The test counts reads of the clock. |
| Nothing pinned that the sync face and a session pass the filters through. | One test for both. |

All ten decisions of the spec were found kept. On ordinary files, 18 filter sets gave the same rows as `grep`, across two mounts, before and after indexing.

## Found and left, each a task in `agents/tasks.md`

- A row at a mount point, the row of the root, and the row of the trash view's head each make `search` over rows in hand fail with `invalid`, where `grep` given the same row succeeds. The storage turns the path `/` into a glob.
- `search` without `observations` does not expand a brace pattern in the kernel, as `grep` does.
- `grep` over a held row in the trash view matches nothing and reports nothing.
- 10,000 rows in hand take 8 to 9 seconds on one in-memory storage, against a budget of 10.
