"""Load real MCP tool catalogs checked into three repositories, as data.

Sources (shallow clones beside the vfs checkout, read only):

- /home/user/github-mcp-server/pkg/github/__toolsnaps__/*.snap  (GitHub's server, Go)
- /home/user/alibabacloud-devops-mcp-server/tools.json          (Alibaba Cloud DevOps, TypeScript/zod)
- /home/user/mcp-registry/servers/*/tools.json                  (Docker's MCP registry, many servers)

Every tool is normalised to one dict:
    server, name, description, input_schema (dict or None), annotations, output_schema, origin
`origin` says how faithful the schema is: "toolsnap" and "export" and "docker-inputSchema" are full
JSON Schemas as the server publishes them; "docker-arguments" is Docker's flat argument list converted
to a JSON Schema here (lossy: no enums, no nested shapes); "docker-none" has no argument data at all.
"""

from __future__ import annotations

import glob
import json
import os
import sys

GITHUB = "/home/user/github-mcp-server/pkg/github/__toolsnaps__"
ALIBABA = "/home/user/alibabacloud-devops-mcp-server/tools.json"
DOCKER = "/home/user/mcp-registry/servers"
SCRATCH = "/tmp/claude-0/-home-user-vfs/73990fc9-bba6-5cb3-8c5e-89a0fb7832d2/scratchpad"


def _tool(server, raw, input_schema, origin):
    return {
        "server": server,
        "name": raw["name"],
        "description": raw.get("description") or "",
        "input_schema": input_schema,
        "annotations": raw.get("annotations") or {},
        "output_schema": raw.get("outputSchema"),
        "origin": origin,
    }


def load_github():
    """One tool per name; the `_output` variants (no description) and a second job-logs variant are test fixtures."""
    by_name = {}
    for path in sorted(glob.glob(os.path.join(GITHUB, "*.snap"))):
        raw = json.load(open(path, encoding="utf-8"))
        base = os.path.basename(path)[: -len(".snap")]
        if base.endswith("_output"):
            continue
        name = raw["name"]
        if name in by_name and base != name:
            continue
        by_name[name] = _tool("github", raw, raw.get("inputSchema"), "toolsnap")
    return [by_name[n] for n in sorted(by_name)]


def load_alibaba():
    data = json.load(open(ALIBABA, encoding="utf-8"))
    return [_tool("alibaba-devops", raw, raw.get("inputSchema"), "export") for raw in data["tools"]]


def _from_arguments(arguments):
    properties, required = {}, []
    for arg in arguments:
        prop = {"type": arg.get("type", "string")}
        if arg.get("desc"):
            prop["description"] = arg["desc"]
        if "items" in arg:
            prop["items"] = arg["items"]
        properties[arg["name"]] = prop
        if not arg.get("optional"):
            required.append(arg["name"])
    return {"type": "object", "properties": properties, "required": required}


def load_docker():
    tools = []
    for path in sorted(glob.glob(os.path.join(DOCKER, "*", "tools.json"))):
        server = os.path.basename(os.path.dirname(path))
        raws = json.load(open(path, encoding="utf-8"))
        if not raws:
            continue
        server_has_args = any("arguments" in r or "inputSchema" in r for r in raws)
        for raw in raws:
            if "inputSchema" in raw:
                tools.append(_tool(server, raw, raw["inputSchema"], "docker-inputSchema"))
            elif "arguments" in raw:
                tools.append(_tool(server, raw, _from_arguments(raw["arguments"]), "docker-arguments"))
            elif server_has_args:
                tools.append(_tool(server, raw, {"type": "object", "properties": {}}, "docker-arguments"))
            else:
                tools.append(_tool(server, raw, None, "docker-none"))
    return tools


def load_all():
    return load_github() + load_alibaba() + load_docker()


def model_view(tool):
    """What a tools/list consumer is given per tool, minus annotations and outputSchema."""
    view = {"name": tool["name"], "description": tool["description"]}
    if tool["input_schema"] is not None:
        view["inputSchema"] = tool["input_schema"]
    return view


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def est_tokens(text):
    """chars / 4, rounded up: an estimate, no tokenizer."""
    return -(-len(text) // 4)


def nbytes(text):
    return len(text.encode("utf-8"))


if __name__ == "__main__":
    everything = load_all()
    servers = {}
    for t in everything:
        servers.setdefault(t["server"], 0)
        servers[t["server"]] += 1
    print(len(everything), "tools,", len(servers), "servers", file=sys.stderr)
