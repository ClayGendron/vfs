# 12 — Review of the durable-run design (roadmap third revision)

- **Status:** review of `context/standards/roadmap.md` §5 (H1–H6), F3
  criterion 10, T2, T5, M3, §14 and decisions D40–D44 as they stood
  after Clay's 2026-10-28 request that a run with several
  human-in-the-loop events pick up where it stopped instead of
  re-running. Read-only; one subagent; every claim labelled READ,
  EXECUTED or INFERRED. The roadmap's third revision folds in (a) 1–7
  and 9, holes 1–8, the criterion rewrites, the arithmetic and (e)
  1–4 and 6; (e) 5 was kept as drain-per-pipeline with `xargs -P`
  riding F6.
- **What changed because of it:** a resumed step runs as the run's
  recorded authority (D45); effectful steps are claimed before entry
  and a crash leaves an in-doubt step (D46); expansion reads are always
  recorded and re-executed reads are hash-checked (D41); the ledger
  lives in the root binding's storage (D43); host tools and guests are
  re-entered with their vfs calls matched by fingerprint (D42); H3's
  second re-send is a replay hit, not `pending`; T2 lands as rows;
  `/.vfs/jobs/<run>/steps` is 0.2.

---

## (a) Contradictions with the repo's records

1. **H3 criterion 5 vs spec 177's replay flow.** The draft said a second re-send with `request_key=ticket` "is `pending` again (one-shot spent)". Spec 177 stores the first successful answer under the key and serves it on every later send: `context/specs/active/177-replay-the-contract-and-the-request-key/spec.md:496` ("A live row answers"), `:513` (record on success), `:543` ("A resend answers what happened, not what would happen now"). Under 177 the second re-send is a replay **hit** with `vfs.replayed`, not `pending`. 177's is the safer behaviour (a lost reply to the approved call must get the same answer back). READ.
2. **H3 criterion 1's hook order vs spec 177's lookup placement.** The hook runs "after the gate's structural checks and before storage"; 177's key lookup runs *inside* storage's mutation runner, inside `attempt()` (`177/spec.md:483-500`, `:539`). So a re-send with an answered ticket reaches the policy hook *before* anything has seen the ticket; the hook says `pending` again and the call never proceeds. The ask-ledger check must sit in the router ahead of the hook, which 177 does not provide. READ/INFERRED.
3. **"Served only to the same caller" vs cross-process, cross-person resume.** 177 scopes `request_id` to actor + subjects + narrowing (`177/spec.md:427-449`) and refuses a key from the anonymous caller (`:445`). H3's `request_key=ticket` therefore works only for the original caller; H4/M3's "resume from a different process, by an authorised approver" and spec 171's anonymous HTTP caller (`context/specs/active/171-the-mcp-adapter-and-the-cli-tool/spec.md:58-59`) cannot use that door. The page never said which authority a resume runs under (see hole 1). READ.
4. **H4 criterion 2 records failed `Result`s; 177's store records only successes** (`177/spec.md:513-517`: "A failed `Result` is not stored"). The page called them "one row family" but the two have opposite retention rules, and the replay store "never carries bytes" (`177/spec.md:560-562`) while step rows carry read bodies. Step rows must be a separate table with their own rule. READ.
5. **H4 criterion 9's chunked sweep vs 177's unsliced arm.** 177 §4 says the chunked sweep is spec 180's shape and "until 180 lands, the arm is the two whole statements" (`177/spec.md:667-695`). K5 c5 had the same drift. READ.
6. **Spec 169c's record is keyed by the exact `Authority` value** (`context/specs/active/169-programs-the-index-and-the-vfs-views/spec.md:627-634`: "Only an equal `Authority` reads a record"). H4 c8 copied "another authority's read is `not_found`" while M3 c3 lets "an authorised approver" continue the run; under the copied rule the approver cannot read the ask they approve. READ.
7. **Spec 169a reserves `jobs` as unserved** (`169/spec.md:84`). H4 serves it; 169a's head table was missing from H1's amendment list. READ.
8. **ADR 084 pin 1 and pin 4** (`context/decisions/084-…md:72-76`, `:97-100`) and **ADR 063 rule 5** ("Timeout is the host's policy, never storage behaviour", `context/decisions/063-…md:65-66`) are contradicted by H3 c5 / H4 c9 (TTL judged by storage). The page names both amendments in H1 c1, so these are acknowledged, not silent. Spec 170 §4's elicitation row (`context/specs/active/170-…/spec.md:292`) is likewise acknowledged. READ.
9. **Spec 167 §7's `Session.cli` write-back** ("A call snapshots `cwd` and `env` at start and writes them back at end, whatever its status", `context/specs/active/167-the-shell-pipeline-core/spec.md:480-483`) and ADR 081 pin 6/11 (`set -e` and shell state are per call, `081-…md:106-111`, `:141-149`): a stopped run "ends" its call, so the session's `cwd` moves; the resume re-walks the line from the top. Nothing on the page said the run row records starting `cwd`, `env`, `workdir`, the `set -e` state or the authority shape. Without that, `cd /a && asking_tool && ls` resumes from `/a` and walks `cd /a` again (harmless here, wrong for `cd sub`). READ/INFERRED.

## (b) Design holes, ranked

**1. Resume authority was unspecified — privilege confusion (security, blocking).** If unrecorded steps run under the *resumer's* authority, an agent's line finishes with the approver's rights (escalation), or an approver with narrower rights breaks it. If they run under the recorded agent authority, then anyone who can present a `run_id` can drive the agent's remaining mutations. Scenario: agent Alice's line `cat secret | upload; rm -rf /shared` stops at `upload`; approver Bob calls `resume`; `rm -rf /shared` runs — as whom, authorised by whom? Fix: the run row stores the stopping `Authority` (actor, subjects, narrowing, provenance); every resumed step runs under *that* authority re-derived; `authority=` on `resume` only answers "may this principal resume": the run's owner, or an approver who holds `read_write` on every path the open asks name. Also make `requestState` (M3) bind run_id + the recorded actor digest so a token for one principal cannot resume another's run. INFERRED.

**2. Crash semantics were absent — "nothing happens twice" was only true for a clean stop.** A process dying with a host tool, a `tools/call` (spec 170 §3.3 rule 4: no idempotency key, never auto-retry, `170/spec.md:243-246`) or a mutation in flight leaves no step row; the next `resume` re-enters it. Scenario: Postgres worker OOM-killed mid `upload`; `resume` uploads again. Fix: claim-before-enter for effectful steps (177's claim-first shape: insert the `(run_id, stage, ordinal)` row with status `running` before entering a tool/mutation; a resume that meets a `running` row refuses `vfs.unavailable.in_doubt` for that step and asks the host) and state the law: kernel verbs at-most-once (claim + their own replay keys), host/MCP tools at-most-once *when stopped*, in-doubt after a crash. INFERRED.

**3. The determinism law was false for early-close and for degraded reads.** (i) spec 167 §5 / ADR 083 pin 10: a producer is "cancelled at its next emit" (`167/spec.md:342-345`; `083-…md:135-137`). `cat a b c | head -1` issues `read(b)` or not depending on whether `head` closed before `cat`'s second emit (queue depth 2). The per-stage key sequence is scheduling-dependent by construction; F3 c10 as written was a flaky test. Guests have the same shape via the cancel-flag sentinel (`169/spec.md:559-562`). (ii) D41's degrade: past `RUN_LEDGER_BYTES`, reads were re-executed. But reads *are* inputs to later keys: `$( )` output becomes argv (`167/spec.md:356-359`), glob expansion becomes operand count (`:365-371`), `find` candidates drive `xargs -n` batch count, and a guest's `path_open` → `read` body drives its control flow (`169/spec.md:365-380`). If the world moved, the re-walk produces a *different* key sequence than the recorded one and the replayed prefix is served against the wrong line. Fix: (a) F3 c10 states the law as "same keys up to the chunk the consumer consumed; early-close lines are excluded from the pin"; (b) split reads into *expansion reads* (glob, `$( )`, `find`, `cd`'s `stat`, `test`) that are always recorded regardless of budget, and *body reads* that may degrade; (c) a degraded body read always keeps `(entry_id, version, content_hash)`; on re-execution a mismatch is `vfs.conflict` on the run, never a silent divergence; (d) a resume whose re-walk produces a key not in the ledger (or a ledger key the walk does not produce) refuses `vfs.internal` with both keys named. READ/INFERRED.

**4. D40 "drain then stop" vs `set -e` and `head`.** With `set -e`, a stage that asks (exit 75) must not let later statements of the list run; "drain" must be scoped to *the pipeline that asked*, not the whole line. `cat big | asking_tool | head -1`: `head` closes after one chunk while `asking_tool` is suspended; draining the producer to completion and cancelling it (ADR 083 pin 10) were both defined; which wins? Fix: define "round" = the set of stages of the *current pipeline* that are runnable without an answer; the drain is per pipeline; a suspended stage's downstream consumer sees EOF-pending (not EOF), so `head` neither closes nor completes; later `;`/`&&` statements are "not run". INFERRED.

**5. Guest replay is deterministic only with a closed import list, and the list given was wrong.** The draft named the door, `clock_time_get`, `random_get`, `args_get`, `environ_get`. Spec 172 says the preview1 file calls are the other way out (`172/spec.md:165-166`) and the shim issues verbs on `path_open`/`fd_close`/`fd_sync` (`169/spec.md:365-420`); `poll_oneoff` (`time.sleep`), `sched_yield`, `fd_read` on stdin (deterministic only because 169 b10 materializes stdin, `:553-557`) and `proc_exit` are host imports too. Threads: none (`172/spec.md:174-175`). The real risk is a host import *the list misses* returning a non-recorded value. If full determinism is wanted, the law is "every function the host links into the instance is a step, enumerated by the linker table, and a drift test asserts the ledger's step kinds == the linker's exports". Also `WALL_TIME_BUDGET` (10 s per line, `084-…md:107`) restarts per walk and each re-instantiation pays the prefix's fuel and epoch again. READ/INFERRED. *(The revision took (e) 4 instead: re-entry with fingerprint-matched door calls.)*

**6. Host-tool memoisation (H5 c2) assumed the tool's `Fs` calls are a deterministic function of the recorded answers.** A tool that branches on time, a network call, or `random` makes a different sequence of `Fs` calls on re-entry; the ledger then serves recorded answers to the wrong calls. LangGraph has the same rule; the page copied it but did not say what happens on divergence. Fix: key tool-internal `Fs` calls as `(stage, ordinal)` within the tool, and on re-entry compare the call's fingerprint (177 §3.3) against the recorded one; a mismatch is a *fresh* call (statement issued, counted), with a `vfs.replay_diverged` info record naming the ordinal — never a served wrong answer. INFERRED.

**7. Where the ledger lives for a multi-mount line.** "The mount's schema" was singular; a `cli` line spans mounts, views re-enter the router at the root (`169/spec.md:113-131`), and the root may be `InMemoryStorage` while a submount is Postgres. A run stopped with its ledger in memory does not survive a worker. Fix: the ledger lives in the **root binding's** storage (same rule as grants on `/.vfs` paths, `169/spec.md:93-97`); a root without the `replay` trait makes `cli` lines that ask `vfs.unsupported` at the first ask, and H4's cross-process criterion is parametrised over the root's engine. READ/INFERRED.

**8. `/.vfs/jobs` leaks bodies across principals only if ownership is sloppy — but ticket replay was a real gap.** Step rows hold read bodies; the view must be scoped to the recorded run authority, and an approver sees only `asks/` (plan blocks), not `steps/`. Ticket replay: a ticket spent by `answer` admits "exactly one re-run" — the admission is checked in the ask ledger before the hook (hole 2's fix), and a concurrent double re-send must be serialised; reuse 177's claim-first insert on the ticket row so the second sender waits and gets the replay hit. INFERRED.

**9. Budget `RUN_LEDGER_BYTES` = 64 MiB *per run* on a shared SQL engine** with no per-principal or per-mount cap means N concurrent runs hold N × 64 MiB of bodies in the mount until a 24 h sweep. Not a cap on vfs's scale (CLAUDE.md), but the number should be a documented floor with the eviction direction named. Minor.

## (c) Criterion rewrites

- **H4 c1** "in the same scheduling round" — undefined. Rewrite: "Two asks raised by `xargs -P 2` children of one pipeline appear in one stop result (`len(asks) == 2`, one `vfs.pending` error, one run row with `status='stopped'`, counted), and every stage of that pipeline not waiting on an answer has status 0 or 1, never `running`."
- **H4 c2** "bodies offloaded by `BLOB_PAGE_BYTES` pages, chunk boundaries kept" — chunk boundaries cannot be observed by any consumer (guests and tools materialise; kernels obey the split law, F6 c2). Rewrite: "…holds N + M step rows; a step whose packed `Result` exceeds `BLOB_PAGE_BYTES` is `ceil(size / BLOB_PAGE_BYTES)` page rows (counted); no statement's bind count grows with the body."
- **H4 c3** add the negative: "a resume whose re-walk produces a step key absent from the ledger refuses `vfs.internal` naming both keys with zero mutation statements."
- **H4 c4** add "and issues zero `tools/call` re-sends (spied)".
- **H4 c7** must say which mount holds the ledger: "…the run, step and ask rows are in the *root* binding's schema; the battery binds the root on each engine leg with an in-memory submount."
- **H4 c9** "stops recording read results" — ambiguous. Rewrite: "…stops recording *body* reads but keeps every expansion read and every read's `(entry_id, version, content_hash)`; a resume re-executes body reads (statements counted = number of degraded reads) and a re-read whose `content_hash` differs is `vfs.conflict` on the run."
- **H5 c2** "the how-to says in one line…" — docs, not a test; mark "CI evidence (docs gate)".
- **H5 c3** list incomplete (hole 5); if full determinism: "The set of step kinds recorded for a guest equals the set of functions linked into the instance minus `fd_read`/`fd_write`/`fd_seek`/`fd_tell` on staged buffers (drift test over the linker table); the pandas job with one ask instantiates the guest exactly twice (spied), issues each verb to storage once (statements counted), and its stdout equals the uninterrupted run's."
- **H5 c5** "in the same boundaries" — drop; keep "the consumer received exactly the bytes the producer emitted before the stop (byte count equal) and the resumed line's stdout equals an uninterrupted run's."
- **F3 c10** — a flaky pin as written (hole 3). Rewrite: "For a line with no early-closing consumer, two executions over the same world produce equal per-stage key lists (compared as lists); for `cat a b c | head -1` the test asserts only that the recorded prefix equals a prefix of the uninterrupted sequence; keys never carry a timestamp, a task id or a queue position (a grep over the key type)."
- **M3 c1** name the mechanism: "HMAC with the server's key; a one-byte change is `vfs.invalid` with zero handler calls (spied)"; add "a `requestState` whose principal digest differs from the run row's actor is `vfs.permission_denied` with zero steps run."

## (d) Arithmetic (§14)

EXECUTED (summed the story sizes from the headings; S=1 d, M=2–4 d, L=5–10 d, XL=10–20 d, 5-day weeks):

| Batch | Composition on the page | Recount from headings | Effort recount | Page |
|---|---|---|---|---|
| a2 | 2 L, 3 M, 7 S | matches | 4.6–7.8 | 5–8 ✔ |
| a3 | 9 M, 8 S | matches | 5.2–8.8 | 5.5–9.5 ✔ |
| a4 | 1 XL, 2 L, 2 M | matches | 4.8–9.6 | 5–9+ ✔ |
| a5 | 4 L, 3 M, 2 S | matches | 5.6–10.8 | 6–11.5 (high end +0.7) |
| a6 | 2 L, 3 M | matches | 3.2–6.4 | 3–6.5 ✔ |
| beta→final | 1 L, 7 M, 4 S | **F6 is "M + M"**: 1 L, 8 M, 4 S | 5.0–9.2 | 5.5–10 (high) |
| Total | | | 28.6–52.4 | the page said 31–57; its own rows sum to 30.6–55.1 |

The named critical chain K2, F3, F4, T1, T3, T4, M1, H4, H5 is **nine** L/XL items, not seven. a6 carries M3, I4, H6 which are gate `f`; the beta→final row omits them, which is why the two views of "what is left after b1" disagree.

## (e) Over-engineered for 0.1.0; the smaller honest version

1. **Recording chunk boundaries**: no consumer can observe them. Drop; record each stage's plain-projection bytes and re-slice by the declared constants.
2. **Recording every read's full `Result` within 64 MiB** (D41): the only reads that *must* be recorded are expansion reads and the bodies a *guest* or *tool* consumed. Pipe-stage body reads can always be re-executed and hash-checked. Honest version: record effects + expansion reads + the identity triple of every read; record bodies only for guest/tool inputs.
3. **T2 as a per-process ring then rewritten to rows by H4**: throwaway work on the critical path. Land T2 as rows in the root binding from the start (S → M), delete 169c's ring.
4. **Guest replay from recorded imports** (D42) is correct but buys little at 0.1.0 over treating the guest as a host tool: re-executed, its door calls memoised by fingerprint, a diverging call made fresh and marked. That removes the "every host import is a step" machinery and the linker drift test; the memory snapshot stays 0.2.
5. **Two parallel asks surfaced together** (D40) is an `xargs -P` feature that F6 (gate f) does not ship at b. For 0.1.0b: stop at the first ask per pipeline; D40 becomes an `f` story riding F6. *(Not taken: two stages of one pipeline can ask concurrently at b; the drain is per pipeline.)*
6. **`/.vfs/jobs/<run>/steps`** exposes read bodies through a view for no stated consumer; ship `asks/` only, keep `steps` for the operator in 0.2.

One line: the model (stop, record, re-walk) is sound; what was missing was *whose* authority a resume runs under, what a crash leaves behind, and the admission that reads are inputs to the key sequence — and H3 c5 contradicted the replay spec it stands on.
