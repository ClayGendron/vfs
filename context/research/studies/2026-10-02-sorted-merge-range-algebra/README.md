# Study: every grant operation as a linear sorted merge over range sets

`src/vfs/storage/grants.py` turns a caller's grants into sorted, disjoint
path pieces (ADR 072) and combines rights across members. The 2026-10-01
review found three quadratic operations in it (findings 6 and 7:
`_subtract`, `meet`, `_everyone_arms`/`_already`) and one correctness
bug (finding 2: sibling grants `/v1` + `/v10` ship a bound ending in
NUL, which Postgres rejects). This study asks one question: can every
operation become a linear pass over sorted input, give the same
answers, and lose the sibling bug? The answer is yes, and it is
measured.

Nothing in `src/` or `tests/` was changed. The study imports the shipped
code and the test oracle only to hold the candidate against them.

## What is here

| file | what it does |
|---|---|
| `algebra.py` | The candidate. Range sets as sorted tuples of half-open spans `[lo, hi)` over path strings, with `\x00` as the internal sentinel (`[p, p\x00)` is exactly the path `p`). `normalise`, `union`, `union_many`, `intersect`, `subtract`, `contains`, `subtree_contained`: each one linear pass over sorted input. `split_to_pieces`: spans to exact points and open ranges, with the sibling fix. Prefix sets in *tree order* (`tree_key`), with linear `minimise`, `meet`, `meet_all_but_each`, `uncovered`. `everyone_region`: the deepest-posture-wins region by a stack walk. `resolve_rights`: the shipped resolver's answer on these primitives; `RangeRights.admits` is the pointwise decision. |
| `parity.py` | Three-way parity on the suite's own generator and a sibling generator: the pointwise oracle, the shipped `Rights.admits`, the new `admits`; plus pieces equality and well-formedness. Writes `runs/parity.md`. |
| `fuzz.py` | Random worlds over hostile alphabets; twelve named invariants; writes `runs/fuzz.md`. |
| `mutants.py` | Three in-memory breaks of `algebra.py`; shows which fuzz invariants catch each. |
| `timing.py` | Shipped vs new at 1k, 10k, 100k holes, postures and grants with 1, 2 and 5 members. Writes `runs/timing.md`. |
| `runs/` | The run outputs this README's tables are copied from. |
| `results.md` | The short answer. |

## Rerun

From the repo root (about 4 minutes in all):

    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/parity.py --worlds 2000
    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/fuzz.py --cases 100000
    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/timing.py
    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/mutants.py

## The semantics, restated

These are the rules the candidate reproduces. They are the shipped
rules; the study only re-expresses them.

- A grant row says *principal holds level at and below prefix*. Rows
  only widen. A subject's level on a path is the max over every row
  that covers it: its own, its groups', and the everyone rows.
- Everyone rows (`*`) carry postures. The *deepest* everyone row
  covering a path decides what everyone holds there. A lower posture
  row beneath a higher one is a hole; a higher one beneath a lower one
  re-opens.
- A subject set holds a right where *every* member does: the meet
  (pointwise min) across members. Explicit grants are met per member
  first, never over a pooled bag of groups.
- The owner floor: a member's own rows pass where the *other* members
  can see, even where the member itself has no grant.
- The root is the exact path `/` plus the open range `('/', '0')`. A
  prefix `p` is the point `p` plus the open range `(p/, p0)`: two
  pieces, because `/a-b` sorts between `/a` and `/a/`.
- No bound ever ends in a low byte. `\x00` is an internal sentinel only.

So, pointwise: a row at `path` owned by `owner` passes for members M iff
`E(path)` or every member in `M \ {owner}` holds a grant covering
`path`, where `E` is the everyone region.

## The sibling fix, in plain words

Two grants on `/v1` and `/v10` give the spans `[/v1, /v1\x00)`,
`[/v1/, /v10)` and `[/v10, /v10\x00)`, `[/v10/, /v100)`. The middle two
touch: the subtree of `/v1` ends exactly where the point `/v10` begins,
because `0` is the byte after `/`. Merging them is right — the set is
one unbroken run — but it produces the span `[/v1/, /v10\x00)`. The
shipped `_split` only recognises a NUL-ended span when it is a single
point (`hi == lo + \x00`), so it ships `/v10\x00` as an open upper
bound. Postgres refuses a text bind holding NUL. Every other engine
accepted it, which is why it was invisible on SQLite.

The fix is one rule in `split_to_pieces`: a span whose upper bound ends
in the sentinel runs *through* the path just before it, inclusive. So
`[lo, p\x00)` becomes the open range `(lo, p)` plus the exact point
`p`. The pieces for the pair become `points=('/v1', '/v10')`,
`opens=(('/v1/', '/v10'), ('/v10/', '/v100'))`. The lower-bound half of
this rule is already in the shipped `_split` (a hole's upper edge
`p\x00` becomes the exclusive lower bound `p`); the upper-bound half was
missing.

This is not a rare shape. Any numbered siblings (`/home/u1` and
`/home/u10`, `/proj1` and `/proj10`, `/2024` and `/20240`) trigger it,
and the timing run's own `/home/uN` layout hit it 99 times per 1,000
names. The suite's random worlds never generate such a pair, which is
why the 400-world parity test did not see it; `parity.py` adds a
generator that does.

### Why no emitted bound can end in NUL or a control byte

Every span bound the resolver produces is one of: `/`, `0`, `p`,
`p + "\x00"`, `p + "/"`, `p + "0"`, for an input prefix `p`
(`cover` emits only these; `union`, `intersect` and `subtract` only
ever reuse existing bounds). `split_to_pieces` strips every `\x00`
suffix, so each emitted bound is `/`, `0`, `p`, `p/` or `p0`. Its last
byte is therefore `/` (0x2F), `0` (0x30), or the last byte of a lawful
prefix. Path validation refuses NUL and every control byte (0x01–0x1F,
0x7F, 0x80–0x9F), and normalisation strips trailing spaces, so a
prefix's last byte is at least 0x21. The fuzz checks this membership
on every case (invariant I11 for spans, I2 for pieces).

Note the honest form of the claim: a bound may end in a byte *below*
`/` when the grant prefix itself does (`/a-`, `/a.`, `/a!`). That is
the prefix's own name, not a sentinel, and SQL Server compares it
correctly. The hazard ADR 072 names is a path *plus* an appended low
byte, and that never happens.

## Parity

`runs/parity.md`. 2,000 worlds from the suite's generator (seed 58)
and 2,000 from the sibling generator, each × 5 subject sets × 2 levels
× every probe path × every owner variant (`None`, `u1`, `u2`, `u3`).

| check | result |
|---|---|
| admits: oracle = shipped = new | 3,762,840 checks, 0 disagreements |
| pieces: new identical to shipped wherever shipped is well-formed | 39,814 of 40,050 identical |
| pieces: shipped carries a NUL bound | 236 (all from the sibling generator and the two hand-made sibling pairs; 0 from the suite's generator) |
| pieces: in those 236, new has no NUL and admits the same paths pointwise | yes, all 236 listed in the run file |
| owner pieces: same owners, same paths pointwise | yes |
| `covers_subtree`: shipped True ⇒ new True | always; the reverse fails 550 times (see subtleties) |
| `whole`: shipped True ⇒ new True | always; new True while shipped False 584 times (see subtleties) |

## Fuzz

`runs/fuzz.md`. 100,000 random worlds. Segments drawn from
`('a', 'b', '0', '00', 'a0', 'a-', 'a.', 'b!', 'a a', '~', 'é', '日本',
'-', '.', '!', 'a-b', 'z0', 'A', '~a')`, depth 1–3, plus derived
siblings `p0`, `p-x`, `p/x`, `p00`, `p/x/y`, `p.`, `p!`, `p x`, `p~`;
posture rows on random prefixes and the root; a hole equal to a named
grant; grants from several members; groups with no rows; nested
postures. Probes include each prefix, `p0`, `p/x`, `p-x`, `p00`,
`p/x/y`, `p!`, the parent, `/`, `/0`, `/-`, `/zzz`.

- cases: 100,000 (seed 20261002), probes: 1,389,026, 137 s
- shipped pieces carrying a NUL bound (the sibling bug), arm or owner pieces: 6,295

| invariant | breaks |
|---|---|
| I1 admits: oracle == shipped == new (every probe, every owner) | 0 |
| I2 new pieces well-formed: sorted, disjoint, no NUL, no bound ending below space, every bound in {p, p/, p0, /, 0} | 0 |
| I3 new pieces == new range set pointwise; owner pieces == owner range set pointwise | 0 |
| I4 shipped pieces == new pieces pointwise (arms and owners) | 0 |
| I5 new pieces identical to shipped pieces whenever the shipped pieces are well-formed | 0 |
| I6 whole is True exactly when the arm range set is the whole mount | 0 |
| I7 range-set laws: union/intersect/subtract pointwise; (A-B) and B disjoint; (A-B) | (A&B) == A; normalise idempotent; union == union_many == normalise(A+B) | 0 |
| I8 cover_all(meet(a, b)) == intersect(cover_all(a), cover_all(b)); meet == shipped meet as a set; minimise == shipped minimise as a set | 0 |
| I9 everyone_region == oracle everyone_rank pointwise | 0 |
| I10 covers_subtree(p) implies every probe under p is covered; shipped covers_subtree implies new | 0 |
| I11 the new resolver never emits a span bound outside the input prefixes' closure {p, p+NUL, p/, p0, /, 0} | 0 |
| I12 an empty subject set resolves to the whole mount in both resolvers (shipped vs new only; the oracle cannot answer) | 0 |

`mutants.py` shows the invariants bite: removing the sibling fix is
caught by I2 (NUL in a bound); an off-by-one in `subtract` is caught by
I1, I4, I5, I9 and I11; a one-directional `meet` by I1, I4, I5 and I10.

## Timing

`runs/timing.md`. One process, pure Python, M-series laptop. "resolve"
is the resolver; "pieces" is `Rights.ranges()` (shipped) or
`RangeRights.pieces()` (new). A shipped run is skipped when the previous
size projects it past 60 s.

### holes (open root, H private homes), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 1 ms | 97 ms | 98 ms | 3 ms | 0 ms | 3 ms | 2,804 / 2,804 |
| 10,000 | 13 ms | 16.3 s | 16.3 s | 34 ms | 3 ms | 37 ms | 28,004 / 28,004 |
| 100,000 | skipped: projected ~1632 s | | | 253 ms | 34 ms | 287 ms | – / 280,004 |

### postures (private root, H shared homes each with a private sub), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 214 ms | 3 ms | 216 ms | 4 ms | 1 ms | 4 ms | 4,901 / 5,000 |
| 10,000 | 21.6 s | 27 ms | 21.6 s | 41 ms | 6 ms | 47 ms | 49,001 / 50,000 |
| 100,000 | skipped: projected ~2161 s | | | 554 ms | 65 ms | 619 ms | – / 500,000 |

### grants (G grants to one group), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 2 ms | 1 ms | 3 ms | 2 ms | 0 ms | 2 ms | 1,901 / 2,000 |
| 10,000 | 20 ms | 11 ms | 31 ms | 17 ms | 2 ms | 20 ms | 19,001 / 20,000 |
| 100,000 | 252 ms | 114 ms | 366 ms | 255 ms | 27 ms | 282 ms | 190,001 / 200,000 |

### grants (G grants to one group), 2 members

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 300 ms | 1 ms | 301 ms | 5 ms | 0 ms | 5 ms | 1,901 / 2,000 |
| 10,000 | 26.0 s | 11 ms | 26.0 s | 55 ms | 2 ms | 57 ms | 19,001 / 20,000 |
| 100,000 | skipped: projected ~2600 s | | | 692 ms | 27 ms | 719 ms | – / 200,000 |

### grants (G grants to one group), 5 members

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 3.4 s | 1 ms | 3.4 s | 16 ms | 0 ms | 16 ms | 1,901 / 2,000 |
| 10,000 | skipped: projected ~340 s | | | 169 ms | 2 ms | 171 ms | – / 20,000 |
| 100,000 | skipped: projected ~34011 s | | | 1.9 s | 27 ms | 1.9 s | – / 200,000 |

### grants, 2 members with different prefixes (u1: /p/i, u2: /p/i/sub) — the meet keeps the deeper one

| n | shipped total | new total | pieces (shipped / new) |
|---|---|---|---|
| 1,000 | 264 ms | 6 ms | 2,000 / 2,000 |
| 10,000 | 26.2 s | 64 ms | 20,000 / 20,000 |
| 100,000 | skipped: projected ~2616 s | 798 ms | – / 200,000 |

Reading the table: the shipped `pieces` is O(H²) in holes (97 ms → 16 s
for 10×); the shipped resolver is O(H²) in posture rows and O(G²) in
grants once there are two members. The new path is linear after the
sort everywhere; at 100,000 holes or grants it costs 0.3–0.6 s, most of
it building the Python tuples. A single-member authority with no
holes was already linear in the shipped code and stays so.

## What would change in `grants.py`

Described, not patched. Each line is a replacement for one shipped
function; the public names and the `Rights.admits` contract stay.

- `minimise(prefixes)`: sort by `tree_key` (split on `/`), keep a
  prefix when the last kept does not cover it. One pass; today it is a
  set lookup per ancestor per prefix.
- `meet(left, right)`: a two-pointer merge over two tree-ordered
  minimised lists: when one covers the other emit the deeper and
  advance it, else advance the earlier. Today a cross product.
- `meet_all(sets)` unchanged in shape; add `meet_all_but_each` (prefix
  and suffix meets) so the owner floor costs M meets instead of M².
- The `trimmed` comprehension in `resolve`: `uncovered(rest, shared)`,
  a two-pointer walk; today G×G.
- `_everyone_arms` + `_already`: replaced by `everyone_region(star,
  need)`: tree-order the posture rows, find each row's nearest posture
  parent with a stack, and give each qualifying row its own region
  (`cover(p)` minus its posture children's covers). Union the regions.
  Today each qualifying row scans every posture row, and `_already`
  scans every earlier arm.
- `_merged`: unchanged (it is `normalise`). `_subtract`: the two-pointer
  `subtract`, one pass instead of one rebuild per hole.
- `_split`: add the upper-bound rule (the sibling fix).
- `pieces(arms)`: becomes `split_to_pieces(range_set)`.
- `Rights` would hold a range set for the arms and one per owner, not
  `Arm(prefix, holes)` tuples. `covers` becomes a bisect
  (`contains`), `covers_subtree` becomes `subtree_contained`, `admits`
  is unchanged in shape. `whole` becomes `arms == (("/", "0"),)`.
- Consumers to re-point: `rights.py:_units` builds the Oracle/unknown
  dialect and vector-leg fan from `Arm.prefix`/`Arm.holes`; it would
  build it from the pieces instead (which also splits a many-holed arm
  into bounded clauses — review finding 4). `rights.py:_existing_roots`
  uses `Rights.roots()`; the root of each span run is its lower bound
  (`lo`, or `lo[:-1]` for a sentinel-ended `lo`) — the same prefixes,
  available in one pass. `OwnerArm.prefixes` is consumed by
  `_owned_beneath` and `_units`; keep the trimmed prefix list beside the
  owner range set (`RangeRights.owner_prefixes` does).
- Tests: the suite's `_assert_well_formed` should also assert
  `"\x00" not in bound` and that every bound is in `{p, p/, p0, /, 0}`;
  the world generator should hold `p`/`p0` sibling names.

## Semantic subtleties found

These are statements the ADR or spec should make, because the shipped
code and the candidate both rely on them and nothing writes them down.

1. **The empty subject set resolves to the whole mount.** `meet_all([])`
   is `(ROOT,)`, so `resolve({}, rows, level)` returns
   `Rights.everything`. The oracle cannot answer for an empty set
   (`min` of nothing). Both resolvers agree (fuzz I12). If an empty
   authority can reach the resolver, the spec should say it sees
   everything, or the resolver should refuse it.
2. **`whole` is syntactic today.** The shipped flag is "one arm is the
   root with no holes". An open root with a private `/a` plus a grant
   on `/a` admits every row, but `whole` is False and the backend takes
   the predicate path. The candidate's `whole` is semantic (the range
   set is the whole mount). Parity found 584 such triples in 4,000
   worlds. Both are correct; the semantic one takes the fast path more
   often. The spec should say which `whole` means.
3. **`covers_subtree` is syntactic today, too.** It asks whether one arm
   covers the path with no hole inside; it says False when two arms
   jointly cover the subtree. The candidate answers the semantic
   question. Sound in both; the semantic one is more complete (550
   cases in 4,000 worlds).
4. **A duplicate `(principal, prefix)` row is undefined.** The oracle
   takes the first row, the shipped resolver takes the last (dict
   comprehension). The store's unique key prevents it; the pure
   resolver's contract should say the input is keyed.
5. **The owner floor is not trimmed by the everyone region.** A
   single-member authority's owner arm is `(ROOT,)` even under an open
   root with holes. Harmless for `admits` (arms are checked first), but
   the owner branch in SQL does more work than it needs to. The
   candidate keeps the shipped behaviour for parity; subtracting the
   everyone region from the owner set is a free improvement.
6. **Sibling names are an ordinary layout, not a trap.** `/home/u1` and
   `/home/u10` arise from any numbered naming. The two-piece rule and
   the sentinel discipline must be stated together: a sentinel may
   appear as an *upper* bound after a merge, and the split must handle
   both edges.
