# What makes great open-source package websites

Research memo, refreshed from primary site reviews on April 26, 2026.

Anchor references: [DuckDB](https://duckdb.org/), [LangChain](https://www.langchain.com/), [Bun](https://bun.sh/), [Astro](https://astro.build/), [Tailwind CSS](https://tailwindcss.com/), [shadcn/ui](https://ui.shadcn.com/), [htmx](https://htmx.org/), [Vite](https://vite.dev/), [FastAPI](https://fastapi.tiangolo.com/), [TanStack](https://tanstack.com/), [uv](https://docs.astral.sh/uv/), [Svelte](https://svelte.dev/), [Prisma](https://www.prisma.io/), and [Supabase](https://supabase.com/).

## Executive read

The best OSS package websites are not generic landing pages. They behave like a compressed README, docs index, proof page, and product demo at once.

They win by doing five things quickly:

1. **Name the job in one sentence.** DuckDB says analytics run where data lives. Vite says it is the build tool for the web. uv says it is a fast Python package and project manager. The category is clear before any feature list appears.
2. **Show an artifact above the fold.** Great sites show an install command, code sample, terminal output, UI rendered by the library, benchmark, or real product surface. They do not ask a developer to infer value from abstract art.
3. **Use quantified proof.** Bun leads with benchmark tables. Astro uses Core Web Vitals comparisons and links to the dataset. Vite surfaces stars and weekly downloads. FastAPI states productivity and bug-reduction claims with footnotes.
4. **Expose the ecosystem.** DuckDB lists clients, formats, databases, storage, and data-science integrations. Prisma and Supabase show the surrounding stack. TanStack makes the library family itself the IA.
5. **Maintain a point of view.** htmx is intentionally anti-framework and retro. shadcn/ui says "Open Source. Open Code." Tailwind speaks in concrete CSS capabilities. These sites sound like they were written by product engineers.

The strongest sites answer, in order: **what is this, why should I believe it, how do I try it, where does it fit, and what does it replace?**

## The homepage formula that keeps repeating

Most high-performing OSS homepages follow this shape:

```text
Navigation: Docs, GitHub, Blog, Community, Search

Hero:
  headline: concrete job + differentiator
  subhead: category + audience + scope
  CTAs: Get started / Docs / GitHub
  expert path: install command, quickstart, or search

Proof:
  user logos, stars/downloads, benchmarks, or version/license facts

Demo:
  real code, terminal session, live component, benchmark, or screenshot

Fit:
  integrations, supported clients, frameworks, backends, formats

Positioning:
  why this instead of the obvious alternative

Repeat CTA:
  get started, docs, GitHub, community
```

DuckDB, Astro, Vite, and Bun are closest to this exact model. LangChain and Prisma bend the formula toward a commercial buyer, but still keep open docs, clear framework links, and visible proof.

## Examples worth copying

| Site | What the homepage does well | Why it works |
| --- | --- | --- |
| [DuckDB](https://duckdb.org/) | Opens with "Run analytics where your data lives," then immediately shows docs, live demo, language tabs, client APIs, and install commands. | It makes locality, SQL familiarity, and ecosystem breadth visible without overexplaining. |
| [LangChain](https://www.langchain.com/) | Leads with agent reliability, then separates product platform from open-source frameworks: deepagents, langchain, and langgraph. | The IA acknowledges that the brand now spans OSS libraries and a hosted platform. |
| [Bun](https://bun.sh/) | Combines a sharp install path with benchmark tables, "used by" logos, and a replacement matrix for Node/npm/Jest/Vite-style jobs. | The site answers the migration question directly: adopt one tool or the whole toolkit. |
| [Astro](https://astro.build/) | Uses an install command in the hero, performance proof, framework logos, a code sample, and a dataset-backed comparison. | It turns "fast content sites" from a claim into an inspectable argument. |
| [Tailwind CSS](https://tailwindcss.com/) | Shows actual Tailwind classes and rendered UI immediately, then demonstrates responsive design, filters, dark mode, variables, color, and grid. | The reader evaluates the product by seeing the product's syntax and output together. |
| [shadcn/ui](https://ui.shadcn.com/) | Embeds a dashboard-like interface made from its components and exposes Docs, Components, Blocks, Charts, Directory, and Create. | The homepage is itself a product sample. |
| [htmx](https://htmx.org/) | Explains the philosophy, includes a tiny quickstart, states size/dependency facts, and links to essays. | Its voice is inseparable from its positioning: small, hypertext-first, deliberately non-corporate. |
| [Vite](https://vite.dev/) | Puts `npm create vite@latest` above the fold, includes package-manager tabs, logos, ecosystem claims, stars, downloads, and testimonials. | The page sells speed and ecosystem maturity at the same time. |
| [FastAPI](https://fastapi.tiangolo.com/) | Treats docs as the homepage: installation, example, run, check, interactive docs, performance, dependencies, license. | It is not polished like a SaaS site, but it is deeply effective because the path to first success is explicit. |
| [TanStack](https://tanstack.com/) | Turns a suite of packages into a navigable stack with status labels such as beta, alpha, and new. | It gives a large OSS surface area a coherent mental model. |
| [uv](https://docs.astral.sh/uv/) | Opens with a precise category, benchmark graphics, "replaces" list, and pip-compatible migration path. | It frames adoption around replacing existing Python workflow tools incrementally. |
| [Svelte](https://svelte.dev/) | Uses a simple emotional headline, proof from surveys, company logos, community links, and maintainer/backer visibility. | It makes a framework feel like a movement without hiding the technical premise. |
| [Prisma](https://www.prisma.io/) | Combines a very short headline, `npx prisma init`, stack integrations, monthly developer count, and many developer quotes. | It pairs a commercial Postgres push with developer workflow credibility. |
| [Supabase](https://supabase.com/) | Names the substrate, lists the bundled primitives, shows recognizable users, and maps the product into common app needs. | The site makes a broad platform feel like one coherent Postgres-centered toolkit. |

## What the best headlines have in common

Strong headlines are short, concrete, and shaped around a job:

| Site | Headline pattern | Lesson |
| --- | --- | --- |
| DuckDB | Verb + job + differentiator | Put the unique execution model in the first line. |
| Bun | Category + audience + primary advantage | Tell the reader what bucket to put it in. |
| Astro | Category + ideal workload | Name the workload you are best at, not every workload you support. |
| Tailwind | Speed + workflow constraint | Tie the value to a developer pain point. |
| shadcn/ui | Infrastructure framing | Elevate components into system-building material. |
| Vite | Category ownership | Make the page easy to recall and search for. |
| uv | Category + implementation reason | "Written in Rust" supports the performance claim. |
| htmx | Memorable philosophy | A simple phrase can carry a whole worldview. |

Weak OSS headlines usually fail by saying "modern," "powerful," "open," "AI-native," or "developer-first" without naming the job.

## Show the thing

The strongest pages make the homepage self-proving:

- DuckDB shows SQL plus Python, Java, Node.js, and install commands.
- Bun shows command snippets and benchmark tables with versioned competitors.
- Tailwind shows HTML classes next to UI output.
- shadcn/ui shows real form, dashboard, table, chart, settings, and AI prompt UI fragments.
- Astro shows a `.astro` component and framework logos.
- htmx shows the actual `<script>` include and `hx-post` button.
- FastAPI shows the create/run/check path and links to interactive API docs.
- Vite shows one-command project creation across npm, Yarn, pnpm, Bun, and Deno.

The common principle: **the first page should contain at least one artifact a developer could paste, run, inspect, or recognize from their workflow.**

## Proof patterns

Not every project has enterprise logos. That is fine. The best sites choose proof appropriate to their maturity:

| Maturity | Best proof | Examples |
| --- | --- | --- |
| New / alpha | tests, coverage, license, supported backends, release cadence, architecture notes | Better than fake logos or vague "trusted by teams." |
| Growing OSS | GitHub stars, downloads, issue velocity, known adopters, community links | Vite and shadcn/ui surface stars; Vite also shows weekly downloads. |
| Performance-led | benchmark chart, methodology link, competitor versions | Bun and uv are strongest here. |
| Ecosystem-led | integrations, clients, formats, plugins, framework logos | DuckDB, Astro, Prisma, Supabase, TanStack. |
| Commercializing OSS | real customer logos, case-study metrics, named quotes | LangChain, Prisma, Supabase. |

Specific beats grand. "2,157 tests, 99% coverage, 4 backends" is more credible than "production-ready infrastructure" for an alpha package.

## Navigation and information architecture

Developer-tool navigation is usually best when it gives four entry points:

- **Start:** quickstart, install, create command, or tutorial.
- **Reference:** docs, API reference, configuration, CLI reference.
- **Evaluate:** GitHub, releases, benchmarks, roadmap, examples, comparison.
- **Belong:** blog, Discord, community, sponsors, contributors.

DuckDB adds a strong search shortcut and divides docs by installation, guides, data import, client APIs, SQL introduction, and "Why DuckDB." Vite exposes old version docs, plugin registry, changelog, GitHub, and community. FastAPI's left nav is dense, but it works because users can jump from tutorial to reference to deployment without leaving the docs surface.

For small OSS tools, this means the homepage does not need many pages, but it does need clear exits: **Install, Docs, Source, Examples, Community or Contact.**

## Voice and brand

The compelling sites do not sound identical:

- DuckDB is practical and database-native.
- Bun is performance-obsessed and direct.
- htmx is funny, contrarian, and philosophical.
- Tailwind is confident and specific about CSS.
- Svelte is warmer and community-oriented.
- shadcn/ui is minimal, design-system focused, and product-like.
- FastAPI is almost all substance, little polish, and still highly persuasive.

The lesson is not "be quirky." The lesson is **pick a worldview and let the copy, layout, and examples all reinforce it.**

## Anti-patterns

| Anti-pattern | Better move |
| --- | --- |
| Hero copy that could fit any developer tool | Name the job, substrate, and differentiator. |
| Abstract network/cloud/AI visuals | Show code, terminal output, UI, graph, schema, or benchmark. |
| Three to five equal CTAs | Use one primary path, one docs/source path, and one expert shortcut. |
| Fake enterprise polish for an early OSS project | Use alpha-appropriate proof: tests, coverage, architecture, supported integrations. |
| Feature cards with icons but no examples | Pair each feature with a command, path, snippet, or output. |
| "AI-native" without showing agent workflow | Show the loop: input, operation, result object, next operation. |
| Hiding docs behind marketing pages | Let docs, examples, GitHub, and quickstart be one click away. |
| Testimonials without names or specificity | Prefer metrics, named adopters, or no testimonial section. |
| Long prose before code | Put a pasteable artifact on the first screen. |

## Practical checklist

- [ ] The hero says what the package is in under 10 seconds.
- [ ] The headline names the job or differentiator, not just the category.
- [ ] There is a pasteable install command above the fold.
- [ ] There is real code, terminal output, UI, or benchmark above or immediately below the hero.
- [ ] The first code sample represents the core workflow, not a toy API call.
- [ ] Docs, GitHub, install, and examples are visible without scrolling or searching.
- [ ] The site shows proof appropriate to project maturity.
- [ ] Metrics include enough context to be credible.
- [ ] Ecosystem support is visible as a grid or list.
- [ ] The page answers "why this instead of X?"
- [ ] The voice has a clear point of view.
- [ ] The commercial path, if any, does not block OSS evaluation.
- [ ] The footer gives real deep links: releases, roadmap, issues, license, community.

## Implications for vfs.dev

vfs should borrow the structure, not the visual language. Its current spec-sheet/file system identity is more distinctive than a generic shadcn-modern landing page. The research points to a few concrete moves:

1. Keep the file system/spec-sheet identity.
2. Add a short job-shaped headline before the `vfs` wordmark.
3. Move code or terminal output into the hero.
4. Turn alpha proof into a spec strip: tests, coverage, backends, graph algorithms, license.
5. Add an integrations/backends grid.
6. Add a direct "why vfs?" comparison against vector DBs, `fsspec`, and retriever frameworks.
7. Promote the terminal route with a scripted homepage preview.

The target is: **DuckDB's practical clarity, Bun's proof density, htmx's point of view, and FastAPI's docs-first usefulness, expressed through vfs's own file system aesthetic.**
