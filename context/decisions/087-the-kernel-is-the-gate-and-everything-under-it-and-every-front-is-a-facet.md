# 087. The kernel is the gate and everything under it, every front is a facet, and the kernel states its promises: the atomic unit, the fault model, the trust tiers

- **Status:** proposed 2026-10-24. Clay's decisions of 2026-10-24 are
  recorded as pins; six pins carry a lean the assistant proposes and
  Clay has not confirmed, marked **(lean)** and listed under *Pending
  Clay*. Stands on two memos and fourteen studies (below). Amends ADRs
  010, 033, 074 and 080 as listed under *Amendments*. Six contract-free
  fixes the studies found landed the same day (commits `25f6da4` to
  `ba77449`); nothing else here is built. **Amended the same day by the
  eight spec authors** (specs 174–181, cut from this ADR): pins 3, 7,
  8, 10 and 14 carry their corrections, marked *(spec NNN)*, and three
  items joined *Pending Clay*.
- **Date:** 2026-10-24
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay asked the question, challenged the first
  draft's placement of search outside the kernel, and answered the
  nine questions the two memos raised; the assistant led the studies,
  ran the probes and drafted the pins)

## Context

vfs was shaped around tools for a model, then a CLI was planned over
those tools, then a WebAssembly Python guest, and more fronts will
come. Clay asked on 2026-10-23 what a refactor toward a real
filesystem would look like, with cost set aside and only growth and
performance in view. Two research passes answered.

The first,
`../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
(six studies under `research/studies/2026-10-23-filesystem-shaped-api/`),
measured what every filesystem protocol that serves more than one
front has in common. 9P, FUSE, WASI's filesystem interface and
SQLite's own VFS share nine path-keyed operations and none of them has
search, a handle in the kernel, or a seek. Every system studied that
serves several fronts over one store converged on a small kernel with
adapters above it, and vfs's closest competitor rebuilt itself that
way this year. The audit of vfs found the kernel already present in
the router and the storage seam, with four things missing: a listing
cursor, a byte range on read, write preconditions, and a replace rule
on rename. The memo's first draft put the query verbs in a layer above
the kernel. Clay challenged that, and the memo was corrected the same
day: `grep` passes the same gate as `read`, its index and its dirty
overlay live in storage, and the caller's rights are compiled into the
search statement, which nothing above the kernel could do. The query
verbs are kernel operations.

The second,
`../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
(eight studies under `research/studies/2026-10-24-ostep-principles-for-vfs/`),
laid the operating-systems textbook against vfs chapter by chapter. It
confirmed the kernel shape: a fixed table of operations, one gate every
call passes, arguments checked before anything acts, rights checked on
every access. It found promises vfs keeps and never states, and three
places vfs is quietly wrong, each shown by an executed probe:

- Twenty concurrent read-then-write appends to one file all reported
  success and one line survived. Inside one call every check sits
  inside the write statement; across two calls nothing guards the gap.
- A body changed or deleted underneath vfs with direct SQL is served
  by `read` as success. The sha256 is stored on the entry row and
  never compared. A full `reindex` reports nothing.
- A replayed `move` returns a bare `not_found`, so a client that lost
  the reply cannot tell "already moved" from "never existed". Five of
  eleven mutating verbs are safe to send twice; six are not.

It also corrected the first memo once more: the search indexes are not
written in the write transaction. The write stamps the row dirty, and
`reindex` builds the index later in its own transactions (ADR 033 §6);
`grep` stays correct by scanning the dirty side.

Clay's answers of 2026-10-24, recorded in the second memo §6: verify
the checksum on every read; store the replay key's first result as a
row in the mount with a short time to live; keep the full version
history and convert cold versions to deltas during `reindex`, keeping
ADR 017's name `pack`; expose `entry_id` as a read-only `stat` column;
land the small fixes first, with the lock-order sort keyed by path,
jitter on the retry wait, and the write-path hash offloaded above
100 KB; run the real-engine legs after the lock-order change. All of
that landed the same day.

## Options considered

- **A kernel and facets, drawn at the gate (chosen).** The kernel is
  everything that touches stored data under the one gate: the
  filesystem core, the query, history and rights operations. The
  fronts and the derived verbs sit on top. Pros: it is what the code
  already is; the query verbs keep their index and their compiled
  rights; the refactor is an extraction, not an addition. Cons: the
  kernel is richer than any file protocol, and the ADR must say why.
- **A POSIX-shaped public API.** Rejected: handles bring back the
  check-once model that a revoked right survives through; inode
  addressing breaks the path-keyed rights (ADRs 011, 021) and is the
  regret of the one peer that chose it; links break text-only `..`
  resolution and double the answer to "who may read this"; mode bits
  cannot express per-caller rights on one tree. Every studied peer
  that serves POSIX does it through an adapter with its own handle
  table.
- **A filesystem kernel with search as a program over `read`.** The
  first memo's draft. Rejected by Clay's challenge and the trace: the
  index lives in storage, the permission view is a filter inside the
  query, and a program over `read` would open every file, which is
  what vfs exists to avoid.
- **Leave the surface as it is.** Rejected: the three probes above are
  live defects, and three in-flight specs (167, 171, 172) are each
  about to add a front over a kernel whose promises are unwritten.

## Decision

1. **The kernel is the gate and everything under it.** The gate is the
   one funnel every call passes: `_gate_params`, the resolve, the
   permission layers, `_dispatch_entry` and `_call_storage`'s fixed
   table of operations ending in `assert_never`, and storage's rights
   judged inside the statement. Under it are four groups of kernel
   operations: the **filesystem core** (`stat`, `ls`, `read`, `write`,
   `mkdir`, `delete`, `move`, `copy`), the **query operations**
   (`glob`, `grep`, `glean`, `graph`, `mkedge`, `rmedge`), the
   **history operations** (`restore`, `sweep`, a future history read),
   and the **rights operations** (`grant`, `revoke`, `grants`,
   `posture`, `members`). Everything else is a facet: the fronts (the
   MCP tool, the CLI programs, the WASI mount provider, a future FUSE
   or NFS mount) and the derived verbs (`tree`, `edit`, `rmdir`),
   which are built from kernel calls and store no fact of their own.
   A facet adds only its own machinery: a flag grammar, a handle
   table, a wire, a line window, a staged buffer, the errno table.
2. **The query verbs are kernel operations, not a layer above it.**
   They pass the same gate as `read`; storage executes them against
   the index plus the dirty overlay the write transaction stamps; the
   caller's rights are a filter inside the query (ADRs 067, 072). A
   backend that declares no index is still served `grep` through the
   kernel, by a scan over what `read` returns: a slower kernel answer,
   not grep leaving the kernel. This is where vfs's kernel is
   deliberately richer than any file protocol, and it is the one thing
   no SQL-backed filesystem studied has.
3. **The filesystem core gains four arguments and keeps its batches.**
   `ls` (and `tree`, `glob`) take `after=` and `limit=` and the
   envelope carries a resumption key, the last row's full path *(spec
   176: a path, not a name, so `tree` and `glob` page on the same key)*,
   keyset on `(parent_id, name)` for `ls`, which the listing already
   orders by; `read` takes `range=(offset,
   length)` served by the dialect's substring over the body column;
   `write` takes `if_version=` and `if_absent=` (the batch form takes
   `if_versions=`, a path-to-version mapping, since an `Entry` may not
   author a version; *spec 174*), and `append=True` is a guarded form
   of `write` that maps to the `add` rung; `move` and
   `copy` take `replace=` with refuse-on-occupant as the default.
   `entries=`, `moves=` and the other plural forms stay: the plural of
   each operation over N paths is the 10,000-row ETL contract. The
   `authority` stays on every call. The names `delete` and `move` stay
   at the Python surface **(lean)**; a POSIX front spells them
   `unlink`, `rmdir` and `rename`.
4. **Not in the kernel, by evidence.** Handles (no studied Python
   kernel has a descriptor table; every FUSE, WASI and NFS adapter owns
   its own); inode-keyed addressing (`entry_id` becomes a read-only
   `stat` and `ls` column, per Clay, and no verb accepts it as an
   address: rights and routing stay keyed by path); hard and symbolic
   links (one path per entry is the grant coordinate; `..` resolves
   by text; typed edges key on `entry_id` and survive a move, which is
   what a link is for); mode bits and `chmod` (rights are per caller on
   the row and in grant rows; a FUSE front computes `st_mode` from the
   caller's rung and says so); an access time (a read never writes);
   `fsync` as a verb (every mutation commits before it returns; the
   `durability` trait says what commit means); seek (a range per call
   instead).
5. **The gate has two halves, and three trust tiers.** The router's
   half judges capability, grammar and the structural permission maps;
   storage's half judges grants inside the SQL statement. A front that
   bypassed either would bypass the gate. In process the gate is a
   convention: any caller can construct the system authority and reach
   the storage object (ADR 068, by design). On the wire and in the
   WebAssembly guest the gate is a wall: a token in and an `Authority`
   out (ADR 062), the guest's only exits the file calls and the host
   door (ADRs 082, 084). The kernel ADR says this in one place.
6. **A front's handle carries a path and an offset, never a right.** A
   descriptor is checked once at open; vfs checks on every call, cache
   hit included (ADR 084 pin 2). Every kernel call a handle makes is
   gated fresh. The consistency check sits at write time, not open
   time, because the largest client cache is a model's context window,
   which no server can invalidate: `edit`'s content match already does
   this, and `write(if_version=)` does it for whole bodies.
7. **The atomic unit, stated at the seam.** One mutation call on one
   mount commits whole or not at all, at any batch size (executed:
   10,000 rows, one commit; 10,000 good plus one bad, zero rows). A
   batch that spans two mounts is per-mount atomic only and can land
   in part; cross-mount atomicity, if ever wanted, is a designed entry
   point (ADR 001), never a router tweak. What commits with a body is
   the entry row, the path segments, the fs edge mirror, the version
   row, the body and the parent bumps, plus the dirty flag that says
   the search indexes no longer cover the row; the indexes catch up in
   `reindex`'s own transactions. vfs has two atomicity models and
   names them: **whole-batch** verbs (`write`, `edit`, `mkdir`, `move`,
   `copy`, `delete`, `restore`, `mkedge`, `rmedge`, the grant writes,
   `posture`'s own row, and `sweep` until spec 180 lands; *spec 179*)
   and **resumable** verbs that commit in bounded chunks behind a
   durable mark (`posture`'s relabel, `reindex` and its `pack` phase,
   render, embed, and `sweep` once it takes a limit). The
   storage protocol declares the unit as a trait so a backend that
   cannot keep it can say so.
8. **The fault model, written once.** The engine owns media faults and
   atomic commit; vfs owns logical faults above the engine, and
   `content_hash` on the entry row is its detector: a body written
   under the wrong id, a dropped body insert, and the out-of-band
   writer (an ETL job or migration with SQL credentials), which is
   more likely than bit rot and which only an end-to-end hash can
   catch. Engines fail partially, not fail-stop: timeouts, deadlocks,
   lost serialization races, dropped connections; the retry classes
   and the `conflict` redrive are the response. Out-of-band edits are
   outside the contract. Identities are never reused: ULIDs, skipped
   epochs, tombstones instead of frees (and a delete then a write at
   the same path revives the same `entry_id`, ADR 074; the id is fresh
   only after a sweep; *spec 181*). The engine's own error code
   travels as `data["vfs.engine_error"]`, read from the driver's
   attributes, never from the message text (ADR 076; *spec 179*). A
   rule the seam follows from here: a presence is a feature, a quality
   is a trait *(spec 179)*.
9. **Integrity: verify on every read (Clay).** `read` compares the
   served body's sha256 with `content_hash` and classifies a mismatch,
   or a missing body behind a hashed entry, as an error, never success.
   The hash stays in Python's standard library, which runs OpenSSL's
   hardware path and measured faster than the Rust `sha2` crate;
   bodies of 100 KB or more hash on a worker thread, because below
   that the thread hop costs more than the hash and above it the hash
   would hold the event loop against every other caller (executed: 32
   concurrent 1 MB writes, 13 ms inline, 2.5 ms offloaded). A
   report-only, paced `scrub` reads what nobody reads, version rows
   included, and reports; vfs has no second copy to repair from. Every
   written row returns its `content_hash` so a client can check end to
   end without a second `stat`.
10. **Replay: every mutating verb is safe to send twice or recognisable
    on the second send, or it takes a request key.** Two forms apply
    twice and cannot be made recognisable: an `edit` whose new text
    contains its old text, and the guarded append; those forms are
    key-only *(spec 177)*. A write of an identical body reports
    `unchanged` and leaves the version alone (today it bumps). A
    replayed `move` names the destination it finds occupied by the
    same `entry_id`. The replay table is a pinned contract, one row per
    verb, and the MCP tool sets `idempotentHint` where it is earned. An
    optional request key on mutating verbs is answered from the stored
    first `Result`; that row lives in the mount's schema with a short
    time to live and is swept with the trash (Clay). A disconnect
    during `COMMIT` classifies apart from one before it, as an outcome
    to verify with a `stat`, not a plain retry.
11. **History: the full history is kept; cold versions become deltas
    (Clay).** No version row is deleted by default. `pack`, ADR 017's
    name, runs as a `reindex` phase and rewrites cold version ranges
    into a snapshot plus forward diffs into the `version_diff` column
    that already exists. `sweep` takes a limit and returns a resumption
    key, the same cursor shape as `ls`, and reclaims tombstones and
    orphan bodies in slices. A garbage gauge per mount (tombstoned rows,
    version rows and bytes) is a cheap read a deployment job consults
    before it cleans. `delete` stays a tombstone (ADRs 027, 074).
12. **Rows stay the one result type.** `Entry` is the stored file,
    `Observation` the view with its populated mask, `Result` the
    verdict of a plural call (ADRs 010, 015, 034). The cursor's
    resumption key is a field of `Result` **(lean)**; a ranged-read row
    says which slice it carries; the per-row construction cost is
    addressed by the cursor first and a cheaper row type later.
13. **Concurrency rules the studies pinned.** Row locks are taken in
    path order on every write pass (landed, `25f6da4`); retry waits
    carry jitter inside a doubling step (landed, `ae27108`); fairness
    is a named axis in every arbitration decision from here; a retry
    counter per verb is the measurement ADR 025's revisit trigger
    needs.
14. **Every kernel verb has an access-path table, pinned as a test,
    counting three units.** Statements, rows and body bytes moved
    (every string and bytes value bound and fetched; *spec 179*), at
    the system actor, a named principal and anonymous, with depth as a
    dimension. Counts, never clocks. Three hidden statements the first
    such table exposed landed the same day (`4459271`, `ecc798c`,
    `99884aa`). The whole-body rewrite is the next cost to cut, and
    the engine's own chunked storage is where to look before vfs
    chunks bodies itself.
15. **Every kernel-level decision scores its options on one standing
    table of axes:** agent latency (statements and round trips for one
    small call), ETL throughput (statements and transactions for a
    10,000-entry batch), boundedness (no statement grows with N past
    the dialect budget), correctness under rivals, the atomic unit,
    dialect reach, protection (can the change widen what a caller
    sees), and overhead above the engine.
16. **Naming and grouping at the Python surface stay flat (lean).**
    `vfs.read`, `vfs.ls`, `vfs.grep` keep their names with the new
    arguments; the kernel groups are documentation and the conformance
    suite's organisation, not namespaces.
17. **When `move(replace=True)` lands on an occupant, the destination
    row's identity survives (lean).** Spec 167's direction: the
    replaced body is kept as a version of the destination's history,
    and the source row is tombstoned. The alternative, POSIX's, keeps
    the source's inode and would leave two rows claiming one
    `(parent_id, name)` under the tombstone law (ADR 074). Edges that
    pointed at the source's `entry_id` follow it into the trash and
    surface as dangling until restored or re-pointed.

## Pending Clay

- Pin 3: keep `delete` and `move` as the Python names, or rename to
  `remove` and `rename` (the first memo's Q2).
- Pin 12: the resumption key as a field of `Result`, or a separate
  return (the first memo's Q3).
- Pin 16: flat names with new arguments, or kernel groups as
  namespaces such as `vfs.query.grep` (the first memo's Q1).
- Pin 17: the destination's identity survives a replace (spec 167's
  direction), or the source's (POSIX's).
- Pin 9's threshold constant (100 KB, measured on one laptop) and
  whether an integrity failure deserves a kind of its own or rides
  `unavailable`.
- Pin 10's time to live for the replay row (spec 177 leans 24 hours),
  and whether `idempotentHint` is withheld from a tool whose verb has
  one non-idempotent form (spec 177 leans withhold).
- Spec 174 proposes that `overwrite=` leave `write`, since
  `if_absent=True` is exactly today's `overwrite=False`. A public
  argument disappears; Clay's call.
- Spec 180's hot window (`PACK_HOT_ROWS`, lean 1) and the history
  verb's name (`versions`, lean, so the shell's `history` keeps its
  meaning).

## Consequences

- The refactor is an extraction. The schema, the row types, the
  rights, the versions, the trash, the indexes and the Rust engine
  stay. What changes is the middle: the seam protocols, the router
  core's split from its tool-shaped arguments, the public surface
  regrouped by kernel group, the conformance suite reorganised by
  kernel operation.
- Nine specs follow, in the order of harm today: write preconditions
  and append (174), integrity (175), the listing cursor (176), replay
  (177), the ranged read (178), the storage seam as the kernel with
  the crash-point and access-path families (179), history with `pack`
  and the bounded `sweep` (180), the public surface regrouped (181);
  rename and copy with `replace=` fold into spec 167's existing task
  with pin 17.
- Specs 167, 171 and 172 are rebased on this ADR where it touches
  them: 167's `>>` becomes a guarded append and its `overwrite=` takes
  pin 17; 171 carries the replay table and `idempotentHint`; 172's
  close-time write-back carries `if_version=` from the open-time
  `read`, and its staged-buffer cache keys by `entry_id` or adds
  `content_hash`, because `(path, version)` repeats after a rename or
  a sweep. Spec 169b narrows to generic WebAssembly programs as the
  first memo says.
- Two promises become checkable: the atomic unit (a mixed good-and-bad
  `write` batch and a crash at each mutating statement, on every
  engine leg) and the integrity of every served body.
- The three probes stop being true: an append cannot silently lose a
  rival's line, a rotten body cannot read as success, and a lost reply
  cannot leave a client unable to tell what happened.
- Reads of large bodies pay a hash. For agent-sized files that is
  under 4%; for a 4 MB body it is as much again as the read on an
  in-process engine and less on a remote one. Pin 9 accepts that on
  Clay's word.

## Amendments

- **ADR 010** (the result envelope): `Result` gains the resumption key
  (pin 12, lean) and a ranged-read row says its slice.
- **ADR 033** §6 and its deferral: the cursor deferred to "the MCP
  pass" is now spec 176, and the wire shape it waited for exists (the
  MCP 2026-07-28 revision's handle etiquette).
- **ADR 074**: handles are named as a trash-leak seam there; pin 6
  rules that a handle lives in a front and carries no right, so no
  kernel handle can hold a tombstoned row open.
- **ADR 080** pin 3 ("no append verb; a later one maps to `add`"):
  append arrives as a guarded form of `write` (pin 3) and maps to the
  `add` rung as that pin foresaw.
- **ADR 017**: `pack` is scheduled (pin 11) as a `reindex` phase, and
  its cold ranges are the ones `reindex` chooses, not a retention cut.
- **ADR 004** pin 1: a `stat`-visible `entry_id` (pin 4) is fresh after
  delete, sweep and recreate, and the same after delete and recreate
  (the revive); the pin's wording should say so *(spec 181)*.
- **Landing note, not a decision:** specs 176, 177 and 180 each bump
  the schema format from 23; whichever lands first takes 24 and the
  others follow in order.
