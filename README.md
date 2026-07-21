# VFS: Agentic Search on your Database

<p align="center">
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/v/vfs-py" alt="PyPI version"></a>
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/pyversions/vfs-py" alt="Python"></a>
  <a href="https://github.com/ClayGendron/vfs/actions/workflows/test.yml"><img src="https://github.com/ClayGendron/vfs/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://codecov.io/gh/ClayGendron/vfs"><img src="https://codecov.io/gh/ClayGendron/vfs/branch/main/graph/badge.svg" alt="Coverage"></a>
  <a href="https://github.com/ClayGendron/vfs/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ClayGendron/vfs" alt="License"></a>
</p>

Compose a fully-featured, Unix-like environment for your agents. VFS is built on one claim: glob, grep, glean, and graph are the four verbs any agent needs to navigate a knowledge base.

```bash
pip install vfs-py
```

> ⚠️ **Alpha, mid-rebuild.** The core described below is the v2 design landing in this repo now — the router and its fundamentals are implemented at 100% coverage by a 1,600-test suite; the SQL backends are being ported onto it next. The current PyPI release (`vfs-py 0.0.22`) still ships the previous-generation API. Pin versions and expect change.

## Why a file system?

Your agent has driven Unix through its entire pretraining — it already knows `ls`, `grep`, and `cat`. Mount your database as a file system and that training becomes your interface: no tool schemas to design, no prompt engineering to teach. And because the namespace is backed by the database you already run, there is no new infrastructure to stand up either — it works for the agent, and it works for you.

## One namespace, mounted from your stack

A `VirtualFileSystem` node routes a namespace. Give it a storage backend and it serves files; mount other nodes into it and it routes across them. Agents see one tree; each subtree is answered by whatever store owns it.

```python
from vfs import VirtualFileSystem
from vfs.backends import DatabaseFileSystem, PostgresFileSystem

root = VirtualFileSystem()
await root.add_mount(PostgresFileSystem(dsn="postgresql+asyncpg://..."), "/enterprise")
await root.add_mount(DatabaseFileSystem(dsn="sqlite+aiosqlite:///knowledge.db"), "/knowledge")

await root.write(path="/knowledge/notes/auth.md", content="All logins require MFA.")
result = await root.grep("authenticate", paths=("/enterprise",))
ranked = await root.glean("how does user login work?", limit=10)
```

Mounts nest — a mounted node can carry mounts of its own — and every path an agent sees stays in its own coordinates: results are rebased on the way back up, so `/enterprise/policies/mfa.md` is the same name no matter which store answered it.

## The verb surface

Every node speaks the same small vocabulary. Verbs take paths in, return one composable `Result` out.

| Family | Verbs | What they answer |
|---|---|---|
| Read | `read` · `stat` · `ls` · `tree` | point reads and listings |
| Search | `glob` · `grep` · `glean` · `graph` | *where it sits · what it says · what it means · how it connects* |
| Mutate | `write` · `edit` · `delete` · `mkdir` · `move` · `copy` · `mkedge` | versioned, reversible changes |
| Execute | `run` | invoke a tool that lives at a path |

Every family follows the same contract — paths in, one `Result` out, and a mutation is always versioned so it can be undone.

## Search from every angle: glob, grep, glean, graph

A file carries information four ways — where it sits, what it says, what it means, and how it connects. VFS gives each signal its own verb, and all four return the same composable result type, so they combine instead of competing.

```python
await root.glob("**/*.py", paths=("/enterprise",))          # where it sits — match names and structure
await root.grep("def login", ext=(".py",), before_context=2)  # what it says — match content, ripgrep-style
await root.glean("how does user login work?", limit=10)     # what it means — one fused, ranked list
await root.graph("neighborhood", "/enterprise/auth.py")     # how it connects — walk typed edges
```

- **`glob`** answers by *location*: names and structure, the shape of the tree.
- **`grep`** answers by *content*: literal or regex matching with the options agents already know — case modes, context lines, include/exclude globs.
- **`glean`** answers by *meaning*: text in, one ranked list out. The caller never picks a retrieval strategy — the backend fuses whatever signals it has (lexical, vector, graph) and owns the ranking.
- **`graph`** answers by *connection*: typed edges between files are first-class, and traversals (`predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`) walk them like any other query.

Searches scope naturally: pass `paths=` to search a region, or nothing to search the whole namespace — the query fans out to every mount that can answer it, and mounts that can't are skipped rather than failing the sweep.

## One result type, classified errors

Every verb returns a `Result` carrying typed `Observation` rows. Results merge with `|`, so multi-mount answers compose losslessly — and failures are values, not exceptions: errors come back classified (`not_found`, `wrong_kind`, `unsupported`, `permission`, `invalid`, `cross_mount`, …) so an agent can branch on the kind instead of parsing a traceback. A raw exception always means a bug, never a bad input. Results also round-trip a wire payload (`to_payload` / `from_payload`), which is what will cross the MCP boundary as structured content.

## Everything is a file

Files live in the user namespace; everything derived from them lives at reserved paths beneath it:

```
/enterprise/auth.py                      the file
/.vfs/enterprise/auth.py/__meta__/
├── chunks/login                         a function, addressable on its own
├── versions/2                           history — operations are reversible
└── edges/out/imports/enterprise/utils.py   a typed link to another file
/.agents/tools/<name>/                   a tool an agent can discover and run
```

Chunks, versions, edges, tools, and skills are ordinary entries: `ls` them, `grep` them, `mkedge` new links, `run` a tool. One abstraction, one set of verbs.

## Storage is composed, not inherited

A node *holds* its storage rather than *being* it. Backends implement small protocol families — reads, pattern search, ranked search, mutation, graph, run — and a backend claims only the families it genuinely supports. A node's `capabilities()` are derived from what its backend actually implements, so a partial backend (an MCP tool catalog that only does `ls`/`read`/`run`, an in-memory store without ranked search) is a first-class citizen, not a liar.

```python
class MemoryStorage:                       # the read family is the minimum viable backend
    async def read(self, *, path=None, observations=None, columns=None, user_id=None): ...
    async def stat(self, ...): ...
    async def ls(self, ...): ...
    async def tree(self, ...): ...

fs = VirtualFileSystem(storage=MemoryStorage())
```

Database backends come in exactly two constructions: give one a DSN and it builds and owns its engine, or hand it your application's session factory and it borrows yours — ownership follows construction, never a flag.

Permissions compose the same way: each node carries a permission map (`"read_only"`, `"read_write"`, or per-prefix rules), enforced at the routing chokepoint before anything dispatches.

## Where this is heading: MCP-native

The namespace is designed to be an agent's whole toolbox behind one MCP tool: verbs as the call surface, `Result` payloads as structured content, tools discovered at paths instead of preloaded into context. The same design runs the other direction — mounting external MCP servers into the tree as just another backend. The wire contract and MCP mount stories are drafted; they land on the backend port that's in progress now.

## Status

- **Implemented (v2 core):** typed path grammar, models, the classified result channel, the op vocabulary, permissions, and the full async mount router — spine listings, capability gating, batched and fanned-out dispatch — at 99–100% coverage across 1,094 tests.
- **In progress:** porting the SQL backends (`DatabaseStorage` → Postgres/MSSQL) onto the storage protocol.
- **Next:** the MCP surface (serve the namespace as one tool; mount MCP servers), local file backend, and the ranked-search and graph engines re-homed behind their protocol families.
- **Released:** `vfs-py 0.0.22` on PyPI ships the previous-generation API (sync/async clients, database backends, CLI query engine, BM25 and vector search, graph algorithms). See the [CHANGELOG](CHANGELOG.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
