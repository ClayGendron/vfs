"""Spike: what LangGraph re-runs when a tool that interrupts is resumed.

Run from this directory:
    uv run --with langgraph --with langchain-core python langgraph_resume.py

No model calls, no network beyond the package install. Prints one line per
finding, prefixed by the scenario it belongs to.
"""

from __future__ import annotations

import asyncio
import importlib.metadata as md
import operator
from typing import Annotated, Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphBubbleUp, GraphInterrupt
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, Send, interrupt
from typing_extensions import TypedDict

COUNTS: dict[str, int] = {}


def bump(name: str) -> None:
    COUNTS[name] = COUNTS.get(name, 0) + 1


@tool
def convert(path: str, to: str = "pdf") -> str:
    """Convert a document, asking twice."""
    bump("convert.entered")
    bump("convert.effect_before_first")
    first = interrupt({"question": f"Convert {path} to {to}?"})
    bump("convert.effect_between")
    second = interrupt({"question": f"Overwrite {path}.{to}?"})
    bump("convert.effect_after_second")
    return f"{path}->{to} first={first} second={second}"


class State(TypedDict):
    path: str
    out: str


def node(state: State) -> dict[str, Any]:
    return {"out": convert.invoke({"path": state["path"], "to": "pdf"})}


def s1_two_interrupts_one_tool() -> None:
    COUNTS.clear()
    graph = StateGraph(State)
    graph.add_node("n", node)
    graph.add_edge(START, "n")
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    r1 = app.invoke({"path": "/r/a.md", "out": ""}, config, version="v2")
    ids = [i.id for i in r1.interrupts]
    print("S1 first stop: interrupts", len(r1.interrupts), "value", r1.interrupts[0].value, "counts", dict(COUNTS))
    r2 = app.invoke(Command(resume="yes"), config, version="v2")
    ids2 = [i.id for i in r2.interrupts]
    print("S1 second stop: interrupts", len(r2.interrupts), "value", r2.interrupts[0].value, "counts", dict(COUNTS))
    print("S1 interrupt ids differ between the two asks:", ids != ids2, ids[0][:8], ids2[0][:8])
    r3 = app.invoke(Command(resume={ids2[0]: "overwrite"}), config, version="v2")
    print("S1 done: value", r3.value["out"], "interrupts", len(r3.interrupts), "counts", dict(COUNTS))
    snap = app.get_state(config)
    print("S1 checkpoint after done: next", snap.next, "pending interrupts", len(snap.interrupts))


def s2_outside_a_graph() -> None:
    COUNTS.clear()
    try:
        convert.invoke({"path": "/r/a.md"})
    except BaseException as error:  # noqa: BLE001
        print("S2 unmodified tool called outside a graph raises", type(error).__name__, "-", error, "counts", dict(COUNTS))


class AgentState(MessagesState):
    pass


@tool
def tally(path: str) -> str:
    """A tool with an effect and no interrupt."""
    bump("tally.entered")
    return f"tallied {path}"


def _ai_with_two_calls() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "tally", "args": {"path": "/r/a.md"}, "id": "c1", "type": "tool_call"},
            {"name": "convert", "args": {"path": "/r/b.md"}, "id": "c2", "type": "tool_call"},
        ],
    )


def s3_toolnode_one_task() -> None:
    COUNTS.clear()
    graph = StateGraph(AgentState)
    graph.add_node("tools", ToolNode([tally, convert]))
    graph.add_edge(START, "tools")
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "s3"}}
    app.invoke({"messages": [_ai_with_two_calls()]}, config, version="v2")
    app.invoke(Command(resume="yes"), config, version="v2")
    app.invoke(Command(resume="yes"), config, version="v2")
    print("S3 ToolNode, both calls in one task: counts", dict(COUNTS))


def s4_send_per_call() -> None:
    COUNTS.clear()
    graph = StateGraph(AgentState)

    def fan(state: AgentState) -> list[Send]:
        last = state["messages"][-1]
        return [Send("tools", {"messages": [AIMessage(content="", tool_calls=[c])]}) for c in last.tool_calls]

    graph.add_node("tools", ToolNode([tally, convert]))
    graph.add_conditional_edges(START, fan, ["tools"])
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "s4"}}
    app.invoke({"messages": [_ai_with_two_calls()]}, config, version="v2")
    app.invoke(Command(resume="yes"), config, version="v2")
    app.invoke(Command(resume="yes"), config, version="v2")
    print("S4 one Send per tool call (create_agent's shape): counts", dict(COUNTS))


def s5_scratchpad_shim() -> None:
    """Drive an unmodified tool's interrupt() with no graph, through LangGraph's private config keys."""
    from langgraph._internal._constants import CONFIG_KEY_CHECKPOINT_NS, CONFIG_KEY_SCRATCHPAD, CONFIG_KEY_SEND
    from langgraph._internal._scratchpad import PregelScratchpad

    def run(answers: list[Any]) -> Any:
        counter = iter(range(1_000_000))
        pad = PregelScratchpad(
            step=0,
            stop=1,
            call_counter=lambda: 0,
            interrupt_counter=lambda: next(counter),
            get_null_resume=lambda consume=False: None,
            resume=list(answers),
            subgraph_counter=lambda: 0,
        )
        conf = {CONFIG_KEY_SCRATCHPAD: pad, CONFIG_KEY_SEND: lambda writes: None, CONFIG_KEY_CHECKPOINT_NS: "vfs:run1:0.1#3"}
        return convert.invoke({"path": "/r/a.md"}, config={"configurable": conf})

    COUNTS.clear()
    for answers in ([], ["yes"], ["yes", "overwrite"]):
        try:
            out = run(answers)
            print("S5 shim with", len(answers), "answers: returned", out, "counts", dict(COUNTS))
        except GraphInterrupt as stop:
            print("S5 shim with", len(answers), "answers: GraphInterrupt", stop.args[0][0].value, "counts", dict(COUNTS))


async def s6_shim_async_and_thread() -> None:
    """The same shim through ainvoke of a sync-only tool, which LangChain runs in an executor."""
    from langgraph._internal._constants import CONFIG_KEY_CHECKPOINT_NS, CONFIG_KEY_SCRATCHPAD, CONFIG_KEY_SEND
    from langgraph._internal._scratchpad import PregelScratchpad

    counter = iter(range(1_000_000))
    pad = PregelScratchpad(
        step=0,
        stop=1,
        call_counter=lambda: 0,
        interrupt_counter=lambda: next(counter),
        get_null_resume=lambda consume=False: None,
        resume=["yes"],
        subgraph_counter=lambda: 0,
    )
    conf = {CONFIG_KEY_SCRATCHPAD: pad, CONFIG_KEY_SEND: lambda writes: None, CONFIG_KEY_CHECKPOINT_NS: "vfs"}
    try:
        await convert.ainvoke({"path": "/r/a.md"}, config={"configurable": conf})
    except GraphInterrupt as stop:
        print("S6 ainvoke of a sync tool (executor thread) still sees the config: second ask", stop.args[0][0].value)


def s7_exception_hierarchy() -> None:
    print(
        "S7 GraphInterrupt is an Exception subclass:",
        issubclass(GraphInterrupt, Exception),
        "| GraphBubbleUp base:",
        GraphBubbleUp.__mro__[1].__name__,
    )


def main() -> None:
    for name in ("langgraph", "langchain-core", "langgraph-prebuilt", "langgraph-checkpoint"):
        print("version", name, md.version(name))
    s1_two_interrupts_one_tool()
    s2_outside_a_graph()
    s3_toolnode_one_task()
    s4_send_per_call()
    s5_scratchpad_shim()
    asyncio.run(s6_shim_async_and_thread())
    s7_exception_hierarchy()


_ = (Annotated, operator)

if __name__ == "__main__":
    main()
