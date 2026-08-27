# Glob/grep/indexing review campaign — findings report and decision pass

- **Date:** 2026-08-13
- **Provenance:** synthesized output of a 73-agent review campaign over
  the commit range `f1ab5b3^..0359c8d` (specs 092/093/094, ADRs 033–035,
  and follow-up refactors; run `wf_c780e724-818`): five review lenses
  (ownership, contract, scale, test, adversarial) on Fable, an Opus
  skeptic panel per finding (three for critical/major, one for
  minor/question), one synthesis agent. All four Docker engine legs were
  live for the whole run; findings cite executed repros. Repro scripts
  were written to the session scratchpad (ephemeral); every finding
  names its script. Funnel: 35 raw findings → 34 survived verification
  (one refuted) → 4 merged as cross-lens duplicates → 30 reported.
- **Feeds:** specs 095–099 (born 2026-08-13 from this memo); the 094
  mining pass (STATUS true-up — decision 7 below).

---

## Decision pass (Clay, 2026-08-13)

The review's eight downgraded design questions were posed with
prior-art-grounded recommendations; Clay accepted all eight. These
resolutions govern specs 095 and 099; the mining pass may promote any
of them to a decision record if they prove load-bearing.

1. **`passes_filters` moves to `pattern_matching/glob.py`.** The
   path-language module owns path gates; grep imports one-way —
   ripgrep's `globset`/`ignore` ↔ `searcher` split is the precedent.
2. **The two inline admission-law re-spellings consolidate** onto the
   named gate where the signature fits; the irreducible per-row keep
   closure stays, with its authority named in a comment.
3. **The ext-membership rideability condition and its bind count get
   one paired helper** — the same centralize-the-budget-fact move as
   `membership_budget`/`chunked()`.
4. **`meta_scoped` stays in the backend and imports
   `paths._under_meta_root`** — closes the byte-identical duplication;
   hoisting for a second backend that doesn't exist is speculative
   generality.
5. **Index-format identity becomes a hand-bumped
   `INDEX_FORMAT_VERSION`** named as the one knob every fold, chunk
   grain, or extraction change must bump — zoekt
   (`IndexFormatVersion`/`IndexFeatureVersion`) and codesearch
   (`"csearch index 2\n"` magic) both hand-declare; the derived
   fingerprint is dropped as verified-insufficient.
6. **Refusal labels unify through one channel→label map** at the
   minting sites.
7. **STATUS.md trues up with 094's mining pass** (which also archives
   094) — no standalone ledger commit; the repo's own convention is
   that STATUS true-ups ride mining/landing docs commits.
8. **The posting-insert row cap is deleted.** SQLAlchemy's
   insertmanyvalues owns per-dialect row chunking (verified uncapped on
   MSSQL and Oracle); the byte-budget half stays; one test pins the
   insertmanyvalues behavior.

---

# Code review report — glob/grep/indexing arc, `f1ab5b3^..0359c8d`

**Scope:** 15 commits landing spec 092 (pattern-only glob seam), spec 093 (postings codec, reindex, indexed grep, capability flip), ADR 034 (chaining filters rows in hand), spec 094 (glob field parity), ADR 035 (Python floor), plus refactors. Five lenses ran (ownership, contract, scale, test, adversarial); every finding below passed an adversarial verification pass with executed reproductions — **no finding in this report is unverified**. "Leads" inside findings are unverified side-observations and are flagged as such. Working-tree drift on `pyproject.toml`, `uv.lock`, `context/open-questions.md` was handled by judging the committed state at `0359c8d`.

**Dedup note:** 34 verified findings arrived; 4 were duplicate lenses on the same defect and are merged below (the MSSQL reindex break was found independently by the test and scale lenses and rediscovered twice more as leads; the metachar-root defect by the ownership and contract lenses; the 3.12-floor doc drift by ownership, contract, and test). Arrival ranking (most-severe first) is preserved.

**Theme:** all three criticals live in the flag-partitioned index lifecycle — the `chunked`/`encoded` flag algebra and the per-chunk gram grain each open a path to the exact failure ADR 033 declares forbidden everywhere: a silent false negative from a search verb, with `success=True` and empty `errors`. The enabler for two of them is a structural coverage gap: no test anywhere runs `reindex()` against a real engine.

---

## Critical

### 1. Restore after a rebuild leaves grep silently blind to live content
`src/vfs/storage/backends/database/indexing.py:146` — breach (contract_review, CONFIRMED 3/3)

**What:** `build_epoch` excludes deleted entries from the fresh posting set (`.where(entry.c.chunked, entry.c.deleted_at.is_(None))`), but publish never demotes their `encoded` flag and restore preserves flags. The sequence delete → reindex → restore lands a live row with `encoded=True` and zero grams in the current epoch: the index side cannot nominate it, the scan side (`WHERE NOT encoded`) excludes it, and `reindex()` no-ops because `_work_pending` requires `chunked & ~encoded`.

**Why it matters:** grep returns no match for content that `read` serves intact — `success=True`, `errors=[]`, `allow_scan=True` does not rescue it (verified). The blindness is unbounded on an idle namespace (repaired only by an unrelated dirty write) and permanent for trash-scoped grep after a rebuild. This is the failure ADR 033 D1 names as forbidden everywhere; grep.py's docstring promises "index staleness can never lose a match".

**Evidence:** reproduced three ways — public `VirtualFileSystem` facade on sqlite, direct backend with flag dumps, and live Postgres (engine-independent; the defect is in the flag algebra). ~20-line facade repro in the finding record; longer variants at scratchpad `v1_restore.py`, `v1_pg.py`, `v1_trash.py`, `v1_facade.py`.

**Fix direction:** reindex must demote `encoded` on entries leaving epoch coverage (or include deleted entries' chunks in the build, which also restores trash-scoped grep parity).

### 2. Reindex is broken on MSSQL — and no test on any real engine can see it
`src/vfs/storage/backends/database/indexing.py:247` — parity-gap + engine-floor (test_review CONFIRMED 3/3 held critical; scale_review CONFIRMED 3/3 corrected major; independently rediscovered as leads by two other verifications — four converging observations total)

**What (two halves, one defect surface):**
- *The break:* `_work_pending` builds `select(exists().where(...))`, which compiles to a bare `SELECT EXISTS (...)` — invalid T-SQL. The branch is only reached once an epoch exists, so the **first** reindex passes and **every subsequent reindex fails permanently** on SQL Server (`42000: Incorrect syntax near the keyword 'EXISTS'`), misclassified as `unavailable`/retryable. The index freezes at epoch 1; every file written afterward is served scan-side forever — at declared 10k+ scale, exactly the cliff the index exists to prevent.
- *The gap that let it land:* no test in the suite ever calls `reindex()` on a non-sqlite engine. The conformance battery the four Docker legs run never mentions reindex; all reindex tests are sqlite-only. The commit-claimed "four Docker engine legs green with grep live" is vacuous for the entire index tier — on every server leg the epoch pointer is `None` and all grep conformance rows run scan-side.

**Mitigating fact (scale lens):** grep answers stay *correct* on MSSQL after the failure — the `NOT encoded` overlay still scans everything — so this is a hard permanent verb failure plus index freeze, not wrong answers. The test lens held critical (100% reproducible, unconditional, on a declared first-class engine, with spec/commit parity claims no test can check); the scale lens corrected to major on the correctness point. Reported at its arrival rank: **critical**.

**Evidence:** minimal repro (write → reindex → write → reindex against the live MSSQL container) at scratchpad `v1_minimal_repro.py` / `reindex_twice.py`; dialect-only compile check needs no server. All three other engines pass the same script. Oracle 23ai accepts the statement; older Oracle is untested (unverified lead).

**Fix direction:** reshape the probe (e.g. `select(literal(1)).where(...).limit(1)`, or the correlated `.exists()` inside a WHERE as topology.py:615 already does), fix the error classification (a permanent syntax error should not be retryable-`unavailable`), and add an engine-marked reindex→indexed-grep conformance row so the four legs actually exercise the tier.

### 3. Indexed grep silently loses matches straddling a chunk boundary
`src/vfs/storage/backends/database/indexing.py:151-154` — correctness (adversarial_review, CONFIRMED 3/3)

**What:** chunks split with no overlap; grams are extracted per chunk and posting lists intersect per chunk id. A match straddling a 2048-char cut whose straddling trigram(s) appear in **no single chunk of the file** is never nominated; the entry is `encoded` so the overlay skips it; `allow_scan=True` only bypasses the refusal gate, not `scan_all`. Silent — `success=True`, `errors=[]`.

**Refinement over the raw claim (verified):** verification fetches the full entry body, so an entry recovers whenever every required trigram recurs elsewhere in the same chunk — the loss is narrower than "always", but the class is real and routine for intra-line cuts: lines longer than the 2048 budget (minified JS/CSS, single-line JSON, long log lines, CSV rows, base64) — precisely the ETL corpus CLAUDE.md names first-class.

**Evidence:** minimal repro (`"a"*2045 + "NEEDLE" + ...` — grep finds it before reindex, loses it after; control survives) at scratchpad `v1_straddle.py`; realistic 4 KB log line and minified JSON reproduced on sqlite **and live Postgres** (`v1_realistic.py --pg`). No test covers a boundary case. Contradicts ADR 033:41, code_grams.py's "must never introduce false negatives", grep.py's docstring.

**Fix direction:** GRAM_SIZE−1 overlap on chunk emission at the indexer, or extract grams per entry rather than per chunk (the posting doc-id grain of ADR 033 §4 is what couples nomination to the split). Unverified adjacent lead: `split_code` drops whitespace-only spans entirely — a second coverage gap worth checking with the same fix.

---

## Major

### 4. Scope-root path text is reinterpreted as glob syntax — no layer quotes it
`src/vfs/pattern_matching/glob.py:200-215`, `src/vfs/base.py:1977, 1874` — breach/divergence (ownership_review + contract_review, both CONFIRMED 3/3 — converging lenses, merged)

**What:** `composed_pattern` splices `str(root)` into pattern text (`base + "/**/" + pattern`), grep's find-operand rule adds the raw root path as a pattern member, and the keep closure composes `effective_pattern(row.path, arm)` — all with no glob-escaping. Paths legally contain `[ ] { } * ?` (paths.py forbids only null/control/surrogate/format chars). Consequences, all executed on memory backend **and live Postgres**:
- `glob("*.csv", paths=("/data/[x]",))` serves the **sibling** `/data/x` subtree and silently drops everything under the real root; grep leaks out-of-scope content the same way.
- A root containing `{` refuses the entire call as `invalid: unclosed '{'` — an error about a pattern the caller never wrote, against a directory they addressed by path.
- ADR 030's own worked example (`data [prod]`) returns silent empty success; the probe channel serves the root literally while the dispatch channel reinterprets it — two channels disagree about the same root.
- Real-world reach: Next.js `[slug]` route directories — `glob`/`grep` scoped there return silently empty.

**This is a regression introduced by the set:** at the base commit roots crossed the seam as literal `Path`s and behaved correctly (verified against the extracted base tree); f1ab5b3/d890bdf made the unquoted splice the only channel. ADR 030 rationale 3 ("roots are literal and immune to glob metacharacters") was *reaffirmed inside this set* (79dd27e annotation) — the set documents the correct behavior and implements the opposite. No test uses a glob metachar in a scope root (the LIKE-metachar battery covers `%_\` only).

**Fix direction:** glob-escape root literal text at every composition point (composed_pattern, effective_pattern's base, the root-literal member, composed exclusions) — class notation (`[[]`) escapes every metachar and is expressible in the shipped language (verified). Held at major: silent wrong/cross-scope results, but `paths=` is scoping, not the permission boundary. Unverified leads: same splice feeds skip-suppression composition across mounts, and the exclusion channels.

### 5. PRE-EXISTING (not introduced by this set): `escape_like` leaves MSSQL's `[` bracket class unescaped — silent empty subtree, and delete/move orphaning
`src/vfs/storage/backends/database/descent.py:172` — (ownership_review, CONFIRMED; filed minor per scope rule, verifier raised impact to **major** as a standing bug)

**What:** `escape_like` escapes `\ % _` only; T-SQL LIKE also treats `[...]` as a class. On MSSQL, `tree('/data[1]')` returns zero rows with `success=True` (all four other engines correct); worse — verified — `delete(cascade=True)` on a bracketed directory trashes the directory row and **leaves live descendants orphaned** under a parent that no longer exists; `move` composes the same filter. The set's new arm machinery is *not* exposed (`_glob_like` returns None on `[`; verified correct on MSSQL).

**Fix caution (verified on all engines):** unconditionally escaping `[` trades the silent MSSQL miss for a hard Oracle error (ORA-01424). The fix must be dialect-conditioned (MSSQL-family only — a legitimate `DialectProfile` fact per CLAUDE.md's rule), plus a bracketed-path conformance row per engine: today no test anywhere uses `[` in a path.

### 6. Rival reclaim between build and publish publishes an empty epoch — all indexed matches silently lost
`src/vfs/storage/backends/database/indexing.py:221` — concurrency (scale_review, CONFIRMED 3/3; corrected critical→major)

**What:** `reclaim_epochs` deletes `epoch != current` using R1's own stale in-memory epoch, in a separate transaction after publish. A rival that publishes in that window has its (already published) epoch's posting rows destroyed; the pointer names an epoch with zero postings; covered entries are `encoded=True` so the scan side hides them too. Reproduced on real Postgres through the public `reindex()` verb: `pointer=3, posting rows=0`, grep for previously-hit content returns `[]` with `success=True`. Total and silent while it lasts; corrected to major because it needs two concurrent reindexers plus a narrow window, corrupts no stored content, and self-heals on the next reindex (verified). Nothing serializes reindexers and no doc tells operators to run only one.

**Fix direction:** reclaim `epoch < current`, or re-read the live pointer inside the reclaim transaction — either leaves the rival's epoch intact (the repro discriminates both). Unverified leads: same-epoch build collisions race the posting PK (loud), and a CAS-losing publish leaves its built epoch's rows unreclaimed indefinitely.

### 7. Grep vs concurrent reindex silently loses matches on engines without an isolation pin (MSSQL, Oracle, GENERIC)
`src/vfs/storage/backends/database/grep.py:230` — concurrency (scale_review, CONFIRMED 3/3)

**What:** Postgres/MySQL profiles pin REPEATABLE READ; MSSQL/Oracle/GENERIC run the grep ladder at statement-level READ COMMITTED. The epoch pointer read and the posting/entry reads are separate statements: a rival publish+reclaim in between empties the index side for the pinned epoch while the newly-encoded rows are excluded from the scan side. Reproduced live: MSSQL and Oracle return `rows=0, success=True, errors=[]` where the identical pre-race call returned the match, and a follow-up grep proves the data never left; Postgres/MySQL/SQLite are protected. Contradicts ADR 033 §6 ("old or new, never a mix") and backend.py's one-snapshot claim; no document declares those engines deliberately unpinned. Transient and non-corrupting → major.

**Fix direction:** pin op isolation on those profiles, or make the ladder epoch-consistent (re-read the pointer at the end and retry on movement).

### 8. Grep fetches up to 10,000 full bodies into one dict — no content-byte budget
`src/vfs/storage/backends/database/grep.py:187` — memory-growth (scale_review, CONFIRMED 3/3)

**What:** `_content_for_entries` materializes the entire gated candidate set's full bodies before the verify loop. `POSTING_BYTE_BUDGET` bounds posting blobs only; nothing bounds content bytes. Aggravators, all verified: files over `MAX_INDEXABLE_BYTES` (2 MB) never encode, so a large-file corpus takes the full-fetch path on every scan-tier grep; the scan tier is the *default* for any never-reindexed corpus (first grep after ETL ingest); the wall-time deadline is checked before and after — never around — the fetch, so an already-expired call still pulls all 10k bodies; `output_mode="files"/"count"` hold every body they then discard. Measured: 60×4.19 MB files → 251.7 MB in one dict, peak RSS 77→348 MB for a 1-row result; 12k small files → exactly 10,000 bodies, 307 MB; identical on live Postgres. Ceiling is 10k × unbounded body size under the repo's declared 10k+/high-concurrency posture.

**Fix direction:** byte-bound and/or stream the content fetch (chunked fetch-verify-release), check the deadline before fetching, and skip body retention in files/count modes.

### 9. Overlay scan side is a whole-table pass on every grep call — `NOT encoded` has no serving index
`src/vfs/storage/backends/database/grep.py:380`, `src/vfs/models/rows.py:358` — index-fit (scale_review, CONFIRMED 3/3)

**What:** the permanent overlay union filters `kind IN (...) AND NOT encoded` with no index on `encoded`; at steady state (everything encoded) every grep pays a full-table filter pass to return zero overlay rows. Measured on live Postgres, 20k rows: Seq Scan, `Rows Removed by Filter: 20006`, 2,286 buffers per call — linear in table size (~1.1M buffers/~2 s extrapolated at 10M rows), on the latency-sensitive agent path; glob-gated variants are no better (scoped index range visits the whole scope). Remedy measured on the same corpus: a plain btree on `encoded` → 6 buffers / 0.05 ms.

**Fix direction:** add the index (`encoded` or `(encoded, kind)`) in rows.py. Unverified lead worth its own look: when the index side saturates `CANDIDATE_BUDGET`, the overlay is skipped entirely — a busy pattern silently drops coverage of freshly-written files behind a generic truncation record.

### 10. The version guard on reindex's flag flips is pinned by no test — deleting it silently and permanently loses fresh-content matches
`src/vfs/storage/backends/database/indexing.py:201` (also `:117`) — surviving-mutation (test_review, CONFIRMED 3/3)

**What:** removing `entry.c.version == bindparam("b_ver")` from `publish_epoch` (or `chunk_dirty`) survives the entire suite (2180 passed) and the live Postgres leg (which never reaches the reindex phases at all). The lost behavior is worse than transient, verified: a write raced into the publish window gets stamped `encoded=True` under the unguarded flip, the published epoch keeps grams for deleted chunk ids, and `_work_pending` no-ops forever — the fresh body is permanently unfindable with `reindex()` reporting success. The guard is a declared contract in four places (module docstring, ADR 033, spec 093).

**Fix direction:** the missing test is written out in the finding record — a rival `storage.write` installed on the existing `reindex:before-publish` seam, asserting flags stay `(False, False)` and grep serves the fresh body; belongs beside `TestPublishRace`. The `chunk_dirty` guard needs a new seam to pin (noted, not demonstrated).

### 11. `invert_match`'s membership in `scan_all` is unkilled — invert over an indexed corpus is untested
`src/vfs/storage/backends/database/grep.py:131` — surviving-mutation (test_review, CONFIRMED 3/3)

**What:** mutating `scan_all = invert_match or plan.is_any()` to drop `invert_match` passes the whole suite and the Postgres conformance leg; behaviorally the mutant silently returns `[]` for invert over encoded rows (verified: live tree `['/without.txt']`, mutant `[]`). ADR 033 §5 explicitly says the conformance pin "is the contract... recorded so nobody later 'fixes' invert into a refusal without a decision" — but that pin never reindexes, so every row it sees is scan-side regardless; the other invert test uses a gramless pattern. The routing the ADR asks nobody to break is defended by no test.

**Fix direction:** the 4-line missing test (write two files, reindex, invert-grep, assert the non-containing file) is in the finding record; home: `TestOverlayPartition`. Unverified lead: the fixed_strings/word_regexp conformance rows share the same never-encoded blind spot.

### 12. grep line semantics use `str.splitlines` — `\x0c`/`\x85`/U+2028 in content cause silent false negatives and wrong line numbers vs grep/rg
`src/vfs/pattern_matching/grep.py:133` — correctness (adversarial_review, CONFIRMED 3/3)

**What:** `splitlines()` breaks on `\x0b \x0c \x1c-\x1e \x85 U+2028 U+2029` — bytes grep/ripgrep treat as ordinary in-line characters. Verified on memory tier, sqlite both tiers, and live Postgres: a pattern spanning a form feed matches nothing (`success=True, errors=[]`); every match after such a byte carries a wrong line number (could misdirect a downstream edit); `output_mode="count"` reports wrong counts. Content round-trips byte-identical, so nothing upstream normalizes. The a0290dc differential-battery parity claim is untested here — the battery corpus is `\n`-only ASCII. Form feeds are conventional section separators in real source; U+2028/29 appear in JS/JSON/scraped text. CRLF is benign (verified).

**Fix direction:** split on `"\n"` (with trailing-empty handling), matching the index fold's own newline normalization; the same fix must land in `results/render.py:401,403` or rendering re-introduces the skew; add a control-character battery row. Unverified lead: fold-vs-verify `\r` asymmetry may plan grams no posting carries.

---

## Minor

### 13. Ext-channel normalization law spelled inline at 6 sites; three of them unpinned
`src/vfs/pattern_matching/glob.py:120` + 5 more — duplication (ownership_review, DOWNGRADED major→minor 3/3)

The `lstrip(".").lower()` channel law is spelled identically at 6 sites in 5 modules (all added in-range). **No behavioral divergence exists today** (14-way storage-vs-chained probe: all SAME), and the "declared owner bypassed" half was refuted — `normalize_extension` owns the *column* law by its own scoped docstring; the channel has its own documented law. What survives: deleting `.lstrip(".")` at three of the sites passes the whole suite. Fix: a `normalize_ext_channel()` helper in `vfs.paths` beside (not replacing) `normalize_extension`, plus one dotted/uppercase pin at each unpinned consumer. Unverified lead: `ext=("",)` vs docs on extensionless names read as contradictory.

### 14. "3.12 floor" doc drift — two docstrings contradict the floor the same set decided
`src/vfs/pattern_matching/glob.py:366` and `tests/pattern_matching/test_glob.py:473` — divergence/decay (ownership + contract + test lenses, all CONFIRMED — converging, merged)

Both say "the 3.12 floor"; ADR 035/pyproject/CI/tooling.md all say 3.11, and the parenthetical was already wrong at authoring (pyproject then read `>=3.13`). Zero runtime effect; the translator's justification holds at any floor below 3.13. Two-word fix (or drop the number — pyproject/ADR own the fact). Unverified leads found alongside: `docs/index.md:16` and `docs/contributing.md:15` still say "Python 3.12+"; `STATUS.md:38` says "py3.13 floor"; ADR 032:53's `>=3.13` consequence line is likely deliberate history.

### 15. Posting-byte budget exempts the first chosen gram per AND node — undeclared policy
`src/vfs/storage/backends/database/grep.py:260` — gap (contract_review, CONFIRMED)

The rarest gram is always fetched regardless of `byte_size`, and the exemption repeats per OR branch (verified: 402-byte blob fetched under a 10-byte budget; 804 across two branches; no error). Correctness-safe and arguably the right choice (strict enforcement would silently lose index-side matches — verified), but ADR 033/spec 093/the module docstring all state the strict form. Fix: state the exemption in the contract, or decide to route an over-budget sole gram to the scan tier. Unverified lead: nothing caps OR-branch count, so wide alternations fetch one blob per branch regardless of the budget.

### 16. Reindex has no declared corpus-memory ceiling (design note)
`src/vfs/storage/backends/database/indexing.py:151` — memory-growth (scale_review, DOWNGRADED major→minor 2/3 confirmed→downgraded on the framing)

Measured: peak resident ≈3.6–4.3× live corpus bytes on every rebuild (sqlite and Postgres), paid in full when a single entry is dirty. The dominant term is the whole-corpus postings dict that ADR 033 §6 *mandates* ("build the full posting set"; incremental maintenance explicitly rejected), and the declared scale contract is statement-shaped and met — so this is a recorded design ceiling question for the owner, not a defect: declare a corpus ceiling, or partition the build into gram-range passes. `session.stream()` (not `yield_per`, which raises on the async path — verified) trims only 15–32% and must not be filed as the boundedness fix.

### 17. Reindex flag flips degrade to one round trip per entry on MySQL — and (verified) MSSQL
`src/vfs/storage/backends/database/indexing.py:204, 120` — round-trips (scale_review, CONFIRMED)

aiomysql's `executemany` falls back to a per-paramset loop for UPDATE (verified: 300 entries → 300+300 round trips, linear at 3000); MSSQL shows the same per-row execution server-side (250 executions in `dm_exec_query_stats`). 10k dirty entries = 20k sequential round trips inside writer transactions. The existing bind-count scale pin is blind to round trips. Fix: set-based guarded updates — `_values_update` is legal on MSSQL/Postgres; MySQL (no UPDATE...RETURNING) needs a chunked row-constructor `IN`. Unverified lead: writes.py's `_guarded_by_aggregate` has the same shape on the ordinary write path (outside this range).

### 18. Scan-side merge holds up to arm-chunks × (limit+1) rows before truncating
`src/vfs/storage/backends/database/grep.py:371-385` — memory-growth (scale_review, CONFIRMED)

Verified at the shipped budget: 400 scope globs → 20,002 rows held for 10,000 owed; linear in chunk count; at the router's 10k-root contract (~2 globs/root → ~100 chunks) ≈1M RowMappings (~0.5–1 GB). Per-chunk top-(limit+1) is the correct merge input (proven), so incremental pruning to the lowest limit+1 preserves results and the overflow flag. Results are correct and truncation is loud → minor; the trigger is the default (never-reindexed) state. Unverified lead worth attention: the arm-chunk loop checks no deadline — measured 9.43 s of the 10 s budget burned inside the executor, in one run returning 0 observations after the over-fetch ate the deadline.

### 19. Posting decode over-wide boundary off-by-one untested
`tests/models/test_postings.py:107` — boundary-gap (test_review, CONFIRMED)

The test feeds an 11-byte varint; the minimal illegal width is 10. Mutant `_MAX_VARINT_BYTES = 10` survives the full suite and the Postgres leg, and decodes a crafted 10-byte blob **silently wrong** (`[5]` via int64 wrap) — the exact class the codec docstring forbids. One-test fix (written out in the finding record).

### 20. Declared grep traits are asserted by no test; deleting them silently skips the tier-gated conformance rows
`src/vfs/storage/backends/database/backend.py:107` — conditional-test-logic (test_review, CONFIRMED)

Popping `grep_tier`/`grep_staleness` off `traits()` flips exactly 4 conformance rows from pass to skip with zero failures (verified). ADR 033 §9 commits to the declaration as contract; the gate-on-trait is the amplifier. No runtime consumer today keeps it minor. Fix: direct traits pin beside the capabilities pin, and harden `_indexed_grep_tier` so absence fails and only an explicit `"scan"` skips.

### 21. Glob class reducing to bare `!` emits invalid regex `[^]` — raw `re.PatternError` through the public API
`src/vfs/pattern_matching/glob.py:452` — correctness (adversarial_review, CONFIRMED 3/3; corrected major→minor)

`_translate_class` omits fnmatch's `stuff == '!'` arm: `fs.glob("[]-[!]")` / `grep(globs=...)` raise a raw `PatternError` instead of a classified invalid Result, and `glob_defect` wrongly returns None. An exhaustive ≤6-char fuzz (1.65M patterns) found 84 raising patterns and **zero silent source mismatches** — so 82a83cf's byte-parity claim holds everywhere except this crash class. Minor because only a degenerate class interior reaches it; loud, no wrong matches. Fix: `if body == "!": return "."` plus a parity-battery row (and consider folding the bounded fuzz into the battery).

### 22. Concurrent reindex rivals die on a leaked UniqueViolation classified `unavailable`, not the declared `conflict` channel
`src/vfs/storage/backends/database/indexing.py:142` — error-channel (adversarial_review, CONFIRMED)

Both rivals mint `previous+1`, so the loser hits the `(epoch, gram_key)` PK in phase B and never reaches the CAS whose declared classification is `conflict` — under real concurrency the declared channel is effectively unreachable (only a synthetic seam test exercises it). Raw driver text (constraint/table/key values) reaches a public Result, contradicting ADR 029's hygiene line; state stays consistent and a retry heals (verified on Postgres/MSSQL/Oracle). Fix: arbitrate the reindex inserts or classify the PK collision as `conflict` without driver text.

---

## Design questions (downgraded from defects — no wrong behavior; recorded for the owner)

23. **`passes_filters`' home** (`pattern_matching/grep.py:53`) — the shared path-gate is used by chained *glob* too; the package docstring assigns "structural path gates" to grep and plan 094 deliberately keeps `filter_paths` as the simple public form. Question: relabel the shared gate, or move it to glob.py keeping the one-way dependency. (ownership, DOWNGRADED)
24. **Admission/exclusion law inline copies** (`reads.py:238`, `base.py:1874`) — two behavior-equivalent inline re-spellings of `passes_filters` (38,880-case differential: 0 mismatches); the per-row compile in the keep closure is irreducible (pattern is row-derived). Consolidation optional. (ownership, DOWNGRADED)
25. **Ext-membership rideability + bind count four-site pair** (`reads.py:234/276`, `grep.py:369/378`) — character-identical spellings, cannot drift by input, bind ceiling verified accurate on MSSQL; a paired helper would drift-proof it. (ownership, DOWNGRADED)
26. **`meta_scoped` placement** (`reads.py:288`) — protocol docstring assigns *behavior*, not a shared implementation; only one backend exists. Real two-line duplication is with `paths._under_meta_root` (byte-identical) — one import would do; also an ADR-031 "literal prefix" vs docstring edge worth one glance. (ownership, DOWNGRADED)
27. **Epoch fingerprint hand-transcribes the fold identity** (`indexing.py:57`) — accurate today; the fingerprint is hand-maintained by design and also omits chunk grain and the extraction algorithm; the proposed FOLD_SIGNATURE would not close the hole (verified). Question: derive the fingerprint, or name INDEX_FORMAT_VERSION as the one obligated knob in ADR 033. Cross-interpreter casefold tables 3.11↔3.13 verified identical today. (ownership, DOWNGRADED)
28. **Refusal-label vocabulary across the four glob-channel minting sites** — labels drift ("glob exclusion" vs "grep glob" vs "glob pattern" for globs_not) but every message quotes the offending pattern and no contract owns the wording; the loose storage label is effectively unreachable from the public surface. One channel→label map would unify. (ownership, DOWNGRADED)
29. **STATUS.md lags ADR 034/035 and spec 094** — the file declares itself "a snapshot, not a live index" and per-spec status lines are authoritative, so lagging is its declared mode; also carries two different as-of dates. Question: regenerate now or with 094's mining pass. Unverified lead: 094 is story-complete yet still in `active/`. (contract, DOWNGRADED)
30. **Posting-insert row cap never forced across a boundary** (`indexing.py:260`) — the `max_rows` branch is hit 0 times across the suite and every mutant survives, but SQLAlchemy's insertmanyvalues re-chunks the INSERT by the same budget on its own (verified uncapped on MSSQL: 128 statements ≤2,094 binds; Oracle: executemany at 6 binds) — no engine error is reachable. Question: delete the redundant cap or pin it as declared belt-and-braces. (test, DOWNGRADED)

---

## Coverage

All five lenses completed; no lens failed. Everything below "not reached" is **unreviewed surface**, not clean.

**ownership_review (10 raw findings):** Read whole at tip: pattern_matching package, database backend (grep/indexing/reads/descent/dialects/backend diffs), protocol.py, models (postings/code_grams/chunk/entry/rows), params, kinds, and all touched regions of base.py. Verified correctly placed: posting codec and corruption taxonomy in models; fold single-homed in code_grams; reindex phase logic in indexing with transactions owned solely by backend; budgets/chunking single-homed in dialects; Annotated primitives minted beside producers; flag law consistent across rows/writes; capability derivation; router/storage double-gating as deliberate seam defense; chained paths reusing the pattern_matching authorities. Smells noted, not filed: grep_rows' truncation bookkeeping spelled thrice; `_REFINE_GUIDANCE` hand-transcribing GRAM_SIZE. Engines touched: sqlite, MSSQL (bracket note); PG/MySQL/Oracle not needed for its claims. **Not reached:** docs-only commit content beyond metachar/escape searches, notebooks/, CI workflow, .claude/skills; tests read selectively only.

**test_review (7 raw):** Verified well pinned: postings battery (one boundary gap filed); glob defect/expansion/composition batteries — plus an 8,736-pattern generated stdlib differential (zero mismatches, battery understates real parity); sqlite reindex lifecycle; db grep battery (refusal gate, overlay union, budgets, atomicity seam); write-side flag lifecycle; router batteries incl. 10k-root call-log; arm_budget caps; per-dialect DDL. Empirically drove a full write→reindex→grep→rewrite→reindex arc on all four live engines (surfacing the MSSQL break and the structural no-reindex-in-conformance gap). **Not reached:** research-study harnesses, CI mechanics beyond the floor change, graph/mkedge stubs, test_dispatch.py line-by-line, Chunk.split internals, MySQL LONGBLOB behavior >64 KB (DDL pinned only).

**scale_review (8 raw):** All four live engines exercised. Verified clean: every membership predicate chunks by declared budgets (gram meta/blobs, chunk/entry/content ids, path lookups, chunk deletes); pattern fans chunk at the 200-arm ceiling under bind/IN-list/depth caps — 5,000-pattern glob and 10k-target stat verified live on Oracle; ARM_FIXED_BINDS=7 recounted accurate; posting inserts under bind+byte caps; LONGBLOB pinned; no rogue chunk constants; GENERIC floor by code inspection; grep's id-first ladder avoids content overfetch until the final set; version-guard miss posture; move/trash flag interplay defended by the meta gate; PG/MySQL race legs protected by their pins; codec refusals loud; build_epoch's dict growth inherent to the ADR'd design. **Not reached:** no true GENERIC engine run (judged from profile code + MSSQL/Oracle); reindex at millions-of-chunks scale (memory findings extrapolate from measured shapes, not a driven OOM); router-level 10k-root pins taken from landed tests plus backend-level Oracle runs; ADR/spec prose accuracy audited only as declared intent.

**contract_review (6 raw):** Suite 2180/788 and ruff+ty zero confirmed at tip. Translator parity re-verified by a 163,214-pattern fuzz (zero byte-level mismatches on defect-free inputs). All 32 example/refusal rows of `docs/reference/glob-patterns.md` re-executed — pass. ADR 034 chained semantics traced line-by-line into the routers — as declared (order/duplicates/no-meta/kind fetch-to-populate/loud ladder/no refusal gate); protocol signatures match; deleted machinery confirmed gone. ADR 033 refusal gate, folded-planning/sensitive-verify, dedupe, budgets, capability/traits, CAS+seam, eligibility gates — verified in code; edit/write flag resets verified empirically. Oracle and MSSQL grep/glob conformance selections green; Postgres exercised directly. **Not reached:** the MySQL leg (no claim verified against it in this pass); re-running the rg/grep differential batteries and MSSQL fan/ladder benchmarks (numeric claims — 3.8×/1.4×, 121/109 case-checks — taken on the commit record); 10k scale rows trusted to their suite pins; the residuation notebook; index-side truncation survivor order (contract-silent, noted only).

**adversarial_review (4 raw):** Executed attack batteries: translate fuzz 115k patterns (one root cause found — bang-class); postings codec 250k random/mutated blobs vs a pure-Python oracle — fully clean, every corruption refused loudly; 399-trial indexed-grep-vs-oracle fuzz over a Turkic-i/sharp-s/CRLF corpus — clean; chunk-boundary sweep (critical found, reproduced on three engines); ripgrep line-semantics differential (finding); delete/move/overwrite lifecycle between reindex and grep — clean; brace cap/defect probes vs a bash oracle — clean and loud; chained rows-in-hand edge battery — per ADR 034 contract; 3-way rival reindex on real Postgres — state consistent, error channel wrong (finding); Oracle 1,200-file single-call scale — clean, no ORA-01795; budget/boundary probes incl. loud candidate-budget truncation at 10,050 files. Refuted its own leads where the code was right (brace oracle, straddle survivor, wrap refusals, per-mount error fan-out). **Not reached (time-boxed):** wall-time-budget truncation path, trash/restore × index interplay (independently caught by contract lens — finding 1), the 10k-root probe-scale claim, deep residuation fuzz, grep `paths=` root-probe channel, MySQL/MSSQL/Oracle concurrency legs, smart-case handling of regex escape classes vs ripgrep.

**No lens reached at all:** the five docs-only commits' prose content as such (beyond targeted contract greps), `examples/glob_residuation.ipynb` execution (one stale-text lead noted), `.github/workflows/test.yml` beyond the floor matrix, `.claude/skills` changes, `uv.lock`, and `context/open-questions.md`'s committed content.