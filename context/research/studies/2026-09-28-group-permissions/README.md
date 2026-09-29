# Study: group permissions — max within each subject, min across the set

Companion to the memo
`../../2026-09-28-group-permissions-max-within-min-across.md`.

The question (Clay, 2026-09-28): Ann is in three groups; she should see
what any of them can see. Ann and John each have their own groups; a
session acting for both should get, per path, the best level each of
them holds (the **max within** each person), and then the worst of
those two (the **min across** the pair). Is that case in scope for spec
058, and does the resolver it specifies compute it correctly and inside
every engine's budgets?

## What is here

| file | what it does |
|---|---|
| `model.py` | A pure-Python model of spec 058's resolver with groups. (1) The worked example the memo tabulates: Ann, John, their groups, eight paths, and the level each of them and the pair gets. (2) An **oracle** (per subject: the maximum of the everyone rows, its own rows, its groups' rows and the owner floor; per set: the minimum) checked against the resolver's **prefix algebra** (per subject: the covering prefix set at a level; per set: the meet; posture rows as arms with holes; per-member owner arms) on thousands of random worlds with nested groups, group cycles, posture rows and `%`/`_` in path names; the resolved arms compiled to SQL and run on stdlib SQLite, compared row for row. Four deliberately wrong variants run beside it and are counted: groups pooled across the set, the owner floor only for a set of one (spec 058 §3 step 4 as written), posture holes attached only to the nearest `*` row, and the root prefix compiled literally (`path LIKE '//%'`). (3) A budget sweep on an S1-shaped grant corpus (2,000 users, 300 team groups with one level of nesting, an all-hands group, private root, five shared top-level folders) for subject sets of 1 to 64 and 0 to 50 groups per person: ids fetched, statements, arms, literal binds, and the binds of the `EXISTS` fallback once group lists ride in it. (4) SQLite's arm ceiling by bisection. (5) Nesting: a 13-deep chain under caps of 4, 8, 16, and a cycle. |
| `results.md` | The output of one full run, with the reading of each section. |

## Rerun

Nothing to start: stdlib SQLite only, no containers.

    cd context/research/studies/2026-09-28-group-permissions
    uv run --no-sync python model.py           # 3,000 worlds, 20 sets per cell, a few minutes
    uv run --no-sync python model.py --quick   # 300 worlds, 5 sets per cell, about a minute

The seed is fixed (`--seed 20260928`), so a rerun prints the same
tables.

## Limits

- The model counts binds and arms; it does not time engines. Study S1
  (`../2026-09-05-permissions-predicate-at-scale/`) already timed the
  literal intersection with per-member owner arms (its shape (c)) on
  all five engines; this study only asks whether groups change the
  *size* of what S1 timed.
- SQLite is the only engine executed. The expression-depth finding is
  SQLite's (`SQLITE_MAX_EXPR_DEPTH`, 1,000 by default); other engines'
  parse limits are not probed here.
- The worlds are small and random on purpose: they hunt for algebra
  mistakes, not for realistic distributions. The sweep corpus is the
  realistic one.
