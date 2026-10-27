"""Probe: what a long-lived McpView must do with the SDK client's lifecycle.

(1) twenty concurrent tools/call on one stdio Client from different tasks;
(2) open the Client in one task and close it from another (the naive
    add_mcp()/close() shape);
(3) the stdio server process dies: what a later call raises;
(4) the default client meets an elicitation (input_required) request;
(5) what a tools/list ttlMs of 0 means for the SDK's cache: calls counted.

Run from the vfs repo root:

    uv run --with mcp python -I \
        context/research/studies/2026-10-15-agent-shell/experiments/r170/lifecycle_probe.py
"""

from __future__ import annotations

import importlib.metadata
import os
import sys
import traceback

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from pydantic import BaseModel

HERE = os.path.abspath(__file__)


class Confirm(BaseModel):
    ok: bool


def serve() -> None:
    server = MCPServer("lifecycle")

    @server.tool()
    async def slow_echo(text: str, delay: float = 0.05) -> str:
        await anyio.sleep(delay)
        return text

    @server.tool()
    def die() -> str:
        os._exit(3)

    @server.tool()
    async def ask(ctx: Context) -> str:
        answer = await ctx.elicit("Proceed?", Confirm)
        return str(answer)

    server.run("stdio")


def params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-I", HERE, "--serve"])


async def part1() -> None:
    async with Client(params()) as client:
        print("(1) protocol:", client.protocol_version)
        results: list[str] = []

        async def one(i: int) -> None:
            r = await client.call_tool("slow_echo", {"text": f"t{i}"})
            results.append(r.content[0].text)

        async with anyio.create_task_group() as tg:
            for i in range(20):
                tg.start_soon(one, i)
        print("(1) concurrent calls ok:", len(results), "distinct:", len(set(results)))


async def part2() -> None:
    holder: dict[str, Client] = {}

    async def opener() -> None:
        c = Client(params())
        await c.__aenter__()
        holder["c"] = c

    async with anyio.create_task_group() as tg:
        tg.start_soon(opener)
    c = holder["c"]
    try:
        r = await c.call_tool("slow_echo", {"text": "after-open-in-other-task"})
        print("(2) call from a different task than the opener:", r.content[0].text)
    except BaseException as exc:  # noqa: BLE001
        print("(2) call from a different task RAISED:", type(exc).__name__, exc)
    try:
        await c.__aexit__(None, None, None)
        print("(2) close from a different task: ok")
    except BaseException as exc:  # noqa: BLE001
        print("(2) close from a different task RAISED:", type(exc).__name__, str(exc)[:200])


async def part3() -> None:
    try:
        async with Client(params(), read_timeout_seconds=5) as client:
            try:
                await client.call_tool("die", {})
            except BaseException as exc:  # noqa: BLE001
                print("(3) call that kills the server RAISED:", type(exc).__module__, type(exc).__name__, str(exc)[:160])
            try:
                await client.call_tool("slow_echo", {"text": "x"})
            except BaseException as exc:  # noqa: BLE001
                print("(3) next call after death RAISED:", type(exc).__module__, type(exc).__name__, str(exc)[:160])
    except BaseException as exc:  # noqa: BLE001
        print("(3) context exit RAISED:", type(exc).__name__, str(exc)[:160])


async def part4() -> None:
    async with Client(params()) as client:
        try:
            r = await client.call_tool("ask", {})
            print("(4) elicitation with no callback ->", r.model_dump(by_alias=True, exclude_none=True))
        except BaseException as exc:  # noqa: BLE001
            print("(4) elicitation with no callback RAISED:", type(exc).__module__, type(exc).__name__, str(exc)[:200])


async def part5() -> None:
    async with Client(params()) as client:
        a = await client.list_tools()
        b = await client.list_tools()
        print("(5) tools/list ttlMs:", a.ttl_ms, "cacheScope:", a.cache_scope, "| same object served twice:", a is b)


async def main() -> None:
    print("mcp", importlib.metadata.version("mcp"))
    for part in (part1, part2, part3, part4, part5):
        try:
            await part()
        except BaseException:  # noqa: BLE001
            print(f"{part.__name__} crashed:")
            traceback.print_exc(limit=3, file=sys.stdout)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        anyio.run(main)
