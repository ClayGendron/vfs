# Candidate verifier brief for `v21-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w4a-cost. Repository: . at commit 3586750 (read-only).

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
  "proposed_verdict": "confirmed",
  "fingerprint": "vfs:storage/backends/database/rights.py:grant_rows:uncapped-foreign-grant-rows-inflate-grantee-clause-fan",
  "title": "Uncapped grant rows naming another principal make that principal's glean issue a growing number of statements and stall the shared event loop",
  "description": "Any principal holding read_write at some path (anonymous everywhere under the default read_write root posture) can write any number of grant rows naming another sub or a group: id at distinct sub-paths. Every later call by the grantee (or by every member of the group) compiles all of those rows. The glean vector leg then runs one statement per visibility clause, about one per 100 planted rows. The rows persist, and the grantee cannot revoke them. Measured on InMemoryStorage: with 5000 planted rows a warm glean grew from 44 ms to 2.3 s and from 12 to 61 statements, and the event loop stalled for up to 455 ms per call. Each further grant also retires the grantee's RightsCache entry, which forces a fresh compile that grows with n.",
  "root_cause": "grant_rows/_grant_refusal impose no count bound on rows naming a principal other than the granter. The glean vector leg uses the per-clause fan from visibility_clauses (glean.py:648-670) instead of the single-statement range source, so the statement count grows with the grantee's piece count. The compile (Resolution.compile) and statement construction run on the event loop.",
  "intended_behavior": "A grantee's per-call cost should not grow without bound with rows another principal plants. Either cap the grant rows naming a principal (or per granter), or keep the vector leg's visibility pushdown at a statement count that is constant in the grantee's rights, as narrow() already does through visible_entries.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 987,
    "scope": "DatabaseStorage.grant",
    "description": "Any caller with read_write at the path may grant any lawful principal, including another sub or a group: id"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 915,
    "scope": "grant_rows",
    "description": "The gate checks only principal lawfulness, level and read_write at the path; there is no count cap. stamp_principals retires the grantee's cache"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 371,
    "scope": "resolve_authority",
    "description": "On a cache miss, the call reads every row naming the grantee's subjects and groups, then compiles them in Python"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 418,
    "scope": "visibility_clauses",
    "description": "Splits the rights into OR-clauses of at most 200 units each, so the clause count grows linearly with planted prefixes"
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/glean.py",
    "line": 648,
    "scope": "vector leg",
    "description": "Runs one statement per clause (and per probe window) on every dialect"
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 1349,
    "description": "_lawful_principal accepts any non-reserved, non-blank id within the column length; no count check exists anywhere in the grant path"
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 205,
    "description": "The default posture is read_write at the root, so under defaults anonymous passes the grant gate"
   },
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 541,
    "description": "narrow() uses the single-statement range source where the dialect has one; glean's vector leg does not, and the GENERIC floor fans out for all read verbs"
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 666,
    "description": "arm_budget caps clause width at 200 units, which keeps each statement bounded while the statement count grows"
   }
  ],
  "conditions": [
   {
    "kind": "authorization_role",
    "description": "The attacker holds read_write at some path. Under the default root posture this includes anonymous."
   },
   {
    "kind": "data_state",
    "description": "The attacker plants rows naming the victim sub or a group: id at distinct prefixes the victim does not otherwise cover. The victim must use glean (any dialect), or any read verb on the GENERIC floor, to see the statement fan."
   }
  ],
  "execution": {
   "attacker_perspective": "A principal with read_write on its own subtree grants read on many distinct sub-paths to a victim sub",
   "payloads": [
    "for i in range(n): storage.grant(path=Path(f'/home/mallory/p{i:06d}'), principal='alice', level='read', authority=Authority.of(Principal('mallory')))",
    "storage.glean(query='alpha doc', authority=Authority.of(Principal('alice')))"
   ],
   "instructions": [
    "Create an InMemoryStorage, write 20 files owned by alice, set posture none at /, grant alice read_write on /home/alice and mallory read_write on /home/mallory as system",
    "Plant 250 grants as mallory through grant(), then bulk-insert identical rows up to n",
    "Count the statements alice's glob, read and glean calls issue, with a 1 ms asyncio ticker running, at n = 250, 1250, 2500 and 5000, inside the sandbox"
   ],
   "observed_result": "glean took 12/22/35/61 statements and made 3/13/26/52 clauses. Warm glean took 44/395/1267/2348 ms, and the largest event-loop gap was 17/133/187/455 ms. glob and read stayed at a constant statement count, but their cold compile grew from 1.0 to 26.4 ms and a single mallory grant forced it again."
  },
  "remediation": {
   "strategy": "Route the glean vector leg's visibility through visible_entries (a join or a semi-join on the range source), as narrow() already does, so the statement count is constant in the grantee's rights. Separately, bound the number of grant rows naming one principal or written by one granter, or require the grantee's consent for rows that name it. Offload compiles above a size threshold."
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "It needs only read_write somewhere; the default posture grants that to anonymous. Planting is cheap (a few ms per grant), and the rows persist."
   },
   "impact": {
    "score": "medium",
    "reason": "It degrades a chosen victim's (or a whole group's) glean persistently and linearly with planted rows, and the event-loop stalls affect every caller in the process. No data is disclosed."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "medium",
   "reason": "The growth was measured locally on SQLite only. The GENERIC fan-out for every read verb is source-derived, and real-engine timings were not observed."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20%28and%20revoke%29%20naming%20another%20principal%20or%20a%20group%20id%2C%20repeated%20over%20many%20distinct%20path%20prefixes%20the%20granter%20holds%20read_write%20on%20%28the%20path%20need%20not%20hold%20a%20row%29::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23resolve_authority%20-%3E%20_grant_rows%20-%3E%20Resolution.compile%20-%3E%20visibility_clauses%3A%20the%20grantee%27s%20own%20per-call%20rights%20compile%20and%20per-clause%20statement%20fan-out%2C%20with%20revision.py%23stamp_principals%20retiring%20the%20grantee%27s%20RightsCache%20entry%20on%20every%20grant::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Resource%20accumulation%20attack%20classes",
  "agent_id": "w4a-cost",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py",
   "src/vfs/storage/backends/database/dialects.py"
  ],
  "invariant": "No source-visible cap on how many grant rows one granter may write naming another sub or group: id",
  "method": "source",
  "result": "grant_rows (rights.py:894-920) checks only lawful principal, level, and read_write at the addressed path (_grant_refusal 1305-1336). _lawful_principal accepts any non-reserved id, including any group: id. No per-principal, per-granter or per-mount row-count cap exists (searched for grant cap/limit/budget). The backend default posture is read_write at the root (backend.py:205), so under defaults anonymous can grant. The victim cannot revoke rows naming itself at paths where it lacks read_write.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20%28and%20revoke%29%20naming%20another%20principal%20or%20a%20group%20id%2C%20repeated%20over%20many%20distinct%20path%20prefixes%20the%20granter%20holds%20read_write%20on%20%28the%20path%20need%20not%20hold%20a%20row%29::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23resolve_authority%20-%3E%20_grant_rows%20-%3E%20Resolution.compile%20-%3E%20visibility_clauses%3A%20the%20grantee%27s%20own%20per-call%20rights%20compile%20and%20per-clause%20statement%20fan-out%2C%20with%20revision.py%23stamp_principals%20retiring%20the%20grantee%27s%20RightsCache%20entry%20on%20every%20grant::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Resource%20accumulation%20attack%20classes",
  "agent_id": "w4a-cost",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/ranges.py",
   "src/vfs/storage/backends/database/glean.py"
  ],
  "invariant": "How the grantee's per-call cost scales with planted rows",
  "method": "source",
  "result": "Every profiled dialect declares range_source, so Visibility.narrow (rights.py:541-551) uses visible_entries (ranges.py:96) as one statement for read, glob and the other narrowed verbs. That path does not fan out by statement count. The GENERIC floor has no range_source, so narrow fans out one statement per visibility_clauses clause for every read verb. The glean vector leg (glean.py:648-670) always calls view.clauses() and runs one statement per clause, on every dialect, up to two probe windows. visibility_clauses caps each clause at 200 units (arm_budget, dialects.py:666-676), so the clause count is about 2n/200 for n planted prefixes. Each statement stays inside the bind budget, but the number of statements per call grows without bound.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20%28and%20revoke%29%20naming%20another%20principal%20or%20a%20group%20id%2C%20repeated%20over%20many%20distinct%20path%20prefixes%20the%20granter%20holds%20read_write%20on%20%28the%20path%20need%20not%20hold%20a%20row%29::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23resolve_authority%20-%3E%20_grant_rows%20-%3E%20Resolution.compile%20-%3E%20visibility_clauses%3A%20the%20grantee%27s%20own%20per-call%20rights%20compile%20and%20per-clause%20statement%20fan-out%2C%20with%20revision.py%23stamp_principals%20retiring%20the%20grantee%27s%20RightsCache%20entry%20on%20every%20grant::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Resource%20accumulation%20attack%20classes",
  "agent_id": "w4a-cost",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/glean.py"
  ],
  "invariant": "Measured victim statements, compile time, call time and event-loop gap as planted rows grow",
  "method": "local",
  "result": "InMemoryStorage, posture none at /, mallory read_write at /home/mallory, victim alice. The first 250 rows were planted through grant() as mallory (3.4-5.7 ms each); the rest were bulk-inserted as identical rows. Planted 250/1250/2500/5000: glob and read stayed at 4 statements warm and 8-10 cold; the cold compile took 1.0/4.7/10.3/26.4 ms and was redone after a single mallory grant (the stamp retires the cache entry). glean took 12/22/35/61 statements and made 3/13/26/52 clauses. Warm glean took 44/395/1267/2348 ms, and the largest event-loop gap was 17/133/187/455 ms. The statement count roughly doubles when n doubles.",
  "artifact": "agents/w4a-cost/artifacts/evidence/u1_grant_rows_growth.txt"
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

### RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name untrusted input, requester work, service amplification or retained resource, shared blast radius, and recovery. Missing limits without concrete shared impact are hardening.
2. Confirm no source-visible upstream, parser, queue, tenant, or framework bound prevents the path. Unknown deployed controls require `needs_validation`.
3. For superlinear behavior, establish the accepted complexity and bounded local growth. For leaks, show repeatable retention after cleanup should occur. For fatal paths, identify process/supervisor isolation.
4. Prioritize by low requester work, unauthenticated reachability, cross-tenant scope, persistence, and poor recovery; do not validate with availability impact.
5. Return `confirmed` only with safe local proof and meaningful shared effect. Return `needs_validation` with the exact upstream limit, topology, quota, or recovery observation an owner must check.

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

- Scratch, the only place you or target code may write: `./agents/v21-p3/scratch/`. Never write `./agents/v21-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v21-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v21-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs:storage/backends/database/rights.py:grant_rows:uncapped-foreign-grant-rows-inflate-grantee-clause-fan` unless you identify a genuinely different root cause.

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
