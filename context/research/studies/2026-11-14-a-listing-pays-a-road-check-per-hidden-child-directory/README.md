# The probes behind the road memo

The scripts and recorded outputs [the road memo](../../2026-11-14-a-listing-pays-a-road-check-per-hidden-child-directory.md) cites, written for the state check of [the rights-compile scale pins](../../../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md) and run on 2026-11-14 at `e90ec653`, on SQLite through `uv run`, Python 3.13. They count statements, binds and rows; none reads a clock. Each `.out` file is the output the memo quotes, recorded from the command below it.

Every database probe takes, as its first argument, a directory outside the repository for its SQLite files. `probe_compile.py` builds the world there when it is absent, and `world-10000.sqlite` takes several minutes; run it first. Run each from the repository root. `probe_floors.py` needs no directory: it compiles in memory.

| file | what it measures | command |
|---|---|---|
| `experiments/world.py` | support, not a probe: the scale-pins world at N users (homes at posture `none`, 100 shared folders, 50 groups, the named callers), a fast build, and a statement recorder | imported by the others |
| `experiments/probe_compile.py` | per caller and verb, the statements, binds and bound bytes at each N, and whether the texts are identical across the sizes | `uv run python <dir>/experiments/probe_compile.py <data-dir> 1000 10000` |
| `experiments/probe_statements.py` | every statement one caller's verb issues at each N, with its binds and bound bytes | `uv run python <dir>/experiments/probe_statements.py <data-dir> ann "ls /home" 1000 10000` |
| `experiments/probe_budget.py` | the same verbs under another engine's `IN`-list cap emulated on SQLite (1,000 is Oracle's) | `uv run python <dir>/experiments/probe_budget.py <data-dir> 1000 1000 10000` |
| `experiments/probe_floors.py` | per profile, a caller's statements as its own grants grow, the road's owner tests among them | `uv run python <dir>/experiments/probe_floors.py` |

Here `<dir>` is `context/research/studies/2026-11-14-a-listing-pays-a-road-check-per-hidden-child-directory`. The outputs are `experiments/<probe>.out`. In `probe_compile.out` the only texts that differ between the sizes are the partial callers' `ls /home` and `glob /home/**`, the road this memo is about, and admin's and the system actor's `grep` and `search`, whose content fetch lists the ids of every file they see, more in the larger world.
