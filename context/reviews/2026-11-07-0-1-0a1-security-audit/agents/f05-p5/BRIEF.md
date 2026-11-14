# Final record verifier brief for `f05-p5`

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
 "fingerprint": "vfs.base._grep_rows_in_hand:inline-unbudgeted-verify",
 "title": "Chained grep over observations runs regex verification on the event loop with no wall, candidate or byte budget, amplified by duplicate rows",
 "description": "grep(observations=...) goes to _grep_rows_in_hand. That function reads the content of every listed row that has no content attached, in one self.read call. It then calls match_texts with budget=None, synchronously on the event-loop thread. The storage-tier grep does the same verification work under several controls: a 25,000-candidate budget, 32 MiB content chunks, a 10 s wall deadline, and an offload to an executor (its own comment says 'Verify leaves the loop'). The chained path applies none of these. Rows are not deduplicated, so a caller can list one stored file it may read N times; the file is fetched once and verified N times. Loop occupancy therefore grows linearly with N x body bytes x the per-byte cost of the pattern, and the pattern length has no cap. Every other coroutine on that loop is stalled until the native call returns. That includes every thread sharing one sync VirtualFileSystem facade, which serves all its callers from one loop thread. This was reproduced locally: one stored file of about 0.98 MB, the pattern (\\w|\\s){60}Q, and 10, 20 and 40 duplicate Observations blocked the loop for 0.65 s, 1.22 s and 2.70 s. The storage-tier scan of the same file and pattern never blocked the loop for more than 13 ms.",
 "root_cause": "_grep_rows_in_hand (src/vfs/base.py:1919) calls pattern_matching.grep.match_texts, which passes budget=None to ContentMatcher.count_lines/hit_lines (src/vfs/pattern_matching/grep.py:252,259). It makes this call inline on the coroutine's thread. It does not use the storage tier's VerifyOffload, byte_chunked(CONTENT_BYTE_BUDGET), CANDIDATE_BUDGET or WALL_TIME_BUDGET controls. The observations list has no length cap and is not deduplicated, and the pattern has no length cap.",
 "intended_behavior": "Content verification should carry the same bounds whether its rows come from storage or from observations=. That means running off the event loop on the backend's executor, under a wall-time deadline that truncates with a warning, with bodies processed in byte-budgeted batches, and with each distinct body verified at most once per call. The storage tier already declares and enforces exactly this contract.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 1430,
   "scope": "AsyncVirtualFileSystem.grep",
   "description": "Once the parameter gate passes and observations is not None, grep dispatches to _grep_rows_in_hand (return at line 1433). No row-count cap and no deduplication apply, and the pattern has no length cap."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 1911,
   "scope": "AsyncVirtualFileSystem._grep_rows_in_hand",
   "description": "Every candidate row without content is read in a single self.read(observations=absent) call, with no candidate or byte budget. A row that already carries content needs no read at all."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/base.py",
   "line": 1919,
   "scope": "AsyncVirtualFileSystem._grep_rows_in_hand",
   "description": "match_texts runs over every texted row, duplicates included, synchronously on the event-loop thread."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/pattern_matching/grep.py",
   "line": 252,
   "scope": "match_texts",
   "description": "verifier.count_lines (or hit_lines at line 259) is called with budget=None, so no deadline exists."
  },
  {
   "kind": "sink",
   "file": "crates/vfs-core/src/verify.rs",
   "line": 195,
   "scope": "hits_batch / count_batch",
   "description": "Every body is matched to completion across rayon threads. The binding releases the GIL (python.rs py.detach), but the calling loop thread waits for the whole batch."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 120,
   "description": "The storage tier declares CANDIDATE_BUDGET 25,000, POSTING_BYTE_BUDGET, WALL_TIME_BUDGET 10.0 s, and (line 126) CONTENT_BYTE_BUDGET 32 MiB."
  },
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 325,
   "description": "Declared intent, 'Verify leaves the loop'. Line 328 builds VerifyOffload(verifier, executor), and lines 329-354 verify in byte_chunked batches against the deadline."
  },
  {
   "file": "src/vfs/pattern_matching/grep.py",
   "line": 252,
   "description": "match_texts passes budget=None to the engine (also line 259)."
  },
  {
   "file": "crates/vfs-core/src/python.rs",
   "line": 143,
   "description": "A deadline is built only when a budget is given. Even then, verify.rs checks it only before each body starts."
  },
  {
   "file": "src/vfs/base.py",
   "line": 1811,
   "description": "_observation_rows only type-checks the batch. It applies no length cap and no deduplication."
  },
  {
   "file": "src/vfs/sync.py",
   "line": 3,
   "description": "VirtualFileSystem owns one asyncio loop on one daemon thread (lines 647-648). Every thread that calls one facade shares that loop, so a stall on it is shared within the library itself."
  },
  {
   "file": "agents/v05-p3/artifacts/evidence/growth-output.txt",
   "line": 17,
   "description": "Local run: one 975,000-byte stored file, pattern (\\w|\\s){60}Q, files mode. The loop was blocked 0.654 s at 10 duplicate rows, 1.222 s at 20 and 2.703 s at 40. The storage scan tier on the same file had a 0.013 s maximum loop gap (line 23)."
  },
  {
   "file": "agents/v05-p3/artifacts/evidence/growth.py",
   "line": 1,
   "description": "The script that produced growth-output.txt. It runs a 1 ms asyncio ticker beside fs.grep(observations=[Observation(path=/data/big.txt)] * N) and records the largest loop gap."
  },
  {
   "file": "agents/v05-p3/artifacts/evidence/patterns-output.txt",
   "line": 1,
   "description": "Pattern calibration. Literal-prefiltered patterns finished in milliseconds. (\\w|\\s){60}Q cost about 0.43 s per MB: it blocked the loop on the chained path (gap 0.418-0.465 s) but not on the storage tier (gap 0.012 s)."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The caller must hold read on at least one stored file with content. Alternatively it can attach content to the Observations itself, in which case the bytes are its own. Only an ordinary verb argument (observations=) is needed."
  },
  {
   "kind": "system_configuration",
   "description": "The host serves several agents or principals from one AsyncVirtualFileSystem event loop, or from one sync VirtualFileSystem facade (one loop thread by construction), and passes agent-supplied observations and patterns through without a size limit."
  },
  {
   "kind": "data_state",
   "description": "The stall scales with the body bytes in the listed rows and with the pattern's per-byte cost. Patterns with a literal prefilter finish quickly; alternation-under-repetition patterns such as (\\w|\\s){60}Q are slow."
  }
 ],
 "execution": {
  "attacker_perspective": "An agent with read access to one roughly 1 MB file, calling grep through a host that shares one vfs event loop among agents.",
  "payloads": [
   "fs.grep(r\"(\\w|\\s){60}Q\", observations=[Observation(path=Path(\"/data/big.txt\"), kind=\"file\")] * 40, output_mode=\"files\")"
  ],
  "instructions": [
   "Build AsyncVirtualFileSystem(storage=InMemoryStorage()) and write about 0.98 MB of plain text lines to /data/big.txt.",
   "Start a coroutine that sleeps 1 ms in a loop and records the largest gap between wakeups.",
   "Await fs.grep with the payload for N = 10, 20 and 40 duplicate rows, recording the largest ticker gap each time.",
   "For comparison, await fs.grep with the same pattern and allow_scan=True, output_mode='files'."
  ],
  "observed_result": "The chained grep blocked the event loop for 0.654 s, 1.222 s and 2.703 s at N = 10, 20 and 40. That is linear in N, while the stored file was fetched once. The storage-tier scan of the same file and pattern took 0.428 s, but the loop was never blocked for more than 0.013 s, because that tier offloads the work. All calls returned success with no errors and no truncation warning."
 },
 "remediation": {
  "strategy": "Route chained verification through the same controls as the storage tier. First, verify each distinct (path, body) pair once and fan the result out to duplicate rows. Second, run the matcher off the loop through VerifyOffload on an executor, or through asyncio.to_thread when no backend executor is available. Third, pass a wall-time deadline derived from WALL_TIME_BUDGET and truncate with a warning when it trips. Fourth, process bodies in byte_chunked(CONTENT_BYTE_BUDGET) batches, checking the deadline between batches. A host-side cap on observations length and pattern length is additional defense in depth.",
  "code_changes": [
   {
    "file_name": "src/vfs/base.py",
    "fixed_code": "# in _grep_rows_in_hand, replacing the inline match_texts call\ndeadline = monotonic() + WALL_TIME_BUDGET\nunique: dict[tuple[str, str], int] = {}\nbodies: list[tuple[Path, str]] = []\nfor row, text in texted:\n    key = (str(row.path), text)\n    if key not in unique:\n        unique[key] = len(bodies)\n        bodies.append((row.path, text))\nhits_unique, completed = await match_texts_offloaded(\n    bodies, verifier, invert=invert_match, before=before_context, after=after_context,\n    mode=output_mode, cap=max_count, deadline=deadline,\n)  # executor-run, byte-chunked, budget=deadline - monotonic() per batch\nhits = [hits_unique[unique[(str(row.path), text)]] for row, text in texted]\n# append a 'wall-time budget' truncation warning when not completed"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "It needs only an ordinary grep argument and read access to one file, or caller-held content. The pattern and row count are uncapped and duplicates are not collapsed. Whether many principals share one loop depends on how the host deploys vfs."
  },
  "impact": {
   "score": "medium",
   "reason": "This is a temporary availability loss. Every coroutine and every sync-facade caller sharing the loop stalls for a time proportional to N x body size x pattern cost, with no deadline; about 2.7 s was observed at N=40 on 1 MB, and it grows linearly. Nothing persists and no data is exposed, and the loop recovers when the call returns. The synchronous native call cannot be cancelled."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The full trace was checked in source. The storage tier's declared off-loop contract confirms the chained path diverges from intent. The linear loop stall was reproduced locally with a sandboxed, bounded run against InMemoryStorage. The one fact this record leaves to the deployment is how many principals the host puts on one loop."
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

- Scratch, the only place you or target code may write: `./agents/f05-p5/scratch/`. Never write `./agents/f05-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f05-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f05-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.base._grep_rows_in_hand:inline-unbudgeted-verify"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
