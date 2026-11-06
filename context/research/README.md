# /context/research

The RESEARCH stage of the pipeline described in [the context README](../README.md). A research memo is produced by gathering new findings: executed experiments, studied sources at named commits, measured runs. It never records in-session reasoning alone and never restates a decision. A memo commits us to nothing; the spec that stands on it decides.

## The memo

The file is `YYYY-MM-DD-descriptive-slug.md`; the title states the finding, not the topic. There are no header lines. The opening paragraph says who asked what and when (quoting the owner where it can), what was done and in how much time, links the intention it serves, and links its studies folder. Then a line defining the labels, a first section that gives the answer in one paragraph, numbered sections each carrying its label, a section "What this memo does not settle" whose items link a placeholder memo or name an experiment, and "One line". Sources are a `## Sources` section near the top: files by path and commit, clones by name, commit and licence, web pages by URL and read date.

Every claim is labelled. EXECUTED means a command ran here and the claim reports its output. READ means read in a file or page cited by path or URL. INFERRED means the researcher's reasoning from the two. Synthesis sits apart from evidence, so a reader can weigh the evidence before the opinion.

## The studies folder

A memo that fans out to several researchers stands on `studies/YYYY-MM-DD-descriptive-slug/`, the same slug as the memo:

```
studies/YYYY-MM-DD-descriptive-slug/
  00-brief.md        # the brief every researcher received, verbatim, and a table of the files
  01-slug.md         # one study per researcher, in reading order; the NN- prefix is order, not identity
  02-slug.md
  experiments/       # scripts and outputs of each experiment, never read by the lint
  refresh.log        # clones refreshed to their upstream default branch, with commits
  licenses.log       # the licence read from each clone
```

A study is self-contained: a reader who opens only it learns what was asked, against which commit, and what was found. It never cites a sibling study it did not read.

## The placeholder memo

A placeholder memo is a research memo that holds a question instead of an answer. Its first paragraph says it is a placeholder, who raised it and from which document, which spec will use the answer, which spec waits on it, and the time box the research will have. Its sections are the question, what is known today (labelled), and the experiment that answers it. It is the one memo edited in place: when the research is done, the placeholder is completed and the first paragraph says so. It is where an undecided choice waits, and it replaced `open-questions.md` on 2026-10-29.

## The rules

- **Label every claim.** A memo with no label is not a memo; if every label would be INFERRED, it is a section of the spec that needs it.
- **State the box; stop at the box.** The opening paragraph names the time box and, when it ran out, where the researcher stood and what was skipped. A blocked step is skipped and named, never forced.
- **Append-mostly; supersede, do not rewrite.** A correction is a new memo whose opening paragraph names the one it supersedes. Two exceptions, both written down: a placeholder memo is completed in place, and a brief's file table is filled in when the studies land.
- **No open questions.** The last section names what the memo does not settle, each item a placeholder memo or an experiment. A to-be-decided note, a to-do note or a heading that announces open questions does not appear.
- **Research is skipped when there is nothing to learn.** A spec says "none" for its research when the choice has no trade-off a study would change, when the prior art is already in a memo, or when the work corrects something decided.
- **No code copied; clones refreshed and licensed.** Every clone studied is refreshed to its upstream default branch first, its licence read and logged, its commit recorded. Descriptions and citations only.
- **Count operations; report clocks as facts.** A wall-clock number may appear, labelled EXECUTED with the machine named; a test derived from a memo counts operations.

The lint in `tests/lint/` holds the name, the absence of header lines, resolving links, one-line paragraphs and the presence of at least one label on every memo dated 2026-10-29 or later; earlier memos stay as written. Memos written before 2026-07-16 lived in `context/learnings/` and may reference `stories/` paths, which now resolve under `../specifications/` or `../specifications/archive/`.

## Reference checkouts

Prior art is studied in local clones of other projects, kept as sibling directories of this checkout (`../<name>`, one directory per project). The rules for using them (read-only, never copied, licence checked, refreshed before study) are in [AGENTS.md](../../AGENTS.md), "Reference repos for research". This catalog lists what has proved worth cloning, grouped by topic. It is not exhaustive, and a fresh clone of vfs has none of them: `ls ..` shows what is cloned on a given machine, and a study clones what it needs.

- **Filesystem heritage and semantics**: `plan9`, `plan9port`, `unix-history-repo`, `freebsd-src`, `linux`, `libfuse`, `pjdfstest` (POSIX fs test suite).
- **VFS and storage layers**: `filesystem_spec` (fsspec), `pyfilesystem2`, `opendal`, `juicefs`, `seaweedfs`, `minio`, `libsqlfs`, `agentfs`, `jackrabbit-oak`, `mirage` (Strukto's unified virtual filesystem for agents, the direct competitor; Apache-2.0; profiles, hide/show, ask, explain, the hierarchy kit), `afs` (AIGNE's Agentic File System: typed verbs incl. `explain`/`search` over a wire protocol; BSL 1.1), `mcpfs` (mount MCP servers as a filesystem: tool→file/dir/CLI classification; MIT), `branchfs` (FUSE copy-on-write branches with commit/abort for parallel agents; MIT).
- **Databases**: `sqlite`, `postgres`, `turso`, `sqlalchemy`.
- **Array kernels** (prior art for our own Rust kernels: decode, sorted-set intersection, `searchsorted`, `unique`, `bincount`, `maximum.at`): `numpy` (BSD-3-Clause; study `numpy/_core/src/`, never copy).
- **Code search and indexing** (trigram-index stories): `zoekt`, `codesearch`, `scip`.
- **BM25 inside Postgres** (lexical-leg design record): `pg_textsearch` (TigerData/Timescale, PostgreSQL licence; LSM memtable + paged segments, Block-Max WAND), `paradedb` (`pg_search`, AGPL; Tantivy segments on Postgres pages), `VectorChord-bm25` (AGPL/ELv2; bm25 index type with Block WeakAnd), `pg_bestmatch.rs` (Apache-2.0; BM25 as sparse vectors).
- **Ranked search, fusion and embeddings** (glean stories): `pgvector`, `pgvector-python`, `sqlite-vec`, `bm25s`, `tantivy`, `lucene` (unified highlighter), `ranx` (rank fusion + IR metrics), `neural-search` (OpenSearch hybrid normalization), `lancedb`, `haystack`, `llama_index`, `pyserini`, `fastembed`, `model2vec`, `openai-python`.
- **Graphs and relation stores** (edge/graph stories): `neo4j`, `kuzu` (archived upstream, kept as a frozen design record), `ladybug` (Kuzu's community successor), `age` (graph on Postgres), `gel` (typed links compiled onto Postgres), `cayley` (graph over SQL/KV backends), `terminusdb` (versioned KG), `helix-db`, `tinkerpop` (Gremlin traversal API), `networkx`, `rustworkx`, `spicedb`, `openfga`.
- **Graph query standards**: `openCypher`, `opengql-grammar` (LDBC's ISO GQL 2024 grammar), `GraphLite` (early embedded ISO-GQL), `duckpgq` (SQL/PGQ on DuckDB).
- **Knowledge graphs, agent memory and ontologies**: `graphrag`, `graphiti`, `cognee`, `LightRAG`, `graphify`, `letta`, `mem0`, `memori` (bring-your-own-SQL agent memory), `MemOS`, `HippoRAG`, `KAG`, `youtu-graphrag`, `ontogpt`, `rdflib`, `oxigraph`, `jena`.
- **Agent frameworks as consumers** (how a host loop would consume vfs): `eve` (Vercel's agent-is-a-directory framework; Apache-2.0; the MCP-connection and memory-provider seams, `byPrincipal` scope, the sandbox `/workspace` that vfs is *not*), `deepagents`, `langgraph`, `letta`, `openai-agents-python`, `claude-agent-sdk-python`, `adk-python`, `opencode`, `gemini-cli`.
- **Filesystems over databases** (the direct category peers; see [the landscape memo](2026-09-15-filesystem-over-database-landscape-and-vfs-differentiation.md)): `computer` (Cloudflare's `dofs` inode tree in Durable Object SQLite, content-addressed chunks, FUSE and sync; MIT), `langchain-mongodb` (`libs/langchain-mongodb-deepagents-vfs`: S3 bytes, Atlas chunks and hybrid `grep`; MIT), `deepagents` (the `BackendProtocol` and the tool-tier permission rules), `letta` (MemFS git-per-agent memory; Python server archived off `main` 2026-08-15, read via `git show`), `agentfs`, `mirage`.
- **MCP**: `modelcontextprotocol`, `python-sdk`, `fastmcp`.
- **Sync and async faces of one library** (the API-shape question, [the 2026-11-06 memo](2026-11-06-sync-and-async-api-shapes.md)): `fastapi`, `starlette`, `httpx`, `httpcore` (generated sync face), `psycopg` (LGPL, studied only), `mongo-python-driver`, `redis-py`, `langchain`, `langgraph`, `pandas`, `polars`, `duckdb-python`, `arrow`, `distributed` (Dask), `prefect` (`sync_compatible`), `filesystem_spec`.
- **Sandboxed execution and wasm** (hermetic-runtime direction): `monty` (pydantic's sandboxed Python interpreter), `wasmtime-py` (wasm embedding), `browser_wasi_shim` (WASI preview1 over a virtual fs), `WASI` (spec; preview1 lives on branch `origin/wasi-0.1`), `nushell` (structured-value pipelines).
