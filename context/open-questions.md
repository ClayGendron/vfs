# Open Questions

**Status:** live — first populated 2026-07-16 (from the specs/STATUS.md picture)
**Purpose:** A single list of unknowns, undecided calls, and parked ideas. Anything tagged `[NEEDS CLARIFICATION]` anywhere in `/context` should have a pointer here.

## Format

```

## <short title>
- **Asked:** YYYY-MM-DD by <who>
- **Context:** 1-2 sentences of what prompted the question
- **Blocking:** list of specs/plans/decisions that are waiting on this
- **Options considered:** bullet list
- **Status:** open | parked | resolved (→ link to decision or story that closed it)
```

## Lifecycle

- **open** — actively unresolved; blocks work
- **parked** — deliberately deferred; not blocking but not forgotten
- **resolved** — closed by a decision or story; the entry moves to
  `open-questions-archive.md` (split 2026-08-14) as the permanent
  record, keeping this file live-only

---

## MySQL-family batch UPDATEs are per-row driver round trips

- **Asked:** 2026-07-23 (multi-agent review of the spec 079 landing; scale lens, CONFIRMED 3/3)
- **Context:** pymysql/aiomysql `executemany` batches only INSERT/REPLACE (`RE_INSERT_VALUES`) and loops per-row for UPDATE, so on mysql/mariadb the guarded aggregate arm and the unguarded absorb executemany each cost one driver round trip per row — a 10k overwrite batch is ~10k sequential UPDATEs inside one REPEATABLE READ transaction. Results stay correct and statements stay bounded; the cost defeats plan.md's "one executemany regardless of N" and widens the 1205/1213 lock window. Postgres/mssql (VALUES-join arm) and oracledb (real array DML) are unaffected.
- **Blocking:** nothing lands broken; a fix is a capability-ladder change (a set-based join-UPDATE for the mysql family, verified by aggregate rowcount == N, no RETURNING needed).
- **Preconditions to verify before designing:** (1) rowcount semantics — SQLAlchemy's mysql dialect defaults to `found_rows` (rows *matched*); the guard always bumps `version`, so matched == changed today, but the fix must not silently depend on that; (2) validate on the real mysql/mariadb legs via the db_test cycle.
- **Options considered:** multi-table UPDATE with a derived-table join (mysql-native); leave as-is and document the cost; raise the driver's executemany capability upstream.
- **Status:** open — owned by `specs/active/080-mysql-batch-update-statements/` (research questions and acceptance criteria live there); do not fix inline
- **Researched 2026-08-25:** `research/2026-08-25-mysql-family-batch-update-shapes.md` — FOUND_ROWS pinned as the semantic SQLAlchemy always sets (raw driver 0, SQLAlchemy 1, measured), the UNION ALL derived-table multi-table UPDATE as the family's one join shape (10k rows: 4.05 s → 1.07 s MySQL, 4.72 s → 1.16 s MariaDB, one statement per 10,900 rows), savepoint-and-redrive attribution proven on both members, MariaDB leg green at parity; design waits on Clay's review

## Row-level grant semantics (spec 058's clarification forks)

- **Asked:** 2026-07-10 (spec 058 seeded with `[NEEDS CLARIFICATION]` forks — nine in the spec as it stands; this entry long said eleven)
- **Context:** Row-level permission grants need a verified `Principal` before enforcement semantics can be pinned; the forks cover grant shape, inheritance, and query-construction enforcement.
- **Blocking:** `specs/active/058-row-level-permission-grants/`
- **Coupled to:** the parked full-dirent question below. 058 attaches grants to **path prefixes** and computes coverage from the path string; ADR 018's parked end-state gives one entry many paths via hard links, which makes prefix coverage ambiguous and dissolves `Entry.path` as sole domain identity — the classic POSIX hard-link permission problem. Ratifying a prefix-attached grant model entrenches against that end-state; unparking it forces 058 to re-derive around ids.
- **Also lands here:** the *per-principal* half of the execute-policy question below — an `execute` level in this grant ladder, not a reopening of 039.
- **Stale premise:** 058's depends-on line cites `src/vfs/models.py` / `VFSEntry`, neither of which survived spec 076's model split (now `src/vfs/models/entry.py`, `Entry`), and its "identity threaded as `user_id` through `_call_storage`" language is superseded by spec 070. True these up before the full spec is written.
- **Options considered:** see the forks inline in 058's spec
- **Status:** resolved 2026-09-06 — every fork is decided by ADR 062 to 067 (ratified) and written into spec 058's full text; the prefix-coordinate cost against the parked full-dirent end-state is accepted with ADR 021/067. The last marker, 058 §8 (group administration), closed 2026-09-28 by ADR 071 rule 8: the system actor only in this landing; a per-group admin flag is a follow-up.

## serve() topology-lock policy premise

- **Asked:** 2026-07-10 (flagged in the STATUS true-up)
- **Context:** Spec 054 decides that `serve()` locks mount topology, but its `allow_child_mounts` premise went stale after 056/068 reshaped mount admin. **Verified 2026-07-22:** `allow_child_mounts` has zero occurrences in live `src/` — the spec's mechanism language is not merely stale but unimplementable as written, and should be deleted rather than re-derived.
- **Blocking:** `specs/archive/054-mcp-serve-locks-topology/` — cancelled 2026-09-05 (rule holds by construction); the serve spec, when written, carries the one-line rule
- **Options considered:** re-derive the policy against the post-068 mount admin surface, or fold it into the MCP serve spec when that work starts
- **Status:** parked

## Per-path / per-principal execute policy

- **Asked:** 2026-07-11 (068 landing superseded spec 039's mechanism)
- **Context:** `run` stays outside the permission-map vocabulary; denied execution classifies `unsupported`. 068's `deny_ops` covers the mount-level need.
- **Blocking:** nothing today
- **The two halves have different owners** — route incoming demand accordingly: **per-path** execute (uniform across principals) reopens `specs/active/039-execute-permission-tier/`, whose rights-set is already drafted and whose implicit-grant fork is signed off, so nothing needs re-deciding first. **Per-principal** execute is a grant-ladder extension in spec 058 (an `execute` level beyond `read_write`), not a 039 question. Treating them as one thing sends the demand to the wrong spec.
- **Options considered:** permission-map tier (039's original shape) vs. mount-level `deny_ops` (landed)
- **Status:** parked — unblocked only by a real consumer asking for "runnable except these paths" (→ 039) or "runnable by these principals" (→ 058)

## Full dirent model: name-on-edge, parent_id dropped, hard links?

- **Asked:** 2026-07-19 by Clay + Claude (edge-authoring session, while deciding ADR 018)
- **Context:** ADR 018 materializes fs edges but keeps `parent_id` as the write-side arbiter because `UNIQUE(parent_id, name)` is portable where a shared-edges-table unique constraint is not (SQL Server single-NULL, Oracle composite-NULL, no clean GENERIC floor). The POSIX-pure end-state — names live on the edge (juicefs `edge(parent, name, inode, type)`), entries hold no parent, hard links become possible — would make the edges table the sole hierarchy store.
- **Blocking:** nothing — ADR 018 works without it; revisiting means rethinking `Entry.path` as sole domain identity and per-dialect unique strategies
- **Coupled to:** the row-level grant question above — 058's path-prefix grants assume one path per entry, which hard links break. Every year of path-attached features raises the cost of unparking this, so the two must be decided with each other in view.
- **Why juicefs's shape does not port directly:** its dirent table is portable precisely because it is *dedicated* — `edge{Parent, Name}` are both NOT NULL in a table nothing else shares (`juicefs/pkg/meta/sql.go:65-71`), so the shared-table NULL-semantics problem never arises. That is ADR 018's rejected option two, and it resurrects the two-table traversal the one-query-one-table requirement forecloses.
- **Options considered:** keep ADR 018's mirror (landed); full dirent model via a dedicated fs-edge/dirent table (resurrects two-table traversal); name-on-edge in the shared table with per-dialect functional/filtered unique indexes
- **Status:** parked — unlocked only by a ratified requirement for hard links, or for rename of giant subtrees where path-cache regeneration dominates, or by dropping the one-table traversal requirement. Unparking means a full research → ADR cycle, not an amendment.

## Hermetic-runtime guest bet: Monty, CPython-on-WASI, or both behind one capability contract

- **Asked:** 2026-07-24 by Clay + Claude (hermetic-runtime research memo §7)
- **Context:** The CLI-as-hermetic-runtime direction needs a sandboxed guest interpreter for agent-written code. Monty (pydantic, 0.0.19) is purpose-built — dict-based host functions, async coroutine externals, pause/resume snapshots — but self-labeled experimental with a real language subset (no inheritance, no generators, nine-module stdlib) and no security audit. CPython-on-WASI under wasmtime is the full language behind the same capability idea, at higher startup/memory cost. The research memo's mitigation: define the guest-visible capability contract once and treat the interpreter as swappable.
- **Blocking:** the Monty phase of the runtime work — not the wasm-CLI spike, which needs no guest interpreter
- **Options considered:** Monty first, WASI-CPython later behind the same contract (memo's lean); both from day one; wasm-only until Monty matures
- **Status:** open — decide when the code-execution phase is specced; the wasm spike proceeds regardless

## Shell pipe payload: Result envelopes with a canonical wire serialization, or bytes at v1?

- **Asked:** 2026-07-24 by Clay + Claude (hermetic-runtime research memo §2, from nushell's documented wart)
- **Context:** nushell pipes structured values but serializes structured→external-stdin via its *human table renderer* (run_external.rs:502-518) — the display format became the wire format and cannot be fixed post-ship. If vfs shell pipes carry Result envelopes, the structured→wasm-stdin boundary needs a canonical serialization declared before the first shell ships (JSON lines is the obvious candidate — it is what jq eats); the alternative is bytes-only pipes at v1 with structure layered later.
- **Blocking:** the shell-surface ADR; the wasm spike only touches it at the stdin boundary and can hardcode JSON lines without prejudice
- **Options considered:** envelopes in the pipe + declared JSON-lines wire format at the external boundary (memo's lean); bytes-only v1; per-command negotiated formats (rejected on its face — nushell's warts show format decisions must be global)
- **Status:** open

## Result content must be typed blocks (text/image/audio) for the MCP wire — where does the content channel live?

- **Asked:** 2026-07-25 by Clay (surfaced while designing image handling for opendocs; the same physics applies to the vfs hermetic shell)
- **Context:** Models only "see" media delivered as typed content blocks (MCP `content` arrays / Messages API image blocks) — base64 in a text stream is invisible noise. The `Result` envelope carries only rows and errors, so a `read` of a PNG has no representable output a model can see. The hermetic-shell direction stands but its output has two consumers with different physics: stdout (text-only forever — media renders as a placeholder) and MCP tool results (ordered, interleaved text+image+audio blocks the model actually sees). `Result` needs a typed content channel that chains under the algebra and projects onto MCP block shapes.
- **Blocking:** the shell-surface ADR (its output contract), any verb that returns media, the `run` verb's story for program-generated media (matplotlib PNGs etc.)
- **Options considered (unstudied):** `content: list[ContentBlock]` on `Result`; media as a species of `Observation` row keyed by path; projection-time-only (renderer fetches payloads); see the brief for the full question list
- **Status:** open — research memo drafted 2026-07-25
  (`research/2026-07-25-multimodal-result-content.md`, superseding the brief;
  eleven prior-art studies under `research/studies/2026-07-25-multimodal/`);
  awaiting review, feeds the content-channel ADR. Hard prerequisite surfaced:
  the live tree has no binary channel at all (`Entry.content` is `str`-only,
  null-byte-rejecting) — the storage bytes story must be settled first.

## Multimodal storage and search — how do media bytes live in the database, and what do the four search verbs mean over them?

- **Asked:** 2026-07-25 by Clay (the storage prerequisite surfaced by the
  result-content memo, widened to the search half: multimodal embeddings and
  what `glob`/`grep`/`glean`/`graph` become over media)
- **Context:** No binary channel exists in the live tree; the hypothesis is a
  binary sidecar beside the text `content` table — extending the existing
  bodies-leave-the-narrow-row segmentation — rather than widening text
  columns to bytes. Search must not be foreclosed by storage: derived-text
  sidecars (OCR/transcripts/captions) make media greppable; multimodal
  embedding spaces make `glean` see pixels; `graph` edges to media should be
  free; all of it must survive 10,000-file batches on the least generous
  engine and ride trash → restore → sweep.
- **Blocking:** the storage-bytes ADR, which gates the content-channel ADR;
  any verb that stores or searches media
- **Options considered (unstudied):** entry-keyed blob rows vs hash-keyed
  content-addressed blobs (GC × sweep); inline vs external-reference tiers;
  one joint embedding space vs multi-space fan-out-and-fuse; see the brief
  for the full question list
- **Status:** open — research memo drafted 2026-07-25
  (`research/2026-07-25-multimodal-storage-and-search.md`, superseding the
  brief; eight studies under `research/studies/2026-07-25-multimodal-storage/`);
  awaiting review, feeds the storage-bytes ADR that gates the content-channel
  ADR. Headline positions: entry-keyed binary sidecar, hash-ready for later
  content addressing; two new byte-denominated `DialectProfile` budgets;
  derived-text table keyed to `(entry, content_hash)` feeding ordinary
  chunks; glean as multi-space fan-out with rank fusion. Researched
  further 2026-08-26 (the glean memos, below): the single-space form of
  the space registry is the recommended first landing — model identity
  on the `meta` row, packed float32 vectors, the registry reserved for
  media spaces.
- **Researched 2026-09-15:** `research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md` §6, §10 — MongoDB's VFS keeps bytes in S3 and only chunks in Atlas ("object storage is the data plane"), Archil and Mastra mount buckets, and Cloudflare Computer plans R2 tiering above 4 MiB; every peer keeps large bytes outside the relational store. Sharpened question: is there a size above which vfs content should live in an object store with the row holding a reference, and does that change the read-your-writes guarantee?

## Scattered 10k-target delete holds the topology lock for minutes — set-based batches or cross-transaction chunking?

- **Asked:** 2026-07-25 by the b16c38b code review (scale lens)
- **Context:** Trash-everything delete runs ~4 statements per target inside
  one serialized transaction: a scattered 10k-target batch measured 52.9s
  on Postgres while blocking a rival move for 51.9s, and ~2 minutes on
  MSSQL. Not a regression — the commit made scattered batches 1.9-2.8x
  *faster* than the removed permanent arm, and the set-based bulk escape
  (cascade delete of one holding directory) is intact.
- **Blocking:** nothing — bulk deletes have the documented escape; this is
  latency under the topology lock, not a correctness defect
- **Options considered:** set-based scattered execution (group targets per
  bucket: one reparent executemany plus one rewrite pass); cross-transaction
  chunking (weakens batch atomicity); leave as-is with the documented bulk
  escape
- **Status:** open — research and spec scheduled 2026-08-14 (Clay, in
  session): owned by `specs/active/102-set-based-scattered-delete/`
  (research-first; preconditions and acceptance criteria live there);
  do not fix inline
- **Researched 2026-08-25:** `research/2026-08-25-set-based-scattered-delete.md` — the per-target bumps are the measured cost (65 % on Postgres, 83 % on MySQL); a set-based prototype with byte-for-byte parity on all five engines holds the lock 37× (Postgres), 40× (MySQL), 24× (MariaDB), 26× (Oracle), 7.6× (MSSQL, residual = the snapshot IN-list fetch, 10.9 s → 0.4 s as a VALUES join) shorter at 10k; the byte-range predicate is sargable where LIKE is not; chunking not needed; design waits on Clay's review

## OKF integration: frontmatter as a query surface, and where bundle ingestion lives

- **Asked:** 2026-08-10 by Clay + Claude (OKF research pass — `research/2026-08-10-okf-open-knowledge-format.md`, cloned and surveyed `~/Git/Repos/knowledge-catalog`, Apache-2.0)
- **Context:** Google's Open Knowledge Format (June 2026) is a markdown-plus-YAML-frontmatter bundle convention with no serving story — its frontmatter (`type`, `tags`, `status`, trust families) is queryable in principle and unqueried in practice, which is a vfs-shaped hole. Ingesting a bundle as plain files needs zero schema change today; the real design work is the memo's §7.2 fork. Three sub-questions: (1) is frontmatter-as-facets a **general** vfs capability (skills, MDX, Hugo, our own memos all carry frontmatter) with OKF as one profile, or OKF-specific ingestion? (2) storage shape — entry-keyed sidecar table (ADR 016 shape, also proposed by the multimodal question) vs facet columns on `entries` (the `ext` precedent, with the `SCHEMA_FORMAT_VERSION` bump)? (3) do `type=`/`tags=`/`status=` join the glob/grep filter channels the way `kind=` did in spec 094? Adjacent, smaller: dangling-link policy when minting edges from markdown links at ingestion (OKF §6.1 requires tolerating them; `mkedge` — the one unbuilt hinge — resolves endpoints), and whether bundle ingestion is a library helper (`skills.py` shape), a dev-plane verb, or a mount-type concern.
- **Blocking:** nothing — the memo's §8 sequence starts with a zero-schema ingestion demo that needs none of these answered.
- **Options considered:** per-fork options in the memo §7.2–7.3; recommended order of attack in §8.
- **Status:** open

## MCP 2026-07-28: long-batch execution model and serving-stack choice for serve()

- **Asked:** 2026-08-10 by Clay + Claude (MCP revision research pass — `research/2026-08-10-mcp-2026-07-28-stateless-revision.md`; spec pages plus line-level studies of the freshly-pulled `modelcontextprotocol`, `python-sdk`, and `fastmcp` checkouts)
- **Context:** The 2026-07-28 revision makes MCP stateless: a broken response stream *is* cancellation, the client re-issues the request fresh, and the protocol ships **no idempotency mechanism** — so a re-issued 10k-file `write` batch is a double-execution question the verb surface has never had to answer as a whole. The spec's designated durability answer is the optional tasks extension (`io.modelcontextprotocol/tasks`: poll-based, `completed` includes `isError: true` results — evidence-in/verdict-derived, matching ADR 010), which today only FastMCP 4 implements (Redis-backed) while python-sdk v2 has reserved seams but no implementation. The memo's §8.1 `[NEEDS CLARIFICATION]`: is task-backed execution in scope for the first serve() landing, or is the first landing synchronous-only with documented re-issue semantics? Entangled with it (§8.6): the stack choice — python-sdk v2 (official, disciplined wire pins, AEAD requestState, no tasks) vs FastMCP 4 (tasks today, heavier and faster-moving) vs implementing the tasks extension ourselves on python-sdk's open seams, backed by vfs's own storage.
- **Blocking:** the serve() spec (056 Pass C's successor); also feeds spec 045's schema pinning (JSON Schema 2020-12, `inputResponses`/`requestState` as protocol-owned params) and the read-family cursor question, whose wire shape SEP-2567's handle etiquette now settles (memo §8.2).
- **Options considered:** memo §8.1 and §8.6; ADR 022's refresh notes in §8.4 (stale fastmcp citation, "session state" wording).
- **Status:** open

## vfs-js and vfs-rs sibling implementations

- **Asked:** 2026-08-16 by Clay (at spec 103's packaging-fork review)
- **Context:** Roadmap intent, stated while picking the pendulum packaging model: vfs should eventually have full JavaScript and Rust implementations so devs build apps with vfs in those languages, not only Python. Spec 103's workspace is already shaped for it — engine logic in binding-free core crates under `crates/`, the pyo3 crate a thin binding — so the grep cores that land there become the first shared foundation. What a "full implementation" means (verb-surface parity, storage backends, MCP serving, result envelopes) is entirely undesigned.
- **Blocking:** nothing current; it shaped spec 103 §1's crate layout (recorded there). Its own research → decide arc starts when Clay prioritizes it.
- **Options considered:** none yet — the fork space (shared Rust core with bindings everywhere vs independent idiomatic implementations vs wasm-first) is the future research question.
- **Status:** parked

## Should a closed backend refuse, for every verb?

- **Asked:** 2026-08-25 by Clay + Claude (chunking-arc landing review, finding F3's decision pass — `research/2026-08-25-chunking-arc-landing-review.md`)
- **Context:** Spec 122 ruled grep's close posture by the sibling law — after and across `close()`, every verb serves, transparently re-establishing what it needs (the ready latch now falls with close, so first touch re-runs; the verify pool re-mints; a call racing close serves its batch inline). What was deliberately *not* ruled: whether that sibling law itself is right. `close()` today releases resources but never ends service — a post-close `write` still mutates (executed in the review's leads) — and `SupportsClose` commits only to idempotence and dead-peer tolerance, taking no position on refusal. A refuse-after-close contract would touch every backend, the router's dispose walk, and the conformance battery's lifecycle row (`test_pattern_search_serves_after_close`, which currently pins serve-after-close for glob and grep).
- **Blocking:** nothing — the current posture is coherent and pinned; this is a contract question about what `close()` *means*, not a defect.
- **Options considered:** (a) status quo — close releases, service re-establishes (the POSIX-fd analogy fails here, but the SQLAlchemy-engine analogy holds: dispose then reuse works); (b) closed-means-refuse — every verb returns a classified `unavailable` after close, requiring an explicit reopen; (c) closed-means-refuse only for mutations, reads re-establish. Each needs the router and memory backend ruled together.
- **Evidence since:** the 2026-08-25 prior-art survey (`research/2026-08-25-close-lifecycle-and-shutdown-race-prior-art.md`) found every surveyed close-latch exists to *refuse* — latch-without-refusal has no precedent — so option (b) is the only shape under which a closed flag would ever return (spec 126 removes the current one as incoherent without it).
- **Status:** open

## Close-window inline cost: prose disclosure, or a zombie pool?

- **Asked:** 2026-08-25 by Clay + Claude (remediation-round landing review, finding F7's decision pass — `research/2026-08-25-remediation-round-landing-review.md`)
- **Context:** A verb that captured the offload pool before `close()` serves all its remaining CPU hops inline on the event loop — verb-sized exposure, measured 1.56 s on-loop (1,714 ms worst gap) for a 20,000-file reindex racing close, correct results throughout. The 2026-08-25 prior-art survey found the drain idiom universal (in-flight work finishes on what it captured; the closer owns any deadline) and no precedent for per-hop migration to re-minted resources or for chunking degraded work. Spec 129 rules prose + pin; this entry holds the code question.
- **Blocking:** nothing — the window is a rare close race and the verb serves; this is loop-latency during teardown, not correctness.
- **Options considered:** (a) status quo with honest prose (landed by spec 129); (b) zombie pool — the prior-art-faithful shape: close defers executor teardown until in-flight verbs drain (SQLite `close_v2` / SQLAlchemy checked-out-connection shape), so a racing verb finishes on real worker threads and the loop never pays — at the cost of close no longer being instant; (c) a closer-owned drain deadline escalating to the current inline fallback. Per-hop pool re-reads were considered and declined — no prior art, and they move mid-verb ownership.
- **Status:** open — unblocked by evidence that real workloads hit the window (a latency report during shutdown, or the close-race pin flaking on gap-sensitive infrastructure)

## A shared `_presence_probe` owner for the LIMIT-1 existence shape?

- **Asked:** 2026-08-25 by Clay + Claude (remediation-round landing review, design question Q3's decision pass)
- **Context:** Spec 121's inline generation probe duplicates `_pending_probe`'s LIMIT-1 shape (`indexing.py`) without its "never a bare SELECT EXISTS" rationale — a rule confirmed real on live MSSQL (error 42000). Mitigations today: spec 121 cites the pattern by name, and an `.exists()` rewrite fails loudly on the MSSQL conformance leg. Two call sites is thin ground for a wrapper.
- **Blocking:** nothing — both sites are correct and engine-proven.
- **Options considered:** a shared `_presence_probe(session, whereclause)` helper holding the T-SQL rationale once, plus a Docker-free compile-level legality pin covering both shapes (the strongest argument for the wrapper — `TestStatementLegality` currently holds exactly one such row); or status quo with the rationale living at `_pending_probe` alone.
- **Status:** parked — unblocked by a third probe site, or by the statement-legality class growing per the review's lead

## A `_Truncations` owner for grep's at-most-once record law?

- **Asked:** 2026-08-25 by Clay + Claude (remediation-round landing review, design question Q2's decision pass)
- **Context:** Six repeated `if <literal> not in truncations` guards plus an upgrade dance implement the at-most-once truncation-record law per-site in `storage/backends/database/grep.py`. Per-site guards were spec 125's deliberate ruling; every path is at-most-once by construction today, and `Result.merge` dedupes at the facade. The 2026-08-25 decision pass declined to reverse a same-round ruling without new evidence.
- **Blocking:** nothing — no wrong output exists.
- **Options considered:** a small `_Truncations` type enforcing at-most-once by construction (a taker must preserve the load-bearing `truncations == ["candidate budget"]` equality gate); status quo. Adjacent unverified lead: whether the facade's `Result.merge` dedupe — the only non-local safety net — is itself pinned.
- **Status:** parked — the tripwire is a seventh guard site or a duplicate-record bug reaching the seam

## glean — what the database backend's fused ranked search must be

- **Asked:** 2026-08-26 by Clay (the glean requirements: in-engine RRF of vector + BM25-style lexical, glob scope pushed down, centrality and read-derived signals through a customisable ranker API, an embedding provider in Storage with LangChain/OpenAI adapters, top-*n* entries with fast query-biased previews, and an honest merge of top-*n* lists across mounts with different embedders)
- **Context:** ADR 007 pins the verb and no backend implements `SupportsGlean`; the reindex pipeline mints chunk rows with an `embedding` column nothing fills; no lexical ranking index exists; edges are user-minted only; reads leave no trace; glean's render path falls through to the path list, which sorts alphabetically. Brief: `research/2026-08-26-glean-brief.md`.
- **Blocking:** any glean implementation; the compose-file bumps the engine legs need (pgvector image, MariaDB 11.8, MySQL 9, SQL Server 2025 + FTS, Oracle regular image).
- **Options considered:** recorded as named forks in each memo — fusion in SQL vs Python (E1), term text vs id (E2), precomputed weight vs runtime formula (E3), epoch rebuild vs incremental (E4), native vector types on MSSQL/MariaDB (E5), convex combination vs RRF as the reference (A-series), aggregate-then-fuse vs fuse-then-max (A3), router re-fusion of cosine (B2), in-degree vs PageRank/Katz first (signals F1), prior as factor vs rank list (F2), read capture default (F3), identity home and mismatch policy (embedding 1–2), preview field placement (previews 1).
- **Status:** **decided 2026-08-26** — ADRs 051 (the fused statement, the owned lexical index, vector tiers, predicate scope, freshness), 052 (convex fusion amending ADR 007, aggregate-then-fuse, bounded priors, download-and-rerank across mounts with corpus-wide statistics as a `SupportsGlean` requirement and `min(limit×3, 256)` fetch depth, the result shape), 053 (a `signals` table computed at reindex, in-degree with hierarchy smoothing, `fs` edges excluded from the walk, the declarative `Ranker`; reads deferred), 054 (the vfs-owned `EmbeddingProvider`, identity on the meta row, embedding as a streaming step of `reindex`). **Amended 2026-08-26 by ADR 055** after spec 130's first landing measured the relational lexical index at 32 B/posting and ~9× over the linux-scale reindex target: BM25 is now block postings per term built and scored by the Rust engine (pure fallback pinned), fused client-side on every engine — `research/2026-08-26-bm25-storage-design.md` and its four studies; spec 130 reopened and rewritten, specs 131/132/135/136/137 amended. Next: the spec; the reference-edge extractor as its own spec; the accuracy study (signals memo §9) as the next research leg. Research record: eight studies plus three hierarchy-edge studies under `research/studies/2026-08-26-glean/` (engine matrix verified on running containers, lexical leg built and timed, fusion and cross-mount merge simulated on BEIR with labels, centrality and read signals, embedding seam measured, previews prototyped, landscape, and one no-requirements design) synthesised into five memos: `research/2026-08-26-glean-in-the-engine.md`, `-fusion-and-cross-mount-merge.md`, `-ranking-signals-and-ranker-api.md`, `-embedding-seam.md`, `-previews-and-result-shape.md`. Awaiting Clay's review; then ADRs (storage statement + lexical index; fusion + merge; signals + ranker API; embedding provider), an ADR 007 amendment (reference fusion), then the spec.

## The plane's real name, and whether the Catalog is open source

- **Asked:** 2026-08-27 by Clay + Claude (the positioning memo, `research/2026-08-27-agent-access-layer-positioning.md` §6 and §9; ADR 058)
- **Context:** ADR 058 splits vfs into two products: the library — the access layer for agents, enforces, in the data path, OSS `pip install` — and an admin plane above it that shows what is mounted, who can reach what, which tools live where, and what changed. "vfs Catalog" is a working name only: "catalog" is a category word (Unity Catalog, Snowflake Horizon Catalog, Apache Polaris), not a brand, and "agent catalog / registry" now means *a list of agents*. The July company memo's split (OSS funnel, paid plane, enterprise features never in the OSS quickstart) makes the plane the business but does not say whether its code is open.
- **Blocking:** nothing today — the library's positioning stands without it. Blocks the Catalog work once it starts (its v1 is a read-only viewer over C7 introspection, itself unbuilt — memo §8), and the mission v0.2 revision's reading of the "we are not a managed service" non-goal (the library never is; the plane may be).
- **Options considered:** *Name* — keep "Catalog" as the descriptor under a brand of its own; a name built on "namespace", the mechanism word; anything but the nouns ADR 058 rejects ("agent catalog", "registry", "control plane", "sandbox", "workspace"). *Shape* — (a) an open-source plane with paid hosting: the code is open, the business is running it; (b) a closed plane over the open library: the July memo's default reading; (c) open-core: the read-only viewer open, the decide-and-change panels (grants, principals, edit-in-place) paid. Each shape changes what the library's introspection surface must expose publicly versus keep behind the plane.
- **Status:** open

## Search-first or governance-first after the glean arc?

- **Asked:** 2026-08-27 by Clay + Claude (ADR 058's sequencing consequence; memo §4.1 and §9)
- **Context:** The positioning leads with governance because that is the pain the market is buying, and the memo's reading is that principals (spec 070) and grants (ADR 021 → spec 058) move ahead of further search work *if* the governed half is what we sell, with C7 introspection (publishing what the router already computes) as the Catalog's cheap prerequisite. The memo does not itself decide it, and ADR 058 records it as a consequence, not a ruling. The glean arc (specs 132–137) is mid-flight; ADR 021 is still proposed.
- **Blocking:** the roadmap order of specs 070 and 058 (and ADR 021's ratification) relative to specs 135–137; whether C7 introspection lands as its own spec before either.
- **Options considered:** (a) finish the glean arc, then principals → grants → introspection; (b) principals and grants now, glean's vector leg and signals after — the memo's lean; (c) C7 introspection first regardless, since it is small and unblocks the Catalog's v1 and the "who can reach what" panel that grants will feed.
- **Status:** open
- **Researched 2026-09-15:** `research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md` — the four category peers (deep agents/LangSmith, Cloudflare Computer, MongoDB VFS, Letta MemFS) and fourteen adjacent systems all ship the verb set and a store underneath; hybrid search is now shipped by MongoDB, Mastra, Cloudflare Agent Memory and two hobby projects, while per-path, per-principal enforcement in the data path is shipped by nobody and is deferred "to the application" in writing by three of the four. The memo recommends (b): principals and grants now, glean's remaining legs after.

## `serve()` re-spec against a named consumer: one tool with a verb argument, or one tool per verb?

- **Asked:** 2026-09-15 by Claude (eve memo `research/2026-09-15-eve-vercel-agent-framework.md` §7.2, §9)
- **Context:** Vercel's eve consumes MCP servers as *connections*: the model finds tools by the connection's description through `connection_search`, each remote tool becomes `<connection>__<tool>`, and eve layers a per-tool allow-list and approval policy on top. That favours few, well-described tools. The July company memo's line was "one MCP tool, sixteen verbs." The two shapes give a consumer different least-privilege and approval handles (eve can gate `vfs__delete` with `always()` only if delete is its own tool). eve also supplies a replay-stable `callId` per remote call and serves MCP `2026-07-28` with stateless `2025-11-25` compatibility, which pins the version and the idempotency contract the re-spec should target.
- **Blocking:** the `serve()` re-spec (the existing "MCP 2026-07-28: long-batch execution model and serving-stack choice" entry); ADR 022's topology-off-the-wire rule rides on it.
- **Options considered:** (a) one tool per agent-facing verb, `sweep` and topology admin withheld, capabilities advertised so a consumer's allow-list can be derived; (b) one `vfs` tool with a `verb` argument and the `Result` envelope as structured content; (c) both, with (b) as the compact surface for code-mode and tool-search clients.
- **Status:** open

## Reference adapters for host frameworks: publish them, or document the wire and let hosts write them?

- **Asked:** 2026-09-15 by Claude (eve memo §7.1 seam 2, §9)
- **Context:** eve's cleanest conceptual seam for vfs is its memory provider (`recall`/`capture`/`tools` driven at fixed lifecycle points with an opaque per-tenant scope key). Filling it needs a thin TypeScript package that calls a served vfs. That is not vfs-js, but it is TypeScript vfs would own or bless. The pre-refactor deepagents adapter design (`docs/deepagents-integration.md`) is the Python twin of the same question and references retired names.
- **Blocking:** nothing yet; becomes concrete the moment `serve()` lands.
- **Options considered:** (a) publish small reference adapters (an eve memory provider, a deepagents backend) in a separate repo, versioned against the wire; (b) document the wire contract only and point hosts at it; (c) publish only the eve one, since it is the consumer with a real principal on every call.
- **Status:** parked — unblocked by `serve()`

## Where does an agent's bundle live in the namespace: a user directory, or a reserved `/.agents/<agent>/` family?

- **Asked:** 2026-09-15 by Claude (eve memo §9; vfs-side brief §F)
- **Context:** eve's agent is a directory (instructions, skills, tools, memory, subagents per agent). vfs's reserved `/.agents` tree has exactly two families, `tools` and `skills` (`paths.py::AGENT_FAMILIES`), which match the halves of that shape the industry is converging on. Hosting a whole agent-shaped subtree is either an ordinary user directory (`/agents/<name>/…`, no grammar) or a third reserved family with its own path rules and a materializer like `Skill.to_entries()`.
- **Blocking:** nothing today; the skills/memory how-to and any per-agent posture rule in spec 058 would take a position.
- **Options considered:** (a) plain user directories, no reserved family; (b) a reserved `/.agents/<agent>/` family with grammar for instructions, skills and memory; (c) defer until a real consumer asks for per-agent isolation.
- **Status:** parked

## Write preconditions on the wire: expected version, content hash, or both?

- **Asked:** 2026-09-15 by Claude (`research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md` §4.3, §8.4, §10)
- **Context:** The emerging write-safety idiom across peers is a precondition on `write`/`edit`: Anthropic Managed Agents memory takes a `content_sha256`, memgres a `base_hash` (409 on mismatch), MongoDB's VFS an S3 `IfMatch` on `edit` only, eve a read-before-write hash stamp. It is also what a replayed durable-execution step needs from a store. vfs already carries a per-entry `version` stamp on every observation but no verb accepts one as a condition. An expected version is vfs's own coordinate and cheap to check; a content hash is what a client can compute without a prior read and what peers speak.
- **Blocking:** the `serve()` re-spec (the served `write`/`edit` contract); the version-row design (a refused write should not mint a row).
- **Options considered:** (a) expected `version` only; (b) `content_sha256` only; (c) both, either sufficient, mismatch classified as a child of `invalid` (or a new `conflict` kind); (d) neither, keep last-write-wins and rely on reversibility.
- **Status:** open

## A "when not to use vfs" statement

- **Asked:** 2026-09-15 by Claude (`research/2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md` §7, §8.7)
- **Context:** Arize's June 2026 benchmark (a Postgres-backed VFS vs a "query once, materialize, use real bash" skill: 93 vs 99 of 100) and its line "every time you fake a filesystem, you sign up to maintain one" is the live counter-argument to the category. vfs's answer is that it is not a filesystem emulation but a namespace with semantics a POSIX filesystem cannot give (principal on every call, per-caller visibility on one tree, attributed versions, typed edges, predicate-scoped search). Saying plainly where a checkout plus ripgrep wins (one agent, one machine, no sharing, no policy) sharpens the pitch and pre-empts the critique.
- **Blocking:** nothing; the README and ADR 058 refresh would carry it.
- **Options considered:** (a) a short section in the README; (b) a line in `standards/mission.md` under non-goals; (c) a paragraph in the positioning ADR only.
- **Status:** parked

## Path-ordered lexical ids: a flat-cost visible `df` for partial callers?

- **Asked:** 2026-09-28 (spec 058 landing; the Q3 statistics memo's option e)
- **Context:** A caller whose rights do not cover the whole mount gets exact visible-set statistics (ADR 065 rule 5). Today `glean` computes the visible `df` of each query term by reading every block of that term's postings, so the cost grows with the term's corpus-wide document frequency, not with what the caller can see. If lexical ids were assigned in path order, a caller's visible prefixes would map to id ranges, and the visible `df` would be a range count per prefix.
- **Blocking:** nothing; partial-caller `glean` is correct today, only its cost on common terms is high.
- **Options considered:** path-ordered id assignment at index build (renumbering on move); per-prefix `df` summaries kept beside the blocks; leave as-is.
- **Status:** open — needs its own ADR. Memo: `research/2026-09-28-search-statistics-under-permissions-precedent.md` §option e.

## Stored ranking signals may count hidden in-links

- **Asked:** 2026-09-28 (spec 058 landing)
- **Context:** `glean`'s link signals (in-degree, and anything derived from the reference graph) are computed at index time over the whole mount. A partial caller's score could then move with edges from rows it cannot see, the same class of leak ADR 065 rule 5 closed for BM25 statistics. The signals are off by default and the leak is unstudied.
- **Blocking:** turning any stored graph signal on by default for a mount with a non-open posture.
- **Options considered:** withhold stored signals from partial callers; recompute over the visible subgraph; accept and document.
- **Status:** open

## grep's candidate budget counts hidden candidates

- **Asked:** 2026-09-28 (spec 058 landing)
- **Context:** grep bounds the candidates it fetches before the per-row gates run. The visibility check runs beside the structural gates, after the candidate list is cut, so a partial caller whose scope holds many hidden matches can hit the budget (and see a truncation warning) with few visible hits.
- **Blocking:** nothing; the answer is correct and the truncation is loud.
- **Options considered:** push the visibility clauses into the candidate query itself (the fan grep already runs); raise the budget for partial callers; leave as-is and document.
- **Status:** open

## Rows deleted since an index build still count in the stored statistics

- **Asked:** 2026-09-28 (spec 058 landing)
- **Context:** The stored corpus statistics (`N`, `avg_dl`, per-term `df`) that whole-mount callers use are rebuilt by `reindex`. Between builds, deleted rows still count, so a whole-mount caller's scores can reflect rows that no longer exist. Partial callers compute visible statistics live, so they are not affected.
- **Blocking:** nothing; bounded by reindex cadence.
- **Options considered:** decrement the stored statistics on delete; compute live statistics for every caller; leave as-is.
- **Status:** open

## Group ownership: can a principal with members own a row?

- **Asked:** 2026-10-07 by Clay (permissions teaching session, step 6)
- **Context:** A `read_write` card for `group:eng` on `/eng` is not the same as the team owning `/eng`: a card can be revoked by anyone holding `read_write` there, while the owner floor (ADR 064 rule 4) cannot be revoked at all. A team running a daily report job wants the *team* to own the output so no one person's departure strands it. Today a `service` principal can own rows (`Authority.of(Principal(..., kind="service"))`), but no member of any group inherits an owner floor from a row the group or service owns; `Principal` refuses `group:` subs, and `Rights.admits` matches `owner_id` only against the calling set's members. Clay's framing: groups should act like ordinary principals, so "the principal is a group" and ownership follows.
- **Blocking:** nothing; parked for research after the teaching journey.
- **Prior art to study first:** Postgres role ownership (a role with members owns an object; members hold owner privileges; `ALTER ... OWNER TO`; ownership survives any `REVOKE`); Unix group owner and set-group-id directories (new files inherit the directory's group — the container rule ADR 064 already takes); Plan 9 group leaders.
- **Options considered:** (a) allow `group:` ids in `owner_id`, with the owner leg compiled as `owner_id IN (sub, *closure)` per member; (b) a `service` principal as the owning identity plus a membership edge from the team to it; (c) leave ownership personal and document "team ownership is a card on the folder" as the contract.
- **Questions a memo must answer:** cost of the widened owner leg at 100k users; transfer when a member leaves; whether set-created and anonymous rows stay ownerless or take the container's group; interaction with the intersection law when members share the owning group; what the system-actor path should refuse in a declared `owner_id` (today it validates nothing).
- **Status:** parked

## A `manage` rung: granting and revoking ride on `read_write`

- **Asked:** 2026-10-07 by Clay (permissions teaching session, step 6): "a card can be revoked by anyone holding `read_write` at that path ... makes me think we need additional levels: none, read, read_write, manage."
- **Context:** The grant gate (`rights.py`, `_grant_refusal`) requires only `read_write` at the path, so any writer may grant up to `read_write` and may revoke **any** card at that path, including their own team's (spec 058 §8). The inverse also holds: the gate reads the caller's spans and the everyone level, never the owner floor (`Rights.reaches`), so under a `private` posture an owner cannot share a row they wrote. Both come from fusing "may change the data" with "may change who may". Spec 058 and the 2026-09-28 memo weighed an admin right for *group membership* only (chose system-actor-only, `ADMIN OPTION` as follow-up); no record considers one for cards on paths. The Unix lens memo's verdict table already marks NFSv4's "owner keeps `WRITE_ACL` no matter the ACL" as **take** ("a principal can never be locked out of its own grants by a narrowing"); the grant gate does not implement it.
- **Blocking:** nothing lands broken; parked for research after the teaching journey. Related: *Group ownership* above (same root: one notion of "may change" where three are needed — data, rules, ownership).
- **Prior art to study first:** Unix `chmod` owner-only / FreeBSD `VADMIN` (no ACL can confer it, `vfs_subr.c:5681`); NFSv4 `WRITE_ACL` and `WRITE_OWNER` as bits distinct from `WRITE_DATA`, owner keeps `WRITE_ACL` (`subr_acl_nfs4.c:208-210`); Plan 9 `wstat` mode changes by owner or group leader only (`stat(5)`); Postgres `WITH GRANT OPTION` / `ADMIN OPTION` and its refusal of a grantor revoking the admin granted back to it (`user.c`).
- **Options considered:** (a) a fourth rung `manage` on the ladder, card-granted and attenuating (only a manager makes a manager), everyone's rung capped at `read_write`, owner floor includes `manage` on own rows, and a rule that a caller may not revoke the card its own `manage` stands on; (b) a Postgres-style per-card grant-option flag instead of a rung; (c) owner-only administration (Unix): only the owner or the system actor may grant on a row, with no delegation.
- **Cost sketch for (a):** one `LEVEL_RANK` entry; a third `Rights` compile per call for the gate (`Resolution` gains `manage`); the gate asks `manage` instead of `read_write`; `everyone_level` and the range algebra unchanged since posture tops out at `read_write`; the `*` card and `Posture` words unchanged.
- **Status:** parked
- **Addendum 2026-10-07 (Clay: "any other permissions that should be in the ladder?").** Test for a rung: a per-path, per-principal fact; strictly includes every rung below (the total order the row label and the meet depend on); needed exactly by a verb in `ops.py`'s inventory. Candidates that pass: **`list`** (name and kind without contents — NFSv4 `READ_ATTRIBUTES`, S3 `ListBucket`, the road generalised to files by card; lets an agent say "there is a file here you cannot read, ask for access" instead of hidden-is-absent; `grep`/`glean` score the *readable* set only) and **`contribute`** (create and append; alter or remove only your own rows — Plan 9 append bit, NFSv4 `ADD_FILE`/`APPEND_DATA`, the sticky bit, Drive "contributor"; the write gate's `GateMode.create` passes and `modify` falls through to the owner floor; inbox, journal, add-only ingest). Proposed ladder: `none < list < read < contribute < read_write < manage`; posture gains `listed` and `inbox` words, everyone capped at `read_write`. Candidates that fail: **destroy/sweep** (a plane question and the one irreversible verb; require `manage`, keep developer-plane), **own/transfer** (ownership is a floor; a verb needing `manage`; see *Group ownership*), **traverse** (structural: the road), **run** (fails total order — one may run what one cannot read and read what one cannot run; Unix `x`, Postgres `EXECUTE`, MCP allowlists; today `run` takes no write gate — a real missing right that needs its own axis, not a rung; park separately when researched), edges/versions/comments (derived). Costs: one `LEVEL_RANK` entry per rung; one more `Rights` compile per level a verb can need, so cache weight grows with rung count; row label and range algebra unchanged; `list` is the one rung needing new machinery (visible row, hidden body). Make the verb→rung mapping one declared table in `ops.py`.

## Three enforcement gaps noticed in the 2026-10-07 permissions teaching session

- **Asked:** 2026-10-07/08 by Claude while grounding teaching steps; Clay's scale question ("are permissions pushed down to SQL?") surfaced the third.
- **Context:** (1) **grep applies the view after candidate nomination.** `grep.py` strikes hidden rows out in Python (`view.admits`) after the id-first candidate fetch; no body is read for a hidden row, but the 25,000 `CANDIDATE_BUDGET` counts hidden candidates, so a partial caller on a mostly-hidden corpus truncates sooner than a whole one (the docstring says so). Every other read joins `visible_entries` through `Visibility.narrow`; grep's `_entries_for_docs` and the scan nominator do not. (2) **A move emits no notice when rows leave a granted prefix.** Spec 058 §6 says move "is a permission event ... the info record names it"; `topology.py`'s move touches no grant row and emits no such record. (3) **The system-actor write path does not validate a declared `owner_id`.** `owner_for(authority, declared)` stamps whatever the payload says; a batch job could write `group:eng` or `*` into `owner_id`. Harmless for rights (owner arms match only a set's members) but misleading in the audit.
- **Blocking:** nothing; (1) is a scale correctness gap under the 10k-batch / partial-caller contract and is the one to fix first.
- **Options considered:** (1) wrap grep's candidate statements in `view.narrow` (range join where the dialect has one, the fan elsewhere) so the budget counts visible candidates; (2) emit an info-severity `ResultError` from move when a source prefix lies under any grant row's `path_prefix`, or amend the spec to drop the promise; (3) refuse reserved and `group:` ids in `_lawful_owner`-style check at staging, system actor included.
- **Status:** open

## Markers in specs 153–161 (cut 2026-10-08 from the SmartOwl memo)

- **Asked:** 2026-10-08 by Claude while cutting nine specs from `research/2026-10-08-smartowl-workspace-integration-issues.md`.
- **Context:** each spec carries `[NEEDS CLARIFICATION]` markers for a call that is Clay's. Revised 2026-10-08 after a per-spec review against `0760fe9` (ten reviewers, one per spec; several markers resolved by the tree): **153** resolved (Clay, 2026-10-10: the deepagents page and `docs/plans/` deleted outright; built the same day); **154** resolved by the 2026-10-10 rewrite (errors are facts: the seam rebases `data["vfs.target"]`, and no producer authors `message`); **155** rank only by default, or rank plus the raw score (the MCP-default-budget marker is withdrawn: no MCP or CLI surface exists in `src/vfs`); **156** refuse a bare `VirtualFileSystem` in `add_mount` or ship the forwarding adapter (the root seal was dropped, Clay 2026-10-08: the default root is an in-process SQLite `DatabaseStorage`, the owner's choice); **157** resolved (Postgres checks `IF NOT EXISTS` before privilege, so no tolerance step; psycopg takes `"core"`, `"driver"` is a measured fork); **158** dropped (Clay, 2026-10-08: no release soon; the release facts its review found are in `standards/release.md`); **159** resolved (Clay, 2026-10-08: no scoped reindex, since the posting index is whole-corpus; a rival run keeps refusing `conflict`; the inline budget is 16 rows and one `BLOB_PAGE_BYTES`); **160** resolved (no description or custom-metadata column exists; parity with in-mount copy stated); **161** the read-side shape for history (`versions` verb or `read(version=)`; `restore(version=)` is out per ADR 064 rule 6), owed to its research pass, which also decides the fate of the dormant `models/versioning.py` and the ADR 017 pin 1 amendment.
- **Blocking:** 161 cannot be shaped without its markers; the others can land with the leaning answer.
- **Status:** open

## Trash as a tombstone on the row (ADR 074, accepted 2026-10-08)

- **Asked:** 2026-10-08 by Clay ("could we just create a visibility flag? … if you write back to that location, it turns it back on and creates a new version?").
- **Context:** memo `research/2026-10-08-trash-as-a-tombstone-on-the-row.md` (measured: six row writes per file on delete today; MinIO, JuiceFS, SQLAlchemy and three agent-audience peers studied); ADR 074 proposes delete flags, restore clears, a write revives, one row per path so the unique index stays plain.
- **Resolution:** Clay accepted ADR 074 and its three leanings on 2026-10-08 ("those all sounds good"): kind change on revive allowed, edges survive, `/.vfs/trash` served as a view. Spec 162 cut the same day. Correction recorded in the memo: spec 150 §8 was already built (`f823436`), so the permission leak was closed; the tombstone removes the doubled predicate forms rather than fixing a live leak.
- **Reopened in part, 2026-10-08:** the spec 162 review worked the revive by hand and found the ADR's item 5 (kind change on revive, same entry id) produces a live file with live children after `mkdir /d`, `write /d/a.md`, `delete /d`, `write /d`, `delete /d`, `restore /d`, and that its escape hatch ("descendants restore individually once the site is a directory again") is unreachable under item 9. Spec 162 rule 5 proposes the alternative the ADR names, a `wrong_kind` refusal on mismatch, and rule 4 drops a "same root" clause the cut spec had added (it let `restore /d/f.md` leave a live file under a tombstoned `/d`). Two decisions for Clay: amend ADR 074 item 5 to same-kind revive only; confirm that `overwrite=False` admits a revive. Spec 162 task 0 gates both slices on them.
- **Status:** resolved; two amendments pending Clay

## A borrowed session factory over an in-memory SQLite engine fails `grep`

- **Asked:** 2026-10-10 by Claude while making the README's first code block run under Sybil (spec 153).
- **Context:** `DatabaseStorage(session_factory=async_sessionmaker(create_async_engine("sqlite+aiosqlite:///:memory:")))` serves `write` and `read`, then `grep` comes back `unavailable`: "cannot start a transaction within a transaction". SQLAlchemy puts a `:memory:` aiosqlite engine on a `StaticPool` (one shared connection). The engine host serializes sessions on that connection only in the `url=` form, where it built the engine itself; a borrowed factory over the same pool is driven concurrently by grep's fan and collides. The `url=` form on `:memory:` and a borrowed factory over a file-backed engine both work. Measured 2026-10-10 on `0760fe9`.
- **Blocking:** nothing; the README borrows a file-backed engine. A host that hands vfs a shared-connection session factory (tests, demos) hits it.
- **Options considered:** read the pool class off the borrowed factory's bind and serialize when it is a `StaticPool`, as the owned form does; refuse a borrowed `StaticPool` factory at construction with a classified reason; document the shape as unsupported in the `DatabaseStorage` docstring.
- **Status:** open — small; a slice of spec 157 (provisioning for host apps) or a one-line spec of its own

## Per-test CPU inflates 2× under ten xdist workers

- **Asked:** 2026-10-10 by Claude while measuring `pytest-xdist` for spec 163 (memo `research/2026-10-10-the-test-suite-slice-by-slice.md` §3).
- **Context:** The whole suite is 253s serial and ~100s at 10, 16 or 20 workers on the M1 Pro, with about 5 of 10 cores busy. Two subtrees at 1/5/10 workers show the same tests burning 2.2 to 2.8× the CPU time at ten workers that they burn at one. About 25s of that is per-worker startup; the rest is per-test inflation whose cause was not separated: performance versus efficiency cores, all-core clock, shared cache, or kernel wake-up latency on the aiosqlite thread hand-off (two wake-ups per statement, ~300k statements a run).
- **Blocking:** nothing in spec 163; the statement-count levers help regardless. It decides which later lever helps xdist most (fewer statements per test versus fewer workers than cores).
- **Options considered:** `py-spy` one worker at `-n 1` against `-n 10` and compare where the extra time lands; repeat the 1/5/10 probe on a Linux box with homogeneous cores; measure `-n 8` (performance cores only) against `-n 10`.
- **Status:** open — a one-hour probe when spec 163's frame has landed
