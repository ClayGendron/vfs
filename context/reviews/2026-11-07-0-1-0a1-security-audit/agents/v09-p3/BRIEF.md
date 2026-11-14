# Candidate verifier brief for `v09-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) h08-render. Repository: . at commit 3586750 (read-only).

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
  "proposed_verdict": "needs_validation",
  "fingerprint": "vfs.rendering.xlsx:dimension-driven-row-iteration-unclocked",
  "title": "An xlsx sheet's declared dimension drives empty-row iteration that the 60 s render clock never checks",
  "description": "XlsxRenderer opens workbooks read_only. In openpyxl 3.1.5, ReadOnlyWorksheet takes max_row and max_column from the sheet's <dimension ref>, and _cells_by_row yields a filler row of max_column cells for every row up to max_row, even when sheetData is empty. vfs's _cells() iterates every yielded cell with no clock or budget check. The deadline is consulted only after _cells returns, in Builder.table. A tiny sheet declaring a huge row range therefore makes the render loop run for time proportional to rows times columns. No vfs limit stops it, and the offload worker that runs it cannot be interrupted. The stamp is never landed, so each later reindex starts the same work again.",
  "claimed_root_cause": "_cells() walks sheet.iter_rows() with no deadline, cell-count or row-count budget. The cooperative clock covers only Builder calls, not openpyxl's dimension-driven iteration.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1287,
    "scope": "DatabaseStorage._render_step",
    "description": "Operator reindex renders a writer-supplied pending xlsx row on the offload pool"
   },
   {
    "kind": "propagation",
    "file": "src/vfs/rendering/xlsx.py",
    "line": 75,
    "scope": "XlsxRenderer.render",
    "description": "load_workbook(read_only=True, data_only=True); each sheet calls _cells(sheet) before any Builder clock check"
   },
   {
    "kind": "sink",
    "file": "src/vfs/rendering/xlsx.py",
    "line": 160,
    "scope": "_cells",
    "description": "for row in sheet.iter_rows(): for cell in row: ... runs with no deadline check"
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/rendering/xlsx.py",
    "line": 160,
    "description": "_cells iterates all rows and cells openpyxl yields; no limits object is passed in"
   },
   {
    "file": "src/vfs/rendering/markdown.py",
    "line": 112,
    "description": "Builder.out_of_time is consulted only from Builder methods, which run after _cells returns"
   },
   {
    "file": "src/vfs/storage/backends/database/offload.py",
    "line": 1,
    "description": "The offload docstring states that a running worker finishes into the void; no interrupt exists"
   }
  ],
  "blockers": [
   "The local check was not executed. The fixture-harness attempt was stopped by the session's safety classifier.",
   "The openpyxl 3.1.5 read-only padding behaviour (worksheet/_read_only.py _cells_by_row yields empty_row up to max_row from parse_dimensions) comes from reading source; it needs an executed observation."
  ],
  "validation_plan": {
   "local": "In the sandbox, build a one-cell xlsx and rewrite its sheet <dimension ref> to A1:Z{R} for R = 1,000 and then 10,000. Render with RenderLimits(seconds=0.5) and record wall time and status. The claim holds if wall time grows with R at constant input size and exceeds limits.seconds by a wide margin before the status returns. Regression: pass the Builder or deadline into _cells and stop on out_of_time, cap the iterated cell count, or iterate only parsed cells instead of the dimension-padded grid."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/render.py",
   "src/vfs/storage/backends/database/offload.py",
   "src/vfs/ops.py"
  ],
  "invariant": "Who runs rendering: whether caller bytes are rendered in the writer's own call or later on behalf of the operator",
  "method": "source",
  "result": "Rendering never runs in the write verb. write(data=...) stores the blob and the row is set to render_status='pending' (writes.py:1181). Rendering happens only inside DatabaseStorage.reindex() (backend.py:1118), which is a storage-maintenance method and not one of the 25 router verbs (ops.py:36-62). _render_step (backend.py:1250-1296) selects every dirty bytes row of every subject (render.py select_render_dirty, with no authority filter) and renders each one serially in render_rows on the shared offload pool through call_offloaded (backend.py:1287-1288). A worker that is already running cannot be interrupted (offload.py docstring). The stamp is landed only after the whole cut has rendered, so a row whose render never finishes stays pending, and every later reindex picks it up again. The cost therefore lands on the operator's maintenance job and on the host process that all agents share, not on the writer. There is no body-size cap on write data; BLOB_PAGE_BYTES (8 MiB, dialects.py:102) only meters the bytes held in flight per cut.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/rendering/seam.py",
   "src/vfs/rendering/markdown.py",
   "src/vfs/rendering/registry.py"
  ],
  "invariant": "Whether RenderLimits bound memory and CPU during library parsing, or only the emitted text",
  "method": "source",
  "result": "Every limit is enforced only inside Builder: the character and ratio checks run in _append (markdown.py:265-279), the clock is checked in boundary()/unit() and between table rows (markdown.py:122-160, 186-200), and the unit cap is checked in unit(). Nothing bounds the work a library or renderer helper does before it hands a value to Builder: zip decompression, XML parsing, python-docx row-cell expansion, openpyxl row iteration, xlsx region and table construction, docx inline note assembly. The RENDER_RATIO comment calls the ratio 'the decompression-bomb guard', but it compares output characters with input bytes after expansion has already happened. The registry catches Exception (registry.py:105-108), so MemoryError comes back as a 'failed' state if it is raised at all, while RecursionError and timeouts never arrive as exceptions.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/rendering/docx.py"
  ],
  "invariant": "Whether docx footnote and comment parts parsed with stdlib ElementTree are safe from entity expansion and external entities",
  "method": "source",
  "result": "_note_texts calls xml.etree.ElementTree.fromstring(part.blob) (docx.py:90-101). The interpreter in this environment, Python 3.13.11, reports pyexpat.EXPAT_VERSION 'expat_2.6.3'. That was a version read of the third-party library only, with no vfs code run. Expat 2.4.0 and later has built-in protection against billion-laughs amplification, and ElementTree does not resolve external entities. No candidate for entity expansion or external entities. Separate docx footnote amplification is reported as a candidate below.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/rendering/pdf.py"
  ],
  "invariant": "Whether the pypdf path bounds stream decompression",
  "method": "source",
  "result": "The installed pypdf is 6.19.0. Its filters.py and Configuration declare 75,000,000-byte caps on FlateDecode and LZW output and on declared or array-based stream lengths, plus a 5,000,000-byte recovery input cap. The vfs PdfRenderer catches only PyPdfError as corrupt; anything else, including MemoryError, is caught by the registry. Peak memory per stream is bounded by the library at about 75 MB, and I found no unbounded pdf-specific path in vfs code. A 75 MB cap per stream across many pages is a library-level residual; it is recorded as hardening.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/rendering/seam.py",
   "src/vfs/storage/backends/database/render.py",
   "src/vfs/models/rows.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/topology.py"
  ],
  "invariant": "Whether caller-shaped JSON can reach units_from_json -> Unit(**item)",
  "method": "source",
  "result": "render_units is a row-only column (rows.py:90), so callers never author it. Writes reset it to None (writes.py:1185). Move and copy copy it verbatim between rows (topology.py:98), and only land_renderings writes it, from units_to_json of renderer-produced Unit tuples (render.py:355; seam.py:238-242). json.dumps escapes the attacker-influenced label, for example an xlsx sheet title. No caller path reaches Unit(**item) with keys the caller chose. Covered.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/models/chunking.py"
  ],
  "invariant": "Whether the notebook chunker bounds nested or oversized JSON",
  "method": "source",
  "result": "split_notebook (chunking.py:327-347) calls json.loads and falls back to the recursive splitter on ValueError, KeyError, TypeError or RecursionError. CPython's json decoder runs in linear time and guards recursion, so deep nesting raises RecursionError, which is caught. The cell walk is linear in the number of cells and the length of their sources. No superlinear path found. Covered.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Frendering%23renderers::src%2Fvfs%2Frendering%2Fseam.py%23RenderLimits::src%2Fvfs%2Frendering::ATTACK-CLASSES.md%23Resource%20and%20file%20handling",
  "agent_id": "h08-render",
  "reviewed_paths": [
   "src/vfs/rendering/pptx.py"
  ],
  "invariant": "Whether the pptx shape walk and tables are bounded",
  "method": "source",
  "result": "The group walk is bounded by embedded_depth (pptx.py:79-85). python-pptx row.cells yields only the tc elements present, with no expansion for spans. Text frames go straight to Builder, so pptx-specific amplification is limited to zip-part decompression, which is reported below.",
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

- Scratch, the only place you or target code may write: `./agents/v09-p3/scratch/`. Never write `./agents/v09-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v09-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v09-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs.rendering.xlsx:dimension-driven-row-iteration-unclocked` unless you identify a genuinely different root cause.

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
