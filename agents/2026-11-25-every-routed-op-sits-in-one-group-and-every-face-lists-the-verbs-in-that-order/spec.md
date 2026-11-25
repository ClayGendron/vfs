# Every routed op sits in exactly one group, and every table and face lists the verbs in that one order

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. It was checked against `dev` at `27f3d24d`. It serves criterion 2 of roadmap story K9 (`context/standards/roadmap.md:212`, `:218`), gate b. It is converted from [the archived spec 181](../../context/specifications/archive/181-the-public-surface-regrouped-by-kernel-group/spec.md), sections 1, 2 and 7, called spec 181 below, and it rests on the kernel rulings' decision 4, roadmap row D5 (flat names, decided) and roadmap row D63 (`run` kept, a lean).

## The outcome wanted

A reader of `vfs.ops` finds every routed op in exactly one named group: `filesystem`, `query`, `history`, `rights`, `derived` or `execution`. The `Op` literal, the needs table `VERB_RUNGS`, the parameter table `PARAMS` and the four public faces (`AsyncVirtualFileSystem`, `VirtualFileSystem`, `AsyncSession`, `Session`) list the 25 verbs in the order the groups give, and `cli` comes after them on every face. A drift test in `tests/test_ops.py` fails by name when a verb joins `Op` without a group, sits in two groups, or is defined out of order on a table or a face. Later verbs register in that one table: `versions` (story K8) joins `history`. No call changes, no name changes, and no row a caller gets back changes.

## Builds on

- The kernel rulings, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`, built as a ruling. Decision 4: "The verbs stay flat methods; kernel groups are documentation and freeze nothing", and "which names the README, the reference pages and `ops.py` share is decided when spec 181 is converted". Decision 3: the verb that destroys for good is `destroy`, and `sweep` is retired as a name when the deletes spec lands. Roadmap row D5 records decision 4 as decided (`roadmap.md:1216`).
- Roadmap row D63, a lean and not a ruling (`roadmap.md:1274`): `run` is "Kept. One verb means the gate, the policy and the log see a tool the same way from Python and from a line ... K9 criterion 1 changes to match." The interrupt draft, on the open branch `origin/a-call-is-interrupted-and-the-host-asks` at `agents/2026-11-21-a-call-is-interrupted-and-the-host-asks/spec.md`, decision 7: "One public verb runs a tool: `run(path, arguments=, stdin=)`. It is on the router today, with nothing behind it." This spec relies on `run` being an op; it does not rely on its signature. Unit 167-1, the retirement of `run`, is not built and is not waited for: choice 1 says what happens if D63 is ruled the other way.
- The ruling of 2026-11-22 that `cli` is a front and not an op, built on `dev`: `FRONT_METHODS = frozenset({"cli"})` (`src/vfs/ops.py:115`), pinned by `tests/test_ops.py::test_the_shell_is_a_front_and_no_op` (`:288`). The roadmap's state line for K9 records it (`roadmap.md:214`), and so does the shell's acceptance, criterion 8 (`agents/2026-11-21-the-shell-speaks-bash/acceptance.md:27`): `OpGroup`'s derived verbs "are not its place".
- The four faces, built on `dev`: `src/vfs/base.py:251`, `src/vfs/sync.py:88`, `src/vfs/session.py:52`, `src/vfs/sync_session.py:36`, from the archived specs `context/specifications/archive/2026-11-06-the-sync-facade.md` and `context/specifications/archive/2026-11-06-the-two-faces-named.md`. The verb names `search` and `traverse` are from `context/specifications/archive/2026-11-09-the-verbs-take-the-names-agents-know.md`.
- The deletes spec, fit to build and not built, on the open branch `origin/a-deleted-row-gives-up-its-path` at `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md`. Its decision 11: "`destroy` takes `sweep`'s place on the four faces, in `Op`, in `VERB_RUNGS`, in `DEVELOPER_OPS` and on the seam, with its default path `/.vfs/trash`. `sweep` is removed in the same landing, with no second name kept." Build order: this unit is best built after the deletes spec lands, and decision 9 says what each order does.
- Units of this conversion that build on this one: [180-1](../2026-11-25-a-files-replaced-versions-are-listed-newest-first-in-pages-with-who-wrote-each/spec.md) registers `versions` in `history`; [179-2](../2026-11-25-the-storage-protocols-are-regrouped-into-families-before-the-freeze/spec.md) regroups the storage protocols by these groups; [181-3](../2026-11-25-chaining-moves-onto-the-result-and-the-query-verbs-lose-rows-in-hand/spec.md) and [170-1](../2026-11-25-a-callers-rung-at-many-catalogue-paths-is-one-chunked-statement-per-budget-slice/spec.md) name it as a dependency.

## Terms

- **Group.** What kind of fact an op touches, or that it is built from other ops. One value of `OpGroup`.
- **Dispatch class.** How the router routes and gates an op: `MUTATING_OPS`, `TWO_PATH_OPS`, `READ_OPS`, `EXEC_OPS`, `GRANT_OPS` (`src/vfs/ops.py:68-98`). It is a second axis, independent of the group.
- **Surface order.** The 25 ops in the order of the group table, group by group. `SURFACE_ORDER` in `vfs.ops`.
- **Face.** One of the four public classes whose methods are the verbs.

## What the code does today

- No `OpGroup`, `OP_GROUPS`, `GROUP_OF` or `SURFACE_ORDER` exists under `src/vfs` or on any open branch (EXECUTED by the reassessment, `agents/2026-11-25-the-backlog-converted/reassessment/history-and-surface.md`, section 181-1).
- The verbs are listed in three orders (EXECUTED, a probe with `uv run python` on 2026-11-25):
  - `Op` (`src/vfs/ops.py:38-64`): `read, write, edit, delete, restore, sweep, stat, mkdir, mkedge, rmedge, move, copy, ls, tree, glob, grep, search, traverse, run, grant, revoke, grants, set_posture, add_member, remove_member`.
  - `VERB_RUNGS` (`src/vfs/ops.py:151-177`): `read, stat, ls, tree, glob, grep, search, traverse, write, edit, mkdir, delete, restore, move, copy, mkedge, rmedge, grant, revoke, set_posture, grants, run, sweep, add_member, remove_member`.
  - `PARAMS` (`src/vfs/params.py:155`) and the ops of all four faces: `read, stat, ls, tree, write, edit, delete, restore, sweep, mkdir, mkedge, rmedge, move, copy, glob, grep, search, traverse, run, grant, revoke, grants, set_posture, add_member, remove_member`.
- `cli` sits in two places. It comes before `run` on `AsyncVirtualFileSystem` (`base.py:1668`, `:1679`) and `AsyncSession` (`session.py:414`, `:419`), and after it on `VirtualFileSystem` (`sync.py:589`, `:598`) and `Session` (`sync_session.py:361`, `:364`).
- The faces carry banners by kind, not by group: `base.py` has `public methods — reads`, `— mutations`, `— find`, `— execution`, `— grants` (`base.py:799`, `:922`, `:1294`, `:1665`, `:1699`); the other three have `reads`, `mutations`, `find, execution`, `grants` (`sync.py:264-602`, `session.py:94-425`, `sync_session.py:77-370`).
- The tests pin the sets and never an order: `tests/test_ops.py::test_expected_vocabulary` (`:74`), `test_every_op_has_exactly_one_rung_entry` (`:129`), `test_router_public_verbs_are_exactly_the_registered_ops` (`:273`), `tests/test_params.py:24` (`set(PARAMS) == ALL_OPS`).
- `src/vfs/base.py` holds 3,090 lines, its exact entry in `MODULE_LINE_BASELINE` (`tests/lint/allowlist.py:27`), and a listed module that grows fails `tests/lint/test_code_shape.py::test_a_listed_module_never_grows_and_an_unlisted_one_stays_under_the_ceiling`.

## The problem

The op vocabulary says how each verb is routed and nothing about what kind of verb it is. A reader of the surface sees reads, then mutations, then search, then grants, with `restore` among the mutations and `tree` among the reads, and three tables that disagree on order. Story K9 needs one place where a later verb registers before the beta freezes the surface: K8's `versions` is the first. Without an order test, a verb added at the bottom of `base.py` or out of place in `PARAMS` passes every test today. Nothing here runs per call, so the reference deployment's multipliers do not apply; the cost of the problem is to readers and to the freeze.

## Decisions

1. **`OpGroup` has six names: `filesystem`, `query`, `history`, `rights`, `derived`, `execution`.** The first five are K9 criterion 2's (`roadmap.md:218`), which was written while `run` was to be retired. D63 keeps `run`, and `run` fits none of the five: it changes no stored fact and reads none in the sense of the kernel groups, and it has no definition from other ops, which is what `derived` means. Its dispatch class is already its own (`EXEC_OPS`, `ops.py:89`), the face banner on `dev` already names it `execution` (`base.py:1665`), and the README already shows it as its own family, `Execute` (`README.md:73`). The noun `execution` follows that banner and `how-we-name.md`'s rule that one concept has one noun. This adds a sixth name to K9's five; choice 1 records it.
2. **The table is, in this order:**
   - `filesystem`: `stat`, `ls`, `read`, `write`, `mkdir`, `delete`, `move`, `copy`.
   - `query`: `glob`, `grep`, `search`, `traverse`, `mkedge`, `rmedge`.
   - `history`: `restore`, `destroy`.
   - `rights`: `grant`, `revoke`, `grants`, `set_posture`, `add_member`, `remove_member`.
   - `derived`: `tree`, `edit`.
   - `execution`: `run`.

   Reason: spec 181 section 1's table, with four corrections against `dev`. `glean` and `graph` are `search` and `traverse` (the verb-names spec). Spec 181's `posture` is `set_posture`, the code's name (`ops.py:61`). `sweep` is `destroy` (decision 9). `run` is placed (decision 1). Inside a group the order is spec 181's: a name is found before its body is read, a row is made before it is removed, and a grant comes before the list of grants.
3. **The group order is the kernel's four groups, then the facets.** `filesystem`, `query`, `history` and `rights` are the four kinds of stored fact a storage answers for. `derived` and `execution` come after: the derived verbs are built from kernel calls with a storage push-down (spec 181 section 1.5), and `run` hands the call to a tool. `execution` is last so that `run` and the `cli` front sit together at the end of each face, under one banner, as they do on `dev` (`base.py:1665-1697`). The order follows AGENTS.md's rule that groups are ordered by the flow a caller follows.
4. **`vfs.ops` gains `OpGroup`, `OP_GROUPS` and `SURFACE_ORDER`, and nothing else.** `OpGroup` is a `Literal` of the six names, in the order of decision 3. `OP_GROUPS: Final[dict[OpGroup, tuple[Op, ...]]]` is the table of decision 2. `SURFACE_ORDER: Final[tuple[Op, ...]]` is `tuple(op for ops in OP_GROUPS.values() for op in ops)`. They sit directly under `Op`, since a derived constant sits under the public name it comes from (AGENTS.md, File organization). `GROUP_OF`, `CONTROL_METHODS` and a second name for `MANAGEMENT_METHODS`, which spec 181 section 2.1 adds, are left out: nothing in `src/` reads a group by op, and `MANAGEMENT_METHODS` is already in `ops.py` (`:110`). `ty` refuses a name in `OP_GROUPS` that is not an `Op` (EXECUTED on 2026-11-25: a scratch copy of the table naming `destroy` against today's `Op` gave one `invalid-assignment` diagnostic), so the type checker holds the members and the tests hold the coverage and the order.
5. **The `Op` literal, `VERB_RUNGS` and `PARAMS` are rewritten in the surface order.** Each entry moves and none changes. A `Literal` cannot be derived from a table, so `Op` is spelled out and a test pins it to `SURFACE_ORDER`. `ALL_OPS` and the dispatch classes are unchanged. The `ops.py` module docstring gains one paragraph on the two axes: the group says what kind of fact an op touches; the dispatch class says how it is routed and gated; `mkedge` is a mutation in `query`, `restore` a mutation in `history`, and `tree` a read in `derived`. It also says that `cli` is in no group. Reason: spec 181 section 2.1; the docstring states the axis that a reader would otherwise infer from the banners.
6. **`cli` is in no group, and it follows `run` on every face.** It stays in `FRONT_METHODS`, apart from `ALL_OPS` and `MANAGEMENT_METHODS`. Reason: the ruling of 2026-11-22 (Builds on). `cli` spans every mount and no storage answers it, while each verb inside a line is gated as its own op. This departs from K9 criterion 2's "`cli` → `derived`", as the roadmap's state line for K9 already records.
7. **Each face defines its verbs in the surface order, then `cli`, under one banner per group.** The methods move and their bodies do not change. On `base.py` the banners are `public methods — filesystem core`, `— query`, `— history`, `— rights`, `— derived` and `— execution`, in the file's 67-dash form; `cli` sits under `execution` after `run`. On `sync.py`, `session.py` and `sync_session.py` they are `filesystem core`, `query`, `history`, `rights`, `derived` and `execution`, in each file's own banner form. The members before the verbs (`sync.py`'s lifecycle, each face's mount administration and each session's `authority`, `closed` and `close`) stay where they are. Reason: spec 181 section 7.2, adapted to four faces and to the `execution` group.
8. **The drift tests read definition order from each class's `__dict__`, never from comments.** A class's `__dict__` keeps the order of the definitions in its file, so the face test filters it to `ALL_OPS | FRONT_METHODS`. The banners are comments, and no test reads them: a test of comment text breaks on a reworded banner and proves nothing about the surface.
9. **The history group names `destroy`; if this unit is built before the deletes spec lands, the slot holds `sweep`.** Built after the deletes spec, the table is written with `destroy`. Built before it, the table holds `sweep` in the same place, and the deletes spec's rename then carries `OP_GROUPS` too. Its landing cannot miss the table: `test_every_op_sits_in_exactly_one_group` fails as soon as `Op` names `destroy` and the table does not. Reason: the reassessment asks for `destroy` "if it lands first"; neither spec waits on the other, and the test makes the second landing correct.
10. **`OpGroup`, `OP_GROUPS` and `SURFACE_ORDER` stay in `vfs.ops` and do not join `vfs.__all__`.** Reason: decision 4 of the kernel rulings says a group's name is not a public name and freezes nothing. Kept out of `__all__`, the names reach no generated reference page and no freeze list, so a later rename of a group costs one module.
11. **A later op registers in `Op`, in one group of `OP_GROUPS` and in the test's literal table, and a later method that is not an op registers nowhere here.** `test_the_groups_are_the_registered_table` holds the table as a literal, as `test_expected_vocabulary` holds the vocabulary (`tests/test_ops.py:74`), so it is the one test a story edits to add a verb (K9 criterion 2). K8's `versions` joins `history`. The kernel methods later stories add (`fs.calls`, `answer`, `resume`, `cancel`; `roadmap.md:311`, `:348`, `:366`) are management methods, not ops, so they join `MANAGEMENT_METHODS` and no group.
12. **`base.py`'s size entry moves to the exact count the file ends at.** The regroup adds one banner to the file's public verbs (six where there were five): four lines, three for the banner and one blank line. Nothing else in the file grows. Raising the entry by that amount in the same landing has precedent: `885b6a29` (3,091 to 3,103) and `f36595fe` (3,092 to 3,098) each raised it with the change that grew it. Moving code out of `base.py` to make room would mix a refactor into a reorder whose diff is meant to be moves and banners alone.
13. **The README's verb table is not changed.** It keeps its families, Read, Find, Mutate and Execute (`README.md:68-73`). The groups are named in `ops.py` and nowhere in the published docs. Reason: decision 4 of the kernel rulings leaves this to the conversion, the `Find` label is a landed ruling (the verb-names spec), and a README table relabelled by groups would need its own parsing test for a list that freezes nothing. Choice 2 records it.

## Cost

Nothing is added to a call path. No statement, loop or lock is added on any engine, so the per-verb-call, per-write, per-index-visit, per-batch and per-lock multipliers of AGENTS.md's reference deployment are all untouched. The three new constants are built once at import: a dict of six tuples and one tuple of 25 names. Their size follows the vocabulary, not the corpus, the batch or the engine. The face methods move and run the same code.

## Left as it is

- **`RULES` and `VALUE_RULES`** (`src/vfs/params.py:444`, `:538`). They are sparse tables keyed by the ops that carry a shape rule, looked up by op and never listed, so their order serves no reader. Spec 181 section 7.3 reordered them; this unit does not.
- **The plain members that are neither ops nor coroutines:** `mounts`, `open_session`, `capabilities`, `wrap`, `closed`, `authority`. That `test_router_public_verbs_are_exactly_the_registered_ops` counts coroutines only (`tests/test_ops.py:273`) is a gap in the list of the whole surface, which is K9 criterion 4's frozen list. It is not a gap in the order.
- **The storage protocols and their capability table** (`src/vfs/storage/protocol.py:131-609`). Regrouping them is unit 179-2.
- **`MANAGEMENT_METHODS` and `FRONT_METHODS`:** same names, same members. `tests/test_sync.py::test_the_management_allowlist_is_owned_by_ops` (`:685`) keeps passing.
- **`capabilities()`, `Result.ops`, the projection tables and the shell's program table.** They are sets or lookups, not lists of the surface.

## Tests

Written first, in `tests/test_ops.py`, under a new banner `The groups and the surface order`. Before `ops.py` changes, the module fails to import `OP_GROUPS`. Once the tables are added and before anything is reordered, exactly seven cases fail: three tables and four faces. Every assertion is a set, a tuple or a count, and none uses a clock. No storage and no rights change, so no engine leg and no leak test applies. The suite passes otherwise untouched, because the change is moves, banners and three constants.

- `test_every_op_sits_in_exactly_one_group`: `len(SURFACE_ORDER) == len(set(SURFACE_ORDER)) == len(ALL_OPS) == 25` and `frozenset(SURFACE_ORDER) == ALL_OPS`. Mutant: an op in two groups, or in none.
- `test_the_groups_are_the_registered_table`: `OP_GROUPS` equals the literal table of decision 2, groups and members in order, and `tuple(OP_GROUPS) == get_args(OpGroup)`. This is the one test a later story edits to register a verb.
- `test_the_rights_group_is_the_grant_class`: `frozenset(OP_GROUPS["rights"]) == GRANT_OPS`.
- `test_a_group_is_not_a_dispatch_class`: `mkedge` is in `query` and in `MUTATING_OPS`, `restore` (with `destroy` or `sweep`) is in `history` and in `MUTATING_OPS`, `tree` is in `derived` and in `READ_OPS`, and `OP_GROUPS["execution"] == tuple(EXEC_OPS)`. It pins the docstring's two-axes paragraph.
- `test_the_vocabulary_tables_list_the_surface_order[op_literal|needs|params]`: `get_args(Op)`, `tuple(VERB_RUNGS)` and `tuple(PARAMS)` each equal `SURFACE_ORDER`.
- `test_each_face_lists_the_verbs_in_the_surface_order[AsyncVirtualFileSystem|VirtualFileSystem|AsyncSession|Session]`: `[name for name in face.__dict__ if name in ALL_OPS | FRONT_METHODS] == [*SURFACE_ORDER, "cli"]`. Mutant: `cli` before `run` on one face, or `tree` back beside `ls`.
- `test_the_shell_is_a_front_and_no_op` (`tests/test_ops.py:288`) gains one assertion: `"cli" not in SURFACE_ORDER`.
- The size lint, `tests/lint/test_code_shape.py::test_a_listed_module_never_grows_and_an_unlisted_one_stays_under_the_ceiling`, passes with `base.py`'s entry at its new exact count (decision 12).

The gate before the pull request is `scripts/ci.sh`. Because the `ops.py` module docstring changes and the methods of `AsyncVirtualFileSystem` move (the docs export lists a class's members in source order, `scripts/docs_export.py:658`), `scripts/docs.sh check` runs too.

## Scope

In: `src/vfs/ops.py` (the three constants, the order of `Op` and `VERB_RUNGS`, the docstring paragraph); `src/vfs/params.py` (the order of `PARAMS`); the method order and the banners of `src/vfs/base.py`, `src/vfs/sync.py`, `src/vfs/session.py` and `src/vfs/sync_session.py`; `tests/test_ops.py`; the `base.py` entry in `tests/lint/allowlist.py`.

Out:
- The retirement of `run`: unit 167-1, if D63 is ruled against the lean.
- `entry_id` and `owner_id` on rows: unit [181-2](../2026-11-25-every-row-reports-the-entrys-permanent-id-and-its-owner/spec.md).
- `Result.pipe` and `glob` and `grep` without `observations=`: unit 181-3.
- The derived-verb oracles: unit [181-4](../2026-11-25-the-derived-verbs-are-pinned-to-their-definitions-by-oracles/spec.md).
- The trust tiers and the kernel paragraph of spec 181 section 7.1, and the docstring sentences of section 7.2 on `move` and `stat`: they describe `entry_id`, which is 181-2's.
- The frozen list and `documentation/` pages (K9 criterion 4); the conformance battery by kernel operation (K9 criterion 5, unit 179-1); the storage protocols (179-2).
- The rename of `sweep` to `destroy`: the deletes spec.
- Namespaces: ruled against by D5.

## What the docs must say

- The module docstring of `src/vfs/ops.py` gains the two-axes paragraph of decision 5. No spec number appears in it.
- The `cli` paragraph of that docstring (`ops.py:15-19`) adds that `cli` is in no group.
- No page under `documentation/` changes by hand. The generated reference pages follow the new source order of each face.

## Not checked

- `scripts/docs.sh check` and the generated API export were not run. That the reordered methods render with no new fault on the reference pages is inferred from `docs_export.py:658`, not seen.
- `ty` was run on a scratch copy of the table, not on the changed `ops.py`, `params.py` and faces.
- Which lands first, this unit or the deletes spec, is not known; decision 9 covers both orders.
- D63 is not ruled. The signature of `run` on `dev` takes `arguments` and no `stdin` (`base.py:1679-1685`), unlike the interrupt draft's decision 7. Neither shape is relied on here.
- The exact line count `base.py` ends at is estimated (four lines added), not counted.
- Whether `tests/base/test_authority.py::test_a_session_cannot_reach_a_mount` or any other test depends on method order was not run. A read of the face tests in `tests/test_sync.py` and `tests/base/test_authority.py` finds only sets and sorted lists.

## Choices to confirm

1. **Where `run` sits.** The options: a sixth group, `execution` (taken); `run` under `derived`; or no placement, waiting for D63 to retire `run`. The side taken is the sixth group, because `run` matches no definition of the five and is already its own dispatch class and its own README family. All three are cheap to reverse, since groups freeze nothing (rulings decision 4): if D63 is ruled to retire `run`, unit 167-1 deletes the `execution` row and the name with the verb, a two-line change to the table and one to the literal test; if `derived` is ruled, the row moves. The build does not wait.
2. **What the README calls the families.** The options: the README keeps Read, Find, Mutate and Execute (taken); or it adopts the six group names with a test that parses its table against `OP_GROUPS`, as spec 181 section 8.1 had it. The side taken changes nothing, so it is the cheaper to reverse: adopting the groups later is one table and one test, and adopting them now relabels a landed ruling's `Find` row for a list that freezes nothing.

## One line

`vfs.ops` declares six groups of ops once, and the op literal, the needs table, the parameter table and all four faces list the 25 verbs in that order with `cli` after them, held by drift tests in `tests/test_ops.py`.
