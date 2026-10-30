# Study 06: distribution, NFS and AFS, laid against vfs over MCP

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Source:** OSTEP v1.10, chapters 47 (dialogue), 48 (Distributed Systems), 49 (Sun's NFS), 50 (AFS), 51 (summary dialogue), read in full from the pdftotext split. **Page convention:** "ch. 49 p. 5" is the page number printed inside the chapter. PDF page = chapter start + p − 1, where the starts are ch. 48 = 646, ch. 49 = 663, ch. 50 = 681, ch. 51 = 695. Nothing from the book is quoted; every idea is paraphrased and cited.
- **vfs at:** HEAD `ac5c515`, `main`.
- **Experiments (EXECUTED):** three scripts run with `uv run python` against `VirtualFileSystem(storage=InMemoryStorage())`, as the system actor. Scripts and their output live in the session scratchpad, outside the repo: `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/5d8df80f-e1a8-4b32-8c5d-fd4fe65a3cc5/scratchpad/ostep/s06/replay.py` (`replay.out`), `details.py` (`details.out`) and `transfer.py` (`transfer.out`) in the same folder. The results that matter are copied into the tables below.
- **The angle:** vfs served over MCP is a distributed file system. The MCP client is the NFS client. `vfs serve` is the file server. The SQL database is the server's disk.

Terms used throughout:

- **Idempotent:** doing it twice leaves the same state as doing it once.
- **Replay:** the client sends the same request again because it got no reply. It cannot know whether the first one ran.
- **Stateless server:** the server keeps no memory of any client between requests. Each request carries all it needs.
- **File handle:** a short, stable, low-level name for a file that the server hands the client and the client sends back.
- **Cache consistency:** what version of a file a client sees when another client has changed it.

---

## 1. What the chapters say

**Chapter 47 (dialogue, PDF 644–645).** Distribution is the same problem as before, but the thing you want is far away, there are many of them, and some of them are broken. Everything fails. The craft is building a whole that rarely fails out of parts that often do (READ, ch. 47 pp. 1–2).

**Chapter 48 (Distributed Systems).** The crux is how to build a working system when components fail (READ, ch. 48 p. 1). The network loses packets as a matter of course, for example when a router's buffers fill (READ, p. 2). A reliable layer adds an acknowledgment, a timeout and a retry (READ, p. 6). Retry alone is not enough: if the reply is the thing lost, the receiver sees the request twice (READ, p. 7). So each message needs an identity, and a cheap one is a sequence counter both sides agree on (READ, pp. 7–8). Timeouts should back off exponentially under load (READ, p. 8 tip). Distributed shared memory failed because failure and cost were invisible to the programmer (READ, p. 9). Remote procedure call (RPC) won: a stub generator turns a declared interface into marshaling code, and a runtime handles naming, transport and retry (READ, pp. 9–12). RPC over a raw datagram layer can promise at most once under failure (READ, p. 12). A long call needs a way to say it is still working, or the client will time out and retry it (READ, pp. 12–13). The end-to-end argument: only the endpoints can verify the result, so lower-layer reliability is an optimization, never the proof (READ, p. 13 aside).

**Chapter 49 (Sun's NFS).** NFSv2's one goal was fast, simple recovery when the server crashes (READ, ch. 49 p. 3). It got there with a **stateless** protocol: the server tracks nothing about clients, no open files, no positions (READ, p. 4). A file descriptor held on the server would be shared state that a crash destroys (READ, pp. 4–5). Instead the client gets a **file handle** made of a volume id, an inode number and a generation number; the generation stops a stale handle from reaching a reused inode (READ, p. 5). Every READ and WRITE names the handle, the offset and the count, so each request stands alone (READ, pp. 6–8). The client keeps the open file table and the position (READ, p. 7 and fig. 49.5). Because LOOKUP, READ and even WRITE are idempotent, the client handles a lost request, a down server and a lost reply the same way: it retries (READ, pp. 9–10). Some verbs resist it: a replayed MKDIR fails even though the first one worked, and NFS accepts that (READ, pp. 10–11). Client caches speed things up but raise the cache consistency problem, which has two parts: when do other clients see an update, and when does a client notice its copy is stale (READ, pp. 11–12). NFS answers with flush-on-close and a GETATTR check before using the cache, then an attribute cache with a timeout to stop GETATTR flooding the server (READ, pp. 12–13). The timeout makes the semantics hard to reason about: the implementation defined the behaviour, not the other way round (READ, p. 13). Last, the server must put each write on stable storage before it replies success, or a crash can leave a file with holes the client never sees (READ, pp. 13–15). The VFS/vnode interface was born to plug NFS into the kernel (READ, p. 15 aside).

**Chapter 50 (AFS).** AFS's goal was scale: as many clients per server as possible (READ, ch. 50 p. 1). It also made user-visible consistency a first-class design goal (READ, p. 1). Version 1 cached **whole files** on the client's disk: fetch at open, local reads and writes, store at close (READ, p. 2). Measurement found two costs: the server walked every full path, and clients flooded it with TestAuth validity checks (READ, p. 3). Version 2 added **callbacks**, a server promise to tell the client when its cached file changes, and file identifiers (volume, file, uniquifier) so the client walks paths and the server does not (READ, p. 4). The result is a simple model: across machines, an update becomes visible and cached copies are invalidated at the moment the writer closes the file (READ, pp. 6–7). Two writers on two machines resolve by last writer wins, really last closer wins, and the file is whole from one writer, never a mix of both (READ, pp. 7–8). The price is state on the server: callbacks live in memory, so a server or client crash forces everyone to treat their caches as suspect and revalidate (READ, p. 8). Whole-file transfer loses to block transfer for small reads or writes inside large files (READ, pp. 9–11). An aside warns that cache consistency is not concurrency control: an application that cares about concurrent updates must bring its own locking or conflict machinery (READ, p. 6 aside).

**Chapter 51 (summary dialogue).** Everything fails; redundancy hides much of it; retry is the basic tool; and the protocol, the exact bits on the wire, decides both how a system fails and how far it scales (READ, ch. 51 p. 1).

---

## 2. Principles vfs should adopt

Each item: the principle; the source; where vfs stands; the one change it implies, if any.

### 2.1 The replay table (EXECUTED)

Several principles below rest on one experiment. It sends each mutating verb twice, as a client would after a lost reply. "Replay" means the second, identical call.

| Verb, replayed | First call | Replay answers | Idempotent? |
|---|---|---|---|
| `write` same body | `created` v1 | success, `updated`, **v2**, no version row minted | Body and history yes; the version counter ticks |
| `write` body "two", then replay | `updated` v3, 1 version row | success, `updated`, **v4**, still 1 version row | same |
| `edit world→there` | `updated` v2 | **failure**, `vfs.invalid`, "old_string not found" | No (the MKDIR case) |
| `mkdir /d` | `created` | failure, `vfs.exists` | No |
| `mkdir /d, exist_ok=True` | — | success, `unchanged` | Yes |
| `delete` | `deleted` | failure, `vfs.not_found`, but `data` carries `vfs.trashed: true` and `deleted_at` | No, but the replay is recognisable |
| `restore` | `created` v3 | failure, `vfs.exists` | No |
| `copy` | `created` | failure, `vfs.exists`, `data` names the target | No |
| `move` | `created` | failure, `vfs.not_found`, **no data** | No, and unrecognisable |
| `mkedge` | `created` | success, `updated` | Yes |
| `rmedge` | `deleted` | **success**, warning `vfs.not_found` | Yes |
| `grant` | success | success | Yes |
| `revoke` | success | **success**, warning `vfs.not_found` | Yes |
| `write` batch of 3, one with a missing parent | — | failure, nothing written (`/p/1.md` is `not_found` after) | The batch is all-or-nothing |

Spec 171 already ran a smaller probe of the same thing (READ, `context/research/studies/2026-10-15-agent-shell/experiments/r171/p4_replay.out`), and it plans a replay line in each tool description (READ, spec 171 §0 and §1.3). This table adds the version counter, the version rows, the error `data`, and the edge and grant verbs.

### 2.2 The numbered principles

1. **Assume every call can be lost on the way out or on the way back, and that the client cannot tell which.**
   - Source: ch. 48 pp. 6–7; ch. 49 pp. 9–10 (the three kinds of loss).
   - vfs: **half follows.** The MCP 2026-07-28 revision treats a broken stream as cancellation, the client re-issues fresh, and the protocol has no idempotency mechanism (READ, `context/open-questions.md`, the "long-batch execution model" entry). Spec 171 answers with synchronous calls, a shield so a broken stream does not cancel a mutation mid-flight, and a stated replay behaviour per verb (READ, spec 171 §0). That is NFS's own answer: retry, and know what retry does.
   - Change: make the replay table in §2.1 a pinned contract, one row per mutating verb, and test it (spec 171 criterion 15 already asks for the test; READ).

2. **Keep the server stateless toward clients: each request carries everything needed to serve it.**
   - Source: ch. 49 pp. 4–5, 7.
   - vfs: **follows on the wire, with named exceptions.**
     - Every verb takes `authority` and is keyed by path (READ, `src/vfs/base.py`, every public method's signature). Over HTTP the authority is derived per request from the access token; over stdio it is fixed per pipe (READ, spec 171 §0; spec 149 rule 3 as amended 2026-10-15). That is NFS's rule exactly: no per-client memory on the server.
     - `Session` holds one authority value and a closed flag, and nothing else; rights are re-derived on every call (READ, `src/vfs/session.py` class docstring). It is an in-process convenience, not wire state.
     - Each `cli` call starts a fresh shell at `workdir`; `cwd`, `env` and `history` do not survive across wire calls (READ, spec 171 §1.4; spec 148 amendment of 2026-10-15). That is NFS's client-side open-file table, kept on the client.
     - ADR 022's topology lock is host-process state for the serve lifetime, and not per client (READ, ADR 022 decisions 2 and 4). A restart re-creates it from configuration. It does not break crash recovery.
     - **Where state creeps in:** spec 148 plans a narrowing document, sub-sessions, a `surfaced` ring for leak notices and an ask ledger for `pending` (READ, spec 148 rules 1–5). The ask ledger is per-request server state with a TTL. Spec 149 rule 5 already pushes the wire half of `pending` into an integrity-protected `requestState` the client carries back (READ). That is the NFS move: hand the state to the client, signed, so the server can forget it.
   - Change: any state spec 148 adds is either carried by the client and integrity-protected, or a durable row; never volatile server memory keyed by a conversation (INFERRED).

3. **Make the verbs a client retries idempotent; where one cannot be, accept it knowingly and make the replay recognisable.**
   - Source: ch. 49 pp. 9–11 (the idempotency tip, the MKDIR aside, and the tip about not letting the perfect beat the good).
   - vfs: **half follows** (EXECUTED, §2.1).
     - Idempotent today: `write` of a body (the body and history do not double), `mkdir(exist_ok=True)`, `mkedge`, `rmedge`, `grant`, `revoke`. NFS WRITE is idempotent for the same reason: it is a store of a value, not an increment (READ, ch. 49 p. 9).
     - Not idempotent: `edit`, strict `mkdir`, `delete`, `restore`, `copy`, `move`. These are NFS's MKDIR case.
     - Inconsistent: `rmedge` and `revoke` treat "already gone" as success with a warning; `delete` treats it as a failure.
     - Recognisable: a replayed `delete` carries `vfs.trashed` and `deleted_at`, and a replayed `copy` names its target. A replayed `move` says only `not_found`, with no data, so a client cannot tell "I already moved it" from "it never existed" (EXECUTED, `transfer.out`).
     - Spec 171 leaves `idempotentHint` unset on every tool (READ, §1.3), though five verbs earn it.
   - Change: give each non-idempotent replay a recognisable answer, the way `delete` already does; the cheapest is a `move` replay whose `not_found` names the destination it finds occupied by the same `entry_id` (INFERRED).

4. **Detect a duplicate by giving each request an identity; a sequence counter makes that cheap.**
   - Source: ch. 48 pp. 7–8; at-most-once RPC, p. 12.
   - vfs: **does not follow.** No verb accepts a request id (READ, `src/vfs/base.py`; `grep` for `idempot` in `src/` finds only `close` and pure helpers). MCP gives none (READ, open-questions entry above). The eve memo already named the need: eve supplies a replay-stable call id, and the memo asks vfs to accept one so a re-issued 10,000-file write is a no-op (READ, `context/research/2026-09-15-eve-vercel-agent-framework.md` §8 items 1–2).
   - Change: an optional request key on mutating verbs, answered from a stored copy of the first `Result` when it repeats. This is the one tool that makes `move`, `edit` and a 10,000-row batch replay-safe all at once (INFERRED).

5. **Reply success only after the change is on stable storage.**
   - Source: ch. 49 pp. 13–15.
   - vfs: **follows.** The mutation runner commits iff the batch succeeded and returns the `Result` only after the commit (READ, `src/vfs/storage/backends/database/backend.py` `_mutate`, L1721–1736). A batch is one transaction, so a batch with one bad entry writes nothing (EXECUTED, §2.1 last row). NFS's interleaved-holes failure cannot happen inside one call.
   - **The gap is the hop below.** vfs is itself a client of the database, over a network. If the connection drops during `COMMIT`, the driver cannot say whether the commit landed. `classify_failure` turns any disconnect into `vfs.unavailable.backend` with `retryable=True` (READ, `src/vfs/storage/backends/database/engine.py` L323–349). So the client is told to retry when the write may already be in. For `write` the retry is harmless; for `move` or `copy` the retry fails as in §2.1 (INFERRED from the two READ and EXECUTED facts; not reproduced against a real engine here).
   - Change: classify a disconnect during commit apart from one before it, as an outcome to verify with a `stat`, not a plain retry (INFERRED).

6. **Name files on the wire with a stable low-level name that carries a generation, so a stale name cannot reach a new file.**
   - Source: ch. 49 p. 5 (volume, inode, generation); ch. 50 p. 4 (AFS's FID and its uniquifier).
   - vfs: **deliberately does not, at the API; follows inside.**
     - The wire names files by path (READ, memo `2026-10-23-a-filesystem-shaped-kernel…` §4.2 and §6; ADRs 011 and 021 assume one path per entry for rights).
     - Inside, every row has a ULID `entry_id`, and versions and edges key on it (READ, ADR 004, ADR 019). A ULID is never reused, so it needs no generation number: it is its own uniquifier (INFERRED). Each mount also has a ULID `mount_identity`, the analogue of NFS's volume id (READ, `engine.py` L519).
     - Paths on the wire do not bring back AFSv1's path-walk cost. `path` is a unique indexed column, so resolving a path is one index seek, not a walk down every component (READ, `src/vfs/models/rows.py`, the `vfs_entries` table).
     - **But a path plus a version is not a safe cache key.** A rename then a create at the old path gives `/h.md` at version 1 twice, with different bodies. A sweep then a create does the same, with a new `entry_id` (EXECUTED, `replay.out` §7). A revive after `delete` keeps the `entry_id` and carries the version on, so it is safe (EXECUTED). This is exactly the reused-inode problem the generation number solves.
     - Spec 172's staged-buffer cache is keyed by `(path, version)` (READ, spec 172 §3). It holds only within one run, which shrinks the window, but the key is the unsafe one.
   - Change: key every client cache by `(path, version, content_hash)` or by `entry_id`; `content_hash` is already a column the WASI open can request (INFERRED).

7. **Validate a cached copy against a cheap change attribute before using it, and count what validation costs.**
   - Source: ch. 49 pp. 12–13 (GETATTR before use, then the attribute cache); ch. 50 p. 3 (AFSv1's TestAuth flood).
   - vfs: **follows on the attribute, half on the cost.**
     - `version` is a per-entry monotone counter bumped by every material update (READ, ADR 013 pin 1; ADR 017). It is a better change attribute than NFS's modification time: no clock, no ties.
     - One `stat` is one statement as the system actor, three as a named principal (READ, memo §2, citing study S05).
     - A small pandas job in the WASI guest issued 17 `stat` calls out of 21 verbs, from the guest probing paths (READ, `2026-10-23-wasi-python-0-1-0-over-vfs…` §4). That is NFS's GETATTR storm in miniature.
     - **The version also ticks when nothing changed.** A replayed identical write moves v1 to v2 and v3 to v4 while the body hash stays put and no version row is minted (EXECUTED, §2.1). Every cache keyed on version then throws away a copy that was still good. The status vocabulary already has `unchanged` (READ, `src/vfs/models/entry.py` L449), but a file write never emits it (READ, `staging.py` L325 returns only `created` or `updated`).
   - Change: an identical-body write reports `unchanged` and leaves the version alone, as the version mint already leaves history alone (READ, `versions.py` docstring: an identical body mints nothing) (INFERRED).

8. **Design the consistency model first and write it down; do not let a cache timer define it.**
   - Source: ch. 49 p. 13 (NFS's semantics fell out of the attribute cache); ch. 50 pp. 1, 6–8 (AFS made it a goal and kept it simple).
   - vfs: **half follows.** For a direct verb call the model is simple and strong: one transaction, committed before the reply, with no server-side body cache, so any later call from anyone sees it (INFERRED from principle 5's READ facts). The fronts each have their own model, and none is written in one place:
     - WASI guest: AFS's model. A file is staged whole at open, nothing touches the database until close, and close is one `write` (READ, spec 169 §b5). Visible at close; last closer wins.
     - CLI `>>`: read then write with no precondition, documented as able to lose a concurrent append (READ, memo §2 and §5).
     - MCP: the 2026-07-28 revision gives list and read results a time-to-live and a cache scope (READ, `2026-10-15-the-agent-shell-prior-art-and-experiments.md` §10). Spec 171 sets them to zero and private for the list calls (READ, §0 "Cache hints"). That is NFS's attribute-cache timeout, switched off. Good.
   - Change: one table, per front, of when an update becomes visible and what two concurrent writers get (INFERRED).

9. **Cache consistency is not concurrency control. Code that cares about concurrent updates needs its own conflict check.**
   - Source: ch. 50 p. 6 aside; last writer wins, pp. 7–8.
   - vfs: **half follows.** Three facts (all EXECUTED, `transfer.out` and `replay.out` §2):
     - `edit` carries a content precondition: its `old` string must still be there. Agent A's stale edit of a line agent B did not touch merges cleanly; a stale edit of the line B changed is refused. That is a real conflict check.
     - A whole-body `write` from a stale copy silently reverts the other agent's change. A delayed replay of agent A's write after agent B's write leaves A's body. Last writer wins.
     - Nothing is lost for good: the clobbered body is kept as a version row (three version rows on `/b.md` after base, A, B, A). But no one is told.
   - vfs also already speaks the conflict language without a verb to use it. `vfs.conflict` is ESTALE with the hint to re-read and retry with the current version, and its `data` may carry `version` (READ, `src/vfs/results/kinds.py` L41–49, L146–149, and the `ErrorKind` docstring). No public verb accepts an expected version (READ, `base.py` `write` and `edit`).
   - Change: `write(if_version=)`, as yesterday's memo proposes (READ, memo §4.2). See §2.3 for what it is in these chapters.

10. **Match the transfer unit to the workload: whole files when files are small and read whole, blocks when access is partial.**
    - Source: ch. 50 pp. 9–11 and the workload aside on p. 11.
    - vfs: **follows for today's workload.** Every seam method is whole-body (READ, memo §2, study S05). Agent files are small and read whole, which is AFS's home ground. Large `data` rows read for a head are AFS's bad case (workload 7 in the book's comparison).
    - Change: the ranged read the memo already proposes (READ, memo §4.2 `read(range=)`); nothing new here.

11. **Server-pushed invalidation scales, but it is server state, and crash recovery must rebuild it.**
    - Source: ch. 50 p. 4 (callbacks), p. 8 (recovery: everyone revalidates after a crash).
    - vfs: **deliberately does not push.** Storage owns no background work (READ, ADR 013 pin 5). MCP now has `subscriptions/listen` (READ, agent-shell memo §10), and spec 171 does not use it (READ, spec 171). The model in a conversation cannot be called back anyway (INFERRED; see §4).
    - Change: none. If a front ever wants callbacks, they belong in that front as leases with an expiry, so a crash only costs a timeout (INFERRED).

12. **Back off exponentially when retrying against a loaded server.**
    - Source: ch. 48 p. 8 tip.
    - vfs: **follows.** `with_retry` restarts the whole transaction on a retryable engine outcome and doubles the delay each time (READ, `engine.py` L297–321). Kinds declare a retry class and may carry `retry_after_ms` (READ, `kinds.py` `RetryClass` and the `ErrorKind` docstring). The server-side retry is sound because a rolled-back transaction ran zero times, which is at-most-once by construction (INFERRED).
    - Change: none.

13. **Only the endpoints can prove the bytes arrived intact; give them the check.**
    - Source: ch. 48 p. 13 (end-to-end aside); checksums, p. 5 tip.
    - vfs: **half follows.** Every row stores a SHA-256-sized `content_hash` (READ, `rows.py` `vfs_versions.content_hash` `String(64)`, and the entries hash index). A write's observation returns path, kind, size, version and status, but not the hash (READ, `writes.py` L341–349). A client that wants to verify must spend a `stat`.
    - Change: return `content_hash` on each written row (INFERRED).

14. **Generate the wire stubs from one declared interface; never hand-write marshaling.**
    - Source: ch. 48 pp. 9–11 (the stub generator).
    - vfs: **follows, as planned.** Spec 171 projects each tool's input schema from `vfs.params.PARAMS`, never from Python signatures, with a drift test; bytes cross as base64 (READ, spec 171 §1.1). That is the stub compiler and XDR in modern form.
    - Change: none.

15. **A long call must be able to say it is still working, or the client will time out and retry it.**
    - Source: ch. 48 pp. 12–13.
    - vfs: **does not follow yet.** Served calls are synchronous and complete-only (READ, spec 171 §0). The tasks extension, which would give a 10,000-file batch a pollable handle, is an open question (READ, open-questions entry above). Until then a big batch that outlives the client's timeout is re-issued. Under §2.1 that re-issue is safe for `write` (all-or-nothing, same bodies) and unsafe for `move` and `copy` batches.
    - Change: none beyond principle 4; a request key covers this case too (INFERRED).

### 2.3 What `if_version` is, in these chapters

The brief asks what yesterday's `if_version=` corresponds to here.

- **It is not in NFSv2 or AFS.** Neither has a conditional write. Both validate at read time: NFS by GETATTR before using the cache (ch. 49 p. 12), AFS by callback or TestAuth at open (ch. 50 pp. 2,
  4) (READ).
- **It is the machinery the AFS aside says applications must bring for themselves** (ch. 50 p. 6) (READ). The book says file-system consistency gives you a reasonable copy, not safe concurrent updates. `if_version` is the smallest such machinery: an optimistic, per-file check at write time (INFERRED).
- **It turns last writer wins into first writer wins, loudly.** In §2.1's rival-writer run, agent A's delayed replay would meet version 3, not the version 1 it read, and be refused `conflict` instead of reverting agent B (INFERRED from the EXECUTED run).
- **It validates at write, not at read.** That is the right end for vfs, because the main client cache is a model's context window, which nobody can invalidate (see §4) (INFERRED).
- **It creates a new replay problem.** If agent A's own write landed and only the reply was lost, A's replay with `if_version=1` meets version 2, its own write, and is refused. NFS never met this, because its WRITE carries no precondition. Two fixes, both INFERRED: on a version mismatch, compare the body hash, and answer `unchanged` if the body is already the one requested; or answer from the request key of principle 4. The first fix needs principle 7's change (an identical body leaves the version alone).
- **The error is already named.** `vfs.conflict` maps to ESTALE, the NFS stale-handle errno, and to errno 72 `STALE` in the WASI table (READ, `kinds.py`; spec 169 §b7 table). The WASI shim's close-time write-back is the natural first user: the version from the open-time `read` is in hand (READ, spec 169 §b4 reads `version`).

---

## 3. Nouns and verbs

"Adopt name" means use the book's word. "Adopt concept" means keep vfs's word for the same idea. "Not have" means deliberately absent.

| Book term | What it is | vfs today | Decision and reason |
|---|---|---|---|
| message, RPC | a request and its reply | an MCP `tools/call` and its `Result` (spec 171) | Adopt concept. MCP is the RPC layer. |
| stub generator, marshaling | code that packs arguments from a declared interface | `input_schema(op)` from `PARAMS`; base64 bytes (spec 171 §1.1) | Adopt concept. Already planned that way. |
| acknowledgment | the receiver's "got it" | `Result.success` after commit | Adopt concept. |
| timeout, retry | resend after silence | `vfs.timeout`; `RetryClass`; `retry_after_ms` (`kinds.py`) | Adopt concept. |
| exponential back-off | double the wait each retry | `with_retry` (`engine.py` L297–321) | Adopt concept. Already there. |
| sequence counter, message id | detects duplicates | none | Adopt concept as a request key (principle 4). |
| exactly-once, at-most-once | delivery guarantees | at-most-once per transaction; nothing across a lost reply | Adopt the names in docs: they say precisely what a replay gets. |
| end-to-end check, checksum | the endpoints verify the bytes | `content_hash`, not returned on write | Adopt concept; return it (principle 13). |
| stateless protocol | server keeps no client memory | per-request `authority`, path-keyed verbs (spec 171 §0) | Adopt the name. It is what vfs's wire already is; saying so guards it. |
| distributed state | state shared by client and server | spec 148's ledger and ring, if kept in server memory | Adopt the name as a warning label. |
| file descriptor, open-file table | a server-side cursor on an open file | none on the server; the WASI shim holds fds (spec 169 §b4–b5) | Not have, in the kernel. Fronts own handles, as NFS clients do. |
| file handle (volume, inode, generation) | stable low-level name on the wire | path on the wire; `entry_id` ULID and `mount_identity` inside (ADR 004, 019) | Adopt concept inside only. Paths stay the wire name; caches must not key on path plus version alone (principle 6). |
| generation number, uniquifier | stops a stale name hitting a new file | none needed for ULIDs; missing from `(path, version)` keys | Adopt concept where a cache keys on path. |
| attributes, GETATTR | the stat record | `stat` with `columns=` | Adopt concept. |
| change attribute (mtime in NFSv2) | what says "changed" | `version` (ADR 013, 017) | Adopt concept. vfs's is better than a clock. |
| LOOKUP | name to handle, one component | the resolve gate (`resolve_path`, `locate`) | Adopt concept. One index seek, not one per component. |
| READDIR with cookie | paged directory listing | `ls` returns everything | Adopt concept: the cursor the memo proposes. |
| READ/WRITE with offset | ranged body access | whole body only | Adopt concept for reads (memo `range=`); writes stay whole at v1. |
| idempotent operation | safe to replay | true for 5 of 11 mutating verbs, plus `mkdir(exist_ok=True)` (§2.1) | Adopt the name in each tool description and in `idempotentHint`. |
| client-side cache | local copies of server data | WASI staged buffers; spec 172's staged-buffer cache; the agent's context | Adopt concept; name the context window as a cache (§4). |
| update visibility, stale cache | the two halves of consistency | undocumented per front | Adopt the names. They make a clean two-column table (principle 8). |
| flush-on-close, close-to-open | write back at close, check at open | WASI `fd_close` is one `write` (spec 169 §b5) | Adopt the name for the WASI front. |
| attribute cache with timeout | skip validation for a few seconds | MCP `ttlMs`, set to 0 by spec 171 | Not have a nonzero TTL. It is what made NFS hard to reason about. |
| commit before reply | durability before success | `_mutate` commits, then returns | Adopt the rule as a stated invariant. |
| server write buffering, NVRAM | fast durable acks | the database's own WAL and group commit | Not have. The engine owns it. |
| VFS / vnode | a generic layer over many file systems | `VirtualFileSystem` router over `StorageBackend` (`base.py` docstring) | Adopt. It is the project's name. |
| mount protocol | how a client gets the root handle | `bind`, `add_mount`, `serve` | Adopt concept. |
| whole-file caching (AFS) | fetch at open, store at close | the WASI front | Adopt concept for that front. |
| Fetch / Store | whole-file transfer verbs | `read` / `write` | Adopt concept. |
| TestAuth | is my copy still valid? | `stat` and compare `version` | Adopt concept. |
| callback, break callback | server tells clients a file changed | none; ADR 013 pin 5 | Not have. It is server state, and models cannot be called back. |
| heartbeat | liveness probe after a crash | none | Not have; nothing to recover. |
| volume | movable unit of files | a mount | Adopt concept. |
| last writer wins (last closer wins) | the outcome of concurrent whole-file writes | `write(overwrite=True)`, the default (`base.py` L942) | Adopt the name; it is the honest description today. |
| global namespace | same names on every client | one `VirtualFileSystem` namespace (ADR 006) | Adopt concept. |
| access control lists | per-user rights | grants and the permission ladder (ADRs 062–080) | Adopt concept. |
| ESTALE | the stale handle error | `vfs.conflict`, mapped to `STALE` | Adopt; already mapped. |

---

## 4. What does not transfer, and why

- **Server crash recovery is mostly not vfs's problem.** NFS had to design statelessness in, because the server's memory was the only place state could hide. vfs's durable state is in a SQL database with its own log. A crash of the `vfs serve` process rolls back its open transactions and loses nothing a client relies on (INFERRED from principle 5's READ facts). The two real network hops are client to vfs (MCP) and vfs to the database, and both get the chapter's lessons; the process between them is nearly stateless already.
- **The biggest client cache cannot be invalidated.** NFS and AFS clients are kernels: they can be told, or can check, that a copy is stale. vfs's main client is a language model, and its cache is the conversation. A file read twenty turns ago is a cached copy with no timeout and no callback, and no protocol can reach into it (INFERRED). So the AFS and NFS tools, validate at open and break callbacks, have nothing to act on. The defence must sit at write time. `edit`'s content precondition already does this (EXECUTED); `if_version` would do it for whole-body writes.
- **The NFS argument for idempotent WRITE rested on offsets.** NFS WRITE is safe to replay because it names an exact offset and count. vfs writes whole bodies, which is also a store of a value, so it is safe for the same reason (EXECUTED). But an append verb, which the memo proposes, is an increment. It would be the first vfs write that is not idempotent by shape, and it needs a precondition or a request key from day one (INFERRED).
- **AFSv1's path-walk cost is gone.** `path` is a unique indexed column (READ, `rows.py`). A path costs one seek however deep it is. vfs's real per-call cost is the rights judgment, not the walk (READ, memo §2: one statement as system, three as a principal).
- **Generations are unnecessary for ULIDs.** Inode numbers are small and reused; ULIDs are minted once and never reused (READ, ADR 004, 019). The generation problem only comes back where a cache keys on path (principle 6).
- **Server-side write buffering and NVRAM do not apply.** Durability speed is the engine's job (group commit, its WAL). vfs only has to commit before replying, and it does.
- **UDP versus TCP does not apply, but its lesson does.** MCP rides HTTP or stdio, which are reliable streams. The chapter's point survives anyway: a reliable stream does not tell you whether the far end finished its work before the stream broke. The 2026-07-28 revision makes a broken stream a cancellation and the client re-issues (READ, open-questions entry). That is the end-to-end argument, at the application layer.
- **One server is not the vfs shape.** NFS and AFS assume one server per volume. vfs can run several `vfs serve` processes over one database, and the database is the single point of serialization (READ, ADR 078's lock row). ADR 022 already names this as its re-derive trigger: a multi-process host breaks "the host keeps admin" (READ, ADR 022 consequences).
- **Byte order and XDR do not apply.** JSON on the wire; bytes as base64 (READ, spec 171 §1.1).
- **Security transfers in reverse.** NFSv2 trusted the client about who the user was (READ, ch. 49 p. 16). vfs verifies a token at the edge on every request and refuses identity as data (READ, spec 149 rules 1 and 3). vfs starts where NFS ended up.

---

## 5. The one design lesson

The protocol decides how a distributed file system fails: NFS stays simple because each request stands alone and most requests can be sent twice, and vfs's wire already has the first property but has the second for only half its mutating verbs. vfs's clients are models whose cached copies no server can invalidate, so the consistency check has to move from open time, where NFS and AFS put it, to write time, as `edit`'s content match already does and `if_version` would for whole bodies. Make every mutating verb either safe to replay or recognisable on replay, and keep any state a conversation needs on the client or in a row, never in the server's memory.
