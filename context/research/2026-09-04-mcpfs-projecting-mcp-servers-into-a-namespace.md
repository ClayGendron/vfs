# mcpfs: projecting an MCP server into a namespace, and what vfs should take from it

- **Status**: research memo (commits us to nothing; feeds roadmap item
  020 (remote backends over `mcp+stdio://` / `mcp+http://`), the
  re-spec of archived draft 034 (MCP-native mounts), and the `run`
  verb's tools-at-paths story)
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: mcpfs has one rule for turning *any* MCP server into a
  directory tree: classify each tool as a read or a write; a list tool
  with no required parameters becomes a file; a get tool with a required
  id becomes a directory; create/update/delete/search tools are kept off
  the filesystem and exposed only through a CLI; MCP resources mount as
  files too. What exactly is that rule, how does it handle parameters,
  pagination, caching, errors and freshness, and what should vfs take
  from it for an MCP mount and for tools at paths?
- **Method**: a line-level read of the whole `airshelf/mcpfs` checkout
  at `~/Git/Repos/mcpfs` (every Go file — `internal/toolfs/classify.go`,
  `internal/toolfs/tree.go`, `internal/fuse/fs.go`,
  `internal/fuse/toolnode.go`, `internal/fuse/cache.go`,
  `pkg/mcpclient/{client,http,types}.go`,
  `pkg/mcptool/{dispatch,schema,call_stdio,call_http}.go`,
  `internal/config/config.go`, `cmd/mcpfs/{main,auto}.go` — plus the
  tests, `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/gateway-design.md`,
  `bench/README.md`), with `grep` checks for what the code does *not*
  do (tool annotations, `isError`, `nextCursor`, attribute timeouts,
  cache wiring). Then a read of the vfs seams the comparison lands on:
  `src/vfs/ops.py`, `src/vfs/base.py` (`run`), `src/vfs/storage/
  protocol.py` (`SupportsRun`, `capabilities()`, `TransportError`),
  `src/vfs/paths.py` (`/.agents/tools`), `src/vfs/skills.py`,
  `src/vfs/models/entry.py`, `context/standards/roadmap.md` (020),
  archived specs 034 and 039, ADR 022 / spec 054, ADR 058,
  `context/research/2026-08-10-mcp-2026-07-28-stateless-revision.md`
  (§1, §6, §8.2), and the Mirage memo (§3.15, §4.7). Cites and
  describes only — every line of vfs code stays ours.
- **License**: MIT (`LICENSE`, "Copyright (c) 2026 AirShelf"). Study
  freely; copy nothing.
- **Sources line**: `airshelf/mcpfs` @ `640511e` (2026-03-06), 44
  commits, all between 2026-03-04 and 2026-03-06, one author. Go:
  2,742 source lines, 2,639 test lines; one dependency
  (`hanwen/go-fuse/v2 v2.9.0`). Hard-codes MCP `protocolVersion`
  `2025-03-26`. No tagged release; public numbers not checked. The
  checkout has not moved in six months.

---

## 1. Bottom line

mcpfs is a three-day, one-author, 2.7 k-line Go prototype. It is small
and early. Its one idea is still worth a memo: **a read-shaped tool can
be shown as a file, and a write-shaped tool should not be.** vfs's
own design already draws the same line, from the other direction: in
vfs every tool is a *path* you `run`, and spec 034 (archived draft)
says a tool's *definition* becomes a `TOOL.md` file. mcpfs says a tool's
*result* becomes a file. Those are different projections. The first is
what vfs has decided; the second is a view layer vfs does not have yet.

Three findings decide the verdicts:

1. **The classification is a name heuristic, and its fall-through is
   unsafe.** Four verb lists plus one JSON Schema check
   (`classify.go:33-53`). A tool whose verb is not in any list and that
   takes no required parameter becomes a **file**, and that file's tool
   is **executed by `stat`** (`toolnode.go:44-54`). So `ls -l` on a
   mount of a server with a `deploy` or `restart` tool runs it. MCP
   already ships declared facts for this decision — `readOnlyHint`,
   `destructiveHint`, `idempotentHint` on every tool — and mcpfs reads
   none of them. vfs decided in spec 034 that "tool names are not a
   contract" and that a mount's shape comes from a *declaration*. Keep
   that. The mcpfs heuristic is a generator for *proposing* rows, never
   the thing that binds them (§4.1).
2. **The two-class split maps onto vfs as `read` versus `run`, and vfs's
   shape is the better one.** mcpfs sends every write to a CLI that
   opens a *separate* MCP session outside the mount (`main.go:296-317`),
   so nothing in the namespace ever sees a write, gates it, or
   invalidates for it. In vfs a write-class tool is a path under
   `/.agents/tools/<name>` and `run` is the one verb that executes it,
   through the same gate every verb passes (`base.py` `run`,
   `ops.py` `EXEC_OPS`, `deny_ops`). What to lift is the *declared*
   read/write class riding on the tool's own annotations into
   `TOOL.md` and into `stat`, so a read-only mount can be told apart
   from a destructive one by a fact the server stated (§4.2).
3. **A tool-backed file cannot be honest about size or freshness the
   way mcpfs does it.** mcpfs answers `stat` by running the tool and
   measuring the bytes; a failed call reports a healthy empty file
   (`toolnode.go:44-54`); every `read()` chunk runs the tool again
   (`toolnode.go:60-74`, pinned by its own test); the TTL cache exists
   as a type and is never constructed (`cache.go`; no caller). The
   2026-07-28 MCP revision states the rule mcpfs breaks: `resources/read`
   is cacheable with a required `ttlMs`, and `tools/call` is *not*
   cacheable. For vfs this fixes three things: `stat` on a view path
   must never execute; size must be allowed to be **unknown** (today
   `Entry.size_bytes` is `int = 0` and cannot say so); freshness must
   be a declared, structured fact per row, not an accident of the
   kernel page cache (§4.3).

The declarative version of mcpfs's rule is a **scope table** — one
per-mount description of which paths exist, which tool or resource backs
each, how path segments bind to arguments, and what freshness and size
policy each row carries — the same shape Mirage's hierarchy kit uses
(Mirage memo §3.15), and the same "every verb classifies through one
table" invariant vfs already holds for its SQL backend (§4.1).

One line: **take the read-versus-write split as a declared fact, take
the scope-table shape for read-shaped views, keep `run` for everything
else, and do not take the name heuristic, the call-on-stat, or the
side-door CLI.**

---

## 2. What mcpfs is

**Terms used below.** *FUSE* is the kernel interface that lets a user
process answer filesystem calls (`readdir`, `stat`, `read`). *MCP tool*
is a callable a server lists under `tools/list` with a JSON Schema for
its input. *MCP resource* is a readable thing a server lists under
`resources/list` with a URI; a *resource template* is a URI with `{param}`
holes. *`required`* is the JSON Schema list of parameter names a caller
must supply.

**Shape.** One Go binary. It connects to one MCP server (a subprocess
over stdio, or an HTTP endpoint), asks it for resources, resource
templates and tools, builds an in-memory tree, and serves that tree over
FUSE (`fs.go:411-511`). Reads are files. Writes are a subcommand,
`mcpfs tool <server> <tool> --flag value`, that opens its own connection
to the server and calls the tool (`main.go:245-333`). A config file in
Claude Desktop's `mcpServers` shape mounts many servers at once
(`config.go`, `main.go:364-414`), and `mcpfs auto` discovers servers
from Claude Code's own config, plugin cache and OAuth credential file
and mounts them under `.mcpfs/` in the current directory (`auto.go`).

**The bet.** From `AGENTS.md`: "`ls` costs 0 tokens. MCP tool schemas
cost 20,000+ tokens. `cat | jq` is one universal query language.
Unix pipes compose across services." The design doc frames it as a
gateway — "one binary mounts any MCP server, no per-server Go code"
(`docs/gateway-design.md`), replacing eleven hand-written per-service
servers the project started with two days earlier.

**Size and maturity, honestly.** 44 commits in three days by one
author. The FUSE layer is 511 lines, the classifier 133, the CLI bridge
about 400, the two MCP clients about 430. Tests are unit tests over
tree-building, flag parsing and the clients against a fake server;
there is no end-to-end FUSE test. The design doc promises things the
code does not do (§3.2). The repo is a sketch of an idea, and the idea
is the part worth reading.

**How it differs from vfs in one table.**

| | mcpfs | vfs |
| --- | --- | --- |
| Unit of truth | a FUSE call (`stat`, `read`) | a verb call, `paths in → Result out` |
| What a tool becomes | its *result*, as a `.json` file (reads only) | its *definition*, as `/.agents/tools/<name>/TOOL.md`; `run` executes it (spec 034, `paths.py`) |
| Read/write split | name heuristic + `required` check | declared: `READ_OPS` vs `EXEC_OPS` vs `MUTATING_OPS` (`ops.py`); `deny_ops` per mount |
| Where writes go | a CLI with its own session, outside the mount | `run` at the path, through the router's gate |
| Freshness | none declared; kernel page cache; dead TTL type | declared traits (`grep_staleness`, `glean_staleness`); no tool-backed view yet |
| Errors | `EIO` on read; empty file on `stat` | classified `Result` kinds (`backend_unavailable`, `unsupported`, `truncated`) |
| MCP version | `2025-03-26`, handshake + `Mcp-Session-Id` | targets the 2026-07-28 stateless revision (memo 2026-08-10) |

---

## 3. The projection rule and its mechanics

All paths are under `~/Git/Repos/mcpfs` @ `640511e`.

### 3.1 The classification rule, exactly

`ClassifyTool(name, inputSchema)` (`internal/toolfs/classify.go:33-53`)
returns one of four classes (`:9-16`): `ToolList` ("no required params,
read-only → static file"), `ToolGet` ("has required params, read-only →
template dir"), `ToolWrite` ("mutating → CLI only"), `ToolQuery`
("search/query → CLI only"). The predicates run in this order and the
first hit wins:

1. Split the name into *segments*: lowercase, `_` → `-`, split on `-`
   (`splitSegments`, `:55-60`). Matching is whole-segment, never
   substring (`segmentsMatchAny`, `:62-72`).
2. Any segment in `{create, update, delete, remove, add, set, patch,
   put, post}` → **write** (`:36`).
3. Any segment in `{search, query, find, run, execute}` → **query**
   (`:39`).
4. Top-level `required` list empty → **list** (`:43-46`).
   `RequiredParams` (`:86-95`) reads only the schema's top-level
   `required`; it ignores `properties`, nested objects, `oneOf`/`anyOf`.
5. Any segment in `{get, retrieve, read, show, describe}` → **get**
   (`:48`).
6. Otherwise → **write**, commented "safe default" (`:52`).

Only list and get tools enter the tree; write and query are dropped at
mount time (`fs.go:431-434`). Naming: `ToolToFilename` (`classify.go:
76-83`) strips a verb affix (`stripVerb`, `:98-123`: suffixes `-get-all`
and `-list` pluralize the rest; `-retrieve`/`-get` do not; prefixes
`list-`, `get-all-`, `retrieve-all-`, `get-`, `retrieve-` are removed)
and then a list tool gets `.json` while a get tool is pluralized into a
directory name (`pluralize`, `:125-133`: append `s` unless the name
already ends in `s`). So `dashboards-get-all` → `dashboards.json` and
`dashboard-get` → `dashboards/`, side by side.

**Edge cases the tests admit** (`classify_test.go`): `get-settings` with
no required params is a list, because segment matching keeps `set` from
matching `settings` (`:107-120`); `list_updates` likewise (`:131-138`);
`retrieve_balance` with no params → `balance.json` (`:37`, `:60`);
`show-config` → list; `frobulate-widget` *with* a required param → write,
"safe default" (`:147-162`); `get_commit(owner, repo, sha)` → get
(`:122-129`); `status` pluralizes to `status` (`:223-237`).

**Edge cases neither the code nor the README admits:**

- **Step 4 runs before step 5.** An unknown verb with *no* required
  parameters is a **file**, not a "safe default". `deploy`, `restart`,
  `sync`, `purge_cache`, `rotate_token`, `send_digest` — any
  parameterless action whose verb is not in the write or query lists —
  is mounted as `deploy.json` and executed by the next `stat` (§3.3).
  The "safe default" comment on step 6 is true only for tools that take
  arguments.
- **Tool annotations are ignored.** MCP `2025-03-26`, the version mcpfs
  pins, defines `annotations.readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint` on every tool. `grep` finds no
  occurrence of any of them in the repo. The one declared fact that
  answers the read/write question is never consulted.
- **`run` and `execute` are query verbs** (`:39`). vfs's own execution
  verb is named `run`; a vfs server mounted by mcpfs would have its
  `run` tool hidden behind the CLI, which is the right outcome by
  accident.
- **`read` is a get verb** (`:48`). A `read_file(path)` tool becomes a
  `files/` directory whose child names are whatever the caller types —
  path segments become the argument, so a slash in the id is
  unrepresentable.
- **Name collisions overwrite silently.** `BuildToolTree` is a map keyed
  by filename (`tree.go:19-35`); `get_user` and `retrieve_user` both
  become `users/` and the last one wins. When a tool's filename matches a
  resource's, the resource wins and the tool is dropped without a log
  line (`fs.go:463-468`).
- **`required` is the only schema fact read.** A tool with one optional
  `limit` and a required `data` object is a get whose directory binds
  `data` to a path segment as a string.

### 3.2 The path scheme

**Tool-backed entries are flat.** Every list tool is a file at the mount
root; every get tool is a directory at the mount root
(`fs.go:463-480`). There is no nesting by resource family.

**A get directory binds one parameter.** At mount time the directory
node records `param = RequiredParams[0]` and `toolParams =
RequiredParams` (`fs.go:474-477`). `Lookup` on a child name inside that
directory (`fs.go:241-259` → `lookupTemplateChild`, `:291-342`) sets
`params[param] = name` (`:293`) and, because a tool-backed directory has
no static children, returns a **file** node whose call arguments are
exactly that one binding (`:296-308`). So for
`get_commit(owner, repo, sha)` the design doc promises
`commits/{owner}/{repo}/{sha}.json` (`docs/gateway-design.md`, table
row "Get (2+ required params)"), but the code serves `commits/<owner>`
as a file whose `tools/call` sends `{"owner": "<owner>"}` and nothing
else. The only test for the multi-parameter case checks that three
names were recorded, not what a read sends (`tree_test.go:157-173`).

**A get directory lists nothing.** `Readdir` iterates the static
children map (`fs.go:205-226`); a tool-backed directory has none, so
`ls dashboards/` is empty. Ids are not enumerable; the reader must learn
them from the sibling list file and type them. Nothing links the two
tools.

**Resources.** A static resource's URI is split after `scheme://`
(scheme sniffed from the first resource, `fs.go:450-459`), each `/`
segment becomes a directory, and the leaf gets `.json` unless the MIME
type is `text/plain` (`fs.go:81-96`). A resource template's `{param}`
segment becomes a parameter directory; a second `{param}` beneath it is
supported one level deep (`registerTemplateTail`, `:138-163`;
`registerNestedTail`, `:165-185`), and a template's trailing literal
segments become files inside the resolved directory. Resources take
priority over tools on a name clash (`:466-468`). Resource templates
are the one place mcpfs handles nested parameters properly — and the
tool path does not reuse that code.

**Nested parameters, summarized.** Resource templates: two levels.
Tools: one, and the design doc's three-level example is not
implemented.

### 3.3 How a read is served

The FUSE call sequence for `cat customers.json` is: `Lookup` (no call —
it only mints an inode, `fs.go:274-282`), `Getattr`, `Open`, one or more
`Read`. mcpfs runs the tool on two of those:

- **`Getattr` executes the tool** to learn the size
  (`toolnode.go:44-54`). On error it logs, reports **size 0**, and
  returns success — a broken or refused tool stats as a healthy,
  empty, readable file (mode `0444`). The same shape for resource files
  (`fs.go:355-365`).
- **`Open`** returns `FOPEN_KEEP_CACHE` (`toolnode.go:56-58`), which
  asks the kernel to keep page-cache pages across opens.
- **Every `Read` executes the tool again** and slices the rendered bytes
  at the requested offset (`toolnode.go:60-74`). A response larger than
  one kernel read (128 KiB on Linux) is fetched once per chunk, from
  fresh calls, so a listing that changes mid-`cat` is torn. The unit
  test pins this: two `readData` calls, two tool calls, "no caching in
  toolFileNode" (`toolnode_test.go:108-135`).
- **Rendering** pretty-prints the tool's text as JSON if it parses,
  else passes it through, and appends a newline (`toolnode.go:30-42`).

Consequences: `cat` is at least two tool calls; `ls -l` at the mount
root is one tool call **per list tool**, because `ls -l` stats every
entry; `stat` is a side-effecting operation on any tool that is not
idempotent.

**Caching.** `internal/fuse/cache.go` defines a TTL `Cache` with a
background sweeper. `NewCache` has no caller anywhere in the repo. No
`AttrTimeout` or `EntryTimeout` is set on the mount options
(`fs.go:496-502`), so the kernel does not cache attributes either. What
freshness a reader gets is whatever the page cache does under
`FOPEN_KEEP_CACHE` — mcpfs neither declares nor controls it. A write
made through `mcpfs tool` invalidates nothing, because it runs in a
different process with a different session (§3.4).

**Errors.** A JSON-RPC error (`client.go:87-89`, `http.go:100-102`,
`:121-123`) becomes a Go error, which `Read` turns into `EIO`
(`toolnode.go:63-64`) and `Getattr` turns into an empty file. A tool
result with `isError: true` is **not** an error: `CallTool` parses only
`content` (`client.go:191-204`, `http.go:181-190`), so the error text
becomes the file's body. Only `content[0].text` is used; further
content blocks are dropped; `structuredContent` is never read; a
non-text first block yields `{}`.

**Pagination.** None. `tools/list`, `resources/list` and
`resources/templates/list` are called once with `{}`; `nextCursor` has
no occurrence in the repo. A list tool is called with `{}` — no page
argument — and whichever page the server returns *is* the file, with
no signal that more exists.

### 3.4 Writes: the CLI path

`mcpfs tool <server> [tool] [--flags]` (`main.go:245-333`) loads
`servers.json`, exports the server's `env` into the process
(`os.Setenv`, `:306-308`), **opens a new MCP session** — a fresh
subprocess for stdio, a fresh `initialize` for HTTP (`:296-317`) — lists
tools, and dispatches (`pkg/mcptool/dispatch.go:19-64`).

- No tool name, or `--help` → the tool list to stderr, sorted, with
  descriptions cut at 80 characters (`:20-23`, `:75-86`).
- `<tool> --help` → the flag list derived from the schema (`:88-111`).
- Flags come from `ParseSchema` (`schema.go:36-58`): one flag per
  top-level property; `Type`, `Description`, and `Required` from the
  schema. A schema whose single property is a `data` object is flattened
  so its inner properties become the flags, and the call re-wraps them
  (`schema.go:60-72`, `dispatch.go:43-47`) — a PostHog convention, not
  an MCP one.
- `parseFlags` (`dispatch.go:113-202`): `--flag value` or `--flag=value`;
  unknown flag is an error; `boolean` needs no value; `integer` and
  `number` are parsed; `array` is comma-split into strings; `object` is
  raw JSON; anything else is a string; every `required` flag must be
  present. Nested schemas beyond the `data` wrapper are "paste JSON".
- Output: the first content block, pretty-printed if JSON, to stdout;
  hints and errors to stderr; exit 0 or 1 (`:49-63`).

Any tool can be called this way, including the ones mounted as files.
The CLI is the whole write surface and it never touches the mount.

### 3.5 Transport, sessions, auth

**stdio** (`pkg/mcpclient/client.go`). Spawns the server with stderr
inherited (`:25-27`); newline-delimited JSON-RPC; one mutex held across
write-and-read, so calls are fully serialized (`:56-92`). The reader
loop skips any line that does not parse or whose id does not match
(`:80-85`) — server notifications *and server-to-client requests* are
silently dropped, so a server that asks for sampling or elicitation
hangs its own call. Sends `initialize` with `protocolVersion`
`2025-03-26` and then `notifications/initialized` (`:94-113`). `Close`
kills the process (`:208-212`).

**HTTP** (`pkg/mcpclient/http.go`). One POST per request with
`Accept: application/json, text/event-stream` (`:52-53`) and the
configured headers (`:54-56`). Captures `Mcp-Session-Id` from any
response and replays it (`:57-61`, `:69-73`). For an SSE body it takes
the first `data:` line that parses as a JSON-RPC response (`:85-108`),
without matching ids. Every request after `initialize` uses JSON-RPC
`id: 1` (`:130`, `:145`, `:160`, `:175`, `:196`). `notifications/
initialized` is never sent on HTTP (`:32-44`). No GET stream, no
`DELETE` on close (`:216`). HTTP status ≥ 400 becomes an error carrying
the first 200 body bytes (`:75-82`). `pkg/mcptool/call_http.go` is a
second, near-duplicate HTTP client for the CLI.

**Auth.** `--auth` sets the `Authorization` header (`main.go:139-143`,
`:163-166`). Config headers and env values interpolate `${VAR}` from the
process environment (`config.go:47-60`), loaded from
`~/.config/mcpfs/env`, then `.env.local` / `.env` in the current
directory, then Claude Code's `~/.claude/.credentials.json` OAuth tokens
and `gh auth token` (`auto.go:15-48`). Servers with no token are skipped
(`auto.go:160-171`). One consequence worth naming: `runConfig` sets each
server's `env` with `os.Setenv` inside a per-server goroutine
(`main.go:391-393`), and `exec.Command` inherits the whole process
environment, so every stdio server spawned after the first inherits
every other server's secrets.

### 3.6 Which MCP it targets

`2025-03-26`, hard-coded in three places (`client.go:96`, `http.go:37`,
`call_http.go:71`). That is the handshake-and-session shape. Against the
2026-07-28 stateless revision (memo 2026-08-10, §1): `initialize`,
`notifications/initialized` and `Mcp-Session-Id` are gone; every request
carries its version and capabilities in `_meta`; server-initiated
requests are replaced by multi-round-trip results. mcpfs's HTTP client —
one self-contained POST per call, ids never correlated, session id
treated as optional — is closer to the new shape than its stdio client,
by accident rather than design. Two facts from the revision bear on the
design question directly (memo §6): `resources/read` is a
`CacheableResult` with a **required** `ttlMs`, and `tools/call` is
**not** cacheable. The spec itself says a resource is a thing with a
freshness and a tool call is not.

---

## 4. Mapping onto vfs

Legend: **adopt** — take the concept now, in vfs's own shape; **adapt**
— take it when the roadmap reaches the consumer; **parity** — vfs
already has it, sometimes better; **skip** — a consequence of a bet vfs
did not make.

| # | mcpfs mechanism | vfs today | Verdict |
| --- | --- | --- | --- |
| 3.1 | read/write split of a tool catalog | `READ_OPS` / `EXEC_OPS` / `MUTATING_OPS`; `deny_ops` per mount | parity in principle; **adopt** the declared per-tool class from annotations (§4.2) |
| 3.1 | verb-name heuristic decides file vs directory vs CLI | spec 034: "tool names are not a contract"; shape by declaration | **skip** as a binding rule; adapt as a *proposal generator* (§4.1) |
| 3.1 | unknown parameterless verb → file, run on `stat` | denied/unknown execution classifies `unsupported`; fail closed | skip; vfs's direction is right |
| 3.2 | list tool → `<name>.json`; get tool → `<names>/<id>` | no tool-backed view paths; tools are `/.agents/tools/<name>` | **adapt** as a per-mount scope table (§4.1) |
| 3.2 | first required param only; get dirs list nothing | — | adapt with the fix: every slot bound, enumeration declared (§4.1, §4.3) |
| 3.2 | resources → files, templates → param dirs | spec 034 leaves resources out of scope | **adapt**: resources are the honest file-shaped half (§4.1) |
| 3.3 | `stat` executes the tool; failure = empty file | `stat` is a read; `Entry.size_bytes: int = 0` | **adopt** the rule "stat never executes"; fix unknown size (§4.3) |
| 3.3 | no declared freshness; dead TTL cache | `*_staleness` traits exist; no cache layer yet | adapt: freshness as a declared per-row fact (§4.3) |
| 3.3 | tool error → `EIO`; `isError` becomes content | classified kinds; `TransportError` → `backend_unavailable` | parity; add the `run`-result kinds (§4.3) |
| 3.3 | no pagination; a page is the file | memo 2026-08-10 §8.2: opaque cursor as an argument | adapt; surface `truncated` (§4.3) |
| 3.4 | CLI with its own session; flags from JSON Schema | `cli` re-enters verbs; `run(path, arguments)` | parity for the path; **adopt** flag derivation for `cli run` (§4.2) |
| 3.5 | stdio + HTTP clients, session id, header auth | roadmap 020: `VFSTransport`, `mcp+stdio://`, `mcp+http://` | parity; target the stateless revision, not `2025-03-26` (§4.4) |
| 3.5 | secrets via process env, leaked across servers | — | skip; per-mount credentials never touch the process env |
| 3.6 | pinned to `2025-03-26` | memo 2026-08-10 | cautionary; see §4.4 |
| — | "`ls` is cheaper than 20 k tokens of schemas" | spec 034's whole premise: tools as discoverable files, loaded on demand | parity |

### 4.1 (a) Is the heuristic a good default? No. The declarative version is a scope table.

**Why not the heuristic.** Three reasons, each already a vfs rule.

- **vfs decided that names carry no contract.** Spec 034: "A generic MCP
  server may expose a tool named `read` whose arguments and result shape
  are unrelated to VFS's `read`. ... Conformance to the VFS protocol
  must be a *declared* fact, never inferred from a coincidence of
  naming." The same logic covers "a tool named `list_x` is a harmless
  read." It usually is. "Usually" is not a mount-time contract.
- **The fail direction is wrong.** vfs fails closed: an op a backend
  did not declare is `unsupported` and never dispatched
  (`protocol.py` docstring; `_gate_entry`). mcpfs's rule fails *open*
  for the one case that matters — an unrecognized parameterless tool
  becomes a file and `stat` runs it (§3.1, §3.3).
- **The server already says what mcpfs guesses.** `readOnlyHint` and
  `destructiveHint` are per-tool declared facts in the very MCP version
  mcpfs pins. A projection rule that ignores a declared fact to guess
  from a name is backwards.

**What to keep from it.** The *shape* of the output is right: some
tools are data-shaped (a listing, a lookup by id) and reading them as a
file is genuinely useful for an agent — `cat` and `grep` over a
customer list beats a tool call with a 20 k-token schema, which is
vfs's own thesis. So the heuristic survives as a **generator that
proposes rows for a human or a mount config to accept**, exactly like
`mcpfs auto --json` is a dry run that prints what it would mount. It
never binds a path on its own.

**The declarative version.** A *scope table* is one description, per
mount, of the fixed tree an API-backed mount presents. Mirage's
hierarchy kit is the worked example (Mirage memo §3.15): a tuple of
scopes, each a sequence of literal segments and typed *slots*; a slot
has a codec (suffix, validator) and binds one argument; one compiled
classifier serves `readdir`, `stat`, `read` and search "so the file
surface and the search surface cannot disagree about what a path
means." vfs already holds that invariant for its SQL backend by sharing
one `scope` module across the verbs. For an MCP mount the rows would
say, for each view path:

| path pattern | source | bindings | enumerate from | freshness | size |
| --- | --- | --- | --- | --- | --- |
| `customers.jsonl` | tool `list_customers` | `{}` | — | `ttl: 30s` (declared by mounter) | unknown until read |
| `customers/{customer_id}.json` | tool `retrieve_customer` | `customer_id ← segment 1` | `list_customers`, id field `id` | `ttl: 30s` | unknown until read |
| `commits/{owner}/{repo}/{sha}.json` | tool `get_commit` | three slots, in order | none (not enumerable) | `none` | unknown |
| `readme.md` | resource `repo://acme/app/README.md` | uri | — | `ttlMs` from the server | from `resources/read` |
| `/.agents/tools/<name>/TOOL.md` | every tool (spec 034) | — | `tools/list` | `tools/list.ttlMs` | known (stored) |

Rules the table carries that mcpfs's code does not:

- **Every required slot binds, in order, or the row is refused at mount
  time.** No first-param-only. A template with three slots is three
  directory levels.
- **A directory row that is not enumerable says so.** Either it names
  the list tool and id field it enumerates from, or `ls` on it returns
  a classified `unsupported`-family result rather than an empty
  listing. Mirage's `entry_listers` and `partial` flags are the same
  idea.
- **Resources are rows by default; tools are rows by opt-in.** A
  resource is what MCP *calls* a file — it has a URI, a MIME type, and
  (since 2026-07-28) a `ttlMs`. Spec 034 left resources out of scope;
  this memo says they are the easy, honest half of the projection and
  should come first. A tool row is accepted only when the mounter
  writes it (or accepts the generator's proposal) *and* the tool's
  annotations do not say `destructiveHint: true`.
- **The default for every tool is still spec 034's.** Every tool, of
  every class, materializes as `/.agents/tools/<name>/TOOL.md` and is
  run at that path. The scope table adds view paths on top; it does not
  replace the catalog.
- **`capabilities()` follows the table.** Spec 034 says a materializing
  mount declares `{"run"}` only. With view rows it also declares
  `read`, `stat`, `ls` (and `glob`/`grep` if the mount chooses to
  render-and-scan the way Mirage's Postgres resource does, Mirage memo
  §3.16). Still declaration, never sniffing.

### 4.2 (b) `run` at a path and the write-class tool

mcpfs keeps writes out of the namespace: a write tool has no path, and
the CLI that calls it opens its own session (§3.4). Nothing in the
mount can gate a write, log it, or invalidate a cached read after it.

vfs's shape is the opposite and the better one. ADR 058: "a tool is a
path (`run`), so tool access falls out of the same rule." `run` is the
one execution verb (`base.py`: "`read`/`stat`/`ls` discover a tool's
definition; `run` is the only verb that executes it"); it is routed and
capability-gated like every verb; `deny_ops` is the mount-level
execution lever (spec 039's supersession by 068); per-path and
per-principal execute policy have named owners (039 and 058, parked in
`open-questions.md`). A write-class tool is therefore just
`run /.agents/tools/create_customer` with `arguments`. Parity, and the
gate is the difference.

Three things to take from mcpfs here:

1. **The tool's own class rides into the namespace as a declared fact.**
   `TOOL.md` frontmatter (spec 034 already puts provenance there) should
   carry `readOnlyHint`, `destructiveHint`, `idempotentHint`,
   `openWorldHint` as stated by the server, and `stat` on the tool
   directory should surface them in structured `data`. Then a policy
   can say "this read-only mount may `run` tools annotated read-only
   and nothing else" from a server-declared fact — the honest version
   of mcpfs's read/write split. When spec 039's rights-set reopens,
   this is the fact its execute carve-outs would key on.
2. **A view row is a `read`; a write-class tool is only ever a `run`.**
   Never map `write` on a view path to a create tool. mcpfs gets this
   right by making every file `0444`; vfs gets it by construction — a
   view row declares `read`/`stat`, and the mutation family is absent
   from the mount's `capabilities()`.
3. **Flag derivation from the input schema is what `cli run` needs.**
   `parseFlags` (§3.4) is a tidy, complete mapping from JSON Schema
   types to `--flag value`: booleans without a value, integers and
   numbers parsed, arrays comma-split, objects as raw JSON, `required`
   enforced, unknown flags refused. When the `cli` front door re-enters
   `run`, this is the mapping to write (in our own code). Do not take
   the `data`-wrapper flattening; it is one vendor's convention.

### 4.3 (c) What a read-class view needs for `stat` and `ls` to be honest

mcpfs's `stat` is a tool call, its failure mode is "healthy empty file",
and its freshness is undeclared (§3.3). Each of those maps onto a vfs
rule, and one of them exposes a gap in vfs's own model.

- **`stat` never executes.** MCP says `tools/call` is not cacheable and
  makes no idempotency promise unless the tool declares
  `idempotentHint`. A `stat` that runs the tool is a side effect
  triggered by `ls -l`. In vfs, `stat` on a view path answers from the
  table and from whatever rendering is already cached; it does not call
  the source. This should be a stated rule for any tool-backed view,
  in the same voice as "reads must keep working on read-only mounts"
  (`ops.py` `READ_OPS`).
- **Size may be unknown, and the model must be able to say so.** Mirage
  memo §3.16 records the rule: "a confidently wrong size is worse than
  an unknown one." `Observation.size_bytes` is `int | None` and can say
  it; `Entry.size_bytes` is `int = 0` (`models/entry.py:96`) and cannot
  — an unrendered view would stat as an empty file, which is mcpfs's
  failure mode restated in vfs's types. Before a view row exists,
  `Entry` needs an unknown size (`None`) distinct from zero, and `ls`
  and `stat` need to render it as unknown rather than `0`.
- **Freshness is a declared, structured fact per row.** For a resource
  row it is the server's `ttlMs` (required since 2026-07-28); for a
  tool row it is what the table says (`none` if it says nothing); for
  the `TOOL.md` catalog it is `tools/list.ttlMs` and the
  `tools/list_changed` notification. The read `Result` should carry
  `fetched_at` and the effective `ttl` in `data`, so an agent can tell
  a 30-second-old listing from a fresh one without parsing `message`.
  vfs already has the vocabulary shape — `grep_staleness` and
  `glean_staleness` are declared traits with a drift test
  (`protocol.py` `TRAIT_VALUES`); a per-row freshness is the same idea
  one level down.
- **Errors classify; they do not become content or emptiness.** A
  transport failure is `TransportError` → `backend_unavailable`, which
  vfs already normalizes. A tool result with `isError: true` needs a
  kind in the `run` family with a retry class; a page cut short needs
  `truncated`; a slot value that fails its codec needs the existing
  validation path. None of these is "size 0, mode 0444, success".
- **Pagination is a cursor in the result, not a silently short file.**
  Memo 2026-08-10 §8.2 already settles the wire shape: an opaque
  server-minted handle passed back as an ordinary argument, with
  expiry as a named recoverable kind. A list-tool view row reads one
  page, reports `truncated` with the cursor in `data`, and the reader
  asks for the next page through the same verb.
- **`ls` on an id-addressed directory is either real or refused.** The
  table names the list tool and id field to enumerate from, or `ls`
  answers with a classification. An empty listing that means "I cannot
  know" is the one answer that is never honest.

### 4.4 Transport: what to keep in view for roadmap 020

mcpfs's two clients are ordinary and small. Nothing to lift, three
things to avoid: a serialized stdio client that drops every
server-originated message (§3.5); an HTTP client that reuses JSON-RPC
`id: 1` and takes the first SSE `data:` line without correlating it;
and a version pin to the handshake-era spec. Roadmap 020 names
"capability negotiation at `initialize`"; per memo 2026-08-10 §1 there
is no `initialize` in the stateless revision — capabilities ride in
`_meta` on every request. When 020 is specced, its transport section
should be written against the 2026-07-28 shape, and its session story
should follow memo §5 (server-minted handles as application data), not
`Mcp-Session-Id`.

---

## 5. What not to take

- **The name heuristic as a binding rule.** Spec 034 already forbids
  it; §3.1 shows why the fall-through is unsafe. A generator that
  *proposes* rows is fine; a rule that *binds* them from a verb list is
  not.
- **`stat` that runs the tool.** The single most consequential design
  error in the repo. `ls -l` must not be an API call per entry.
- **A write CLI outside the namespace.** It is a second session with no
  gate and no invalidation. In vfs the CLI is a front door that
  re-enters verbs (`ops.py`); a write-class tool is `run` at a path.
- **`content[0].text` only.** Multiple blocks, non-text blocks and
  `structuredContent` all exist; vfs's routing mount (spec 034) already
  reads `structuredContent` for the VFS-protocol case and should read
  it for generic tools too when the tool declares an `outputSchema`.
- **Freshness by page cache.** Undeclared, uncontrolled, and different
  on macOS and Linux. Freshness is a fact the mount states.
- **Secrets in the process environment.** One `os.Setenv` per server in
  a shared process leaks every server's token to every other server's
  subprocess (§3.5). Per-mount credentials are per-mount configuration
  and never cross into `os.environ`.
- **FUSE.** Out of vfs's scope by decision (Mirage memo §5). mcpfs's
  value is the projection rule, not the kernel mount.
- **The `2025-03-26` pin.** vfs targets the stateless revision.
- **The "0 tokens" framing as a benchmark.** `bench/README.md` compares
  characters of output across interfaces; it is a claim about rendered
  size, not a measurement of agent behavior. vfs's version of the claim
  is spec 034's "tools as discoverable files, loaded on demand", and it
  needs no benchmark from here.

---

## 6. Next steps

1. **When spec 034 is re-drafted for roadmap 020, add the scope table
   (§4.1) as the view layer above the `TOOL.md` catalog**, with the two
   rules stated in its intent: *generation proposes, declaration
   binds*; and *resources are rows by default, tools by opt-in*. Cite
   this memo and Mirage memo §3.15.
2. **Record "stat never executes" as a standard** for any tool-backed
   or API-backed view, beside the read-only-mount rule in
   `standards/` — it is a property of `READ_OPS`, not of one backend.
3. **Open the `Entry.size_bytes` question** (§4.3): `int = 0` cannot
   express unknown; `Observation.size_bytes` already can. Decide whether
   `Entry` gains `None` before any view row exists, and what `ls`
   renders for it. Small, model-level, and it blocks honesty for every
   API-backed mount, not only MCP.
4. **Carry tool annotations into `TOOL.md` frontmatter and `stat`
   `data`** (§4.2) in the 034 re-draft; note in `open-questions.md`
   under the parked execute-policy entry that a declared
   `readOnlyHint` / `destructiveHint` is the fact per-path execute
   carve-outs (039) would key on.
5. **Write the `cli run` flag derivation** (§4.2) into spec 045's
   front-door grammar when `cli` is specced: JSON Schema type → flag
   shape, `required` enforced, unknown flags refused, no vendor
   wrappers.
6. **Reserve the `run`-family result kinds** — a tool's `isError`
   result, a cursor expiry, a slot-codec failure — in `KIND_CONTRACTS`
   before a remote speaks them (spec 045's rule), and pin the list-view
   cursor to memo 2026-08-10 §8.2.
7. **Rewrite roadmap 020's transport line** against the 2026-07-28
   revision (§4.4): no `initialize`, capabilities in `_meta`, handles
   as application data; `mcp+stdio://` and `mcp+http://` stay as the
   schemes.

---

## Sources

All paths under `~/Git/Repos/mcpfs` @ `640511e` (2026-03-06) unless
noted.

- Classification and naming: `internal/toolfs/classify.go` (`ToolClass`
  `:9-16`, `ClassifyTool` `:33-53`, `splitSegments` `:55-60`,
  `segmentsMatchAny` `:62-72`, `ToolToFilename` `:76-83`,
  `RequiredParams` `:86-95`, `stripVerb` `:98-123`, `pluralize`
  `:125-133`); `internal/toolfs/tree.go` (`BuildToolTree` `:19-35`);
  `internal/toolfs/classify_test.go`, `tree_test.go`.
- FUSE tree and reads: `internal/fuse/fs.go` (`BuildTree` `:76-129`,
  `registerTemplateTail` `:138-163`, `registerNestedTail` `:165-185`,
  `Readdir` `:205-226`, `Lookup` `:241-259`, `buildInode` `:261-289`,
  `lookupTemplateChild` `:291-342`, `fileNode.Getattr` `:355-365`,
  `Mount` `:411-511`); `internal/fuse/toolnode.go` (`readData` `:30-42`,
  `Getattr` `:44-54`, `Open` `:56-58`, `Read` `:60-74`);
  `internal/fuse/cache.go` (unused `Cache`); `internal/fuse/
  toolnode_test.go:108-135` (two reads, two calls).
- MCP clients: `pkg/mcpclient/client.go` (`call` `:56-92`, `initialize`
  `:94-113`, `CallTool` `:183-205`); `pkg/mcpclient/http.go`
  (`initialize` `:32-44`, `rpc` `:46-125`, `CallTool` `:173-191`,
  `ReadResource` `:194-213`); `pkg/mcpclient/types.go`.
- CLI bridge: `pkg/mcptool/dispatch.go` (`Run` `:19-64`, `printToolHelp`
  `:88-111`, `parseFlags` `:113-202`); `pkg/mcptool/schema.go`
  (`ParseSchema` `:36-58`, `IsDataWrapped` `:60-72`);
  `pkg/mcptool/call_stdio.go`, `call_http.go`.
- Entry points and config: `cmd/mcpfs/main.go` (`runTool` `:245-333`,
  `runConfig` `:364-414`); `cmd/mcpfs/auto.go` (`discoverClaudePlugins`
  `:15-48`, `shouldSkip` `:342`); `internal/config/config.go`
  (`interpolateEnv` `:47-60`).
- Docs: `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/gateway-design.md`
  (classification table and heuristics), `bench/README.md`, `LICENSE`.
- vfs seams read for the mapping: `src/vfs/ops.py` (`READ_OPS`,
  `EXEC_OPS`, `MUTATING_OPS`, `DEVELOPER_OPS`); `src/vfs/base.py`
  (module docstring, `run`); `src/vfs/storage/protocol.py` (module
  docstring, `TransportError`, `SupportsRun`, `StorageBackend`,
  `TRAIT_VALUES`, `_FAMILY_OPS`); `src/vfs/paths.py` (`AGENTS_ROOT`,
  `tool_path`, `tool_manifest_path`); `src/vfs/skills.py` (module
  docstring); `src/vfs/models/entry.py` (`Entry.size_bytes`,
  `Observation.size_bytes`); `context/standards/roadmap.md` (020,
  Wave 3, sequencing notes); `context/specs/archive/034-mcp-native-
  mounts/spec.md`; `context/specs/archive/039-execute-permission-tier/
  spec.md`; `context/specs/active/045-verb-wire-contract/spec.md`;
  `context/specs/active/054-mcp-serve-locks-topology/spec.md`;
  `context/decisions/022-serve-topology-lock-binds-the-wire.md`;
  `context/decisions/058-the-access-layer-for-agents-positioning.md`;
  `context/open-questions.md` (per-path / per-principal execute
  policy); `context/research/2026-08-10-mcp-2026-07-28-stateless-
  revision.md` (§1, §6, §8.2); `context/research/2026-09-04-mirage-
  design-patterns.md` (§3.15, §3.16, §4.7, §5).
