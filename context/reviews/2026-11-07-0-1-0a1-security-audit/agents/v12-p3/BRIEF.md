# Candidate verifier brief for `v12-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w3a-labels. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs/storage/database/labels:mint-reads-posture-outside-revision-lock-stale-everyone-level",
  "title": "A write, move or copy that read the posture before a tightening commits keeps the old, more open everyone_level after the relabel clears its mark",
  "description": "entries.everyone_level is a derived copy of the everyone posture. Once no relabel mark covers a row, readers trust it outright. Posture writes and Relabeller chunks serialize on the revision lock. The mint paths do not: write/mkdir labels_for at writes.py:379, and move/copy posture_beneath at topology.py:197 feeding lines 315, 373 and 453. They read the grants rows with plain SELECTs, outside that lock, and never re-check the relabels table. Take a write W whose snapshot predates a posture commit P that tightens a path to none. Postgres and MariaDB pin W's snapshot at its first statement, under op_isolation REPEATABLE READ. P's Relabeller runs and clears the mark while W is still open. The relabel cannot see W's uncommitted rows, so it skips them. W then commits its rows stamped with the old level, and no mark remains. Any named principal with no grant (bob) can then read the row, and anonymous grep and glob list it, although the posture says none. Where the old level was read_write, the stale label also admits modification. The label stays wrong until some later posture change covers that path, because nothing in src calls rebuild_labels. Locally, the consequence is shown on SQLite by passing the mint its pre-commit posture read. SQLite's BEGIN IMMEDIATE prevents the real interleaving, as the real seam showed.",
  "claimed_root_cause": "labels_for and posture_beneath read the everyone posture rows without the revision lock (or any shared lock on it) and without consulting inflight relabel marks. The Relabeller rewrites only rows visible to its own statement, then clears the mark. A mint whose posture read predates a posture commit, and whose commit follows the relabel's pass over its path, therefore stamps a stale label that no mark covers.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 686,
    "scope": "DatabaseStorage.write",
    "description": "The write verb runs its plan via _execute_write (backend.py:1666-1673) with op_execution_options. On Postgres and MariaDB that stamps REPEATABLE READ (dialects.py:436,500), so the snapshot is fixed at the first statement."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 379,
    "scope": "_apply",
    "description": "After staging, labels_for is called for the creates. No hold_revision, no locking read, no relabels check precedes it in the write transaction."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/labels.py",
    "line": 117,
    "scope": "posture_rows",
    "description": "A plain SELECT of the '*' grants rows. Under the write's snapshot it returns the posture as it stood before a concurrent posture commit."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/topology.py",
    "line": 197,
    "scope": "transfer_rows",
    "description": "Move and copy compute posture_beneath with the same unlocked read (labels.py:456). They stamp it at topology.py:315 (moved root), 373 (descendants) and 453 (copied rows). The serialize() point is the lock table, not the revision lock."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 1034,
    "scope": "set_posture",
    "description": "The posture write commits the row and the relabel mark together under the revision bump (backend.py:1594). The mark protects readers only while it stands."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/labels.py",
    "line": 248,
    "scope": "Relabeller.step",
    "description": "Each chunk takes hold_revision and rewrites rows its statement sees (labels.py:350 and the range form). It cannot see the concurrent write's uncommitted rows. The last chunk deletes the mark and bumps the revision (labels.py:265-266)."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/grants.py",
    "line": 491,
    "scope": "Rights.admits",
    "description": "With no hole standing, a row whose stored everyone_level is at least the needed rung is admitted. Visibility and WriteGate (rights.py:747, backend.py:821) and grep's per-row filter (grep.py:261) admit bob and anonymous to the stale-labeled row."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/labels.py",
    "line": 1,
    "description": "The module doc says the label is derived and in step by construction: 'stamped at every mint' from the posture rows, with the mark in force until the relabel settles. Nothing ties the mint's read to the lock that orders posture commits."
   },
   {
    "file": "src/vfs/storage/backends/database/revision.py",
    "line": 60,
    "scope_note": "",
    "description": "hold_revision is the lock that relabel chunks take so that 'a chunk never writes a level a rival posture change has already replaced'. The mint paths do not take it."
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 436,
    "description": "Postgres pins op_isolation REPEATABLE READ for every op connection, writers included. MariaDB does the same at line 500. The write's posture read therefore comes from its first statement's snapshot."
   },
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 394,
    "description": "The strongest visible control: anonymous calls addressing a path are judged from the posture rows, not the label. So an anonymous direct read stays refused, but list and search verbs and every named principal's reads trust the label."
   },
   {
    "file": "src/vfs/storage/backends/database/engine.py",
    "line": 654,
    "description": "On SQLite, writers open BEGIN IMMEDIATE, so a posture commit cannot land inside a write's window. That is why the real interleaving is unobservable locally (the seam rival got vfs.conflict)."
   }
  ],
  "blockers": [
   "The decisive interleaving is impossible on SQLite. Writers hold BEGIN IMMEDIATE from the first read (engine.py:649-654), and the real write:before-apply seam rival posture failed with vfs.conflict. Real engines (Postgres, MariaDB, MSSQL, Oracle) are prohibited in this sandbox. Locally only the consequence was demonstrated, by passing the mint its pre-commit posture read.",
   "Postgres REPEATABLE READ: when the created row's existing parent lies inside the tightened region, the relabel rewrites the parent. The write's guarded parent bump (writes.py:1026) should then fail with 40001 and redrive with a fresh snapshot. That would leave only the cases where the posture is set at the created path itself (or at a directory the batch itself creates), plus move/copy under READ COMMITTED. This engine behaviour is unobserved.",
   "MariaDB: whether innodb_snapshot_isolation (default ON from 11.6, error 1020) turns the parent bump into a restart, and whether a Relabeller range UPDATE (a current read with next-key locks) blocks on and then relabels a concurrently moved row's new path index entry, are both unobserved.",
   "MSSQL: under default locking READ COMMITTED (no op_isolation), the relabel UPDATE would block on the writer's uncommitted inserted key and then relabel it. That would narrow the window to the gap between labels_for and the insert statement. Under READ_COMMITTED_SNAPSHOT the row-versioned scan would skip it. Which mode a deployment runs is a database setting outside source.",
   "Oracle: the statement-level consistent read in the relabel UPDATE is expected to skip uncommitted inserted or moved rows, leaving the window from labels_for or posture_beneath to commit. Unobserved."
  ],
  "validation_plan": {
   "local": "Rerun agents/w3a-labels/artifacts/evidence/stale_label.py under the sandbox. Experiments exp2 and exp3 show the consequence on SQLite: bob reads 'TOPSECRET payroll', and anonymous grep and glob list /eng/secret.md, at everyone_level=2 under posture none with no pending marks. rebuild_labels repairs it. exp1 shows SQLite refusing the interleaving through the real seam.",
   "deployment": "Owner-run on the db_test containers (VFS_TEST_POSTGRES_URL etc.), following tests/storage/database/test_races.py. Grant alice read_write at /, set root posture read and mkdir /eng. Install a self-clearing handler on 'write:before-apply' that awaits storage.posture(path=/eng/secret.md, posture='none', authority=system) to completion on its own session, then have alice write /eng/secret.md. After commit, assert relabels is empty and read everyone_level for /eng/secret.md. Expected if vulnerable: 2. Then assert storage.read(path=/eng/secret.md, authority=Authority.of(Principal('bob'))) succeeds. Repeat on 'transfer:post-collect' with move and copy <tmp>/draft.md to /eng/secret.md. Repeat with the posture on an existing directory /eng to observe whether the parent-bump 40001 or 1020 redrive closes that case on each engine."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fwrites.py%23_apply%20labels_for%20at%20mint%2C%20and%20topology.py%23posture_beneath%20at%20move%2Fcopy%2Frestore::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Flabels.py%23everyone_level%2C%20a%20stored%20copy%20of%20the%20posture%2C%20kept%20in%20step%20by%20Relabeller%20under%20the%20revision%20lock::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Deletion%2C%20revocation%2C%20and%20lifecycle%20attack%20classes",
  "agent_id": "w3a-labels",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/labels.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/topology.py",
   "src/vfs/storage/backends/database/revision.py",
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/serialized.py",
   "src/vfs/storage/backends/database/dialects.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/trash.py",
   "src/vfs/storage/grants.py"
  ],
  "invariant": "A row minted (write/mkdir/copy) or relocated (move) after a posture change commits must carry the label of the posture in force, or stay covered by a standing relabel mark until it is relabelled. The mint must not stamp a label from a posture read that predates a posture commit whose Relabeller has already passed the row's path.",
  "method": "source",
  "result": "Posture writes bump the revision lock (backend.py:1594) and plant the mark in the same transaction (rights.py:1032-1034). Each Relabeller chunk takes hold_revision (labels.py:248), rewrites only rows its statement can see (labels.py:350 and the range form), and the last chunk deletes the mark and bumps the revision (labels.py:265-266). The mint paths take no lock and check nothing: writes.py:379 labels_for and topology.py:197 posture_beneath are plain SELECTs of the grants rows (labels.py:117,456). They also do not re-check relabels marks. Writes run in _execute_write under op_isolation REPEATABLE READ on Postgres and MariaDB (dialects.py:436,500; backend.py:1666-1673), so the snapshot is pinned at the write's first statement, well before labels_for. Topology runs under READ COMMITTED behind the lock-table point (serialized.py serialize), and that point is not the revision lock. Once the mark clears, Rights.admits trusts the stored label outside holes (grants.py:491). No src path reconciles labels: rebuild_labels has no caller in src. The anonymous direct-path refusal (rights.py:394, unauthenticated_at) reads the posture rows and still holds. List and search verbs (grep, glob) and every named caller's reads trust the label. On SQLite, BEGIN IMMEDIATE holds the writer lock from the plan's first read (engine.py:649-654), so the posture commit and its relabel cannot fall inside a write's window. On Postgres REPEATABLE READ, a write whose parent row the relabel rewrote fails its guarded parent bump with 40001 and redrives, which closes the window by accident. That leaves the posture-at-the-created-path case open (parent outside the region), along with the move/copy cases under READ COMMITTED.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fwrites.py%23_apply%20labels_for%20at%20mint%2C%20and%20topology.py%23posture_beneath%20at%20move%2Fcopy%2Frestore::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Flabels.py%23everyone_level%2C%20a%20stored%20copy%20of%20the%20posture%2C%20kept%20in%20step%20by%20Relabeller%20under%20the%20revision%20lock::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Deletion%2C%20revocation%2C%20and%20lifecycle%20attack%20classes",
  "agent_id": "w3a-labels",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/seams.py",
   "src/vfs/storage/backends/database/engine.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/backend.py"
  ],
  "invariant": "On SQLite, can a posture commit plus its relabel be staged inside a write's window through the real write:before-apply seam?",
  "method": "local",
  "result": "No. The rival posture(/eng/secret.md, none), run on its own session from the seam inside alice's write, failed with vfs.conflict ('a retryable engine conflict outlived 4 attempts') because the write holds BEGIN IMMEDIATE. The write committed with label 2 and the posture was never written, so the stored state is consistent. SQLite's writer serialization prevents the real interleaving locally.",
  "artifact": "agents/w3a-labels/artifacts/evidence/stale-label-run.json"
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fwrites.py%23_apply%20labels_for%20at%20mint%2C%20and%20topology.py%23posture_beneath%20at%20move%2Fcopy%2Frestore::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Flabels.py%23everyone_level%2C%20a%20stored%20copy%20of%20the%20posture%2C%20kept%20in%20step%20by%20Relabeller%20under%20the%20revision%20lock::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Deletion%2C%20revocation%2C%20and%20lifecycle%20attack%20classes",
  "agent_id": "w3a-labels",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/labels.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/topology.py",
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py"
  ],
  "invariant": "Consequence check. When the mint stamps a label read from a snapshot taken before the posture commit (emulated by passing the real labels_for/posture_beneath output from before the commit), is the row exposed after the mark clears, with nothing left to correct it?",
  "method": "local",
  "result": "Yes, in all three mint paths (write, move, copy). Setup: root posture read, then posture none at /eng/secret.md, settled (relabel rows=0, marks=[]). Alice's write of /eng/secret.md then stamped everyone_level=2 with no pending mark. bob (no grants) read it successfully and got content 'TOPSECRET payroll'. Anonymous grep and glob listed /eng/secret.md. Anonymous direct read was refused (unauthenticated), as expected. Move and copy behaved the same. Control (real fresh labels): label 0, and bob got not_found. Running rebuild_labels set the label to 0 and bob was refused, which shows the stored label is the sole cause.",
  "artifact": "agents/w3a-labels/artifacts/evidence/stale_label.py"
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

- Scratch, the only place you or target code may write: `./agents/v12-p3/scratch/`. Never write `./agents/v12-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v12-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v12-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs/storage/database/labels:mint-reads-posture-outside-revision-lock-stale-everyone-level` unless you identify a genuinely different root cause.

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
