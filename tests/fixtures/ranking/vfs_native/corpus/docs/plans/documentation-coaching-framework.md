# Documentation Coaching Framework & Process

> **Purpose.** This is the playbook for coaching documentation writing on `vfs`. It captures (1) the established frameworks, (2) the real-world reference models worth emulating, (3) the coaching *process* and collaboration contract actually used, and (4) the recurring heuristics for what to flag. Read this before helping write or review any doc here.

---

## 0. The collaboration contract (read this first)

How documentation work is run on this project. These are not defaults — they were established with the author and should be honored unless they say otherwise.

- **The author writes; the coach flags, does not rewrite.** Critique against the frameworks. Point at the seam. Do not silently replace their prose.
- **When asked to "write" something, give options, not a ghostwritten answer.** 2–4 labeled candidates, each optimized for a *different* thing, each with a one-line "what this optimizes for," followed by an editor's recommendation. (See the closing-paragraph and synthesis-closer interactions for the pattern.)
- **One thing at a time.** Be diligent and focused on the *specific* question asked. Do not flood with adjacent advice. End by naming the single next decision and offering a small set of ways forward.
- **Surface the load-bearing decision instead of writing around it.** When a doc can't progress because an underlying design/vocabulary choice is unmade, name it and force the choice. Do not paper over it with prose.
- **Track deferred items every turn.** When the author postpones something (a synthesis line, a transition, a vocabulary map), restate the open list so no promise goes unpaid. Never let a doc make a claim it never delivers.
- **Edit in passes.** Do not copyedit typos while the argument is still being composed. Flag the *pattern* once; the line-level pass comes later.
- **Affirm specifically and truthfully.** When the author's solution beats the coach's, say so and say exactly why. Recognition must be earned and concrete, never generic encouragement.
- **No memory files for this work.** Persistent knowledge for documentation coaching lives in this repo doc, not in the agent memory store.

---

## 1. The frameworks

### Diátaxis — the organizing skeleton (canonical: https://diataxis.fr/)

Documentation is four distinct kinds, on two axes: **Action ↔ Cognition** (is the content about *doing* or *thinking*?) and **Acquisition ↔ Application** (does it serve *study* or *work*?).

| Type | Serves | User need | Rule |
|---|---|---|---|
| **Tutorial** | learning (action+study) | "teach me" | A lesson, not a task. One reliable path, no options, no explanation (link out). Every step yields a visible result. Must work end-to-end every time. |
| **How-to** | tasks (action+work) | "show me how" | Starts from a goal a competent user already has. No teaching, no concepts. Title "How to X". May branch. |
| **Reference** | information (cognition+work) | "tell me" | Austere, neutral, complete. Mirrors the code's structure. Accuracy is the entire job. No instruction, no opinion. |
| **Explanation** | understanding (cognition+study) | "help me understand" | Discursive. Context, rationale, alternatives weighed. Read *away* from the work. No steps, no reference tables. |

**The compass:** for any page ask the two binary questions; the intersection deterministically gives the quadrant. The #1 documentation failure is **conflation** — explanation buried in a tutorial, instruction creeping into reference. Never mix modes on one page; split or link.

Origin: the **Divio system** (https://docs.divio.com/documentation-system/) by David Laing; Diátaxis (Daniele Procida) is its mature successor. Treat Diátaxis as the live reference.

### Google developer style — prose craft (https://developers.google.com/style, courses: /tech-writing)

- Active voice, present tense, second person. Don't anthropomorphize software.
- Define acronyms on first use; use terminology consistently.
- Short sentences, one idea each. Topic sentence first. One topic per paragraph.
- Numbered lists = ordered steps; bullets = unordered sets; keep items parallel; introduce with a lead-in.
- State scope, audience, and key point at the top. Counter the *curse of knowledge* (write to the reader's prior knowledge, not yours).
- Edit in passes — don't copyedit while drafting.

### Write the Docs — docs as code (https://www.writethedocs.org/guide/docs-as-code/)

Version control, plain-text markup, code review of doc PRs, issues, and CI (build + link-check + prose lint). Docs ship in the same PR as the code.

### arc42 + C4 — architecture docs (https://arc42.org/, https://c4model.com/)

Complementary, not competing. **C4** = visual zoom levels (Context → Container → Component → Code; most projects need only 1–2). **arc42** = a lean 12-section document template; fill only sections that carry signal. C4 diagrams populate arc42's structural sections. Record significant decisions as ADRs (arc42 §9).

### README-Driven Development (Tom Preston-Werner, 2010)

Canonical: https://tom.preston-werner.com/2010/08/23/readme-driven-development.html — *"A perfect implementation of the wrong specification is worthless."* Write the README/spec first — design in prose, where changing your mind is cheap. The README is a useful constraint: real enough to force decisions, small enough to avoid waterfall bloat. **Implication for `vfs`:** when docs describe an API the code doesn't have yet, that's legitimate RDD — *if* it's declared the canonical target and cascaded everywhere. Undeclared, it's just drift.

### Documentation-Driven Development & design-doc culture

DDD: *"if a feature is not documented, it doesn't exist."* Docs precede code; tests match the documented spec; doc version matches code version. Real case study with honest pitfalls: https://ubuntu.com/blog/a-year-of-documentation-driven-development (design docs adopted fast; user-docs-first required a real behavior change; did **not** fix legacy doc debt; uneven depth is fine — rigidity is the failure).

Design-doc template (Google, https://www.industrialempathy.com/posts/design-docs-at-google/): Context & Scope · **Goals and Non-Goals** · The Design (emphasize trade-offs) · **Alternatives Considered** · Cross-cutting concerns. Write one only if ≥3 of: design uncertain/contentious, senior input helps, cross-cutting concerns hard, documenting a legacy system. **Templates rot upward — keep them lean** (Google's backend RFC ballooned to ~14 empty pages).

### Specification by Example / docs-as-tests

The structural fix for doc/code drift: the spec is *executed against the code* (doctests, golden/snapshot tests, Gherkin). If code changes and the example breaks, the build fails, forcing the doc current. Gojko Adzic, *Specification by Example* (2011); Python `doctest`.

---

## 2. Reference models to emulate

Ranked for a database-backed virtual filesystem.

1. **SQLite file format spec** — https://sqlite.org/fileformat.html — *The* model for on-disk/wire Reference. Offset/size/description tables; every constant in hex; for each fixed invariant, state why it is fixed; separate version axes; a dedicated legacy/compat-constraints subsection. Use for `reference/metadata-paths.md` (the `/.vfs/.../__meta__/...` format).
2. **Rust RFC template** — https://github.com/rust-lang/rfcs/blob/master/0000-template.md — Best design-doc forcing function. Summary · Motivation · Guide-level · Reference-level · **Drawbacks** · **Rationale & alternatives** · Unresolved. Never allow an internal design doc without Drawbacks + Alternatives.
3. **Oxide RFD process** — https://rfd.shared.oxide.computer/rfd/0001 — Lifecycle/culture model: explicit state machine in the header, structured metadata, living documents (evolve after merge).
4. **rqlite design doc** — https://rqlite.io/docs/design/ — Closest analog (SQLite-backed system). Names the authoritative store, the consistency invariant, exact durability knobs, recovery per failure mode. Shape for `explanation/filesystem-internals.md`.
5. **Diátaxis** — the top-level skeleton (see §1).

Honorable mentions: **SQLite "As An Application File Format"** (https://sqlite.org/appfileformat.html — design-rationale template: name alternatives → their specific failure modes → why this design → honest overhead; use for `explanation/why-database-backed.md`); **Stripe API docs** (https://docs.stripe.com/api — runnable examples adjacent to every reference entry; docs as a product); **Tailscale deep-dives** (https://tailscale.com/blog/how-nat-traversal-works — first-principles explanatory narrative: state the core idea in one sentence, back claims with measured numbers, tell the story of why the design changed).

---

## 3. The coaching process (the loop actually used)

**Step 0 — Diagnose before doing anything.** A stuck-on-docs feeling is rarely a writing gap. Check for: planning *sprawl* with no canonical source of truth; mode confusion (one page doing all four Diátaxis jobs); or an unmade design/vocabulary decision hiding inside the prose. Name the real blocker.

**Step 1 — Build the skeleton.** Create the Diátaxis directory structure (`tutorials/ how-to/ reference/ explanation/`) with stub files. Each stub opens with an HTML comment stating its Diátaxis type, the one rule for that bucket, and the source file to migrate from — so the constraint is in front of the author while they write. Update site nav to match. Do **not** migrate or delete existing content; it is source material. (HTML comments are invisible in the rendered site and meant to be deleted when the page is done.)

**Step 2 — Decide the spine before prose.** If a page can't progress, there is usually one undecided thing: the rhetorical backbone (e.g., "a list of assumptions" — how many, what structure, parallel phrasing), or a vocabulary decision (target API names vs. code names). Force that decision; everything downstream depends on it.

**Step 3 — Write-then-review loop.** Author drafts; coach reviews against: correct Diátaxis mode, prose craft (Google), accuracy vs. code, and unpaid promises. Lead with specific earned praise, then the single most important issue, then ≤3 smaller diligent flags, then the next decision.

**Step 4 — Options, not ghostwriting.** When explicitly asked to write: produce 2–4 labeled candidates, each optimized for a different property (coherence / memorability / paying off an existing thread), each with a one-line rationale, then an editor's recommendation — possibly a splice of two.

**Step 5 — Generative questions for "why" content.** An Explanation's conviction must be the author's. The fastest way in is sharp diagnostic questions whose answers *become the section's spine* ("What did you personally hit that made this necessary?" → the problem section).

---

## 4. Recurring heuristics — what to flag

- **Mode mismatch.** "This is the wrong Diátaxis mode for this page" — e.g., an API catalog (Reference) stapled to a *why* page (Explanation). Relocate, name the destination file.
- **Author-voice vs reader-voice.** Cut narration of the writing process ("Now I want to re-write…", "Let's now…", "I'm going to…"). Keep the device, delete the scaffolding. These almost always delete cleanly.
- **Under-earned leap / unpaid promise.** A section that promises X (in its heading or a lead-in) but never delivers X. The most important review finding; state it as the headline, not a footnote.
- **Parallelism in enumerations.** A framework of N items reads stronger when the items are grammatically parallel — parallelism signals "these are siblings." Vary the *second* sentence, not the first, if it feels templated.
- **The definition-substitution device.** Re-quote an earlier definition and substitute concrete terms into it; the reader reaches the conclusion a beat before it's stated. Stronger than asserting a synthesis. (Worked well for "An AI coding agent is an LLM using a *terminal* to interact with a *file system*.")
- **Reference accuracy is non-negotiable.** Never invent signatures or names for Reference docs. If the target vocabulary is unmade, force the decision (Step 2) before writing — confidently-wrong reference docs are the RDD failure mode.
- **Narrator consistency.** Watch for drift between "I" / "we" / "VFS" as the speaker. A founder's *why* page is strongest in one consistent voice. Flag once it becomes a pattern; fix on the edit pass.
- **Subtle taxonomy seams.** When a label absorbs something that doesn't cleanly belong (e.g., "lexical" search under the *meaning* dimension), name the seam and propose the cleaner model, even if the current version is defensible.

---

## 5. Canonical URL index

- Diátaxis — https://diataxis.fr/ · compass https://diataxis.fr/compass/
- Divio — https://docs.divio.com/documentation-system/
- Google style — https://developers.google.com/style · courses https://developers.google.com/tech-writing
- Write the Docs / docs as code — https://www.writethedocs.org/guide/docs-as-code/
- C4 — https://c4model.com/ · arc42 — https://arc42.org/
- README-Driven Development — https://tom.preston-werner.com/2010/08/23/readme-driven-development.html
- Design Docs at Google — https://www.industrialempathy.com/posts/design-docs-at-google/
- RFC/design-doc roundup — https://blog.pragmaticengineer.com/rfcs-and-design-docs/
- DDD case study — https://ubuntu.com/blog/a-year-of-documentation-driven-development
- Specification by Example — https://en.wikipedia.org/wiki/Specification_by_example
- SQLite file format — https://sqlite.org/fileformat.html
- SQLite as application file format — https://sqlite.org/appfileformat.html
- Rust RFC template — https://github.com/rust-lang/rfcs/blob/master/0000-template.md
- Oxide RFD — https://rfd.shared.oxide.computer/rfd/0001
- rqlite design — https://rqlite.io/docs/design/
- Stripe API docs — https://docs.stripe.com/api
- Tailscale NAT traversal — https://tailscale.com/blog/how-nat-traversal-works
