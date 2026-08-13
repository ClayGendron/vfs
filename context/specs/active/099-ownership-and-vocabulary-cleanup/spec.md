# 099 — Ownership and vocabulary cleanup: the review's decision pass lands

- **Status: implemented 2026-08-13, awaiting commit** — born from the
  review campaign memo's decision pass
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`,
  decisions 1–4, 6, 8, all resolved by Clay 2026-08-13) plus the two
  verified duplication/drift findings (memo 13, 14). No open forks —
  every item is decided; this spec is the work package that lands
  them.
- **Landing ledger (2026-08-13):**
  - Suite 2,276 passed at 100.00% coverage; `ruff`/`ty` zero. Four
    Docker legs not required (nothing engine-shaped moved), per the
    verification obligations.
  - §1: `passes_filters` lives in `glob.py`'s path-filtering group;
    grep imports it one-way and the package docstring's concern
    assignment is true again. The move revealed no dead code:
    `filter_paths` is the deliberate simple public form (plan 094),
    exported and pinned — kept.
  - §2: the `reads.py` glob-candidate loop routes through
    `passes_filters` (wanted rides inside the gates, so the wanted
    argument is empty by construction); the `base.py` keep closure
    stays irreducible with a comment naming its authority. Landing
    differential: 38,880 cases, 0 mismatches
    (`differential_admission_law.py`, session scratchpad — old inline
    spelling transcribed from `a577c28` vs the landed routing; the
    empty-gates divergence is unreachable in `glob_rows`, and the
    grid mirrors that precondition).
  - §3: `ext_membership(entry, wanted, membership_budget) →
    (predicate | None, binds)` lands in `reads.py` beside
    `pattern_arm`/`ARM_FIXED_BINDS`; all four sites (glob fan budget
    + arm, grep scan budget + bare-scan terms) route through it, and
    a unit row pins the stand-down cases and the pairing.
  - §4: `meta_scoped` delegates to `paths._under_meta_root`. The
    ADR 031 one-glance check found the real edge: the docstring
    claimed the "literal prefix" law while the code implements the
    stricter whole-literal-head law (`/.vfs*` has a meta-addressed
    extracted prefix yet never lifts — it also matches `/.vfsx`).
    Docstring reworded to the implemented law; ADR 031 §5 annotated
    recording the deliberate tightening.
  - §5: `normalize_ext_channel()` lands in `vfs.paths` beside
    `normalize_extension` (column law untouched); all six sites call
    it — the only remaining `lstrip(".")` in `src/` is the helper
    itself. The three formerly-unpinned consumers (batch
    `filter_candidates`, chained glob, chained grep) each gained a
    dotted/uppercase pin; hand-mutant proof: bypassing the law at
    the grep-module and router sites fails exactly the three new
    pins, and restoration re-verified. The `ext=("",)` lead was a
    real docs contradiction: `docs/reference/glob-patterns.md`
    claimed "an extensionless row is never `ext_not`'s business" —
    behavior (pinned by the storage `ext=(".",)` row) deliberately
    treats the empty member as the extensionless arm; docs aligned
    to behavior.
  - §6: `GLOB_CHANNEL_LABELS` (frozen `MappingProxyType`) with one
    label per channel — pattern → "glob pattern", globs → "grep
    glob", globs_not → "glob exclusion" — consumed by all four
    minting sites (router glob/grep, backend glob/grep loops).
    **Placement deviates from the spec's letter for a structural
    reason:** the backend minting sites are among the four, and
    `base.py` imports the backends package (memory), so
    base.py-ownership would be a real import cycle; the map lives in
    `pattern_matching/glob.py` — the language owns its channels'
    names, and every minting site already imports the layer. Pinned
    by a frozen-map unit row and a cross-verb row asserting glob and
    grep mint the identical exclusion label.
  - §7: `_byte_capped`'s `max_rows` branch and `_POSTING_ROW_BINDS`
    deleted; `build_epoch` no longer takes `parameter_budget`. The
    sqlite pin records the *actual* lean-on, spike-verified: a
    non-RETURNING posting insert executes as one `executemany` whose
    statement carries a single row's six binds — per-row parameter
    sets, never an accumulated list — so no statement grows with
    batch size (the multi-statement insertmanyvalues chunking the
    campaign observed is MSSQL/Oracle's shape of the same
    SQLAlchemy-owned law). Rides the 095 §9 battery on real engines
    when 095 lands.
  - §8: both "3.12 floor" mentions dropped the number (pyproject/ADR
    035 own the fact); `docs/index.md` and `docs/contributing.md`
    trued to Python 3.11+ (pyproject: `>=3.11`); ADR 032 §1's
    `>=3.13` consequence annotated as superseded history rather than
    edited. `STATUS.md` untouched — decision 7's territory.
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** structural cleanup — placement moves, duplication
  consolidation, vocabulary unification, doc-fact true-up, one dead
  branch deleted. No behavior changes; every item is
  refactor-shaped and pinned where drift was possible.
- **Depends on:** the decision pass (memo §Decision pass); ADR 029
  (error hygiene — decision 6's motivation); CLAUDE.md's
  lean-on-SQLAlchemy rule (decision 8) and code-smell doctrine
  (duplication as ownership evidence).
- **Relates to:** specs 095–098 (land those first where files
  overlap — this spec rebases cheaply, they don't); the 094 mining
  pass (decision 7: STATUS.md true-up rides it, explicitly *not* this
  spec).

## Intent

The review's ownership lens found no misbehavior in this class — it
found logic homed against the package's own docstrings, laws re-spelled
inline at sites that cannot be edited together, vocabulary drifting
across minting sites, and facts (the Python floor) contradicting the
decision the same commit set landed. The decision pass settled all
eight questions with prior art; this spec turns those resolutions into
one mechanical slice.

One sentence: **move the shared gates to their declared homes, give
every re-spelled law one owner and a pin, unify the refusal
vocabulary, true up the floor facts, and delete the one dead branch —
behavior byte-identical throughout, proven by the suite and the
existing differential batteries.**

## Shape

### 1. `passes_filters` moves to `glob.py` (decision 1)

The shared structural path-gate moves from `pattern_matching/grep.py`
to `pattern_matching/glob.py`; grep imports it (the dependency is
already glob ← grep one-way). The package docstring's concern
assignment becomes true again. `filter_paths` stays as the simple
public form (plan 094's deliberate choice); glob's production-dead
batch filter is deleted or wired per what the move reveals — dead
code does not survive the move.

### 2. Admission-law inline copies consolidate (decision 2)

The two behavior-identical inline re-spellings (`reads.py:238`,
`base.py:1874`) route through the named gate where the signature
fits. The per-row compile inside the keep closure is irreducible
(pattern is row-derived) — it stays, with a one-line comment naming
`passes_filters` as its authority. The campaign's 38,880-case
differential re-runs once at landing to prove byte-identical
behavior; it does not join the suite.

### 3. The ext-rideability pair gets one owner (decision 3)

The ext-membership SQL rideability condition and its bind count —
character-identical at four sites (`reads.py:234/276`,
`grep.py:369/378`) — become one paired helper in the backend's shared
vocabulary (beside the budget helpers), returning predicate and bind
count together so the four sites cannot be edited independently.

### 4. `meta_scoped` imports its path law (decision 4)

`meta_scoped` stays in the backend (one backend exists; hoisting is
speculative generality) and imports `paths._under_meta_root` for the
two byte-identical lines. While there: the one-glance check on the
ADR 031 "literal prefix" vs docstring edge the verifier noted — align
the docstring or the code, whichever is wrong.

### 5. The ext-channel law gets a named home and its pins (memo 13)

The `lstrip(".").lower()` channel law, spelled identically at six
sites in five modules with three sites unpinned: a
`normalize_ext_channel()` helper lands in `vfs.paths` beside
`normalize_extension` (which keeps its column-law scope — the
refuted half of the original finding stands), all six sites call it,
and each formerly-unpinned consumer gains one dotted/uppercase pin.
The `ext=("",)`-vs-docs extensionless lead: check it while touching
the sites; align docs or behavior, one line either way.

### 6. One channel→label map for glob-channel refusals (decision 6)

The four minting sites' drifting labels ("glob exclusion" / "grep
glob" / "glob pattern" for the same channel) unify through one frozen
channel→label mapping owned beside the refusal constructors in
`base.py`. Message shapes are otherwise untouched (every message
already quotes the offending pattern).

### 7. The posting-insert row cap is deleted (decision 8)

`_byte_capped`'s `max_rows` branch (`indexing.py:260`) is deleted:
SQLAlchemy's insertmanyvalues owns per-dialect row chunking (verified
uncapped on MSSQL — 128 statements, ≤2,094 binds — and Oracle). The
byte-budget half stays (SQLAlchemy takes no position on blob bytes).
One test pins the lean-on relied upon: a posting insert past the
parameter budget executes as multiple chunked statements on the
sqlite leg's captured SQL (and rides the 095 §9 battery on real
engines).

### 8. Floor facts true up (memo 14)

`glob.py:366` and `test_glob.py:473` say "3.12 floor"; ADR 035 set
3.11. Fix both (or drop the number and let pyproject/ADR own the
fact — preferred where the sentence survives without it). The
unverified doc leads ride along after a 30-second check each:
`docs/index.md:16`, `docs/contributing.md:15` ("Python 3.12+"),
and ADR 032:53's `>=3.13` consequence line (likely deliberate
history — annotate rather than edit if so). `STATUS.md`'s "py3.13
floor" line is decision 7's territory: it waits for the 094 mining
pass, not this spec.

## Verification obligations

- Suite green, coverage 100%, `ruff`/`ty` zero — after every slice.
- §2's differential re-run recorded in the landing message
  (zero mismatches required).
- §5's new pins fail before the helper lands (verified by reverting
  one site by hand) and pass after.
- No behavior change anywhere: the four Docker legs are **not**
  required for this spec (nothing engine-shaped moves), except §7's
  pin riding the 095 battery when that lands.

## Touch points

`src/vfs/pattern_matching/{__init__,glob,grep}.py` (§1, §2),
`src/vfs/paths.py` (§5), `src/vfs/base.py` (§2, §6),
`src/vfs/storage/backends/database/{reads,grep,indexing}.py`
(§2, §3, §7), `docs/` + the two docstrings (§8), tests beside each
touched site.

## Slices

Order after specs 095–098 where files overlap (this spec rebases
cheaply; correctness work doesn't):

- **A** — §1 + §2 (the move and the consolidation, one landing).
- **B** — §3 + §4 + §5 (owners and pins).
- **C** — §6 + §7 + §8 (vocabulary, dead branch, doc facts).

## Open questions

None — all items resolved in the 2026-08-13 decision pass; the only
in-flight judgment (§8's annotate-vs-edit on ADR 032) resolves on
inspection.
