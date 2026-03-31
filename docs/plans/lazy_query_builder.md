# Future Plan: `GroverQuery`

## Context

Grover's primary query-construction UX should be the CLI / MCP expression language, not a Python query builder.

That means the near-term architecture should be:

```text
CLI / MCP string
    -> parser
    -> AST
    -> executor
    -> existing eager async Grover API
```

Python should stay simple and explicit:

```python
result = await grover.semantic_search("auth")
result = await grover.ancestors(candidates=result)
result = await grover.pagerank(candidates=result)
result = result.top(20)
```

Even so, it is still useful to plan for a future `GroverQuery` object that can support the fluent chaining style:

```python
result = await g.search("auth").ancestors().pagerank().sort().top(20)
```

The important constraint is that `GroverQuery` should be a future secondary surface over the same query model used by the CLI. It should not become the primary product surface, and it should not force `GroverResult` to carry lazy execution state.

## Decision

If Grover eventually adds fluent Python chaining, it should do so with a dedicated `GroverQuery` builder layered on top of the CLI query AST / executor.

This implies:

- `GroverFileSystem` remains the eager async execution layer
- `GroverResult` remains the resolved value type
- CLI / MCP stays the primary query-construction surface
- `GroverQuery` is a future ergonomic adapter over the same underlying plan model

## Goals

- Preserve the existing eager async API on `GroverFileSystem`
- Keep CLI / MCP as the canonical query language
- Make any future `GroverQuery` reuse the same AST and executor as the CLI
- Support one-terminal-`await` Python chaining in the future
- Avoid `_grover` back-references and result-driven execution

## Non-goals

- Making `GroverQuery` the main UX
- Turning `GroverResult` into a lazy builder
- Depending on `await result.method()` as the core execution story
- Supporting arbitrary Python callables in future lazy query steps
- Building a separate Python-only planning system

## Core Principle

`GroverQuery` should compile to the same internal representation as the CLI.

There should be one execution engine:

```text
CLI string  -------------------\
                                -> shared AST -> shared executor -> GroverFileSystem methods -> GroverResult
GroverQuery fluent builder ----/
```

If the CLI and Python builder produce different plan types, Grover will end up maintaining two query languages and two execution models. That is exactly what this plan is trying to avoid.

## What `GroverQuery` Is

`GroverQuery` is a future immutable, awaitable query-plan builder.

Responsibilities:

- hold a reference to the target Grover instance
- hold an immutable list / tuple of query steps
- expose fluent builder methods
- execute only when awaited or explicitly executed
- lower to the same AST / execution path as the CLI

Non-responsibilities:

- store result candidates
- serialize resolved values
- perform mount routing directly
- call providers directly

## What `GroverQuery` Is Not

`GroverQuery` is not:

- a replacement for `GroverFileSystem`
- a replacement for `GroverResult`
- a place to store `_grover`
- the main way CLI queries are authored

`GroverResult` should stay concrete and eager. It should represent data that already exists, not a plan that might execute later.

## Recommended Future API

### Async-first surface

If this is added later, it should look like:

```python
result = await g.search("auth").ancestors().pagerank().sort().top(20)

result = await (
    g.query()
    .glob("**/*.py")
    .grep("auth")
    .ancestors()
    .pagerank()
    .sort()
    .top(20)
)
```

Recommended entrypoints:

```python
g.query() -> GroverQuery
g.search(query: str, *, mode: Literal["semantic", "lexical"] = "semantic", k: int = 15) -> GroverQuery
```

`search()` is sugar.

`query()` is the neutral root for pipelines that do not begin with search.

### Sync surface

If the sync wrapper eventually wants parity, prefer an explicit terminal call:

```python
result = g.search("auth").ancestors().pagerank().sort().top(20).execute()
```

That is cleaner than trying to fake terminal `await` in sync code.

## Execution Model

The future `GroverQuery` executor should not rely on `GroverResult` chain stubs.

Instead, it should lower into explicit eager calls:

```python
result = await grover.semantic_search("auth")
result = await grover.ancestors(candidates=result)
result = await grover.pagerank(candidates=result)
result = result.sort()
result = result.top(20)
```

That keeps the execution contract obvious:

- Grover methods execute
- `GroverResult` stores data
- local transforms operate on resolved results

This is also the same shape the CLI executor should use internally.

## Relationship To `GroverResult`

This future plan assumes `GroverResult` should become a pure resolved-value type.

That means:

- keep local result behavior such as `paths`, `content`, `file`, `explain`
- keep pure eager transforms such as `sort`, `top`, `filter`, `kinds`
- keep set algebra such as `&`, `|`, `-`
- eventually remove `_grover` and methods that call through it

In other words:

- `GroverQuery` is the future lazy builder
- `GroverResult` is the eager result

They should not overlap in responsibility.

## Step Model

The future `GroverQuery` should build a query-step subset of the shared AST.

Likely step families:

- discovery: `glob`, `grep`, `semantic_search`, `lexical_search`, `vector_search`
- traversal: `predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`, `min_meeting_subgraph`
- scoring: `pagerank`, `betweenness_centrality`, `closeness_centrality`, `degree_centrality`, `in_degree_centrality`, `out_degree_centrality`, `hits`
- eager-local transforms: `sort`, `top`, `kinds`
- future composition: `union`, `intersect`, `diff`

Important constraint:

The builder subset should remain serializable and compatible with the CLI query model.

So future lazy query steps should not support arbitrary Python callables like:

- `filter(fn)`
- `sort(key=callable)`

Those can stay on `GroverResult` as eager, Python-only helpers.

## Relationship To The CLI Plan

This future plan depends on the CLI execution model being the source of truth.

Recommended order:

1. build the CLI / MCP parser and AST
2. build the executor that lowers AST nodes into explicit Grover calls
3. simplify `GroverResult` into a pure eager value type
4. only then consider adding `GroverQuery` as a thin Python builder over that same AST

If Grover builds `GroverQuery` first, there is a high risk that:

- the Python builder becomes the accidental primary UX
- the CLI executor has to adapt to a Python-shaped model
- `GroverResult` keeps carrying `_grover` longer than it should

## Implementation Phases

### Phase 1: CLI-first query model

- finish the CLI / MCP query grammar
- define the shared AST
- implement the executor
- route every step through the eager async Grover API

### Phase 2: result cleanup

- stop treating `_grover` chaining as intended public API
- deprecate `_grover`-dependent methods on `GroverResult`
- keep only pure eager result behavior on `GroverResult`

### Phase 3: future `GroverQuery`

- add `GroverQuery` as a builder for the shared AST
- add `query()` and `search()` entrypoints
- add terminal `await` / `execute()`
- keep builder methods to the serializable query subset

### Phase 4: composition

- add query-level `|`, `&`, `-`
- add AST serialization for reuse across Python, CLI, and MCP

## Tests For The Future `GroverQuery`

When it is eventually built, add tests that verify:

- no execution happens before `await`
- `await g.search("auth").ancestors().pagerank()` matches the imperative equivalent
- local transform steps match the eager `GroverResult` behavior
- the builder lowers to the same AST shape the CLI parser produces
- mount routing and rebasing are unchanged when going through the builder

## Open Questions

1. Should `search()` default to semantic search only, or represent a higher-level hybrid search concept?
2. Should `GroverQuery` land only after `_grover` is fully removed from `GroverResult`?
3. Should query set algebra be part of the first `GroverQuery` slice, or wait until the CLI query language settles?
4. Does the shared AST for CLI need a dedicated query-only subset, or is the same node set good enough for both CLI and future `GroverQuery`?

## Recommendation

Treat `GroverQuery` as a future secondary surface, not an immediate project.

The priority order should be:

1. CLI / MCP query language
2. shared AST + executor
3. clean eager Grover API and eager `GroverResult`
4. future `GroverQuery` adapter

If Grover later wants the fluent Python syntax:

```python
result = await g.search("auth").ancestors().pagerank().sort().top(20)
```

it should get there by reusing the CLI query engine, not by adding more hidden execution behavior to `GroverResult`.
