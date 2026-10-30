# Study 01: The intention document

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: what format should an intention document take, when is one written, and how does it link forward to research and the spec? Its method: read Anthropic's published guidance on AI in the software development lifecycle (the playbook, the security article, the Claude Code docs); read the user-story prior art, the Connextra template, Amazon's PR/FAQ, Shape Up's pitch and the job story; read how the sibling project wasi-python frames a need before research; read the `Intent` section of vfs's own active specs and the first-draft intention. Time box 30 minutes; it was met.

## Sources

- Louis Claxton, "The AI-native SDLC playbook", Anthropic, 2026-08-21. <https://claude.com/resources/articles/the-ai-native-sdlc-playbook> (read 2026-10-29). Course form: <https://academy.claude.com/courses/ai-native-sdlc-playbook> and its "plan mode" lesson <https://academy.claude.com/courses/ai-native-sdlc-playbook/plan-mode> (read 2026-10-29).
- Jason Clinton, "How Anthropic secures its AI-native software development lifecycle", 2026-07-21. <https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle> (read 2026-10-29).
- Claude Code docs, "Best practices" <https://code.claude.com/docs/en/best-practices> and "Common workflows" <https://code.claude.com/docs/en/common-workflows> (read 2026-10-29).
- Connextra template: Wikipedia "User story" <https://en.wikipedia.org/wiki/User_story>; Cucumber blog on the origin <https://cucumber.io/blog/user-stories-are-not-the-same-as-features> (read 2026-10-29).
- Amazon PR/FAQ: About Amazon, "An insider look at Amazon's culture and processes" <https://www.aboutamazon.com/news/workplace/an-insider-look-at-amazons-culture-and-processes>; the Working Backwards guide <https://www.koji.so/docs/working-backwards-pr-faq-guide> (read 2026-10-29).
- Shape Up pitch: reflectoring book review <https://reflectoring.io/book-review-shape-up/>; Dan Lebrero's summary <https://danlebrero.com/2021/06/16/shape-up-summary/> (read 2026-10-29).
- Job story: Mountain Goat Software, "Job stories offer a viable alternative to user stories" <https://mountaingoatsoftware.com/blog/job-stories-offer-a-viable-alternative-to-user-stories>; thoughtbot's job story template <https://thoughtbot.com/blog/product-management-templates-job-story> (read 2026-10-29).
- wasi-python at `~/Git/Repos/wasi_python`, commit `1431ba6f` (read-only): `context/README.md`, `context/constitution.md` §2, §3, §5, `context/specifications/150-a-starting-image-the-embedder-chooses.md`.
- vfs at HEAD `1198d92`: `context/README.md`, `context/intentions/2026-10-29-the-development-process.md`, `context/standards/roadmap.md` (the user-story rule, lines 61–65), the `Intent` sections of `context/specs/active/{155,167,176,181}*/spec.md`, the header of spec 173.

Labels: READ means read from a cited source. INFERRED means my own reasoning on what was read.

Terms used below. An **intention** is the document written before research, saying what the project intends to do and why. A **user story** is one sentence naming a person, what they want, and the value they get. A **spec** is the specification: the design that decides every choice before code is written. A **research memo** is a dated study of precedent or an executed experiment.

## What the sources say

### Anthropic's guidance

- READ. The playbook names six stages: Plan, Design, Build, Test, Deploy, Maintain. The Plan stage produces one file, `intent.md`. It captures the idea once, in the originator's own words, as a version-controlled file the next stage can act on.
- READ. The intent file holds: the problem, the proposed outcome, the affected users and systems, the constraints, and open questions. The example carries a short header for author and status.
- READ. The intent file lives in an `intent/` folder in the product repo. Git records the author, the time and the history. The owner's accept or reject is the merge or the closed review.
- READ. The Design stage turns the accepted `intent.md` into `spec.md`, the requirements and design. The two are committed side by side, so the pair records what was asked for and what was decided.
- READ. The Build stage starts in plan mode with `spec.md`, and `intent.md` beside it when one exists. The plan names the files, the order of work, the risks and the proof. The lesson says an intent file is given "if one exists": not every change has one.
- READ. The Maintain stage closes the loop: a production metric leaving its range opens a new intent file.
- READ. Clinton's security article says humans "direct, set intent, and own final approval". It says planning has compressed and detailed documents are no longer required at every stage; context should be read from where it already lives.
- READ. The Claude Code docs say: interview me until you could write the spec, then write it to `SPEC.md`; build from it in a fresh session; point the reviewer at it; and before leaving a task to run alone, make sure it knows what done looks like.
- INFERRED. Anthropic's intent file is two things at once: the user's words, and the input the spec is generated from. It allows open questions, because it is written before anyone has studied the problem. The spec that follows closes them. That is the same split vfs wants: intention first, research in between, spec with no open questions.

### User-story prior art

- READ. The Connextra template (2001, Rachel Davies and the Connextra team, London) is one sentence: as a role, I want a capability, so that a benefit. Mike Cohn calls the "so that" clause optional but useful. It names a person, a want and a value. It says nothing about design.
- READ. Amazon's PR/FAQ is a one-page press release written as if the product has shipped, then a FAQ. The first half of the FAQ answers customer questions; the second half answers internal questions. It is written before any design and rewritten through several rounds of review.
- READ. Shape Up's pitch has five parts: the problem, the appetite (how much time the problem is worth), the solution sketched at low fidelity, the rabbit holes (traps to avoid), and the no-gos (what is deliberately left out).
- READ. The job story (Alan Klement, Intercom) replaces the persona with a situation: when a situation, I want a motivation, so I can get an outcome. The outcome should be concrete and testable, not a feeling.
- INFERRED. The four templates agree on three parts: a person or situation, the value wanted, and a check that the value arrived. They disagree on how much solution to include. Connextra and the job story include none. Shape Up includes a sketch. PR/FAQ includes the shipped experience. For vfs the right amount is none: the solution belongs to the spec. What vfs should take from Shape Up is the no-gos and the appetite. What it should take from PR/FAQ is the "written as if done" voice in the done-when section.

### wasi-python

- READ. wasi-python has no intention stage. Its pipeline is study → research → specify → build → review (`constitution.md` §5.1). Nothing is specified on a question no research has answered.
- READ. The need is written as a research memo. Spec 150's header cites "the need" by path and section (`research/2026-10-27-a-snapshot-the-embedder-chooses.md`, §1 the cost, §2 why the options fall short, §3 the shape) and "the spike" by path. The spec's first body section is "The problem", which restates the need with executed numbers and quotes the owner's decision verbatim with its line number.
- READ. The constitution's §2 states the goal "so it can be checked": five numbered facts a judge verifies. §3 lists "what this project is not".
- READ. A spec's header has: Status, Date, Owner, Kind, Depends on, Research it stands on. Every claim is labelled EXECUTED, READ or INFERRED.
- INFERRED. wasi-python folds the intention into the first research memo and the spec's "The problem" section. That works there because one person owns every need. vfs wants the need in its own file so a story can be read before a single memo exists. The thing to carry over is the citation discipline: the spec cites the need by relative path and section, and the problem is restated in the spec, never only pointed at.

## What vfs does today

- READ. The roadmap rule (`context/standards/roadmap.md`, lines 61–65): a story opens with a user story in the Connextra shape, with one of three named audiences, "agent", "software developer" or "ETL developer". The functionality is the point; the mechanism is the why.
- READ. Every active spec has an `## Intent` section. The older ones (051, 152, 157) describe what is wrong today. The newer ones (167 to 181) are written in the future tense from the user's seat: "After this spec an agent types … and gets …", and several end with "One line: …". Spec 173 is of kind "spike" and its intent is a go/no-go question.
- READ. A spec's header carries Status, Date, Owner, Kind, Depends on, Decisions it implements, Research it stands on. Research is cited by relative path and section. No header line points at an intention, because intentions did not exist.
- READ. The intention as rewritten today (`context/intentions/2026-10-29-the-development-process.md`) has a title and five sections: The story, What we intend to achieve, Part of the story, What this is not, Done when. No header lines, no number in the name. The story names "a developer on vfs, human or AI coding agent". The outcomes are experiences: output of high quality, people and agents who can hand work over, decisions a reviewer can question and a later reader can trust. The pipeline is one short paragraph under "Part of the story", named as the means, not the end.
- INFERRED. vfs already writes intent twice: once as the roadmap story, once as the spec's `Intent` paragraph. The intention document is the roadmap story grown to a page, written before research, with a done-when list the spec can inherit. The owner's correction of today sets the proportion: the page is about the experience; the mechanism gets one paragraph at most.

## The recommended format

The file is `context/intentions/YYYY-MM-DD-descriptive-slug.md`. The date is in the name. The title is the first line. The body starts right after it. There are no header lines.

The proportion is the rule. An intention is about the experience being enabled: who gets what, and how they will know they have it. Mechanism, the pipeline or the design that delivers the experience, gets one short section, and only when it is needed to make the story readable.

```markdown
# <The title, a short noun phrase, the same words as the file's slug>

## The story

<One sentence: "As a <developer | agent | software developer | ETL developer | owner>, I want <an experience>, so that <the value>." One story. If two audiences want it, two sentences.>

## The problem today

<Two to five sentences on what the audience cannot do or cannot trust now, each a fact. A fact that was run is labelled EXECUTED; one read from a file or page is labelled READ. No design.>

## What we intend to achieve

<A bullet list of outcomes. Each bullet is an experience: something a person or an agent can do, see or rely on after the work lands. No file names, no code spans, no choice between designs: those are the spec's.>

## Part of the story

<Optional. One paragraph, at most. The means, named as the means: "one written pipeline is how we get there". Nothing that decides a design.>

## What this is not

<A bullet list of the no-gos: what is deliberately left out, so the research and the spec do not grow to cover it.>

## Done when

<A numbered list of checks. Each is something the audience can do or find, written as if the work has landed, verifiable by a person. Counts, never clocks.>

## What the research must answer

<A numbered list of what must be learned before a spec can be cut. Each item is one research task. "None." when the spec can be written now; the intention then goes straight to a spec.>
```

Why each section is there. The story is the Connextra sentence; the roadmap already demands it. The problem today is the job story's situation and wasi-python's "The problem", written from the audience's seat. What we intend to achieve is the playbook's proposed outcome. Part of the story is Shape Up's low-fidelity sketch, cut to one paragraph and made optional, so the mechanism cannot take over the page. What this is not is Shape Up's no-gos. Done when is the constitution's "stated so it can be checked" and the PR/FAQ's shipped voice. Open questions is the playbook's open questions, and it is the only place in the whole pipeline where an open question is allowed to stand.

Say it again, shorter: a story, a problem, outcomes, one paragraph of means, no-gos, checks, questions. Nearly all of it about the value.

## When an intention is written and when it is skipped

The rule. An intention is written when any one of these holds:

1. Research will be commissioned. Research spends agent time; the intention is the sentence that justifies the spend and the list of questions the research answers.
2. More than one spec will carry the work. The intention is the one place that says what the series is for.
3. The work gives an audience an experience it does not have today, or takes one away. A new verb, a new way of working, a changed contract.

An intention is skipped when none of them holds: a fix to an existing contract, a refactor with no visible change, a docs change, a dependency bump. Those start at the spec. The spec's `Intent` section then carries the story in one paragraph, as the active specs do today.

The test to apply: "Will the spec's `Intent` paragraph need to say anything that the code and the tests do not already show?" If yes, write the intention first. If no, write the spec.

Same rule in one line: research never starts without an intention; a spec may.

## How it links to research and the spec

Links point backward only. A later document cites an earlier one by relative path. An earlier document is never edited to point forward, so the intention is frozen once the owner accepts it, exactly as a research memo is.

- A research memo written for an intention carries a header line `- **Intention:** ../intentions/YYYY-MM-DD-slug.md` and names which open question (by number) it answers.
- A spec cut from an intention carries a header line `- **Intention:** ../../intentions/YYYY-MM-DD-slug.md`. Its `Intent` section restates the story and the done-when list in the spec's own words; it does not only point. Its acceptance criteria include every done-when item, each mapped to a test.
- A spec with no intention carries `- **Intention:** none`, with a short reason from the skip list above (a fix, a refactor, a docs change).
- The spec's existing `- **Research it stands on:**` line stays as it is. The chain is intention → research → spec, and a reader walks it backward from the spec.

Finding an intention's spec is then a grep for its path, which a lint can do. The intention needs no "Becomes" line.

## A lint rule that could hold its shape

For every file under `context/intentions/`:

1. The file name matches `^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.md$`, and the slug does not begin with a bare number.
2. Line 1 starts with `# ` and nothing else precedes it.
3. No line before the first `## ` starts with `- **` (no header lines).
4. The `## ` headings are, in order: `The story`, `The problem today`, `What we intend to achieve`, `Part of the story` (optional), `What this is not`, `Done when`, `Open questions`. No other `## ` heading.
5. `The story` contains the three tokens `As a`, `I want` and `so that`, and names one of the audiences `developer`, `agent`, `software developer`, `ETL developer` or `owner`.
6. `What we intend to achieve` contains no code span (no backtick) and no path (no `/` inside a word). A design detail reads as mechanism; it belongs in the spec.
7. `Part of the story`, when present, is one paragraph: no blank line inside it, no list.
8. `Done when` is a numbered list with at least one item, and no item contains a time unit (`ms`, `second`, `minute`).
9. `Open questions` is a numbered list or the single word `None.`
10. The marker `[NEEDS CLARIFICATION` appears nowhere; a question goes in `Open questions`.

Rule 6 is the one that holds the owner's proportion: mechanism is detected by its vocabulary (paths and code), which an intention about experience has no reason to use. The review of the intention, not the lint, judges whether a bullet that passes rule 6 is still a design in disguise.

For every spec under `context/specs/active/`: a header line `- **Intention:**` exists, and its value is `none` followed by a reason, or a relative path to a file that exists. For every research memo dated after the process lands: the same line, path required.

## Where the first draft intention departs from the recommendation

The draft is `context/intentions/2026-10-29-the-development-process.md` as rewritten today after the owner's three corrections (no header lines; no number; experience, not mechanism). Most of the recommendation is now drawn from it. What still differs:

1. It has no `The problem today` section. What a developer cannot do today (pick up another's work from the repository alone; find why a decision was made; know that a landing was checked by a fresh reader) is implied by the outcomes, not stated as facts.
2. It has no `Open questions` section. The seven studies commissioned today are its open questions, and they are not written in it. Under the recommendation they would be seven numbered lines, each the question one study answers.
3. Its story's audience, "a developer on vfs, human or AI coding agent", is not one of the roadmap's three product audiences. That is right for process work, and the lint's audience list includes `developer` for it.
4. Its `What we intend to achieve` passes rule 6 as written: no paths, no code spans, every bullet an experience. The earlier draft of this morning failed it on three bullets (no decision records, a diagram, a named security skill); the rewrite moved them out, which is the proportion the rule holds.
5. Its `Part of the story` is one paragraph naming the pipeline as the means. That is the shape the recommendation makes optional and bounds to one paragraph.
6. Nothing in it points forward. That matches the recommendation: the spec will point back by relative path.

## One line

An intention is a dated page about an experience: a story, a problem, outcomes, one paragraph of means at most, no-gos, checks and questions; it is written whenever research starts or an audience gains a capability, it is never edited after acceptance, and the research and the spec cite it by relative path.
