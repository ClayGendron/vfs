# Final record verifier brief for `f11-p5`

You are a fresh, independent final verifier. You did not hunt this candidate, did not perform its Phase 3 validation, and did not write this record. Repository: . at commit 3586750 (read-only). Check the structured record below against current source, not any hunter write-up. Earlier agents' artifacts under context/reviews/2026-11-07-0-1-0a1-security-audit/agents/*/artifacts/ are cited evidence you may read; reproduce any decisive local result yourself.

## 1. Phase 5 instructions (verbatim from the skill)

```text
### Phase 5: Verify the final records with fresh eyes

Launch one fresh `research` verifier per final `confirmed` and `needs_validation` record, in parallel. This verifier checks the structured record, not the hunter write-up, and remains inside source/local boundaries.

In a `quick` run, Phase 3 and Phase 5 merge: the Phase 3 verifier also performs these record checks and returns the final schema-shaped record, so each candidate gets one fresh independent reviewer instead of two. Every other profile keeps the two passes separate. Never skip independent review of a `confirmed` record in any profile.

For `confirmed`, require it to check:

1. Every repository-relative trace/evidence path, line, scope, and described operation.
2. Real entry interface and exact local input shape.
3. Every condition, parser/policy step, source-visible preventing layer, and observed local result.
4. Affected principal/resource and demonstrated impact.
5. Severity separation: realistic likelihood, demonstrated impact, overall no greater than impact.
6. Remediation strategy and any `code_changes`, including whether the fix enforces the invariant without merely moving trust.

For `needs_validation`, require it to check:

1. The source path is real and supports only the `claimed_root_cause` stated.
2. Every listed blocker is decisive and not already answerable locally.
3. The candidate names a boundary and a possible concrete result rather than a generic concern.
4. At least one validation-plan field is present and exact. `local` uses a bounded fixture; `deployment` asks an owner to observe a configuration, identity, route, policy, or runtime fact. Do not invent a plan for an inapplicable context, and never send audit traffic to a deployment.
5. The fingerprint matches prior/current records for the same root cause.

Each verifier returns exactly one JSON object: `{"decision":"verified","fingerprint":"..."}` or `{"decision":"replace","reason":"...","record":{...}}`, with no surrounding prose. A replacement record must match its `confirmed`, `needs_validation`, or `rejected` schema branch. Treat a malformed or prose-wrapped Phase 5 result the same way as in Phase 3: discard it without repairing it and re-run with a fresh verifier when the budget permits.

Do not apply a Phase 5 replacement as final when it promotes a record to a stronger verdict, including any promotion to `confirmed`, or materially changes the root cause, trace, execution input or observed result, demonstrated impact, or severity. Give that complete replacement to a new independent verifier that did not hunt, perform Phase 3 validation, or propose the Phase 5 replacement. The new verifier rechecks the current source and independently reproduces any decisive local result under the execution boundary, then returns `verified` or another replacement. Apply a material replacement only after this fresh verification. If another material replacement results, repeat with a fresh verifier. If budget or independence is unavailable, remove the disputed record from `findings.json`, keep its ledger unit as an unresolved candidate, and set `run_status: "incomplete"` with an exact `incomplete_reason`. Non-material wording or repository-line corrections may be applied directly when they do not change meaning or evidence.

After every applied replacement, rerun both validators and update linked ledger decisions. If a final verifier identifies a separate root cause, assign a new fingerprint and send it through independent candidate validation before inclusion. Set `run_status: "complete"` only when every ledger candidate has an independent final disposition and every retained record passes Phase 5.

Do not verify only `confirmed` records. A misleading `needs_validation` handoff wastes owner time and can preserve a false premise.
```

## 2. The record under review (verdict `needs_validation`)

```json
{
 "verdict": "needs_validation",
 "fingerprint": "vfs/storage/database/labels:mint-reads-posture-outside-revision-lock-stale-everyone-level",
 "title": "A write, move or copy that read the everyone posture before a tightening posture commit can stamp the old, more open everyone_level after the relabel has cleared its mark",
 "description": "entries.everyone_level is a derived copy of the deepest everyone ('*') posture on a row's path. Once no relabel mark stands over a path, Rights.admits trusts the stored label outright. Posture writes take the admin lock with bump_revision, and every Relabeller chunk takes it with hold_revision. The mint paths take neither. write and mkdir call labels_for at writes.py:379, and move and copy call posture_beneath at topology.py:197. Both read the grants rows with plain SELECTs and never re-check the relabels table. Here is the interleaving. A write W pins its snapshot at its first statement, because op_isolation is REPEATABLE READ on Postgres and MariaDB. A posture commit P then tightens /eng/secret.md to none. The path need not hold a row, per _grant_refusal at rights.py:1318. P's Relabeller runs and clears the mark while W is still open. It cannot see W's uncommitted insert. When the posture sits at the created path, it rewrites 0 rows. W then commits with the old label. After that, any named principal with no grant can read the row, and anonymous grep and glob list it. Nothing in src corrects the label: rebuild_labels has no caller there. I re-ran the hunter's consequence emulation on SQLite in the sandbox: the mint is handed the labels that the real labels_for and posture_beneath computed before the posture commit. Results with no pending marks: write, move and copy stamp everyone_level=2 under posture none. bob (no grants) reads 'TOPSECRET payroll'. Anonymous and bob grep and glob list /eng/secret.md. Anonymous direct read stays refused (unauthenticated). bob's overwrite stays refused, because read is below the write rung. The control with fresh labels gives label 0 and not_found. rebuild_labels repairs the label. The real interleaving cannot happen on SQLite, because writers hold BEGIN IMMEDIATE. So the decisive concurrent behaviour on a real engine has not been observed. The spec that introduced the label (context/specifications/archive/150-rights-at-scale/spec.md) analyses rival admin writes, but not a concurrent mint against a relabel.",
 "claimed_root_cause": "labels_for (labels.py:124, reading posture_rows at labels.py:110-121) and posture_beneath (labels.py:139) read the everyone posture rows without the admin revision lock (no hold_revision, nothing that conflicts with bump_revision) and without consulting inflight relabel marks. The Relabeller (labels.py:244-266) rewrites only rows visible to its own statements, then deletes the mark. A mint whose posture read predates a posture commit, and which commits after that posture's relabel has passed its path, therefore stamps a stale label that no mark covers. readers then trust it (grants.py:491).",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 686,
   "scope": "DatabaseStorage.write",
   "description": "The write verb, called by a named principal holding write rights (alice), runs its plan through _execute_write (backend.py:1666-1673) with op_execution_options(writer=True). On Postgres and MariaDB that stamps isolation_level REPEATABLE READ (dialects.py:593-594), so the snapshot is pinned at the first statement."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 379,
   "scope": "_apply",
   "description": "labels_for is called for the creates after staging. Nothing in writes.py takes hold_revision or bump_revision, issues a locking read, or reads the relabels table."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/labels.py",
   "line": 117,
   "scope": "posture_rows",
   "description": "A plain SELECT of the '*' grants rows over the ancestor prefixes. Under W's pinned snapshot it returns the posture as it stood before a concurrent posture commit."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/topology.py",
   "line": 197,
   "scope": "transfer_rows",
   "description": "Move and copy compute posture_beneath with the same unlocked read, after the serialize() lock-table point (topology.py:143), which is not the revision lock. They stamp the result at topology.py:315 (moved root), 373 (descendants) and 453 (copied rows), under topology_isolation READ COMMITTED."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 1034,
   "scope": "set_posture",
   "description": "The posture write upserts the '*' row and plants the relabel mark in one transaction, after bump_revision (backend.py:1594). _grant_refusal (rights.py:1318) lets the path hold no row, so a posture can be set at a path a concurrent write is creating."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/labels.py",
   "line": 248,
   "scope": "Relabeller.step",
   "description": "Each chunk takes hold_revision and rewrites the rows its statements see. It cannot see W's uncommitted rows; for a posture at a not-yet-existing path it rewrites 0 rows (observed: relabel rows=0). The last chunk deletes the mark and bumps the revision (labels.py:265-266)."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/grants.py",
   "line": 491,
   "scope": "Rights.admits",
   "description": "With no hole standing (the mark is gone), a row whose stored everyone_level reaches the needed rung is admitted. Named callers' reads, and grep and glob for anonymous and named callers alike, then admit the stale-labelled row."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/labels.py",
   "line": 1,
   "description": "The module docstring says the label is derived, stamped at every mint from the posture rows, and covered by the mark only while the relabel is in flight. Nothing ties the mint's read to the lock that orders posture commits."
  },
  {
   "file": "src/vfs/storage/backends/database/revision.py",
   "line": 60,
   "description": "hold_revision is the admin lock that relabel chunks take, so they serialize behind rival admin writes. The mint paths take neither it nor bump_revision (no revision import in writes.py or topology.py)."
  },
  {
   "file": "src/vfs/storage/backends/database/dialects.py",
   "line": 436,
   "description": "Postgres declares op_isolation REPEATABLE READ, and MariaDB does the same at line 500. op_execution_options (line 582) applies it to writer connections, so the write's posture read comes from its first statement's snapshot."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 389,
   "description": "The strongest visible control. unauthenticated_at judges anonymous path-addressed calls from the posture rows, not the label, so an anonymous direct read stays refused (observed). Named callers and the anonymous list and search verbs still trust the label."
  },
  {
   "file": "src/vfs/storage/backends/database/engine.py",
   "line": 654,
   "description": "On SQLite, writers open BEGIN IMMEDIATE, so a posture commit cannot land inside a write's window. That is why the real interleaving cannot be observed locally."
  },
  {
   "file": "context/specifications/archive/150-rights-at-scale/spec.md",
   "line": 74,
   "description": "The in-flight rule covers stale labels only while the mark stands. The spec's race analysis (line 242) covers rival admin writes, not a mint that is concurrent with a relabel."
  },
  {
   "file": "agents/v12-p3/artifacts/evidence/stale-label-rerun.json",
   "line": 1,
   "description": "My sandboxed SQLite re-run of the hunter's consequence emulation. Fresh-label control: label 0, bob not_found. Mint given the pre-commit posture read: everyone_level=2 under posture none with no marks. bob reads TOPSECRET content, and anonymous grep and glob list the path. Anonymous direct read and bob's overwrite stay refused. rebuild_labels resets the label to 0. The relabel rewrote 0 rows for the posture at the created path."
  }
 ],
 "blockers": [
  "The decisive concurrent interleaving cannot happen on SQLite. Writers hold BEGIN IMMEDIATE from the plan's first read (engine.py:649-655), and a deferred SQLite reader could not upgrade a stale snapshot to a write anyway. Real engines (Postgres, MariaDB, SQL Server, Oracle) and Docker are prohibited in this sandbox. Only the consequence was observed, by handing the mint its pre-commit posture read.",
  "Postgres REPEATABLE READ: the source predicts that a posture at the created path, or at a directory the same batch creates, leaves W's existing parent outside the relabelled region. Then no 40001 conflict arises and W commits the stale label. Where the posture covers an existing parent, the relabel rewrites that parent, so W's guarded parent bump (_bump_parents, writes.py:1026) should fail with a serialization error and redrive. Neither outcome has been observed on a live engine.",
  "MariaDB: whether innodb_snapshot_isolation (ON by default from 11.6, error 1020) turns the parent bump into a restart, and whether a Relabeller range UPDATE (a current read) blocks on a concurrently moved row's uncommitted index entry and then relabels it, are both unobserved.",
  "SQL Server (no op_isolation): under locking READ COMMITTED, the relabel UPDATE may block on W's uncommitted key and then relabel it, which narrows the window to the gap between labels_for and the insert. Under READ_COMMITTED_SNAPSHOT it would skip the row. Which mode a deployment runs is a database setting outside source.",
  "Oracle: the statement-level consistent read in the relabel UPDATE is expected to skip uncommitted inserted or moved rows, leaving the window open from labels_for or posture_beneath to commit. Unobserved."
 ],
 "validation_plan": {
  "local": "Re-run agents/v12-p3/scratch/work/stale_label.py (a copy of the hunter's script) under tools/sandbox-run.py with the venv python -I. It reproduces the consequence on SQLite (output: agents/v12-p3/artifacts/evidence/stale-label-rerun.json). It cannot reproduce the interleaving, because SQLite serializes writers. No further local step can resolve the blocker.",
  "deployment": "Owner-run on the db_test containers (VFS_TEST_POSTGRES_URL, VFS_TEST_MARIADB_URL, VFS_TEST_MSSQL_URL, VFS_TEST_ORACLE_URL), following the seam idiom in tests/storage/database/test_races.py, on throwaway mounts with dummy principals. Setup: grant alice read_write at /, set root posture read, mkdir /eng. Install a self-clearing handler on 'write:before-apply' that runs storage.posture(path=/eng/secret.md, posture='none', authority=Authority.system()) to completion on its own session (relabel included). Then have alice write /eng/secret.md. After commit, assert the vfs_relabels table is empty and read everyone_level for /eng/secret.md. If vulnerable it is 2; if correct it is 0. Then assert whether storage.read(path=/eng/secret.md, authority=Authority.of(Principal('bob'))) succeeds and whether anonymous grep and glob list the path. Repeat on 'transfer:post-collect' with move and copy of <tmp>/draft.md to /eng/secret.md. Repeat with the posture on the existing directory /eng, to see per engine whether the parent-bump serialization error (40001 or 1020) redrives the write and closes that case. Repeat on SQL Server with READ_COMMITTED_SNAPSHOT both ON and OFF."
 }
}
```

## 3. Architecture facts

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

## 4. Source/local execution boundary

- Scratch, the only place you or target code may write: `./agents/f11-p5/scratch/`. Never write `./agents/f11-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f11-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f11-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs/storage/database/labels:mint-reads-posture-outside-revision-lock-stale-everyone-level"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
