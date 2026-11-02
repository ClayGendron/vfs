"""Every shell verb, both principals, the governance moment and the scripted agent, on the real kernel."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from pluto_demo import agent
from pluto_demo.kernel import Workspace


@pytest.fixture
async def workspace() -> AsyncIterator[Workspace]:
    ws = Workspace()
    await ws.seed()
    yield ws
    await ws.close()


@pytest.mark.parametrize(
    "command",
    [
        "help",
        "whoami",
        "ls /",
        "tree /meetings -L 2",
        "cat /docs/handbook.md",
        "find '**/*.csv'",
        "grep -i -C 1 runway /",
        "grep -c gripper /meetings",
        "glean 'gripper firmware decision' -n 3",
        "graph out /meetings/2026-10-21-leadership.md",
        "graph in /product/gripper-firmware-spec.md -d 1",
        "grants /finance",
        "mkdir -p /scratch/x",
    ],
)
async def test_every_verb_succeeds_for_clay(workspace: Workspace, command: str) -> None:
    out = await workspace.run(command)
    assert out.ok, out.output
    assert out.output


async def test_mutations_land_in_order(workspace: Workspace) -> None:
    for command in [
        "write /docs/test.md 'hello world'",
        "edit /docs/test.md hello goodbye",
        "link /docs/test.md /docs/handbook.md references",
        "graph in /docs/handbook.md -d 1",
        "rm /docs/test.md",
    ]:
        out = await workspace.run(command)
        assert out.ok, out.output
    assert not (await workspace.run("cat /docs/test.md")).ok


async def test_bad_lines_are_refused_not_raised(workspace: Workspace) -> None:
    for line in ["bogus", "grep", "cat", "graph sideways /docs", "su nobody", "grep 'unbalanced"]:
        out = await workspace.run(line)
        assert not out.ok
        assert out.output.startswith("ERROR")


async def test_finance_is_invisible_until_granted(workspace: Workspace) -> None:
    assert "/finance" in (await workspace.run("ls /")).output
    await workspace.run("su sam")
    assert workspace.principal == "sam"
    assert "/finance" not in (await workspace.run("ls /")).output
    assert not (await workspace.run("cat /finance/board-update-2026-10.md")).ok
    assert not (await workspace.run("grant /finance sam read")).ok
    await workspace.run("su clay")
    assert (await workspace.run("grant /finance sam read")).ok
    await workspace.run("su sam")
    assert (await workspace.run("cat /finance/runway-model.csv")).ok
    assert not (await workspace.run("revoke /finance sam")).ok
    tree = await workspace.tree()
    assert "finance" in [child["name"] for child in tree["children"]]


async def test_the_agent_runs_on_behalf_of_the_signed_in_person(workspace: Workspace) -> None:
    await workspace.run("su sam")
    events = [chunk async for chunk in agent.respond(workspace, "How much runway do we have?", [])]
    assert any(chunk.startswith("event: tool") for chunk in events)
    assert events[-1].startswith("event: done")
    assert workspace.log[-1].actor == "atlas"
    assert workspace.log[-1].principal == "sam"
    assert not (await workspace.run("su clay", as_agent=True)).ok
