"""Atlas, the workspace agent: Claude with exactly one tool, the shell.

The agent gets no schema per data type and no retrieval pipeline to pick.
It gets a shell whose verbs it already knows, run on behalf of the person
it is helping, so the kernel judges every call by that person's rights.
Without an API key the same loop replays a scripted transcript, executing
the commands for real so the terminal, the log and the refusals are
genuine.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic

from pluto_demo.shell import HELP

if TYPE_CHECKING:
    from pluto_demo.kernel import Workspace

MODEL = os.environ.get("PLUTO_MODEL", "claude-sonnet-5-5")
MAX_TURNS = 12

SYSTEM_PROMPT = (
    """You are Atlas, the workspace agent at Halyard Robotics. You help the signed-in person with their work.

You have one tool: `shell`, a bash-like shell over the company workspace. Everything at Halyard is a file in one namespace: documents, meeting notes, specs, customer notes, sheets, policies. The shell's verbs are the search primitives you already know, plus three a file system never had:

- drill: ls, tree
- filter: find
- match: grep (ripgrep flags), glean (ranked search by meaning)
- connect: graph in|out|around <path> (typed edges between files)
- seek: cat
- act: write, edit, mkdir, link
- govern: grants, grant, revoke

The folders: /docs (handbook, policies, engineering notes), /meetings (dated notes with the decisions), /product (specs, the recall notice, the roadmap), /customers (one file per account), /people (onboarding, headcount), /slides (decks, slides separated by ---), /code (the firmware limits and estimator), /finance (leadership only).

Work the way a careful colleague would: glean or grep to find candidates, graph to see what a decision touched, cat to read before you answer, and cite the paths you relied on. If a path you expect is missing or a call is refused, say so plainly: you only see what the signed-in person may see, and the kernel decides, not you. Never claim to have read something you did not cat. Keep answers short and concrete; use markdown lightly.

Shell reference:
"""
    + HELP
)

TOOL: dict[str, Any] = {
    "name": "shell",
    "description": "Run one line in the Halyard workspace shell and get its output.",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "One shell line, e.g. grep -i runway /finance"}},
        "required": ["command"],
    },
}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def event(name: str, **data: Any) -> str:
    """One server-sent event, framed."""
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def respond(workspace: Workspace, message: str, history: list[dict[str, str]]) -> AsyncIterator[str]:
    """Stream the agent's answer to *message* as server-sent events."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            async for chunk in _live(workspace, message, history):
                yield chunk
        except Exception as exc:
            yield event("error", message=f"The live agent failed: {exc}")
            yield event("done", mode="live")
        return
    async for chunk in _scripted(workspace, message):
        yield chunk


# ---------------------------------------------------------------------------
# Live: Claude with one tool
# ---------------------------------------------------------------------------


async def _live(workspace: Workspace, message: str, history: list[dict[str, str]]) -> AsyncIterator[str]:
    client = AsyncAnthropic()
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": message}]
    for _ in range(MAX_TURNS):
        async with client.messages.stream(
            model=MODEL, max_tokens=2048, system=SYSTEM_PROMPT, tools=[TOOL], messages=messages
        ) as stream:
            async for item in stream.text_stream:
                yield event("text", delta=item)
            final = await stream.get_final_message()
        messages.append({"role": "assistant", "content": [block.model_dump() for block in final.content]})
        tool_uses = [block for block in final.content if block.type == "tool_use"]
        if not tool_uses:
            break
        results: list[dict[str, Any]] = []
        for use in tool_uses:
            command = str(dict(use.input).get("command", ""))
            call_id = uuid.uuid4().hex[:8]
            yield event("tool", id=call_id, command=command)
            out = await workspace.run(command, as_agent=True)
            elapsed = workspace.log[-1].elapsed_ms if workspace.log else 0.0
            yield event("result", id=call_id, output=out.output, ok=out.ok, verb=out.verb, elapsed_ms=elapsed)
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": out.output or "(no output)"})
        messages.append({"role": "user", "content": results})
    yield event("done", mode="live")


# ---------------------------------------------------------------------------
# Scripted: the same loop without a model
# ---------------------------------------------------------------------------

Step = tuple[str | None, str | None]
"""(narration to stream, command to run); either may be absent."""

SCRIPTS: dict[str, list[Step]] = {
    "gripper": [
        (
            "Let me find what the team decided about the gripper firmware.",
            "glean 'gripper firmware decision' /meetings",
        ),
        (
            "The firmware review on 14 October is the one. I'll check what that meeting touched.",
            "graph out /meetings/2026-10-14-firmware-review.md",
        ),
        (None, "cat /meetings/2026-10-14-firmware-review.md"),
        (
            "**Decision, 14 October:** roll the GX-2 fleet back to firmware 2026.8.3 immediately and ship the fixed force estimator as 2026.10.2 after a week on the hardware-in-the-loop rig. Marco owns the rollback, Priya owns 2026.10.2.\n\nThe product sync on 28 October then agreed to cut 2026.10.2 on 30 October, Tandem Logistics first.\n\nSources: `/meetings/2026-10-14-firmware-review.md`, `/product/gripper-firmware-spec.md`.",
            None,
        ),
    ],
    "runway": [
        ("I'll look for the runway figures.", "glean 'runway cash burn' /finance"),
        (None, "grep -i runway /"),
        (None, "cat /finance/board-update-2026-10.md"),
        (
            "From the October board update: cash at end of October is **4.1M**, net burn is heading to **310k a month**, so runway is **about thirteen months**, to the end of November 2027. The AX-40 recall is being funded from the operating budget, and the bridge is revisited at the December board meeting.\n\nSource: `/finance/board-update-2026-10.md`.",
            None,
        ),
    ],
    "runway-refused": [
        ("I'll look for the runway figures.", "glean 'runway cash burn' /finance"),
        (None, "grep -i runway /"),
        (None, "ls /"),
        (
            "I can't answer that. There is no `/finance` folder in the workspace as you see it, and nothing you can read mentions runway. The kernel judges my calls by your rights, so if finance is restricted to the leadership group, someone with access would need to grant it (`grant /finance sam read`).",
            None,
        ),
    ],
    "onboarding": [
        ("I'll read the handbook and the onboarding sheet first.", "cat /docs/handbook.md"),
        (None, "grep -i sam /people /meetings"),
        (
            "Drafting the note now and saving it where Sam will find it.",
            "write /docs/onboarding-sam.md '# Welcome, Sam\n\nYour buddy is Priya. This week: read the gripper firmware spec and the two meeting notes that produced it (14 and 28 October), pair with Priya on one field ticket, and ship something small to staging by Friday using /docs/release-checklist.md. Your first-week ticket is the 2026.10.2 release checklist.\n\nTime off: tell your lead, mark the calendar. Details in /docs/time-off-policy.md.'",
        ),
        (None, "link /docs/onboarding-sam.md /docs/handbook.md references"),
        (
            "Done. I wrote `/docs/onboarding-sam.md` from the handbook, the buddy sheet and the leadership note that assigned Priya, and linked it back to the handbook so it shows up in the graph. It is already searchable.",
            None,
        ),
    ],
    "recall": [
        ("I'll start from the recall notice and follow its edges.", "graph out /product/ax40-recall-notice.md"),
        (None, "grep -i -C 1 'not affected\\|affected' /customers"),
        (
            "Three customers are affected by the AX-40 recall:\n\n- **Tandem Logistics**: 1,100 units across two sites, seal swaps under way since 23 October.\n- **Bellweather Fulfilment**: 620 units, swaps in the first two weeks of November.\n- **Orinoco Parcel**: 180 units, swaps on 12 November.\n\nNorthgate Grocery is not affected; their units were built in September.\n\nSources: `/product/ax40-recall-notice.md` and the four files under `/customers`.",
            None,
        ),
    ],
}

DEFAULT_SCRIPT: list[Step] = [
    ("Let me search the workspace for that.", "glean '{query}'"),
    (None, "grep -i -m 3 '{query}' /"),
    (
        "Those are the files that match. Open any of them in the editor, or ask me to summarise one, and I'll `cat` it first.",
        None,
    ),
]


async def _pick_script(workspace: Workspace, message: str) -> list[Step]:
    lower = message.lower()
    if "gripper" in lower or "firmware" in lower:
        return SCRIPTS["gripper"]
    if "runway" in lower or "burn" in lower or "cash" in lower:
        sees_finance = (await workspace.fs.session(workspace.authority()).stat("/finance")).success
        return SCRIPTS["runway"] if sees_finance else SCRIPTS["runway-refused"]
    if "onboard" in lower or "welcome" in lower:
        return SCRIPTS["onboarding"]
    if "recall" in lower or "actuator" in lower or "affected" in lower:
        return SCRIPTS["recall"]
    query = " ".join(w for w in message.replace("?", "").split() if len(w) > 3)[:60] or message[:60]
    return [(text, cmd.format(query=query.replace("'", "")) if cmd else None) for text, cmd in DEFAULT_SCRIPT]


async def _scripted(workspace: Workspace, message: str) -> AsyncIterator[str]:
    for narration, command in await _pick_script(workspace, message):
        if narration:
            for piece in narration.split(" "):
                yield event("text", delta=piece + " ")
                await asyncio.sleep(0.02)
            yield event("text", delta="\n\n")
        if command:
            call_id = uuid.uuid4().hex[:8]
            yield event("tool", id=call_id, command=command)
            await asyncio.sleep(0.35)
            out = await workspace.run(command, as_agent=True)
            elapsed = workspace.log[-1].elapsed_ms if workspace.log else 0.0
            yield event("result", id=call_id, output=out.output, ok=out.ok, verb=out.verb, elapsed_ms=elapsed)
            await asyncio.sleep(0.25)
    yield event("done", mode="scripted")
