# Pluto demo HTTP contract

The server (`server/pluto_demo`) serves the built web app at `/` and this API under `/api`. One process, one vfs kernel, one principal at a time.

## GET /api/state
```json
{
  "principal": "clay",
  "principals": [{"id": "clay", "name": "Clay Gendron", "role": "Founder", "kind": "user"},
                 {"id": "sam", "name": "Sam Reyes", "role": "Engineer, joined last week", "kind": "user"},
                 {"id": "atlas", "name": "Atlas", "role": "Workspace agent", "kind": "service"}],
  "embedder": "model2vec" | "lexical",
  "tree": {"name": "/", "path": "/", "kind": "directory", "children": [ ...nodes... ]}
}
```
A tree node is `{"name","path","kind":"directory"|"file","children"?}`, listed as the current principal sees it. Switching principal changes the tree.

## POST /api/principal  `{"id": "sam"}` → the same body as GET /api/state

## POST /api/shell  `{"command": "grep -i runway /finance"}`
```json
{"command": "...", "principal": "clay", "actor": "clay", "verb": "grep", "ok": true,
 "output": "rendered text", "elapsed_ms": 3.2, "paths": ["/finance/board-update.md"]}
```
`verb` is one of ls, tree, cat, find, grep, glean, graph, write, edit, mkdir, rm, link, grant, revoke, grants, whoami, su, help. `su <id>` switches the principal server-side and the response's `principal` reflects it. Every call is appended to the log.

## GET /api/log → `[{"ts": 1730000000.1, "principal": "clay", "actor": "atlas", "command": "...", "verb": "glean", "ok": true, "elapsed_ms": 4.1}]`
`actor` is `atlas` when the agent ran it on the principal's behalf, else the principal.

## GET /api/file?path=/docs/handbook.md → `{"path", "content", "kind": "file"}`
## PUT /api/file  `{"path": "/docs/new.md", "content": "# ..."}` → `{"ok": true, "output": "write success: 1 file ..."}`

## POST /api/chat  `{"message": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}`
Server-sent events, each `event: <name>` with a JSON `data:` line:
- `text`   `{"delta": "..."}`           assistant prose, streamed
- `tool`   `{"id": "...", "command": "glean 'runway' /finance"}`   the agent is about to run this
- `result` `{"id": "...", "output": "...", "ok": true, "verb": "glean", "elapsed_ms": 4.0}`
- `done`   `{"mode": "live" | "scripted"}`
- `error`  `{"message": "..."}`
The agent runs as actor `atlas` on behalf of the current principal; its commands appear in the log.
