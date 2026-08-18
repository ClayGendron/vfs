# Matcher offload — one design for loop occupancy and the backtracking residual

- **Date:** 2026-08-18
- **Provenance:** commissioned by the remediation-landing decision pass
  (`2026-08-18-remediation-landing-review.md`, "Decision pass") to
  ready the one decision that settles both recorded forks in
  `../open-questions.md` — "Grep verify occupies the event loop" and
  "Bounding the pure scan's backtracking residual". Three
  investigations, run 2026-08-18: a code-seam study of the verify
  path and the pyo3 boundary; a prior-art study (SQLAlchemy's asyncio
  bridge, the MCP python-sdk and fastmcp, opendal's Python binding,
  zoekt, codesearch, plus CPython facts verified empirically on
  3.10–3.14); and executed experiments on the installed engines
  (Apple M1 Pro laptop; medians over 2,000–5,000 trials for
  microbenchmarks). Probe and experiment scripts lived in the session
  scratchpad (ephemeral); this memo carries the operative numbers.
- **Headline:** the Rust seam **already releases the GIL** — every
  heavy pyo3 entry point wraps its work in `py.detach` over
  GIL-independent `PyBackedBytes`, and the batch is rayon-parallel
  inside — so offloading the matcher call to a worker thread fully
  fixes loop occupancy on the Rust engine (measured: a 1.56 s native
  call off-loop leaves worst-case tick gaps of 29–41 ms, versus
  1,535 ms on-loop today). On the pure engine a thread bounds loop
  stalls at the **longest single `re` call** (the GIL hands over
  between calls: 171 consecutive short matches produced ≤21 ms gaps)
  but cannot touch a single pathological backtracking episode (a
  2.13 s sre call stalled the loop 2,151 ms from a thread vs 2,141 ms
  on-loop, and an `asyncio.wait_for` timeout of 0.5 s could not even
  fire until sre finished). Only killing a process truly stops the
  burn (measured dead at 0.507 s) — a mechanism none of the studied
  libraries adopted. The per-call thread tax is ~38 µs median.
- **Feeds:** the offload decision/spec when the concurrency story
  becomes active work; until then both `open-questions.md` entries
  stay open pointing here. Adjacent: the semantic-chunking pool
  question (same library-posture frame) should be settled in the same
  decision.

---

## 1. What the seam already provides

The verify stage is the tail of `grep_rows`
(`storage/backends/database/grep.py`): candidates merge path-ordered,
`_content_batches` slices them under the 32 MiB
`CONTENT_BYTE_BUDGET`, bodies are fetched per batch, and the matcher
is invoked **synchronously inside the coroutine, once per batch** —
`verifier.count_lines(texts, ...)` / `verifier.hit_lines(texts, ...)`
against the `ContentMatcher` protocol (two methods, `Sequence[Body]`
in, index-aligned results out, `strict=True` zips downstream).
Facts that bind any offload design:

- **The Rust binding detaches the GIL today.** `python.rs` wraps
  `count_batch`/`hits_batch` (and the postings builder) in
  `py.detach(...)` — pyo3 0.29's rename of `allow_threads` — taking
  bodies as `PyBackedBytes` (GIL-independent owned handles, `Send +
  Sync`) with the `&[u8]` slices bound before the detach. No copying
  is needed, no new GIL work is owed, and inside the detached region
  the batch is already rayon-parallel across bodies. What remains
  on-loop is only the Python-side seam work (the `_as_bytes` list
  build and result conversion, measured as the residual ~30–40 ms
  gaps).
- **Both matchers are immutable after compile and per-call** — the
  Rust `Matcher` holds one `regex::bytes::Regex` (internally
  thread-safe), `_PureMatcher` two compiled `re.Pattern`s with all
  scan state method-local. One in-flight batch per verifier is safe
  from a worker thread today; *concurrent* calls on one instance are
  unverified and should stay out of scope.
- **Deadline fidelity has a trap.** The storage caller converts its
  absolute deadline to a relative budget at call time
  (`budget = max(0.0, deadline - monotonic())`), and both engines
  re-anchor that budget to their own clock at entry. Queue wait
  between computing the budget and worker start would silently extend
  the wall — an offload must pass the absolute deadline or recompute
  the budget at worker start.
- **Ordering and truncation contracts.** Rows stay path-sorted
  because batches are consumed in order and results are index-aligned;
  an incomplete batch appends the "wall-time budget" truncation and
  breaks the batch loop. Offload must keep batches sequential (no
  cross-batch reordering) and preserve the completed→truncate→break
  flow.
- **Cancellation today is clean but late.** The synchronous matcher
  call cannot be interrupted; `CancelledError` lands at the next
  await (worst case the full remaining wall). Nothing swallows it
  (`with_retry` catches only `DBAPIError | StaleSnapshot`), sessions
  close via `async with`, and the StaticPool serialized-session lock
  releases in `finally`. Under `to_thread` cancellation ends the
  *await* while the thread runs to completion — safe here because
  content is fully materialized before the matcher runs (the worker
  never touches the session), but an orphaned worker holds its
  ≤32 MiB batch until it finishes, and a `StaleSnapshot` redrive
  re-runs the whole call, so a superseded worker from the prior
  attempt must be (and is) harmless.
- **This would be the first thread in `src/`.** No
  `to_thread`/executor/`threading` use exists anywhere in the live
  tree; the only sync-in-async bridge is SQLAlchemy's own greenlet
  `run_sync` for DDL. The semantic-chunking entry already names the
  posture question: a library verb spawning workers — processes
  especially — is a deployment decision, not a local optimization.

## 2. Measured behavior (executed experiments)

Ticker harness: a 10 ms `asyncio.sleep` loop recording inter-wakeup
gaps (idle median ≈ 11.0 ms). Pathological pure workload:
`(a+)+bcd` vs one line of `'a'*25` → 2.13 s of uninterruptible sre
backtracking (doubling per character, matching the docstring's
profile). Benign Rust workload: a word-shaped regex over ~5 GB of
bodies → 1.53 s native call.

| Experiment | Result |
|---|---|
| Sync call on-loop (today) | Loop stalled for the full call on **both** engines: max gap 2,140.9 ms (pure) / 1,534.5 ms (Rust). |
| `to_thread`, pure pathological | Max gap **2,151.3 ms** — no improvement; one sre episode is a single GIL-holding C call. |
| `to_thread`, control (`time.sleep`) | Max gap 11.1 ms — the harness shows improvement when the GIL is released. |
| `to_thread`, Rust benign | Max gap **40.5 / 28.7 ms** (two runs) — the detach works; occupancy solved. |
| Many short pure calls in a thread | GIL hands over **between** calls: 171 consecutive ~18 ms matches → median gap 17.4 ms, max 21.3 ms. Thread offload bounds pure-engine stalls at the longest single call. |
| `wait_for(to_thread(...), 0.5)` on pathological | `TimeoutError` surfaced at **2.13 s**, not 0.5 s — the loop needs the GIL to fire its own timer; the orphaned thread burned to completion regardless. |
| Offload tax (trivial call, ~230 B body) | Direct 0.7 µs (Rust) / 2.0 µs (pure); via `to_thread` ~38–39 µs median, p99 ≤ 78 µs; pre-owned `ThreadPoolExecutor` same median, tighter p99 (≤48 µs). |
| Process pool | First task (spawn + imports) **258 ms**; warm round-trip **115 µs** median; `Process.kill()` stopped a pathological burn at **0.507 s** — the only hard stop measured; each kill breaks the pool (~255 ms to rebuild). |

A methodological note worth keeping: naive stall probes lie — a probe
that takes its baseline after `Thread.start()` can hide a 48 s stall
entirely; only per-iteration wakeup logging is trustworthy.

Verified CPython facts underneath: `_sre` contains no
`Py_BEGIN_ALLOW_THREADS`; since 3.11 it checks *signals* every 4,096
opcodes (main-thread Ctrl-C works; other threads get nothing);
threads cannot be killed; `asyncio.to_thread` runs on the loop's
default executor (lazily `min(32, cpus + 4)` workers, shared with
everything else on the loop); anyio's equivalent ambient resource is
a per-loop 40-token limiter, and its `to_thread.run_sync` defaults to
`abandon_on_cancel=False` (cancellation *waits* for the thread).

## 3. What the prior art does

- **Nobody uses process pools.** Every studied project either keeps
  CPU on the calling thread and bounds it cooperatively, offloads to
  threads as a thin sync/async adapter, or escapes the GIL through a
  native core.
- **SQLAlchemy** bridges with greenlets on the loop thread — it never
  offloads its own CPU work — and treats cancellation as
  **abandonment made safe**: `CancelledError` marks the connection
  invalid (the interrupted conversation is unknowable), a shielded
  graceful close falls back to a forced close, and the pool survives.
  Real threads appear only inside aiosqlite (thread-per-connection,
  invisible from above).
- **The MCP SDKs** (python-sdk, fastmcp) run possibly-blocking user
  code via `anyio.to_thread.run_sync` on the **ambient** pool — no
  owned executor, no sizing knobs — and make cancellation explicit at
  the protocol layer instead: "interrupt" (cancel the scope) vs
  "signal" (set a flag, let it finish); either way the result is
  dropped, and the running thread is never abandoned mid-run.
- **opendal** — the closest analogue to the vfs seam — owns a
  process-global tokio runtime inside the extension; its async path
  leaves the GIL entirely (futures poll on tokio workers, re-attach
  only to build results). Notably its *blocking* Python API holds the
  GIL for the whole call: the seam alone buys nothing — only the
  explicit GIL release does. vfs's binding is already on the right
  side of that line.
- **zoekt** bounds CPU cooperatively: a cheap `ctx.Done()` check
  **once per document**, one document of overshoot accepted,
  cancellation returns partial results with honest skip statistics;
  workers sized to GOMAXPROCS behind an admission semaphore, with a
  two-class scheduler (interactive bursts full-width; after 5 s a
  request demotes to a batch lane capped at quarter capacity).
- **codesearch** has no cancellation at all — because its matcher is
  a lazy DFA (linear time, no catastrophic backtracking), there is no
  pathological runtime to defend against. The engine choice *is* the
  timeout story. Rust's `regex` crate is the same family — the vfs
  Rust engine is already the linear-time answer.
- **Ownership etiquette**, as practiced: thin per-call adapters
  borrow the shared ambient pool and add no knobs; sustained engines
  own their concurrency and size it to cores. A grep engine is the
  second kind — flooding the loop's default executor starves
  neighbors that `asyncio` itself uses.

## 4. What this settles, and the residual it cannot

**The occupancy fork is thread-settleable, wholesale.** Offloading
the per-batch matcher call to a worker thread ends the measured
10-second-class loop stalls: completely on the Rust engine (GIL
detached; ~30–40 ms residual seam work), and down to the longest
single `re` call on the pure engine (GIL hand-over between calls).
The tax is ~38 µs per batch call — noise against real matching, and
bounded even for trivial calls. The natural shape is a decorating
wrapper at the storage call site around the existing `ContentMatcher`
protocol (never a per-engine fork of the protocol), a small owned
executor sized to cores rather than the shared default, and the
absolute deadline passed across the hop.

**The residual fork is not thread-settleable — by physics, not
design.** One pathological sre episode holds the GIL as a single C
call: a thread cannot bound it, a timer cannot fire under it, and an
abandoned thread burns to completion. The only hard stop is process
death (measured: kill at 0.507 s; ~255 ms respawn, ~115 µs warm
round-trip, broken pool per kill) — a posture no studied library
accepted, and the same worker-process posture question the
semantic-chunking entry already holds. The prior-art alternatives are
exactly vfs's existing positions: the linear-time engine (Rust, the
default wheel) as the codesearch-style answer, and honest disclosure
plus budget stacking on the pure fallback (landed by spec 112).

## 5. Recommendation (for the decision, when taken)

1. **Adopt thread offload of the verify calls** behind the storage
   seam when the concurrency story activates: a wrapper around
   `ContentMatcher` at the call site, one in-flight batch per
   verifier, absolute-deadline passing, cancellation-as-abandonment
   (await ends, worker finishes into the void, ≤32 MiB batch
   residency acknowledged), truncation contracts unchanged. This
   closes "grep verify occupies the event loop" for both engines'
   benign workloads and entirely for the Rust engine.
2. **Own a small executor** (≈ core count) rather than borrowing the
   loop's default; zoekt's two-lane scheduler is the recorded shape
   if latency-sensitive agents and bulk ETL ever contend on it.
3. **Do not chase the pure-engine pathological residual with
   threads** — record it as settled-by-engine-choice: the Rust engine
   is the linear-time answer; the pure fallback keeps its disclosed
   exponential residual. A process-kill mechanism is the only true
   bound and should be considered only together with the chunking
   pool question, as one library-posture decision, if a daemonized
   host posture ever makes worker ownership natural.
4. **Sequence:** nothing here is urgent — nothing shipped is wrong.
   The offload spec belongs at the front of the concurrency story,
   not before it.
