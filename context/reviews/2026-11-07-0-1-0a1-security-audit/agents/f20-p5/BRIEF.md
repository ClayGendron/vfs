# Final record verifier brief for `f20-p5`

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
 "fingerprint": "vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine",
 "title": "One refused embed batch at the head of the NULL-embedding keyset stops vector indexing for every later writer on the store",
 "description": "Each run of the reindex embed step starts again at chunk id 0. It selects the lowest-id rows that have no embedding, cuts them into batches using the provider's ceil(len/4) token estimate, and ends the whole step at the first page where any batch fails. When the provider refuses a batch deterministically, nothing splits the batch, skips it, or quarantines its rows. Those rows stay NULL and form the same head batch on every later run. The shipped OpenAI adapter meters batches with ceil(len/4) against 5/6 of its declared 300000-token request cap. Text denser than about 3.3 characters per real token, such as CJK, can therefore pass the estimate and still exceed the real cap. A principal with read_write on only its own subtree can write about 4096 small CJK files, about 2 MB in total. After that, no chunk written later by any principal on the same DatabaseStorage gets a vector, however many times reindex runs, and glean's vector leg misses that content. A smaller amount of such text leaves only the neighbouring rows in its batch unembedded, and limits the rest to one page of progress per run. Benign CJK corpora can trigger the same refusal.",
 "root_cause": "_embed_step (backend.py:1416) sets last = 0 on every run (1442). On any outcome.failure it records stopped_by and breaks out of the loop (1466-1468). It does not tell a deterministic refusal apart from a transient one, and it never advances past the failing page. embed_page (embed.py:319-325) keeps the first failure and lands only the batches that answered. _embed_with_retry (embed.py:346-355) retries only when the error carries Retry-After. No code bisects a refused batch, and there is no per-row failed state. So select_unembedded (embed.py:172-182) returns the same rows first on every run. token_batched (embed.py:112-133) meters each row with provider.estimate_tokens. For OpenAIEmbeddingProvider that is ceil(len/4) (openai.py:63-64, provider.py:96), checked against 5/6 of MAX_BATCH_TOKENS=300000 (openai.py:34, embed.py:121). Rows the writer controls can therefore make up a batch whose real token count exceeds the hard cap that the adapter itself declares.",
 "intended_behavior": "Batches should be metered with a bound that cannot undercount real tokens, for example the UTF-8 byte length for byte-level BPE. A batch refused without Retry-After should be bisected down to single rows. A single row that is still refused should be quarantined with a per-row failed state that select_unembedded and count_unembedded skip and that the report counts, as the render stage's _land already does (backend.py:1298-1321). The loop should keep advancing to later pages, so one writer's content cannot stop vector indexing for other principals.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 686,
   "scope": "DatabaseStorage.write",
   "description": "Principal alice, with read_write on /alice only, writes ordinary CJK text files. Beyond the write gate, no rule limits their content, script or length."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/models/chunking.py",
   "line": 217,
   "scope": "recursive_text_split",
   "description": "Reindex chunks each body into rows of at most 2048 characters. Alice's rows get lower chunk ids than any chunk written after them."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1442,
   "scope": "DatabaseStorage._embed_step",
   "description": "Every run starts the keyset at last = 0."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 178,
   "scope": "select_unembedded",
   "description": "The page is the lowest-id live rows whose embedding is NULL, so alice's rows come first on every run."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 125,
   "scope": "token_batched",
   "description": "Each row's cost is provider.estimate_tokens, which is ceil(len/4) for the OpenAI adapter, checked against 250000 (5/6 of 300000). A batch of 2048 rows of 160 CJK characters estimates at 81920 tokens. With about 1 real token per ideograph it is 319488."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 349,
   "scope": "_embed_with_retry",
   "description": "The provider refuses with a 400 that carries no Retry-After. The openai client does not retry a 400, and the error is re-raised without splitting the batch or marking its rows."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 319,
   "scope": "embed_page",
   "description": "gather(return_exceptions=True) keeps the first failure. The refused batch's rows land nothing."
  },
  {
   "kind": "sink",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1466,
   "scope": "DatabaseStorage._embed_step",
   "description": "outcome.failure records stopped_by and breaks the loop, so later pages are never selected. The same rows head the next run, and every chunk written later by any principal stays with a NULL embedding."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1466,
   "description": "A failed batch on any page breaks the whole embed loop (stopped_by at 1467, break at 1468)."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1442,
   "description": "last = 0 on every run, so the refused rows are always selected first again."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1317,
   "description": "The sibling render stage retries row by row and quarantines a refused row as 'failed'. The embed step has nothing equivalent."
  },
  {
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 121,
   "description": "The batch budget is 5/6 of max_batch_tokens, metered by the provider's own estimate."
  },
  {
   "file": "src/vfs/embedding/provider.py",
   "line": 96,
   "description": "estimate_tokens is ceil(len/4), at least 1, whatever the script."
  },
  {
   "file": "src/vfs/embedding/openai.py",
   "line": 34,
   "description": "The shipped adapter declares MAX_BATCH_TOKENS=300000 and meters with the generic estimate_tokens (line 64)."
  },
  {
   "file": "src/vfs/storage/backends/database/embed.py",
   "line": 358,
   "description": "_retry_after_seconds returns None for a 400 without Retry-After, so the refusal is re-raised without a split or a row mark."
  },
  {
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1479,
   "description": "The operator sees only a retryable 'unavailable' warning that names no rows, while reindex reports success=True."
  },
  {
   "file": "agents/v19-p3/artifacts/evidence/run-4096.json",
   "line": 1,
   "description": "Independent repro with the real OpenAIEmbeddingProvider and a real openai.BadRequestError. In both runs both requests were refused ([2048 inputs, 319488 tokens] each). Bob stayed at 1 of 41 chunks embedded, unembedded stayed 4136, success=True, and bob's glean vector leg returned hits=2."
  },
  {
   "file": "agents/v19-p3/artifacts/evidence/run-0.json",
   "line": 1,
   "description": "Control without alice's files: bob was 41 of 41 embedded after run 1, and the vector leg returned hits=42."
  },
  {
   "file": "agents/v19-p3/artifacts/evidence/repro.py",
   "line": 1,
   "description": "Repro harness: no network, the real OpenAI adapter, and a fake client that enforces 300000 tokens per request, counting 1 token per CJK ideograph."
  }
 ],
 "conditions": [
  {
   "kind": "system_configuration",
   "description": "The mount uses an embedder whose hard caps are enforced on real tokens while vfs meters them with ceil(len/4). The shipped OpenAIEmbeddingProvider is the only shipped adapter that declares such caps. LangChain declares none, and the local providers do not refuse."
  },
  {
   "kind": "authorization_role",
   "description": "The writer needs write access to some path on the same DatabaseStorage mount and no other right. The operator runs reindex as usual."
  },
  {
   "kind": "data_state",
   "description": "The token-dense rows must have lower chunk ids than the victims' unembedded rows: written before them, or still unembedded. A full stop needs about 4096 rows, one EMBED_PAGE_ROWS page, with more than about 147 real tokens per row. Fewer rows strand only the rows that share their batch, and limit progress to one page per run."
  },
  {
   "kind": "third_party_dependency",
   "description": "OpenAI's tokenizer must count the text at more than about 1.2 times len/4, and must refuse a request over 300000 tokens deterministically with a 400 and no Retry-After. The repository's adapter docstring declares this cap as documented. The installed openai client (_base_client.py _should_retry) retries only 408, 409, 429 and 5xx, not 400. The real cl100k token density of CJK was not measured locally; the repro used a stand-in counter of 1 token per ideograph."
  }
 ],
 "execution": {
  "attacker_perspective": "An agent or user (alice) with read_write on its own subtree of a shared DatabaseStorage mount that uses the OpenAI embedder. The victims (bob) write content later.",
  "payloads": [
   "4096 files /alice/n/NNNNN.txt, each a distinct 160-character string: a 6-character id prefix followed by CJK ideographs from U+4E00 (estimate 40 tokens; stand-in real count about 154)"
  ],
  "instructions": [
   "Mount DatabaseStorage(url=sqlite+aiosqlite:///<scratch>/r.db, embedder=OpenAIEmbeddingProvider(fake_client, 'text-embedding-3-small', dimensions=256)). The fake client's embeddings.create counts 1 token per CJK ideograph and ceil(rest/4) for other text, and raises openai.BadRequestError with an httpx 400 response and no Retry-After when a request exceeds 300000 tokens.",
   "As system, write /alice/README.txt and /bob/README.txt, grant each principal read_write on its own directory, and run reindex once.",
   "As alice, write the 4096 CJK files. As bob, then write 40 ordinary English files.",
   "Run reindex twice. After each run, count embedded and NULL chunk rows per top-level directory. Then run glean as bob and read legs['vector'].",
   "Control: the same steps with zero alice files."
  ],
  "observed_result": "Attack: in each of the 2 runs the provider got 2 requests, both refused ([2048 inputs, 319488 tokens]). Bob stayed at 1 of 41 chunks embedded and unembedded=4136. reindex returned success=True with one warning, vfs.unavailable retryable=True: 'embedding stopped after 0 requests: BadRequestError: Requested 319488 tokens, max 300000 tokens per request'. Bob's glean vector leg returned hits=2. Control: bob was 41 of 41 embedded after run 1, and the vector leg returned hits=42."
 },
 "remediation": {
  "strategy": "Meter with a bound that cannot undercount, and stop treating a deterministic refusal as a reason to end the run. (1) The OpenAI adapter's estimate_tokens should return the UTF-8 byte length, because byte-level BPE never yields more tokens than bytes. (2) embed_page should bisect a batch refused without Retry-After, and return a single row that is still refused as a per-row failure. (3) Quarantine such rows with a failed marker that select_unembedded and count_unembedded exclude, reset it when the chunk's content_hash changes, and report the count in the embedding extra. (4) _embed_step should break only on transient failures (timeout, 429 or Retry-After, network errors) and otherwise keep advancing last. Regression test: a fake provider that counts 1 token per CJK character and enforces 300000 per request; alice writes 4096 CJK files and bob writes 40; after one reindex, all of bob's chunks are embedded.",
  "code_changes": [
   {
    "file_name": "src/vfs/embedding/openai.py",
    "fixed_code": "    def estimate_tokens(self, text: str) -> int:\n        # byte-level BPE never emits more tokens than UTF-8 bytes: an upper bound the hard caps can trust\n        return max(1, len(text.encode(\"utf-8\")))"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "The attacker needs only ordinary write access to some path and about 2 MB of CJK text. The deployment must use the OpenAI embedder, the only shipped adapter with hard caps. Benign CJK or Cyrillic corpora with default 2048-character chunks also exceed the real cap, so this can happen without any malice."
  },
  "impact": {
   "score": "medium",
   "reason": "The effect is persistent and store-wide, and it crosses principals: no chunk written later gets a vector on any reindex until an operator deletes or rewrites the offending rows or changes the code. glean's vector leg silently misses that content. The lexical leg and all other verbs are unaffected, and nothing is disclosed or lost. The warning names no rows and is marked retryable."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "medium",
  "reason": "The vfs logic (no split, skip or quarantine; break; restart at 0) is visible in source, and I reproduced it independently through the real shipped OpenAI adapter and a real openai.BadRequestError, with caps and page size unscaled. The one external fact, OpenAI's real CJK token density and its 400 on a request over 300000 tokens, rests on the repository's declared caps and public tokenizer behaviour, not on a local measurement."
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

- Scratch, the only place you or target code may write: `./agents/f20-p5/scratch/`. Never write `./agents/f20-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f20-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f20-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
