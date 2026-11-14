# Candidate verifier brief for `v15-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w5a-content-hash. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs/storage/database/write-trusts-caller-authored-content-hash",
  "title": "Caller-authored content_hash is stored unverified and keys cross-principal render lending and version skipping",
  "description": "write(entries=[...]) stores the content_hash carried on the caller's Entry without measuring the body it stores. A bodiless bytes Entry keeps any hash, and so does an Entry built with the MEASURED_BODY validation context. The reindex render cache then lends a settled rendering per (content_hash, generation) with no owner or rights term, and the landing guard checks only the receiving row's own (forged) hash. Two effects follow. First, a principal who cannot read another's file but knows its hash obtains its rendered text, and can test whether the mount holds a given document. Second, a principal can plant a donor so that another principal's later upload of a known document is served attacker-chosen text through read, grep and glean. This is an integrity break in another principal's model-facing content. The same trust lets a contributor skip version minting and erase the prior body's history.",
  "root_cause": "The storage write path (writes.py write_rows → staging.put_file → _material_values) takes entry.content_hash, which Entry's validator leaves caller-supplied for bodiless bytes entries and for MEASURED_BODY-vouched entries, as the row's hash. It never re-measures the stored body. render.py treats that hash as proof of byte identity when choosing a donor and when guarding the landing.",
  "intended_behavior": "A row's content_hash must always be the hash of the body storage holds for it. A bodiless authored Entry must be refused, or must keep the stored row's measured metrics. Render and version dedup must depend only on storage-measured hashes, and must not draw donors from tombstoned rows.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/base.py",
    "line": 2601,
    "scope": "AsyncVirtualFileSystem._route_entry_batch",
    "description": "Accepts any Entry instance from write(entries=...), path-gates it and dispatches it unchanged."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/models/entry.py",
    "line": 228,
    "scope": "Entry._derive_and_measure",
    "description": "Measures only when data is not None or source=='text'. Otherwise the caller's content_hash stands, and MEASURED_BODY context overrides measurement."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 163,
    "scope": "write_rows",
    "description": "Passes entry.content_hash into WritePlan.put_file and the staged row."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/writes.py",
    "line": 1172,
    "scope": "_material_values",
    "description": "Persists the staged content_hash. _replace_bodies keeps the old blob for a bodiless row."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/render.py",
    "line": 184,
    "scope": "cached_renderings",
    "description": "Lowest-id settled donor per (content_hash, generation), with no principal, rights or deleted_at term."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/render.py",
    "line": 336,
    "scope": "land_renderings",
    "description": "The stamp guard compares the key only to the receiving row's own content_hash, so the lent text lands as that row's content."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/models/entry.py",
    "line": 238,
    "description": "The text branch measures unless MEASURED_BODY is present. The bytes branch at 228 runs only when data is not None."
   },
   {
    "file": "src/vfs/storage/backends/database/render.py",
    "line": 204,
    "description": "The donor WHERE clause has only hash, source, stamp and status predicates."
   },
   {
    "file": "src/vfs/storage/backends/database/render.py",
    "line": 283,
    "description": "render_rows reuses seen[(hash, generation)] for any row in the page."
   },
   {
    "file": "src/vfs/storage/backends/database/versions.py",
    "line": 145,
    "description": "The pre-image version is skipped when its measured hash equals the staged (caller-supplied) hash."
   },
   {
    "file": "src/vfs/storage/backends/database/reads.py",
    "line": 107,
    "description": "List-level rows expose only path and kind, so H is not leaked to list-only callers. The attacker needs it from elsewhere."
   }
  ],
  "conditions": [
   {
    "kind": "authorization_role",
    "description": "The attacker is a named subject with write (add or higher) somewhere on the same mount as the victim's file. No rights on the victim's path are needed."
   },
   {
    "kind": "data_state",
    "description": "The attacker knows the exact sha-256 of the target document's bytes, for example a publicly distributed or shared document. For the reverse case, the attacker's donor must be the lowest-id settled row for that hash."
   },
   {
    "kind": "system_configuration",
    "description": "The operator runs reindex on the storage. This is routine and needed for any bytes rendering."
   }
  ],
  "execution": {
   "attacker_perspective": "Named subject alice with read_write only on /alice. Posture / is none, and bob owns /bob.",
   "payloads": [
    "Entry.model_validate({'path':'/alice/x.pdf','source':'bytes','content_hash':H_bob,'mime_type':'application/pdf'})",
    "Entry.model_validate({'path':'/alice/d.pdf','source':'bytes','content_hash':H_public,'mime_type':'application/pdf'}) written over a row holding alice's own PDF bytes"
   ],
   "instructions": [
    "In the sandbox on InMemoryStorage, set posture / to none and grant bob and alice read_write on their own prefixes.",
    "Bob writes a dummy PDF. Run reindex. Confirm that alice's read and stat of bob's file return not_found.",
    "Alice writes the bodiless Entry naming bob's hash. Run reindex. Alice reads her own path.",
    "Separately, alice overwrites her own PDF row bodiless with the hash of a public document. Run reindex. Bob uploads that public document. Run reindex. Bob reads his file."
   ],
   "observed_result": "Alice's /alice/x.pdf returned render_status ok with bob's text ('BOB-SECRET salary 123456'), with the rendering report showing cached=1. A wrong-guess hash stayed pending. Bob's /bob/form.pdf returned alice's chosen text, and bob's grep for it hit his own file. A forged-hash overwrite in a contribute region minted 0 versions, against 1 for an honest overwrite."
  },
  "remediation": {
   "strategy": "Measure at the storage seam. In write_rows, refuse a content-kind Entry that carries neither content nor data (or ignore its metrics and keep the stored row's). Recompute content_hash, size and lines from the staged body in the storage layer or the offload pool, never from the Entry. Reserve MEASURED_BODY for router-internal use, for example a private sentinel object rather than a public context key. In cached_renderings, add entry.deleted_at IS NULL. A rights-independent fix is that lending is safe once hashes are storage-measured.",
   "code_changes": [
    {
     "file_name": "src/vfs/storage/backends/database/writes.py",
     "fixed_code": "# in write_rows, before put_file:\nif entry.kind in CONTENT_KINDS and entry.content is None and entry.data is None:\n    plan.errors.append(classified(ErrorKind.invalid, entry.path, detail='a file write needs a body'))\n    continue\nmetrics = measure_bytes(entry.data) if entry.data is not None else measure_text(entry.content)\n# pass metrics.content_hash / size_bytes / lines instead of entry.*"
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "low",
    "reason": "The attacker needs a writable path on the victim's mount and the exact hash of the target bytes. Without read access that mostly means a known or shared document. The poisoning case also needs to win the lowest-id donor race."
   },
   "impact": {
    "score": "medium",
    "reason": "It crosses a principal boundary in both directions. One direction discloses another principal's rendered text and gives an existence oracle. The other plants attacker-chosen text as another principal's file content, which reaches their agents' context through read, grep and glean. Version history can also be erased."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "high",
   "reason": "Complete source lineage, and bounded local reproduction of every variant on InMemoryStorage through the public router API with dummy data."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%28entries%3D%5BEntry%5D%29%20with%20caller-authored%20body%20metrics%3A%20an%20Entry%28source%3D%27bytes%27%2C%20data%3DNone%2C%20content_hash%3DH%29%20keeps%20the%20caller%27s%20H%2C%20and%20the%20MEASURED_BODY%20validation%20context%20lets%20a%20caller-built%20Entry%20vouch%20any%20hash%20for%20real%20bytes::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frender.py%23cached_renderings%20and%20render_rows%20lend%20a%20settled%20rendering%20per%20%28content_hash%2C%20generation%29%20across%20rows%20with%20no%20principal%20or%20rights%20term%2C%20and%20land_renderings%20guards%20only%20on%20the%20receiving%20row%27s%20own%20content_hash%3B%20the%20same%20key%20is%20also%20used%20by%20rerank.py%23merge_ranked%20cross-mount%20dedup%20and%20versions.py%23_mint_rows%20history%20skip::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Composite-key%20and%20namespace%20collision",
  "agent_id": "w5a-content-hash",
  "reviewed_paths": [
   "src/vfs/models/entry.py",
   "src/vfs/base.py",
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/staging.py"
  ],
  "invariant": "Storage must measure or verify a row's content_hash from the body it actually stores, never accept a caller-authored value.",
  "method": "source",
  "result": "Entry._derive_and_measure measures only when data is not None or source=='text'; a bodiless bytes Entry keeps the caller's content_hash and mime_type, and MEASURED_BODY context is taken on trust. _route_entry_batch accepts any Entry instance and only path-gates it. write_rows/put_file/stage_* copy entry.content_hash into the staged row, and _material_values writes it. _replace_bodies skips a row with neither content nor data, so a bodiless overwrite keeps the old blob under the new hash. No layer re-measures.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%28entries%3D%5BEntry%5D%29%20with%20caller-authored%20body%20metrics%3A%20an%20Entry%28source%3D%27bytes%27%2C%20data%3DNone%2C%20content_hash%3DH%29%20keeps%20the%20caller%27s%20H%2C%20and%20the%20MEASURED_BODY%20validation%20context%20lets%20a%20caller-built%20Entry%20vouch%20any%20hash%20for%20real%20bytes::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frender.py%23cached_renderings%20and%20render_rows%20lend%20a%20settled%20rendering%20per%20%28content_hash%2C%20generation%29%20across%20rows%20with%20no%20principal%20or%20rights%20term%2C%20and%20land_renderings%20guards%20only%20on%20the%20receiving%20row%27s%20own%20content_hash%3B%20the%20same%20key%20is%20also%20used%20by%20rerank.py%23merge_ranked%20cross-mount%20dedup%20and%20versions.py%23_mint_rows%20history%20skip::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Composite-key%20and%20namespace%20collision",
  "agent_id": "w5a-content-hash",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/render.py"
  ],
  "invariant": "A rendering lent between rows must be bound to the receiving row's real bytes, or to a principal and rights term.",
  "method": "source",
  "result": "cached_renderings picks the lowest-id settled donor per (content_hash, render_generation). It has no owner or rights filter and no deleted_at filter, so trashed rows still donate. render_rows reuses a page twin by the same key. The land_renderings stamp guard checks only that the receiving row's own content_hash equals the key, and a forged hash satisfies that.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%28entries%3D%5BEntry%5D%29%20with%20caller-authored%20body%20metrics%3A%20an%20Entry%28source%3D%27bytes%27%2C%20data%3DNone%2C%20content_hash%3DH%29%20keeps%20the%20caller%27s%20H%2C%20and%20the%20MEASURED_BODY%20validation%20context%20lets%20a%20caller-built%20Entry%20vouch%20any%20hash%20for%20real%20bytes::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frender.py%23cached_renderings%20and%20render_rows%20lend%20a%20settled%20rendering%20per%20%28content_hash%2C%20generation%29%20across%20rows%20with%20no%20principal%20or%20rights%20term%2C%20and%20land_renderings%20guards%20only%20on%20the%20receiving%20row%27s%20own%20content_hash%3B%20the%20same%20key%20is%20also%20used%20by%20rerank.py%23merge_ranked%20cross-mount%20dedup%20and%20versions.py%23_mint_rows%20history%20skip::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Composite-key%20and%20namespace%20collision",
  "agent_id": "w5a-content-hash",
  "reviewed_paths": [
   "src/vfs/base.py",
   "src/vfs/storage/backends/database/render.py",
   "src/vfs/storage/backends/database/backend.py"
  ],
  "invariant": "A caller without read on another principal's file must not obtain its rendered text through the dedup cache.",
  "method": "local",
  "result": "Confirmed on InMemoryStorage. Setup: posture / none; bob has read_write on /bob, alice on /alice. Alice gets not_found on bob's PDF. She writes a bodiless Entry(source='bytes', content_hash=H_bob, mime_type='application/pdf') at /alice/x.pdf. After the operator's reindex (report cached=1), alice's read returns bob's rendered text, and grep finds it under her path. A wrong-guess hash stays 'pending' with an unavailable error: an existence oracle. The reverse case also works: alice plants a donor of her own bytes with a vouched H (MEASURED_BODY); bob's later upload of the document with hash H is served alice's text.",
  "artifact": "agents/w5a-content-hash/artifacts/evidence/render-lend-poc-output.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%28entries%3D%5BEntry%5D%29%20with%20caller-authored%20body%20metrics%3A%20an%20Entry%28source%3D%27bytes%27%2C%20data%3DNone%2C%20content_hash%3DH%29%20keeps%20the%20caller%27s%20H%2C%20and%20the%20MEASURED_BODY%20validation%20context%20lets%20a%20caller-built%20Entry%20vouch%20any%20hash%20for%20real%20bytes::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frender.py%23cached_renderings%20and%20render_rows%20lend%20a%20settled%20rendering%20per%20%28content_hash%2C%20generation%29%20across%20rows%20with%20no%20principal%20or%20rights%20term%2C%20and%20land_renderings%20guards%20only%20on%20the%20receiving%20row%27s%20own%20content_hash%3B%20the%20same%20key%20is%20also%20used%20by%20rerank.py%23merge_ranked%20cross-mount%20dedup%20and%20versions.py%23_mint_rows%20history%20skip::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Composite-key%20and%20namespace%20collision",
  "agent_id": "w5a-content-hash",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/writes.py",
   "src/vfs/storage/backends/database/render.py",
   "src/vfs/storage/backends/database/versions.py"
  ],
  "invariant": "Variants must be established independently: a donor planted without the Python-only context, the version-history skip, and trashed donors.",
  "method": "local",
  "result": "(C) Using only JSON-shaped model_validate dicts, alice writes her own bytes honestly, then overwrites the row bodiless with content_hash=H. The old blob is retained, reindex renders her bytes and stamps them under H, and bob's later upload of the H document gets her text. (D) Two files in a contribute region: an honest overwrite by alice mints 1 version of bob's v1, while an overwrite with a vouched hash equal to v1's hash mints 0. Bob's prior body is unrecoverable. (E) Bob trashes his PDF, and a bodiless H row of alice's still borrows its rendering.",
  "artifact": "agents/w5a-content-hash/artifacts/evidence/content-hash-variants-output.txt"
 },
 {
  "coverage_id": "src%2Fvfs%2Fbase.py%23write%28entries%3D%5BEntry%5D%29%20with%20caller-authored%20body%20metrics%3A%20an%20Entry%28source%3D%27bytes%27%2C%20data%3DNone%2C%20content_hash%3DH%29%20keeps%20the%20caller%27s%20H%2C%20and%20the%20MEASURED_BODY%20validation%20context%20lets%20a%20caller-built%20Entry%20vouch%20any%20hash%20for%20real%20bytes::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Frender.py%23cached_renderings%20and%20render_rows%20lend%20a%20settled%20rendering%20per%20%28content_hash%2C%20generation%29%20across%20rows%20with%20no%20principal%20or%20rights%20term%2C%20and%20land_renderings%20guards%20only%20on%20the%20receiving%20row%27s%20own%20content_hash%3B%20the%20same%20key%20is%20also%20used%20by%20rerank.py%23merge_ranked%20cross-mount%20dedup%20and%20versions.py%23_mint_rows%20history%20skip::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::DATA-ISOLATION-AND-LIFECYCLE.md%23Composite-key%20and%20namespace%20collision",
  "agent_id": "w5a-content-hash",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/reads.py",
   "src/vfs/rerank.py"
  ],
  "invariant": "How a lower-trust caller learns H, and other uses of the same key.",
  "method": "source",
  "result": "reads.py LIST_FIELDS={path,kind} for list-level rows and ROAD_FIELDS, so content_hash surfaces only to callers who can already read the row. Learning H otherwise requires knowing the exact bytes (a public or shared document) or an outside leak. The render_status pending-to-ok transition is an existence oracle for a guessed H. rerank._union drops later cross-mount rows whose content_hash was already seen, in dispatch order, so a forged row could shadow another principal's identical-hash row in a multi-mount glean. This was observed from source only, not run.",
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

- Scratch, the only place you or target code may write: `./agents/v15-p3/scratch/`. Never write `./agents/v15-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v15-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v15-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs/storage/database/write-trusts-caller-authored-content-hash` unless you identify a genuinely different root cause.

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
