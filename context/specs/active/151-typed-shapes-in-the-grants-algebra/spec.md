# 151 — Typed shapes in the grants algebra: brand the ordered kinds, name the rest

- **Status:** **built 2026-10-03, awaiting Clay's review; `scripts/ci.sh`
  not run.** Drafted the same day from a three-perspective review Clay
  asked for (typing, maintainer, domain); Clay: "create a spec for
  these typing changes and then implement it". Landed as one slice:
  `grants.py` plus its four consumers and six test modules; ruff,
  format and `ty` at zero; the targeted tests green; the full suite
  and docs run recorded under *Implementation progress*.
- **Date:** 2026-10-03
- **Owner:** Clay Gendron
- **Kind:** refactor (types and names only; no behaviour, no schema,
  no statement shape changes)
- **Depends on:** 150 as built (the algebra it types), ADR 072 and
  ADR 073 (the vocabulary it adopts)
- **Decisions it implements:** none new. ADR 073 rule 4 (every range
  operation is one pass over sorted input) is the invariant the brands
  make visible to the type checker.
- **Research it stands on:** the three reviewer reports of 2026-10-03
  (scratch, not retained): the typing specialist's `ty` prototypes
  (brands over tuples enforce at every call site; a tuple subclass is
  2.7× slower in `bisect`; `ty` cannot pass a branded tuple to
  `bisect_left`), the maintainer's construction-site count (about 20
  mint sites in `src/`, 36 raw-tuple arguments in tests, none in the
  oracle), the domain critic's vocabulary table (ADR 072's "covering",
  the spec's "widens / narrows", no record uses the word `star`).

## Intent

`storage/grants.py` is a function algebra over sorted tuples. Two of
its kinds carry a precondition that only the docstrings state: a
*range set* is sorted, disjoint and not touching, and a *covering* is
minimised and in tree order. `meet` says "both are minimised and in
tree order, so one merge decides" and types its parameters
`Sequence[str]`, so an unminimised list gives a silently wrong meet
and the checker says nothing. Three other kinds have no name at all:
the posture map (`Mapping[str, GrantLevel]`, spelled nine times across
four modules and built by hand in four places), the group closures,
and the pair `inflight_regions` returns, whose destructuring inside
`resolve` shadows the module function `covers`.

This spec gives the ordered kinds a brand the checker enforces, gives
the unordered kinds a name, and renames the one insider's word. It
changes no behaviour and adds no runtime cost on the per-row path.

## Decided semantics

### 1. Two brands, minted only where the invariant is established

- `RangeSet = NewType("RangeSet", tuple[Span, ...])`: the normal form.
  Minted by `normalise`, `cover`, `union`, `subtract`, `intersect`,
  `above`, `through`, and the constants `FULL` and `NO_SPANS`. Every
  combiner takes the brand. A raw tuple, `()`, a slice, a concatenation
  or a comprehension passed where a `RangeSet` is asked is a type error.
- `Covering = NewType("Covering", tuple[str, ...])`: a minimised,
  tree-ordered prefix set — the subtree roots one holder is granted, no
  root beneath another (ADR 072: "a caller's covering prefixes never
  overlap"; `resolve` already names its local `covering`). Minted by
  `minimise`, `meet`, `meet_all`, `_uncovered`, `_roots`, and the
  constant `NO_PREFIXES`. `meet`, `meet_all`, `_uncovered` and
  `_meet_all_but_each` take the brand.
- **Readers that bisect take the base type.** `ty` cannot pass a
  branded tuple to `bisect_left` (its `SupportsLenAndGetItem` protocol
  does not see through the brand), so `contains` and `_contains_span`
  are declared on `tuple[Span, ...]`. A brand is assignable to its base,
  so every caller still passes. No `cast` on the per-row path.
- **Not branded:** `OwnerArm.prefixes` and `Rights.roots`. Neither
  feeds `meet`; both are consumed only by `cover_all`, which takes any
  iterable of prefixes. Branding them would force wraps for no check.
- **A brand records who minted the value; it validates nothing.** A
  wrong-order tuple wrapped by hand still passes. That is the house
  rule (`assert` narrows, never validates) applied to types; the
  random-world parity test stays the referee of the algebra.

### 2. Names for the unordered kinds

- `Bound = str`: a span edge. May hold the sentinel, a trailing `/` or
  `0`; never a `Path`. `Span = tuple[Bound, Bound]`.
- `Open = tuple[Bound, Bound]`: an open range as `Pieces` carries it —
  exclusive at both ends, never holding a sentinel. The same pair shape
  as `Span` and a different thing; the alias says which one a signature
  means (`Pieces.opens`, `range_counts`, the relabel batches).
- `PostureRows = Mapping[str, GrantLevel]`: each posture row's prefix
  and level. The parameter is named `postures` everywhere it was
  `star`. One constructor, `postures_of(rows)`, replaces the four
  hand-written comprehensions (`resolve`, the admin verbs' posture
  read, two tests).
- `GroupClosures = Mapping[str, frozenset[str]]`: each subject's groups,
  nesting flattened (ADR 071 rule 3).
- `Rank = NewType("Rank", int)`: a level's position on the ladder, the
  value stored in `entries.everyone_level`. `LEVEL_RANK` is
  `dict[GrantLevel, Rank]`, so a bad key is a type error. `Rights.need`
  and the `need` parameters of `inflight_regions` and `visible_entries`
  take `Rank`; `admits(everyone_level: int, ...)` keeps `int`, because
  that is the column as read. No parameter is renamed in this spec.
- `Inflight(widened: RangeSet, narrowed: RangeSet)` is what
  `inflight_regions` returns: what the unsettled posture rows add at
  this level and what they withhold (spec 150 §4: "an arm if it widens,
  a hole if it narrows"). It replaces the bare pair and the local
  `covers` that shadowed the function.

### 3. What does not change

- `Path` stays out of the algebra. Bounds are not paths, and the
  consumers already pass `str(path)` at the seam.
- No value classes. A `tuple` subclass measured 2.7× slower in
  `bisect`, which `admits` runs per row; a wrapper class breaks the
  `for lo, hi in spans` idiom at about a hundred sites.
- `Span`, `cover`, `above`, `through`, `end`: the key-range library
  keeps structural names. `OwnerArm`, `Pieces`, `Ranges`, `holes`,
  `roots`: ADR vocabulary, kept.
- The oracle under `tests/support/oracles/` imports two names and is
  untouched.

## Non-goals

- Renaming `need`, `rank`, `label` and `everyone_level` to one word
  across the backend modules. The type is unified here; the parameter
  names are left for the next edit of each signature.
- Making `GrantRow.path_prefix` a `Path` (an open question for the
  owner, recorded below).
- Any change to statements, binds, the cache key or the relabel.

## Acceptance criteria

- `ruff check`, `ruff format --check` and `ty` at zero across `src/`
  and `tests/`.
- The brand is enforced by `ty` at every call site in `src/` and
  `tests/`: a raw tuple passed to `meet` or `union` is an
  `invalid-argument-type` error. There is no negative fixture in the
  tree (one would fail the checker the tree must keep at zero); the
  evidence is the typing review's prototype and the fact that the
  mechanical test edits below were each forced by the checker.
- No behaviour change: the full suite and the random-world parity test
  pass unchanged; `tests/storage/test_grants.py` fixtures build their
  inputs through `normalise` and `minimise`, not by wrapping literals.
- 100% coverage holds; the new constructor `postures_of` is covered by
  the resolver tests.
- Docs that name these shapes (`docs/`, the module docstring) use the
  new names.

## Slices

| Slice | Content | Lands green? |
|---|---|---|
| A | the brands, the aliases, `Rank`, `Inflight`, `postures_of`, the `star` rename, in `grants.py` and its four consumers; tests moved to the constructors | yes |

One slice; the change is about 120 lines over eight files.

## Open questions

- Should `GrantRow.path_prefix` be a `Path`, making `resolve` the one
  place `Path` enters the algebra? Raised by the domain review; not
  decided here.
- The ladder is stored twice, as a string on `grants.level` and an
  integer on `entries.everyone_level`. `Rank` names the second; whether
  the first should become the integer is a schema question, not a
  naming one.

## Implementation progress (2026-10-03)

Landed as one slice on top of the uncommitted `vfs_*` table-name
change, all in the same working tree.

- `src/vfs/storage/grants.py`: `Rank`, `Bound`, `Span`, `RangeSet`
  (brand), `Open`, `Covering` (brand), `PostureRows`, `GroupClosures`;
  the constants `NO_SPANS`, `FULL`, `NO_PREFIXES`, `ROOT_COVERING`;
  `postures_of`; `Inflight`; every minting function wraps its result;
  `contains`, `_contains_span`, `end` and `pieces` are declared on the
  base tuple; `_up_to` holds the one-span cut `above` and `through`
  share; `star` is `postures` throughout, and `resolve` no longer
  shadows `covers`. `ROOT` is imported from `vfs.paths` (an earlier
  fix the same day) rather than redeclared.
- Consumers: `labels.py` (the four `_Batch` mints wrap, `covered`
  starts at `NO_SPANS`, `Open` on the count maps and the relabel
  statement), `rights.py` (`PostureRows` on the gate's decide,
  `postures_of` for the `grants` listing's posture read), `ranges.py`
  (`Rank` on `visible_entries`, `Open` on `range_counts` and
  `open_rows`), `topology.py` (`PostureRows` on the three transfer
  signatures).
- Tests: `test_grants.py` builds every `meet` and `meet_all` input
  with `minimise`, every raw span set with `normalise`, every empty
  set as `NO_SPANS`, and asserts `inflight_regions` against `Inflight`
  values with ranks from `LEVEL_RANK`; `test_labels.py` and
  `test_ranges.py` likewise. The oracle and the contract mixin are
  untouched.
- Gates: `ruff check`, `ruff format --check`, `ty` at zero across
  `src` and `tests`. Full suite: 3711 passed, 1312 skipped, 100%
  coverage (10,185 statements). `pytest docs`: 23 passed. The four
  engine legs were not rerun for this slice: it changes no statement
  and no bind, and the table-name change beneath it ran them the same
  day. `scripts/ci.sh` not run (Clay, 2026-09-28).
