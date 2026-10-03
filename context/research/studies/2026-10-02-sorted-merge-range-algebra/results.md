# Results: the sorted-merge range algebra

Date: 2026-10-02. Pure Python, no database. Details and rerun commands
in `README.md`; raw outputs in `runs/`.

## The question

Can every operation in `grants.py` (`_subtract`, `meet`, the owner-floor
trim, `_everyone_arms`, `_already`, `_split`) become a linear pass over
sorted range sets, with the same `Rights.admits` answers, and with the
sibling NUL-bound bug gone?

## The answer

Yes. `algebra.py` does it, and three harnesses hold it against the
shipped code and the pointwise oracle.

**Parity** (`runs/parity.md`): 2,000 worlds from the suite's generator
plus 2,000 from a sibling generator, every subject set, both levels,
every probe path, every owner variant: 3,762,840 three-way `admits`
checks, 0 disagreements. The pieces are byte-identical to the shipped
pieces in 39,814 of 40,050 cases; the other 236 are the cases where the
shipped pieces carry a NUL bound, and in all 236 the new pieces have no
NUL and admit the same paths pointwise. No world from the suite's own
generator produced a NUL bound; the sibling generator produced 236.

**Fuzz** (`runs/fuzz.md`): 100,000 worlds over segments that sort
around `/` (`0`, `-`, `.`, `!`, space, `~`, `é`, `日本`), with derived
siblings `p0`, `p-x`, `p/x`, nested holes, hole-equals-grant, holes on
the root, many members, empty groups. Twelve invariants, 0 breaks. The
shipped pieces carried a NUL bound in 6,295 of the cases. `mutants.py`
confirms the invariants catch three deliberate breaks.

**Timing** (`runs/timing.md`), shipped total vs new total:

| shape | 1k | 10k | 100k |
|---|---|---|---|
| holes: open root, H private homes | 98 ms vs 3 ms | 16.3 s vs 37 ms | skipped (~1,600 s projected) vs 287 ms |
| postures: H shared homes each with a private sub | 216 ms vs 4 ms | 21.6 s vs 47 ms | skipped (~2,200 s) vs 619 ms |
| grants: G to one group, 1 member | 3 ms vs 2 ms | 31 ms vs 20 ms | 366 ms vs 282 ms |
| grants: G to one group, 2 members | 301 ms vs 5 ms | 26.0 s vs 57 ms | skipped (~2,600 s) vs 719 ms |
| grants: G to one group, 5 members | 3.4 s vs 16 ms | skipped (~340 s) vs 171 ms | skipped (~34,000 s) vs 1.9 s |
| grants: 2 members, u1 `/p/i`, u2 `/p/i/sub` | 264 ms vs 6 ms | 26.2 s vs 64 ms | skipped (~2,600 s) vs 798 ms |

The new path is linear after one sort everywhere; the shipped path is
quadratic in holes, in posture rows, and in grants once two members
meet.

## The sibling fix

Grants on `/v1` and `/v10`: the subtree span of `/v1` ends at `/v10`,
exactly where the point span of `/v10` begins, so merging gives
`[/v1/, /v10\x00)`. The shipped `_split` ships `/v10\x00` as a bound.
The fix: a span whose upper bound ends in the sentinel runs through the
path before it, so it becomes the open range up to that path plus the
exact point. `/v1` + `/v10` → `points=('/v1', '/v10')`,
`opens=(('/v1/', '/v10'), ('/v10/', '/v100'))`. Every bound the algebra
emits is `/`, `0`, `p`, `p/` or `p0` for an input prefix `p`, so no
bound can end in NUL or any control byte. Numbered siblings
(`/home/u1`, `/home/u10`) hit this on every layout the review called
canonical: 99 pairs per 1,000 homes.

## Subtleties the ADR or spec should state

1. An empty subject set resolves to the whole mount (`meet_all([])` is
   the root); the oracle cannot answer for it.
2. `whole` and `covers_subtree` are syntactic in the shipped code (one
   arm, no holes); the range form answers them semantically. Both are
   sound; the semantic one takes the fast path more often (584 and 550
   extra cases in 4,000 worlds).
3. Duplicate `(principal, prefix)` rows are undefined input: the oracle
   takes the first, the resolver the last.
4. The owner floor is not trimmed by the everyone region; it could be.
5. The sentinel can appear as an upper bound after a merge, so the
   split rule must cover both edges. The two-piece rule and the
   sentinel discipline belong in one sentence.

## What would change in `grants.py`

A function-by-function list is in `README.md`. In one line: keep the
public names, replace each pairwise loop with a tree-ordered or
byte-ordered merge, give `Rights` a range set per arm set instead of
`Arm(prefix, holes)`, and add the upper-bound rule to `_split`.
