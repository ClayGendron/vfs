# Brief: code mode and its peers, studied as the reference design for a vfs code mode

This is the brief every researcher in this studies folder received, verbatim, followed by the table of studies.

## The question

Requested on 2026-11-23: research Cloudflare's Code Mode "and other similar" designs, as a reference design so that vfs is the better choice. The vfs code mode named in the request: an agent calls tools and MCP servers **through the vfs bash CLI**, and tools, MCP servers (and their results) are **stored as files, so they are searchable like anything else** in the namespace.

The question each study answers, from its own angle: what did the field build when it replaced direct tool calling with code (or with a shell), what evidence exists that it works, what does each design get right and wrong, and what does that mean for a vfs code mode whose language is the vfs shell and whose tool catalog is the vfs namespace?

## What vfs is, in five lines

vfs (this repository, `/home/user/vfs`) is governed data access for AI agents: one namespace of everything an agent can see, search and change, with permissions (an `Authority` judged against row-level grants) enforced before anything is dispatched. Every node speaks one verb set (`read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, `traverse`, `write`, `edit`, `delete`, `mkdir`, `move`, `copy`, `mkedge`, `run`), every verb returns one composable `Result`, storage is a database (Postgres, SQL Server, Oracle, SQLite...). Drafted but not built: a bash-shaped shell over the verbs (spec 167), programs and a bin union (169), tools and MCP servers projected as views under `/.vfs` and callable by name (170), an MCP adapter exposing the verbs plus one `cli` tool (171). Read `README.md` and `AGENTS.md` ("Production posture", "The reference deployment") for the scale every idea is costed against: 10,000,000 files, 1,000 people, about 150,000 agent verb calls a day.

## The rules every study keeps

- **Label every claim.** EXECUTED: a command ran here and the claim reports its output. READ: read in a file (cite path and commit) or a web page (cite URL and read date). INFERRED: the researcher's reasoning from the two. Keep synthesis apart from evidence.
- **Clone, refresh, license.** Prior-art repositories are cloned as sibling directories of the checkout: `/home/user/<name>` (never inside `/home/user/vfs`). A shallow clone (`git clone --depth 1`) is fine for a large repository. If the directory already exists, `git fetch origin` and check out `origin/HEAD`'s branch; skip a dirty clone and say so. Read the licence right after cloning. Append one line per repository to `/home/user/vfs/agents/2026-11-23-code-mode-prior-art/studies/refresh.log` (`<name> <url> <default-branch> <commit> <commit-date> 2026-11-23`) and one to `licenses.log` in the same folder (`<name> <SPDX or "none"> <file it was read from>`), using `>>`. Delete a clone only if it has no licence or unclear terms, and study it through public docs instead.
- **Read-only, never copied.** Reference repositories are never modified and no code is copied from them into this repository, whatever the licence. Describe and cite (`path:line @ commit`). Short quotations of prose (a sentence of a blog or README) are fine, with the source.
- **Web sources.** Use web search and fetch for blogs, docs and papers; cite URL and the read date (2026-11-23). Prefer primary sources (the vendor's own post, the paper, the repository) to commentary. Note when a figure is the vendor's own claim and not independently measured.
- **Do not touch `src/`, `tests/`, `crates/` or any file outside the studies folder.** Scripts and outputs of an experiment go in `studies/experiments/<NN-slug>/`.
- **Every shell command gets a timeout**, about twice its estimated duration. A timeout that fires is a finding, not a number to raise.
- **Voice.** Objective and impersonal: no names of people (authors of prior art may be named as authors of their work), no "I", "we", "you". State what was found.
- **Shape of the study file.** One Markdown file, `NN-slug.md`, one line per paragraph (no hard-wrapped prose). Sections: the question as this study received it; `## Sources` (clones with commit, date and licence; pages with URL and read date); `## Findings`, numbered, each labelled; `## What this means for a vfs code mode` (INFERRED, kept apart); `## What this study does not settle`; `## One line`. Tables are welcome. Aim for depth over breadth: the study is the evidence a memo will stand on.

## What every study should look for, where its subject has it

1. **The shape of the call surface.** What the model writes (TypeScript, Python, shell, a DSL), what the generated API looks like (how a JSON Schema becomes a typed function, a CLI flag set, a file), and how many tools the model is shown up front.
2. **Discovery.** How the model finds the right tool among hundreds: everything preloaded, a search tool, a file tree it browses, progressive disclosure. What is indexed (names, descriptions, parameter schemas, examples) and how it is ranked.
3. **Execution and isolation.** Where the code runs (V8 isolate, Worker Loader, Deno, wasm, a container, a Python AST interpreter), what it can reach (network off, bindings only), per-call limits (CPU, memory, wall, output size).
4. **Credentials and authority.** Whether secrets ever enter the sandbox; how a call is authorized (the sandbox holds a binding or a capability, the host injects the token); whether per-user permissions survive the hop.
5. **Results and state.** What comes back to the model (only what the code prints, the full tool result, a file path), whether intermediate results are written to files, whether code the agent wrote is saved as a reusable skill.
6. **Evidence.** Token, latency, cost or accuracy numbers, with the workload they came from and who measured them.
7. **Failure modes and criticism.** Where code mode is worse than direct tool calling (small models, write-shaped tools, debugging, prompt-injection, human approval of side effects).
