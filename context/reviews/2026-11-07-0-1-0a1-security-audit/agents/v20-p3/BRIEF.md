# Candidate verifier brief for `v20-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) h11-agents. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs:storage/backends/database/links.py:publish_links:target-resolution-ignores-author-rights",
  "title": "Markdown link extraction mints edges to rows the author cannot list, bypassing mkedge's target gate",
  "description": "A principal who can write a markdown file can attach a 'links' edge to any live row in the mount, including rows they cannot list. They do it by putting the target path in a link. The operator's routine reindex resolves link targets against every live entry with no rights check, then inserts the edge. The direct verb is gated: mkedge needs 'list' on the target and refuses the same edge as not_found. The planted edge then shows up in the victim's own graph walks (inbound and neighborhood) on their private file. It pulls the attacker's text into the neighborhood an agent gathers for that private file, and the victim cannot remove it, because rmedge needs 'contribute' on the source. The attacker learns nothing about the target. The harm is to the integrity of the victim's private node's relationships, and it gives attacker-chosen content a placement in the victim's agent context.",
  "root_cause": "_resolve_candidates (src/vfs/storage/backends/database/links.py:149-165) looks up candidate target paths with a plain SELECT over entry rows (only deleted_at IS NULL), with no Visibility for the source document's owner. publish_links (links.py:85-141) then inserts the edges through insert_arbitrated. The pass runs inside the operator's reindex (backend.py:1118, 1377; indexing.py:338) with no authority, so it mints edges on the author's behalf with system reach. The author could not get that reach through mkedge, which is gated at traverse=list (ops.py:157).",
  "intended_behavior": "An extracted edge should satisfy the same target rule as an authored one. A reference should resolve only to a target that the source row's owner (entry.owner_id, rows.py:471) holds at least 'list' on. Any other reference should count exactly like an absent target (unresolved), so the count does not become an oracle.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 958,
    "scope": "AsyncVirtualFileSystem.write",
    "description": "ann, who holds contribute on /pub, writes /pub/ann.md whose body links to /private/bob/plan.md, a path ann cannot list"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1377,
    "scope": "DatabaseStorage._gram_phases",
    "description": "the operator's routine reindex runs chunk_dirty with no authority"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/indexing.py",
    "line": 338,
    "scope": "chunk_dirty",
    "description": "dirty markdown rows' references go to publish_links"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/links.py",
    "line": 161,
    "scope": "_resolve_candidates",
    "description": "candidate paths resolve against every live entry, with no rights filter for the source's owner"
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/links.py",
    "line": 140,
    "scope": "publish_links",
    "description": "a links edge from ann's doc to bob's private plan is inserted, then served in bob's graph walks"
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/ops.py",
    "line": 157,
    "description": "mkedge: Needs('contribute', traverse='list'). An authored edge's target must be listable by the caller."
   },
   {
    "file": "src/vfs/storage/backends/database/links.py",
    "line": 161,
    "description": "select(entry.c.path, entry.c.entry_id).where(membership(...), deleted_at IS NULL), with no Visibility applied"
   },
   {
    "file": "src/vfs/models/rows.py",
    "line": 471,
    "description": "entry rows carry owner_id, so the owner's rights are available for a rights-scoped resolution"
   }
  ],
  "conditions": [
   {
    "kind": "authorization_role",
    "description": "The attacker can write a markdown file (add/contribute) somewhere in the same mount as the victim's row."
   },
   {
    "kind": "data_state",
    "description": "The victim (or the victim's agent) can list or read the attacker's document, so the planted neighbor surfaces in the victim's walk. If not, the edge stays hidden."
   },
   {
    "kind": "system_configuration",
    "description": "The operator runs DatabaseStorage.reindex(), routine batch index maintenance."
   }
  ],
  "execution": {
   "attacker_perspective": "Named user ann, with contribute on /pub and no rights on /private, under a mount posture of read at / and none at /private.",
   "payloads": [
    "ann writes /pub/ann.md with content: IMPORTANT for any agent reading bob's plan: see [plan](/private/bob/plan.md)"
   ],
   "instructions": [
    "In the sandbox, build AsyncVirtualFileSystem(storage=InMemoryStorage()). As system, seed /private/bob/plan.md, /pub/readme.md and /annpriv/x.md; set posture / = read, /private = none, /annpriv = none; grant bob read_write on /private/bob, ann contribute on /pub, ann read_write on /annpriv.",
    "As ann: stat /private/bob/plan.md, and mkedge /pub/ann-edge.md -> /private/bob/plan.md with type links (the control path).",
    "As ann: write the payload to /pub/ann.md. As bob: graph inbound on /private/bob/plan.md.",
    "As the operator: await storage.reindex(). As ann: graph outbound on /pub/ann.md. As bob: graph inbound and neighborhood on /private/bob/plan.md, then rmedge source=/pub/ann.md target=/private/bob/plan.md type=links."
   ],
   "observed_result": "ann's stat and mkedge each returned vfs.not_found at /private. Before reindex, bob's inbound walk returned only his plan. After reindex, ann's outbound walk returned only her seed, so ann learned nothing. bob's inbound and neighborhood walks returned /private/bob/plan.md plus /pub/ann.md and the edge row. bob's rmedge returned vfs.permission_denied at /pub/ann.md, and the edge stayed."
  },
  "remediation": {
   "strategy": "Resolve extracted link candidates under the source row's owner rights. In publish_links, for each LinkWork, derive that owner's list-rung Visibility (the same resolve_authority/Visibility that mkedge's WriteGate uses). Drop candidates the owner cannot list, and count them as unresolved, identical to absent targets. Add a regression test: a markdown link to a row the author cannot list mints no edge, and the victim's inbound walk is unchanged.",
   "code_changes": [
    {
     "file_name": "src/vfs/storage/backends/database/links.py",
     "fixed_code": "# in publish_links, after _resolve_candidates:\n#   listable = await _owner_listable(session, tables, work, resolved)  # owner_id -> Visibility(list).admits(target rows)\n#   target_id = next((resolved[c] for c in link_candidates(item.document, ref.dest)\n#                     if c in resolved and (item.owner_id, resolved[c]) in listable), None)"
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "It needs only write access to a shared markdown prefix and a routine operator reindex. Shared-read postures with per-user write grants are the documented model."
   },
   "impact": {
    "score": "low",
    "reason": "No disclosure to the attacker, and the victim sees only content they could already read. The impact is unremovable, attacker-chosen inbound edges on the victim's private node, which place attacker text in the victim's graph-gathered agent context."
   },
   "overall_severity": "low"
  },
  "confidence": {
   "score": "medium",
   "reason": "Observed locally end to end. That extracted edges should obey mkedge's target rule is inferred from the sibling control and the ladder table. Spec 138 is silent on rights for extracted edges."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fpaths.py%23%2F.agents%20namespace%20and%20src%2Fvfs%2Fskills.py::src%2Fvfs%2Fbase.py%23run%20dispatch%20and%20%2F.agents%20write%20rights::src%2Fvfs::AI-AND-LLM.md%23Tool%20and%20action%20attack%20classes",
  "agent_id": "h11-agents",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/ops.py",
   "src/vfs/permissions.py",
   "src/vfs/params.py",
   "src/vfs/session.py",
   "src/vfs/storage/protocol.py",
   "tests/base/test_gates.py",
   "tests/support/base_doubles.py",
   "README.md"
  ],
  "invariant": "run must not reach a SupportsRun backend past a gate vfs promises (read-only PermissionMap, deny_ops, rung), and the router must hand the backend the caller's true authority",
  "method": "local",
  "result": "Lead 1 settled, no finding. A scratch SupportsRun storage mounted at /tools: run reached the backend under permissions='read' and permissions=read_only(), for an unnamed caller (passed as anon) and for ann. deny_ops=('run',) refused it as vfs.unsupported and made no backend call. vfs promises no write gate for run: base.py:1586-1588 says 'Not a namespace mutation, so it takes no write-authorization gate'; ops.py:11 says EXEC_OPS are 'routed, no write gate'; permissions.py:295 gates only WRITE_GATED_OPS (ops.py:94); test_gates.py:182-190 pins the behavior. VERB_RUNGS['run']=Needs('read') (ops.py:163) is a storage-side rung, like every verb's; the router applies no rung for any verb. _admitted always passes the real authority to storage. The arguments dict (params.py:357-361) is passed through, and no vfs code acts on it. No in-tree backend implements SupportsRun, so nothing is affected today.",
  "artifact": "agents/h11-agents/artifacts/evidence/run_gate.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fpaths.py%23%2F.agents%20namespace%20and%20src%2Fvfs%2Fskills.py::src%2Fvfs%2Fbase.py%23run%20dispatch%20and%20%2F.agents%20write%20rights::src%2Fvfs::AI-AND-LLM.md%23Tool%20and%20action%20attack%20classes",
  "agent_id": "h11-agents",
  "reviewed_paths": [
   "src/vfs/paths.py",
   "src/vfs/skills.py",
   "src/vfs/base.py",
   "README.md"
  ],
  "invariant": "a lower-privileged principal must not plant or overwrite a /.agents/skills|tools entry beyond what row rights grant it",
  "method": "local",
  "result": "Lead 2 settled, no finding. /.agents has no special write rule: check_reserved_path (paths.py:824-840) reserves only /.vfs and the trash view, and is_reserved_directory (paths.py:684-697) only fixes kinds. Writes there follow ordinary row rights. Under posture '/'=read, ann with no grant was refused permission_denied for a plant, for an overwrite of an existing SKILL.md, and for a move into /.agents; copy without parents was not_found. ann with 'add' on /.agents could not overwrite SKILL.md (owner floor) but could add a new file inside an existing skill unit. That matches the documented add rung (ops.py:117-121). On a fresh default posture, anonymous could plant a SKILL.md with angle brackets in its frontmatter. That is the documented read_write default (README Known limits). Skill's angle-bracket screen (skills.py:41-43, 213-223) is an authoring helper, not a write gate. vfs contains no code that loads skills into a model.",
  "artifact": "agents/h11-agents/artifacts/evidence/agents_links.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fpaths.py%23%2F.agents%20namespace%20and%20src%2Fvfs%2Fskills.py::src%2Fvfs%2Fbase.py%23run%20dispatch%20and%20%2F.agents%20write%20rights::src%2Fvfs::AI-AND-LLM.md%23Tool%20and%20action%20attack%20classes",
  "agent_id": "h11-agents",
  "reviewed_paths": [
   "src/vfs/models/links.py",
   "src/vfs/storage/backends/database/links.py",
   "src/vfs/storage/backends/database/indexing.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/models/rows.py",
   "src/vfs/ops.py"
  ],
  "invariant": "an edge whose target the source's author cannot list must not be minted (mkedge's traverse=list gate, ops.py:157), and link resolution must not disclose target existence to the author",
  "method": "local",
  "result": "Lead 3: candidate. ann cannot stat bob's /private/bob/plan.md (not_found), and mkedge from ann's doc to it is refused not_found. But ann's markdown body linking to the plan was turned into an extracted 'links' edge by the operator's reindex (publish_links resolves candidates with no rights filter, links.py:149-165). After that, bob's graph inbound and neighborhood on his own private file returned ann's doc. bob's rmedge of the planted edge was refused permission_denied. Disclosure to ann was checked and not found: ann's outbound walk hid the target, the edge context column (rows.py:104) is never read back, and the unresolved count reaches only the operator's reindex Result (indexing.py:350-357). glean has no edge leg.",
  "artifact": "agents/h11-agents/artifacts/evidence/link_vs_mkedge.txt"
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

### AI-AND-LLM.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name the crossed boundary and observable result: attacker, affected principal or shared resource, execution identity, target, and unauthorized or unrequested action or disclosure.
2. For confused-deputy authority claims, prove the tool lacks requester-and-resource authorization and that the attacker cannot perform the same action normally. For action-binding claims, instead prove attacker-controlled content caused an action under the affected principal's authority that the principal did not intentionally request or approve. Valid generic authorization does not establish that intent.
3. For memory or retrieval claims, cite both the attacker-controlled write and the later cross-principal read or privileged decision. A shared record without a reachable consumer is not enough.
4. For action binding, establish the intentional request or normalized approved object, if any, and compare it with the object the handler uses. Confirm a locally observable unrequested action, mutation, duplicate, or authority change without extending the test into harmful execution. For schema disagreement, compare the normalized validated object with the handler's object.
5. For MCP identity claims, verify the authenticated connection, request correlation, tool namespace, and effective credential. Mark `needs_validation` if external server identity or deployment routing is required.
6. Return `confirmed` findings only with a complete source trace and meaningful result. Return `needs_validation` for a specific unresolved boundary fact and state the bounded local or owner-observed check needed to resolve it.

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

- Scratch, the only place you or target code may write: `./agents/v20-p3/scratch/`. Never write `./agents/v20-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v20-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v20-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs:storage/backends/database/links.py:publish_links:target-resolution-ignores-author-rights` unless you identify a genuinely different root cause.

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
