# Final record verifier brief for `f10-p5`

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
 "fingerprint": "vfs.rendering:ooxml-part-decompression-unbounded",
 "title": "OOXML parts are fully decompressed into host memory before any render limit applies, so a small docx can cost hundreds of times its size in RSS during reindex",
 "description": "The docx and pptx renderers pass the stored bytes straight to docx.Document and pptx.Presentation. vfs checks no zip entry sizes, compression ratios or member counts first. When python-docx 1.2.0 opens a package, it walks every internal relationship and calls ZipFile.read on each target part. python-pptx 1.0.2 goes further and reads every zip member, referenced or not, into a dict. Every RenderLimits check runs inside Builder, on output characters, after this expansion has already happened. The RENDER_RATIO comment calls the ratio the decompression-bomb guard, but a part that decompresses large and yields no text never reaches it. Rendering runs on the DatabaseStorage offload ThreadPoolExecutor, which is inside the host process all agents share. I reproduced this locally. One docx stored at 442,096 bytes, holding one relationship-referenced 400 MiB part of zeros, raised peak RSS by 805 MiB in a direct registry render and by 807 MiB in a real write-then-reindex on SQLite. That is about 1,900 times the stored size. The render still returned status ok with text 'hello quokka', and no limit fired. Because deflate tops out near 1000:1 and the library holds the blob, a stored body of a few MiB can be enough to exhaust the host's memory.",
 "root_cause": "DocxRenderer.render (docx.py:50) and PptxRenderer.render (pptx.py:38) open caller-supplied zip containers with libraries that eagerly decompress part blobs (docx/opc/pkgreader.py:79 via phys_pkg.py:83 ZipFile.read; pptx/opc/serialized.py:195 reads every member). vfs does no central-directory inspection before that call. Every RenderLimits check (chars, ratio, units, seconds) lives in Builder, which measures emitted text after expansion, so input-side decompression has no bound at all.",
 "intended_behavior": "A render's memory should be bounded by declared limits relative to the stored input, as the seam's 'decompression-bomb guard' comment says. An OOXML body whose declared total uncompressed size, single-entry size, member count or compression ratio exceeds a RenderLimits cap should be refused as a classified 'failed' or 'corrupt' state before the parsing library decompresses anything.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1287,
   "scope": "DatabaseStorage._render_step",
   "description": "During reindex, each dirty bytes row that any writer stored through write(data=...) gets rendered. render_rows runs on the shared offload ThreadPoolExecutor via call_offloaded at line 1288, inside the host process."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/models/media.py",
   "line": 89,
   "scope": "sniff_mime",
   "description": "The PK\\x03\\x04 magic marks the body as a zip, and the .docx/.pptx extension or the declared type then selects the Office media type and its renderer (lines 104-108)."
  },
  {
   "kind": "sink",
   "file": "src/vfs/rendering/docx.py",
   "line": 50,
   "scope": "DocxRenderer.render",
   "description": "docx.Document(BytesIO(source.data)) runs with no prior zip inspection. python-docx reads every relationship-referenced part fully into memory. pptx.py:38 has the same shape, and python-pptx reads every member."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/rendering/seam.py",
   "line": 43,
   "description": "The comment calls RENDER_RATIO 'the decompression-bomb guard', but every RenderLimits field bounds output or the walk, never decompressed input."
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 287,
   "description": "The ratio check compares emitted characters (self._chars) with ratio * input_bytes after parsing. A large part that yields no text is invisible to it."
  },
  {
   "file": "src/vfs/rendering/pptx.py",
   "line": 38,
   "description": "pptx.Presentation(BytesIO(source.data)) has no prior inspection. The installed python-pptx 1.0.2 _ZipPkgReader._blobs (pptx/opc/serialized.py:192-195) reads every zip member into a dict, including unreferenced ones. This is source-read only; I did not run the pptx path."
  },
  {
   "file": "src/vfs/storage/backends/database/engine.py",
   "line": 227,
   "description": "offload_executor is a ThreadPoolExecutor, so the decompressed blobs are allocated in the shared host process, not in an isolated worker."
  },
  {
   "file": "agents/v11-p3/artifacts/evidence/ooxml-part-bomb-rss.txt",
   "line": 1,
   "description": "Sandboxed reproduction log and scripts. A 442,096-byte docx with one 400 MiB referenced part grew max RSS by 805 MiB in a registry render and by 807 MiB in a DatabaseStorage write-then-reindex; render_status stayed ok. The 34,419-byte control docx grew it by 5 MiB."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker is any principal allowed to write a bytes body into a DatabaseStorage-backed mount (for example a named agent subject with write rights). The cost is not paid in the writer's call."
  },
  {
   "kind": "system_configuration",
   "description": "The vfs[docx] or vfs[pptx] extra is installed, so a bundled Office renderer is available. The operator or host runs DatabaseStorage.reindex(), which is routine index maintenance."
  },
  {
   "kind": "data_state",
   "description": "The stored body starts with PK\\x03\\x04 and carries an Office extension or declared type, so sniff_mime selects DOCX or PPTX. For docx, the large part must be a relationship target; for pptx, any zip member works."
  },
  {
   "kind": "third_party_dependency",
   "description": "This depends on how python-docx 1.2.0 and python-pptx 1.0.2 load parts, which is eager and unbounded. I observed this for python-docx only. For python-pptx it comes from reading the source. openpyxl (read_only=True) was not shown to be affected."
  }
 ],
 "execution": {
  "attacker_perspective": "A lower-trust writer stores one small docx. Inside it is a highly compressible part that the main document's relationships point to. Later, the operator's reindex renders it inside the host process that every agent shares.",
  "payloads": [
   "docx built from tests.support.documents.docx_bytes(['hello quokka']), plus [Content_Types].xml <Default Extension=\"bin\" ContentType=\"application/octet-stream\"/>, plus a word/_rels/document.xml.rels <Relationship Id=\"rIdBig\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"media/big.bin\"/>, plus word/media/big.bin = 400 MiB of 0x00, deflate level 9; stored size 442,096 bytes"
  ],
  "instructions": [
   "Build the payload with scratch build.py (args 400 bomb400.docx), and build a control with args 0 base.docx.",
   "Under tools/sandbox-run.py, run render.py on each file. It calls RendererRegistry.bundled().render(RenderSource(data, DOCX, 'x.docx'), RenderLimits()) and records ru_maxrss before and after.",
   "Under tools/sandbox-run.py, run e2e.py on bomb400.docx. It opens DatabaseStorage on a scratch SQLite file, writes /up/report.docx with data=..., records ru_maxrss around reindex(), and then stats render_status.",
   "Stop at that first clear ratio. Do not scale the payload toward OOM."
  ],
  "observed_result": "Control docx (34,419 bytes): RSS grew by 5 MiB. Payload docx (442,096 bytes), direct render: status ok, text 'hello quokka', max RSS 106 MiB before and 912 MiB after, a growth of 805 MiB, which is 1,909.6 times the stored bytes. End to end: write succeeded, reindex succeeded, render_status was ok, and max RSS grew by 807 MiB during reindex. No RenderLimits check fired."
 },
 "remediation": {
  "strategy": "Before calling any OOXML library, open the body with zipfile.ZipFile and inspect infolist(). Refuse with a classified failed/corrupt Rendering when any of these exceeds a declared RenderLimits field: the member count, any entry's file_size, the sum of file_size, or the file_size/compress_size ratio. Because a central directory can lie, also bound the actual decompression, either by streaming each member through a size-capped reader or by trusting only the verified caps. Apply the same pre-check to xlsx for defense in depth. Then correct the RENDER_RATIO comment so that it describes an output guard.",
  "code_changes": [
   {
    "file_name": "src/vfs/rendering/seam.py",
    "fixed_code": "RENDER_PACKAGE_BYTES: Final = 256 * 1024 * 1024\nRENDER_PACKAGE_MEMBERS: Final = 10_000\nRENDER_MEMBER_RATIO: Final = 200\n\ndef package_refusal(data: bytes, limits: RenderLimits) -> str | None:\n    \"\"\"Why a zip container is refused before any library decompresses it, or None.\"\"\"\n    try:\n        infos = zipfile.ZipFile(BytesIO(data)).infolist()\n    except zipfile.BadZipFile as exc:\n        return f\"not a zip container: {exc}\"\n    if len(infos) > limits.package_members:\n        return f\"{len(infos)} members exceed {limits.package_members}\"\n    total = sum(i.file_size for i in infos)\n    if total > limits.package_bytes:\n        return f\"{total} uncompressed bytes exceed {limits.package_bytes}\"\n    for i in infos:\n        if i.file_size > limits.member_ratio * max(1, i.compress_size) and i.file_size > RENDER_RATIO_FLOOR:\n            return f\"{i.filename} expands {i.file_size}/{i.compress_size}\"\n    return None"
   },
   {
    "file_name": "src/vfs/rendering/docx.py",
    "fixed_code": "        refusal = package_refusal(source.data, limits)\n        if refusal is not None:\n            return failure(\"failed\", refusal)\n        try:\n            document = docx.Document(BytesIO(source.data))"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "It needs only ordinary write rights to a database mount and a routine operator reindex with the Office extras installed. The attacker's work is tiny: a 442 KB file, made with standard tools."
  },
  "impact": {
   "score": "medium",
   "reason": "I observed about 1,900x memory amplification in the host process that every agent shares, and no limit fired. Extrapolation says a few MiB stored is enough for multi-GiB allocations, which could OOM the shared process during maintenance. I did not demonstrate OOM itself, or that the row stays pending after a crash. The effect is availability only, with no data exposure."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "For docx, both the direct renderer and the real DatabaseStorage write-then-reindex path reproduced the result, measured against a control. For pptx, the eager read of every member was confirmed in the installed library source but not executed. For xlsx, the effect was not established."
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

- Scratch, the only place you or target code may write: `./agents/f10-p5/scratch/`. Never write `./agents/f10-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f10-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f10-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.rendering:ooxml-part-decompression-unbounded"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
