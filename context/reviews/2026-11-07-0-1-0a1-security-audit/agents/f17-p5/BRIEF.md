# Final record verifier brief for `f17-p5`

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
 "fingerprint": "vfs:permissions:check_writable:subtree-override-not-consulted",
 "title": "Read-only PermissionMap overrides are bypassed by subtree verbs (delete, sweep, move, copy) addressed at a writable ancestor or destination",
 "description": "The router's PermissionMap is the per-prefix write policy enforced at the routing chokepoint before dispatch (README.md:127), and the mount-admin spec states that a map 'gates every path beneath'. The write gate resolves only the exact rel a verb addresses. A verb whose effect spans a subtree is checked against the rule that covers its addressed root, and never against a read-only override nested beneath that root. A non-system caller with ordinary row rights (the default fresh-mount posture) is refused on every direct write, edit, delete, sweep, move or copy inside the read-only region. Yet the same caller can: trash the read-only rows with delete(ancestor); purge them permanently with sweep(ancestor), after which restore finds nothing; move the ancestor out, rewrite the formerly read-only file at its new address, and move it back; or plant attacker content inside the read-only region in one call by copying or moving a staged tree onto an absent ancestor. The router already applies a subtree rule for bind sites (_busy_guard with subtree=True) but has no equivalent for permission overrides.",
 "root_cause": "check_writable (src/vfs/permissions.py:269-321) resolves the gated rel through PermissionMap._resolve. That function matches only overrides whose prefix equals or covers the path (permissions.py:196) and never looks at overrides lying strictly beneath it. _gate_entry (base.py:2902) calls check_writable_composed only for the addressed rels. It does this for every op, subtree-shaped ones included: single-path delete, restore and sweep at base.py:1748 and 2189, move's src and dest and copy's dest at base.py:2535. So a read rule deeper than the target is invisible to the gate.",
 "intended_behavior": "A read-only override must refuse every write-gated op whose effect lands at or beneath it. For subtree-shaped ops (delete, restore, sweep, move src and dest, copy dest), the gate should refuse with read_only when any layer's map holds a read override strictly beneath the gated rel, or beneath its /.vfs alias. This mirrors how _busy_guard refuses a region that contains a bind site.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 1059,
   "scope": "AsyncVirtualFileSystem.delete (also restore 1094, sweep 1117, move 1233, copy 1246)",
   "description": "A non-system caller (anonymous or a named principal) calls delete('/proj'), sweep('/proj'), move('/proj','/x') or copy/move('/stage','/proj') with its own authority"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 1748,
   "scope": "_route_single",
   "description": "Single-path verbs gate with write_rels=(terminal.rel,), the addressed path only. The busy guard just above (1743) checks bind sites beneath the path, but nothing checks permission rules beneath it"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 2535,
   "scope": "_route_two_path",
   "description": "move gates (src, dest) and copy gates dest only. These are the roots of the transferred subtree, not the paths that will be written beneath dest or vacated beneath src"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 2902,
   "scope": "_gate_entry",
   "description": "check_writable_composed(self._permission_layers(full), op) is called once per addressed rel"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/permissions.py",
   "line": 297,
   "scope": "check_writable",
   "description": "Resolution covers only _permission_candidates(rel), meaning the path and its /.vfs alias, through PermissionMap._resolve"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/permissions.py",
   "line": 196,
   "scope": "PermissionMap._resolve",
   "description": "Matches only prefixes that equal or cover the path. '/proj' resolves to the read_write default even though '/proj/locked' is read-only, so the gate returns None"
  },
  {
   "kind": "sink",
   "file": "src/vfs/base.py",
   "line": 1754,
   "scope": "_route_single -> _dispatch_entry",
   "description": "Storage runs the subtree delete or sweep, mutating rows under the read-only override. The move and copy subtree transfer is dispatched the same way from _route_two_path"
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/permissions.py",
   "line": 196,
   "description": "The override match is 'normalized == prefix or normalized.startswith(prefix + \"/\")' only. Nothing checks for override prefixes beneath the path"
  },
  {
   "file": "src/vfs/base.py",
   "line": 2902,
   "description": "The only permission-map call in the gate, invoked with addressed rels only"
  },
  {
   "file": "src/vfs/base.py",
   "line": 2939,
   "description": "_busy_guard does consider the subtree (_bindings_beneath when subtree=True) for bind sites. Subtree-shaped effects are recognised for mounts but not for permission overrides"
  },
  {
   "file": "src/vfs/base.py",
   "line": 122,
   "description": "_BUSY_GUARDED_OPS = {delete, restore, sweep}: the router's own list of ops that act beneath the addressed site"
  },
  {
   "file": "README.md",
   "line": 127,
   "description": "The per-prefix map is documented as enforced at the routing chokepoint before anything dispatches"
  },
  {
   "file": "context/specifications/archive/068-mount-admin-completeness/spec.md",
   "line": 93,
   "description": "Declared intent: a parent layer's map 'still gates every path beneath'"
  },
  {
   "file": "agents/v18-p3/artifacts/evidence/subtree-override-bypass.txt",
   "line": 1,
   "description": "Verifier's independent sandboxed reproduction (harness and output). All six direct controls are refused read_only; delete, sweep, move-out/write/move-back, copy and move onto the ancestor all succeed against the locked file"
  }
 ],
 "conditions": [
  {
   "kind": "system_configuration",
   "description": "The operator configured a read-only PermissionMap override nested beneath a writable non-root prefix of the same entry, for example read_write(read=['/proj/locked']). A read-only region expressed as a separate child mount is protected by the bind-site busy guard instead. An override whose parent is the mount root is reachable only through copy or move onto a missing ancestor, since the root itself cannot be deleted or moved."
  },
  {
   "kind": "authorization_role",
   "description": "The caller holds the row rung that delete, sweep or move needs on the writable ancestor, or that copy or move needs at the destination. A fresh storage's default posture is read_write for everyone, anonymous included, so no grant is needed by default. Row grants still apply where postures are tightened."
  },
  {
   "kind": "data_state",
   "description": "Rows exist under the read-only override (for trash, purge or move-tamper), or the destination ancestor is absent and the caller can stage a tree elsewhere in the same mount (for copy or move planting)."
  }
 ],
 "execution": {
  "attacker_perspective": "A named non-system principal (bob) calls public routed verbs on an AsyncVirtualFileSystem whose root InMemoryStorage carries permissions=read_write(read=['/proj/locked']). The host seeded /proj/locked/policy.txt as 'ORIGINAL' through the storage as Authority.system().",
  "payloads": [
   "await fs.delete('/proj', authority=bob)",
   "await fs.sweep('/proj', authority=bob)",
   "await fs.move(src='/proj', dest='/tmpx', authority=bob); await fs.write(path='/tmpx/locked/policy.txt', content='TAMPERED', authority=bob); await fs.move(src='/tmpx', dest='/proj', authority=bob)",
   "await fs.write(path='/stage/locked/policy.txt', content='FORGED', parents=True, authority=bob); await fs.copy(src='/stage', dest='/proj', authority=bob)",
   "await fs.write(path='/stage/locked/policy.txt', content='FORGED', parents=True, authority=bob); await fs.move(src='/stage', dest='/proj', authority=bob)"
  ],
  "instructions": [
   "Build AsyncVirtualFileSystem(storage=InMemoryStorage(), permissions=read_write(read=['/proj/locked'])) and seed /proj/locked/policy.txt='ORIGINAL' via fs._bindings['/'].storage.write(..., parents=True, authority=Authority.system()).",
   "Controls: as bob, run write, edit, delete('/proj/locked'), sweep('/proj/locked'), move of the locked file, and copy into /proj/locked. Each must classify vfs.read_only.",
   "Run each payload on a fresh filesystem (planting cases with /proj absent), then read /proj/locked/policy.txt as Authority.system().",
   "Command: ./tools/sandbox-run.py ./agents/v18-p3/scratch ./.venv/bin/python -I v_subtree.py (InMemoryStorage over private SQLite, no network)."
  ],
  "observed_result": "All six controls returned success=False with vfs.read_only. delete('/proj') returned success=True and the locked file read not_found; restore('/proj') then brought back 'ORIGINAL', so this effect is soft. sweep('/proj') returned success=True and the file read not_found; restore('/proj') also returned not_found, so the purge is permanent. The move-out/write/move-back sequence succeeded and the file content became ['TAMPERED']. A direct write into the empty locked region was refused read_only, yet copy('/stage','/proj') and move('/stage','/proj') both succeeded and the file content became ['FORGED']. A follow-up direct write was again refused read_only."
 },
 "remediation": {
  "strategy": "Treat delete, restore, sweep, move (src and dest) and copy (dest) as subtree-shaped in the permission gate. Besides resolving the addressed rel, refuse with read_only when any layer's map holds a 'read' override strictly beneath that rel or beneath its /.vfs alias. Thread a subtree flag from _gate_entry through check_writable_composed to check_writable, mirroring the bind-site busy guard. Add regression tests with read_write(read=['/dir/frozen']) asserting that delete('/dir'), sweep('/dir'), restore('/dir'), move('/dir','/x'), move('/stage','/dir') and copy('/stage','/dir') each classify read_only with no storage call recorded. Apply the same flag in the grouped-observations path (base.py:2189).",
  "code_changes": [
   {
    "file_name": "src/vfs/permissions.py",
    "fixed_code": "def check_writable_composed(layers: Iterable[PermissionLayer], op: str, *, subtree: bool = False) -> Result | None:\n    for layer in layers:\n        denied = check_writable(layer.permission_map, op, layer.rel, mount_prefix=layer.mount_prefix, subtree=subtree)\n        if denied is not None:\n            return denied\n    return None\n\n\ndef check_writable(permission_map, op, rel, *, mount_prefix=ROOT, subtree=False):\n    if op not in WRITE_GATED_OPS:\n        return None\n    first, *rest = _permission_candidates(rel)\n    resolved = permission_map._resolve(first)\n    for candidate in rest:\n        alternate = permission_map._resolve(candidate)\n        if alternate.rule_prefix is None:\n            continue\n        if resolved.rule_prefix is None or len(alternate.rule_prefix) > len(resolved.rule_prefix):\n            resolved = alternate\n    if resolved.permission == \"read_write\" and subtree:\n        resolved = _read_rule_beneath(permission_map, rel) or resolved\n    if resolved.permission == \"read_write\":\n        return None\n    ...  # unchanged error construction\n\n\ndef _read_rule_beneath(permission_map: PermissionMap, rel: str) -> _Resolution | None:\n    \"\"\"A read-only override strictly beneath *rel* (or its metadata alias), which a subtree verb would reach.\"\"\"\n    for candidate in _permission_candidates(rel):\n        base = \"\" if candidate == \"/\" else candidate\n        for prefix, perm in permission_map.overrides:\n            if perm == \"read\" and prefix.startswith(base + \"/\"):\n                return _Resolution(\"read\", prefix)\n    return None"
   },
   {
    "file_name": "src/vfs/base.py",
    "fixed_code": "# Mutations whose effect reaches beneath the addressed path.\n_SUBTREE_OPS: frozenset[Op] = frozenset({\"delete\", \"restore\", \"sweep\", \"move\", \"copy\"})\n\n# in _gate_entry:\n            err = check_writable_composed(self._permission_layers(full), op, subtree=op in _SUBTREE_OPS)"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Requires an operator map with a read-only override nested under a writable prefix, which is an advertised read_write(read=[...]) pattern, and a caller with row rights on the ancestor. A fresh mount's default posture already gives everyone read_write. delete, move and copy are ordinary agent verbs."
  },
  "impact": {
   "score": "medium",
   "reason": "Breaks the integrity and availability of data the operator marked read-only, within one mount. Content can be replaced or planted (move/copy), soft-deleted (delete, which restore can undo) or permanently purged (sweep). Row-level grants still apply, there is no confidentiality loss, and there is no escape across mounts."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "Independently reproduced end to end through public router verbs on InMemoryStorage, with matched refused controls. Source shows the gate never consults overrides beneath the addressed path, and the declared intent (README, spec 068) is that the map gates every path beneath."
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

- Scratch, the only place you or target code may write: `./agents/f17-p5/scratch/`. Never write `./agents/f17-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f17-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f17-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs:permissions:check_writable:subtree-override-not-consulted"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
