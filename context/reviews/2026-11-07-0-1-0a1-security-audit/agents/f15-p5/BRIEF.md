# Final record verifier brief for `f15-p5`

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
 "fingerprint": "vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction",
 "title": "edit's fuzzy replacers run quadratic pure-Python matching on the event loop inside the writer transaction, with no size, count or time bound",
 "description": "A principal that may modify one text entry, for example a file it just wrote itself, can send an edit whose old string does not match exactly. replace() then falls back to the fuzzy replacers in src/vfs/storage/replace.py. Three costs there grow with the square of the input. First, block_anchor_replacer scans forward from every first-anchor line to the end of the file when the last anchor never appears, which is O(L^2) in lines. Second, its similarity step runs a full-matrix pure-Python Levenshtein, which is O(M^2) in the length of the middle line. Third, line_trimmed_replacer recomputes each match's start offset with an O(i) sum, and replace() then computes a line number and splits the whole content again for every match when it builds the multi-match error, so L matches cost O(L^2). edit_rows calls this code synchronously inside the coroutine, once per target, inside the writer transaction (BEGIN IMMEDIATE on SQLite). InMemoryStorage also serializes every session behind one asyncio.Lock. Nothing caps the length of old or new, the number of edits, the number of targets, or the wall time. So one small call freezes the host's shared event loop for every other agent in the process, and holds the mount's write lock the whole time. Every probe failed with vfs.invalid and committed nothing, so the attacker does not need a successful edit. Measured independently through the public verb: a 24 KB file with a 5-byte old string stalled the loop for 2.6 s (block_anchor). A 24 KB file with a 3-byte old string stalled it for 4.0 s (line_trimmed). A 4.8 KB request stalled it for 1.2 s (Levenshtein). Each doubling of input cost about 3.7x to 4.1x.",
 "root_cause": "replace() falls back to line_trimmed_replacer and block_anchor_replacer whenever the exact search misses. block_anchor_replacer's forward scan (replace.py:179-185) only stops when it finds the last anchor, so an absent last anchor makes it O(L^2). levenshtein (replace.py:61-82) builds a full O(n*m) Python matrix with no length cap, and calculate_similarity calls it for every middle line of every candidate. line_trimmed_replacer (replace.py:145) and replace()'s multi-match error builder (replace.py:321-325, which calls get_line_number and get_context_lines; the latter splits the whole content each time) recompute offsets and context for every match. edit_rows (writes.py:261) runs edited_entry inline in the async writer transaction for every target, with no call_offloaded, no deadline and no input caps. That differs from glean, indexing and signals, which do offload their CPU-bound work.",
 "intended_behavior": "An edit's matching cost should stay bounded: close to linear in the sizes of the content and of old. Fuzzy fallback should be refused, or capped, once it would exceed a declared work budget. CPU-bound matching should run off the event loop through call_offloaded with a deadline, the way the reindex, glean and signals paths already do. It should also run before the writer lock is taken, or at least not hold that lock for an unbounded time, so one caller cannot stall other principals sharing the host.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 1016,
   "scope": "AsyncVirtualFileSystem.edit",
   "description": "The public verb takes caller-supplied path/observations plus old/new or an edits list. _gate_params (1031-1041) checks only types, then the call routes to storage at 1057."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/params.py",
   "line": 173,
   "scope": "PARAM_SPECS['edit']",
   "description": "old and new are typed 'str', edits is an EditOperation list and observations is a list. None has a length or count limit."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 734,
   "scope": "DatabaseStorage.edit",
   "description": "After the rung gate and the per-target modify check, edit_rows runs inside _execute_write (745). That is a writer transaction, opened BEGIN IMMEDIATE on SQLite (1666-1673)."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 261,
   "scope": "edit_rows",
   "description": "edited_entry runs synchronously in the coroutine for every target. A failed target appends an error and the loop continues to the next target."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/editing.py",
   "line": 38,
   "scope": "edited_entry",
   "description": "apply_edits (replace.py:342-355) passes every EditOperation through replace()."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/replace.py",
   "line": 287,
   "scope": "replace",
   "description": "An exact miss falls through to line_trimmed_replacer and then block_anchor_replacer. When there are many matches, 321-325 compute a line number and the context lines for each one, splitting the whole content every time."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/replace.py",
   "line": 182,
   "scope": "block_anchor_replacer",
   "description": "When the last anchor is absent, the forward scan runs from each first-anchor line to the end of the file, O(L^2). calculate_similarity then calls levenshtein (202, defined 61-82), which is O(M^2) per middle line."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/replace.py",
   "line": 179,
   "description": "The nested loop over content_lines breaks only when the last anchor matches."
  },
  {
   "file": "src/vfs/storage/replace.py",
   "line": 66,
   "description": "levenshtein allocates and fills a full (len(a)+1)x(len(b)+1) Python list matrix, with no length cap."
  },
  {
   "file": "src/vfs/storage/replace.py",
   "line": 145,
   "description": "line_trimmed_replacer recomputes start_pos with an O(i) sum for every match."
  },
  {
   "file": "src/vfs/storage/replace.py",
   "line": 324,
   "description": "get_context_lines splits the whole content and counts newlines in a prefix, once per match, while building the multi-match error."
  },
  {
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 261,
   "description": "edited_entry is called inline in the coroutine with no call_offloaded. Compare indexing.py:330, glean.py:872 and signals.py:123, which do offload."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1666,
   "description": "_execute_write opens the writer transaction (BEGIN IMMEDIATE on SQLite) and holds it across edit_rows."
  },
  {
   "file": "src/vfs/params.py",
   "line": 173,
   "description": "The edit parameter specs declare no maximum for old, new, edits or observations."
  },
  {
   "file": "src/vfs/storage/backends/database/engine.py",
   "line": 722,
   "description": "On InMemoryStorage, _SerializedSessions puts every session behind one asyncio.Lock, so other principals' operations also queue behind the edit."
  },
  {
   "file": "agents/v16-p3/artifacts/evidence/verify_edit.txt",
   "line": 1,
   "description": "Verifier's own sandboxed run through the public edit verb. Edit time grows about 4x per doubling for all three shapes. The longest event-loop gap equals the edit time. A control exact edit on a 16 KB file took 20 ms with a 3.5 ms gap. Script: agents/v16-p3/artifacts/evidence/verify_edit.py."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The caller needs modify rights on at least one text entry, for example a file it wrote itself. No rights over other principals' data are needed."
  },
  {
   "kind": "system_configuration",
   "description": "The host process serves several agents or principals from one event loop and mount, which is the embedded-library model. The writer-lock effect applies to SQLite-backed mounts and to InMemoryStorage's serialized sessions. On other engines the event-loop stall remains. The host must also not impose its own cap on edit argument or file size; vfs itself has none."
  },
  {
   "kind": "data_state",
   "description": "The target's content and the old string are shaped to miss exactly and reach a quadratic fuzzy path. Three shapes work: many lines equal to the first anchor with the last anchor absent; one candidate whose long middle line differs; or many lines that match a whitespace-trimmed single-line old."
  }
 ],
 "execution": {
  "attacker_perspective": "A named principal (alice) has ordinary write and modify rights on her own file in a shared AsyncVirtualFileSystem over InMemoryStorage. Another principal (carol) reads her own file concurrently on the same loop.",
  "payloads": [
   "write /a12000.txt content='a\\n'*12000; edit(path='/a12000.txt', old='a\\nx\\nb', new='z')",
   "write /l2400.txt content='a\\n'+'x'*2400+'\\nb\\n'; edit(path='/l2400.txt', old='a\\n'+'y'*2400+'\\nb', new='z')",
   "write /t12000.txt content='a\\n'*12000; edit(path='/t12000.txt', old='  a', new='z')"
  ],
  "instructions": [
   "Run agents/v16-p3/artifacts/evidence/verify_edit.py as tools/sandbox-run.py <scratch> ./.venv/bin/python -I <script>. The sandbox has no network, an empty environment, scratch-only writes, CPU 60 s, wall-clock 120 s and RSS 2 GiB.",
   "For each shape, call the public edit verb at sizes n, 2n and 4n. Record the edit duration, the longest gap seen by a 2 ms asyncio ticker, the number of Levenshtein cells (counted by wrapping replace.levenshtein), and the latency of carol's concurrent read. A control exact-match edit gives the baseline."
  ],
  "observed_result": "Control exact edit on 16 KB: 20 ms, longest loop gap 3.5 ms. block_anchor at L=3000/6000/12000 lines: 176/642/2628 ms (x3.66, x4.09). levenshtein at M=600/1200/2400: 76/311/1214 ms (x4.09, x3.90), with Levenshtein cells 361201/1442401/5764801 (exactly quadratic). line_trimmed at L=3000/6000/12000: 266/1011/3995 ms (x3.81, x3.95). In every fuzzy probe the longest event-loop gap was within 15 ms of the edit duration. When carol's read was scheduled during the stall it waited the same span (2628 ms at anchor L=12000). Pure replace() alone reproduces the anchor timings (159/632/2552 ms). Every fuzzy edit returned vfs.invalid and committed nothing."
 },
 "remediation": {
  "strategy": "Bound the work and move it off the event loop. (1) In block_anchor_replacer, precompute the indices of the stripped lines once, find each first anchor's next last anchor with bisect, and cap the number of candidates. That removes the O(L^2) scan. Compute line start offsets once with a prefix sum and use them in both fuzzy replacers. In replace(), compute line numbers from those offsets, split the content once, and list context for only the first few matches in the multi-match error. (2) Replace the Python levenshtein with a banded or early-exit version, or a vfs-core kernel. Skip fuzzy similarity when a middle line exceeds a declared length, or when len(content_lines)*len(find_lines) exceeds a work budget, and refuse with a classified invalid error that names the exact-match requirement. (3) Run the batch's edited_entry work through call_offloaded with a deadline, or do the matching before the writer transaction where the existing version guard keeps that safe. Regression test: count operations, never wall time. For example, count levenshtein cells or replacer loop iterations for the 'a\\n'*L / 'a\\nx\\nb' and '  a' shapes at L and 2L, and assert that growth is linear.",
  "code_changes": [
   {
    "file_name": "src/vfs/storage/replace.py",
    "fixed_code": "from bisect import bisect_left\n\ndef block_anchor_replacer(content: str, find: str) -> Generator[Match]:\n    content_lines = content.split(\"\\n\")\n    find_lines = _split_dropping_trailing_blank(find)\n    if len(find_lines) < 3:\n        return\n    first_line, last_line = find_lines[0].strip(), find_lines[-1].strip()\n    stripped = [line.strip() for line in content_lines]\n    last_at = [j for j, line in enumerate(stripped) if line == last_line]\n    candidates: list[tuple[int, int]] = []\n    for i, line in enumerate(stripped):\n        if line != first_line:\n            continue\n        k = bisect_left(last_at, i + 2)\n        if k < len(last_at):\n            candidates.append((i, last_at[k]))\n        if len(candidates) > MAX_ANCHOR_CANDIDATES:\n            return\n    # similarity as before, but refuse lines longer than MAX_FUZZY_LINE_CHARS before calling levenshtein,\n    # and compute start offsets from one prefix-sum list instead of a per-match sum"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Any principal with modify rights on any one file, including its own, can trigger this with a request of a few KB plus a cheap prior write. Agents routinely send edits whose old string misses. Nothing in params.py, base.py or the storage caps old/new length, edit count, target count or file size, except MariaDB's packet cap on writes."
  },
  "impact": {
   "score": "medium",
   "reason": "The stall freezes the shared event loop for every other principal on the host. On SQLite-backed mounts it also holds the writer lock, for a time that grows with the square of the input: 24 KB gave 2.6 to 4.0 s, and at the measured 4x per doubling about 100 KB would give roughly 40 to 60 s. The effect is transient: it ends when the call returns, leaves no persistent state, and the attacker can repeat it on every call. It costs availability only, with no confidentiality or integrity effect."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The quadratic loops are plain in source and match the trace line for line. The verifier reproduced the result independently through the public verb in the sandbox. Growth was about 4x per doubling for all three shapes, the Levenshtein cell count was exactly quadratic, the loop stall equalled the edit time, and a different principal's read was blocked. A control exact edit stayed fast."
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

- Scratch, the only place you or target code may write: `./agents/f15-p5/scratch/`. Never write `./agents/f15-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f15-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f15-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
