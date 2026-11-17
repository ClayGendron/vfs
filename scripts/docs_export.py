"""Export the public API of vfs for the docs app: every exported name, read from the source.

The docs app draws the Python API pages from one JSON file. This script writes
it. Griffe reads the package's source and never imports it, so the export needs
no build of the Rust extension::

    uv run --only-group docs python scripts/docs_export.py    # writes docs-app/src/lib/generated/api.json

The export is ``{"names": [...], "objects": {name: {kind, labels, signature,
bases, doc, members: [{name, kind, labels, signature, annotation, value, doc,
members}]}}, "internals": {path: {...}}}``. ``internals`` holds the private
objects a page under ``maintainers/`` pulls in, each under its dotted path inside
the package and in the shape of an exported one; a private object on any other
page, or a public one on a maintainer page, is refused.
``names`` is the package's ``__all__`` in its own order, ``labels``
says how a name is declared (``async``, ``property``, ``classmethod``), ``doc``
is Markdown with every marker already replaced, and a field with no value is
null. A member's own ``members`` are empty, except for a class that a module
lists and no page pulls in by name: it has no other place for its fields.

Four things are refused, each as an ``ExportError`` that names the place: a
``:term:`` marker for a term the glossary does not define, an exported name that
is on no API page or on two, a page that pulls in a name the package does not
export, and a glossary term out of shape. An API page pulls a name in with a
line of its own, ``::: vfs.Name``.

A glossary term is a second-level heading, one opening sentence of at most 25
words, a longer description, and one labelled part, a list item that opens
``- **Types:**``. Terms are in alphabetical order, and none is defined twice.
Types holds names only, each in backticks: an exported name (``Entry``) or a
path inside the package (``paths.split``); each must be in the source.

``glossary`` in the export is ``{term: {anchor, short, types, code,
documentation, mentions, mentioned_by}}``. ``short`` is the opening sentence.
``types`` and ``code`` are lists of ``{name, id, page, public}``: the names the
page writes, and every object in the package, private ones included, whose
docstring marks the term with ``:term:``. ``documentation`` is every page
outside the reference section that links to the term, as ``{page, title}``.
``mentions`` and ``mentioned_by`` are the other terms a definition links to and
the terms that link to it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

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

# The folder of pages for people who change the package; only these pages may pull in a private object.
INTERNAL_PAGES = "maintainers"

# The labelled parts every glossary term carries after its definition, in this order.
GLOSSARY_PARTS = ("Types",)
# The most words a term's opening sentence may have: it is what the site shows where a term is linked.
SHORT_WORDS = 25
CODE_SPAN = re.compile(r"`([^`]+)`")
SAME_PAGE_LINK = re.compile(r"\]\(#([a-z0-9-]+)\)")
PAGE_LINK = re.compile(r"\]\((?P<target>[^)\s#]+)#(?P<anchor>[^)\s]+)\)")

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
    api, internal = _api_and_internal(api_blocks(documentation, package))
    _check_placement(names, api, package)
    terms = glossary_terms(documentation)
    loaded = griffe.load(package, search_paths=[str(source)])
    resolved = {name: _resolved(loaded, name, package) for name in names}
    # Where each exported name is defined: a class a module lists is described in full only if it is not one.
    exported = frozenset(target.path for target in resolved.values())
    objects = {name: _describe_object(target, terms, exported) for name, target in resolved.items()}
    private = {name: _private_target(loaded, name, pages, exported, package) for name, pages in internal.items()}
    internals = {name: _describe_object(target, terms, exported) for name, target in private.items()}
    public = {target.path: name for name, target in resolved.items()}
    book = _Book(package, loaded, resolved, public, api, internal, terms)
    glossary = _describe_glossary(_glossary_sections(documentation), documentation, book)
    return {"names": names, "objects": objects, "internals": internals, "glossary": glossary}


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
    return {term.casefold(): anchor_of(term) for term, _ in _glossary_sections(documentation)}


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


def _glossary_sections(documentation: Path) -> list[tuple[str, list[str]]]:
    """Each term of the glossary page with its lines, checked for shape; empty when there is no page."""
    page = documentation / GLOSSARY_PAGE
    if not page.is_file():
        return []
    sections = _term_sections(page.read_text(encoding="utf-8"))
    _check_glossary(sections)
    return sections


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
    """Refuse a term defined twice, out of order, without its sentence and description, or without its part."""
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
        paragraphs = _paragraphs(lines[: _first_part(lines)])
        if not paragraphs:
            msg = f"the glossary term {term!r} has no definition above its parts"
            raise ExportError(msg)
        words = len(paragraphs[0].split())
        if words > SHORT_WORDS or not paragraphs[0].endswith("."):
            msg = (
                f"the glossary term {term!r} opens with {words} words; a term opens with one sentence of at most "
                f"{SHORT_WORDS} words that ends in a full stop"
            )
            raise ExportError(msg)
        if len(paragraphs) == 1:
            msg = f"the glossary term {term!r} has no longer description under its opening sentence"
            raise ExportError(msg)
        if labels != list(GLOSSARY_PARTS):
            msg = f"the glossary term {term!r} has the parts {labels}; a term has {list(GLOSSARY_PARTS)}, in that order"
            raise ExportError(msg)


def _first_part(lines: list[str]) -> int:
    """Where a term's labelled parts begin among its lines: the end, when it has none."""
    return next((at for at, line in enumerate(lines) if TERM_PART.match(line)), len(lines))


def _paragraphs(lines: list[str]) -> list[str]:
    """Runs of lines between blank ones, each joined into one line."""
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paragraphs[-1].append(line.strip())
        elif paragraphs[-1]:
            paragraphs.append([])
    return [" ".join(paragraph) for paragraph in paragraphs if paragraph]


class _Book(NamedTuple):
    """What a name the glossary cites is read against: the source, the exported names, and the pages that hold them."""

    package: str
    loaded: griffe.Object | griffe.Alias
    resolved: dict[str, griffe.Object]
    public: dict[str, str]
    api: dict[str, list[str]]
    internal: dict[str, list[str]]
    terms: dict[str, str]


def _describe_glossary(
    sections: list[tuple[str, list[str]]], documentation: Path, book: _Book
) -> dict[str, dict[str, Any]]:
    """Each term: its opening sentence and types as written, then what marks it, links to it and mentions it."""
    names = {anchor_of(term): term for term, _ in sections}
    marked = _marked_by_term(book)
    linking = _linking_pages(documentation, frozenset(names))
    mentions = {
        term: [names[anchor] for anchor in _linked_terms(lines) if names.get(anchor, term) != term]
        for term, lines in sections
    }
    return {
        term: {
            "anchor": anchor_of(term),
            "short": _paragraphs(lines[: _first_part(lines)])[0],
            "types": [_cite(_cited_target(name, term, book), book) for name in _type_names(lines)],
            "code": marked.get(term.casefold(), []),
            "documentation": linking.get(anchor_of(term), []),
            "mentions": mentions[term],
            "mentioned_by": [other for other, found in mentions.items() if term in found],
        }
        for term, lines in sections
    }


def _type_names(lines: list[str]) -> list[str]:
    """The names a term writes under Types: every code span from that label on."""
    return [name for line in lines[_first_part(lines) :] for name in CODE_SPAN.findall(line)]


def _linked_terms(lines: list[str]) -> list[str]:
    """The anchors a term's lines link to on the glossary page itself, each once, in the order met."""
    return list(dict.fromkeys(anchor for line in lines for anchor in SAME_PAGE_LINK.findall(line)))


def _marked_by_term(book: _Book) -> dict[str, list[dict[str, Any]]]:
    """Each term with the objects whose docstring marks it, public ones first, each once and by name."""
    marked: dict[str, dict[str, dict[str, Any]]] = {}
    for target in _documented(book.loaded):
        for role in TERM_ROLE.finditer(target.docstring.value if target.docstring else ""):
            term = _text_and_target(role["body"])[1]
            if term.casefold() not in book.terms:
                msg = f"{target.path} marks the term {term!r}, which the glossary does not define"
                raise ExportError(msg)
            cited = _cite(target, book)
            marked.setdefault(term.casefold(), {})[cited["name"]] = cited
    return {
        term: sorted(found.values(), key=lambda cited: (not cited["public"], cited["name"]))
        for term, found in marked.items()
    }


def _documented(root: griffe.Object | griffe.Alias) -> Iterator[griffe.Object]:
    """Every object the package itself defines, at any depth: modules, classes, functions and attributes."""
    for member in root.members.values():
        if isinstance(member, griffe.Alias):
            continue
        yield member
        if member.is_module or member.is_class:
            yield from _documented(member)


def _linking_pages(documentation: Path, anchors: frozenset[str]) -> dict[str, list[dict[str, str]]]:
    """Each term's anchor with the pages outside the reference section that link to it, each once, by path."""
    glossary = (documentation / GLOSSARY_PAGE).resolve()
    linking: dict[str, list[dict[str, str]]] = {}
    for page in sorted(documentation.rglob("*.md")):
        inside = page.relative_to(documentation)
        if inside.parts[0] == GLOSSARY_PAGE.parts[0]:
            continue
        lines = list(_lines_outside_fences(page.read_text(encoding="utf-8")))
        title = next((line[2:].strip() for line in lines if line.startswith("# ")), inside.stem)
        found = {
            link["anchor"]
            for line in lines
            for link in PAGE_LINK.finditer(line)
            if (page.parent / link["target"]).resolve() == glossary and link["anchor"] in anchors
        }
        for anchor in sorted(found):
            linking.setdefault(anchor, []).append({"page": inside.as_posix(), "title": title})
    return linking


def _cited_target(written: str, term: str, book: _Book) -> griffe.Object:
    """The object a cited name stands for: read from an exported name first, then as a path inside the package."""
    first, _, rest = written.partition(".")
    places: list[tuple[griffe.Object | griffe.Alias, str]] = [(book.loaded, written)]
    if first in book.resolved:
        places.insert(0, (book.resolved[first], rest))
    for root, path in places:
        try:
            found = root[path] if path else root
            return found.final_target if isinstance(found, griffe.Alias) else found
        except (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError):
            continue
    msg = f"the glossary term {term!r} names `{written}`, which is not in the source"
    raise ExportError(msg)


def _cite(target: griffe.Object, book: _Book) -> dict[str, Any]:
    """One cited object: its name as a caller writes it, the page that holds it, and whether it is public."""
    name, page, public = _placed(target, book)
    return {"name": name, "id": f"{book.package}.{name}", "page": page, "public": public}


def _placed(target: griffe.Object, book: _Book) -> tuple[str, str | None, bool]:
    """An object's name, its page and whether it is public: by the exported name above it, or by its own path."""
    parts = target.path.split(".")
    for cut in range(len(parts), 0, -1):
        exported = book.public.get(".".join(parts[:cut]))
        if exported is not None:
            return ".".join([exported, *parts[cut:]]), book.api[exported][0], True
    inside = parts[1:]
    for cut in range(len(inside), 0, -1):
        pages = book.internal.get(".".join(inside[:cut]))
        if pages:
            return ".".join(inside), pages[0], False
    return ".".join(inside), None, False


def _api_and_internal(blocks: dict[str, list[str]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The blocks split by where their page sits: on an API page, or on a maintainer page."""
    api: dict[str, list[str]] = {}
    internal: dict[str, list[str]] = {}
    for name, pages in blocks.items():
        for page in pages:
            side = internal if Path(page).parts[0] == INTERNAL_PAGES else api
            side.setdefault(name, []).append(page)
    return api, internal


def _private_target(
    loaded: griffe.Object | griffe.Alias, name: str, pages: list[str], exported: frozenset[str], package: str
) -> griffe.Object:
    """The private object a maintainer page pulls in by its path; refused when missing, public, or on two pages."""
    where = ", ".join(pages)
    if len(pages) > 1:
        msg = f"{package}.{name} is on {len(pages)} maintainer pages: {where}"
        raise ExportError(msg)
    try:
        member = loaded[name]
        target = member.final_target if member.is_alias else member
    except (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError) as error:
        msg = f"{package}.{name}, pulled in by {where}, cannot be read from the source: {error}"
        raise ExportError(msg) from error
    if target.path in exported:
        msg = f"{package}.{name}, pulled in by {where}, is public and belongs on an API page"
        raise ExportError(msg)
    return target


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
