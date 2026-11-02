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

A workspace suite, not an IDE. The ribbon on the left holds the apps; each one is a different face of the same files.

| App | What it shows |
| --- | --- |
| Docs | Every document, grouped by folder, in a WYSIWYG editor. Save writes through vfs, which reindexes the file: it is greppable and gleanable the moment it lands. |
| Sheets | The CSV files as editable grids: the runway model, vendor payments, headcount. |
| Slides | Markdown decks as 16:9 slides: the November all hands, the Tandem quarterly review. |
| Code | The firmware limits and estimator, in a plain code editor. |
| Terminal | Bare unix names over the vfs verbs: `ls`, `tree`, `cat`, `find`, `grep`, plus `glean` (meaning), `graph` (connection) and `grant` (governance). Every call from a person or the agent lands in this one log, tagged by who ran it. |
| Atlas | Claude with exactly one tool, the shell, acting on behalf of the signed-in person. A side panel open over any app; its commands appear in the Terminal as it runs them. |

The principal switcher in the top bar is the governance moment: switch to Sam and the finance sheet, the board update and the whole finance folder leave every app at once.

The shell grammar is in `server/pluto_demo/shell.py`; type `help` in the Terminal.

## The five-minute walkthrough

The order below is built for a screen recording: product first, the insight in the first fifteen seconds, the governance gate on camera, no slides about slides.

1. **One workspace, many apps.** Signed in as Clay. Click through Docs, Sheets, Slides and Code. "Documents, sheets, decks, code. At Halyard every one of them is a file in one namespace, on one governed data layer."
2. **The agent uses a shell.** Open Atlas and ask: *Which customers are affected by the actuator recall?* Switch to Terminal and watch its `graph` and `grep` calls land in the same log you type into. "The agent gets one tool. It already knows how to use it. No schema per data type, no retrieval pipeline to pick."
3. **Four search verbs.** In Terminal: `grep -i overshoot /meetings`, then `glean 'what did we decide about the gripper firmware'`, then `graph out /meetings/2026-10-14-firmware-review.md`. "Where it sits, what it says, what it means, how it connects. Four verbs, one result type, any scale, on the SQL database you already run."
4. **The gate.** Switch to Sam in the top bar. Finance leaves Docs and Sheets. Ask Atlas: *How much runway do we have?* It searches, finds nothing it may see, and says so. Switch back to Clay, type `grant /finance sam read` in Terminal, switch to Sam, ask again. "One kernel enforces every permission for every app and every agent. The agent is judged by the rights of the person it works for."
5. **Work product.** Ask Atlas: *Draft an onboarding note for Sam from the handbook.* It reads, writes `/docs/onboarding-sam.md` and links it. Open the note in Docs, change a line, save. In Terminal, `grep -i priya /docs` finds the edit immediately. "People and agents write to the same place through the same gate, and everything is searchable the moment it lands."

Close on Slides with Atlas open beside it: the deck, the agent, the same files.

## What YC will look for, and where it is

- **The product working, on a real screen.** Everything runs on the real engine; record the browser, not slides.
- **The insight early.** Beat 1 says it in one line: everything is a file, one gate, verbs the agent already knows.
- **One workflow, not a feature tour.** Beats 2 to 5 are one story: an agent helping a new hire, governed.
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
└── web/                   the SvelteKit app on the Pluto design tokens: the ribbon, five apps, Atlas
```

Test the server with:

```bash
PYTHONPATH=examples/pluto-demo/server uv run pytest examples/pluto-demo/server/tests
```
