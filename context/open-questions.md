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

## Row-level grant semantics (spec 058's clarification forks)

- **Asked:** 2026-07-10 (spec 058 seeded with `[NEEDS CLARIFICATION]` forks — nine in the spec as it stands; this entry long said eleven)
- **Context:** Row-level permission grants need a verified `Principal` before enforcement semantics can be pinned; the forks cover grant shape, inheritance, and query-construction enforcement.
- **Blocking:** `specs/active/058-row-level-permission-grants/`
- **Coupled to:** the parked full-dirent question below. 058 attaches grants to **path prefixes** and computes coverage from the path string; ADR 018's parked end-state gives one entry many paths via hard links, which makes prefix coverage ambiguous and dissolves `Entry.path` as sole domain identity — the classic POSIX hard-link permission problem. Ratifying a prefix-attached grant model entrenches against that end-state; unparking it forces 058 to re-derive around ids.
- **Also lands here:** the *per-principal* half of the execute-policy question below — an `execute` level in this grant ladder, not a reopening of 039.
- **Stale premise:** 058's depends-on line cites `src/vfs/models.py` / `VFSEntry`, neither of which survived spec 076's model split (now `src/vfs/models/entry.py`, `Entry`), and its "identity threaded as `user_id` through `_call_storage`" language is superseded by spec 070. True these up before the full spec is written.
- **Options considered:** see the forks inline in 058's spec
- **Status:** open — waits on spec 070 (`Principal`) landing first

## serve() topology-lock policy premise

- **Asked:** 2026-07-10 (flagged in the STATUS true-up)
- **Context:** Spec 054 decides that `serve()` locks mount topology, but its `allow_child_mounts` premise went stale after 056/068 reshaped mount admin. **Verified 2026-07-22:** `allow_child_mounts` has zero occurrences in live `src/` — the spec's mechanism language is not merely stale but unimplementable as written, and should be deleted rather than re-derived.
- **Blocking:** `specs/active/054-mcp-serve-locks-topology/` — itself waiting on `serve()` existing
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
  chunks; glean as multi-space fan-out with rank fusion.

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

## Rust extension posture for the grep pipeline

- **Asked:** 2026-08-16 by Clay (at the linux-tree benchmark readout — `research/studies/2026-08-16-linux-grep-benchmark/`)
- **Context:** The benchmark named five interpreted-throughput costs (672 s reindex, ~700 ms per-call floor, verify-heavy rows losing to rg, the 102 s wrapped-wildcard row, the 4 MB budget truncating hot rows). Clay's directional resolution: the slow parts of the index build and read path move to Rust, acceptance bar = beat rg on every recorded bench row. The open fork is dependency posture: a required compiled dependency, or an optional accelerator behind an import seam with the pure-Python implementation as the always-installable fallback (wheels for the platform matrix either way). Downstream of the fork: fold ownership (Rust reproduces `fold_content` pinned by the exhaustive orbit test, vs receiving pre-folded bytes).
- **Blocking:** spec 103 slices B–D (`specs/active/103-grep-pipeline-rust-core/`); resolved by slice A's packaging memo.
- **Options considered:** required extension (one path, no drift risk, sdist needs a toolchain); optional accelerator + fallback seam (installs anywhere, CI runs both sides, bench gate binds the accelerated path); numpy-only vectorization (declined by Clay 2026-08-16 — clears one loop, not the class).
- **Status:** open — owned by spec 103 slice A
