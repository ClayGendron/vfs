# Candidate verifier brief for `v02-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) h01-grants. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "src/vfs/storage/backends/database/rights.py:grant-refusal:addressed-path-gate-ignores-posture-holes-beneath",
  "title": "grant() is checked only at the addressed path, so a caller with read_write from the everyone posture can grant itself (or anyone) read_write over a private posture hole beneath",
  "description": "Before a grant or revoke, the grant verbs check one thing: does the caller hold read_write at the exact path it addressed? That check counts read_write the caller gets from the everyone level (the posture). The row a grant writes, though, covers the path and its whole subtree. Grant rows only ever add access, and a principal's grant outranks any deeper, narrower posture. Take a mount whose ancestor posture gives everyone read_write (the default for a fresh mount) and whose child folder has a narrower posture, such as none: the documented 'open root with a private child' shape. On that mount, any named principal can grant itself read_write at the ancestor and then read, overwrite, and re-posture the private child. So can anonymous through the router, by granting to a principal it names. The caller held nothing in that child. delete/move/sweep run a subtree check that catches this very posture hole. grant and revoke do not.",
  "root_cause": "_grant_refusal (rights.py:1305-1336) reads only the posture rows on the addressed path's ancestor chain (ancestors_and_self, line 1327). It passes as soon as Rights.reaches(path, label) is true (line 1332). reaches (grants.py:477-479) is a point test: everyone_level >= need at the path itself, or the caller's spans cover that one path. It never asks whether the caller holds the level across the subtree the new row will cover. grant_rows then upserts a principal row at path (rights.py:919, 1356-1376). resolve and Rights.covers/admits (grants.py:150-152, 485-494, 624-629) apply that row to every path beneath, even under posture holes, because principal rows only widen.",
  "intended_behavior": "Spec 058 (line 74): the granting subject set must hold read_write on the path, 'and may grant at most its own level (attenuation)'. The router docstring (base.py:1614-1615) says 'so nobody grants more than it holds'. The grant_rows docstring (rights.py:909-910) says 'what it grants never exceeds its own level there'. Spec 058 (line 64) requires subtree mutations to check beneath the target 'since an owner-floor row or a posture hole can sit inside a writable directory'. A grant or revoke at /P should be refused unless the granter holds read_write throughout /P's subtree, either by its own covering spans or with no posture row beneath /P giving everyone less than read_write.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 1599,
    "scope": "AsyncVirtualFileSystem.grant",
    "description": "The public grant verb accepts path, principal, and level from the caller and routes through _route_grant. With no authority it acts as default_authority or anonymous (base.py:3094-3107)."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/base.py",
    "line": 2025,
    "scope": "AsyncVirtualFileSystem._route_grant",
    "description": "Applies only the mount PermissionMap/_gate_entry for the addressed rel path, then dispatches to storage.grant (line 2044)."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1577,
    "scope": "DatabaseStorage._grant_write",
    "description": "Bumps the revision, resolves the gate at VERB_RUNGS['grant'] = read_write (line 1595), and runs grant_rows."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 1327,
    "scope": "_grant_refusal",
    "description": "Reads posture rows only for ancestors_and_self(path) and computes the everyone label at the addressed path. Posture rows beneath the path are never read."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 1332,
    "scope": "_grant_refusal",
    "description": "Returns None (allowed) if gate.resolution.at('read_write').reaches(path, label). A read_write everyone level at the path is enough."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/grants.py",
    "line": 477,
    "scope": "Rights.reaches",
    "description": "A point test: everyone_level >= need or self.covers(path). It does not test the subtree (contrast covers_subtree at line 481, which WriteGate.subtrees uses at rights.py:754)."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 919,
    "scope": "grant_rows -> _upsert_grant",
    "description": "Writes (principal, path, read_write). Rights.admits (grants.py:493) then admits every row beneath path through covers(), whatever the deeper posture says."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 1305,
    "description": "_grant_refusal is the shared gate for grant, revoke, and posture. It judges read_write only at the addressed path."
   },
   {
    "file": "src/vfs/storage/grants.py",
    "line": 477,
    "description": "reaches() is a point check. covers_subtree() exists (line 481), but the grant gate does not use it."
   },
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 730,
    "description": "WriteGate.subtrees is the sibling control. delete/move/sweep use it to refuse when a row beneath the target fails the rung (a posture hole). grant/revoke have no equivalent check."
   },
   {
    "file": "src/vfs/storage/grants.py",
    "line": 493,
    "description": "Rights.admits returns True on covers(path), so a principal row at /P admits /P/Q rows even when everyone_level there is 0."
   },
   {
    "file": "src/vfs/base.py",
    "line": 1615,
    "description": "The declared contract: 'so nobody grants more than it holds'."
   },
   {
    "file": "src/vfs/storage/backends/database/rights.py",
    "line": 910,
    "description": "The grant_rows docstring: 'what it grants never exceeds its own level there'."
   },
   {
    "file": "context/specifications/archive/058-row-level-permission-grants/spec.md",
    "line": 74,
    "description": "The spec requires attenuation: the granter 'may grant at most its own level'."
   },
   {
    "file": "context/specifications/archive/058-row-level-permission-grants/spec.md",
    "line": 64,
    "description": "Subtree mutations must check beneath the target because 'a posture hole can sit inside a writable directory'. The grant path is not held to this."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 205,
    "description": "The default first-touch posture is read_write, so a mount that adds a private child posture without changing the root is exposed."
   },
   {
    "file": "tests/support/grants_contract.py",
    "line": 817,
    "description": "test_nobody_grants_more_than_it_holds tests attenuation only at the addressed path. No test covers a grant on an ancestor of a posture hole."
   }
  ],
  "conditions": [
   {
    "kind": "system_configuration",
    "description": "Some ancestor path P has an everyone level of read_write (the default first-touch root posture, or an explicit posture), and a deeper posture row at P/Q narrows everyone to less (for example none, list, or read). Spec 058 names this 'open root with a private child' shape."
   },
   {
    "kind": "authentication_level",
    "description": "Any named Authority with no grants of its own suffices. Through the router, an anonymous call (no authority and no default_authority) also suffices, because unauthenticated_at is judged only at P, where everyone holds read_write. Anonymous cannot name itself as grantee ('anon' is reserved), so it grants to a principal it names."
   },
   {
    "kind": "data_state",
    "description": "Protected rows exist beneath P/Q (or are written later: the grant also covers future rows)."
   }
  ],
  "execution": {
   "attacker_perspective": "A named principal 'mallory' with no grant rows, or an anonymous router caller, on a mount whose root posture is read_write and whose /P/Q posture is none.",
   "payloads": [
    "await storage.grant(path=Path('/P'), principal='mallory', level='read_write', authority=Authority.of(Principal('mallory')))",
    "await fs.grant('/P', 'mallory', 'read_write')  # AsyncVirtualFileSystem, no authority -> anonymous",
    "await storage.revoke(path=Path('/P'), principal='bob', authority=Authority.of(Principal('mallory')))"
   ],
   "instructions": [
    "Create InMemoryStorage(). As Authority.system(), write /P/Q/secret.md ('SECRET-Q') with parents=True, set posture('/', 'read_write'), then set posture('/P/Q', 'none').",
    "As mallory, confirm the baseline: read('/P/Q/secret.md') -> not_found; grant('/P/Q', 'mallory', 'read_write') -> not_found; posture('/P/Q', 'read_write') -> not_found; delete('/P') -> permission_denied.",
    "As mallory, call grant('/P', 'mallory', 'read_write'). It answers ok.",
    "As mallory, read /P/Q/secret.md, overwrite it, and set posture('/P/Q', 'read_write').",
    "Repeat through AsyncVirtualFileSystem(storage=...) with no authority (anonymous): grant('/P/Q', ...) -> unauthenticated, grant('/P', 'mallory', 'read_write') -> ok, then mallory reads the secret.",
    "Revoke variant: system grants bob read_write at /P. mallory (everyone read_write at /P) revokes bob at /P, and bob loses /P/Q.",
    "Run inside tools/sandbox-run.py with .venv/bin/python -I (no network, empty env, scratch-only writes)."
   ],
   "observed_result": "Before the attack: mallory read /P/Q/secret.md -> vfs.not_found, grant at /P/Q -> vfs.not_found, posture at /P/Q -> vfs.not_found, delete /P -> vfs.permission_denied. Attack: grant /P mallory read_write -> ok (row {'principal_id':'mallory','path_prefix':'/P','level':'read_write','granted_by':'mallory'}). After: read /P/Q/secret.md -> ok 'SECRET-Q', overwrite -> ok, posture /P/Q read_write -> ok. Router, anonymous: read /P/Q/secret.md -> vfs.unauthenticated, grant /P/Q -> vfs.unauthenticated, grant /P mallory read_write -> ok, then mallory read -> ok 'SECRET-Q'. Revoke variant: bob read ok -> mallory revoke bob at /P ok -> bob read vfs.not_found. Control: ann granted read_write at /P by system already reads /P/Q (no gain for a grant-derived holder)."
  },
  "remediation": {
   "strategy": "Make the grant and revoke gate check the subtree the row will cover, not just the addressed point. When the caller's own spans do not cover the whole subtree at read_write (rights.whole or rights.covers_subtree(path)), read the posture ('*') rows strictly beneath path. Read them in pages over the bytewise range (path + '/', path + '0') on grants (principal_id = '*'), chunked by the membership budget. Refuse with permission_denied if any of them gives everyone less than read_write at a prefix the caller's spans do not cover whole. posture() itself needs no change, because deeper posture rows already win, but it may share the helper. Add a contract test: open root, private /P/Q; a principal with no rows (and anonymous through the router) is refused grant and revoke at /P and /, and is still allowed at an unrelated open sibling. Run it on every StorageContract leg.",
   "code_changes": [
    {
     "file_name": "src/vfs/storage/backends/database/rights.py",
     "fixed_code": "    if gate.resolution.at(gate.needs.primary).reaches(str(path), label):\n        rights = gate.resolution.at(gate.needs.primary)\n        if principal is not None and not (rights.whole or rights.covers_subtree(str(path))):\n            need = LEVEL_RANK[gate.needs.primary]\n            async for prefix, level in _postures_beneath(session, tables, profile, str(path)):\n                if LEVEL_RANK[level] < need and not rights.covers_subtree(prefix):\n                    return denied(path)\n        return None\n\n# _postures_beneath: page grants where principal_id == EVERYONE_NAME and\n# path_prefix > path + '/' - 1 byte range (path + '/', path + '0'), ordered by path_prefix, bounded page size."
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "The attacker needs only an ordinary named Authority, or none at all through the router. The precondition is a deliberate operator setup (a permissive ancestor posture with a narrower child posture). That setup is documented and tested, and the default first-touch posture already supplies the read_write ancestor."
   },
   "impact": {
    "score": "high",
    "reason": "An unauthorized principal gets full read_write over a subtree the operator made private. It can read every row, overwrite or trash them, mint grants, and re-posture the subtree open to everyone, anonymous included. The revoke variant also lets it strip other principals' access beneath. This crosses the row-rights boundary between anonymous or named callers and protected entries."
   },
   "overall_severity": "high"
  },
  "confidence": {
   "score": "high",
   "reason": "The source trace is complete. A bounded local run on InMemoryStorage (the same DatabaseStorage code path as production engines) shows the refused baseline, the grant succeeding, and the protected read and overwrite afterwards, directly and through the router as anonymous. A control rules out the grant-derived case."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20revoke%20posture::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23grant%20and%20posture%20gate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h01-grants",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/memory.py",
   "src/vfs/base.py"
  ],
  "invariant": "A grant (and a revoke) never gives or takes more than the granter holds across the subtree the row covers (attenuation: 'nobody grants more than it holds')",
  "method": "local",
  "result": "Disproved: the invariant does not hold. Setup: the root posture is read_write and /P/Q has posture none. mallory, a named principal with no rows, is refused when reading /P/Q/secret.md (not_found), when granting at /P/Q (not_found), when setting posture at /P/Q (not_found), and when deleting /P (permission_denied, the subtree check). Yet grant(/P, 'mallory', 'read_write', authority=mallory) answers ok. After it, mallory reads 'SECRET-Q', overwrites it, and sets /P/Q's posture to read_write. Through the router with no authority (the anonymous fallback), anonymous gets unauthenticated at /P/Q but grant('/P','mallory','read_write') answers ok, and mallory then reads the secret. Revoke variant: mallory revokes bob's /P row and bob loses /P/Q. Control: a principal whose read_write comes from its own grant at /P already holds /P/Q, so no gain there.",
  "artifact": "agents/h01-grants/artifacts/evidence/grant-subtree-escalation.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20revoke%20posture::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23grant%20and%20posture%20gate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h01-grants",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/rights.py",
   "src/vfs/storage/grants.py"
  ],
  "invariant": "posture() cannot be used to override a deeper, narrower posture, including while a relabel is in flight",
  "method": "source",
  "result": "Holds. The deepest posture row decides (level_at; posture_regions at grants.py:346-359 subtracts the posture children). inflight_regions (grants.py:369-387) also takes each pending row's cover minus its posture children, so an in-flight wide posture at /P never covers /P/Q's region. revoke/grant refuse the reserved '*' principal (_lawful_principal at rights.py:1349-1353), so a narrower posture row cannot be removed except through posture at its own path, which needs read_write there. With grant closed, posture alone gives no escalation.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23grant%20revoke%20posture::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frights.py%23grant%20and%20posture%20gate::src%2Fvfs%2Fstorage::ATTACK-CLASSES.md%23Access%20control",
  "agent_id": "h01-grants",
  "reviewed_paths": [
   "src/vfs/models/rows.py",
   "src/vfs/storage/grants.py",
   "src/vfs/storage/backends/database/rights.py"
  ],
  "invariant": "A case-variant principal on MariaDB cannot pick up another principal's grant rows or exceed the grant gate through a SQL-only comparison",
  "method": "source",
  "result": "grants.principal_id is _string (rows.py:809), which pins no collation on MariaDB. _grant_rows (rights.py:1169-1179) fetches through a SQL IN, but resolve (grants.py:624-629) attributes every row by a Python-exact principal_id lookup. A row stored for 'ann' never counts toward the compiled rights of 'ANN'. The SQL-only effects in this unit are row-identity collisions in _upsert_grant (rights.py:1356-1376) and revoke's delete (rights.py:945-950): a grant or revoke naming 'ANN' would replace or delete 'ann''s row at that path. Both are behind _grant_refusal at that path, and that gate already lets the caller grant or revoke any principal there, so the caller gains nothing new. Settled from source. A MariaDB run is not needed for this boundary.",
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

- Scratch, the only place you or target code may write: `./agents/v02-p3/scratch/`. Never write `./agents/v02-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v02-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v02-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `src/vfs/storage/backends/database/rights.py:grant-refusal:addressed-path-gate-ignores-posture-holes-beneath` unless you identify a genuinely different root cause.

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
