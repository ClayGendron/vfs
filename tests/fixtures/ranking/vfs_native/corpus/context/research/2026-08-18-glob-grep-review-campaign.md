# Glob/grep read-path review campaign — findings report

- **Date:** 2026-08-18 (campaign run 2026-08-17, machine-local evening)
- **Provenance:** synthesized output of a 34-agent review campaign over
  the commit range `0359c8d..da3cee3` — everything landed since the
  2026-08-13 campaign: specs 095–100 (flag algebra, entry-grain grams,
  epoch-consistent reads, literal quoting, one-owner refactor, planner
  caps), spec 103 (Rust verify core), spec 104 (path-segment index),
  the priced-nomination perf arc, spec 105 (overlay gate), spec 106
  (bytes content path); run `wf_2784b845-963`. Five review lenses
  (ownership, contract, scale, test, adversarial) on Fable, one
  independent Opus skeptic per finding at high effort, one synthesis
  agent. All four Docker engine legs were live for the whole run;
  findings cite executed repros. Repro scripts were written to the
  session scratchpad (ephemeral); every finding names its script.
  Funnel: 28 raw findings → 27 survived verification (one refuted) →
  3 merged as one defect (the CI-red tip) → **25 reported: 1
  critical, 4 major, 9 minor, 11 downgraded to design questions.
  None unverified; no lens failed.**
  Working-tree note: four scoped files were dirty at review time with
  the CI-gate repairs; all findings were judged against the committed
  state, and those repairs have since landed (`e4c72a5`, `771c019`,
  `bd0b14a`).
- **Feeds:** specs 107–111 (born 2026-08-18 from this memo, one per
  defect category): 107 overlay verdict at the recheck (the critical
  finding), 108 statement growth in the grep pushdown, 109 pins for
  unpinned laws, 110 seam bounds, 111 assembly and batch shapes.

## Decision pass (Clay, 2026-08-18)

1. **The critical finding's mitigation is the lock-free late verdict**
   (finding 1 → spec 107): the constraint that selected it is that no
   repair may hold locks or make a writer wait, even milliseconds.
   Isolation pins (SQL Server SNAPSHOT needs a database option;
   REPEATABLE READ takes shared locks), a writer-maintained overlay
   generation (meta-row hotspot), and EXISTS-into-fetch fusion
   (unsound under locking READ COMMITTED) were assessed and rejected
   against it; disabling the gate on unpinned engines was sound but
   strictly dominated.
2. **Remediations land by category, one spec per defect class**
   (107–111 above), so each lands as one reviewable change.
3. **The 11 design questions remain open** for a future decision
   pass; none require action to keep the tree correct.

---
## Critical

### 1. Overlay-emptiness gate silently loses rows edited mid-call on MSSQL and Oracle
`src/vfs/storage/backends/database/grep.py:253` — concurrency-wrong-results — adversarial_review — **CONFIRMED, critical**

**What is wrong.** On engines without the REPEATABLE READ op-isolation pin (MSSQL, Oracle, and the GENERIC floor — `dialects.py` pins only Postgres and MySQL), a rival content write that demotes an `encoded` row after the same-statement pointer+overlay read but before the candidate fetch makes grep return `success=True` with the row silently missing: the demoted row is excluded from the index side (`encoded=False`) and the scan tier is skipped on the now-stale overlay-empty verdict. The `StaleSnapshot` redrive at grep.py:276 cannot fire — it detects pointer movement (a publish), not a flag demotion.

**Why it matters.** Silent recall loss with no error signal, from routine concurrency (the declared agent read/edit/search workload), on the read path whose stated contract is recall. Spec 105 law 2 says "false empty must be impossible within the snapshot the call already trusts"; the gate is same-*statement*, which is same-snapshot only where an isolation pin exists. Mitigating only in that it is transient per-call.

**Evidence (executed, all five engines).** Seam-staged race (`gate_verify.py`): sqlite/Postgres/MySQL hold all 3 rows; MSSQL and Oracle return 2 of 3 with `success=True, errors=[]`. Control arm forcing `overlay_empty=False` restores all 3 rows on both engines — the gate is the sole cause. Reproduced **with no seams at all** (`gate_natural.py`: 200 files, 12 rounds of `reindex` + `asyncio.gather(grep, rival write)`): MSSQL lost a row in 7 of 12 rounds.

**Repro.** Scratchpad scripts `gate_verify.py` (seam-staged, deterministic), `gate_natural.py` (hook-free), `gate_control.py` (causation control), under `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/0e5b6050-047e-4aa4-9c2b-859dd3ac7aa4/scratchpad/`.

**Fix direction.** Make the false-empty direction impossible on unpinned engines: either restrict the gate to profiles carrying an op-isolation pin (Postgres/MySQL), widen the redrive trigger to detect overlay-state movement (re-check the EXISTS alongside the pointer re-read and redrive on empty→non-empty), or pin isolation for the gated statement pair on MSSQL/Oracle. Name the GENERIC floor's exposure explicitly wherever the fix lands.

---

## Major

### 2. Grep ext pushdown undercounts expanding IN binds; statement exceeds MSSQL's 2,100-parameter cap
`src/vfs/storage/backends/database/grep.py:677` — statement-growth — scale_review — **CONFIRMED, corrected critical→major**

**What is wrong.** `_predicate_binds` counts bind slots off the compiled bind registry, where an expanding `IN` — the `ext_membership` ride carrying up to `membership_budget` elements — counts as 2 regardless of width but expands to `len(wanted)` parameters at execution. `_entries_for_docs` sizes its id chunk as `membership_budget - _predicate_binds(pushdown)`, so on MSSQL the executed statement crosses the server's 2,100-parameter cap whenever the caller passes ≥32 ext values and the candidate set fills a chunk. `ExtMembership` exists precisely to pair predicate with true bind count; `_pushdown_terms` drops `ride.binds` and grep re-counts via compile — the exact drift that type was built to prevent.

**Why major, not critical.** Deterministic and loud (driver error, no wrong data), confined to MSSQL among profiled engines, but a hard failure of a supported production engine at modest scale (2,300-file corpus) with no workaround but shrinking the ext channel. CLAUDE.md names the ~2,100-bind cap as a floor to design against.

**Evidence.** Live MSSQL end-to-end through public `DatabaseStorage.grep`: `n_ext=31 → success, rows=2300`; `n_ext=32 → 42000 "The incoming request has too many parameters"`; `n_ext=35+ → 07002`, surfaced as `vfs.unavailable`. Oracle control at 40 ext members passes (its `in_list_budget=1000` keeps chunks small). Boundary sits exactly where the arithmetic predicts.

**Repro.** Self-contained script in the finding record (2,300 files, reindex, grep at n_ext 31 vs 32 against the MSSQL container).

**Fix direction.** Thread `ride.binds` through `_pushdown_terms` (carry `(predicate, binds)` pairs, or the `ExtMembership` object itself) so the chunk arithmetic charges the true count. Side observation (unverified): the same overflow classifies as retry-shaped `vfs.unavailable` at 35+ members — worth auditing the MSSQL error-classification table separately.

### 3. `_channel_facts` renders one unchunked OR over every channel arm — public grep fails at 499+ arms
`src/vfs/storage/backends/database/grep.py:674` — statement-growth — scale_review — **CONFIRMED, corrected critical→major**

**What is wrong.** The candidate-fetch pushdown compiles the whole admissions channel as a single `or_(*arms)` with no chunking, no cap, and no consultation of `expression_depth_budget` — the field `DialectProfile`'s own docstring says exists for exactly this hazard, and which the scan tier's fan (via `arm_budget` + `chunked`) already respects. `MAX_PATTERN_ARMS=64` caps *per pattern* by design; the channel takes an unbounded `globs` tuple and the router multiplies it by scope roots.

**Why it matters.** sqlite (the dev/test default) fails at 499 plain globs (`Expression tree is too large (maximum depth 1000)`); MSSQL fails between 500 and 1088 arms (parameter cap). Secondary degradations from the same root: `per_chunk` collapses to 1 when arm binds exceed the membership budget — measured on live Oracle, 400 arms turns one candidate-fetch statement into one **per candidate** (300 statements, 0.10 s → 1.52 s; 25,000 at full budget). Loud failure, no wrong rows — hence major. Aggravator: the failure classifies `vfs.unavailable` ("Retry shortly"), inviting agents to loop on a permanently failing call.

**Evidence.** Executed through `VirtualFileSystem.grep` (17 globs × 64 brace arms fails; a realistic 8 scope roots × 63 globs = 504 composed arms fails); binary-searched threshold at 499 on sqlite; four live engine legs (Postgres/MySQL/Oracle pass to 2,000 arms; MSSQL fails at 1,088); cause isolated by neutralizing only `_channel_facts`.

**Repro.** 12-line script in the finding record: sqlite, 5 files, `grep(pattern="hello", globs=tuple(f"*.e{i}" for i in range(499)))` → engine refusal.

**Fix direction.** Mirror `_entries_for_scan`: chunk `channel.arms` by `arm_budget(...)` and union per-chunk row sets — or drop the pushdown to `None` when the fan exceeds budget (lawful: it is narrowing-only; `_passes_gates` remains the authority). Reclassify over-cap statements as `invalid`, not `unavailable`. Related unverified lead: `pathterms.allow_list_ids` issues one self-join per arm in a Python loop — bounded per statement but not in statement count (504 sequential round trips for the same shape).

### 4. Mixed glob-channel pushdown soundness clause is unpinned — executed mutation loses recall silently
`src/vfs/storage/backends/database/grep.py:672` — test-gap-correctness — test_review — **CONFIRMED, major**

**What is wrong.** `_channel_facts`' one soundness law — an arm with no facts makes the disjunction vacuous, so `if not facts: return None` — has no test that fails when it breaks. Mutating `return None` to `continue` (emitting the partial OR) drops in-scope rows with `success=True`, `errors=[]`, and the **whole suite green** (2,516 passed under the mutant). An instrumented run shows the suite already makes 14 calls that compile the mixed shape where the mutant emits different SQL — exercised, never asserted on.

**Why it matters.** It is a soundness law on the recall path whose regression mode is the forbidden silent false negative; the file's other soundness clauses carry hand-verified mutant pins. The shipped code is correct today — this is a test gap, not a live defect.

**Evidence/repro.** `minimal_repro.py`: store `{/src/a.py, /docs/readme.md}`, `grep(pattern="needle", globs=("*.py","docs/**"))` — live returns both; mutant silently drops `/docs/readme.md`. Suite-under-mutation via pytest plugin: fully green.

**Fix direction.** Add the pin: a grep through a mixed fact-carrying/fact-free channel asserting the non-.py row under /docs is served, in both worlds (pre/post reindex) — in `TestScopedNomination` or, better, in `tests/support/storage_contract.py` with the memory backend as oracle. A brace-expanded single glob (`*.{txt,md}`-shaped) may be the cheaper spelling. Lead: `_channel_facts` has no direct unit test at all, including its dialect-conditioned LIKE-escape branch.

### 5. Pure-engine grep ignores the wall budget inside a single body: a small ReDoS pattern hangs the call indefinitely
`src/vfs/pattern_matching/grep.py:435` — unbounded-runtime — adversarial_review — **CONFIRMED, major**

**What is wrong.** `_PureMatcher` consults the deadline only between bodies, and Python `re`'s backtracking is unbounded within one `finditer`. On the pure engine (a documented first-class configuration: `VFS_PURE_PYTHON=1`, CI's fallback leg, extension-less wheels, protocol-mismatch fallback), `grep(pattern="(a+)+bcd")` against a 35-byte body was still running after 30 s under a declared 2.0 s budget — the call never returns, so there is no truncation record and no error. The Rust engine finishes in 4 ms (the regex crate is linear per body; deadline granularity is identical — the divergence is engine-specific). Blast radius exceeds one call: verify is a synchronous call inside the `grep_rows` coroutine with no `wait_for`/`to_thread` anywhere on the read path, so the hang blocks the entire event loop.

**Why it matters.** ADR 039's cataloged pure-engine residuals are semantic only (Turkic orbit, `\N{...}`); spec 097 declares "the bound is time, not shape" and the `ContentMatcher` docstring promises an incomplete-report second return that here can never happen. Major rather than critical only because shipped wheels carry the extension.

**Evidence/repro.** Script in the finding record — same call both legs: Rust `elapsed=0.004s success=True`; pure `HUNG after 30 s` (killed by alarm), growing ~2x per added `a`. Matcher-only variant confirms the seam.

**Fix direction.** Bound the pure engine's per-body cost: chunk the whole-text scan with deadline checks between slices, run verify under a timeout/executor, or gate patterns with catastrophic-backtracking shapes on the pure engine. Separately worth a look (unverified lead): even on Rust, a full `grep_wall_seconds` of synchronous matching blocks the event loop — relevant to the high-concurrency agent audience.

---

## Minor

### 6. Committed tip is CI-red: three files fail `ruff format --check`, and `_pointer_with_overlay`'s missing-meta-row branch is uncovered (100% gate fails)
`src/vfs/storage/backends/database/grep.py` (grep.py, pathterms.py, test_pathterms.py; committed line 359) — breach — **contract_review + test_review converging (three filings merged)** — format finding DOWNGRADED major→minor; coverage finding CONFIRMED minor; combined filing DOWNGRADED major→minor

**What is wrong.** Two independent gate failures at da3cee3, both reproduced with the CI-pinned tooling: (1) `ruff format --check` fails on grep.py (unformatted since 9033eaf), pathterms.py (since 1b36b4a), and test_pathterms.py (born unformatted in b10c65d) — whitespace-only, zero semantic surface; (2) the `row is None → (None, False)` branch of `_pointer_with_overlay` is the single uncovered line in all of `src/vfs` (99% vs the declared `fail_under=100`), with no committed test reaching it. Decisive evidence: GitHub Actions run 32054111337 (the push of da3cee3) went red at the Format check step on all four legs. A function-local `from dataclasses import replace` in the drift also breaches the imports rule.

**Why minor, not major.** No behavioral defect — the uncovered branch is correct defensive code, the format diffs are line rejoins. Both are already remediated post-scope (e4c72a5, 771c019; HEAD is green). The real process cost, and why this is not dismissed as cosmetic: because Format check precedes Tests, the range's only CI run died at 48 s — **the entire spec 104/105/106 arc (11 commits) reached main in one batch with zero CI test verification on record**, only local runs.

**Repro.** `git archive da3cee3 src tests pyproject.toml | tar -x -C $S && uv run ruff format --check $S/src $S/tests` → 3 files; `uv run pytest --cov --cov-fail-under=100 --deselect ...test_a_missing_meta_row_reads_as_unpublished_and_pending` → 99%, line 355/359.

**Fix direction.** Done on main. Process leads (unverified): run the test step regardless of lint/format outcome so a whitespace failure cannot swallow an arc's test verification; note the coverage gate runs only on the 3.13 leg and the pure-Python leg runs without `--cov`.

### 7. Dotfile-rescue derived-ext SQL predicate has two homes (reads.pattern_arm and grep._channel_facts)
`src/vfs/storage/backends/database/grep.py:670` — duplication — ownership_review — **DOWNGRADED major→minor**

The `(ext = X OR name = dot_suffix)` rendering is spelled at reads.py:316 and grep.py:670 (plus, deliberately, as the test battery's independent oracle). The verifier refuted the "silent false negative on drift" harm by executing the predicted drift into each copy: both mutants die loudly (4 dedicated pins across test_reads/test_grep/conformance — the grep-side pin even catches the reads-side drift). The meaning is owned by `DerivedExt`; only the two-comparison SQL spelling repeats, and the secondary name-fact-LIKE claim was factually wrong (different inputs, columns, roles). What stands: `_channel_facts` is feature-envious, reaching through `ChannelTerms→ArmTerms` fields to build SQL the compiled-terms layer could hand back. **Fix direction:** cleanup, not a fix — one predicate builder beside the shared pattern-arm machinery (or beside `ArmTerms`), consumed by both sites; behavior-identical.

### 8. Stored-path hydration law (re-brand, don't re-gate) declared in paths.py but obeyed only by grep
`src/vfs/storage/backends/database/reads.py:450` — divergence — ownership_review — **CONFIRMED, minor**

`Path._brand`'s docstring (edited in-range) and ADR 041 §3 declare backend row hydration a branded site; grep's assembly implements it (`Path._brand`), but `reads._observe` — serving read/stat/ls/tree/glob — still runs the full gate per row, and glob's candidate loop mints a second gated `Path` per candidate (reads.py:248) despite `passes_row_filters` existing for exactly that. Measured: 38.9% of a 20k-row glob and 29.4% of a 20k-child ls (`Path(str)` 8.77 µs vs `_brand` 0.15 µs per row); results identical on every arm. No correctness impact (stored paths canonical by invariant). **Fix direction:** `_observe` adopts `Path._brand`; glob's gate adopts `passes_row_filters` with `name`/`ext` ridden along (constraint: `effective_columns` can exclude them under a narrow `columns=`). Repro script in the finding record. Unverified lead: `DatabaseStorage.ls(path="/flat")` with a plain `str` dies with a raw `AttributeError` — an unstated load-bearing precondition on the storage seam.

### 9. ADR 042/spec 105 "allow_scan callers never consult the gate" is false for indexable patterns
`context/decisions/042-overlay-probe-composite-index-and-emptiness-gate.md:39` — decay — contract_review — **CONFIRMED, minor**

The gate keys off `scan_all = invert_match or plan.is_any()`, not the flag: an `allow_scan=True` call with an indexable pattern is gated and skips the scan on an empty verdict (reproduced with a scan spy; results identical by construction — the code is right, the prose overstates). The committed pin covers only the gramless case. **Fix direction:** reword ADR 042 and spec 105 §2 to name scan-shaped calls (gramless-under-allow_scan, invert_match), and add the indexable-`allow_scan` row to `TestOverlayGate` so a future refactor that really keys off the flag is caught.

### 10. delete_rows issues per-target single-move segment maintenance despite move_postings' batch API
`src/vfs/storage/backends/database/topology.py:243` — query-in-loop — scale_review — **CONFIRMED, minor**

Each trashed target calls `move_postings` with a one-element list; a trash reparent is never the rename fast path, so each call is ~depth extra statements. Measured: 5.01 segments-table statements per target (62% of the verb's statements); on live Postgres at the contract's 10,000-target scale, 29 s of a 72 s delete — 40% of the verb — spent in single-element calls. Batching the loop's moves into one flush is 30–55x faster on the same deltas (3.5x even with a grouping-hostile vocabulary), and the verifier checked the deferral hazards (no read-your-writes on segments inside the loop, no id collisions, order-independent keying) — behavior-identical. ADR 040 §2 and spec 104 §2 describe the batched shape. **Fix direction:** accumulate moves across the loop, flush once per call. Unverified lead: the shared move/restore executor has the same single-element shape per pair (topology.py:1116).

### 11. allow_list_ids: uncapped per-arm query loop and Python-object materialization of the scope's id union
`src/vfs/storage/backends/database/pathterms.py:169` — memory-growth — scale_review — **CONFIRMED, minor**

The allow-list union is corpus-scaled, not batch-scaled: measured 103 MB traced peak / +360 MB RSS and 5.5 s for a 1M-entry scope (~50–100 B/id in `set[int]` + sorted list, vs 8 B/id in the numpy pipeline it feeds; `CANDIDATE_BUDGET` truncates only *after* the wide structure exists), plus one round trip per deduped arm (32 statements for 30 globs). No deadline reaches it — `allow_list_ids` is called without the wall clock every other stage consults. No correctness or engine-cap issue; ~10 MB/sub-second at the benchmarked 94k scale. **Fix direction:** under CLAUDE.md's acknowledged-suboptimality law, the module docstring must name the corpus-width profile and the future direction (pushing the allow-list join into the candidate fetch as a SQL predicate); consider passing the deadline.

### 12. Allow-list multi-term intersection is unpinned: rarest-term-only mutation passes the whole suite
`src/vfs/storage/backends/database/pathterms.py:248` — surviving-mutation — test_review — **CONFIRMED, minor**

Deleting the self-join chain (join only the rarest term) passes all 2,516 tests — the corpus has no `app`-without-`src` decoy, the superset battery asserts covering in one direction only, and no test arm exceeds 4 segment terms so `_INTERSECT_TERMS` never slices. The shape the mutation reverts to is a measured-and-rejected alternative recorded in ADR 041, with no test standing behind the decision. Amplification if it regressed: a wider allow-list can push scoped rows past `CANDIDATE_BUDGET` and drop in-scope results. **Fix direction (verified to kill the mutant):** add a `/app/solo.txt` decoy to the pathterms corpus and assert it is absent from a `src/app/**` allow-list; add a 5+-literal-directory glob so the cap actually slices. Lead: the rarest-first *ordering* is equally unpinned.

### 13. The priced ladder-defer decision has no behavioral pin — pricing-constant drift is invisible
`src/vfs/storage/backends/database/grep.py:464` — surviving-mutation — test_review — **CONFIRMED, minor**

Both branches of `_ladder_defers` are lawful supersets producing identical results, so nothing distinguishes them: all 10 suite calls land on the defer side, and branch-preserving magnitude errors in any of the three pricing constants (75→7.5, 500→5000, 0.055→0.55) pass the suite **and** the 100%-coverage gate — the likely real-world mistake when the constants are re-derived per ADR 041, and a silent whole-scope-verify regression on every scoped call. Performance-only blast radius. **Fix direction:** pin the decision itself (spy on `_posting_blobs`/branch taken at a constructed crossover shape), since result assertions cannot see it; no CI bench gate exists. Lead: the `laddered ∩ allow` branch (grep.py:227) is reachable in the suite only via the never-indexed early return — no test ever intersects real laddered postings with an allow-list.

### 14. Context and max_count parameters cross the pyo3 seam unvalidated past the ingress gate's missing maxima
`src/vfs/storage/backends/database/grep.py:313` — wrong-error-channel — adversarial_review — **DOWNGRADED major→minor**

The filed mechanism ("the router adds no validation") is wrong: `_gate_params` refuses negatives and `max_count=0` with typed `vfs.invalid` — the raw-OverflowError-on-negatives and pure-engine malformed spans reproduce only by bypassing the router, which the storage protocol declares out of contract. What survives: the gate declares minima but **no maxima**, so `before_context=2**32` (or `max_count=2**64`) passes the router and raises a raw `OverflowError` out of the public API on the Rust build, while the pure engine returns normally — violating "the router never raises" and diverging by engine on router-admitted input. Absurd magnitudes, no corruption. **Fix direction:** add maxima to the int ParamSpecs (or clamp at the seam). Lead: no int channel in the ingress table carries a maximum — one sweep worth doing.

---

## Downgraded to questions / design notes

All eleven were verified to state no reachable defect; each was refuted on reproduction, intent, or materiality and survives as its corrected question. None require action to keep the tree correct.

15. **Brace globs at the storage grep seam are half-expanded** (`pathterms.py:125`, adversarial_review, filed major). The tier divergence reproduces at `DatabaseStorage.grep` (a literal-brace directory serves pre-reindex, drops post-reindex) — but ADR 037 declares braces expand before anything downstream, the router provably makes the divergence unreachable (`_expanded_channel` + `escape_glob`, verified), and the claimed conformance pin doesn't exist. **Question:** `compile_terms` claims `compile_glob`'s input contract while reading braces the opposite way — either drop its `expand_pattern` call (superset law then holds unconditionally) or refuse brace-carrying globs at the seam, so the invariant is self-enforcing rather than inherited.
16. **chunk_dirty materializes every dirty body plus chunk rows in memory** (`indexing.py:209`, scale_review, filed major). Reproduces at ~2.7x corpus bytes and is now the dominant reindex memory term — but the shape is byte-identical to the already-reviewed base, sits *below* the 3.6–4.3x envelope Clay already adjudicated and accepted (spec 095 §8), and the range improved the whole-run peak. **Question:** should the acknowledgment that moved off `build_epoch`'s docstring now land on `chunk_dirty`, and should phase A adopt phase B's streaming shape (a real design slice — version-guarded flips complicate a mechanical port)? Already adjacent to the open `chunk_dirty` fork in open-questions.md.
17. **Posting-blob fetch runs before any deadline consult; exempt bytes "uncapped"** (`grep.py:395`, scale_review). The fetch-before-deadline part reproduces, but the load-bearing premise — unbounded OR width — is false: the planner hard-caps branches at `MAX_VARIANT_WIDTH=64`, bounding the exempt set at ~6 MB at benchmark scale; un-interruptible statements are the pipeline's consistent design. **Question:** true up grep.py's docstring and ADR 033's §5 annotation ("deliberately uncapped", "consulted between branches") to the 64-branch cap and the intersection loop.
18. **Literal-head `"*?["` law spelled in two storage modules** (`pathterms.py:55` / `reads.py:493`, ownership_review). Copies agree exactly and both are mutant-pinned (verified: dropping `[` from either fails loudly). **Question:** export `literal_head`/`is_literal_component` from `pattern_matching/glob.py` per ADR 032's one-owner doctrine — placement hygiene only. Lead: `_name_fact("")` raises on an empty component, guarded only upstream.
19. **Glob-channel defect-gate loop + refusal-sentence format duplicated** (grep.py:172 / reads.py:228 — and a third home at base.py:1463 the filing missed). Spec 099 §6 deliberately unified labels only and left message shapes; the backend loops are unreachable through the router (verified: 22 gate calls, 0 defects). **Question:** should a future pass give the refusal sentence one owner, or is "no contract owns the wording" the settled posture?
20. **Candidate ride-along column law duplicated in both fetch arms** (grep.py:521/569). Verbatim, one law — but divergence is loud (mutants fail immediately on both tiers) and cannot land under the coverage gate. **Question:** hoist `_RIDE_ALONG` + a helper; also document the law in `_entries_for_scan`'s docstring, which currently omits it. Lead: `ARM_FIXED_BINDS + len(CONTENT_KINDS)` arithmetic is a second copy of the same fact.
21. **Two `DocIds` aliases with different runtime shapes** (pathterms.py:61 list vs grep.py:124 ndarray). Never imported across the seam; `ty` machine-enforces the distinction (verified); sortedness declared at the owner. **Question:** distinct names (`AllowIds`/`DocIdArray`) or one shared alias — naming preference for Clay.
22. **Content-kind SQL gate: three `sorted(CONTENT_KINDS)` sites, one unsorted outlier** (indexing.py:206). The claimed harm is refuted on all four real engines: `in_()` renders as one expanding bind, so statement text and cache key are order-free; no test asserts on parameters. **Question:** give the predicate a named home beside `liveness_filters`, and drop the decorative `sorted()` everywhere rather than adding it to the fourth site.
23. **One grep Result can carry two identical candidate-budget truncation records** (grep.py:266). Real at the storage seam, but the envelope contract declares value-identity dedup and the router's merge collapses it before any facade caller sees it (verified). **Question:** guard the line-266 append the way the wall-time appends are guarded, for direct-storage-caller consistency. Lead: a wall-expired call never reports that the overlay went unconsulted.
24. **`_native.pyi` omits `ContentMatcher`** (\_native.pyi:11). The stub's declared scope ("what the seam programs against") is satisfied; `ty` passes; the consumer is typed `Any` by declared design, so widening the stub checks nothing. **Question:** mirror the module or keep the scoped stub (rewording its title) — and note the real type-safety lever is narrowing `extension()`'s return to a Protocol. Lead: nothing static cross-checks the `ContentMatcher` Protocol against the pyo3 signatures.
25. **`surrogatepass` decodes tolerate surrogate-encoded invalid UTF-8** (pattern_matching/grep.py:294). The proposed strict fix is refuted by execution: `surrogatepass` is load-bearing — it is what makes a lone-surrogate `str` (legal in Python, matchable by the pure engine) round-trip identically through the Rust arm, i.e. the mirror-conversion law of ADR 043; genuine corruption (`0xff`) still fails loudly per spec 106 law 1. **Question:** name the handler and its rationale in the mirror-conversion law so the next reader doesn't "fix" it to strict. Lead: an out-of-band corrupt body escapes grep as a raw `UnicodeDecodeError` rather than a classified Result.

---

## Coverage

All five lenses completed and reported ledgers; no lens failed, so there is no unreviewed-by-lens-failure surface. Findings above were verified by execution except where a verifier noted quoted-text-only verification (two contract items in that lens's ledger).

**Checked and found clean:**

- **Ownership** (judged at committed tip; dirty files snapshotted): segments.py owns all segment-delta computation with verbs only calling in-transaction; the lease split (SQL in indexing, orchestration in backend) matches remits; `passes_filters`/`passes_row_filters`, `normalize_ext_channel`, `escape_glob`, dialect-conditioned `escape_like`, and the pattern-arm machinery each single-homed; the language gate runs once before either engine; Rust/pure dual implementation is the declared pendulum model with byte-parity pinned; new profile facts (`tuple_in`, `like_bracket_class`, `content_bytes`) declared once with no hardcoded twins; `native.py` is the single engine-decision point. Noted-not-filed: `_pointer_with_overlay`'s deliberate pointer-select re-spell; `_predicate_binds` as a second bind-counting mechanism (which became finding 2's mechanism via scale_review).
- **Tests**: flag algebra and epoch lifecycle, reindex lease arms, epoch-reread ladder (with real-engine race rows), every grep error classification, all budget truncations, the overlay-gate spy battery, the segment-mirror battery across every verb, Rust/pure parity including refusal-message identity, planner cap mutants, flip-arm statement shapes, statement-growth laws under tightened budgets — all pinned with distinguishing rows.
- **Scale**: dialect budget helpers; segment posting writes (chunked, grouped, savepoint-safe); PK width vs key-byte floors; lease atomicity and TTL; epoch mint/publish/reclaim; `_flip_flags`' three bounded arms; posting meta/blob IN-chunking; the scan-tier fan's correct per-arm bind accounting (the drift is grep's pushdown only — findings 2 and 3); scan-merge pruning; content batching under `CONTENT_BYTE_BUDGET`; the bytes BLOB cast gated on sqlite's fact; the same-snapshot EXISTS argument (on pinned engines); collect/repair drift guards; trash exclusion from both tiers.
- **Contracts**: ADR 040/041/042/043 and specs 095–100/103–106 walked clause-by-clause against code with quotes verified — allow-list laws, segment maintenance, schema format 5, the pricing formula matching ADR 041 exactly, `content_bytes` never-transcode doctrine, protocol 2 pinned both sides, the sre-gate refusal set, per-body deadline honoring in verify.rs, spec 095–097's lifecycle laws, spec 098/099 placements. A four-engine live smoke probe (write → overlay grep → reindex → gated grep → scoped grep) passed on Postgres/MySQL/MSSQL/Oracle.
- **Adversarial**: 400-case engine-parity fuzz (zero divergences beyond the ReDoS case), oracle-differential over 25 pattern shapes × both tiers (clean), scope-superset fuzz (one hit — the brace question), 23 hostile-input probes, lifecycle flag-algebra fuzz vs a dict oracle (clean), 1,500-entry Oracle scale probe with >1,000-id allow-lists and 1,101-member ext channels (clean), concurrency hammers on MSSQL (found finding 1) and Postgres (clean). Full suite green at 2,516/850.

**Not reached by any lens (unreviewed surface, not clean):**

- `crates/vfs-core` internals block-by-block — `grams.rs`, `postings.rs`, `python.rs`, and the verify.rs codec beyond its contract surface and the Python-side parity batteries (cargo tests and byte-parity pins stand in; no line-level review).
- `models/code_grams.py` planner internals beyond module head, cap sites, and cap-mutant spot checks.
- `results/render.py`, `engine.py`, `descent.py` beyond its shared-helper surface, `storage/protocol.py` beyond the diff.
- MySQL-specific runs of the adversarial fuzzes (its REPEATABLE READ pin defuses finding 1's mechanism by inference, not execution); the pure-Python leg of the storage-level fuzzes; 10k+ single batches on real engines (1,500 proved the chunking; suite pins carry 10k); an end-to-end ≥2,061-candidate grep on MSSQL (the statement-seam repro stands in).
- Per-engine cascade legs for the segments table and some bytes-cast audit legs — the specs themselves record these as awaiting a real-server run.
- Benchmark/ladder numeric claims in commit messages and dated studies (taken as declared measurements, not re-run); the differential batteries' case inventories; docs pages and research-memo content beyond spot checks; CI workflow/publish changes beyond the format-gate investigation; reindex-lease TTL/crash abuse; posting-blob corruption injection; MSSQL forced-parameterization under load.
- The two post-scope repair commits (e4c72a5, 771c019) are outside this range and unreviewed by this campaign.

**Notable unverified leads carried out of verification** (flagged as unverified, for triage): the GENERIC floor's exposure to finding 1's mechanism; the segment-postings cross-snapshot read at grep.py:213 (likely benign); MSSQL error-classification of permanent statement defects as `vfs.unavailable` (two findings independently observed it); the event-loop-blocking synchronous verify stage on the Rust engine; `allow_list_ids`' statement-count growth and deadline blindness (partially absorbed into findings 3 and 11); missing maxima across all ingress int channels; the batch-shape of move/restore's per-pair `move_postings`; `chunk_dirty`'s single whole-payload chunk insert on networked engines.