"""Spike: what a host must supply to call an unmodified LangChain tool outside an agent.

Run from this directory:
    uv run --no-project --with langgraph --with langchain-core python -I langchain_injection.py

Checks, with no model and no network beyond the install: which injected
arguments are hidden from the schema, how each is supplied on a direct
``invoke``, what ``invoke`` returns for a plain input and for a ToolCall,
how ``ToolException`` and a plain exception come back, and whether a
paused Python body can be saved for another process.
"""

from __future__ import annotations

import pickle
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, ToolException, tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command


class Handle:
    """Stands in for the caller-scoped vfs handle a host would inject."""

    def __repr__(self) -> str:
        return "Handle()"


@tool
def with_handle(path: str, fs: Annotated[Handle, InjectedToolArg]) -> str:
    """Read through an injected handle."""
    return f"{path} via {fs!r}"


@tool
def with_call_id(path: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> str:
    """Needs the call id."""
    return f"{path} call={tool_call_id}"


@tool
def with_runtime(path: str, runtime: ToolRuntime) -> str:
    """Reads its context from the runtime."""
    return f"{path} ctx={runtime.context!r}"


@tool(response_format="content_and_artifact")
def with_artifact(path: str) -> tuple[str, dict[str, Any]]:
    """Returns content and an artifact."""
    return f"converted {path}", {"bytes": 3}


@tool
def returns_command(path: str) -> Command:
    """Returns a graph Command."""
    return Command(update={"x": path})


@tool
def raises_tool_exception(path: str) -> str:
    """Raises a ToolException, handled."""
    raise ToolException(f"cannot convert {path}")


raises_tool_exception.handle_tool_error = True


@tool
def raises_plain(path: str) -> str:
    """Raises a plain error."""
    raise ValueError("boom")


def schema_props(t: Any) -> list[str]:
    return sorted(t.tool_call_schema.model_json_schema().get("properties", {}))


def main() -> None:
    print("A schema seen by a model, with_handle:", schema_props(with_handle))
    print("A schema seen by a model, with_call_id:", schema_props(with_call_id))
    print("A schema seen by a model, with_runtime:", schema_props(with_runtime))
    print("A full input model fields, with_handle:", sorted(with_handle.get_input_schema().model_fields))
    try:
        with_handle.get_input_schema().model_json_schema()
    except Exception as error:  # noqa: BLE001
        print("A full input model as JSON schema, with_handle:", type(error).__name__)
    print("B injected handle in the args dict:", with_handle.invoke({"path": "/a", "fs": Handle()}))
    try:
        with_handle.invoke({"path": "/a"})
    except Exception as error:  # noqa: BLE001
        print("B injected handle missing:", type(error).__name__, str(error).splitlines()[0])
    try:
        with_call_id.invoke({"path": "/a"})
    except Exception as error:  # noqa: BLE001
        print("C call id with plain args:", type(error).__name__, str(error).splitlines()[0][:100])
    msg = with_call_id.invoke({"name": "with_call_id", "args": {"path": "/a"}, "id": "0.1#3", "type": "tool_call"})
    print("C call id with a ToolCall: returns", type(msg).__name__, repr(msg.content))
    runtime = ToolRuntime(state={}, context={"fs": "Handle()"}, config={}, stream_writer=lambda _: None, tool_call_id="0.1#3", store=None)
    print("D runtime in the args dict:", with_runtime.invoke({"path": "/a", "runtime": runtime}))
    out = with_artifact.invoke({"path": "/a"})
    print("E content_and_artifact, plain args: returns", type(out).__name__, repr(out))
    msg = with_artifact.invoke({"name": "with_artifact", "args": {"path": "/a"}, "id": "k", "type": "tool_call"})
    print("E content_and_artifact, ToolCall: content", repr(msg.content), "artifact", msg.artifact, isinstance(msg, ToolMessage))
    print("F returns Command: type", type(returns_command.invoke({"path": "/a"})).__name__)
    print("G handled ToolException, plain args: returns", repr(raises_tool_exception.invoke({"path": "/a"})))
    msg = raises_tool_exception.invoke({"name": "raises_tool_exception", "args": {"path": "/a"}, "id": "k", "type": "tool_call"})
    print("G handled ToolException, ToolCall: status", msg.status)
    try:
        raises_plain.invoke({"path": "/a"})
    except Exception as error:  # noqa: BLE001
        print("H plain exception propagates:", type(error).__name__, error)
    try:
        with_handle.invoke({"path": 3, "fs": Handle()})
    except Exception as error:  # noqa: BLE001
        print("I bad argument type:", type(error).__name__)

    def body():
        yield "asked"
        yield "done"

    paused = body()
    next(paused)
    try:
        pickle.dumps(paused)
    except TypeError as error:
        print("J a paused generator cannot be saved:", error)


if __name__ == "__main__":
    main()
