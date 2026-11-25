# Handoff: the backlog conversion, paused on 2026-11-25

The goal: every spec in the backlog is either removed or fit to build, delivered as one pull request to `dev`. The work paused when the subagent usage limit was reached; nothing is running and every file is committed on `claude/dreamy-brahmagupta-y1wphu`.

## Done

- Thirty studies of the numbered specs against the tree and the roadmap, under `studies/`, and seven verifications of the roadmap's unruled decisions for sense and precedent, under `decisions/`.
- The map of the conversion, [units.md](units.md): 3 numbered specs archived as landed (162, 165, 173), 3 withdrawn as overtaken (102, 155, 161), and 24 converted into 88 units, each one spec and one pull request, with a dependency graph that has no cycle.
- All thirty numbered folders moved to `context/specifications/archive/`, each headed by a dated disposition line; `tests/lint/allowlist.py` follows the paths.
- The spec and review templates under `agents/templates/`, with provisional decisions and the dependency rule, and the shape checker [check_shape.py](check_shape.py).
- 27 of the 88 unit specs drafted; each holds the nine sections and passes the shape checker. None is reviewed.
- Two dated specs under `context/` brought to a standing verdict of Fit to build: the rights compile, and the SQL Server reader (evidenced on a SQL Server container).

## Not done

- 61 unit specs not drafted. Units whose dependencies are drafted can be converted next; the order is the layer order of the map.
- No unit spec is reviewed. Each needs a review, answers to its findings and a re-read to a standing "Fit to build".
- The miss-beneath and docs-site specs have new 2026-11-25 reviews with findings not yet answered. The lint placeholder spec's memo carries part of its experiments; the spec is not completed or reviewed. The release-audit and kernel-rulings specs still wait on their code reviews' re-reads. The docs-deployment spec waits on the `vfs.dev` zone and its placeholder memo.
- The roadmap (`context/standards/roadmap.md`) does not yet point at the unit specs.
- No pull request is opened.

## How to resume

- The workflow script that converts, reviews, answers and re-reads a unit is kept outside the repository, in the session scratchpad (`convert.js`, generated per batch by `gen.py`, with `sched.py` reporting which units are ready). In a fresh session, regenerate it from this note and [units.md](units.md): one writer per unit following `agents/templates/spec.md`, then a reviewer that did not write it following `agents/templates/review.md`, up to three rounds.
- Each reviewer is given the reviewer questions the writer raised, never the writer's summary.
- A dependency of a unit that is drafted and not built does not hold its verdict; after all units are reviewed, each spec's quotations of its dependencies are checked against them once more.

## Found on the way, not caused by this work

- The lint tier was red on `main` before this branch: `tests/lint/test_context_shape.py::test_links_resolve` reports 24 links to `.log` files that `.gitignore` keeps out of the repository, and 6 links from an archived spec to specs still under `active/`.
