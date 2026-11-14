# Hunter brief for agent `h01-grants`

## 1. Role

Your goal is to find source-grounded security invariant failures in your assigned coverage units of the vfs repository at .. You must return exactly one JSON object matching the structured-result contract at the end of this brief, with no surrounding prose.

## 2. architecture.md (verbatim)

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

## 3. Assigned units (verbatim from coverage-ledger.json)

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23add_member%20remove_member%20and%20default%20posture::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23membership%20and%20posture%20defaults::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Business%20logic",
  "canonical_refs": {
   "surface": "src/vfs/base.py#add_member remove_member and default posture",
   "boundary": "src/vfs/storage/backends/database/rights.py#membership and posture defaults",
   "subsystem": "src/vfs/storage",
   "attack_class": "ATTACK-CLASSES.md#Business logic"
  },
  "surface": "src/vfs/base.py#add_member remove_member and default posture",
  "boundary": "src/vfs/storage/backends/database/rights.py#membership and posture defaults",
  "subsystem": "src/vfs/storage",
  "attack_class": "Business logic",
  "starting_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/backends/database/membership.py",
   "src/vfs/storage/backends/database/engine.py",
   "src/vfs/storage/grants.py",
   "src/vfs/storage/backends/memory.py"
  ],
  "ordinary_attack_class_block": "ATTACK-CLASSES.md#Business logic",
  "selected_companion_blocks": [],
  "excluded_blocks": [
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Tenant and object-isolation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Derived-data and disclosure attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Export, backup, restore, and migration attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Deletion, revocation, and lifecycle attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Bounds, integer, and representation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Lifetime, type, and concurrency attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#FFI and ABI attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Binary loading and runtime attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Kernel and privileged-interface attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Computational amplification attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Resource accumulation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Quota and scheduling attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Failure and recovery attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#Dependency and build-input attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#CI and automation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#Release and update attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Context, retrieval, and memory attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Tool and action attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#MCP and sub-agent trust classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Output and disclosure attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "WEB-PROTOCOL-AND-AUTH.md#Core discipline",
    "reason": "no HTTP, token, session or identity protocol exists in source; the host supplies the Authority in-process"
   },
   {
    "block": "CLIENT-SIDE.md#Core discipline",
    "reason": "no browser, DOM or webview code in source"
   },
   {
    "block": "CLOUD-AND-DEPLOYMENT.md#Core discipline",
    "reason": "no IaC or runtime deployment config in source; Docker is test-only"
   },
   {
    "block": "PROTOCOLS-RPC-AND-MESSAGING.md#Core discipline",
    "reason": "no RPC, wire protocol, queue or broker in source"
   },
   {
    "block": "DESKTOP-MOBILE-AND-LOCAL-IPC.md#Core discipline",
    "reason": "no native app, IPC endpoint or privileged helper in source"
   }
  ]
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20revoke%20posture::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23grant%20and%20posture%20gate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "canonical_refs": {
   "surface": "src/vfs/base.py#grant revoke posture",
   "boundary": "src/vfs/storage/backends/database/rights.py#grant and posture gate",
   "subsystem": "src/vfs/storage",
   "attack_class": "ATTACK-CLASSES.md#Access control"
  },
  "surface": "src/vfs/base.py#grant revoke posture",
  "boundary": "src/vfs/storage/backends/database/rights.py#grant and posture gate",
  "subsystem": "src/vfs/storage",
  "attack_class": "Access control",
  "starting_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/base.py"
  ],
  "ordinary_attack_class_block": "ATTACK-CLASSES.md#Access control",
  "selected_companion_blocks": [
   "DATA-ISOLATION-AND-LIFECYCLE.md#Core discipline",
   "DATA-ISOLATION-AND-LIFECYCLE.md#Tenant and object-isolation attack classes",
   "DATA-ISOLATION-AND-LIFECYCLE.md#Universal moves",
   "DATA-ISOLATION-AND-LIFECYCLE.md#Validation rules"
  ],
  "excluded_blocks": [
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Derived-data and disclosure attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Export, backup, restore, and migration attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "DATA-ISOLATION-AND-LIFECYCLE.md#Deletion, revocation, and lifecycle attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Bounds, integer, and representation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Lifetime, type, and concurrency attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#FFI and ABI attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Binary loading and runtime attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "MEMORY-SAFETY-AND-BINARY.md#Kernel and privileged-interface attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Computational amplification attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Resource accumulation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Quota and scheduling attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Failure and recovery attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#Dependency and build-input attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#CI and automation attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "SUPPLY-CHAIN-AND-RELEASE.md#Release and update attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Context, retrieval, and memory attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Tool and action attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#MCP and sub-agent trust classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "AI-AND-LLM.md#Output and disclosure attack classes",
    "reason": "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies"
   },
   {
    "block": "WEB-PROTOCOL-AND-AUTH.md#Core discipline",
    "reason": "no HTTP, token, session or identity protocol exists in source; the host supplies the Authority in-process"
   },
   {
    "block": "CLIENT-SIDE.md#Core discipline",
    "reason": "no browser, DOM or webview code in source"
   },
   {
    "block": "CLOUD-AND-DEPLOYMENT.md#Core discipline",
    "reason": "no IaC or runtime deployment config in source; Docker is test-only"
   },
   {
    "block": "PROTOCOLS-RPC-AND-MESSAGING.md#Core discipline",
    "reason": "no RPC, wire protocol, queue or broker in source"
   },
   {
    "block": "DESKTOP-MOBILE-AND-LOCAL-IPC.md#Core discipline",
    "reason": "no native app, IPC endpoint or privileged helper in source"
   }
  ]
 }
]
```

## 4. Selected blocks (verbatim)

### ATTACK-CLASSES.md#Business logic

**Business logic** (subagent_type: `general`)
Hunt logic errors by hand: standard scanners cannot find them, and they yield high-impact findings. For each major workflow:
- **State machine violations**: Can you skip steps? Go backwards? Reach an invalid state? What happens if you replay a completed flow? What about partial failure — if step 2 of 3 fails, is step 1 rolled back?
- **Race conditions with business impact**: Concurrent operations that produce invalid states (double-spend, double-approve, lost updates). Focus on operations that check-then-act non-atomically.
- **Numeric/quantity manipulation**: Negative values, zero values, overflow, precision loss, type coercion between string and number.
- **Access boundary violations**: Not "does the permission check exist" but "is it the right check for the business rule?" Can input to one operation bypass a restriction enforced on a different operation for the same effect?
- **Implicit trust assumptions**: Data from storage, config, other components, or plugins assumed safe because "we validated it on the way in." What if a different code path wrote it?
- **Time-based logic**: Expiry checks, scheduling, rate windows, clock skew. What happens at exact boundary moments? What about timezone differences between components?
- **Default and fallback behavior**: What is the security posture when config is missing? When a feature flag is off? When a dependency is unavailable? When the system is mid-migration?

---

### ATTACK-CLASSES.md#Access control

**Access control** (subagent_type: `general`)
Verify that a caller cannot do something outside its authority. Go beyond checking whether permission checks exist — verify they check the *right* permission for the *right* resource via the *right* mechanism:
- Is there a path to the same state change that checks a different (weaker) permission?
- Can a field in the request body override what the permission system intended to restrict?
- Are there endpoints that gate on authentication but forget authorization?
- Does the same resource have multiple access paths with inconsistent checks?
- What about bulk/batch/export/import operations — do they enforce per-item permissions?

For complex access models, split into separate agents for auth bypass vs authorization logic.

---

### DATA-ISOLATION-AND-LIFECYCLE.md#Core discipline

## Core discipline (include in every agent prompt for this domain)

```
- A tenant or owner field on a record is not isolation. Find the query, key, path, policy, or row-level control that enforces it for each read and write path.
- Trace derived copies. Sanitized primary data can become unsafe in search, cache, analytics, export, previews, logs, replicas, and backups with different ACL and retention rules.
- Deletion and revocation are lifecycle contracts. Check current, historical, cached, indexed, exported, restored, and queued copies within the product's stated boundary.
- Privacy or retention preference is not automatically a security vulnerability. Require an explicit data-access boundary or deletion/revocation guarantee and an unauthorized reader or later operation.
- Use `confirmed` for complete source-visible lineage and bounded dummy-tenant tests. Use `needs_validation` when external storage policy, retention, CDN behavior, replica lag, or backup access is unavailable.
```

---

### DATA-ISOLATION-AND-LIFECYCLE.md#Tenant and object-isolation attack classes

## Tenant and object-isolation attack classes (subagent_type: `general`)

**Missing tenant or owner enforcement**
A read, update, delete, list, count, or bulk query identifies an object without binding it to the authenticated tenant/owner, or trusts body fields to supply that identity. Compare direct lookup, nested relationship, background, admin, import, and legacy paths.

**Composite-key and namespace collision**
Cache keys, object paths, database uniqueness, search document IDs, temporary files, or deduplication keys omit tenant or environment. Two principals can overwrite or retrieve the same logical key even though application records carry separate owners.

**Policy and query disagreement**
Row-level policy, ORM default scopes, authorization filters, and raw/bypass clients apply different predicates. Check joins, aggregates, aliases, views, transactions, `unscoped` or service clients, and error paths where context is missing.

**Blob and signed-reference overreach**
Object keys, attachment IDs, version IDs, shared links, or signed URLs permit operations or namespaces beyond the issuing principal's access, or remain valid after the underlying ACL changes. Bind operation, exact object/version, audience, expiry, and tenant.

---

### DATA-ISOLATION-AND-LIFECYCLE.md#Universal moves

## Universal moves (apply across the above)

- Pick one protected record and draw primary write, query, cache, index, event, export, backup, deletion, and restore paths. Mark principal and tenant at every edge.
- Compare two dummy tenants through the same local service methods, then repeat after ACL change, deletion, account switch, and restore. Do not use real user data.
- Start at bypass clients, background jobs, migrations, global uniqueness, and cache keys. These paths commonly omit request-scoped identity that interactive endpoints carry.

---

### DATA-ISOLATION-AND-LIFECYCLE.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name attacker or lower-trust principal, protected data/state, affected owner/tenant, alternate copy or operation, and unauthorized disclosure or mutation.
2. Cite both intended source-of-truth policy and the path that omits or disagrees with it. Confirm another layer does not enforce the same tenant/lifecycle condition.
3. Use local dummy tenants and non-sensitive fixtures to prove cross-scope access or stale lifecycle behavior. Stop at the minimum observable record or operation.
4. If external cache, object storage, replicas, analytics, backup, or retention policy is required, classify `needs_validation` and state the owner-observed check.
5. Return `confirmed` only with complete lineage and concrete boundary impact. Return `needs_validation` with the exact unresolved storage, ACL, invalidation, retention, or restore fact.

## 5. Excluded blocks

- AI-AND-LLM.md#Context, retrieval, and memory attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- AI-AND-LLM.md#MCP and sub-agent trust classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- AI-AND-LLM.md#Output and disclosure attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- AI-AND-LLM.md#Tool and action attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- CLIENT-SIDE.md#Core discipline: no browser, DOM or webview code in source
- CLOUD-AND-DEPLOYMENT.md#Core discipline: no IaC or runtime deployment config in source; Docker is test-only
- DATA-ISOLATION-AND-LIFECYCLE.md#Deletion, revocation, and lifecycle attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- DATA-ISOLATION-AND-LIFECYCLE.md#Derived-data and disclosure attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- DATA-ISOLATION-AND-LIFECYCLE.md#Export, backup, restore, and migration attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- DATA-ISOLATION-AND-LIFECYCLE.md#Tenant and object-isolation attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- DESKTOP-MOBILE-AND-LOCAL-IPC.md#Core discipline: no native app, IPC endpoint or privileged helper in source
- MEMORY-SAFETY-AND-BINARY.md#Binary loading and runtime attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- MEMORY-SAFETY-AND-BINARY.md#Bounds, integer, and representation attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- MEMORY-SAFETY-AND-BINARY.md#FFI and ABI attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- MEMORY-SAFETY-AND-BINARY.md#Kernel and privileged-interface attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- MEMORY-SAFETY-AND-BINARY.md#Lifetime, type, and concurrency attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- PROTOCOLS-RPC-AND-MESSAGING.md#Core discipline: no RPC, wire protocol, queue or broker in source
- RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Computational amplification attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Failure and recovery attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Quota and scheduling attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- RESOURCE-EXHAUSTION-AND-AVAILABILITY.md#Resource accumulation attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- SUPPLY-CHAIN-AND-RELEASE.md#CI and automation attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- SUPPLY-CHAIN-AND-RELEASE.md#Dependency and build-input attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- SUPPLY-CHAIN-AND-RELEASE.md#Release and update attack classes: considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies
- WEB-PROTOCOL-AND-AUTH.md#Core discipline: no HTTP, token, session or identity protocol exists in source; the host supplies the Authority in-process

## 6. Core hunting method (verbatim)

```text
## Defensive vulnerability-finding method

Your goal is to find source-grounded security invariant failures and the smallest fix,
not to expand harm beyond the boundary result. Stay within source review and bounded local execution.
Do not contact deployed endpoints, provider APIs, registries, identity systems,
message brokers, shared services, or other users. Use local dummy data only.

READ THE CODE AT DEPTH. Follow each assigned input through parsing, identity,
authorization, normalization, state, derived copies, and the final sink. Read sibling,
legacy, batch, retry, cancellation, migration, and error paths that produce the same
effect. Compare sibling controls for equivalence, not only presence, and compare what
one component guarantees with what the next component assumes.

WORK FROM A CONCRETE INVARIANT:
1. Name the lower-trust principal and starting capability.
2. Name the accepted value, action, state transition, or resource selector.
3. Locate the control that should reject, bind, isolate, limit, or revoke it.
4. Trace the exact source path after that decision.
5. Stop at the smallest affected dummy record, wrong return value, process-integrity
   effect, or locally observable shared-resource effect.
6. State a source-level change and regression case that enforce the invariant.

DEPTH BOUND: trace only paths that can reach your assigned boundary or whose
guarantees that boundary relies on. Stop a line of investigation as soon as the
invariant is settled either way, and record the result in your structured output —
a covered, candidate, or blocked disposition, or an `uncovered` entry — instead of
continuing to search.

TEST SAD PATHS AND DISAGREEMENTS. Check absent, empty, zero, negative, maximum,
over-limit, duplicate, mixed encoding, stale, revoked, reordered, concurrent,
partially migrated, failed dependency, and rollback state only where the interface
accepts them. Compare canonicalization and units at every parser or policy handoff.
For multi-step issues, treat each output as a prerequisite and do not assume a later
boundary. If any prerequisite is not established, record a blocker.

When a proposed high or critical candidate reveals a reusable root cause, search paths
owned by the assigned coverage IDs for lexical, structural, and logical variants.
Consolidate the same root cause, but establish each variant's conditions and impact
independently. Do not investigate peer-owned units. Return a variant with no current
coverage unit as `uncovered`.

USE THE NARROWEST LOCAL CHECK THAT SETTLES THE CLAIM. Target-controlled builds,
tests, processes, browsers, emulators, fuzzers, and fixture processing may run only
inside the parent-approved OS-enforced sandbox. It must disable external networking,
start from an empty allowlisted environment, expose target and tools read-only, permit
writes only to your scratch directory, and apply low CPU, memory, process, file-size,
disk, and wall-clock limits. Isolated loopback is allowed only for a local fixture.
If any control is unavailable, do not execute: return needs_validation with that exact
blocker. Prefer an existing unit test, minimal function harness, dummy-tenant service
call, small malformed fixture, deterministic race schedule, or locally rendered policy.
Do not install or fetch tools.

Record the exact input, command, limits, and minimum result. For the environment,
record only allowlisted variable names and safe non-secret values needed to reproduce
the check. Never capture the ambient environment, inherited variables, credentials,
authentication state, or unrelated host paths. The target-controlled process writes
only in scratch. After the sandbox and all its processes terminate, only trusted
parent-side code may promote predeclared scratch-relative files, following the
promotion procedure block included verbatim in this prompt. You and target code never
write retained artifacts. If promotion is unavailable or fails for decisive evidence,
return needs_validation with the exact promotion blocker.
Never stress availability, invoke a live target, use a real credential, publish an
artifact, or continue past the minimum observed effect.

A deployment, browser, provider, broker, OS, proxy, package, secret, or identity fact
outside source is not proof either way. If one such fact is decisive, return a
needs_validation record with the exact missing observation and safe owner-observed check.
```

### Promotion procedure (verbatim)

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

## 7. Core validation rules (verbatim)

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

## 8. Exclusions

No prior run exists, so there are no carried same-source confirmed exclusions. Peer-owned coverage IDs you must not duplicate (return a variant there under `uncovered` only if no unit covers it):

- .github%2Fworkflows%23push%20and%20pull_request::.github%2Fworkflows%23token%20permissions%20secrets%20and%20pinning::.github%2Fworkflows::SUPPLY-CHAIN-AND-RELEASE.md%23CI%20and%20automation%20attack%20classes
- .github%2Fworkflows%2Fpublish.yml%23release%20published::scripts%2Fcheck_release_tag.py%23tag%20check%20and%20environment%20pypi::.github%2Fworkflows::SUPPLY-CHAIN-AND-RELEASE.md%23Release%20and%20update%20attack%20classes
- crates%2Fvfs-core%2Fsrc%2Fpython.rs%23pyo3%20entry%20points::crates%2Fvfs-core%2Fsrc%23bounds%20and%20panic%20containment::crates%2Fvfs-core::ATTACK-CLASSES.md%23Resource%20and%20file%20handling
- repository%23tracked%20files::repository%23secrets%20debug%20gates%20and%20dangerous%20calls::repository::ATTACK-CLASSES.md%23Obvious%20things
- repository%23tracked%20files::repository%23secrets%20randomness%20and%20comparisons::repository::ATTACK-CLASSES.md%23Cryptography%20and%20secrets
- src%2Fvfs%23all%20modules::src%2Fvfs%23any::src%2Fvfs::ATTACK-CLASSES.md%23Wildcard
- src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control
- src%2Fvfs%2Fbase.py%23delete%20restore%20sweep%20move%20copy::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Ftrash.py%23subtree%20checks::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Chained%20vulnerabilities%20and%20trust%20boundaries
- src%2Fvfs%2Fbase.py%23grep%20glean%20graph::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23Visibility%20over%20derived%20copies::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Feature%20abuse%20and%20data%20leakage
- src%2Fvfs%2Fbase.py%23read%20stat%20ls%20tree%20glob::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23Visibility::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control
- src%2Fvfs%2Fbase.py%23write%20edit%20mkdir%20mkedge::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23WriteGate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control
- src%2Fvfs%2Fparams.py%23pattern%20query%20edit%20graph%20arguments::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fgrep.py%23budgets%20and%20caps::src%2Fvfs::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes
- src%2Fvfs%2Fpaths.py%23%2F.agents%20namespace%20and%20src%2Fvfs%2Fskills.py::src%2Fvfs%2Fbase.py%23run%20dispatch%20and%20%2F.agents%20write%20rights::src%2Fvfs::AI-AND-LLM.md%23Tool%20and%20action%20attack%20classes
- src%2Fvfs%2Fpaths.py%23normalize_path::src%2Fvfs%2Fbase.py%23mount%20boundary%20and%20reserved%20namespaces::src%2Fvfs::ATTACK-CLASSES.md%23Resource%20and%20file%20handling
- src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling
- src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2F%23statement%20builders::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fdialects.py%23bound%20parameters%20and%20escape_like::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::ATTACK-CLASSES.md%23Injection

## 9. Your paths, sandbox, and result contract

- Agent ID: `h01-grants`. Scratch (the only place you or target code may write): `./agents/h01-grants/scratch/`. Never write `./agents/h01-grants/artifacts/`; the parent promotes.
- Promotion allowlist: any regular files you name under `scratch/evidence/` in your result's local-check `artifact` fields (as `agents/h01-grants/artifacts/evidence/<name>`), at most 256 KiB each and 1 MiB total. List them; the parent promotes them after you return.
- Sandbox: run target code ONLY as `./tools/sandbox-run.py ./agents/h01-grants/scratch <cmd...>`. It denies all network (loopback too), starts an empty env (HOME/TMPDIR in scratch), makes everything but scratch read-only, and caps CPU 60 s, wall 120 s, RSS 2 GiB (watchdog), files 64 MiB, 256 procs. Use `./.venv/bin/python -I <scratch-script>` as the interpreter (vfs and all extras are installed; do not use uv, pip, or network). Write harness scripts into scratch first. SQLite files and InMemoryStorage only; no real database engines. Never run target code outside this launcher.
- Do not edit anything in the repository. Do not run git commands that change state.

### Structured hunter result (verbatim)

Return exactly one JSON object, with no surrounding prose:

```json
{
  "units": [
    {
      "coverage_id": "one assigned ID",
      "disposition": "covered|candidate|blocked",
      "reviewed_paths": ["repo/relative/path"],
      "checks": [
        {
          "agent_id": "canonical owner of this check",
          "reviewed_paths": ["repo/relative/path owned by this check"],
          "invariant": "specific control checked for this unit",
          "method": "source|local",
          "result": "what source or the bounded check established",
          "artifact": "agents/<agent-id>/artifacts/file for local, null for source"
        }
      ],
      "candidate_fingerprints": [],
      "unresolved": []
    }
  ],
  "candidates": [],
  "hardening": ["concrete non-finding note"],
  "uncovered": [
    {
      "surface": "...",
      "boundary": "...",
      "subsystem": "...",
      "attack_class": "...",
      "starting_paths": ["repo/relative/path"],
      "reason": "why this needs its own deterministic coverage unit"
    }
  ]
}
```

Each `candidates` entry is schema-shaped except that it uses `proposed_verdict` in place of `verdict`:

- `proposed_verdict: "confirmed"`: include every field required by the `confirmed` branch of `report-schema.json` other than `verdict`: `fingerprint`, title, description, `root_cause`, `intended_behavior`, ordered `trace`, `evidence`, `conditions`, target-neutral `execution`, `remediation`, `severity`, and `confidence`. The execution instructions describe only the bounded local check already performed. `payloads` holds the minimum test input, fixture, or native invocation. `observed_result` records actual local output. Overall severity must not exceed observed impact.
- `proposed_verdict: "needs_validation"`: include every field required by that schema branch other than `verdict`: `fingerprint`, title, description, `claimed_root_cause`, ordered `trace`, `evidence`, nonempty `blockers`, and `validation_plan` with at least one applicable `local` or `deployment` step. Do not invent an inapplicable context. Do not include severity, execution, remediation, reason, or a confirmed `root_cause`. `deployment` is an owner-observed check, not a request to probe a live target.

Every assigned coverage ID appears exactly once in `units`. A `covered` unit needs an owner, nonempty `reviewed_paths` and `checks`, no unresolved fact, and no candidate. A `candidate` unit has the same owned evidence and is the only state that carries linked fingerprints. A `blocked` unit is an owned partial review with nonempty paths, checks, and unresolved facts but no fingerprint. All source paths are repository-relative, never absolute or traversal paths. A trace with several entries begins at `entrypoint`, ends at `sink`, and labels intermediate steps `propagation`. Every check has its own canonical lowercase `agent_id` and nonempty `reviewed_paths`; the unit-level list is exactly the union of those owned paths. A `source` check uses `artifact: null`. A `local` check uses one successfully parent-promoted regular file beneath `agents/<check.agent_id>/artifacts/`; this permits a verifier to add independently owned evidence without taking ownership from the hunter. Never link scratch, an output-root file, or another check owner's artifact.

### report-schema.json `confirmed` branch (verbatim)

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

### report-schema.json `needs_validation` branch (verbatim)

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
