# Spec review: Nine shell implementation contracts

A fresh sub-agent of the author's session reviewed the nine added specs at `180ba6e64a05ae0e56ae0f945cdf1d5e032dfda2`, independently of drafting. The brief provided the diff, the repository, the questions below and a 45-minute ceiling; no author summary, discussion, proposed resolution or expected verdict was supplied. All thirteen review steps were reached inside the ceiling. Source probes confirmed the public path-only delete and version-only write, the parser constructing the tree before the machine constructs its memory meter, and the Wasm step having neither a timer nor correlation checking for a complete reply envelope. This was a design review of local sources, including existing ranged-read research and the shell recorder. No destructive reproduction, database benchmark, or implementation test was run. Labels: EXECUTED means the reviewer ran the cited source inspection; READ means the reviewer read the file cited; INFERRED means an implication of the written design.

## The author's questions, answered first

- INFERRED — Independently implementable areas include exact integer decoding, protected rm operand spellings, failed-writer latching and ordinary sed compile rejection. The package needs one agreed public range contract, a green feature rollout, timer/response schemas, and an atomic boundary between confirmation and deletion.
- INFERRED — The most consequential literal consequences are removal of a replacement entry after confirmation, work proportional to a whole database value for every small read, and a newly shipped bundled pair refusing to start ordinary lines.
- INFERRED — Most tests can use the existing native corpus, Wasm laws and SQLite/Postgres fixtures. Operation counts need to cover engine work, not just returned bytes. Timeout, concurrent replacement, fork and publication need controlled seams. The byte oracle and finite fuel must be distinguishable from an interpreter differential.

## Decisions, one line each

Short names below link to the exact revision. Numbers are decision numbers within each document. References H and M identify the ranked findings.

| Spec | Decision | Review |
|---|---:|---|
| [Wire][wire] | 1 | READ — Exact integer lexemes and scalar-pair validation give portable values. Apply validation in both directions. |
| Wire | 2 | INFERRED — Reject-before-dispatch protects a mixed document. Correlated replies and malformed input to an active instance need their own transition (H3). |
| Wire | 3 | INFERRED — Mutual acknowledgement is appropriate. Activation before feature implementations and unspecified host messages leave a broken intermediate release (H3). |
| Wire | 4 | READ — A rejected restart retains the original line and a terminal line can start afresh. Compare that with an invalid step, as H3 requests. |
| Wire | 5 | READ — Checked bounds, allocation order and instance serialization have directly observable cases. |
| [Runtime][runtime] | 1 | INFERRED — One absolute deadline and pre-dispatch checks cover the queue. Preserve existing storage cancellation at the outward cancellation boundary (H4). |
| Runtime | 2 | INFERRED — First terminal outcome, completed effects and no replay are coherent. Supervised cleanup needs an owner and drain rule (H4). |
| Runtime | 3 | INFERRED — Preflight input and charge overlapping buffers. Keep release/transfer rules across Python and Rust consistent with the admission budget (H5). |
| Runtime | 4 | READ — Fuel bounds, bool rejection and positive search limits provide countable admission. |
| Runtime | 5 | READ — Separate parse, execution, deadline and machine cancellation outcomes; checkpoint progress prevents a zero-slice spin. |
| Runtime | 6 | INFERRED — Process-local replacement avoids inherited initialization locks. Guard destruction as well as step/cancel (M3). |
| [Reads][reads] | 1 | INFERRED — Reader IDs and shared cursors solve reopen mixing. Define release on EOF/error/fatal teardown and handling of an already authorized in-memory suffix (H2, H3). |
| Reads | 2 | INFERRED — A raw caller-authorized range is useful; the public spelling, row semantics and unsupported-backend behavior conflict with spec 178 (H1). |
| Reads | 3 | INFERRED — An in-engine expression returns few bytes but its engine can repeatedly process the whole value (H2). |
| Reads | 4 | INFERRED — Public cursor suits incremental enumeration. Bound by bytes before materialization or explicitly define the minimum progress unit (H2). |
| Reads | 5 | INFERRED — Keep stat projections advisory and fail unknown closed. Declare their exposure in all faces and mask/projection rules (H1). |
| Reads | 6 | READ — Stable identity plus version, checked in the write transaction under current authority, closes same-version pathname reuse. |
| [Descriptors][fds] | 1 | INFERRED — Ordered authoritative opens fix redirection refusal order. Retain one-write optimization only for demonstrably inert expansion/invocation. |
| Descriptors | 2 | INFERRED — A refusal latches for all aliases, but a successful path open does not bind a later append to that object (H6). |
| Descriptors | 3 | READ — Explicit data/EOF/error, partial record handling and shared unread suffix have direct laws. |
| Descriptors | 4 | READ — Endpoint lifetimes, free-slot selection and joining substitutions give testable producer/consumer ordering. |
| Descriptors | 5 | INFERRED — Streaming tee removes whole-input duplication. The accepted -p option needs its own broken-pipe rule (M2). |
| [Builtins][builtins] | 1 | READ — Resolve binding and subscript once before updating; preserves unrelated elements and rightful arithmetic side effects. |
| Builtins | 2 | READ — Preserve nameref target, local shadow and literal private-use scalars; use the pinned oracle for state transitions. |
| Builtins | 3 | INFERRED — Nonconsuming probes and exact deadline tie rule are meaningful; no common wait/resume protocol or per-descriptor positive-timeout matrix yet (H3). |
| Builtins | 4 | READ — Owned waits and loop-control scope are clear. Charge retained completion records and release them under the memory owner. |
| Builtins | 5 | INFERRED — Checked %n has a direct state oracle. %a/%A shares an unresolved extended-precision dependency with the earlier active spec (M2). |
| [Parser][parse] | 1 | READ — Complete parse, quote removal, and inclusive counted limits make a request-free syntax refusal testable. |
| Parser | 2 | INFERRED — Accurate ownership after construction is insufficient to enforce admission while building the syntax tree (H5). |
| Parser | 3 | READ — Charge before allocation and model overlapping lifetimes. Count allocations, release on both normal and refused paths. |
| Parser | 4 | READ — Parse-time/deferred-depth distinctions and iterative wrappers retain meaningful error classifications. |
| Parser | 5 | READ — Full subscript recognition and function deparse/reparse specify visible semantic witnesses. |
| Parser | 6 | READ — Isolating the first overflowing case before increasing a harness stack protects the public entry point. |
| [File operations][files] | 1 | READ — Operand spelling is validated before normalization and the root after resolution; later valid siblings remain eligible. |
| File operations | 2 | INFERRED — Noncascade removal protects an unlisted child beneath a nonempty parent; same-name replacement still defeats a confirmed leaf delete (H7). |
| File operations | 3 | READ — Preserve occupied-target semantics, confirm only intended transfer and keep the actual transfer as authority. |
| File operations | 4 | READ — Parse unsupported modes before mutation; check each mkdir ancestor. |
| File operations | 5 | READ — Typed absence versus operational failure and quiet-grep precedence preserve useful evidence. |
| [Sed][sed] | 1 | READ — Entire script compiled and validated before auxiliary file effects, including scripts loaded from explicit sources. |
| Sed | 2 | INFERRED — Explicit script-read exceptions are clear. The order of auxiliary truncation and read versus repeated source opens needs a decision (H8). |
| Sed | 3 | READ — Opaque invalid-byte units and exact valid scalars avoid conflating raw bytes with private-use characters. |
| Sed | 4 | INFERRED — One successful publication per operand is a useful unit, but buffering later operands before earlier publication changes what bytes they observe (H8). |
| Sed | 5 | INFERRED — Identity-checked source and backup-before-replacement are sound. Decide how the source and backup select their stored body representation (H8). |
| [Filters][filters] | 1 | INFERRED — Raw record retention is sound. A pair-dependent fallback does not define one transitive comparator (H9). |
| Filters | 2 | READ — Exact decimal magnitude comparison avoids f64 rounding. Apply key construction to all records, including ill-formed byte strings (H9). |
| Filters | 3 | READ — Zero versus one empty pattern, option ordering and max-count zero have concise oracle cases. |
| Filters | 4 | READ — A local search exhaustion survives negation and never quietly selects a partial pathname set. Specify exact sed runtime status and effect ordering under H8. |
| Filters | 5 | READ — Live shell case options and hidden-path transitions provide independent, deterministic cases. |

## Acceptance criteria, countable as written

| Spec | Criterion 1 | Criterion 2 |
|---|---|---|
| Wire | READ — Exact integer round trips, zero mixed-batch dispatch. Add invalid reply-key cases (H3). | READ — Valid starts/steps, range allocations and negotiations; add a feature rollout matrix (H3). |
| Runtime | READ — Barriers distinguish queue, admission, verb and commit; add cancellation drain behavior (H4). | READ — Instrument actual reserve, encode, completed jobs and late child destruction (H5/M3). |
| Reads | READ — Real engines and split UTF-8 are appropriate; counting only returned bytes misses engine work (H2). | READ — Count live memory and cursors; cover typed field masks, bare rows and same-name reuse (H1/H2). |
| Descriptors | READ — Trace requests, bytes/statuses and saved write failure; add successful-open/replaced-target race (H6). | READ — Count fd reclamation, check saved suffix and tee prefixes; add the accepted -p mode (M2). |
| Builtins | READ — Declarations and byte-count conversion are observable; explicitly pin extended-precision results (M2). | READ — Shared-fd probes, fake-clock ties and job ownership are countable after defining timer protocol (H3). |
| Parser | READ — Boundary counts and zero-effect parse failure are meaningful; include budget refusal during parse allocation (H5). | READ — High-water and trap-free default-profile corpus are separate testable outcomes. |
| File operations | READ — Exact path/cascade traces cover newly named siblings; add same-name replacement (H7). | READ — Existing real-engine fixtures can test occupied targets and VFS deltas. |
| Sed | READ — Publication count, original/backup bytes, exit statuses and warning kinds can be fixed without wall times; add repeated/alias operands (H8). | READ — Byte fixtures, input identity and reserve-before-publish can use raw VFS observations (H8). |
| Filters | READ — Base64 records are supported by scripts/shell_record.py:154, permitting exact binary output. Add a three-record ordering law (H9). | READ — Local test budget can distinguish incomplete matches from ordinary misses; also distinguish shared line-fatal exhaustion. |

## The diagram and the scope

- READ — The nine drafts use the newer agents/ outcome/problem/decisions pattern. None identifies an architecture figure. Both the wire handshake and the cancellation lifecycle cross layers; a shared state diagram and a concrete reference documentation target would make their interfaces easier to review (M1).
- INFERRED — The parser can start independently. Wire validation can land with features disabled. Then the driver, bounded public storage operations and descriptor primitives can land with old/new sides interoperable. Timer support should activate with the scheduler and both drivers, guarded sed publication with the guarded storage host. File operations can follow the required removal semantics. Byte units can be introduced by sed, then reused by filters. Each stage should pass the old corpus before the next turns on a feature.
- READ — Other affected active sources include [binary transport][binary], [known failures and depth][known], [linear matching][linear], [verb budgets][budget], and especially [spec 178][range]. Paged listing is already implemented. The lists of internal prerequisites omit compatibility choices with these external drafts (H1/H3/M2).

## Scale and the production posture

- INFERRED — A 4 MiB sequential read at 64 KiB needs 64 authorized chunks. With SQLite's whole-value substr behavior, 64 full-value loads can represent 256 MiB of internal payload work even though the Python boundary transfers only 4 MiB. Across a stream of length B the risk is proportional to B²/chunk; [spec 178 §4.2][range] documents the operator behavior. This is a calculation, not a measured runtime (H2).
- READ — The repository's production posture supports 10,000-file batch verbs, SQLite and Postgres. Shell commands themselves already document per-path calls; preserve aggregate public read semantics and name the split between a shell single-file open and a batched reads API. Python memory proportional to returned bytes alone does not bound a storage driver's work or an abandoned transaction (H1/H2/H4).
- INFERRED — Per-entry reader metadata, fd records, pending replies and staged output need actual ownership and teardown counts. A byte allowance and a page limit expressed in rows are different units. A page that cannot hold its first entry needs a classified outcome without an endless cursor loop.

## Constitution and CLAUDE.md checks

- READ — Namespace, Entry, observation/Candidate, Mount and Revision remain the governing primitives. Reader keys are line-local protocol state and expected identity is a condition on a routed path; neither should become a public addressing mechanism.
- INFERRED — Articles 2 and 4 require negotiated host features to be distinguished from a mount's own declared ability to perform a bounded range/atomic guard. Verify unsupported on a mounted third-party backend without executing a whole read first, while existing ordinary read still works (H1).
- READ — Article 3 supports composed bytes/streams and caller-routed verbs. Article 5 and AGENTS.md support measuring actual bounded work on both engines. Rust owns the hot kernels; none of the specs introduces numpy or a pure-Python hot-path fallback. Use controlled timers for semantics; elapsed time is not a performance assertion.

## Premortem

1. INFERRED — A green wire-only commit enables an advertised protocol before the driver and backend can fulfill it; ordinary lines refuse at startup or an old client silently performs an unsafe unguarded edit (H3).
2. INFERRED — A large, frequently accessed document returns a small range per query, passing the proposed tests, but occupies the shared database doing full-value operations repeatedly (H2).
3. INFERRED — A user confirms an item, its path acquires a different object while waiting, and an authorized path-only operation then modifies the wrong object (H6/H7).

## Findings, most severe first

1. **H1 — Public range contract and backend declarations.** READ/INFERRED — [Reads §2–3, 5–6][reads] conflicts with roadmap K6 and [spec 178 §§1–7][range] on argument spelling, observation batches, text widening, column selection, returned fields, fallback and integrity. Pick a single contract or explicit distinct strict raw-byte mode, name superseded provisions and the migrated roadmap/ADR, write down integer bounds, update AsyncVFS/session/sync/sync-session, parameter admission, storage declarations and results. Specify canonical body versus rendering and original column gates, bare/missing metadata, conditional identity token lifetime and masked versus conflicting outcomes. Test all faces and a legacy backend. The current public interface and capability/trait declaration are in src/vfs/base.py:802 and src/vfs/storage/protocol.py:494.
2. **H2 — Actual bounded storage and genuinely bounded pages.** READ/INFERRED — [Reads §§1–4][reads] prescribes slices known to materialize a complete SQLite value; PostgreSQL whole-text conversion can do the same. Identify a measured bounded/linear-in-total-stream strategy per body kind and engine, or explicitly describe the unsupported case and fallback decision. Validate storage-side read/converted bytes or pages and statement counts, along with Python bytes. State how row count is converted to a byte allowance before list materialization, behavior when one legal row is too large, and which already-delivered bytes a buffered reader may consume after revoke. Reject unrequested future data and free readers locally on fatal/EOF. See [existing engine analysis][range] and [landed paging design][paging].
3. **H3 — Feature activation and response lifecycle.** READ/INFERRED — [Wire §§2–4][wire], [Builtins §3][builtins], [Reads §§1,4,6][reads] and [Runtime §1][runtime] need one small protocol table. Specify exact field shapes/widths, timer clock domain/units, expired and canceled wakes, concurrent runnable work versus waiting for data, and action on malformed, duplicate, unknown or missing reply keys. A machine currently ignores unknown keys, overwrites duplicate keys and can wait for missing replies (crates/vfs-shell/src/machine/mod.rs:382); malformed input is ambiguous on an active module (crates/vfs-shell-wasm/src/lib.rs:82). State when a whole message can be retried without effects. Distinguish a terminal batch's completed output from undispatched requests. Define positive timeout behavior per fd kind, including an EOF-ready pipe and host-backed regular file. Add combinations of old/new host/module, keep flags off until both implementations exist, and name exact legacy behavior for existing sed -i and timed read before redirections or mutation.
4. **H4 — Deadline versus caller cancellation and lifecycle of outstanding work.** READ/INFERRED — [Runtime §§1–2][runtime] allows cleanup beyond return. [The existing cancellation contract][cancel] requires the original CancelledError after SQLite transaction cleanup, and permits a queued storage attempt to take longer than a caller deadline. Distinguish timeout/124 delivery from external task cancellation delivery, name the owner of still-running cleanup and how close drains it, and preserve zero new requests after termination. Cover cancellation before commit, during commit, at the pool queue, repeated cancel and close while cleaning up using the existing controlled SQLite probes; state the Postgres outcome separately. Specify handling of the shared executor's inline fallback when a pool has shut down (src/vfs/offload.py:154).
5. **H5 — No parser budget owner exists at first allocation.** READ/INFERRED — [Parser §§2–4][parse] and [Runtime §§3,5][runtime] prohibit overshoot, but Machine::new calls parse before constructing the hub and parse(source, ParseLimits) has no logical-memory limit (crates/vfs-shell/src/machine/mod.rs:350; crates/vfs-shell/src/syntax/parser.rs:56). Define who constructs and moves the reservation across parse → from_script, what the pre-parsed/native public entry point promises, and the outcome when source/token/depth (2) competes with live allocation (137). Specify requested-capacity accounting before actual vector/string growth and overlapping Python/native temporaries. Test a token-legal, small-source AST over a tiny byte budget; count allocations and check zero host effects.
6. **H6 — Successful writer still follows the pathname after a replacement.** READ/INFERRED — [Descriptors §§1–2,5][fds] correctly makes a refused writer terminal. After a *successful* open, subsequent existing append requests address only path and create the file if missing (src/vfs/base.py:925, crates/vfs-shell/src/machine/files.rs:182). Another caller can replace/move that object and have later bytes reach a different entry. Decide binding semantics: compare the opened entry identity, allow same-entry concurrent appends and recheck rights at each write, or document the intentional pathname-based deviation and exact outcomes. Test two hosts/transactions, aliases and create-only followed by replacement. Name any feature dependency on the resulting guarded append.
7. **H7 — Confirmed pathname may now name an unconfirmed entry.** READ/INFERRED — [File operations §2][files] guarantees a new arrival survives. Current public delete is path/cascade only (src/vfs/base.py:1072, src/vfs/storage/backends/database/backend.py:781); checking identity and then issuing ordinary delete still leaves a race. Bind confirmation to an object identity checked atomically on deletion, or expressly define consent as applying to a pathname and narrow the promise. Supply both a newly named child and same-name replacement fixture. Specify whether a declined child suppresses the final parent prompt/removal and what -I confirms when a new item appears during a paged walk.
8. **H8 — Per-operand publication requires ordered opens, and byte representation matters.** READ/INFERRED — [Sed §§2–5][sed] can be implemented using today's eager, path-keyed operand loads (crates/vfs-shell/src/programs/mod.rs:293). A repeated operand or a later operand equal to an earlier backup then sees stale input, and guarded writing reports a spurious conflict. Specify open/read/evaluate/backup/conditional-publish before opening the next operand, early q/Q boundary, and when an auxiliary w target is created/truncated relative to aliased operands. Define whether identity edits retain a VFS binary body's stored kind even when its bytes happen to be valid UTF-8, and how backup/output differ. Current _body in src/vfs/shell/host.py:505 selects text for any valid UTF-8 bytes. Cover alias and repeated operand, source conflict versus output already applied, and distinguish sed local evaluation status from shared fatal 137.
9. **H9 — Numeric and raw-byte fallback orders can contradict one another.** INFERRED — [Filters §§1–2][filters] allows a pair to fall back to raw-byte comparison when an operand is ill-formed. Numeric order puts the valid record 2 before 10, whereas byte comparisons place the record with bytes 0x31 0xff between 10 and 2. That is a cycle. Define a key/comparator that orders every input in a single transitive domain for each selected option, independently of the other operand. Specify the last-resort byte tie-break and -u equivalence, then use triples with mixed encodings, numeric and case-folded keys to test antisymmetry/transitivity and first retained representative.
10. **M1 — Cross-layer architecture and verification ownership.** READ — All nine drafts lack architecture views, and their identical verification paragraph does not identify which tests own each new seam. Close with a shared state/ownership sketch for high-risk boundaries, named durable documentation targets (documentation/reference/shell.md, documentation/maintainers/cancellation.md), explicit dependency stages, and targeted existing suites plus planned named laws. There is no current context/architecture directory, so no new legacy tree is required.
11. **M2 — Existing option and precision contracts.** READ — [Descriptors §5][fds] specifies default stdout SIGPIPE while tee already accepts -p as a no-op (crates/vfs-shell/src/programs/text.rs:1693). Specify retained option semantics including -p under early close, '--', option errors and named outputs, and record the appropriate GNU cases. [Builtins §5][builtins] requires exact Bash %a/%A while crates/vfs-shell/src/machine/printf.rs:419 parses f64 and the [known-failures spec][known] owns 80-bit formatting. Name the implementation order/owner, pin default/explicit precision plus an extended-only input, and run the pre-existing corpus after both landings.
12. **M3 — Fork cleanup includes object destruction.** READ/INFERRED — [Runtime §6][runtime] forbids touching inherited Wasmtime state but explicitly guards only step/cancel. Dropping the last inherited Python object in the child or tearing down the interpreter can invoke the Rust destruction path for its Instance. State the PID-gated drop/no-destruction rule, supported platform/embedding boundary and which parent resource is intentionally abandoned until child exit; exercise child collection and new machine startup in a bounded subprocess while the parent remains usable.

## Checked and found clean

- READ — Each spec preserves the separation between shell command status and a line-level classified failure. The byte corpus records pinned GNU/Bash output independently and allows a separately recorded VFS policy difference.
- READ — Ordered backup then guarded replacement explicitly accepts partial publication, successful prior files stay committed and a conflicting target survives. A stat probe remains advisory: an actual mutation checks current rights.
- READ — Read continuation, no mixed revisions, logical versus Wasm memory, first line-fatal stop and parent-owned waitable jobs have clear, testable intended outcomes. A default-stack test for the actual parse/machine entry point constrains the allowable harness exception.

## Disposition

The first revision addressed H1–H9 and M1–M3 in the nine contracts. The second revision resolved the remaining read-path locking, guarded directory removal, object revival, backup representation and wire-field issues. The independent re-reads below record the disposition of every finding.

The local review and published commits have identical Git trees at each checkpoint. The published revisions are [initial draft](https://github.com/ClayGendron/vfs/commit/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc), [first amendment](https://github.com/ClayGendron/vfs/commit/e2737c6a0cf986748928113aa293be9b3dbe96da) and [signed specifications](https://github.com/ClayGendron/vfs/commit/9c5c7dc038a090a3be96f47b97ad2847052cdffb).

## Verdict

**Not yet: H1–H9 and M1–M3 remain open on 180ba6e6.**

[wire]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-wire-and-instance-lifecycle/spec.md
[runtime]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-runtime-termination/spec.md
[reads]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-file-reads-and-metadata/spec.md
[fds]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-descriptors/spec.md
[builtins]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-builtins-and-variables/spec.md
[files]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-file-operations/spec.md
[parse]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-parsing-and-memory/spec.md
[sed]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-sed-edits/spec.md
[filters]: https://github.com/ClayGendron/vfs/blob/4051b964f3caa9e77c2aeb7f9fcb95d2a3048fcc/agents/2026-11-22-shell-filters-and-matching/spec.md
[range]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/context/specifications/active/178-the-ranged-read/spec.md
[cancel]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/documentation/maintainers/cancellation.md
[binary]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md
[known]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/agents/2026-11-21-the-shell-closes-its-known-failures/spec.md
[linear]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/agents/2026-11-21-the-shell-matches-in-linear-time/spec.md
[budget]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/agents/2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md
[paging]: https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md

### Independent re-read on 089eb630

READ — The nine specs were independently re-read at commit `089eb630be612c7a7d9297c624da445a0af3089a`. The comparisons below refer to that commit even if a newer working copy exists. Source checks used the existing storage implementation to distinguish a hypothetical race from an actual contract mismatch. No implementation or attack reproduction was run.

| Original finding | Disposition check | Remaining work at this revision |
|---|---|---|
| H1, public ranges | READ, confirmed. The shared ordinary ByteRange contract, bounded exact mode, raw versus rendered data, four public faces, capability advertisement, masking and verification are now explicit. | None on H1. |
| H2, storage work and paging | Partially confirmed. SQLite incremental reads, indexed PostgreSQL text/byte projections, row/byte page budgets, cursor progress and authorization of buffered bytes repair the original design. | Reads, “Physical byte reads and upgrade,” allows a PostgreSQL read on a stale projection to lock the entry and backfill. This makes a reader wait behind writers, contrary to the repository's production rule. Complete the backfill/dual-write rollout outside the read path. Serve a current projection from a snapshot; report unsupported for a missing/stale projection or use a genuinely bounded lock-free alternative. Pin a held writer, first read of a stale projection, and unchanged reader-side write count. Update the two superseded cache-eviction regression cases to test refusal and EOF/close release. |
| H3, protocol | Partially confirmed. Optional rollout, timer transport, partial-versus-complete batches, malformed-step poisoning, reply correlation and legacy command refusal are now specified. | Wire “Interfaces and edge cases” leaves the meaning of an unknown local read_close unclear against the explicit successful no-op in Reads. Distinguish syntactically valid local close, invalid identifiers and invalid next in both documents. Make stat_meta.size explicitly nullable for callers such as find -empty. Implement the backup representation agreement under H8. |
| H4, cancellation | READ, confirmed. SQLite and PostgreSQL settle before an externally canceled await re-raises its original exception. Deadline settlement, third-party cleanup ownership, router close and executor rejection are named. | None. |
| H5, parse admission | READ, confirmed. The metered parser receives reservations before growth, transfers them to the Hub, separates parse-only from machine admission and defines source/parse/runtime classifications. | None. |
| H6, writer object | Partially confirmed. The successful opening mutation returns the object token, later appends use atomically reauthorized if_object, and two ordinary appenders can coexist. | Object comparison uses mount registration and entry_id alone. A production write at a tombstoned pathname revives the same row and preserves its entry_id (src/vfs/storage/backends/database/writes.py:21; restore operates on the same IDs in trash.py:334). Delete/revive between two flushes admits the old writer despite the stated effect of deletion. Define an incarnation/generation that changes on revived lifetimes but is constant across ordinary writes, or explicitly allow same-ID revivals as the same object. Pin a complete delete→revive between chunks separately from a different-ID replacement. |
| H7, confirmed remove | Partially confirmed. Leaves bind approval to identity and version in the deleting transaction; declined and new children survive. | File operations “Interfaces and edge cases” re-authorizes an updated directory version for a final -i prompt, but -I has one initial prompt. A noncascade child delete bumps its parent (src/vfs/storage/backends/database/trash.py:145). A strict parent token from the snapshot becomes stale during a normal successful -rI. Define an atomic same-object/empty-directory guard for directory removal, or carry forward the newly committed parental revision as each authorized child is removed. Preserve full identity/version guards for files. Add a successful removal of a multi-level nonempty tree after one yes, alongside replacement and new-child cases. |
| H8, sed ordering and representation | Partially confirmed. Operand timing, auxiliary outputs, q/Q and source/backup representation are now specified in the sed program. | The ordinary wire Write still has only a byte payload and mode. It cannot request the original representation for an unguarded backup, whereas guarded_write carries source. The Python adapter otherwise turns UTF-8-decodable bytes into text (src/vfs/shell/host.py:505). Define a negotiated unguarded write with a source discriminator, including validation and a bytes-backed, valid-UTF-8 round-trip/backup case through Wasm and both real engines. |
| H9, comparator | READ, confirmed. All inputs share one numeric key function and an independent total textual unit ordering. Ties, uniqueness and permutation tests are defined. | None. |
| M1, architecture and verification | READ, confirmed. Each contract now maps its boundary and names a target regression suite/test and the durable shell documentation. | None. |
| M2, existing options and precision | READ, confirmed. The tee modes and early pipe closure are specified, and the prior extended-precision implementation is explicitly required for %a/%A. | None. |
| M3, fork destruction | READ, confirmed. The PID check covers Rust/Python destruction, and the child-abandonment scope, platform boundary and collection test are explicit. | None. |

**2026-11-22, re-read on 089eb630: Not yet.** H2, H3, H6, H7 and H8 need the concrete amendments above. The remaining seven findings are confirmed closed at this revision.

### Independent re-read on 670b5935

READ — The separate amendment `670b5935655eb29e077c364c309453707b4f3987` changes the five contracts implicated by the previous verdict. The findings closed on the previous revision remain closed. The table verifies the outstanding clauses against the new text.

| Finding | Disposition verification |
|---|---|
| H2 | READ, confirmed. Exact PostgreSQL reads now take an ordinary MVCC snapshot, neither lock nor repair a row, and return bounded unsupported on a stale projection. Backfill, reconciliation and activation belong to deployment. A held writer, a stale projection and a fresh post-repair read have explicit tests for zero reader-side DML and row locks. The old live-reader eviction scenarios were replaced by admission pressure, ownership and EOF/close checks. |
| H3 | READ, confirmed. The wire explicitly distinguishes a foreign/malformed close, an idempotent valid local close and invalid next; unknown size is nullable. The bounded I/O feature includes both the new guarded directory form and the representation-bearing backup mutation with validation before dispatch. |
| H6 | READ, confirmed. Durable namespace incarnation changes on revive, restore and path-changing moves, including affected descendants. Existing rows have an upgrade rule, and ordinary concurrent appends retain their object guard. A real-engine deletion and same-ID revival between writes is now a dedicated case. |
| H7 | READ, confirmed. Files keep strict versioned guards. The noncascade guarded directory delete binds the same object and its current kind, permission and emptiness in one transaction independent of its version. A one-confirmation successful recursive deletion is tested alongside inserted-child and replaced-parent preservation. |
| H8 | READ, confirmed. Negotiated write_body carries a text/bytes discriminator for an ordinary authorized backup write. Both real engines and the Wasm/Python path must preserve a bytes-sourced body even when its bytes are valid UTF-8. |

No outstanding finding remains on the revised specifications. The engine counts, corpus cases, rollback/fork tests and compatibility fixtures are implementation acceptance work; they were not executed during spec review.

**2026-11-22, re-read on 670b5935655eb29e077c364c309453707b4f3987: Fit to build.**
