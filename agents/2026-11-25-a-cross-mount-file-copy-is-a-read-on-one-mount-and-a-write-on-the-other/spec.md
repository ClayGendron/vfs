# A cross-mount file copy is a read on one mount and a write on the other

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. It was checked against `dev` at `27f3d24d`. No roadmap story names it, so its gate is unplaced; the study's lean is gate b, beside story F4's `cp`. It is converted from [the numbered spec 160](../../context/specifications/archive/160-cross-mount-copy-as-read-plus-write/spec.md), which holds `spec.md` alone, as unit 160-1 of [the backlog's map](../2026-11-25-the-backlog-converted/units.md), with the amendments of [its study](../2026-11-25-the-backlog-converted/studies/051-162/160-cross-mount-copy-as-read-plus-write.md) and of [the reassessment's section for 160-1](../2026-11-25-the-backlog-converted/reassessment/bodies-and-mounts.md). It rests on the built preconditions of `write`, the built listing pages, the kernel rulings of 2026-11-15 and roadmap decision D7, and it is built after the second landing of the deletes spec on the branch `origin/a-deleted-row-gives-up-its-path`.

## The outcome wanted

An agent asks to "copy the course rubric into my files", and `copy(src="/course/rubric.pdf", dest="/mine/rubric.pdf")` succeeds where `/course` and `/mine` are two mounts, even when `/course` is read-only. The file at `/mine/rubric.pdf` holds the same bytes, is a new file at version 1, is owned by the caller and is labelled by `/mine`'s posture. The result says, for each pair, that the copy was a read of one mount and a write of another and so was not atomic. A caller with no right to read the source, or no right to create at the destination, is refused exactly as a `read` followed by `write(if_absent=True)` would refuse it. An ETL pipeline copies 10,000 files across two mounts in one call, and the call holds at most one page of bodies in memory and costs a number of storage calls set by the bytes it moves, never by a per-pair round trip. A directory does not cross: its caller copies it file by file from `tree` pages. `move` across mounts is refused `cross_mount`, as today.

## Builds on

- **The preconditions of `write`**, built on `dev`: [`agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`](../2026-11-20-write-takes-preconditions-and-an-append/spec.md). Its decision 7: "A live occupant is `exists`. The refusal carries the occupant's `version` and `content_hash` in `data`", and "An occupant that the same batch staged is named bare". `if_absent` is a parameter of the kernel's `write` (`src/vfs/base.py:934`) and of the seam's (`src/vfs/storage/protocol.py:193-202`).
- **The listing pages**, built on `dev`: [`agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md`](../2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md). `tree` takes `after=` and `limit=` and returns `Result.next_after` (`src/vfs/base.py:884-919`). A directory copied across mounts is composed from these pages.
- **The kernel rulings of 2026-11-15**, on `dev`: [`context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md). Decision 7: "The flag that lets `move` or `copy` land on an existing file is `replace=`, default refuse, and `overwrite=` leaves `write`" (roadmap decision D7, `context/standards/roadmap.md:1218`). Decision 6: a replacing `copy` keeps the destination's identity. Decision 9 leaves to spec 175 which verbs that read a body refuse a damaged one. Decision 12's table reads spec 160's `write(overwrite=False)` as `write(if_absent=True)`.
- **The deletes spec**, specified on the branch `origin/a-deleted-row-gives-up-its-path` at `d8c1d55d`, reviewed fit to build, not built: `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md` on that branch. Its decision 4: "A name that holds only deleted rows is free", and "`write`, `mkdir`, `move` and `copy` treat such a name as empty". Its decision 5: "No write brings a deleted row back", so `if_absent=True` there makes "a new row, `created`". Both are in its second landing, "The name is free" (its decision 16). This spec is built after that landing (decision 11).
- **The vid spec**, specified on `dev` and built on the branches `origin/every-row-carries-a-vid`, `origin/write-requires-a-vid`, `origin/edit-requires-a-vid` and `origin/delete-move-and-restore-require-a-vid`, none in `dev`: [`agents/2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md`](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md). Its decision 3 says of an in-mount copy: "The copy is another entry at version 1, with a vid of its own." This spec amends that decision's cross-mount row and nothing else. Either may be built first.
- **The policy seam**, specified on `dev`, not built: [`agents/2026-11-22-a-policy-judges-each-step/spec.md`](../2026-11-22-a-policy-judges-each-step/spec.md). Its decision 2 gives `copy` one class, `CopyStep`, with `src`, `dest` and `copies`. Its decision 4 puts each pair's source and then its destination in `paths`, with `subtree` true. Its decision 10 places the call site in `_route_two_path`, "after the loop over pairs, before the mounts are asked". Its decision 11 proves a change's rights through each storage's `admits`. Decision 15 below says what a cross-mount pair adds. Either may be built first.
- **The integrity check on read**, unit 175-1, written at [`agents/2026-11-25-a-read-refuses-a-body-that-fails-its-recorded-hash/spec.md`](../2026-11-25-a-read-refuses-a-body-that-fails-its-recorded-hash/spec.md), not reviewed, not built. Its decision 6 checks a text file's served `content` and a bytes file's projected `data`, and "a projection with no body field" against nothing. Its decision 12: "A target whose fault is confirmed returns one `integrity` error and no row", beside the other targets' rows. Its decision 15 gives `verify` to `read` alone, and its decision 18 has a storage declare the `read_check` trait. Its decision 20: "`copy` within a mount does not hash". Decision 14 below follows from these. Either may be built first.
- **Landed code.** The two-path route and its gate (`src/vfs/base.py:2322-2385`, `:2705-2753`); the in-mount copy (`src/vfs/storage/backends/database/topology.py:1-23`, `:450-562`); the byte batcher (`src/vfs/batching.py:65-81`); the commit-point judgment of a transfer (`context/specifications/archive/2026-11-14-a-mutation-is-authorized-for-the-rows-it-acts-on-at-its-commit-point.md`); the cancellation rule (`documentation/maintainers/cancellation.md`).

## Terms

- **Cross-mount pair.** A pair of a `copy` whose source and destination resolve to different mounts.
- **Group.** The cross-mount pairs of one call that share a source mount and a destination mount.
- **Sizing read.** The one `read` of every source of a group that projects no body: `kind`, `source`, `size_bytes`, `mime_type` and `version`. It is judged at the `read` rung and fetches no body.
- **Page.** A run of a group's pairs whose recorded source sizes sum to at most the page budget, cut by the byte batcher's flush law.
- **Body source.** A row's `source` field, `"text"` or `"bytes"`: which body a file has. It is called "body source" in this spec because `ResultError.source` is a different thing, the provenance path of a record.

## What the code does today

| Fact | How it is known |
|---|---|
| `_route_two_path` refuses every pair whose two terminals lie in different mounts with `cross_mount`, before the gate and before any storage is called, for `copy` as for `move`. | Read, `src/vfs/base.py:2366-2369`. Run: `copy("/a/t.md", "/b/t.md")` over two in-memory mounts answers `cross_mount` at `/a/t.md` with `data["vfs.target"] == "/b/t.md"`. |
| The docstrings of `move`, `copy` and `_route_two_path` say a pair that crosses mounts is refused and is "never turned into a copy and a delete". | Read, `src/vfs/base.py:1261-1263`, `:1279-1287`, `:2333-2336`. |
| `tests/base/test_dispatch.py:207-216` pins the refusal for both verbs, and `:219-227` pins that one cross-mount `move` pair refuses its whole batch. | Read. |
| The `cross_mount` kind's hint reads "Move within one mount, or copy then delete across mounts." | Read, `src/vfs/results/kinds.py:246-251`. |
| The README's Known limits says the copy "lifts this for files". | Read, `README.md:139`. |
| The shell's `cp` calls `copy` straight through, with no cross-mount path of its own, and maps `cross_mount` to no host error of its own, so it reads as `invalid`. | Read, `src/vfs/shell/host.py:487-488`, `:94-102`, `:505`. |
| The constitution says a cross-mount operation is not atomic and "MUST either declare so in its result or raise `CrossMount`". | Read, `context/standards/constitution.md:63`. |
| A `read` of several rows with `columns={"kind", "source", "size_bytes", "mime_type"}` returns those fields and no body, a `wrong_kind` error for a directory and a `not_found` error for a missing path, beside the rows of the others. | Run, two in-memory mounts. Read, `effective_columns` in `src/vfs/storage/backends/database/reads.py:131-147`. |
| `read(columns={"data", ...})` of a bytes row returns its bytes, and `read(columns={"content", ...})` of a text row returns its text. A bytes row's `content` is its rendering. | Run. Read, `reads.py:105-107`. |
| `write(entries=..., if_absent=True)` of a new path returns status `created` at version 1 and keeps a declared `mime_type`. Two entries for one path under `if_absent` are refused `exists` with no `data`. A path holding only a deleted file is revived, status `updated`, version 3. | Run. The revive is what the deletes spec removes. |
| An in-mount copy carries the render stamps and the media dimensions verbatim, mints fresh ids at version 1, copies no edge and no `external_id`, pages its bodies under `BLOB_PAGE_BYTES`, refuses a deleted occupant `exists` with the trashed hint, and fails its batch whole on any per-pair error, inside one transaction that holds the mount's serialization point. | Read, `topology.py:1-23`, `:92-108`, `:148`, `:450-562`; `dialects.py:81`. |
| An in-mount copy needs `read` on its source and `add` to create its destination. | Read, `VERB_RUNGS["copy"]`, `src/vfs/ops.py:166`. A create-only write is judged at `add` too (`ADDITIVE_WRITE`, `:190`). |
| A record the router mints above the rebase seam stamps its own bind path as `source`; a skipped mount is reported as an `info` record that is never a failure. | Read, `classified` in `src/vfs/results/envelope.py:239-262`; `skip_record` in `src/vfs/listing.py:674-681`. |
| `src/vfs/base.py` holds 3,090 lines, exactly its entry in `MODULE_LINE_BASELINE`, so any growth fails the lint. | Executed `wc -l`; read, `tests/lint/allowlist.py:27`, `tests/lint/test_code_shape.py:76`. |

## The problem

`copy` of a file between two mounts is refused, even when both are writable. That is the wrong default for `copy`. It is what every agent tries first, it is what `cp` has always done across filesystems, and the kind's own hint tells the caller to do it. The agent's workaround is `read` then `write`, which is right for text and wrong for bytes, because a default `read` of a bytes file returns its rendering and not its body. The shell's `cp` between two mounts fails where GNU `cp` copies.

At the reference deployment the workaround also costs the wrong things. An ETL pipeline that copies 10,000 files out of a read-only reference mount into a working mount does it today as 10,000 reads and one large write, or holds every body in memory at once: at the mean file size of 0.3 to 0.7 MB that is 3 to 7 GB for one batch. The router can do it bounded, by the bytes it moves, and can say honestly that it was two operations.

## Decisions

### 1. A `copy` pair whose ends lie in different mounts copies a file as a read of the source mount and a write of the destination mount; `move` keeps refusing `cross_mount`

The router does the copy where it refuses one today. A `move` pair across mounts is refused as before, at the source with the destination as its target, and is never turned into a copy and a delete.

Reason: a copy only reads its source, so nothing is lost when the two halves are separate: the worst case is a file written at the destination and nothing changed at the source. A move across mounts would delete in one storage what it wrote in another, and a half-move loses or duplicates a file. Precedent: POSIX `rename()` returns `EXDEV` across filesystems and `cp` copies in user space; the constitution allows a cross-mount operation that declares itself in its result (`context/standards/constitution.md:63`); the kernel rulings' decision 9 names "a cross-mount `move`" only as a verb that reads a body, for spec 175, and builds none.

### 2. Files cross and directories do not; a tree is copied by its caller from `tree` pages

A directory source of a cross-mount pair is refused `cross_mount` at the source, with the destination as its target and the detail "a directory does not cross a mount boundary; copy its files". The kind of the source is known only from a storage, so the refusal comes from the sizing read of decision 6, which answers `wrong_kind` for a directory; the router reports it as `cross_mount`. The `copy` docstring gives the composition in words: `mkdir` the destination directories, page `tree(src, after=..., limit=...)`, and pass each page's files as `copies=`.

Reason: a directory across mounts cannot be one transaction on either side, and a tree has no bound. As one call it would hold no snapshot, and a failure part way would leave half a tree with no row naming where it stopped. A caller that pages it sees, per page, what landed. Precedent: the kernel leaves a cross-device copy to user space for the same reason; `tree` pages are built (`src/vfs/base.py:884-919`). The source spec's rule 1 and the study's choice 1, which holds.

### 3. A cross-mount pair is checked up front with every other pair, and its two ends are gated as a read and a write

In the loop of `_route_two_path`, before any storage is called, a cross-mount `copy` pair passes the checks every pair passes (both paths resolve, the destination is not a mount point and holds none), and then two gates:

- The source is gated as a read: its mount must declare `read`, and its path inside the mount must lie outside the reserved space, so a copy out of a trash view stays `invalid` at the path the caller sent, as `_gate_entry`'s docstring says of a copy's source today (`src/vfs/base.py:2730-2733`). The source mount's mask of `copy` is not consulted, because the source is only read, as the `copy` docstring already says.
- The destination is gated as a write: its mount must declare `write`, its path must lie outside the reserved space, and it must pass every permission map from `/` down (`check_writable_composed`), with `subtree` false. A destination mount whose mounter masked `copy` refuses `unsupported` at the mount's path (choice 2).

One refused pair refuses the whole call, and no storage is asked, as today (`src/vfs/base.py:2339-2341`). So a read-only destination is `read_only` before any storage call.

Reason: the gate's order is a promise, and the up-front rule is what the docstrings and the tests already pin. Each end is gated as the verb the router will send it. Precedent: `_gate_entry` already takes read paths and written paths apart (`src/vfs/base.py:2705-2753`); the source spec's rule 5.

### 4. Two pairs of one call that name one destination, one of them across mounts, are refused `exists` up front

When a call's pairs name one destination twice and at least one of the two crosses mounts, the call is refused before any storage is asked, with `exists` at that destination, the later pair's source as its target, and no `data`. Two in-mount pairs that name one destination keep today's answer from their storage.

Reason: the two pairs can fall on different pages, or one on the in-mount path and one on the cross-mount path, so no single storage call sees both, and the outcome would turn on page order or on a race. The answer is the one `write` gives an entry that meets another entry of the same call (the write spec's decision 7, "named bare").

### 5. Cross-mount pairs are grouped by source mount and destination mount, and the groups run one after another in one task beside the in-mount groups

After the loop, the in-mount pairs group by mount as today. The cross-mount pairs group by their (source mount, destination mount), in the order each group first appears. One coroutine runs the groups in that order, page by page, and it runs under `gather_settled` beside the in-mount groups. A group's result does not depend on another's: one group can fail while another lands, as one mount can today.

Reason: one page of bodies is in memory per call, whatever the number of groups, and the in-mount groups keep their concurrency. A group shares one source and one destination, so a page is one call on each. Precedent: the write path groups per mount (`src/vfs/base.py:2470-2514`); the source spec's two groupings, which the study holds.

### 6. A group begins with one sizing read of all its sources, and any refusal there fails the group with nothing written

The router calls `read` on the source mount once for the group, with `observations` holding each source path and `columns` set to `{"kind", "source", "size_bytes", "mime_type", "version"}`. The storage chunks it under its own membership budget. If the answer holds any error, the group fails whole, no write is sent for it, and its result carries the read's errors, with a `wrong_kind` for a directory reported as decision 2 says. A source for which the read returns neither a row nor an error is refused `not_found` at that source, as the mount-site probe reads a storage that answers a `stat` with no row (`src/vfs/mounts.py:438-440`).

Reason: the sizing read proves that every source exists, is a file and is readable by the caller before any write, which is as close to the in-mount ladder's whole-batch refusal (`topology.py:21-22`) as a call across two storages can come. It also gives the sizes the pages are cut by, without fetching a body. It is judged at the `read` rung, so a caller who holds `list` on a source is refused there and its body never moves.

### 7. A group is cut into pages by recorded size under `TRANSFER_PAGE_BYTES`, and each page is one body read per body source and one write

`TRANSFER_PAGE_BYTES: Final = 8 * 1024 * 1024`, a module constant of `vfs/pairs.py` (decision 17). The group's pairs, in the caller's order, are cut by `byte_chunked` on the sizing read's `size_bytes`. A row whose `size_bytes` is absent counts as the whole budget, so it rides alone. For each page:

- **First, the reads.** One `read` on the source mount for the page's text sources, with `columns={"content", "source", "mime_type", "version"}`, and one for its bytes sources, with `columns={"data", "source", "mime_type", "version"}`. A page of one body source issues one read.
- **Then, the write.** One `write` on the destination mount of the page's entries, with `if_absent=True` and `parents=False`, under the caller's authority.

Reason: a bytes row's rendering is not its body and must not be fetched as one, so each body source asks for its own body field alone. The budget bounds what is held, never what is eligible: one file larger than the budget is copied alone, as the flush law says (`src/vfs/batching.py:1-14`). The value is the one every engine already holds for a body page (`BLOB_PAGE_BYTES`, `src/vfs/storage/backends/database/dialects.py:80-81`), named again at the kernel because the kernel imports no backend's constant. Precedent: the in-mount copy's `_copy_bodies` (`topology.py:527-562`). The study's choice 9, which replaces the source spec's every-body-in-memory profile.

### 8. A page whose source moved on after the sizing read is refused `conflict`, and is retryable

When a row of a page's body read is at a version other than the one the sizing read saw, or its body source differs, the page is refused `conflict` at that source, with `data={"version": <the version now>}` and `retryable=True`, and the page's write is not sent. The same holds for a source the body read no longer finds: it is the read's own refusal.

Reason: the page was sized, and its body field chosen, from the sizing read. A rival write in between can change a text file into a bytes file or a 4 KB file into a 1 GB one, and copying the newer state would break the memory bound and could fetch the wrong body. A retry reads afresh and copies the file as it is then. Precedent: a write whose guard misses on a row with no expected version is a retryable `conflict` (the write spec's decision 6); the in-mount copy redrives when a body's version moved between its two reads (`topology.py:557-558`). Choice 3.

### 9. The written file carries what a write carries: its body, its kind, its declared type and the destination's name, owner and posture

Each entry is `Entry(path=<destination>, content=<text>, mime_type=<declared>)` for a text source and `Entry(path=<destination>, data=<bytes>, mime_type=<declared>)` for a bytes source. So the bytes are measured and sniffed against the declared type, `ext` comes from the destination path, a bytes file starts `render_status="pending"` (`src/vfs/models/entry.py:243-250`), the writer owns it and the destination's posture labels it. `external_id`, edges, the render stamps and the media dimensions stay behind. The file is a new entry at version 1, with a vid of its own once vids are built.

Reason: the destination storage is another storage. It renders with its own renderers and indexes with its own index, so a rendering stamped by the source would describe work the destination never did. This departs from the in-mount copy, which carries the render stamps and the media dimensions verbatim (`topology.py:92-108`): within one storage the stamps describe that storage's own work. The source spec's rule 6 claimed parity with the in-mount copy on what travels; the study found that claim false, and this decision states the difference instead.

### 10. An occupied destination is `exists`; a destination holding only deleted rows gets a new file

The write's `if_absent=True` gives the answers of the write spec's decision 7 and of the deletes spec's decisions 4 and 5: a live file or directory at the destination refuses the page `exists`, carrying the occupant's `version` and, for a file, its `content_hash`; a name holding only deleted rows is free, so the copy makes a new file there, status `created`, and the deleted rows stay restorable.

Reason: no transfer replaces an occupant unless told to (the kernel rulings' decision 7). After the deletes spec's second landing, the in-mount copy and the cross-mount copy give the same answer at a deleted name: the name is free. The source spec's interim `overwrite=False` is moot, because `if_absent` is built.

### 11. This spec is built after the deletes spec's second landing

Reason: before it, `if_absent=True` revives a deleted file at the destination (run above: status `updated`, version 3), which makes the deleted file and the copied one a single file and keeps the deleted file's id, while an in-mount copy refuses the same destination `exists` with the trashed hint. Building after leaves no interval in which the two copies disagree and no test written for an answer that is about to change. Choice 1 names the other order.

### 12. A page that fails stops its group; the pages before it stay written; the result's rows name every pair that landed

A page's read refusal, its `conflict` (decision 8) and its write refusal each end the group: no later page of that group is read or written. The destination write of a page is one storage write, so a page lands whole or not at all on the destination's own terms: a write plan with any error runs no mutation statement (the write spec's Terms, "Plan"). Pages already written stay; nothing on the source is touched, so there is nothing to roll back. The rows of the result are exactly the files written, so a caller resends the pairs whose destinations have no row.

Reason: the call is not atomic and the constitution requires it to say so (`constitution.md:63`). Stopping at the first failed page keeps the landed set a prefix of the group in the caller's order, which a caller can resume from. Going on past a failed page would leave holes that only a comparison of the whole batch could find.

### 13. The result is the write's, under `ops=("copy",)`, with one `info` record for each pair that landed

A group's result is rebuilt from its writes' results with `ops=("copy",)`, so the merged result's `ops` is `("copy",)` alone and not `("copy", "write")`. The reads' rows are dropped; their errors are kept. Each row is the row the write returned, status `created`, at the destination path. Beside each row is one record built by `classified`:

- `kind=cross_mount`, `severity=info`, so it is never a failure and `success` is unchanged;
- `path` the destination and `target` the source, kept at `data["vfs.target"]` and rebased with `path` at every hop;
- `data["body_source"]`, `"text"` or `"bytes"`;
- `source` the destination mount's path, as a record the router mints above the rebase seam does.

Reason: the record is the declaration the constitution asks for, and it is per pair so that an auditor reading one row can tell it came from another mount. The source and destination ride the fields the seams already rebase, where plain strings in `data` would keep one hop's paths after the result crossed another. The data key is `body_source` and not `source`, because `ResultError.source` holds a provenance path (`src/vfs/results/envelope.py:84-86`). Precedent: `skip_record` reuses a refusal kind at `info` for a coverage fact (`src/vfs/listing.py:674-681`). The source spec's rule 2, with the study's amendment of the key.

### 14. The rights are two judgments, each by its own storage at its own commit point, and they add no right

The source is judged by the source storage as a `read` judges, the owner floor included. The destination is judged by the destination storage as `write(if_absent=True)` judges: a fresh name at `add` (`ADDITIVE_WRITE`, `src/vfs/ops.py:190`). So a cross-mount copy succeeds exactly when the same caller's `read` of the source and `write(if_absent=True)` at the destination both would, and refuses with the first refusal of the two. The row "`copy` to a new path" of the access levels page (`documentation/reference/access-levels.md:30`) holds across mounts as it stands. A refused pair leaves no row, no `info` record and no file at the destination. A damaged source, once unit 175-1 is built and where the source storage declares its `read_check` trait, is refused by the page's body read with `vfs.unavailable.integrity`, as `read` refuses it, and nothing is written for its page: unlike an in-mount copy (unit 175-1's decision 20), a cross-mount copy hands the body out of its storage, so it does not launder a damaged body into a new hash. The sizing read serves no body and so meets no check (unit 175-1's decision 6): the refusal comes at the damaged file's page, never at the sizing read, and the pages before it stay written (decision 12). The copy passes no `verify`, which unit 175-1's decision 15 gives to `read` alone, so it never takes the salvage read.

Reason: the copy is composed of the two verbs a caller could have called, so it must never reach further than they do. Precedent: rights are judged by each storage inside its own transaction (`context/specifications/archive/2026-11-14-a-mutation-is-authorized-for-the-rows-it-acts-on-at-its-commit-point.md`); the source spec's rule 5.

### 15. To a policy, a cross-mount copy is the call's one `CopyStep`; its reads and writes are storage calls and no step of their own

The router sends the sizing read, the body reads and the writes through `_dispatch_entry`, never through the public verbs, so no call site builds a second step, and no `decisions.within` mark is needed. When the policy seam is built, the rights proof of decision 10 of the policy spec covers a cross-mount pair in two parts: the group's sizing read on the source mount, which is a read that has ended and is then reused for the pages, and the destination mount's `admits("write", entries=..., if_absent=True)` on the destination paths, with bodiless entries, since the write's gate reads no body. The call's order becomes: the router's checks, the proofs, the policies, then the in-mount groups and the cross-mount pages. Whichever of the two specs is built second carries this.

Reason: the policy spec's step is one verb about to run (its decision 1), and a `copy` call is one verb. Its promise that a call the caller may not make is refused before any policy sees it is kept by proving both ends. Precedent: the policy spec's decisions 10, 11 and 23.

### 16. A cancelled cross-mount copy keeps the pages it committed and sends nothing after

Each page's write is one storage write, so a cancellation follows the cancellation rule: a write cancelled before its commit changes nothing, and one cancelled at its commit or after has landed (`documentation/maintainers/cancellation.md`, "The rule"). The pages committed before the cancellation stay. No later read or write is sent, and the caller is raised the cancellation it was cancelled with.

Reason: a call across two storages cannot leave both as if it was never made, as a call across two mounts already cannot. The rule each storage call obeys is kept, and the call adds no new partial state beyond the pages it says it wrote.

### 17. The code lives in a private module `vfs/pairs.py`, and `base.py` does not grow

`src/vfs/pairs.py` holds the pairs of `move` and `copy`: `coerce_pair`, moved from the static method `_coerce_two_path` (`src/vfs/base.py:2386-2401`), `TRANSFER_PAGE_BYTES`, and `copy_across_mounts`, which takes the call on a storage (`AskStorage`, `src/vfs/mounts.py:408-415`), the groups and the authority and returns the merged `Result`. The kernel passes `self._dispatch_entry` as the call. The module sits on the ladder's rung with `vfs.listing`, `vfs.cursor` and `vfs.shell` in `tests/lint/test_code_shape.py:46-71`, and imports only lower rungs (`vfs.batching`, `vfs.paths`, `vfs.models`, `vfs.results`, `vfs.mounts`). `src/vfs/base.py` stays at or under its baseline of 3,090 lines, and its entry is lowered to the new count.

Reason: `base.py` is at its ceiling, and the cursor precedent put a new route concern in a module of its own beside the listing (`src/vfs/cursor.py:1-20`). The pair coercion moves with it because it is the other half of the pairs' own code and its lines pay for the new branch.

### 18. One landing, gated by `scripts/ci.sh`, `scripts/docs.sh check` and the Postgres leg

The tests below, the branch in `_route_two_path`, the module, the hint, the docstrings and the README land together in one pull request. The Postgres leg runs before it, because the cost pin of the Tests section runs on Postgres.

Reason: each part is wrong without the others: the hint and the README describe the branch, and the old refusal test fails the moment the branch exists.

## Cost

| What is added | Multiplier | Arithmetic | Bound |
|---|---|---|---|
| A single-file cross-mount `copy` | per verb call | 3 storage calls: the sizing read, one body read, one write, where an in-mount copy is 1. About one verb call in four of the day's 150,000 is a change; if every one of those 37,500 were such a copy, that is 75,000 extra point reads a day. | Each call is the storages' own, bounded as a one-file `read` and a one-file `write` are. |
| The sizing read of a group | per batch | One call over every source of the group. The storage chunks it: on Postgres one array bind per chunk under `membership_budget`; on SQLite chunks of the same budget. | The membership budget of each engine; no statement grows with the batch. |
| The pages of a 10,000-pair group | per batch | `ceil(bytes / 8 MiB)` pages, each 1 or 2 reads and 1 write. At the median file of 4 KB, 41 MB is 5 pages and 11 calls in all. At the mean of 0.3 to 0.7 MB, 3 to 7 GB is 358 to 835 pages, about 720 to 1,700 calls. At about 20 statements a page (a read's rights reads and fetch, a write's families in `tests/base/test_write_at_scale.py:35-51`), that is about 7,000 to 17,000 statements (INFERRED, not counted). | `TRANSFER_PAGE_BYTES`; statements follow the bytes moved, never a round trip per pair. |
| Memory of one call | per batch | The sizing read's metadata rows for the group (10,000 rows of a few hundred bytes, a few MB), one page of bodies, held once by the read's rows and the write's entries, which share the same `str` and `bytes` objects, and the result's rows and `info` records (2 × 10,000 small objects). | `max(TRANSFER_PAGE_BYTES, the largest file)` of bodies; one page per call by decision 5. |
| Locks | per lock | No lock spans a page. The sizing read and the body reads are plain reads: on Postgres and on a SQLite file in WAL they wait on no writer. Each page's write holds the destination's write transaction for that page alone: on SQLite the one writer lock for a write of at most 8 MiB of bodies, as any batch write of that size holds it. The source is never locked. An in-mount copy of the same batch holds its mount's serialization point for the whole batch (`topology.py:148`). | A lock is held for one page's write and its commit. A read never waits on the copy. |
| The index | per index visit | Nothing is added to the rebuild path. Each written file is a new row the next partial pass indexes, as any write's is, and a bytes file is rendered by `refresh`. | Unchanged. |

No statement is built by this spec: every statement is a storage's own, chunked by that storage's budgets on SQLite and on Postgres.

## Left as it is

- **`move` across mounts.** It stays `cross_mount` (decision 1). A caller copies and then deletes, and the two results say which half happened.
- **`copy(replace=True)`.** Unit 167-7, [the replace spec](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md), written, not reviewed, not built, adds `replace=`. Its decision 12: where this spec is built, a `copy` across mounts with `replace=True` "writes the source's body at the destination without `if_absent`, which keeps the destination's identity and its old body as a version, and a destination key of `if_vids` is passed to that write as its key", and a `move` across mounts "stays `cross_mount`, with or without the flag". That is the kernel rulings' decision 6 for a replacing copy. This spec adds no argument.
- **A request key.** Unit 177-4, [the request-key spec](../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md), written, not reviewed, not built, puts `request_key` on `copy` (its decision 1) and forwards one key with each admitted mount slice, never with a lookup (its decision 6). Its decision 7 reads "A pair or edge with its own endpoints on different mounts still gives `vfs.cross_mount`", which is `dev`'s answer; once this spec is built it holds for a `move` pair and an edge and not for a `copy` pair (decision 1). Neither spec says what a keyed cross-mount `copy` stores, or whether its key rides the destination's write: that is not decided. This spec builds no key.
- **`plan=`.** Story H2 has no spec; when it lands, a cross-mount `copy(plan=True)` issues the sizing read and no write.
- **The executable bit** of `agents/2026-11-22-a-file-carries-its-executable-bit/spec.md`, not built. Whether it travels is that spec's to say once a write takes it.
- **The in-mount copy.** It keeps its one transaction, its render stamps and its ladder.

## Tests

Written first, and seen failing. Counts and states, never clocks. The kernel tests run on two in-memory `DatabaseStorage` mounts unless they say otherwise.

In a new file, `tests/base/test_copy_across_mounts.py`:

- `test_a_text_file_copies_across_mounts`: `/b/t.md` reads the source's text; the row is `created` at version 1; `result.ops == ("copy",)`; exactly one `info` record, `cross_mount`, at `/b/t.md`, with `data["vfs.target"] == "/a/t.md"` and `data["body_source"] == "text"`; `result.success` is true.
- `test_a_bytes_file_copies_across_mounts_byte_equal`: a PDF body; `read("/b/p.pdf", columns={"data"})` returns equal bytes, `source == "bytes"`, `mime_type == "application/pdf"`, `render_status == "pending"`, and the record's `body_source` is `"bytes"`.
- `test_a_read_only_mount_is_a_source`: `/course` added with `permissions="read"`, and a copy into `/mine` succeeds.
- `test_a_source_whose_mutations_are_masked_is_still_a_source`: the source mount masks `write` and `copy`; the copy succeeds.
- `test_a_read_only_destination_is_refused_before_any_storage_call`: `read_only` at the destination; a recording double at the source and at the destination counts 0 calls each.
- `test_a_destination_that_masks_write_or_copy_is_unsupported`: two cases, each `unsupported` at the destination mount's path with 0 storage calls.
- `test_a_copy_out_of_a_trash_view_across_mounts_is_invalid`: `invalid` at the path sent, 0 storage calls.
- `test_an_occupied_destination_is_exists_with_its_version_and_hash`: `exists` at the destination, `data["version"]` and `data["content_hash"]` of the occupant, the occupant's body unchanged, no `info` record.
- `test_a_destination_holding_only_a_deleted_file_gets_a_new_file`: status `created` at version 1, and the deleted file is still listed in the trash view and restorable.
- `test_a_directory_source_is_refused_cross_mount_and_nothing_is_written`: `cross_mount` at the source with the destination as target; the destination mount's write calls count 0.
- `test_move_across_mounts_is_still_refused`: `cross_mount`, 0 storage calls.
- `test_a_refused_sizing_read_fails_its_group_and_writes_nothing`: three pairs into `/b`, one source missing; `not_found` at it; none of the three destinations exists.
- `test_a_source_the_storage_answers_with_nothing_is_not_found`: a double whose `read` returns no row and no error.
- `test_two_pairs_naming_one_destination_are_refused_up_front`: `exists` at the destination, no `data`, 0 storage calls.
- `test_a_mixed_batch_lands_its_in_mount_pairs_beside_a_refused_cross_mount_group`: the in-mount pair's file exists; the cross-mount pair's error is on the result.
- `test_a_batch_spanning_three_destination_mounts_writes_once_per_mount`: one source mount, three destination mounts, small text files, so three groups; a counting wrapper sees 1 sizing read, 1 body read and 1 write for each group, 9 calls in all.
- `test_a_group_is_paged_by_recorded_size`: `TRANSFER_PAGE_BYTES` patched to 1,000; 12 text files of 400 bytes and 3 bytes files of 400 bytes, interleaved; the calls are 1 sizing read, then per page 1 or 2 reads and 1 write, matching `byte_chunked` of the sizes; the bodies sent to each write sum to at most 1,000 bytes except a page of one file.
- `test_a_failed_page_stops_its_group_and_keeps_the_pages_before_it`: the destination wrapper refuses the second write; the rows are exactly the first page's files; no third read or write is sent; the second page's files do not exist.
- `test_a_source_written_between_its_two_reads_refuses_its_page_conflict`: a wrapper writes the source after the sizing read; `conflict` at the source with the current version in `data`, `retryable` true, and no write for that page.
- `test_what_stays_behind_on_a_copy_across_mounts`: a source with an edge, an `external_id` and a rendered bytes body; the destination has no edge, no `external_id`, and `render_status == "pending"`.
- `test_the_writer_owns_the_copy_and_the_destination_posture_labels_it`: a named caller; the destination's owner is the caller, and an anonymous `stat` there answers as the destination's posture says.
- `test_a_cancelled_copy_keeps_the_pages_it_committed`: cancelled while the second page's write waits on a gate; the first page's files exist, the third page's do not, and the caller sees the same `CancelledError` object.

The leak test, in the same file:

- `test_a_cross_mount_copy_answers_as_read_then_create_does_at_every_level`: for each of the 36 pairs of levels on the ladder `none, list, read, add, contribute, read_write`, set as the posture of the source mount and of the destination mount, a named caller's cross-mount `copy` succeeds exactly when its `read` of the source and its `write(if_absent=True)` at a fresh destination both succeed, and otherwise refuses with the kind of the first of the two that refuses; on every refusal the destination holds no file, the result has no row and no `info` record, and no body crossed (a wrapper on the destination's `write` counts 0 calls whenever the source is refused). The anonymous caller runs the same 36 and meets `unauthenticated` where a posture of `none` wants a name.

The cost pin, in a new file, `tests/base/test_copy_across_mounts_at_scale.py`, marked `slow`:

- `test_a_ten_thousand_pair_copy_across_mounts_costs_its_pages`, parametrized `sqlite-file` and `postgres`, the second marked `postgres` and built on two `server_storage` schemas: 10,000 text files of 1,000 bytes, `TRANSFER_PAGE_BYTES` patched to 1,000,000, so 10 pages. The storage calls are 1 sizing read, 10 body reads and 10 writes. Every page's body read issues the same number of statements, and every page's write the same number; the statements of the whole call equal the sum of its calls' statements, so nothing but the storages issues one; and the sizing read's statements equal those of one standalone bodiless `read` of the 10,000 sources.

Changed:

- `tests/base/test_dispatch.py::test_two_path_cross_mount_rejected` loses its `copy` case and keeps `move`; `test_two_path_batch_one_bad_pair_rejects_all` is unchanged, since its cross-mount pair is a `move`.
- `tests/lint/test_code_shape.py`: `vfs.pairs` on the rung of `vfs.listing`; `tests/lint/allowlist.py`: the baseline of `src/vfs/base.py` lowered to its new count.

When the policy seam is built, the second of the two to land adds `test_a_cross_mount_copy_is_one_step_proven_at_both_ends` to this file: one policy typed `CopyStep` is asked once for a 3-pair call with 2 cross-mount pairs; a caller with no read at a source is refused by the sizing read and the policy is asked 0 times; a caller with no right at a destination is refused by its `admits` and the policy is asked 0 times.

## Scope

In: the cross-mount branch of `_route_two_path` and the docstrings of `copy` and `_route_two_path` in `src/vfs/base.py`; `src/vfs/pairs.py`; the `cross_mount` hint in `src/vfs/results/kinds.py`; the README's Known limits bullet; the sentence in `documentation/reference/access-levels.md`; the tests above; the ladder and the baseline in `tests/lint/`.

Out:

- A cross-mount `move`: decision 1; not planned.
- A recursive copy across mounts in the kernel: decision 2.
- `cp -r` across mounts, and a shell exit for `cross_mount` in place of `invalid`: no spec of this conversion holds either. Unit 167-8, [the shell's remaining program work](../2026-11-25-the-program-forms-set-e-and-the-never-table-answer-as-gnu-and-bash-do/spec.md), written, not reviewed, not built, is narrower than its directory's name: its Scope is the literal `trav`, the hints for unavailable programs and `vfs.busy` on `rm -rf` of a mount, its decision 6 adds `busy` alone to the host's error table, and it leaves the occupied-destination forms of `cp` and `mv` to unit 167-7. So after this spec the shell's `cp -r` of a directory across mounts is still one `copy` of a directory (`crates/vfs-shell/src/programs/files.rs:588-595`), refused `cross_mount` by decision 2, which the shell prints as `Invalid argument`.
- `replace=` on `copy`: unit 167-7, [the replace spec](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md), written, not reviewed, not built; its decision 12 states the cross-mount pair.
- `request_key` on `copy`: unit 177-4, [the request-key spec](../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md), written, not reviewed, not built.
- Edges across mounts: `mkedge` stays within one mount (`src/vfs/base.py:2581-2588`).
- The vid code and the policy code: their own specs; this spec amends one row of each.

## What the docs must say

- **The `copy` docstring.** Across mounts a file is copied as a read of its source and a write at its destination, which is not atomic. Each copied pair carries an `info` record of kind `cross_mount` with the source as its target and `data["body_source"]`. An occupied destination is `exists`. A directory across mounts is refused `cross_mount`: make its directories with `mkdir`, page `tree`, and pass each page's files as `copies=`. The call reads its sources in pages of bodies, so a failure part way leaves the earlier pages written, and the rows say which.
- **The `_route_two_path` docstring.** The sentence on a pair that crosses mounts is said of `move` alone; a cross-mount `copy` pair goes to `copy_across_mounts`.
- **The `cross_mount` hint.** "Move within one mount; across mounts, copy each file and then delete it."
- **`README.md:139`.** "`move` does not cross a mount boundary; it comes back `cross_mount`. `copy` copies a file across mounts as a read and a write and says so in its result; a directory crosses as its files."
- **`documentation/reference/access-levels.md`.** Under the table: "A `copy` from one mount to another needs `read` at the source and `add` at the destination, as a copy within one mount does."

## Earlier decisions this reverses

- **The refusal of a cross-mount `copy`**, landed in `_route_two_path` (`src/vfs/base.py:2366-2369`), stated in the docstrings of `move`, `copy` and `_route_two_path`, and pinned by `tests/base/test_dispatch.py:207-216`. It stays for `move`.
- **The vid spec's decision 3, its row "A move or a copy between mounts"**, which reads "Refused `cross_mount`, as today" (`agents/2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md:166`). The copy half becomes: "the copy is another entry at version 1, with a vid of its own, in the other mount". The move half stands.
- **The policy spec's decision 11, its row for `move` and `copy`** ("The transfer's gate, with `admit_destinations`"), which assumes one storage judges both ends. A cross-mount pair is proven by decision 15 of this spec.
- **The source spec's rules 3 and 6 and its Scope**: the interim `overwrite=False`, the parity claims on a deleted destination and on what travels, and the profile that held every body of a batch in memory. Decisions 7, 9 and 10 replace them.

## Not checked

- No code of the cross-mount path was written or run. The cost figures are arithmetic; the 20 statements a page is an estimate from the write pin's families, not a count.
- The Postgres leg was not run for anything in this spec. Whether a page's read and write on Postgres each issue a fixed count is the claim the cost pin will test.
- The deletes spec was read on its branch at `d8c1d55d`, not built; the answer at a deleted destination rests on its decisions 4 and 5 as written there.
- The vid branches' code was not read; whether a `write` row there already carries the vid this spec's copy would return was not checked.
- The siblings of this conversion that this spec names, or that name it, were read as they stood on 2026-11-25: units 156-1, 167-3, 167-7, 167-8, 175-1 and 177-4. Each is written, not reviewed and not built, so every quotation of one here is of a draft.
- The bounded renderer, unit 167-3, [the renderer spec](../2026-11-25-the-verb-renderer-is-bounded-never-silent-and-marks-kind-and-rank/spec.md), was read and is not built. Its decision 7: "The note, the `more: after=` line and the errors section are never cut". Its decision 19: "an entry carrying `data` is never merged". Each `info` record of decision 13 has its own path and carries `data`, so by those two decisions a 10,000-pair copy renders 10,000 `INFO` lines under any budget (INFERRED from its text; nothing of it is built to run). Run on `dev` at `27f3d24d`, on a `Result` built by hand with `ops=("copy",)` and three such records made by `classified`: `success` is true, and the text holds three `INFO` lines, each ending with the kind's hint and `(retry: never)`. So the hint of What the docs must say is printed beside every pair that landed; whether an `info` record should print its kind's hint was not decided.
- A keyed cross-mount `copy` was not designed: Left as it is, "A request key", says what unit 177-4 holds and what neither spec decides.
- The wall-time budget of `vfs.deadline` (`src/vfs/base.py:1379`, `:2250`) was not read for whether a long cross-mount copy should take a deadline.
- How the shell prints a `cp` whose result carries `info` records was not run; by `src/vfs/shell/host.py:494-505` a successful result prints nothing more.
- `TRANSFER_PAGE_BYTES` at 8 MiB was not measured on either engine; it is the value the in-mount copy already holds.

## Choices to confirm

1. **Build after the deletes spec's second landing, or before it.** Taken: after (decision 11), since it leaves no interval in which an in-mount and a cross-mount copy disagree at a deleted name, and no test written for the revive. The other side lands first, lets a cross-mount copy revive a deleted destination until then, and rewrites that test when the deletes spec lands. Waiting is the cheaper to reverse: it can be dropped at any time.
2. **Does a `copy` mask on the destination mount refuse a cross-mount copy?** Taken: yes, `unsupported` at the mount's path (decision 3), because a mounter who masked `copy` said no copy lands there, and a later decision to ignore the mask only widens. The other side checks the `write` capability alone, since the destination storage is only written.
3. **A source that moved on between its two reads refuses its page `conflict`, or the newer state is copied.** Taken: refuse (decision 8), which keeps the memory bound and the body field true, and which a later ruling can relax without breaking a caller. The other side re-reads the row with its current body field and copies it, at the cost of a page that can exceed its budget.
4. **A refusal at the sizing read fails the whole group, or only its pair.** Taken: the whole group (decision 6), matching the in-mount ladder's whole-batch failure; the study left this to a ruling. Per pair is a relaxation a later ruling can make additively. The other side copies every readable source and reports the rest.

## One line

A `copy` pair across mounts is a bounded, paged read of the source with the caller's rights and an `if_absent` write at the destination through that mount's gate, refused for a directory, reported per pair as two operations, and `move` keeps `cross_mount`.
