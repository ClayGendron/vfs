# The eight open kernel rulings, checked against the tree and the specs as they stand

This is the one study for roadmap story K1 in [the roadmap](../../../standards/roadmap.md), written on 2026-11-15 to [the brief](00-brief.md). The brief asks one thing for each of eight items: what is true today, and what each choice costs. The eight items are the ones a retired decision record, ADR 087 of 2026-10-24, left for the developer to rule on; the record is saved as [the retired record](experiments/adr-087-as-retired.md). Everything was read against commit `08c372affd1730739c27aec84b8e94e0d6ef1e87` (`git rev-parse HEAD`). `git status --short` showed `src/` and `tests/` clean; `AGENTS.md` and two documents under `context/` carried uncommitted edits, and the reference-deployment figures used below are from that working copy of `AGENTS.md`. What was done: the code under `src/vfs` was read and introspected with `uv run --no-sync python -c`; the twelve numbered specs that stand on the record were searched for every item and read where they touch one; the two research memos and the study lines they rest on were read; every count was taken with `git grep`. Nothing was run against a database, not a test, not an engine and not an in-memory store, so every statement about behaviour is read from code and was not observed.

EXECUTED means a command ran here and the claim reports its output. READ means read in a file cited by path and line, or by commit. INFERRED means this study's reasoning from the two.

The documents cited below, once each: the kernel memo is [the 2026-10-23 memo](../../2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md) and the OSTEP memo is [the 2026-10-24 memo](../../2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md). Their studies are [kernel study 01](../2026-10-23-filesystem-shaped-api/01-minimal-kernels-pyfilesystem-fsspec-opendal.md), [kernel study 02](../2026-10-23-filesystem-shaped-api/02-protocol-shapes-9p-fuse-wasi-sqlite-vfs-pjdfstest.md), [kernel study 04](../2026-10-23-filesystem-shaped-api/04-ai-tool-shaped-peers-deepagents-mirage-afs-langchain-mongodb-mcpfs.md), [kernel study 05](../2026-10-23-filesystem-shaped-api/05-vfs-surface-audit.md), [OSTEP study 02](../2026-10-24-ostep-principles-for-vfs/02-files-and-directories-the-api.md), [OSTEP study 04](../2026-10-24-ostep-principles-for-vfs/04-locality-and-log-structure-ffs-lfs-ssd.md) and [OSTEP study 06](../2026-10-24-ostep-principles-for-vfs/06-distribution-nfs-afs.md). The specs are [spec 167](../../../specifications/active/167-the-shell-pipeline-core/spec.md), [spec 169](../../../specifications/active/169-programs-the-index-and-the-vfs-views/spec.md), [spec 171](../../../specifications/active/171-the-mcp-adapter-and-the-cli-tool/spec.md), [spec 172](../../../specifications/active/172-the-wasi-python-runtime/spec.md), [spec 174](../../../specifications/active/174-write-preconditions-and-the-guarded-append/spec.md), [spec 175](../../../specifications/active/175-integrity-verify-on-read-and-scrub/spec.md), [spec 176](../../../specifications/active/176-the-listing-cursor/spec.md), [spec 177](../../../specifications/active/177-replay-the-contract-and-the-request-key/spec.md), [spec 178](../../../specifications/active/178-the-ranged-read/spec.md), [spec 179](../../../specifications/active/179-the-storage-seam-as-the-kernel/spec.md), [spec 180](../../../specifications/active/180-history-pack-on-reindex-and-the-bounded-sweep/spec.md) and [spec 181](../../../specifications/active/181-the-public-surface-regrouped-by-kernel-group/spec.md). The standards are [the constitution](../../../standards/constitution.md), [the release standard](../../../standards/release.md), [how we code](../../../standards/how-we-code.md) and [the process page](../../../README.md). Three landed specs matter: [the verb-rename spec](../../../specifications/archive/2026-11-09-the-verbs-take-the-names-agents-know.md), [the two-faces spec](../../../specifications/archive/2026-11-06-the-two-faces-named.md) and [the body-measurement spec](../../../specifications/archive/2026-11-07-storage-measures-every-body-it-stores.md).

One fact frames all eight items. READ: the release standard says an alpha may change anything and a beta allows "no rename, removal or change of meaning" (lines 13 to 14), and that beta begins when the public surface is frozen (line 18). READ: `pyproject.toml` line 15 still says version `0.0.22`, so no alpha has shipped. INFERRED: every rename below costs nothing in compatibility today and cannot be made once the beta begins. The cost of each choice is therefore a count of edits, not a count of users.

## 1. Pin 3: `delete` and `move`, or `remove` and `rename`

**Today.** READ: the verbs are `delete` and `move` at every layer. The op literal names them (`src/vfs/ops.py:40`, `:47`). They are defined on the kernel (`src/vfs/base.py:1061`, `:1235`), the session (`src/vfs/session.py:179`, `:243`), both synchronous classes (`src/vfs/sync.py:361`, `:432`, `:850`, `:901`), the storage protocol (`src/vfs/storage/protocol.py:190`, `:223`) and the database backend (`src/vfs/storage/backends/database/backend.py:746`, `:907`). EXECUTED: `inspect.signature` over the four public classes prints `delete(self, path=None, observations=None, *, cascade=True, authority=None)` and `move(self, src=None, dest=None, moves=None, *, authority=None)`, identical on each class. READ: three hints an agent reads already use the words: "remove the existing entry first" (`src/vfs/results/kinds.py:168`), "Empty the directory before removing it" (`:180`) and "Move within one mount, or copy then delete across mounts" (`:246`). READ: the same class already has `remove_mount` (`base.py:558`) and `remove_member` (`base.py:1710`). INFERRED: a verb named `remove` would be the third public method starting with that word, and the only one of the three that tombstones a file.

**The specs.** READ: no active spec renames either verb, and no two specs disagree here. Spec 179 follows the lean and says that if the developer picks `remove` and `rename`, the seam methods rename with the public verbs in the same commit (line 111). Spec 181 puts any rename out of its scope (line 503) and says the choice is independent of flat names (line 480). Spec 167 spells the shell programs `rm` and `mv` whatever the Python names are (lines 102 to 103). Spec 169 maps the WASI `path_rename` onto `move` (line 189).

**The research.** READ: the kernel memo's table writes the operations as `remove(path)` and `rename(src, dst)` with the tree's names beside them (§4.2, lines 67 to 68). Its question Q2 asks only about `delete` becoming `remove` (line 126); the record widened it to `move` and `rename`. The studies show the field does not agree on a word for removal.

| System | Removal | Move | Where |
|---|---|---|---|
| pyfilesystem2 | `remove`, `removedir` | `move`, derived from copy and remove | kernel study 01, lines 23, 41, 141 |
| fsspec | `rm_file`, `rm`; `delete` as an alias | `mv`, derived; `rename` as an alias | kernel study 01, line 67 |
| opendal | `delete` | `rename` | kernel study 01, lines 95, 99 |
| 9P | `Tremove` | a stat write with a new name | kernel study 02, lines 24, 122 |
| FUSE | `unlink` | `rename` | kernel study 02, lines 42, 45 |
| WASI 0.3 | `unlink-file-at` | `rename-at` | kernel study 02, lines 122, 128 |
| the wasi-python mount provider | `remove`, `rmdir` | `rename` | kernel study 02, line 63 |
| deepagents, the model's tools | `delete` | none | kernel study 04, line 35 |
| mirage's kernel | `unlink` | `rename` | kernel study 04, line 39 |
| afs | `delete` | `rename` | kernel study 04, line 43 |

READ, counting that table: removal is `delete` in three systems, `remove` in three, `unlink` in three and `rm` in one. A move is `rename` in six, a stat write in one, and `move` or `mv` in two. The memos leave one gap: neither asked what agent harnesses, the callers of these verbs, call the two operations. That is the test the verb-rename spec applied to `search` and `traverse`, and it was not applied to `delete` or `move`.

**Since 2026-10-24.** READ: three things bear on this item. First, the verb-rename spec landed on 2026-11-12 (commit `280a983c`). It set how a verb is named: the name agents already know, one name at every layer, and a short form only as a shell alias that never becomes an op (its decisions 1, 2 and 7). Second, the two faces landed on 2026-11-06 (commit `f9632d9c`), so each verb is now defined six times in `src/`, two more than when the record was written. Third, the constitution's Article 3 says the project should follow a Plan 9 or Unix convention where one exists, and that a deviation "MUST be well documented as a numbered Decision in the spec that makes them, naming the principle, the deviation, the motivating constraint, and the expected expiry" (lines 96 and 104). INFERRED: Unix has two conventions here, `rm` and `mv` at the shell and `unlink` and `rename` at the system call, and the tree follows neither at the Python surface. Whichever way the ruling goes, the spec that carries it owes that four-part Decision.

**What each choice costs.** EXECUTED, by `git grep` at the commit above. The literal count is `git grep -o -E` over the quoted word in `src` and in `tests` with `':!tests/fixtures'`. The call-site count is `git grep -o -h -E "[A-Za-z_][A-Za-z0-9_]*\.delete\("` and the same for `move`, with receivers that are SQLAlchemy tables left out. The test-name count is the word between underscores in `def test_` names.

| What a rename touches | `delete` to `remove` | `move` to `rename` |
|---|---|---|
| Method definitions in `src/` | 6 | 6 |
| Quoted op-name literals in `src/` | 20 in 8 files | 27 in 8 files |
| Quoted op-name literals in `tests/`, fixtures left out | 112 in 20 files | 94 in 20 files |
| Call sites in `tests/` | 275 in 38 files, 215 of them on a receiver named `storage` | 113 in 25 files, 84 of them on `storage` |
| Call sites in `src/` | 3 | 2 |
| Test function names holding the word | 50 | 49 |
| Mentions in `docs/`, `documentation/` and `README.md`, backticked or called | 2, 2 and 2 | 2, 1 and 2 |
| Backticked mentions in active specs and standards | 63 in 16 files | 90 in 19 files |

INFERRED: keeping the names costs no edit and one numbered Decision. Renaming costs about 470 edits in `src/` and `tests/` for `delete` and about 290 for `move`, by the rows above, changes the strings in every `Result.ops` and every capability set, and puts `remove` beside `remove_mount` and `remove_member`.

**Lean.** INFERRED: keep `delete` and `move`, because the field splits three ways on the removal word, the tree already uses `remove` for two other things on the same class, and `move` here crosses directories and takes batches, which `rename` does not say; the POSIX fronts keep their own words as the record already has it.

## 2. Pin 12: the resumption key as a field of `Result`, or a separate return

**Today.** READ: `Result` declares three fields, `ops`, `observations` and `errors` (`src/vfs/results/envelope.py:357` to `:359`), and allows extras (`:355`). READ: every merge builds a new `Result` from those three alone (`:520`, `:532`, `:587`), so an extra does not survive a merge. EXECUTED: the signatures of `ls`, `tree` and `glob` on all four classes carry no `after` and no `limit`. READ: a cut listing today is reported only as a `vfs.budget_exhausted.truncated` entry (`src/vfs/results/kinds.py:88`), produced among other places at `grep.py:401`, `search.py:973`, `traverse.py:497`, `reads.py:890` and `src/vfs/offload.py:98`. No key exists anywhere in `src/` or `tests/` (EXECUTED: `git grep -n -E "next_after|resumption" -- src tests ':!tests/fixtures'` finds only an unrelated chunk cursor in `indexing.py`).

**The specs.** READ: spec 176 declares the field as `next_after: Path | None = None` on `Result`, declared and not an extra "because an extra would be dropped by `merge` and rebased by nobody" (lines 84 to 92), and gives one rule per operation: kept by `filter`, `sort` and `top`, cleared by every merge, rebased by `with_mount` like a row path (lines 105 to 112). Spec 181 says `Result.pipe` forwards rows and never the key (line 572). Spec 171 says the MCP adapter sets the envelope's `next_after` when its text cap cuts rows (line 275). All four specs lean to a field.

**Where two specs disagree.** READ: spec 176 types the field as a path, gated like a path and rebased like a path. Spec 180 says the sweep key "rides" that field but is "an opaque, URL-safe string" naming the mount, the phase and the last `entry_id` (lines 287 to 289), and its `versions` key carries an `entry_id` and a version label (line 354). Spec 175 says the scrub key is a short JSON string that "rides the resumption-key field that spec 176 adds" (lines 349 to 351). INFERRED: a field typed `Path` and rebased by `with_mount` cannot carry those three keys. The ruling "a field" therefore needs one more word: the field's type.

**The research.** READ: the kernel memo recommends that "the cursor becomes a field" of the envelope (§4.1 rule 4, line 55), puts the key on the envelope in its table (§4.2, line 62) and asks the question as Q3, noting that the MCP wire needs it as a field (line 127). It rests on Oak's `hasMore` and on keyset listings in SeaweedFS and JuiceFS. The memos leave one gap: no studied peer returns a pair of result and key, so the cost of the separate return was never observed in prior art.

**Since 2026-10-24.** READ: the constitution's Article 2 says "Every public operation MUST return" the one result type (line 84) and that every listing "MUST return a deterministic cap with a refine or cursor mechanism" (line 88). How we code says "Every op returns a `Result`" (line 23). EXECUTED: there are now four public classes, so a changed return type is a change to `ls`, `tree` and `glob` on each of them, twelve signatures, plus the protocol and the backend.

**What each choice costs.** EXECUTED: `git grep -o -E "[A-Za-z_][A-Za-z0-9_]*\.(ls|tree|glob)\("` over `src tests docs documentation docs-app README.md examples` with fixtures left out finds 424 call sites: 409 in `tests/`, 7 in `src/`, 5 in `documentation/`, 2 in `docs/` and 1 in `README.md`; 236 are on a receiver named `storage` and about 180 are on a router or a session. EXECUTED: `git grep -o -E "\-> Result:" -- src` finds 280 annotations. The table below is INFERRED from those counts and from the spec lines it cites.

| | A field of `Result` | A separate return |
|---|---|---|
| What changes in `src/` | one declared field, and its rule in each of the envelope's operations as spec 176's table lists them | the return type of `ls`, `tree` and `glob` on four classes, the protocol and the backend; later `versions`, `sweep` and `scrub` too |
| Call sites that must change | none: a caller that ignores the field reads rows as today | all 424, or every one that unpacks |
| Set algebra | merges clear the key, by rule | a pair is not a `Result`, so the union and intersection operators do not apply to what the verb returned |
| The wire | `to_payload` emits one more key (spec 176, lines 96 to 102) | the adapter must put the key back into the payload anyway (spec 171, line 275) |
| The constitution | holds | Article 2's "one envelope" needs an exception written down |

**Lean.** INFERRED: a field, because the constitution and the coding standard both say every op returns the one result type and a pair would rewrite 424 call sites to carry a value most callers ignore; the same ruling should fix the field's type as a path, as spec 176 has it, and say that a key which is not a path does not ride it.

## 3. Pin 16: flat names, or kernel groups as namespaces

**Today.** EXECUTED: `inspect.getmembers` over `AsyncVirtualFileSystem`, `VirtualFileSystem`, `AsyncSession` and `Session` finds the same 25 verbs as flat methods on each. READ: a drift test holds the kernel's public coroutines to exactly the op vocabulary plus the management methods (`tests/test_ops.py:274`), and a parity test holds the synchronous class to the same list by name (`tests/test_sync.py:231`). EXECUTED: `git grep -n -E "OP_GROUPS|OpGroup|SURFACE_ORDER" -- src tests` finds nothing, so the groups are declared nowhere in code. READ: the README groups the verbs as Read, Find, Mutate and Execute (`README.md:68` to `:73`), which are not the record's four groups.

**The specs.** READ: spec 181 §9 keeps names flat as a lean and prices the alternative at commit `ba77449`: 1,286 matches of a grouped verb's call, 857 on a receiver named `storage`, 48 in a frozen fixture corpus, and so about 381 call sites to rewrite, plus four namespace objects on the router and four on the session (lines 469 to 480). No spec leans the other way.

**The research.** READ: the kernel memo asks the question as Q1 and calls it "ergonomics", because the kernel is the same either way (line 125). Its order of work says to "keep the flat method names where a group has one verb" (§7 step 7, line 120). READ: the three Python file abstractions in kernel study 01 are each one flat class of methods. The memos leave one gap: no study looked at a library that groups methods under attribute namespaces, so the ergonomic gain is asserted and not measured.

**Since 2026-10-24.** READ: the two faces landed, so there are four public classes and not two. READ: the verb-rename spec's decision 8 labelled the four find verbs "Find" in the README, a group name the record never used. READ: `src/vfs/chain.py` now exists and holds `glob_rows_in_hand`, `grep_rows_in_hand` and `judge_in_hand` (lines 62, 103, 186), which is not the `vfs.chain.glob` and `vfs.chain.grep` pair spec 181 §4 planned under that name. READ: the docs site now draws its reference pages from the docstrings of the exported classes (`scripts/docs_export.py:109` to `:117` reads `__all__`), one page per class.

**What each choice costs.** EXECUTED: the same search spec 181 ran, with today's verb names, `git grep -o -h -E "[A-Za-z_][A-Za-z0-9_]*\.(glob|grep|search|traverse|mkedge|rmedge|restore|sweep|grant|revoke|grants|posture|add_member|remove_member|tree|edit)\("` over `src tests docs documentation docs-app README.md examples`. It finds 1,744 matches. 65 are in `tests/fixtures`. Of the 1,679 that remain, 1,590 are in `tests/`, 36 in `src/`, 25 in `docs/`, 13 in `documentation/`, 8 in `examples/` and 7 in `README.md`. By receiver, 1,143 are on a storage object, about 50 are regular-expression objects whose `.search(` now shares a name with the verb, and about 470 are on a router or a session (`fs` 310, `root` 82, `s` 22, `_fs` 16, and smaller names). The table below is INFERRED from those counts and from the lines already cited.

| | Flat | Namespaces |
|---|---|---|
| Call sites to rewrite | none | about 470, up from the 381 spec 181 counted |
| New objects | none | four groups on each of four classes, sixteen |
| Tests that walk the surface | unchanged | `tests/test_ops.py:274` and `tests/test_sync.py:231` walk attribute paths |
| The docs export | unchanged | must learn nested members |
| The wire and the shell | op names | op names either way (spec 181, line 477) |
| What it buys | one spelling for every verb | grouping in an editor's completion list |

INFERRED: flat is not free of work. The record says the groups are "documentation and the conformance suite's organisation", and today the one published grouping, the README's, uses different group names. The ruling should name the groups once, so the README, the reference pages and `ops.py` can agree.

**Lean.** INFERRED: flat, because namespaces would rewrite about 470 call sites and add sixteen objects for a gain that reaches no agent, since tool names and shell words are op names either way.

## 4. Pin 17: whose identity survives `move(replace=True)`

**Today.** READ: no transfer replaces an occupant. The pair ladder refuses an occupied destination with `exists` before anything else is judged (`src/vfs/storage/backends/database/topology.py:186` to `:191`), and its docstring says "no transfer replaces an occupant, a tombstoned one included" (`:138` to `:143`). A tombstoned occupant refuses `exists` with the trashed hint (`:276` to `:281`). EXECUTED: `move` and `copy` take no `replace` and no `overwrite` on any of the four classes. READ: the schema holds one row per `path` (`src/vfs/models/rows.py:432`, `unique=True`) and one per `(parent_id, name)` (`:486`), and a tombstone keeps its path, parent and name (`src/vfs/storage/backends/database/trash.py:26` to `:27`). Version rows are keyed by `(entry_id, version_number)` (`rows.py:545` to `:546`). Edges are keyed by the two rows' ids (`rows.py:623` to `:624`). READ: when a write lands on an occupant, the columns it overwrites are listed in `_CLOBBER_COLUMNS` (`src/vfs/storage/backends/database/writes.py:115` to `:136`); `owner_id` is not among them, so the occupant keeps its owner. READ: the transfer module's own docstring already words the rule for `copy`: "an overwritten occupant keeps its identity as a material update" (`topology.py:20` to `:21`), though no code arm does it yet.

**The specs.** READ: spec 167 adds the flag to `copy` and `move`, default false, and says the replaced body is kept as a version (line 115); its rebase note takes pin 17 as the answer: the destination keeps its `entry_id` and history, the source is tombstoned, edges follow the source into the trash (line 240). Spec 181 says the same in four bullets and gives the reason: the write-a-temp-file-then-rename idiom then keeps the real file's identity, history and edges (lines 543 to 549). The roadmap's story F4 pins it as an acceptance criterion (line 624).

**Where two specs disagree.** READ: three places. First, spec 177 says a replayed `move` is recognised because "a replay finds the same `entry_id` at the destination that the first call moved there" (lines 143 to 151) and that "`move(replace=True)` replays like `move`" (line 505). INFERRED: under pin 17 that is not so. After a replace the destination holds its own id, not the source's, so the proof by id fails for exactly this form; the caller would see the source's trashed hint instead. Second, spec 181 refuses a directory over a directory with `exists` "until one is decided" (line 549), while spec 169 says a directory destination answers `EISDIR` or `ENOTEMPTY` "as POSIX says" (line 189). Third, the flag's name, which is counted under item 7.

**The research.** READ: the OSTEP memo names the question and does not answer it: POSIX keeps the source inode, spec 167 keeps the target's history, and "the write-temp-then-rename idiom fails today" (§2.10, line 112). OSTEP study 02 says to "pick one on purpose, and say what happens to edges that pointed at the losing `entry_id`" (line 79). Kernel study 02 records the two POSIX tests that bear on it: `rename/00.t` expects the inode to follow the source, and `rename/23.t` expects a rename onto an existing file to succeed (lines 89 to 90). The memos leave no gap on the facts; they leave the choice.

**Since 2026-10-24.** EXECUTED: `git log -S` for the `(parent_id, name)` constraint finds its last change on 2026-07-14, and the tombstone module's design landed by 2026-10-12, so the schema facts above are older than the record and unchanged since. READ: a spec that judges a mutation's rights on the rows it acts on at commit landed on 2026-11-14 (commit `c39238ab`), so a replacing move will be judged on both rows it touches. READ: the schema format is now 26 (`rows.py:139`), not the 23 the record's landing note assumed.

**What each choice costs.** INFERRED from the lines read above, except where a row says READ.

| | The destination's identity survives | The source's identity survives |
|---|---|---|
| The replaced row | updated in place, as a write updates an occupant | must leave its path, because one path holds one row, tombstones included (READ, `rows.py:432`, `:486`) |
| Schema | no change | one or both unique constraints change, or the replaced row is destroyed and not tombstoned |
| The replaced body | minted as a version of the destination, by the mint the write path already runs | has no row of its own to hang from: its version rows key on an id with no live row |
| Undo | `restore` of the source brings the source back; the replaced body is one version back | nothing restores the replaced file without the schema change |
| Edges on the replaced file | stay | dangle, or are destroyed with the row |
| Edges on the moved file | go to the trash with the source | stay |
| Owner | the destination's owner keeps the file | the source's owner |
| A replayed call | not recognisable by id; spec 177 §1.3 needs a second rule for this form | recognisable by id |
| A POSIX front | reports the destination's number after a rename-over, where `rename/00.t` expects the source's | matches |
| The constitution | a deviation from Unix that Article 3 wants written as a numbered Decision | none |

INFERRED: the ruling leaves three smaller choices that the spec carrying it must also make, because the code will need them. One is a tombstoned occupant at the destination: today it refuses; under the lean the natural rule is the one `write` has, a revive (`src/vfs/storage/backends/database/staging.py:287` to `:289`). Two is a directory over a directory. Three is the rung judged on each row: spec 167 says the occupant is judged as `write` judges one (line 115) and the source at `move`'s own rung.

**Lean.** INFERRED: the destination's, because the schema holds one row per path including tombstones, so keeping the source's identity would need a schema change or would destroy the replaced file with no undo, and the destination rule is the write path's existing behaviour applied to a transfer.

## 5. Pin 9: the offload threshold and the integrity kind

**Today, the threshold.** READ: it is built. `MEASURE_OFFLOAD_BYTES: Final = 100_000` stands at `src/vfs/models/version.py:60`, with the comment that below it the hop costs more than the hash and above it the hash would hold the loop. A single-path write measures a body at or over it on the pool (`src/vfs/base.py:333` to `:339`). A batch write measures inline when the call's bodies total less than it, and otherwise measures every body of the call in one hop (`src/vfs/storage/backends/database/writes.py:165` to `:169`). READ: it landed twice: `ba774495` on 2026-10-24 put it in `base.py`, and `b25bcd62` on 2026-11-07 moved it to the models layer and extended it to storage, as decision 3 of the body-measurement spec. EXECUTED: `git grep -o "MEASURE_OFFLOAD_BYTES"` finds 8 mentions in `src/` and 6 in `tests/`, in `tests/base/test_dispatch.py` and `tests/test_offload.py`. READ: the pool is as wide as the machine, `os.cpu_count()` (`src/vfs/offload.py:84`). READ: nothing hashes on the read path yet; `reads.py` and the backend's read methods call no measure function.

**Today, the kind.** EXECUTED: `len(ErrorKind)` is 24 and `len(KIND_CONTRACTS)` is 24. READ: the `unavailable` family has a parent and two children: `vfs.unavailable` with retry class `transient`, `vfs.unavailable.backend` with `transient`, and `vfs.unavailable.schema` with `never` (`src/vfs/results/kinds.py:92` to `:94`, `:267` to `:284`). READ: an unknown child degrades to its nearest known parent (`kinds.py:311` to `:326`), and a kind with no known prefix raises as the base exception (`src/vfs/exceptions.py:97` to `:100`). READ: plain `vfs.unavailable` is already produced with `retryable=False` for states a retry cannot heal (`src/vfs/storage/backends/database/indexing.py:493` to `:502`). EXECUTED: `git grep -n -i "integrity" -- src/vfs` finds only the driver's constraint-violation classifier, so no integrity kind exists.

**The specs.** READ: spec 175 asks whether to keep 100,000 bytes or measure again on an x86 runner of the class CI uses, and leans to keep it because "it is a cost knob, not a correctness rule" (line 83). It defines the kind as the child `vfs.unavailable.integrity` with retry class `never`, citing `vfs.unavailable.schema` as the precedent (lines 114 to 137), and lists the alternatives as a top-level `vfs.integrity` or plain `vfs.unavailable` with a data record (line 152). The roadmap's K3 criterion 1 already writes the child kind (line 151).

**Where the specs and the tree disagree.** READ: spec 175 §1.2 says to move the constant to the models layer; that is done. Spec 175 §1.3 says a large call is cut into blob pages and each page measured in its own hop, "Hops = number of pages" (lines 106 to 107), and the roadmap's K3 criterion 4 pins that count (line 154). The landed write path makes one hop for the whole call (`writes.py:169`), by decision 3 of the body-measurement spec, whose scale note says "the hop count is at most one per call, not per entry" (line 75). INFERRED: spec 175's hop arithmetic and K3's fourth criterion describe a rule the tree did not build. Spec 175 also names `storage/backends/database/offload.py`, a module that no longer exists; the pool lives in `src/vfs/offload.py`.

**The research.** READ: the OSTEP memo measured the threshold on one arm64 laptop with an eight-thread pool and 32 concurrent callers: one hand-off costs 32 microseconds, inline wins at 10,000 bytes and offloading wins at 100,000 (§6 Q1, lines 218 to 229). It gives the rule: "hash inline under a size threshold near 100 KB, offload above it, and pin the threshold by counting offload calls, never by time". On the kind the memo says only that a mismatch or a missing body classifies "as an error, not success" (§2.3, line 60). The memos leave two gaps: the crossover was never measured on another machine, and no study compared the three kind shapes.

**Since 2026-10-24.** READ: beyond the two landings above, all offloaded work has shared one process pool as wide as the machine's core count since 2026-11-12 (commit `4a6d3e08`; `src/vfs/offload.py:84`), and the router's write measurement uses that pool (`base.py:335` to `:338`), where spec 175 §1.2 describes a hop on the loop's default executor. INFERRED: the laptop's measurement used eight workers; a two-core container has two, so the parallel gain the memo measured is smaller there, while the loop-stall argument is unchanged. INFERRED from the reference deployment in `AGENTS.md`: the median file is 4 KB, so a single read or write of a median file never hops, and a batch hops once its bodies pass 100,000 bytes, about 25 median files.

**What each choice costs.** INFERRED from the lines read above; the spec and roadmap lines in the last row of the second table are READ.

| The threshold | Keep 100,000 | Measure again first |
|---|---|---|
| Edits | none: built, and pinned by count in two test files | one bench run of `experiments/synthesis/offload_threshold.py` from the OSTEP studies folder on another machine; one constant if the value moves |
| Risk | the value is one laptop's | none added; the tests name the constant, so they follow it |

| The kind | Child `vfs.unavailable.integrity` | Top-level `vfs.integrity` | Plain `vfs.unavailable` with a data record |
|---|---|---|---|
| Enum members | 25 | 25 | 24 |
| What a consumer that does not know it sees | `vfs.unavailable` | no family; base handling | the kind it knows |
| Retry class | `never`, by its own contract row | `never` | the contract says `transient`; each producer passes `retryable=False` |
| Errno for a front | the family's, EIO | needs its own row | EIO |
| Spec lines to change | none | spec 175 §2, roadmap line 151 and decision D8 | spec 175 §2, roadmap line 151 |

READ: the constitution's Article 2 lists a closed error taxonomy of seven names with no integrity entry (line 84). INFERRED: the list is older than the 24 kinds the tree has, but a child under an existing family is the choice that adds no top-level name to it.

**Lean.** INFERRED: keep 100,000 bytes, because it is built, pinned by count, and a cost knob that a later bench can move without touching a contract; and take the child kind `vfs.unavailable.integrity`, because the tree already has a child of `unavailable` whose retry class is `never` and a caller that does not know the child still lands on the right family.

## 6. Pin 10: the replay row's time to live, and the withheld hint

**Today.** EXECUTED: no verb on any of the four classes takes a request key, and `git grep -n -E "request_key|IDEMPOTENT" -- src` finds nothing. EXECUTED: `git grep -n -i "idempotentHint" -- src` finds nothing, and `mcp` appears in `src/` only in comments, so no adapter exists to carry a hint. READ: an identical rewrite of a file still reports `updated`; the staging pass returns only `created` or `updated` for a file (`src/vfs/storage/backends/database/staging.py:326`). READ: a missed move source is classified with no destination facts (`topology.py:171` to `:173`). READ: the trash is kept 90 days by default (`backend.py:156`), and `sweep` is the only reclaimer because "storage owns no background work" (`base.py:1135` to `:1136`).

**The specs.** READ: spec 177 makes the time to live a constructor argument, `replay_hours: int = 24`, on both storage classes, and leans to 24 hours over 1 hour or 7 days (lines 338 to 340). It says outright that the day figure comes from "general knowledge, not studied here". Expired rows are deleted by `sweep`'s retention arm in two statements (lines 368 to 374). On the hint it gives the rule `op in IDEMPOTENT_OPS` and leans to withhold it from a tool whose verb has any form that applies twice (lines 420 to 426). Spec 171 as drafted sets no `idempotentHint` at all (line 88) and its rebase note takes spec 177's rule (line 276). The roadmap's decision D11 leans to withhold (line 1044).

**What the hint rule does to `write`.** READ: spec 177's shape rule says a verb is key-only "if any form it accepts can change state twice", and that `write` "is idempotent until 174's `append=True` becomes one of its forms, when it becomes key-only" (§0.1). INFERRED: under "withhold", the `write` tool loses the hint the day spec 174 lands. The agent tools that keep it are `mkedge`, `rmedge`, `grant` and `revoke` (line 424). Spec 177 names the way out: spec 171 could serve append as its own tool so `write` keeps the hint (line 426). That is a consequence of this ruling and pin 3's "append is a form of write" taken together.

**The research.** READ: the OSTEP memo's Q2 answer is that the stored result is "a row in the mount's schema with a short TTL", swept with the trash (line 230), and its §2.4 says to set `idempotentHint` "where earned" (line 68). OSTEP study 06 found that spec 171 "leaves `idempotentHint` unset on every tool, though five verbs earn it" (line 85) and that an append "needs a precondition or a request key from day one" (line 229). The memos leave two gaps: no time to live was measured or taken from a studied peer, and no study read how an MCP host acts on the hint.

**Since 2026-10-24.** READ: the roadmap now ties two more ledgers to this number. Decision D10 gives the ask ledger 24 hours (line 1043) and D43 gives the run ledger 24 hours on "the same sweep arm as the replay store" (line 1076). Story K5 says "the request key is also the resumption token" for a human's approval (line 166). INFERRED: the replay row must live at least as long as an ask can wait, or an approval that arrives late finds its key lapsed. A 1-hour value would contradict D10 and D43 as written.

**What each choice costs.** INFERRED from spec 177's own figure and the reference deployment. Spec 177 puts 2,400 stored answers of 10,000 rows each under 100 MB, about 42 KB an answer (line 340). The reference deployment runs 100 batches of 10,000 files a night and 50,000 to 100,000 single-file writes a day.

| Time to live | Batch answers held | Their bytes | Single-write head rows held if every write were keyed |
|---|---|---|---|
| 1 hour | about 17 | under 1 MB | about 6,000 to 12,500 |
| 24 hours | 100 | about 4 MB | 50,000 to 100,000 |
| 7 days | 700 | about 29 MB | 350,000 to 700,000 |

INFERRED: storage does not decide this at any of the three values. What decides it is how long a key stays bound to its first answer: long enough for a resume, short enough that a reused key is not answered from a stale row. The rows also outlive the time to live until a deployment runs `sweep`, so the value bounds serving, and the sweep schedule bounds space. The hint's two readings, in the table below, are INFERRED from spec 177's replay table.

| The hint | Withhold | Set it on MCP's effects-only reading |
|---|---|---|
| Tools that carry it after spec 174 | `mkedge`, `rmedge`, `grant`, `revoke`, and the read-only tools | those, plus every tool whose replay only refuses: `mkdir`, `delete`, `restore`, `copy`, `move` |
| What an auto-resending host does | never resends an append or an edit on its own | may resend a `move` that already landed and get a refusal for work that succeeded |
| Code to change today | none; no adapter exists | none |

**Lean.** INFERRED: 24 hours as the default of the per-storage setting, because the roadmap already gives the ask and run ledgers 24 hours on the same sweep arm and the key is their resumption token; and withhold the hint, because a host that resends an append on its own applies it twice, which is the silent loss the kernel plan set out to close.

## 7. Spec 174's fork: `overwrite=` leaves `write`

**Today.** EXECUTED: `write` takes `overwrite: bool = True` on all four classes. READ: it stands at `base.py:967`, `session.py:151`, `sync.py:330` and `:825`, the protocol (`protocol.py:176`), the backend (`backend.py:685`) and the parameter table (`src/vfs/params.py:169`). READ: `overwrite=False` refuses a live occupant with `exists` (`staging.py:307`) and does not refuse a tombstone: a tombstoned file is revived "whatever `overwrite` says" (`staging.py:287` to `:289`). READ: an exception docstring names the argument (`src/vfs/exceptions.py:54`).

**The specs.** READ: spec 174 removes it: "`if_absent=True` is today's `overwrite=False`, with one name for one fact", with no alias (line 71), and its criterion 25 says `overwrite` is absent from `write`, `Session.write`, the seam and the parameter table (line 417). Spec 171 follows and marks the removal as pending the developer (line 273). Spec 181's table says "`overwrite` leaves with 174" (line 41). The roadmap's K2 criterion 6 and decision D7 say yes (lines 146 and 1040).

**Where the specs disagree, and the count the brief asked for.** EXECUTED: `git grep -o "overwrite=" -- context/specifications/active` finds 43 occurrences in 12 files, on 35 lines.

| File | Occurrences | What they name |
|---|---|---|
| spec 181, `spec.md` | 10 | the flag on `move` and `copy` |
| spec 174, `spec.md` | 10 | the flag on `write` |
| spec 167, `spec.md` | 8 | the flag on `move` and `copy` |
| spec 169, `spec.md` | 3 | the flag on `move` |
| spec 177, `spec.md` | 2 | `write(overwrite=False)` in a recorded probe |
| spec 174, `tasks.md` | 2 | the flag on `write` |
| spec 162, `spec.md` | 2 | `write(overwrite=False)`, a built rule |
| spec 162, `tasks.md` | 2 | the same, in checked-off tasks |
| spec 171, `spec.md` | 1 | the flag on `write`, in the removal note |
| spec 167, `tasks.md` | 1 | the flag on `move` and `copy` |
| spec 162, `plan.md` | 1 | the flag on `write` |
| spec 160, `spec.md` | 1 | `write(overwrite=False)` inside cross-mount copy |

READ: so 22 occurrences name a flag on `move` and `copy` (specs 167, 169 and 181) and 21 name `write`'s flag. EXECUTED: `replace=` occurs 10 times in four files: 4 in spec 181, 3 in spec 177, 2 in spec 167 and 1 in spec 174. READ: the roadmap says "specs 167/169/171 say `overwrite=`, ADR 087 and spec 181 say `replace=`" (line 124). Two parts of that sentence do not match the files. Spec 171's one occurrence is about `write`, not about `move` or `copy`. And spec 181 does not say `replace=`: its lean is `overwrite=` on `move` and `copy`, "because `write` already has it and changing `write` would touch every ETL caller" (line 550). Spec 177 writes `replace=` (line 505). The roadmap itself says "The one flag name is `replace=`" (line 997).

INFERRED: this is a ninth ruling inside the eight. If `overwrite=` leaves `write`, spec 181's one reason for spelling the transfer flag `overwrite=` is gone, and the word would leave one verb only to arrive on two others. The two flags also have opposite defaults: `write` replaces unless told not to (`base.py:967`), and a transfer refuses unless told to replace (`topology.py:186` to `:191`). One word cannot serve both without inverting one default.

**The research.** READ: kernel study 05 lists `overwrite` among the tree's POSIX-named parameters and reads it as create-exclusive, `O_EXCL` (lines 21 and 47). The kernel memo proposes `if_absent=` for create-exclusive from opendal's precondition arguments (§4.2, line 65). The memos leave one gap: neither discusses removing `overwrite=`; the fork was raised by spec 174's author.

**Since 2026-10-24.** READ: the ETL spec made `write` take any iterable of entries, and the two faces added two more public signatures. READ: the docs site now teaches the argument: "To refuse a load that would replace existing files, pass `overwrite=False`" (`documentation/how-to/load-a-folder-of-files.md:229` and `:232`). READ: the constitution's Article 5 says every write path "MUST specify last-writer-wins, revision-guarded, or reject-on-conflict" (line 121). INFERRED: those three modes are the default, `if_version=` and `if_absent=True`, one argument each. READ: Article 1.5 names the precondition `if_revision=X` (line 75), not `if_version=`; the spec that carries this ruling should say which word stands.

**What each choice costs.** EXECUTED: `git grep -o -E "overwrite="` by folder finds 20 occurrences in `src/`, 66 in `tests/` outside fixtures, and 2 in `documentation/`. The 66 are in 15 files, 28 of them in `tests/storage/database/test_writes.py`; 43 pass `True`, 20 pass `False`, 2 forward a variable and 1 passes a wrong type on purpose. 13 more are in the frozen fixture corpus and do not change. The table below sets those counts against spec 174's text and is otherwise INFERRED.

| | `overwrite=` leaves `write` | `overwrite=` stays |
|---|---|---|
| Public signatures | six lose the argument: kernel, session, two synchronous classes, protocol, backend | none |
| `src/` | 9 of the 20 occurrences are in the public layers and go: 4 in `base.py`, 2 in `sync.py`, 1 each in `session.py`, `backend.py` and `exceptions.py`; the 11 in `writes.py` are internal and spec 174 keeps the word there | none |
| `tests/` | 66 occurrences in 15 files: the 43 `True` drop the argument, the 20 `False` become `if_absent=True` | none |
| Docs | two lines of one how-to page | none |
| The surface after spec 174 | `if_version`, `if_absent`, `append`, `parents` | the same four plus `overwrite`, where `overwrite=False` and `if_absent=True` say one thing and `overwrite=False, if_absent=False` says two |
| Spec lines | none in spec 174; the built record in spec 162 keeps its word | spec 174 line 71, criterion 25, tasks section 2; spec 171 line 273; roadmap lines 146 and 1040 |

**Lean.** INFERRED: yes, it leaves, because `if_absent=True` is the same rule down to the tombstone revive and two arguments for one fact would freeze a contradiction into the beta; and the same ruling should name the transfer flag `replace=`, since spec 181's reason for `overwrite=` there does not survive it.

## 8. Spec 180's fork: the hot window and the history verb's name

**Today.** READ: a write that replaces a body mints one whole snapshot row; creates and identical bodies mint nothing (`src/vfs/storage/backends/database/versions.py:1` to `:15`). No diff is ever written (`versions.py:188` sets `version_diff` to `None`). EXECUTED: `git grep -n -E "tables\.versions" -- src/vfs/storage` finds two inserts in `versions.py` and one delete in `trash.py:606`; nothing reads the table. READ: the diff law exists unused, with `SNAPSHOT_INTERVAL: int = 10` (`src/vfs/models/versioning.py:23`). EXECUTED: no class has a `versions` or a `history` method, and `git grep -n "PACK_" -- src` finds nothing. READ: the schema comment still promises "the batch pack verb" (`rows.py:535` to `:538`).

**The specs.** READ: spec 180 defines a row as cold when at least `PACK_HOT_ROWS` newer rows of the same file exist, sets the constant to 1, and measures both values (lines 49 to 76). Its numbers, executed by its author at `ba77449`: with three rewrites per file and small edits, the stored bytes fall to 0.791 of the original at 1 and 0.616 at 0 for 20-line bodies, and to 0.681 against 0.376 for 200-line bodies; with 25 rewrites the two values give 0.620 and 0.604. It names the verb `versions`, "a plural noun like `grants`", to leave `history` to the shell (line 349). Spec 167 agrees: "The history verb is `versions`", so the shell's `history` builtin keeps its meaning (line 244), and it lists `history` among its builtins (line 83). Spec 171 makes `versions` a tool (line 279). A second active spec touches the name: [spec 161](../../../specifications/active/161-every-mutation-mints-a-version-row/spec.md), an older seed, asks whether the read side is "a `versions` read verb, a `version=` parameter on `read`, or both" (line 22). No spec leans to `history`.

**Where the specs and the tree disagree.** READ: spec 180 puts pack as the last step of `DatabaseStorage._reindex_phases` at `backend.py` line 1187 (line 148). That method is gone. The full pass is `rebuild` and the incremental pass is `refresh`, both run from `src/vfs/storage/backends/database/maintenance.py` (`:141`, `:152`), with their phases at `:322` and `:558`. INFERRED: the spec that builds pack must say which pass packs. The reference deployment runs the full pass once a day and the incremental pass every 15 minutes.

**The research.** READ: the OSTEP memo's Q3 answer is the developer's: keep the full history, convert cold versions to deltas during the index pass, and keep the name `pack` (line 231). Its §2.6 measured 1,000 files rewritten three times leaving 3,000 version rows of 833,400 bytes beside 277,800 live bytes (line 80). OSTEP study 04 says the hot and cold split is the textbook's rule and that a file rewritten nightly makes almost all the version garbage (lines 72 to 77). The kernel memo names the read `history(path)` (§4.3, line 78). The memos leave two gaps: neither proposes a hot window of any size, and neither weighs `versions` against `history`.

**Since 2026-10-24.** READ: `reindex` was renamed `rebuild` and split from `refresh` on 2026-11-14 (commits `e90ec653`, `844ef423`). READ: the verb-rename spec judged `graph` a poor verb name because it "reads as 'return the graph'" (its problem section). INFERRED: by that same reading `versions` is a good name, because returning the versions is exactly what the verb does, as `grants` returns the grants. READ: the constitution already uses the word for this thing: prior content is "reached through the reserved `/.vfs/path/to/file/__meta__/versions/N` namespace" (Article 1.5, line 78).

**What each choice costs.** INFERRED from spec 180's table and the reference deployment, where the median file is 4 KB, the corpus holds about 40 GB of text, 10 percent of files are rewritten every night and 0.5 percent a working day by hand.

| The hot window | `PACK_HOT_ROWS = 1` | `PACK_HOT_ROWS = 0` |
|---|---|---|
| The newest version row | kept whole | a diff |
| Reading the most recent undo | one row | up to ten rows fetched and up to nine diffs applied, by `SNAPSHOT_INTERVAL` |
| Whole snapshots that stay | at most one per file ever rewritten, so at most about one more copy of the corpus text | one in every ten rows |
| Files rewritten nightly | almost no difference: 0.620 against 0.604 at 25 rewrites | the same |
| Files rewritten a few times | holds about a third of the history whole | roughly halves the bytes |
| Changing the value later | rows not yet judged are simply judged under the new value | the same |

INFERRED: this constant is not a public name and freezes nothing. It can be ruled now and moved after a measurement without a rename or a migration.

EXECUTED: the name's cost today is in documents only, since no code exists. `versions(` is written 13 times in four files under active specs and standards, and backticked `versions` 32 times in eight files; backticked `history` is written 14 times in six files, where it names the shell builtin, the session field, the group, or the alternative spec 180 sets aside. The table's rows are READ from those documents and from the code lines cited under "Today".

| The name | `versions` | `history` |
|---|---|---|
| Code to change | none | none |
| Spec and roadmap lines | none | spec 180 §7, spec 167 line 244, spec 171 line 279, roadmap story K8 and its registration rows |
| What else uses the word | the `Version` model, the `version` field on a row, spec 174's `if_versions=` argument, the constitution's namespace segment | the shell's `history` builtin and the session's `history` field (spec 167, lines 83, 164, 169) |

**Lean.** INFERRED: `PACK_HOT_ROWS = 1`, because it bounds the extra whole bodies at one per file and keeps the most likely history read at one row, and the value can move later at no cost to a public name; and `versions`, because every spec already writes it, the constitution already uses the word for the same thing, and `history` is taken by the shell.

## The seventeen pins against the tree

READ unless a row says EXECUTED. "Built" means the tree agrees with the pin. "Not built" means the pin asks for something the tree lacks. "Contradicts" means the tree says something else. Where a pin names a verb that was since renamed, the row says so, because the spec that carries the pins must carry today's names.

| Pin | What it says, in short | State today | Where |
|---|---|---|---|
| 1 | The kernel is the gate and four groups; all else is a facet | Built in part. The gate funnel exists. The groups are declared nowhere. The pin's names are stale: `glean` is `search`, `graph` is `traverse`, `members` is `add_member` and `remove_member`, `reindex` is `rebuild` and `refresh` and neither is an op. `run` is still a routed op. No front exists. | `base.py:2734`, `:2845`, `:2859`, `:2987`; `ops.py:53` to `:61`, `:85`; `backend.py:1117`, `:1121`; EXECUTED: `ls src/vfs/shell` fails |
| 2 | The query verbs are kernel operations; a backend with no index is still served `grep` by a scan | Built for the one backend, which has a scan tier. The kernel-side scan for a backend that declares no `grep` is not built; the capability gate answers `unsupported`. | `protocol.py:84`; `kinds.py:75`, `:80` |
| 3 | Four new arguments; the plurals and `authority` stay; `delete` and `move` keep their names | Not built: no `after`, `limit`, `range`, `if_version`, `if_absent`, `append` or `replace`. The plurals, `authority` and the two names are as the pin says. | EXECUTED: the 25 signatures; `base.py:904` to `:1259` |
| 4 | No handles, inode addressing, links, mode bits, access time, `fsync` or seek; `entry_id` is a read-only column | Built for the absences. `entry_id` as a column is not built. The constitution rejects "raw inode exposure" (line 100), so the carrying spec should say why a read-only id is not that. | EXECUTED: `Observation.model_fields` holds neither `entry_id` nor `owner_id`; `Entry` holds `owner_id` only (`src/vfs/models/entry.py:120`) |
| 5 | Two halves of the gate, three trust tiers, said in one place | Built as mechanism in process. Not written in one place: the kernel's module docstring does not say it, and an older page under `docs/` states only the in-process and network-edge line. No wire and no guest exist. | `base.py:1` to `:33`; `docs/explanation/open-in-process-loud-at-the-edge.md` |
| 6 | A front's handle carries a path and an offset, never a right | Not built and not contradicted: no front holds a handle. | EXECUTED: no `cli`, `bound` or `serve` in `src/` |
| 7 | The atomic unit, stated at the seam and declared as a trait; whole-batch and resumable verbs named | Built as behaviour and tested. Not stated in one sentence at the seam, and no trait declares it. `sweep` is still whole-batch. The pin's `reindex` is `rebuild` and `refresh`. | `tests/storage/database/test_writes.py:82`; `tests/support/storage_contract.py:740`, `:765`; `protocol.py:78` to `:91` |
| 8 | The fault model written once; the engine's code in `data["vfs.engine_error"]` | Not built. EXECUTED: `git grep -n "engine_error" -- src` and a search for "fault model" in `src`, `docs` and `documentation` find nothing. Identities are never reused, as the pin says. | `staging.py:287` to `:289` |
| 9 | Verify on every read; hash in the standard library; offload at 100 KB; a report-only `scrub`; written rows return their hash | Built for the write-path offload only. No read compares a hash, no `scrub` exists, and a written row carries no `content_hash`. | `version.py:60`; `writes.py:376` to `:383` |
| 10 | Every mutating verb safe twice, recognisable, or keyed; an identical write reports `unchanged` | Not built. An identical file write reports `updated`. No request key, no replay table. | `staging.py:326`; `topology.py:171` to `:173` |
| 11 | Full history kept; `pack` on the index pass; `sweep` takes a limit; a garbage gauge; `delete` is a tombstone | Built for "no version row is deleted by default" and for the tombstone. `pack`, the bounded `sweep` and the gauge are not built. | `trash.py:606`; `base.py:1119` to `:1124`; `versions.py:188` |
| 12 | Rows stay the one result type; the key is a field of `Result` | Built for the one result type. No key, and no ranged row. | `envelope.py:357` to `:359` |
| 13 | Locks in path order; jittered retries; a retry counter per verb | Built for the first two. The counter is not built. | `writes.py:407` to `:409`; `src/vfs/storage/backends/database/engine.py:353` to `:366` |
| 14 | An access-path table per verb, counting statements, rows and body bytes at three authorities | Not built as a family. EXECUTED: 23 test files count statements with a cursor hook; a search of `tests/` for a body-bytes pin finds none. | `git grep -l "before_cursor_execute" -- tests` |
| 15 | Every kernel decision scores its options on one table of eight axes | Not carried by any standard. EXECUTED: a search of `context/standards`, the skills and `AGENTS.md` for "agent latency", "ETL throughput" or "dialect reach" finds nothing. `AGENTS.md` now carries a later filter, the reference deployment and its six multipliers, which covers much of the same ground. | `AGENTS.md`, "The reference deployment" |
| 16 | Flat names; the groups are documentation | Built for flat names. The one published grouping uses other names. | `tests/test_ops.py:274`; `README.md:68` to `:73` |
| 17 | On `move(replace=True)` the destination's identity survives | Not built. Today every occupant refuses `exists`. | `topology.py:186` to `:191`, `:276` to `:281` |

INFERRED: no pin is contradicted by code. Three are contradicted by words: pin 1 by renamed verbs, pin 7 by the renamed index pass, and pin 16 by the README's group names. Only pin 9 has moved since the day the record was written: its write-path offload was extended from the router to storage on 2026-11-07. Pin 15 has been overtaken by a newer rule.

## Where the retired records are still cited

EXECUTED: `git grep -o -w "087" -- context/specifications/active context/standards`, counted by file, finds 151 occurrences in 14 files; 146 of them are the phrase "ADR 087".

| File | Occurrences of `087` |
|---|---|
| spec 181, `spec.md` | 33 |
| `context/standards/roadmap.md` | 23 |
| spec 179, `spec.md` | 18 |
| spec 178, `spec.md` | 14 |
| spec 175, `spec.md` | 13 |
| spec 176, `spec.md` | 12 |
| spec 174, `spec.md` | 12 |
| spec 180, `spec.md` | 8 |
| spec 177, `spec.md` | 7 |
| spec 171, `spec.md` | 3 |
| spec 167, `spec.md` | 3 |
| spec 181, `tasks.md` | 2 |
| spec 172, `spec.md` | 2 |
| spec 175, `tasks.md` | 1 |

EXECUTED: a parse of every "ADR" or "ADRs" followed by three-digit numbers, lists and ranges expanded, over the same two folders finds 495 citations of 48 distinct records in 35 files. 375 of them are in the twelve kernel spec folders and the standards. After `087` with 146, the records cited most are `074` with 38, `084` with 34, `082` with 32, `083` with 21, `080` with 20, `017` with 18 and `081` with 18. The roadmap alone holds 79. No other standards file cites the record; `mutant-ledger.md` cites one other record once.

READ: none of those records is in the tree. `context/decisions/` does not exist, and commit `3667fec2` of 2026-10-30 removed it together with `context/open-questions.md` and all of `context/architecture/`. The commit message says what was left: "the process docs and the spec_review skill still ask for an architecture page whose folder is gone, and the numbered active specs keep their ADR and open-questions mentions until each is converted on pickup."

READ: the roadmap's "Architecture page 02" was `context/architecture/02-the-kernel-and-the-facets.md`. EXECUTED: `git show '3667fec2^:context/architecture/02-the-kernel-and-the-facets.md'` prints it; its last section, "Open", held three lines: pin 3, pin 16 and pin 17. The page and its list exist nowhere in the tree today. EXECUTED: `git ls-files | grep -i architect` finds only an eight-line stub at `docs/explanation/architecture.md`, a picture, a security-audit note, a research memo about another system and fixture files. READ: the process page still speaks of "the architecture page" twice (lines 74 and 93), and the `spec_review` skill names architecture pages three times.

INFERRED: story K1's three acceptance criteria cannot be met as the roadmap words them (lines 134 to 136). The first asks for a status line on a record that is gone. The third asks for an empty list on a page that is gone. The second asks that a search of the active specs for `overwrite=` find "only spec 174's removal note". Meeting it would mean editing 43 occurrences in 12 files, among them a recorded probe output in spec 177 (line 520) and the checked-off record of a built spec, spec 162.

READ: four rules written since say where the rulings go instead. The frozen status page says a proposed record's "pending pins are answered in the spec that implements them" (`context/specifications/STATUS.md`, line 3). The process page says a numbered spec "picked up to build is converted in place: its markers become decisions or a placeholder memo" (line 97). The two-faces spec decided "the active numbered specs are not rewritten" (decision 9). The verb-rename spec decided an active spec is "built against the new names with its text unedited" and its landing notes say how to read the old words (decision 11). INFERRED: the precedent is that the K1 spec carries each ruling as a numbered Decision and a reading table for the old words, and each numbered spec takes its rulings in when it is picked up.

EXECUTED: the eight items do not cover every unsettled choice in the series. `git grep -o -F` for the opening of a clarification marker over specs 174 to 181 finds 28 markers. The eight items, with the flag's name, answer 12 of them: two in spec 175, one in 176, two in 177, one in 179, two in 180 and four in 181. Sixteen remain: one in 174, three in 175, two in 176, one in 178, one in 179, six in 180 and two in 181. INFERRED: at least four of the sixteen name a public argument or a default, such as the listing's default page (spec 176, line 50), the key's shape (line 64) and whether `observations=` becomes a list of paths (spec 181, line 329), so the stories after K1 still cannot freeze every name once the eight are ruled. READ: the lint counts 16 marker lines in four of these files (`tests/lint/allowlist.py:71` to `:74`) and that table may only shrink, so a spec edited to remove a counted marker lowers its entry in the same change.

## Today's public surface

EXECUTED: `uv run --no-sync python -c` with `inspect.getmembers` over the four classes and `vfs.ops`.

The two faces are `AsyncVirtualFileSystem`, the kernel, and `VirtualFileSystem`, the synchronous face. Each exposes the same 25 verbs with identical signatures: `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse`, `write`, `edit`, `delete`, `restore`, `sweep`, `mkdir`, `mkedge`, `rmedge`, `move`, `copy`, `run`, `grant`, `revoke`, `grants`, `posture`, `add_member`, `remove_member`. That set equals `ALL_OPS` (`ops.py:103`).

Each face also exposes 8 management methods that are not verbs: `add_mount`, `remove_mount`, `bind`, `unbind`, `remount`, `close`, `locate`, `locate_edge`. Each has three more plain methods: `capabilities`, `mounts`, `session`. The synchronous face adds `wrap` and a `closed` property. So the kernel has 36 public methods and the synchronous face 37.

The two session classes, `AsyncSession` and `Session`, expose the same 25 verbs without the `authority` argument, plus `close`, and the properties `authority` and `closed`.

Of the 25 verbs, 4 are developer-plane and are never offered to an agent: `sweep`, `posture`, `add_member`, `remove_member` (`ops.py:97`). That leaves 21, of which one, `run`, is retired on paper and served by nothing: neither `DatabaseStorage` nor `InMemoryStorage` has a `run` method.

The package exports 22 names in `__all__`: the two faces, the two sessions, `Authority`, `Principal`, `Path`, `Entry`, `Result`, `ResultError`, `DatabaseStorage`, `InMemoryStorage`, `MountInfo`, `PermissionMap`, `PermissionsPayload`, `permissions`, and six exceptions.

There are 24 error kinds, each with a contract row: `vfs.not_found`, `vfs.exists`, `vfs.wrong_kind`, `vfs.not_empty`, `vfs.unauthenticated`, `vfs.permission_denied`, `vfs.read_only`, `vfs.unsupported`, `vfs.unrecognized`, `vfs.invalid`, `vfs.invalid.unindexable_pattern`, `vfs.unaddressable`, `vfs.conflict`, `vfs.busy`, `vfs.cross_mount`, `vfs.budget_exhausted`, `vfs.budget_exhausted.truncated`, `vfs.budget_exhausted.authority`, `vfs.unavailable`, `vfs.unavailable.backend`, `vfs.unavailable.schema`, `vfs.timeout`, `vfs.cancelled`, `vfs.internal`. Retry class is `refresh` for `conflict`; `transient` for `busy`, `unavailable`, `unavailable.backend`, `timeout` and `cancelled`; `never` for the other 18. One retired string, `vfs.backend_unavailable`, is kept as an inbound alias (`kinds.py:102` to `:104`). READ: the specs in this series would add three: `vfs.unavailable.integrity` (spec 175), and `vfs.replayed` and `vfs.unavailable.in_doubt` (spec 177).

## What this study did not reach

- Nothing was executed against storage. The brief forbade tests and databases while experiments held the engines, and this study took that to include the in-memory store. So the three probes the record rests on were not re-run, and every "today" above is read from code. Re-running the probe scripts kept under the OSTEP studies' `experiments/` folder at this commit would settle whether each still reproduces.
- The sibling reference clones were not opened, as the brief required. What agent harnesses call the removal and move operations is therefore not measured; item 1's table is what the two memos' studies already recorded. One study in the shape of the verb-rename spec's problem section would settle it.
- The offload threshold was not measured again. Running `offload_threshold.py` from the OSTEP studies folder on an x86 runner of the class CI uses, with the pool at that machine's core count, would settle whether 100,000 bytes holds there.
- No time to live was measured, and no peer's value was read. A read of how the durable-workflow hosts in the catalog resume, and after how long, would settle whether 24 hours is long enough.
- Specs 167, 169, 171, 172, 178 and 179 were searched for each item and read around every hit, not read whole. Specs 174 to 177, 180 and 181 were read in the sections that carry the items. A line an item depends on in a section that was not read would be missed.
- The sixteen clarification markers outside the eight items were counted and not studied.
- The call-site counts classify by the receiver's name. They are exact as counts of matches and approximate as counts of router calls, by about ten either way.
- The numbered specs cite many line numbers in `src/` from commit `ba77449`. Only the ones this study leaned on were checked against today's files; spec 180's `backend.py` line 1187 is one that no longer exists.
- `docs-app/` was searched and not read. A rename's cost there is the generated export, which follows the docstrings.

## One line

This study's lean matches the record's on all eight items, the offload threshold in item 5 is already built, and the rulings need three more words than the record asked for: the transfer flag's name, the type of the `Result` field, and what a replayed replacing move is recognised by.
