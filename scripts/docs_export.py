"""Export the public API of vfs for the docs app: every exported name, read from the source.

The docs app draws the Python API pages from one JSON file. This script writes
it. Griffe reads the package's source and never imports it, so the export needs
no build of the Rust extension::

    uv run --only-group docs python scripts/docs_export.py    # writes docs-app/src/lib/generated/api.json

The export is ``{"names": [...], "objects": {name: {kind, labels, signature,
bases, doc, members: [{name, kind, labels, signature, annotation, value, doc,
members}]}}}``. ``names`` is the package's ``__all__`` in its own order, ``labels``
says how a name is declared (``async``, ``property``, ``classmethod``), ``doc``
is Markdown with every marker already replaced, and a field with no value is
null. A member's own ``members`` are empty, except for a class that a module
lists and no page pulls in by name: it has no other place for its fields.

Four things are refused, each as an ``ExportError`` that names the place: a
``:term:`` marker for a term the glossary does not define, an exported name that
is on no API page or on two, a page that pulls in a name the package does not
export, and a glossary term out of shape. An API page pulls a name in with a
line of its own, ``::: vfs.Name``.

A glossary term is a second-level heading, a definition, and three labelled
parts in a fixed order, each a list item that opens ``- **Label:**``: "Seen by
callers", "In code" and "Instead of". Terms are in alphabetical order, and none
is defined twice.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import griffe

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src"
DOCUMENTATION = ROOT / "documentation"
OUT = ROOT / "docs-app" / "src" / "lib" / "generated" / "api.json"
PACKAGE = "vfs"

# The glossary page inside the documentation folder, and the route the app serves it at.
GLOSSARY_PAGE = Path("reference") / "glossary.md"
GLOSSARY_ROUTE = "/reference/glossary"

# The labelled parts every glossary term carries after its definition, in this order.
GLOSSARY_PARTS = ("Seen by callers", "In code", "Instead of")

TERM_HEADING = re.compile(r"^## (?P<term>.+?)\s*$")
TERM_PART = re.compile(r"^- \*\*(?P<label>[^*:]+):\*\*")
TERM_ROLE = re.compile(r":term:`(?P<body>[^`]+)`")
CODE_ROLE = re.compile(r":(?:py:)?(?:func|meth|class|data|attr|mod|exc|obj|const):`(?P<body>[^`]+)`")

# A role's body that carries its own wording: "arms <arm>" shows "arms" and points at "arm".
LABELLED = re.compile(r"^(?P<text>.+?)\s*<(?P<target>[^<>]+)>$")

FENCE = re.compile(r"^\s*(```|~~~)")

# Griffe's labels for an attribute the class body assigns, and for one a method assigns to ``self``.
CLASS_ATTRIBUTE = "class-attribute"
INSTANCE_ATTRIBUTE = "instance-attribute"


class ExportError(Exception):
    """The export was refused; the message names the object or the page, and why."""


# ---------------------------------------------------------------------------
# The export
# ---------------------------------------------------------------------------


def export(source: Path, documentation: Path, *, package: str = PACKAGE) -> dict[str, Any]:
    """The public API of *package* under *source*, placed on the API pages of *documentation*."""
    names = public_names(source / package / "__init__.py")
    _check_placement(names, api_blocks(documentation, package), package)
    terms = glossary_terms(documentation)
    loaded = griffe.load(package, search_paths=[str(source)])
    resolved = {name: _resolved(loaded, name, package) for name in names}
    # Where each exported name is defined: a class a module lists is described in full only if it is not one.
    exported = frozenset(target.path for target in resolved.values())
    objects = {name: _describe_object(target, terms, exported) for name, target in resolved.items()}
    return {"names": names, "objects": objects}


def main(argv: list[str] | None = None) -> int:
    """Write the export as JSON; 1, with the reason on stderr and no file written, when it is refused."""
    parser = argparse.ArgumentParser(description="Export the public API for the docs app")
    parser.add_argument("--source", type=Path, default=SOURCE, help="the folder that holds the package")
    parser.add_argument("--documentation", type=Path, default=DOCUMENTATION, help="the folder of Markdown pages")
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--out", type=Path, default=OUT, help="the JSON file to write")
    args = parser.parse_args(argv)
    try:
        exported = export(args.source, args.documentation, package=args.package)
    except ExportError as refusal:
        print(f"docs export refused: {refusal}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(exported, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    members = sum(len(entry["members"]) for entry in exported["objects"].values())
    print(f"docs export: {len(exported['names'])} names, {members} members -> {args.out}")
    return 0


# ---------------------------------------------------------------------------
# Reading the package and the pages
# ---------------------------------------------------------------------------


def public_names(init: Path) -> list[str]:
    """The names ``__all__`` exports, in its own order, read from the source without importing it."""
    tree = ast.parse(init.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            return list(ast.literal_eval(node.value))
    msg = f"{init} defines no __all__"
    raise ExportError(msg)


def glossary_terms(documentation: Path) -> dict[str, str]:
    """Each glossary term, case-folded, with the anchor of its heading; empty when there is no glossary page.

    A term out of shape is refused here, before any docstring is read against the glossary.
    """
    page = documentation / GLOSSARY_PAGE
    if not page.is_file():
        return {}
    sections = _term_sections(page.read_text(encoding="utf-8"))
    _check_glossary(sections)
    return {term.casefold(): anchor_of(term) for term, _ in sections}


def anchor_of(heading: str) -> str:
    """A heading's anchor: lower case, each run of other characters one hyphen, none at either end."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def api_blocks(documentation: Path, package: str) -> dict[str, list[str]]:
    """Each name an API block pulls in, with the pages that pull it, by path inside *documentation*."""
    block = re.compile(rf"^::: {re.escape(package)}\.(?P<name>\S+)\s*$")
    found: dict[str, list[str]] = {}
    for page in sorted(documentation.rglob("*.md")):
        for line in _lines_outside_fences(page.read_text(encoding="utf-8")):
            match = block.match(line)
            if match:
                found.setdefault(match["name"], []).append(page.relative_to(documentation).as_posix())
    return found


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lines_outside_fences(text: str) -> Iterator[str]:
    """The lines of a page that sit outside every fenced code block."""
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield line


def _term_sections(text: str) -> list[tuple[str, list[str]]]:
    """Each term of the glossary page with the lines under its heading, in the page's order."""
    sections: list[tuple[str, list[str]]] = []
    for line in _lines_outside_fences(text):
        heading = TERM_HEADING.match(line)
        if heading:
            sections.append((heading["term"], []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def _check_glossary(sections: list[tuple[str, list[str]]]) -> None:
    """Refuse a term defined twice, out of alphabetical order, with no definition, or without its three parts."""
    keys: list[str] = []
    for term, lines in sections:
        key = term.casefold()
        if key in keys:
            msg = f"the glossary defines the term {term!r} twice"
            raise ExportError(msg)
        if keys and key < keys[-1]:
            msg = f"the glossary term {term!r} is out of alphabetical order"
            raise ExportError(msg)
        keys.append(key)
        labels = [part["label"] for line in lines if (part := TERM_PART.match(line))]
        before_parts = lines[: next((at for at, line in enumerate(lines) if TERM_PART.match(line)), len(lines))]
        if not any(line.strip() for line in before_parts):
            msg = f"the glossary term {term!r} has no definition above its parts"
            raise ExportError(msg)
        if labels != list(GLOSSARY_PARTS):
            msg = f"the glossary term {term!r} has the parts {labels}; a term has {list(GLOSSARY_PARTS)}, in that order"
            raise ExportError(msg)


def _check_placement(names: list[str], blocks: dict[str, list[str]], package: str) -> None:
    """Refuse unless every exported name is on exactly one page and every block names an exported name."""
    problems = [f"{package}.{name} is on no page" for name in names if name not in blocks]
    problems += [
        f"{package}.{name} is on {len(pages)} pages: {', '.join(pages)}"
        for name, pages in blocks.items()
        if name in names and len(pages) > 1
    ]
    problems += [
        f"{package}.{name}, pulled in by {', '.join(pages)}, is not exported by {package}.__all__"
        for name, pages in blocks.items()
        if name not in names
    ]
    if problems:
        raise ExportError("; ".join(problems))


def _resolved(loaded: griffe.Object | griffe.Alias, name: str, package: str) -> griffe.Object:
    """The object an exported name stands for, wherever in the package it is defined."""
    try:
        member = loaded[name]
        return member.final_target if member.is_alias else member
    except (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError) as error:
        msg = f"{package}.{name} is exported and cannot be read from the source: {error}"
        raise ExportError(msg) from error


def _describe_object(target: griffe.Object, terms: dict[str, str], exported: frozenset[str]) -> dict[str, Any]:
    """One exported name: its kind, signature, bases, docstring and members."""
    members: list[dict[str, Any]] = []
    if target.is_class or target.is_module:
        members = [_describe_member(member, terms, exported) for member in _public_members(target)]
    return {
        "kind": target.kind.value,
        "labels": sorted(target.labels),
        "signature": _signature_of(target),
        "bases": [str(base) for base in target.bases] if isinstance(target, griffe.Class) else [],
        "doc": _markdown(target, terms),
        "members": members,
    }


def _describe_member(
    target: griffe.Object, terms: dict[str, str], exported: frozenset[str], *, nested: bool = False
) -> dict[str, Any]:
    """One member of a class or a module; a class no page pulls in by name carries its own members."""
    attribute = target if isinstance(target, griffe.Attribute) else None
    # A value is what a class or a module assigns. What a method assigns to ``self`` is a parameter's name.
    labels = attribute.labels if attribute is not None else set()
    set_in_a_method = INSTANCE_ATTRIBUTE in labels and CLASS_ATTRIBUTE not in labels
    valued = attribute is not None and attribute.value is not None and not set_in_a_method
    members: list[dict[str, Any]] = []
    if target.is_class and not nested and target.path not in exported:
        members = [_describe_member(member, terms, exported, nested=True) for member in _public_members(target)]
    return {
        "name": target.name,
        "kind": target.kind.value,
        "labels": sorted(target.labels),
        "signature": _signature_of(target),
        "annotation": None if attribute is None or attribute.annotation is None else str(attribute.annotation),
        "value": str(attribute.value) if attribute is not None and valued else None,
        "doc": _markdown(target, terms),
        "members": members,
    }


def _public_members(target: griffe.Object) -> list[griffe.Object]:
    """A class's public attributes and functions, or what a module itself defines, in source order."""
    members: list[griffe.Object] = []
    for name, member in target.members.items():
        if isinstance(member, griffe.Alias) or name == "__init__" or not _is_public(name):
            continue
        # A module's special names, such as ``__all__``, say how it is imported, not what it holds.
        if target.is_module and name.startswith("__"):
            continue
        members.append(member)
    return members


def _is_public(name: str) -> bool:
    """Whether a name is for callers: no leading underscore, or a special method such as ``__len__``."""
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def _signature_of(target: griffe.Object) -> str | None:
    """A function's signature, a class's constructor signature when it writes one, and null for the rest."""
    if isinstance(target, griffe.Function):
        return _signature(target)
    if isinstance(target, griffe.Class):
        constructor = target.members.get("__init__")
        if isinstance(constructor, griffe.Function):
            return _signature(constructor)
    return None


def _signature(function: griffe.Function) -> str:
    """A function's parameters and return type as source text, without ``self`` or ``cls``."""
    kinds = griffe.ParameterKind
    parameters = [parameter for parameter in function.parameters if parameter.name not in ("self", "cls")]
    parts: list[str] = []
    starred = False
    for index, parameter in enumerate(parameters):
        text = parameter.name
        if parameter.kind is kinds.var_positional:
            text, starred = f"*{text}", True
        elif parameter.kind is kinds.var_keyword:
            text = f"**{text}"
        elif parameter.kind is kinds.keyword_only and not starred:
            parts.append("*")
            starred = True
        if parameter.annotation is not None:
            text += f": {parameter.annotation}"
        if parameter.default is not None and parameter.kind not in (kinds.var_positional, kinds.var_keyword):
            text += f" = {parameter.default}"
        parts.append(text)
        last_positional_only = parameter.kind is kinds.positional_only and (
            index + 1 == len(parameters) or parameters[index + 1].kind is not kinds.positional_only
        )
        if last_positional_only:
            parts.append("/")
    returns = f" -> {function.returns}" if function.returns is not None else ""
    return f"({', '.join(parts)}){returns}"


def _markdown(target: griffe.Object, terms: dict[str, str]) -> str:
    """A docstring as Markdown: each term marker a glossary link, each code role inline code."""
    if target.docstring is None:
        return ""

    def link(match: re.Match[str]) -> str:
        text, term = _text_and_target(match["body"])
        anchor = terms.get(term.casefold())
        if anchor is None:
            msg = f"{target.path} marks the term {term!r}, which the glossary does not define"
            raise ExportError(msg)
        return f"[{text}]({GLOSSARY_ROUTE}#{anchor})"

    return CODE_ROLE.sub(_code_span, TERM_ROLE.sub(link, target.docstring.value))


def _text_and_target(body: str) -> tuple[str, str]:
    """A role body's wording and what it points at: the same text unless it is written "text <target>"."""
    labelled = LABELLED.match(body)
    return (labelled["text"], labelled["target"]) if labelled else (body, body)


def _code_span(match: re.Match[str]) -> str:
    """A code role as inline code: its own wording, or the last part of a name written with a leading ``~``."""
    text, target = _text_and_target(match["body"])
    if text == target and target.startswith("~"):
        text = target.rpartition(".")[2]
    return f"`{text}`"


if __name__ == "__main__":
    raise SystemExit(main())
