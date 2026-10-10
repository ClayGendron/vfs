# vfs — the access layer for agents

<p align="center">
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/v/vfs-py" alt="PyPI version"></a>
  <a href="https://pypi.org/project/vfs-py/"><img src="https://img.shields.io/pypi/pyversions/vfs-py" alt="Python"></a>
  <a href="https://github.com/ClayGendron/vfs/actions/workflows/test.yml"><img src="https://github.com/ClayGendron/vfs/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://codecov.io/gh/ClayGendron/vfs"><img src="https://codecov.io/gh/ClayGendron/vfs/branch/main/graph/badge.svg" alt="Coverage"></a>
  <a href="https://github.com/ClayGendron/vfs/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ClayGendron/vfs" alt="License"></a>
</p>

**One namespace of everything an agent can see, search, and change. You decide what's in it.**

Frameworks build the agent. Control planes set the policy. Gateways check the tool call. vfs enforces it on the data itself — the files, rows, and tools the agent actually touches.

```bash
pip install vfs-py
```

> ⚠️ **Alpha, mid-rebuild.** The core described below is the v2 design landing in this repo now; the current PyPI release (`vfs-py 0.0.22`) still ships the previous-generation API. Pin versions and expect change. **What is built:** the search half — `glob`, `grep`, and `glean` over the database you already run — the router's mount-level and per-prefix permissions, enforced before anything dispatches, and the first layer of the governed half: agent identity (`Authority`, `Principal`) and row-level grants (`grant`, `revoke`, `posture`, `grants`), built and under review. **What is not:** tools at paths. The `run` verb exists and routes to a storage that declares `SupportsRun`; no shipped storage does. The same holds for `graph`: the verb routes, and no shipped storage answers it yet. The positioning above says where vfs is going; this banner says what is real today, and [Known limits](#known-limits) lists the edges.

## Why a file system?

Your agent has driven Unix through its entire pretraining — it already knows `ls`, `grep`, and `cat`. Mount your database as a file system and that training becomes your interface: no tool schemas to design, no prompt engineering to teach. And because the namespace is backed by the database you already run, there is no new infrastructure to stand up either — it works for the agent, and it works for you.

## One namespace, mounted from your stack

A `VirtualFileSystem` node routes a namespace. Give it a storage backend and it serves files; mount other storages into it and it routes across them. Agents see one tree; each subtree is answered by whatever store owns it.

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vfs import VirtualFileSystem
from vfs.storage.backends import DatabaseStorage

# Your application's engine and session factory — any SQLAlchemy URL works.
engine = create_async_engine("sqlite+aiosqlite:///enterprise.db")
sessions = async_sessionmaker(engine, expire_on_commit=False)

root = VirtualFileSystem()
await root.add_mount(DatabaseStorage(session_factory=sessions), "/enterprise")
await root.add_mount(DatabaseStorage(url="sqlite+aiosqlite:///knowledge.db"), "/knowledge", permissions="read")

await root.write(path="/enterprise/policies/mfa.md", content="All logins require MFA.", parents=True)
result = await root.grep("MFA", paths=("/enterprise",))
ranked = await root.glean("do logins need a second factor?", limit=10)
```

A `VirtualFileSystem()` built with no `storage` gets an `InMemoryStorage` at `/`: a `DatabaseStorage` over a private in-process SQLite database. Writes outside every mount land there and live as long as the process; pass `storage=` to put something durable at the root.

Mounts can be bound at any depth, and every path an agent sees stays in its own coordinates: results are rebased on the way back up, so `/enterprise/policies/mfa.md` is the same name no matter which store answered it.

## The verb surface

Every node speaks the same small vocabulary. Verbs take paths in, return one composable `Result` out.

| Family | Verbs | What they answer |
|---|---|---|
| Read | `read` · `stat` · `ls` · `tree` | point reads and listings |
| Search | `glob` · `grep` · `glean` · `graph` | *where it sits · what it says · what it means · how it connects* |
| Mutate | `write` · `edit` · `delete` · `mkdir` · `move` · `copy` · `mkedge` | changes; `delete` is reversible through the trash and `restore` |
| Execute | `run` | invoke a tool that lives at a path |

Every family follows the same contract — paths in, one `Result` out.

## Search from every angle: glob, grep, glean, graph

A file carries information four ways — where it sits, what it says, what it means, and how it connects. VFS gives each signal its own verb, and all four return the same composable result type, so they combine instead of competing.

```python
await root.glob("**/*.md", paths=("/enterprise",))             # where it sits — match names and structure
await root.grep("logins", ext=(".md",), before_context=2)      # what it says — match content, ripgrep-style
await root.glean("do logins need a second factor?", limit=10)  # what it means — one fused, ranked list
await root.graph("neighborhood", "/enterprise/policies/mfa.md")  # how it connects — walk typed edges
```

- **`glob`** answers by *location*: names and structure, the shape of the tree.
- **`grep`** answers by *content*: literal or regex matching with the options agents already know — case modes, context lines, include/exclude globs.
- **`glean`** answers by *meaning*: text in, one ranked list out. The caller never picks a retrieval strategy — the backend fuses whatever signals it has (lexical, vector, graph) and owns the ranking. With no embedding provider configured, the lexical leg answers alone and the result says so.
- **`graph`** answers by *connection*: typed edges between files are first-class, and traversals (`predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, `meeting_subgraph`) walk them like any other query. Today the verb routes and comes back `unsupported`: no shipped storage declares the graph family yet.

Searches scope naturally: pass `paths=` to search a region, or nothing to search the whole namespace — the query fans out to every mount that can answer it, and mounts that can't are skipped rather than failing the sweep.

## One result type, classified errors

Every verb returns a `Result` carrying typed `Observation` rows. Results merge with `|`, so multi-mount answers compose losslessly — and failures are values, not exceptions: errors come back classified (`not_found`, `wrong_kind`, `unsupported`, `permission`, `invalid`, `cross_mount`, …) so an agent can branch on the kind instead of parsing a traceback. A raw exception always means a bug, never a bad input. Results also round-trip a wire payload (`to_payload` / `from_payload`), which is what will cross the MCP boundary as structured content.

## Everything is a file

Files live in the user namespace; everything derived from them lives at reserved paths beneath it:

```
/enterprise/auth.py                      the file
/.vfs/enterprise/auth.py/__meta__/
├── chunks/login                         a function, addressable on its own
└── edges/out/imports/enterprise/utils.py   a typed link to another file
/.agents/tools/<name>/                   a tool an agent can discover and run
```

Chunks, edges, tools, and skills are ordinary entries: `ls` them, `grep` them, `mkedge` new links, `run` a tool. One abstraction, one set of verbs.

## Storage is composed, not inherited

A node *holds* its storage rather than *being* it. Backends implement small protocol families — reads, pattern search, ranked search, mutation, graph, run — and a backend claims only the families it genuinely supports. A node's `capabilities()` are derived from what its backend actually declares, so a partial backend (an MCP tool catalog that only does `ls`/`read`/`run`, a store without ranked search) is a first-class citizen, not a liar.

```python
from vfs.storage.backends import InMemoryStorage

fs = VirtualFileSystem(storage=InMemoryStorage())  # a DatabaseStorage on a private in-process SQLite
assert {"read", "glob", "grep", "glean", "write"} <= fs.capabilities()
```

Database backends come in exactly two constructions: give one a URL and it builds and owns its engine, or hand it your application's session factory and it borrows yours — ownership follows construction, never a flag.

Permissions compose the same way: each node carries a permission map (`"read"`, `"read_write"`, or a per-prefix map of those two), enforced at the routing chokepoint before anything dispatches. The map lives on the node, not on the data: two nodes over one schema do not see each other's maps.

## Where this is heading: MCP-native

The namespace is designed to be an agent's whole toolbox behind one MCP tool: verbs as the call surface, `Result` payloads as structured content, tools discovered at paths instead of preloaded into context. The same design runs the other direction — mounting external MCP servers into the tree as just another backend. The wire contract and MCP mount stories are drafted, not built.

## Known limits

What the tree does not do yet, and where each decision lives.

- **Permissions are enforced at the node.** The mount-level and per-prefix map is checked before dispatch; row-level grants are built and under review ([spec 058](context/specs/active/058-row-level-permission-grants/spec.md), [ADR 073](context/decisions/073-the-everyone-level-lives-on-the-row-and-a-callers-rights-are-caller-sized.md)).
- **A fresh storage is `open`.** Until its posture changes, an anonymous caller may read, write and delete on it ([ADR 068](context/decisions/068-open-by-default-in-process-anonymous-is-a-name-loud-at-the-edge.md)).
- **`copy` and `move` do not cross a mount boundary.** They come back `cross_mount`; copy a file across mounts with `read` and `write` ([spec 160](context/specs/active/160-cross-mount-copy-as-read-plus-write/spec.md) lifts this for files).
- **`edit` does not touch a binary body.** It refuses `wrong_kind`; replace the bytes with `write(data=...)` ([spec 154](context/specs/active/154-errors-are-facts/spec.md)).
- **A `VirtualFileSystem` is not a storage and cannot be mounted.** `add_mount` takes a storage backend ([spec 156](context/specs/active/156-mount-admission/spec.md) makes the refusal explicit).

## Status

- **Implemented (v2 core):** typed path grammar, models, the classified result channel, the op vocabulary, node permissions, the full async mount router — spine listings, capability gating, batched and fanned-out dispatch — and the database backend on the storage protocol: reads, writes, `glob`, `grep`, `glean` with its lexical and vector legs and the cross-mount rerank, the trash arc, identity and row-level grants, binary bodies with text renderings. 5,266 tests at 100% coverage, green on SQLite, Postgres, MariaDB, SQL Server and Oracle.
- **Under review:** row-level grants at scale (specs 058 and 150) and binary bodies (spec 152).
- **Next:** the MCP surface (serve the namespace as one tool; mount MCP servers), the local file backend, the graph engine re-homed behind its protocol family, tools at paths, and a version row on every mutation.
- **Released:** `vfs-py 0.0.22` on PyPI ships the previous-generation API (sync/async clients, database backends, CLI query engine, BM25 and vector search, graph algorithms). See the [CHANGELOG](CHANGELOG.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
