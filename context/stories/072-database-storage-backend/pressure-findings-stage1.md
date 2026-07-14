# Stage-1 pressure-test findings — implementation brief

- **Date:** 2026-07-14 (run against the uncommitted Stage-1 tree, 1,395
  tests green at the time)
- **Provenance:** 6 adversarial pressure agents (scratch scripts,
  executed repros) + 2 independent refuters per claimed finding.
  23 claims → **11 confirmed, 3 contested, 9 refuted**. Only survivors
  are recorded here.
- **How to read this:** items in §1 are defects with a clear contract to
  restore — implement directly, no product input needed. Items in §2
  carry **⚖ DECISION** markers: the defect is real (or the tension is),
  but the resolution changes a contract, so the owner must pick before
  code is written. Repro scripts lived in the session scratchpad and are
  gone; every finding below carries enough inline detail to rebuild the
  repro, and each fix should land with a pinned regression test.

---

## 1. Ready to implement (no decision needed)

> **Status 2026-07-14: all four §1 items implemented and pinned.**
> 1.1 — SUBPATTERN splices only pure-literal/empty bodies; other bodies
> break adjacency both sides (`_pure_literal_text`; the dead `terminated`
> return removed); group-shape regressions + 500-case seeded fuzz in
> `tests/test_code_grams.py`. 1.2 — `_write_entries`, `_transfer`, and
> `edit` (same defect via repeated targets) observe post-staging,
> mkdir-style; five conformance rows pin observation == post-commit stat.
> 1.3 — read refusal prose names the row's kind. 1.4 — rollup groups by
> (kind, severity, retryable) and stamps the rollup entry.

### 1.1 CRITICAL — gram planner splices group runs unsoundly

`src/vfs/models/code_grams.py`, `_collect_runs`, SUBPATTERN arm.

A capturing/named group whose body is **not** pure literal (contains
`.`, a class, alternation, backref, lookaround…) still has its inner
literal runs spliced into the caller's open buffer as if adjacent — and
a group yielding no runs leaves the buffer running across it. Only a
truly empty group or a pure-literal body is adjacency-transparent.

- Repro: `build_code_gram_query("abc(.)def").required_grams()` demands
  grams `bcd`/`cde`; content `"abcXdef"` matches `re.search` but its
  folded index lacks both → silent false negative (file dropped from
  grep candidates). Also over-claims on partial inner runs:
  `abc(d.)ghi` requires `cdg`, `dgh`.
- Root cause detail: the `terminated` soundness flag the walker's
  docstring describes is hardcoded `return runs, True` and discarded at
  the SUBPATTERN call site (`inner_runs, _ = ...`).
- Existing tests only cover `foo(bar)baz` (pure literal) and
  `abc(?:xx|yy)def` (sre inlines non-capturing alternation to a bare
  BRANCH, which flushes correctly) — add group-with-wildcard/class/
  alternation cases to `tests/test_code_grams.py`.
- Done when: the no-false-negative fuzz invariant (pattern matches
  content ⇒ required grams ⊆ `unique_code_grams(content, folded=True)`)
  holds for group-bearing patterns; a seeded fuzzer found 80/5,495
  failures in this family, so consider porting a bounded fuzz test.

### 1.2 MAJOR — batch verbs report mid-batch revisions

`src/vfs/storage/backends/memory.py`: `_write_entries` (observes
per-entry via `_put_file`) and `_transfer` (observes per-pair).

Observations are built **during** staging; a later entry/pair in the
same batch can bump the same row (parent bumps, duplicate paths), so
the returned observation carries a (revision, state) pair that never
exists in any committed state. Spec §5 pins: "a revision value is never
observable before the state it stamps." `mkdir` was already fixed for
exactly this in the same diff (observe after every stamp and bump) —
apply the same discipline to the other two batch verbs.

- Repro: a write-entries batch containing the same file path twice
  (`base.py`'s `_route_entry_batch` does not dedupe) returns
  `status=created` with a revision stamping content that was superseded
  inside the staged dict before commit. Also visible with two siblings
  (the second sibling's parent bump invalidates the first observation's
  parent-revision reading).
- Done when: every observation returned by a successful batch equals a
  post-commit `stat` of the same path (revision included). Pin as a
  conformance row.

### 1.3 MINOR — edge-row read message is factually wrong

`src/vfs/storage/backends/memory.py` read verb: any existing
non-content row refuses with `wrong_kind` and the message
`"Is a directory: {target}"`. For a directly-addressed edge projection
row the prose is false (it's an edge). Message is declared
non-load-bearing for code, but it is "the prose an agent reads."
Make the message name the actual kind. Classification itself
(wrong_kind) is unchanged.

### 1.4 MINOR — `retryable` dropped by the wire rollup

`src/vfs/results/envelope.py`, `_rolled_errors()`: rollup entries are
constructed without carrying `retryable`, so under
`to_payload(max_errors=N)` every `retryable=True` error beyond its
group head loses the transient signal. Latent (no in-tree caller passes
`max_errors` yet) but the MCP boundary is the designed consumer.
Include `retryable` in the grouping key or propagate it into the rollup
entry; pin with a test beside the existing rollup tests.

---

## 2. Decision required before implementation

### 2.1 ⚖ DECISION — Result merge × the populated mask (and revision coherence)

> **Ruled 2026-07-14 (owner-approved) and implemented: option 1 plus a
> revision rule — mask-driven fill (right fills only fields absent from
> the left mask; fetched-and-null never overwritten), masks union, and
> revision merges agree-or-null: differing revisions stamp the merged
> row's revision null (still masked), so a composite row never claims a
> single snapshot. Precedent survey (statx `stx_mask`, NFS
> `fattr->valid` + change_attr gating, SQLAlchemy loaded-state merge +
> `StaleDataError`, Oak single-read-revision rows, 9P wstat sentinels as
> the anti-pattern) was unanimous for mask-driven fill and against
> cross-revision fusion claiming one revision; the null stamp is the
> algebra-compatible analogue of NFS's invalidate-and-revalidate that
> keeps bind-path decoration working across unrelated counters. Pinned
> in `tests/test_result_laws.py::TestMaskedMerge`.**

`src/vfs/results/envelope.py`, `_merge_observation`. Two confirmed
findings, one underlying question.

**(a) The mask goes stale under merge (MAJOR).** `_merge_observation`
fills left-null fields from the right row but never updates
`populated` (a frozenset is never None, so the mask itself can never
merge). Any overlapping-path merge — `|`, `&`, `Result.merge`,
including the router's documented bind-path decoration — produces rows
whose values exceed their mask. Consequences, all demonstrated:
`projection=("all",)` and any mask-narrowing consumer silently drop
the filled data; the conformance invariant `valued <= o.populated`
(tests/storage_conformance.py) is false for algebra-produced rows.

**(b) The fill rule itself is a value null-check (QUESTION).** The fill
decision is `getattr(a, name) is None` — the exact fetched-vs-null
conflation the mask was introduced to eliminate. A left row whose mask
says "content fetched, observed null" still gets content overwritten
from the right ("left wins" fails for fetched-and-null). And with
`revision` now a mirror, field-level fill across rows observed at
different revisions fabricates unobserved states: stat@rev5 merged
with read@rev3 yields one row claiming rev-3 content at revision 5.

**The decision:** what does merge *mean* under the mask model?
Options on the table (pick one; each restores `valued ⊆ populated`):

1. **Mask-driven fill** — fill only fields absent from the left mask;
   union the masks. Fetched-and-null survives; masks stay honest.
   (Closest to the spirit of the mask contract.)
2. **Value-driven fill (status quo) + mask union** — keep the null-check
   fill, always union masks. Cheapest; accepts that fetched-and-null is
   fillable and that merged rows can pair fields observed at different
   revisions.
3. Either of the above **plus a revision rule** — e.g. never fill across
   differing revisions, or stamp the merged row's revision null when
   sources disagree. Decides finding (b)'s second half.

Whatever is chosen, document it on `__or__`/`merge` (whose docstrings
predate the mask) and pin: mask-honesty under merge, fetched-and-null
behavior, and cross-revision fill behavior.

### 2.2 ⚖ DECISION — move leaf table: no-replace vs kind, and dir-over-empty-dir

> **Ruled 2026-07-14 (owner-approved, jointly with 2.3) and
> implemented.** (i) No-replace `exists` outranks kind translation —
> Linux (`LOOKUP_EXCL` EEXIST fires at target lookup, before
> vfs_rename's kind checks exist), FreeBSD (`kern_renameat` checks
> `AT_RENAME_NOREPLACE → EEXIST` first), and JuiceFS (all three meta
> engines) are unanimous. (ii) POSIX dir-over-dir: empty target is
> replaced; non-empty classifies `not_empty` (POSIX latitude allows
> EEXIST|ENOTEMPTY per pjdfstest; FreeBSD/JuiceFS/SeaweedFS emit
> ENOTEMPTY; libsqlfs's blanket refusal is a documented `>=`-vs-`>`
> bug, not a design). The emptiness probe is an `EXISTS … LIMIT 1` on
> the children relation in-transaction — effectively free. The same
> leaf table applies to copy (shared `_transfer` block, explicit
> ruling). Pinned as conformance rows; spec §12 order updated.

`src/vfs/storage/backends/memory.py`, `_transfer` occupied-target
block (MAJOR). Two intertwined divergences from the adopted R8 matrix:

- With `overwrite=False`, an occupied destination involving a directory
  (either side) classifies `wrong_kind`; the R8 row pins **`exists`
  before** anything else for no-replace (Linux `RENAME_NOREPLACE`
  returns EEXIST before kind checks).
- With `overwrite=True`, dir-over-**empty**-dir is refused `wrong_kind`
  where POSIX rename succeeds. The matrix's only wrong_kind move row is
  dir-over-non-dir / non-dir-over-dir; dir-over-dir matches no row.

**The decision:** (i) confirm no-replace `exists` outranks kind
translation (this half is arguably just R8-conformance — but it changes
an error kind agents may already see, so confirm); (ii) pick a
dir-over-dir contract: POSIX (replace empty dir, `not_empty` otherwise)
or the current blanket refusal — the spec never pins it. Add per-verb
conformance rows for whichever is chosen.

### 2.3 ⚖ DECISION — the one-cycle-kind pin is unreachable in one direction

> **Ruled 2026-07-14 (owner-approved, jointly with 2.2) and
> implemented: option (a) — cycle detection runs before occupied-target
> classification.** This is the Linux-faithful order: the rename trap
> checks (`d1 == trap` / `d2 == trap` in `__start_renaming`) fire in
> the lookup phase, structurally before `vfs_rename`'s kind checks, so
> both cycle directions reach the one cycle kind (`invalid`) and the
> spec conflict dissolves. Full ladder now: source-missing >
> exists-under-no-replace > cycle (one kind, both directions) >
> wrong_kind > not_empty. The old occupied-before-cycle conformance pin
> flipped (`test_move_cycle_classifies_before_the_occupied_destination`)
> and the previously-unreachable direction gained its own row
> (`test_move_onto_own_ancestor_is_the_same_cycle_kind`). Spec §10/§12
> updated together with the code.

`_transfer` + spec §10/§12 (MAJOR). Spec pins "both cycle directions
collapse to one refusal kind." But target-ancestor-of-source is by
construction an existing non-empty directory, so the (also spec-pinned)
occupied-before-cycle ordering classifies it `wrong_kind`/`not_empty`
before any cycle test can run. The two directions demonstrably return
`invalid` vs `wrong_kind`, and **no ordering of the current checks
satisfies both pins simultaneously** — this is a spec-level conflict
between two rows, not a coding slip.

**The decision:** amend one pin. Either (a) cycle detection runs before
occupied-target classification for ancestor-related pairs (one cycle
kind, both directions, matching spec §10's cycle language), or (b) the
one-kind pin is narrowed to the source-ancestor direction and the spec
records that the target-ancestor direction surfaces as the occupied
-target kind (closer to Linux's ENOTEMPTY half). Update spec §10/§12
wording and the conformance row (which currently tests only one
direction) together with the code.

### 2.4 ⚖ DECISION — planner Unicode false negatives (two families)

> **Ruled 2026-07-14 (owner-approved) and implemented.** (a) Turkic-i
> pre-fold added to the one shared fold (`fold_content`): U+0131 and
> U+0130 map to `i` before `casefold` — zoekt's invariant (candidate
> fold ⊇ verifier case orbit) restored at the breaker codepoints; this
> widens candidates only, match semantics unchanged (the verify tier
> rules). **The finding under-counted: U+0130 (dotted capital I) is a
> second breaker** — sre uses Unicode *simple* lowercase (U+0130 → i)
> while casefold explodes it to i+U+0307; invisible to the original
> scan because its full lowercase is multi-codepoint. An exhaustive
> orbit scan (every codepoint × case variants × `re._casefix` table)
> now shows zero breakers and is pinned as a test. (b) NFC dropped
> from the gram pipeline entirely — the stream is newline-normalized,
> Turkic-folded, casefolded **raw** codepoints. Key insight: the
> NFD/NFC unification defended matches the raw-content `re` verifier
> cannot make (it is codepoint-exact), while creating real false
> negatives via substring instability; zoekt/codesearch index raw and
> pg_trgm never normalizes (its `trgm_regexp.c` carries the "we're
> probably screwed" XXX admitting exactly our family-(a) hazard).
> Cross-form gram tests (which pinned the vacuous guarantee) replaced
> by raw-stream regressions + seeded decomposed-content fuzz; spec §6
> updated; the Pass C fingerprint covers the fold definition.

`src/vfs/models/code_grams.py` (both MAJOR). The always-folded rewrite
fixed the confirmed NFC bug but two residual families violate the
no-false-negatives contract:

**(a) Dotless-i.** CPython's `re` IGNORECASE matches `i`/`I` ↔ `ı`
(U+0131) via `re._casefix._EXTRA_CASES`, but `str.casefold()` does not
unify them (Turkic folding is locale-scoped). `(?i)iii` genuinely
matches content `ııı`, but the plan requires gram `b'iii'` which the
folded index of `ııı` lacks; the reverse direction fails identically.
An exhaustive case-orbit scan (all codepoints, lower/upper/casefold/
title + the full `_EXTRA_CASES` table) confirms **U+0131 is the only
single-codepoint breaker** — ſ, K, µ, ς, the Greek symbol set, ẛ, ﬅ/ﬆ
all unify under NFC+casefold.

**(b) NFC composes across matched-span edges.** Index grams come from
whole-content `NFC(casefold(NFC(content)))`, but the authoritative
`re.search` runs on **raw** content, and NFC is not substring-stable.
Pure-ASCII pattern `abce` matches raw `xxabcéyy` (é = `e`+U+0301) at
(2,6), but the index composes `e`+mark → `é`, so required gram `bce`
is absent. `fixed_strings=True` has the identical hole. Casefold
expansion even mints new composition sites (`ß`+U+0301 folds to
`ss`+mark → NFC composes `ś`). ~62/5,495 seeded fuzz cases.

**The decision:** these trade index semantics against the absolute
contract, so pick a posture per family rather than patching blind:
for (a), options include folding `ı→i` in both pipelines (accepting
Turkic-insensitive grep), or excluding patterns/content containing the
orbit from indexed planning (degrade to `GramAny`). For (b), options
include verifying against normalized content instead of raw (changes
what grep *matches*), normalizing content at write ingress (a spec §9
content-fidelity question — probably a non-starter), gramming without
NFC (index raw folded bytes; costs the NFD/NFC unification the module
exists for), or emitting weakened edge grams (drop the first/last
gram of every run — strictly weaker plans, sound). Each option changes
either match semantics or index selectivity; the spec's §6 contract
("never a false negative") plus §9 (content stored verbatim) should
arbitrate. Record the choice in the spec before Pass C builds on it.

### 2.5 ⚖ DECISION — MSSQL collation variant pins non-Unicode VARCHAR

`src/vfs/models/rows.py`, `_binary_string` (MAJOR; evidence is rendered
DDL + documented SQL Server semantics — no live server was available).

`String(n)` + `Latin1_General_BIN2` renders `VARCHAR(n)` on MSSQL:
byte-counted, code-page 1252. It cannot encode lawful CJK/Cyrillic/
Greek paths (silent `?` substitution) and cannot hold a lawful
1,024-character multibyte path (up to 4,096 UTF-8 bytes per spec §8)
in 1,024 bytes. The spec's per-engine byte-budget paragraph covers
key-length overflow but not encoding loss, which corrupts silently at
any length.

**The decision:** MSSQL Unicode posture — `NVARCHAR` + a `_BIN2`
collation (UTF-16, doubles key bytes against the ~1,700-byte key cap),
vs `Latin1_General_100_BIN2_UTF8` (requires SQL Server 2019+ — a
declared platform floor), vs deferring the whole question to the MSSQL
provider story with a loud note that the portable DDL is not
MSSQL-safe today. Whichever way, spec §8's byte-budget table should
gain the encoding dimension.

> **Ruling (owner, 2026-07-14): `Latin1_General_100_BIN2_UTF8`, SQL
> Server 2019+ floor.** Precedent research (SQLAlchemy mssql dialect,
> Jackrabbit Oak `RDBDocumentStoreDB`; JuiceFS/SeaweedFS/libsqlfs ship
> no MSSQL at all): SQLAlchemy is a pure collation passthrough with
> zero UTF-8/`_BIN2` awareness; Oak — the one production precedent —
> stores its path key as `varbinary(512)` of UTF-8 bytes on SQL
> Server, an implicit rejection of NVARCHAR ordering. NVARCHAR+`_BIN2`
> is rejected: UTF-16 code-unit order diverges from UTF-8/code-point
> order on supplementary-plane characters (cross-engine pagination
> break), and 2 bytes/char busts the 1,700-byte index cap even for
> ASCII paths at the full 1,024-char budget — the UTF-8 collation
> keeps every all-ASCII path indexable. Landed in `_binary_string`
> (`rows.py`) with the DDL test updated; spec §8 records the ruling,
> the ODBC UTF-8 param-path validation the MSSQL provider story owes,
> and Oak's varbinary key as fallback.

### 2.6 ⚖ DECISION — contested batch semantics (three, from split verdicts)

Each of these reproduced cleanly but split the refuters on
"working as designed." The owner should rule; each ruling is a one-line
spec/docstring note plus (if changed) code.

1. **Order-dependent batch abort with misattributed error (MAJOR).**
   `delete(observations=[/a, /a/b/c])` stages `/a`'s cascade, then
   classifies `/a/b/c` against staged state → fails whole with
   `not_found: /a` — naming a path that exists in committed state and
   was never a failing target; the reversed order succeeds. Same for
   move. Defense: stage-and-abort + descent ladder are both pinned.
   Attack: the docstring's "reports every failing target" doesn't hold,
   and glob-feeding-delete makes this reachable in normal agent use.
   Rule: intended (document per-batch staged-visibility semantics) or
   defect (classify against committed state / dedupe subsumed targets).
2. **Value-identical errors for distinct failed rows (MINOR).** Two
   targets under one dead ancestor yield two equal `ResultError`s
   (ancestor-attributed, no per-target field), which `Result.merge`'s
   value-equality dedup collapses to one — demonstrated through the
   real router path. envelope.py itself says producers wanting
   N-occurrence semantics must add a `data` discriminator. Rule:
   accept the collapse, or stamp the requested target into
   `error.data` at the producer.
3. **Postgres identifier overflow at `table_name` length 42–44
   (MINOR).** All table names fit the 63-char cap but
   `uq_{table_name}_chunks_entry_index` / `uq_{...}_edges_src_tgt_type`
   don't → `create_all` raises on Postgres, succeeds on SQLite.
   Loud, and first-touch provisioning doesn't exist until Pass A. Rule:
   validate/bound `table_name` in `build_vfs_tables` now, shorten the
   constraint-name scheme, or explicitly defer to Pass A task 9 (where
   the mount-name→table-name mapping gets decided anyway).

> **Rulings (owner, 2026-07-14), all three implemented:**
>
> 1. **Defect.** Precedent research (minio S3 DeleteObjects, fsspec,
>    opendal, pyfilesystem2, JuiceFS): no surveyed batch API validates
>    against accumulating staged state; the hierarchical precedent
>    (fsspec `expand_path`) subsumes a descendant into its ancestor's
>    recursive expansion, order-independent. Landed: cascade delete
>    subsumes requested descendants and repeats (judged against
>    committed state — a covered-but-missing target classifies
>    `not_found` under its own name, never the cascade root); move
>    refuses duplicate sources and a source inside another moved
>    source as `invalid`, both orders (copy fan-out stays legal — copy
>    never consumes its source). Conformance rows pin both orders.
> 2. **Producer stamps the discriminator.** Per-requested-key error
>    attribution is the wild norm (minio: one `DeleteError` per key;
>    opendal: `(path, error)` per item). Landed: `_classify_miss`,
>    `_parent_gate`, and `_transfer` errors stamp the requested target
>    into `error.data["target"]`; merge dedup semantics unchanged.
> 3. **Bound the prefix.** Postgres itself would NOTICE-truncate; the
>    raise is SQLAlchemy's compile-time `IdentifierError` for plain-str
>    names (SQLite's dialect has effectively no cap — the observed
>    asymmetry). Landed: `MAX_TABLE_NAME_LENGTH = 41` (63 − 22, the
>    longest derived suffix) refused loudly in `build_vfs_tables`, with
>    a tightness test asserting the longest derived identifier is
>    exactly 63 at the bound. SQLAlchemy's naming-convention md5
>    truncation is the documented fallback if Pass A's mount-name
>    mapping ever needs longer prefixes. Spec §3 and §8 record all
>    three.

---

## 3. What held under attack (no action)

Wire round-trips of stamped masks (both `exclude_none` modes);
failed-batch revision atomicity (no revision moves on any failed batch
kind); counter independence across instances; the shared descent ladder
(missing/file ancestors classify at the failing component for every
verb probed); `allow_scan` intact through router fan-out on every input
shape; ingress typing of `allow_scan`; the traits vocabulary and
`SupportsTraits` isinstance behavior; the conformance harness's
capability gate over partial backends; DDL compile on
sqlite/postgres/mssql with collations rendering; SQLite
`AUTOINCREMENT` non-reuse on entries and chunks; the meta single-row
check constraint; posting-list/gram-epoch composite PKs.
