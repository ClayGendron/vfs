# Mission

- **Status:** draft (v0.1) — seeded 2026-04-18
- **Purpose:** What we're building, who it's for, and why it should exist.

## One-paragraph thesis

**VFS is the agentic filesystem.** It mounts data from heterogeneous sources — local disk, SQL databases, eventually live APIs — into a single Unix-like namespace, and exposes it through a unified set of operations: file CRUD, pattern search (`glob`, `grep`), semantic and lexical retrieval, graph traversal, and graph ranking. Every operation returns the same composable result type, and every method has a CLI equivalent that LLM agents can drive directly. VFS is the substrate AI agents stand on when they need to read, write, search, and reason over a real organisation's knowledge — without forcing the org to migrate its data into a new system.

## Target users

- **Primary:** developers building AI agents that need to operate on enterprise knowledge over long horizons — not toy chatbots, not single-shot retrieval. Concretely: people writing LangGraph / deepagents / custom agents that already wrestle with bolting together a vector store, a graph, a versioned filesystem, and ACLs.
- **Secondary:** application teams that already own infrastructure (Postgres, MSSQL, an embeddings provider) and want a coherent retrieval surface over it without standing up a new platform.
- **Not for:** end users of finished AI products. VFS is a library and an MCP server — it ships inside someone else's application.

## The core problem

Agents operating on real organisational knowledge need three things at once: a versioned, permission-aware filesystem; semantic + lexical retrieval; and a graph of how things connect. Today these live in separate systems with separate identity models — files in S3, vectors in Pinecone, graph in Neo4j, ACLs in some auth service — and the agent ends up as the integration layer, paying for that integration in context tokens, latency, and bugs.

VFS collapses the three layers into one identity model: **everything is a file path**. Graph nodes are paths. Search results are paths. Chunks, versions, and connections are paths. One namespace, one result type, one CLI. The agent stops integrating and starts operating.

## What success looks like

- An agent author can mount their organisation's data sources into VFS and have semantic search, graph traversal, and versioned writes working in under an hour, with their existing infrastructure.
- Agents written against VFS need only one MCP tool entry: VFS itself, with sub-operations discovered through `--help`. Context budgets stop bleeding on tool definitions.
- Long-running agents can write, edit, and roll back without losing work; a wrong write is a `restore`, not an incident.
- "Where does this knowledge live?" stops being a routing question and becomes a path question.

## Explicit non-goals

- We are not building a competitor to Cursor, Aider, or Sourcegraph. VFS is the substrate; agent products are downstream.
- We are not a managed service. VFS runs in-process or as an MCP server inside the consumer's stack.
- We are not a general-purpose database. The schema is shaped for filesystem semantics; consumers don't reach in and `SELECT *`.
