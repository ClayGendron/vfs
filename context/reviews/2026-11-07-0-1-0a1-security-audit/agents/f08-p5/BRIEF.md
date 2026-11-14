# Final record verifier brief for `f08-p5`

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
 "fingerprint": "vfs.rendering.docx:table-gridspan-expansion",
 "title": "A docx table cell's gridSpan value expands into an unbounded cell list before any render limit applies",
 "description": "_Writer.table builds rows = [[cell.text for cell in row.cells] for row in table.rows] and only then hands the rows to Builder.table. In the installed python-docx 1.2.0, _Row.cells yields the same _Cell once for each grid column the cell spans (iter_tc_cells: for _ in range(tc.grid_span): yield cell). grid_span is read straight from the w:tcPr/w:gridSpan/@val integer and is never compared with the table's real grid width. The renderer then calls cell.text once for each yielded entry, and each call builds a new string. So one attribute in a document of about 36 KB decides how many tuple entries, cell.text calls and list strings get created. All of this work finishes before Builder sees the first row. The character budget, the ratio guard, the unit cap and the cooperative clock (RenderLimits.seconds, checked only at block boundaries and between table rows) therefore do not bound it. The bytes come from any principal allowed to write(data=...) to a DatabaseStorage mount; the write stores them as render_status='pending'. The expansion runs later, when the operator calls reindex(). It runs on the backend's in-process ThreadPoolExecutor, the pool that grep's verify stage also uses, and a running worker cannot be interrupted. Local run: input size held constant at 36,705 bytes, gridSpan raised from 1e3 to 1e6. cell.text calls grew exactly linearly (1,000 to 1,000,000). Peak RSS rose from 113.6 MiB to 473.0 MiB. Wall time was about 22 s against RenderLimits(seconds=1.0); this is informational only. Spans of 1e5 and above also return status 'empty' with no text, because the header line alone overflows the character budget. Correction to the hunter's wording: a render that completes lands a terminal state and is not retried. A row stays pending, and is retried on every reindex, only when the span is large enough that the render never finishes or the process dies. The schema allows values up to 2^31-1. That size was not executed: by extrapolation it is more than 16 GiB of tuple pointers alone, plus hours of CPU.",
 "root_cause": "DocxRenderer's table path builds the span-expanded row.cells tuple and one cell.text string per grid position, with no cap and no clamp to the table's declared grid width. RenderLimits are enforced only inside Builder, on text it emits. The materialization runs as one uninterruptible step on the offload thread, before any of those checks.",
 "intended_behavior": "A render's memory and CPU should stay bounded by RenderLimits and roughly proportional to the input bytes. Per the seam's own docstring, a malformed or hostile docx should end as a classified 'truncated' or 'failed' state within the time budget, not do work set by an attribute value.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 958,
   "scope": "AsyncVirtualFileSystem.write",
   "description": "A lower-trust caller with write rights stores arbitrary docx bytes through write(data=...)"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 1181,
   "scope": "bytes write staging",
   "description": "The bytes row is stored with render_status='pending' and is not rendered in the writer's call"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1288,
   "scope": "DatabaseStorage._render_step",
   "description": "The operator's reindex() renders every pending bytes row via render_rows on the in-process offload ThreadPoolExecutor (call_offloaded)"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 294,
   "scope": "render_rows",
   "description": "Each pending row goes to registry.render with the configured RenderLimits"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/registry.py",
   "line": 107,
   "scope": "RendererRegistry.render",
   "description": "Dispatches to DocxRenderer.render; only an Exception raised from inside the renderer becomes a state"
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/docx.py",
   "line": 63,
   "scope": "DocxRenderer.render",
   "description": "Each body table block goes to _Writer.table after a single boundary() clock check"
  },
  {
   "kind": "sink",
   "file": "src/vfs/rendering/docx.py",
   "line": 128,
   "scope": "_Writer.table",
   "description": "rows = [[cell.text for cell in row.cells] for row in table.rows] creates one tuple entry and one cell.text string per spanned grid column, with the count set by w:gridSpan/@val, before Builder.table checks any budget"
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/rendering/docx.py",
   "line": 128,
   "description": "The full row matrix is materialized before self._builder.table(rows) runs; there is no cap on len(row.cells) and no clamp to the table grid"
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 191,
   "description": "Builder.table checks out_of_time() and the character budget only while emitting rows that already exist"
  },
  {
   "file": "src/vfs/rendering/seam.py",
   "line": 67,
   "description": "RenderLimits caps characters, ratio, embedded objects, units and seconds; none of these bounds parsed structure size or work done before Builder"
  },
  {
   "file": "src/vfs/storage/backends/database/engine.py",
   "line": 237,
   "description": "The offload pool is an in-process ThreadPoolExecutor shared with grep's verify stage, so memory and CPU exhaustion affects the whole host process"
  },
  {
   "file": "agents/v08-p3/artifacts/evidence/gridspan-growth.jsonl",
   "line": 4,
   "description": "Sandboxed run, constant 36,705-byte input: gridSpan 1e3/1e4/1e5/1e6 gives cell.text calls of exactly 1e3/1e4/1e5/1e6 and peak RSS of 113.6/117.2/148.6/473.0 MiB; wall time 22.4 s at 1e6 against a 1.0 s limit"
  },
  {
   "file": "agents/v08-p3/artifacts/evidence/gridspan.py",
   "line": 30,
   "description": "The harness: builds a 1x1 docx with python-docx, sets w:gridSpan/@val, counts _Cell.text calls, and calls RendererRegistry.bundled().render(RenderSource(data, DOCX, 'a.docx'), RenderLimits(seconds=1.0))"
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker can write bytes entries to a DatabaseStorage mount (any subject with write rights on some path)"
  },
  {
   "kind": "system_configuration",
   "description": "The vfs[docx] extra (python-docx) is installed, so the docx renderer is available"
  },
  {
   "kind": "user_interaction",
   "description": "The operator or host later runs DatabaseStorage.reindex(), the only place rendering happens"
  },
  {
   "kind": "third_party_dependency",
   "description": "python-docx 1.2.0 _Row.cells expands a horizontal span into grid_span repeated cells, taken from the unvalidated w:gridSpan/@val"
  }
 ],
 "execution": {
  "attacker_perspective": "A lower-trust agent or ETL writer with ordinary write rights stores one small .docx entry. The renderer cost lands later on the operator's reindex, in the host process that all agents share.",
  "payloads": [
   "A word/document.xml holding one table, one w:tc whose w:tcPr contains <w:gridSpan w:val=\"1000000\"/> and a paragraph of 100 characters (about 36 KB zipped)"
  ],
  "instructions": [
   "Build a 1x1 table docx with python-docx, put 100 characters in the cell, and append w:gridSpan with w:val=N to the cell's w:tcPr",
   "Call RendererRegistry.bundled().render(RenderSource(data, DOCX, 'a.docx'), RenderLimits(seconds=1.0)) in the sandbox, counting _Cell.text calls and reading ru_maxrss",
   "Repeat for N = 1e3, 1e4, 1e5, 1e6 with the input size held constant, and stop there (no larger values)"
  ],
  "observed_result": "Input stayed at 36,705 bytes. cell.text calls equalled N exactly (1,000 to 1,000,000). Peak RSS grew from 113.6 MiB to 473.0 MiB. Wall time at N=1e6 was 22.4 s against RenderLimits.seconds=1.0, so the clock did not stop the expansion. Statuses were 'ok' for 1e3 and 1e4, and 'empty' ('no text in 1 units') for 1e5 and 1e6. Work and memory grow linearly with the attribute value, not with the input size."
 },
 "remediation": {
  "strategy": "Do not iterate python-docx's span-expanded row.cells. Walk each row's w:tc elements directly. Compute each cell's text once. Clamp each span to the table's declared grid width (len(tblGrid.gridCol_lst), which is proportional to the input bytes) and to the columns that remain in the row. Then repeat the already computed string, so the row length is bounded by bytes actually present. Optionally check builder.out_of_time() between rows during collection, and return 'truncated' when a row is cut.",
  "code_changes": [
   {
    "file_name": "src/vfs/rendering/docx.py",
    "fixed_code": "    def table(self, table: Any) -> None:\n        grid = max(1, len(table._tbl.tblGrid.gridCol_lst))\n        rows: list[list[str]] = []\n        for tr in table._tbl.tr_lst:\n            if rows and self._builder.out_of_time():\n                break\n            cells: list[str] = []\n            for tc in tr.tc_lst:\n                if len(cells) >= grid:\n                    break\n                text = self._docx.table._Cell(tc, table).text\n                cells.extend([text] * max(1, min(tc.grid_span, grid - len(cells))))\n            rows.append(cells)\n        self._builder.table(rows)"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Any principal with write rights can plant the payload; it is trivial and a few KB. It needs the docx extra installed and fires only when the operator runs reindex, which is routine maintenance."
  },
  "impact": {
   "score": "medium",
   "reason": "Memory and CPU on the operator's reindex grow linearly with an attribute value up to 2^31-1. They run in the in-process offload pool shared with every agent's grep, and that work cannot be interrupted. Observed: 473 MiB and 22 s at 1e6. Extrapolated, not executed: process-wide OOM or hours-long stalls at the maximum, and an un-landed row that is retried on every reindex. This is availability only; no data is disclosed or changed."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The source path is verified line by line. The library behaviour was read from the installed python-docx 1.2.0, and linear growth at constant input size was reproduced in the approved sandbox with counted calls. Only the maximum-span process exhaustion is extrapolated, not observed."
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

- Scratch, the only place you or target code may write: `./agents/f08-p5/scratch/`. Never write `./agents/f08-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f08-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f08-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.rendering.docx:table-gridspan-expansion"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
