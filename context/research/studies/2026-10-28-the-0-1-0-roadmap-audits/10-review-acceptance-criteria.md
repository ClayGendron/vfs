# Review of the roadmap acceptance criteria (§4–§14)

Reviewed against: `context/standards/roadmap.md` at `main` `90f5883`
(2026-10-28); CLAUDE.md; the constitution; ADRs 063, 068, 080, 082,
083, 084, 085, 087; specs 148, 149, 157, 166, 167, 169, 170, 171,
174–181; the live tree (`ops.py`, `kinds.py`, `base.py`,
`dialects.py`, `protocol.py`, `embedding/`, `tests/conftest.py`,
`tests/test_ops.py`, the two workflows).

Severity: **blocking** = a test written from the criterion would pin
the wrong contract, the story cannot be scheduled as written, or the
gate list is wrong; **should-fix** = the criterion is untestable as
worded, names a thing that does not exist, or leaves a fork the test
author must guess; **nit** = wording or vocabulary.

Counts: blocking 9 · should-fix 40 (33 criterion rewrites + 7
completeness gaps) · nit 35 (wording and vocabulary; the "fine,
consistent" notes under some criteria are confirmations, not counted).

Cross-references: a per-story line marked "(freeze)" or "(gate list)"
points at the single blocking finding R5-A or the §2 finding and is
not counted twice.

---

## Cross-cutting (not one story)

### X-A · "Engine legs" means three different sets · should-fix

- *Quoted:* K2.1 "on SQLite, Postgres, SQL Server and Oracle"; K3.1
  "on all four engine legs" (after listing the same four); F4.2 "on
  all five engine legs"; D4.2 "parametrized over `ENGINE_LEGS`";
  I5.4 "on SQLite by default and on each engine leg when the URL is
  set".
- *Problem:* CI's four legs are Postgres, **MariaDB**, SQL Server,
  Oracle (`test-dialects.yml` matrix; `tests/conftest.py`
  `ENGINE_URLS`). SQLite is not a leg, it always runs. K2.1/K3.1's
  "four" omits MariaDB and includes SQLite; F4.2's "five" presumably
  adds SQLite. `ENGINE_LEGS` is a local list in two test files
  (`test_signals.py`, `test_races.py`), not a shared fixture.
- *Rewrite:* add to §0: "**An engine leg** is one of the four
  `VFS_TEST_<ENGINE>_URL` legs — Postgres, MariaDB, SQL Server,
  Oracle — deselected by `tests/conftest.py` when the URL is unset.
  SQLite and the in-memory backend always run. 'On every engine leg'
  means SQLite plus those four." Then replace every "four/five engine
  legs" with "on SQLite and on each engine leg". D4 should also carry
  the task "promote `ENGINE_LEGS` to a shared fixture in
  `tests/conftest.py`".

### X-B · The constitution's names are stale and no story amends it · should-fix

- *Quoted:* roadmap §0 "where this page and a decision record
  disagree, the record wins"; constitution Art 1.3 `Candidate`, Art
  1.5 `if_revision=X` → `Conflict`, Art 2 §1 `VFSResult` and a
  seven-kind taxonomy.
- *Problem:* the live tree has `Result`, `Observation`, `if_version`
  (K2) and 23 kinds. K1/R5 freeze names that contradict the
  constitution; a test that "pins the constitution" cannot be written.
- *Rewrite:* add to R5 (or R6.4): "The constitution's Art 1.2, 1.3,
  1.5 and 2 §1 are amended to the frozen names (`Entry`,
  `Observation`, `Result`, `version`/`if_version`, the `ErrorKind`
  enum) in the same landing as `docs/reference/api.md`."

### X-C · Criteria that leave a fork for the test author · should-fix

- *Quoted:* K2.6 "`overwrite=` leaves `write` (or stays, per D7)";
  K3.1 "one error of the chosen kind"; D3.4 "one of the two, pinned";
  H5.2 "refused `invalid` or classifies the in-doubt kind, one of the
  two, pinned"; I6.2 "(or the equivalent flag D17 names)"; D2.2 "a
  corruption kind (D19)".
- *Problem:* a criterion that names two outcomes is not pinnable. The
  page already has a lean column in §16; the criterion should carry it.
- *Rewrite:* state the lean in the criterion and mark the decision:
  K2.6 "`overwrite=` is removed from `write` (D7); the params drift
  test and `Session.write` agree"; K3.1 "…one `vfs.unavailable.integrity`
  error (D8; spec 175's lean)…"; D3.4 "…is refused `invalid` at first
  touch naming `use_setinputsizes` (lean)…"; H5.2 "A deadline on a
  mutation is refused `invalid` before any statement (lean), counted";
  D2.2 "…classifies `vfs.unavailable.corrupt` (D19 lean)…"; I6.2
  "`VirtualFileSystem(default_authority=…, loud=True)` logs…".

---

## Domain A — the kernel

### K1

- **K1.2 · nit.** "a grep over `context/specs/active` for `overwrite=`
  finds only spec 174's removal note" — spec 169 lines 21 and 429–430
  also say `overwrite=`; the criterion names 167 and 169 so this is
  consistent, but say "specs 167, 169 and 171" (171 §carries the
  argument table from `PARAMS`).

### K2

- **K2.2 · should-fix.** "Twenty concurrent `write(append=True)` of
  one line each leave twenty lines; each call commits exactly one
  version row" — ADR 080 pin 3 and spec 174 put append at the `add`
  rung; the criterion does not say so, so a test cannot pin the
  refusal for a `list`/`read` caller. *Rewrite:* "…at rung `add`: a
  caller holding `read` on the row gets `permission_denied` with zero
  mutation statements; a caller holding `add` appends."
- **K2.3 · should-fix.** "`write(if_absent=True)` on a live occupant
  is `exists`; on a tombstone it revives and reports `created`" — ADR
  080 pin 3 (Clay, 2026-10-14): a write at a tombstone is a restore
  judged at `read_write` or own. *Rewrite:* "…on a tombstone it
  revives (judged at `read_write` or own) and reports `created`; a
  `contribute` caller who does not own the tombstone is
  `permission_denied`."

### K3

- **K3.4 · blocking.** "Bodies at or above the offload threshold hash
  on a worker thread: `to_thread` calls equal the number of large
  bodies in the batch, zero for small ones" — contradicts spec 175
  §1.3, which the story says it lands: the rule is **per call**, not
  per body (inline when `sum(size) < MEASURE_OFFLOAD_BYTES`; otherwise
  hops = number of `BLOB_PAGE_BYTES` pages, an oversize body alone in
  its page). A test written from the roadmap fails the spec's
  implementation on a 10,000 × 10 KB batch (zero large bodies, 100 MB
  total). *Rewrite:* "Hashing is offloaded per call (spec 175 §1.3):
  a batch whose bodies sum below `MEASURE_OFFLOAD_BYTES` makes zero
  `call_offloaded` calls; one that sums above it makes exactly
  `len(byte_chunked(items, BLOB_PAGE_BYTES))` calls; a single 16 MB
  body makes one."
- **K3.1 · should-fix.** D8's lean is a top-level `vfs.integrity`;
  spec 175 §2's lean (and its reasoning: `kind_family` degrades the
  child to EIO; `vfs.unavailable.schema` is the precedent) is the
  child `vfs.unavailable.integrity`. The page and the spec lean
  opposite ways. *Rewrite:* align D8 with the spec ("child
  `vfs.unavailable.integrity`, `RetryClass.never`") or say in D8 that
  it reverses spec 175's lean and why.

### K4

- **K4.1 · should-fix.** "rows visited per page ≤ 1,001 on every
  engine (counted on the keyset statement)" — spec 176 fetches
  `limit + 1` **emitted** rows and reads around tombstones; "visited"
  is not what the statement returns. *Rewrite:* "the keyset statement
  returns at most `limit + 1` rows per page, tombstones excluded by
  the predicate (rows fetched counted); with 500 tombstones between
  children 1,000 and 1,001, page two still returns ≤ 1,001 rows and
  starts at the first live child."
- **K4.2 · should-fix.** "A tombstone between two pages is never
  emitted and never stalls the key" — "never" with no counted case.
  Fold into the K4.1 rewrite above (a named tombstone count, a named
  page boundary, rows fetched counted).
- **K4 why · nit.** "`scrub` and the bounded `sweep` all page on this
  key" — both are 0.2 (§15). Say "will page".

### K5

- **K5.1 · blocking.** "A replayed `move` returns `not_found` with
  `data["vfs.occupant"]` naming the destination and its `entry_id`" —
  spec 177's replay table (row `move`) says `not_found` at the source
  with `vfs.target` the destination and `data.dest` carrying the
  occupant's `entry_id`. A test from the roadmap pins a key the spec
  never writes. *Rewrite:* "…returns `not_found` at the source with
  `vfs.target` = the destination and `data["dest"]["entry_id"]` = the
  occupant's id (spec 177 §1.3); a move of a path that never existed
  carries neither."
- **K5.6 · should-fix.** "A connection lost during `COMMIT` classifies
  apart from one lost before it" — the kinds exist in spec 177:
  `vfs.unavailable.in_doubt` (retry class `refresh`) after the commit
  seam, `vfs.unavailable.backend` (`retryable=True`) before it.
  *Rewrite:* name them, and the seam: "a fault at
  `mutate:after-commit` answers `vfs.unavailable.in_doubt`; one inside
  the statement answers `vfs.unavailable.backend`; the replayed keyed
  call answers `vfs.replayed` as an info record."
- **K5.5 · nit.** "stores its answer under the dialect's byte budget"
  — name it (`REPLAY_OFFLOAD_BYTES` / the dialect's `BLOB_PAGE_BYTES`).

### K6

- **K6.3 · blocking.** "A range past the end is `invalid` naming the
  length" — spec 178 §5: "A range past the end answers an empty slice:
  `content == ""` or `data == b""`" (POSIX `pread` behaviour; refusing
  was weighed and rejected at line 188). *Rewrite:* "A range whose
  offset is at or past `size_bytes` answers an empty slice with
  `success is True`, the row saying `range=(offset, 0)`; an offset
  below zero or a non-integer is `invalid`; a range on a directory is
  `wrong_kind`."

### K7

- **K7 · blocking (freeze).** See R5 finding R5-A: K7 is `f` and adds
  `traits()` values (`whole_batch`/`resumable`) and a new storage
  protocol method `features()` after the surface K9.4 freezes
  ("storage protocol" is on the frozen list).
- **K7.1 · nit.** "(transactions counted)" — say how: "`COMMIT`
  statements counted on the statement hook".

### K8

- **K8 · blocking (freeze).** `versions(path)`, `read(version=)` and a
  schema-format bump are public names landing at gate `f`, after b1.
  Spec 171 line 628 also makes `versions` an MCP tool, which changes
  M1.1's pinned count (21 → 22) after M1 is frozen. See R5-A.
- **K8.3 · should-fix (scope).** "A `created_by` column on the entry
  row is stamped on every mint" — no active spec or ADR carries a
  `created_by` column (spec 180's read slice lists `actor`,
  `provenance`, `source_identity`, `subjects`, `grant_revision` on
  **version** rows; ADR 064 is about version rows). *Rewrite:* either
  "spec 180 gains §N: `created_by` on `vfs_entries`, stamped from the
  authority's actor at mint" with the format-bump line, or drop the
  column and pin "the v1 version row of every entry carries the
  creator's `actor`, including `anon` and `system`" (which spec 180
  already gives).

### K9

- **K9.1 · should-fix.** "`ALL_OPS` has 24 members" — true only
  between K9 and the next verb: `cli` (F3; spec 181 line 188 counts
  "the 24 verbs, `cli` and …"), `versions` (K8), and H3's `fs.answer`
  (a router method — is it an op or a management method?). The drift
  test must know. *Rewrite:* "`ALL_OPS` has 24 members at this
  landing; the `OpGroup` drift test is the one place later verbs
  register (`cli` → `derived`, `versions` → `history`, `answer` →
  `rights`), so each later story updates that one table." And H3.4
  should say which allowlist `answer` joins.
- **K9.3 · nit.** Fine; consistent with spec 181 §3.

---

## Domain B — human in the loop

### H1

- **H1.1 · should-fix.** "The ADR … lists its amendments: ADR 084 pin
  4 and pin 9's kind list, spec 148 §5, spec 149 §5, spec 170 §4's
  failure table, spec 171's scope, the glossary line and architecture
  page 11" — two more records are contradicted and not listed: (a)
  **ADR 063 rule 5** "Timeout is the host's policy, never storage
  behaviour" vs H1.5/H3.5 (a TTL on a ledger row in the mount's schema,
  swept by storage); (b) **ADR 084 pin 1** "No verdict is passed on
  the command text" and the rejected option "a command-string policy
  language" vs H3.1 (a hook that receives "for `cli` the static parse
  of the whole line" and may `deny`). *Rewrite:* add both to the
  amendment list; for (b) say "the hook judges the static parse, never
  the text, and may only deny or suspend, never widen".
- **H1.4 · should-fix.** "a tool that cannot restart keeps its own
  checkpoint as a file under `/.vfs/jobs/<ticket>`" — §15 defers
  `/.vfs/jobs` to 0.2 and ADR 082 pin 6 reserves it unserved. An ADR
  at gate `b` cannot state a mechanism the same page says does not
  ship. *Rewrite:* "…keeps its own checkpoint outside vfs at 0.1.0;
  `/.vfs/jobs/<ticket>` is the 0.2 home and the ADR names it as such."
- **H1.2 · nit.** "a new `RetryClass.resume`" — `RetryClass` is
  documented as "derived, never wired" (`kinds.py`); say the new value
  is derived from the kind like the others.

### H2

- **H2.3 · blocking (scope).** "Every planned row carries the
  `version` it was computed against; re-sending the call with
  `plan=False` and `if_versions=` taken from the plan applies it; if
  any row moved in between, the apply is `conflict` and writes
  nothing" — stated for all twelve verbs in H2.1, but `if_version(s)=`
  exists on `write` only (ADR 087 pin 3; spec 174 §1; K2). No story
  gives `delete`, `mkdir`, `move`, `copy`, `restore`, `mkedge`,
  `rmedge`, `grant`, `revoke` or `posture` a precondition argument,
  and `edit` has its content match instead. *Rewrite:* either (a)
  H2 declares the work — "every verb in H2.1 gains `if_versions=`
  (same `ParamKind` as spec 174's), judged in the same guarded
  statement as `write`'s" — and sizes up to L; or (b) narrow: "for
  `write` and `edit` the apply carries `if_versions=`; for the other
  verbs the plan carries the rows' versions and the apply is
  `conflict` when `stat` at apply time disagrees (one extra chunked
  select, counted), with the race window documented."
- **H2.1 · nit.** `posture`'s relabel is a resumable verb (ADR 087 pin
  7); say the plan is "the everyone row that would appear and the
  count of rows the relabel would touch", so the test has a number.

### H3

- **H3.4 · should-fix.** "`fs.answer(ticket, allow=True,
  authority=approver)` writes one attributed ledger row … `Session.answer`
  does not exist (the answer channel is the grant channel)" — if it is
  the grant channel, it needs a rung: ADR 080 pin 9 puts `grant` at
  `read_write`. *Rewrite:* "…an approver below `read_write` on the
  ticket's path is `permission_denied` and the ledger gains no row."
  Also say whether `answer` is a registered `Op` (then K9.1's count
  moves) or a management method.
- **H3.5 · should-fix.** "an expired ticket is `pending` with
  `expired=True`; `sweep` reclaims expired rows (counted)" — ADR 063
  rule 5 says timeout is never storage behaviour (see H1.1). Either
  H1 amends it (then fine) or the TTL is enforced at answer time only
  and `sweep` never reads the clock. Pick one and say it.
- **H3.1 · nit.** "`CallDescription`" is a new public name; add it to
  K9.4's frozen list or mark it as landing at H3 (gate `b`, fine).

### H4

- **H4 · blocking (freeze).** `Interrupt(payload)`, exit code 75 in
  the shell table, `cli(request_key=)` (implied by H4.2 "re-issuing
  the same line with a live allowance") are public names at gate `f`.
  See R5-A.
- **H4.2 · should-fix (scope).** "Re-issuing the same line with a live
  allowance runs the tool once more with the answer as its resume
  value" — spec 177's `request_key` is on twelve verbs; `cli` is not
  one (spec 171 §cli schema: `command`, `workdir`, `timeout_ms`). The
  resume token for a line needs an argument no spec carries.
  *Rewrite:* "`cli(line, request_key=ticket)` (amends spec 171's `cli`
  schema and spec 177's verb list) re-runs the line once…".
- **H4.3 · nit.** "A mounted 2026-07-28 server" — name the SDK
  revision string the test vendors (M1.5 names three schemas).

### H5

- **H5.2 · should-fix.** See X-C.
- **H5.3 · nit.** "An outer `CancelledError` still re-raises untouched"
  — testable; fine.
- **H5.4 · nit.** "on the wire this is the MCP tasks extension's cancel
  when M3 lets tasks in" — D25 lean is "no tasks at 0.1.0"; drop the
  clause or mark 0.2.

---

## Domain C — identity

### I1

- **I1.2 · should-fix (scope).** "one shipped implementation over a
  JOSE library behind a new `vfs-py[serve]` extra" — no decision
  names the library (PyJWT, joserfc, authlib, python-jose) and D13/D14
  do not cover it; the choice fixes the extra's dependency set and
  the audience/`act` claim handling. *Rewrite:* add D-n "JOSE
  library for `vfs-py[serve]`: lean joserfc (RFC 7519/7523, typed
  claims, maintained)" and cite it from I1.2.
- **I1.5 · nit.** "a bare `Authority(...)` constructed outside
  `vfs.authority` raises `TypeError` naming the doors" — the repo's
  rule is classified `Result`s for input errors; a constructor raising
  is Python-level misuse so `TypeError` is defensible — say so in one
  clause ("a programming error, not a classified refusal").

### I2

- **I2.4 · nit.** "logs one warning per open mount" — pin with
  `caplog`: "exactly one `WARNING` record per open mount, naming it".

### I3

- **I3 · blocking (dependency cycle).** "*Depends on.* T1, T3 (the
  catalogues); K9" while T3 says "*Depends on.* T1, T2; I3 for the
  rungs". I3 ↔ T3 is a cycle; §14 puts both in a5 with no arrow.
  *Rewrite:* split I3 into the seam (I3a: `SupportsGrants.rungs_at`,
  criteria 1 — depends on nothing but K9) and the catalogue postures
  (I3b: criteria 2–4 — depends on T1, T3). T3 then depends on I3a; §14
  a5 reads "I3a → T1 → T2 → T3 → I3b → T4".
- **I3.3 · nit.** Exit codes 126/127 are consistent with ADR 084 pin 2
  and ADR 082 pin 11. Fine.

### I4

- **I4 · blocking (freeze).** `add_mcp(credentials=)` accepting a
  `CredentialResolver` protocol is a new public name at gate `f`. See
  R5-A.
- **I4.3 · nit.** "100 calls by one principal issue exactly one
  `initialize`" — good; add "and `tools/list` is issued once per
  `(server, principal)` inside the list floor" so I4.3 and T4.3 agree
  on the cache key after I4 changes it from per-server to
  per-principal (spec 170 §3.1 says one list per server; I4 amends
  that and T4.3 should say "per server, per principal once I4 lands").

### I5

- **I5.3 · should-fix.** "runs in `ceil(rows / RELABEL_CHUNK)`
  statements" — no such constant; the live name is `RELABEL_ROWS`
  (`dialects.py:96`, profile field `relabel_rows`). *Rewrite:*
  "`ceil(rows / profile.relabel_rows)` statements".
- **I5.1 · nit.** "holds ≤ 64 pieces and ≤ 4 KiB of bind bytes" —
  "pieces" is the `rights.py` docstring's word, not a field; say
  "`Rights` compiles to ≤ 64 path ranges and the bound value is ≤ 4 KiB
  (len of the joined ranges string)".

### I6

- **I6 · blocking (gate list).** Tagged `b` and absent from §2's
  Identity line. See §2 finding.

---

## Domain D — storage

### D1

- **D1.1 · nit.** "SQL Server 2,100 binds and the 2,000 lock budget"
  and D4.2 "SQL Server 2,000" — both are right (`in_list_budget=2_000`
  is the lock-derived IN cap; 2,100 is `insertmanyvalues_max_parameters`);
  say in D4.2 "the chunk is `membership_budget` = min(2,000, bind
  budget)" so the formula names one number.
- **D1.3 · nit.** Consistent with live `backend.py:280–286` (only
  `glean` withheld) and ADR 059's 2026-08 amendment. Note that
  **spec 171 §tool set** still says "withholds `glean` and `graph` …
  18 verbs plus `cli`" — add spec 171 to the list of pages D1.3 fixes
  (see M1.1).

### D2

- **D2.2 · should-fix.** See X-C (name the corruption kind).
- **D2.3 · nit.** "(DDL statements counted per bump)" — fine.

### D3

- **D3.2 · should-fix.** "first touch refuses a classified kind with
  `data["schema"]` and `data["privilege"] == "CREATE"`" — spec 157
  decision 2 names it: `unavailable` with `data={"schema": …}`. Name
  the kind so the test is exact: "`vfs.unavailable` (spec 157 §2) with
  `retryable=False`, `data["schema"]`, `data["privilege"] == "CREATE"`".
- **D3.4 · should-fix.** See X-C.
- **D3.5 · nit.** "`fs.install_extensions(path)` (or an equivalent
  admin reach from the router)" — pick the spelling; the drift test
  on management methods needs a name.

### D4

- **D4.1 · nit.** "asserts the verb's statement count equals a
  declared `O(chunks)` formula" — good; add "and the formula is a
  named constant beside the test (`EXPECTED_STATEMENTS[verb]`)" so
  the delta D4.4 wants is visible in one place.

### D6

- **D6.1, D6.3 · nit (process).** "the next storage push is green on
  all four legs with per-leg pass counts in the commit body"; "The run
  against the last beta is recorded in the release notes" — not
  pinnable in `tests/`; acceptable for a release story, but mark them
  "(CI evidence, not a test)" so the "every criterion is a test" claim
  in §0 stays honest. Same for R2.1, R2.4, R3.3, R3.4.

### D7

- **D7 · blocking (gate list and freeze).** Tagged `f`, absent from
  §2's Storage line; adds pool kwargs to `DatabaseStorage(...)` after
  the constructor is frozen (X4.3 documents "constructor parameters"
  at `f` too). See §2 finding and R5-A.
- **D7.1 · should-fix (scope).** "Pool settings (size, overflow,
  pre-ping, recycle) are plumbed to `create_async_engine`" — no story
  names the public shape (kwargs on `DatabaseStorage`, a `PoolConfig`,
  or pass-through `engine_kwargs=`). *Rewrite:* "`DatabaseStorage(url,
  pool=PoolConfig(size=, max_overflow=, pre_ping=, recycle=))`; the
  params drift test lists the four fields; the `:memory:` path ignores
  them and keeps `StaticPool`."

---

## Domain E — search

### E2

- **E2.1 · should-fix.** "A scripted provider whose per-input latency
  makes a 2,048-input batch exceed the timeout still finishes
  `reindex` with `unembedded == 0`; assert on request count, not the
  clock" — the setup itself needs wall time (a 120 s timeout must
  elapse) or a patched timeout; the criterion says what to assert but
  not how the timeout fires. *Rewrite:* "A scripted provider that
  raises `TimeoutError` for any batch above N inputs (no clock)
  finishes `reindex` with `unembedded == 0`; requests issued equal
  `ceil(pages / N)` plus the `log2` retries E2.2 pins."

### E4

- **E4.2 · nit.** "`ndcg@10(fused) ≥ ndcg@10(bm25) − GATE`" — name the
  constant and its value in the criterion (the study's number) so a
  regression is a diff, not a judgement.
- **E4.4 · nit.** "`tier ∈ {native_exact, native_ann}`" matches
  `glean.py:170`; D1.1 uses the profile's `vector_distance`
  (`exact`/`ann`). Say "the `legs` extra's `tier` equals
  `f"native_{profile.vector_distance}"`" so the two vocabularies are
  tied.

### E5

- **E5 · blocking (gate list).** Tagged `b`, absent from §2's Search
  line. See §2 finding.

---

## Domain F — the shell

### F3

- **F3 · should-fix (dependencies).** "*Depends on.* F1, F2" — §14
  and D33 say "K2 (174) before F3 (167 C) so the shell never ships the
  racy `>>`", and spec 167's amendment list makes `>>` one guarded
  call. F3 must depend on K2 or its `>>` criterion is unpinnable.
  *Rewrite:* "*Depends on.* F1, F2, K2 (`>>` is `write(append=True)`;
  `touch` is `write(if_absent=True)`)" and add criterion 8: "`echo x
  >> f` issues one `write(append=True)` call (spied) and twenty
  concurrent lines leave twenty."
- **F3.7 · nit.** "The four engine legs are green" — unbounded;
  rewrite "the slice-C battery is parametrized over the engine legs
  (deselected when the URL is unset)". Same for T1.6.
- **F3.4 · nit.** Consistent with ADR 084 pins 5/9 (`STAGE_BUDGET` 64
  → a 65-stage line is `invalid`; `curl` 126; `sweep` 127).

### F4

- **F4.2 · nit.** "on all five engine legs" — see X-A.
- **F4.4 · should-fix.** "`set -e` stops at the first failing statement
  with every POSIX exemption pinned" — "every" with no list. *Rewrite:*
  name them: "the exemptions pinned are: the left side of `&&`/`||`,
  a `!`-negated pipeline, a pipeline whose last stage succeeds, the
  condition of a (refused) `if`, and a subshell's inner failure".

### F5

- **F5 · nit (dependencies).** No *Depends on* line, yet F5.3's exit
  table includes 75 (H4, gate `f`, batch a6) and 123 (F6's `xargs`).
  Add "*Depends on.* F4; H4 and F6 for rows 75 and 123".
- **F5.1 · nit.** "the in-scope run rate is at least 85%; the number
  is printed in the README" vs §9 "about 25 programs cover 87% of the
  measured corpus". Two numbers, one README. Say "the README prints
  the harness's measured rate, and the 87% corpus figure is the memo's
  not the README's".

### F6

- **F6.4 · nit.** "over 25 files calls the `grep` verb 3 times" — good
  (ceil(25/10)); say "(spied on `VirtualFileSystem.grep`)".

---

## Domain G — tools

### T1

- **T1.3 · blocking (scope).** "`ls /.vfs/mounts` answers the mount
  table (closing the shell memo's gap 9)" — no spec or ADR serves a
  `mounts` view: ADR 082 pin 6 enumerates the heads (`bin`, `tools`,
  `mcp`, `skills`, `sessions`, `jobs`, `run`, `trash`), spec 169 lists
  the served heads at the root (`bin`, `skills`, `run`), and the shell
  memo (07-session-state §165) records the mount table as **not** in
  the namespace. The criterion quietly adds a view and a projection
  (what columns does a mount row show? is it bare at `list`?).
  *Rewrite:* either drop it from T1 and open a D-n ("a `/.vfs/mounts`
  view: yes/no; lean no at 0.1.0, `mounts()` is the API"), or add a
  task to spec 169 with the row shape and the rung, and keep the
  criterion.
- **T1.1 · should-fix.** "On a fresh node `ls /.vfs` lists `bin skills
  trash`" — spec 169 adds `run` (169c = T2), T3 adds `tools`, T4 adds
  `mcp`; a test pinning the exact set at T1 breaks at T2. *Rewrite:*
  "`ls /.vfs` lists exactly the served heads plus `trash`: `{bin,
  skills, trash}` at this landing; T2, T3 and T4 each add one head and
  update the same pin; a reserved, unserved head is `not_found` on
  read and `invalid` on write."
- **T1.2 · should-fix.** "`sweep /.vfs/trash` passes; `posture
  /.vfs/bin` lands in the root binding's grants table" — written in
  shell spelling, but F3.4 pins `sweep` and `posture` as `unrecognized`
  127 in the shell, and D34 adds only `grant`/`revoke`/`grants`
  spellings. *Rewrite:* "`fs.sweep("/.vfs/trash")` succeeds;
  `fs.posture("/.vfs/bin", "list")` writes its row in the root
  binding's grants table (one `grants` row counted)".

### T2

- **T2 · nit.** No *Depends on* line; it sits in §14's chain after T1.
  Add "*Depends on.* T1 (the view table), F3 (the `cli` Result)".

### T3

- **T3 · blocking (dependency cycle).** See I3.
- **T3.1 · nit.** "`str` → one text row, `dict` → one JSON row, `None`
  → no row, a `Result` passes through" — ADR 082 pin 15 also has
  `bytes` → a bytes row. Add it.

### T4

- **T4.2 · should-fix.** "elicitation → `pending` (H4) once H1 lands,
  `unsupported` 126 until then" — H1 is batch a2 and T4 is a5, so
  "until then" is dead text; but the **producer** is H4 (a6). At T4's
  landing the kind exists and nobody produces it. *Rewrite:*
  "elicitation → `vfs.unsupported` 126 at this landing (spec 170 §4);
  H4 flips the row to `vfs.pending` 75 and updates this pin".
- **T4.3 · should-fix.** "`ls /.vfs/bin` twice in one `cli` call issues
  one `tools/list` per server" — I4.3 changes the key to `(server,
  principal)`. Say "per server (per principal once I4 lands)".
- **T4.5 · nit.** "no cross-task error on Python 3.11 and 3.13" — the
  CI matrix runs 3.11–3.14; say "on every matrix leg".

### T5

- **T5.2 · nit.** "at most 21 verbs (the measured 17 `stat`, 2 `read`,
  2 `write`; a stat cache lowers the bound and the test pins the new
  number)" — good; counts.

---

## Domain H — the MCP front

### M1

- **M1.1 · should-fix.** "21 on the default router, 19 on an unknown
  dialect" — 21 matches spec 171 (`AGENT_OPS` = 20 + `cli`), but 19
  assumes `glean` **and** `graph` withheld; the live floor withholds
  `glean` only (`backend.py:280–286`; ADR 059 amendment; D1.3 on this
  very page). Spec 171 line 128 is stale. *Rewrite:* "21 on the
  default router, **20** on an unknown dialect (`glean` withheld,
  D1.3), 1 with `tools={"cli"}`" and add spec 171 to D1.3's fix list.
  Also note the count moves to 22 when K8 lands `versions` as a tool
  (spec 171 line 628) — see R5-A.
- **M1.4 · nit.** "a row over 12 MiB is refused with zero bytes
  fetched" — spec 171 and ADR 085 pin 11 name the code: `-32603`,
  decided by a `stat` first. Say "refused `-32603` after one `stat`
  and zero body bytes bound".
- **M1.6 · nit.** "`idempotentHint` … derived from `ops.py` and K5's
  replay table" — spec 171 line 618 names `IDEMPOTENT_OPS`; name it.

### M2

- **M2.2 · should-fix.** "Starting against an open mount exits non-zero
  naming it unless `--allow-open`; `--as system` exits non-zero before
  binding" — the style rule is "exit codes named". *Rewrite:* "exits
  78 (`EX_CONFIG`) naming every open mount; `--as system` exits 64
  (`EX_USAGE`) before binding; both print to stderr and start no
  transport (spied)".
- **M2 why · nit (scope).** "It needs a router-from-URL constructor,
  which is small" — no criterion names it; M2.1 implies it. Add
  criterion 5: "`vfs.mcp.router_from_url(url, *, embedder=None,
  workdir='/', authority=None, verifier=None) -> VirtualFileSystem` is
  the one constructor `serve`, `sh` and `reindex` share; a drift test
  pins its signature."

### M3

- **M3 · nit (dependencies).** "*Depends on.* H3, H4, M1" — H4 is in
  the same batch (a6) with no arrow in §14. Add "H4 → M3".

---

## Domain I — developer experience

### X1

- **X1.3 · should-fix.** "the facade exposes exactly `ALL_OPS` plus
  `MANAGEMENT_METHODS`" — `MANAGEMENT_METHODS` is today a constant in
  `tests/test_ops.py:37`, not `src/`; spec 167 task 11 (F3, batch a4)
  moves it to `src/`. X1 is a3. Also `Session.cli` (F3) joins
  `Session` after X1's parity test lands. *Rewrite:* "…exactly
  `ALL_OPS` plus the management allowlist (`MANAGEMENT_METHODS`,
  promoted to `ops.py` in this story); the parity test is the one
  place later verbs (`cli`, `versions`, `answer`) must pass, so it
  fails loudly when a verb joins `Session` without a sync twin."
- **X1.5 · should-fix.** "a verb after close returns the router's
  `closed` error, not a raised exception" — there is no `closed` kind;
  the router answers `vfs.unavailable.backend` with detail "the
  filesystem is closed" (`base.py:3249–3251`). *Rewrite:* "…returns
  `vfs.unavailable.backend` (detail: the filesystem is closed), never
  raises".
- **X1 why · nit.** "lands after K4/K5 so its signature test covers
  the new arguments once" — K6, K8, K9 (`entry_id`), H2 (`plan=`), K5
  (`request_key`) all add arguments later; the parity test will run
  many times. Drop the sentence; the rewrite of X1.3 covers it.

### X4

- **X4.2 · should-fix.** "`docs/reference/verbs.md`: every public verb
  with its signature; a test asserts the set equals the live public
  surface (K9's list)" — K9.4 and R5.1 already make
  `docs/reference/api.md` the page that "lists every public name,
  signature, `Result` field…" with the same import test. Two pages,
  one pin. *Rewrite:* "`docs/reference/api.md` (K9.4) is the one
  signature page; `verbs.md` is the narrative per verb and links to
  it; the import test runs against `api.md` only."

### X6

- **X6 · nit.** "The five notebooks and two scripts that import dead
  names are removed" — §12's table says "5 of 9 import dead names";
  `examples/` holds 5 notebooks and 4 scripts. Seven vs five. State
  the exact file list in the criterion.

---

## Domain J — release

### R5

- **R5-A · blocking (the freeze contradicts the `f` stories).** R5.3
  "none tagged `0.2.0+` changes a frozen name", §14 "Nothing after b1
  changes a public name", spec 166 item 4 "Beta begins when the public
  surface is frozen" — yet these `f`-gated stories add public names
  **after** b1: K7 (`traits()` atomic-unit values, storage
  `features()`), K8 (`versions`, `read(version=)`, `created_by`, a
  schema-format bump, a 22nd MCP tool), H4 (`Interrupt`, exit 75,
  `cli(request_key=)`), H5 (`grep(deadline=)`, `cancel(ticket)`), I4
  (`add_mcp(credentials=)`, `CredentialResolver`), D7 (pool kwargs on
  `DatabaseStorage`), M3 (the `requestState` wire shape). K9.4 freezes
  "every public name, signature, `Result` field, storage protocol and
  `SCHEMA_FORMAT_VERSION`". *Rewrite (pick one):* (a) R5.5's
  `versioning.md` defines the beta freeze as "no rename, no removal,
  no semantic change; **additive** arguments, verbs and protocol
  methods are allowed in a beta and listed under *Added*", and K9.4's
  import test asserts "frozen ⊆ live" not "frozen == live"; or (b)
  retag K8, H4, H5, I4, D7 to `b` and move them to a5/a6. The lean is
  (a): it matches spec 166's "a beta may only fix" only if "fix"
  includes "add", which `versioning.md` must say.
- **R5.2 · nit.** Consistent with K1.

### R6 / R7

- **R7.4 · nit (dependencies).** "The ten proposed ADRs … are each
  ratified, amended or withdrawn" — depends on K1 and H1 (same batch
  a2, no arrow). Add "after K1 and H1".
- **R6.1 · nit.** Fine; the root listing is a pinned set.

---

## §2 — the gate list vs the tags

- **blocking.** Stories tagged `b`/`f` missing from §2: **K1** (b),
  **K7** (f), **I6** (b), **D7** (f), **E5** (b). Stories in §2 that
  are tagged `a`: **F1, F2** ("167 A–E (F1–F5)") and **R1, R2, R3**
  ("R1–R7"). *Rewrite:* Kernel: "K1–K6, K8, K9 (b); K7, K8 (f)";
  Identity: "I1, I2, I3, I6 (b); I4 (f)"; Storage: "D1–D4 (b); D6, D7
  (f)"; Search: "E1–E5 (b); E6 (f)"; Shell: "F3, F4 (b); F5, F6 (f)";
  Release: "R5, R6, R7 (b); R4 (f)". Add a one-line rule under the
  table: "`a`-tagged stories ride any alpha and are not gate items."

## §14 — sequencing

- **blocking.** **K5 is in a2 and depends on K4 (a3)** ("*Depends
  on.* K2 (the `unchanged` row), K4 (the sweep arm)"). Either move
  K5's sweep arm (K5.5) into K4's batch or drop the K4 dependency by
  letting K5.5's `sweep` reclaim replay rows without the cursor (it
  can: a TTL delete needs no page key). Lean: drop the dependency and
  reword K5.5 "`sweep` deletes replay rows older than the TTL in
  chunks of `membership_budget` (rows counted); it does not page."
- **blocking.** **I3 ↔ T3 cycle** (see I3).
- **should-fix.** **K9 (a3) depends on K4 and K6 (a3)** with no arrow;
  the batch note says stories are independent unless an arrow says
  otherwise. Write "K4, K6 → K9".
- **should-fix.** **F3 lacks K2** (D33; see F3).
- **nit.** H4 → M3 (a6), K1/H1 → R7 (a2) arrows missing. R4 (f) is
  absent from b1's row (it is D6's items 2–3; say "D6/R4").
- **nit.** The critical-path line "K1 → K2/K5 → F3 → F4 → T1 → T3 →
  T4 → M1 → H3 → H4" skips I3a, which T3 needs; after the I3 split it
  reads "… → T1 → I3a → T3 → …".

## Completeness gaps worth one criterion each (should-fix unless noted)

- **K2** has no anonymous-caller case: under an `add` posture
  anonymous may append and never alter (ADR 080 pin 12). Add "under
  `posture(p, 'add')`, anonymous `write(append=True)` succeeds and
  `write(if_version=)` of an existing row is `unauthenticated`".
- **K4** has no anonymous case either: "anonymous `ls(limit=)` under a
  `list` posture pages the same key; under `none` it is
  `unauthenticated` at the first page".
- **K6** has no 10k pin: "a 10,000-path `read(ranges=)` — or the
  batch form the spec chooses — binds at most `10,000 × length` body
  bytes and issues `ceil(10000 / membership_budget)` statements".
- **H2** has no engine-leg parametrization on criterion 3 (the
  conflict apply); add "on SQLite and on each engine leg".
- **I1** has no wire round-trip: "an `Authority` minted by
  `authority_from_token` survives `to_payload`/`from_payload` of a
  `Result` it produced with `provenance == 'edge'` intact and never
  serialises the token".
- **E3** has no `serve()` consumer pin beyond M2.1; fine (nit).
- **T3** has no 10k pin: "a tool directory of 10,000 registered
  functions lists in `ceil(10000 / membership_budget)` `rungs_at`
  statements and `ls /.vfs/tools | head -1` closes after one chunk".
- **M1** has no anonymous case: "HTTP with no token and a `read`
  posture serves `tools/list` and `ls` as `Authority.anonymous()`;
  `write` is `unauthenticated` with zero mutation statements".
- **X2.3** names the router-level 10k pin — good; D4 should cite it so
  the two 10k families do not diverge (nit).
