# Pluto Systems demo: the Halyard workspace

Work runs on data. This demo is the whole thesis on one screen: a workspace suite (documents, a file tree, an agent) on one centrally governed data layer built for agentic search, where the agent's entire interface is a bash-like shell.

Everything at Halyard Robotics, the fictional forty-person customer, is a file in one namespace: the handbook, meeting notes, specs, customer notes, finance sheets, and the typed edges between them. The web app, the shell and the agent all go through the same vfs kernel, as the person who is signed in. Nothing is mocked: every command runs on the real engine, every refusal is the kernel's own classified answer.

## Run it

```bash
export ANTHROPIC_API_KEY=...   # optional: without it Atlas replays a scripted transcript against the real kernel
examples/pluto-demo/run.sh
```

Open http://127.0.0.1:8765. The first run builds the web app with Bun and downloads a small local embedding model (model2vec `potion-base-8M`) for semantic search; without network the search index falls back to lexical and the top bar says so.

Requirements: `uv`, `bun`, and the Rust toolchain the vfs wheel is built with (`uv sync` builds it).

## What is on the screen

| Region | What it shows |
| --- | --- |
| File tree | The namespace as the signed-in person sees it. Switch to Sam and the finance folder is simply not there. |
| Document | A WYSIWYG editor. Save writes through vfs, which reindexes the file: it is greppable and gleanable the moment it lands. |
| Shell | Bare unix names over the vfs verbs: `ls`, `tree`, `cat`, `find`, `grep`, plus `glean` (meaning), `graph` (connection) and `grant` (governance). Every call from a person or the agent lands in this one log, tagged by who ran it. |
| Atlas | Claude with exactly one tool, the shell, acting on behalf of the signed-in person. Its commands appear in the shell log as it runs them. |

The shell grammar is in `server/pluto_demo/shell.py`; type `help` in the drawer.

## The five-minute walkthrough

The order below is built for a screen recording: product first, the insight in the first fifteen seconds, the governance gate on camera, no slides.

1. **The namespace.** Signed in as Clay. Type `tree / -L 2` in the shell. "Everything at this company is a file. Docs, meeting notes, customer accounts, finance sheets. One namespace."
2. **The four search verbs.** `grep -i overshoot /meetings`, then `glean 'what did we decide about the gripper firmware'`, then `graph out /meetings/2026-10-14-firmware-review.md`. "Where it sits, what it says, what it means, how it connects. Four verbs, one result type, any scale, on the SQL database you already run."
3. **The agent uses the same shell.** Ask Atlas: *Which customers are affected by the actuator recall?* Watch its `graph` and `grep` calls land in the shell log as it runs them. "The agent gets one tool. It already knows how to use it. No schema per data type, no retrieval pipeline to pick."
4. **The gate.** Switch to Sam in the top bar. The finance folder leaves the tree. Ask Atlas: *How much runway do we have?* It searches, finds nothing it may see, and says so. Switch back to Clay, type `grant /finance sam read`, switch to Sam, ask again. "One kernel enforces every permission for every product and every agent. The agent is judged by the rights of the person it works for."
5. **Work product.** Ask Atlas: *Draft an onboarding note for Sam from the handbook.* It reads, writes `/docs/onboarding-sam.md` and links it. Open the file in the editor, change a line, save. `grep -i priya /docs` finds the edit immediately. "Humans and agents write to the same place through the same gate, and everything is searchable the moment it lands."

Close on the file tree, the shell log and the chat all visible: three faces of one data layer.

## What YC will look for, and where it is

- **The product working, on a real screen.** Everything runs on the real engine; record the browser, not slides.
- **The insight early.** Beat 1 says it in one line: everything is a file, one gate, verbs the agent already knows.
- **One workflow, not a feature tour.** Beats 3 to 5 are one story: an agent helping a new hire, governed.
- **The gate on camera.** Beat 4 is the thing no competitor shows: the same question, two principals, two kernel verdicts, fixed live with one command.

## Layout

```
examples/pluto-demo/
├── API.md                 the HTTP contract the web app and the server share
├── run.sh                 build if needed, then serve
├── server/pluto_demo/
│   ├── seed.py            the Halyard corpus, its edges, the people and the finance grant
│   ├── shell.py           the bare-unix grammar over the vfs verbs
│   ├── kernel.py          one vfs kernel, the signed-in principal, the shared log
│   ├── agent.py           Atlas: Claude with one tool, or the scripted replay
│   └── server.py          FastAPI: the API and the built web app
├── server/tests/          the smoke test: every verb, both principals, the gate, the agent
└── web/                   the SvelteKit app on the Pluto design tokens
```

Test the server with:

```bash
PYTHONPATH=examples/pluto-demo/server uv run pytest examples/pluto-demo/server/tests
```
