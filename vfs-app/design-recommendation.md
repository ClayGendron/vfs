# Design recommendation for vfs.dev

Based on:

- The parent project at `/Users/claygendron/Git/Repos/grover`: `vfs-py`, alpha, Apache 2.0, "context layer for enterprise agents"
- The current app in `vfs-app`: Pluto/spec-sheet theme, `SpecHero`, `Values`, `Sample`, `/terminal`, file system footer
- The refreshed OSS website research in `oss-website-research.md`
- Primary site review on April 26, 2026 of DuckDB, LangChain, Bun, Astro, Tailwind, shadcn/ui, htmx, Vite, FastAPI, TanStack, uv, Svelte, Prisma, and Supabase

## Diagnosis

vfs.dev already has the hard part: a distinctive design language. The path chrome, metadata cells, `ls`-style footer, mono install chip, and Pluto palette make the site feel like a file system/manual page rather than another generic developer SaaS homepage.

The main gap is not visual polish. The main gap is **communication order**.

The current homepage asks visitors to decode:

1. `vfs`
2. `v0.x - context layer - apache 2.0`
3. A long lede about in-process file systems, mounts, search, graph traversal, CLI pipelines, and backends
4. Principles
5. Only then, code

The best OSS sites reverse that burden. DuckDB, Bun, Vite, Astro, uv, Tailwind, htmx, and FastAPI all put the concrete job, install path, and a working artifact very early.

## What to preserve

- **File-system-as-IA.** The page structure, footer, route naming, and metadata should continue to feel like a mounted file system.
- **Spec-sheet identity.** The hero's top-left/top-right cells, version metadata, and mono details are the site's strongest visual choices.
- **Pluto palette.** Grayscale plus a cobalt signal fits infrastructure and keeps the brand from feeling like a trend clone.
- **Real alpha framing.** Do not hide the stage. Alpha plus concrete proof is more credible than pretending to be enterprise-mature.
- **The terminal route.** `/terminal` is the strongest demo surface and should be promoted, not replaced.
- **Code samples.** `Sample` is the right primitive. The issue is placement, not existence.

## Highest-leverage recommendation

Commit fully to a **protocol/manual-page homepage**: concise headline, immediate code, proof strip, integrations grid, and direct positioning.

The site should feel like DuckDB's practical clarity, Bun's proof density, htmx's point of view, and FastAPI's docs-first usefulness, but rendered through vfs's own file system aesthetic.

## Priority changes

### 1. Add a job-shaped headline above the wordmark

Right now the first large text is only `vfs`. That works for recall, but not for first comprehension.

Add a short headline prop to `SpecHero` and render it above or immediately beside the wordmark:

```text
One Namespace for Enterprise-Scale Context Engineering.
```

Other viable options:

- `One namespace where agents can use enterprise data.`
- `One namespace for data, tools, and agent action.`
- `One namespace to engineer enterprise-scale agent context.`
- `Mount enterprise context. Traverse it like Unix.`
- `One file system for search, graph, and agent memory.`
- `Grep the enterprise. Rank the graph. Feed the agent.`

Recommended final version: **One Namespace for Enterprise-Scale Context Engineering.**

Lead with `namespace`, not `file system`, and use `context engineering` as the category. `Namespace` is less common in AI-agent positioning, so it gives vfs a more distinctive frame: an organizing substrate for engineering context, not just a file browser or retrieval wrapper. Because the headline no longer says `agents`, the supporting copy should mention agents immediately. It can still use `virtual file system` to ground the mechanism.

Then tighten the lede:

```text
Mount data, tools, and retrieval systems behind one virtual file system so agents can search, traverse, and act across enterprise context.
```

This keeps the homepage promise specific to agents: more usable context without stuffing everything into the context window. It also preserves the technical mechanism through `virtual file system` and the workflow through `search, traverse, and act`.

### 2. Move code into the hero

Every strong package site shows the thing early: DuckDB shows SQL, Vite shows the create command, htmx shows `hx-post`, Tailwind shows classes, shadcn/ui shows rendered UI, Bun shows commands and benchmarks.

For vfs, the first artifact should be a real agent-context workflow:

```python
from vfs import VFSClient
from vfs.backends import PostgresFileSystem

g = VFSClient()
g.add_mount("/enterprise", PostgresFileSystem(...))

g.cli('grep "authenticate" | nbr | pagerank | top 15')
```

Implementation:

- Keep `SpecHero` as the component.
- Add a `headline?: ReactNode` prop.
- Change `side` from small metadata-only content into a general hero-side slot.
- Put a compact `Sample` in the side slot on desktop.
- Keep the install chip below the hero content.

This is the single most important page change.

### 3. Add an alpha-appropriate proof strip

vfs does not need fake enterprise logos. It needs specific proof.

Place a mono strip directly below the hero:

```text
2,157 TESTS - 99% COVERAGE - POSTGRES/MSSQL/SQLITE - GRAPH + BM25 - MCP READY - APACHE 2.0
```

If any number changes, source it from `SITE.metrics` rather than hardcoding it in copy.

This borrows from Bun's benchmark density and Vite's stars/downloads pattern, but adapts it to alpha maturity.

### 4. Replace principles-first structure with demo-first structure

The current section 01 principles are good, but they are abstract. Move them below the concrete demo.

Recommended homepage order:

1. Hero: headline, lede, install, code sample
2. Spec strip: tests, coverage, backends, algorithms, license
3. On-wire: `VFSClient` input and `VFSResult` output
4. Integrations: backends, embeddings, agent frameworks, protocols
5. Why vfs: comparison against obvious alternatives
6. Terminal preview: scripted tape with CTA to `/terminal`
7. Principles/status: concise, below proof and demo

This keeps the brand but aligns the page with how developers evaluate packages.

### 5. Add an integrations grid

DuckDB, Astro, Prisma, Supabase, Vite, and TanStack all make ecosystem fit visible. vfs currently hides that maturity inside install extras and prose.

Add a plain-text grid:

| Group | Items |
| --- | --- |
| Backends | Postgres, MSSQL, SQLite, LocalFileSystem when ready |
| Retrieval | BM25, pgvector, lexical search, semantic search |
| Graph | rustworkx, neighborhood, pagerank, betweenness |
| Agents | MCP, LangChain, LangGraph, deepagents |
| Embeddings | OpenAI, LangChain providers |
| Interfaces | Python API, CLI, async/sync clients |

Use mono labels and square borders. Avoid logo polish unless official marks are already available.

### 6. Add a "why vfs?" positioning section

This is the most important content gap after the hero.

Developers will immediately ask whether vfs is a vector database, `fsspec`, retriever framework, or graph database. Answer directly:

| If you already use... | vfs adds... |
| --- | --- |
| A vector database | Paths, CRUD, lexical search, graph traversal, and CLI pipelines over one result contract. |
| `fsspec` or object storage | Search/ranking/graph operations over mounted data, not just file access. |
| LangChain or LangGraph retrievers | A composable context substrate that agents can query through Unix-like operations. |
| A graph database | File system semantics and retrieval workflows without making graph storage the whole product. |

Tone should be clarifying, not combative. Bun's replacement matrix is the right model: direct because it reduces evaluation friction.

### 7. Promote `/terminal` with a scripted preview

The terminal page is currently one navigation click away. The homepage should preview it.

Add a non-interactive terminal tape:

```text
$ vfs mount /enterprise postgres://...
$ vfs grep "authenticate" /enterprise
$ vfs nbr --depth 2 | vfs pagerank | vfs top 5
/enterprise/auth.py        0.184
/enterprise/session.py     0.131
/enterprise/policy.md      0.097
```

Then link: `TRY THE REPL`.

Do not make this a toy animation. Keep it short, copyable-looking, and close to real CLI semantics.

### 8. Keep the commercial surface absent for now

The research shows that LangChain, Prisma, and Supabase can mix OSS with commercial CTAs because they have mature hosted products and customer proof.

vfs should not add "request demo," "trusted by," or fake enterprise logos yet. For this stage, the stronger message is:

- Apache 2.0
- source available
- tested core
- specific backends
- clear roadmap
- direct terminal demo

## Suggested copy

Hero:

```text
One Namespace for Enterprise-Scale Context Engineering.

Mount data, tools, and retrieval systems behind one virtual file system
so agents can search, traverse, and act across enterprise context.
```

Spec strip:

```text
2,157 TESTS - 99% COVERAGE - POSTGRES/MSSQL/SQLITE - GRAPH + BM25 - PYTHON 3.12+ - APACHE 2.0
```

Positioning section title:

```text
Why vfs?
```

Terminal section title:

```text
The interface agents already know.
```

Status copy:

```text
Alpha means the API is still moving. The core file system, CLI query engine, graph algorithms, and BM25 lexical search are implemented and tested.
```

## File-level implementation plan

1. `src/lib/site.ts`
   - Add `headline`
   - Tighten `description`
   - Add `metrics`
   - Add `integrations`
   - Add `positioning`

2. `src/components/brand/SpecHero.tsx`
   - Add `headline?: ReactNode`
   - Allow the side slot to hold a `Sample`
   - Adjust hero grid to support text/code composition

3. `src/components/brand/SpecStrip.tsx`
   - New compact mono proof band
   - Data-driven from `SITE.metrics`

4. `src/components/brand/IntegrationsGrid.tsx`
   - New grouped grid
   - Plain text is enough for v1

5. `src/components/brand/Positioning.tsx`
   - New comparison table
   - Keep copy direct and short

6. `src/components/brand/TerminalTape.tsx`
   - Scripted, deterministic preview
   - Link to `/terminal`

7. `src/routes/Home.tsx`
   - Reorder sections around demo, proof, integrations, positioning, terminal, principles/status

8. `src/styles/brand.css`
   - Add selectors for spec strip, integrations grid, positioning table, and tape
   - Preserve square/schematic feel; avoid new rounded-card vocabulary

## Suggested implementation order

1. Copy only: headline, lede, `SITE` fields.
2. Hero code placement: use existing `Sample`.
3. Spec strip.
4. Integrations grid.
5. Positioning table.
6. Terminal tape.
7. Section order and polish.

This keeps the work incremental and avoids a redesign.

## Things not to add

- Fake logo strip
- Generic testimonials
- "AI-native" copy without workflow proof
- Gradient or abstract network hero
- A marketing landing page before the product surface
- A signup/request-demo CTA
- Large rounded SaaS cards that fight the current spec-sheet style

## One-sentence recommendation

**Keep the file system/spec-sheet identity, but make the first screen behave like the best OSS package sites: clear job-shaped headline, pasteable code, install command, and concrete proof before philosophy.**
