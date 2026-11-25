# The derived verbs are pinned to their definitions by oracles

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. It was checked against `dev` at `27f3d24d`, and against the open branch `origin/edit-requires-a-vid` at `85880fed` for the guarded `edit`. It serves no roadmap story and no gate: it is unit 181-4 of [the backlog conversion](../2026-11-25-the-backlog-converted/units.md), unplaced. It is converted from section 5, criterion 17 and task 9 of [spec 181](../../context/specifications/archive/181-the-public-surface-regrouped-by-kernel-group/spec.md), read through [the reassessment of 181-4](../2026-11-25-the-backlog-converted/reassessment/history-and-surface.md). It rests on the listing cursor, which is built, and on the third landing of the vid spec, which is reviewed and not merged.

## The outcome wanted

A reader of the test suite finds one readable definition of `tree` and of `edit` in terms of the verbs they are derived from, and a test on every engine leg that goes red when a storage's own answer departs from that definition.

- `tree` of a path, asked whole or drained a page at a time, returns the same rows in the same order as `ls` of that path and of every directory beneath it, each `ls` drained a page at a time, collected and sorted by path. "The same rows" means every field, the populated mask and the `vid` included, at the system actor and at named callers who see only part of the tree.
- `edit` of a file returns what a `read` of the file, the same edits applied to the text, and a `write` that requires the vid the read returned would return: the same status, version, body, media type and refusal kind. The composition, given a rival write between its read and its write, is refused `conflict` and leaves the rival's body.
- The third clause of the unit's title, `delete(cascade=False)` on a non-empty directory answering `not_empty`, is built and pinned on `dev`, and is cited, not specified again.

Two later pieces of work then have a referee: a reshaped `tree` push-down (the shallow page and the Postgres subtree range), and the kernel's synthesized `tree` and `edit` for a storage that has neither (unit 179-10).

## Builds on

- [The listing spec](../2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md), built on `dev`. `ls` and `tree` take `after=` and `limit=` at the kernel (`src/vfs/base.py:847`, `:884`) and at the seam (`src/vfs/storage/protocol.py:161-181`), and a page carries `Result.next_after` (`src/vfs/results/envelope.py:367`). `tests/support/cursor_contract.py:1-7` already pins that each paged listing equals itself asked whole, so this spec compares the two verbs and never a verb with itself.
- The `not_empty` clause, built on `dev`: `delete` takes `cascade: bool = True` (`src/vfs/base.py:1077`) and its docstring says a non-empty directory is refused `not_empty` (`:1091-1092`). It is pinned by `tests/support/storage_contract.py:862-868` on every conformance leg and by `tests/storage/database/test_trash.py:233-235` at the database layer. Nothing here touches it.
- [The vid spec](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md), on `dev` as a spec and built on the branch series `origin/every-row-carries-a-vid`, `origin/write-requires-a-vid` and `origin/edit-requires-a-vid`, each an ancestor of the next (EXECUTED, `git merge-base --is-ancestor`). Each is reviewed "lands" and none is merged. The shapes relied on, by its decision numbers:
  - Decision 4: every whole row of `ls`, `tree` and `read` carries a `vid`, and a bare row carries none.
  - Decision 6: the seam's `write` and `edit` take `if_vids: Mapping[Path, Vid]` (`origin/edit-requires-a-vid:src/vfs/storage/protocol.py:200`, `:213`).
  - Decision 7, ruled 2026-11-23: `if_version` and `if_versions` leave every face and the seam.
  - Decision 9: `edit` judges a required vid after the miss and before every other judgment of the row, so its body is not looked at (`origin/edit-requires-a-vid:src/vfs/storage/backends/database/writes.py:1450`).
  - Decision 18: the mark `ABSENT` in place of a vid; on `edit` it refuses a file that is there with `conflict`.
  - Decision 19: one constructor, `vfs.results.stale_vid(path, version, vid)`, makes the refusal of a failed precondition "word for word and key for key" for a storage and for the kernel (`origin/edit-requires-a-vid:src/vfs/results/envelope.py:308`).
- The build order: this unit is built on `dev` once `origin/edit-requires-a-vid` has merged. It replaces the unit's recorded dependency 174-3, [the write-preconditions spec](../2026-11-20-write-takes-preconditions-and-an-append/spec.md), built on `dev` with `if_version=` (`src/vfs/base.py:932`) and being replaced by the vid series. Decision 8 of the dated kernel rulings, `if_version=` as the spelling, is superseded by the vid spec's decision 7, so nothing here is written against `if_version`.
- The shared edit semantics, built on `dev`: `vfs.storage.editing.edited_entry` (`src/vfs/storage/editing.py:30`) is the one function every backend runs to apply edits and re-validate the text, "so it cannot drift" (its module docstring).
- The conformance harness, built on `dev`: `StorageContract`, `GrantsContract` and `CursorContract` mix into `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance` (`tests/storage/test_conformance.py:65`, `:102`, `:182`); the vid branch adds `VidContract` to the same three (`origin/edit-requires-a-vid:tests/storage/test_conformance.py:66`, `:103`, `:183`).
- The random grant worlds, built on `dev`: `tests/support/grant_worlds.py` with its `SIBLINGS` layout of names that sort beside each other in byte order (`:47-66`), and the replay helpers `_replay` and `_authority` of `tests/storage/database/test_rights.py:102`, `:121`.
- Units of this conversion, neither built. [Unit 179-1](../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md) splits the contracts into a package of mixins; whichever lands second moves the mixin of decision 8. [Unit 179-10](../2026-11-25-a-backend-that-lacks-a-derivable-verb-is-still-served-it/spec.md) synthesizes `tree` and `edit` for a storage without them, and its fallback is held to the oracles of this spec.

## Terms

- **Oracle.** A readable reference implementation under `tests/support/oracles/`, kept only where a parity test reads it, and shipped in no wheel (AGENTS.md, Tooling).
- **Push-down.** A storage's own answer to a derived verb: one subtree select for `tree` (`tree_rows`, `src/vfs/storage/backends/database/listings.py:142`), one transaction for `edit` (`edit_rows`, `src/vfs/storage/backends/database/writes.py:280`).
- **Drained.** A listing asked page after page, each page `after=` the `next_after` of the one before, until `next_after` is `None`.
- **Partial view.** What a named caller under a restrictive posture sees: whole rows where it holds `read`, bare rows (`path` and `kind` only) where it holds `list` or where a hidden directory is the road down to a row it may see, and nothing elsewhere.

## What the code does today

- `ls` lists a directory by `parent_id`, and under a partial view "a road directory lists like any directory, a row the caller holds only `list` on shows bare, and a hidden child directory shows as a bare name only when it is itself on the road" (`listings.py:88-92`). `tree` reads the subtree in one select and shows each visible row's hidden ancestors as bare road rows (`listings.py:160-164`, `:205-213`).
- `tree` orders by the binary-collated `path` column, byte-identical across engines (`listings.py:6-8`). Path order is not the order of a depth-first walk: `/t/a-x` sorts before `/t/a/b`, because `-` is below `/` (EXECUTED).
- The native `edit` judges a target in this order on the vid branch: the rights of every live target at the verb's rung (`origin/edit-requires-a-vid:src/vfs/storage/backends/database/writes.py:318`), the miss, the required vid (`:1450`), a bytes-sourced body as `wrong_kind`, then the edits through `edited_entry`. It stages the update with the row's own `mime_type` and `owner_id` (`src/vfs/storage/backends/database/writes.py:1384-1414` on `dev`).
- A `read` of a bytes-sourced file returns its text rendering as `content`, with `source == "bytes"` (`src/vfs/storage/backends/database/reads.py:937`). Writing that text back would turn the file's bytes into text. A file whose rendering is pending reads with no content.
- A `write` that replaces a file and names no `mime_type` stores none, where `edit` keeps the row's: a file written with `text/markdown` read `text/markdown` after `edit` and `None` after read, apply and `write` (EXECUTED on dev, in-memory storage). The stored `owner_id` survives both (EXECUTED).
- On `dev` on 2026-11-25, with a scratch oracle over the in-memory storage (EXECUTED):
  - `tree` against `ls` drained: 360 comparisons over one seeded world of each layout (`random.Random(181)`), one file deleted in each, at the system actor and the five subject sets, at the root and four directories, at `max_depth` `None`, 1 and 2, and at `limit` `None` and 1: no mismatch. A fixed world with a cascaded deleted directory, a deleted file, a non-ASCII name and `columns={"size_bytes"}`: 18 comparisons, no mismatch. The 360 comparisons took 23 seconds of wall time with process start, recorded only to size the seeded test.
  - `edit` against read, `edited_entry` and `write(if_versions=)` on files of identical history: the same answer for a read-write, a read-only, a list-only and a hidden caller (`updated` at version 2, `permission_denied`, `permission_denied`, `not_found`) and at the system actor for a missed edit, a NUL in the result and an edit whose `old` equals its `new` (`invalid`), a bytes file and a directory (`wrong_kind`), a missing path (`not_found`), and two edits that restore the body (`unchanged`, version 1). The populated masks of the result rows were equal. A rival write between the read and the write was refused `conflict` with `data == {"version": 3}` and its body stayed.

## The problem

Spec 181 calls `tree` and `edit` derived: built from kernel calls, storing no fact of their own. Nothing in the tree says what they are derived from, and no test would see a push-down depart from it. The existing `tree` tests compare against hand-written path lists of a few rows (`storage_contract.py:525-578`), and none is asked at a partial view against `ls`.

Three pieces of work will change or replace the push-downs. [The shallow tree page](../2026-11-21-a-shallow-tree-page-reads-only-its-depth/spec.md) adds a depth column to `tree`'s read. [The Postgres subtree range](../2026-11-21-postgres-reads-a-subtree-by-its-range/spec.md) reads a subtree by an explicit range. Unit 179-10 synthesizes both verbs for a storage that lacks them. Each needs a referee whose answer is right by construction, at a partial view, where a wrong row is a leak.

The composition is the definition and never the product. At the reference deployment's 1,000,000 directories, `tree` composed from `ls` is one call per directory; the push-down is a fixed handful of statements a call (see Cost). `edit` composed from a read and a write loses a rival's change unless the write is guarded, and since `if_version` leaves, the guard is a vid.

## Decisions

1. **The oracles live in `tests/support/oracles/derived.py`, as two async functions over the storage seam.** Reason: AGENTS.md places the readable reference implementations there, and they ship in no wheel. The seam is where both push-downs live; the kernel routes `tree` and `edit` to one storage call each (`base.py:917-919`, `:1069`). The package docstring of `tests/support/oracles/__init__.py` gains one sentence: an oracle may compose the seam's own verbs, as `derived.py` does, and still never imports `vfs.native`, which `tests/test_oracles.py:12-18` already enforces over every module of the package.

2. **The `tree` oracle is `ls` repeated, drained, and sorted by path.**

   ```python
   async def tree(storage, path: Path, *, max_depth: int | None = None, limit: int | None = None,
                  columns: frozenset[str] | None = None, authority: Authority | None = None) -> Result: ...
   ```

   It asks `ls(path)` at `columns` and `authority`. A refusal is its answer. A single row whose path is `path` and whose kind is not `directory` is its answer, since `ls` of a file lists the file. Otherwise every directory row is listed in turn by `ls`, drained at `limit`, starting from `path` at depth 0: a row at depth `k` is kept, and listed when it is a directory and `max_depth` is `None` or `k < max_depth`. A bare road directory is listed like any other, as `ls` promises. The rows are returned in `Result(ops=("tree",), observations=...)` sorted by `str(row.path)`. Reason: `tree_rows` promises "every row beneath *path*, in path order, to *max_depth* levels" (`listings.py:155`), Python's code-point order of a `str` is UTF-8 byte order, and that is the binary collation the column carries. The sort is load-bearing: a depth-first walk gives `/t/a/b` before `/t/a-x`. The oracle takes no `after`, because it compares whole drains, and no `max_depth` below 1, which the push-down refuses `invalid` and `storage_contract.py:568-572` pins.

3. **`tree` and its oracle are compared whole, row for row.** Each side's rows are compared as `[row.model_dump() for row in rows]`, in order, so every field, the populated mask and the `vid` count. Each refusal is compared as `[(error.kind, error.path) for error in errors]`. Reason: "row for row" at a partial view means the mask too, since a leak is a field populated where it should be bare. Both sides read one storage, so a row's vid is the same on both.

4. **`tree` is drained at the oracle's `limit`.** The test asks `storage.tree` at `limit=None` once and at `limit=1` page after page, and compares each with the oracle at the same `limit`. Reason: `limit=1` puts a key after every row, in both verbs' cursors, and is the case the listing spec's road rule is hardest on ("a road directory counts toward `limit` and can be the key").

5. **The `edit` oracle is a read, the shared edit semantics and a write that requires a vid.**

   ```python
   async def edit(storage, path: Path, edits: list[EditOperation], *, if_vid: VidOrAbsent | None = None,
                  between: Callable[[], Awaitable[object]] | None = None,
                  authority: Authority | None = None) -> Result: ...
   ```

   Its steps, in this order:
   1. `read(path)` at `authority`; a refusal is its answer.
   2. The vid required is `if_vid`, or the read row's `vid` when none is given. When it is not the read row's vid, the answer is `stale_vid(path, row.version, row.vid)`, and the edits are not applied. The mark `ABSENT` is never a vid, so it is always refused here.
   3. A row with `source == "bytes"` is `wrong_kind`.
   4. `edited_entry(path, kind=row.kind, content=row.content, edits=edits)`; a `ResultError` is its answer.
   5. The entry written carries the read row's `mime_type`.
   6. `between`, when given, is awaited.
   7. `write(entries=[entry], if_vids={path: required})` at `authority`; its `Result` is the answer.

   Reason for step 2's place: the vid spec's decision 9 judges the vid before the body is looked at, so a stale vid with an edit that would miss is `conflict` and not `invalid`, and decision 19 makes the refusal through one constructor so the oracle's words and data are the storage's. Reason for step 3: a read of a bytes-sourced file returns its rendering, and the native edit refuses it (`writes.py:1169`). Reason for step 4: the replacement engine is one meaning for every backend, so the oracle pins the composition, not the matcher. Reason for step 5: without it the oracle drops a media type the native edit keeps (EXECUTED). No step carries `owner_id`, because a replacing write keeps the stored owner (EXECUTED).

6. **`edit` and its oracle are compared on two files of identical history in one storage.** Each case writes the same body to a native file and an oracle file in one directory, runs `storage.edit(edits=..., path=native, if_vids=...)` on the first and the oracle on the second, and compares: `success`; each result row's `status`, `version`, `kind`, `size_bytes` and populated mask; each result row's `vid` equal to the vid a `stat` of its own path returns afterwards; after the call, each file's `content`, `content_hash`, `mime_type`, `source` and `version` from a `read`; and each refusal's `kind`, with its path the side's own file, and for `conflict` its `data["version"]` equal and its `data["vid"]` equal to the `stat` vid of its own file. Reason: a vid is minted from the entry id (the vid spec's decision 2), so two files never share one, and each side's vid is checked against its own row instead.

7. **The `edit` cases are these, at the system actor unless named.**

   | Case | Body before | Edits or vid | Both answer |
   |---|---|---|---|
   | Two edits in sequence | `hello world` | `hello`→`hi`, `hi world`→`hi there` | `updated`, version 2 |
   | A later edit misses | `hello world` | `hello`→`hi`, `nonexistent`→`x` | `invalid`, body kept |
   | The result holds a NUL | `clean text` | `clean`→`cl\x00ean` | `invalid` |
   | `old` equals `new` | `hello` | `hello`→`hello` | `invalid` |
   | Two edits restore the body | `ab` | `a`→`c`, `c`→`a` | `unchanged`, version 1 |
   | `replace_all` | `a a a` | `a`→`b`, every match | `updated` |
   | A media type set by the caller | `hello`, `text/markdown` | `hello`→`hi` | `updated`, `text/markdown` kept |
   | A bytes-sourced file | `b"\x00\x01"` | `a`→`b` | `wrong_kind` |
   | A directory | none | `a`→`b` | `wrong_kind` |
   | A missing path | none | `a`→`b` | `not_found` |
   | A deleted file | `hello`, then deleted | `hello`→`hi` | `not_found` |
   | The vid of the read, given | `alpha` | `alpha`→`beta`, `if_vid` the read's | `updated` |
   | A stale vid, with an edit that would miss | `alpha`, then `gamma` | `zzz`→`y`, `if_vid` of `alpha` | `conflict`, the row now there in `data` |
   | `ABSENT` over a file | `alpha` | `alpha`→`beta`, `if_vid=ABSENT` | `conflict` |
   | A caller holding `read_write` on the directory | `hello world` | `hello`→`hi` | `updated` |
   | A caller holding `read` | `hello world` | `hello`→`hi` | `permission_denied` |
   | A caller holding `list` | `hello world` | `hello`→`hi` | `permission_denied` |
   | A caller holding nothing | `hello world` | `hello`→`hi` | `not_found` |

   The last three vid rows run also at the `read_write` holder. Reason: the first eleven are the edit battery of `storage_contract.py:808-844` and the rows the probe ran; the vid rows are the native pins of `origin/edit-requires-a-vid:tests/support/vid_contract.py:334-399`; the four callers are the rungs below and at the verb's.

8. **The rows that require a vid run only at callers who hold `read_write`.** Reason: the native edit judges rights before the vid (`writes.py:318` before `:1450` on the branch), while the oracle's read passes at the `read` rung, so for a caller below `read_write` a stale vid is `permission_denied` natively and `conflict` in the oracle. That order is the storage's own, judged in one snapshot, and is no part of what `edit` is derived from. The same holds for a required vid over a directory, which the native edit answers `conflict` from the directory's row and the oracle's read answers `wrong_kind`; `vid_contract.py:362` pins the native answer.

9. **The oracle, given a rival write between its read and its write, is refused.** The test passes a `between` that writes a new body to the oracle file as the system actor. The answer is `conflict` with `data` naming the rival's row, its `version` and the vid a `stat` returns, and a read afterwards returns the rival's body. Reason: this is what "guarded" means, and spec 181's section 5 item 2 asks for it. The native `edit` has no gap to stage, because it matches and replaces in one transaction.

10. **The parity tests are a contract mixin, `DerivedContract`, in `tests/support/derived_contract.py`, mixed into the three conformance classes.** Its fixed world is built in the module through the seam as the system actor: `/t/a/b/c.txt`, `/t/a/b.txt`, `/t/a-x/é.md`, `/t/h/secret.txt`, `/t/h/pub/ok.txt`, `/t/z.txt`, `/t/bin.dat` (bytes), the empty directory `/t/empty`, the directory `/t/gone` holding `f.txt` and `g/h.txt` and deleted with its cascade, and the file `/t/f0.txt`, deleted. The posture at `/` is `none`; `bob` holds `read` on `/t/a` and on `/t/h/pub`, and `list` on `/t/a-x` and on `/t/z.txt`. Reason: `CursorContract` and `VidContract` are mixed the same way, so the Postgres leg runs it and checks the byte order of `é` and `-` on a server collation. The names hold a sibling that sorts before `/` (`a-x`), a file beside a directory of the same stem (`b.txt`), a non-ASCII name, a road directory (`/t/h`), a list-only file and a list-only directory, and tombstones in the range. If unit 179-1 has landed first, the mixin is `tests/support/contract/derived.py` in its package, with the same class.

11. **A seeded test runs the `tree` oracle over random grant worlds, in the heavy tier.** `tests/storage/database/test_rights.py` gains one test that draws one world of each layout from `random.Random(181)`, replays it with `_replay`, deletes the layout's second file, and compares `tree` with the oracle at `/` for the system actor and each of `SUBJECT_SETS` through `_authority`, at `(max_depth, limit)` of `(None, None)`, `(None, 1)` and `(2, None)`: 36 comparisons. It is marked `slow`. Reason: the random worlds hold nested postures, group memberships and owner floors that no fixed world states, on the memory leg, where `_replay` builds them. Thirty-six comparisons are a tenth of the probe's 360, so about two to three seconds; the fixed world carries the engine legs.

12. **No code under `src/` changes.** No router fallback is built from the oracles, no docstring changes (choice 1), and the push-downs are not touched. Reason: every shipped backend answers both verbs natively, and a synthesized fallback is unit 179-10's, which must equal these oracles.

13. **Each test is seen failing before the suite is called green, by a mutation of the oracle.** The mutations: drop the sort of decision 2; descend one level past `max_depth`; drop step 2, step 3 or step 5 of decision 5; pass no `if_vids` in step 7. Each is applied to a backup-guarded copy and restored from the backup, as AGENTS.md's git rules require. Reason: the push-downs already exist, so a parity test written first passes at once; a test that no mutation turns red pins nothing.

## Cost

Nothing ships: no statement, loop or structure is added under `src/`, so no multiplier of the reference deployment applies to the product.

The tests' own work, by count. On the fixed world of decision 10, one `tree` comparison drains `ls` once per directory listed: at most seven directories, so at most eight `ls` calls whole, and at `limit=1` one page per row and one per directory, at most about 30 calls. Each `ls` is a fixed number of statements, three for the system actor and five for a named caller (the listing spec's measured table). Twelve `tree` comparisons a leg (two authorities, three depths, two limits) are under 400 `ls` calls. The eighteen `edit` rows are one native call and one read and one write each. The seeded test is 36 comparisons on the memory leg alone.

The figure recorded for unit 179-10, which composes `tree` this way for a storage without its own: one `ls` per directory. At the reference deployment's 1,000,000 directories a whole-corpus `tree` composed from `ls` is 1,000,000 calls, about 5,000,000 statements for a named caller, against the push-down's five statements and its rows. That is per verb call, about 150,000 a day across every verb, so a fallback built on the oracle is a profile its docstring must state, and never the push-down a served engine uses.

## Left as it is

- **The order of a rights refusal and a vid refusal** for a caller below `read_write`, and the answer to a required vid over a directory. Each is the native edit's own judgment in one snapshot, pinned by the vid contract (decision 8).
- **A plain replacing `write` that names no `mime_type` stores none.** The oracle carries the type explicitly, as a caller that reads and writes back must. Whether `write` keeps the stored type is a question for `write`, not for this pin.
- **The trash view.** `ls` of `/.vfs/trash` lists the tombstoned roots at every depth (`listings.py:96-103`), so it is not `ls` repeated, and no oracle claims it.
- **The kernel across mounts.** `tree` crossing a mount is not compared with `ls` repeated (choice 3).
- **The push-downs.** Their statements and costs are unchanged; the cursor contract and the listing spec's counts hold them.

## Tests

Written before the suite is called green, and each seen failing by decision 13's mutations. Counts and states, never clocks.

In `tests/support/derived_contract.py`, class `DerivedContract`, run on the memory, SQLite-file and Postgres legs through `tests/storage/test_conformance.py`:

- `test_tree_equals_ls_repeated`, parametrized over the authority (`system`, `bob`), `max_depth` (`None`, 1, 2) and `limit` (`None`, 1): twelve cases, at `/t`, by decisions 2 to 4.
- `test_tree_of_a_file_equals_ls_of_it`, at `/t/a/b.txt` for both authorities and at `/t/z.txt` for `bob`, where the row is bare.
- `test_tree_refusals_equal_ls_refusals`: `/t/nope` for both authorities and `/t/h/secret.txt` for `bob` are `not_found` from both.
- `test_tree_with_columns_equals_ls_repeated_with_columns`, at `columns={"size_bytes"}`, for both authorities.
- `test_edit_equals_read_then_a_guarded_write`, parametrized over the rows of decision 7's table, by decision 6's comparison.
- `test_the_oracle_refuses_a_rival_write_between_its_read_and_its_write`, by decision 9.

In `tests/storage/database/test_rights.py`: `test_tree_lists_what_ls_repeated_lists_in_every_world`, marked `slow`, by decision 11.

`tests/test_oracles.py::test_oracles_import_nothing_from_the_seam` covers the new oracle module unchanged, since it walks every module of the package.

The partial-view cases are the leak pin of `tree` against `ls`: a row or a field `ls` withholds from `bob` that `tree` returns fails decision 3's comparison. No right changes, so no further leak test is needed.

The Postgres leg runs through the `db_test` skill, on the server CI runs; every row of `DerivedContract` runs there.

## Scope

In: `tests/support/oracles/derived.py`, new; one sentence in the docstring of `tests/support/oracles/__init__.py`; `tests/support/derived_contract.py`, new; the import and the three class lines of `tests/storage/test_conformance.py`; one test in `tests/storage/database/test_rights.py`.

Out:

- `delete(cascade=False)` and `not_empty`, built and pinned (Builds on).
- A synthesized `tree` or `edit` in the kernel: unit 179-10.
- `tree` across mounts at the kernel: [the mount-point listing draft](../2026-11-21-a-listing-at-a-mount-point-is-read-again/spec.md) first (choice 3).
- The shell's `sed -i` guarded write, which spec 181's section 5 item 3 asked for: [the sed spec](../2026-11-22-shell-sed-edits/spec.md) sends `if_vid` from its session's stamp.
- The kernel's docstrings of `tree` and `edit` (choice 1), and the regrouping of the faces: unit 181-1.
- A cheaper `tree` under `max_depth`: the shallow tree page spec, which this pin then referees.

## Earlier decisions this reverses

- Spec 181 section 5 item 1 wrote the `edit` oracle over the router `fs`, as `read(path, columns={"content", "version"})` then `write(..., if_version=<the read's version>)`. Here it is over the seam, reads the default columns because it needs `source`, `mime_type` and `vid`, and requires the read's vid through `if_vids`, by the vid spec's decision 7.
- Spec 181 section 5 wrote three docstring sentences for `tree`, `edit` and `delete`. The `delete` sentence is on `dev` already; the other two are not written (choice 1).

## Not checked

- Nothing was run on the vid branch: it was read with `git show` and never checked out. The `edit` probe ran on `dev` with `if_versions` in place of `if_vids`, so the three vid rows of decision 7 and the vid half of decision 6 rest on the branch's code and its `vid_contract.py` as read.
- No probe ran on Postgres. The byte order of `é` and `-` there rests on `listings.py:6-8` and the listing spec's legs.
- Whether a `stat` on the branch returns the same vid a `write` result row carries, which decision 6 compares; the branch's `vid_contract.py:168` pins one vid from every verb, read and not run.
- `tree` against `ls` repeated at the kernel across nested mounts, healthy or failing.
- The seeded test's time at 36 comparisons; the two to three seconds are scaled from the 360-comparison probe.
- The listing spec's statement counts, three and five, on today's code; the Cost section takes them from its landing notes.

## Choices to confirm

1. **Do the kernel's `tree` and `edit` docstrings state the definition?** Taken: no. `src/vfs/base.py` is held at its exact line count by `MODULE_LINE_BASELINE` (3,090 on `dev`, 3,123 on the vid branch, `tests/lint/allowlist.py`), so each sentence forces lines out of the module, and a docstring change runs the docs gate. The definition lives in the oracle module, and the sentences can be added later with nothing to undo. The other side writes spec 181's two sentences.
2. **One pull request, after the vid landing?** Taken: yes. The `tree` half needs nothing unbuilt and could land now; the two halves share one oracle module and one mixin, and the vid landing is reviewed "lands". Splitting is cheap if the vid series stalls: the `tree` half lands alone with the same tests.
3. **Is `tree` compared with `ls` repeated at the kernel across mounts?** Taken: no, until the mount-point listing draft lands. That draft names defects in `tree` at a mount point, so the comparison may be red on `dev` for reasons this unit does not fix. The other side adds a kernel-level row over a nested mount now and marks the known divergences.

## One line

A readable oracle defines `tree` as `ls` repeated and sorted by path and `edit` as a read, the shared edits and a write that requires the read's vid, and a conformance mixin on every leg, with a seeded test over random grant worlds, holds both push-downs to it at the system actor and at partial views.
