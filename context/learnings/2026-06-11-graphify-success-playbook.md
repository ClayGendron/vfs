# Graphify success playbook — what made it win, and what transfers

> Date: 2026-06-11
> Reference repo: `/Users/claygendron/Git/Repos/graphify` (now YC S26, PyPI
> `graphifyy`, active external-contributor flow)
> Companion to [`2026-04-20-graphify-and-lightrag.md`](./2026-04-20-graphify-and-lightrag.md)
> (technical internals — extraction passes, confidence tags, cache design) and
> [`2026-06-09-direction-and-developer-first-strategy.md`](./2026-06-09-direction-and-developer-first-strategy.md)
> (VFS direction). This doc covers what those two don't: the distribution and
> product mechanics behind the breakout.

## If only one sentence survives

Graphify's secret sauce is not the graph — it's that the tool is **distributed
as a skill inside ~20 coding agents, uses the host agent's own model so it
needs no API key, steers the agent back to itself via always-on hooks, commits
its artifact to git so adoption spreads team-wise, and backs its pitch with a
reproducible token-reduction benchmark** — every one of which is a
go-to-market mechanism implemented as code.

## What changed since the April analysis

In April graphify was a well-built tool. Since then (CHANGELOG v0.8.x, ~60
recent commits, many external PRs): platform installers grew from a handful to
~20 assistants, the PreToolUse steering hooks shipped, `graphify-out/` became
a committable team artifact with a git merge driver, the `worked/` benchmark
corpus became the canonical contribution channel, and a paid layer (Penpax,
"always-on graph of your working life") appeared on top of the OSS core. The
core pipeline barely changed. **The success delta is almost entirely
distribution work** — roughly 60% of the 35k-line codebase is platform/install
glue, and they treat that glue as the product.

## The seven mechanisms

### 1. Skill-first distribution: the agent is the runtime

`/graphify` is a SKILL.md that orchestrates the *host* agent: it dispatches
parallel subagents (20–25 files each, all in one message) to do semantic
extraction using whatever model the user's IDE session already runs. The
skill explicitly forbids the slow path ("Reading files yourself one-by-one is
forbidden — it is 5-10x slower").

Consequences: no API key, no rate limits, no inference cost to the vendor, and
the install motion is `uv tool install graphifyy && graphify install` — one
command per platform, ~20 platforms. The CLI is the same engine headless
(`graphify extract --backend ...`) for CI.

**For VFS:** the roadmap's "VFS Agent Skill" (direction doc, DX item 4) is
under-scoped as a docs aid. Graphify shows the skill *is* a primary product
surface: a `/vfs` skill that ingests a directory/corpus into the namespace
using the host agent for any semantic work (summaries, edge inference), with
`vfs install --platform ...` writing the skill file for each assistant. MCP
server and skill are complements: skill = build/ingest moments, MCP = query
loop. Structural verbs (glob/grep/graph-from-AST) should work offline with
zero keys, exactly like graphify's "code-only corpus requires no API key."

### 2. Always-on steering: retention implemented as a hook

`graphify claude install` writes a CLAUDE.md section plus a **PreToolUse hook**
that fires before grep/Read-style tool calls and nudges: "first run
`graphify query \"<question>\"` when graphify-out/graph.json exists … returns a
scoped subgraph, usually much smaller than raw grep output." On platforms
without hooks, AGENTS.md / `.cursor/rules` carry the same query-first
instruction.

This makes the *agent* the repeat-usage channel — every codebase question is
a chance for the graph to prove itself, with zero human habit change.

**For VFS:** ship `vfs claude install` (and peers) that wires "for questions
over mounted knowledge, query the VFS namespace before grepping raw files"
via the same hook + instruction-file mechanisms. This is cheap, additive to
the MCP plan, and is the difference between "installed once" and "used daily."

### 3. The artifact is committed: team-wise viral loop

`graphify-out/` is meant to be committed. One dev runs it; everyone who pulls
gets a working graph immediately; a post-commit hook keeps the AST layer fresh
for free; a git **merge driver** union-merges `graph.json` so two devs
committing in parallel never see conflict markers; `manifest.json` keys are
relative paths so the cache is portable across checkouts.

**For VFS:** decide what the committable/shareable namespace artifact is.
Options: a SQLite `vfs.db` checked in for small corpora, or an export/import
format (`vfs export` → deterministic file → `vfs import`). Whichever it is,
the team story "one person builds the namespace, everyone's agent mounts it on
pull" needs a deliberate answer, including merge semantics. This is also the
bridge from single-dev OSS adoption to the org product.

### 4. A reproducible headline number

`benchmark.py` measures corpus-tokens vs query-subgraph-tokens over five
canned questions and prints a ratio. `worked/` holds full reproduction
kits (raw inputs + outputs + honest `review.md`) — e.g. karpathy-repos: 52
files → **71.5× token reduction**. Anyone can re-run it; the README's claim is
verifiable, and worked examples are the #1 requested community contribution
(they double as regression fixtures).

**For VFS:** create the equivalent: `vfs benchmark` comparing raw-corpus
tokens vs glob/grep/glean/graph answer-context tokens on a public corpus, and
a `worked/` (or `examples/corpora/`) directory with reproduction kits and
honest reviews. The four-verbs pitch currently has no number attached;
"agents answer in N× fewer tokens over a VFS mount than over raw files" is
the missing headline, and Anthropic's own "98.7% token reduction" framing
(direction doc, Part 2) shows the market responds to exactly this metric.

### 5. Instant gratification output

One command yields three files, one of which is `graph.html` — clickable,
zero-dependency, openable immediately — plus a `GRAPH_REPORT.md` with "god
nodes, surprising connections, suggested questions." The first five minutes
end with something visual and shareable (screenshots of graph.html are their
organic marketing).

**For VFS:** the quickstart currently ends with API calls returning Python
objects. Add a "look at what you built" moment: `vfs report` (markdown map of
the namespace: biggest mounts, most-connected files, suggested queries)
and/or a small self-contained HTML view of the namespace + edge graph. The
direction doc's `_repr_html_` item is the same instinct — extend it to a
first-run artifact.

### 6. Honest uncertainty as a trust feature

Every edge carries `EXTRACTED | INFERRED | AMBIGUOUS`; the report says what
was found vs guessed. (Covered in depth in the April doc — confidence +
provenance columns on `vfs_objects`, `min_confidence` on the read path. Still
the right call; graphify's continued growth confirms users reward visible
uncertainty rather than punishing it.)

### 7. OSS core + adjacent paid product, not a gated core

Apache-style OSS tool → Penpax (hosted always-on layer, "no cloud, fully
on-device", waitlist) + a book + sponsors. The paid product applies the same
engine to a different corpus (your whole working life), rather than gating
features of the dev tool. Matches the direction doc's two-sided model; the
confirmation is that nothing in graphify's OSS quickstart asks for an account.

Smaller tactical notes:

- **Name defense:** PyPI squatters forced them to `graphifyy` with a README
  disclaimer. Register `vfs-py` (and close variants) on PyPI *now*, before
  any launch noise.
- **Windows/PowerShell/WSL papercuts** get their own README sections and many
  community PRs — cross-platform install friction is where contributors show
  up first.
- **Hub suppression in query ranking** (don't traverse through p99-degree
  nodes) is directly relevant to VFS's graph verb and pagerank pipeline —
  god-node neighbors otherwise dominate every answer.

## What does NOT transfer

- **Graphify is a static-artifact generator; VFS is a live system.** Don't
  pivot toward "VFS builds you a graph.html." VFS's differentiation (April +
  June docs) remains live typed edges, mounts over heterogeneous backends,
  database substrate, MCP-native query. Graphify is, if anything, a future
  *mount source* (its graph.json could be mounted) and a validation that
  "queryable structure over a corpus beats grepping raw files" sells.
- **20-platform glue is a follower move for them, premature for VFS.** They
  built it after product-market fit on Claude Code alone. VFS should do
  Claude Code (skill + hook + MCP) excellently first; the installer
  architecture just shouldn't preclude adding platforms later (keep skill
  content separate from per-platform writers, as graphify does).
- **Their query engine (TF-IDF + BFS over NetworkX) is weaker than VFS's
  planned Postgres-native glean/grep.** Nothing to borrow there beyond hub
  suppression.

## Sequencing impact on the v0.1.0 plan

The June direction doc's DX list (zero-config client, Arrow, CLI+MCP, skill,
notebook polish) stands. This playbook adds/strengthens, in order of leverage:

1. `/vfs` skill + `vfs install` for Claude Code (skill-first distribution, §1)
   — promote from "docs aid" to a launch surface alongside the MCP server.
2. `vfs claude install` always-on hook + instruction injection (§2).
3. `vfs benchmark` + one worked-example corpus with the token-reduction
   number (§4) — this is the launch post's headline.
4. First-run report/HTML artifact (§5).
5. Committable-namespace story (§3) — can land after v0.1.0 but design the
   export format before the schema freezes.
