# Placeholder: the coverage gate's ellipsis pattern excludes, whole, every function whose signature holds an ellipsis, 111 functions and about 1,400 statements today; what the 100% figure measures and what the exclusion should be is not yet researched

This is a placeholder memo: it holds a question, what is known, and the experiment that answers it, and it decides nothing. The question was raised on 2026-11-12 by [the second spec review of the router spec](../reviews/2026-11-12-the-router-keeps-routing-spec-review.md), in a note beside its criterion 17, and was seen the same day on a scratch build by the author of [that spec](../specifications/active/2026-11-07-the-router-keeps-routing.md). The session lead ruled the same day that it is not that spec's to fix and must not stay a note in a review, so it is a document now, under decision 9 of [the gate-and-review spec](../specifications/archive/2026-11-07-the-gate-and-the-review-read-the-layer-map-and-the-size-baseline.md). The answer will be used by the spec that changes the exclusion, which is not yet written. No spec waits on this memo: the router spec lands with its two new modules partly outside the coverage measure, says so, and links this memo from its Scope. The research will have one 45-minute box. There is no studies folder yet; every figure below comes from `coverage`'s own static analysis, `Coverage.analysis2`, run under the project's configuration over each module of `src/vfs` at `b2a32c3`, by a scratch script that reads the tree and writes nothing. There is no intention: no caller's experience changes with what a gate counts.

Labels: EXECUTED means a command ran here and the claim reports its output. READ means read in a file cited by path. INFERRED means this memo's reasoning from the two.

## The question

The gate fails a landing unless coverage is 100%. The configuration leaves some lines out of that count, and one of the six patterns that say which is an ellipsis anywhere on a line. When the line that matches is a function's header, `coverage` leaves out the whole function. So three things are asked. What does the 100% figure measure today, and what is outside it? What should the exclusion be, so that a stub body stays out and a real function comes in? And of the statements that would come in, how many does no test reach?

## What is known today

1. READ, vfs at `b2a32c3`. `pyproject.toml`, under `[tool.coverage.report]`, sets `fail_under = 100` and six `exclude_lines` patterns: `pragma: no cover`, `if TYPE_CHECKING:`, `if __name__ == .__main__.`, `@overload`, `raise NotImplementedError`, and `\.\.\.`. `scripts/ci.sh` runs the suite with `--cov-fail-under=100`.
2. EXECUTED on 2026-11-12, the same commit. The ellipsis pattern matches anywhere in a line, and a function whose header holds an ellipsis is excluded whole: every line of it is in the excluded set `analysis2` returns. The usual cause is an annotation such as `tuple[str, ...]`. In `src/vfs/base.py` that is 21 of 112 functions: the public verbs `glob`, `grep`, `search` and `traverse`; `mounts`; the fan-out router `_route_fanout` with `_classify_fanout_scopes`, `_glob_dispatches`, `_grep_dispatches`, `_planned` and `_root_probes`; both chained filters, `_glob_rows_in_hand` and `_grep_rows_in_hand`; and eight functions of the planner, `_plan_scope` and `_walks` among them.
3. EXECUTED, the same run, the package whole: 97 modules and 39,618 lines. Under today's configuration 13,202 statements are measured, the number the gate prints, and 4,144 lines are excluded. With the ellipsis pattern removed, 14,666 statements are measured. With it narrowed to a line that holds nothing but an ellipsis, 14,655. With it narrowed to that or a line that ends in a colon and an ellipsis, which keeps a one-line stub out, 14,617, and 760 lines stay excluded. By that last count 1,415 statements that are not stub bodies are outside the measure today, in 44 of the 97 modules, and 111 of the package's 1,552 functions are excluded whole by an ellipsis in the header. That is about one statement in ten.
4. EXECUTED, the same run, the ten modules with the most lines excluded today. "Outside" is the statements that the third narrowing above would bring into the measure.

| Module | Lines | Statements measured | Lines excluded | Statements outside | Functions excluded whole |
|---|---|---|---|---|---|
| `src/vfs/base.py` | 3,660 | 1,023 | 1,036 | 332 | 21 of 112 |
| `src/vfs/storage/backends/database/grep.py` | 648 | 81 | 322 | 167 | 4 of 10 |
| `src/vfs/storage/backends/database/search.py` | 1,248 | 369 | 318 | 132 | 3 of 29 |
| `src/vfs/sync.py` | 1,086 | 222 | 284 | 35 | 12 of 83 |
| `src/vfs/storage/backends/database/backend.py` | 1,997 | 674 | 250 | 48 | 5 of 80 |
| `src/vfs/results/render.py` | 725 | 249 | 247 | 147 | 9 of 33 |
| `src/vfs/storage/protocol.py` | 550 | 47 | 229 | 1 | 0 of 31 |
| `src/vfs/pattern_matching/glob.py` | 912 | 309 | 205 | 122 | 10 of 41 |
| `src/vfs/storage/backends/database/reads.py` | 1,318 | 473 | 178 | 70 | 4 of 45 |
| `src/vfs/session.py` | 444 | 117 | 134 | 16 | 4 of 34 |

5. EXECUTED, the same run. Sorted by statements outside the measure instead, three other modules enter the ten: `src/vfs/models/chunking.py` with 52, `src/vfs/results/projection.py` with 48 (against 14 measured), and `src/vfs/storage/grants.py` with 38; `sync.py`, `protocol.py` and `session.py` leave it. `src/vfs/storage/protocol.py` shows the pattern doing what it was written for: its 229 excluded lines are protocol stubs, and one statement of it is outside the measure.
6. EXECUTED on 2026-11-12, on the router spec's scratch build. One arm that no test reaches sits inside an excluded function: chained grep's refusal of an invalid pattern. With that arm made to raise, 4,810 nodes passed and none failed, and the gate reads 100% on the same tree. On that build, 8 of the 13 functions of `src/vfs/fanout.py`, `plan_scope` and `walks` among them, are outside the measure, which counts 29 of the module's 113 statements; both filters of `src/vfs/chain.py` are outside, and it counts 57 of 107. The spec holds the two modules by direct pins and their mutants.
7. INFERRED. The pattern was written to leave out stub bodies: a protocol method or an overload whose body is an ellipsis. Nothing in the configuration or in the standards says a function with an ellipsis in an annotation should be left out.
8. Not known: how many of the statements outside the measure are reached by no test. Item 6 is one; no count exists.

## The experiment that answers it

The research is done when each item below has a labelled result.

1. The three candidate exclusions of item 3, and any other the study finds in `coverage`'s documentation for excluding a stub body, each applied in a scratch copy of the tree. For each: the statements measured, the lines still excluded, and the number of stub bodies that wrongly come into the measure, by module.
2. The gate's coverage leg run in the scratch copy under each candidate, as `scripts/ci.sh` runs it. For each: the statements no test reaches, by module and by function. This is the number item 8 lacks.
3. Each unreached statement sorted into one of four kinds, with a count for each: reached only on a real-engine leg; a refusal or defensive arm a unit test could reach; code no caller can reach; and a stub the candidate failed to leave out.
4. What the following spec needs from this memo: the candidates side by side on the counts of items 1 and 2, and the list of item 3. Which exclusion to adopt, and whether the unreached statements gain tests or pragmas, is that spec's choice.

## One line

An ellipsis in a signature takes the whole function out of the coverage measure, about one statement in ten across the package, so 100% says less than it reads; the research is to narrow the pattern in a scratch copy and count what no test reaches.
