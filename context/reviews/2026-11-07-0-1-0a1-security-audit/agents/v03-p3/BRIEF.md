# Candidate verifier brief for `v03-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w2d-reindex-edit. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs-core.links.line_context:per-reference-whole-line-fold",
  "title": "markdown_refs folds the whole enclosing line for every reference, so one agent-written markdown line makes reindex hold the mount's writer transaction for quadratic time",
  "description": "During reindex, the chunk pass parses every dirty markdown body with the Rust markdown_refs. For each link destination or path-shaped code span it calls line_context. That function scans back to the previous newline and forward to the next one, then folds the whole line, before it keeps 256 characters. So N references on one line of length ~N cost O(N^2). The pass is offloaded to a thread, so the event loop keeps running. But it runs inside chunk_dirty's writer transaction (BEGIN IMMEDIATE on SQLite), with no time or size budget. Every other principal's write on that mount waits for the whole parse. An agent that writes one 160 KB single-line markdown file makes the next operator reindex take 6.8 s instead of about 0.5 s, and other writers on the mount block for 6.5 s. Each doubling of the line costs about 3.5-4x. The stall repeats on every reindex after the agent rewrites the file.",
  "root_cause": "line_context (crates/vfs-core/src/links.rs:71-75) recomputes the line bounds and folds the entire line per reference, rather than once per line or within a window bounded by MAX_CONTEXT_CHARS. extract_link_work runs inside _assess_and_split, awaited while chunk_dirty's writer transaction is open (indexing.py:330, backend.py:1375), with no deadline or per-body work cap.",
  "intended_behavior": "The reference extraction should be linear in body size, with a per-reference context cost bounded by MAX_CONTEXT_CHARS. Reindex CPU over caller-written content should be bounded or should run without the mount's writer lock held, so one document cannot block other principals' writes for superlinear time.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 958,
    "scope": "AsyncVirtualFileSystem.write",
    "description": "A lower-trust principal writes a .md body of N links on one line; there is no body-size cap on SQLite or InMemory."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1375,
    "scope": "DatabaseStorage._gram_phases",
    "description": "The operator's reindex runs chunk_dirty inside _execute_write, a BEGIN IMMEDIATE writer transaction on SQLite and the single serialized session on InMemoryStorage."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/indexing.py",
    "line": 330,
    "scope": "chunk_dirty",
    "description": "call_offloaded(_assess_and_split) is awaited with the writer transaction open and no deadline."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/indexing.py",
    "line": 583,
    "scope": "_assess_and_split",
    "description": "extract_link_work(rows, ...) runs over every dirty markdown body."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/links.py",
    "line": 76,
    "scope": "extract_link_work",
    "description": "extract_links -> native.markdown_refs over the bodies (models/links.py:78, python.rs:207)."
   },
   {
    "kind": "propagation",
    "file": "crates/vfs-core/src/links.rs",
    "line": 54,
    "scope": "markdown_refs",
    "description": "line_context is called once per reference."
   },
   {
    "kind": "sink",
    "file": "crates/vfs-core/src/links.rs",
    "line": 72,
    "scope": "line_context",
    "description": "rposition/position over the whole line plus fold_line over the whole line, per reference: O(N x line length)."
   }
  ],
  "evidence": [
   {
    "file": "crates/vfs-core/src/links.rs",
    "line": 71,
    "description": "line_context scans to both line ends and folds the full line before truncating to MAX_CONTEXT_CHARS."
   },
   {
    "file": "crates/vfs-core/src/links.rs",
    "line": 78,
    "description": "fold_line builds the folded copy of the entire line and only then takes 256 chars."
   },
   {
    "file": "src/vfs/storage/backends/database/indexing.py",
    "line": 330,
    "description": "The offloaded split is awaited inside the writer transaction, with no budget."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1666,
    "description": "_execute_write opens the writer transaction with BEGIN IMMEDIATE on SQLite, holding the write lock from the first read."
   },
   {
    "file": "src/vfs/storage/backends/database/dialects.py",
    "line": 398,
    "description": "Other SQLite writers wait busy_timeout 5000 ms per attempt; with_retry (engine.py:298) gives 4 attempts before a conflict."
   },
   {
    "file": "src/vfs/storage/backends/database/engine.py",
    "line": 722,
    "description": "InMemoryStorage serializes all sessions behind one asyncio.Lock held for the whole transaction."
   }
  ],
  "conditions": [
   {
    "kind": "authorization_role",
    "description": "The attacker needs write rights to any one .md path on the mount, for example its own file."
   },
   {
    "kind": "user_interaction",
    "description": "The trusted operator or host runs reindex on the mount (the routine maintenance verb that fills indexes and vectors); agents cannot call it themselves."
   },
   {
    "kind": "system_configuration",
    "description": "Other principals write to the same mount while reindex runs. The writer-lock effect is direct on SQLite and InMemoryStorage; on server engines the transaction holds row locks from the stale-flag UPDATE only, so the shared effect there was not measured."
   }
  ],
  "execution": {
   "attacker_perspective": "A named agent principal (alice) writes one markdown file to a shared mount; the operator later runs storage.reindex(); another principal (bob) writes his own file during the reindex.",
   "payloads": [
    "write /doc.md content='[a](b.md) ' * 16000 (160 KB, one line)",
    "control: write /doc.md content='[a](b.md)\\n' * 16000 (same bytes and refs on 16000 lines)",
    "native split: markdown_refs([b'`a.md` ' * N]) versus markdown_refs([b'`a b` ' * N])"
   ],
   "instructions": [
    "Run agents/w2d-reindex-edit/scratch/reindex_scale.py and md_rootcause.py under tools/sandbox-run.py (no network, empty env, CPU 60 s, wall 120 s, RSS 2 GiB) with .venv/bin/python -I.",
    "For N=4000, 8000 and 16000 on a fresh InMemoryStorage, time reindex(). Record bob's concurrent write latency, a rival reindex() outcome and the longest event-loop gap. Repeat N=16000 on a file-backed SQLite DatabaseStorage."
   ],
   "observed_result": "InMemoryStorage one-line: reindex 559 / 1864 / 6819 ms at N=4000/8000/16000 (x3.34, x3.66). bob's write waited 218 / 1509 / 6478 ms; the event-loop gap stayed at most 85 ms; the rival reindex got vfs.conflict. Control on N lines: 165 ms (N=4000), 533 ms (N=16000), bob's write 7-188 ms. File SQLite N=16000: reindex 6722 ms, and bob's write on a separate pooled connection waited 6463 ms. Native split: path-shaped spans 1146 -> 4458 ms (x3.89) versus non-path spans 41.6 -> 84.4 ms (x2.03)."
  },
  "remediation": {
   "strategy": "Make the context cost per reference O(MAX_CONTEXT_CHARS). One way: compute the newline offsets once per body with memchr, and find each reference's line by binary search. Because references come in document order, cache the folded context per line start, so each line is folded once and early-exits after MAX_CONTEXT_CHARS output chars. Separately, consider a per-body reference cap or time budget for the extraction, and doing the offloaded CPU before the writer transaction opens, since the chunked flip is already version-guarded. Regression test: count fold_line invocations or bytes scanned, never wall time, for one line with N and 2N references, and assert linear growth.",
   "code_changes": [
    {
     "file_name": "crates/vfs-core/src/links.rs",
     "fixed_code": "pub fn markdown_refs(parser: &mut MarkdownParser, body: &[u8]) -> Vec<MarkdownRef> {\n    let newlines: Vec<usize> = memchr::memchr_iter(b'\\n', body).collect();\n    let mut cached: Option<(usize, String)> = None;\n    // ... in the walk, replacing line_context(body, node.start_byte()):\n    let at = node.start_byte();\n    let k = newlines.partition_point(|&i| i < at);\n    let start = if k == 0 { 0 } else { newlines[k - 1] + 1 };\n    let end = newlines.get(k).copied().unwrap_or(body.len());\n    let context = match &cached {\n        Some((s, c)) if *s == start => c.clone(),\n        _ => { let c = fold_line(&String::from_utf8_lossy(&body[start..end])); cached = Some((start, c.clone())); c }\n    };\n    refs.push(MarkdownRef { dest, context });\n}\n// and fold_line stops pushing once MAX_CONTEXT_CHARS chars are emitted."
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "Writing one markdown file is ordinary agent capability, and reindex is routine operator maintenance. The attacker cannot start reindex, but every reindex after each rewrite of the file pays the cost again."
   },
   "impact": {
    "score": "medium",
    "reason": "All principals' writes on the mount block for a time quadratic in one file's line length: 6.5 s at 160 KB, and about 100 s extrapolated at 640 KB at the measured 3.5-4x per doubling. On file SQLite a writer blocked past about 4 x 5 s busy_timeout would fail with a conflict (inferred from source, not run). The event loop is not stalled, and the stall ends when the pass commits."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "high",
   "reason": "The root cause is isolated by the native split (non-path spans with the same parse are linear). The end-to-end quadratic growth and the blocked concurrent writer were observed on InMemoryStorage and on file SQLite."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "crates%2Fvfs-core%2Fsrc%2Flinks.rs%23markdown_refs%20and%20line_context%20in%20the%20reindex%20chunk%20pass::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Findexing.py%23_assess_and_split%2C%20offloaded%20with%20no%20budget%20under%20the%20single-runner%20lease::crates%2Fvfs-core::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "crates/vfs-core/src/links.rs",
   "crates/vfs-core/src/python.rs",
   "src/vfs/models/links.py",
   "src/vfs/storage/backends/database/links.py"
  ],
  "invariant": "Per-reference context extraction in markdown_refs costs O(MAX_CONTEXT_CHARS), not O(line length), so the parse is linear in body size",
  "method": "source",
  "result": "links.rs:54 calls line_context for every link_destination and path-shaped code_span; line_context (71-75) scans back to the previous newline, forward to the next newline and folds the whole line before taking 256 chars, so N refs on one line of length ~N cost O(N^2). python.rs:207-210 detaches the GIL and the batch is rayon-parallel per body, so one body is single-threaded. No body-size, ref-count or time budget exists in extract_links (models/links.py:72-78) or extract_link_work (database/links.py:62-77).",
  "artifact": null
 },
 {
  "coverage_id": "crates%2Fvfs-core%2Fsrc%2Flinks.rs%23markdown_refs%20and%20line_context%20in%20the%20reindex%20chunk%20pass::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Findexing.py%23_assess_and_split%2C%20offloaded%20with%20no%20budget%20under%20the%20single-runner%20lease::crates%2Fvfs-core::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "crates/vfs-core/src/links.rs"
  ],
  "invariant": "The quadratic term is line_context, not the tree-sitter inline parse",
  "method": "local",
  "result": "Direct native.markdown_refs on one line: path-shaped code spans N=8000 -> 1146 ms, N=16000 -> 4458 ms (3.89x per doubling); identical code-span parse with non-path spans (no line_context call) 41.6 -> 84.4 ms (2.03x, linear).",
  "artifact": "agents/w2d-reindex-edit/artifacts/evidence/md_rootcause.txt"
 },
 {
  "coverage_id": "crates%2Fvfs-core%2Fsrc%2Flinks.rs%23markdown_refs%20and%20line_context%20in%20the%20reindex%20chunk%20pass::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Findexing.py%23_assess_and_split%2C%20offloaded%20with%20no%20budget%20under%20the%20single-runner%20lease::crates%2Fvfs-core::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/indexing.py",
   "src/vfs/storage/backends/database/offload.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/engine.py",
   "src/vfs/storage/backends/database/dialects.py"
  ],
  "invariant": "Reindex CPU on agent-written content does not hold the mount's writer transaction (and so every other writer) for superlinear time",
  "method": "source",
  "result": "backend.py:1375-1386 runs chunk_dirty inside _execute_write (backend.py:1666-1673: SQLite BEGIN IMMEDIATE, the write lock is held from the first read). indexing.py:330 awaits call_offloaded(_assess_and_split) while that transaction is open; _assess_and_split (540-583) ends with extract_link_work over every dirty markdown body. call_offloaded carries no deadline for this hop (offload.py). On InMemoryStorage the StaticPool session factory is _SerializedSessions (engine.py:722), an asyncio.Lock over the whole session context; on file SQLite other writers wait PRAGMA busy_timeout=5000 (dialects.py:398) per attempt under with_retry (4 attempts, engine.py:298-327). The loop itself is not stalled: the parse is offloaded and GIL-detached. Reindex is storage-direct (operator), not a router verb; the single-runner lease (backend.py:1118-1143, TTL 5 min indexing.py:124) refuses a rival reindex with a retryable conflict, as designed.",
  "artifact": null
 },
 {
  "coverage_id": "crates%2Fvfs-core%2Fsrc%2Flinks.rs%23markdown_refs%20and%20line_context%20in%20the%20reindex%20chunk%20pass::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Findexing.py%23_assess_and_split%2C%20offloaded%20with%20no%20budget%20under%20the%20single-runner%20lease::crates%2Fvfs-core::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/indexing.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/engine.py"
  ],
  "invariant": "End-to-end write + reindex time is linear in the markdown body, and concurrent writers by other principals are not held for it",
  "method": "local",
  "result": "InMemoryStorage, alice writes /doc.md with N links on one line, operator reindex(): N=4000 (40 KB) 559 ms, N=8000 1864 ms (3.34x), N=16000 (160 KB) 6819 ms (3.66x). bob's concurrent write of his own file waited 218 / 1509 / 6478 ms; event-loop max gap stayed 22-85 ms (offloaded); a rival reindex got vfs.conflict (lease). Control with the same refs on N lines: 165 ms at N=4000, 533 ms at N=16000, bob write 7-188 ms. File-backed SQLite DatabaseStorage (pooled connections), N=16000: reindex 6722 ms, bob's write on another connection waited 6463 ms (past one 5 s busy_timeout).",
  "artifact": "agents/w2d-reindex-edit/artifacts/evidence/reindex_scale.txt"
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

- Scratch, the only place you or target code may write: `./agents/v03-p3/scratch/`. Never write `./agents/v03-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v03-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v03-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs-core.links.line_context:per-reference-whole-line-fold` unless you identify a genuinely different root cause.

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
