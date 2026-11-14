# Findings detail

Each confirmed medium, high or critical record from `findings.json`, copied in full. Run `vfs-run-1-2026-11-07` at commit `35867501a71f0246d9a9f6b755e1fcf323d58bb4`. Artifact paths are relative to the run folder.

## 1. grant() and revoke() are checked only at the addressed path, so a caller that gets read_write from the everyone posture at an ancestor can grant itself (or anyone) access to a private posture hole beneath it, or revoke others' access there

**Severity:** high (likelihood medium, impact high). **Confidence:** high. **Fingerprint:** `src/vfs/storage/backends/database/rights.py:grant-refusal:addressed-path-gate-ignores-posture-holes-beneath`

Before a grant or a revoke, the gate checks one thing: does the caller hold read_write at the exact path it named? That check counts read_write the caller gets from the everyone level (the posture). A grant row, though, covers the path and its whole subtree. Grant rows only add access, and a principal's covering row outranks any deeper, narrower posture. Take a mount whose ancestor posture gives everyone read_write (the default for a fresh DatabaseStorage/InMemoryStorage) and whose child folder has a narrower posture such as none. That is the 'open root with a private child' shape. On it, any named principal with no rows can grant itself read (or read_write) at the ancestor, then read and overwrite the private child and re-posture it open to everyone. An anonymous router caller can do the same by granting to a principal it names. A revoke at the ancestor likewise strips another principal's access inside the hole, which the revoker could not see. The caller held nothing in that child. delete/move/sweep run a subtree check (WriteGate.subtrees) that catches this posture hole. grant and revoke do not.

### Root cause

_grant_refusal (src/vfs/storage/backends/database/rights.py:1305-1336) reads posture rows only for ancestors_and_self(path) (line 1327). It allows the call as soon as gate.resolution.at('read_write').reaches(path, label) is true (line 1332). Rights.reaches (src/vfs/storage/grants.py:477-479) is a point test: everyone_level >= need at the path itself, or the caller's spans cover that one path. It never asks whether the caller holds the level across the subtree the new row will cover, although Rights.covers_subtree (grants.py:481) exists for exactly that. grant_rows then upserts a principal row at path (rights.py:919). Rights.admits (grants.py:493) returns True on covers(path) for every row beneath that prefix, holes included, so the new row overrides the deeper posture. revoke_rows uses the same point gate, so it can delete a row whose effect reaches into a hole.

### Intended behaviour

Spec 058 section 8 (context/specifications/archive/058-row-level-permission-grants/spec.md:74) says the granting subject set must hold read_write on the path and 'may grant at most its own level (attenuation)'. The router docstring (src/vfs/base.py:1614-1615) says 'so nobody grants more than it holds'. The grant_rows docstring (rights.py:909-910) says 'what it grants never exceeds its own level there'. Spec 058 section 6 (spec.md:64) requires subtree mutations to check beneath the target 'since an owner-floor row or a posture hole can sit inside a writable directory'. A grant or revoke at /P should be refused unless the granter holds the required level throughout /P's subtree: either its own spans cover the subtree, or no posture row beneath /P gives everyone less than that level at a prefix the spans do not cover.

### Trace

1. **entrypoint** `src/vfs/base.py:1599` `AsyncVirtualFileSystem.grant`: Public grant verb taking path, principal and level from the caller. With no authority it acts as default_authority or anonymous (base.py:3094-3107). revoke follows the same route.
2. **propagation** `src/vfs/base.py:2025` `AsyncVirtualFileSystem._route_grant`: Applies only the mount permission layers via _gate_entry for the addressed rel path, then dispatches to the storage grant verb (line 2044).
3. **propagation** `src/vfs/storage/backends/database/backend.py:1577` `DatabaseStorage._grant_write`: Bumps the revision, resolves the gate at VERB_RUNGS[op] = read_write (line 1595), and runs grant_rows or revoke_rows.
4. **propagation** `src/vfs/storage/backends/database/rights.py:1327` `_grant_refusal`: Reads posture rows only for ancestors_and_self(path) and computes the everyone label at the addressed path. Posture rows beneath the path are never read.
5. **propagation** `src/vfs/storage/backends/database/rights.py:1332` `_grant_refusal`: Returns None (allowed) when gate.resolution.at('read_write').reaches(path, label). An everyone read_write at the path is enough.
6. **propagation** `src/vfs/storage/grants.py:477` `Rights.reaches`: Point test: everyone_level >= need or self.covers(path). It does not test the subtree; covers_subtree at line 481 does, and WriteGate.subtrees uses it, but the grant gate does not.
7. **sink** `src/vfs/storage/backends/database/rights.py:919` `grant_rows -> _upsert_grant`: Writes (principal, path, level). Rights.admits (grants.py:493) then admits every row beneath path through covers(), whatever the deeper posture says. revoke_rows (rights.py:945-950) deletes a row at path under the same point gate.

### Evidence

- `src/vfs/storage/backends/database/rights.py:1305`: _grant_refusal is the shared gate for grant, revoke and posture. It judges read_write only at the addressed path.
- `src/vfs/storage/grants.py:481`: covers_subtree() exists and is the subtree-aware test, but the grant gate calls only the point test reaches() (line 477).
- `src/vfs/storage/backends/database/rights.py:730`: WriteGate.subtrees is the sibling control. delete/move/sweep use it to refuse when a row beneath the target fails the rung, posture holes included. grant/revoke have no equivalent.
- `src/vfs/storage/grants.py:493`: Rights.admits returns True on covers(path), so a principal row at /P admits /P/Q rows even when everyone_level there is 0.
- `src/vfs/base.py:1615`: Declared contract: 'so nobody grants more than it holds'.
- `src/vfs/storage/backends/database/rights.py:910`: grant_rows docstring: 'what it grants never exceeds its own level there'.
- `context/specifications/archive/058-row-level-permission-grants/spec.md:74`: Spec requires attenuation: the granter 'may grant at most its own level'. grant is not listed among the developer-plane-only verbs, so it is an agent-facing verb.
- `context/specifications/archive/058-row-level-permission-grants/spec.md:64`: Subtree mutations must check beneath the target because 'a posture hole can sit inside a writable directory'. The grant verbs are not held to this.
- `src/vfs/storage/backends/database/backend.py:205`: The default posture is read_write, so a mount that only narrows a child posture is exposed with no explicit root posture (reproduced).
- `tests/support/grants_contract.py:817`: test_nobody_grants_more_than_it_holds tests attenuation only at the addressed path. No test grants or revokes at an ancestor of a posture hole.
- `agents/v02-p3/artifacts/evidence/grant-ancestor-of-posture-hole.txt:1`: Independent verifier run (InMemoryStorage, sandboxed). Default root posture, /team/hr posture none: eve is refused reading the hr file (not_found), refused granting at /team/hr (not_found), refused deleting /team (permission_denied). eve grant('/', 'eve', 'read') answers ok, then eve reads 'DUMMY-PRIVATE'. eve grant('/team', 'eve', 'read_write') answers ok, then overwrite ok, re-posture /team/hr read_write ok, and anonymous then reads the file. Router with no authority: anon read is unauthenticated and grant at /team/hr is unauthenticated, but grant('/team', 'eve', 'read') answers ok and eve reads the secret.
- `agents/v02-p3/artifacts/evidence/revoke-ancestor-of-posture-hole.txt:1`: Independent revoke run: system grants bob read_write at /team, /team/hr posture none. bob reads hr ok, eve gets not_found. eve revoke('/team', 'bob') answers ok, and bob then gets not_found inside the hole.

### Conditions

- *system_configuration*: An ancestor path P has an everyone level that reaches read_write (the default posture of a fresh DatabaseStorage/InMemoryStorage, or an explicit one), and a deeper posture row at P/Q narrows everyone to less (none, list, read, add or contribute). Spec 058 tests this 'open root with a private child' shape.
- *authentication_level*: Any named Authority with no rows of its own is enough. Through the router, an anonymous call (no authority and no default_authority) is also enough, because unauthenticated_at is judged only at P, where everyone holds read_write. Anonymous cannot name itself as grantee ('anon' is reserved), so it grants to a principal it names or controls.
- *data_state*: Protected rows exist beneath P/Q, or are written there later; the grant also covers future rows. For the revoke variant, another principal holds a row at P that gives it access inside P/Q.

### Reproduction

**Attacker perspective:** A named principal 'eve' with no grant rows, or an anonymous caller through AsyncVirtualFileSystem, on a mount with the default read_write posture whose /team/hr posture is none.

Payloads:

- `await storage.grant(path=Path('/'), principal='eve', level='read', authority=Authority.of(Principal('eve')))`
- `await storage.grant(path=Path('/team'), principal='eve', level='read_write', authority=Authority.of(Principal('eve')))`
- `await fs.grant('/team', 'eve', 'read')  # AsyncVirtualFileSystem(storage=...), no authority -> anonymous`
- `await storage.revoke(path=Path('/team'), principal='bob', authority=Authority.of(Principal('eve')))`

Instructions:

1. Create InMemoryStorage(). As Authority.system(), write /team/hr/salaries.md (dummy content 'DUMMY-PRIVATE') and /team/notes.md with parents=True. Leave the root at its default posture and set posture('/team/hr', 'none').
2. As eve, confirm the baseline: read('/team/hr/salaries.md') -> not_found; grant('/team/hr', 'eve', 'read_write') -> not_found; delete('/team') -> permission_denied.
3. As eve, call grant('/', 'eve', 'read') (or grant('/team', 'eve', 'read_write')). It answers ok.
4. As eve, read /team/hr/salaries.md (ok, 'DUMMY-PRIVATE'); with the read_write row, overwrite it and set posture('/team/hr', 'read_write'); anonymous can then read it.
5. Router variant: AsyncVirtualFileSystem(storage=...) with no authority: read -> unauthenticated, grant('/team/hr', ...) -> unauthenticated, grant('/team', 'eve', 'read') -> ok, then eve reads the file.
6. Revoke variant: system grants bob read_write at /team, then posture('/team/hr', 'none'). eve revoke('/team', 'bob') -> ok; bob's read of the hr file goes from ok to not_found.
7. Run with tools/sandbox-run.py and .venv/bin/python -I (no network, empty env, scratch-only writes).

**Observed result:** Verifier run, direct: eve read hr -> vfs.not_found; grant at /team/hr -> vfs.not_found; delete /team -> vfs.permission_denied; grant / eve read -> ok; read hr -> ok 'DUMMY-PRIVATE'; grant /team eve read_write -> ok; overwrite -> ok; posture /team/hr read_write -> ok; anonymous read -> ok. Router, anonymous: read -> vfs.unauthenticated; grant /team/hr -> vfs.unauthenticated; grant /team eve read -> ok; eve read -> ok 'DUMMY-PRIVATE'. Revoke: bob read ok; eve read not_found; eve revoke bob at /team ok; bob read not_found. This matches the hunter's independent observation.

### Priority

Likelihood medium: The attacker needs only an ordinary named Authority, or none at all through the router. The precondition is an operator choice: a narrower posture on a child under a permissive ancestor. That shape is documented and tested, and the default posture already supplies the permissive ancestor.

Impact high: A principal with no rights in the private subtree gains read or full read_write over it: it reads every row, overwrites or trashes them, and can re-posture the subtree open to everyone, anonymous included. The revoke variant lets it remove other principals' access inside the hole. This crosses the row-rights boundary between anonymous or named callers and protected entries.

Confidence: Every trace line was checked in source at 3586750. The verifier reproduced the result independently in a sandboxed InMemoryStorage run, which uses the DatabaseStorage rights code path, both directly and through the router as anonymous, and for revoke. The refused baselines (not_found at the hole, permission_denied on delete) show that the posture hole is meant to be enforced. No other layer checks beneath the grant prefix.

### Remediation

Make the grant and revoke gate check the subtree the row covers, not just the addressed point, as WriteGate.subtrees does for delete/move/sweep. When the caller's own spans at the required rung do not cover the subtree (neither rights.whole nor rights.covers_subtree(path)), read the posture ('*') rows strictly beneath path. Read them in bounded pages over the bytewise range (path + '/', path + '0') on grants where principal_id = '*', chunked by the membership budget. Refuse with permission_denied when any of them gives everyone less than the rung at a prefix the caller's spans do not cover whole. Add a contract test on every StorageContract leg: open root, private /P/Q. A principal with no rows, and anonymous through the router, must be refused grant and revoke at /P and at /, and still be allowed at an unrelated open sibling.

Sketch for `src/vfs/storage/backends/database/rights.py`:

```python
    rights = gate.resolution.at(gate.needs.primary)
    if rights.reaches(str(path), label):
        if not (rights.whole or rights.covers_subtree(str(path))):
            async for prefix, level in _postures_beneath(session, tables, profile, membership_budget, str(path)):
                if LEVEL_RANK[level] < rights.need and not rights.covers_subtree(prefix):
                    return denied(path)
        return None

# _postures_beneath: page grants where principal_id == EVERYONE_NAME and
# path_prefix in the bytewise range (path + '/', path + '0'), ordered by path_prefix, bounded page size.
```

## 2. markdown_refs folds the whole enclosing line once per reference, so one agent-written single-line markdown body makes reindex hold the mount's writer transaction for quadratic time

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs-core.links.line_context:per-reference-whole-line-fold`

During reindex, the chunk pass sends every dirty markdown body to the Rust markdown_refs. That function calls line_context once for each link destination or path-shaped code span. line_context scans back to the previous newline and forward to the next one, then folds the whole line, and only after that keeps 256 characters. So a body with N references on one line of length about N costs O(N^2). The parse runs on the offload pool with the GIL released, so the event loop keeps running. But it is awaited inside chunk_dirty's writer transaction (BEGIN IMMEDIATE on SQLite; on InMemoryStorage, the single serialized session), and there is no time, size or reference budget on it. Every other principal's write to that mount waits until the parse finishes. In an independent run, one 160 KB single-line file written by alice made the operator's reindex take about 7.0 s, against about 0.6 s for the same bytes and references spread over 16,000 lines. bob's unrelated write waited 6.7 s on InMemoryStorage and 6.9 s on file-backed SQLite. Each doubling of the line costs about 3.7-3.9x. The stall comes back on every reindex after the file is rewritten.

### Root cause

line_context (crates/vfs-core/src/links.rs:71-75) recomputes the line bounds with rposition/position over the whole line and calls fold_line over the whole line for every reference. fold_line (links.rs:78-93) builds the full folded copy before it truncates to MAX_CONTEXT_CHARS. The per-reference cost is therefore O(line length), not O(MAX_CONTEXT_CHARS). The quadratic work is reachable while a writer transaction is open: _gram_phases runs chunk_dirty inside _execute_write (backend.py:1375), and chunk_dirty awaits call_offloaded(_assess_and_split) (indexing.py:330). _assess_and_split ends with extract_link_work over every dirty markdown body (indexing.py:583). None of these places has a deadline or a per-body cap.

### Intended behaviour

Reference extraction should be linear in body size, and each reference's context should cost at most O(MAX_CONTEXT_CHARS). CPU that reindex spends on caller-written content should be bounded, or should run without the mount's writer lock held, so that one principal's document cannot block other principals' writes for superlinear time.

### Trace

1. **entrypoint** `src/vfs/base.py:958` `AsyncVirtualFileSystem.write`: A lower-trust named principal (alice) writes a .md body that holds N link destinations on one line. No body-size or line-length cap exists on this path.
2. **propagation** `src/vfs/storage/backends/database/backend.py:1375` `DatabaseStorage._gram_phases`: The operator's reindex runs chunk_dirty inside _execute_write. That is a BEGIN IMMEDIATE writer transaction on SQLite, and the one serialized session on InMemoryStorage.
3. **propagation** `src/vfs/storage/backends/database/indexing.py:330` `chunk_dirty`: call_offloaded(_assess_and_split) is awaited while the writer transaction is open, with no deadline.
4. **propagation** `src/vfs/storage/backends/database/indexing.py:583` `_assess_and_split`: extract_link_work(rows, links_generation) runs over every dirty markdown body.
5. **propagation** `src/vfs/storage/backends/database/links.py:76` `extract_link_work`: extract_links passes the bodies to native.markdown_refs (models/links.py:78, python.rs:207), which parses each body on one thread, off the GIL.
6. **propagation** `crates/vfs-core/src/links.rs:54` `markdown_refs`: line_context(body, node.start_byte()) is called once for every link_destination and path-shaped code_span.
7. **sink** `crates/vfs-core/src/links.rs:72` `line_context`: rposition and position over the whole line, then fold_line over the whole line, for each reference: O(N x line length) CPU while the writer lock is held.

### Evidence

- `crates/vfs-core/src/links.rs:71`: line_context scans to both ends of the line and folds all of it before the result is cut to MAX_CONTEXT_CHARS.
- `crates/vfs-core/src/links.rs:78`: fold_line iterates every char of the line and builds the whole folded string. Only the final collect takes 256 chars, so there is no early exit.
- `src/vfs/storage/backends/database/indexing.py:330`: The offloaded split is awaited inside the writer transaction, with no budget.
- `src/vfs/storage/backends/database/backend.py:1666`: _execute_write marks the connection vfs_writer, so SQLite opens BEGIN IMMEDIATE and holds the write lock from the first read.
- `src/vfs/storage/backends/database/dialects.py:398`: Other SQLite writers wait up to busy_timeout 5000 ms per attempt. Under with_retry (engine.py:298) they get a bounded number of attempts and then a conflict.
- `src/vfs/storage/backends/database/engine.py:722`: On InMemoryStorage, _SerializedSessions holds one asyncio.Lock for each session's whole context, so every other operation waits for the chunk transaction.
- `agents/v03-p3/artifacts/evidence/verify.txt:1`: Verifier's independent sandboxed run. Native one-line parse took 460/1706/6625 ms at N=4000/8000/16000, against 49/103/216 ms for the same references on N lines. End to end, reindex took 593/1930/7044 ms, and bob's concurrent write waited 295/1645/6685 ms. The N-line control took 592 ms, with bob waiting 284 ms. File SQLite at N=16000: reindex 7090 ms, bob's write waited 6920 ms.

### Conditions

- *authorization_role*: The attacker needs write rights to any one .md path on the mount, for example its own file.
- *user_interaction*: The trusted operator or host runs storage.reindex() on the mount. This is routine maintenance, but it is a storage-direct verb that agents cannot call.
- *system_configuration*: The mount is SQLite-backed (file DatabaseStorage or InMemoryStorage), and other principals write to it while reindex runs. On server engines the chunk transaction holds only row locks, so the cross-writer effect there was not measured. The quadratic CPU, and the delay to the operator's reindex, apply on every engine.

### Reproduction

**Attacker perspective:** A named agent principal (alice) writes one markdown file to a shared mount. Later the operator runs storage.reindex(). Another principal (bob) writes his own unrelated file while the reindex runs.

Payloads:

- `fs.write(path='/doc.md', content='[a](b.md) ' * 16000, authority=alice)  # 160 KB, one line`
- `control: fs.write(path='/doc.md', content='[a](b.md)\n' * 16000, authority=alice)  # same bytes and refs, 16000 lines`
- `native: vfs.native.markdown_refs([('[a](b.md) ' * N).encode()]) versus markdown_refs([('[a](b.md)\n' * N).encode()])`

Instructions:

1. Run agents/v03-p3/scratch/verify.py under tools/sandbox-run.py (no network, empty env, CPU 60 s, wall 120 s, RSS 2 GiB) with ./.venv/bin/python -I.
2. Time native.markdown_refs at N=4000, 8000 and 16000 for the one-line body and for the N-line body.
3. For each N, on a fresh InMemoryStorage behind AsyncVirtualFileSystem: alice writes /doc.md, the operator awaits storage.reindex(), and 250 ms in, bob writes /bob.txt. Record the reindex time and bob's write latency. Repeat N=16000 with the N-line control, and on a file-backed SQLite DatabaseStorage.

**Observed result:** Native one-line: 459.6 / 1705.8 / 6624.5 ms (x3.71, x3.88 per doubling). N-line control: 49.3 / 103.3 / 215.8 ms (linear). In both cases every reference got a 256-char context. InMemoryStorage one-line: reindex 592.6 / 1930.3 / 7044.2 ms, and bob's write waited 295.0 / 1645.5 / 6684.9 ms (it succeeded). N-line control at N=16000: reindex 591.8 ms, bob waited 284.1 ms. File-backed SQLite one-line at N=16000: reindex 7089.9 ms, and bob's write on another pooled connection waited 6920.4 ms, longer than one 5 s busy_timeout, before it succeeded.

### Priority

Likelihood medium: Writing one markdown file is ordinary agent capability, and reindex is routine operator maintenance. The attacker cannot start reindex itself, but every reindex after each rewrite of the file pays the cost again.

Impact medium: On SQLite-backed mounts, every other principal's write blocks for a time that grows quadratically with one file's line length: about 6.7-6.9 s at 160 KB, measured. On InMemoryStorage, all other sessions wait as well. Larger lines extrapolate past busy_timeout times the retry attempts, after which a blocked writer would fail with a conflict. That is inferred from source, not run. The event loop is not stalled, and the stall ends when the pass commits.

Confidence: The cited source lines were verified. The native split isolates line_context: the same references and the same inline parse grow linearly when spread over lines and quadratically on one line. The verifier independently reproduced the end-to-end blocking of a concurrent writer on InMemoryStorage and on file SQLite.

### Remediation

Make each reference's context cost O(MAX_CONTEXT_CHARS). Compute the newline offsets once per body with memchr and find each reference's line by binary search. References arrive in document order, so cache the folded context per line start and fold each line only once. Make fold_line stop as soon as it has emitted MAX_CONTEXT_CHARS chars. As defence in depth, consider a per-body reference cap or work budget. Also consider running the offloaded CPU before the writer transaction opens, since the chunk flip is already version-guarded. For a regression test, count bytes scanned or fold invocations for one line with N and with 2N references and assert linear growth. Do not assert on wall time.

Sketch for `crates/vfs-core/src/links.rs`:

```rust
pub fn markdown_refs(parser: &mut MarkdownParser, body: &[u8]) -> Vec<MarkdownRef> {
    let newlines: Vec<usize> = memchr::memchr_iter(b'\n', body).collect();
    let mut cached: Option<(usize, String)> = None;
    // ... in the walk, replacing line_context(body, node.start_byte()):
    let at = node.start_byte();
    let k = newlines.partition_point(|&i| i < at);
    let start = if k == 0 { 0 } else { newlines[k - 1] + 1 };
    let end = newlines.get(k).copied().unwrap_or(body.len());
    let context = match &cached {
        Some((s, c)) if *s == start => c.clone(),
        _ => { let c = fold_line(&String::from_utf8_lossy(&body[start..end])); cached = Some((start, c.clone())); c }
    };
    refs.push(MarkdownRef { dest, context });
}
// fold_line: track the emitted char count and break once it reaches MAX_CONTEXT_CHARS.
```

## 3. Grep lines mode copies a separate context window for every hit line, so output grows as hit lines × body size

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs-core.verify.extend_context:per-hit-context-duplication`

In grep's lines output mode, before_context and after_context are accepted up to 2^31-1. The Rust matcher builds one context span for each hit line and never merges spans that overlap. python.rs then copies each span into its own PyBytes, and grep.py wraps each one in a Match. Nothing limits the size of the output. If the pattern matches every line, or if invert_match is used with a pattern that matches nothing, each of L lines carries about the whole body as its context. The output is then about L × body bytes, which is quadratic in the body. Any caller who can read one multi-line entry can trigger this with a single grep call. allow_scan is not needed, because invert_match takes the scan tier on its own. The memory is allocated in the host process, which many agents share. Local run on InMemoryStorage: a 40,000-byte body of 4,000 lines returned 159,996,000 characters of match content, and peak RSS rose to about 634 MB. Each doubling of L multiplied the output by 4.

### Root cause

extend_context (crates/vfs-core/src/verify.rs:242) builds a full span for each hit line on its own. Matcher::hit_lines (verify.rs:118) pushes one span per hit and only stops at max_count, which defaults to None. Overlapping windows are never merged. python.rs:154 copies each span into a new PyBytes, and grep.py:358 wraps each in a Match. Nothing bounds the output: CONTENT_BYTE_BUDGET (grep.py:126) only limits input bodies held at once, the parameter gate allows context up to INT_CEILING, and the wall-time deadline is checked only before each body starts (verify.rs:197), never inside one.

### Intended behaviour

Grep's lines-mode output should stay bounded by about the size of the matched body, whatever the context arguments are. That is how the ripgrep baseline behaves: it merges overlapping or adjacent context windows and emits each line at most once. The repo's own early spec expected the same ('merged context windows render correctly', context/specifications/archive/001-unify-vfs-result-and-optimize-queries/spec.md:169). Failing that, a declared output budget should truncate the result with a classified warning, as grep's other budgets do.

### Trace

1. **entrypoint** `src/vfs/params.py:270` `grep before_context / after_context ParamSpec`: The caller's before_context and after_context are accepted as ints from 0 to INT_CEILING (2^31-1). Lines 278-286 do the same for after_context. max_count (line 288) is optional and defaults to None.
2. **propagation** `src/vfs/storage/backends/database/grep.py:348` `grep_rows lines-mode verify`: Passes before_context, after_context and cap=max_count (None by default) to VerifyOffload.hit_lines for each content batch. No output budget is applied.
3. **propagation** `crates/vfs-core/src/verify.rs:118` `Matcher::hit_lines`: Pushes one extend_context span for every hit line. It stops only at cap, so with no cap every line gets its own span.
4. **propagation** `crates/vfs-core/src/verify.rs:242` `extend_context`: Walks back up to `before` lines and forward up to `after` lines from each hit, clamped only to the body. With huge context each span is the whole body. Spans are not merged with the previous hit's span.
5. **propagation** `crates/vfs-core/src/python.rs:154` `PyContentMatcher::hit_lines`: Copies the bytes of every span into a new PyBytes while holding the GIL. Total allocation is the sum of all span lengths, about hits × body bytes.
6. **sink** `src/vfs/storage/backends/database/grep.py:358` `grep_rows Match assembly`: Wraps each span's content in a pydantic Match on the event loop. The quadratic payload is kept in Observation.matches and returned to the caller.

### Evidence

- `crates/vfs-core/src/verify.rs:118`: hits.push(extend_context(...)) runs once per hit line, and the cap is the only stop condition.
- `crates/vfs-core/src/verify.rs:242`: extend_context computes a span per hit on its own. There is no merge with earlier spans.
- `crates/vfs-core/src/verify.rs:197`: hits_batch checks the deadline only before it starts each body. Inside one body, matching and span building are not bounded.
- `crates/vfs-core/src/python.rs:154`: Each span is copied into a separate PyBytes.
- `src/vfs/storage/backends/database/grep.py:126`: CONTENT_BYTE_BUDGET (32 MiB) limits how many input body bytes are resident at once. It does not limit output size. The other budgets (lines 119-121) count candidates, posting bytes and wall time.
- `src/vfs/params.py:274`: maximum=INT_CEILING is the only bound on before_context. after_context gets the same bound at line 283.
- `src/vfs/storage/backends/database/grep.py:199`: The unindexable-pattern refusal is skipped when invert_match is set. So a reader needs no allow_scan to make every line of a body a hit.
- `agents/v04-p3/artifacts/evidence/grep_context_growth.txt:1`: Sandboxed local run through VirtualFileSystem(InMemoryStorage()) with context 2^31-1. L=250/500/1000/2000/4000 ten-byte lines gave 624,750 / 2,499,500 / 9,999,000 / 39,998,000 / 159,996,000 match-content characters, about 4x per doubling. Peak RSS went from about 126 MB to about 634 MB. With context 0 the output stays at about 0.9 × body. The invert_match variant without allow_scan gave the same 159,996,000 characters at L=4000.

### Conditions

- *authorization_role*: The caller has read visibility on at least one multi-line entry, or write rights to create one. No elevated or system authority is needed.
- *data_state*: The visible body has many lines that count as hits: they match the pattern, or with invert_match they do not match it. The output is about (hit lines) × (body bytes).
- *system_configuration*: The host does not set max_count and does not cap before_context or after_context below the library's INT_CEILING. These are the library defaults.

### Reproduction

**Attacker perspective:** An agent with ordinary read access to the shared vfs host makes one grep call on a readable multi-line file. It sets very large context values and either uses a pattern that matches every line or uses invert_match with a pattern that matches nothing.

Payloads:

- `fs.grep("abc", before_context=2**31-1, after_context=2**31-1)`
- `fs.grep("zzqq_never", invert_match=True, before_context=2**31-1, after_context=2**31-1)`

Instructions:

1. Build VirtualFileSystem(storage=InMemoryStorage()) and write /f.txt containing L short lines, for example 'abc000000\n' repeated with increasing numbers (10 bytes per line).
2. Call fs.grep with before_context=after_context=2**31-1 and the default output_mode='lines' and max_count.
3. Add up len(m.content) over every Match in r.observations and record peak RSS.
4. Repeat for L = 250, 500, 1000, 2000, 4000, and once with context=0 as a control.
5. Run the invert_match payload at L=2000 and L=4000 to show that allow_scan is not needed.

**Observed result:** Run under the sandbox launcher (no network, empty environment, CPU/RSS/wall caps). With context 0 the output was about 0.9 × body at every size. With context 2^31-1 the output was 249.9, 499.9, 999.9, 1999.9 and 3999.9 times the body for L=250 to 4000. At L=4000 a 40 KB body returned 159,996,000 characters in 4,000 Match objects, and peak RSS reached about 634 MB, up from about 126 MB. The invert_match variant without allow_scan gave the same 159,996,000 characters and about 605 MB RSS at L=4000. No truncation warning or error was returned. Output grew about 4x per doubling of L, which is quadratic. Larger bodies were not run; extrapolated, a body of a few hundred KB would exceed host memory.

### Priority

Likelihood medium: It needs only ordinary read access to any multi-line entry and one grep call with two integer arguments. invert_match bypasses the allow_scan refusal. The context values look like normal grep options, and no host-side cap exists in source. The caller must already be a principal the host lets call grep.

Impact medium: A quadratic memory and CPU amplification is allocated in the host process shared by every agent. It was observed reaching 634 MB from a 40 KB body, and it extrapolates to exhausting host memory with modest bodies, which can OOM-kill the process for all tenants. The pydantic Match assembly also blocks the shared event loop. The effect is temporary availability loss with no persistence or data exposure, and a restart recovers it.

Confidence: The source path is direct and was checked line by line. The quadratic growth was reproduced locally through the public VirtualFileSystem API, exactly 4x per doubling, with a context=0 control and an invert_match variant. It ran against the prebuilt _native extension, which the brief assumes matches source.

### Remediation

Bound lines-mode output by the body, not by hits × body. The preferred fix follows ripgrep: when a hit's context window overlaps or touches the previous window, extend the previous window instead of starting a new one, so each body line is emitted at most once per entry. The Match shape may need to carry several match lines per window, or keep per-hit match line numbers that point into a shared window. As defense in depth, add a declared per-call output-byte budget in hits_batch and the Python assembly that truncates with a classified 'truncated' warning, and check the deadline inside the per-body hit loop, not only between bodies.

Sketch for `crates/vfs-core/src/verify.rs`:

```rust
pub fn hit_lines(&self, hay: &[u8], before: u32, after: u32, cap: Option<u64>, invert: bool) -> Vec<Hit> {
    let mut hits: Vec<Hit> = Vec::new();
    let mut emitted = 0u64;
    self.each_hit_line(hay, invert, |ls, le, line_no| {
        let next = extend_context(hay, ls, le, line_no, before, after);
        match hits.last_mut() {
            // Overlapping or adjacent windows merge, so each body byte is emitted at most once.
            Some(prev) if next.span.0 <= prev.span.1 + 1 => {
                prev.span.1 = prev.span.1.max(next.span.1);
                prev.end_line = prev.end_line.max(next.end_line);
            }
            _ => hits.push(next),
        }
        emitted += 1;
        cap.is_none_or(|cap| emitted < cap)
    });
    hits
}
```

## 4. Chained grep over observations runs regex verification on the event loop with no wall, candidate or byte budget, amplified by duplicate rows

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.base._grep_rows_in_hand:inline-unbudgeted-verify`

grep(observations=...) goes to _grep_rows_in_hand. That function reads the content of every listed row that has no content attached, in one self.read call. It then calls match_texts with budget=None, synchronously on the event-loop thread. The storage-tier grep does the same verification work under several controls: a 25,000-candidate budget, 32 MiB content chunks, a 10 s wall deadline, and an offload to an executor (its own comment says 'Verify leaves the loop'). The chained path applies none of these. Rows are not deduplicated, so a caller can list one stored file it may read N times; the file is fetched once and verified N times. Loop occupancy therefore grows linearly with N x body bytes x the per-byte cost of the pattern, and the pattern length has no cap. Every other coroutine on that loop is stalled until the native call returns. That includes every thread sharing one sync VirtualFileSystem facade, which serves all its callers from one loop thread. This was reproduced locally: one stored file of about 0.98 MB, the pattern (\w|\s){60}Q, and 10, 20 and 40 duplicate Observations blocked the loop for 0.65 s, 1.22 s and 2.70 s. The storage-tier scan of the same file and pattern never blocked the loop for more than 13 ms.

### Root cause

_grep_rows_in_hand (src/vfs/base.py:1919) calls pattern_matching.grep.match_texts, which passes budget=None to ContentMatcher.count_lines/hit_lines (src/vfs/pattern_matching/grep.py:252,259). It makes this call inline on the coroutine's thread. It does not use the storage tier's VerifyOffload, byte_chunked(CONTENT_BYTE_BUDGET), CANDIDATE_BUDGET or WALL_TIME_BUDGET controls. The observations list has no length cap and is not deduplicated, and the pattern has no length cap.

### Intended behaviour

Content verification should carry the same bounds whether its rows come from storage or from observations=. That means running off the event loop on the backend's executor, under a wall-time deadline that truncates with a warning, with bodies processed in byte-budgeted batches, and with each distinct body verified at most once per call. The storage tier already declares and enforces exactly this contract.

### Trace

1. **entrypoint** `src/vfs/base.py:1430` `AsyncVirtualFileSystem.grep`: Once the parameter gate passes and observations is not None, grep dispatches to _grep_rows_in_hand (return at line 1433). No row-count cap and no deduplication apply, and the pattern has no length cap.
2. **propagation** `src/vfs/base.py:1911` `AsyncVirtualFileSystem._grep_rows_in_hand`: Every candidate row without content is read in a single self.read(observations=absent) call, with no candidate or byte budget. A row that already carries content needs no read at all.
3. **propagation** `src/vfs/base.py:1919` `AsyncVirtualFileSystem._grep_rows_in_hand`: match_texts runs over every texted row, duplicates included, synchronously on the event-loop thread.
4. **propagation** `src/vfs/pattern_matching/grep.py:252` `match_texts`: verifier.count_lines (or hit_lines at line 259) is called with budget=None, so no deadline exists.
5. **sink** `crates/vfs-core/src/verify.rs:195` `hits_batch / count_batch`: Every body is matched to completion across rayon threads. The binding releases the GIL (python.rs py.detach), but the calling loop thread waits for the whole batch.

### Evidence

- `src/vfs/storage/backends/database/grep.py:120`: The storage tier declares CANDIDATE_BUDGET 25,000, POSTING_BYTE_BUDGET, WALL_TIME_BUDGET 10.0 s, and (line 126) CONTENT_BYTE_BUDGET 32 MiB.
- `src/vfs/storage/backends/database/grep.py:325`: Declared intent, 'Verify leaves the loop'. Line 328 builds VerifyOffload(verifier, executor), and lines 329-354 verify in byte_chunked batches against the deadline.
- `src/vfs/pattern_matching/grep.py:252`: match_texts passes budget=None to the engine (also line 259).
- `crates/vfs-core/src/python.rs:143`: A deadline is built only when a budget is given. Even then, verify.rs checks it only before each body starts.
- `src/vfs/base.py:1811`: _observation_rows only type-checks the batch. It applies no length cap and no deduplication.
- `src/vfs/sync.py:3`: VirtualFileSystem owns one asyncio loop on one daemon thread (lines 647-648). Every thread that calls one facade shares that loop, so a stall on it is shared within the library itself.
- `agents/v05-p3/artifacts/evidence/growth-output.txt:17`: Local run: one 975,000-byte stored file, pattern (\w|\s){60}Q, files mode. The loop was blocked 0.654 s at 10 duplicate rows, 1.222 s at 20 and 2.703 s at 40. The storage scan tier on the same file had a 0.013 s maximum loop gap (line 23).
- `agents/v05-p3/artifacts/evidence/growth.py:1`: The script that produced growth-output.txt. It runs a 1 ms asyncio ticker beside fs.grep(observations=[Observation(path=/data/big.txt)] * N) and records the largest loop gap.
- `agents/v05-p3/artifacts/evidence/patterns-output.txt:1`: Pattern calibration. Literal-prefiltered patterns finished in milliseconds. (\w|\s){60}Q cost about 0.43 s per MB: it blocked the loop on the chained path (gap 0.418-0.465 s) but not on the storage tier (gap 0.012 s).

### Conditions

- *authorization_role*: The caller must hold read on at least one stored file with content. Alternatively it can attach content to the Observations itself, in which case the bytes are its own. Only an ordinary verb argument (observations=) is needed.
- *system_configuration*: The host serves several agents or principals from one AsyncVirtualFileSystem event loop, or from one sync VirtualFileSystem facade (one loop thread by construction), and passes agent-supplied observations and patterns through without a size limit.
- *data_state*: The stall scales with the body bytes in the listed rows and with the pattern's per-byte cost. Patterns with a literal prefilter finish quickly; alternation-under-repetition patterns such as (\w|\s){60}Q are slow.

### Reproduction

**Attacker perspective:** An agent with read access to one roughly 1 MB file, calling grep through a host that shares one vfs event loop among agents.

Payloads:

- `fs.grep(r"(\w|\s){60}Q", observations=[Observation(path=Path("/data/big.txt"), kind="file")] * 40, output_mode="files")`

Instructions:

1. Build AsyncVirtualFileSystem(storage=InMemoryStorage()) and write about 0.98 MB of plain text lines to /data/big.txt.
2. Start a coroutine that sleeps 1 ms in a loop and records the largest gap between wakeups.
3. Await fs.grep with the payload for N = 10, 20 and 40 duplicate rows, recording the largest ticker gap each time.
4. For comparison, await fs.grep with the same pattern and allow_scan=True, output_mode='files'.

**Observed result:** The chained grep blocked the event loop for 0.654 s, 1.222 s and 2.703 s at N = 10, 20 and 40. That is linear in N, while the stored file was fetched once. The storage-tier scan of the same file and pattern took 0.428 s, but the loop was never blocked for more than 0.013 s, because that tier offloads the work. All calls returned success with no errors and no truncation warning.

### Priority

Likelihood medium: It needs only an ordinary grep argument and read access to one file, or caller-held content. The pattern and row count are uncapped and duplicates are not collapsed. Whether many principals share one loop depends on how the host deploys vfs.

Impact medium: This is a temporary availability loss. Every coroutine and every sync-facade caller sharing the loop stalls for a time proportional to N x body size x pattern cost, with no deadline; about 2.7 s was observed at N=40 on 1 MB, and it grows linearly. Nothing persists and no data is exposed, and the loop recovers when the call returns. The synchronous native call cannot be cancelled.

Confidence: The full trace was checked in source. The storage tier's declared off-loop contract confirms the chained path diverges from intent. The linear loop stall was reproduced locally with a sandboxed, bounded run against InMemoryStorage. The one fact this record leaves to the deployment is how many principals the host puts on one loop.

### Remediation

Route chained verification through the same controls as the storage tier. First, verify each distinct (path, body) pair once and fan the result out to duplicate rows. Second, run the matcher off the loop through VerifyOffload on an executor, or through asyncio.to_thread when no backend executor is available. Third, pass a wall-time deadline derived from WALL_TIME_BUDGET and truncate with a warning when it trips. Fourth, process bodies in byte_chunked(CONTENT_BYTE_BUDGET) batches, checking the deadline between batches. A host-side cap on observations length and pattern length is additional defense in depth.

Sketch for `src/vfs/base.py`:

```python
# in _grep_rows_in_hand, replacing the inline match_texts call
deadline = monotonic() + WALL_TIME_BUDGET
unique: dict[tuple[str, str], int] = {}
bodies: list[tuple[Path, str]] = []
for row, text in texted:
    key = (str(row.path), text)
    if key not in unique:
        unique[key] = len(bodies)
        bodies.append((row.path, text))
hits_unique, completed = await match_texts_offloaded(
    bodies, verifier, invert=invert_match, before=before_context, after=after_context,
    mode=output_mode, cap=max_count, deadline=deadline,
)  # executor-run, byte-chunked, budget=deadline - monotonic() per batch
hits = [hits_unique[unique[(str(row.path), text)]] for row, text in texted]
# append a 'wall-time budget' truncation warning when not completed
```

## 5. Glob patterns compile to backtracking Python regex with no cap on wildcards, so one glob call can stall the shared event loop

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.pattern_matching.glob._translate:backtracking-wildcards`

A caller who can run glob, or grep/glean with glob channels, sends a short pattern with k wildcard pairs such as '*?' repeated k times, plus a '[...]' class. vfs turns each '*' into a backtracking [^/]* and compiles it with CPython re. Matching against one stored name of length n then costs roughly O(n^k). The match runs synchronously on the asyncio event loop for every candidate row, and it runs before the visibility check (view.shows). So rows the caller cannot see still cost time. The '[' class makes the SQL LIKE prefilter fall back to an empty literal prefix plus '%', so every live row in the mount is a candidate. The path-segment cap of 255 bytes bounds n for each name. Nothing bounds k or the pattern length. Local reproduction on a fresh InMemoryStorage with the default caller: '*?*?*?*?[Q]' against one 250-character name blocked the loop for 0.85 s, and '*?*?*?*?*?*?[Q]' against one 64-character name blocked it for 0.54 s. A concurrent unrelated glob had to wait the whole time. Cost also grows linearly with the number of candidate rows: 10 rows with 128-character names took 0.61 s, against 0.07 s for one.

### Root cause

_translate and _translate_component (src/vfs/pattern_matching/glob.py) emit [^/]* for each '*' and (?:.+/)? for each non-final '**', with no limit on how many wildcards or how long the pattern is. compile_glob compiles the result with Python re, which backtracks, instead of the linear-time Rust regex engine that vfs-core already uses for grep. glob_rows runs passes_row_filters, and so the regex, inline on the event loop for every SQL candidate, before view.shows, with no deadline. _glob_like returns None for any '[' class, so the prefilter matches every row.

### Intended behaviour

Glob matching should take time linear in the subject length, as the Rust regex engine used by grep does. Otherwise it should be bounded by a wildcard or pattern-length cap and a deadline, so one caller's glob cannot block other agents on the same loop.

### Trace

1. **entrypoint** `src/vfs/base.py:1263` `AsyncVirtualFileSystem.glob`: Public verb that accepts a caller pattern string. Neither it nor the params gate caps pattern length or wildcard count.
2. **propagation** `src/vfs/storage/backends/database/reads.py:523` `pattern_arm`: _glob_like returns None for a '[' class, so the prefilter becomes escape_like(literal_prefix) + '%'. With an empty literal prefix, every live row in the mount is a SQL candidate.
3. **propagation** `src/vfs/storage/backends/database/reads.py:368` `glob_rows`: passes_row_filters runs the compiled glob regex on each candidate row, synchronously on the loop, before view.shows (line 370) applies visibility.
4. **sink** `src/vfs/pattern_matching/glob.py:555` `_translate_component`: Each '*' becomes the backtracking [^/]*. compile_glob (line 208) compiles it with Python re.compile, which gives O(n^k) failing matches.

### Evidence

- `src/vfs/pattern_matching/glob.py:208`: compile_glob returns re.compile(_translate(_canonical(pattern), recursive=True)), which uses the backtracking CPython engine.
- `src/vfs/pattern_matching/glob.py:536`: A non-final '**' component becomes (?:.+/)?, which also backtracks across segments of path-subject patterns.
- `src/vfs/storage/backends/database/reads.py:985`: _glob_like returns None whenever '[' appears in the pattern, which disables the selective LIKE prefilter.
- `src/vfs/pattern_matching/glob.py:39`: The strongest pattern-side control: MAX_PATTERN_ARMS = 64 caps brace expansion only. It does not cap wildcard count or pattern length.
- `src/vfs/paths.py:41`: MAX_SEGMENT_LENGTH = 255 bytes caps n for each name-subject match, but it does not cap the polynomial degree k. At n=250, k=4 already costs about 0.85 s for each row.
- `agents/v06-p3/artifacts/evidence/glob_backtracking_verify.txt:7`: Verifier's sandboxed reproduction. k=4 at n=64/128/250 took 0.014/0.070/0.854 s, k=6 at n=48/64 took 0.12/0.54 s, and 10 rows at k=4, n=128 took 0.61 s. The largest event-loop gap and a concurrent victim glob's latency each matched the attacking glob's duration. The benign control '*.txt' took 0.016 s.

### Conditions

- *authorization_role*: The caller can invoke glob, or grep/glean with glob channels, on a mount. The reproduction used the default router caller on a fresh InMemoryStorage. Visibility does not gate the cost, because the regex runs before view.shows.
- *data_state*: The mount holds rows whose names or path segments are tens of characters or longer (up to 255 bytes for each segment). Cost scales with the number of live rows in the mount, because the '[' class disables the prefilter.
- *system_configuration*: The host serves several agents or callers from one process and asyncio event loop, so a stall on that loop delays every other caller.

### Reproduction

**Attacker perspective:** An agent with glob access to an AsyncVirtualFileSystem whose event loop is shared with other agents.

Payloads:

- `'*?*?*?*?[Q]' against a stored name of 'a' * 250`
- `'*?*?*?*?*?*?[Q]' against a stored name of 'a' * 64`

Instructions:

1. Inside the sandbox, build AsyncVirtualFileSystem(storage=InMemoryStorage()) and write one file whose leaf name is n characters long (n <= 255), plus an unrelated small file.
2. Start a 1 ms asyncio ticker and a concurrent victim task that globs '/small.txt'.
3. Await fs.glob(payload) and record the glob duration, the largest gap between ticker wakeups, and the victim's glob latency. Compare with a benign '*.txt' glob.

**Observed result:** Python 3.13.11. For k=4: 0.014 s at n=64, 0.070 s at n=128 and 0.854 s at n=250. For k=6: 0.12 s at n=48 and 0.54 s at n=64. With k=4, n=128, 10 rows took 0.61 s. Each call returned zero rows and no errors. The largest event-loop gap was within a few ms of each glob's duration (for example 0.848 s at k=4, n=250). The concurrent victim glob took the same 0.85 s. The benign '*.txt' glob over the same 10 rows took 0.016 s. A 256-byte segment was refused (the segment cap), which bounds n but not k.

### Priority

Likelihood medium: The payload is a short string and needs only glob access, which the default caller on a fresh storage has. A shared-loop, multi-agent host is the intended deployment, but vfs is a library, and whether the loop is shared depends on the host.

Impact medium: Each call blocks the shared event loop for every co-hosted agent, for up to about a second for each long-named row at k=4 and more for larger k or more rows. The stall is temporary and recovers when the call ends. Repeated calls can sustain it. There is no persistence, and no effect on confidentiality or integrity.

Confidence: The verifier reproduced the result independently through the public glob API in the sandbox, with bounded growth points and a concurrent victim. Every trace line was checked against source at commit 3586750.

### Remediation

Compile glob regexes with the linear-time Rust regex engine already in vfs-core, or with a non-backtracking glob matcher, for compile_glob, compile_filter and _component_matches. Until then, refuse patterns above a declared wildcard count and pattern length in glob_defect/expand_pattern. Also consider applying view.shows before the regex, or running the per-row matching under the same deadline grep uses. Add a regression test that runs a fixed adversarial pattern and asserts on an operation count (matcher calls or steps), not on time.

## 6. Repeated docx footnote or comment references copy the full note text inline before the character budget applies

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.rendering.docx:note-reference-inline-expansion`

The docx renderer writes a note's text inline at each footnoteReference or commentReference. _Writer._inline makes a fresh formatted copy of the full note text for every reference, keeps every copy in a list, joins them into one string, and only then hands that string to Builder.paragraph. Builder.paragraph runs sanitize() and splitlines() over the whole string before _append checks any budget. So a paragraph that repeats one reference N times to a note of L characters builds about N x L characters in memory, plus further copies, before RenderLimits.chars or the ratio guard can act. This grows with the product of two values the writer chooses, not with the decompressed input. Repeated references and repeated note text compress almost to nothing. In the sandbox, a 2,783-byte docx (one 10,000-character footnote, 10,000 references) reached a traced peak of 191.5 MiB inside DocxRenderer.render. The growth was linear: 1.9 MiB at 100 references, 19.2 MiB at 1,000 and 191.5 MiB at 10,000. A 13,970-byte docx built the same way (a 100,000-character note, 100,000 references) implies 10^10 inline characters, about 10 GB. That case was built and measured only, not rendered. Rendering runs in DatabaseStorage.reindex on the offload pool of the host process that all agents share. Because the copies build up one note at a time rather than in one huge allocation, the likely end is that the OS kills the process or the host swaps heavily, not a MemoryError that the registry would catch. A killed render never lands its stamp, so the row stays render_status='pending' and every later reindex renders it again.

### Root cause

_Writer._inline (src/vfs/rendering/docx.py:131-149) appends _note(...) for every footnoteReference and commentReference with no limit on how many copies or how many characters it collects. Each _note call formats a new string holding the full note text (docx.py:152-154). The result is ''.join(parts), built in full before Builder sees it. Builder enforces RenderLimits.chars and the ratio guard only per line in _append (markdown.py:275-289), after paragraph() has already run sanitize(text).splitlines() over the whole string (markdown.py:180). The ratio guard compares output characters with the compressed input size, and only after the text exists.

### Intended behaviour

RenderLimits.chars (2 MiB by default) and the ratio guard should bound what a renderer builds, not only what it emits. The docx module docstring says 'the character budget bounds a document'. Inline note assembly should stop once the paragraph can no longer fit in the Builder's remaining budget, or write each note's text once and mark later references by id, so that memory stays within a small multiple of the budget whatever the reference count.

### Trace

1. **entrypoint** `src/vfs/storage/backends/database/writes.py:1181` `write row staging`: A caller with write rights stores docx bytes through the write verb. There is no body-size cap, and the row is marked render_status='pending'.
2. **propagation** `src/vfs/storage/backends/database/backend.py:1287` `DatabaseStorage._render_step`: The operator's reindex selects every dirty bytes row, with no authority filter, and renders it through render_rows on the shared offload pool (call_offloaded at line 1288).
3. **propagation** `src/vfs/rendering/docx.py:117` `_Writer.paragraph`: text, pictures = self._inline(paragraph._p): the whole paragraph string is built before the Builder is called.
4. **sink** `src/vfs/rendering/docx.py:144` `_Writer._inline`: parts.append(_note('footnote', ...)) runs for every footnoteReference (and line 146 for commentReference). Each call is a fresh copy of the full note text, and line 149 joins them all with no budget.

### Evidence

- `src/vfs/rendering/docx.py:152`: _note formats f' [{kind} {note_id}: {text}]' with the whole note text on every call.
- `src/vfs/rendering/markdown.py:180`: Builder.paragraph runs sanitize(text).splitlines() over the whole joined string before any per-line budget check.
- `src/vfs/rendering/markdown.py:280`: The character budget and, at line 287, the ratio guard are checked only per appended line, after the text has been built.
- `src/vfs/rendering/registry.py:107`: The registry catches only Exception. An OS kill of the process or heavy swapping is not caught, so the row stays pending.
- `agents/v07-p3/artifacts/evidence/run.txt:1`: Sandbox run with a 10,000-character footnote. Traced peak inside DocxRenderer.render: 0.2 MiB at 0 references, 1.9 MiB at 100, 19.2 MiB at 1,000 and 191.5 MiB at 10,000. Input size stayed between 1,505 and 2,783 bytes.
- `agents/v07-p3/artifacts/evidence/size.txt:1`: Size-only build, not rendered: a 13,970-byte docx (100,000-character note, 100,000 references) implies 10^10 inline characters, and a 15,713-byte docx (1,000,000-character note) implies 10^11.
- `agents/v07-p3/artifacts/evidence/repro.py:1`: The reproduction script. It builds a minimal docx with dummy text and measures tracemalloc peak during DocxRenderer().render with the default RenderLimits.

### Conditions

- *authorization_role*: The attacker is a principal with write rights to some path on a DatabaseStorage or InMemoryStorage mount that stores bytes bodies.
- *system_configuration*: The vfs[docx] extra (python-docx) is installed, so the docx renderer is active.
- *timing_dependency*: The operator or host later runs reindex(), the only place rendering happens. The cost lands on that maintenance job and on the host process that all agents share, not on the writer's own call.

### Reproduction

**Attacker perspective:** An agent or user with ordinary write rights uploads a small docx, a few kilobytes compressed. Its footnotes part holds one long footnote, and its body has one paragraph that repeats a reference to that footnote many times.

Payloads:

- `word/footnotes.xml: <w:footnotes><w:footnote w:id="1"><w:p><w:r><w:t>{10,000 chars of 'lorem ipsum '}</w:t></w:r></w:p></w:footnote></w:footnotes>`
- `word/document.xml: <w:document><w:body><w:p>{'<w:r><w:footnoteReference w:id="1"/></w:r>' x 10,000}</w:p></w:body></w:document>`

Instructions:

1. Build a minimal docx zip: [Content_Types].xml, _rels/.rels, word/_rels/document.xml.rels (with a footnotes relationship), word/document.xml and word/footnotes.xml as in the payloads, compressed with ZIP_DEFLATED.
2. Call DocxRenderer().render(RenderSource(data, DOCX, 'dummy.docx'), RenderLimits()) under tracemalloc. This is the same call that render_rows makes during reindex.
3. Repeat with 0, 100, 1,000 and 10,000 references and record the traced peak memory against the input size.

**Observed result:** Traced peak memory grew linearly with the reference count: 1.9, 19.2 and 191.5 MiB for 100, 1,000 and 10,000 references. The input stayed at 1,560 to 2,783 bytes, so the 10,000-reference case built about 70,000 bytes in memory for each input byte. The render then returned 'empty' or 'failed' only after that memory had been allocated. Larger cases were not executed; only their input sizes were measured. This shows memory amplification in one render. It does not show a process crash, because no run was taken to OOM.

### Priority

Likelihood medium: Ordinary write rights and a payload of a few kilobytes are enough, and there is no body-size cap. Rendering still waits for an operator-run reindex, and the writer cannot trigger it.

Impact medium: Memory in the host process that all agents share grows with the product of reference count and note length. A 14 KB input implies about 10 GB. If the process is killed, the row stays pending and is retried on every reindex, so the file keeps failing the job. The impact is availability of a shared host and its maintenance job, with no disclosure and no integrity loss. The OOM end state was inferred from linear growth and was not observed.

Confidence: The source path is direct and has no control before the join. I independently reproduced linear memory growth at bounded sizes using the real DocxRenderer and default RenderLimits, inside the sandbox, with dummy data.

### Remediation

Bound inline assembly in _Writer._inline. Write each note's full text only the first time it is referenced, and mark later references by id alone. Also stop collecting parts once the running length passes the Builder's remaining character budget, so no paragraph string can exceed a small multiple of RenderLimits.chars. Add a test that counts the characters (or tracemalloc bytes) built for a paragraph with many repeated references, rather than timing it.

Sketch for `src/vfs/rendering/docx.py`:

```python
    def _inline(self, element: Any) -> tuple[str, list[str | None]]:
        """The paragraph's text with each note written once at its first reference, bounded by the budget."""
        parts: list[str] = []
        pictures: list[str | None] = []
        size = 0
        cap = self._builder.remaining + 1
        for node in element.iter():
            tag = node.tag
            piece: str | None = None
            if tag == f"{_W}t":
                piece = node.text or ""
            elif tag == f"{_W}tab":
                piece = "\t"
            elif tag in (f"{_W}br", f"{_W}cr"):
                piece = "\n"
            elif tag == f"{_W}footnoteReference":
                piece = self._note_once("footnote", node.get(f"{_W}id"), self._notes.footnotes)
            elif tag == f"{_W}commentReference":
                piece = self._note_once("comment", node.get(f"{_W}id"), self._notes.comments)
            elif tag == f"{_WP}docPr":
                pictures.append(node.get("descr") or node.get("title") or node.get("name"))
            if piece is not None and size <= cap:
                parts.append(piece)
                size += len(piece)
        return "".join(parts), pictures

    def _note_once(self, kind: str, note_id: str | None, texts: dict[str, str]) -> str:
        key = (kind, note_id)
        if key in self._written:
            return f" [{kind} {note_id}]"
        self._written.add(key)
        return _note(kind, note_id, texts)

# with self._written: set[tuple[str, str | None]] = set() in __init__, and a Builder.remaining
# property returning max(0, self._budget - self._chars)
```

## 7. A docx table cell's gridSpan value expands into an unbounded cell list before any render limit applies

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.rendering.docx:table-gridspan-expansion`

_Writer.table builds rows = [[cell.text for cell in row.cells] for row in table.rows] and only then hands the rows to Builder.table. In the installed python-docx 1.2.0, _Row.cells yields the same _Cell once for each grid column the cell spans (iter_tc_cells: for _ in range(tc.grid_span): yield cell). grid_span is read straight from the w:tcPr/w:gridSpan/@val integer and is never compared with the table's real grid width. The renderer then calls cell.text once for each yielded entry, and each call builds a new string. So one attribute in a document of about 36 KB decides how many tuple entries, cell.text calls and list strings get created. All of this work finishes before Builder sees the first row. The character budget, the ratio guard, the unit cap and the cooperative clock (RenderLimits.seconds, checked only at block boundaries and between table rows) therefore do not bound it. The bytes come from any principal allowed to write(data=...) to a DatabaseStorage mount; the write stores them as render_status='pending'. The expansion runs later, when the operator calls reindex(). It runs on the backend's in-process ThreadPoolExecutor, the pool that grep's verify stage also uses, and a running worker cannot be interrupted. Local run: input size held constant at about 36.7 KB (36,703 to 36,705 bytes), gridSpan raised from 1e3 to 1e6. cell.text calls grew exactly linearly (1,000 to 1,000,000). Peak RSS rose from 113.6 MiB to 473.0 MiB. Wall time was about 22 s against RenderLimits(seconds=1.0); this is informational only. Spans of 1e5 and above also return status 'empty' with no text, because the header line alone overflows the character budget. Correction to the hunter's wording: a render that completes lands a terminal state and is not retried. A row stays pending, and is retried on every reindex, only when the span is large enough that the render never finishes or the process dies. The schema allows values up to 2^31-1. That size was not executed: by extrapolation it is more than 16 GiB of tuple pointers alone, plus hours of CPU.

### Root cause

DocxRenderer's table path builds the span-expanded row.cells tuple and one cell.text string per grid position, with no cap and no clamp to the table's declared grid width. RenderLimits are enforced only inside Builder, on text it emits. The materialization runs as one uninterruptible step on the offload thread, before any of those checks.

### Intended behaviour

A render's memory and CPU should stay bounded by RenderLimits and roughly proportional to the input bytes. Per the seam's own docstring, a malformed or hostile docx should end as a classified 'truncated' or 'failed' state within the time budget, not do work set by an attribute value.

### Trace

1. **entrypoint** `src/vfs/base.py:958` `AsyncVirtualFileSystem.write`: A lower-trust caller with write rights stores arbitrary docx bytes through write(data=...)
2. **propagation** `src/vfs/storage/backends/database/writes.py:1181` `bytes write staging`: The bytes row is stored with render_status='pending' and is not rendered in the writer's call
3. **propagation** `src/vfs/storage/backends/database/backend.py:1288` `DatabaseStorage._render_step`: The operator's reindex() renders every pending bytes row via render_rows on the in-process offload ThreadPoolExecutor (call_offloaded)
4. **propagation** `src/vfs/storage/backends/database/render.py:294` `render_rows`: Each pending row goes to registry.render with the configured RenderLimits
5. **propagation** `src/vfs/rendering/registry.py:107` `RendererRegistry.render`: Dispatches to DocxRenderer.render; only an Exception raised from inside the renderer becomes a state
6. **propagation** `src/vfs/rendering/docx.py:63` `DocxRenderer.render`: Each body table block goes to _Writer.table after a single boundary() clock check
7. **sink** `src/vfs/rendering/docx.py:128` `_Writer.table`: rows = [[cell.text for cell in row.cells] for row in table.rows] creates one tuple entry and one cell.text string per spanned grid column, with the count set by w:gridSpan/@val, before Builder.table checks any budget

### Evidence

- `src/vfs/rendering/docx.py:128`: The full row matrix is materialized before self._builder.table(rows) runs; there is no cap on len(row.cells) and no clamp to the table grid
- `src/vfs/rendering/markdown.py:191`: Builder.table checks out_of_time() and the character budget only while emitting rows that already exist
- `src/vfs/rendering/seam.py:67`: RenderLimits caps characters, ratio, embedded objects, units and seconds; none of these bounds parsed structure size or work done before Builder
- `src/vfs/storage/backends/database/engine.py:237`: The offload pool is an in-process ThreadPoolExecutor shared with grep's verify stage, so memory and CPU exhaustion affects the whole host process
- `agents/v08-p3/artifacts/evidence/gridspan-growth.jsonl:4`: Sandboxed run, constant 36,703 to 36,705-byte input: gridSpan 1e3/1e4/1e5/1e6 gives cell.text calls of exactly 1e3/1e4/1e5/1e6 and peak RSS of 113.6/117.2/148.6/473.0 MiB; wall time 22.4 s at 1e6 against a 1.0 s limit
- `agents/v08-p3/artifacts/evidence/gridspan.py:30`: The harness: builds a 1x1 docx with python-docx, sets w:gridSpan/@val, counts _Cell.text calls, and calls RendererRegistry.bundled().render(RenderSource(data, DOCX, 'a.docx'), RenderLimits(seconds=1.0))
- `agents/f08-p5/artifacts/evidence/gridspan-recheck.jsonl:3`: Independent Phase 5 sandbox rerun at gridSpan 1e6 on a 36,718-byte input: 1,000,001 cell.text calls, status 'empty', peak RSS 476.2 MiB, wall 22.4 s (informational) against RenderLimits(seconds=1.0)
- `agents/f08-p5/artifacts/evidence/gridspan-fixcheck.jsonl:2`: The corrected remediation, patched in under the sandbox: the same gridSpan 1e6 input renders 'ok' with 1 cell.text call; on a 3x3 table with a horizontal and a vertical merge it emits text identical to the current renderer

### Conditions

- *authorization_role*: The attacker can write bytes entries to a DatabaseStorage mount (any subject with write rights on some path)
- *system_configuration*: The vfs[docx] extra (python-docx) is installed, so the docx renderer is available
- *user_interaction*: The operator or host later runs DatabaseStorage.reindex(), the only place rendering happens
- *third_party_dependency*: python-docx 1.2.0 _Row.cells expands a horizontal span into grid_span repeated cells, taken from the unvalidated w:gridSpan/@val

### Reproduction

**Attacker perspective:** A lower-trust agent or ETL writer with ordinary write rights stores one small .docx entry. The renderer cost lands later on the operator's reindex, in the host process that all agents share.

Payloads:

- `A word/document.xml holding one table, one w:tc whose w:tcPr contains <w:gridSpan w:val="1000000"/> and a paragraph of 100 characters (about 36 KB zipped)`

Instructions:

1. Build a 1x1 table docx with python-docx, put 100 characters in the cell, and append w:gridSpan with w:val=N to the cell's w:tcPr
2. Call RendererRegistry.bundled().render(RenderSource(data, DOCX, 'a.docx'), RenderLimits(seconds=1.0)) in the sandbox, counting _Cell.text calls and reading ru_maxrss
3. Repeat for N = 1e3, 1e4, 1e5, 1e6 with the input size held constant, and stop there (no larger values)

**Observed result:** Input stayed at 36,703 to 36,705 bytes. cell.text calls equalled N exactly (1,000 to 1,000,000). Peak RSS grew from 113.6 MiB to 473.0 MiB. Wall time at N=1e6 was 22.4 s against RenderLimits.seconds=1.0, so the clock did not stop the expansion. Statuses were 'ok' for 1e3 and 1e4, and 'empty' ('no text in 1 units') for 1e5 and 1e6. Work and memory grow linearly with the attribute value, not with the input size. An independent Phase 5 rerun (two-row table, the same 100-character cell) reproduced it: 1,000,001 cell.text calls, status 'empty', peak RSS 476.2 MiB, 22.4 s against seconds=1.0.

### Priority

Likelihood medium: Any principal with write rights can plant the payload; it is trivial and a few KB. It needs the docx extra installed and fires only when the operator runs reindex, which is routine maintenance.

Impact medium: Memory and CPU on the operator's reindex grow linearly with an attribute value up to 2^31-1. They run in the in-process offload pool shared with every agent's grep, and that work cannot be interrupted. Observed: 473 MiB and 22 s at 1e6. Extrapolated, not executed: process-wide OOM or hours-long stalls at the maximum, and an un-landed row that is retried on every reindex. This is availability only; no data is disclosed or changed.

Confidence: The source path is verified line by line. The library behaviour was read from the installed python-docx 1.2.0, and linear growth at constant input size was reproduced in the approved sandbox with counted calls. Only the maximum-span process exhaustion is extrapolated, not observed. An independent Phase 5 rerun reproduced the linear growth, and the corrected fix was executed against both the attack input and a merged-cell table.

### Remediation

Do not iterate python-docx's span-expanded row.cells. Walk each row's w:tc elements directly. Compute each cell's text once. Clamp each span to the table's declared grid width (len(tblGrid.gridCol_lst), which is proportional to the parsed input) and to the columns that remain in the row. Then repeat the already computed string, so the row length is bounded by the grid actually present. For a vMerge='continue' cell, reuse the text already collected at the same grid position in the row above, which keeps python-docx's current output without its recursive walk. docx.py imports python-docx lazily (DocxRenderer.library), so the cell class must be handed to _Writer from render(); the record's earlier fixed_code referenced a nonexistent self._docx and, when run, turned every docx table into a 'failed' render with AttributeError. Optionally check builder.out_of_time() between rows during collection; the builder already remembers the timeout and classifies the rendering as partial at build().

Sketch for `src/vfs/rendering/docx.py`:

```python
# In DocxRenderer.render: hand the lazily imported library's cell class to the writer.
        writer = _Writer(builder, _Notes(document), docx.table._Cell)

# In _Writer:
    def __init__(self, builder: Builder, notes: _Notes, cell: Any) -> None:
        self._builder = builder
        self._notes = notes
        self._cell = cell
        self._pictures = 0

    def table(self, table: Any) -> None:
        grid = max(1, len(table._tbl.tblGrid.gridCol_lst))
        rows: list[list[str]] = []
        for tr in table._tbl.tr_lst:
            if rows and self._builder.out_of_time():
                break
            above = rows[-1] if rows else []
            cells: list[str] = []
            for tc in tr.tc_lst:
                if len(cells) >= grid:
                    break
                at = len(cells)
                if tc.vMerge == "continue":
                    text = above[at] if at < len(above) else ""
                else:
                    text = self._cell(tc, table).text
                cells.extend([text] * max(1, min(tc.grid_span, grid - at)))
            rows.append(cells)
        self._builder.table(rows)
```

## 8. An xlsx sheet's declared dimension and far-off row index drive padded cell iteration that the render clock never checks

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.rendering.xlsx:dimension-driven-row-iteration-unclocked`

XlsxRenderer opens workbooks with read_only=True. In openpyxl 3.1.5, ReadOnlyWorksheet takes max_column and max_row from the sheet's <dimension ref>. Then _cells_by_row yields a padding row (one shared tuple of max_column EMPTY_CELLs) for every missing row between two populated rows. vfs's _cells() walks every yielded cell and checks no clock, cell budget or row budget. The deadline is consulted only after _cells returns, in Builder.table and Builder.unit. So a file of about 4.7 KB, with one cell at A1, one cell at A<R> and a dimension of A1:ZZZ<R>, makes one render iterate 18,278 x R cells. Columns are capped at ZZZ (18,278) by openpyxl; the row index is a plain int with no cap. Measured in the sandbox, with RenderLimits(seconds=0.5): 365,560,000 cells took 3.24 s, and 50,000,000 padded rows took 3.34 s, both about 6.5x over the limit. Cost is linear at about 9 ns per cell, so A1:ZZZ1048576 projects to roughly 170 s, and a row index of 10^8 projects to hours, all against the 60 s RENDER_SECONDS default. This happens during the operator's reindex, on an offload worker that cannot be interrupted. The single-runner reindex lease keeps its heartbeat, so the lease stays held and every other subject's pending render, chunk and posting work waits behind it. The row is landed only after its cut finishes, so a run that is abandoned leaves the row pending, and the next reindex starts the same work again. Correction to the hunter: an empty sheetData, or a lone A1 with a huge dimension, does NOT pad. openpyxl's tail-padding guard is 'max_row < idx' (_read_only.py:100), so the trailing rows are never yielded; this was measured as 26 cells for dimension A1:Z100000 with only A1. The attack needs a second populated row at the far end, which uses the in-between gap padding (_read_only.py:92).

### Root cause

_cells() (src/vfs/rendering/xlsx.py:161-172) walks sheet.iter_rows() over openpyxl's dimension-padded read-only grid. It takes no Builder, deadline or cell or row budget. The cooperative clock in Builder covers only the Builder calls that come after _cells has collected the whole sheet. So the iteration work grows with the declared extent (columns x row gap), not with the input bytes, and no RenderLimits field bounds it.

### Intended behaviour

RenderLimits.seconds (RENDER_SECONDS, 'Wall seconds one render may spend before the text so far is kept as partial') should bound each render. Once the clock runs out, an xlsx render should stop within a small constant amount of work and return partial. The work should be proportional to the cells actually stored, not to the dimension or row numbers the file declares.

### Trace

1. **entrypoint** `src/vfs/storage/backends/database/writes.py:1181` `write staging (row values)`: A caller with write rights stores arbitrary bytes. The row is staged with render_status='pending', with no body-size or content-shape check on xlsx structure.
2. **propagation** `src/vfs/storage/backends/database/backend.py:1288` `DatabaseStorage._render_step`: Operator reindex (under the single-runner lease claimed at backend.py:1140-1143) selects every dirty bytes row and runs render_rows on the offload pool through call_offloaded. It awaits until the worker finishes.
3. **propagation** `src/vfs/rendering/xlsx.py:87` `XlsxRenderer.render`: After load_workbook(read_only=True), each sheet calls _cells(sheet) before any Builder clock check runs on its tables.
4. **sink** `src/vfs/rendering/xlsx.py:164` `_cells`: for row in sheet.iter_rows(): for cell in row: walks every padded EMPTY_CELL that openpyxl yields (max_column wide, one row per missing index), with no deadline or budget.

### Evidence

- `src/vfs/rendering/xlsx.py:161`: _cells takes only the sheet. No limits object or Builder is passed, so it cannot see the deadline.
- `src/vfs/rendering/markdown.py:128`: Builder.out_of_time is the only clock. It is called from boundary/unit and between table rows (markdown.py:191 table), all after _cells returns.
- `src/vfs/storage/backends/database/offload.py:24`: Offload law: a worker that is already running finishes into the void. No protocol-level interrupt exists.
- `src/vfs/storage/backends/database/backend.py:1143`: The reindex holds a heartbeating single-runner lease around the render stage, so one stalled render blocks every reindex for all subjects while it runs.
- `agents/v09-p3/artifacts/evidence/xlsx-dimension-probe.json:1`: Sandbox run, openpyxl 3.1.5, input about 4.7 KB in every case. A lone A1 with dimension A1:Z100000 yields 26 cells, so tail padding does not happen. A1+A<R> with A1:Z<R> yields 26R cells (R = 1e3, 1e4, 1e5). A1+A4000 with A1:XFD4000 yields 65,536,000 cells, takes 0.564 s and returns partial against a 0.5 s limit.
- `agents/v09-p3/artifacts/evidence/xlsx-dimension-overshoot.json:1`: Sandbox run: A1+A20000 with dimension A1:ZZZ20000 iterates 365,560,000 cells, render wall 3.243 s against limit 0.5 s (6.5x). A1+A50000000 with dimension A1:A50000000 takes 3.339 s (6.7x). Constant 4.7 KB input; time grows linearly with the declared extent.

### Conditions

- *authorization_role*: The attacker holds write rights on some path in a DatabaseStorage or InMemoryStorage mount, so it can store a bytes entry sniffed as xlsx. Any named subject or agent with write access qualifies.
- *third_party_dependency*: The vfs[xlsx] extra (openpyxl 3.1.5) is installed, so the xlsx renderer is registered and not 'unavailable'.
- *system_configuration*: The operator or host runs DatabaseStorage.reindex(), which is the only place rendering happens.

### Reproduction

**Attacker perspective:** A lower-trust writer (an agent or subject with write access to one path) uploads one small xlsx. A later operator reindex, shared by all subjects on the host, renders it.

Payloads:

- `xl/worksheets/sheet1.xml = <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:ZZZ20000"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c></row><row r="20000"><c r="A20000" t="inlineStr"><is><t>x</t></is></c></row></sheetData></worksheet> (inside an otherwise standard openpyxl-generated workbook zip, about 4.7 KB)`

Instructions:

1. Create a one-cell workbook with openpyxl and save it to bytes.
2. Rewrite xl/worksheets/sheet1.xml with the payload: a dimension of A1:ZZZ<R> and populated rows 1 and R.
3. Call XlsxRenderer().render(RenderSource(data, XLSX, 's.xlsx'), RenderLimits(seconds=0.5)) and time it. In deployment, write the bytes and run reindex().
4. Raise R, or use a dimension of A1:A<huge> with populated rows 1 and <huge>, to scale the time linearly with no input growth.

**Observed result:** With limit 0.5 s, the render took 3.243 s for R=20000 at ZZZ width (365,560,000 cells), and 3.339 s for a 50,000,000-row gap at width 1. Both came back 'partial' ('0 of 1 units within 0.5 seconds') only after _cells had finished. Input size stayed about 4.7 KB. No further escalation was attempted.

### Priority

Likelihood medium: It needs only ordinary write access and one file of about 5 KB with no special configuration beyond the xlsx extra. Reindex is a routine operator job, and the pending row is picked up again on every run.

Impact medium: Availability only. One render overruns the 60 s clock by a factor the attacker chooses (minutes to hours), on an offload worker that cannot be interrupted. Meanwhile the heartbeating single-runner reindex lease stays held, so every subject's render, chunk and posting maintenance stalls, and one offload worker shared with grep verify is busy. Memory stays bounded, because the padding is one shared tuple. There is no confidentiality or integrity effect, and an operator can recover by deleting the entry.

Confidence: The source path is verified end to end, and the behaviour was reproduced in the sandbox against the installed openpyxl 3.1.5 and the repo's XlsxRenderer: time grows linearly with the declared extent at constant input size and overshoots the limit. The hunter's empty-sheetData variant was refuted, and the record is corrected to the gap-padding trigger.

### Remediation

Bound the walk by stored cells and by the clock. Call sheet.reset_dimensions() before iterating, so openpyxl stops padding rows to the declared dimension width. Then pass the Builder into _cells, check builder.out_of_time() every N rows, and stop with a partial result when the clock runs out. That way both wide padding and huge row gaps end within the deadline. Add a regression test that counts the cells or rows _cells visits (not wall time) for a tiny file with a huge dimension and row gap.

Sketch for `src/vfs/rendering/xlsx.py`:

```python
_CLOCK_EVERY: Final = 1024

def _cells(sheet: Any, builder: Builder) -> Cells | None:
    """``(row, column) → text`` for every stored cell of *sheet*; ``None`` once the clock runs out."""
    sheet.reset_dimensions()  # padding follows stored cells, never the declared dimension
    cells: Cells = {}
    for index, row in enumerate(sheet.iter_rows(), 1):
        if index % _CLOCK_EVERY == 0 and builder.out_of_time():
            return None
        for cell in row:
            value = cell.value
            if value is None:
                continue
            text = _cell_text(value)
            if text:
                cells[cell.row, cell.column] = text
    return cells

# in XlsxRenderer.render:
#     cells = _cells(sheet, builder)
#     if cells is None:
#         break
```

## 9. xlsx region layout does quadratic work on writer-shaped cell layouts before any render budget applies

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.rendering.xlsx:region-table-quadratic-materialization`

A subject that can write a bytes entry stores a small .xlsx file. The operator's reindex later renders it with the bundled XlsxRenderer, on the shared offload pool inside the host process. regions() joins cells that touch by side or by corner. So an L-shape (R cells down column A, then C cells across the last row) or a diagonal of n cells becomes one region whose bounding box is R x C, or n x n. _table() then builds the whole box as Python lists, header plus body, (bottom-top+1) x (right-left+1) entries, before Builder.table() emits its first row. The character budget, the output/input ratio guard and the clock are only checked inside Builder, so they act after that allocation has already happened. Observed locally: a 56,977-byte workbook made 32,012,001 table entries and a 270.9 MB traced peak during DatabaseStorage.reindex() on SQLite, and the rendering still landed as 'rendered'. Doubling both sides quadrupled the peak (68.7 MB, then 270.9 MB), while the file grew less than 2x. Separately, _merged() compares each region box with every box already kept, so k isolated cells cost k(k-1)/2 overlap checks: 400 cells made 79,800 calls and 6,400 cells made 20,476,800. That work also runs before any budget and never reads the clock. The module docstring says the region pass is linear. Neither of these two steps is linear.

### Root cause

In src/vfs/rendering/xlsx.py, _table() builds every grid position of a region's bounding box as a list of lists, and _merged() does pairwise overlap checks over all region boxes. Both run in full before control reaches Builder, and Builder is the only place RenderLimits (chars, ratio, seconds) are enforced. Box area and region count depend on how the writer lays out cells, not on the input size or on the output budget.

### Intended behaviour

Per the xlsx module docstring and RenderLimits: one render holds memory linear in a sheet's non-empty cell count, the region pass is linear, and the character budget and wall clock bound the work spent on any one rendering, so a small input cannot make the renderer allocate or compute far beyond what it can emit.

### Trace

1. **entrypoint** `src/vfs/storage/backends/database/backend.py:686` `DatabaseStorage.write`: A lower-trust subject with write rights stores arbitrary .xlsx bytes. No body-size or cell-layout check applies to write data.
2. **propagation** `src/vfs/storage/backends/database/writes.py:1181` `staged row values`: The bytes row is stored with render_status 'pending', so a later reindex picks it up.
3. **propagation** `src/vfs/storage/backends/database/backend.py:1288` `DatabaseStorage._render_step`: The operator's reindex runs render_rows on the shared offload pool with call_offloaded. A worker that is already running cannot be interrupted.
4. **propagation** `src/vfs/storage/backends/database/render.py:294` `render_rows`: registry.render(RenderSource(data, row.mime, row.name), limits) dispatches to the bundled XlsxRenderer.
5. **propagation** `src/vfs/rendering/xlsx.py:88` `XlsxRenderer.render`: for box in regions(cells): builder.table(_table(cells, box, ...)). Both regions() and _table() run before Builder sees any row.
6. **propagation** `src/vfs/rendering/xlsx.py:120` `regions`: Joining cells that touch by corner turns a diagonal or an L-shape of O(R+C) cells into one region with an R x C bounding box.
7. **propagation** `src/vfs/rendering/xlsx.py:137` `_merged`: Each box is checked against every box already kept: O(k^2) overlap checks over k regions, with no clock or budget check.
8. **sink** `src/vfs/rendering/xlsx.py:157` `_table`: The body list comprehension builds every grid position of the bounding box, area R x C, before Builder.table applies the character or time budget.

### Evidence

- `src/vfs/rendering/xlsx.py:157`: body = [[str(row), *(cells.get((row, column), '') for column in columns)] for row in range(box.top, box.bottom + 1)] is built in full and returned as a list.
- `src/vfs/rendering/xlsx.py:143`: The inner loop 'for other in out: if merged.overlaps(other)' runs once per kept box for each new box, which is quadratic in the number of regions.
- `src/vfs/rendering/xlsx.py:17`: The module docstring states 'the region pass is linear too' (and regions() at line 106 claims union-find makes it linear). _merged and _table contradict this.
- `src/vfs/rendering/markdown.py:191`: Builder.table takes an already-built Sequence. It computes width = max(len(row) for row in rows), and only then checks the clock and the character budget per row (lines 198-204), after the full table exists.
- `src/vfs/rendering/seam.py:43`: RENDER_CHARS is 2 MiB and RENDER_SECONDS is 60. Both are enforced only through Builder, so neither bounds _table or _merged.
- `src/vfs/rendering/registry.py:46`: RendererRegistry.bundled() includes XlsxRenderer, and DatabaseStorage uses it by default (backend.py:234). The renderer is active wherever openpyxl is installed.
- `agents/v10-p3/artifacts/evidence/xlsx-growth.json:1`: Direct XlsxRenderer.render under default RenderLimits, with each <dimension> element removed. L 2000x1000 (18,775 B): 2,003,001 entries, 20.6 MB peak. L 4000x2000 (30,928 B): 8,006,001 entries, 68.3 MB. L 8000x4000 (56,978 B): 32,012,001 entries, 270.7 MB, status truncated. Diagonal n=500/1000/2000: 251,001 / 1,002,001 / 4,004,001 entries; the ratio guard failed the larger two only after materialization. Isolated grids of 400 / 1,600 / 6,400 cells: 79,800 / 1,279,200 / 20,476,800 overlap calls.
- `agents/v10-p3/artifacts/evidence/xlsx-e2e-reindex.json:1`: End to end through DatabaseStorage.write and reindex on SQLite. Control workbook (3 cells): 0.71 MB peak. L 4000x2000 (30,928 B): 68.7 MB peak. L 8000x4000 (56,977 B): 270.9 MB peak, 32,012,001 table entries. Each reindex succeeded and reported the row as rendered.

### Conditions

- *authorization_role*: The attacker is a named subject or service with write rights on some path of a DatabaseStorage mount. Any writer can store arbitrary bytes there.
- *third_party_dependency*: openpyxl (the vfs[xlsx] extra) is installed, so the bundled XlsxRenderer is available. Version 3.1.5 was observed.
- *system_configuration*: The host or operator runs DatabaseStorage.reindex() in the same process that serves agents. That is the shipped design: offload pool threads in the host process.
- *data_state*: The stored workbook's sheet XML omits the <dimension> element (or declares a small one), so openpyxl's read-only iterator does not pad every row to the full width and the quadratic cost falls on vfs's _table rather than on the library.

### Reproduction

**Attacker perspective:** A lower-trust writer stores a few tens of kilobytes of .xlsx. They wait for the operator's routine reindex to render it on the host process that all agents share.

Payloads:

- `An .xlsx with one sheet: numeric cells at A1..A8000 plus row 8000 columns B..ER (4,000 columns total), and <dimension> removed from xl/worksheets/sheet1.xml. That is 11,999 cells and 56,977 bytes.`
- `An .xlsx with one sheet of k isolated cells at (2i+1, 2j+1), for example an 80x80 grid of 6,400 cells, to drive _merged's pairwise loop.`

Instructions:

1. Build the workbook with openpyxl write_only mode, then rewrite the zip without the <dimension .../> element.
2. Under tools/sandbox-run.py: DatabaseStorage(url='sqlite+aiosqlite:///<scratch>/b.sqlite').write(entries=[Entry(path=Path('/u/b.xlsx'), data=payload)], parents=True).
3. Start tracemalloc, await storage.reindex(), and record the traced peak. Wrap xlsx._table to count the entries it returns, and wrap Box.overlaps to count calls.
4. Repeat at half size (4000x2000) and with a 3-cell control to see the growth.

**Observed result:** Reindex peak traced memory was 0.71 MB for the 3-cell control, 68.7 MB for 4000x2000 (30,928 B) and 270.9 MB for 8000x4000 (56,977 B). _table returned 32,012,001 entries for the last one, and its rendering landed as 'rendered' (text truncated at about 2.09M chars). Memory grew about 4x per doubling, against under 2x growth in file size. Isolated-cell grids made exactly k(k-1)/2 overlap calls (20,476,800 at k=6,400) before any budget or clock check. Larger sizes were not run, to stay inside the 2 GiB sandbox cap.

### Priority

Likelihood medium: Any subject with write rights can plant the file, and it is small (under 60 KB) and easy to build. It needs the openpyxl extra, and it fires only when the operator runs reindex, which is routine maintenance. A row whose render never finishes stays pending and is retried on every reindex.

Impact medium: Memory and CPU grow quadratically in the shared host process, before any RenderLimits check. 57 KB produced a 271 MB peak, and each further doubling quadruples it, so a few hundred KB can reach multiple GB. The isolated-cell layout drives unbounded uninterruptible CPU on a worker. This is availability only, for the reindex job and the host process shared by agents. No confidentiality or integrity effect. Process OOM at production scale was inferred from the measured growth, not observed.

Confidence: The source path is direct and the defaults activate it. The quadratic growth was reproduced twice inside the sandbox with operation counts and traced memory: directly on the renderer, and end to end through write and reindex on SQLite. The control and the doubling series rule out a constant overhead.

### Remediation

Make the xlsx table path stream rows and stop against the output budget. Make the region merge sub-quadratic or check the clock. (1) Turn _table into a generator that yields the header and then one body row at a time. Change Builder.table to accept an iterable plus an explicit width, so its existing per-row clock and character checks run before the next row is built. Rows needed is then bounded by the remaining budget divided by about 4*width, and width is at most 18,278 because of get_column_letter. (2) Replace _merged's all-pairs loop with a sweep over boxes sorted by top, keeping an interval structure on columns, or at least pass the Builder and check out_of_time()/budget inside the loop and in regions(). (3) Fix the module and regions() docstrings so they describe the real complexity. Add operation-count tests (entries built, overlap calls) at two sizes, asserting linear growth.

Sketch for `src/vfs/rendering/xlsx.py`:

```python
def _table(cells: Cells, box: Box, column_letter: Any) -> Iterator[list[str]]:
    """One region as table rows, lazily: letters across, row numbers down, blanks empty."""
    columns = range(box.left, box.right + 1)
    yield ["", *(column_letter(column) for column in columns)]
    for row in range(box.top, box.bottom + 1):
        yield [str(row), *(cells.get((row, column), "") for column in columns)]

# caller: builder.table(_table(cells, box, letter), width=box.right - box.left + 2)
```

Sketch for `src/vfs/rendering/markdown.py`:

```python
def table(self, rows: Iterable[Sequence[object]], *, width: int | None = None) -> bool:
    """A GFM pipe table whose first row is the header; rows are pulled one at a time."""
    if self.stopped:
        return False
    if width is None:
        rows = list(rows)
        if not rows:
            return True
        width = max(len(row) for row in rows)
    self._blank()
    for index, row in enumerate(rows):
        if index and self.out_of_time():
            self._open = False
            return False
        cells = [table_cell(value) for value in row] + [""] * (width - len(row))
        if not self._text("| " + " | ".join(cells) + " |"):
            return False
        if index == 0 and not self._append("|" + " --- |" * width):
            return False
    self._blank()
    return True
```

## 10. OOXML parts are fully decompressed into host memory before any render limit applies, so a small docx can cost hundreds of times its size in RSS during reindex

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs.rendering:ooxml-part-decompression-unbounded`

The docx and pptx renderers pass the stored bytes straight to docx.Document and pptx.Presentation. vfs checks no zip entry sizes, compression ratios or member counts first. When python-docx 1.2.0 opens a package, it walks every internal relationship and calls ZipFile.read on each target part. python-pptx 1.0.2 goes further and reads every zip member, referenced or not, into a dict. Every RenderLimits check runs inside Builder, on output characters, after this expansion has already happened. The RENDER_RATIO comment calls the ratio the decompression-bomb guard, but a part that decompresses large and yields no text never reaches it. Rendering runs on the DatabaseStorage offload ThreadPoolExecutor, which is inside the host process all agents share. I reproduced this locally. One docx stored at 442,096 bytes, holding one relationship-referenced 400 MiB part of zeros, raised peak RSS by 805 MiB in a direct registry render and by 807 MiB in a real write-then-reindex on SQLite. That is about 1,900 times the stored size. The render still returned status ok with text 'hello quokka', and no limit fired. Because deflate tops out near 1000:1 and the library holds the blob, a stored body of a few MiB can be enough to exhaust the host's memory.

### Root cause

DocxRenderer.render (docx.py:50) and PptxRenderer.render (pptx.py:38) open caller-supplied zip containers with libraries that eagerly decompress part blobs (docx/opc/pkgreader.py:79 via phys_pkg.py:83 ZipFile.read; pptx/opc/serialized.py:195 reads every member). vfs does no central-directory inspection before that call. Every RenderLimits check (chars, ratio, units, seconds) lives in Builder, which measures emitted text after expansion, so input-side decompression has no bound at all.

### Intended behaviour

A render's memory should be bounded by declared limits relative to the stored input, as the seam's 'decompression-bomb guard' comment says. An OOXML body whose declared total uncompressed size, single-entry size, member count or compression ratio exceeds a RenderLimits cap should be refused as a classified 'failed' or 'corrupt' state before the parsing library decompresses anything.

### Trace

1. **entrypoint** `src/vfs/storage/backends/database/backend.py:1287` `DatabaseStorage._render_step`: During reindex, each dirty bytes row that any writer stored through write(data=...) gets rendered. render_rows runs on the shared offload ThreadPoolExecutor via call_offloaded at line 1288, inside the host process.
2. **propagation** `src/vfs/models/media.py:89` `sniff_mime`: The PK\x03\x04 magic marks the body as a zip, and the .docx/.pptx extension or the declared type then selects the Office media type and its renderer (lines 108-111).
3. **sink** `src/vfs/rendering/docx.py:50` `DocxRenderer.render`: docx.Document(BytesIO(source.data)) runs with no prior zip inspection. python-docx reads every relationship-referenced part fully into memory. pptx.py:38 has the same shape, and python-pptx reads every member.

### Evidence

- `src/vfs/rendering/seam.py:44`: The comment at lines 44-45 calls RENDER_RATIO 'the decompression-bomb guard', but every RenderLimits field bounds output or the walk, never decompressed input.
- `src/vfs/rendering/markdown.py:287`: The ratio check compares emitted characters (self._chars) with ratio * input_bytes after parsing. A large part that yields no text is invisible to it.
- `src/vfs/rendering/pptx.py:38`: pptx.Presentation(BytesIO(source.data)) has no prior inspection. The installed python-pptx 1.0.2 _ZipPkgReader._blobs (pptx/opc/serialized.py:192-195) reads every zip member into a dict, including unreferenced ones. This is source-read only; I did not run the pptx path.
- `src/vfs/storage/backends/database/engine.py:227`: The offload_executor property returns a ThreadPoolExecutor (constructed at line 237), so the decompressed blobs are allocated in the shared host process, not in an isolated worker.
- `agents/v11-p3/artifacts/evidence/ooxml-part-bomb-rss.txt:1`: Sandboxed reproduction log and scripts. A 442,096-byte docx with one 400 MiB referenced part grew max RSS by 805 MiB in a registry render and by 807 MiB in a DatabaseStorage write-then-reindex; render_status stayed ok. The 34,419-byte control docx grew it by 5 MiB.

### Conditions

- *authorization_role*: The attacker is any principal allowed to write a bytes body into a DatabaseStorage-backed mount (for example a named agent subject with write rights). The cost is not paid in the writer's call.
- *system_configuration*: The vfs[docx] or vfs[pptx] extra is installed, so a bundled Office renderer is available. The operator or host runs DatabaseStorage.reindex(), which is routine index maintenance.
- *data_state*: The stored body starts with PK\x03\x04 and carries an Office extension or declared type, so sniff_mime selects DOCX or PPTX. For docx, the large part must be a relationship target; for pptx, any zip member works.
- *third_party_dependency*: This depends on how python-docx 1.2.0 and python-pptx 1.0.2 load parts, which is eager and unbounded. I observed this for python-docx only. For python-pptx it comes from reading the source. openpyxl (read_only=True) was not shown to be affected.

### Reproduction

**Attacker perspective:** A lower-trust writer stores one small docx. Inside it is a highly compressible part that the main document's relationships point to. Later, the operator's reindex renders it inside the host process that every agent shares.

Payloads:

- `docx built from tests.support.documents.docx_bytes(['hello quokka']), plus [Content_Types].xml <Default Extension="bin" ContentType="application/octet-stream"/>, plus a word/_rels/document.xml.rels <Relationship Id="rIdBig" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/big.bin"/>, plus word/media/big.bin = 400 MiB of 0x00, deflate level 9; stored size 442,096 bytes`

Instructions:

1. Build the payload with scratch build.py (args 400 bomb400.docx), and build a control with args 0 base.docx.
2. Under tools/sandbox-run.py, run render.py on each file. It calls RendererRegistry.bundled().render(RenderSource(data, DOCX, 'x.docx'), RenderLimits()) and records ru_maxrss before and after.
3. Under tools/sandbox-run.py, run e2e.py on bomb400.docx. It opens DatabaseStorage on a scratch SQLite file, writes /up/report.docx with data=..., records ru_maxrss around reindex(), and then stats render_status.
4. Stop at that first clear ratio. Do not scale the payload toward OOM.

**Observed result:** Control docx (34,419 bytes): RSS grew by 5 MiB. Payload docx (442,096 bytes), direct render: status ok, text 'hello quokka', max RSS 106 MiB before and 912 MiB after, a growth of 805 MiB, which is 1,909.6 times the stored bytes. End to end: write succeeded, reindex succeeded, render_status was ok, and max RSS grew by 807 MiB during reindex. No RenderLimits check fired.

### Priority

Likelihood medium: It needs only ordinary write rights to a database mount and a routine operator reindex with the Office extras installed. The attacker's work is tiny: a 442 KB file, made with standard tools.

Impact medium: I observed about 1,900x memory amplification in the host process that every agent shares, and no limit fired. Extrapolation says a few MiB stored is enough for multi-GiB allocations, which could OOM the shared process during maintenance. I did not demonstrate OOM itself, or that the row stays pending after a crash. The effect is availability only, with no data exposure.

Confidence: For docx, both the direct renderer and the real DatabaseStorage write-then-reindex path reproduced the result, measured against a control. For pptx, the eager read of every member was confirmed in the installed library source but not executed. For xlsx, the effect was not established.

### Remediation

Before calling any OOXML library, open the body with zipfile.ZipFile and inspect infolist(). Refuse with a classified failed/corrupt Rendering when any of these exceeds a declared RenderLimits field: the member count, any entry's file_size, the sum of file_size, or the file_size/compress_size ratio. Because a central directory can lie, also bound the actual decompression, either by streaming each member through a size-capped reader or by trusting only the verified caps. Apply the same pre-check to xlsx for defense in depth. Then correct the RENDER_RATIO comment so that it describes an output guard.

Sketch for `src/vfs/rendering/seam.py`:

```python
import zipfile
from io import BytesIO

RENDER_PACKAGE_BYTES: Final = 256 * 1024 * 1024
RENDER_PACKAGE_MEMBERS: Final = 10_000
RENDER_MEMBER_RATIO: Final = 200


@dataclass(frozen=True)
class RenderLimits:
    """The caps one render runs inside; a host may lower them, never raise the ratio."""

    chars: int = RENDER_CHARS
    ratio: int = RENDER_RATIO
    embedded_depth: int = RENDER_EMBEDDED_DEPTH
    embedded_count: int = RENDER_EMBEDDED_COUNT
    pages: int = RENDER_PAGES
    seconds: float = RENDER_SECONDS
    package_bytes: int = RENDER_PACKAGE_BYTES
    package_members: int = RENDER_PACKAGE_MEMBERS
    member_ratio: int = RENDER_MEMBER_RATIO
    # __post_init__ also checks the three new fields are positive


def package_refusal(data: bytes, limits: RenderLimits) -> str | None:
    """Why a zip container is refused before any library decompresses it, or None."""
    try:
        infos = zipfile.ZipFile(BytesIO(data)).infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        return f"not a zip container: {exc}"
    if len(infos) > limits.package_members:
        return f"{len(infos)} members exceed {limits.package_members}"
    total = sum(i.file_size for i in infos)
    if total > limits.package_bytes:
        return f"{total} uncompressed bytes exceed {limits.package_bytes}"
    for i in infos:
        if i.file_size > RENDER_RATIO_FLOOR and i.file_size > limits.member_ratio * max(1, i.compress_size):
            return f"{i.filename} expands {i.file_size}/{i.compress_size}"
    return None
```

Sketch for `src/vfs/rendering/docx.py`:

```python
from vfs.rendering.seam import BundledRenderer, Rendering, failure, failure_from, package_refusal

...
        refusal = package_refusal(source.data, limits)
        if refusal is not None:
            return failure("failed", refusal)
        try:
            document = docx.Document(BytesIO(source.data))
```

Sketch for `src/vfs/rendering/pptx.py`:

```python
        refusal = package_refusal(source.data, limits)
        if refusal is not None:
            return failure("failed", refusal)
        try:
            presentation = pptx.Presentation(BytesIO(source.data))
```

## 11. Caller-authored content_hash is stored unverified and keys cross-principal render lending

**Severity:** medium (likelihood low, impact medium). **Confidence:** high. **Fingerprint:** `vfs/storage/database/write-trusts-caller-authored-content-hash`

AsyncVirtualFileSystem.write(entries=[...]) stores the content_hash carried on a caller-built Entry without measuring the body storage holds. A bodiless bytes Entry (data=None, source='bytes') keeps any hash the caller names. This works with plain JSON-shaped model_validate dicts and needs no MEASURED_BODY context. The reindex render stage then lends a settled rendering per (content_hash, generation) from any row. The donor query has no owner, rights or deleted_at term. The landing guard compares the key only with the receiving row's own stored hash, which the attacker forged. Two cross-principal effects follow, and both reproduce locally. First, disclosure: a principal with no rights on another principal's file, who knows that file's sha-256, gets its rendered text in a row they own, readable through read and grep. A wrong guess stays pending, so the same write is an existence oracle. Second, integrity: a principal writes their own bytes, then overwrites the row bodiless under the hash of a known public document. The old blob stays, reindex renders the attacker's bytes, and the result is stamped under the forged hash. When another principal later uploads the real document, reindex serves them the attacker's text as their file's content, through read and grep. From source, the same trust also lets a contributor stop the version minting on overwrite (versions.py skips a pre-image whose hash equals the staged hash). The hunter reports that variant as executed; this verifier did not re-run it.

### Root cause

write_rows (writes.py:163) passes entry.content_hash, entry.size_bytes and entry.lines from the caller's Entry into WritePlan.put_file, and _material_values (writes.py:1172) persists them. Entry._derive_and_measure (entry.py:232, 242) measures only when data is not None or source=='text', so a bodiless bytes Entry keeps the caller's hash. _replace_bodies (writes.py:987) skips a row with no content and no data, so a bodiless overwrite keeps the old blob under the new hash. No layer re-measures. render.py treats content_hash as proof of byte identity in two places: when cached_renderings picks a donor, and when land_renderings guards the stamp.

### Intended behaviour

A row's content_hash must always be the hash of the body storage holds for it. A content-kind write with neither content nor data must be refused, or must keep the stored row's measured metrics. Render dedup and version dedup must key only on hashes that storage measured itself. A tombstoned row must not lend its rendering.

### Trace

1. **entrypoint** `src/vfs/base.py:958` `AsyncVirtualFileSystem.write`: Public verb. It accepts entries=, an iterable of caller-built Entry objects, from any named or anonymous Authority.
2. **propagation** `src/vfs/base.py:2601` `AsyncVirtualFileSystem._route_entry_batch`: Checks only that each item is an Entry, then path-gates and write-gates it. without_mount uses model_copy, which does not re-validate or re-measure.
3. **propagation** `src/vfs/models/entry.py:232` `Entry._derive_and_measure`: Measures bytes only when data is not None, and text only when source=='text' (line 242). A source='bytes' Entry with data=None keeps the caller's content_hash and mime_type.
4. **propagation** `src/vfs/storage/backends/database/writes.py:163` `write_rows`: Passes entry.content_hash, size_bytes and lines unchanged into plan.put_file.
5. **propagation** `src/vfs/storage/backends/database/writes.py:1172` `_material_values`: Writes the staged caller hash into the entry row. _replace_bodies (line 987) skips bodiless rows, so any earlier blob stays under the forged hash.
6. **propagation** `src/vfs/storage/backends/database/render.py:206` `cached_renderings`: Selects the lowest-id settled donor per (content_hash, generation). Its predicates are hash, source, stamp and status only: no owner, rights or deleted_at term.
7. **propagation** `src/vfs/storage/backends/database/render.py:287` `render_rows`: Reuses the cached or in-page rendering for any row whose (content_hash, generation) key matches, without reading that row's blob.
8. **sink** `src/vfs/storage/backends/database/render.py:342` `land_renderings`: The stamp guard requires only that the receiving row's own content_hash equals the key. A forged hash passes, so the lent text is inserted as that row's content and is served by read, grep and glean.

### Evidence

- `src/vfs/models/entry.py:242`: The text branch measures with measure_text unless MEASURED_BODY is supplied. The bytes branch at line 232 runs only when data is not None. Nothing measures a bodiless bytes entry.
- `src/vfs/storage/backends/database/writes.py:987`: Only rows that have content or data count as bearing. A bodiless overwrite leaves the prior blob in place under the newly written hash.
- `src/vfs/storage/backends/database/render.py:206`: The donor WHERE clause filters on hash membership, source, render_source_hash == content_hash, generation and settled status. It has no principal or deleted_at filter.
- `src/vfs/storage/backends/database/versions.py:145`: A pre-image version is skipped when its measured hash equals staged.content_hash, which is the caller's value.
- `src/vfs/storage/backends/database/reads.py:107`: A caller with list-level rights sees only path and kind, so the hash does not leak there. The attacker must learn H some other way, for example from a public or shared document.
- `agents/v15-p3/artifacts/evidence/verify-output.txt:1`: Verifier's own sandboxed run on InMemoryStorage. dave gets not_found on /carol/n.pdf, then gets carol's text CAROL-PRIVATE note 98765 at /dave/y.pdf after a bodiless JSON-shaped Entry and a reindex (cached=1). In the reverse run, carol's upload of a public PDF is served dave's PLANTED text (cached=1).

### Conditions

- *authorization_role*: The attacker is a named subject with write rights on some path in the same mount as the victim's file. No rights on the victim's path are needed.
- *data_state*: Disclosure requires the attacker to know the exact sha-256 of the victim's bytes, for example a shared or leaked document. Poisoning requires the hash of a document the victim will later upload, such as a public form. It also requires the attacker's row to be the lowest-id settled donor for that hash, for example by planting first.
- *system_configuration*: The operator runs reindex on the storage. This is routine: reindex is what produces any bytes rendering at all.

### Reproduction

**Attacker perspective:** Named subject dave with read_write only on /dave. The posture on / is none. Victim carol has read_write on /carol.

Payloads:

- `Entry.model_validate({'path':'/dave/y.pdf','source':'bytes','content_hash':H_carol,'mime_type':'application/pdf'})`
- `fs.write(path='/dave/p.pdf', data=<dave's PDF>) followed by Entry.model_validate({'path':'/dave/p.pdf','source':'bytes','content_hash':H_public,'mime_type':'application/pdf'})`

Instructions:

1. On InMemoryStorage, mkdir /carol and /dave as system, set posture / to none, and grant carol and dave read_write on their own prefixes.
2. carol writes a dummy PDF at /carol/n.pdf. Run storage.reindex(). Confirm dave's read of /carol/n.pdf returns not_found.
3. dave writes the bodiless Entry naming carol's hash at /dave/y.pdf. Run reindex. dave reads /dave/y.pdf and greps for carol's text.
4. On a fresh storage, dave writes his own PDF at /dave/p.pdf, then overwrites it bodiless with the hash of a public PDF. Run reindex. carol uploads the public PDF at /carol/b.pdf. Run reindex. carol reads and greps her file.

**Observed result:** In dave's control read, /carol/n.pdf returned vfs.not_found. After the bodiless write and a reindex (rendering report cached=1), dave's read of /dave/y.pdf returned render_status ok with content 'CAROL-PRIVATE note 98765', and dave's grep for it hit /dave/y.pdf. In the reverse case, after reindex (cached=1), carol's read of /carol/b.pdf returned render_status ok with content 'PLANTED text by dave', and carol's grep for PLANTED hit her own file. The hunter separately reports that a forged-hash overwrite in a contribute region minted 0 versions, against 1 for an honest overwrite. This verifier did not re-run that variant.

### Priority

Likelihood low: The attacker needs a writable path on the victim's mount and the exact hash of the target bytes. For disclosure, that mostly means a shared or leaked document. For poisoning, the hash of a public document is easy to get, but the attacker must plant first to be the lowest-id donor.

Impact medium: The effect crosses a principal boundary in both directions. In one direction it discloses rendered text and gives an existence oracle. In the other it substitutes attacker-chosen text for another principal's file content, which reaches that principal's agents through read and grep. The version-skip variant also lets a contributor stop history from being minted.

Confidence: The full source lineage was re-read at commit 3586750. The verifier independently reproduced both the disclosure and the poisoning variants in the sandbox, through the public router API with only JSON-shaped Entry dicts and dummy principals. No spec or docstring declares a caller-supplied hash trusted; spec 175 lists integrity-on-read as not yet built.

### Remediation

Measure at the storage seam. In write_rows, refuse a content-kind Entry that has neither content nor data, or ignore its metrics and keep the stored row's. Always compute content_hash, size_bytes and lines from the staged body in the storage layer, on the offload pool when the body is large, and never take them from the Entry. Make MEASURED_BODY router-internal, for example a private sentinel object rather than a public context key. Add entry.deleted_at IS NULL to the cached_renderings donor query. Once every hash is measured by storage, cross-row render lending is safe without a rights term.

Sketch for `src/vfs/storage/backends/database/writes.py`:

```python
# in write_rows, before plan.put_file:
if entry.kind in CONTENT_KINDS and entry.content is None and entry.data is None:
    plan.errors.append(classified(ErrorKind.invalid, entry.path, detail='a file write needs a body'))
    continue
metrics = measure_bytes(entry.data) if entry.data is not None else measure_text(entry.content)
# pass metrics.content_hash / metrics.size_bytes / metrics.lines instead of entry.*
```

Sketch for `src/vfs/storage/backends/database/render.py`:

```python
# in cached_renderings, the donor WHERE clause:
entry.c.deleted_at.is_(None),
```

## 12. edit's fuzzy replacers run quadratic pure-Python matching on the event loop inside the writer transaction, with no size, count or time bound

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs/storage/replace.py:fuzzy-replacers-quadratic-inline-in-writer-transaction`

A principal that may modify one text entry, for example a file it just wrote itself, can send an edit whose old string does not match exactly. replace() then falls back to the fuzzy replacers in src/vfs/storage/replace.py. Three costs there grow with the square of the input. First, block_anchor_replacer scans forward from every first-anchor line to the end of the file when the last anchor never appears, which is O(L^2) in lines. Second, its similarity step runs a full-matrix pure-Python Levenshtein, which is O(M^2) in the length of the middle line. Third, line_trimmed_replacer recomputes each match's start offset with an O(i) sum, and replace() then computes a line number and splits the whole content again for every match when it builds the multi-match error, so L matches cost O(L^2). edit_rows calls this code synchronously inside the coroutine, once per target, inside the writer transaction (BEGIN IMMEDIATE on SQLite). InMemoryStorage also serializes every session behind one asyncio.Lock. Nothing caps the length of old or new, the number of edits, the number of targets, or the wall time. So one small call freezes the host's shared event loop for every other agent in the process, and holds the mount's write lock the whole time. Every probe failed with vfs.invalid and committed nothing, so the attacker does not need a successful edit. Measured independently through the public verb: a 24 KB file with a 5-byte old string stalled the loop for 2.6 s (block_anchor). A 24 KB file with a 3-byte old string stalled it for 4.0 s (line_trimmed). A 4.8 KB request stalled it for 1.2 s (Levenshtein). Each doubling of input cost about 3.7x to 4.1x.

### Root cause

replace() falls back to line_trimmed_replacer and block_anchor_replacer whenever the exact search misses. block_anchor_replacer's forward scan (replace.py:179-185) only stops when it finds the last anchor, so an absent last anchor makes it O(L^2). levenshtein (replace.py:61-82) builds a full O(n*m) Python matrix with no length cap, and calculate_similarity calls it for every middle line of every candidate. line_trimmed_replacer (replace.py:145) and replace()'s multi-match error builder (replace.py:321-325, which calls get_line_number and get_context_lines; the latter splits the whole content each time) recompute offsets and context for every match. edit_rows (writes.py:261) runs edited_entry inline in the async writer transaction for every target, with no call_offloaded, no deadline and no input caps. That differs from glean, indexing and signals, which do offload their CPU-bound work.

### Intended behaviour

An edit's matching cost should stay bounded: close to linear in the sizes of the content and of old. Fuzzy fallback should be refused, or capped, once it would exceed a declared work budget. CPU-bound matching should run off the event loop through call_offloaded with a deadline, the way the reindex, glean and signals paths already do. It should also run before the writer lock is taken, or at least not hold that lock for an unbounded time, so one caller cannot stall other principals sharing the host.

### Trace

1. **entrypoint** `src/vfs/base.py:1016` `AsyncVirtualFileSystem.edit`: The public verb takes caller-supplied path/observations plus old/new or an edits list. _gate_params (1031-1041) checks only types, then the call routes to storage at 1057.
2. **propagation** `src/vfs/params.py:173` `PARAM_SPECS['edit']`: old and new are typed 'str', edits is an EditOperation list and observations is a list. None has a length or count limit.
3. **propagation** `src/vfs/storage/backends/database/backend.py:734` `DatabaseStorage.edit`: After the rung gate and the per-target modify check, edit_rows runs inside _execute_write (745). That is a writer transaction, opened BEGIN IMMEDIATE on SQLite (1666-1673).
4. **propagation** `src/vfs/storage/backends/database/writes.py:261` `edit_rows`: edited_entry runs synchronously in the coroutine for every target. A failed target appends an error and the loop continues to the next target.
5. **propagation** `src/vfs/storage/editing.py:38` `edited_entry`: apply_edits (replace.py:342-355) passes every EditOperation through replace().
6. **propagation** `src/vfs/storage/replace.py:287` `replace`: An exact miss falls through to line_trimmed_replacer and then block_anchor_replacer. When there are many matches, 321-325 compute a line number and the context lines for each one, splitting the whole content every time.
7. **sink** `src/vfs/storage/replace.py:182` `block_anchor_replacer`: When the last anchor is absent, the forward scan runs from each first-anchor line to the end of the file, O(L^2). calculate_similarity then calls levenshtein (202, defined 61-82), which is O(M^2) per middle line.

### Evidence

- `src/vfs/storage/replace.py:179`: The nested loop over content_lines breaks only when the last anchor matches.
- `src/vfs/storage/replace.py:66`: levenshtein allocates and fills a full (len(a)+1)x(len(b)+1) Python list matrix, with no length cap.
- `src/vfs/storage/replace.py:145`: line_trimmed_replacer recomputes start_pos with an O(i) sum for every match.
- `src/vfs/storage/replace.py:324`: get_context_lines splits the whole content and counts newlines in a prefix, once per match, while building the multi-match error.
- `src/vfs/storage/backends/database/writes.py:261`: edited_entry is called inline in the coroutine with no call_offloaded. Compare indexing.py:330, glean.py:872 and signals.py:123, which do offload.
- `src/vfs/storage/backends/database/backend.py:1666`: _execute_write opens the writer transaction (BEGIN IMMEDIATE on SQLite) and holds it across edit_rows.
- `src/vfs/params.py:173`: The edit parameter specs declare no maximum for old, new, edits or observations.
- `src/vfs/storage/backends/database/engine.py:722`: On InMemoryStorage, _SerializedSessions puts every session behind one asyncio.Lock, so other principals' operations also queue behind the edit.
- `agents/v16-p3/artifacts/evidence/verify_edit.txt:1`: Phase 3 verifier's own sandboxed run through the public edit verb. Edit time grows about 4x per doubling for all three shapes. The longest event-loop gap equals the edit time. A control exact edit on a 16 KB file took 20 ms with a 3.5 ms gap.
- `agents/f15-p5/artifacts/evidence/probe.txt:1`: Phase 5 verifier's independent sandboxed reproduction (script agents/f15-p5/artifacts/evidence/probe.py). On InMemoryStorage it reproduces the same three quadratic shapes: anchor 2.5 s, lev 1.1 s with 5764801 cells, trim 3.9-4.0 s at the largest size, loop gap equal to edit time. On file-backed SQLite DatabaseStorage, a separate connection's BEGIN IMMEDIATE (timeout 0) issued 150 ms into each longer edit was refused with 'database is locked', which confirms the writer lock is held across the matching.

### Conditions

- *authorization_role*: The caller needs modify rights on at least one text entry, for example a file it wrote itself. No rights over other principals' data are needed.
- *system_configuration*: The host process serves several agents or principals from one event loop and mount, which is the embedded-library model. The writer-lock effect applies to SQLite-backed mounts and to InMemoryStorage's serialized sessions. On other engines the event-loop stall remains. The host must also not impose its own cap on edit argument or file size; vfs itself has none.
- *data_state*: The target's content and the old string are shaped to miss exactly and reach a quadratic fuzzy path. Three shapes work: many lines equal to the first anchor with the last anchor absent; one candidate whose long middle line differs; or many lines that match a whitespace-trimmed single-line old.

### Reproduction

**Attacker perspective:** A named principal (alice) has ordinary write and modify rights on her own file in a shared AsyncVirtualFileSystem over InMemoryStorage. Another principal (carol) reads her own file concurrently on the same loop.

Payloads:

- `write /a12000.txt content='a\n'*12000; edit(path='/a12000.txt', old='a\nx\nb', new='z')`
- `write /l2400.txt content='a\n'+'x'*2400+'\nb\n'; edit(path='/l2400.txt', old='a\n'+'y'*2400+'\nb', new='z')`
- `write /t12000.txt content='a\n'*12000; edit(path='/t12000.txt', old='  a', new='z')`

Instructions:

1. Run agents/f15-p5/artifacts/evidence/probe.py as tools/sandbox-run.py <scratch> ./.venv/bin/python -I <script>. The sandbox has no network, an empty environment, scratch-only writes, CPU 60 s, wall-clock 120 s and RSS 2 GiB.
2. For each shape, call the public edit verb at sizes n, 2n and 4n. Record the edit duration, the longest gap seen by a 2 ms asyncio ticker, the number of Levenshtein cells (counted by wrapping replace.levenshtein), and the latency of carol's concurrent read. A control exact-match edit gives the baseline.

**Observed result:** Control exact edit on 16 KB: 20 ms, longest loop gap 3.5 ms. block_anchor at L=3000/6000/12000 lines: 176/642/2628 ms (x3.66, x4.09). levenshtein at M=600/1200/2400: 76/311/1214 ms (x4.09, x3.90), with Levenshtein cells 361201/1442401/5764801 (exactly quadratic). line_trimmed at L=3000/6000/12000: 266/1011/3995 ms (x3.81, x3.95). In every fuzzy probe the longest event-loop gap was within 15 ms of the edit duration. When carol's read was scheduled during the stall it waited the same span (2628 ms at anchor L=12000). Pure replace() alone reproduces the anchor timings (159/632/2552 ms). Every fuzzy edit returned vfs.invalid and committed nothing.

### Priority

Likelihood medium: Any principal with modify rights on any one file, including its own, can trigger this with a request of a few KB plus a cheap prior write. Agents routinely send edits whose old string misses. Nothing in params.py, base.py or the storage caps old/new length, edit count, target count or file size, except MariaDB's packet cap on writes.

Impact medium: The stall freezes the shared event loop for every other principal on the host. On SQLite-backed mounts it also holds the writer lock, for a time that grows with the square of the input: 24 KB gave 2.6 to 4.0 s, and at the measured 4x per doubling about 100 KB would give roughly 40 to 60 s. The effect is transient: it ends when the call returns, leaves no persistent state, and the attacker can repeat it on every call. It costs availability only, with no confidentiality or integrity effect.

Confidence: The quadratic loops are plain in source and match the trace line for line. Two independent verifiers reproduced the result through the public verb in the sandbox. Growth was about 4x per doubling for all three shapes, the Levenshtein cell count was exactly quadratic, the loop stall equalled the edit time, a different principal's read was blocked, and on file-backed SQLite a rival connection's BEGIN IMMEDIATE was refused while the edit ran. A control exact edit stayed fast.

### Remediation

Bound the work and move it off the event loop. (1) In block_anchor_replacer, precompute the indices of the stripped lines once, find each first anchor's next last anchor with bisect, and cap the number of candidates. That removes the O(L^2) scan. Compute line start offsets once with a prefix sum and use them in both fuzzy replacers. In replace(), compute line numbers from those offsets, split the content once, and list context for only the first few matches in the multi-match error. (2) Replace the Python levenshtein with a banded or early-exit version, or a vfs-core kernel. Skip fuzzy similarity when a middle line exceeds a declared length, or when len(content_lines)*len(find_lines) exceeds a work budget, and refuse with a classified invalid error that names the exact-match requirement. (3) Run the batch's edited_entry work through call_offloaded with a deadline, or do the matching before the writer transaction where the existing version guard keeps that safe. Regression test: count operations, never wall time. For example, count levenshtein cells or replacer loop iterations for the 'a\n'*L / 'a\nx\nb' and '  a' shapes at L and 2L, and assert that growth is linear.

Sketch for `src/vfs/storage/replace.py`:

```python
from bisect import bisect_left

def block_anchor_replacer(content: str, find: str) -> Generator[Match]:
    content_lines = content.split("\n")
    find_lines = _split_dropping_trailing_blank(find)
    if len(find_lines) < 3:
        return
    first_line, last_line = find_lines[0].strip(), find_lines[-1].strip()
    stripped = [line.strip() for line in content_lines]
    last_at = [j for j, line in enumerate(stripped) if line == last_line]
    candidates: list[tuple[int, int]] = []
    for i, line in enumerate(stripped):
        if line != first_line:
            continue
        k = bisect_left(last_at, i + 2)
        if k < len(last_at):
            candidates.append((i, last_at[k]))
        if len(candidates) > MAX_ANCHOR_CANDIDATES:
            return
    # similarity as before, but refuse lines longer than MAX_FUZZY_LINE_CHARS before calling levenshtein,
    # and compute start offsets from one prefix-sum list instead of a per-match sum
```

## 13. Read-only PermissionMap overrides are bypassed by subtree verbs (delete, sweep, move, copy) addressed at a writable ancestor or destination

**Severity:** medium (likelihood medium, impact medium). **Confidence:** high. **Fingerprint:** `vfs:permissions:check_writable:subtree-override-not-consulted`

The router's PermissionMap is the per-prefix write policy enforced at the routing chokepoint before dispatch (README.md:127), and the mount-admin spec states that a map 'gates every path beneath'. The write gate resolves only the exact rel a verb addresses. A verb whose effect spans a subtree is checked against the rule that covers its addressed root, and never against a read-only override nested beneath that root. A non-system caller with ordinary row rights (the default fresh-mount posture) is refused on every direct write, edit, delete, sweep, move or copy inside the read-only region. Yet the same caller can: trash the read-only rows with delete(ancestor); purge them permanently with sweep(ancestor), after which restore finds nothing; move the ancestor out, rewrite the formerly read-only file at its new address, and move it back; or plant attacker content inside the read-only region in one call by copying or moving a staged tree onto an absent ancestor. The router already applies a subtree rule for bind sites (_busy_guard with subtree=True) but has no equivalent for permission overrides.

### Root cause

check_writable (src/vfs/permissions.py:269-321) resolves the gated rel through PermissionMap._resolve. That function matches only overrides whose prefix equals or covers the path (permissions.py:196) and never looks at overrides lying strictly beneath it. _gate_entry (base.py:2902) calls check_writable_composed only for the addressed rels. It does this for every op, subtree-shaped ones included: single-path delete, restore and sweep at base.py:1748 and 2189, move's src and dest and copy's dest at base.py:2535. So a read rule deeper than the target is invisible to the gate.

### Intended behaviour

A read-only override must refuse every write-gated op whose effect lands at or beneath it. For subtree-shaped ops (delete, restore, sweep, move src and dest, copy dest), the gate should refuse with read_only when any layer's map holds a read override strictly beneath the gated rel, or beneath its /.vfs alias. This mirrors how _busy_guard refuses a region that contains a bind site.

### Trace

1. **entrypoint** `src/vfs/base.py:1059` `AsyncVirtualFileSystem.delete (also restore 1094, sweep 1117, move 1233, copy 1246)`: A non-system caller (anonymous or a named principal) calls delete('/proj'), sweep('/proj'), move('/proj','/x') or copy/move('/stage','/proj') with its own authority
2. **propagation** `src/vfs/base.py:1748` `_route_single`: Single-path verbs gate with write_rels=(terminal.rel,), the addressed path only. The busy guard just above (1743) checks bind sites beneath the path, but nothing checks permission rules beneath it
3. **propagation** `src/vfs/base.py:2535` `_route_two_path`: move gates (src, dest) and copy gates dest only. These are the roots of the transferred subtree, not the paths that will be written beneath dest or vacated beneath src
4. **propagation** `src/vfs/base.py:2902` `_gate_entry`: check_writable_composed(self._permission_layers(full), op) is called once per addressed rel
5. **propagation** `src/vfs/permissions.py:297` `check_writable`: Resolution covers only _permission_candidates(rel), meaning the path and its /.vfs alias, through PermissionMap._resolve
6. **propagation** `src/vfs/permissions.py:196` `PermissionMap._resolve`: Matches only prefixes that equal or cover the path. '/proj' resolves to the read_write default even though '/proj/locked' is read-only, so the gate returns None
7. **sink** `src/vfs/base.py:1754` `_route_single -> _dispatch_entry`: Storage runs the subtree delete or sweep, mutating rows under the read-only override. The move and copy subtree transfer is dispatched the same way from _route_two_path

### Evidence

- `src/vfs/permissions.py:196`: The override match is 'normalized == prefix or normalized.startswith(prefix + "/")' only. Nothing checks for override prefixes beneath the path
- `src/vfs/base.py:2902`: The only permission-map call in the gate, invoked with addressed rels only
- `src/vfs/base.py:2939`: _busy_guard does consider the subtree (_bindings_beneath when subtree=True) for bind sites. Subtree-shaped effects are recognised for mounts but not for permission overrides
- `src/vfs/base.py:122`: _BUSY_GUARDED_OPS = {delete, restore, sweep}: the router's own list of ops that act beneath the addressed site
- `README.md:127`: The per-prefix map is documented as enforced at the routing chokepoint before anything dispatches
- `context/specifications/archive/068-mount-admin-completeness/spec.md:93`: Declared intent: a parent layer's map 'still gates every path beneath'
- `agents/v18-p3/artifacts/evidence/subtree-override-bypass.txt:1`: Verifier's independent sandboxed reproduction (harness and output). All six direct controls are refused read_only; delete, sweep, move-out/write/move-back, copy and move onto the ancestor all succeed against the locked file

### Conditions

- *system_configuration*: The operator configured a read-only PermissionMap override nested beneath a writable non-root prefix of the same entry, for example read_write(read=['/proj/locked']). A read-only region expressed as a separate child mount is protected by the bind-site busy guard instead. An override whose parent is the mount root is reachable only through copy or move onto a missing ancestor, since the root itself cannot be deleted or moved.
- *authorization_role*: The caller holds the row rung that delete, sweep or move needs on the writable ancestor, or that copy or move needs at the destination. A fresh storage's default posture is read_write for everyone, anonymous included, so no grant is needed by default. Row grants still apply where postures are tightened.
- *data_state*: Rows exist under the read-only override (for trash, purge or move-tamper), or the destination ancestor is absent and the caller can stage a tree elsewhere in the same mount (for copy or move planting).

### Reproduction

**Attacker perspective:** A named non-system principal (bob) calls public routed verbs on an AsyncVirtualFileSystem whose root InMemoryStorage carries permissions=read_write(read=['/proj/locked']). The host seeded /proj/locked/policy.txt as 'ORIGINAL' through the storage as Authority.system().

Payloads:

- `await fs.delete('/proj', authority=bob)`
- `await fs.sweep('/proj', authority=bob)`
- `await fs.move(src='/proj', dest='/tmpx', authority=bob); await fs.write(path='/tmpx/locked/policy.txt', content='TAMPERED', authority=bob); await fs.move(src='/tmpx', dest='/proj', authority=bob)`
- `await fs.write(path='/stage/locked/policy.txt', content='FORGED', parents=True, authority=bob); await fs.copy(src='/stage', dest='/proj', authority=bob)`
- `await fs.write(path='/stage/locked/policy.txt', content='FORGED', parents=True, authority=bob); await fs.move(src='/stage', dest='/proj', authority=bob)`

Instructions:

1. Build AsyncVirtualFileSystem(storage=InMemoryStorage(), permissions=read_write(read=['/proj/locked'])) and seed /proj/locked/policy.txt='ORIGINAL' via fs._bindings['/'].storage.write(..., parents=True, authority=Authority.system()).
2. Controls: as bob, run write, edit, delete('/proj/locked'), sweep('/proj/locked'), move of the locked file, and copy into /proj/locked. Each must classify vfs.read_only.
3. Run each payload on a fresh filesystem (planting cases with /proj absent), then read /proj/locked/policy.txt as Authority.system().
4. Command: ./tools/sandbox-run.py ./agents/v18-p3/scratch ./.venv/bin/python -I v_subtree.py (InMemoryStorage over private SQLite, no network).

**Observed result:** All six controls returned success=False with vfs.read_only. delete('/proj') returned success=True and the locked file read not_found; restore('/proj') then brought back 'ORIGINAL', so this effect is soft. sweep('/proj') returned success=True and the file read not_found; restore('/proj') also returned not_found, so the purge is permanent. The move-out/write/move-back sequence succeeded and the file content became ['TAMPERED']. A direct write into the empty locked region was refused read_only, yet copy('/stage','/proj') and move('/stage','/proj') both succeeded and the file content became ['FORGED']. A follow-up direct write was again refused read_only.

### Priority

Likelihood medium: Requires an operator map with a read-only override nested under a writable prefix, which is an advertised read_write(read=[...]) pattern, and a caller with row rights on the ancestor. A fresh mount's default posture already gives everyone read_write. delete, move and copy are ordinary agent verbs.

Impact medium: Breaks the integrity and availability of data the operator marked read-only, within one mount. Content can be replaced or planted (move/copy), soft-deleted (delete, which restore can undo) or permanently purged (sweep). Row-level grants still apply, there is no confidentiality loss, and there is no escape across mounts.

Confidence: Independently reproduced end to end through public router verbs on InMemoryStorage, with matched refused controls. Source shows the gate never consults overrides beneath the addressed path, and the declared intent (README, spec 068) is that the map gates every path beneath.

### Remediation

Treat delete, restore, sweep, move (src and dest) and copy (dest) as subtree-shaped in the permission gate. Besides resolving the addressed rel, refuse with read_only when any layer's map holds a 'read' override strictly beneath that rel or beneath its /.vfs alias. Thread a subtree flag from _gate_entry through check_writable_composed to check_writable, mirroring the bind-site busy guard. Add regression tests with read_write(read=['/dir/frozen']) asserting that delete('/dir'), sweep('/dir'), restore('/dir'), move('/dir','/x'), move('/stage','/dir') and copy('/stage','/dir') each classify read_only with no storage call recorded. Apply the same flag in the grouped-observations path (base.py:2189).

Sketch for `src/vfs/permissions.py`:

```python
def check_writable_composed(layers: Iterable[PermissionLayer], op: str, *, subtree: bool = False) -> Result | None:
    for layer in layers:
        denied = check_writable(layer.permission_map, op, layer.rel, mount_prefix=layer.mount_prefix, subtree=subtree)
        if denied is not None:
            return denied
    return None


def check_writable(permission_map, op, rel, *, mount_prefix=ROOT, subtree=False):
    if op not in WRITE_GATED_OPS:
        return None
    first, *rest = _permission_candidates(rel)
    resolved = permission_map._resolve(first)
    for candidate in rest:
        alternate = permission_map._resolve(candidate)
        if alternate.rule_prefix is None:
            continue
        if resolved.rule_prefix is None or len(alternate.rule_prefix) > len(resolved.rule_prefix):
            resolved = alternate
    if resolved.permission == "read_write" and subtree:
        resolved = _read_rule_beneath(permission_map, rel) or resolved
    if resolved.permission == "read_write":
        return None
    ...  # unchanged error construction


def _read_rule_beneath(permission_map: PermissionMap, rel: str) -> _Resolution | None:
    """A read-only override strictly beneath *rel* (or its metadata alias), which a subtree verb would reach."""
    for candidate in _permission_candidates(rel):
        base = "" if candidate == "/" else candidate
        for prefix, perm in permission_map.overrides:
            if perm == "read" and prefix.startswith(base + "/"):
                return _Resolution("read", prefix)
    return None
```

Sketch for `src/vfs/base.py`:

```python
# Mutations whose effect reaches beneath the addressed path.
_SUBTREE_OPS: frozenset[Op] = frozenset({"delete", "restore", "sweep", "move", "copy"})

# in _gate_entry:
            err = check_writable_composed(self._permission_layers(full), op, subtree=op in _SUBTREE_OPS)
```

## 14. One refused embed batch at the head of the NULL-embedding keyset stops vector indexing for every later writer on the store

**Severity:** medium (likelihood medium, impact medium). **Confidence:** medium. **Fingerprint:** `vfs:storage/backends/database/backend.py:_embed_step:refused-batch-head-of-line-no-split-or-quarantine`

Each run of the reindex embed step starts again at chunk id 0. It selects the lowest-id rows that have no embedding, cuts them into batches using the provider's ceil(len/4) token estimate, and ends the whole step at the first page where any batch fails. When the provider refuses a batch deterministically, nothing splits the batch, skips it, or quarantines its rows. Those rows stay NULL and form the same head batch on every later run. The shipped OpenAI adapter meters batches with ceil(len/4) against 5/6 of its declared 300000-token request cap. Text denser than about 3.3 characters per real token, such as CJK, can therefore pass the estimate and still exceed the real cap. A principal with read_write on only its own subtree can write about 4096 small CJK files, about 2 MB in total. After that, no chunk written later by any principal on the same DatabaseStorage gets a vector, however many times reindex runs, and glean's vector leg misses that content. A smaller amount of such text leaves only the neighbouring rows in its batch unembedded, and limits the rest to one page of progress per run. Benign CJK corpora can trigger the same refusal.

### Root cause

_embed_step (backend.py:1416) sets last = 0 on every run (1442). On any outcome.failure it records stopped_by and breaks out of the loop (1466-1468). It does not tell a deterministic refusal apart from a transient one, and it never advances past the failing page. embed_page (embed.py:319-325) keeps the first failure and lands only the batches that answered. _embed_with_retry (embed.py:346-355) retries only when the error carries Retry-After. No code bisects a refused batch, and there is no per-row failed state. So select_unembedded (embed.py:172-182) returns the same rows first on every run. token_batched (embed.py:112-133) meters each row with provider.estimate_tokens. For OpenAIEmbeddingProvider that is ceil(len/4) (openai.py:63-64, provider.py:96), checked against 5/6 of MAX_BATCH_TOKENS=300000 (openai.py:34, embed.py:121). Rows the writer controls can therefore make up a batch whose real token count exceeds the hard cap that the adapter itself declares.

### Intended behaviour

Batches should be metered with a bound that cannot undercount real tokens, for example the UTF-8 byte length for byte-level BPE. A batch refused without Retry-After should be bisected down to single rows. A single row that is still refused should be quarantined with a per-row failed state that select_unembedded and count_unembedded skip and that the report counts, as the render stage's _land already does (backend.py:1298-1321). The loop should keep advancing to later pages, so one writer's content cannot stop vector indexing for other principals.

### Trace

1. **entrypoint** `src/vfs/storage/backends/database/backend.py:686` `DatabaseStorage.write`: Principal alice writes ordinary CJK text files under /alice. Beyond the write gate, no rule limits their content, script or length. A write right on its own subtree is enough: with a closed root posture (posture='none') and read_write granted only on /alice, the same result follows.
2. **propagation** `src/vfs/models/chunking.py:217` `recursive_text_split`: Reindex chunks each body into rows of at most 2048 characters. Alice's rows get lower chunk ids than any chunk written after them.
3. **propagation** `src/vfs/storage/backends/database/backend.py:1442` `DatabaseStorage._embed_step`: Every run starts the keyset at last = 0.
4. **propagation** `src/vfs/storage/backends/database/embed.py:178` `select_unembedded`: The page is the lowest-id live rows whose embedding is NULL, so alice's rows come first on every run.
5. **propagation** `src/vfs/storage/backends/database/embed.py:125` `token_batched`: Each row's cost is provider.estimate_tokens, which is ceil(len/4) for the OpenAI adapter, checked against 250000 (5/6 of 300000). A batch of 2048 rows of 160 CJK characters estimates at 81920 tokens. With about 1 real token per ideograph it is 319488.
6. **propagation** `src/vfs/storage/backends/database/embed.py:349` `_embed_with_retry`: The provider refuses with a 400 that carries no Retry-After. The openai client does not retry a 400, and the error is re-raised without splitting the batch or marking its rows.
7. **propagation** `src/vfs/storage/backends/database/embed.py:319` `embed_page`: gather(return_exceptions=True) keeps the first failure. The refused batch's rows land nothing.
8. **sink** `src/vfs/storage/backends/database/backend.py:1466` `DatabaseStorage._embed_step`: outcome.failure records stopped_by and breaks the loop, so later pages are never selected. The same rows head the next run, and every chunk written later by any principal stays with a NULL embedding.

### Evidence

- `src/vfs/storage/backends/database/backend.py:1466`: A failed batch on any page breaks the whole embed loop (stopped_by at 1467, break at 1468).
- `src/vfs/storage/backends/database/backend.py:1442`: last = 0 on every run, so the refused rows are always selected first again.
- `src/vfs/storage/backends/database/backend.py:1317`: The sibling render stage retries row by row and quarantines a refused row as 'failed'. The embed step has nothing equivalent.
- `src/vfs/storage/backends/database/embed.py:121`: The batch budget is 5/6 of max_batch_tokens, metered by the provider's own estimate.
- `src/vfs/embedding/provider.py:96`: estimate_tokens is ceil(len/4), at least 1, whatever the script.
- `src/vfs/embedding/openai.py:34`: The shipped adapter declares MAX_BATCH_TOKENS=300000 and meters with the generic estimate_tokens (line 64).
- `src/vfs/storage/backends/database/embed.py:358`: _retry_after_seconds returns None for a 400 without Retry-After, so the refusal is re-raised without a split or a row mark.
- `src/vfs/storage/backends/database/backend.py:1479`: The operator sees only a retryable 'unavailable' warning that names no rows, while reindex reports success=True.
- `agents/v19-p3/artifacts/evidence/run-4096.json:1`: Independent repro with the real OpenAIEmbeddingProvider and a real openai.BadRequestError. In both runs both requests were refused ([2048 inputs, 319488 tokens] each). Bob stayed at 1 of 41 chunks embedded, unembedded stayed 4136, success=True, and bob's glean vector leg returned hits=2.
- `agents/v19-p3/artifacts/evidence/run-0.json:1`: Control without alice's files: bob was 41 of 41 embedded after run 1, and the vector leg returned hits=42.
- `agents/v19-p3/artifacts/evidence/repro.py:1`: Repro harness: no network, the real OpenAI adapter, and a fake client that enforces 300000 tokens per request, counting 1 token per CJK ideograph.
- `agents/f20-p5/artifacts/evidence/f20-closed-attack.json:1`: Final-verifier rerun under posture='none', with alice's write right only on /alice (bob's write into /alice was refused). In each of 3 runs, both requests were refused ([2048, 319488] each). Bob stayed at 1 of 41 embedded, unembedded=4136, success=True, and bob's vector leg returned hits=1. The control (f20-closed-control.json) had bob at 41 of 41 and hits=41.
- `agents/f20-p5/artifacts/evidence/f20-attack.json:1`: Final-verifier rerun with the default posture and an independently written harness (f20_repro.py). 3 runs gave the same stop: bob at 1 of 41 embedded, unembedded 4136, vector hits=2. The control (f20-control.json) gave 41 of 41 and hits=42.
- `agents/f20-p5/artifacts/evidence/f20-fixed.json:1`: The proposed code change, the UTF-8 byte-length estimate patched onto the provider instance, under the same attack. One reindex embedded all 4136 rows in 9 requests, the largest at 83308 tokens, with unembedded=0 and no warning.

### Conditions

- *system_configuration*: The mount uses an embedder whose hard caps are enforced on real tokens while vfs meters them with ceil(len/4). The shipped OpenAIEmbeddingProvider is the only shipped adapter that declares such caps. LangChain declares none, and the local providers do not refuse.
- *authorization_role*: The writer needs write access to some path on the same DatabaseStorage mount and no other right. The operator runs reindex as usual.
- *data_state*: The token-dense rows must have lower chunk ids than the victims' unembedded rows: written before them, or still unembedded. A full stop needs about 4096 rows, one EMBED_PAGE_ROWS page, with more than about 147 real tokens per row. Fewer rows strand only the rows that share their batch, and limit progress to one page per run.
- *third_party_dependency*: OpenAI's tokenizer must count the text at more than about 1.2 times len/4, and must refuse a request over 300000 tokens deterministically with a 400 and no Retry-After. The repository's adapter docstring declares this cap as documented. The installed openai client (_base_client.py _should_retry) retries only 408, 409, 429 and 5xx, not 400. The real cl100k token density of CJK was not measured locally; the repro used a stand-in counter of 1 token per ideograph.

### Reproduction

**Attacker perspective:** An agent or user (alice) that can write its own subtree of a shared DatabaseStorage mount using the OpenAI embedder. The default root posture gives everyone read_write; the result is the same under a closed root posture where alice's only write right is read_write on /alice. The victims (bob) write content later.

Payloads:

- `4096 files /alice/n/NNNNN.txt, each a distinct 160-character string: a 6-character id prefix followed by CJK ideographs from U+4E00 (estimate 40 tokens; stand-in real count about 154)`

Instructions:

1. Mount DatabaseStorage(url=sqlite+aiosqlite:///<scratch>/r.db, embedder=OpenAIEmbeddingProvider(fake_client, 'text-embedding-3-small', dimensions=256)) with the default root posture (read_write for everyone); posture='none' gives the same embedding result. The fake client's embeddings.create counts 1 token per CJK ideograph and ceil(rest/4) for other text, and raises openai.BadRequestError with an httpx 400 response and no Retry-After when a request exceeds 300000 tokens.
2. As system, write /alice/README.txt and /bob/README.txt, grant each principal read_write on its own directory, and run reindex once.
3. As alice, write the 4096 CJK files. As bob, then write 40 ordinary English files.
4. Run reindex twice. After each run, count embedded and NULL chunk rows per top-level directory. Then run glean as bob and read legs['vector'].
5. Control: the same steps with zero alice files.

**Observed result:** Attack: in each of the 2 runs the provider got 2 requests, both refused ([2048 inputs, 319488 tokens]). Bob stayed at 1 of 41 chunks embedded and unembedded=4136. reindex returned success=True with one warning, vfs.unavailable retryable=True: 'embedding stopped after 0 requests: BadRequestError: Requested 319488 tokens, max 300000 tokens per request'. Bob's glean vector leg returned hits=2. Control: bob was 41 of 41 embedded after run 1, and the vector leg returned hits=42.

### Priority

Likelihood medium: The attacker needs only ordinary write access to some path and about 2 MB of CJK text. The deployment must use the OpenAI embedder, the only shipped adapter with hard caps. Benign CJK or Cyrillic corpora with default 2048-character chunks also exceed the real cap, so this can happen without any malice.

Impact medium: The effect is persistent and store-wide, and it crosses principals: no chunk written later gets a vector on any reindex until an operator deletes or rewrites the offending rows or changes the code. glean's vector leg silently misses that content. The lexical leg and all other verbs are unaffected, and nothing is disclosed or lost. The warning names no rows and is marked retryable.

Confidence: The vfs logic (no split, skip or quarantine; break; restart at 0) is visible in source, and I reproduced it independently through the real shipped OpenAI adapter and a real openai.BadRequestError, with caps and page size unscaled. The one external fact, OpenAI's real CJK token density and its 400 on a request over 300000 tokens, rests on the repository's declared caps and public tokenizer behaviour, not on a local measurement. A fresh final verifier reproduced the stop three runs in a row, under both the default and a closed root posture, and confirmed that the byte-length estimate removes it.

### Remediation

Meter with a bound that cannot undercount, and stop treating a deterministic refusal as a reason to end the run. (1) The OpenAI adapter's estimate_tokens should return the UTF-8 byte length, because byte-level BPE never yields more tokens than bytes. (2) embed_page should bisect a batch refused without Retry-After, and return a single row that is still refused as a per-row failure. (3) Quarantine such rows with a failed marker that select_unembedded and count_unembedded exclude, reset it when the chunk's content_hash changes, and report the count in the embedding extra. (4) _embed_step should break only on transient failures (timeout, 429 or Retry-After, network errors) and otherwise keep advancing last. Regression test: a fake provider that counts 1 token per CJK character and enforces 300000 per request; alice writes 4096 CJK files and bob writes 40; after one reindex, all of bob's chunks are embedded.

Sketch for `src/vfs/embedding/openai.py`:

```python
    def estimate_tokens(self, text: str) -> int:
        # byte-level BPE never emits more tokens than UTF-8 bytes: an upper bound the hard caps can trust
        return max(1, len(text.encode("utf-8")))
```
