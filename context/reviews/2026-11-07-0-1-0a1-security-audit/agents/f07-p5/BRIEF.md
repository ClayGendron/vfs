# Final record verifier brief for `f07-p5`

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
 "fingerprint": "vfs.rendering.docx:note-reference-inline-expansion",
 "title": "Repeated docx footnote or comment references copy the full note text inline before the character budget applies",
 "description": "The docx renderer writes a note's text inline at each footnoteReference or commentReference. _Writer._inline makes a fresh formatted copy of the full note text for every reference, keeps every copy in a list, joins them into one string, and only then hands that string to Builder.paragraph. Builder.paragraph runs sanitize() and splitlines() over the whole string before _append checks any budget. So a paragraph that repeats one reference N times to a note of L characters builds about N x L characters in memory, plus further copies, before RenderLimits.chars or the ratio guard can act. This grows with the product of two values the writer chooses, not with the decompressed input. Repeated references and repeated note text compress almost to nothing. In the sandbox, a 2,783-byte docx (one 10,000-character footnote, 10,000 references) reached a traced peak of 191.5 MiB inside DocxRenderer.render. The growth was linear: 1.9 MiB at 100 references, 19.2 MiB at 1,000 and 191.5 MiB at 10,000. A 13,970-byte docx built the same way (a 100,000-character note, 100,000 references) implies 10^10 inline characters, about 10 GB. That case was built and measured only, not rendered. Rendering runs in DatabaseStorage.reindex on the offload pool of the host process that all agents share. Because the copies build up one note at a time rather than in one huge allocation, the likely end is that the OS kills the process or the host swaps heavily, not a MemoryError that the registry would catch. A killed render never lands its stamp, so the row stays render_status='pending' and every later reindex renders it again.",
 "root_cause": "_Writer._inline (src/vfs/rendering/docx.py:131-149) appends _note(...) for every footnoteReference and commentReference with no limit on how many copies or how many characters it collects. Each _note call formats a new string holding the full note text (docx.py:152-154). The result is ''.join(parts), built in full before Builder sees it. Builder enforces RenderLimits.chars and the ratio guard only per line in _append (markdown.py:275-289), after paragraph() has already run sanitize(text).splitlines() over the whole string (markdown.py:180). The ratio guard compares output characters with the compressed input size, and only after the text exists.",
 "intended_behavior": "RenderLimits.chars (2 MiB by default) and the ratio guard should bound what a renderer builds, not only what it emits. The docx module docstring says 'the character budget bounds a document'. Inline note assembly should stop once the paragraph can no longer fit in the Builder's remaining budget, or write each note's text once and mark later references by id, so that memory stays within a small multiple of the budget whatever the reference count.",
 "trace": [
  {
   "kind": "entrypoint",
   "file": "src/vfs/storage/backends/database/writes.py",
   "line": 1181,
   "scope": "write row staging",
   "description": "A caller with write rights stores docx bytes through the write verb. There is no body-size cap, and the row is marked render_status='pending'."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/storage/backends/database/backend.py",
   "line": 1287,
   "scope": "DatabaseStorage._render_step",
   "description": "The operator's reindex selects every dirty bytes row, with no authority filter, and renders it through render_rows on the shared offload pool (call_offloaded at line 1288)."
  },
  {
   "kind": "propagation",
   "file": "src/vfs/rendering/docx.py",
   "line": 117,
   "scope": "_Writer.paragraph",
   "description": "text, pictures = self._inline(paragraph._p): the whole paragraph string is built before the Builder is called."
  },
  {
   "kind": "sink",
   "file": "src/vfs/rendering/docx.py",
   "line": 144,
   "scope": "_Writer._inline",
   "description": "parts.append(_note('footnote', ...)) runs for every footnoteReference (and line 146 for commentReference). Each call is a fresh copy of the full note text, and line 149 joins them all with no budget."
  }
 ],
 "evidence": [
  {
   "file": "src/vfs/rendering/docx.py",
   "line": 152,
   "description": "_note formats f' [{kind} {note_id}: {text}]' with the whole note text on every call."
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 180,
   "description": "Builder.paragraph runs sanitize(text).splitlines() over the whole joined string before any per-line budget check."
  },
  {
   "file": "src/vfs/rendering/markdown.py",
   "line": 280,
   "description": "The character budget and, at line 287, the ratio guard are checked only per appended line, after the text has been built."
  },
  {
   "file": "src/vfs/rendering/registry.py",
   "line": 107,
   "description": "The registry catches only Exception. An OS kill of the process or heavy swapping is not caught, so the row stays pending."
  },
  {
   "file": "agents/v07-p3/artifacts/evidence/run.txt",
   "line": 1,
   "description": "Sandbox run with a 10,000-character footnote. Traced peak inside DocxRenderer.render: 0.2 MiB at 0 references, 1.9 MiB at 100, 19.2 MiB at 1,000 and 191.5 MiB at 10,000. Input size stayed between 1,505 and 2,783 bytes."
  },
  {
   "file": "agents/v07-p3/artifacts/evidence/size.txt",
   "line": 1,
   "description": "Size-only build, not rendered: a 13,970-byte docx (100,000-character note, 100,000 references) implies 10^10 inline characters, and a 15,713-byte docx (1,000,000-character note) implies 10^11."
  },
  {
   "file": "agents/v07-p3/artifacts/evidence/repro.py",
   "line": 1,
   "description": "The reproduction script. It builds a minimal docx with dummy text and measures tracemalloc peak during DocxRenderer().render with the default RenderLimits."
  }
 ],
 "conditions": [
  {
   "kind": "authorization_role",
   "description": "The attacker is a principal with write rights to some path on a DatabaseStorage or InMemoryStorage mount that stores bytes bodies."
  },
  {
   "kind": "system_configuration",
   "description": "The vfs[docx] extra (python-docx) is installed, so the docx renderer is active."
  },
  {
   "kind": "timing_dependency",
   "description": "The operator or host later runs reindex(), the only place rendering happens. The cost lands on that maintenance job and on the host process that all agents share, not on the writer's own call."
  }
 ],
 "execution": {
  "attacker_perspective": "An agent or user with ordinary write rights uploads a small docx, a few kilobytes compressed. Its footnotes part holds one long footnote, and its body has one paragraph that repeats a reference to that footnote many times.",
  "payloads": [
   "word/footnotes.xml: <w:footnotes><w:footnote w:id=\"1\"><w:p><w:r><w:t>{10,000 chars of 'lorem ipsum '}</w:t></w:r></w:p></w:footnote></w:footnotes>",
   "word/document.xml: <w:document><w:body><w:p>{'<w:r><w:footnoteReference w:id=\"1\"/></w:r>' x 10,000}</w:p></w:body></w:document>"
  ],
  "instructions": [
   "Build a minimal docx zip: [Content_Types].xml, _rels/.rels, word/_rels/document.xml.rels (with a footnotes relationship), word/document.xml and word/footnotes.xml as in the payloads, compressed with ZIP_DEFLATED.",
   "Call DocxRenderer().render(RenderSource(data, DOCX, 'dummy.docx'), RenderLimits()) under tracemalloc. This is the same call that render_rows makes during reindex.",
   "Repeat with 0, 100, 1,000 and 10,000 references and record the traced peak memory against the input size."
  ],
  "observed_result": "Traced peak memory grew linearly with the reference count: 1.9, 19.2 and 191.5 MiB for 100, 1,000 and 10,000 references. The input stayed at 1,560 to 2,783 bytes, so the 10,000-reference case built about 70,000 bytes in memory for each input byte. The render then returned 'empty' or 'failed' only after that memory had been allocated. Larger cases were not executed; only their input sizes were measured. This shows memory amplification in one render. It does not show a process crash, because no run was taken to OOM."
 },
 "remediation": {
  "strategy": "Bound inline assembly in _Writer._inline. Write each note's full text only the first time it is referenced, and mark later references by id alone. Also stop collecting parts once the running length passes the Builder's remaining character budget, so no paragraph string can exceed a small multiple of RenderLimits.chars. Add a test that counts the characters (or tracemalloc bytes) built for a paragraph with many repeated references, rather than timing it.",
  "code_changes": [
   {
    "file_name": "src/vfs/rendering/docx.py",
    "fixed_code": "    def _inline(self, element: Any) -> tuple[str, list[str | None]]:\n        \"\"\"The paragraph's text with each note written once at its first reference, bounded by the budget.\"\"\"\n        parts: list[str] = []\n        pictures: list[str | None] = []\n        size = 0\n        cap = self._builder.remaining + 1\n        for node in element.iter():\n            tag = node.tag\n            piece: str | None = None\n            if tag == f\"{_W}t\":\n                piece = node.text or \"\"\n            elif tag == f\"{_W}tab\":\n                piece = \"\\t\"\n            elif tag in (f\"{_W}br\", f\"{_W}cr\"):\n                piece = \"\\n\"\n            elif tag == f\"{_W}footnoteReference\":\n                piece = self._note_once(\"footnote\", node.get(f\"{_W}id\"), self._notes.footnotes)\n            elif tag == f\"{_W}commentReference\":\n                piece = self._note_once(\"comment\", node.get(f\"{_W}id\"), self._notes.comments)\n            elif tag == f\"{_WP}docPr\":\n                pictures.append(node.get(\"descr\") or node.get(\"title\") or node.get(\"name\"))\n            if piece is not None and size <= cap:\n                parts.append(piece)\n                size += len(piece)\n        return \"\".join(parts), pictures\n\n    def _note_once(self, kind: str, note_id: str | None, texts: dict[str, str]) -> str:\n        key = (kind, note_id)\n        if key in self._written:\n            return f\" [{kind} {note_id}]\"\n        self._written.add(key)\n        return _note(kind, note_id, texts)\n\n# with self._written: set[tuple[str, str | None]] = set() in __init__, and a Builder.remaining\n# property returning max(0, self._budget - self._chars)"
   }
  ]
 },
 "severity": {
  "likelihood": {
   "score": "medium",
   "reason": "Ordinary write rights and a payload of a few kilobytes are enough, and there is no body-size cap. Rendering still waits for an operator-run reindex, and the writer cannot trigger it."
  },
  "impact": {
   "score": "medium",
   "reason": "Memory in the host process that all agents share grows with the product of reference count and note length. A 14 KB input implies about 10 GB. If the process is killed, the row stays pending and is retried on every reindex, so the file keeps failing the job. The impact is availability of a shared host and its maintenance job, with no disclosure and no integrity loss. The OOM end state was inferred from linear growth and was not observed."
  },
  "overall_severity": "medium"
 },
 "confidence": {
  "score": "high",
  "reason": "The source path is direct and has no control before the join. I independently reproduced linear memory growth at bounded sizes using the real DocxRenderer and default RenderLimits, inside the sandbox, with dummy data."
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

- Scratch, the only place you or target code may write: `./agents/f07-p5/scratch/`. Never write `./agents/f07-p5/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/f07-p5/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/f07-p5/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only. Use dummy principals and data, and stop at the minimum effect.
- Do not edit any repository file. Do not run git commands that change state.

## 5. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision":"verified","fingerprint":"vfs.rendering.docx:note-reference-inline-expansion"}` or `{"decision":"replace","reason":"...","record":{...}}`. A replacement record must exactly match one verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). In `reason`, say whether the change is material (verdict, root cause, trace, execution input or observed result, demonstrated impact, or severity) or only wording or line corrections.

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
