# Placeholder: the signals kernel in `vfs.models` is typed against three measure classes declared on the storage seam; where the measures belong is not yet researched

This is a placeholder memo: it holds a question, what is known, and the experiment that answers it, and it decides nothing. The question was raised on 2026-11-12 by the author of [the layer-map spec](../specifications/active/2026-11-07-the-gate-and-the-review-read-the-layer-map-and-the-size-baseline.md), while redrawing its ladder against the tree in answer to [its spec review](../reviews/2026-11-09-the-gate-and-the-review-read-the-layer-map-and-the-size-baseline-spec-review.md). That review judged runtime imports only and did not meet this one; the amended spec judges imports under `if TYPE_CHECKING:` too (its decision 3), and this is the one such import that points up its ladder. The answer will be used by the spec that removes the entry `("vfs.models.signals", "vfs.storage.ranking")` from `UPWARD_IMPORT_ALLOWANCE`, which is not yet written. No spec waits on this memo: the layer-map spec lands with the entry and links this memo from its decision 5. The research will have one 25-minute box. There is no studies folder yet; the figures below come from a scratch probe that judges the rows of the lint's own import walk, `import_edges()` in `tests/lint/test_code_shape.py`, under the ladder of that spec's decision 1. There is no intention: the import exists today and no caller's experience changes with where three classes are declared.

Labels: EXECUTED means a command ran here and the claim reports its output. READ means read in a file cited by path. INFERRED means this memo's reasoning from the two.

## The question

The centrality kernel lives in `vfs.models`, on a low rung. Its `measure` parameter is annotated with three classes that are declared in `vfs.storage.ranking`, on the storage seam, four rungs higher. Where do the measures belong, or what should the kernel take in their place, so that a module of the models layer names no type of the seam?

## What is known today

1. EXECUTED on 2026-11-12, vfs at `4a6d3e0`. `src/vfs/models/signals.py` imports `InDegree`, `Katz` and `PageRank` from `vfs.storage.ranking` under `if TYPE_CHECKING:`. Of the package's 170 typing-only imports it is the only one that points up the ladder. The module's one other `vfs` import is `vfs.native`, at runtime.
2. READ. `centrality_prior(node_count, sources, targets, parents, files, measure, gamma)` uses the measure on one line, `name, damping, alpha, iterations = measure.kernel_args()`, and hands those four values to the engine. The three classes are frozen dataclasses in `src/vfs/storage/ranking.py`, each with `kernel_args() -> tuple[str, float, float, int]`. The same module declares `Measure`, the union of the three and `PathShape`, and `Signal`, whose `measure` field holds one. `vfs.storage.ranking` imports no `vfs` module.
3. EXECUTED, the same run. `vfs.storage.ranking` is imported at runtime by `vfs.rerank` and by three modules of the database adapter (`backend.py`, `search.py`, `signals.py`), and for types by `models/signals.py`. READ: `centrality_prior` has one caller in `src/`, `signal_values` in `src/vfs/storage/backends/database/signals.py`, which already holds the `Signal`, branches on `PathShape` itself, and passes the measure through. Three test modules call the kernel: `tests/models/test_signals_kernel.py`, `tests/ranking/test_harness.py` and the reference implementation in `tests/support/oracles/signals.py`. No page under `docs/` names the three classes.
4. EXECUTED, the same run. Naming `vfs.storage.ranking` on either of the ladder's two lowest rungs would make the import point down and leave the ladder three exceptions. The spec did not do that: the module's own docstring calls it the ranking seam declared on the storage, and placing one module of a package apart from its package to dissolve an exception would be a map drawn to fit an import. The spec's decision 2 now refuses such a name outright: a deeper name never sits on a lower rung than the package it is part of.
5. INFERRED. Three shapes would each end with no import against the ladder, and this memo chooses none. First, the kernel takes the four kernel arguments, or a small protocol with `kernel_args`, and names no seam type. Second, the measures move down beside the kernel and the seam re-exports them. Third, the kernel's thin wrapper moves up beside its one caller, and `vfs.models` keeps nothing of the centrality prior.

## The experiment that answers it

The research is done when each item below has a labelled result.

1. Each of the three shapes in a scratch copy of the tree. For each: the number of faults the ladder test reports; the number of errors `uv run ty check src/ tests/` reports; the number of lines of `src/` and `tests/` that change; and the number of public names whose import path moves.
2. Whether `kernel_args` is the only member of a measure the kernel layer ever reads, by a count of every attribute read on a measure outside `storage/ranking.py`.
3. The prior art, each from a clone refreshed and licence-checked as [AGENTS.md](../../AGENTS.md) requires, described and never copied: how `networkx` and `rustworkx` hand a centrality's parameters to its kernel (plain arguments, a configuration object, or a protocol), and which module owns the parameter types.
4. What the following spec needs from this memo: the three shapes side by side on the counts of item 1, the attribute count, and the prior art's choices. The choice among them is that spec's.

## One line

One typing-only import runs from the models layer up to the storage seam, for three classes the kernel reads one method of; the research is to cost the three ways the kernel could stop naming them.
