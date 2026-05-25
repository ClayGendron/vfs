<!--
PARKED 2026-05-16 — moved out of docs/home.md to keep the Explanation page clean.
This is the old public-API catalog (Reference content, not Explanation).
Destination when revived: docs/reference/api.md (per the Diátaxis skeleton).
Typos preserved as-is; copyedit on migration, not here.
-->

# Parked: public API catalog (from home.md)

The `VirtualFileSystem` defines the public API of VFS:

- **File System Operations:** Perform core CRUD and navigational commands of interacting with file system.
  - `read`, `write`, `edit`, `stat`, `delete`, `move`, `copy`, `mkdir`, `list`, `tree`
- **Pattern Mathching:** Regex pattern matching for percise search. Accelerated by trigram indexing.
  - `glob`, `grep`
- **Semantic Search:** Fuzzy search with vector embeddings, keyword matching, or a hybrid approach.
  - `glean`
- **Graph Traversal:** Create connections, navigate network relationships, and calculate centrality measures on sub-graphs.
  - `mkedge`, `near`, `between`, `rank`
- **Tools and Skills:** Run tools and store repeatable skills workflows.
  - `exec`

The methods can be provided to an AI agent as seperate tools or as a composable CLI.

```bash
# Common UNIX aliases can be used inside vfs for consistancy

vfs cat prompts/system.md
vfs stat output/large_file.txt
vfs ls src/agent
vfs tree src/ --depth 3

```
