# The probes behind the in-flight compile memo

The scripts and recorded outputs [the in-flight memo](../../2026-11-14-a-posture-change-in-flight-compiles-every-posture-row-beneath-it.md) cites, written for the state check of [the rights-compile scale pins](../../../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md) and run on 2026-11-14 at `e90ec653`, on SQLite through `uv run`, Python 3.13. They count statements, binds, pieces and rows; none reads a clock. Each `.out` file is the output the memo quotes, recorded from the command below it.

Every database probe takes, as its first argument, a directory outside the repository for its SQLite files, and builds the world it needs there when the file is absent; `world-10000.sqlite` takes several minutes to build. Run each from the repository root. `probe_floors.py` needs no directory: it compiles in memory.

| file | what it measures | command |
|---|---|---|
| `experiments/world.py` | support, not a probe: the scale-pins world at N users (homes at posture `none`, 100 shared folders, 50 groups, the named callers), a fast build, and a statement recorder | imported by the others |
| `experiments/probe_window.py` | ann's compile and her `grep`, `glob` and `read` while `/home` is narrowed and held in flight, at each N | `uv run python <dir>/experiments/probe_window.py <data-dir> 1000 10000` |
| `experiments/probe_stuck.py` | a posture change whose first relabel chunk fails: the verb's answer, the standing mark, ann's cost, a reopen, and the unrelated `posture` call that clears it | `uv run python <dir>/experiments/probe_stuck.py <data-dir> 1000` |
| `experiments/probe_relabel.py` | a relabel's rows, statements and transactions against the planner's law, and every read between two chunks against the pointwise oracle | `uv run python <dir>/experiments/probe_relabel.py <data-dir> 2000 250`, also with `100 250`, `995 250` and `100000 50000` |
| `experiments/probe_floors.py` | per profile, a caller's statements as its grants grow, and the hole an in-flight posture adds over 100, 1,000 and 10,000 posture rows beneath it | `uv run python <dir>/experiments/probe_floors.py` |
| `experiments/probe_generic_hole.py` | the generic floor's road during a window over D posture rows, against SQLite's own spelling | `uv run python <dir>/experiments/probe_generic_hole.py <data-dir> 400`, also `100` and `400 range` |

Here `<dir>` is `context/research/studies/2026-11-14-a-posture-change-in-flight-compiles-every-posture-row-beneath-it`. The outputs are `experiments/<probe>.out`; `probe_relabel.out` and `probe_generic_hole.out` hold each listed argument set in the order given.
