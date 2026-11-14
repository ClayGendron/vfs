# Final record verifier brief for `f14-p5`

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

## 2. The record under review (verdict `confirmed`)

```json
{
 "verdict": "confirmed",
 "fingerprint": "vfs/storage/database/write-trusts-caller-authored-content-hash",
 "title": "Caller-authored content_hash is stored unverified and keys cross-principal render lending",
 "description": "AsyncVirtualFileSystem.write(entries=[...]) stores the content_hash carried on a caller-built Entry without measuring the body storage holds. A bodiless bytes Entry (data=None, source='bytes') keeps any hash the caller names. This works with plain JSON-shaped model_validate dicts and needs no MEASURED_BODY context. The reindex render stage then lends a settled rendering per (content_hash, generation) from any row. The donor query has no owner, rights or deleted_at term. The landing guard compares the key only with the receiving row's own stored hash, which the attacker forged. Two cross-principal effects follow, and both reproduce locally. First, disclosure: a principal with no rights on another principal's file, who knows that file's sha-256, gets its rendered text in a row they own, readable through read and grep. A wrong guess stays pending, so the same write is an existence oracle. Second, integrity: a principal writes their own bytes, then overwrites the row bodiless under the hash of a known public document. The old blob stays, reindex renders the attacker's bytes, and the result is stamped under the forged hash. When another principal later uploads the real document, reindex serves them the attacker's text as their file's content, through read and grep. From source, the same trust also lets a contributor stop the version minting on overwrite (versions.py skips a pre-image whose hash equals the staged hash). The hunter reports that variant as executed; this verifier did not re-run it.",
 "root_cause": "write_rows (writes.py:163) passes entry.content_hash, entry.size_bytes and entry.lines from the caller's Entry into WritePlan.put_file, and _material_values (writes.py:1172) persists them. Entry._derive_and_measure (entry.py:232, 242) measures only when data is not None or source=='text', so a bodiless bytes Entry keeps the caller's hash. _replace_bodies (writes.py:987) skips a row with no content and no data, so a bodiless overwrite keeps the old blob under the new hash. No layer re-measures. render.py treats content_hash as proof of byte identity in two places: when cached_renderings picks a donor, and when land_renderings guards the stamp.",
 "intended_behavior": "A row's content_hash must always be the hash of the body storage holds for it. A content-kind write with neither content nor data must be refused, or must keep the stored row's measured metrics. Render dedup and version dedup must key only on hashes that storage measured itself. A tombstoned row must not lend its rendering.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 958,
   "scope": "AsyncVirtualFileSystem.write",
   "description": "Public verb. It accepts entries=, an iterable of caller-built Entry objects, from any named or anonymous Authority."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 2601,
   "scope": "AsyncVirtualFileSystem._route_entry_batch",
   "description": "Checks only that each item is an Entry, then path-gates and write-gates it. without_mount uses model_copy, which does not re-validate or re-measure."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/models/entry.py",
   "line": 232,
   "scope": "Entry._derive_and_measure",
   "description": "Measures bytes only when data is not None, and text only when source=='text' (line 242). A source='bytes' Entry with data=None keeps the caller's content_hash and mime_type."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 163,
   "scope": "write_rows",
   "description": "Passes entry.content_hash, size_bytes and lines unchanged into plan.put_file."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 1172,
   "scope": "_material_values",
   "description": "Writes the staged caller hash into the entry row. _replace_bodies (line 987) skips bodiless rows, so any earlier blob stays under the forged hash."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 206,
   "scope": "cached_renderings",
   "description": "Selects the lowest-id settled donor per (content_hash, generation). Its predicates are hash, source, stamp and status only: no owner, rights or deleted_at term."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 287,
   "scope": "render_rows",
   "description": "Reuses the cached or in-page rendering for any row whose (content_hash, generation) key matches, without reading that row's blob."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 342,
   "scope": "land_renderings",
   "description": "The stamp guard requires only that the receiving row's own content_hash equals the key. A forged hash passes, so the lent text is inserted as that row's content and is served by read, grep and glean."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/models/entry.py",
   "line": 242,
   "description": "The text branch measures with measure_text unless MEASURED_BODY is supplied. The bytes branch at line 232 runs only when data is not None. Nothing measures a bodiless bytes entry."
  },
  {
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 987,
   "description": "Only rows that have content or data count as bearing. A bodiless overwrite leaves the prior blob in place under the newly written hash."
  },
  {
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 206,
   "description": "The donor WHERE clause filters on hash membership, source, render_source_hash == content_hash, generation and settled status. It has no principal or deleted_at filter."
  },
  {
   "file": "src/vfs/storage/backends/database/versions.py",
   "line": 145,
   "description": "A pre-image version is skipped when its measured hash equals staged.content_hash, which is the caller's value."
  },
  {
   "file": "src/vfs/storage/backends/database/reads.py",
   "line": 107,
   "description": "A caller with list-level rights sees only path and kind, so the hash does not leak there. The attacker must learn H some other way, for example from a public or shared document."
  },
  {
   "file": "agents/v15-p3/artifacts/evidence/verify-output.txt",
   "line": 1,
   "description": "Verifier's own sandboxed run on InMemoryStorage. dave gets not_found on /carol/n.pdf, then gets carol's text CAROL-PRIVATE note 98765 at /dave/y.pdf after a bodiless JSON-shaped Entry and a reindex (cached=1). In the reverse run, carol's upload of a public PDF is served dave's PLANTED text (cached=1)."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker is a named subject with write rights on some path in the same mount as the victim's file. No rights on the victim's path are needed."
  },
  {
   "kind": "data_state",
   "description": "Disclosure requires the attacker to know the exact sha-256 of the victim's bytes, for example a shared or leaked document. Poisoning requires the hash of a document the victim will later upload, such as a public form. It also requires the attacker's row to be the lowest-id settled donor for that hash, for example by planting first."
  },
  {
   "kind": "system_configuration",
   "description": "The operator runs reindex on the storage. This is routine: reindex is what produces any bytes rendering at all."
  }
 ],
 "execution": {
  "attacker_perspective": "Named subject dave with read_write only on /dave. The posture on / is none. Victim carol has read_write on /carol.",
  "payloads": [
   "Entry.model_validate({'path':'/dave/y.pdf','source':'bytes','content_hash':H_carol,'mime_type':'application/pdf'})",
   "fs.write(path='/dave/p.pdf', data=<dave's PDF>) followed by Entry.model_validate({'path':'/dave/p.pdf','source':'bytes','content_hash':H_public,'mime_type':'application/pdf'})"
  ],
  "instructions": [
   "On InMemoryStorage, mkdir /carol and /dave as system, set posture / to none, and grant carol and dave read_write on their own prefixes.",
   "carol writes a dummy PDF at /carol/n.pdf. Run storage.reindex(). Confirm dave's read of /carol/n.pdf returns not_found.",
   "dave writes the bodiless Entry naming carol's hash at /dave/y.pdf. Run reindex. dave reads /dave/y.pdf and greps for carol's text.",
   "On a fresh storage, dave writes his own PDF at /dave/p.pdf, then overwrites it bodiless with the hash of a public PDF. Run reindex. carol uploads the public PDF at /carol/b.pdf. Run reindex. carol reads and greps her file."
  ],
  "observed_result": "In dave's control read, /carol/n.pdf returned vfs.not_found. After the bodiless write and a reindex (rendering report cached=1), dave's read of /dave/y.pdf returned render_status ok with content 'CAROL-PRIVATE note 98765', and dave's grep for it hit /dave/y.pdf. In the reverse case, after reindex (cached=1), carol's read of /carol/b.pdf returned render_status ok with content 'PLANTED text by dave', and carol's grep for PLANTED hit her own file. The hunter separately reports that a forged-hash overwrite in a contribute region minted 0 versions, against 1 for an honest overwrite. This verifier did not re-run that variant."
 },
 "remediation": {
  "strategy": "Measure at the storage seam. In write_rows, refuse a content-kind Entry that has neither content nor data, or ignore its metrics and keep the stored row's. Always compute content_hash, size_bytes and lines from the staged body in the storage layer, on the offload pool when the body is large, and never take them from the Entry. Make MEASURED_BODY router-internal, for example a private sentinel object rather than a public context key. Add entry.deleted_at IS NULL to the cached_renderings donor query. Once every hash is measured by storage, cross-row render lending is safe without a rights term.",
  "code_changes": [
   {
    "file_name": "src/vfs/storage/backends/database/writes.py",
    "fixed_code": "# in write_rows, before plan.put_file:\nif entry.kind in CONTENT_KINDS and entry.content is None and entry.data is None:\n    plan.errors.append(classified(ErrorKind.invalid, entry.path, detail='a file write needs a body'))\n    continue\nmetrics = measure_bytes(entry.data) if entry.data is not None else measure_text(entry.content)\n# pass metrics.content_hash / metrics.size_bytes / metrics.lines instead of entry.*"
   },
   {
    "file_name": "src/vfs/storage/backends/database/render.py",
    "fixed_code": "# in cached_renderings, the donor WHERE clause:\nentry.c.deleted_at.is_(None),"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "low",
   "reason": "The attacker needs a writable path on the victim's mount and the exact hash of the target bytes. For disclosure, that mostly means a shared or leaked document. For poisoning, the hash of a public document is easy to get, but the attacker must plant first to be the lowest-id donor."
  },
  "impact": {
   "score": "medium",
   "reason": "The effect crosses a principal boundary in both directions. In one direction it discloses rendered text and gives an existence oracle. In the other it substitutes attacker-chosen text for another principal's file content, which reaches that principal's agents through read and grep. The version-skip variant also lets a contributor stop history from being minted."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The full source lineage was re-read at commit 3586750. The verifier independently reproduced both the disclosure and the poisoning variants in the sandbox, through the public router API with only JSON-shaped Entry dicts and dummy principals. No spec or docstring declares a caller-supplied hash trusted; spec 175 lists integrity-on-read as not yet built."
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

- Scratch, the only place you or target code may write: `./agents/f14-p5/scratch/`. Never write `./agents/f14-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f14-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f14-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs/storage/database/write-trusts-caller-authored-content-hash"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
