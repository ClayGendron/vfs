# Final record verifier brief for `f23-p5`

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
 "fingerprint": "vfs:storage/database:search-budget-counts-hidden-rows",
 "title": "grep and glean count rows the caller cannot read toward their budgets, so the warnings and row counts reveal hidden rows and, through the gram index, what they contain",
 "description": "Take a caller with partial rights in DatabaseStorage or InMemoryStorage, such as a named user granted read on one prefix. For that caller, grep and glean work out whether a call hit its candidate or overlay budget from candidate rows that have not yet passed the per-row Visibility check. Hidden rows therefore use up budget slots and then get dropped. That has two visible effects. First, a truncated warning appears or disappears. Second, a matching row the caller can see goes missing from the results. Both change with rows the caller cannot see, even though a direct read of those rows answers not_found. There are three variants, all reproduced at the shipped budgets. (1) grep scan tier, used for unindexed rows or allow_scan: any hidden unindexed row in scope that sorts before the visible rows triggers the 'candidate budget' warning and drops one visible match. (2) grep index tier: whether a hidden indexed row contains the searched literal changes the row count (25,000 vs 24,999) and the warning text. That is a content oracle on rows the caller cannot read. (3) glean overlay: one hidden unindexed row triggers the 'overlay budget' warning and drops one visible hit, at a threshold of only 500 rows.",
 "root_cause": "In grep_rows, the index side caps doc_ids at CANDIDATE_BUDGET and sets nominated_count from the posting kernel (grep.py:243-254). The scan side gets its overflow flag from entries_for_scan, which runs SELECT ... ORDER BY path LIMIT limit+1 with no visibility predicate (scope.py:279-294). The per-row view.holds filter runs only afterwards (grep.py:261, 303; glean.py:380). So hidden rows take budget slots and set the truncation flags (grep.py:254, 269, 299; glean.py:384) before they are thrown away. The rights module says a statement with a LIMIT should carry the visibility pushdown (rights.py:38-39), and that hidden rows should read as absent. entries_for_scan and the nomination kernel do neither.",
 "intended_behavior": "For a caller with partial rights, every grep and glean output (rows, row count, truncation records) should depend only on rows the caller's Visibility admits. A hidden row should affect search output exactly as a row that does not exist. The rights module states this: hidden reads exactly as absent, a road directory reveals nothing beyond the visible rows' own paths, and SQL statements with a LIMIT carry the visibility pushdown.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 495,
   "scope": "DatabaseStorage.grep",
   "description": "A named or anonymous caller with partial rights calls grep. The backend resolves a partial Visibility through _viewed and passes it to grep_rows as view."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 243,
   "scope": "grep_rows",
   "description": "The index tier gets candidate doc ids and nominated_count from the posting kernel over every indexed row in scope, hidden rows included. The ids are capped at CANDIDATE_BUDGET before any visibility check."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 254,
   "scope": "grep_rows",
   "description": "The 'candidate budget' truncation is recorded from nominated_count, which includes hidden rows."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 261,
   "scope": "grep_rows",
   "description": "view.holds drops hidden rows only after they have used candidate slots. remaining (line 269) is then computed from the visible rows that survived."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/scope.py",
   "line": 279,
   "scope": "entries_for_scan",
   "description": "The scan and overlay fetch is SELECT ... ORDER BY path LIMIT limit+1 with no visibility predicate. Hidden rows fill the window, and overflow is set from the unfiltered count (scope.py:281, 294)."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 299,
   "scope": "grep_rows",
   "description": "The scan-side overflow, which includes hidden rows, adds the 'candidate budget' truncation. view.holds at line 303 then removes the hidden rows that displaced visible ones."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 380,
   "scope": "glean_rows",
   "description": "The glean overlay applies view.holds after entries_for_scan(limit=OVERLAY_BUDGET=500). At line 384 it records 'overlay budget' from the overflow flag, which includes hidden rows."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 369,
   "scope": "grep_rows",
   "description": "The truncation records built from those counts, and the shortened row list, are returned to the partial caller as warning errors on the Result."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 185,
   "description": "The grep_rows docstring admits that the candidate budget still counts hidden candidates. The behaviour is known, but it is not treated as a disclosure, and no other layer compensates for it."
  },
  {
   "file": "src/vfs/storage/backends/database/grep.py",
   "line": 120,
   "description": "CANDIDATE_BUDGET is 25,000, the threshold at which grep's index and scan variants flip."
  },
  {
   "file": "src/vfs/storage/backends/database/glean.py",
   "line": 143,
   "description": "OVERLAY_BUDGET is 500, a much lower threshold for the glean variant."
  },
  {
   "file": "src/vfs/storage/backends/database/scope.py",
   "line": 290,
   "description": "The unscoped scan statement orders by path and limits to limit+1 with no visibility pushdown, so hidden rows that sort earlier take the window."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 38,
   "description": "The stated design is that SQL predicates are pushdowns that narrow toward the Visibility wherever a statement's shape needs one, a LIMIT included. entries_for_scan has a LIMIT and no such pushdown."
  },
  {
   "file": "src/vfs/storage/backends/database/rights.py",
   "line": 796,
   "description": "The stated policy is that hidden reads exactly as absent. The search budgets break this for derived search outputs."
  },
  {
   "file": "agents/v24-p3/artifacts/evidence/grep_scan_tier_budget25000.txt",
   "line": 1,
   "description": "Observed at the real budget of 25,000, scan tier. No hidden row: 25,000 rows, no warning. One hidden row, either content: 24,999 rows and a 'candidate budget' truncated warning. Direct read of the hidden row: not_found."
  },
  {
   "file": "agents/v24-p3/artifacts/evidence/grep_index_tier_budget25000.txt",
   "line": 1,
   "description": "Observed at the real budget of 25,000, index tier after reindex. No hidden row, or a hidden row without 'needle': 25,000 rows and the 'overlay not consulted' warning. Hidden row containing 'needle': 24,999 rows and the plain 'candidate budget' warning. This is a content oracle on an unreadable row."
  },
  {
   "file": "agents/v24-p3/artifacts/evidence/glean_overlay_budget500.txt",
   "line": 1,
   "description": "Observed at the real OVERLAY_BUDGET of 500. No hidden row: 500 rows, no warning. One hidden unindexed row: 499 rows and an 'overlay budget' truncated warning."
  },
  {
   "file": "agents/v24-p3/artifacts/evidence/repro_grep.py",
   "line": 1,
   "description": "The grep reproduction script. It sets posture none at /, grants alice read on /pub, and as system writes N visible '/pub' files plus an optional hidden '/aaa-sec/h.txt'. It then compares alice's grep output."
  },
  {
   "file": "agents/v24-p3/artifacts/evidence/repro_glean.py",
   "line": 1,
   "description": "The glean reproduction script, using the same world shape with 500 visible unindexed files."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker is a named, group, or anonymous principal with partial rights: read on some prefixes and no rights on the target prefix. A system caller is not affected."
  },
  {
   "kind": "data_state",
   "description": "The grep variants need about 25,000 visible entries in the call's scope that match the pattern on the index tier, or are unindexed on the scan tier. The glean variant needs 500 visible unindexed entries. The attacker can create these with add or write rights on any prefix in the same mount, or an existing visible corpus can supply them. Globs let the attacker scope the call to its own prefix plus the target prefix."
  },
  {
   "kind": "data_state",
   "description": "Ordering decides which rows are displaced. On the scan tier and the glean overlay, hidden rows must sort by path before the window's visible rows, and the attacker chooses its own path names. On the index tier, the hidden row's doc id must fall inside the first CANDIDATE_BUDGET ids. The scan and overlay variants also need the hidden rows to be unindexed, that is before reindex publishes them."
  }
 ],
 "execution": {
  "attacker_perspective": "Alice holds read only on /pub (root posture none). She is not allowed to learn whether rows exist under /aaa-sec, or what they contain. A direct read of /aaa-sec/h.txt answers not_found.",
  "payloads": [
   "storage.grep(pattern=\"needle\", output_mode=\"files\", allow_scan=True, authority=Authority.of(Principal(\"alice\")))",
   "storage.glean(query=\"lantern\", limit=1000, authority=Authority.of(Principal(\"alice\")))"
  ],
  "instructions": [
   "Create an InMemoryStorage and call first_touch. As Authority.system(), set posture('/', 'none') and grant alice 'read' on /pub.",
   "As system, optionally write a hidden /aaa-sec/h.txt, in one world containing 'needle secret' and in another 'other text'. Then write 25,000 visible /pub/vNNNNNN.txt files containing 'needle visible'. For the index tier, call reindex().",
   "As alice, call grep(pattern='needle', output_mode='files', allow_scan=True). Record the row count and the truncated warnings. Confirm that read('/aaa-sec/h.txt') as alice returns not_found.",
   "For glean, write 500 visible unindexed /pub files containing 'lantern', with and without one hidden /aaa-sec row. Call glean(query='lantern') as alice and compare.",
   "Run everything under tools/sandbox-run.py with the repo .venv python -I. The scripts are agents/v24-p3/artifacts/evidence/repro_grep.py (args: 25000 scan, or 25000 index none|without|with) and repro_glean.py."
  ],
  "observed_result": "All runs used the unpatched shipped budgets. Scan tier: 25,000 rows and no warning without a hidden row; 24,999 rows and a 'candidate budget' truncated warning with one hidden row of any content. Index tier: 25,000 rows and the 'overlay not consulted' warning when no hidden row matches; 24,999 rows and the plain 'candidate budget' warning when the hidden row contains 'needle'. Glean: 500 rows and no warning, against 499 rows and an 'overlay budget' warning when one hidden row is present. In every world, alice's direct read of the hidden row answered not_found."
 },
 "remediation": {
  "strategy": "Apply the caller's Visibility before counting anything toward a budget. In entries_for_scan, add the visibility_clauses / visible_entries pushdown to the WHERE clause, so LIMIT limit+1 and overflow count only rows the caller may see. Thread view into entries_for_scan from grep_rows and glean_rows. On the index tier, restrict the allow-list or the kernel's candidate ids to visible entries before the CANDIDATE_BUDGET cap and the nominated_count comparison. This could be done by computing allow_list_ids under the view pushdown, or by filtering doc ids through the view before capping. Replace the grep_rows docstring note that the budget counts hidden candidates with a regression test. The test should assert that grep and glean output (rows and truncation records) is identical for a partial caller whether or not hidden rows are present, both just below and at each budget.",
  "code_changes": []
 },
 "severity": {
  "likelihood": {
   "score": "low",
   "reason": "The attacker needs partial rights plus about 25,000 matching or unindexed visible entries in scope for grep, or 500 unindexed entries for glean. Typically that means add rights to create padding. Ordering conditions also apply. Each query yields about one bit."
  },
  "impact": {
   "score": "low",
   "reason": "This is a one-bit-per-query oracle across the row-rights boundary. It reveals whether hidden rows exist in a scope, and on the index tier whether a hidden row contains the searched grams, which can be repeated to probe content. It also silently drops visible matches. It does not read hidden bodies or paths directly."
  },
  "overall_severity": "low"
 },
 "confidence": {
  "score": "high",
  "reason": "The path is fully visible in the source, including the docstring that admits the behaviour. All three variants were reproduced locally under the sandbox at the shipped CANDIDATE_BUDGET of 25,000 and OVERLAY_BUDGET of 500, with a not_found direct-read control on the same row."
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

- Scratch, the only place you or target code may write: `./agents/f23-p5/scratch/`. Never write `./agents/f23-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f23-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f23-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs:storage/database:search-budget-counts-hidden-rows"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
