# Candidate verifier brief for `v14-p3`

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
  "fingerprint": "vfs/storage/database/write-arbitration-absorb-without-reauthorization",
  "title": "A write that the gate judged as a fresh create (add rung) can overwrite a rival's concurrently created file through insert arbitration",
  "description": "write gates each target in upsert mode. A path absent at the gate is judged only at the create rung (add), which per ops.py lets a caller alter only its own rows. Occupied rows need contribute. If another principal creates the same path between the gate and alice's insert, the insert conflicts. On catch_retry engines (MSSQL, Oracle and the generic floor, all at the default READ COMMITTED), the occupant probe sees the rival's row and staged.absorb switches the create into a clobbering update of the rival's row. The update is guarded only by path and liveness, so an add-only caller replaces another owner's body. Sequentially, the same overwrite is permission_denied. The owner_id stays the rival's, and the replaced body goes to vfs_versions, which no verb reads. Under PostgreSQL's REPEATABLE READ pin the ON CONFLICT update should raise a serialization failure and redrive, and MariaDB's snapshot-blinded probe raises StaleSnapshot. Those engines are likely not affected, but this is unverified. A likely fix: when arbitration resolves to absorb or clobber for a non-whole authority, raise StaleSnapshot so that the redriven gate judges the occupant at contribute; or re-check the occupant's owner_id and everyone_level against the contribute rights before absorbing.",
  "claimed_root_cause": "WriteGate._decide authorizes an absent target at the create rung (rights.py:881-886). Insert arbitration in writes.py (_resolve_rows absorb at writes.py:628-631, and the upsert on_conflict_do_update at writes.py:489) then adopts a rival's row as the write target without re-applying the primary-rung check that an occupied target requires.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 700,
    "scope": "DatabaseStorage.write.run",
    "description": "gate.targets(..., 'upsert') runs on the committed state at that moment, and the target path is absent."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 884,
    "scope": "WriteGate._decide",
    "description": "An absent target passes when minting.reaches holds at the create rung (add). Contribute is never asked."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 444,
    "scope": "_insert_creates",
    "description": "catch_retry engines insert under a savepoint; the rival's committed row raises an IntegrityError, and the chunk is redriven row by row."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 631,
    "scope": "_resolve_rows",
    "description": "With overwrite (the default), a non-directory occupant at the same path is absorbed: the staged create becomes an update of the rival's entry_id."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 690,
    "scope": "_update_materials",
    "description": "The absorb arm updates the rival's row without a version guard, and _replace_bodies writes the caller's body into it. mint_versions (writes.py:404) records the rival's replaced body."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/ops.py",
    "line": 150,
    "description": "write needs contribute on an occupied target and add for a fresh name; the add rung alters only one's own rows (ops.py:117-121)."
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 468,
    "description": "MSSQL is catch_retry with no op_isolation pin, so the server default READ COMMITTED applies. Oracle (line 533) and the GENERIC floor (line 557) are the same."
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 436,
    "description": "PostgreSQL pins op_isolation to REPEATABLE READ, which should turn a concurrent ON CONFLICT update into a retryable serialization failure (unverified)."
   },
   {
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 100,
    "description": "The clobber columns replace the material state and clear the tombstone, but keep the rival's owner_id."
   }
  ],
  "blockers": [
   "The decisive race needs a second connection committing on MSSQL or Oracle at their default isolation (and a check of whether RCSI changes the probe's view). Real engines are prohibited in this sandbox, and SQLite serializes writers with BEGIN IMMEDIATE.",
   "The local evidence forces arbitration=catch_retry on SQLite and injects the rival write on the same session before _apply. It shows the code path; it does not show engine behavior.",
   "Whether PostgreSQL REPEATABLE READ and MariaDB actually redrive, rather than clobber, is unobserved."
  ],
  "validation_plan": {
   "local": "Add a race test to tests/storage/database/test_races.py and run it with the db_test skill on the mssql, oracle, postgres and mariadb legs. Posture '/' is none, and alice and bob each hold add on /drop. Install a self-clearing handler on 'write:before-apply' that commits bob's write of /drop/report.txt ('bob') on its own session, then run alice's write of /drop/report.txt ('ALICE'). Assert alice is refused (permission_denied after the redrive) and that a system read still returns 'bob'."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py",
   "src/vfs/ops.py",
   "src/vfs/storage/backends/database/labels.py"
  ],
  "invariant": "WriteGate._decide never lets a creation-rung (add) caller land on an occupied row it cannot modify; a hidden target reads as absent; a write onto a tombstone is judged as a restore",
  "method": "source",
  "result": "A creation passes when Rights.reaches holds: the add-level spans cover the path, or the posture label is at least add (grants.py:477-479). Add spans are a subset of list spans, and a stored label equals the current posture label: relabels rewrite tombstones too, and in-flight relabels compile as covers or holes (labels.py:35, rights.py:372-375). So any occupant at a reachable path is visible, and the gate judges it at the primary rung (contribute/read_write) with the owner floor (rights.py:873-875). A tombstone the caller can list is judged at the restore rung (rights.py:876-880). A road directory admits only list legs (rights.py:870-872), and a creation under a road parent is denied (rights.py:884). Any refusal fails the whole batch (backend.py:700). The sequential gate is sound.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/authority.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/staging.py",
   "src/vfs/storage/backends/database/topology.py"
  ],
  "invariant": "only the system actor may stamp a declared owner_id",
  "method": "source",
  "result": "owner_for returns the declared owner only when authority.is_system, and otherwise the single subject or None (authority.py:216-227). It is applied at insert (writes.py:1205) and at copy (topology.py:452). An edit stages the row's existing owner (writes.py:259-268). Clobber columns exclude owner_id (writes.py:100-121).",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/edges.py",
   "src/vfs/storage/backends/database/links.py",
   "src/vfs/params.py",
   "src/vfs/base.py"
  ],
  "invariant": "mkedge/rmedge need contribute on the source and list on the target; a caller-chosen provenance cannot reach a trust decision",
  "method": "source",
  "result": "mkedge gates the source in modify mode and the target in read mode at traverse=list (backend.py:937-938). rmedge gates the source and folds unnamed targets into the absent warning (backend.py:966-970, edges.py:212-214). The provenance choices are user/agent/system; 'extracted' is refused (params.py:214-221). Provenance is read only by links.py:137, where extracted rows are deleted by source, so an authored provenance never feeds authorization.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/edges.py",
   "src/vfs/storage/backends/database/topology.py"
  ],
  "invariant": "sequential sad paths: owner_id spoofing, mixed batch, edit/overwrite of another's row, hidden ancestor, mkedge to a hidden target, write-revive/restore/sweep of another's tombstone",
  "method": "local",
  "result": "All were refused as expected. owner_id='bob' from alice was stamped 'alice'. A mixed batch failed whole and created nothing. Overwrite and edit of bob's file were permission_denied. A hidden /secret ancestor answered not_found. An mkedge to a hidden target answered not_found. A write-revive, restore or sweep of bob's tombstone by alice was permission_denied, and bob's own restore succeeded.",
  "artifact": "agents/h03-mutations/artifacts/evidence/gate-sad-paths.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h03-mutations",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/dialects.py"
  ],
  "invariant": "insert arbitration never applies a creation-rung caller's body to a rival's row the gate never judged",
  "method": "local",
  "result": "alice holds only add on /drop. Sequentially, her overwrite of bob's /drop/report.txt is permission_denied. When bob's create of the same path is injected after alice's gate (same session, before _apply), alice's write succeeds, and the stored body of bob's row becomes 'ALICE'. This happened both under the SQLite upsert path and with the profile forced to arbitration=catch_retry, which uses the absorb path that MSSQL, Oracle and the generic floor take.",
  "artifact": "agents/h03-mutations/artifacts/evidence/write-arbitration-clobber.txt"
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

- Scratch, the only place you or target code may write: `./agents/v14-p3/scratch/`. Never write `./agents/v14-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v14-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v14-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs/storage/database/write-arbitration-absorb-without-reauthorization` unless you identify a genuinely different root cause.

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
