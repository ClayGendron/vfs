# Decisions verified: the durable run, its ledger, and the action log

Scope: rows D40, D41, D42, D43, D46, D52, D53 and D54 of `context/standards/roadmap.md` section 16 (READ, `context/standards/roadmap.md:1112-1126`), the stories that name them (H0, H1, H4, H5, F3, F7, T2), the backlog specs those stories rewrite or amend (148, 167, 169, 170, 171, 172, 177, 180), and the review of the durable-run design (READ, `context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/12-review-the-durable-run.md`). None of these rows is marked Decided. Decided 2026-10-28: analytics is a must for 0.1.0, the elapsed time of every call is a must, the log is the checkpointer, and a run with several asks picks up where it stopped instead of re-running (READ, `context/standards/roadmap.md:239`, `:278`, `:322`).

Landed work: nothing in the tree settles any row. No action-log table, run ledger, ask ledger, `request_key`, `in_doubt` kind, `RUN_LEDGER_BYTES` or `LOG_RETENTION_DAYS` exists under `src/vfs` (EXECUTED, grep over `src/vfs`; the only `replay` hits are unrelated docstrings in `base.py`, `versioning.py`, `rows.py`, `writes.py`, `permissions.py`). No shell exists in `src/vfs` (EXECUTED, `ls src/vfs`). The archive holds no spec on these subjects (EXECUTED, `ls context/specifications/archive`).

## D40. When one step asks, the run drains its pipeline, then stops

Lean: drain, then stop, per pipeline; a suspended stage's consumer sees neither data nor end-of-stream; later statements of the line are not run (READ, `context/standards/roadmap.md:1112`).

Verification: HOLDS.

Decision text: "When a stage of a pipeline asks, every other stage of that pipeline runs until it finishes or reaches its own ask, and every ask raised is reported in one stop; the consumer of a suspended stage receives neither data nor end-of-stream, so an early-closing consumer such as `head` neither closes nor completes; no later `;`, `&&` or `||` statement of the line runs."

Reason: the drain is what lets asks raised together be answered together, and scoping it to the pipeline that asked keeps `set -e` and list semantics intact: a later statement can depend on the asking stage's status, so it cannot run before the answer (INFERRED, following the review's hole 4, READ `12-review-the-durable-run.md:28`). The review proposed stopping at the first ask instead; the roadmap kept the drain because two stages of one pipeline can ask concurrently at gate b (READ, `12-review-the-durable-run.md:76`).

Precedent: LangGraph surfaces the interrupts raised by parallel nodes of one step together and resumes them in one call with a map from interrupt id to answer (public docs, https://docs.langchain.com/oss/python/langgraph/interrupts; multiple-interrupt resume introduced in LangGraph v0.4, https://changelog.langchain.com/announcements/ann_gihffEmRqXpOM). POSIX `read()` on an empty pipe blocks while any process holds it open for writing and returns end-of-file only when no writer remains (POSIX.1-2017 `read`, https://pubs.opengroup.org/onlinepubs/9699919799/functions/read.html), which is exactly "neither data nor end-of-stream" for a consumer whose producer is suspended, not exited. Spec 167's early-close rule cancels a producer at its next emit (READ, `context/specifications/active/167-the-shell-pipeline-core/spec.md:129`); the decision text keeps it, since a consumer that is waiting on a suspended stage has not closed.

Specs affected: 167 (§5 pipeline execution and early close, F3 and F6 slices), 169 (the `/.vfs/jobs` head), 170 and 171 (a tool or `tools/call` stage that asks inside a pipeline, H5 criterion 5), the durable-run spec that rewrites 169c (H4).

## D41. A run records its effects, its expansion reads, and the identity of every other read

Lean: effects, expansion reads (`glob`, `$( )`, `find`, `stat`, `test`) and every read's identity triple always; bodies only where a guest or tool consumed them, within `RUN_LEDGER_BYTES`; a re-executed read is hash-checked (READ, `context/standards/roadmap.md:1113`).

Verification: HOLDS.

Decision text: "A run's ledger records every effect, every expansion read (`glob`, `$( )`, `find`, `cd`'s `stat`, `test`, and the nondeterministic words of D54) and the `(entry_id, version, content_hash)` of every other read, whatever the budget; it records a body only where a guest or a host tool consumed it, within `RUN_LEDGER_BYTES`; a body read re-executed on resume whose `content_hash` differs from the recorded one refuses the run `vfs.conflict`."

Reason: expansion reads decide the shape of the walk (operand counts, argv), so a world that moved between stop and resume would make the re-walk a different line; recording them always keeps the walk the same, and the hash check turns any other drift into a classified refusal instead of a silent divergence (READ, the review's hole 3, `12-review-the-durable-run.md:26`). Recording every pipe-stage body would put corpus bytes into the ledger at the per-step multiplier for no reader, since a pipe stage can always re-read (READ, `12-review-the-durable-run.md:73`; INFERRED against AGENTS.md's per-verb-call row).

Precedent: Temporal persists activity results and side-effect values in the event history and replays them, while workflow code itself is required to be deterministic and is not recorded (public docs, https://docs.temporal.io/develop/go/side-effects). The identity triple is the identity vfs already stores on every entry and version row (READ, `src/vfs/models/rows.py:436`, `:548`). The roadmap's own H4 rule ii and criteria 3 and 10 carry the same split (READ, `context/standards/roadmap.md:322`, `:325`, `:332`).

Specs affected: the durable-run spec (H4), 167 (F3 criterion 10, the determinism law keyed `(stage, ordinal)`, READ `context/standards/roadmap.md:629`), 169 (169c rewritten as rows), 172 (a guest's consumed inputs).

## D42. A stopped guest or host tool is re-entered from the start, its vfs calls served by fingerprint

Lean: re-enter and match by fingerprint at 0.1.0; recording every host import and snapshotting guest memory are 0.2 (READ, `context/standards/roadmap.md:1114`, `:1054`).

Verification: HOLDS.

Decision text: "On resume a host tool or a Python or JavaScript guest is entered again from its start; each vfs call it makes is keyed by its ordinal within the stage and served from the ledger when its fingerprint equals the recorded one; a call whose fingerprint differs is issued fresh, counted, with one `vfs.replay_diverged` info record naming the ordinal; host-side effects made before the interrupt run again, and the how-to says so."

Reason: vfs does not own the code, so it cannot make it deterministic; the only honest rule is to serve what provably repeats and issue fresh what does not, never answering a different call with a stale result (READ, the review's hole 6, `12-review-the-durable-run.md:32`). Temporal fails a workflow on a non-deterministic replay; that option is unavailable here because the code is a third party's and a failed re-entry would strand the run (INFERRED). Recording every host import needs a linker drift test and buys little at 0.1.0 (READ, `12-review-the-durable-run.md:30`, `:75`).

Precedent: LangGraph resumes by re-running the interrupted node from its start, returns saved answers to `interrupt()` in order, and documents that code before the interrupt runs again (public docs, https://docs.langchain.com/oss/python/langgraph/interrupts). The fingerprint is spec 177's sha256 over verb and canonical arguments (READ, `context/specifications/active/177-replay-the-contract-and-the-request-key/spec.md:265-268`).

Specs affected: 170 (host tools, §4's interrupt row), 171 (`cli(request_key=)`), 172 (one door through which every host import passes), 177 (the fingerprint reused), the durable-run spec (H4, H5).

## D43. The run ledger lives in the root binding's storage, with a per-run body budget and a 24-hour TTL

Lean: the root binding's storage; `RUN_LEDGER_BYTES` = 64 MiB per run (spec 169c's number), oldest run evicted first; TTL 24 h on the replay store's sweep arm (READ, `context/standards/roadmap.md:1115`).

Verification: HOLDS-AMENDED.

Decision text: "The run head, step pages and ask rows live in the root binding's storage beside the replay store; `RUN_LEDGER_BYTES` (64 MiB) bounds the recorded bodies of one run, and a run past it keeps recording effects, expansion reads and identity triples and stops recording bodies, which are re-read and hash-checked on resume; no run is evicted before its TTL; run and ask rows live 24 hours and are reclaimed by the replay store's sweep arm in chunks."

Reason for the amendment: "oldest run evicted first" is the per-process ring of spec 169c, whose 64 MiB is shared across all authorities (READ, `context/specifications/active/169-programs-the-index-and-the-vfs-views/spec.md:282`). Applied to a per-run budget it has no meaning, and applied across runs it would destroy a stopped run still waiting on its answer, turning a resume into an expiry, which breaks the decided "picks up where it left off" rule (INFERRED from `context/standards/roadmap.md:239`). H4 criterion 10 already states the per-run degrade (READ, `context/standards/roadmap.md:332`), so the amendment resolves the scope question an earlier study left open (READ, `agents/2026-11-25-the-backlog-converted/studies/165-181/169-programs-the-index-and-the-vfs-views.md:50`). An aggregate cap would be a designed scale ceiling, which AGENTS.md forbids absent an external limit (READ, AGENTS.md, "Never design toward a hard scale cap"). At the reference deployment, stopped runs arrive at the rate of asks answered by hand, not the 150,000 daily verb calls, and median bodies are 4 KB, so the 24-hour population is small; the 64 MiB figure is a ceiling per run, not an expected size (INFERRED from AGENTS.md's table). H4 criterion 12's "eviction direction (oldest run first)" and T2's byte eviction for the ledger change with this text; T2's count eviction of `/.vfs/run` output rows is a separate record and is not judged here.

Precedent: the 24 hours equal the replay store's default, ruled with D11 (READ, `context/standards/roadmap.md:1083`; `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:85`; `177/spec.md:338`) and the sweep arm is spec 177 §4's (READ, `177/spec.md:368-373`). The root binding as home follows the review's hole 7: a line spans mounts and only the root is reachable from every resume (READ, `12-review-the-durable-run.md:34`).

Specs affected: 169 (169c rewritten as rows), 177 (§4 sweep arm gains the run tables), 180 (the sliced sweep absorbs the arm), the durable-run spec (H4 criteria 10 and 12).

## D46. A step left `running` by a crash is in doubt and the host answers `done` or `redo`

Lean: in doubt; the host answers `done` or `redo` (READ, `context/standards/roadmap.md:1117`).

Verification: HOLDS-AMENDED.

Decision text: "A resume that meets a step row still `running` never re-enters it on its own: a host tool, a `tools/call` or a guest's effectful door call answers `vfs.unavailable.in_doubt` as an ask naming the step, and `answer(ticket, allow=True, outcome="done" | "redo")` either records the step as done or re-enters it once; a kernel verb step that carried its replay key is resent under that key, which answers what happened if it committed and runs it if it did not."

Reason: an external effect whose outcome vfs cannot observe is not safe to repeat or to skip, so only the party that can look outside vfs decides (INFERRED). The amendment exempts kernel verbs because spec 177 already makes a keyed resend safe: the claim and the recorded answer commit with the change, so a resend after a crash finds the stored answer or runs the call (READ, `177/spec.md:412`); and the replay key lives 24 hours, as long as the run (READ, D43 above). Raising an ask about a step vfs can resolve itself would add an ask at no gain. The roadmap's own law states kernel verbs at most once through their own keys (READ, `context/standards/roadmap.md:322`, rule iii).

Precedent: spec 177 answers a dropped commit `vfs.unavailable.in_doubt` and never redrives it server-side (READ, `177/spec.md:406`, `:418`). PostgreSQL leaves a prepared transaction whose coordinator vanished for manual resolution by `COMMIT PREPARED` or `ROLLBACK PREPARED` from any session (public docs, https://www.postgresql.org/docs/18/sql-commit-prepared.html; https://www.postgresql.org/docs/18/sql-prepare-transaction.html). Temporal and DBOS instead re-execute an interrupted step (at-least-once); that is the `redo` answer, available but never chosen by vfs alone.

Specs affected: 177 (§5 in doubt reused), 170 and 171 (spec 170 §3.3's "never auto-retry" for `tools/call`, READ `12-review-the-durable-run.md:24`), 172, the durable-run spec (H4 criterion 7), the action-log spec (H0 criterion 3's `running` row).

## D52. The action log is on by default, keeps rows 30 days, and `log=False` turns it off

Lean: on by default with `LOG_RETENTION_DAYS = 30` and a `log=False` escape; run and ask rows keep their own 24 h; analytics is a 0.1.0 must (READ, `context/standards/roadmap.md:1124`).

Verification: HOLDS-AMENDED.

Decision text: "The action log is on by default, keeps its rows `LOG_RETENTION_DAYS` (30) days on the router and reclaims older rows by the sweep arm in chunks of `membership_budget`; `VirtualFileSystem(log=False)` writes no log rows, `fs.calls()` then answers `vfs.unsupported`, and a durable run is unavailable: a line's first ask answers `vfs.unsupported` and `traits()` says so, as for a root without the `replay` trait."

Reason: the default follows from the ruling that analytics is a 0.1.0 must (READ, `context/standards/roadmap.md:278`), and the default stands on L0's GO, which measures the bar of zero synchronous statements per read and two per effect (READ, `context/standards/roadmap.md:271-274`). The amendment closes a contradiction: H4 makes a run's steps action-log rows (READ, `context/standards/roadmap.md:322`, rule iv), so H0 criterion 6's "zero log rows" under `log=False` would leave a run with no ledger; the precedent for the answer is H4's own rule for a root without the `replay` trait (READ, same line). Arithmetic: at about 150,000 verb calls a day, 30 days is about 4.5 million rows, one row per call (a 10,000-file batch is one row); reads add no synchronous statement and the roughly 50,000 daily single-file writes add two each, about 100,000 statements a day, each one bounded row (INFERRED from AGENTS.md's table and H0 rules i and iii).

Precedent: SQL Server 2022 turns Query Store, a per-query runtime record kept in the user's own database, on by default for new databases, with `STALE_QUERY_THRESHOLD_DAYS` defaulting to 30 (public docs, https://www.microsoft.com/en-us/sql-server/blog/2022/08/18/query-store-is-enabled-by-default-in-sql-server-2022/; https://learn.microsoft.com/en-us/sql/relational-databases/performance/manage-the-query-store).

Specs affected: the action-log spec (H0, new; criteria 6 and the `traits()` line), the durable-run spec (H4), 169 (T2's record as an action-log row), 177 and 180 (the sweep arm).

## D53. At 0.1.0 the action log is read as a documented table and through `fs.calls` by the system actor

Lean: a documented, frozen table schema plus `fs.calls(...)` on the management plane for the system actor, with a `/.vfs/log` view and rows readable by other principals in 0.2 (READ, `context/standards/roadmap.md:1125`, `:1058`).

Verification: HOLDS-AMENDED.

Decision text: "The action log's table schema is documented in `docs/reference/analytics.md` and, from the beta, frozen under the beta rule: no column is renamed, removed or changes meaning, and columns may be added; `fs.calls(since=, until=, actor=, verb=, outcome=, limit=, after=)` is a management method answered to the system actor alone, paged on the listing key, never a served tool or a program name; a `/.vfs/log` view and log rows readable by other principals are 0.2."

Reason for the amendment: "frozen" in the lean would forbid the additive columns a beta allows for every other public name; the beta freeze forbids renames, removals and changes of meaning and admits additions (READ, `context/standards/roadmap.md:17`, `:60`). The system-actor limit holds because a log row names paths across principals, and a non-system reader would learn of rows it cannot read, which the landed scan-tier rule forbids (READ, `context/specifications/archive/2026-11-12-the-scan-tier-reveals-nothing-about-rows-a-caller-cannot-read.md`, title).

Precedent: vfs already keeps management calls outside `Op` in `MANAGEMENT_METHODS` (READ, `src/vfs/ops.py:106-110`) and answers the mount table as an API rather than a view (D38, READ `context/standards/roadmap.md:1110`). SQL Server documents Query Store's catalog views as a schema queried with ordinary SQL (public docs, https://learn.microsoft.com/en-us/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store).

Specs affected: the action-log spec (H0 criteria 1, 7, 8), 169 (`log` stays unserved in the head table), 171 (T1 and M1's served-heads pins gain the `fs.calls` absence), 181 (K9's frozen list).

## D54. The shell's nondeterministic words are recorded and replayed under the durable run

Lean: record each of `$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `$EPOCHREALTIME`, `$BASHPID`, `$$` and `date` as an expansion read (D41) and replay it on resume (READ, `context/standards/roadmap.md:1126`, F7 criterion 7 at `:651`).

Verification: HOLDS-AMENDED.

Decision text: "Each expansion of `$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `$EPOCHREALTIME`, `$BASHPID` and `$$`, and each run of `date`, is recorded in the run's ledger as a value of its stage, keyed by its ordinal, and served from the ledger on resume; the values are part of the stage's recorded step, never an action-log row of their own."

Reason: the alternative, refusing these words in a line that may ask, cannot be applied, because whether a line asks is decided while it runs, by the policy hook and by liftable gate refusals (READ, H3 criteria 1 and 3, `context/standards/roadmap.md:311`, `:313`), so under a hook every line may ask (INFERRED). The amendment keeps H0's rule that a row is a call, never a finer unit (READ, `context/standards/roadmap.md:278`, rule i): a loop may expand `$RANDOM` up to `LOOP_ITERATION_BUDGET` times, 1,000,000, and one row per expansion would write a million rows for one line, whereas a value list in the stage's page rows is bounded by `BLOB_PAGE_BYTES` pages (INFERRED from `context/standards/roadmap.md:324` and the budget recorded in `agents/2026-11-25-the-backlog-converted/studies/165-181/167-the-shell-pipeline-core.md:61`).

Precedent: Temporal's `SideEffect` stores a nondeterministic value in the event history and returns the recorded value on replay without running the function again (public docs, https://docs.temporal.io/develop/go/side-effects). The earlier study of spec 167 found the same precedent (READ, `agents/2026-11-25-the-backlog-converted/studies/165-181/167-the-shell-pipeline-core.md:58`).

Specs affected: 167 (the F7 slice, criterion 7), the durable-run spec (H4).
