# Brand

- **Status:** draft (v0.1) — seeded 2026-04-18 from `grover-lookbook.html` and existing repo voice
- **Purpose:** How the product shows up in the world.

> **Naming note.** The product is being renamed from "Grover" to **VFS** (`pip install vfs-py`). The lookbook (`grover-lookbook.html`) still says "Grover" and uses the tagline *"Rove through your data"* — that tagline was tied to the *grover/rover* wordplay and does not survive the rename. A new positioning line is `[NEEDS CLARIFICATION]`.

## Name

**VFS** — short for *virtual filesystem*. The name is the thing: a filesystem abstraction that doesn't require the data to actually live in one. The acronym is set, written, and spoken as **"V-F-S"** (three letters, not "viffs").

The package name on PyPI is `vfs-py` because `vfs` was already taken; the import is `vfs`.

## Positioning

One-line options on the table (none committed yet):

- *The agentic filesystem.*
- *Graph, vectors, and a filesystem — one namespace.*
- *The retrieval trifecta for generative AI.* (current lookbook hero, predates rename)

`[NEEDS CLARIFICATION: pick a positioning line for the README hero and homepage]`

## Voice

Five adjectives:

- **Direct** — say the thing. Not "leverages cutting-edge"; just "this is what it does."
- **Technical** — assume the reader knows what a filesystem and an embedding are. Don't define terms a developer would already know.
- **Dry** — humour is incidental, never performed. No exclamation points in marketing copy.
- **Concrete** — every claim attaches to a code example or a benchmark, not an adjective.
- **Quietly confident** — VFS is alpha, not vapourware. Show; don't oversell.

What that means in practice (from the lookbook, still load-bearing):

- ✓ "VFS mounts your graph as a filesystem. Agents use `ls` and `read` — tools they already have."
- ✓ "Vector search finds what's similar. Graph traversal finds what's connected. You need both."
- ✓ "`pip install vfs-py`. That's the whole ops story."
- ✗ "VFS leverages cutting-edge AI to revolutionise the retrieval paradigm."
- ✗ "Our enterprise-grade solution enables seamless integration with your existing infrastructure."
- ✗ "Unlock the full potential of your data with VFS's powerful platform."

## Tone by surface

- **CLI output** — terse, structured. Errors point at the path. No emoji, no colour codes the user didn't opt into.
- **Error messages** — name what failed, in what coordinate (path + filesystem), and what the user can do. Never "an error occurred."
- **Docs** — declarative, second person. Code first; prose around it. No "let's" or "we'll".
- **README** — single page, opinionated, ships the install command above the fold. Quick start in under fifteen lines of code.
- **Marketing / homepage** — three sentences and a code block beats a paragraph. Visual identity does the heavy lifting.

## Naming conventions

- **Module:** `vfs` (currently `grover`; mid-rename).
- **Top-level class:** `VFS` (the sync facade) and `VFSAsync` (the async core). Today: `Grover` and `GroverAsync`.
- **Filesystem class:** `VFSFileSystem` is the eventual name; today: `GroverFileSystem`. Backends inherit from it (`DatabaseFileSystem`, `MSSQLFileSystem`).
- **Result type:** `VFSResult` (today `GroverResult`).
- **CLI verbs:** Unix-shaped, lowercase, single word where possible (`read`, `write`, `glob`, `grep`, `search`, `tree`, `ls`, `stat`). Composed via `|` pipes that mirror the Python chaining API.
- **Domain terms we will not rename:** *file*, *directory*, *chunk*, *version*, *connection*, *mount*. These are Unix words; Unix won.

## Visual

- **Lookbook:** [`grover-lookbook.html`](../../grover-lookbook.html) — needs a rename pass but the system is still current.
- **Type:** DM Serif Display (wordmark, headlines), Instrument Sans (body), JetBrains Mono (code, eyebrows).
- **Palette — Forest (core):** Canopy `#1A2F23`, Understory `#243B2E`, Moss `#2D4A38`, Fern `#4A7C5C`, Sage `#7BAE8E`, Mint `#A8D5BA`, Meadow `#D4F0E0`, Daylight `#F0FAF4`.
- **Palette — Signal (pillar accents):** Ember `#E8734A` (primary CTA, entry point), Violet `#8B6CC1` (vectors), Cyan `#4ABCE8` (filesystem), Amber `#E8B44A` (warnings).
- **Palette — Neutral:** Bark `#1A1A18`, Stone `#2A2A27`, Cloud `#F5F5F0`, Snow `#FAFAF8`.
- **Imagery posture:** structural — directed graphs that read as trees, file trees as visual rhythm. No stock photos. No people. No abstract "AI" gradients.

`[NEEDS CLARIFICATION: does the existing logomark (the directed-graph-as-tree) survive the Grover→VFS rename, or do we redesign? It currently sits next to the wordmark "Grover" and the tagline that's being retired.]`

## Non-goals

- We do not want to sound like a SaaS landing page. No "platforms", no "solutions", no "transformative".
- We do not anthropomorphise the product. VFS doesn't *understand* or *think*; it indexes, returns, and routes.
- We do not adopt the visual language of generic AI products (purple gradients, neural-net hero illustrations, glowing orbs). The forest palette and structural marks are deliberate distance from that.
