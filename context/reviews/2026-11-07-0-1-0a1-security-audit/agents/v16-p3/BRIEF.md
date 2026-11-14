# Candidate verifier brief for `v16-p3`

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
  "fingerprint": "vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction",
  "title": "edit's fuzzy replacers run quadratic pure-Python matching on the event loop inside the writer transaction, with no size, count or time bound",
  "description": "Any principal that may edit one file, including its own, can send an edit whose old string misses exactly. The router then falls back to the fuzzy replacers in src/vfs/storage/replace.py, and three of them are quadratic. block_anchor_replacer scans from every first-anchor line to the end of the file, so it is O(L^2) in lines. It also runs a full-matrix pure-Python Levenshtein, O(M^2) in line length. line_trimmed_replacer pays O(L^2) through its per-match prefix sums and the per-match context split. edit_rows calls this code synchronously in the coroutine. It runs once per target, inside the SQLite BEGIN IMMEDIATE writer transaction. No cap applies to old/new length, the number of edits, the number of targets, or wall time. One small call therefore freezes the host's event loop for every agent sharing the process, and it holds the mount's write lock the whole time. Measured: a 16 KB file with a 5-byte old string blocked the loop for 1.08 s; a 2 KB file with a 2 KB old string blocked it for 0.74 s. Each doubling of input costs about 4x, and the cost multiplies by the number of targets.",
  "root_cause": "replace() falls back to the fuzzy replacers whenever the exact search misses. block_anchor_replacer's forward scan has no exit when the last anchor is absent, levenshtein is a full O(n*m) Python matrix with no length cap, and line_trimmed/replace recompute offsets and context per match. edit_rows runs edited_entry inline in the async writer transaction for every target, with no offload, deadline or input caps.",
  "intended_behavior": "An edit's matching cost should be bounded: near-linear in content and old_string size, with fuzzy fallback refused or capped above a declared work budget. CPU-bound matching should leave the event loop the way grep verify and reindex do (call_offloaded with a deadline), and should finish before the writer lock is taken, or at least without holding it unbounded, so one caller cannot stall other principals.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 1016,
    "scope": "AsyncVirtualFileSystem.edit",
    "description": "Caller-supplied old/new or edits list and path/observations; _gate_params (1035) checks types only and the call routes at 1057."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/params.py",
    "line": 173,
    "scope": "PARAM_SPECS['edit']",
    "description": "old/new are 'str' and edits/observations are lists, with no length or count limit."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 734,
    "scope": "DatabaseStorage.edit",
    "description": "After the rights gate, edit_rows runs inside _execute_write (745), a BEGIN IMMEDIATE writer transaction on SQLite (1666-1673)."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 261,
    "scope": "edit_rows",
    "description": "edited_entry runs synchronously for every target; a failed target appends an error and the loop continues to the next one."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/editing.py",
    "line": 38,
    "scope": "edited_entry",
    "description": "apply_edits threads every EditOperation through replace()."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/replace.py",
    "line": 287,
    "scope": "replace",
    "description": "An exact miss falls through to line_trimmed_replacer and block_anchor_replacer; on many matches, 321-325 compute line number and context per match."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/replace.py",
    "line": 182,
    "scope": "block_anchor_replacer",
    "description": "The forward scan runs from each first-anchor line to the end when the last anchor is absent, O(L^2); calculate_similarity calls levenshtein (202, defined 61-82), O(M^2) per middle line."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/replace.py",
    "line": 179,
    "description": "The nested loop over content_lines has no break unless the last anchor matches."
   },
   {
    "file": "src/vfs/storage/replace.py",
    "line": 66,
    "description": "levenshtein allocates and fills a full (len(a)+1)x(len(b)+1) Python matrix, with no length cap."
   },
   {
    "file": "src/vfs/storage/replace.py",
    "line": 145,
    "description": "line_trimmed_replacer recomputes start_pos with an O(i) sum for every match."
   },
   {
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 261,
    "description": "edited_entry is called inline in the coroutine; no call_offloaded, unlike grep verify and the reindex chunk pass."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1666,
    "description": "_execute_write opens the writer transaction (BEGIN IMMEDIATE on SQLite) that is held across edit_rows."
   },
   {
    "file": "src/vfs/params.py",
    "line": 173,
    "description": "The edit parameter specs declare no maximum for old, new, edits or observations."
   },
   {
    "file": "src/vfs/storage/backends/database/engine.py",
    "line": 722,
    "description": "On InMemoryStorage, _SerializedSessions serializes every session behind one asyncio.Lock, so other principals' ops also queue behind the edit."
   }
  ],
  "conditions": [
   {
    "kind": "authorization_role",
    "description": "The caller needs edit (modify) rights on at least one text entry, for example a file it wrote itself. No rights over other principals' data are needed."
   },
   {
    "kind": "system_configuration",
    "description": "The host process serves several agents or principals from one event loop and mount (the embedded-library model). The writer-lock effect applies to SQLite-backed mounts; on other engines the loop stall remains."
   },
   {
    "kind": "data_state",
    "description": "The target's content and the old string are shaped to miss exactly and reach a quadratic fuzzy path: many lines equal to the first anchor with the last anchor absent, a long differing middle line, or many whitespace-trimmed matches."
   }
  ],
  "execution": {
   "attacker_perspective": "A named agent principal (alice) with ordinary write and edit rights on its own file in a shared AsyncVirtualFileSystem over InMemoryStorage; another principal (bob) reads his own file concurrently.",
   "payloads": [
    "write /a8000.txt content='a\\n'*8000 (16 KB); edit(path='/a8000.txt', old='a\\nx\\nb', new='z')",
    "write /l2000.txt content='a\\n'+'x'*2000+'\\nb\\n'; edit(path='/l2000.txt', old='a\\n'+'y'*2000+'\\nb', new='z')",
    "write /t8000.txt content='a\\n'*8000; edit(path='/t8000.txt', old='  a', new='z')",
    "the M=1000 levenshtein edit applied to K=4 targets through edit(observations=[...])"
   ],
   "instructions": [
    "Run agents/w2d-reindex-edit/scratch/edit_scale.py under tools/sandbox-run.py (no network, empty env, CPU 60 s, wall 120 s, RSS 2 GiB) with .venv/bin/python -I.",
    "For each shape and size n, 2n, 4n, time the public edit verb. Record the longest gap of a 5 ms asyncio ticker and the latency of bob's concurrent read of /bob.txt."
   ],
   "observed_result": "block_anchor L=2000/4000/8000: 71/274/1080 ms (x3.84, x3.94); levenshtein M=500/1000/2000: 42/178/737 ms (x4.22, x4.14); line_trimmed L=2000/4000/8000: 114/440/1679 ms (x3.86, x3.81); K=1/2/4 targets: 176/347/693 ms. Each time, the max event-loop gap and bob's read latency equalled the edit duration (for example 1078 ms gap and 1072 ms read at L=8000). All edits returned vfs.invalid and committed nothing."
  },
  "remediation": {
   "strategy": "Bound the work and move it off the loop. (1) In block_anchor_replacer, precompute the indices of last-anchor lines once and find the next one by bisect, which removes the O(L^2) scan. Compute line start offsets once with a prefix sum and use them in both fuzzy replacers. Cap the context listed in the multi-match error at a few matches. (2) Replace the Python levenshtein with a banded or early-exit version, or a vfs-core kernel, and skip fuzzy similarity when a middle line exceeds a declared length or len(content_lines)*len(find_lines) exceeds a work budget. Refuse with a classified invalid error that names the exact-match requirement. (3) Run edited_entry for the batch through call_offloaded with a deadline, before or outside the writer transaction where the version guard already makes that safe. Regression test: count calls to str.strip or levenshtein cells, never wall time, for the 'a\\n'*L / 'a\\nx\\nb' shape at L and 2L, and assert linear growth.",
   "code_changes": [
    {
     "file_name": "src/vfs/storage/replace.py",
     "fixed_code": "from bisect import bisect_left\n\ndef block_anchor_replacer(content: str, find: str) -> Generator[Match]:\n    content_lines = content.split(\"\\n\")\n    find_lines = _split_dropping_trailing_blank(find)\n    if len(find_lines) < 3:\n        return\n    first_line, last_line = find_lines[0].strip(), find_lines[-1].strip()\n    stripped = [line.strip() for line in content_lines]\n    last_at = [j for j, line in enumerate(stripped) if line == last_line]\n    candidates: list[tuple[int, int]] = []\n    for i, line in enumerate(stripped):\n        if line != first_line:\n            continue\n        k = bisect_left(last_at, i + 2)\n        if k < len(last_at):\n            candidates.append((i, last_at[k]))\n    if len(candidates) > MAX_ANCHOR_CANDIDATES:\n        return\n    ...  # similarity unchanged, but levenshtein refuses lines longer than MAX_FUZZY_LINE_CHARS"
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "Any principal with edit rights on any one file, including its own, can trigger it with a few-KB request. Agents routinely issue edits whose old string misses, and nothing upstream in params.py, base.py or the storage caps old/new length, edit count or target count."
   },
   "impact": {
    "score": "medium",
    "reason": "The stall freezes the shared event loop for every other principal on the host, and on SQLite it holds the mount's writer lock for a time quadratic in input. 16 KB gave about 1 s; extrapolated at the measured 4x per doubling, 64 KB gives about 17 s. The effect is transient (ends when the call ends), leaves no persistent state, and repeats per call."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "high",
   "reason": "The quadratic loops are plain in source. The growth (about 4x per doubling), the loop stall and the blocked read by a different principal were all observed through the public verb at three sizes per shape."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23edit%20%28EditOperation%20old%2Fnew%2C%20replace_all%2C%20many%20targets%29::src%2Fvfs%2Fstorage%2Freplace.py%23fuzzy%20replacers%20run%20inline%20in%20the%20writer%20transaction::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/params.py",
   "src/vfs/storage/editing.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/engine.py",
   "src/vfs/storage/backends/database/dialects.py"
  ],
  "invariant": "edit bounds old/new length, edit count, target count, or replacer time, and runs replacer CPU off the event loop and outside the writer lock",
  "method": "source",
  "result": "params.py:173-180 types edit's old/new/edits/observations with no length or count cap; base.py:1035-1057 only type-checks and routes. backend.py:717-745 gates rights then calls edit_rows inside _execute_write (BEGIN IMMEDIATE on SQLite, backend.py:1666-1673). writes.py:252-261 loops every target and calls edited_entry synchronously in the coroutine (no call_offloaded), continuing past each failed target; editing.py:38 calls apply_edits, which runs replace() per EditOperation. The only content cap is MariaDB's max_allowed_packet value_cap on write, none on SQLite/Postgres.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23edit%20%28EditOperation%20old%2Fnew%2C%20replace_all%2C%20many%20targets%29::src%2Fvfs%2Fstorage%2Freplace.py%23fuzzy%20replacers%20run%20inline%20in%20the%20writer%20transaction::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "src/vfs/storage/replace.py"
  ],
  "invariant": "Each replacer is linear (or bounded) in content and old_string size",
  "method": "source",
  "result": "block_anchor_replacer (179-185): for every line equal to the first anchor it scans forward to the end looking for the last anchor and stops only on a hit, so an absent last anchor makes it O(L^2). calculate_similarity (190-205) runs pure-Python full-matrix levenshtein (61-82), O(M^2) time and memory per middle line, for every candidate. line_trimmed_replacer (137-159) recomputes start_pos with an O(i) sum per match, and replace() (321-325) calls get_line_number and get_context_lines (which splits the whole content) per match, so L matches cost O(L^2). Fuzzy fallback runs whenever the exact search misses (287-291).",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23edit%20%28EditOperation%20old%2Fnew%2C%20replace_all%2C%20many%20targets%29::src%2Fvfs%2Fstorage%2Freplace.py%23fuzzy%20replacers%20run%20inline%20in%20the%20writer%20transaction::src%2Fvfs%2Fstorage::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Computational%20amplification%20attack%20classes",
  "agent_id": "w2d-reindex-edit",
  "reviewed_paths": [
   "src/vfs/storage/replace.py",
   "src/vfs/base.py",
   "src/vfs/storage/backends/database/writes.py"
  ],
  "invariant": "An edit from one principal does not stall other principals' calls on the same host for superlinear time",
  "method": "local",
  "result": "Public AsyncVirtualFileSystem.edit on InMemoryStorage, authority alice on her own file: block_anchor (content 'a\\n'*L, old 'a\\nx\\nb') L=2000/4000/8000 -> 71/274/1080 ms (3.84x, 3.94x); levenshtein (one 3-line candidate, M-char middle) M=500/1000/2000 -> 42/178/737 ms (4.22x, 4.14x) on a 2 KB file; line_trimmed (old '  a') L=2000/4000/8000 -> 114/440/1679 ms (3.86x, 3.81x). The longest event-loop gap equalled the edit time each time, and bob's concurrent read of his own file waited the same span (e.g. 1072 ms at L=8000). Targets multiply it: the M=1000 edit over K=1/2/4 targets -> 176/347/693 ms. Every probe failed (vfs.invalid) and committed nothing, so the cost needs no successful edit.",
  "artifact": "agents/w2d-reindex-edit/artifacts/evidence/edit_scale.txt"
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

- Scratch, the only place you or target code may write: `./agents/v16-p3/scratch/`. Never write `./agents/v16-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v16-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v16-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction` unless you identify a genuinely different root cause.

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
