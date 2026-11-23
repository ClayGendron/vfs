"""Findability of real MCP tools under vfs's lexical `search` and `grep`, by manifest shape.

Corpus: the tool lists of five server records in the agentic-community/mcp-gateway-registry
clone (registry/servers/*.json), 81 tools. Each tool is written twice, into two mounts:

  /desc  the body is the tool's description alone (what a description-only index holds)
  /card  the body is name, server and description only
  /man   the body is a TOOL.md manifest: name, server, description, arguments, returns

The path is the same shape in both: /<mount>/<server>/tools/<tool>.md. Queries are
hand-written task phrasings with an accepted set of tools each. Lexical leg only: the
storage is built with no embedder. Each shape is ranked before and after `rebuild`.

Usage: uv run python -I run.py /home/user/mcp-gateway-registry
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path as FsPath

from vfs import AsyncVirtualFileSystem, DatabaseStorage

SERVERS = ("atlassian", "sre-gateway", "mcpgw", "currenttime", "realserverfaketools")

QUERIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("find tickets matching a JQL filter", frozenset({"jira_search"})),
    ("log two hours of work on a ticket", frozenset({"jira_add_worklog"})),
    ("move a ticket to Done", frozenset({"jira_transition_issue"})),
    ("open a new bug in Jira", frozenset({"jira_create_issue"})),
    ("attach an issue to an epic", frozenset({"jira_link_to_epic"})),
    ("which sprints does a board have", frozenset({"jira_get_sprints_from_board"})),
    ("start a new sprint on the board", frozenset({"jira_create_sprint"})),
    ("list every Jira project I can see", frozenset({"jira_get_all_projects"})),
    ("release versions of a Jira project", frozenset({"jira_get_project_versions"})),
    ("write a new wiki page", frozenset({"confluence_create_page"})),
    ("find Confluence pages about onboarding", frozenset({"confluence_search"})),
    ("comment on a Confluence page", frozenset({"confluence_add_comment"})),
    ("tag a page with a label", frozenset({"confluence_add_label"})),
    ("which pods are crashing in the cluster", frozenset({"k8s-api___get_pod_status"})),
    ("has the deployment finished rolling out", frozenset({"k8s-api___get_deployment_status"})),
    ("recent error logs for the checkout service", frozenset({"logs-api___get_error_logs"})),
    ("error rate of the API over the last hour", frozenset({"metrics-api___get_error_rates"})),
    ("incident playbook for a database outage", frozenset({"runbooks-api___get_incident_playbook"})),
    ("who do I escalate a sev1 to", frozenset({"runbooks-api___get_escalation_procedures"})),
    (
        "cpu and memory usage of the nodes",
        frozenset({"k8s-api___get_resource_usage", "metrics-api___get_resource_metrics", "k8s-api___get_node_status"}),
    ),
    ("what time is it in Tokyo", frozenset({"current_time_by_timezone"})),
    ("disable an MCP server in the gateway", frozenset({"toggle_service"})),
    ("register a new MCP server", frozenset({"register_service"})),
    ("generate fake test data from a schema", frozenset({"synthetic_data_generator"})),
    ("download the files attached to a ticket", frozenset({"jira_download_attachments"})),
    ("remove the link between two tickets", frozenset({"jira_remove_issue_link"})),
)

# A second query set: the agent already knows (or guesses) the identifier.
NAME_QUERIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("jira_add_worklog", frozenset({"jira_add_worklog"})),
    ("get_pod_status", frozenset({"k8s-api___get_pod_status"})),
    ("search_runbooks", frozenset({"runbooks-api___search_runbooks"})),
    ("confluence_get_page_children", frozenset({"confluence_get_page_children"})),
    ("toggle_service", frozenset({"toggle_service"})),
)


VERBOSE = "-v" in sys.argv


def load(root: FsPath) -> list[dict[str, str]]:
    tools: list[dict[str, str]] = []
    for server in SERVERS:
        record = json.loads((root / "registry" / "servers" / f"{server}.json").read_text())
        for tool in record["tool_list"]:
            parsed = tool.get("parsed_description") or {}
            props = (tool.get("schema") or {}).get("properties") or {}
            args = "\n".join(
                f"- `{name}` ({spec.get('type', 'any')}): {spec.get('description', '')}" for name, spec in props.items()
            )
            tools.append(
                {
                    "server": server,
                    "server_title": record.get("server_name", server),
                    "name": tool["name"],
                    "description": parsed.get("main") or tool.get("description") or "No description available.",
                    "returns": parsed.get("returns") or "",
                    "args": args,
                }
            )
    return tools


def manifest(tool: dict[str, str]) -> str:
    return (
        f"# {tool['name']}\n\n"
        f"server: {tool['server']} ({tool['server_title']})\n\n"
        f"{tool['description']}\n\n"
        f"## Arguments\n\n{tool['args'] or '(none)'}\n\n"
        f"## Returns\n\n{tool['returns'] or '(unspecified)'}\n"
    )


def card(tool: dict[str, str]) -> str:
    return f"# {tool['name']}\n\nserver: {tool['server']} ({tool['server_title']})\n\n{tool['description']}\n"


def tool_of(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".md")


async def rank(fs: AsyncVirtualFileSystem, mount: str, queries) -> dict[str, float]:
    hit1 = hit5 = 0
    reciprocal = 0.0
    misses: list[str] = []
    for query, accepted in queries:
        result = await fs.search(query, limit=10, paths=(f"/{mount}",))
        names = [tool_of(str(p)) for p in result.paths]
        position = next((i for i, n in enumerate(names) if n in accepted), None)
        if VERBOSE:
            print(f"  {mount} {query!r}: rank {None if position is None else position + 1}; top3 {names[:3]}")
        if position is None:
            misses.append(query)
            continue
        reciprocal += 1 / (position + 1)
        hit1 += position == 0
        hit5 += position < 5
    n = len(queries)
    return {"hit@1": hit1 / n, "hit@5": hit5 / n, "mrr@10": round(reciprocal / n, 3), "misses_in_top10": misses}


async def main(root: FsPath) -> None:
    tools = load(root)
    fs = AsyncVirtualFileSystem()
    storages = {mount: DatabaseStorage(url="sqlite+aiosqlite:///:memory:") for mount in ("desc", "card", "man")}
    for mount, storage in storages.items():
        await fs.add_mount(storage, f"/{mount}")
    for tool in tools:
        tail = f"{tool['server']}/tools/{tool['name']}.md"
        await fs.write(path=f"/desc/{tail}", content=tool["description"], parents=True)
        await fs.write(path=f"/card/{tail}", content=card(tool), parents=True)
        await fs.write(path=f"/man/{tail}", content=manifest(tool), parents=True)
    print(f"tools: {len(tools)}; without a description: {sum(t['description'].startswith('No description') for t in tools)}")
    for phase in ("before rebuild (overlay)", "after rebuild (index)"):
        if phase.startswith("after"):
            for storage in storages.values():
                print("rebuild", (await storage.rebuild()).success)
        for label, queries in (("task queries", QUERIES), ("identifier queries", NAME_QUERIES)):
            for mount in ("desc", "card", "man"):
                print(phase, "|", label, "|", mount, "|", await rank(fs, mount, queries))
    for pattern in ("pod", "escalat", "worklog"):
        for mount in ("desc", "man"):
            found = await fs.grep(pattern, paths=(f"/{mount}",), case_mode="insensitive")
            print("grep", repr(pattern), mount, sorted({tool_of(str(p)) for p in found.paths}))
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main(FsPath(sys.argv[1])))
