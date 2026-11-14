# Candidate verifier brief for `v13-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) h03-mutations. Repository: . at commit 3586750 (read-only).

## 1. Verifier instructions (verbatim)

```text
You did not write this candidate. Try to refute it from repository source and bounded
local evidence. Do not contact deployed endpoints or external/shared services. Run
target-controlled code only inside the approved OS-enforced sandbox: no external
network, empty allowlisted environment, read-only target and tools, scratch-only
writes, and explicit low resource and wall-clock limits. If any control is unavailable,
do not execute; retain the exact missing capability as a needs_validation blocker.
Treat every scratch entry as target-controlled after execution. After the sandbox and
all its processes terminate, only trusted parent-side code may promote a predeclared
scratch-relative file, following the promotion procedure block included verbatim in
this prompt. You and target code never write retained artifacts. If promotion is
unavailable or fails, do not use that file as evidence.

1. Verify every trace and evidence file, positive line number, scope, and description.
   Confirm the first entry is a real lower-trust entrypoint and the last is the
   claimed sink or boundary effect.
2. Reconstruct the strongest source-visible validation, identity, authorization,
   normalization, lifecycle, framework, and containment controls on the path.
   Where the architecture summary names a comparable baseline, note whether it
   shares the pattern — as calibration, never as grounds to dismiss.
3. For a proposed confirmed candidate, independently reproduce the minimum observed
   result when possible. Verify inputs, interface shape, conditions, and affected
   dummy principal/resource. Do not infer a stronger result or continue after it.
4. Verify that likelihood, impact, confidence, and the proposed source fix match only
   what the evidence establishes.
5. For a proposed needs_validation candidate, decide whether the blocker is genuinely
   outside source/local observation. If source refutes the trace, reject it. If the
   missing fact remains decisive, keep needs_validation and make the local and
   owner-observed plans exact and non-destructive.
6. Preserve the fingerprint for the same source-derived root cause across every state.

Return exactly one JSON object and no surrounding prose:
{"decision": "confirmed|needs_validation|rejected", "record": { ... }}
where record exactly matches the decision's verdict branch of the schema included
in this prompt. A corrected record replaces the hunter's wording.
```

## 2. Promotion procedure (verbatim)

```text
Artifact promotion procedure (trusted parent-side code only):
Reference only for you: the parent performs these steps; you never perform them.

Before execution, the parent opens and retains trusted, non-inheritable directory
descriptors for the agent's scratch/ and artifacts/ roots, and records an allowlist
of expected scratch-relative artifact files plus explicit per-file and cumulative
byte limits. Never pass those descriptors to the agent or sandbox. After the sandbox
and all its processes terminate, trusted parent-side code promotes each allowlisted
file separately:

1. Validate the declared relative path: reject absolute, empty, `.`, `..`, or
   symlinked components.
2. Walk each parent component from the retained scratch-root descriptor with
   no-follow directory-relative operations; never reopen by path.
3. Open the leaf no-follow and nonblocking.
4. Verify with `fstat` that it is a regular file with link count exactly one and
   within the recorded per-file and cumulative byte limits.
5. Enforce those limits again while reading from that descriptor.
6. Copy exactly the verified size, repeat `fstat`, and reject a changed identity,
   type, link count, or size.
7. For the destination, walk every parent component from the retained
   artifacts-root descriptor with no-follow directory-relative operations; require
   each existing component to be a real directory, and create any missing directory
   exclusively before reopening and verifying it no-follow.
8. Create the leaf exclusively without following links, verify that the opened
   destination is a regular file with link count exactly one, and copy from the
   verified source descriptor without reopening either path.
9. Use equivalent race-safe APIs on non-POSIX systems.
10. Never recursively copy or glob scratch, extract an archive into artifacts, or
    open or promote a symlink, FIFO, socket, device, directory, hard-linked file,
    changing file, or file that exceeds its bound.
11. If any check is unavailable, cannot be enforced, or fails, discard the scratch
    entry; if it is decisive evidence, retain `needs_validation` with the exact
    promotion blocker.
```

## 3. The candidate (as the hunter proposed it)

```json
[
 {
  "proposed_verdict": "needs_validation",
  "fingerprint": "vfs/storage/database/topology-subtree-authorized-before-collection",
  "title": "copy, move, delete and sweep authorize a subtree once, then act on rows collected later, including a concurrent rival's rows",
  "description": "The topology and trash verbs judge the caller's rung over the source subtree once, inside the gate (WriteGate.subtrees). Later statements re-collect the rows they act on, live: copy and move fetch the subtree, delete stamps every live descendant by LIKE, and the sweep purge loops until its scope reads empty. The serialization point blocks only other serialized verbs; ordinary writes never wait on it. A row that another principal writes into the subtree between the gate and the collection is therefore copied, moved, tombstoned or permanently purged, although the caller holds no rung on it. Example: alice holds rights over her directory only through the owner floor, and bob holds add there. If bob's write lands in the window, alice's copy duplicates bob's file (which she cannot read) into her own space, owned by her, and she can then read it. Alice's sweep in the same window destroys bob's file for good. Run sequentially, all of these operations are permission_denied. A likely fix: inside the mutation, re-check each collected row with resolution.at(rung).admits(path, owner_id, everyone_level) and redrive or refuse on a miss. Alternatively, make child creations take a shared lock on the serialization row.",
  "claimed_root_cause": "The authorization decision (WriteGate.subtrees, rights.py:730-781) runs over a point-in-time read. The mutation scope is re-collected afterwards by path pattern (topology.py:186 _fetch_subtree, topology.py:397 _descendant_rewrites, trash.py:483 _tombstone_descendants, trash.py:567 the _purge loop). Writes do not serialize with these verbs (serialized.py:115-118), and the server engines' topology isolation is READ COMMITTED (dialects.py:437,503). Nothing re-judges rows that arrived after the gate.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1692,
    "scope": "DatabaseStorage._execute_transfer.gate",
    "description": "A copy or move source is authorized by subtrees(sources, passing) at read or read_write. Delete (backend.py:763) and sweep (backend.py:862) make the same call."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 763,
    "scope": "WriteGate._refused_beneath",
    "description": "Pages through the rows that exist beneath the root at that moment and checks each with rights.admits. A row created afterwards is never seen."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/serialized.py",
    "line": 117,
    "scope": "serialize",
    "description": "The lock row is read only by serialized verbs, so ordinary writes and creations commit concurrently with copy, move, delete and sweep on every server engine."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/topology.py",
    "line": 186,
    "scope": "transfer_rows",
    "description": "After the gate, the subtree is re-read live by subtree_filter. Under READ COMMITTED it includes a rival's newly committed rows."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/trash.py",
    "line": 567,
    "scope": "_purge",
    "description": "The sweep purge arm repeats its collection until the scope is empty, specifically to catch late children, and hard-deletes them without any authorization check."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/topology.py",
    "line": 452,
    "scope": "_execute_copy",
    "description": "Every collected row, including the rival's, is minted at the destination with owner_id set to the copier and the destination label, and its body is copied (topology.py:479-515). The copier can then read it."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/trash.py",
    "line": 483,
    "description": "_tombstone_descendants stamps every live row under the claimed directory, and its docstring states that a child a rival landed after the snapshot rides with its parent."
   },
   {
    "file": "src/vfs/storage/backends/database/trash.py",
    "line": 381,
    "description": "The sweep purge arm calls _purge with subtree_filter and no proof predicate."
   },
   {
    "file": "src/vfs/storage/backends/database/topology.py",
    "line": 397,
    "scope_note": null,
    "description": "A move rewrites descendants collected live after the root claim, so a late arrival is relocated to the destination with the destination's label."
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 437,
    "description": "PostgreSQL topology_isolation is READ COMMITTED (MariaDB matches at line 503), so each statement sees rows committed after the gate."
   },
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 754,
    "description": "subtrees skips the read only when the caller's spans cover the subtree whole. The gap is reachable exactly where rights are partial: an owner floor, or a deeper posture narrowing a region that is still empty."
   }
  ],
  "blockers": [
   "The decisive interleaving needs a real concurrent commit on a server engine (PostgreSQL, MSSQL, MariaDB or Oracle). Real engines and Docker are prohibited in this sandbox. SQLite's BEGIN IMMEDIATE serializes all writers, so the race cannot happen locally.",
   "The local evidence injects the rival's write on the victim's own session after WriteGate.subtrees. It simulates READ COMMITTED visibility; it is not an observed commit from a second connection.",
   "The exact window per verb on each engine is unobserved: copy (gate to _fetch_subtree), move (gate to point_row, after which the root version guard applies), delete (gate to fetch_snapshot, after which the root version guard applies), and sweep (gate to the last purge collect)."
  ],
  "validation_plan": {
   "local": "Add an engine-leg test to tests/storage/database/test_races.py, run through the db_test skill against the postgres, mssql, mariadb and oracle legs. Posture '/' is none. Alice writes /team/alice/a.txt while holding add on /team; that grant is then revoked. Bob is granted add on /team/alice, and alice add on /mine. Install a self-clearing handler on 'transfer:post-snapshot' that commits bob's write of /team/alice/s.txt on its own session, then run alice's copy of /team/alice to /mine/c. Assert the copy is refused, or that /mine/c/s.txt does not exist. Repeat for sweep on 'purge:post-collect' and assert bob's row survives. For delete, add a seam between the gate and fetch_snapshot."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23delete%20restore%20sweep%20move%20copy::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Ftrash.py%23subtree%20checks::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Chained%20vulnerabilities%20and%20trust%20boundaries",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/trash.py",
   "src/vfs/storage/backends/database/labels.py"
  ],
  "invariant": "restore re-authorizes the tombstoned root under current rights and labels, and a directory restore needs read_write on every row beneath it",
  "method": "source",
  "result": "The restore permit (backend.py:798-828) checks list visibility, then read_write on the root at its own path, owner and stored label. For a directory it also runs subtrees(read_write) over every live and tombstoned row beneath. Relabels also rewrite tombstoned rows (labels.py:35), so a stored label always matches the current posture. The revived set (rows whose trash_root_id is the root) always lies inside the root's subtree, because tombstoned sources cannot be moved (topology.py:160-163). Restore and delete both serialize on the lock row (trash.py:299). No stale-rights restore path was found.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23delete%20restore%20sweep%20move%20copy::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Ftrash.py%23subtree%20checks::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Chained%20vulnerabilities%20and%20trust%20boundaries",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/trash.py",
   "src/vfs/storage/backends/database/versions.py",
   "src/vfs/models/version.py",
   "src/vfs/base.py"
  ],
  "invariant": "sweep at the trash head needs whole-mount read_write; the purge arm needs read_write on the target and its whole subtree; history left after delete or sweep cannot be read",
  "method": "source",
  "result": "Sweep at TRASH_ROOT runs subtrees([ROOT], read_write) (backend.py:857-859). Any other address runs targets(modify) plus subtrees(read_write) (backend.py:860-862). This matches the documented developer-plane contract, under which the purge of live rows is intended. The purge deletes the content, blob, version, version_subject, chunk, segment and edge rows for each id (trash.py:567-591). vfs_versions has no reader anywhere in src (only the mint at versions.py:151-153 and the purge at trash.py:581), and base.py exposes no history verb, so retained versions of tombstoned rows are not disclosed through any verb.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23delete%20restore%20sweep%20move%20copy::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Ftrash.py%23subtree%20checks::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Chained%20vulnerabilities%20and%20trust%20boundaries",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/topology.py",
   "src/vfs/storage/backends/database/backend.py"
  ],
  "invariant": "move/copy never replace an occupant; moved and copied rows take the destination's posture label; a copy is owned by the copier",
  "method": "source",
  "result": "Any occupied destination, tombstoned or live, is refused with exists (topology.py:173-177). Move stamps label_of(destination postures) on the root and all descendants (topology.py:315,370-377). Copy stamps owner_for(authority) and the destination label (topology.py:452-453) and copies only live rows. Copying readable data to a place where others can read it is ordinary read-then-write capability and is intended. When the subtree is judged sequentially, these paths are sound.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23delete%20restore%20sweep%20move%20copy::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Ftrash.py%23subtree%20checks::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Chained%20vulnerabilities%20and%20trust%20boundaries",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/topology.py",
   "src/vfs/storage/backends/database/trash.py",
   "src/vfs/storage/backends/database/serialized.py",
   "src/vfs/storage/backends/database/dialects.py"
  ],
  "invariant": "the rows a topology verb mutates or duplicates are exactly the rows its subtree gate authorized",
  "method": "local",
  "result": "Sequential controls work: alice (owner floor only) is denied when copying, sweeping or deleting her directory once bob's file is inside it. With a deterministic schedule that inserts bob's legitimate write on the same session after WriteGate.subtrees passes, each of the three verbs succeeds and acts on bob's row. The copy duplicated bob's unreadable file into /mine/c, owned by alice, and alice then read 'BOB SECRET'. The sweep destroyed bob's file permanently, and the delete tombstoned it. The sandbox is SQLite only, and SQLite's BEGIN IMMEDIATE serializes all writers, so a real concurrent commit cannot happen here.",
  "artifact": "agents/h03-mutations/artifacts/evidence/topology-subtree-race.txt"
 }
]
```

## 5. Architecture facts

# vfs architecture summary (run-1, commit 3586750)

## Product, principals, resources

vfs (`vfs-py`) is an embeddable Python library: "governed data access for AI agents". A host application builds an `AsyncVirtualFileSystem` (or the sync `VirtualFileSystem`, `src/vfs/sync.py`), mounts storages (`DatabaseStorage` over SQLAlchemy, `InMemoryStorage` over a private SQLite), and exposes 25 verbs (`src/vfs/ops.py:36-62`) to agents and ETL pipelines. There is no server, CLI, or MCP surface in source; the MCP surface is planned.

Principals (`src/vfs/authority.py`): a caller is an `Authority` (subjects, actor, narrowing, provenance). Kinds: user, service, system, anonymous. vfs does not authenticate: the host constructs the Authority and passes it per call or binds it in an `AsyncSession` (`src/vfs/session.py`). An unnamed router call becomes `default_authority` or anonymous (`src/vfs/base.py:3094-3107`); an unnamed direct storage call becomes system (`src/vfs/storage/backends/database/backend.py:1493-1495`). `Authority.system()` bypasses row rights. The lower-trust principals the library itself must contain are: **anonymous**, **a named subject or subject set** (agent acting for a user, `on_behalf_of`), and **group members**. The host, the operator who configures mounts/schema/URLs/providers, and system are trusted.

Protected resources: stored entries (text and binary bodies), their derived copies (chunks, postings, lexical/vector indexes, renderings, edges, versions, trash tombstones), grant rows and postures, group membership, and the process itself (memory safety of the Rust extension, availability of the host process shared by many agents). Release authority over PyPI `vfs-py` is a further resource.

## Comparable baseline

Authorization follows a ReBAC/ladder model comparable to SpiceDB/OpenFGA (row grants, groups, subtree inheritance); grep follows ripgrep and Rust `regex` (linear time). Agent filesystems (mirage, agentfs, deepagents BackendProtocol) are the product comparables (`context/research/README.md:48-59`). Calibration only.

## Stack and local limits

Python ≥3.11 (pydantic, SQLAlchemy async, aiosqlite, sqlite-vec, unidiff, pyyaml safe_dump), Rust crate `crates/vfs-core` via pyo3 abi3 (regex, rayon, memchr, ~55 tree-sitter C grammars), maturin build. Optional extras: pypdf, python-docx, python-pptx, openpyxl; openai, langchain, model2vec; asyncpg, aioodbc, aiomysql, oracledb. Dialect profiles: SQLite, PostgreSQL, MSSQL, MariaDB, Oracle, GENERIC floor (`dialects.py:389-579`). Local execution: `.venv/bin/python -I` under `tools/sandbox-run.py` (no network incl. loopback, empty env, scratch-only writes, CPU/wall/RSS caps). SQLite and InMemoryStorage only; real engines, Docker, `uv sync`, cargo builds, providers and HF downloads are prohibited. The prebuilt `src/vfs/_native.abi3.so` is assumed current with source (unverified).

## Entry surfaces and important paths

1. **Verb arguments** (paths, content/data/entries, edit old/new, glob/grep patterns, glean query, graph depth/limit, edge targets, grant principals/levels, `observations` row targets) → `params.py` gate (types, choices, int ≤ 2^31-1; no string-length caps) → `base.py` `_gate_entry` (capability/`deny_ops`, reserved paths, PermissionMap for WRITE_GATED_OPS) → storage.
2. **Row rights in `DatabaseStorage`**: `rights.py` `resolve_authority`/`Visibility`/`WriteGate`, `grants.py` range algebra, owner floor, postures, `RightsCache`. Search filters per row (`grep.py:261,303`, `glean.py:380,575,653`, `graph.py:225-307`).
3. **SQL construction**: SQLAlchemy Core with binds; raw `text()` at `labels.py:470-503` (operator schema interpolated), profile-constant statements (`rights.py:518-520`, `engine.py:422-469,655`), LIKE escaping (`descent.py:239-253`, `reads.py:975-1004`), chunked IN lists.
4. **Untrusted bytes → parsers**: renderers (`src/vfs/rendering/*`, `RenderLimits` in `seam.py:43-84`, cooperative clock); tree-sitter chunking and markdown links in Rust (`chunk.rs`, `links.rs`); notebooks via `json.loads`.
5. **Rust FFI** (`crates/vfs-core/src/python.rs`): matcher, chunker, tokenizer, posting/lexical decode of DB-stored blobs, centrality with `unsafe align_to`; panics surface as `PanicException` (BaseException).
6. **Pattern compilers**: glob → Python `re` (`pattern_matching/glob.py:518-563`); grep gate via `sre_parse` then Rust regex; fuzzy edit replacers with O(n²) Levenshtein (`storage/replace.py:61-255`).
7. **Agent content**: `/.agents/skills|tools` entries, skill manifests (`skills.py`), markdown links becoming `links` edges.
8. **Release**: `.github/workflows/publish.yml` (release:published + dispatch; OIDC trusted publishing in `environment: pypi`), `scripts/check_release_tag.py`, tag-pinned actions, CI `uv sync` without `--locked`.

## Trust boundaries and strongest control

- Anonymous/named caller → stored rows: row rights in storage (`rights.py:322-891`); router maps only gate writes.
- Caller → grant/posture writes: `read_write` at the addressed path (`rights.py:894-1035`); membership verbs system-only (`rights.py:1339-1346`).
- Caller → mount boundary: bind-path filtering (`base.py:3117-3136`), cross-mount move/copy/edges refused.
- Caller → reserved namespaces `/.vfs`, `/.agents`: `paths.py:824-840`.
- Caller input → SQL: bound parameters, escapes.
- Caller bytes → process: RenderLimits, posting validation, budgets (`grep.py:120-126`).
- Contributor/PR → release artifact: workflow triggers, `environment: pypi` (protection unobserved), tag check.

## Starting paths

`src/vfs/base.py`, `src/vfs/params.py`, `src/vfs/paths.py`, `src/vfs/permissions.py`, `src/vfs/authority.py`, `src/vfs/session.py`, `src/vfs/sync.py`, `src/vfs/storage/grants.py`, `src/vfs/storage/backends/database/`, `src/vfs/storage/backends/memory.py`, `src/vfs/storage/replace.py`, `src/vfs/pattern_matching/`, `src/vfs/rendering/`, `src/vfs/models/`, `src/vfs/skills.py`, `src/vfs/embedding/`, `crates/vfs-core/src/`, `.github/workflows/`, `scripts/`.

## Prior coverage

No prior vfs run and no compatible prior ledger; every unit is seeded `prior_status: "none"`. No carried exclusions.

## Companion selection

Selected: DATA-ISOLATION-AND-LIFECYCLE (multi-subject rows, derived search/index/edge copies, trash/restore/sweep), MEMORY-SAFETY-AND-BINARY (Rust FFI, unsafe, C tree-sitter parsers on untrusted bytes), RESOURCE-EXHAUSTION-AND-AVAILABILITY (caller patterns and bytes consume the host process shared by agents), SUPPLY-CHAIN-AND-RELEASE (CI and PyPI publish), AI-AND-LLM (the library is the tool layer agents call; `/.agents` content and `run` are model-facing actions). Excluded: WEB-PROTOCOL-AND-AUTH (no HTTP, token or session protocol in source), CLIENT-SIDE (no browser code), CLOUD-AND-DEPLOYMENT (no IaC; Docker is test-only), PROTOCOLS-RPC-AND-MESSAGING (no RPC or broker), DESKTOP-MOBILE-AND-LOCAL-IPC (no IPC or native app).

## 6. Relevant validation blocks (verbatim)

### DATA-ISOLATION-AND-LIFECYCLE.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name attacker or lower-trust principal, protected data/state, affected owner/tenant, alternate copy or operation, and unauthorized disclosure or mutation.
2. Cite both intended source-of-truth policy and the path that omits or disagrees with it. Confirm another layer does not enforce the same tenant/lifecycle condition.
3. Use local dummy tenants and non-sensitive fixtures to prove cross-scope access or stale lifecycle behavior. Stop at the minimum observable record or operation.
4. If external cache, object storage, replicas, analytics, backup, or retention policy is required, classify `needs_validation` and state the owner-observed check.
5. Return `confirmed` only with complete lineage and concrete boundary impact. Return `needs_validation` with the exact unresolved storage, ACL, invalidation, retention, or restore fact.

### Core candidate gate (verbatim)

```text
## Candidate gate

1. A candidate needs a complete repository-relative source trace and evidence for the
   claimed root cause, including the strongest source-visible control.
2. A proposed confirmed record needs a bounded local observed result, meaningful impact
   across a stated boundary, complete conditions, and no visible preventing layer.
3. Do not strengthen a crash into code execution, ordinary work into shared availability,
   or a same-principal action into privilege gain.
4. If a required fact is not source-visible or locally observable, use
   needs_validation. Name exact blockers; do not give it severity or speculative completion.
5. A missing best practice with no affected principal/resource is excluded or hardening,
   not a finding. A candidate disproved by source is not needs_validation.
6. Use the same source-derived fingerprint for the same root cause in every state.
   It must match `^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$` and must not include a line,
   wave, agent, severity, or verdict.
7. Return an empty candidate array when nothing survives these gates.
```

## 7. Source/local execution boundary

- Scratch, the only place you or target code may write: `./agents/v13-p3/scratch/`. Never write `./agents/v13-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v13-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v13-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs/storage/database/topology-subtree-authorized-before-collection` unless you identify a genuinely different root cause.

### `confirmed` branch (verbatim)

```json
{
 "type": "object",
 "description": "A source-grounded vulnerability that was independently demonstrated.",
 "properties": {
  "verdict": {
   "type": "string",
   "const": "confirmed"
  },
  "fingerprint": {
   "type": "string",
   "minLength": 1,
   "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$",
   "description": "A stable source-derived identifier that does not change between validation states."
  },
  "title": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "description": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "root_cause": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "intended_behavior": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "trace": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "kind": {
      "type": "string",
      "enum": [
       "entrypoint",
       "propagation",
       "sink"
      ]
     },
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "scope": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "kind",
     "file",
     "line",
     "scope",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "evidence": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "file",
     "line",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "conditions": {
   "type": "array",
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "kind": {
      "type": "string",
      "enum": [
       "authentication_level",
       "authorization_role",
       "user_interaction",
       "system_configuration",
       "network_routing",
       "environmental_dependency",
       "data_state",
       "timing_dependency",
       "third_party_dependency"
      ]
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "kind",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "execution": {
   "type": "object",
   "description": "Target-neutral reproduction in the target's native interface.",
   "properties": {
    "attacker_perspective": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    },
    "payloads": {
     "type": "array",
     "minItems": 1,
     "uniqueItems": true,
     "items": {
      "type": "string"
     }
    },
    "instructions": {
     "type": "array",
     "minItems": 1,
     "items": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "observed_result": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    }
   },
   "required": [
    "attacker_perspective",
    "payloads",
    "instructions",
    "observed_result"
   ],
   "additionalProperties": false
  },
  "remediation": {
   "type": "object",
   "properties": {
    "strategy": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    },
    "code_changes": {
     "type": "array",
     "items": {
      "type": "object",
      "properties": {
       "file_name": {
        "type": "string",
        "minLength": 1
       },
       "fixed_code": {
        "type": "string"
       }
      },
      "required": [
       "file_name",
       "fixed_code"
      ],
      "additionalProperties": false
     }
    }
   },
   "required": [
    "strategy"
   ],
   "additionalProperties": false
  },
  "severity": {
   "type": "object",
   "properties": {
    "likelihood": {
     "type": "object",
     "properties": {
      "score": {
       "type": "string",
       "enum": [
        "informational",
        "low",
        "medium",
        "high",
        "critical"
       ]
      },
      "reason": {
       "type": "string",
       "minLength": 1,
       "visibleContent": true
      }
     },
     "required": [
      "score",
      "reason"
     ],
     "additionalProperties": false
    },
    "impact": {
     "type": "object",
     "properties": {
      "score": {
       "type": "string",
       "enum": [
        "informational",
        "low",
        "medium",
        "high",
        "critical"
       ]
      },
      "reason": {
       "type": "string",
       "minLength": 1,
       "visibleContent": true
      }
     },
     "required": [
      "score",
      "reason"
     ],
     "additionalProperties": false
    },
    "overall_severity": {
     "type": "string",
     "enum": [
      "informational",
      "low",
      "medium",
      "high",
      "critical"
     ]
    }
   },
   "required": [
    "likelihood",
    "impact",
    "overall_severity"
   ],
   "additionalProperties": false
  },
  "confidence": {
   "type": "object",
   "properties": {
    "score": {
     "type": "string",
     "enum": [
      "low",
      "medium",
      "high"
     ]
    },
    "reason": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    }
   },
   "required": [
    "score",
    "reason"
   ],
   "additionalProperties": false
  }
 },
 "required": [
  "verdict",
  "fingerprint",
  "title",
  "description",
  "root_cause",
  "intended_behavior",
  "trace",
  "evidence",
  "conditions",
  "execution",
  "remediation",
  "severity",
  "confidence"
 ],
 "additionalProperties": false
}
```

### `needs_validation` branch (verbatim)

```json
{
 "type": "object",
 "description": "A source-grounded candidate whose decisive validation is blocked.",
 "properties": {
  "verdict": {
   "type": "string",
   "const": "needs_validation"
  },
  "fingerprint": {
   "type": "string",
   "minLength": 1,
   "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$"
  },
  "title": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "description": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "claimed_root_cause": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "trace": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "kind": {
      "type": "string",
      "enum": [
       "entrypoint",
       "propagation",
       "sink"
      ]
     },
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "scope": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "kind",
     "file",
     "line",
     "scope",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "evidence": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "file",
     "line",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "blockers": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "string",
    "minLength": 1,
    "visibleContent": true
   }
  },
  "validation_plan": {
   "type": "object",
   "properties": {
    "local": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    },
    "deployment": {
     "type": "string",
     "minLength": 1,
     "visibleContent": true
    }
   },
   "additionalProperties": false
  }
 },
 "required": [
  "verdict",
  "fingerprint",
  "title",
  "description",
  "claimed_root_cause",
  "trace",
  "evidence",
  "blockers",
  "validation_plan"
 ],
 "additionalProperties": false
}
```

### `rejected` branch (verbatim)

```json
{
 "type": "object",
 "description": "A source-grounded candidate refuted during validation.",
 "properties": {
  "verdict": {
   "type": "string",
   "const": "rejected"
  },
  "fingerprint": {
   "type": "string",
   "minLength": 1,
   "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$"
  },
  "title": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "description": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "claimed_root_cause": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  },
  "trace": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "kind": {
      "type": "string",
      "enum": [
       "entrypoint",
       "propagation",
       "sink"
      ]
     },
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "scope": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "kind",
     "file",
     "line",
     "scope",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "evidence": {
   "type": "array",
   "minItems": 1,
   "uniqueItems": true,
   "items": {
    "type": "object",
    "properties": {
     "file": {
      "type": "string",
      "minLength": 1
     },
     "line": {
      "type": "integer",
      "minimum": 1
     },
     "description": {
      "type": "string",
      "minLength": 1,
      "visibleContent": true
     }
    },
    "required": [
     "file",
     "line",
     "description"
    ],
    "additionalProperties": false
   }
  },
  "reason": {
   "type": "string",
   "minLength": 1,
   "visibleContent": true
  }
 },
 "required": [
  "verdict",
  "fingerprint",
  "title",
  "description",
  "claimed_root_cause",
  "trace",
  "evidence",
  "reason"
 ],
 "additionalProperties": false
}
```
