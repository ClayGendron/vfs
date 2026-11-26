# Decisions verified: the pending kind, the suspended stage, the answer and resume API

Scope: rows D9, D10, D12, D44 and D45 of `context/standards/roadmap.md` section 16, at HEAD 0ed462f on 2026-11-25. Labels: EXECUTED (a command ran here), READ (path:line), INFERRED (reasoning). Nothing in `src/` settles any of the five: no `pending` kind, ticket, ledger, `answer` or `resume` exists, and `ErrorKind` holds no suspended-step kind (READ, `src/vfs/results/kinds.py:63-97`; EXECUTED, a grep for `pending` over `src/vfs` returns only render status and posture relabel hits).

## D9. vfs carries `pending` and never asks and never blocks

Lean: yes; amend ADR 084 pin 4 so vfs carries `pending` (READ, `context/standards/roadmap.md:1081`).

Verification: holds-amended.

Decision text: vfs never asks a person and never holds a call open; a host policy hook, a gate refusal a principal could lift, a host tool, a mounted server's `input_required` and a guest's door call may each suspend a step into a `pending` `Result` carrying a ticket, which a host answers and resumes through the ledger; this rule is carried as a numbered decision in the interrupt spec that replaces story H1, which amends spec 148 §5 and spec 170 §4's elicitation row in place of ADR 084.

Reason: ADR 084 was retired on 2026-10-30 with every decision record, so "amend ADR 084 pin 4" amends nothing; a spec must carry the rule (READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:49`, the rulings spec's own account of where retired-record items now live). The substance is consistent with the tree: spec 148 §5 already says "storage never blocks, crashes or auto-rejects" (READ, `context/specifications/active/148-sessions-narrowing-and-pending/spec.md:21`), and the only live text that contradicts it is spec 170's row mapping an elicitation to `vfs.unsupported` "no ask inside vfs, ADR 084 pin 4" (READ, `context/specifications/active/170-tools-and-mcp-servers-as-views/spec.md:108`), which story H5 criterion 4 already flips (READ, `context/standards/roadmap.md:342`). Constitution Article 2 rejects a pattern that makes a caller "guess, retry blindly, or parse prose to learn state" (READ, `context/standards/constitution.md:92`); a classified stop with a ticket is the opposite of that. At the reference deployment a stop costs no held connection or lock, so the per-lock rule of AGENTS.md is untouched (INFERRED).

Precedent: MCP 2026-07-28 replaced the server-to-client back channel with MRTR, an interim `input_required` result the client retries with answers attached (READ, `context/research/2026-08-10-mcp-2026-07-28-stateless-revision.md:18`, `:69-76`); the OpenAI Agents SDK stops a run with `RunResult.interruptions` and resumes it from state, with no timeout (READ, `context/research/2026-09-05-permissions-lens-agent-native-2026.md:116`); ADK re-executes the tool with the answer and an argument match (READ, same memo `:117`); Mirage's `ask` rule returns a refusal record with an ask id into a ledger a host answers (READ, `context/research/2026-09-04-mirage-design-patterns.md:120`).

Specs affected: 148 (§5), 149 (§5, the wire shape), 169 (169a's `jobs` head, 169c's records), 170 (§4's failure table), 171 (scope), 172 (a guest's door call as a step).

## D10. `pending` is a top-level kind with retry class `resume`, its ledger lives with the action log, and its rows live 24 hours

Lean: top-level `vfs.pending` with a derived retry class `resume`; the ledger in the mount's schema; TTL 24 h (READ, `context/standards/roadmap.md:1082`).

Verification: holds-amended (the ledger's home).

Decision text: `ErrorKind` gains one core kind, `vfs.pending`, severity `error`, whose `KIND_CONTRACTS` row carries a new derived `RetryClass.resume`; the ask ledger is one table in the root binding's storage beside the action log and the replay store, so one store serves a bare verb and a multi-mount run alike; a ticket's expiry is a per-storage setting defaulting to 24 hours, judged when the ticket is answered or re-sent, and a row past it is reclaimed by the replay store's sweep arm as garbage collection, never as a verdict.

Reason, the kind: the vocabulary dispatches by longest dotted prefix and a child degrades to its parent (READ, `src/vfs/results/kinds.py:33-42`). A child of `permission_denied` (the Mirage memo's proposal, READ, `context/research/2026-09-04-mirage-design-patterns.md:306`) would misstate the family for four of the six producers (a policy hook on an allowed call, a host tool, an MCP elicitation, a guest), none of which is a denial, and would inherit a reading of "never retry" for a step that is meant to be resumed (INFERRED). Decided 2026-11-15 for the integrity kind (D8): a child kind where the parent is the right family (READ, roadmap `:1080`); here the parent would be the wrong family, so the same rule gives a top-level kind. The pre-release stage leaves no old consumer to degrade gracefully for (READ, `AGENTS.md`, "Project stage").

Reason, the home: the lean's "mount's schema" predates the third roadmap revision, which moved every run, step and ask row to the root binding's storage (READ, `context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/12-review-the-durable-run.md:4`, `:34`); H1 criterion 5 and H4 rule iv say root binding (READ, roadmap `:295`, `:322`) while H3 criterion 6 and this row keep the older word (READ, `:316`, `:1082`), and H3 itself names H0, whose rows live in the root binding, as "the ledger's home" (READ, `:278`, `:310`). A `cli` line spans mounts and has no single mount to live in (INFERRED). Mirage keeps "one record type, one store" for waiting and settled asks (READ, Mirage memo `:120`). An earlier conversion study marked this choice needs-a-ruling (READ, `agents/2026-11-25-the-backlog-converted/studies/051-162/148-sessions-narrowing-and-pending.md:53`); the story text cited here settles it, and if D43 is ruled otherwise this row follows D43.

Reason, the TTL: Decided 2026-11-15: a stored first answer is kept 24 hours by default, and the ruling's reason is that the ask and run ledgers share that window so an approval cannot outlive its key (READ, rulings spec `:83`; roadmap `:1083`). Spec 177 already makes the window a per-storage `replay_hours: int = 24` (READ, `context/specifications/active/177-replay-the-contract-and-the-request-key/spec.md:338`). Judging expiry only at answer or re-send keeps spec 148's "storage never auto-rejects" (READ, spec 148 `:21`). Ask rows arrive at a person's rate, a few hundred a day against 150,000 verb calls, so the table and its sweep are negligible at the reference deployment (INFERRED from the AGENTS.md table).

Precedent: MCP keeps `input_required` as a result type apart from errors (READ, MCP memo `:44`); A2A keeps `TASK_STATE_AUTH_REQUIRED` as a task state of its own (READ, lens memo `:123`); spec 177's replay store, a TTL'd table in storage swept by one arm (READ, spec 177 `:338`, `:374`).

Specs affected: 148 (§5), 149 (§5), 171 (the wire kind), 177 (the sweep arm gains the ask table).

## D12. A suspended shell stage exits with one declared status

Lean: 75 (`EX_TEMPFAIL`) (READ, roadmap `:1084`; used in H5 criterion 1, `:339`). No spec carries a number (READ, the row's own words).

Verification: needs-a-ruling.

Decision text: Needs a ruling: a suspended stage's status is either 75 (`EX_TEMPFAIL`) or 149 (128 + `SIGTTIN`, the status bash reports for a job stopped waiting on input); either way the number is one entry in spec 167's exit-code table, distinct from 126, and the stage's `vfs.pending` record, never the number alone, identifies a suspension.

Option 75: BSD `sysexits.h` defines `EX_TEMPFAIL 75 /* temp failure; user is invited to retry */`, "not really an error ... the request should be reattempted later" (EXECUTED, `grep EX_TEMPFAIL /usr/include/sysexits.h`; `os.EX_TEMPFAIL` prints 75). It matches H3's re-send model and collides with nothing in spec 167's table (READ, `context/specifications/active/167-the-shell-pipeline-core/spec.md:71`: 0, 1, 2, 124, 126, 127, 130). Cost: its meaning is "re-attempt", while the durable run continues rather than re-attempts (INFERRED).

Option 149: bash reports 149 for a job stopped by `SIGTTIN` (EXECUTED: `set -m; sleep 3 & kill -TTIN $!; wait $!` printed `status=149` under bash 5.2.21). The roadmap's own analogy for the durable run is a job stopped with `SIGTTIN` and continued with `fg` (READ, roadmap `:247`), and vfs's tables already follow 128 + signal for 130, 134 and 137 (READ, spec 167 `:71`; `context/specifications/active/169-programs-the-index-and-the-vfs-views/spec.md:231-234`). Constitution Article 3 asks vfs to follow the Unix convention "as completely as possible" (READ, `context/standards/constitution.md:96`). Cost: a script reads 128 + n as "killed by signal n" (INFERRED).

Rejected by the tree: 126, Mirage's status for a pending refusal (READ, Mirage memo `:120`, `:132`), because H5 criterion 4 moves the elicitation row away from 126 so a suspension is never read as "cannot run" (READ, roadmap `:342`). Spec 169's `75 XDEV` is a WASI errno, a separate number space, not a stage status (READ, spec 169 `:207`). Both options cost nothing at the reference deployment; a program's own exit 75 or 149 is told apart by the `vfs.pending` record (INFERRED).

Specs affected: 167 (the exit-code table), 169 (the guest's stage status), 170 (§4's failure table), 172 (a guest's ask).

## D44. A principal answers each ask, and a run is resumed once by its run id

Lean: `answer(ticket, …)` per ask and `resume(run_id)` per run; a bare verb's ticket is its run id, so `request_key=ticket` stays the one-step resume (READ, roadmap `:1118`).

Verification: holds-amended (the anonymous caller).

Decision text: `answer(ticket, …, authority=)` records one attributed answer per ask, and `resume(run_id, authority=)` continues a run once its answers are in, serving the answered stages and stopping again on any still open; a bare verb's ticket equals its run id, so re-sending the identical call with `request_key=ticket` is its one-step resume; because a request key needs a named caller, a call that would suspend under the anonymous authority answers `vfs.unauthenticated` instead of `pending`; over MCP the MRTR retry of `tools/call` with `inputResponses` is the wire's composition of answer and resume, and `answer` and `resume` are also served as two tools for a principal other than the caller.

Reason: answers arrive one at a time, from different principals and processes (READ, roadmap `:241`); a single `resume(run_id, answers={…})` would require one caller to hold every answer, which the cross-principal case of H4 criterion 4 and M3 criterion 3 rules out (READ, `:326`, `:791`). Spec 177 refuses a request key from the anonymous caller "every anonymous caller is the same principal, so their keys would share one space" (READ, spec 177 `:263`), so the lean's one-step resume does not exist for that caller and a ticket handed to it would be resumable by every anonymous caller (INFERRED); `vfs.unauthenticated` is the kind whose hint is "this ... needs a name" (READ, `src/vfs/results/kinds.py:183-187`). The ledger check sits in the router ahead of the hook (READ, roadmap `:311`; audit 12 `:11`). An answer costs one ledger insert and a resume one keyed seek, at a person's rate (INFERRED).

Precedent: the OpenAI Agents SDK approves or rejects each interruption and then resumes the run from its state (READ, lens memo `:116`); the MCP tasks extension delivers `inputResponses` with `tasks/update` and resumes by polling (READ, MCP memo `:93`); MRTR's retry carries the answers in the retried request (READ, MCP memo `:76`); spec 177's replay hit makes the second re-send return the first answer (READ, audit 12 `:10`).

Specs affected: 148 (§5: `Session.answer` does not exist), 149 (§5), 171 (two served tools, MRTR), 177 (`request_key` reused as the ticket).

## D45. A resumed step runs as the run's recorded authority, and only that principal or a qualified approver may resume

Lean: the run's recorded authority, always, re-judged by the gate; `resume` allowed to the principal that started the run or to an approver holding `read_write` on every open ask's path (READ, paraphrased, roadmap `:1116`).

Verification: holds-amended (what the answer adds).

Decision text: the run row records the starting authority (actor, subjects, narrowing, provenance), and every resumed step runs under it, re-derived and re-judged by the gate; the only thing the gate counts beyond it is the answer to that step's own ask, a one-shot allowance bound to the request digest, never any other right of the answering principal; `resume` is permitted to the named principal that started the run or to a principal holding `read_write` on every path the open asks name, checked through the chunked rung seam; a run started anonymously has no resuming principal (D44).

Reason: the roadmap's two texts disagree. H4 criterion 4 says a step the starting principal could not do is `permission_denied` (READ, roadmap `:326`), while H3 criterion 3 suspends exactly such a step, a refusal a principal could lift, and criterion 4 answers it by writing an allowance (READ, `:313-314`); spec 148 §5 makes answers "grant rows or one-shot allowances ... keyed by digest" (READ, spec 148 `:21`). The amended text keeps both: the approver lends no rights, and the one allowance the ask named admits the one call it describes (INFERRED). `read_write` is the top rung (READ, `src/vfs/ops.py:117`), the same bar H3 sets for `answer` (READ, roadmap `:314`). An ask over a 10,000-path batch is judged in `membership_budget` slices by the `rungs_at` seam spec 170 defines, about ten statements at the Oracle floor (READ, spec 170 `:124`; INFERRED arithmetic), and only on a resume, a person's act.

Precedent: spec 177 scopes a key to actor, subjects and narrowing so a second principal is never served the first's answer (READ, spec 177 `:248-263`); MCP's `requestState` SHOULD embed the authenticated principal and reject state presented by a different one (READ, lens memo `:123`); A2A's `AUTH_REQUIRED` transition authorizes nothing by itself (READ, same line); audit 12 names the escalation this rule closes (READ, audit 12 `:22`). POSIX `kill()` lets a privileged sender or one with a matching user id continue a stopped process, which keeps its own credentials (INFERRED from the POSIX text as generally documented; pubs.opengroup.org was unreachable from this session's network and was not read).

Specs affected: 148 (§5), 149 (§5, the principal digest), 169 (169c's record, keyed today by an equal `Authority`, READ, audit 12 `:15`), 171 (the resume tool), 177 (the scope rule reused).
