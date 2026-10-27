"""Probe: which inputSchema shapes a real Python MCP server emits from type hints,
and what tools/call returns for the failure and block cases spec 170's adapter must map.

Run from the vfs repo root:

    uv run --with mcp python -I \
        context/research/studies/2026-10-15-agent-shell/experiments/r170/schema_shapes_probe.py
"""

from __future__ import annotations

import base64
import importlib.metadata
import json
from enum import Enum
from typing import Annotated, Literal

import anyio
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.types import Image
from mcp_types import (
    CallToolResult,
    EmbeddedResource,
    ResourceLink,
    TextContent,
    TextResourceContents,
    ToolAnnotations,
)
from pydantic import BaseModel, Field

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)

server = MCPServer("r170")


class Color(str, Enum):
    red = "red"
    blue = "blue"


class Filter(BaseModel):
    field: str
    op: Literal["eq", "ne"] = "eq"
    value: str | int


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def list_widgets() -> str:
    """No parameters at all."""
    return "w1\nw2"


@server.tool()
def search(
    query: str,
    limit: int = 10,
    threshold: float | None = None,
    exact: bool = False,
    mode: Literal["fast", "deep"] = "fast",
    color: Color = Color.red,
    tags: list[str] | None = None,
    ids: list[int] = [],  # noqa: B006
    where: Filter | None = None,
    extra: dict[str, str] | None = None,
    since: Annotated[str, Field(description="ISO date", pattern=r"^\d{4}-\d{2}-\d{2}$")] = "2026-01-01",
) -> dict:
    """Every shape a host function plausibly takes."""
    return {"query": query, "limit": limit, "tags": tags, "where": where.model_dump() if where else None}


@server.tool()
def upload(body: str) -> str:
    """One required text parameter: the stdin-as-body case."""
    return f"{len(body)} chars"


@server.tool()
def ingest(doc: Filter) -> str:
    """One required object parameter."""
    return doc.field


@server.tool()
def boom() -> str:
    """Raises."""
    raise RuntimeError("upstream exploded")


@server.tool()
def picture() -> Image:
    return Image(data=PNG, format="png")


@server.tool()
def blocks() -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text="three blocks"),
            ResourceLink(type="resource_link", uri="https://example.com/a.pdf", name="a.pdf", mime_type="application/pdf", size=1234),
            EmbeddedResource(type="resource", resource=TextResourceContents(uri="mem://notes/1", text="embedded text", mime_type="text/plain")),
        ],
        structured_content={"n": 3},
    )


@server.tool()
def soft_fail() -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text="quota exceeded for org acme")], is_error=True, structured_content={"code": "quota"})


def dump(label: str, obj: object) -> None:
    print(f"--- {label}")
    print(json.dumps(obj, indent=1, sort_keys=True, default=str))


async def main() -> None:
    print("mcp", importlib.metadata.version("mcp"), "| mcp-types", importlib.metadata.version("mcp-types"))
    async with Client(server) as client:
        print("protocol_version:", client.protocol_version)
        listing = await client.list_tools()
        dump("listing meta (ttl/cacheScope)", {k: v for k, v in listing.model_dump(by_alias=True, exclude_none=True).items() if k != "tools"})
        for tool in listing.tools:
            dump(f"tool {tool.name}", tool.model_dump(by_alias=True, exclude_none=True))

        async def call(label: str, name: str, args: dict | None) -> None:
            try:
                r = await client.call_tool(name, args)
                dump(f"call {label}", r.model_dump(by_alias=True, exclude_none=True))
            except Exception as exc:  # the probe records every raise shape
                print(f"--- call {label}: RAISED {type(exc).__module__}.{type(exc).__name__}: {exc}")
                code = getattr(getattr(exc, "error", None), "code", None)
                if code is not None:
                    print("    jsonrpc code:", code)

        await call("no-arg str with outputSchema", "list_widgets", {})
        await call("search ok", "search", {"query": "x", "where": {"field": "a", "value": 3}})
        await call("search missing required", "search", {"limit": 5})
        await call("search wrong type", "search", {"query": "x", "limit": "five"})
        await call("search string-for-int coerced?", "search", {"query": "x", "limit": "5"})
        await call("search unknown property", "search", {"query": "x", "bogus": 1})
        await call("unknown tool", "nope", {})
        await call("raises", "boom", {})
        await call("image", "picture", {})
        await call("three blocks", "blocks", {})
        await call("isError with structured", "soft_fail", {})


anyio.run(main)
