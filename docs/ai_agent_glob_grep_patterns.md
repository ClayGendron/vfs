# AI Agent Glob and Grep Patterns

## Why this document exists

`glob` and `grep` are the two most-used search primitives for AI coding agents. When an agent is working in a codebase it doesn't already have in context, nearly every navigation step starts with one of these two tools. How well they perform — and how well their interface matches how agents actually call them — has an outsized effect on how fast and how accurately an agent can work.

This document describes how agents *actually* use glob and grep in practice, extracted from observing real usage patterns. It's intended as a spec for humans implementing search: if the tool you build matches these shapes, agents will be fast and precise. If it doesn't, agents will work around it — usually by issuing many more queries than necessary, each one more expensive than it needed to be.

The audience is engineers building the Grover CLI and the `MSSQLFileSystem` grep/glob implementations. The goal is a shared mental model before any code changes.

---

## The agent's mental model

An agent approaching an unfamiliar codebase does not think "scan everything for regex X." It thinks in **progressively narrowing filters**:

1. What *kind* of file am I looking for? (language, extension, role)
2. Where in the tree is it likely to be? (directory scope)
3. What literal token would appear in a matching file? (identifier, error message, config key)
4. Of the hits, which are worth reading in full?

Each step is cheap on its own. The expensive operation — actually reading and understanding file content — is deferred until the candidate pool is small enough to be worth the attention budget. An agent's tool calls mirror this funnel: broad structural filters first, content inspection last.

A search tool that forces the agent to do all four steps in one query (or that treats "scan all content" as the default path) fights this mental model. The result is either slow queries that time out, or result sets so large the agent has to issue follow-up queries to narrow them — paying the full cost twice.

---

## Concrete usage patterns

### Pattern 1: Type-scoped grep (the default shape)

> "Find `UserAuthError` in Python files."

```
grep "UserAuthError" --type py
```

This is the single most common shape. The agent has a literal token and a file-type constraint. It almost never wants to search YAML, markdown, lock files, node_modules, or binary assets — and those categories together are usually 80%+ of the corpus by file count.

**Key properties:**
- File type is the *first* filter the agent reaches for, before path scope.
- The pattern is almost always a literal identifier, not a real regex.
- The agent expects fast results because it's already narrowed hard.

**What agents want from the tool:**
- First-class `--type`/`type=` parameter that maps to an indexed column, not a trailing-wildcard `LIKE '%.py'`.
- Extension or language classification stored at write time, not derived at query time.
- Common aliases: `py`, `js`, `ts`, `go`, `rs`, `md`, `sql`.

### Pattern 2: Path-scoped grep

> "Find `worker.schedule` under `src/grover/api/`."

```
grep "worker.schedule" --path src/grover/api
```

Used once the agent has a hypothesis about *where* the code lives. Path scope is sargable (prefix match) and should be effectively free — a well-indexed path column turns this into an index range scan.

**What agents want:**
- `--path` as a directory prefix (not a glob), because that's how the agent thinks about it.
- Composable with `--type`. "Python files under `src/api/`" is the common shape.

### Pattern 3: Glob-filtered grep

> "Find `TODO` in test files anywhere."

```
grep "TODO" --glob "**/test_*.py"
```

More expressive than `--type` + `--path`, used when the agent needs a pattern the simpler filters can't express. This is the escape hatch, not the default. It should still benefit from SQL pre-filtering via `glob_to_sql_like()`.

### Pattern 4: Glob-then-grep chaining (two queries, one intent)

> "Python files in `api/` that mention `worker`."

```
glob "src/grover/api/**/*.py" | grep "worker"
```

The agent often expresses a narrowing in two steps because that's how the intent decomposes. A good tool design lets the first query's result feed directly into the second without re-scanning. This is exactly what `candidates=` already supports — but it should be the *natural* shape, not a power-user option.

**What agents want:**
- `glob` and `grep` return the same result type.
- Chaining is the default composition; the second operator sees the first's output and pushes the constraint into SQL (`path IN (...)`), not Python.
- Ideally, composition operators (`&`, `|`, `-`) on the result type make "narrow" and "union" feel like set algebra.

### Pattern 5: Two-phase exploration (paths first, content second)

> Round 1: "Where does `login` appear?" (20 files)
> Round 2: "Show me the three in `auth/` with context."

```
grep "login" --type py --output paths
grep "login" --path src/grover/auth --context 3
```

Agents almost never want "all matching lines across 500 files" in one shot — the context window can't hold it and most hits are noise. The real pattern is: get a cheap list of candidate paths, triage, then pull full context for the interesting few.

**What agents want:**
- An `--output paths` mode (or equivalent) that returns only file paths, no line matches, no content hydration. Cheap on the server, cheap on the wire, cheap on the agent's context.
- Per-line match details only when explicitly requested.
- Context lines (`-C N`) only on the narrow follow-up query.

### Pattern 6: Head-limited results

> "First 50 matches will do."

Agents cap result sets aggressively. 10,000 hits is never useful — if that's what the query returns, the agent will re-scope and ask again. A hard `--limit` (or `max_results`) should short-circuit the query as early as possible, ideally pushed into the SQL `TOP`/`LIMIT` clause rather than trimmed client-side.

### Pattern 7: Literal identifier lookup (the symbol case)

> "Where is `login` defined?"

This is technically a grep, but it's really a symbol lookup. The agent wants the *definition*, not every line that mentions the name. Grover already has `grover_file_chunks` with symbol-level granularity — for this shape, a chunk-level search that hits an indexed `symbol_name` column is orders of magnitude faster than regex-scanning file content.

**What agents want:**
- A distinct operator (e.g. `grep_symbols` or `find_definition`) that searches chunk metadata, not file content.
- When an agent greps for `def login` or `class Login`, the tool could recognize the shape and route to the symbol path automatically — but explicit is fine too.

### Pattern 8: Iterative narrowing (the loop)

Agents don't issue one perfect query. They issue a sequence:

```
grep "worker" --type py                              # 500 hits — too many
grep "worker" --type py --path src/grover/api        # 80 hits — still too many
grep "worker.schedule" --type py --path src/grover   # 12 hits — now useful
```

Each step throws away the previous result and re-queries. This means **every individual query needs to be fast**, even the broad ones — because the agent will run several on the way to the answer. A query that takes 30 seconds is a query the agent gives up on.

---

## What these patterns imply for implementation

### 1. Structural filters are first-class, not afterthoughts

`type`, `path`, `glob`, `limit`, and `output` should be direct kwargs on `grep` (and `glob` where applicable), not features the caller has to compose manually. Each should push into SQL:

- `type` → indexed extension column
- `path` → sargable `LIKE 'prefix/%'`
- `glob` → `glob_to_sql_like()` pre-filter
- `limit` → `TOP`/`LIMIT` in the SQL, not Python slicing
- `output=paths` → `SELECT path` only, no content fetch

### 2. Defer content hydration as long as possible

The current grep fetches `o.content` on the initial query because it needs to build per-line match metadata. But for Patterns 1, 2, 3, 4, 6, and the first phase of 5, the agent doesn't want per-line detail — it wants paths. Splitting the implementation into:

- `grep_paths()` → fast, index-friendly, no content transfer
- `grep_lines()` → slower, returns line-level detail, typically called on a narrow candidate set

…matches the real usage curve. Alternatively, a single `grep` with an `output=` flag that controls which path is taken.

### 3. Chunk-level search as a parallel primitive

`grover_file_chunks` already exists and already stores symbol-level data. A `grep_symbols()` (or equivalent) that queries chunks instead of full file content would handle Pattern 7 with an index seek. For identifier-dominated queries — which is most of what agents do — this is the biggest single optimization available, and it doesn't require any changes to the content-grep path.

### 4. Composition should be cheap and push down

`glob | grep` (Pattern 4) should produce SQL where the second operator sees the first operator's paths as an `IN` clause or a temp table, not a Python-side filter. The `candidates=` parameter already does this structurally, but the result-set size should drive the strategy: small candidate sets go through `IN (...)`, large ones go through a join against the first query's result materialized as a temp/CTE.

### 5. CONTAINSTABLE ranking for the long tail

When the agent does issue a broad grep without enough filters to narrow it fast, the mssql CONTAINSTABLE path should sort by FTS rank and apply `TOP` early. A broad query that returns "the 50 most relevant files" in half a second is infinitely more useful than a broad query that returns "all 10,000 files" in thirty seconds.

### 6. Every query on the hot path needs to be fast

Because of Pattern 8 (iterative narrowing), "the slow query is fine because you can always narrow" is not a valid answer. Each step of the funnel is a separate tool call, and the agent won't know it needs to narrow until it sees the first result. A 30-second broad grep costs the agent 30 seconds *and* a second query. Target: every reasonable query returns in <2s on a ~1M-row corpus.

---

## Anti-patterns (things that hurt agents)

- **Forcing a single monolithic query shape.** "Here's grep, it does everything" means the fast paths and the slow paths all go through the same expensive code. Split by usage shape.
- **Returning too much data by default.** Per-line matches for 500 files blows out the agent's context window. Default to paths; opt in to lines.
- **Slow broad queries "because you can always narrow."** The agent can't narrow until it sees the result; the slow query has already happened.
- **Non-sargable filters disguised as fast ones.** `path LIKE '%.py'` looks like a filter but triggers a full scan. If `type="py"` is supposed to be fast, there must be an index behind it.
- **Composition that round-trips through Python.** If `glob | grep` decomposes into "load all glob results into Python, then issue a grep with a 10,000-element `IN` clause," the composition costs more than doing it as one query would have.
- **Untyped or stringly-typed result shapes.** The agent needs to know what it got back. `FileSearchResult` with clear `file_candidates` / per-candidate evidence is already the right shape — keep it that way across all operators.

---

## Summary

Agents use glob and grep as **progressive filters**, not as **full-corpus scans**. The vast majority of queries are narrow, literal, type-scoped, and paths-first. The implementation should optimize for that distribution, not for the worst case, and should expose the narrowing tools (`type`, `path`, `glob`, `limit`, `output`, chunk-level symbol search) as first-class parameters that push into SQL.

The performance wins available aren't in making `REGEXP_LIKE` faster — they're in making sure most queries never reach `REGEXP_LIKE` at all.
