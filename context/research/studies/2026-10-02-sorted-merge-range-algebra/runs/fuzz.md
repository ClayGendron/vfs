# Fuzz run

- cases: 100,000 (seed 20261002), probes: 1,389,026, 137 s
- segments: ('a', 'b', '0', '00', 'a0', 'a-', 'a.', 'b!', 'a a', '~', 'é', '日本', '-', '.', '!', 'a-b', 'z0', 'A', '~a')
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

## First example per broken invariant

none
