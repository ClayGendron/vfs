"""The HTTP face of the workspace: the API under ``/api`` and the built web app at ``/``."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from pluto_demo import agent
from pluto_demo.kernel import Workspace

WEB_BUILD = Path(__file__).resolve().parents[2] / "web" / "build"


class PrincipalBody(BaseModel):
    id: str


class ShellBody(BaseModel):
    command: str


class FileBody(BaseModel):
    path: str
    content: str


class ChatBody(BaseModel):
    message: str
    history: list[dict[str, str]] = []


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    workspace = Workspace()
    await workspace.seed()
    app.state.workspace = workspace
    logging.getLogger("pluto").info(
        "Halyard workspace ready: %d files, search index %s", len(_seed_count()), workspace.embedder_name
    )
    yield
    await workspace.close()


def _seed_count() -> dict[str, str]:
    from pluto_demo import seed  # noqa: PLC0415

    return seed.FILES


app = FastAPI(title="Pluto Systems demo", lifespan=lifespan)


def _ws(request: Request) -> Workspace:
    return request.app.state.workspace


async def _state(ws: Workspace) -> dict:
    return {
        "principal": ws.principal,
        "principals": ws.principals(),
        "embedder": ws.embedder_name,
        "tree": await ws.tree(),
    }


@app.get("/api/state")
async def get_state(request: Request) -> dict:
    return await _state(_ws(request))


@app.post("/api/principal")
async def post_principal(body: PrincipalBody, request: Request) -> dict:
    ws = _ws(request)
    if not ws.switch(body.id):
        raise HTTPException(404, f"no principal named {body.id!r}")
    await ws.run(f"su {body.id}")
    return await _state(ws)


@app.post("/api/shell")
async def post_shell(body: ShellBody, request: Request) -> dict:
    ws = _ws(request)
    out = await ws.run(body.command)
    entry = ws.log[-1]
    return {
        "ts": entry.ts,
        "command": body.command,
        "principal": ws.principal,
        "actor": entry.actor,
        "verb": out.verb,
        "ok": out.ok,
        "output": out.output,
        "elapsed_ms": entry.elapsed_ms,
        "paths": out.paths,
    }


@app.get("/api/log")
async def get_log(request: Request) -> list[dict]:
    return _ws(request).log_payload()


@app.get("/api/file")
async def get_file(path: str, request: Request) -> dict:
    ws = _ws(request)
    result = await ws.fs.session(ws.authority()).read(path)
    if not result.success:
        raise HTTPException(404, result.error_message)
    entry = result.one()
    return {"path": path, "content": entry.content or "", "kind": "file"}


@app.put("/api/file")
async def put_file(body: FileBody, request: Request) -> dict:
    ws = _ws(request)
    result = await ws.fs.session(ws.authority()).write(path=body.path, content=body.content, parents=True)
    if not result.success:
        raise HTTPException(403 if "permission" in result.error_message.lower() else 400, result.error_message)
    from vfs.results.render import render_result  # noqa: PLC0415

    return {"ok": True, "output": render_result(result).rstrip()}


@app.post("/api/chat")
async def post_chat(body: ChatBody, request: Request) -> StreamingResponse:
    ws = _ws(request)
    return StreamingResponse(
        agent.respond(ws, body.message, body.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/{full_path:path}")
async def web(full_path: str) -> FileResponse:
    """The built single-page app, with its index as the fallback for every route."""
    if not WEB_BUILD.exists():
        raise HTTPException(503, "The web app is not built yet: run `bun run build` in examples/pluto-demo/web")
    candidate = (WEB_BUILD / full_path).resolve()
    if full_path and candidate.is_file() and WEB_BUILD in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(WEB_BUILD / "index.html")
