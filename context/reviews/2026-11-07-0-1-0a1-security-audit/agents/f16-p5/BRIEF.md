# Final record verifier brief for `f16-p5`

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
 "fingerprint": "vfs:models/rows.py:_string:principal-columns-unpinned-collation-mysql-family",
 "title": "owner_id uses the engine's default collation on MariaDB, so a principal whose sub differs from another's only by case, accents or trailing spaces sees that owner's road directories",
 "description": "vfs compares principal identities exactly in Python: Principal.sub, grants.resolve and Rights.admits all use exact string equality. The SQL owner-arm predicate entry.owner_id == :owner runs on a column that gets a bytewise collation only on MSSQL. On MariaDB, owner_id compiles as a plain VARCHAR(255), so it inherits the database's default collation. path and name, by contrast, are pinned to VARBINARY there. MariaDB 11.8, the image the test leg uses, is expected to default to utf8mb4_uca1400_ai_ci, which ignores case and accents and pads trailing spaces; this was not observed in this audit. Principal.__post_init__ accepts subs such as 'ALICE', 'alice ' or 'Alicé'. Visibility.road asks SQL, through _owned_beneath, which hidden directories hold a row that each owner arm's sub owns, and Python never re-checks that answer. So a case-, accent- or space-variant principal is shown the victim's road directories in glob, ls and stat, including the trash view, and a write into such a directory fails as permission_denied instead of not_found. That reveals the names and existence of directories, which the principal could otherwise not see. File rows, content and grep results stay hidden, because the fetched rows pass Rights.admits/holds, which compare owner_id exactly. Grant and membership rows are re-keyed by exact sub in Python, so this does not escalate to inherited grants or groups. A second SQL-only consumer of the same predicate is the lexical aggregate in glean._visible_lexicon (glean.py:776, built from ranges.py:128-130). There the victim's chunks would also be counted into the BM25 corpus statistics. That is a minor statistical side channel, and it was not demonstrated. MySQL community is not a supported dialect per AGENTS.md and is served as GENERIC, but its DDL is the same VARCHAR. Postgres deterministic collations compare exactly and are not affected. Oracle is affected only under NLS_COMP=LINGUISTIC with a case-insensitive NLS_SORT. I reproduced this on SQLite, independently of the hunter, using a different tree (/hr/q3/alice-review.txt owned by 'alice', posture '/' none). With owner_id rewritten to COLLATE NOCASE, 'ALICE' sees /hr and /hr/q3 in glob and ls, stat('/hr/q3') succeeds, and its write into the directory returns permission_denied. With COLLATE RTRIM, 'alice ' sees the same. In both cases read is refused. The control 'bob' and the stock BINARY collation leak nothing (not_found).",
 "claimed_root_cause": "_string() (src/vfs/models/rows.py:179-188) adds a collation variant only for 'mssql'. On the mysql family (and Oracle under linguistic NLS settings), principal-bearing columns such as entries.owner_id (rows.py:471) and grants.principal_id are plain VARCHAR, and equality on them follows the server's collation. BytewiseString pins path and name to VARBINARY there (rows.py:224) but is not used for principal columns. The authority model treats subs as exact strings (grants.py:497, 629, 638-641). So the SQL-only owner predicates (rights.py:1250 in _owned_beneath for the road, and ranges.py:128-130 and rights.py:1220 for listing and aggregates) can admit rows that the Python authority would refuse. Where Python re-checks fetched rows (holds/admits), the gap closes. Where Python consumes the SQL result directly (the road directories, the lexicon aggregate), it leaks.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/authority.py",
   "line": 88,
   "scope": "Principal.__post_init__",
   "description": "The host builds Principal(sub) from its identity provider. Only empty or blank subs, '*', 'group:'-prefixed subs and the reserved names are refused, so 'ALICE', 'alice ' and 'Alicé' are accepted as principals distinct from 'alice'."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/grants.py",
   "line": 641,
   "scope": "resolve (owner floor)",
   "description": "A named subject gets OwnerArm(sub, trimmed), keyed by its exact sub ('ALICE'), covering the mount outside its shared grants."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/reads.py",
   "line": 378,
   "scope": "glob (also ls, stat and the trash view through the same road call)",
   "description": "Directories the view does not show are passed to view.road(), and every path it returns is emitted as a road observation."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 576,
   "scope": "Visibility.road",
   "description": "For each owner arm, _owned_beneath asks SQL which candidate directories hold a row owned by that owner. The result is added to the visible set with no Python re-check."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 1250,
   "scope": "_owned_beneath",
   "description": "The predicate is row.c.owner_id == owner. Its equality follows the column's collation, so under a case-, accent- or pad-insensitive collation 'ALICE' or 'alice ' matches rows owned by 'alice'."
  },
  {
   "kind": "sink",
   "file": "src/vfs/models/rows.py",
   "line": 471,
   "scope": "build_vfs_tables entries.owner_id",
   "description": "Column('owner_id', _string(255)) compiles to 'owner_id VARCHAR(255)' on mariadb/mysql, with no COLLATE and no binary type (confirmed by the hunter's DDL compile). Its comparisons therefore follow the server's default collation."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/models/rows.py",
   "line": 188,
   "description": "_string returns String(length).with_variant(String(length, collation=MSSQL_UTF8_COLLATION), 'mssql'). Only MSSQL gets a binary collation."
  },
  {
   "file": "src/vfs/models/rows.py",
   "line": 224,
   "description": "BytewiseString gives the mysql family VARBINARY(n) for path and name. Keys are pinned to bytewise comparison there; principal and owner columns are not."
  },
  {
   "file": "src/vfs/storage/grants.py",
   "line": 497,
   "description": "Rights.admits does self._owned.get(owner_id), an exact dict lookup. This is why file rows stay hidden while road directories leak: the SQL and Python sides of the same rule disagree."
  },
  {
   "file": "src/vfs/storage/grants.py",
   "line": 629,
   "description": "Grant rows are grouped by principal_id and looked up by exact sub and group name. Case-variant grant or membership rows that a collation-insensitive fetch returns are dropped in Python, so grant inheritance is not affected."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 545,
   "description": "The narrow() docstring says fetched rows still pass holds() at the view's rung. That Python re-check covers listing rows but not road(), which returns SQL-derived directory paths directly."
  },
  {
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 776,
   "description": "_visible_lexicon aggregates count and sum(dl) in SQL over the visible-entries union, which uses owner_id == owner (ranges.py:128-130) with no row-level re-check. Under a case-insensitive collation it would count the victim's chunks into the corpus statistics. This is a minor side channel and was not demonstrated."
  },
  {
   "file": "docker/compose.test.yml",
   "line": 53,
   "description": "The MariaDB leg runs image mariadb:11.8 with no charset or collation override, and nothing in src sets mysql_collate or charset on the tables. The engine tests never use a case-variant principal, so no test pins this."
  },
  {
   "file": "agents/v17-p3/artifacts/evidence/owner-collation-verify.txt",
   "line": 1,
   "description": "Independent SQLite simulation (sandboxed). Under BINARY, only 'alice' sees anything. Under NOCASE, 'ALICE' sees glob ['/hr','/hr/q3'] and ls /hr ['/hr/q3'], stat /hr/q3 succeeds, read is refused, and a write into the directory returns permission_denied. Under RTRIM, 'alice ' sees the same. 'bob' sees nothing and gets not_found throughout."
  }
 ],
 "blockers": [
  "No real MariaDB or MySQL engine may run in this audit's sandbox (no Docker and no network, loopback included). The behavior was shown only on SQLite, with owner_id rewritten to COLLATE NOCASE or RTRIM as stand-ins for MariaDB's case-, accent- and pad-insensitive default collation. That MariaDB 11.8's actual default makes 'ALICE' = 'alice' and 'alice ' = 'alice' on the compiled column was not observed.",
  "Whether a deployment exposes this depends on two facts outside source. The first is the production schema's database or table default collation. The second is whether the host's identity provider can issue a sub that differs from another principal's only by case, accents or trailing spaces."
 ],
 "validation_plan": {
  "local": "Start a disposable mariadb:11.8 container from docker/compose.test.yml (profile mariadb, default collation). First run SELECT @@collation_database and SHOW FULL COLUMNS FROM vfs_entries to record owner_id's collation. Then use DatabaseStorage(url='mariadb+aiomysql://vfs:vfs@localhost:<compose port>/vfs'). As Authority.system(), write /hr/q3/alice-review.txt with owner_id='alice' (parents=True) and set posture('/', 'none'). Next, as Authority.of(Principal(x)) for x in 'ALICE', 'alice ', 'Alicé', with 'bob' as the control, call glob(patterns=('/**',)), ls('/hr'), stat('/hr/q3'), read('/hr/q3/alice-review.txt') and write('/hr/q3/planted.txt'). Expected if real: the variants see /hr and /hr/q3 and stat succeeds, the write returns permission_denied, and read is refused, while bob gets empty results and not_found. To check a fix: pin owner_id and the grants and memberships principal and group columns (plus granted_by and actor columns) to a bytewise type on the mysql family, either VARBINARY as BytewiseString does or COLLATE utf8mb4_bin. Rerun the probe and expect every variant to match bob. Add an engine-leg regression test asserting that a case-variant principal sees no road directory.",
  "deployment": "The owner runs SELECT @@collation_database and SHOW FULL COLUMNS FROM vfs_entries LIKE 'owner_id' on the production MariaDB or MySQL schema. On Oracle, the owner checks NLS_COMP and NLS_SORT for the session. The owner then confirms whether the identity provider or host mapping can mint subs that differ from existing ones only by case, accents or trailing spaces, for example user-chosen usernames or emails without normalisation."
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

- Scratch, the only place you or target code may write: `./agents/f16-p5/scratch/`. Never write `./agents/f16-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f16-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f16-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs:models/rows.py:_string:principal-columns-unpinned-collation-mysql-family"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
