# Introduction to VFS

VFS is a virtual file system that gives AI agents governed access to data and tools.

AI agents are usually connected to data one tool at a time, each with its own API and governance patterns. These connections also bloat the context window and make AI agents less effective. Defining every tool in the LLM API call leaves the AI agent moving data between systems instead of solving the problem. VFS replaces those connections with one namespace for data and tools. Both live in one tree, and the AI agent works in it with commands it already knows.

```bash
grep -rn "mfa" /enterprise | head -20
```

Three things make this work.

- **One namespace.** Everything an AI agent can see, search, and change lives at a path, and you decide what is in the namespace.
- **One command line.** AI agents use `ls`, `grep`, `cat`, and a few others through a single tool, and read only what a task needs.
- **One gate.** Every command passes through the VFS kernel, which checks permissions before anything runs and keeps deletes and overwrites reversible.

VFS is a Python library that runs inside your application and stores files in a database, from SQLite on a laptop to Postgres, SQL Server, or Oracle in the cloud.

```bash
pip install vfs-py
```

## Where to Go Next

- [Overview](overview.md) gives a high-level analysis of how to think about VFS.
- [History](history.md) gives the full backstory of where the ideas built into VFS came from.
