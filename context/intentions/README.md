# /context/intentions

The INTENT stage of the pipeline described in [the context README](../README.md). An intention is a page about the experience a piece of work enables, written before any research starts and before any spec is cut. It is nearly entirely about what the project intends to do to provide value; the mechanism gets one paragraph at most, and the design belongs to the spec.

## When one is written

An intention is written when any one of these holds: research will be commissioned; more than one spec will carry the work; an audience gains an experience it does not have today, or loses one. A fix to an existing contract, a refactor with no visible change, a docs change or a dependency bump starts at the spec, whose Intent section carries the story in one paragraph. Research never starts without an intention; a spec may.

## The shape

The file is `YYYY-MM-DD-descriptive-slug.md`. The title is line one; there are no header lines. The sections, in order:

- **The story.** One sentence: as a developer, agent, software developer, ETL developer or owner, I want an experience, so that a value. Two sentences when two audiences want it.
- **The problem today.** What the audience cannot do or cannot trust now, as facts, each labelled EXECUTED (a command was run) or READ (a file or page was read), with the commit they were measured on. No design.
- **What we intend to achieve.** Outcomes, each an experience a person or an agent can have after the work lands. No file names, no code, no choice between designs.
- **Part of the story.** Optional. One paragraph of means, named as the means.
- **What this is not.** The no-gos, so the research and the spec do not grow to cover them.
- **Done when.** Numbered checks a person can verify, written as if the work has landed. Counts, never clocks.
- **What the research must answer.** Numbered questions, one research task each, or "None." when the spec can be written now. This is the one place in the pipeline a question stands.

An intention is frozen once the owner accepts it. The research memo and the spec link back to it; it is never edited to point forward. The worked example is [the development process](2026-10-29-the-development-process.md).
