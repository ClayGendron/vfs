# Brief for the adversarial reviewer of the grep planner design

The design under review is `agents/2026-11-21-grep-query-planner/spec.md`. It proposes how vfs's database `grep` chooses a plan before it fetches a body, and what, if anything, the index must gain for that choice. The job is to break the design: find a case where a plan it chooses returns a wrong or incomplete answer, costs more than the plan it rejected, grows with something it claims it does not grow with, or depends on a fact the design says it has but does not.

## Evidence standard

A finding is admitted only with an executed reproduction: a script that ran against the sandbox or the pinned code, its command, and its output. A finding that cannot be run is reported as a question, not a finding. Every finding states its severity (high, medium or low), the decision of the spec it breaks by number, the script's path, and the observed output. A finding that would hold on Postgres and not on SQLite, or the reverse, says so, and says which engine was run.

## What is provided

- The pinned vfs code the sandbox was built with, commit `5dfdcc79`, in a checkout of its own outside the repository, with the built `_native` module copied into its `src/vfs`. Import it by running `PYTHONPATH=<that checkout>/src uv run python <script>` from the repository root. The main checkout was being edited by another session and did not import.
- The sandbox: `linux.db`, built by `agents/2026-11-21-linux-grep-benchmark/ingest.py`, a SQLite `DatabaseStorage` holding the Linux source tree (93,759 files, 6,160 directories, 1.59 GB of bodies, indexed). Open it read-only for raw SQL (`sqlite3.connect("file:<path>?mode=ro", uri=True)`). Through vfs, run only reads: `grep`, `glob`, `read`, `ls`, `stat`. Never write, delete, move, rebuild or refresh against it. A test that needs a write makes its own database: copy what it needs into a new SQLite file under the scratch directory below, or build a small store from scratch with `DatabaseStorage(url="sqlite+aiosqlite:///<new file>")`.
- The experiments behind the spec: `agents/2026-11-21-grep-query-planner/experiments/`, and the earlier benchmark in `agents/2026-11-21-linux-grep-benchmark/`.
- Docker is available for a real Postgres leg, as `.claude/skills/db_test/SKILL.md` describes, if a finding needs Postgres. A Postgres leg takes a fresh ingest; say so before spending it, and keep it small (a subtree of the Linux tree, not the whole).

## Rules

- Throwaway scripts go in a scratch directory outside the repository, one per round. They are kept afterwards under `reviews/scripts/round-<n>/`. Nothing under `src/`, `tests/` or `crates/` is edited, in either checkout.
- Every shell command gets a timeout set from an estimate of how long it should take, about twice the estimate. A timeout that fires is a finding about the script to diagnose, not a number to raise.
- Another session shares this machine and at times runs a parallel test suite and a Docker VM. Before any timing, run `uptime`. A timing taken with a one-minute load average above 4 is marked *loaded*, and no finding rests on it alone. A finding that needs a timing and cannot get a quiet machine rests on counts, or is reported as a question.
- Count operations as well as time them: statements issued, rows or ids visited, bytes fetched. A timing claim states the median of at least five warm runs.
- The sandbox's entry ids were assigned in path order, because the ingest wrote files sorted by path. Production ids follow write order. A finding that depends on id order says so; a design element that silently depends on it is itself a finding.
- The review is written to `agents/2026-11-21-grep-query-planner/reviews/round-<n>.md`, in an objective, impersonal voice (no "I", "we" or "you", no person named). It opens with a verdict line, "Fit to build", "Fit to build with changes" or "Not yet", then the findings ranked high to low, then what was attacked and held. The spec itself is not edited by the reviewer.

## What to attack, at least

Every decision in the spec, and in particular: whether each plan returns the same rows as the others whenever none of them truncates; whether a cap can drop an in-scope row; whether visibility, trash, the `/.vfs` meta subtree and unencoded (scan-side) rows are treated the same by every plan; whether every statement the design adds is bounded by a declared budget and not by the corpus; whether the cost model's choices hold across the scopes and patterns it was not tuned on, including multi-root scopes, roots that are files, glob-arm scopes, case-insensitive patterns, alternations, anchored patterns and patterns with no indexable literal; and whether the claims against the reference deployment in `AGENTS.md` (ten million files, a million directories, about 20 verb calls a second at peak) follow from the measurements.
