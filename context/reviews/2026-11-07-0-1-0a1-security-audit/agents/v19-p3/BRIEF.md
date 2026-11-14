# Candidate verifier brief for `v19-p3`

You are a fresh verifier. You did not hunt this candidate; it came from hunter(s) w6a-embed. Repository: . at commit 3586750 (read-only).

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
  "fingerprint": "vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine",
  "title": "One refused embed batch at the head of the NULL-embedding keyset stops vector indexing for every later writer on the store",
  "description": "The reindex embed step always restarts at chunk id 0. It takes the lowest-id unembedded rows, cuts them into batches using a ceil(len/4) token estimate, and stops the whole step at the first page where any batch fails. A batch the provider refuses deterministically has no split, skip or per-row quarantine. Its rows stay NULL and form the same first batch on every later run. With the shipped OpenAI provider, ordinary text denser than about 3.3 chars per token (CJK, Cyrillic, emoji) exceeds the real 300000-token request cap while staying under the 250000 estimated budget. A principal with write access to any path on the mount can write about 4096 small CJK files (about 2 MB). After that, every chunk any principal writes later never gets a vector, across any number of reindex runs, and glean's vector leg misses all of it. A smaller amount of such text permanently leaves the neighbouring rows that share its batch (other principals' content) unembedded, and slows the rest to one page per run.",
  "root_cause": "_embed_step (backend.py:1416-1483) treats every provider failure as transient: it records stopped_by and breaks the loop (backend.py:1466-1468), and the next run restarts at last=0 (backend.py:1442). embed_page/_embed_with_retry (embed.py:266-355) do not tell a deterministic refusal apart from a transient one, never bisect a refused batch, and keep no per-row failed state, so select_unembedded (embed.py:172-182) returns the same poison rows first on every run. token_batched (embed.py:112-133) meters with the OpenAI adapter's ceil(len/4) estimate (openai.py:63-64, provider.py:94-96), which undercounts token-dense scripts. Rows the writer controls can therefore push a batch past the hard cap the adapter itself declares (openai.py:34).",
  "intended_behavior": "Batches should be metered by a bound that cannot undercount, such as UTF-8 bytes for byte-level BPE. A refused batch without Retry-After should be bisected down to single rows, and a single row still refused should be quarantined with a per-row failed state that select_unembedded skips and the report counts. This mirrors the render stage's _land (backend.py:1298-1321). The loop should then keep advancing to later pages, so one writer's content cannot stop vector indexing for other principals.",
  "trace": [
   {
    "kind": "entrypoint",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 686,
    "scope": "DatabaseStorage.write",
    "description": "Principal alice, with read_write on /alice only, writes ordinary CJK text files. No content, script or length rule applies beyond the write gate."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/models/chunking.py",
    "line": 217,
    "scope": "recursive_text_split",
    "description": "reindex chunks the bodies into rows of at most 2048 chars. Alice's rows get lower chunk ids than anything written later."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1442,
    "scope": "DatabaseStorage._embed_step",
    "description": "Every run starts the keyset at last=0."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 178,
    "scope": "select_unembedded",
    "description": "The page is the lowest-id 'embedding IS NULL' rows, so alice's rows come first on every run."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 125,
    "scope": "token_batched",
    "description": "Cost is provider.estimate_tokens = ceil(len/4), metered against 250000 (5/6 of 300000). A 2048-input batch of 160-char CJK rows estimates at 81920 tokens but is really about 319488."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 349,
    "scope": "_embed_with_retry",
    "description": "The provider refuses with a 400 that carries no Retry-After, and the error is re-raised with no split and no row marking."
   },
   {
    "kind": "propagation",
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 319,
    "scope": "embed_page",
    "description": "gather(return_exceptions) keeps the first failure. The refused batch's rows land nothing."
   },
   {
    "kind": "sink",
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1466,
    "scope": "DatabaseStorage._embed_step",
    "description": "outcome.failure records stopped_by and breaks, so later pages are never selected. The same rows head the next run, and every later principal's chunks stay embedding NULL indefinitely."
   }
  ],
  "evidence": [
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1466,
    "description": "Any provider failure on a page breaks the whole embed loop."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1442,
    "description": "last = 0 on every run, so the poison rows are always re-selected first."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1317,
    "description": "The sibling render stage retries row by row and quarantines a refused row as 'failed'. The embed step has no equivalent."
   },
   {
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 121,
    "description": "The batch budget is 5/6 of max_batch_tokens, metered by the provider's estimate."
   },
   {
    "file": "src/vfs/embedding/provider.py",
    "line": 96,
    "description": "estimate_tokens = ceil(len/4), whatever the script."
   },
   {
    "file": "src/vfs/embedding/openai.py",
    "line": 34,
    "description": "The shipped adapter declares MAX_BATCH_TOKENS=300000 and uses estimate_tokens (line 63-64)."
   },
   {
    "file": "src/vfs/storage/backends/database/embed.py",
    "line": 358,
    "description": "Only an exception carrying Retry-After is retried; a 400 refusal is not split or marked."
   },
   {
    "file": "src/vfs/storage/backends/database/backend.py",
    "line": 1477,
    "description": "The operator sees only a retryable 'unavailable' warning naming no rows, while reindex reports success=True."
   }
  ],
  "conditions": [
   {
    "kind": "system_configuration",
    "description": "The mount is configured with an embedder whose hard caps are enforced on real tokens while vfs meters them with ceil(len/4). The shipped OpenAIEmbeddingProvider is the one shipped adapter that declares such caps. LangChain declares none, and local providers (model2vec, hashing) do not refuse."
   },
   {
    "kind": "authorization_role",
    "description": "The writer needs write access to some path on the same DatabaseStorage mount. No other right is needed, and reindex is run by the operator as usual."
   },
   {
    "kind": "data_state",
    "description": "The writer's token-dense rows must have lower chunk ids than the victims' unembedded rows, that is, be written before them or still be unembedded. A full stop needs about 4096 such rows (one EMBED_PAGE_ROWS page) with real tokens above about 147 per row. Fewer rows permanently strand only the rows that share their batch, and throttle the rest to one page per run."
   },
   {
    "kind": "third_party_dependency",
    "description": "OpenAI's tokenizer must count the text at more than about 1.2 times len/4, and must refuse a request over 300000 tokens deterministically, with a 400 and no Retry-After. The repository declares the cap. CJK at about 1 token per character in cl100k is widely documented, but it was not measured here: the provider was a local fake."
   }
  ],
  "execution": {
   "attacker_perspective": "An agent or user (alice) with read_write on its own subtree of a shared DatabaseStorage mount that is backed by the OpenAI embedder, whose victims (bob) write content later.",
   "payloads": [
    "4096 files /alice/notes/NNNNN.txt, each a distinct 160-character run of CJK ideographs from U+4E00 (estimate 40 tokens, real 156)",
    "PARTIAL variant: 10 files of 300 CJK chars with max_batch_tokens scaled to 3000"
   ],
   "instructions": [
    "Mount DatabaseStorage(url=sqlite+aiosqlite:///scratch<tmp>/full.db, embedder=CappedProvider) with a fake provider. It declares max_input_tokens=8192, max_batch_inputs=2048 and max_batch_tokens=300000, estimates with vfs.embedding.estimate_tokens, counts 1 token per CJK char when enforcing the caps, and raises a 400-shaped error with empty headers on an overrun.",
    "As system, create /alice and /bob, grant alice and bob read_write on their own directories, and reindex once.",
    "As alice, write the 4096 CJK files. As bob, write 50 ordinary English files.",
    "Run reindex three times. After each run, count embedded and NULL chunk rows per principal. Then run glean as bob and read legs['vector'].",
    "Control: the same run with zero alice files."
   ],
   "observed_result": "FULL, with caps and page size unscaled: in each of 3 runs, 2 requests were refused ([2048 inputs, 81920 estimated, 319488 real]). Bob stayed at 1 of 51 chunks embedded and unembedded=4146 every run. reindex returned success=True with the warning 'Unavailable: embedding stopped after 0 requests: BadRequest: Requested 319488 tokens, max 300000 tokens per request' (retryable=True). Bob's glean vector leg had hits=2. CONTROL: bob had 51 of 51 embedded after run 1, and the vector leg had hits=52. PARTIAL: the same 48-row first batch (alice's 10 plus 38 of bob's) was refused in all 3 runs, leaving bob at 63 of 101 embedded and the vector leg at hits=64."
  },
  "remediation": {
   "strategy": "Meter with a bound that cannot undercount, and stop treating a deterministic refusal as a reason to end the run. (1) The OpenAI adapter's estimate_tokens should return the UTF-8 byte length: byte-level BPE never yields more tokens than bytes, so batches and truncation stay under the hard caps. (2) In embed_page, a refused batch without Retry-After should be bisected recursively, and a single row that is still refused should be returned as a per-row failure. (3) Those rows should get a quarantine stamp: an embed_failed column or a sentinel state that select_unembedded and count_unembedded exclude, reset when the chunk's content_hash changes, with the count reported in the embedding extra. (4) _embed_step should break only on transient failures (timeout, 429/Retry-After, network) and otherwise keep advancing 'last'. Regression test: a fake provider counting 1 token per CJK char and enforcing 300000 per request; alice writes 4096 CJK files and bob writes 50; after one reindex, all of bob's chunks are embedded and alice's are either embedded or counted as quarantined.",
   "code_changes": [
    {
     "file_name": "src/vfs/embedding/openai.py",
     "fixed_code": "    def estimate_tokens(self, text: str) -> int:\n        # byte-level BPE never emits more tokens than UTF-8 bytes: an upper bound the hard caps can trust\n        return max(1, len(text.encode(\"utf-8\")))"
    },
    {
     "file_name": "src/vfs/storage/backends/database/embed.py",
     "fixed_code": "async def _embed_or_split(provider, batch, timeout):\n    \"\"\"Vectors for *batch*; a deterministic refusal is bisected down to single rows, which come back as failures.\"\"\"\n    try:\n        return await _embed_with_retry(provider, [truncated_for(r.content, provider) for r in batch], timeout), []\n    except Exception as exc:\n        if _transient(exc) or len(batch) == 1:\n            if len(batch) == 1 and not _transient(exc):\n                return None, [(batch[0].id, exc)]\n            raise\n        mid = len(batch) // 2\n        left, lf = await _embed_or_split(provider, batch[:mid], timeout)\n        right, rf = await _embed_or_split(provider, batch[mid:], timeout)\n        return _merge(left, right), lf + rf"
    }
   ]
  },
  "severity": {
   "likelihood": {
    "score": "medium",
    "reason": "The attacker cost is low: one ordinary write of about 2 MB of CJK text by any principal with write access to some path, and no special rights. It needs the OpenAI embedder (the only shipped adapter with hard caps) and token-dense content. Benign CJK or Cyrillic corpora with default 2048-char chunks trigger the same refusal (about 488 chunks per batch, about 1M chars, well over 300000 real tokens), so it will also happen without malice."
   },
   "impact": {
    "score": "medium",
    "reason": "The effect is persistent and store-wide: no chunk written later by any principal gets a vector, across every reindex, until an operator finds and deletes the poison rows or changes the provider. glean's vector leg silently misses that content, though the lexical leg still finds it, and nothing is disclosed. Each run also spends refused provider requests. The report names no rows, and its retryable=True flag invites endless retries."
   },
   "overall_severity": "medium"
  },
  "confidence": {
   "score": "medium",
   "reason": "The vfs logic (no split, skip or quarantine; break; restart at 0) is source-visible and was demonstrated with unscaled caps and page size. The external fact, OpenAI's real tokenizer counts and its 400 on going over 300000, comes from the repo's declared caps and public tokenizer behaviour, not from a live measurement."
  }
 }
]
```

## 4. Linked coverage-unit checks and artifacts

Artifacts are relative to context/reviews/2026-11-07-0-1-0a1-security-audit/. You may read them; they are hunter evidence, not your conclusion.

```json
[
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fbackend.py%23reindex%20embed%20step%20loop%20%28keyset%20pages%20from%20last%3D0%2C%20break%20on%20outcome.failure%29%20over%20chunk%20rows%20that%20any%20writer%27s%20body%20produces::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fembed.py%23token_batched%20and%20truncated_for%20metered%20by%20estimate_tokens%20%28ceil%28len%2F4%29%2C%20provider.py%3A94-96%29%20against%20the%20shipped%20OpenAI%20hard%20caps%20%28openai.py%20MAX_BATCH_TOKENS%3D300000%2C%20MAX_INPUT_TOKENS%3D8192%29%2C%20with%20no%20per-batch%20split%2C%20skip%20or%20quarantine%20on%20a%20deterministic%20provider%20refusal::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Failure%20and%20recovery%20attack%20classes",
  "agent_id": "w6a-embed",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/embed.py"
  ],
  "invariant": "A deterministically refused embed batch must not stop the embed step for rows of other principals: the loop should split, skip or quarantine the refused rows and keep advancing, as the render stage does (_land row-by-row retry then 'failed' quarantine, backend.py:1298-1321).",
  "method": "source",
  "result": "_embed_step sets last=0 on every run (backend.py:1442), selects the lowest-id 'embedding IS NULL' rows (embed.py:172-182), and on any page with a failed batch records stopped_by and breaks the whole loop (backend.py:1466-1468). embed_page lands the batches that answered (gather return_exceptions, embed.py:319-325) but never splits the refused batch, never marks its rows, and _embed_with_retry retries only when a Retry-After header exists (embed.py:346-368). No per-row embed state exists, so the same rows reform the same first batch on every run. Unlike the render stage, there is no quarantine.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fbackend.py%23reindex%20embed%20step%20loop%20%28keyset%20pages%20from%20last%3D0%2C%20break%20on%20outcome.failure%29%20over%20chunk%20rows%20that%20any%20writer%27s%20body%20produces::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fembed.py%23token_batched%20and%20truncated_for%20metered%20by%20estimate_tokens%20%28ceil%28len%2F4%29%2C%20provider.py%3A94-96%29%20against%20the%20shipped%20OpenAI%20hard%20caps%20%28openai.py%20MAX_BATCH_TOKENS%3D300000%2C%20MAX_INPUT_TOKENS%3D8192%29%2C%20with%20no%20per-batch%20split%2C%20skip%20or%20quarantine%20on%20a%20deterministic%20provider%20refusal::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Failure%20and%20recovery%20attack%20classes",
  "agent_id": "w6a-embed",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/embed.py",
   "src/vfs/embedding/provider.py",
   "src/vfs/embedding/openai.py",
   "src/vfs/embedding/langchain.py",
   "src/vfs/models/chunking.py"
  ],
  "invariant": "Batches sent to the shipped OpenAI provider must stay under its declared hard caps (300000 tokens per request, 8192 per input), whatever script the content is in.",
  "method": "source",
  "result": "token_batched meters each row by provider.estimate_tokens. For OpenAI that is ceil(len/4) (openai.py:63-64, provider.py:94-96), against 5/6 of 300000, which is 250000 estimated tokens (embed.py:61,121,333-335). The real count only has to be about 1.2 times the estimate to break the cap: about 3.3 chars per token or denser. CJK, Cyrillic, emoji and symbol-heavy text are all that dense or denser, so the batch is refused. Per input: chunks are at most 2048 chars (chunking.py:217), which is at most 8192 UTF-8 bytes, so byte-level BPE cannot exceed MAX_INPUT_TOKENS=8192. truncated_for (embed.py:136-144) is a no-op there, and a per-input refusal is not reachable through default chunking. LangChain declares no caps (langchain.py:34-36), so vfs predicts no refusal for it; model2vec and other local providers do not refuse.",
  "artifact": null
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fbackend.py%23reindex%20embed%20step%20loop%20%28keyset%20pages%20from%20last%3D0%2C%20break%20on%20outcome.failure%29%20over%20chunk%20rows%20that%20any%20writer%27s%20body%20produces::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fembed.py%23token_batched%20and%20truncated_for%20metered%20by%20estimate_tokens%20%28ceil%28len%2F4%29%2C%20provider.py%3A94-96%29%20against%20the%20shipped%20OpenAI%20hard%20caps%20%28openai.py%20MAX_BATCH_TOKENS%3D300000%2C%20MAX_INPUT_TOKENS%3D8192%29%2C%20with%20no%20per-batch%20split%2C%20skip%20or%20quarantine%20on%20a%20deterministic%20provider%20refusal::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Failure%20and%20recovery%20attack%20classes",
  "agent_id": "w6a-embed",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py",
   "src/vfs/storage/backends/database/embed.py",
   "src/vfs/embedding/openai.py"
  ],
  "invariant": "Bounded local proof: after principal alice writes token-dense ordinary text, bob's later writes still get vectors after repeated reindex runs.",
  "method": "local",
  "result": "DatabaseStorage on SQLite with a fake provider. It declares the shipped OpenAI caps (8192/2048/300000) and estimates with vfs's estimate_tokens, but enforces the caps with 1 token per CJK char. A cap overrun raises a 400-shaped error with no Retry-After. EMBED_PAGE_ROWS=4096 was left unscaled. FULL: alice (read_write on /alice) writes 4096 files of 160 CJK chars each (estimate 40, real 156), about 2 MB in total; bob then writes 50 English files. In all 3 reindex runs every batch was refused ([2048 inputs, 81920 estimated, 319488 real]). Bob's chunks stayed embedded 1/51 (only the pre-existing README), and unembedded stayed 4146 each run. reindex returned success=True with one retryable 'vfs.unavailable' warning: 'embedding stopped after 0 requests: BadRequest: Requested 319488 tokens, max 300000 tokens per request'. Bob's glean vector leg hits=2, against hits=52 in the CONTROL run without alice, where bob was 51/51 embedded after run 1. PARTIAL (only max_batch_tokens scaled to 3000): alice writes 10 CJK files of 300 chars. The refused first batch (48 rows: alice's 10 plus 38 of bob's) stayed NULL in all 3 runs; bob ended at 63/101 embedded and the vector leg at hits=64. Each FULL run took about 4 s wall time.",
  "artifact": "agents/w6a-embed/artifacts/evidence/embed-poison-batch-results.json"
 },
 {
  "coverage_id": "src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fbackend.py%23reindex%20embed%20step%20loop%20%28keyset%20pages%20from%20last%3D0%2C%20break%20on%20outcome.failure%29%20over%20chunk%20rows%20that%20any%20writer%27s%20body%20produces::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase%2Fembed.py%23token_batched%20and%20truncated_for%20metered%20by%20estimate_tokens%20%28ceil%28len%2F4%29%2C%20provider.py%3A94-96%29%20against%20the%20shipped%20OpenAI%20hard%20caps%20%28openai.py%20MAX_BATCH_TOKENS%3D300000%2C%20MAX_INPUT_TOKENS%3D8192%29%2C%20with%20no%20per-batch%20split%2C%20skip%20or%20quarantine%20on%20a%20deterministic%20provider%20refusal::src%2Fvfs%2Fstorage%2Fbackends%2Fdatabase::RESOURCE-EXHAUSTION-AND-AVAILABILITY.md%23Failure%20and%20recovery%20attack%20classes",
  "agent_id": "w6a-embed",
  "reviewed_paths": [
   "src/vfs/storage/backends/database/backend.py"
  ],
  "invariant": "Harness source for the local check (fake capped provider, principals, scenarios, scaling notes).",
  "method": "local",
  "result": "The harness used for the control, partial and full scenarios. It uses no network, makes no hosted provider call, and produces hash vectors.",
  "artifact": "agents/w6a-embed/artifacts/evidence/harness.py"
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

- Scratch, the only place you or target code may write: `./agents/v19-p3/scratch/`. Never write `./agents/v19-p3/artifacts/`; the parent promotes.
- Promotion allowlist: regular files you name under `scratch/evidence/`, cited as `agents/v19-p3/artifacts/evidence/<name>` (at most 256 KiB each, 1 MiB total).
- Run target code ONLY as `./tools/sandbox-run.py ./agents/v19-p3/scratch <cmd...>`. That denies all network including loopback, starts an empty env, makes everything but scratch read-only, and caps CPU at 60 s, wall-clock at 120 s, RSS at 2 GiB (watchdog), files at 64 MiB and processes at 256. The interpreter is `./.venv/bin/python -I <scratch-script>`. No uv, pip, cargo, docker or network. SQLite and InMemoryStorage only.
- Do not edit any repository file. Do not run git commands that change state.
- Prior records with the same fingerprint: none (no prior run).

## 8. Return contract

Return exactly one JSON object and no surrounding prose: `{"decision": "confirmed|needs_validation|rejected", "record": { ... }}`. The record must exactly match the decision's verdict branch below, including `"verdict"`, with no extra fields (`additionalProperties: false`). For a local check you ran, cite your own promoted artifact path in the record's evidence where it helps. Keep the fingerprint `vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine` unless you identify a genuinely different root cause.

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
