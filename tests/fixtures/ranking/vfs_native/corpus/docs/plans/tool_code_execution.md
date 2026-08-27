# Tool Code Execution: CLI Expression Language

## Context

Grover exposes itself as a single MCP tool. An LLM sends one string, Grover parses it into an AST, executes it, and returns structured results. This eliminates multi-round-trip tool calling: one invocation can express loops, conditionals, set algebra, and tool composition.

The expression language sits above the filesystem. The parser and AST executor are a separate layer that calls `GroverFileSystem` methods. The filesystem knows nothing about the AST.

```
LLM  →  "search --query 'auth' | glob --pattern 'src/**/*.py' --from result"
              │
              ▼
         Parser  →  AST
              │
              ▼
         Executor (walks tree, manages scope)
              │
              ▼
         GroverFileSystem methods (read, call, glob, pred, ...)
```

## Design goals

- One MCP tool, one round-trip
- LLM-authored first, human-authored second
- Observable and bounded from day one
- Uniform execution envelope for filesystem ops and tool calls
- Small v1 language with explicit semantics

## Non-goals for v1

- General-purpose programming language features
- Arbitrary Python/JavaScript expression evaluation
- Implicit argument magic
- Hidden fallback from multi-candidate results to the first candidate
- JSON string templating as the primary tool-input mechanism

---

## The `.tools/` Namespace

Tools are code-registered on filesystem instances, never DB-persisted. They live in an in-memory registry on each `GroverFileSystem`, including `AsyncGrover`.

- `read /mount/.tools/name` returns a descriptor
- `call /mount/.tools/name --input {...}` executes the tool
- `ls /mount/.tools` lists registered tools
- `stat /mount/.tools/name` returns metadata
- `glob --pattern "**/.tools/*"` discovers tools across mounts
- `tree /mount/.tools` shows the synthetic hierarchy

Tools are never in semantic/vector search results, never embedded, never versioned, and never written to the DB. They are discoverable through namespace navigation, not through ordinary document retrieval.

### Tool registration

```python
fs.register_tool(
    path="/.tools/get_document",
    protocol="python",               # python | mcp | http | cli
    fn=get_document_impl,            # or adapter config for non-python tools
    input_schema=GetDocumentInput,   # Pydantic model or JSON Schema
    output_schema=GetDocumentOutput,
    description="Retrieve a Google Doc by ID",
    read_only=True,
)
```

Bulk registration for MCP-backed tools:

```python
fs.register_mcp_server(
    prefix="/.tools",
    server="google-drive",
    transport=StdioTransport("npx @google/drive-mcp"),
)
```

This creates synthetic entries such as `/.tools/get_document` and `/.tools/list_documents`.

### ToolSpec

```python
@dataclass(frozen=True)
class ToolSpec:
    path: str
    protocol: Literal["python", "mcp", "http", "cli"]
    input_schema: Any
    output_schema: Any
    description: str
    read_only: bool
    hidden: bool = False
    fn: Callable[..., Any] | None = None
    adapter: Any | None = None
```

### RuntimeContext

The same tool definition must work locally, in a web app server, and in a sandbox.

```python
class RuntimeContext(Protocol):
    async def get_secret(self, name: str) -> str: ...
    async def get_client(self, service: str) -> Any: ...
    @property
    def user_id(self) -> str | None: ...
    @property
    def tenant_id(self) -> str | None: ...
```

- Local: env vars, fresh clients, user filesystem
- Server: vault secrets, pooled clients, audit logging
- Sandbox: restricted secrets, network allow-list

`RuntimeContext` is used by `call()`. The expression language remains transport-neutral.

---

## Execution Envelope

### The problem

`GroverResult` has a specific shape: `success`, `message`, `candidates: list[Candidate]`. Tool calls may return dicts, scalars, lists, or payloads that also create filesystem candidates. The executor needs one uniform result type.

### ExecValue

Every stage yields an `ExecValue`.

```python
@dataclass(frozen=True)
class ExecValue:
    ok: bool
    candidates: list[Candidate]
    value: Any
    error: str | None
    source: str
```

Mapping:

| Source | `ok` | `candidates` | `value` |
|--------|------|--------------|---------|
| `read("/x")` | `result.success` | `result.candidates` | `None` |
| `glob("*.py")` | `result.success` | `result.candidates` | `None` |
| `call("/x/.tools/y", ...)` | `True` if no error | `[]` or synced candidates | tool payload |

### Explicit field access

The language does not use implicit fallback from `result.X` to the first candidate. Access is explicit.

Allowed `ExecValue` fields:

- `result.ok`
- `result.error`
- `result.value`
- `result.candidates`
- `result.first`
- `result.count`
- `result.source`

`result.first` is a derived value: the first candidate, or `null` if none exist.

Examples:

- `result.value.content`
- `result.first.path`
- `result.count`
- `semantic.candidates`

For `item` inside `for-each`:

- if iterating candidates, `item` is a `Candidate`
- if iterating a list payload, `item` is the list element

No indexing, bracket syntax, or arbitrary attribute access in v1.

---

## v1 Command Model

The previous draft mixed positional arguments, candidate chaining, and implicit path resolution in ways that do not match the current `GroverFileSystem` API. v1 needs one explicit command contract.

### Core rule

Commands use one of these input forms:

- a target path, either literal or access-resolved
- `--from ACCESS` for candidate-driven operations
- named flags for query/pattern/option arguments
- `--input VALUE` for tool calls

### Command families

#### Path commands

These target one concrete path:

- `read /x`
- `read item.path`
- `stat /x`
- `ls /x`
- `tree /x --depth 2`
- `rm /x`
- `mkdir /x`
- `call /x/.tools/y --input {...}`

#### Candidate commands

These operate on a prior result set:

- `read --from result`
- `stat --from semantic`
- `pred --from result`
- `succ --from semantic`

#### Query commands

These require explicit query arguments:

- `glob --pattern "src/**/*.py"`
- `glob --pattern "src/**/*.py" --from result`
- `grep --pattern "TODO"`
- `grep --pattern "TODO" --from result`
- `search --query "authentication"`
- `lsearch --query "login timeout"`

#### Set operations

These operate on named bindings only:

- `intersect semantic keyword`
- `union a b`
- `diff all stale`

This keeps the language aligned with Grover's existing result algebra in `GroverResult`.

### Tool inputs

Tool calls do not use JSON string interpolation. Structured input is expressed as values in the language itself.

Good:

```
call /google/.tools/get_document --input {documentId: item.id}
```

Avoid:

```
call /google/.tools/get_document --json '{"documentId": "{{item.id}}"}'
```

This keeps construction typed and avoids quote-heavy string templating.

---

## Expression Language v1

### Vocabulary

Filesystem verbs:

```
read  stat  ls  tree
write edit  rm  mv  cp  mkdir  mkedge
glob  grep  search  lsearch
pred  succ  anc  desc  nbr  meet  pagerank
call
intersect union diff
```

CLI aliases like `rm`, `mv`, and `cp` may map to `delete`, `move`, and `copy` internally.

### Syntax by example

Simple pipeline:

```
search --query "authentication"
| glob --pattern "src/**/*.py" --from result
| read --from result
```

Tool call:

```
call /google/.tools/get_document --input {documentId: "abc123"}
```

Loop with conditional:

```
call /google/.tools/list_documents --input {folderId: "abc123"}
| for-each result.value {
  call /google/.tools/get_document --input {documentId: item.id}
  | if result.value.content contains "quarterly" {
    call /salesforce/.tools/update_record --input {
      objectType: "SalesMeeting",
      recordId: item.prospectId,
      data: {Notes: result.value.content}
    }
  }
}
```

Named bindings:

```
read /config/rules.json as config
| glob --pattern "src/**/*.py"
| for-each result.candidates {
  read item.path
  | grep --pattern config.first.content --from result
}
```

Set algebra:

```
search --query "authentication" as semantic
| grep --pattern "login" as keyword
| intersect semantic keyword
| pred --from result
```

Nested loops:

```
glob --pattern "/projects/*"
| for-each result.candidates {
  ls item.path
  | for-each result.candidates {
    read item.path
    | if result.first.content contains "TODO" {
      call /slack/.tools/post --input {
        channel: "todos",
        message: item.path
      }
    }
  }
}
```

### Key syntax decisions

- `result` always means the previous stage
- named bindings created with `as name` are the only way to reach back further
- `item` is only valid inside `for-each`
- `for-each` requires an explicit iterable source
- pipelines fail fast
- `for-each` collects per-item errors and returns an aggregate result

---

## Grammar

```
program     = pipeline

pipeline    = stage ( "|" stage )*

stage       = command
            | for_each
            | if_else
            | set_op

command     = VERB target? arg* ( "as" NAME )?

target      = PATH | access

for_each    = "for-each" access "{" pipeline "}"

if_else     = "if" expr "{" pipeline "}" ( "else" "{" pipeline "}" )?

set_op      = ( "intersect" | "union" | "diff" ) NAME NAME

arg         = "--from" access
            | "--input" value
            | "--query" value
            | "--pattern" value
            | "--path" value
            | "--depth" NUMBER
            | "--k" NUMBER
            | "--" KEY value?

value       = STRING
            | NUMBER
            | BOOLEAN
            | "null"
            | access
            | object
            | array

object      = "{" ( pair ( "," pair )* )? "}"
pair        = KEY ":" value

array       = "[" ( value ( "," value )* )? "]"

access      = NAME ( "." NAME )*

expr        = or_expr
or_expr     = and_expr ( "or" and_expr )*
and_expr    = unary ( "and" unary )*
unary       = "not" unary | atom
atom        = access "contains" value
            | access "matches" STRING
            | access ( "==" | "!=" | ">" | "<" ) value
            | access
            | "(" expr ")"

VERB        = "read" | "stat" | "ls" | "tree"
            | "write" | "edit" | "rm" | "mv" | "cp" | "mkdir" | "mkedge"
            | "glob" | "grep" | "search" | "lsearch"
            | "pred" | "succ" | "anc" | "desc" | "nbr" | "meet" | "pagerank"
            | "call"

NAME        = [a-zA-Z_][a-zA-Z0-9_]*
KEY         = NAME
```

This is still small, but it removes the undefined positional forms from the previous draft.

---

## AST

```
Program
└── Pipeline           stages: list[Stage]

Stage (union)
├── Command            verb: str, target: PathLiteral | Access | None, args: list[Arg], as_name: str?
├── ForEach            source: Access, body: Pipeline
├── IfElse             cond: Expr, then_: Pipeline, else_: Pipeline?
└── SetOp              op: "intersect" | "union" | "diff", left: str, right: str

Arg (union)
├── FromArg            source: Access
├── InputArg           value: Value
├── QueryArg           value: Value
├── PatternArg         value: Value
├── PathArg            value: Value
├── DepthArg           value: int
├── KArg               value: int
└── KeyValueArg        key: str, value: Value | None

Value (union)
├── StringLiteral      value: str
├── NumberLiteral      value: int | float
├── BoolLiteral        value: bool
├── NullLiteral
├── AccessValue        parts: list[str]
├── ObjectLiteral      pairs: list[(str, Value)]
└── ArrayLiteral       items: list[Value]

Expr (union)
├── Access             parts: list[str]
├── Contains           left: Expr, right: Value
├── Matches            left: Expr, pattern: str
├── Compare            left: Expr, op: "==" | "!=" | ">" | "<", right: Value
├── Not                inner: Expr
├── And                left: Expr, right: Expr
└── Or                 left: Expr, right: Expr
```

---

## Execution Model

### Scope

```python
@dataclass
class Scope:
    bindings: dict[str, ExecValue]
    result: ExecValue | None
    item: Candidate | Any | None
```

- `result` is rebound after every stage
- `item` exists only inside `for-each`
- named bindings persist for the enclosing pipeline
- inner pipelines inherit bindings but get their own `result`

### Pipeline execution

```
execute_pipeline(stages, scope):
  for stage in stages:
    exec_value = execute_stage(stage, scope)
    scope.result = exec_value
    if stage is Command with as_name:
      scope.bindings[as_name] = exec_value
    if exec_value.ok is False and stage is not ForEach:
      return exec_value
  return scope.result
```

### Command execution

```
execute_command(cmd, scope):
  resolve target and args against scope
  dispatch to the matching Grover method
  wrap the result in ExecValue
  return
```

Important rule: command dispatch is explicit. Examples:

- `read /x` -> `fs.read(path="/x")`
- `read item.path` -> `fs.read(path=resolve_path(item.path))`
- `read --from result` -> `fs.read(candidates=unwrap_candidates(result))`
- `glob --pattern "*.py" --from result` -> `fs.glob(pattern="*.py", candidates=unwrap_candidates(result))`
- `pred --from semantic` -> `fs.predecessors(candidates=unwrap_candidates(semantic))`
- `call /x/.tools/y --input {...}` -> `fs.call(path="/x/.tools/y", params=...)`

### ForEach execution

```
execute_for_each(node, scope):
  iterable = evaluate_access(node.source, scope)
  results = []
  for element in iterable:
    child_scope = scope.copy()
    child_scope.item = element
    child_scope.result = None
    results.append(execute_pipeline(node.body, child_scope))
  return merge_for_each(results)
```

This removes the ambiguous `candidates or value` precedence from the previous draft. The iterable source is always explicit.

### IfElse execution

```
execute_if(node, scope):
  if evaluate_expr(node.cond, scope):
    return execute_pipeline(node.then_, scope.copy())
  elif node.else_:
    return execute_pipeline(node.else_, scope.copy())
  return scope.result
```

### Expression evaluation

```
evaluate_expr(expr, scope):
  Contains(left, right) -> str(eval(right)) in str(eval(left))
  Matches(left, pattern) -> fnmatch(str(eval(left)), pattern)
  Compare(left, op, right) -> eval(left) <op> eval(right)
  Not(inner) -> not eval(inner)
  And(left, right) -> eval(left) and eval(right)
  Or(left, right) -> eval(left) or eval(right)
```

The previous draft had `contains` backwards. v1 uses normal left-contains-right semantics.

---

## Execution Controls

Every invocation accepts execution bounds:

```
grover --timeout 30s --max-steps 500 --max-fanout 50 \
  "search --query 'auth' | for-each result.candidates { read item.path }"
```

| Control | Default | Meaning |
|---------|---------|---------|
| `timeout` | 60s | Total wall-clock time |
| `max_steps` | 1000 | Total command executions |
| `max_fanout` | 100 | Maximum iterations in one `for-each` |

Exceeding a limit returns `ExecValue(ok=False, ...)` with partial results retained where possible.

### Step trace

Every execution produces a trace:

```python
@dataclass
class StepRecord:
    index: int
    command: str
    ok: bool
    duration_ms: int
    candidates_out: int
    error: str | None
```

This keeps single-round-trip execution observable for both humans and models.

---

## Mapping to the Filesystem Layer

The expression language remains outside the filesystem, but `.tools` support requires concrete filesystem hooks.

| Addition | Where | Notes |
|----------|-------|-------|
| `_tools: dict[str, ToolSpec]` | `GroverFileSystem` | In-memory registry |
| `register_tool()` | `GroverFileSystem` | Adds one tool |
| `register_mcp_server()` | `GroverFileSystem` | Discovers and bulk-registers tools |
| `call()` public method | `GroverFileSystem` | Single-path routing like `read` |
| `_call_impl()` | Override point | Resolves the tool and dispatches |
| synthetic `.tools` support in `read` | descriptor rendering | no DB query |
| synthetic `.tools` support in `ls` | list names | no DB query |
| synthetic `.tools` support in `stat` | tool metadata | no DB query |
| synthetic `.tools` support in `glob` | discoverability | in-memory match |
| synthetic `.tools` support in `tree` | hierarchy rendering | in-memory children |
| search exclusion | routing/search layer | tools are never embedded or semantically searched |

The parser, AST, executor, `ExecValue`, `Scope`, and `StepTrace` live in a separate `grover/executor/` or `grover/cli/` package.

---

## What's deferred

- sandbox isolation and network policy
- typed code export such as `grover export-tools --lang ts`
- dynamic Python proxy objects such as `tools.google.get_document(...)`
- workflow storage, where expression programs become tools
- parallel execution
- retries and structured error handlers
- indexing and bracket syntax for payload access

These are useful, but not required for a coherent v1.

---

## References

- [Anthropic: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [everything_is_a_file.md](/Users/claygendron/Git/Repos/grover/docs/plans/everything_is_a_file.md)
- [grover_filesystem_base_class.md](/Users/claygendron/Git/Repos/grover/docs/plans/grover_filesystem_base_class.md)
- [results.py](/Users/claygendron/Git/Repos/grover/src/grover/results.py)
- [protocol.py](/Users/claygendron/Git/Repos/grover/src/grover/protocol.py)
