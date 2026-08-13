# October 2026 Talk — Abstract Working Doc

- **Status:** draft (v0.1) — seeded 2026-08-07
- **Owner:** Clay Gendron
- **Premise:** talk lands in October 2026; abstract is written against VFS
  0.1.0 (four verbs + MCP surface live), not today's tree.
- **Prior doc:** `business/aie-worldsfair-2026-submission.md` (AIEWF 2026,
  June — deadline passed; title stances and arc mined from it).

---

## 1. Venue calendar for an October talk

| Venue | Dates | CFP window | Fit notes |
|---|---|---|---|
| **AI Engineer NYC 2026** | Oct 12–14, NYC | **Jul 17 – Sep 12, 2026** (waves ~Aug 15, ~Sep 1, final Sep 15) — https://sessionize.com/aienyc2026/ | The live door. Mainstage theme is AI in Financial Services and vendor-only mainstage talks are banned; track talks are open-topic. First-person production case studies are the accepted shape. 18-min stage talks, no Q&A, live demos favored. |
| MLOps World, Austin | Oct 8–9 | closed ~Aug 1 | Missed for 2026; wants "the good, the bad, and the lessons learned" — same abstract works for 2027. |
| All Things Open, Raleigh | Oct 19–20 | closed Mar 31 | Missed for 2026. |
| AIE CODE 2026, SF | Nov 11–13 | Jul 17 – Oct 11 | Backup if October slips; explicitly welcomes vendor/builder talks. |
| QCon SF | November | invitation/rolling | Path in is visibility (blog posts, production war stories), not CFP polish. |

---

## 2. The one-sentence message

**Your agent already learned the interface to your organization's knowledge
— Unix — during pretraining; mount your database as a filesystem and that
training becomes the tool schema.**

Two pillars, everything serves them:

1. **Novel approach** — filesystem semantics + four agent-native search
   verbs over any SQL database, behind one MCP tool.
2. **Real-world case study** — how I use VFS day to day at my organization:
   personal, department, and organizational wikis on one namespace.

## 3. Title options (ranked)

1. **"Unix Beats RAG. Engineer Data as a File System."** — primary. Vetted
   stance from the AIEWF doc; thesis-as-title matches the accepted-talk
   corpus ("Kubernetes Is Not Your Sandbox", "The Base Model is Dead").
2. **"Four Verbs, One Namespace: glob, grep, glean, graph."** —
   numbers-in-title pattern ("500 Skills, Zero Fine-Tuning"); best for a
   search/retrieval track.
3. **"Your Wiki Is a Filesystem. So Is Your Database."** — leads with the
   wiki use case; best if the knowledge-base story goes front and center.

Still banned: *enterprise*, *leveraging*, *composable*, *unified platform*,
*seamless*, *next-gen*.

## 4. The abstract

Structure is Ben Dunphy's formula (linked from every AIE CFP): hook →
problem with empathy → solution tease → explicit learning outcomes. 4–6
sentences, flat prose, no bullets.

> Your agent spent its entire pretraining driving Unix — `ls`, `grep`,
> `cat` — and then we hand it a retrieval stack it has never seen. So
> agents operating on real organizational knowledge become the integration
> layer across a vector store, a graph database, a blob store, and an auth
> service, paying for it in context tokens, latency, and reconciliation
> bugs. VFS takes the opposite bet: mount the SQL databases you already run
> as one filesystem and let pretraining be the interface — four verbs
> (glob, grep, glean, graph) behind a single MCP tool, where a personal,
> department, or company-wide wiki is just a directory with a grant. This
> is a production case study, not a concept: I'll walk through the
> namespace I work in every day at my organization — how the wikis are
> laid out, what agents actually do with them, and what broke along the
> way. You'll leave with a mental model for filesystem-shaped agent
> knowledge, the design rules that keep one namespace honest from SQLite
> to Oracle, and an open-source runtime you can mount on Monday.

## 4b. Long-form CFP answers (250-word-minimum abstract + uniqueness field)

For forms that want a fuller abstract ("minimum 250 words") plus a "what
makes your session unique" field (max 150 words).

Copy-paste ready: no em dashes, one line per paragraph.

### Session Abstract (~325 words)

Every team building agents over organizational knowledge is working in a fragmented ecosystem. AI engineers, data engineers, and software engineers are building ETL pipelines, vector stores, graph databases, SQL databases, APIs, and tools, each with its own access-control layer and data governance. The result is an environment that is hard for developers to develop in and hard for agents to understand and operate within.

There is a better way for both parties, and that is to build on an abstraction engineers and large language models already understand deeply. That abstraction is the file system.

This session presents VFS, an open-source virtual file system built for agents. It provides a Unix-like CLI and agent-native tooling for search that spans pattern matching, semantic meaning, and graph traversal. All of it persists to a SQL database you already have and is exposed as an MCP server your enterprise agents can connect to. Every action is versioned and reversible, so a wrong write is a restore and not an incident. VFS can also mount external MCP servers, CLIs, and tools, and agents can write and run scripts in a hermetic runtime that never touches the host machine's real file system. And permissions work the way your organization already expects from OneDrive, Dropbox, or a shared drive, where personal, department, and organization-wide spaces are directories with grants.

The second half is a case study from daily production use, showing how I use VFS at my own organization to build our enterprise agents. I'll show how we construct the namespace, how agents connect and perform actions inside it, the key design decisions behind how VFS itself was built, and the lessons we learned along the way.

You will leave with a clear mental model of how to build agentic search for your personal or enterprise agents, the design rules that make command-line interfaces work for large language models, and an open-source runtime you can put to work the same week.

### What makes your session unique (~133 words, max 150)

Most retrieval talks add another layer to your existing agent stack. This one proposes a single complete system. The core claim goes beyond the now familiar point that agents are fluent in the command line. VFS is a CLI built for agents from the ground up, with agent-native tooling for pattern matching, semantic search, and graph traversal, permissioning that works like a shared drive, and a design shaped around ETL pipelines. That means data engineers can adopt it to build out a knowledge base while AI engineers and software engineers use the same system to build agents. The session pairs that claim with a real-world case study of how I use VFS every day for my enterprise agents and for my personal use, with a live demo, and everything shown is open source.

## 5. "What attendees will learn" (for venues with a separate field)

- Why filesystem semantics beat bespoke tool schemas for agent search —
  pretraining as the interface contract.
- The four-verb model of agentic search: location (glob), content (grep),
  meaning (glean), connection (graph) — one composable result type,
  classified errors agents branch on instead of tracebacks.
- Running personal, department, and organizational wikis on one namespace
  where isolation is authorization, not path rewriting (the Unix model —
  ADR 006).
- Production constraints designed in from day one: Oracle's 1,000-element
  IN-list cap (ORA-01795) as the design floor, 10k+-file batches as a
  supported contract, delete-never-destroys (sweep is developer-plane only
  — agents structurally cannot destroy).
- Honest lessons from daily use at a real organization: what broke, what
  agents did that surprised me.

## 6. Forward-looking claims ledger (0.1.0 dependency)

The abstract promises the 0.1.0 system. Track the gap:

| Claim in abstract | Status today (2026-08-07) |
|---|---|
| glob + grep | **Live and proven** — trigram index, differential batteries vs `find`/`grep -E`/`rg`, four real-engine conformance legs green |
| glean (semantic) | Protocol exists (`SupportsGlean`); backend not landed |
| graph traversal | Protocol exists; `mkedge` is the last classified stub |
| One MCP tool | Wire contract drafted (spec 045, ADR 022 proposed); spec 056 MCP trio unlanded |
| Wiki permissions story | Per-mount `PermissionMap` live; per-principal row grants designed (ADR 021), not landed |
| Hermetic runtime (agents write/run scripts, mount external MCPs/CLIs/tools) | Open research question today (Monty vs CPython-on-WASI, `context/open-questions.md`); Clay committed 2026-08-07 to having it ready for the talk |

If 0.1.0 slips past the talk date, the demo hollows out — the case-study
beats (wiki layout, daily use, what broke) stand on what's already true,
but "four verbs" does not.

## 7. Remaining gaps before submission (carried from AIEWF doc)

1. **One quantified number from the org deployment** — corpus size, query
   latency, or agent task-success delta. The 2026 accepted-abstract corpus
   is unambiguous: hard numbers + failure-forward honesty are what separate
   accepted case studies from concept talks.
2. Speaker bio: one credential + one proof point, third person.
3. Demo screenshot: terminal session of the four verbs over the real wiki
   namespace (anonymized).
4. Named-but-anonymous deployment framing is fine ("the data team at a
   ~N-person company"); vague is not.

## 8. What the conference research established (with sources)

**Landing well / hungry:** agent memory (promoted to its own 2026 track),
search-for-agents ("almost no one is building it right" got a track slot —
Exa), context engineering, anti-naive-RAG framings, production case studies
with insider numbers (Uber, LinkedIn, DoorDash).

**Saturated:** intro-level MCP (no longer its own track in 2026), generic
agent demos ("building agents is trivial now"), hype talks.

**Accepted-talk patterns:** thesis-as-title; numbers in title/abstract;
"you'll leave with" framing near-universal; failure-forward honesty ("two
architectures that failed", "what infosec pushed back on, and where they
were right"); live demos over prerecorded; vendor engineers fine,
pitch framing desk-rejected "with prejudice".

**AIE mechanics:** Sessionize; 4–6 sentence abstracts; 18-min stage talks,
no on-stage Q&A, minimal self-intro; multiple submissions encouraged;
5–15% CFP acceptance; titles/abstracts tweakable with organizers after
acceptance.

Sources: AIEWF 2026 schedule PDF (562 sessions w/ abstracts)
https://www.ai.engineer/worldsfair/schedule.pdf · AIE NYC 2026 CFP
https://sessionize.com/aienyc2026/ · AIE CODE 2026
https://sessionize.com/aiecode26/ · swyx CFP advice
https://www.swyx.io/cfp-advice · swyx AIEWF 2024 retro
https://swyx.io/aiewf-2024 · Latent.Space 2026 CFP post
https://www.latent.space/p/ainews-ai-engineer-worlds-fair-autoresearch ·
Dunphy abstract guide
https://dev.to/benghamine/on-conference-speaking-and-effective-talk-abstracts-2bp6
· QCon AI selection bar https://newyork.qcon.ai/faq/newyork2026 · MLOps
World speakers guide https://mlopsworld.com/speakers-guide/
