# A filesystem-shaped kernel for vfs: what the field converged on, where vfs stands, and the recommendation

- **Status:** research memo with a recommendation (commits us to nothing). Proposes one ADR ("the kernel is a filesystem with its indexes inside the gate; every front is a facet over it") and a spec series; names the in-flight specs it touches.
- **Revised:** 2026-10-23, same day, after review with Clay. The first draft put the query, history and rights verbs in a "facet" layer above the kernel. That was wrong: they pass the same gate as `read` and storage executes them, so they are kernel operations. §0, §4.1 and §4.3 now say so; the studies are unchanged.
- **Revised again:** 2026-10-24. The OSTEP studies (03 and 05, under `studies/2026-10-24-ostep-principles-for-vfs/`) caught an overstatement: the search indexes are **not** written in the write transaction. A write only stamps the row dirty (`encoded = false`); `reindex` builds the index later in its own transactions (ADR 033 §6). grep stays correct because it scans dirty rows and consults the index only for encoded rows. The kernel argument stands on the dirty flag and the permission view, both inside storage; the wording in §0, §4.1 and §4.3 is corrected below.
- **Date:** 2026-10-23
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-23: vfs was designed around tools for an AI, then a CLI was planned over those tools, then a Python guest, and more will come; the core shape never changed. What would a refactor look like to make vfs "more of a real file system", keeping the database persistence constraint and the search indexes? Time and cost of the rebuild do not matter; only which design positions vfs to grow and to keep or improve performance.
- **Method:** six parallel read-only studies, each a fresh subagent with the same brief (`studies/2026-10-23-filesystem-shaped-api/00-brief.md`), every clone refreshed to its upstream default branch and licence-checked first (`refresh.log`), every claim labelled READ, EXECUTED or INFERRED, no code copied. Studies 01–04 and 06 are prior art; study 05 is an audit of vfs's own surface with executed statement and allocation counts (`experiments/s05/`). This memo cites the studies as `S01`…`S06` and labels its own synthesis INFERRED. It also stands on this morning's memo `2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md`.

## 0. The recommendation in one paragraph

Do not turn vfs's public API into POSIX. Do split vfs into a **kernel** and **facets over it**, and draw the line at the gate. The kernel is everything that touches stored data under the one gate (authority, mount routing, the permission view): the storage seam and the router's core. Its **filesystem core** is a dozen path-keyed operations (resolve, stat, list with a cursor, read with a byte range, write with preconditions, create, remove, mkdir, rmdir, rename with a replace rule, copy) plus the three stored facts vfs already keeps on every row (version, tombstone, everyone-level). Its **query operations** (`glob`, `grep`, `glean`, `graph`) are kernel operations too, not a layer above: the write that changes a body also stamps the row dirty for the index in the same transaction, the index and the dirty overlay live in storage, and the caller's rights are compiled into the search query itself, which nothing above the kernel could do. Its **history operations** (versions, `restore`, `sweep`) and **rights operations** (the grant family) are kernel operations for the same reason: they read and write facts on rows under the gate. Everything else is a facet over the kernel: the **front ends** (the MCP tool, the CLI programs, the WASI mount provider, a future FUSE or NFS mount), each a thin adapter that adds only what a front needs (a handle table, a flag grammar, a wire), and the **derived verbs** (`tree`, `edit`, `rmdir`) built from kernel calls with no stored fact of their own. This is what every studied system that serves more than one front converged on, it is what vfs's closest competitor just did, and the audit shows vfs's own surface already contains the kernel; what it lacks is the layering, a directory cursor, byte ranges, write preconditions and the rename-replace rule. The SQL cost per verb comes from the stored facts, not from the API shape, so the refactor is performance-neutral where vfs is already bounded and a performance win exactly where it is not (a 10,000-child `ls` with no cursor, a whole-body read for a head, a lost-update append).

## 1. What "filesystem-shaped" means, measured

Four protocols that have nothing else in common (9P, FUSE's high-level API, WASI 0.3's `wasi:filesystem`, SQLite's own VFS) share a core of **nine operations**: resolve, stat, open, ranged read, ranged write, truncate, close, create, delete; mkdir/rmdir, list, rename and sync are in three of four. Two things are absent from all four: a seek (the position lives in the client) and any search or query message (S02 §6, READ).

The Python filesystem abstractions agree from the other side. pyfilesystem2 derives its whole API from seven abstract methods; fsspec's practical minimum is `ls` plus one body verb plus `rm_file`; opendal's kernel is thirteen functions and six typed handles with the byte range, the listing limit and start-after, and every precondition as **per-call arguments, not modes** (S01 facts 1–4, READ). All three key every call by path; none has an fd or inode table; rename is a kernel requirement in none; walk, glob, recursive delete, copy and move are universally derived (S01 fact 6, S01 §4).

Production stores whose metadata lives in SQL draw the line in the same place. SeaweedFS's whole store contract is sixteen methods: five row verbs, two keyset-cursor listings, one children sweep, a transaction, three KV verbs; walks, recursive delete, rename and parent creation are composed above it. JuiceFS has about fifty private primitives under a ninety-method POSIX surface, and FUSE, S3, WebDAV, SDKs and the CLI all share one internal API (S06 facts 1, 2, 10, READ).

So "filesystem-shaped" is a **small path-keyed kernel with ranges, cursors and preconditions as arguments**, and derived verbs above it. It is not fds, not mode bits, not links, and not a stateful handle in the kernel.

## 2. Where vfs stands against that (S05, the audit)

- **The kernel is already in there.** Of vfs's twenty-five routed verbs, the filesystem-shaped parameter core is small and POSIX-named: `path`, `src`/`dest`, `parents`, `exist_ok`, `overwrite`, `cascade`, `max_depth` (36 slots). What makes the surface tool-shaped is three cross-cutting channels (row lists in, column projections, the batch twins) and the flag tables of the four search verbs (89 slots), plus `authority` on every call (S05 fact 1, READ).
- **The seam is path-keyed and whole-body throughout**: no offset, length, handle or cursor on any `Supports*` method (S05 fact 2).
- **Missing, each with a recorded reason or a landing site:** rename-replace (spec 167 adds `overwrite=`); a directory cursor (ADR 033 deferred it to "the MCP pass", still open); byte ranges (spec 152: "write is whole-file"; `substr` noted as the cheap ranged fetch); truncate and append (ADR 080 pin 3: no append verb; spec 167's `>>` is read-then-write with no version precondition and can lose data); open handles (ADR 074 names them as a trash-leak seam); links (parked, ADRs 011 and 021 rule them out) (S05 §4, READ).
- **EXECUTED:** `ls` of a 10,000-child directory returns all 10,000 rows in three statements with no limit, cursor or warning. A single `read` or `stat` is one SELECT as the system actor, three as a named principal. A one-row create issues nine statements, of which four are the verb's own; the rest are the version mint, the fs mirror edge, the glob path segments, the owner label and the arbitration savepoint. Per returned row the envelope costs one pydantic construction (about 27 allocated blocks) (S05 facts 4–7).
- **The SQL cost is bought by stored facts, not by the API shape.** A filesystem-shaped API over the same tables issues the same SQL; the only shape-dependent cost is the per-row construction (S05 §7, INFERRED by the study, and this memo agrees).
- **The Rust engine is shape-blind.** It takes bytes, ids and packed arrays and returns ids, spans and scores; no API reshaping touches `crates/vfs-core` (S05 fact 12).
- **Consumers already use the kernel.** The WASI mount provider and the CLI's file commands use nine verbs through the filesystem-shaped slots only; ETL uses the batch twins; the model-facing MCP tool is the only surface that needs every tool-shaped channel at once, and the row-chaining channel (`observations=`) is already withheld from the wire (S05 fact 11).

## 3. What the peers teach, one lesson each

- **Jackrabbit Oak** (S03) is the closest analogue: a versioned tree over a database with a query engine and several adapters. Its kernel is an immutable node-state store under a path-keyed `Tree` API with no handles; its indexes are maintained inside the commit (property and reference) or by checkpoint diffing (Lucene), with a hybrid index hiding the lag; **query results are rows that resolve back into the same tree API**; permissions are checked once in a secure view that filters listing, lookup, mutation and query rows alike. No adapter exposes a query as a virtual directory.
- **mirage** (S04), the direct competitor, rebuilt its kernel since our September memo as POSIX-shaped bytes (`readdir`, `stat`, `read(offset, size)` required; write, rename, unlink, truncate optional) and now serves seven model tools, a shell, FUSE, FSKit, NFS, SFTP, HTTP, RPC and a CLI from one dispatcher. `grep`, `glob`, `head`, `wc` and `edit` are derived above the kernel, with optional push-down hooks. Its recorded costs are all mount-side: a handle table with buffered writes, a size-known flag, NFS read-only.
- **deepagents** (S04) kept the tool shape, made `grep`/`glob` abstract per backend, reimplemented them four ways, shipped two bugs from the shell-string variant, and still refuses path permissions on any backend with `execute` because "shell commands bypass path rules". The second consumer cost it a second implementation of every verb.
- **Cloudflare's dofs** (S03): FUSE forced the kernel to grow ranged writes, a per-open write buffer committed at release, dirty-range flushes and a cached size column (a one-byte write on 64 MiB went from 63.8 ms to 6.3 ms); the path-only adapters (HTTP, MCP, CLI) added nothing below the API.
- **JuiceFS and SeaweedFS** (S06): every listing is keyset-paged on the last name; the child key is `(parent, name)`; a write is an appended shadowing record with lazy compaction; whole-file write-back happens at close from an adapter-held buffer; **errno from the store up makes the FUSE adapter a pass-through**, gRPC codes mean a mapping table per front. Neither indexes bodies; both expose a change feed an external, eventually consistent index would subscribe to. The in-transaction index is the gap vfs fills.
- **agentfs** (S03) is the one kernel that is inode-keyed at the API, "to match FUSE and POSIX", and it regrew a path-keyed layer on the same struct for its SDK, CLI and MCP callers.
- **mcpfs** (S04) is the boundary proof in the other direction: list and get map onto `readdir` and `read`, but create, update, delete and search cannot be paths and were pushed to a CLI in three days. A filesystem face always needs a separate verb door for parameterised actions.
- **Nobody studied has both an index-backed search and a POSIX front over one kernel** (S03 fact 12). That is the position vfs is building toward, and the layering below is how to hold it.

## 4. The recommendation: a kernel and facets

INFERRED throughout; each row names the study fact it rests on.

### 4.1 The four rules

1. **The kernel's core is a filesystem.** One small, path-keyed operation set with byte ranges, listing cursors and write preconditions as per-call arguments; errors as the classified `ErrorKind` set, which already maps one-to-one onto errno (this morning's memo, F5). The storage seam and the router's core speak exactly this set. (S01 facts 4–5, S02 §6, S06 facts 5 and 11.)
2. **The query, history and rights verbs are kernel operations, not a layer above it.** `glob`, `grep`, `glean` and `graph` pass the same gate as `read` (`_call_storage` in `base.py`) and storage executes them against the index plus the dirty overlay the write transaction stamps (the index itself is rebuilt by `reindex`, ADR 033 §6); the caller's rights become a filter inside the query (`_viewed` in `backend.py`, ADRs 067 and 072), which no layer above the kernel could apply, because a layer above only sees rows after the search has run. Versions, `restore`, `sweep` and the grant family read and write facts on rows under the same gate. A backend that declares no index is still served `grep` through the kernel, by a scan over what `read` returns: a slower kernel answer, not grep leaving the kernel. This is where vfs's kernel is deliberately richer than any file protocol in §1, and it is the one thing no SQL-backed filesystem studied has. (S03 fact 10, S06 fact 12, S02 §6.)
3. **Everything else is a facet.** Each front end (MCP, CLI, WASI, FUSE) and each derived verb (`tree`, `edit`, `rmdir`) sits on the kernel and adds only its own machinery: a flag grammar, a handle table, a wire, a line window. (S01 fact 9, S04 fact 4.)
4. **Rows are the one result type, and they are the tree's own rows.** A query returns `Observation` rows that resolve into the same kernel (Oak's rule); the `Result` envelope stays as the evidence-carrying wire ADR 010 decided, but the row becomes cheap and the cursor becomes a field of it. (S03 fact 10, S05 facts 7–8.)

### 4.2 The kernel's filesystem core, as the public surface would show it

| Kernel op | Today | Proposed per-call arguments | Rests on |
|---|---|---|---|
| `stat(path)` | same | `columns=` stays (projection is a kernel argument in opendal too) | S01 fact 4 |
| `ls(path)` | returns everything | `after=<name>`, `limit=`; the envelope carries the resumption key; keyset on `(parent_id, name)`, which `reads.py` already orders by | S06 fact 5, S05 §4b |
| `tree(path, max_depth)` | same | the same cursor; derived from `ls` when a backend declares no `tree` | S01 §4 |
| `read(path)` | whole body | `range=(offset, length)` served by the dialect's `substr` on the body column; whole when absent | S01 fact 8, S05 §4c |
| `write(path, body)` | whole body, mints a version | `if_version=` (precondition; fixes the lost-update append), `if_absent=` (create-exclusive), `append=True` (maps to the `add` rung per ADR 080 pin 3), `truncate` is `write(b"")` with `if_version=` | S01 fact 4 (opendal `if_*`), S06 fact 8 |
| `mkdir`, `rmdir` | `mkdir`; `delete(cascade=False)` | unchanged; `rmdir` named for the facet that wants it, derived from `delete` | S02 §6 |
| `remove(path)` | `delete` (tombstone) | unchanged in meaning: a remove is a tombstone (ADR 074) | S03 fact 8 |
| `rename(src, dst)` | `move`, refuses `exists` | `replace=` (POSIX plain rename replaces; `NOREPLACE` is the default today), `exchange` later if a front asks | S02 fact 7, spec 167 |
| `copy(src, dst)` | same | `replace=`; derived from read+write when a backend declares no `copy` | S01 fact 6 |
| batches | `entries=`, `moves=`, … | **kept**: the plural of each op over N paths is the 10,000-row ETL contract; opendal is the only peer with a kernel batch shape and it is a handle (`Deleter`) | CLAUDE.md, S01 fact 4 |
| `authority` | on every call | on every call; the kernel is the one place rights are judged (Oak's secure view) | S03 fact 11 |

Not in the kernel, by evidence: **handles** (no studied Python kernel has an fd table; FUSE, WASI and NFS adapters own their own handle tables everywhere: mirage, JuiceFS, dofs, wasi-python; ADR 074 names handles as a trash-leak seam), **inode-keyed identity** (agentfs's regret; JuiceFS needed a path wrapper; ADRs 011 and 021 assume one path per entry for rights), **links and mode bits** (declare unsupported; pjdfstest's mode, uid and link families fail by design for any row-backed store), **seek** (absent from every protocol).

### 4.3 The rest of the kernel: query, history, rights

- **Query.** `glob`, `grep`, `glean`, `graph` keep their flag tables; they are the agent-facing differentiator and no file protocol would absorb them (S02 §6). They are kernel operations (§4.1 rule 2): the write transaction stamps the row dirty, `reindex` rebuilds the trigram, lexical and vector indexes later (ADR 033 §6; the edge mirror alone is written with the body), the search reads index plus dirty overlay, and the permission view is applied inside the storage query, not by the router afterwards. They take the same cursor as `ls` and return the same rows. The seam declares each index as a capability; a backend without one is served by a kernel-side scan over `read`, slower but the same operation.
- **History.** Versions, `restore`, `sweep` and the `/.vfs/trash` view as today; a future `history(path)` read belongs here. POSIX-shaped fronts see one version, as Oak's do (S03 fact 8).
- **Rights.** The grant family unchanged; rights are facts on rows, judged at the gate on every call (Oak's secure view, S03 fact 11); never crosses into a guest (ADR 082 pin 2).

### 4.4 The facets: fronts and derived verbs

- **Fronts.** The MCP tool (spec 171) projects the kernel; the CLI (spec 167) is programs over the kernel; the WASI mount provider is eight methods over seven kernel ops (this morning's memo, Table 1); a FUSE or NFS mount later is the same provider with a handle table, as mirage ships. A front's own machinery (flag grammar, line windows, handle buffers, staged bodies, the errno table) lives in the front.
- **Derived verbs.** `tree` is `ls` repeated, `edit` is read then write with `if_version=`, `rmdir` is `remove` on a directory. Each is built from kernel calls and stores no fact of its own; a backend may declare a native `tree` or `copy` and the kernel uses it.
- **In-process chaining** (`observations=` rows in) becomes a method on `Result` or a facet helper, not a kernel argument: it is already off the wire and used only by the CLI's pipe and ETL (S05 fact 11).

### 4.5 Storage: what changes under the seam

- The `Supports*` protocols become the kernel set above plus declared capabilities (`ls_cursor`, `read_range`, `write_preconditions`, `copy`, `tree`, each query index). vfs already declares `capabilities()`; this makes the declaration finer, as opendal's ninety-field `Capability` is (S01 fact 9).
- **Bodies stay whole rows at v1.** Text must stay one row for the lexical index, chunking and rendering; a ranged read is `substr` (opendal's SQL services do exactly this; S01 fact 8). Chunked blobs (every POSIX-serving DB store chunks: 512 KiB, 4 KiB, 8 KiB, 2 MiB; S03 fact 3) are the named direction for `data` rows **only if** a front demands ranged writes; no consumer today does (WASI stages whole; the CLI and MCP are whole). Say this in the docstring; never as a cap.
- **Errors are errno-shaped from the store up** already (`ErrorKind`); the WASI errno table lands in `results/kinds.py` as spec 169b §b7 says. This is what makes the WASI provider and a future FUSE adapter pass-throughs (S06 fact 11).

## 5. What it does to performance

- **Bounded where vfs is unbounded today:** `ls`, `tree` and `glob` gain a cursor, so a 10,000-child directory costs one page, not 10,000 pydantic rows and 275,000 allocated blocks (S05 fact 7). The cursor is keyset on a column the children select already orders by, so it adds a predicate, not a statement.
- **Cheaper where the body is big:** `read(range=)` lets `head`, a line window or a 64 KiB `fd_read` fetch a slice through `substr` instead of staging the whole body three times (this morning's memo, step 2 of the teaching journey).
- **Correct where it loses data:** `write(if_version=)` makes `>>`, `edit` and every read-modify-write a conditional write; today's `>>` is documented as able to lose concurrent appends.
- **Neutral everywhere else:** the per-verb SQL is bought by the version mint, the mirror edge, the path segments and the rights stamps, and the refactor touches none of them (S05 §7). The Rust engine is untouched (S05 fact 12).
- **The row cost is the one shape-dependent cost.** One `Observation.model_validate` per returned row is fine at a page of 100 and expensive at 10,000; with a cursor the 10,000 case stops existing, and a slotted or Rust-built row is a later, independent step.

## 6. What not to do, and the decision each respects

- **Not POSIX at the public API.** No fds, no `open`/`close` verbs, no seek, no mode bits. The studied kernels show handles are an adapter concern, and ADR 074 recorded why vfs must not hold them.
- **Not inode-keyed identity.** `Entry.path` stays the sole identity (ADRs 011, 021); `parent_id` stays the hierarchy arbiter (ADR 018). agentfs and JuiceFS both had to regrow a path layer.
- **Not dropping the envelope.** ADR 010's reasons stand and no peer has an errno analogue for provenance, rebasing and severity (S05 fact 8); Oak's row-to-tree rule is the same idea.
- **Not dropping batches.** The 10,000-row contract is a kernel shape here because ETL is a first-class audience; no peer's single-object protocol constrains us.
- **Not chunking text.** The in-transaction lexical index is the differentiator; chunk `data` rows later, if a front needs ranged writes.
- **Not an `ask` or a policy language.** ADR 084 stands; the kernel allows or classifies.

## 7. Order of work, and the in-flight specs it touches

Each step lands green and is useful on its own; the order is by what is unbounded or incorrect today first.

1. **ADR: the kernel and the facets** (§4.1's four rules, the kernel table, the query verbs as kernel operations, what is not in the kernel). Amends ADR 033's deferral of the cursor and ADR 080 pin 3's "no append verb"; cites this memo.
2. **Spec: the listing cursor** on `ls`, `tree`, `glob` and the envelope's resumption key; the keyset predicate in `reads.py`; conformance rows on every dialect. Closes the open question's cursor thread.
3. **Spec: write preconditions and append** (`if_version`, `if_absent`, `append=True`); rewrites spec 167's `>>` and the WASI provider's create path (one `write(if_absent=True, b"")` is still a version; the second write is wasi-python's, per this morning's memo F9).
4. **Spec: ranged read** (`range=` through `substr` per dialect; the WASI provider and `head` use it).
5. **Spec: rename and copy with `replace=`**: already spec 167 task zero; fold in `NOREPLACE` as the default and the version mint for the replaced body.
6. **Spec: the storage seam as the kernel** (the `Supports*` rewrite, capability declarations, synthesized fallbacks for `tree` and `copy`), with the conformance battery reorganised by kernel op.
7. **Spec: the public surface regrouped by kernel group** (file, query, history, rights; the fronts' machinery moved out; move `observations=` chaining onto `Result`; keep the flat method names where a group has one verb). Specs 167, 171 and 172 are rebased onto the kernel; 169b narrows to generic wasm programs as this morning's memo says; 170 is unchanged.
8. **Later, independent:** a cheaper row type; chunked `data` bodies if a front needs ranged writes; a FUSE or NFS front as a mirage-shaped provider with a handle table.

## 8. Open questions for Clay

- **Q1.** Flat or grouped at the Python surface: keep `vfs.read/ls/write/...` flat with the new arguments, or expose the kernel groups as namespaces (`vfs.query.grep`, `vfs.history.restore`)? The kernel is the same either way; this is ergonomics.
- **Q2.** Should `delete` be renamed `remove` (POSIX's word) while keeping the tombstone meaning, with `rmdir` as its directory form?
- **Q3.** Is the cursor's resumption key a field on `Result` (Oak's `hasMore` pattern) or a separate return? The MCP wire needs it as a field; the open question on long batches already asks this.
- **Q4.** Do we commit now to chunked `data` bodies as the named direction for ranged writes, or leave it unnamed until a front asks?
- **Q5.** Which front comes first after WASI: FUSE (mirage's path, the richest test of the kernel) or NFS (no kernel module, read-only in mirage)?

## Sources

- Studies under `studies/2026-10-23-filesystem-shaped-api/`: `00-brief.md`; `01-minimal-kernels-pyfilesystem-fsspec-opendal.md`; `02-protocol-shapes-9p-fuse-wasi-sqlite-vfs-pjdfstest.md`; `03-filesystems-over-databases-computer-agentfs-libsqlfs-oak.md`; `04-ai-tool-shaped-peers-deepagents-mirage-afs-langchain-mongodb-mcpfs.md`; `05-vfs-surface-audit.md` with `experiments/s05/` (statements, 10k-child `ls`, allocations; vfs at `ac5c515`); `06-sql-metadata-engines-seaweedfs-juicefs.md`; `refresh.log` (every clone's default branch, commit, date and licence as of 2026-10-23: plan9port, libfuse (LGPL, study only), filesystem_spec, pyfilesystem2, opendal, WASI, sqlite, juicefs, computer, agentfs (MIT in package metadata, no top-level licence file in the checkout; study only), libsqlfs (LGPL, study only), jackrabbit-oak, deepagents, mirage, afs (BSL 1.1, study only), langchain-mongodb, mcpfs, pjdfstest, browser_wasi_shim, seaweedfs).
- `2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md` and its experiments.
- ADRs 010, 011, 018, 021, 033, 051, 055, 074, 080, 082, 084, 085; specs 152, 167, 169, 171, 172; `context/standards/mission.md`; `context/open-questions.md`.
