"""The workspace over MCP: one tool, the shell, so any MCP client is an agent here.

Claude Code connects with ``claude mcp add --transport http halyard
http://127.0.0.1:8765/mcp`` and gets the same shell Atlas has, run on
behalf of whoever is signed in to the web app. Its commands land in the
same log, tagged ``claude-code``, so the Terminal shows them as they run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer

from pluto_demo import seed
from pluto_demo.shell import HELP

if TYPE_CHECKING:
    from collections.abc import Callable

    from pluto_demo.kernel import Workspace

INSTRUCTIONS = (
    "This is the Halyard Robotics workspace on Pluto Systems. Everything here is a file in one namespace: "
    "documents, meeting notes, specs, customer notes, sheets, decks and code. You have one tool, `shell`, a "
    "bash-like shell over that namespace, run on behalf of the person signed in to the workspace; the kernel "
    "judges every call by their rights, so a missing path may be one you are not allowed to see. Find with "
    "find, grep and glean, follow edges with graph, read with cat, change with write and edit, and cite the "
    "paths you relied on.\n\n" + HELP
)


def build_mcp(get_workspace: Callable[[], Workspace]) -> MCPServer:
    """An MCP server whose one tool runs the shell on the workspace *get_workspace* returns."""
    server = MCPServer("halyard", instructions=INSTRUCTIONS)

    @server.tool(description="Run one line in the Halyard workspace shell and get its output. Type help for the verbs.")
    async def shell(command: str) -> str:
        out = await get_workspace().run(command, actor=seed.CLAUDE_CODE)
        return out.output or "(no output)"

    return server
