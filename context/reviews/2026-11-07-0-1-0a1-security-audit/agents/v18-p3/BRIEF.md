# Candidate verifier brief for `v18-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) h04-router. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs:permissions:check_writable:subtree-override-not-consulted",
  "title": "Read-only PermissionMap overrides are bypassed by subtree verbs (delete cascade, move, copy, sweep, restore) addressed at a writable ancestor or destination",
  "description": "The router's PermissionMap is documented as the per-prefix write policy enforced at the routing chokepoint before anything dispatches (README.md:127; read_write(read=[...]) reads as 'writable with these read-only holes'). The gate resolves only the exact path a verb addresses. A verb whose effect spans a subtree is therefore checked against the ancestor's rule and never against a read-only override nested beneath it. Any caller with row rights on the ancestor can: trash the read-only rows with delete(ancestor), destroy them permanently with sweep(ancestor), move the ancestor out, edit the formerly read-only file at its new address and move it back, or plant attacker content inside the read-only region in one call with copy/move of a staged tree onto the ancestor. The same router already applies a subtree rule for bind sites (_busy_guard with subtree=True) but not for permission overrides.",
  "root_cause": "check_writable (src/vfs/permissions.py:269-321) resolves the gated rel through PermissionMap._resolve, which matches only overrides whose prefix equals or covers the path (permissions.py:195-196). It never considers overrides lying strictly beneath the path. _gate_entry (base.py:2902) calls check_writable_composed with only the addressed rels for every op, including the subtree-shaped ones (delete, restore, sweep, move src/dest, copy dest), so a read-only rule deeper than the target is invisible to the gate.",
  "intended_behavior": "A read-only override must refuse every write-gated op whose effect lands at or beneath it. For subtree-shaped ops, the gate should refuse with read_only when any layer holds a read rule strictly beneath the target rel (and its /.vfs alias), mirroring how _busy_guard refuses a region that holds a bind site.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 1059,
    "scope": "AsyncVirtualFileSystem.delete / move / copy / sweep",
    "description": "Caller (anonymous or a named agent) calls delete('/dir'), sweep('/dir'), move('/dir','/moved') or copy/move('/stage','/dir') with its own authority"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/base.py",
    "line": 1748,
    "scope": "_route_single",
    "description": "Single-path verbs gate with write_rels=(terminal.rel,): only the addressed path; the busy guard above (1743) checks bind sites beneath but nothing checks permission rules beneath"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/base.py",
    "line": 2535,
    "scope": "_route_two_path",
    "description": "move gates (src, dest) and copy gates dest only: the roots of the transferred subtree, not the paths that will be written beneath dest or vacated beneath src"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/base.py",
    "line": 2902,
    "scope": "_gate_entry",
    "description": "check_writable_composed(self._permission_layers(full), op) is called per addressed rel only"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/permissions.py",
    "line": 297,
    "scope": "check_writable",
    "description": "Resolution walks _permission_candidates(rel) (the path and its /.vfs alias) through PermissionMap._resolve"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/permissions.py",
    "line": 196,
    "scope": "PermissionMap._resolve",
    "description": "Matches only prefixes that equal or cover the path; '/dir' resolves to the read_write default even though '/dir/frozen' is read-only, so the gate returns None"
   },
   {
    "kind": "sink",
    "file": "src/vfs/base.py",
    "line": 1754,
    "scope": "_route_single -> _dispatch_entry",
    "description": "Storage executes the subtree delete/sweep (and, via base.py:2545, the subtree move/copy), mutating rows under the read-only override"
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/permissions.py",
    "line": 195,
    "description": "Override loop matches 'normalized == prefix or normalized.startswith(prefix + \"/\")' only; no check for prefixes beneath the path"
   },
   {
    "file": "src/vfs/base.py",
    "line": 2939,
    "description": "_busy_guard does consider the subtree (_bindings_beneath when subtree=True) for bind sites, showing subtree-shaped effects are recognised for mounts but not for permission overrides"
   },
   {
    "file": "src/vfs/base.py",
    "line": 122,
    "description": "_BUSY_GUARDED_OPS = {delete, restore, sweep}: the router's own list of ops that act beneath the addressed site"
   },
   {
    "file": "README.md",
    "line": 127,
    "description": "Per-prefix map documented as enforced at the routing chokepoint before anything dispatches"
   },
   {
    "file": "src/vfs/base.py",
    "line": 2902,
    "description": "The only permission-map call site in the gate, invoked with addressed rels only"
   }
  ],
  "conditions": [
   {
    "kind": "system_configuration",
    "description": "The operator configured a read-only PermissionMap override nested beneath a writable non-root prefix of the same mount (e.g. read_write(read=['/dir/frozen']), or an explicit nested PermissionMap). A read-only override directly under a mount root is not reachable this way, because the root cannot be deleted or moved and a bind site is busy."
   },
   {
    "kind": "authorization_role",
    "description": "The caller holds row rung read_write on the writable ancestor (for delete/move/sweep/restore) or add/contribute plus read_write on the destination (copy/move). A fresh mount's default posture gives everyone, including anonymous, read_write, so no grant is needed by default."
   },
   {
    "kind": "data_state",
    "description": "Rows exist under the read-only override (for delete/move/sweep tampering), or the caller can stage a tree elsewhere and the destination ancestor is absent (copy/move planting)."
   }
  ],
  "execution": {
   "attacker_perspective": "A named non-system agent principal (alice) calling routed verbs on an AsyncVirtualFileSystem whose root InMemoryStorage carries permissions=read_write(read=['/dir/frozen']), with /dir/frozen/ledger.md seeded by the host as 'LOCKED v1'.",
   "payloads": [
    "await fs.delete('/dir', authority=alice)",
    "await fs.sweep('/dir', authority=alice)",
    "await fs.move(src='/dir', dest='/moved', authority=alice); await fs.write(path='/moved/frozen/ledger.md', content='TAMPERED', authority=alice); await fs.move(src='/moved', dest='/dir', authority=alice)",
    "await fs.write(path='/stage/frozen/ledger.md', content='FORGED', parents=True, authority=alice); await fs.copy(src='/stage', dest='/dir', authority=alice)",
    "await fs.write(path='/stage/frozen/ledger.md', content='FORGED', parents=True, authority=alice); await fs.move(src='/stage', dest='/dir', authority=alice)"
   ],
   "instructions": [
    "Construct AsyncVirtualFileSystem(storage=InMemoryStorage(), permissions=read_write(read=['/dir/frozen'])) and seed /dir, /dir/frozen and /dir/frozen/ledger.md through the storage as Authority.system().",
    "As control, confirm write/delete/move at /dir/frozen and /dir/frozen/ledger.md by alice classify vfs.read_only.",
    "Run each payload on a fresh filesystem and read /dir/frozen/ledger.md as Authority.system().",
    "Commands: ./tools/sandbox-run.py ./agents/h04-router/scratch .venv/bin/python -I t1_subtree.py and t3_copy.py (SQLite in-memory only, no network)."
   ],
   "observed_result": "Controls refused with vfs.read_only. delete('/dir') success=True, then read of /dir/frozen/ledger.md -> not_found. sweep('/dir') success=True, row purged (not_found). move-out/write/move-back all success=True and the file content became ['TAMPERED']. copy('/stage','/dir') and move('/stage','/dir') success=True and /dir/frozen/ledger.md content became ['FORGED']."
  },
  "remediation": {
   "strategy": "Treat delete, restore, sweep, move and copy as subtree-shaped in the permission gate: in addition to resolving the addressed rel, refuse when any layer's map holds a 'read' override strictly beneath that rel (or beneath its /.vfs alias). Apply it to move's src and dest and to copy's dest. This mirrors the bind-site busy guard. Add a regression test with read_write(read=['/dir/frozen']) asserting delete('/dir'), sweep('/dir'), restore('/dir'), move('/dir','/x'), move('/stage','/dir') and copy('/stage','/dir') each classify read_only with no storage call recorded.",
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
    "reason": "Needs an operator map with a read-only override nested under a writable non-root prefix (an advertised PermissionMap pattern) and a caller with row rights on the ancestor; a fresh mount's default posture already gives everyone read_write. delete, move and copy are ordinary agent verbs."
   },
   "impact": {
    "score": "medium",
    "reason": "Integrity and availability of data the operator marked read-only, within one mount: content can be replaced or planted (move/copy), trashed (delete) or irrecoverably purged (sweep). Row-level grants still apply, so no cross-principal read and no escape across mounts."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "high",
   "reason": "Reproduced end to end through the public router verbs on InMemoryStorage with matched refused controls; the source shows the gate never consults overrides beneath the addressed path."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/permissions.py",
   "README.md"
  ],
  "invariant": "A PermissionMap read-only override must refuse every write-gated op whose effect lands on a row at or beneath the override, including subtree-shaped ops (cascade delete, move, copy, sweep, restore) addressed at a writable ancestor or a writable destination",
  "method": "local",
  "result": "Violated. With read_write(read=['/dir/frozen']) on the root, a non-system caller (alice) is correctly refused write/delete/move at /dir/frozen/*, but delete('/dir') trashes /dir/frozen/ledger.md, sweep('/dir') purges it, move('/dir','/moved') + write('/moved/frozen/ledger.md') + move('/moved','/dir') replaces the locked body with 'TAMPERED', and copy('/stage','/dir') or move('/stage','/dir') plants attacker content at /dir/frozen/ledger.md in one call. check_writable resolves only the addressed path (longest prefix that covers it), never overrides strictly beneath it; the router does apply a subtree rule for bind sites (_busy_guard subtree=True) but not for permission overrides.",
  "artifact": "agents/h04-router/artifacts/evidence/permissionmap-subtree-bypass.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/permissions.py"
  ],
  "invariant": "parents=True on write/mkdir must not revive tombstoned or create rows in a read-only region beyond what design intends",
  "method": "local",
  "result": "With read_only(write=['/a/b/c']), write('/a/b/c/new.md', parents=True) mints empty directory rows /a and /a/b inside the read-only default (direct mkdir('/a') is refused read_only). With a tombstoned read-only ancestor, the write is refused not_found and nothing revives. Minting of brand-new ancestors is the documented carve-out that lets a writable hole exist in a read-only mount; recorded as hardening, not a finding.",
  "artifact": "agents/h04-router/artifacts/evidence/t2_parents.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/ops.py",
   "src/vfs/permissions.py"
  ],
  "invariant": "Every write-shaped verb runs _gate_entry (capability minus deny_ops, reserved grammar, composed PermissionMap layers) before dispatch",
  "method": "source",
  "result": "Holds. _route_single (base.py:1748), _dispatch_grouped_observations, _route_two_path (2535-2537, both endpoints for move, dest plus read-grammar src for copy), _route_entry_batch, _route_edge_batch (both endpoints) and _route_grant (2039) all call _gate_entry; WRITE_GATED_OPS = MUTATING_OPS | GRANT_WRITE_OPS covers write/edit/delete/restore/sweep/mkdir/mkedge/rmedge/move/copy/grant/revoke/posture/add_member/remove_member. run is EXEC (not write-gated) but no in-tree storage implements SupportsRun, and deny_ops can mask it. caps = declared_caps - deny_ops is recomputed whole on every meta replacement (MountMeta.__post_init__); read ops cannot be masked by design.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/permissions.py",
   "tests/test_permissions.py"
  ],
  "invariant": "The /.vfs/X -> /X metadata alias must not loosen a read-only rule",
  "method": "source",
  "result": "Holds. _permission_candidates keeps the canonical /.vfs path first and the alias only wins when its matched rule prefix is strictly longer; a read rule on /X therefore also tightens /.vfs/X, and a writable hole on /X extends to /.vfs/X by design (pinned by test_writable_hole_reaches_its_metadata_projection). /.vfs rows are ordinary stored rows in the database backend, so the alias grants no reach into another path's derived metadata.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/base.py"
  ],
  "invariant": "remount or a deeper bind cannot loosen a parent's map",
  "method": "source",
  "result": "Holds. _permission_layers walks every binding whose path prefixes the target (root included, rel rebased per layer) and check_writable_composed returns the first denial, so a loosened child map is still gated by every ancestor layer. remount and bind are host/operator control-plane methods, not routed verbs.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23_gate_entry::src%2Fvfs%2Fpermissions.py%23PermissionMap%20and%20deny_ops::src%2Fvfs::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h04-router",
  "reviewed_paths": [
   "src/vfs/session.py",
   "src/vfs/sync.py",
   "src/vfs/authority.py"
  ],
  "invariant": "A session or sync facade call runs with exactly the bound authority",
  "method": "source",
  "result": "Holds. AsyncSession has no **kwargs and every one of the 25 verbs forwards authority=self._authority; sync.Session wraps an AsyncSession and forwards through it; VirtualFileSystem twins pass the caller's authority argument unchanged. Authority is a frozen value, re-derived per call, so a close() race leaves no stale or swapped authority (an in-flight verb finishes with the same immutable authority it started with).",
  "artifact": null
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

(no companion selected for this unit)

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

- Scratch, the only place you or target code may write: `./agents/v18-p3/scratch/`. Never write `./agents/v18-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v18-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v18-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs:permissions:check_writable:subtree-override-not-consulted` unless you identify a genuinely different root cause.

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
