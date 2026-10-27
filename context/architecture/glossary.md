# Glossary

Every term the architecture pages define, in alphabetical order. Each
entry is one or two sentences and names the page that draws the term
in context (a number in brackets). A term marked *planned* names
designed behaviour not yet in code, with the spec that lands it. The
identity terms agree with `docs/reference/glossary.md`, which is the
public reference; this list is wider because it covers the whole
system.

**ABI.** The one shape every shell program implements: `args`, `env`,
`cwd`, `stdin`, `stdout`, `stderr`, `fs`, `budget` in; `stdout`,
`stderr` and an exit code out. *Planned, spec 167.* [11]

**Access path.** The ordered list of statements one verb issues, with
the table each touches; pinned per verb as a test that counts
statements, rows and bytes. *Planned, spec 179.* [07]

**Actor.** The one principal doing the work in a call. Recorded on every
version row. Differs from the subjects when an agent works for people.
[09]

**Admitted authority.** The authority a call runs as after the router's
`_admitted` step: the explicit one, else the filesystem's default, else
anonymous. Storage always receives one. [04]

**Anonymous principal.** The principal `anon`, kind `anonymous`: what a
call runs as when nothing names an authority and there is no default.
Holds only the everyone level; owns nothing; never joins a subject set.
[09]

**Arbitration.** How two creates of the same path are settled inside
one write transaction: an upsert where the dialect has one, else catch
the unique violation and retry. A `DialectProfile` field. [07]

**Atomic unit.** The largest piece of work that commits whole or not at
all: one call on one mount. [10]

**Authority.** The frozen value every call carries: subjects, actor,
provenance, narrowing, source identity. Built only through the four
doors (`of`, `on_behalf_of`, `system`, `anonymous`). [09]

**Binding.** One mount-table row: `(path, storage, meta)`. The root's own
storage is the identity binding at `/`. [04, 05]

**Block, summary (lexical index).** The lexical index stores up to
`BLOCK_SIZE` postings per `(term, block)` row and one summary row per
term that bounds every block, so a second round can skip blocks that
cannot change the top-k. [08]

**Body.** An entry's content: text in `vfs_content` or bytes in
`vfs_blobs`, never both; `source` on the entry row says which. [06]

**Budget (shell).** A declared constant with a classified outcome:
stages per line, argv bytes, fan-out paths, stdout bytes, wall time,
fuel, verb calls, memory, staging bytes. *Planned, ADR 084.* [11]

**Busy guard.** The router's refusal of a delete, restore, sweep, move
or copy that targets a live mount point or a region holding one;
unmount first. `EBUSY`. [05]

**Candidate (grep).** An entry the gram index nominates for a pattern.
May be a false positive; never a false negative; the matcher decides.
[08]

**Capability.** An operation a backend declares in `capabilities()`.
"Which verbs." A mount's effective set is the declared set minus the
mounter's `deny_ops`. [02]

**Capability-pruned.** A fan-out skips a binding that does not declare
the verb and adds a skip error instead of failing the call. [05]

**Chunk.** One indexed unit of a body, split by tree-sitter spans for
code and markup or by the recursive splitter; entry-scoped, keyed
`(entry_id, chunk_index)`. The unit the lexical index and the embedding
describe. [06, 08]

**cli.** The meta-verb that takes a command string or argv and runs it
through the shell; the one programmatic execution door. Refuses the
system actor. *Planned, spec 167.* [11]

**Conflict redrive.** On a guard miss a verb classifies `conflict` and
runs again from a fresh snapshot, within a retry budget with jittered
waits (ADR 025). [07, 10]

**Derive.** The kernel serves an operation a backend lacks from simpler
calls the backend has: `tree` from `ls`, `copy` from `read` plus
`write`. Correct, slower. *Planned, spec 179.* [02]

**Derived verb.** A verb built from kernel calls that stores no fact of
its own: `tree`, `edit`, `rmdir`. [02]

**DialectProfile.** The per-engine policy record in `dialects.py` for
decisions SQLAlchemy takes no position on: the `IN`-list cap,
arbitration mode, isolation pins, lock hints, membership form, the
vector distance function. Unknown engines resolve to the generic floor.
[01, 07]

**Dirty flag.** `chunked`, `encoded`, `indexable` on the entry row:
whether the chunks, the gram and lexical postings, and gram eligibility
reflect the current body. A write clears them; `reindex` sets them. [06]

**Dispatch class.** How a verb is routed and gated: `MUTATING_OPS`,
`TWO_PATH_OPS`, `READ_OPS`, `EXEC_OPS`, `GRANT_OPS` in `ops.py`
(`DEVELOPER_OPS` is a plane marker beside them, not a class). A
different axis from the kernel group. [02]

**Domain model.** A pydantic value never bound to a database session:
`Entry`, `Observation`, `Chunk`, `Version`, `Edge`. [03]

**Door.** One of the four class methods that construct an `Authority`.
The bare constructor is not a door. [09]

**Edge.** A typed relation between two entries, keyed `(source_id,
target_id, edge_type)`, in `vfs_edges`. Caller-authored by `mkedge`,
minted as `links` from markdown references, or the reserved `fs`
mirror of the hierarchy. [06, 08]

**Embedding provider.** The seam `reindex` fills `chunks.embedding`
through: `model_id`, `dimension`, request caps, embed one batch.
Storage owns budgets and the loop. Providers: hashing floor, model2vec,
OpenAI, LangChain. [08]

**encoded.** The entry flag meaning "this row's postings are in the
current epoch". False means `grep` scans the row. [08]

**Entry.** The stored record of one file or directory; the durable
shape. A pure pydantic value. [06]

**entry_id.** The 26-character ULID on every entry row: the permanent
logical identity and the referential key every dependent table uses.
Minted once, never reused, kept across a move. *Planned:* exposed
read-only on `stat` (spec 181). [06]

**Entry-scoped metadata.** Chunks, versions, edges: rows that belong to
a file and are addressed by file plus discriminator, never by a path.
[06]

**Epoch.** One built generation of the gram and lexical indexes. Built
invisible under a fresh number, published by one pointer flip in
`vfs_meta`, reclaimed when dead. [06, 08]

**Everyone level.** `everyone_level` on the entry row: the rank of the
deepest covering posture row. Derived, stamped at mint, rewritten by a
relabel. Lets a partial caller's read be one index seek. [06, 09]

**Execution policy.** The gate order (capability, grammar, permission),
fired on every verb a command resolves to. Executing a stored program is
`read` on its entry. No `ask` inside vfs. *Planned, ADR 084.* [11]

**Facet.** Anything built on top of kernel calls that stores no fact of
its own: a front or a derived verb (ADR 087). [02]

**Fail-partial.** How engines fail in practice: timeouts, deadlocks,
lost serialization races, dropped connections, not a clean stop. The
retry classes and the conflict redrive are the response. [10]

**Fan-out.** Dispatching one scoped verb (`glob`, `grep`, `glean`) to
every binding its scope reaches, in parallel, and merging the answers.
[05]

**Fault model.** Which layer catches which fault: the engine owns media
faults and atomic commit; vfs owns logical faults and partial failures
above it, with `content_hash` as the detector (ADR 087 pin 8). [10]

**Feature.** An argument family or an index a backend serves itself,
declared in `features()`. "Which arguments." *Planned, spec 179.* [02]

**Filesystem capability (`fs`).** The vfs verb set curried with the
caller's `Authority`, handed to a shell program. No authority
parameter, no grant verbs, absolute paths only. *Planned, ADR 082.* [11]

**Five blocks.** MCP's content block types, the only wire format: text,
image, audio, resource link, embedded resource. *Planned, ADR 085.* [11]

**Forms.** A shell program's declared option grammar and the subset this
kind implements. *Planned, ADR 082.* [11]

**Front.** A way into vfs built on top of the kernel: the Python API and
`Session` (built); the MCP server, the shell, the WASI mount
(planned). Adds its own machinery, stores no fact. [01, 02]

**Frontier walk.** `graph`'s algorithm: the application holds the
frontier and the visited set; each hop is one chunked statement; every
row is judged against the caller's view. [08]

**fs mirror edge.** One reserved-type `fs` edge row per non-root entry,
parent to child, maintained in the write transaction. `parent_id` is
authoritative; the mirror serves the graph verb. [07]

**Funnel.** `_dispatch_entry` and `_call_storage` in `base.py`: the one
seam from op to storage and one seam back. [04]

**Fusion, Ranker.** How a mount combines `glean`'s legs: a `Convex`
weighting declared on the `Ranker` at construction, never per call.
[08]

**Garbage, gauge.** Tombstoned rows, version rows and bytes per mount;
a cheap read a deployment job consults before it cleans. *Planned,
spec 180.* [10]

**Gate.** The one funnel every call passes, with two halves. The
router's half: parameters, routing, capability, reserved grammar,
structural permission maps. Storage's half: the caller's grants judged
inside each SQL statement. [01, 04]

**Generic floor.** The conservative `DialectProfile` an unknown SQL
engine resolves to. Serves the core verbs; withholds `glean` and
`graph`, which need a cosine distance function (ADR 059). [01]

**Gram, trigram.** Three consecutive bytes of a folded body, packed into
24 bits. The key of the gram index behind `grep`. [08]

**Grant.** A row: a principal holds a rung at and below a path prefix.
Additive; there are no deny rows. Written by `grant`, removed by
`revoke`, listed by `grants`. [09]

**Grant revision.** `vfs_meta.grant_revision`: advanced as the first
statement of every grants write so rival admin writes serialise. Stamps
version rows and grant rows. [09]

**Group.** A principal id starting with `group:`. A member holds every
grant its groups hold, nested up to eight levels. Membership is written
by the system actor. [09]

**Guarded update, guarded claim.** An `UPDATE` whose `WHERE` proves the
row still has the entry id, version and path the plan read (a claim
proves the judged version). A rowcount miss means a rival moved first.
[07, 10]

**Hidden row.** A row the caller holds no rung on. Answers `not_found`
exactly as a missing path does; never counted in search statistics.
[09]

**Identity binding.** The root binding at `/`: the node's own storage and
the fallback for every path no deeper binding claims. [05]

**Index (shell).** The ordered list of directories whose entries feed
`/.vfs/bin`; default `/opt/bin`. *Planned, ADR 082.* [11]

**Intersection law.** A subject set holds a right only when every member
does; the set's coverage is the meet of the members' coverage (ADR 066).
[09]

**Kernel.** The gate and everything under it: the router's funnel, the
kernel operations, the storage seam, storage and the Rust engine
(ADR 087). [01, 02]

**Kernel group.** One of four kinds of kernel operation: filesystem core
(`stat`, `ls`, `read`, `write`, `mkdir`, `delete`, `move`, `copy`),
query (`glob`, `grep`, `glean`, `graph`, `mkedge`, `rmedge`), history
(`restore`, `sweep`), rights (`grant`, `revoke`, `grants`, `posture`,
`add_member`, `remove_member`). Spec 181's `OpGroup` adds a fifth
value, `derived`, for `tree` and `edit`. [02]

**Ladder, rung.** The total order `none < list < read < add <
contribute < read_write`. `list` names a row; `read` shows it whole;
`add` creates beneath and alters only one's own; `contribute` also
edits anyone's but trashes only one's own; `read_write` does everything.
Every verb's rung is one row in `VERB_RUNGS` (ADR 080). [09]

**Lease (reindex).** `vfs_meta.reindex_holder` plus a heartbeat: one
`reindex` per mount at a time; a rival refuses `conflict`. [08]

**Leg.** One ranked source inside `glean`: the lexical leg or the vector
leg, each aggregated to entries and normalised to the unit interval.
[08]

**Lexical index, BM25.** The ranked text index: per-term blocks of
postings with term frequencies and lengths, plus summary rows that
bound every block; built under the gram epoch; scored in the Rust
engine. [08]

**links edge.** An edge minted from a markdown reference in a body,
resolved against the live tree during the chunk pass. [08]

**Longest-prefix resolution.** Finding the deepest binding whose path
prefixes the caller's path. Every path resolves to exactly one backend.
[05]

**Matcher.** `ContentMatcher`, the Rust `verify` kernel's class: the one
definition of a grep match for every surface (`count_lines`,
`hit_lines`). [08]

**Membership budget.** The tighter of the dialect's parameter budget and
its `IN`-list cap; every `IN (...)` chunks to it, so no statement grows
with batch size. [07]

**Mount.** One storage backend bound at one path in the namespace. [01,
05]

**Mount coordinates.** Paths as a storage sees them, relative to its
binding. Router (namespace) coordinates are paths as the caller sees
them. [05]

**Mount point.** A directory row stored in the parent's storage at which
a binding attaches another storage. [05]

**Mount protocol, tool protocol.** wasi-python's two embedder seams:
serve the guest's whole filesystem; let guest code call host functions.
*Planned use, spec 172.* [11]

**Mount table.** The router's sorted map from path to `Binding`. [05]

**Namespace.** The one rooted tree. Everything first-class is addressable
in it by an absolute canonical path. [05]

**Narrowing.** What a session has voluntarily given up, on top of what
grants deny. Today one value, `NONE`. A session can narrow and never
widen (ADR 063). *Further values planned, spec 148.* [09]

**Needs.** A verb's rungs: on its target (`primary`), on a fresh name it
mints (`create`), on a row it only passes or reads (`traverse`). [09]

**Observation.** One row an operation returned about an entry at the
moment it returned, with a `populated` mask. The one result row type
for every verb. [06]

**Offload.** Running CPU-bound work on a worker thread so the event loop
keeps serving other callers: grep's verify stage, reindex's chunk and
posting stages, renderers, large-body hashing. [03]

**Overlay, scan side.** The dirty rows `grep` reads directly because the
index does not cover them. Always correct, slower. [08]

**Owner floor.** A principal named in `owner_id` can always read and
write that row regardless of grants. [09]

**Ownership.** The `owner_id` column, set once at creation from the
authority. One subject owns what it makes; a set, the system actor
without a declaration, and anonymous own nothing. [09]

**Pack.** A `reindex` phase that rewrites cold version ranges into a
snapshot plus forward deltas. ADR 017's name. *Planned, spec 180.* [10]

**Parameter budget.** `dialect.insertmanyvalues_max_parameters`: the
bind-parameter cap SQLAlchemy models; bulk inserts chunk to it. [07]

**Parent bump.** Ticking each touched parent's version in a write, with
a guard proving the parent still lives at its path. [07]

**parent_id.** The one structural pointer: the parent's `entry_id`.
Authoritative for the hierarchy. [06]

**Path.** The `Path` type in `paths.py`: normalised, validated, at most
1,024 bytes, segments at most 255 bytes. [05]

**Path segments.** One posting row per ancestor directory name of an
entry, mirroring the `path` column at every commit, so `glob` can push
literal directory components into SQL. [07]

**Permission layer, PermissionMap.** The router's structural layer per
binding: a default of `read` or `read_write` plus prefix overrides,
built by the `read_only()` and `read_write()` factories. Composes
downward and only tightens. Not per caller. [04, 09]

**Persistence model.** The hand-written tables in `models/rows.py`, held
in step with the domain models by a drift test. [03]

**Pipe, chunk (shell).** One ordered stream per seam; each chunk is
`Rows` (a frozen `Result` slice) or `Bytes` (a buffer with a mime),
never both. *Planned, ADR 083.* [11]

**Placeholder.** The one-line stand-in a binary row prints at a text
boundary: `[binary <path> <mime> <size>B v<version>]`. *Planned,
ADR 085.* [11]

**Plan then execute.** The write family's discipline: fetch committed
state once, adjudicate the whole batch in memory, execute only an
error-free plan. [07]

**Populated mask.** The set of field names a call fetched on an
`Observation`. A null outside the mask means "not fetched"; inside it,
"fetched and null". [06]

**Posting list.** One gram's sorted list of entry ids, stored as a varint
count plus LEB128 deltas; decoded only in the Rust engine. [08]

**Posture.** The everyone level at and below a prefix, stored as a grant
row for the reserved principal `*`. Deepest covering posture wins.
Default `read_write`. Named by the rung: `none`, `list`, `read`, `add`,
`contribute`, `read_write`. [06, 09]

**Preview.** The query-biased excerpt cut from a `glean` hit's chunk
text, bounded by construction, no second fetch. [08]

**Principal.** One verified identity: `sub` (the token's subject claim),
a kind (`user`, `service`, `system`, `anonymous`), scopes. [09]

**Program.** Anything callable by name from the shell: one ABI, six kinds
(verb builtin, text program, program, tool, MCP tool, skill).
*Planned, ADR 082.* [11]

**Provenance.** How an authority was proven: `edge` (a verified token at
the transport boundary), `constructed` (trusted code in process),
`system`. Recorded on every version row. [09]

**Rebase.** Translating paths and errors between mount coordinates and
router coordinates: `with_mount` and `without_mount` on `Result`. [04]

**Redrive.** See *conflict redrive*. [10]

**reindex.** The one maintenance verb: renderings, chunks, links, gram
and lexical epochs, segments, edges, signals, embeddings; each phase in
its own transaction under a lease. [08]

**Relabel.** The resumable pass that rewrites `everyone_level` under a
prefix after a posture change, in bounded chunks behind a cursor in
`vfs_relabels`. [09]

**Render cap.** 32,768 characters at the `cli` display and the MCP
adapter; a pipe is never capped. *Planned, ADR 085.* [11]

**Rendering.** The text derived from a bytes body by a per-format
renderer (pdf, docx, pptx, xlsx), stored in the content row and
stamped on the entry with the bytes hash and the renderer's generation.
[06]

**Replay, request key.** Every mutating verb is safe to send twice or
recognisable on the second send; the two forms that cannot be take a
key answered from the stored first `Result`. *Planned, spec 177.* [10]

**Rerank.** The cross-mount merge of `glean` answers: one BM25 over the
union, each mount contributing a prefix of its own list; a mount's own
order is never changed. [05]

**Reserved scope.** `/.vfs`: the system's own tree, served as views,
never written by a caller. [05]

**Result.** The envelope every verb returns: `ops`, `observations`,
`errors`, extras. `success` is derived from the errors, never stored.
Supports set algebra, sort, top, filter, rebase, wire payloads. [06]

**ResultError.** One classified error fact: a kind from the closed
vocabulary, a message composed from the kind's phrase, a severity, a
path. No producer writes prose (ADR 076). [06]

**Resumable.** The atomicity model where a call commits in bounded
chunks behind a durable mark and the next call finishes the work:
relabel, render, embed, `pack`, bounded `sweep`. [10]

**Revive.** A write at a tombstoned path: the same `entry_id` comes back
live and the old body is kept as a version. [10]

**Rights.** The compiled result for one caller at one rung: level,
spans, owner arms, roots, holes. Pure, in `storage/grants.py`. [09]

**RightsCache.** The per-mount cache of compiles, keyed on the greatest
`principal_revisions` stamp over the caller's subjects and groups plus
the relabel marks in flight. A grant write retires its grantee's
compile. [09]

**Road directory.** A hidden directory with a visible row beneath it:
listed as a bare name; refuses every write beneath it. [09]

**Router.** `VirtualFileSystem` in `base.py`: the mount table, the gate,
the funnel, fan-out. One router is one namespace and one policy layer.
[03]

**Rust engine, Rust kernel.** The compiled crate `crates/vfs-core`,
built into the wheel as `vfs._native` (required, ADR 057). Exported
kernels: `distinct_gram_count`, `PostingsBuilder`, `candidate_ids`,
`ContentMatcher`, `chunk_spans`, `markdown_refs`, `tokenize`,
`LexicalBuilder`, `lexical_score`, `decode_summary`, `select_blocks`,
`vector_topk`, `centrality_prior`; `cosine_topk` and `Chunk.split_batch`
are Python wrappers over `vector_topk` and `chunk_spans`. [01, 08]

**Schema format.** The integer in `vfs_meta.schema_format_version`,
bumped on every schema change; a mount at an old format is refused at
first touch, never migrated silently (ADR 020). 23 today. [06]

**Scrub.** A paced, report-only read of everything, version rows
included, comparing bodies to their hashes. *Planned, spec 175.* [10]

**Seam.** A declared boundary with a protocol on one side and replaceable
implementations on the other: the storage seam, the embedding seam, the
renderer seam, the native seam. Also, in tests, a named point where a
rival writer is staged (`seams.py`). [03]

**Serialization point.** The one row of `vfs_lock`, locked by a
serialized verb's first statement. Nothing else reads it. [06, 10]

**Serialized verb.** `move`, `copy`, `delete`, `restore`, `sweep`: a verb
that rewrites or hides parts of the tree other rows depend on, so it
takes the serialization point first and never interleaves with another.
[10]

**Session.** A facade holding one authority and one filesystem. Every
verb on it is the filesystem verb with the authority filled in. Closed
is final. [03]

**Shadow filter.** Dropping rows that a deeper binding owns, so a
listing never shows the parent storage's stale row under a mount point.
[04]

**Signal, prior.** A query-independent importance score per entry in
`[0, 1]`, computed during `reindex` from the reference graph and the
tree (centrality, smoothed), stored under a generation, read on the
query path. [08]

**Snapshot, delta (versions).** A version row holding the whole body,
or (planned, spec 180) a forward diff from the previous one. [10]

**Source identity.** The raw edge identity behind an authority (an
issuer and subject pair), set once at the edge, stored on version rows,
never interpreted. [09]

**Storage seam.** The protocol in `storage/protocol.py` the router's
funnel calls: the `Supports*` families and `StorageBackend`. [01, 02]

**Sub.** A principal's name: the JWT and OpenID Connect claim for
"subject", kept unchanged from the token into every column that names
a principal. [09]

**Subjects.** The set of principals whose permissions apply to a call.
Non-empty except under the system actor; at most 64. [09]

**Sweep.** The one destroying verb: tombstoned rows, their bodies,
versions, chunks and edges. Developer plane. *Planned:* a limit and a
resumption key (spec 180). [10]

**System actor.** `Authority.system()`: no subjects, bypasses grants,
stamps whatever owner a payload declares. Mount administration runs as
it. Refused on the wire. [09]

**Text kernel.** A shell program whose core is bytes-to-bytes Rust in
`vfs-core` with a thin Python layer for operands: `sed`, `awk`, `cut`,
`sort`, `wc`, `diff`. *Planned, spec 168.* [11]

**Three-seek predicate.** The visibility clause storage compiles into a
read: the everyone level on the row, the caller's grant ranges joined
to the path index, the rows the caller owns; three index seeks merged
by `UNION ALL`. The statement text never changes with the number of
grants (ADRs 067, 072). [04, 09]

**Tombstone.** `deleted_at` and `trash_root_id` set on a row in place.
A delete sets it; a restore clears it; the row keeps its path (ADR 074).
[06, 10]

**Trait.** A quality of how a backend serves, from `traits()`: today
the grep tier, the glean staleness, the arbitration mode; a durability
tier is planned (spec 179). "How." [02]

**Trash root.** The row a delete named; every row in its subtree carries
its id, so `restore` clears a root's set in one statement. [10]

**Trash view.** `/.vfs/trash/<path>`: the tombstoned row at `<path>`,
per mount. The one `/.vfs` view built today. [05]

**Trust tier.** Where the gate is a wall and where it is a convention:
in process (a convention, open by default), on the wire (a wall: a
token in, an `Authority` out), in the guest (a wall: file calls and the
host door only). ADR 087 pin 5. [04]

**Unauthenticated.** The mount-side refusal of an anonymous call at a
path whose posture is below the verb's rung. The hint names the fix.
[09]

**Verb builtin.** A shell program written as shell code over vfs verbs.
*Planned, spec 167.* [11]

**Verb door.** The host function behind wasi-python's `host::call` that
carries vfs verb calls as `Result` wire frames. *Planned, spec 172.*
[11]

**Version.** A file's per-entry revision counter, bumped on every
material change; also the number on a version row. [10]

**Version mint.** Writing the replaced body as a version row with the
replacing authority's attribution. Creates mint nothing; identical
bodies mint nothing. [07]

**Version row.** The replaced body kept whole, with actor, subjects,
provenance, source identity and grant revision. [06, 10]

**View.** A `/.vfs` head the router serves from a table of its own,
checked before the mount table: `bin`, `skills`, `run`, `tools`, `mcp`.
*Planned, specs 169 and 170.* [05, 11]

**Visibility.** Storage's compile of what one read call may see at the
verb's rung: which rows the caller may name, which it may read whole.
[04, 09]

**Whole-batch.** The atomicity model where the whole call on one mount
is one transaction: the write family, the topology verbs, the trash
verbs, the edge verbs, the grant writes. [07, 10]

**WriteGate.** Storage's point check before a mutation's first write
statement: the caller's rung on every target and ancestor, decided once
per batch; any refusal fails the batch whole. [04, 09]

**WritePlan, StagedEntry.** The in-memory write plan and one path's
planned final state, carrying the persistence bookkeeping an `Entry`
never holds. [07]

## Deliberately not in vfs

Each with the recorded reason (ADR 087 pin 4; the OSTEP memo §3).

| Not in vfs | Reason |
|---|---|
| File descriptors, an open-file table, `seek`, `close` | Per-process state; a descriptor is checked once and vfs checks every call; fronts own their own handle tables. |
| `fsync` as a verb | Every verb commits before it returns; durability is a trait. |
| Hard links, symlinks, a link count | One path per entry is the grant coordinate; `..` resolves by text; edges key on `entry_id` and survive moves. |
| Mode bits, `chmod` | Rights are per caller on the row and in grant rows; a FUSE front computes `st_mode` from the caller's rung. |
| An access time | A read never writes. |
| Inode-keyed addressing | `entry_id` is read-only on `stat`; rights and routing stay keyed by path. |
| A journal of vfs's own | The engine's log does this; identities are never reused. |
| Server-pushed invalidation | A model cannot be called back; validate at write time (`edit`'s match, `if_version=`). |
| Cross-mount transactions | Per-mount atomicity is the ceiling; a designed entry point if ever wanted. |
| An `ask` or policy language inside vfs | vfs allows or classifies; a host adds its own human-in-the-loop layer. |
