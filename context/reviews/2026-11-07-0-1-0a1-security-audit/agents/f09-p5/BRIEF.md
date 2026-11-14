# Final record verifier brief for `f09-p5`

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
 "fingerprint": "vfs.rendering.xlsx:dimension-driven-row-iteration-unclocked",
 "title": "An xlsx sheet's declared dimension and far-off row index drive padded cell iteration that the render clock never checks",
 "description": "XlsxRenderer opens workbooks with read_only=True. In openpyxl 3.1.5, ReadOnlyWorksheet takes max_column and max_row from the sheet's <dimension ref>. Then _cells_by_row yields a padding row (one shared tuple of max_column EMPTY_CELLs) for every missing row between two populated rows. vfs's _cells() walks every yielded cell and checks no clock, cell budget or row budget. The deadline is consulted only after _cells returns, in Builder.table and Builder.unit. So a file of about 4.7 KB, with one cell at A1, one cell at A<R> and a dimension of A1:ZZZ<R>, makes one render iterate 18,278 x R cells. Columns are capped at ZZZ (18,278) by openpyxl; the row index is a plain int with no cap. Measured in the sandbox, with RenderLimits(seconds=0.5): 365,560,000 cells took 3.24 s, and 50,000,000 padded rows took 3.34 s, both about 6.5x over the limit. Cost is linear at about 9 ns per cell, so A1:ZZZ1048576 projects to roughly 170 s, and a row index of 10^8 projects to hours, all against the 60 s RENDER_SECONDS default. This happens during the operator's reindex, on an offload worker that cannot be interrupted. The single-runner reindex lease keeps its heartbeat, so the lease stays held and every other subject's pending render, chunk and posting work waits behind it. The row is landed only after its cut finishes, so a run that is abandoned leaves the row pending, and the next reindex starts the same work again. Correction to the hunter: an empty sheetData, or a lone A1 with a huge dimension, does NOT pad. openpyxl's tail-padding guard is 'max_row < idx' (_read_only.py:100), so the trailing rows are never yielded; this was measured as 26 cells for dimension A1:Z100000 with only A1. The attack needs a second populated row at the far end, which uses the in-between gap padding (_read_only.py:92).",
 "root_cause": "_cells() (src/vfs/rendering/xlsx.py:161-172) walks sheet.iter_rows() over openpyxl's dimension-padded read-only grid. It takes no Builder, deadline or cell or row budget. The cooperative clock in Builder covers only the Builder calls that come after _cells has collected the whole sheet. So the iteration work grows with the declared extent (columns x row gap), not with the input bytes, and no RenderLimits field bounds it.",
 "intended_behavior": "RenderLimits.seconds (RENDER_SECONDS, 'Wall seconds one render may spend before the text so far is kept as partial') should bound each render. Once the clock runs out, an xlsx render should stop within a small constant amount of work and return partial. The work should be proportional to the cells actually stored, not to the dimension or row numbers the file declares.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 1181,
   "scope": "write staging (row values)",
   "description": "A caller with write rights stores arbitrary bytes. The row is staged with render_status='pending', with no body-size or content-shape check on xlsx structure."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1288,
   "scope": "DatabaseStorage._render_step",
   "description": "Operator reindex (under the single-runner lease claimed at backend.py:1140-1143) selects every dirty bytes row and runs render_rows on the offload pool through call_offloaded. It awaits until the worker finishes."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 87,
   "scope": "XlsxRenderer.render",
   "description": "After load_workbook(read_only=True), each sheet calls _cells(sheet) before any Builder clock check runs on its tables."
  },
  {
   "kind": "sink",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 164,
   "scope": "_cells",
   "description": "for row in sheet.iter_rows(): for cell in row: walks every padded EMPTY_CELL that openpyxl yields (max_column wide, one row per missing index), with no deadline or budget."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/rendering/xlsx.py",
   "line": 161,
   "description": "_cells takes only the sheet. No limits object or Builder is passed, so it cannot see the deadline."
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 128,
   "description": "Builder.out_of_time is the only clock. It is called from boundary/unit and between table rows (markdown.py:191 table), all after _cells returns."
  },
  {
   "file": "src/vfs/storage/backends/database/offload.py",
   "line": 24,
   "description": "Offload law: a worker that is already running finishes into the void. No protocol-level interrupt exists."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1143,
   "description": "The reindex holds a heartbeating single-runner lease around the render stage, so one stalled render blocks every reindex for all subjects while it runs."
  },
  {
   "file": "agents/v09-p3/artifacts/evidence/xlsx-dimension-probe.json",
   "line": 1,
   "description": "Sandbox run, openpyxl 3.1.5, input about 4.7 KB in every case. A lone A1 with dimension A1:Z100000 yields 26 cells, so tail padding does not happen. A1+A<R> with A1:Z<R> yields 26R cells (R = 1e3, 1e4, 1e5). A1+A4000 with A1:XFD4000 yields 65,536,000 cells, takes 0.564 s and returns partial against a 0.5 s limit."
  },
  {
   "file": "agents/v09-p3/artifacts/evidence/xlsx-dimension-overshoot.json",
   "line": 1,
   "description": "Sandbox run: A1+A20000 with dimension A1:ZZZ20000 iterates 365,560,000 cells, render wall 3.243 s against limit 0.5 s (6.5x). A1+A50000000 with dimension A1:A50000000 takes 3.339 s (6.7x). Constant 4.7 KB input; time grows linearly with the declared extent."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker holds write rights on some path in a DatabaseStorage or InMemoryStorage mount, so it can store a bytes entry sniffed as xlsx. Any named subject or agent with write access qualifies."
  },
  {
   "kind": "third_party_dependency",
   "description": "The vfs[xlsx] extra (openpyxl 3.1.5) is installed, so the xlsx renderer is registered and not 'unavailable'."
  },
  {
   "kind": "system_configuration",
   "description": "The operator or host runs DatabaseStorage.reindex(), which is the only place rendering happens."
  }
 ],
 "execution": {
  "attacker_perspective": "A lower-trust writer (an agent or subject with write access to one path) uploads one small xlsx. A later operator reindex, shared by all subjects on the host, renders it.",
  "payloads": [
   "xl/worksheets/sheet1.xml = <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><dimension ref=\"A1:ZZZ20000\"/><sheetData><row r=\"1\"><c r=\"A1\" t=\"inlineStr\"><is><t>x</t></is></c></row><row r=\"20000\"><c r=\"A20000\" t=\"inlineStr\"><is><t>x</t></is></c></row></sheetData></worksheet> (inside an otherwise standard openpyxl-generated workbook zip, about 4.7 KB)"
  ],
  "instructions": [
   "Create a one-cell workbook with openpyxl and save it to bytes.",
   "Rewrite xl/worksheets/sheet1.xml with the payload: a dimension of A1:ZZZ<R> and populated rows 1 and R.",
   "Call XlsxRenderer().render(RenderSource(data, XLSX, 's.xlsx'), RenderLimits(seconds=0.5)) and time it. In deployment, write the bytes and run reindex().",
   "Raise R, or use a dimension of A1:A<huge> with populated rows 1 and <huge>, to scale the time linearly with no input growth."
  ],
  "observed_result": "With limit 0.5 s, the render took 3.243 s for R=20000 at ZZZ width (365,560,000 cells), and 3.339 s for a 50,000,000-row gap at width 1. Both came back 'partial' ('0 of 1 units within 0.5 seconds') only after _cells had finished. Input size stayed about 4.7 KB. No further escalation was attempted."
 },
 "remediation": {
  "strategy": "Bound the walk by stored cells and by the clock. Call sheet.reset_dimensions() before iterating, so openpyxl stops padding rows to the declared dimension width. Then pass the Builder into _cells, check builder.out_of_time() every N rows, and stop with a partial result when the clock runs out. That way both wide padding and huge row gaps end within the deadline. Add a regression test that counts the cells or rows _cells visits (not wall time) for a tiny file with a huge dimension and row gap.",
  "code_changes": [
   {
    "file_name": "src/vfs/rendering/xlsx.py",
    "fixed_code": "_CLOCK_EVERY: Final = 1024\n\ndef _cells(sheet: Any, builder: Builder) -> Cells | None:\n    \"\"\"``(row, column) → text`` for every stored cell of *sheet*; ``None`` once the clock runs out.\"\"\"\n    sheet.reset_dimensions()  # padding follows stored cells, never the declared dimension\n    cells: Cells = {}\n    for index, row in enumerate(sheet.iter_rows(), 1):\n        if index % _CLOCK_EVERY == 0 and builder.out_of_time():\n            return None\n        for cell in row:\n            value = cell.value\n            if value is None:\n                continue\n            text = _cell_text(value)\n            if text:\n                cells[cell.row, cell.column] = text\n    return cells\n\n# in XlsxRenderer.render:\n#     cells = _cells(sheet, builder)\n#     if cells is None:\n#         break"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "It needs only ordinary write access and one file of about 5 KB with no special configuration beyond the xlsx extra. Reindex is a routine operator job, and the pending row is picked up again on every run."
  },
  "impact": {
   "score": "medium",
   "reason": "Availability only. One render overruns the 60 s clock by a factor the attacker chooses (minutes to hours), on an offload worker that cannot be interrupted. Meanwhile the heartbeating single-runner reindex lease stays held, so every subject's render, chunk and posting maintenance stalls, and one offload worker shared with grep verify is busy. Memory stays bounded, because the padding is one shared tuple. There is no confidentiality or integrity effect, and an operator can recover by deleting the entry."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The source path is verified end to end, and the behaviour was reproduced in the sandbox against the installed openpyxl 3.1.5 and the repo's XlsxRenderer: time grows linearly with the declared extent at constant input size and overshoots the limit. The hunter's empty-sheetData variant was refuted, and the record is corrected to the gap-padding trigger."
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

- Scratch, the only place you or target code may write: `./agents/f09-p5/scratch/`. Never write `./agents/f09-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f09-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f09-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.rendering.xlsx:dimension-driven-row-iteration-unclocked"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
