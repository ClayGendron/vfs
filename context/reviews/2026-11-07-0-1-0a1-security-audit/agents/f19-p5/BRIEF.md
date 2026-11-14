# Final record verifier brief for `f19-p5`

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
 "fingerprint": "vfs:storage/backends/database/signals.py:collect_graph:centrality-prior-counts-hidden-edges",
 "title": "glean's link-centrality prior is built from hidden rows, so a partial caller's visible scores reveal hidden in-links",
 "description": "When an operator declares a link signal (InDegree, PageRank or Katz) on a DatabaseStorage Ranker, reindex computes one prior over the whole corpus. It counts every live entry and every non-fs edge, including edges authored on rows and markdown links extracted from bodies the eventual reader cannot see. At query time glean multiplies each visible candidate's fused score by the stored factor whatever the caller's view, then min-max scales. A partial caller (a named principal without whole-mount read, or anonymous) therefore gets glean scores that differ between two worlds that differ only in hidden rows. With a visible calibrator file of known in-degree, the caller can tell whether, and roughly how many, hidden entries reference a visible file, while graph inbound, glob and read on the same data correctly reveal nothing. The same path lets a writer use files only they can see as an invisible link farm that raises a readable target in every other principal's ranking.",
 "root_cause": "signals.collect_graph (src/vfs/storage/backends/database/signals.py:72-118) takes no authority or Visibility and pages every live entry and every non-reserved edge. DatabaseStorage._signal_phase calls it once per reindex (backend.py:1332) and the Rust centrality kernel (models/signals.py:28-61) scores over that whole graph, smooths through directories and min-max scales over all files. signal_factors (signals.py:194-263) takes no view, and glean_rows applies its factors to every candidate after both visibility-filtered legs (glean.py:390-392). The visible-set treatment glean gives N, mean length and df is never applied to the signal leg.",
 "intended_behavior": "glean_rows' own docstring states that under a partial view the statistics are the visible set's, 'so a hidden row never moves a visible score' (glean.py:249-251). The permission-ladder research says degree counts and stored link signals must count only edges whose both endpoints the caller can list (context/research/2026-10-14-the-permission-ladder-list-and-contribute.md:98). The statistics-under-permissions memo names this exact leak and asks for visible-set treatment or a documented exemption (context/research/2026-09-28-search-statistics-under-permissions-precedent.md:349). Spec 136, which landed the signals, has no exemption. The earlier-generation archived spec 009 invariant 6 also says centrality must be computed over the visible subgraph only.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/base.py",
   "line": 1469,
   "scope": "AsyncVirtualFileSystem.glean",
   "description": "A partial or anonymous caller issues glean(query, globs=..., authority=...). The router routes the call to the mount with that authority, and the storage resolves it to a partial Visibility."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1332,
   "scope": "DatabaseStorage._signal_phase",
   "description": "Earlier, reindex collected the graph once with no authority or view, then computed and published each declared signal."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/signals.py",
   "line": 105,
   "scope": "collect_graph",
   "description": "Every non-fs edge between live entries is collected, including edges from rows hidden from the eventual reader and links extracted from hidden markdown bodies."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/models/signals.py",
   "line": 46,
   "scope": "centrality_prior",
   "description": "The Rust kernel computes the measure over the full graph, applies hierarchy smoothing that includes hidden files, and min-max scales over all files."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/signals.py",
   "line": 263,
   "scope": "signal_factors",
   "description": "Stored values for the candidates become 1 + beta*t(v) multipliers. The function has no view parameter."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 392,
   "scope": "glean_rows",
   "description": "Each visible entry's fused score is multiplied by the factor that hidden rows influenced, then ordered, min-max scaled and returned to the partial caller as Observation.score."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 251,
   "description": "The docstring promises that under a partial view 'a hidden row never moves a visible score'."
  },
  {
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 390,
   "description": "signal_factors is called with no view, after both legs and the overlay have filtered rows through the view."
  },
  {
   "file": "src/vfs/storage/backends/database/signals.py",
   "line": 72,
   "description": "collect_graph has no authority or view parameter. It pages every live entry and every non-reserved edge."
  },
  {
   "file": "src/vfs/storage/backends/database/graph.py",
   "line": 307,
   "description": "The comparable control the signal leg lacks: graph hops keep a row only if view.holds(mapping, 'list'), so hidden in-links are left out of graph inbound."
  },
  {
   "file": "context/research/2026-10-14-the-permission-ladder-list-and-contribute.md",
   "line": 98,
   "description": "Stated rule: degree counts and stored link signals must count only edges with both endpoints at list or above for the caller."
  },
  {
   "file": "context/research/2026-09-28-search-statistics-under-permissions-precedent.md",
   "line": 349,
   "description": "Names the leak ('A visible file's centrality can reveal hidden in-links') and requires visible-set treatment or a documented exemption. Neither exists."
  },
  {
   "file": "src/vfs/storage/ranking.py",
   "line": 385,
   "description": "The default Ranker declares no signals, so the leak needs an operator to opt in to a link signal."
  },
  {
   "file": "agents/v22-p3/artifacts/evidence/visible_prior_two_worlds.json",
   "line": 1,
   "description": "Verifier's own sandboxed run. bob's and anonymous's glean scores change with k hidden alice edges or hidden markdown links. The no-signal control is unchanged by k. graph, glob and read reveal nothing about /alice."
  }
 ],
 "conditions": [
  {
   "kind": "system_configuration",
   "description": "The operator declares a link signal (InDegree, PageRank or Katz, for example Signal('centrality', weight=0.5)) on the DatabaseStorage Ranker. The default Ranker declares none."
  },
  {
   "kind": "data_state",
   "description": "reindex has run since the hidden edges or hidden link-bearing bodies were written. Hidden rows reference a visible file. The caller can read that file and, for counting, a calibrator file with a known visible in-degree that matches the same query."
  },
  {
   "kind": "authorization_role",
   "description": "The reader is any named or anonymous principal without whole-mount read (a partial Visibility). For the steering variant, the writer needs modify on their own hidden files and read on the target, which is what mkedge requires."
  }
 ],
 "execution": {
  "attacker_perspective": "bob, or anonymous, can read /pub but not /alice. Comparing glean scores, he learns whether, and roughly how many, of alice's private files reference /pub/a.md. Separately, alice can raise /pub/a.md in everyone's ranking through links from files only she can see.",
  "payloads": [
   "DatabaseStorage(url='sqlite+aiosqlite:///<scratch>.db', ranker=Ranker(signals=(Signal('centrality', weight=0.5),)))",
   "system writes /pub/a.md 'zebra report alpha', /pub/b.md 'zebra report gamma', /pub/c.md 'zebra report delta with many more filler words here', /alice/n0..n4.md; posture / none; posture /pub read; grant alice read_write on /alice; mkedge /pub/c.md -> /pub/b.md (visible calibrator)",
   "edge variant: alice mkedge /alice/n{i}.md -> /pub/a.md for i < k; markdown variant: /alice/n{i}.md bodies contain '[x](/pub/a.md)' for i < k, no mkedge",
   "storage.reindex(); kernel.add_mount(storage, '/kb'); kernel.glean('zebra', globs=('/kb/pub/**',), authority=Authority.of(Principal('bob')))"
  ],
  "instructions": [
   "Ran agents/v22-p3/scratch/verify_prior.py under tools/sandbox-run.py (no network, empty env, scratch-only writes, CPU 60 s, wall 120 s, RSS 2 GiB) with ./.venv/bin/python -I. SQLite files in scratch only.",
   "For k in {0,1,3}, in both the edge and markdown variants, recorded bob's and anonymous's glean scores, legs.signals, graph inbound on /kb/pub/a.md, glob /kb/alice/**, and read /kb/alice/n0.md. As a control, ran the edge variant with k=0 and k=3 using a default Ranker with no signals."
  ],
  "observed_result": "bob and anonymous get identical scores. a.md/b.md: k=0 0.6875/1.0; k=1 1.0/1.0; k=3 1.0/0.848484848. The markdown-body variant gives exactly the same values. With no signal declared, scores are 1.0/1.0 for both k=0 and k=3, which isolates the change to the signal leg. In every world, bob's and anonymous's graph inbound on a.md lists no /alice row, glob /kb/alice/** is empty, and read /kb/alice/n0.md fails. legs.signals reports centrality applied."
 },
 "remediation": {
  "strategy": "Never apply a whole-corpus prior to a partial caller. Smallest fix: in glean_rows, call signal_factors only when view is None. Under a partial view, skip the signal leg and emit a fixed explain that looks the same whether or not any edges exist, so 'applied' and 'no entry earned a value' stop leaking. The fuller design computes or stores priors per visibility class, for example over the rows everyone may read, or computes a visible-subgraph prior at query time, counting only edges whose both endpoints the caller can list. Regression test: two worlds that differ only in hidden edges or hidden link-bearing bodies must give a partial caller byte-identical glean observations and legs.signals.",
  "code_changes": [
   {
    "file_name": "src/vfs/storage/backends/database/glean.py",
    "fixed_code": "    fused = _fuse(ranker, hits, vector_hits)\n    if view is None:\n        signals = await signal_factors(session, tables, profile, membership_budget, ranker, list(fused.entries))\n    else:\n        # Stored priors count every row; a partial caller's scores must not carry them.\n        signals = SignalFactors({}, [], {signal.name: {\"applied\": False, \"reason\": \"partial view\"} for signal in ranker.signals})\n    for entry_id, factor in signals.factors.items():\n        fused.entries[entry_id] *= factor"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "low",
   "reason": "An operator must opt in to a link signal on the Ranker (the default declares none), and reindex must run after the hidden links exist. Once both hold, any partial or anonymous reader can query repeatedly with no special rights."
  },
  "impact": {
   "score": "low",
   "reason": "It discloses link metadata of hidden rows: whether, and roughly how many, hidden entries reference a visible file, including references extracted from hidden bodies. It does not disclose bodies or paths. It also allows invisible ranking manipulation, but only of documents the victim can already read."
  },
  "overall_severity": "low"
 },
 "confidence": {
  "score": "high",
  "reason": "Every source step was verified, and no visibility parameter exists anywhere on the signal path. The code's own docstring and the project's permission research state the opposite policy. An independent sandboxed two-world run shows partial callers' scores moving with hidden edges and hidden markdown links, while a no-signal control is unchanged and graph, glob and read reveal nothing."
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

- Scratch, the only place you or target code may write: `./agents/f19-p5/scratch/`. Never write `./agents/f19-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f19-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f19-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs:storage/backends/database/signals.py:collect_graph:centrality-prior-counts-hidden-edges"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
