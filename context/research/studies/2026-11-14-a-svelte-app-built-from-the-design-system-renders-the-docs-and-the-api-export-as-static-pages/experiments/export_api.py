"""Probe: read the public API of vfs from its source with Griffe and write it as JSON.

Run from the vfs checkout:  uv run --group docs python <this file> <out.json>
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import griffe

ROOT = Path.cwd()
TERM_ROLE = re.compile(r":term:`(?P<body>[^`]+)`")
CODE_ROLE = re.compile(r":(?:py:)?(?:func|meth|class|data|attr|mod|exc|obj|const):`(?P<body>[^`]+)`")
LABELLED = re.compile(r"^(?P<text>.+?)\s*<(?P<target>[^<>]+)>$")
TERM_HEADING = re.compile(r"^## (?P<term>.+?)\s*$", re.MULTILINE)


def public_names() -> list[str]:
    tree = ast.parse((ROOT / "src/vfs/__init__.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit("no __all__")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def markdown(doc: str | None, terms: dict[str, str], unknown: list[str], where: str) -> str:
    if not doc:
        return ""

    def split(body: str) -> tuple[str, str]:
        m = LABELLED.match(body)
        return (m["text"], m["target"]) if m else (body, body)

    def term(match: re.Match[str]) -> str:
        text, target = split(match["body"])
        anchor = terms.get(target.casefold())
        if anchor is None:
            unknown.append(f"{where}: {target}")
            return text
        return f"[{text}](/reference/glossary#{anchor})"

    def code(match: re.Match[str]) -> str:
        text, target = split(match["body"])
        if text == target and target.startswith("~"):
            text = target.rpartition(".")[2]
        return f"`{text}`"

    return CODE_ROLE.sub(code, TERM_ROLE.sub(term, doc))


def signature(fn: griffe.Function) -> str:
    parts = []
    for p in fn.parameters:
        if p.name in ("self", "cls"):
            continue
        text = p.name
        if p.kind is griffe.ParameterKind.var_positional:
            text = "*" + text
        elif p.kind is griffe.ParameterKind.var_keyword:
            text = "**" + text
        if p.annotation is not None:
            text += f": {p.annotation}"
        if p.default is not None and p.kind not in (griffe.ParameterKind.var_positional, griffe.ParameterKind.var_keyword):
            text += f" = {p.default}"
        parts.append((p.kind, text))
    out, seen_kw = [], False
    for kind, text in parts:
        if kind is griffe.ParameterKind.keyword_only and not seen_kw and not any(
            k is griffe.ParameterKind.var_positional for k, _ in parts
        ):
            out.append("*")
            seen_kw = True
        out.append(text)
    returns = f" -> {fn.returns}" if fn.returns is not None else ""
    return f"({', '.join(out)}){returns}"


def describe(obj: griffe.Object | griffe.Alias, terms: dict[str, str], unknown: list[str], depth: int = 0) -> dict:
    target = obj.final_target if obj.is_alias else obj
    entry: dict = {
        "name": obj.name,
        "kind": target.kind.value,
        "doc": markdown(target.docstring.value if target.docstring else None, terms, unknown, target.path),
    }
    if target.is_function:
        entry["signature"] = signature(target)
        entry["labels"] = sorted(target.labels)
    elif target.is_attribute:
        entry["annotation"] = None if target.annotation is None else str(target.annotation)
        entry["value"] = None if target.value is None else str(target.value)
        entry["labels"] = sorted(target.labels)
    elif target.is_class:
        entry["bases"] = [str(b) for b in target.bases]
        init = target.members.get("__init__")
        if init is not None and not init.is_alias and init.is_function:
            entry["signature"] = signature(init)
        if depth == 0:
            members = []
            for name, member in target.members.items():
                if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
                    continue
                if name == "__init__" or member.is_alias and not member.final_target.is_function:
                    continue
                members.append(describe(member, terms, unknown, depth + 1))
            entry["members"] = members
    return entry


def main() -> None:
    out = Path(sys.argv[1])
    glossary = (ROOT / "documentation/reference/glossary.md").read_text()
    terms = {m["term"].casefold(): slug(m["term"]) for m in TERM_HEADING.finditer(glossary)}
    package = griffe.load("vfs", search_paths=[str(ROOT / "src")])
    unknown: list[str] = []
    names = public_names()
    api = {name: describe(package[name], terms, unknown) for name in names}
    out.write_text(json.dumps({"names": names, "objects": api, "terms": terms}, indent=1))
    members = sum(len(o.get("members", [])) for o in api.values())
    undocumented = [f"{n}.{m['name']}" for n, o in api.items() for m in o.get("members", []) if m["kind"] == "function" and not m["doc"]]
    print(f"names {len(names)}  members {members}  bytes {out.stat().st_size}  unknown terms {unknown}")
    print(f"kinds {sorted({o['kind'] for o in api.values()})}  functions with no docstring {len(undocumented)}")
    for name in ("AsyncVirtualFileSystem", "Entry", "MountInfo", "MountError", "Result", "permissions"):
        o = api[name]
        print(f"  {name}: {o['kind']}, members {len(o.get('members', []))}, signature {o.get('signature', '')[:70]!r}")
    if unknown:
        raise SystemExit(1)


main()
