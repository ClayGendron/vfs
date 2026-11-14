# Final record verifier brief for `f18-p5`

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
 "fingerprint": "vfs.rendering.xlsx:region-table-quadratic-materialization",
 "title": "xlsx region layout does quadratic work on writer-shaped cell layouts before any render budget applies",
 "description": "A subject that can write a bytes entry stores a small .xlsx file. The operator's reindex later renders it with the bundled XlsxRenderer, on the shared offload pool inside the host process. regions() joins cells that touch by side or by corner. So an L-shape (R cells down column A, then C cells across the last row) or a diagonal of n cells becomes one region whose bounding box is R x C, or n x n. _table() then builds the whole box as Python lists, header plus body, (bottom-top+1) x (right-left+1) entries, before Builder.table() emits its first row. The character budget, the output/input ratio guard and the clock are only checked inside Builder, so they act after that allocation has already happened. Observed locally: a 56,977-byte workbook made 32,012,001 table entries and a 270.9 MB traced peak during DatabaseStorage.reindex() on SQLite, and the rendering still landed as 'rendered'. Doubling both sides quadrupled the peak (68.7 MB, then 270.9 MB), while the file grew less than 2x. Separately, _merged() compares each region box with every box already kept, so k isolated cells cost k(k-1)/2 overlap checks: 400 cells made 79,800 calls and 6,400 cells made 20,476,800. That work also runs before any budget and never reads the clock. The module docstring says the region pass is linear. Neither of these two steps is linear.",
 "root_cause": "In src/vfs/rendering/xlsx.py, _table() builds every grid position of a region's bounding box as a list of lists, and _merged() does pairwise overlap checks over all region boxes. Both run in full before control reaches Builder, and Builder is the only place RenderLimits (chars, ratio, seconds) are enforced. Box area and region count depend on how the writer lays out cells, not on the input size or on the output budget.",
 "intended_behavior": "Per the xlsx module docstring and RenderLimits: one render holds memory linear in a sheet's non-empty cell count, the region pass is linear, and the character budget and wall clock bound the work spent on any one rendering, so a small input cannot make the renderer allocate or compute far beyond what it can emit.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 686,
   "scope": "DatabaseStorage.write",
   "description": "A lower-trust subject with write rights stores arbitrary .xlsx bytes. No body-size or cell-layout check applies to write data."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 1181,
   "scope": "staged row values",
   "description": "The bytes row is stored with render_status 'pending', so a later reindex picks it up."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1288,
   "scope": "DatabaseStorage._render_step",
   "description": "The operator's reindex runs render_rows on the shared offload pool with call_offloaded. A worker that is already running cannot be interrupted."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/render.py",
   "line": 294,
   "scope": "render_rows",
   "description": "registry.render(RenderSource(data, row.mime, row.name), limits) dispatches to the bundled XlsxRenderer."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 88,
   "scope": "XlsxRenderer.render",
   "description": "for box in regions(cells): builder.table(_table(cells, box, ...)). Both regions() and _table() run before Builder sees any row."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 120,
   "scope": "regions",
   "description": "Joining cells that touch by corner turns a diagonal or an L-shape of O(R+C) cells into one region with an R x C bounding box."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 137,
   "scope": "_merged",
   "description": "Each box is checked against every box already kept: O(k^2) overlap checks over k regions, with no clock or budget check."
  },
  {
   "kind": "sink",
   "file": "src/vfs/rendering/xlsx.py",
   "line": 157,
   "scope": "_table",
   "description": "The body list comprehension builds every grid position of the bounding box, area R x C, before Builder.table applies the character or time budget."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/rendering/xlsx.py",
   "line": 157,
   "description": "body = [[str(row), *(cells.get((row, column), '') for column in columns)] for row in range(box.top, box.bottom + 1)] is built in full and returned as a list."
  },
  {
   "file": "src/vfs/rendering/xlsx.py",
   "line": 143,
   "description": "The inner loop 'for other in out: if merged.overlaps(other)' runs once per kept box for each new box, which is quadratic in the number of regions."
  },
  {
   "file": "src/vfs/rendering/xlsx.py",
   "line": 17,
   "description": "The module docstring states 'the region pass is linear too' (and regions() at line 106 claims union-find makes it linear). _merged and _table contradict this."
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 191,
   "description": "Builder.table takes an already-built Sequence. It computes width = max(len(row) for row in rows), and only then checks the clock and the character budget per row (lines 198-204), after the full table exists."
  },
  {
   "file": "src/vfs/rendering/seam.py",
   "line": 40,
   "description": "RENDER_CHARS is 2 MiB and RENDER_SECONDS is 60. Both are enforced only through Builder, so neither bounds _table or _merged."
  },
  {
   "file": "src/vfs/rendering/registry.py",
   "line": 46,
   "description": "RendererRegistry.bundled() includes XlsxRenderer, and DatabaseStorage uses it by default (backend.py:234). The renderer is active wherever openpyxl is installed."
  },
  {
   "file": "agents/v10-p3/artifacts/evidence/xlsx-growth.json",
   "line": 1,
   "description": "Direct XlsxRenderer.render under default RenderLimits, with each <dimension> element removed. L 2000x1000 (18,775 B): 2,003,001 entries, 20.6 MB peak. L 4000x2000 (30,928 B): 8,006,001 entries, 68.3 MB. L 8000x4000 (56,978 B): 32,012,001 entries, 270.7 MB, status truncated. Diagonal n=500/1000/2000: 251,001 / 1,002,001 / 4,004,001 entries; the ratio guard failed the larger two only after materialization. Isolated grids of 400 / 1,600 / 6,400 cells: 79,800 / 1,279,200 / 20,476,800 overlap calls."
  },
  {
   "file": "agents/v10-p3/artifacts/evidence/xlsx-e2e-reindex.json",
   "line": 1,
   "description": "End to end through DatabaseStorage.write and reindex on SQLite. Control workbook (3 cells): 0.71 MB peak. L 4000x2000 (30,928 B): 68.7 MB peak. L 8000x4000 (56,977 B): 270.9 MB peak, 32,012,001 table entries. Each reindex succeeded and reported the row as rendered."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker is a named subject or service with write rights on some path of a DatabaseStorage mount. Any writer can store arbitrary bytes there."
  },
  {
   "kind": "third_party_dependency",
   "description": "openpyxl (the vfs[xlsx] extra) is installed, so the bundled XlsxRenderer is available. Version 3.1.5 was observed."
  },
  {
   "kind": "system_configuration",
   "description": "The host or operator runs DatabaseStorage.reindex() in the same process that serves agents. That is the shipped design: offload pool threads in the host process."
  },
  {
   "kind": "data_state",
   "description": "The stored workbook's sheet XML omits the <dimension> element (or declares a small one), so openpyxl's read-only iterator does not pad every row to the full width and the quadratic cost falls on vfs's _table rather than on the library."
  }
 ],
 "execution": {
  "attacker_perspective": "A lower-trust writer stores a few tens of kilobytes of .xlsx. They wait for the operator's routine reindex to render it on the host process that all agents share.",
  "payloads": [
   "An .xlsx with one sheet: numeric cells at A1..A8000 plus row 8000 columns B..ER (4,000 columns total), and <dimension> removed from xl/worksheets/sheet1.xml. That is 11,999 cells and 56,977 bytes.",
   "An .xlsx with one sheet of k isolated cells at (2i+1, 2j+1), for example an 80x80 grid of 6,400 cells, to drive _merged's pairwise loop."
  ],
  "instructions": [
   "Build the workbook with openpyxl write_only mode, then rewrite the zip without the <dimension .../> element.",
   "Under tools/sandbox-run.py: DatabaseStorage(url='sqlite+aiosqlite:///<scratch>/b.sqlite').write(entries=[Entry(path=Path('/u/b.xlsx'), data=payload)], parents=True).",
   "Start tracemalloc, await storage.reindex(), and record the traced peak. Wrap xlsx._table to count the entries it returns, and wrap Box.overlaps to count calls.",
   "Repeat at half size (4000x2000) and with a 3-cell control to see the growth."
  ],
  "observed_result": "Reindex peak traced memory was 0.71 MB for the 3-cell control, 68.7 MB for 4000x2000 (30,928 B) and 270.9 MB for 8000x4000 (56,977 B). _table returned 32,012,001 entries for the last one, and its rendering landed as 'rendered' (text truncated at about 2.09M chars). Memory grew about 4x per doubling, against under 2x growth in file size. Isolated-cell grids made exactly k(k-1)/2 overlap calls (20,476,800 at k=6,400) before any budget or clock check. Larger sizes were not run, to stay inside the 2 GiB sandbox cap."
 },
 "remediation": {
  "strategy": "Make the xlsx table path stream rows and stop against the output budget. Make the region merge sub-quadratic or check the clock. (1) Turn _table into a generator that yields the header and then one body row at a time. Change Builder.table to accept an iterable plus an explicit width, so its existing per-row clock and character checks run before the next row is built. Rows needed is then bounded by the remaining budget divided by about 4*width, and width is at most 18,278 because of get_column_letter. (2) Replace _merged's all-pairs loop with a sweep over boxes sorted by top, keeping an interval structure on columns, or at least pass the Builder and check out_of_time()/budget inside the loop and in regions(). (3) Fix the module and regions() docstrings so they describe the real complexity. Add operation-count tests (entries built, overlap calls) at two sizes, asserting linear growth.",
  "code_changes": [
   {
    "file_name": "src/vfs/rendering/xlsx.py",
    "fixed_code": "def _table(cells: Cells, box: Box, column_letter: Any) -> Iterator[list[str]]:\n    \"\"\"One region as table rows, lazily: letters across, row numbers down, blanks empty.\"\"\"\n    columns = range(box.left, box.right + 1)\n    yield [\"\", *(column_letter(column) for column in columns)]\n    for row in range(box.top, box.bottom + 1):\n        yield [str(row), *(cells.get((row, column), \"\") for column in columns)]\n\n# caller: builder.table(_table(cells, box, letter), width=box.right - box.left + 2)"
   },
   {
    "file_name": "src/vfs/rendering/markdown.py",
    "fixed_code": "def table(self, rows: Iterable[Sequence[object]], *, width: int | None = None) -> bool:\n    \"\"\"A GFM pipe table whose first row is the header; rows are pulled one at a time.\"\"\"\n    if self.stopped:\n        return False\n    if width is None:\n        rows = list(rows)\n        if not rows:\n            return True\n        width = max(len(row) for row in rows)\n    self._blank()\n    for index, row in enumerate(rows):\n        if index and self.out_of_time():\n            self._open = False\n            return False\n        cells = [table_cell(value) for value in row] + [\"\"] * (width - len(row))\n        if not self._text(\"| \" + \" | \".join(cells) + \" |\"):\n            return False\n        if index == 0 and not self._append(\"|\" + \" --- |\" * width):\n            return False\n    self._blank()\n    return True"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Any subject with write rights can plant the file, and it is small (under 60 KB) and easy to build. It needs the openpyxl extra, and it fires only when the operator runs reindex, which is routine maintenance. A row whose render never finishes stays pending and is retried on every reindex."
  },
  "impact": {
   "score": "medium",
   "reason": "Memory and CPU grow quadratically in the shared host process, before any RenderLimits check. 57 KB produced a 271 MB peak, and each further doubling quadruples it, so a few hundred KB can reach multiple GB. The isolated-cell layout drives unbounded uninterruptible CPU on a worker. This is availability only, for the reindex job and the host process shared by agents. No confidentiality or integrity effect. Process OOM at production scale was inferred from the measured growth, not observed."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The source path is direct and the defaults activate it. The quadratic growth was reproduced twice inside the sandbox with operation counts and traced memory: directly on the renderer, and end to end through write and reindex on SQLite. The control and the doubling series rule out a constant overhead."
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

- Scratch, the only place you or target code may write: `./agents/f18-p5/scratch/`. Never write `./agents/f18-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f18-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f18-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.rendering.xlsx:region-table-quadratic-materialization"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
