# Final record verifier brief for `f04-p5`

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
 "fingerprint": "vfs-core.verify.extend_context:per-hit-context-duplication",
 "title": "Grep lines mode copies a separate context window for every hit line, so output grows as hit lines × body size",
 "description": "In grep's lines output mode, before_context and after_context are accepted up to 2^31-1. The Rust matcher builds one context span for each hit line and never merges spans that overlap. python.rs then copies each span into its own PyBytes, and grep.py wraps each one in a Match. Nothing limits the size of the output. If the pattern matches every line, or if invert_match is used with a pattern that matches nothing, each of L lines carries about the whole body as its context. The output is then about L × body bytes, which is quadratic in the body. Any caller who can read one multi-line entry can trigger this with a single grep call. allow_scan is not needed, because invert_match takes the scan tier on its own. The memory is allocated in the host process, which many agents share. Local run on InMemoryStorage: a 40,000-byte body of 4,000 lines returned 159,996,000 characters of match content, and peak RSS rose to about 634 MB. Each doubling of L multiplied the output by 4.",
 "root_cause": "extend_context (crates/vfs-core/src/verify.rs:242) builds a full span for each hit line on its own. Matcher::hit_lines (verify.rs:118) pushes one span per hit and only stops at max_count, which defaults to None. Overlapping windows are never merged. python.rs:154 copies each span into a new PyBytes, and grep.py:358 wraps each in a Match. Nothing bounds the output: CONTENT_BYTE_BUDGET (grep.py:126) only limits input bodies held at once, the parameter gate allows context up to INT_CEILING, and the wall-time deadline is checked only before each body starts (verify.rs:197), never inside one.",
 "intended_behavior": "Grep's lines-mode output should stay bounded by about the size of the matched body, whatever the context arguments are. That is how the ripgrep baseline behaves: it merges overlapping or adjacent context windows and emits each line at most once. The repo's own early spec expected the same ('merged context windows render correctly', context/specifications/archive/001-unify-vfs-result-and-optimize-queries/spec.md:169). Failing that, a declared output budget should truncate the result with a classified warning, as grep's other budgets do.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/params.py",
   "line": 270,
   "scope": "grep before_context / after_context ParamSpec",
   "description": "The caller's before_context and after_context are accepted as ints from 0 to INT_CEILING (2^31-1). Lines 278-286 do the same for after_context. max_count (line 288) is optional and defaults to None."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 348,
   "scope": "grep_rows lines-mode verify",
   "description": "Passes before_context, after_context and cap=max_count (None by default) to VerifyOffload.hit_lines for each content batch. No output budget is applied."
  },
  {
   "kind": "propagation",
   "file": "crates/vfs-core/src/verify.rs",
   "line": 118,
   "scope": "Matcher::hit_lines",
   "description": "Pushes one extend_context span for every hit line. It stops only at cap, so with no cap every line gets its own span."
  },
  {
   "kind": "propagation",
   "file": "crates/vfs-core/src/verify.rs",
   "line": 242,
   "scope": "extend_context",
   "description": "Walks back up to `before` lines and forward up to `after` lines from each hit, clamped only to the body. With huge context each span is the whole body. Spans are not merged with the previous hit's span."
  },
  {
   "kind": "propagation",
   "file": "crates/vfs-core/src/python.rs",
   "line": 154,
   "scope": "PyContentMatcher::hit_lines",
   "description": "Copies the bytes of every span into a new PyBytes while holding the GIL. Total allocation is the sum of all span lengths, about hits × body bytes."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 358,
   "scope": "grep_rows Match assembly",
   "description": "Wraps each span's content in a pydantic Match on the event loop. The quadratic payload is kept in Observation.matches and returned to the caller."
  }
 ],
 "evidence": [
  {
   "file": "crates/vfs-core/src/verify.rs",
   "line": 118,
   "description": "hits.push(extend_context(...)) runs once per hit line, and the cap is the only stop condition."
  },
  {
   "file": "crates/vfs-core/src/verify.rs",
   "line": 242,
   "description": "extend_context computes a span per hit on its own. There is no merge with earlier spans."
  },
  {
   "file": "crates/vfs-core/src/verify.rs",
   "line": 197,
   "description": "hits_batch checks the deadline only before it starts each body. Inside one body, matching and span building are not bounded."
  },
  {
   "file": "crates/vfs-core/src/python.rs",
   "line": 154,
   "description": "Each span is copied into a separate PyBytes."
  },
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 126,
   "description": "CONTENT_BYTE_BUDGET (32 MiB) limits how many input body bytes are resident at once. It does not limit output size. The other budgets (lines 119-121) count candidates, posting bytes and wall time."
  },
  {
   "file": "src/vfs/params.py",
   "line": 274,
   "description": "maximum=INT_CEILING is the only bound on before_context. after_context gets the same bound at line 283."
  },
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 199,
   "description": "The unindexable-pattern refusal is skipped when invert_match is set. So a reader needs no allow_scan to make every line of a body a hit."
  },
  {
   "file": "agents/v04-p3/artifacts/evidence/grep_context_growth.txt",
   "line": 1,
   "description": "Sandboxed local run through VirtualFileSystem(InMemoryStorage()) with context 2^31-1. L=250/500/1000/2000/4000 ten-byte lines gave 624,750 / 2,499,500 / 9,999,000 / 39,998,000 / 159,996,000 match-content characters, about 4x per doubling. Peak RSS went from about 126 MB to about 634 MB. With context 0 the output stays at about 0.9 × body. The invert_match variant without allow_scan gave the same 159,996,000 characters at L=4000."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The caller has read visibility on at least one multi-line entry, or write rights to create one. No elevated or system authority is needed."
  },
  {
   "kind": "data_state",
   "description": "The visible body has many lines that count as hits: they match the pattern, or with invert_match they do not match it. The output is about (hit lines) × (body bytes)."
  },
  {
   "kind": "system_configuration",
   "description": "The host does not set max_count and does not cap before_context or after_context below the library's INT_CEILING. These are the library defaults."
  }
 ],
 "execution": {
  "attacker_perspective": "An agent with ordinary read access to the shared vfs host makes one grep call on a readable multi-line file. It sets very large context values and either uses a pattern that matches every line or uses invert_match with a pattern that matches nothing.",
  "payloads": [
   "fs.grep(\"abc\", before_context=2**31-1, after_context=2**31-1)",
   "fs.grep(\"zzqq_never\", invert_match=True, before_context=2**31-1, after_context=2**31-1)"
  ],
  "instructions": [
   "Build VirtualFileSystem(storage=InMemoryStorage()) and write /f.txt containing L short lines, for example 'abc000000\\n' repeated with increasing numbers (10 bytes per line).",
   "Call fs.grep with before_context=after_context=2**31-1 and the default output_mode='lines' and max_count.",
   "Add up len(m.content) over every Match in r.observations and record peak RSS.",
   "Repeat for L = 250, 500, 1000, 2000, 4000, and once with context=0 as a control.",
   "Run the invert_match payload at L=2000 and L=4000 to show that allow_scan is not needed."
  ],
  "observed_result": "Run under the sandbox launcher (no network, empty environment, CPU/RSS/wall caps). With context 0 the output was about 0.9 × body at every size. With context 2^31-1 the output was 249.9, 499.9, 999.9, 1999.9 and 3999.9 times the body for L=250 to 4000. At L=4000 a 40 KB body returned 159,996,000 characters in 4,000 Match objects, and peak RSS reached about 634 MB, up from about 126 MB. The invert_match variant without allow_scan gave the same 159,996,000 characters and about 605 MB RSS at L=4000. No truncation warning or error was returned. Output grew about 4x per doubling of L, which is quadratic. Larger bodies were not run; extrapolated, a body of a few hundred KB would exceed host memory."
 },
 "remediation": {
  "strategy": "Bound lines-mode output by the body, not by hits × body. The preferred fix follows ripgrep: when a hit's context window overlaps or touches the previous window, extend the previous window instead of starting a new one, so each body line is emitted at most once per entry. The Match shape may need to carry several match lines per window, or keep per-hit match line numbers that point into a shared window. As defense in depth, add a declared per-call output-byte budget in hits_batch and the Python assembly that truncates with a classified 'truncated' warning, and check the deadline inside the per-body hit loop, not only between bodies.",
  "code_changes": [
   {
    "file_name": "crates/vfs-core/src/verify.rs",
    "fixed_code": "pub fn hit_lines(&self, hay: &[u8], before: u32, after: u32, cap: Option<u64>, invert: bool) -> Vec<Hit> {\n    let mut hits: Vec<Hit> = Vec::new();\n    let mut emitted = 0u64;\n    self.each_hit_line(hay, invert, |ls, le, line_no| {\n        let next = extend_context(hay, ls, le, line_no, before, after);\n        match hits.last_mut() {\n            // Overlapping or adjacent windows merge, so each body byte is emitted at most once.\n            Some(prev) if next.span.0 <= prev.span.1 + 1 => {\n                prev.span.1 = prev.span.1.max(next.span.1);\n                prev.end_line = prev.end_line.max(next.end_line);\n            }\n            _ => hits.push(next),\n        }\n        emitted += 1;\n        cap.is_none_or(|cap| emitted < cap)\n    });\n    hits\n}"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "It needs only ordinary read access to any multi-line entry and one grep call with two integer arguments. invert_match bypasses the allow_scan refusal. The context values look like normal grep options, and no host-side cap exists in source. The caller must already be a principal the host lets call grep."
  },
  "impact": {
   "score": "medium",
   "reason": "A quadratic memory and CPU amplification is allocated in the host process shared by every agent. It was observed reaching 634 MB from a 40 KB body, and it extrapolates to exhausting host memory with modest bodies, which can OOM-kill the process for all tenants. The pydantic Match assembly also blocks the shared event loop. The effect is temporary availability loss with no persistence or data exposure, and a restart recovers it."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The source path is direct and was checked line by line. The quadratic growth was reproduced locally through the public VirtualFileSystem API, exactly 4x per doubling, with a context=0 control and an invert_match variant. It ran against the prebuilt _native extension, which the brief assumes matches source."
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

- Scratch, the only place you or target code may write: `./agents/f04-p5/scratch/`. Never write `./agents/f04-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f04-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f04-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs-core.verify.extend_context:per-hit-context-duplication"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
