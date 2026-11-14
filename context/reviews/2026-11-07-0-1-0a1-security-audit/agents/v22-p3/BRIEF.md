# Candidate verifier brief for `v22-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w2b-derived. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs:storage/backends/database/signals.py:collect_graph:centrality-prior-counts-hidden-edges",
  "title": "glean's centrality prior is built from hidden rows, so a visible score reveals how many hidden entries link to it",
  "description": "The link-centrality signal is computed at reindex over the whole corpus: every live entry, every reference edge, the hierarchy smoothing, and min-max over all files. It ignores the caller's view. At query time glean multiplies each visible candidate's fused score by the stored factor. Any partial caller, anonymous included, can therefore compare a visible file's score against a calibrator with a known visible in-degree, and read back whether, and how many, hidden entries reference that file. The same holds for references extracted from hidden markdown bodies. graph inbound on the same file correctly shows no such edges, so the two verbs disagree. The same path also lets a writer use rows only they can see as a link farm, invisibly steering every other principal's ranking of a target they can read.",
  "root_cause": "signals.collect_graph (signals.py:72-118) and the kernel (models/signals.py:28, signals.rs:71) build one corpus-wide prior with no Visibility. glean_rows applies signal_factors to every candidate whatever the caller's view (glean.py:390-392). The visible-set treatment that glean gives N, avg_dl and df (_visible_lexicon) is never applied to the signal leg.",
  "intended_behavior": "Under a partial view, a hidden row never moves a visible score (glean.py:249-251, the ADR 065 rule 5 visible-set rule). Degree counts and stored link signals are read-class and should count only edges whose endpoints the caller may see (context/research/2026-10-14-the-permission-ladder-list-and-contribute.md:98). Archived spec 009 invariant 6 states this outright: centrality and pagerank must be computed over the visible subgraph only. The prior research names this exact leak and asks for the visible-set treatment or a documented exemption (2026-09-28-search-statistics-under-permissions-precedent.md:349). No exemption exists in any spec.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 1469,
    "scope": "AsyncVirtualFileSystem.glean",
    "description": "A partial or anonymous caller issues glean(query, authority=...); the router fans out with that authority."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1332,
    "scope": "DatabaseStorage.reindex signal phase",
    "description": "Reindex collects the graph once, with no authority or view, and computes and publishes each declared signal."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/signals.py",
    "line": 105,
    "scope": "collect_graph",
    "description": "Every non-fs edge between live entries is collected, including edges from rows hidden from the eventual reader."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/models/signals.py",
    "line": 46,
    "scope": "centrality_prior",
    "description": "The Rust kernel computes the measure, smooths through directory means that include hidden files, and min-max scales over all files."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/signals.py",
    "line": 263,
    "scope": "signal_factors",
    "description": "Stored values for visible candidates become 1+beta*t(v) multipliers. There is no view parameter."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/glean.py",
    "line": 392,
    "scope": "glean_rows",
    "description": "Each visible entry's fused score is multiplied by the hidden-influenced factor, min-max scaled (glean.py:393, 984-987) and returned as Observation.score."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/glean.py",
    "line": 251,
    "description": "The docstring promises 'a hidden row never moves a visible score' under a partial view."
   },
   {
    "file": "src/vfs/storage/backends/database/glean.py",
    "line": 390,
    "description": "signal_factors is called with no view, after both visibility-filtered legs."
   },
   {
    "file": "src/vfs/storage/backends/database/signals.py",
    "line": 72,
    "scope_note": null,
    "description": "collect_graph has no authority or view parameter and pages every live entry and edge."
   },
   {
    "file": "src/vfs/storage/backends/database/graph.py",
    "line": 307,
    "description": "The control that graph applies, and that the signal leg lacks: an edge's far endpoint must pass holds(list), so hidden in-links are omitted from graph inbound."
   },
   {
    "file": "context/specifications/archive/009-cloud-style-sharing-and-access-control/spec.md",
    "line": 254,
    "description": "Stated policy: centrality and pagerank are computed over the visible subgraph only, and no aggregate over hidden nodes leaks into visible-node scores."
   },
   {
    "file": "context/research/2026-09-28-search-statistics-under-permissions-precedent.md",
    "line": 349,
    "description": "Names this leak ('A visible file's centrality can reveal hidden in-links') and requires visible-set treatment or a documented exemption. None exists."
   }
  ],
  "conditions": [
   {
    "kind": "system_configuration",
    "description": "The operator declares a link signal (InDegree, PageRank or Katz) on the mount's Ranker. The default Ranker declares none (ranking.py:385-391)."
   },
   {
    "kind": "data_state",
    "description": "reindex has run since the hidden edges or hidden markdown links were written. Some hidden rows reference a visible file, and the caller can read at least one calibrator file with a known visible in-degree that matches the same query."
   },
   {
    "kind": "authorization_role",
    "description": "The reader is any named or anonymous principal without whole-mount read. For the steering variant, the writer needs only modify on their own files and read on the target."
   }
  ],
  "execution": {
   "attacker_perspective": "bob (or anonymous), who can read /pub but not /alice, learns how many of alice's private files reference /pub/a.md by comparing glean scores. alice, as writer, can raise /pub/a.md for everyone through links from files only she can see.",
   "payloads": [
    "DatabaseStorage(url='sqlite+aiosqlite:///w.db', ranker=Ranker(signals=(Signal('centrality', weight=0.5),)))",
    "system writes /pub/a.md 'zebra report alpha', /pub/b.md 'zebra report gamma', /pub/c.md 'zebra report delta with many more filler words so the body is longer', /alice/n0..n4.md; posture / none, /pub read; grant alice read_write on /alice; mkedge /pub/c.md -> /pub/b.md (visible calibrator)",
    "alice: mkedge [/alice/n{i}.md -> /pub/a.md for i < k]  (or: hidden bodies containing '[ann](/pub/a.md)')",
    "storage.reindex(); kernel.add_mount(storage, '/kb'); kernel.glean('zebra', globs=('/kb/pub/**',), authority=Authority.of(Principal('bob')))"
   ],
   "instructions": [
    "Ran scratch/centrality_oracle.py (and scratch/markdown_variant.py <k>) under tools/sandbox-run.py: no network, empty env, scratch-only writes, CPU 60 s, wall 120 s, RSS 2 GiB. Interpreter: .venv/bin/python -I. SQLite files only.",
    "For k in {0,1,2,5} hidden links, recorded bob's and anonymous's glean scores, bob's graph inbound on a.md and b.md, bob's glob of /kb/alice/**, and the system glean scores."
   ],
   "observed_result": "bob, anonymous and system get the same scores. a.md/b.md: k=0 0.6875/1.0; k=1 1.0/1.0; k=2 1.0/0.889041006; k=5 1.0/0.812914902. b.md's score falls strictly as k rises, so bob can read off whether a.md's hidden in-degree is below, equal to or above b.md's one visible in-link, and its size. The hidden-markdown-body variant gives the same values for k=0,2,5. bob's graph inbound on a.md shows no edges, and bob's glob of /kb/alice/** is empty."
  },
  "remediation": {
   "strategy": "Never apply a whole-corpus prior to a partial caller. Smallest fix: in glean_rows, apply signal_factors only when view is None. Under a partial view, skip the signal leg and add a fixed info record with a constant explain that is the same whether any edges exist, so applied/'no entry earned a value' stops leaking. The fuller design stores per-visibility-class priors, for example one computed over the rows everyone may read for anonymous and posture-only callers, or computes a visible-subgraph prior at query time. Regression test: two worlds that differ only in hidden edges or hidden link-bearing bodies must give a partial caller byte-identical glean observations and legs.signals.",
   "code_changes": [
    {
     "file_name": "src/vfs/storage/backends/database/glean.py",
     "fixed_code": "    fused = _fuse(ranker, hits, vector_hits)\n    if view is None:\n        signals = await signal_factors(session, tables, profile, membership_budget, ranker, list(fused.entries))\n    else:\n        # The stored priors count every row; a partial caller's scores must not carry them.\n        signals = SignalFactors({}, [], {signal.name: {\"applied\": False, \"reason\": \"partial view\"} for signal in ranker.signals})\n    for entry_id, factor in signals.factors.items():\n        fused.entries[entry_id] *= factor"
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "low",
    "reason": "Requires an operator to opt in to a link signal on the Ranker, and a reindex after the hidden links exist. Once that holds, any reader, including anonymous, can query it repeatedly with no special rights."
   },
   "impact": {
    "score": "low",
    "reason": "Discloses link metadata of hidden rows (existence and count of hidden entries referencing a visible file, including references extracted from hidden bodies), not their bodies. It also allows invisible ranking manipulation, but only of documents the victim may already read."
   },
   "overall_severity": "low"
  },
  "confidence": {
   "score": "high",
   "reason": "Complete source lineage with no visibility parameter anywhere on the path, a stated contrary policy in code and specs, and a bounded local run that shows a visible score changing monotonically with the hidden link count while graph hides those edges."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fsignals.py%23centrality%20prior%20applied%20to%20glean%20scores::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fglean.py%23signal_factors%20over%20a%20whole-corpus%20graph%2C%20with%20no%20Visibility%20filter::src%2Fvfs%2Fstorage::AI-AND-LLM.md%23Context%2C%20retrieval%2C%20and%20memory%20attack%20classes",
  "agent_id": "w2b-derived",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/signals.py",
   "src/vfs/models/signals.py",
   "crates/vfs-core/src/signals.rs",
   "src/vfs/storage/backends/database/glean.py",
   "src/vfs/storage/backends/database/backend.py"
  ],
  "invariant": "a partial caller's glean scores are not moved by rows it cannot see (glean.py:249-251, 'a hidden row never moves a visible score')",
  "method": "source",
  "result": "Violated. collect_graph reads every live entry and every non-fs edge, with no Visibility (signals.py:72-118). reindex runs it once per mount (backend.py:1332-1338). The kernel counts in-degree, PageRank or Katz over that whole graph, smooths through directory means that include hidden files, and min-max scales over all files (models/signals.py:28-61, signals.rs:71, 251-252). glean then multiplies every visible candidate's fused score by the stored factor (glean.py:390-392) before the final min-max (glean.py:393, 984-987). signal_factors takes no view at all (signals.py:194-263). Its explain also reports applied/'no entry earned a value' from the corpus-wide row_count.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fsignals.py%23centrality%20prior%20applied%20to%20glean%20scores::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fglean.py%23signal_factors%20over%20a%20whole-corpus%20graph%2C%20with%20no%20Visibility%20filter::src%2Fvfs%2Fstorage::AI-AND-LLM.md%23Context%2C%20retrieval%2C%20and%20memory%20attack%20classes",
  "agent_id": "w2b-derived",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/signals.py",
   "src/vfs/storage/backends/database/glean.py"
  ],
  "invariant": "a visible entry's glean score for bob/anonymous is the same whether or not hidden rows link to it",
  "method": "local",
  "result": "Violated. Each world has three visible /pub files and one visible edge c->b, and differs only in k hidden alice files with mkedge'd edges to /pub/a.md. bob's (and anonymous's) glean('zebra', globs=/kb/pub/**) gives a/b: k=0 0.6875/1.0, k=1 1.0/1.0, k=2 1.0/0.889041006, k=5 1.0/0.812914902. These are identical to the system answer. In every world bob's graph inbound on a.md shows no edge and his glob of /kb/alice/** is empty.",
  "artifact": "agents/w2b-derived/artifacts/evidence/centrality_oracle.json"
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fsignals.py%23centrality%20prior%20applied%20to%20glean%20scores::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fglean.py%23signal_factors%20over%20a%20whole-corpus%20graph%2C%20with%20no%20Visibility%20filter::src%2Fvfs%2Fstorage::AI-AND-LLM.md%23Context%2C%20retrieval%2C%20and%20memory%20attack%20classes",
  "agent_id": "w2b-derived",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/signals.py"
  ],
  "invariant": "hidden bodies (markdown links extracted at write/reindex) do not move visible scores",
  "method": "local",
  "result": "Violated. With no mkedge for the hidden files, writing k hidden /alice files whose body contains '[ann](/pub/a.md)' gives bob a/b = 0.6875/1.0 (k=0), 1.0/0.889041006 (k=2), 1.0/0.812914902 (k=5). So a hidden body's content (that it references a.md) can be read back through a visible score.",
  "artifact": "agents/w2b-derived/artifacts/evidence/centrality_markdown_links.json"
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fsignals.py%23centrality%20prior%20applied%20to%20glean%20scores::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fglean.py%23signal_factors%20over%20a%20whole-corpus%20graph%2C%20with%20no%20Visibility%20filter::src%2Fvfs%2Fstorage::AI-AND-LLM.md%23Context%2C%20retrieval%2C%20and%20memory%20attack%20classes",
  "agent_id": "w2b-derived",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/ranking.py"
  ],
  "invariant": "writer steering of other principals' rankings is limited to rows the victim can see",
  "method": "source",
  "result": "mkedge requires only modify on the source and read on the target (backend.py:924-952). So a writer can mint any number of edges from files only they can see into any target they can read. After the next reindex this raises the target's prior for every principal, and the victim can neither see nor audit the cause through graph, ls or glob. Steering through visible edges is the designed PageRank behaviour. Steering through hidden rows is the same root cause as the oracle. The prior is opt-in: the default Ranker declares no signals (ranking.py:385-391), so this needs the operator to declare a link signal.",
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

### AI-AND-LLM.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name the crossed boundary and observable result: attacker, affected principal or shared resource, execution identity, target, and unauthorized or unrequested action or disclosure.
2. For confused-deputy authority claims, prove the tool lacks requester-and-resource authorization and that the attacker cannot perform the same action normally. For action-binding claims, instead prove attacker-controlled content caused an action under the affected principal's authority that the principal did not intentionally request or approve. Valid generic authorization does not establish that intent.
3. For memory or retrieval claims, cite both the attacker-controlled write and the later cross-principal read or privileged decision. A shared record without a reachable consumer is not enough.
4. For action binding, establish the intentional request or normalized approved object, if any, and compare it with the object the handler uses. Confirm a locally observable unrequested action, mutation, duplicate, or authority change without extending the test into harmful execution. For schema disagreement, compare the normalized validated object with the handler's object.
5. For MCP identity claims, verify the authenticated connection, request correlation, tool namespace, and effective credential. Mark `needs_validation` if external server identity or deployment routing is required.
6. Return `confirmed` findings only with a complete source trace and meaningful result. Return `needs_validation` for a specific unresolved boundary fact and state the bounded local or owner-observed check needed to resolve it.

### DATA-ISOLATION-AND-LIFECYCLE.md#Validation rules

## Validation rules (apply before reporting ANY finding here)

1. Name attacker or lower-trust principal, protected data/state, affected owner/tenant, alternate copy or operation, and unauthorized disclosure or mutation.
2. Cite both intended source-of-truth policy and the path that omits or disagrees with it. Confirm another layer does not enforce the same tenant/lifecycle condition.
3. Use local dummy tenants and non-sensitive fixtures to prove cross-scope access or stale lifecycle behavior. Stop at the minimum observable record or operation.
4. If external cache, object storage, replicas, analytics, backup, or retention policy is required, classify `needs_validation` and state the owner-observed check.
5. Return `confirmed` only with complete lineage and concrete boundary impact. Return `needs_validation` with the exact unresolved storage, ACL, invalidation, retention, or restore fact.

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

- Scratch, the only place you or target code may write: `./agents/v22-p3/scratch/`. Never write `./agents/v22-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v22-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v22-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs:storage/backends/database/signals.py:collect_graph:centrality-prior-counts-hidden-edges` unless you identify a genuinely different root cause.

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
