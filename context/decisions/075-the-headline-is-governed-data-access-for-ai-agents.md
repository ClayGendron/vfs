# 075. The Headline Is "Governed Data Access for AI Agents"; the Mechanism Line Stays as the Sub-headline

- **Status:** accepted 2026-10-08 (Clay, in conversation: chose the line from a set of seven and asked for it to be saved). Refines ADR 058 pin 1 — the category phrase "the access layer for agents" stands as the category; this record fixes the *headline*, the first line a reader sees, which ADR 058 had set equal to the category phrase. ADR 058 pins 2–8 and ADR 069 are untouched.
- **Date:** 2026-10-08
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay). Claude drafted the alternates, the competitive check, and this record.
- **Context source:** ADR 058 (the category, the mechanism line, the stack line), ADR 069 (the three differentiators), and a web survey run in-session on 2026-10-08 of who already uses the phrase, cited in Context.

## Context

Clay proposed "The governed retrieval system for any AI use case" and asked for a read. Three things were wrong with it. "Retrieval system" narrows vfs to the read half and files it under RAG, where the comparison is recall benchmarks and embedding models, not enforcement. It drops the file system, which is the README's hook (the agent already knows `ls`, `grep`, and `cat`). "For any AI use case" picks no buyer; ADR 058 pin 8 already picked one. One word was right: "governed" is the differentiator ADR 069 ratified, the one thing no category peer has (every peer uses the database as a disk; none uses it as a gate).

Clay then wrote two lines and asked for five more and a pick:

> Governed data access for AI agents
> Governed access to your data, for all the agents you run.

The five alternates (the governed file system for AI agents; every agent, one governed view of your data; your data, governed, for every agent you run; one governed namespace for every agent you run; governed access to everything your agents can see, search, and change) all kept "governed", the agent, and the data. Clay's first line won: four words, every one earning its place, reads as a category. ADR 058's mechanism line already said everything the sub-headline needed, so it stays unchanged beneath it.

**Who already says something close.** Nobody uses the exact headline. The phrase space is occupied, and the neighbours are the right ones to be contrasted with:

| | Immuta | hoop.dev | Cube | Kiteworks | vfs |
| --- | --- | --- | --- | --- | --- |
| Their line | "Agentic Data Access"; page title "Secure data access for AI agents"; blog "Governed Data Access for the Agentic Era" | "Autonomous agents need autonomous controls." | article "Governed AI Data Access": "the control plane between an AI system and the data it can use" | "the industry's first data-layer governance solution purpose-built for AI agent governance" | this record |
| Where it enforces | SaaS above the warehouse (vends a short-lived scoped role per agent request) | network proxy, a sidecar | the query compiler (a semantic layer) | inside its own content store | in-process, at the router, before dispatch |
| What it governs | tables | SQL and shell commands | metrics | files in Kiteworks | paths — files, rows, tools — in one namespace |
| Needs | Snowflake or Databricks | a sidecar | a semantic model | Kiteworks | a DSN |
| Writes | implied by role grants | approval per risky command | no | yes | yes; every mutation versioned and reversible |
| Search | no | no | analytics queries | no | glob, grep, glean, graph |
| Agent interface | SQL | SQL | MCP over metrics | MCP | the file system the model already knows |
| Open source | no | yes | core yes | no | yes |

Immuta is the closest on wording; hoop.dev is the closest in shape (open source, in the data path, covers Postgres, MySQL, S3, GCS, NFS, masks PII, blocks destructive statements, routes risky writes to a human). Databricks Unity AI Gateway and CData Connect AI Gateway (early access 2026-09-29) are registries plus gateways that reuse their platform's row and column policies and require that platform. None of them gives the agent an interface, and none versions what the agent changed.

Sources (all vendor copy, read 2026-10-08):
<https://www.immuta.com/platform/agentic-data-access>,
<https://www.immuta.com/blog/immuta-snowflake-new-agentic-data-access-capabilities/>,
<https://hoop.dev/>,
<https://cube.dev/articles/governed-ai-data-access>,
<https://www.kiteworks.com/cybersecurity-risk-management/ai-agent-data-governance-why-organizations-cant-stop-their-own-ai/>,
<https://siliconangle.com/2026/09/29/cdatas-ai-gateway-governs-agents-access-to-enterprise-data/>,
<https://databricks.com/blog/building-open-ecosystem-ai-governance-unity-ai-gateway>,
<https://www.prnewswire.com/news-releases/bigid-extends-data-access-governance-to-ai-agents-302724948.html>.

## Options considered

- **A. "The governed retrieval system for any AI use case"** (Clay's first draft). *Pro:* "governed". *Con:* read-only category, RAG shelf, no file system, no buyer. Rejected.
- **B. Keep ADR 058's headline, "the access layer for agents".** *Pro:* already ratified; says "in the path". *Con:* does not say the one word the market is buying and the peers lack. Kept as the category phrase, not as the headline.
- **C. "Governed data access for AI agents."** with ADR 058's mechanism line as the sub-headline. *Pro:* names the differentiator in the first word, the surface in the second, the buyer in the last two; the sub-headline carries the mechanism and the "change" verb that "access" alone would under-sell. *Con:* lands on Immuta's shelf. That is the intended contrast (Immuta governs the warehouse and sees tables; vfs governs the namespace the agent works in and sees files, rows, and tools). **Chosen.**
- **D. Any of the five alternates.** Longer, or lead with a noun that is not the category. The strongest, "governed access to everything your agents can see, search, and change", is kept as a second line for places with no room for the pair below.

## Decision

The public headline and sub-headline are, verbatim:

> **Governed data access for AI agents.**
> One namespace of everything an agent can see, search, and change. You decide what's in it.

1. **The headline is the four-word line.** It is the README's title line, the PyPI summary, and the MCP server description where one line is all there is room for.
2. **The sub-headline is ADR 058's mechanism line, unchanged.** It carries "change", which keeps governed *mutation* (ADR 069 pin 1) in the pair; "access" alone reads as read-only.
3. **"The access layer for agents" remains the category phrase** for prose that asks what kind of thing vfs is. ADR 058's three-line stack is still the canonical opening paragraph beneath the pair.
4. **The contrast to say out loud when the headline is challenged:** the peers govern tables or commands on one platform; vfs governs one namespace of files, rows, and tools on any database, with versioned writes and search built in. This is ADR 058 pin 6 restated for the wider shelf.

## Consequences

- **The README title line changes** from "vfs — the access layer for agents" to the headline above; the bold mechanism line already beneath it stays. Not landed with this record.
- **The alpha banner stays load-bearing.** Immuta, hoop.dev, and Kiteworks ship enforcement today; vfs's router-level and per-prefix permissions are built, and principals and row-level grants are designed, not built (spec 150; ADR 069's honesty lines). "Governed" is a claim the peers make in full and vfs makes in part until those land. ADR 058 pin 7 governs: no public line claims a feature the tree does not have.
- **The headline puts vfs on the data-governance shelf**, next to Immuta rather than next to the filesystem-for-agents peers of ADR 069. Comparison pages and docs should lead with the table above, not with the verb set.
