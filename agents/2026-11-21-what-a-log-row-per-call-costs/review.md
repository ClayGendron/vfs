# Review of the study, before its pull request

A review of the commits `9240a9d..ad019e7` on the branch `what-a-log-row-per-call-costs`, made on 2026-11-21 by a fresh agent that did not write them, given the diff and `spec.md` and no summary. It checked spec conformance, at least 15 figures against the result files, the scripts' method, honesty of the claims, and voice. Every finding below was acted on in the commit that follows this record.

## Verdict

The study carries out decisions 1 to 8 of the spec, within scope (nothing under `src/` or `tests/`), and the GO with a log file of its own on SQLite stands on the data. The findings were under-reporting and overclaiming, not a wrong answer, and none changes the verdict.

## Findings and what was done

| rank | finding | done |
|---|---|---|
| High | The log's own write failures outside the waits run went unreported: on SQLite, 19 claims refused batches and 29 completions left `running` rows under 32 batches; 43 of 64 sync rows were lost; and two log writes timed out with no batch at all, inside warm-up calls the failure counts skip. | The memo reports each, from the `closing` records, and says the own-file variant was measured in the waits run only. |
| Medium | "One completion failed" was two, and one of the nine refused writes was vfs's own conflict. | Corrected. |
| Medium | "The counts are the same under 1 and 32 sessions" was true of the log's added counts only; retries and vfs's statistics task move the verb's own. | Narrowed to the log's counts, with the verb's variation and the stray 75 and 22 explained. |
| Medium | On Postgres vfs's bulk insert goes through `COPY`, which `before_cursor_execute` does not see, so the verb's counts miss those round trips. | Stated in the method, the statements section and *Not checked*, with the consequence for H0's `statements` column. |
| Medium | The +151 ms leaned write on Postgres was blamed on the log pool without a measurement, and spreads were compared inconsistently. | Labelled a hypothesis; every change is now judged against the no-log spread; the time bar is stated as covering reads only. |
| Medium | "A 30-day retention holds the table at 30 days of rows" was not shown for Postgres indexes, which grew 17.5 MB in one cycle. | Limited to SQLite and the Postgres heap; index reuse added to *Not checked*. |
| Medium | The Postgres conflict spec said the writes share no path, but all 32 directories share a parent created with `parents=True`; 13 of 960 is a lower bound. | Corrected in that spec, with the parent as the first suspect. |
| Medium | "Reads took what they took with no log" held for the median, not the 95th percentile on SQLite. | Narrowed, with the p95 figures. |
| Low | The 387 to 402 ms harness figure was in no result file. | `scripts/measure_build.py` records it in `results/build.json` (428 to 480 ms); the memo cites that. |
| Low | The waits table said "median over the repeats" where some cells are sums, and gave no sample sizes. | Relabelled; sample sizes added. |
| Low | The percentile rounds one rank high when q·n is an odd integer; the waits run reuses one database per mode. | Both stated in the method. The recorded figures were left as produced. |
| Low | `tables.md` listed result files by commit and dropped two; `run_all.sh` deleted everything in the scratch directory. | `report.py` lists every file; `run_all.sh` deletes only the directories its scripts made. |
| Low | Small slips: "about sixty" statements, "5.5 to 6 s", "3.5 to 4.0 s", "three times", an inferred fact marked run, a `top` reading cited as a figure. | Corrected. |
| Low | ruff, with rules beyond the project's gate, finds 19 issues in the scripts, mostly prints and `×`/`−` characters. | Left: the scripts are outside the `src/` and `tests/` gate, and pass the E, F, I, B and UP rules and the format check. |

## Documentation

No page changes. The study lands nothing under `src/`, so no docstring, user page or glossary term moves. Its answer is for the spec of the action log, H0, which carries it into `documentation/` when the log is built. `scripts/ci.sh` and `scripts/docs.sh check` were not run, because the branch touches neither `src/`, `tests/`, `crates/`, `pyproject.toml` nor any docs path.
