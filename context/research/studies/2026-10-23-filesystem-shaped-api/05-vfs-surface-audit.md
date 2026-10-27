# Study 05 — vfs's own public surface, audited for shape

- **Date:** 2026-10-23
- **vfs commit:** `ac5c515` (`main`, with the uncommitted ADR 081–086
  and spec 166–173 drafts in the tree)
- **Scope:** in-repo only; no reference clone was read.
- **Scripts (EXECUTED, outputs beside them):**
  `experiments/s05/statements.py` → `statements.out`,
  `experiments/s05/ls_10k.py` → `ls_10k.out`,
  `experiments/s05/allocations.py` → `allocations.out`.
  Every number is a count (statements, rows, object constructions,
  allocated blocks); nothing is timed.
- **Labels:** READ = a file at this commit; EXECUTED = ran here;
  INFERRED = my reading across files.

Terms used below. *FS-shaped*: a parameter a POSIX call carries
(`path`, `parents`, `exist_ok`, a source and a destination).
*TOOL-shaped*: a parameter a model-facing tool or a program carries
and no syscall does (a row list to chain on, a column projection, a
batch, a grep flag). *AUTHORITY*: the caller's identity. *Envelope*:
the `Result` every verb returns. *Seam*: the `StorageBackend`
protocol the router calls.

## 1. Every public verb, its signature, and the shape of each parameter

READ, `src/vfs/base.py`. Twenty-five routed verbs (`ALL_OPS`,
`src/vfs/ops.py:103`) plus the admin surface. Every verb returns
`Result`. `authority` is keyword-only on all twenty-five.

| Verb (line) | FS-shaped | TOOL-shaped | AUTHORITY |
|---|---|---|---|
| `read(path, observations, *, columns, authority)` (879) | `path` | `observations` (row list), `columns` (projection) | `authority` |
| `stat(path, observations, *, columns, authority)` (892) | `path` | `observations`, `columns` | `authority` |
| `ls(path, observations, *, columns, authority)` (905) | `path` | `observations`, `columns` | `authority` |
| `tree(path, max_depth, *, columns, authority)` (918) | `path`, `max_depth` (`find -maxdepth`) | `columns` | `authority` |
| `write(entries, *, path, content, data, overwrite, parents, authority)` (935) | `path`, `content`/`data` (the body), `overwrite` (`O_EXCL`), `parents` (`mkdir -p`) | `entries` (batch of `Entry`) | `authority` |
| `edit(path, old, new, edits, observations, replace_all, *, authority)` (987) | `path` | `old`/`new`/`replace_all` (a `sed` form), `edits` (batch), `observations` | `authority` |
| `delete(path, observations, *, cascade, authority)` (1030) | `path`, `cascade` (`rm -r`) | `observations` | `authority` |
| `restore(path, observations, *, authority)` (1065) | `path` | `observations` | `authority` |
| `sweep(path="/.vfs/trash", *, authority)` (1088) | `path` | — (developer plane) | `authority` |
| `mkdir(path, *, parents, exist_ok, authority)` (1112) | `path`, `parents`, `exist_ok` (pathlib's flags) | — | `authority` |
| `mkedge(edges, *, source, target, edge_type, provenance, authority)` (1132) | — | `edges` (batch), `source`/`target`/`edge_type` (a graph triple), `provenance` | `authority` |
| `rmedge(edges, *, source, target, edge_type, authority)` (1177) | — | `edges`, the triple | `authority` |
| `move(src, dest, moves, *, authority)` (1204) | `src`, `dest` (`rename(2)`) | `moves` (batch of pairs) | `authority` |
| `copy(src, dest, copies, *, authority)` (1217) | `src`, `dest` | `copies` (batch) | `authority` |
| `glob(pattern, *, paths, observations, ext, ext_not, globs_not, kind, max_count, columns, authority)` (1234) | `pattern`, `paths` (find roots) | `observations`, `ext`/`ext_not`/`globs_not` (filter channels), `kind`, `max_count`, `columns` | `authority` |
| `grep(pattern, *, paths, observations, ext, ext_not, globs, globs_not, case_mode, fixed_strings, word_regexp, invert_match, before_context, after_context, output_mode, max_count, allow_scan, columns, authority)` (1326) | `pattern`, `paths` | every other parameter: ripgrep's flags (`-i -F -w -v -A -B -l -c -m --include --exclude`), `allow_scan` (index-tier opt-in), `observations`, `columns` | `authority` |
| `glean(query, *, limit, paths, observations, ext, ext_not, globs, globs_not, columns, authority)` (1440) | `paths` | `query`, `limit`, the filter channels, `observations`, `columns` | `authority` |
| `graph(method, path, observations, *, depth, edge_types, edge_types_not, minimal, limit, columns, authority)` (1501) | `path` (the seed) | `method`, `depth`, `edge_types`, `edge_types_not`, `minimal`, `limit`, `observations`, `columns` | `authority` |
| `run(path, *, arguments, authority)` (1548) | `path` | `arguments` (a JSON object) | `authority` |
| `grant(path, principal, level, *, authority)` (1570) | `path` | `principal`, `level` (an ACL row, `setfacl`-like) | `authority` |
| `revoke(path, principal, *, authority)` (1594) | `path` | `principal` | `authority` |
| `grants(path, *, authority)` (1605) | `path` | — | `authority` |
| `posture(path, posture, *, authority)` (1617) | `path` | `posture` | `authority` |
| `add_member(group, member, *, path="/", authority)` (1632) | `path` (picks the mount only) | `group`, `member` | `authority` |
| `remove_member(group, member, *, path="/", authority)` (1651) | `path` | `group`, `member` | `authority` |

Admin surface, not routed and not on the seam (READ, docstring
`base.py:19-21`): `bind` (385), `unbind` (463), `add_mount` (486),
`remove_mount` (533), `remount` (558), `close` (627), `mounts` (670),
`locate` (711), `locate_edge` (739), `session` (764), `capabilities`
(774). `Session` (`src/vfs/session.py`) repeats every routed verb
minus `authority`, delegating to the router (`session.py:7-12`).

Counting parameters across the twenty-five verbs (READ): 36 FS-shaped
slots, 89 TOOL-shaped slots, 25 `authority`. Three shapes recur on
every read verb: a single `path` **or** an `observations` row list
(the `_ONE_TARGET` rule, `src/vfs/params.py:404-409`), a `columns`
projection, and `authority`. Every mutation except `mkdir`, `sweep`
and the grant verbs has a batch twin (`entries`, `edits`, `moves`,
`copies`, `edges`, `observations`).

**Lesson for vfs:** the FS-shaped core is small and already
POSIX-named (`path`, `parents`, `exist_ok`, `overwrite`, `cascade`,
`src`/`dest`); what makes the surface tool-shaped is three
cross-cutting channels (`observations`, `columns`, batches) plus the
program flags of `grep`/`glob`/`glean`/`graph`, not the verb names.

## 2. The envelope: what it buys, what it costs

What `Result`/`Observation` give that a POSIX API (an errno and a
buffer) cannot — READ, `src/vfs/results/envelope.py`,
`src/vfs/models/entry.py`, ADR 010:

- **Classified errors with severity and provenance.** `ResultError`
  carries a dotted `kind`, `severity` (error/warning/info), `source`
  (the bind path of the producing hop, stamped by `with_mount`,
  `envelope.py:158`) and a derived `retry_class`; `success` is a
  property, never stored (`envelope.py:380`). errno has one integer
  and no "nineteen of twenty mounts answered" state (ADR 010 pin 8).
- **Rebasing across mounts.** `Result.with_mount` re-roots every row
  and error and drops a row whose global path would overflow
  `MAX_PATH_LENGTH` as a warning (`envelope.py:662-702`). A POSIX
  mount table does this inside the kernel; here it is a value
  transform the router applies once per dispatch (`base.py:2919`).
- **Set algebra and merge laws.** `&`, `|`, `-` and `merge` fold rows
  by path with a mask-driven "left wins what it fetched" rule and a
  version agree-or-null rule (`envelope.py:458-557`); fan-out demotion
  (`merge_branches`) is the zero-progress rule.
- **The populated mask.** `Observation.populated` distinguishes
  fetched-and-null from not-fetched (`entry.py:453-460`); backends
  stamp it from the requested `columns`
  (`storage/backends/database/reads.py:1-10`). `stat(2)` has no
  such mask; `statx` has one (`stx_mask`), which is the discipline
  cited.
- **The wire.** `to_payload`/`from_payload` round-trip the envelope as
  MCP `structuredContent`, open (`extra='allow'`), lenient per item
  (`envelope.py:723-793`); ADR 085 pin 10 strips bytes on the wire.
- **Projection.** `columns=` narrows the select list
  (`reads.py:900-918`); a `read` with `columns={"data"}` is how the
  WASI spike fetched a program's bytes (ADR 082 context).

What it costs on the hot path — EXECUTED,
`experiments/s05/allocations.py` on `InMemoryStorage`, system actor,
second call of each (first call warmed caches):

| Call | Rows | `Observation.model_validate` | `Result()` | `Path()` | `getallocatedblocks` delta | live blocks at return |
|---|---|---|---|---|---|---|
| `read(/one/f.md)` (1 KiB body) | 1 | 1 | 2 | 6 | 1,001 | 307 |
| `stat(/one/f.md)` | 1 | 1 | 2 | 6 | 904 | 278 |
| `ls(/one)` | 1 | 1 | 2 | 5 | 1,155 | 361 |
| `ls(/hundred)` | 100 | 100 | 2 | 5 | 3,973 | 1,642 |
| `ls(/big)` | 10,000 | 10,000 | 2 | 5 | 275,029 | 122,319 |
| `stat` through `Session` | 1 | 1 | 2 | 6 | 897 | 276 |
| `read` + `to_payload()` | 1 | 1 | 2 | 6 | 997 | 306 |

Reading the counts: exactly one pydantic construction per row
(`reads.py:929-937`, `Observation.model_validate`), no `model_copy`
on the root mount (the rebase is the identity at `/`,
`envelope.py:683`), and two `Result` constructions per call — the
backend's and the `with_mount` copy (`envelope.py:684`). The
per-row marginal cost is about 27 allocated blocks and 12 live
blocks (10,000-row listing minus the 1-row one, divided by 9,999);
the per-call fixed cost is about 900–1,000 blocks, of which the
envelope's own share is small (INFERRED: the fixed cost is
SQLAlchemy's session, the aiosqlite round trip and the six `Path`
brandings — resolve, terminal, rebase; the envelope adds two
`Result` objects and one frozenset mask per row).

**Lesson for vfs:** the envelope's price is one model construction per
row and two per call; the fixed per-call cost is the SQL session, not
the envelope, so a shape change that kept the envelope and removed a
session would move the hot path more than one that did the opposite.

## 3. The storage protocol

READ, `src/vfs/storage/protocol.py`.

| Protocol | Methods | Notes |
|---|---|---|
| `SupportsRead` (118) | `read`, `stat`, `ls`, `tree` | the verb minimum; `StorageBackend` = this + `name`, `description`, `capabilities()` (422) |
| `SupportsMutation` (159) | `write(entries)`, `edit(edits, path\|observations)`, `delete`, `restore`, `sweep`, `mkdir`, `move(operations)`, `copy(operations)`, `mkedge(edges, provenance)`, `rmedge(edges)` | exactly `MUTATING_OPS`; `move`/`copy` take `ResolvedPair` lists |
| `SupportsPatternSearch` (249) | `glob(patterns, ...)`, `grep(pattern, ...)` | scope arrives only as composed pattern text, never as paths |
| `SupportsGlean` (299) | `glean(query, limit, filters, observations, columns)` | separate family: needs a retrieval index |
| `SupportsGraph` (326) | `graph(method, path\|observations, depth, edge_types, ...)` | walks the backend's own subgraph |
| `SupportsRun` (346) | `run(path, arguments)` | ADR 082 pin 12 deletes it; no shipped backend implements it |
| `SupportsGrants` (359) | `grant`, `revoke`, `grants`, `posture`, `add_member`, `remove_member` | answers ride as `grants=`/`members=` extras |
| `SupportsTraits` (443), `SupportsReindex` (459), `SupportsClose` (472) | `traits()`, `reindex()`, `close()` | optional, not routed |

Is the seam path-keyed and whole-body? **Yes to both** (READ).
Every method addresses rows by a branded, terminal-relative `Path`
or a list of `Observation` rows whose `path` is the key
(`protocol.py:24-31`, `targets_of` at 490); bodies cross as whole
`Entry.content` XOR `Entry.data` on the way in (`entry.py:88-89`)
and whole `Observation.content`/`data` on the way out. No method
takes an offset, a length, a handle or a cursor (grep over
`protocol.py`: none).

Where the derived facts live relative to the seam (READ):

- `version`: minted inside storage — "guarded inside the persistence
  layer and reported on observations — a caller cannot author one"
  (`entry.py:66-68`); the mint is `storage/backends/database/versions.py`
  and the per-entry counter `writes.py:33-37`. The router sees it only
  as `Observation.version` and uses it in the merge law.
- `content_hash`, `size_bytes`, `lines`, `mime_type`, `source`,
  `render_status`: computed by `Entry`'s validators at construction
  (`entry.py:211-232`), i.e. router-side before the seam; storage
  stores them and the reindex pass fills a bytes row's text rendering.
- The trash: entirely inside storage. A delete is a tombstone on the
  row (`trash.py:1-10`), the `/.vfs/trash` head is a view the read
  builders synthesize (`reads.py:23-31`), and `restore`/`sweep` are
  seam verbs. The router knows only the path grammar
  (`check_reserved_path`, `base.py:2868`) and the trashed hint key
  (`TRASHED_KEY`, imported at `base.py:103`).
- Rights: inside storage per call (`backend.py:1497-1557`,
  `_resolution`/`_viewed`); the router adds a second, mount-level
  permission map and the ladder's verb table (`ops.py:134-160`).

Composed in the router vs delegated whole (READ, `base.py`):

| Composed in the router | Where | Delegated whole to one backend |
|---|---|---|
| Fan-out of `glob`/`grep`/`glean` over every binding: scope roots composed into pattern text and residuated per mount, concurrent root probes, merge order, `max_count` cap, ranked re-merge by BM25 | `_route_fanout` 2018, `_glob_dispatches` 2174, `_grep_dispatches` 2255, `_rank_fanout` 3158 | a single-mount `glob`/`grep`/`glean` call |
| Two-path verbs: pairs resolved, cross-mount refused (EXDEV), bind sites refused (EBUSY), grouped per mount | `_route_two_path` 2456 | the per-mount pair list |
| Batches: `entries` grouped per mount and depth-sorted; `observations` grouped per mount; `edges` grouped and de-duplicated | `_route_entry_batch` 2572, `_dispatch_grouped_observations` 1727, `_route_edge_batch` 2631 | the per-mount group |
| `tree` across nested mounts | `_tree_region` 1937 | a single mount's subtree |
| Rows-in-hand filters for `glob`/`grep` over `observations` (no storage call) | `_glob_rows_in_hand` 1794, `_grep_rows_in_hand` 1835 | — |
| Shadow filter: rows under a deeper binding dropped | `_shadow_filter` 3088 | — |
| The gate: params → capability → reserved grammar → mount permission map → EBUSY | `_gate_params` 2812, `_gate_entry` 2829, `_busy_guard` 2901 | the ladder and visibility, inside storage |
| — | — | `read`, `stat`, `ls`, `write`, `edit`, `delete`, `restore`, `sweep`, `mkdir`, `graph`, `run`, the grant verbs: one `_call_storage` arm each (2933) |

**Lesson for vfs:** the seam is already a whole-body, path-keyed
filesystem API with a row list as its second addressing mode; the
router owns topology (mounts, fan-out, EXDEV, EBUSY) and the backend
owns history, trash and rights, so a shape change at the top would
touch the router's composition code and the seam's signatures but not
where versions and tombstones live.

## 4. Missing filesystem semantics, and where each would land

**(a) Rename onto an existing file.** Today a `move` onto an occupant
refuses `exists` before the cycle checks (`topology.py:13-19`,
`_occupied` at 258); the WASI memo executed it: `os.replace` fails
with `EEXIST` (memo F10). Spec 167 decision 7 adds
`overwrite: bool = False` to `copy` and `move` on the router
(`base.py:1204`, 1217), `params.py` rows 231/237, both protocol
methods (`protocol.py:218-231`) and `topology.py`'s pair ladder,
judged as `write` judges an occupied target and minting a version for
the replaced body (spec 167 §4.1, lines 337-345). READ.

**(b) Directory listing cursors.** EXECUTED (`ls_10k.py`): 10,000
children written in one `write(entries=…, parents=True)` — 40
statements, ten `SAVEPOINT`/`RELEASE` pairs (insert chunks); then
`ls("/big")` returned **10,000 rows in 3 statements** (`BEGIN`, the
target+ancestor select, one `parent_id IN` children select), no
error, no extra, no limit or cursor field on the envelope; with
`columns={"kind"}` the same 3 statements; as a named principal with a
`read` grant on `/big` under a `none` root posture, 10,000 rows in 5
statements. `ls` has no `limit`, `offset` or `cursor` parameter
(`base.py:905`); `tree` has only `max_depth`. ADR 033 §3 deliberately
deferred "a query-wide row cap or cursor" to the MCP pass as a
read-family-wide question ("no wire surface exists to carry a
cursor"), with "keyset resumption over path-sorted results" as the
recorded sketch; the open question `MCP 2026-07-28: long-batch
execution model` (`open-questions.md:192`) still carries it. A cursor
would land as a parameter on `ls`/`tree`/`glob` (router, `params.py`,
`SupportsRead`/`SupportsPatternSearch`), a resumption token on the
envelope, and a keyset predicate on the children select in
`reads.py:844-897`, which already orders by `(parent_id, name)` on a
binary collation. READ + EXECUTED.

**(c) Ranged reads and appends.** There is no offset anywhere in the
read path: `read` takes `path|observations` and `columns`
(`base.py:879`), `read_rows` fetches the whole body joined from the
content table (`reads.py:149-165`, `_entry_projection` 900-916), and
the only `offset` in `src/` is a shell error locus (`vfs.offset`,
ADR 081 pin). Spec 152 §4 states it: "write is whole-file: there is
no partial or ranged write" (line 105) and lists "partial or ranged
writes; ranged reads beyond the engines' own" out of scope (393), while
noting each engine's `substring` as a cheap ranged fetch (353, 371).
Append: ADR 080 pin 3 — "vfs has no append verb; a later one maps to
`add` on the row"; spec 167 implements `>>` as `read` then `write`
"with no version precondition, so concurrent appends can lose data"
(line 385). A ranged read would land as a `range=` (or
`offset`/`length`) parameter on `read` and a dialect-specific
`substr` on `vfs_content`/`vfs_blobs`; an append as a new verb or a
`write(append=True)` with a version precondition. READ.

**(d) Truncate.** No verb. `write(path, content="")` is a whole-body
replace that mints a version of the old body (`versions.py:3-9`:
every replaced body is kept); spec 167 maps `touch` of an absent
file to `write(content="")` and of a present one to `stat`
(§4.1). An `O_TRUNC`-shaped open has no vfs analogue; the WASI
provider handles it by staging an empty buffer and writing whole at
close (memo §1 table, row "whole-file staging"). READ.

**(e) Stat times.** `Observation` carries `created_at`, `updated_at`,
`deleted_at` (`entry.py:438-440`) and `version`; no `atime`, no
distinct `ctime`, no mode bits, no nlink. ADR 013 pin 4: "`updated_at`
is the mount-wide change cursor, and it is coarse". Spec 167's `ls -l`
prints `kind, size_bytes, updated_at, owner_id, version`, "never mode
bits" (§4.1; ADR 082 pin 5). READ.

**(f) An open-handle model.** None. Every verb is one call with a
whole body; the WASI runner stages "a file whole at open and hand[s]
it to the provider whole at close, `fsync` and the call's ending"
(memo §1 table, "Spec 169b §b4–b5"), keeps a staged-buffer cache keyed
`(path, version)` (spec 172 §3), and the memo measured the
consequence: "two `write` verbs and two versions per created file, by
'a file exists from its open'" (F9). ADR 074's options list names
"open handles" among the seams JuiceFS's two-predicate trash leaks
through (line 71) — the only ADR text on handles, and it is a reason
not to have them. READ.

**(g) Hard and soft links.** None. `Entry.path` "is the model's only
identity" (`entry.py:68`); ADR 018 keeps `parent_id` as the hierarchy
arbiter and parks "name-on-edge, `parent_id` dropped, hard links" in
`open-questions.md:83-91` ("unlocked only by a ratified requirement for
hard links … a full research → ADR cycle"); ADR 021 (line 81) notes
path-prefix grants assume one path per entry, which hard links break;
ADR 011 (line 89): "If symlink-alikes or per-component gates ever
arrive, this shape is re-litigated, not patched." READ.

**Lesson for vfs:** every missing POSIX semantic has a named landing
site and most have a decision that chose against it for a reason
(trash leaks through handles, grants assume one path, cursors need a
wire); the two the consumers have already tripped on — rename-replace
(F10) and the open-time empty write (F9) — are the ones with specs in
flight.

## 5. The four consumers: verbs and parameters each uses

Sources (READ): MCP — spec 171 §1 (`AGENT_OPS` = the twenty-five minus
`DEVELOPER_OPS` {`sweep`, `posture`, `add_member`, `remove_member`}
and `run`, i.e. twenty verbs, plus `cli`; withheld parameters
`authority`, `observations`, `provenance`). CLI — spec 167 §4.1's
flag-to-call table. WASI — memo §2 (the provider's eight methods) and
§3 (the executed verb trace). ETL — CLAUDE.md's "batches of 10,000+
files in a single call" and `default_authority` (`base.py:3076`).

| Verb | MCP tool (171) | CLI (167) | WASI guest (memo §2–3) | ETL (10k batches) |
|---|---|---|---|---|
| `read` | yes: `path`, `columns` | `cat`, `sed` (regex), `<`, `>>` | `open().read()` → `read(path)` whole; a bytes row via `columns={"data"}` | `read(observations=…)` chaining |
| `stat` | yes | `ls -d`, `stat -c`, `rm`, `cp`/`mv` probe, `touch` | `os.stat`, every kind check before a mutation | — |
| `ls` | yes: `columns` for `ls -l` | `ls`, `ls -l` (`columns={kind,size_bytes,updated_at,owner_id,version}`) | `os.listdir` → `ls(path)` | — |
| `tree` | yes: `max_depth` | `ls -R` | — | — |
| `write` | yes: `path`+`content`/`data`, `entries`, `overwrite`, `parents` | `>`, `>>`, `touch`, `sed` (regex) | `open(w).close()` → `write(path, content)` **twice per created file** (F9); text lands as `content` | `write(entries=10k, parents=True, overwrite=…)` |
| `edit` | yes: `edits`, `old`/`new` | `sed -i 's/a/b/g'` fixed-string only | — | — |
| `delete` | yes: `cascade` | `rm` (`cascade=False`), `rm -r` | `os.remove` → `delete`; `os.rmdir` → `delete(cascade=False)` | `delete(observations=…)` |
| `restore` | yes | `restore P` | — | — |
| `mkdir` | yes: `parents`, `exist_ok` | `mkdir`, `mkdir -p` | `os.mkdir` → `mkdir(path)` | `write(entries=[dir rows])` or `parents=True` |
| `move` | yes: `moves` | `mv` (`overwrite=True`), `mv -n` | `os.rename` → `move`; `os.replace` fails until `overwrite=` (F10) | — |
| `copy` | yes: `copies` | `cp`, `cp -n` | — | — |
| `glob` | yes: filters, `kind`, `max_count`, `columns` | `find` (`glob("**", paths=(P,), columns={kind,size_bytes,updated_at})`) | via the tool door only | `glob(..., columns=…)` to seed a batch |
| `grep` | yes: all flags | `grep`/`rg` with the full flag table; `glob \| grep` passes `observations` in process | `tools.grep` (door) | — |
| `glean` | yes: `limit`, filters | `glean Q [P…] --limit --ext --glob --exclude` | door | — |
| `graph` | yes: `method`, `depth`, `edge_types`, `limit`, `minimal` | `graph METHOD P --depth …` | door | — |
| `mkedge`/`rmedge` | yes: `edges`; `provenance` stamped by the adapter | `unrecognized` with a hint naming the tool | — | bulk `mkedge(edges=)` at ingest |
| `grant`/`revoke`/`grants` | yes | `unrecognized` with a hint | — | `grant` at provisioning |
| `posture`, `add_member`, `remove_member`, `sweep` | never (developer plane) | never | — | yes (operator scripts) |
| `run` | retired (ADR 082 pin 12) | the shell's own host executes | — | — |
| `cli` (meta-verb, not yet in the tree) | the one extra tool | is the CLI | — | — |

Parameters that exist only for the model-facing surface, by this
evidence (READ): `allow_scan` (no CLI flag maps to it; the WASI door
could pass it but nothing does); `provenance` (never on the wire —
the adapter stamps it); `kind=` on `glob` (the CLI's `find -type`
runs its predicate in the shell over `columns={kind}`). `observations`
is the inverse case: **withheld from the MCP wire** (spec 171 §1.1)
and used only in-process — by the CLI's pipe (`glob | grep`) and by
ETL chaining. `columns` is used by three of four consumers (not the
WASI provider, which takes whole rows and whole bodies).

**Lesson for vfs:** the WASI guest and the CLI's file commands use
exactly the FS-shaped slots of nine verbs with whole bodies, ETL uses
the batch twins, and the model-facing surface is the only one that
needs every TOOL-shaped channel at once — the envelope's row-chaining
channel is in-process only and already off the wire.

## 6. The engine: what lives in Rust and whether it cares about the API shape

READ, `crates/vfs-core/src/lib.rs:1-15` ("This crate … holds no
policy: inputs are UTF-8 bytes prepared by the host language … outputs
are exact wire shapes the host defines — posting blobs … and chunk
byte-spans"), `python.rs:496-513`, `src/vfs/native.py`.

| Kernel (module) | Python owner (`extension()` call site) | What crosses |
|---|---|---|
| trigram extraction and posting builder (`grams.rs`, `postings.rs`) | `models/code_grams.py:183`, `models/postings.py:85` | folded bytes in; delta-varint blobs out |
| grep candidate kernel `candidate_ids` (decode, AND, OR, allow-list, cap) | `storage/backends/database/grep.py:422` | blobs + id allow-list in; sorted ids out |
| match law `ContentMatcher`, `hits_batch`, `count_batch` (`verify.rs`) | `pattern_matching/grep.py:198` | pattern + bodies in; line hits with context spans out |
| BM25 tokenizer, builder, scorer, `decode_summary`, `select_blocks` (`lexical.rs`) | `models/lexical.py:139,206,240,266,289` | text / block blobs in; scores and block picks out |
| cosine top-k (`vectors.rs`) | `models/vector.py:351` | packed f32 pages in; `(id, score)` out |
| structure-aware chunk spans (`chunk.rs`) | `native.py:62` | `(utf-8 body, grammar)` in; byte spans + line ranges out |
| markdown references (`links.rs`) | `native.py:88` | bodies in; `(destination, line)` out |
| centrality prior (`signals.rs`) | `models/signals.py:47`, `database/glean.py:731` | dense edge arrays in; per-node prior out |

Planned moves: CLAUDE.md names "the remaining numpy sites (posting
decode/intersect, lexical summary decode, block selection, the BM25
fallback scorer)" as slated to move. EXECUTED: `grep -rn numpy src/vfs`
finds only a comment (`engine.py:97`, about sqlite-vec's import) and
`numpy` is absent from `pyproject.toml`; the four named kernels are
`candidate_ids`, `decode_summary`, `select_blocks` and `lexical_score`
in `python.rs`. INFERRED: that CLAUDE.md sentence is stale — the moves
have landed; what is still Python on a hot path is the per-row
`Observation.model_validate` (§2) and SQLAlchemy statement
construction, neither named for Rust.

Does the Rust seam care about the API shape? **No.** No kernel takes
a `Path`, an `Authority`, a `Result` or an `Observation`; every input
is bytes, ids or packed arrays, every output ids, spans or scores,
and the protocol pin (`PROTOCOL_VERSION = 10`) versions those wire
shapes, not verbs. A ranged `read`, a cursor on `ls` or a handle
model would change nothing under `extension()`; only a streaming
`grep` over partial bodies would touch `verify.rs`'s per-body
contract, and its batch entry already takes a list of bodies with a
deadline (`verify.rs:16-19`).

**Lesson for vfs:** the engine is shape-blind by construction, so the
"keep the indexes" constraint and the "reshape the API" question are
independent — the index pipeline hangs off the write path's staged
rows and the search verbs' candidate ids, not off the verb signatures.

## 7. Statements per call, and which come from shape rather than the verb

EXECUTED, `experiments/s05/statements.py`: one `VirtualFileSystem`
over one `InMemoryStorage`, listener on `before_cursor_execute`,
first touch excluded (it is 100 statements, once), each verb run as
three authorities after one warming call. Statements named
`VERB:table`; `control` = `BEGIN`/`SAVEPOINT`/`RELEASE` (`COMMIT` on
aiosqlite does not pass the cursor hook).

| Verb (one row) | system | named (`alice`, `read_write` grant) | anonymous | statements the verb needs | statements the shape adds |
|---|---|---|---|---|---|
| `read` | 2 (1 `SELECT entries`) | 4 (+`principal_revisions`, `relabels`) | 5 (+`grants`) | 1: the point select of the target and its ancestors, body joined | rights-cache validation 2; anonymous posture read 1; the liveness/tombstone term rides inside the one select |
| `stat` | 2 | 4 | 5 | 1 | same as `read` |
| `ls` (3 children) | 3 (2 `SELECT entries`) | 5 | 6 | 2: target+ancestors, then `parent_id IN` children | same |
| `write` create | 12 (9 non-control) | 14 | 16 | 4: snapshot select, `INSERT entries`, `INSERT content`, parent bump `UPDATE` | `SELECT grants` (the owner label), `INSERT edges` (the fs mirror, ADR 018), `INSERT segments` (glob path terms), `DELETE content` + `DELETE blobs` (whole-body replace pre-clear), `SAVEPOINT`/`RELEASE` (create arbitration), rights 2–3 |
| `write` overwrite | 11 (8) | 14 (11) | 16 (13) | 3: snapshot select, guarded `UPDATE entries`, `INSERT content` | the version mint 3 (`SELECT meta` revision, pre-image `SELECT entries`, `INSERT versions`; +`INSERT version_subjects` for a named actor), the two body deletes, rights |
| `mkdir` | 9 (6) | 11 (8) | 13 (10) | 3: snapshot, `INSERT entries`, parent bump | `grants` label, `edges` mirror, `segments`, savepoint |
| `move` | 17 (14) | 19 (16) | 23 (20) | 3–4: pair read, reparent `UPDATE`, descendant rewrite | `SELECT lock` (serialization point), 7–9 entry selects (snapshot, per-pair live reads, subtree, final re-read), `UPDATE edges`, 2–4 `grants` (subtree gate) |
| `delete` | 5 (4) | 7 (6) | 9 (8) | 2: snapshot select, root claim `UPDATE` | `SELECT lock`, the descendants' stamp `UPDATE`, rights |
| `write(entries=100, parents=True)` | 15 (10) | — | — | the same handful as one row | two insert chunks (parents layer, then files); statements do not grow with rows |
| `write(entries=10,000)` (`ls_10k.py`) | 40 | — | — | — | ten savepointed insert chunks of 1,000 (the parameter budget) |

Reading the table: the essential work of a single `read`/`stat` is
one statement, and `ls` two; everything above that line is the
rights model (a stamp check and a relabel-mark read per call for a
named caller; a posture read for anonymous — `backend.py:1511-1557`,
`rights.py:322-392`). On the write side the shape-derived statements
outnumber the essential ones: the version mint (ADR 013/017), the fs
mirror edge (ADR 018), the path-segment postings for glob
(`pathterms.py`), the owner-label read (ADR 080), and the create
arbitration savepoint are five to seven statements a plain
"upsert the row and its body" would not issue. None of them is a
visibility *join*: when the caller's rights are whole
(`resolution.at("read").whole`, `backend.py:1543`) the read builders
take `view=None` and issue the plain select; a partial view adds
clauses, not statements, until the clause budget splits them
(`rights.py:418-440`). The trash check is a predicate inside the same
select (`reads.py:23-31`), never a statement. INFERRED: a
filesystem-shaped API over the same tables would issue the same
statements, because every extra statement is bought by a stored fact
(history, mirror edges, glob postings, labels) rather than by the verb
signature; the shape-dependent cost is the per-row model construction
of §2, not the SQL.

**Lesson for vfs:** per call, the SQL count is set by what the mount
stores (versions, edges, segments, labels), not by how the verb is
spelled; the one count that scales with the API shape is one pydantic
row per returned entry, and the one count that scales with the
authority model is two to three rights statements per call.

## Design facts for the synthesis

1. READ — Twenty-five routed verbs; the FS-shaped core is `path`,
   `src`/`dest`, `parents`, `exist_ok`, `overwrite`, `cascade`,
   `max_depth`; three TOOL channels (`observations`, `columns`,
   batches) and the program flags of `grep`/`glob`/`glean`/`graph`
   make it tool-shaped (`base.py:879-1651`).
2. READ — The seam is path-keyed and whole-body: no offset, length,
   handle or cursor on any `Supports*` method (`protocol.py`).
3. READ — Versions, tombstones, rights and the trash view live inside
   storage; the router owns mounts, fan-out, EXDEV/EBUSY and the
   mount-level permission map.
4. EXECUTED — A single `read` or `stat` costs 1 SELECT as system, 3 as
   a named principal, 4 as anonymous; `ls` adds one children select.
5. EXECUTED — One-row `write` issues 9 non-control statements to
   create and 8 to overwrite; 4 and 3 of those are the verb's own, the
   rest are the version mint, the fs mirror edge, glob segments, the
   owner label and the arbitration savepoint.
6. EXECUTED — `ls` of a 10,000-child directory returns all 10,000 rows
   in 3 statements with no limit, cursor or warning; ADR 033 deferred
   the cursor to the MCP pass and it is still open.
7. EXECUTED — Per returned row the envelope costs exactly one
   `Observation.model_validate` (about 27 allocated blocks); per call
   two `Result` constructions and about 900–1,000 blocks of session
   overhead; `to_payload` adds none measurable.
8. READ — The envelope buys classified severity, provenance stamping
   per hop, mount rebasing, mask-driven merge laws and a lenient wire;
   none of these has an errno analogue.
9. READ + EXECUTED — Rename-replace (`move(overwrite=)`), the
   open-time empty write (two versions per guest-created file) and the
   lost-update `>>` are the consumer-visible gaps today; specs 167 and
   172 name their landing sites.
10. READ — Hard links, symlinks and open handles are each ruled out by
    a decision (open question "full dirent model" parked; ADR 011,
    021, 074), and `Entry.path` is the sole identity.
11. READ — The WASI provider and the CLI's file commands use nine
    verbs through FS-shaped slots only; ETL uses the batch twins;
    `observations` is withheld from the MCP wire and is in-process
    only.
12. EXECUTED + INFERRED — The Rust engine takes bytes, ids and packed
    arrays and returns ids, spans and scores; it is shape-blind, the
    numpy sites CLAUDE.md lists as pending have already moved, and no
    API reshaping would touch `crates/vfs-core`.
