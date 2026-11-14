# Final record verifier brief for `f03-p5`

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
 "fingerprint": "vfs-core.links.line_context:per-reference-whole-line-fold",
 "title": "markdown_refs folds the whole enclosing line once per reference, so one agent-written single-line markdown body makes reindex hold the mount's writer transaction for quadratic time",
 "description": "During reindex, the chunk pass sends every dirty markdown body to the Rust markdown_refs. That function calls line_context once for each link destination or path-shaped code span. line_context scans back to the previous newline and forward to the next one, then folds the whole line, and only after that keeps 256 characters. So a body with N references on one line of length about N costs O(N^2). The parse runs on the offload pool with the GIL released, so the event loop keeps running. But it is awaited inside chunk_dirty's writer transaction (BEGIN IMMEDIATE on SQLite; on InMemoryStorage, the single serialized session), and there is no time, size or reference budget on it. Every other principal's write to that mount waits until the parse finishes. In an independent run, one 160 KB single-line file written by alice made the operator's reindex take about 7.0 s, against about 0.6 s for the same bytes and references spread over 16,000 lines. bob's unrelated write waited 6.7 s on InMemoryStorage and 6.9 s on file-backed SQLite. Each doubling of the line costs about 3.7-3.9x. The stall comes back on every reindex after the file is rewritten.",
 "root_cause": "line_context (crates/vfs-core/src/links.rs:71-75) recomputes the line bounds with rposition/position over the whole line and calls fold_line over the whole line for every reference. fold_line (links.rs:78-93) builds the full folded copy before it truncates to MAX_CONTEXT_CHARS. The per-reference cost is therefore O(line length), not O(MAX_CONTEXT_CHARS). The quadratic work is reachable while a writer transaction is open: _gram_phases runs chunk_dirty inside _execute_write (backend.py:1375), and chunk_dirty awaits call_offloaded(_assess_and_split) (indexing.py:330). _assess_and_split ends with extract_link_work over every dirty markdown body (indexing.py:583). None of these places has a deadline or a per-body cap.",
 "intended_behavior": "Reference extraction should be linear in body size, and each reference's context should cost at most O(MAX_CONTEXT_CHARS). CPU that reindex spends on caller-written content should be bounded, or should run without the mount's writer lock held, so that one principal's document cannot block other principals' writes for superlinear time.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 958,
   "scope": "AsyncVirtualFileSystem.write",
   "description": "A lower-trust named principal (alice) writes a .md body that holds N link destinations on one line. No body-size or line-length cap exists on this path."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1375,
   "scope": "DatabaseStorage._gram_phases",
   "description": "The operator's reindex runs chunk_dirty inside _execute_write. That is a BEGIN IMMEDIATE writer transaction on SQLite, and the one serialized session on InMemoryStorage."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/indexing.py",
   "line": 330,
   "scope": "chunk_dirty",
   "description": "call_offloaded(_assess_and_split) is awaited while the writer transaction is open, with no deadline."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/indexing.py",
   "line": 583,
   "scope": "_assess_and_split",
   "description": "extract_link_work(rows, links_generation) runs over every dirty markdown body."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/links.py",
   "line": 76,
   "scope": "extract_link_work",
   "description": "extract_links passes the bodies to native.markdown_refs (models/links.py:78, python.rs:207), which parses each body on one thread, off the GIL."
  },
  {
   "kind": "propagation",
   "file": "crates/vfs-core/src/links.rs",
   "line": 54,
   "scope": "markdown_refs",
   "description": "line_context(body, node.start_byte()) is called once for every link_destination and path-shaped code_span."
  },
  {
   "kind": "sink",
   "file": "crates/vfs-core/src/links.rs",
   "line": 72,
   "scope": "line_context",
   "description": "rposition and position over the whole line, then fold_line over the whole line, for each reference: O(N x line length) CPU while the writer lock is held."
  }
 ],
 "evidence": [
  {
   "file": "crates/vfs-core/src/links.rs",
   "line": 71,
   "description": "line_context scans to both ends of the line and folds all of it before the result is cut to MAX_CONTEXT_CHARS."
  },
  {
   "file": "crates/vfs-core/src/links.rs",
   "line": 78,
   "description": "fold_line iterates every char of the line and builds the whole folded string. Only the final collect takes 256 chars, so there is no early exit."
  },
  {
   "file": "src/vfs/storage/backends/database/indexing.py",
   "line": 330,
   "description": "The offloaded split is awaited inside the writer transaction, with no budget."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1666,
   "description": "_execute_write marks the connection vfs_writer, so SQLite opens BEGIN IMMEDIATE and holds the write lock from the first read."
  },
  {
   "file": "src/vfs/storage/backends/database/dialects.py",
   "line": 398,
   "description": "Other SQLite writers wait up to busy_timeout 5000 ms per attempt. Under with_retry (engine.py:298) they get a bounded number of attempts and then a conflict."
  },
  {
   "file": "src/vfs/storage/backends/database/engine.py",
   "line": 722,
   "description": "On InMemoryStorage, _SerializedSessions holds one asyncio.Lock for each session's whole context, so every other operation waits for the chunk transaction."
  },
  {
   "file": "agents/v03-p3/artifacts/evidence/verify.txt",
   "line": 1,
   "description": "Verifier's independent sandboxed run. Native one-line parse took 460/1706/6625 ms at N=4000/8000/16000, against 49/103/216 ms for the same references on N lines. End to end, reindex took 593/1930/7044 ms, and bob's concurrent write waited 295/1645/6685 ms. The N-line control took 592 ms, with bob waiting 284 ms. File SQLite at N=16000: reindex 7090 ms, bob's write waited 6920 ms."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker needs write rights to any one .md path on the mount, for example its own file."
  },
  {
   "kind": "user_interaction",
   "description": "The trusted operator or host runs storage.reindex() on the mount. This is routine maintenance, but it is a storage-direct verb that agents cannot call."
  },
  {
   "kind": "system_configuration",
   "description": "The mount is SQLite-backed (file DatabaseStorage or InMemoryStorage), and other principals write to it while reindex runs. On server engines the chunk transaction holds only row locks, so the cross-writer effect there was not measured. The quadratic CPU, and the delay to the operator's reindex, apply on every engine."
  }
 ],
 "execution": {
  "attacker_perspective": "A named agent principal (alice) writes one markdown file to a shared mount. Later the operator runs storage.reindex(). Another principal (bob) writes his own unrelated file while the reindex runs.",
  "payloads": [
   "fs.write(path='/doc.md', content='[a](b.md) ' * 16000, authority=alice)  # 160 KB, one line",
   "control: fs.write(path='/doc.md', content='[a](b.md)\\n' * 16000, authority=alice)  # same bytes and refs, 16000 lines",
   "native: vfs.native.markdown_refs([('[a](b.md) ' * N).encode()]) versus markdown_refs([('[a](b.md)\\n' * N).encode()])"
  ],
  "instructions": [
   "Run agents/v03-p3/scratch/verify.py under tools/sandbox-run.py (no network, empty env, CPU 60 s, wall 120 s, RSS 2 GiB) with ./.venv/bin/python -I.",
   "Time native.markdown_refs at N=4000, 8000 and 16000 for the one-line body and for the N-line body.",
   "For each N, on a fresh InMemoryStorage behind AsyncVirtualFileSystem: alice writes /doc.md, the operator awaits storage.reindex(), and 250 ms in, bob writes /bob.txt. Record the reindex time and bob's write latency. Repeat N=16000 with the N-line control, and on a file-backed SQLite DatabaseStorage."
  ],
  "observed_result": "Native one-line: 459.6 / 1705.8 / 6624.5 ms (x3.71, x3.88 per doubling). N-line control: 49.3 / 103.3 / 215.8 ms (linear). In both cases every reference got a 256-char context. InMemoryStorage one-line: reindex 592.6 / 1930.3 / 7044.2 ms, and bob's write waited 295.0 / 1645.5 / 6684.9 ms (it succeeded). N-line control at N=16000: reindex 591.8 ms, bob waited 284.1 ms. File-backed SQLite one-line at N=16000: reindex 7089.9 ms, and bob's write on another pooled connection waited 6920.4 ms, longer than one 5 s busy_timeout, before it succeeded."
 },
 "remediation": {
  "strategy": "Make each reference's context cost O(MAX_CONTEXT_CHARS). Compute the newline offsets once per body with memchr and find each reference's line by binary search. References arrive in document order, so cache the folded context per line start and fold each line only once. Make fold_line stop as soon as it has emitted MAX_CONTEXT_CHARS chars. As defence in depth, consider a per-body reference cap or work budget. Also consider running the offloaded CPU before the writer transaction opens, since the chunk flip is already version-guarded. For a regression test, count bytes scanned or fold invocations for one line with N and with 2N references and assert linear growth. Do not assert on wall time.",
  "code_changes": [
   {
    "file_name": "crates/vfs-core/src/links.rs",
    "fixed_code": "pub fn markdown_refs(parser: &mut MarkdownParser, body: &[u8]) -> Vec<MarkdownRef> {\n    let newlines: Vec<usize> = memchr::memchr_iter(b'\\n', body).collect();\n    let mut cached: Option<(usize, String)> = None;\n    // ... in the walk, replacing line_context(body, node.start_byte()):\n    let at = node.start_byte();\n    let k = newlines.partition_point(|&i| i < at);\n    let start = if k == 0 { 0 } else { newlines[k - 1] + 1 };\n    let end = newlines.get(k).copied().unwrap_or(body.len());\n    let context = match &cached {\n        Some((s, c)) if *s == start => c.clone(),\n        _ => { let c = fold_line(&String::from_utf8_lossy(&body[start..end])); cached = Some((start, c.clone())); c }\n    };\n    refs.push(MarkdownRef { dest, context });\n}\n// fold_line: track the emitted char count and break once it reaches MAX_CONTEXT_CHARS."
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Writing one markdown file is ordinary agent capability, and reindex is routine operator maintenance. The attacker cannot start reindex itself, but every reindex after each rewrite of the file pays the cost again."
  },
  "impact": {
   "score": "medium",
   "reason": "On SQLite-backed mounts, every other principal's write blocks for a time that grows quadratically with one file's line length: about 6.7-6.9 s at 160 KB, measured. On InMemoryStorage, all other sessions wait as well. Larger lines extrapolate past busy_timeout times the retry attempts, after which a blocked writer would fail with a conflict. That is inferred from source, not run. The event loop is not stalled, and the stall ends when the pass commits."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The cited source lines were verified. The native split isolates line_context: the same references and the same inline parse grow linearly when spread over lines and quadratically on one line. The verifier independently reproduced the end-to-end blocking of a concurrent writer on InMemoryStorage and on file SQLite."
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

- Scratch, the only place you or target code may write: `./agents/f03-p5/scratch/`. Never write `./agents/f03-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f03-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f03-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs-core.links.line_context:per-reference-whole-line-fold"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
