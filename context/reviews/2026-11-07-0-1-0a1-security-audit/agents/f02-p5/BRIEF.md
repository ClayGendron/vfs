# Final record verifier brief for `f02-p5`

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
 "fingerprint": "src/vfs/storage/backends/database/rights.py:grant-refusal:addressed-path-gate-ignores-posture-holes-beneath",
 "title": "grant() and revoke() are checked only at the addressed path, so a caller that gets read_write from the everyone posture at an ancestor can grant itself (or anyone) access to a private posture hole beneath it, or revoke others' access there",
 "description": "Before a grant or a revoke, the gate checks one thing: does the caller hold read_write at the exact path it named? That check counts read_write the caller gets from the everyone level (the posture). A grant row, though, covers the path and its whole subtree. Grant rows only add access, and a principal's covering row outranks any deeper, narrower posture. Take a mount whose ancestor posture gives everyone read_write (the default for a fresh DatabaseStorage/InMemoryStorage) and whose child folder has a narrower posture such as none. That is the 'open root with a private child' shape. On it, any named principal with no rows can grant itself read (or read_write) at the ancestor, then read and overwrite the private child and re-posture it open to everyone. An anonymous router caller can do the same by granting to a principal it names. A revoke at the ancestor likewise strips another principal's access inside the hole, which the revoker could not see. The caller held nothing in that child. delete/move/sweep run a subtree check (WriteGate.subtrees) that catches this posture hole. grant and revoke do not.",
 "root_cause": "_grant_refusal (src/vfs/storage/backends/database/rights.py:1305-1336) reads posture rows only for ancestors_and_self(path) (line 1327). It allows the call as soon as gate.resolution.at('read_write').reaches(path, label) is true (line 1332). Rights.reaches (src/vfs/storage/grants.py:477-479) is a point test: everyone_level >= need at the path itself, or the caller's spans cover that one path. It never asks whether the caller holds the level across the subtree the new row will cover, although Rights.covers_subtree (grants.py:481) exists for exactly that. grant_rows then upserts a principal row at path (rights.py:919). Rights.admits (grants.py:493) returns True on covers(path) for every row beneath that prefix, holes included, so the new row overrides the deeper posture. revoke_rows uses the same point gate, so it can delete a row whose effect reaches into a hole.",
 "intended_behavior": "Spec 058 section 8 (context/specifications/archive/058-row-level-permission-grants/spec.md:74) says the granting subject set must hold read_write on the path and 'may grant at most its own level (attenuation)'. The router docstring (src/vfs/base.py:1614-1615) says 'so nobody grants more than it holds'. The grant_rows docstring (rights.py:909-910) says 'what it grants never exceeds its own level there'. Spec 058 section 6 (spec.md:64) requires subtree mutations to check beneath the target 'since an owner-floor row or a posture hole can sit inside a writable directory'. A grant or revoke at /P should be refused unless the granter holds the required level throughout /P's subtree: either its own spans cover the subtree, or no posture row beneath /P gives everyone less than that level at a prefix the spans do not cover.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 1599,
   "scope": "AsyncVirtualFileSystem.grant",
   "description": "Public grant verb taking path, principal and level from the caller. With no authority it acts as default_authority or anonymous (base.py:3094-3107). revoke follows the same route."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 2025,
   "scope": "AsyncVirtualFileSystem._route_grant",
   "description": "Applies only the mount permission layers via _gate_entry for the addressed rel path, then dispatches to the storage grant verb (line 2044)."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1577,
   "scope": "DatabaseStorage._grant_write",
   "description": "Bumps the revision, resolves the gate at VERB_RUNGS[op] = read_write (line 1595), and runs grant_rows or revoke_rows."
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
   "description": "Returns None (allowed) when gate.resolution.at('read_write').reaches(path, label). An everyone read_write at the path is enough."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/grants.py",
   "line": 477,
   "scope": "Rights.reaches",
   "description": "Point test: everyone_level >= need or self.covers(path). It does not test the subtree; covers_subtree at line 481 does, and WriteGate.subtrees uses it, but the grant gate does not."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 919,
   "scope": "grant_rows -> _upsert_grant",
   "description": "Writes (principal, path, level). Rights.admits (grants.py:493) then admits every row beneath path through covers(), whatever the deeper posture says. revoke_rows (rights.py:945-950) deletes a row at path under the same point gate."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 1305,
   "description": "_grant_refusal is the shared gate for grant, revoke and posture. It judges read_write only at the addressed path."
  },
  {
   "file": "src/vfs/storage/grants.py",
   "line": 481,
   "description": "covers_subtree() exists and is the subtree-aware test, but the grant gate calls only the point test reaches() (line 477)."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 730,
   "description": "WriteGate.subtrees is the sibling control. delete/move/sweep use it to refuse when a row beneath the target fails the rung, posture holes included. grant/revoke have no equivalent."
  },
  {
   "file": "src/vfs/storage/grants.py",
   "line": 493,
   "description": "Rights.admits returns True on covers(path), so a principal row at /P admits /P/Q rows even when everyone_level there is 0."
  },
  {
   "file": "src/vfs/base.py",
   "line": 1615,
   "description": "Declared contract: 'so nobody grants more than it holds'."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 910,
   "description": "grant_rows docstring: 'what it grants never exceeds its own level there'."
  },
  {
   "file": "context/specifications/archive/058-row-level-permission-grants/spec.md",
   "line": 74,
   "description": "Spec requires attenuation: the granter 'may grant at most its own level'. grant is not listed among the developer-plane-only verbs, so it is an agent-facing verb."
  },
  {
   "file": "context/specifications/archive/058-row-level-permission-grants/spec.md",
   "line": 64,
   "description": "Subtree mutations must check beneath the target because 'a posture hole can sit inside a writable directory'. The grant verbs are not held to this."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 205,
   "description": "The default posture is read_write, so a mount that only narrows a child posture is exposed with no explicit root posture (reproduced)."
  },
  {
   "file": "tests/support/grants_contract.py",
   "line": 817,
   "description": "test_nobody_grants_more_than_it_holds tests attenuation only at the addressed path. No test grants or revokes at an ancestor of a posture hole."
  },
  {
   "file": "agents/v02-p3/artifacts/evidence/grant-ancestor-of-posture-hole.txt",
   "line": 1,
   "description": "Independent verifier run (InMemoryStorage, sandboxed). Default root posture, /team/hr posture none: eve is refused reading the hr file (not_found), refused granting at /team/hr (not_found), refused deleting /team (permission_denied). eve grant('/', 'eve', 'read') answers ok, then eve reads 'DUMMY-PRIVATE'. eve grant('/team', 'eve', 'read_write') answers ok, then overwrite ok, re-posture /team/hr read_write ok, and anonymous then reads the file. Router with no authority: anon read is unauthenticated and grant at /team/hr is unauthenticated, but grant('/team', 'eve', 'read') answers ok and eve reads the secret."
  },
  {
   "file": "agents/v02-p3/artifacts/evidence/revoke-ancestor-of-posture-hole.txt",
   "line": 1,
   "description": "Independent revoke run: system grants bob read_write at /team, /team/hr posture none. bob reads hr ok, eve gets not_found. eve revoke('/team', 'bob') answers ok, and bob then gets not_found inside the hole."
  }
 ],
 "conditions": [
  {
   "kind": "system_configuration",
   "description": "An ancestor path P has an everyone level that reaches read_write (the default posture of a fresh DatabaseStorage/InMemoryStorage, or an explicit one), and a deeper posture row at P/Q narrows everyone to less (none, list, read, add or contribute). Spec 058 tests this 'open root with a private child' shape."
  },
  {
   "kind": "authentication_level",
   "description": "Any named Authority with no rows of its own is enough. Through the router, an anonymous call (no authority and no default_authority) is also enough, because unauthenticated_at is judged only at P, where everyone holds read_write. Anonymous cannot name itself as grantee ('anon' is reserved), so it grants to a principal it names or controls."
  },
  {
   "kind": "data_state",
   "description": "Protected rows exist beneath P/Q, or are written there later; the grant also covers future rows. For the revoke variant, another principal holds a row at P that gives it access inside P/Q."
  }
 ],
 "execution": {
  "attacker_perspective": "A named principal 'eve' with no grant rows, or an anonymous caller through AsyncVirtualFileSystem, on a mount with the default read_write posture whose /team/hr posture is none.",
  "payloads": [
   "await storage.grant(path=Path('/'), principal='eve', level='read', authority=Authority.of(Principal('eve')))",
   "await storage.grant(path=Path('/team'), principal='eve', level='read_write', authority=Authority.of(Principal('eve')))",
   "await fs.grant('/team', 'eve', 'read')  # AsyncVirtualFileSystem(storage=...), no authority -> anonymous",
   "await storage.revoke(path=Path('/team'), principal='bob', authority=Authority.of(Principal('eve')))"
  ],
  "instructions": [
   "Create InMemoryStorage(). As Authority.system(), write /team/hr/salaries.md (dummy content 'DUMMY-PRIVATE') and /team/notes.md with parents=True. Leave the root at its default posture and set posture('/team/hr', 'none').",
   "As eve, confirm the baseline: read('/team/hr/salaries.md') -> not_found; grant('/team/hr', 'eve', 'read_write') -> not_found; delete('/team') -> permission_denied.",
   "As eve, call grant('/', 'eve', 'read') (or grant('/team', 'eve', 'read_write')). It answers ok.",
   "As eve, read /team/hr/salaries.md (ok, 'DUMMY-PRIVATE'); with the read_write row, overwrite it and set posture('/team/hr', 'read_write'); anonymous can then read it.",
   "Router variant: AsyncVirtualFileSystem(storage=...) with no authority: read -> unauthenticated, grant('/team/hr', ...) -> unauthenticated, grant('/team', 'eve', 'read') -> ok, then eve reads the file.",
   "Revoke variant: system grants bob read_write at /team, then posture('/team/hr', 'none'). eve revoke('/team', 'bob') -> ok; bob's read of the hr file goes from ok to not_found.",
   "Run with tools/sandbox-run.py and .venv/bin/python -I (no network, empty env, scratch-only writes)."
  ],
  "observed_result": "Verifier run, direct: eve read hr -> vfs.not_found; grant at /team/hr -> vfs.not_found; delete /team -> vfs.permission_denied; grant / eve read -> ok; read hr -> ok 'DUMMY-PRIVATE'; grant /team eve read_write -> ok; overwrite -> ok; posture /team/hr read_write -> ok; anonymous read -> ok. Router, anonymous: read -> vfs.unauthenticated; grant /team/hr -> vfs.unauthenticated; grant /team eve read -> ok; eve read -> ok 'DUMMY-PRIVATE'. Revoke: bob read ok; eve read not_found; eve revoke bob at /team ok; bob read not_found. This matches the hunter's independent observation."
 },
 "remediation": {
  "strategy": "Make the grant and revoke gate check the subtree the row covers, not just the addressed point, as WriteGate.subtrees does for delete/move/sweep. When the caller's own spans at the required rung do not cover the subtree (neither rights.whole nor rights.covers_subtree(path)), read the posture ('*') rows strictly beneath path. Read them in bounded pages over the bytewise range (path + '/', path + '0') on grants where principal_id = '*', chunked by the membership budget. Refuse with permission_denied when any of them gives everyone less than the rung at a prefix the caller's spans do not cover whole. Add a contract test on every StorageContract leg: open root, private /P/Q. A principal with no rows, and anonymous through the router, must be refused grant and revoke at /P and at /, and still be allowed at an unrelated open sibling.",
  "code_changes": [
   {
    "file_name": "src/vfs/storage/backends/database/rights.py",
    "fixed_code": "    rights = gate.resolution.at(gate.needs.primary)\n    if rights.reaches(str(path), label):\n        if not (rights.whole or rights.covers_subtree(str(path))):\n            async for prefix, level in _postures_beneath(session, tables, profile, membership_budget, str(path)):\n                if LEVEL_RANK[level] < rights.need and not rights.covers_subtree(prefix):\n                    return denied(path)\n        return None\n\n# _postures_beneath: page grants where principal_id == EVERYONE_NAME and\n# path_prefix in the bytewise range (path + '/', path + '0'), ordered by path_prefix, bounded page size."
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "The attacker needs only an ordinary named Authority, or none at all through the router. The precondition is an operator choice: a narrower posture on a child under a permissive ancestor. That shape is documented and tested, and the default posture already supplies the permissive ancestor."
  },
  "impact": {
   "score": "high",
   "reason": "A principal with no rights in the private subtree gains read or full read_write over it: it reads every row, overwrites or trashes them, and can re-posture the subtree open to everyone, anonymous included. The revoke variant lets it remove other principals' access inside the hole. This crosses the row-rights boundary between anonymous or named callers and protected entries."
  },
  "overall_severity": "high"
 },
 "confidence": {
  "score": "high",
  "reason": "Every trace line was checked in source at 3586750. The verifier reproduced the result independently in a sandboxed InMemoryStorage run, which uses the DatabaseStorage rights code path, both directly and through the router as anonymous, and for revoke. The refused baselines (not_found at the hole, permission_denied on delete) show that the posture hole is meant to be enforced. No other layer checks beneath the grant prefix."
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

- Scratch, the only place you or target code may write: `./agents/f02-p5/scratch/`. Never write `./agents/f02-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f02-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f02-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"src/vfs/storage/backends/database/rights.py:grant-refusal:addressed-path-gate-ignores-posture-holes-beneath"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
