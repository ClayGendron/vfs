"""Export the public API of vfs for the docs app: every exported name, read from the source.

The docs app draws the Python API pages from one JSON file. This script writes
it. Griffe reads the package's source and never imports it, so the export needs
no build of the Rust extension::

    uv run --only-group docs python scripts/docs_export.py    # writes docs-app/src/lib/generated/api.json

The export is ``{"names": [...], "objects": {name: {kind, labels, signature,
annotation, value, bases, doc, members: [{name, kind, labels, signature,
annotation, value, doc, members}]}}, "internals": {path: {...}}}``. An exported
type alias is an attribute, and its ``value`` is the type it stands for. A type
of the package that a public signature names must itself be reached by an
exported name, or the export is refused. ``internals`` holds the private
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

A glossary term is written in two files. The page, ``reference/glossary.md``,
holds a second-level heading and under it the description, which stands on its
own and so names the term in its first paragraph. The file beside it,
``reference/glossary.json``, is a list of ``{term, summary, types}`` and holds
no other key: ``summary`` is one sentence of at most 25 words with no link in
it, and ``types`` is a list of names, each an exported name (``Entry``) or a
path inside the package (``paths.split``) that must be in the source. The two
hold the same terms, each once, in the same alphabetical order.

``glossary`` in the export is ``{term: {anchor, summary, types, code,
documentation, related}}``. ``types`` and ``code`` are lists of ``{name, id,
page, public}``: the names the file holds, and every object in the package,
private ones included, whose docstring marks the term with ``:term:``.
``documentation`` is every page outside the reference section that links to
the term, as ``{page, title}``. ``related`` is the terms a description links
to and the terms whose descriptions link to it, in alphabetical order.
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

# The glossary page inside the documentation folder, the file of its terms beside it, and the page's route.
GLOSSARY_PAGE = Path("reference") / "glossary.md"
GLOSSARY_FILE = Path("reference") / "glossary.json"
GLOSSARY_ROUTE = "/reference/glossary"

# The folder of pages for people who change the package; only these pages may pull in a private object.
INTERNAL_PAGES = "maintainers"

# The keys the glossary file holds for a term, and no other.
TERM_KEYS = ("term", "summary", "types")
# The most words a term's summary may have: it is what the site shows where a term is linked.
SUMMARY_WORDS = 25
SAME_PAGE_LINK = re.compile(r"\]\(#([a-z0-9-]+)\)")
PAGE_LINK = re.compile(r"\]\((?P<target>[^)\s#]+)#(?P<anchor>[^)\s]+)\)")

TERM_HEADING = re.compile(r"^## (?P<term>.+?)\s*$")
TERM_ROLE = re.compile(r":term:`(?P<body>[^`]+)`")
CODE_ROLE = re.compile(r":(?:py:)?(?:func|meth|class|data|attr|mod|exc|obj|const):`(?P<body>[^`]+)`")

# A role's body that carries its own wording: "arms <arm>" shows "arms" and points at "arm".
LABELLED = re.compile(r"^(?P<text>.+?)\s*<(?P<target>[^<>]+)>$")

FENCE = re.compile(r"^\s*(```|~~~)")

# Griffe's labels for an attribute the class body assigns, and for one a method assigns to ``self``.
CLASS_ATTRIBUTE = "class-attribute"
INSTANCE_ATTRIBUTE = "instance-attribute"

# The most members a refusal names for one type that is not exported; the rest are counted.
SHOWN_HOLDERS = 3
# How the source assigns a type variable, which is a name in a signature and not a type to import.
TYPE_VARIABLES = ("TypeVar(", "ParamSpec(", "TypeVarTuple(")


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
    public, listing = _public_paths(resolved)
    book = _Book(package, loaded, resolved, public, listing, api, internal, terms)
    _check_signatures(book)
    glossary = _describe_glossary(_written_terms(documentation), documentation, book)
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
    """Each glossary term, case-folded, with the anchor of its heading; empty when there is no glossary.

    A term out of shape is refused here, before any docstring is read against the glossary.
    """
    return {term.name.casefold(): anchor_of(term.name) for term in _written_terms(documentation)}


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


class _Term(NamedTuple):
    """One glossary term: its summary and types from the file, and the lines of its description from the page."""

    name: str
    summary: str
    types: list[str]
    lines: list[str]


def _written_terms(documentation: Path) -> list[_Term]:
    """Each term of the glossary, read from the page and the file beside it and checked; empty when there is neither."""
    page = documentation / GLOSSARY_PAGE
    file = documentation / GLOSSARY_FILE
    sections = _term_sections(page.read_text(encoding="utf-8")) if page.is_file() else []
    entries = _term_entries(file) if file.is_file() else []
    _check_descriptions(sections)
    _check_same_terms([term for term, _ in sections], [entry["term"] for entry in entries])
    return [
        _Term(term, entry["summary"], entry["types"], lines)
        for (term, lines), entry in zip(sections, entries, strict=True)
    ]


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


def _term_entries(file: Path) -> list[dict[str, Any]]:
    """The entries of the glossary file, each checked: a term, its summary and its types, and no other key."""
    try:
        entries = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        msg = f"{file.name} is not JSON: {error}"
        raise ExportError(msg) from error
    if not isinstance(entries, list):
        msg = f"{file.name} holds a list of terms, one object each"
        raise ExportError(msg)
    for entry in entries:
        _check_entry(entry, file.name)
    return entries


def _check_entry(entry: Any, file: str) -> None:
    """Refuse an entry with no term, with a key the file does not hold, or with a summary or types out of shape."""
    if not isinstance(entry, dict) or not isinstance(entry.get("term"), str):
        msg = f"{file} holds an entry with no term: {entry!r}"
        raise ExportError(msg)
    term = entry["term"]
    if sorted(entry) != sorted(TERM_KEYS):
        msg = f"the glossary term {term!r} has the keys {sorted(entry)} in {file}; a term has {list(TERM_KEYS)}"
        raise ExportError(msg)
    summary, types = entry["summary"], entry["types"]
    words = len(summary.split()) if isinstance(summary, str) else 0
    if not words or words > SUMMARY_WORDS or not summary.endswith("."):
        msg = (
            f"the glossary term {term!r} has a summary of {words} words; a summary is one sentence of at most "
            f"{SUMMARY_WORDS} words that ends in a full stop"
        )
        raise ExportError(msg)
    if "](" in summary:
        msg = f"the glossary term {term!r} has a link in its summary; a summary is plain text"
        raise ExportError(msg)
    if not isinstance(types, list) or not all(isinstance(name, str) for name in types):
        msg = f"the glossary term {term!r} has types that are not a list of names"
        raise ExportError(msg)


def _check_descriptions(sections: list[tuple[str, list[str]]]) -> None:
    """Refuse a term the page defines twice, out of order, with no description, or with one that does not name it."""
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
        paragraphs = _paragraphs(lines)
        if not paragraphs:
            msg = f"the glossary term {term!r} has no description under its heading"
            raise ExportError(msg)
        # The description is all the page says of a term, so it opens by saying what the term is.
        if not re.search(rf"\b{re.escape(term)}", paragraphs[0], re.IGNORECASE):
            msg = (
                f"the glossary term {term!r} has a description that does not name it in its first paragraph; "
                "the description stands on its own"
            )
            raise ExportError(msg)


def _check_same_terms(defined: list[str], held: list[str]) -> None:
    """Refuse unless the page and the file hold the same terms, each once and in the same order."""
    name = GLOSSARY_FILE.name
    twice = next((term for term in held if held.count(term) > 1), None)
    if twice is not None:
        msg = f"{name} holds the term {twice!r} twice"
        raise ExportError(msg)
    missing = next((term for term in defined if term not in held), None)
    if missing is not None:
        msg = f"the glossary page defines the term {missing!r}, which {name} does not hold"
        raise ExportError(msg)
    unknown = next((term for term in held if term not in defined), None)
    if unknown is not None:
        msg = f"{name} holds the term {unknown!r}, which the glossary page does not define"
        raise ExportError(msg)
    if held != defined:
        msg = f"{name} holds its terms in another order than the glossary page: {held}, not {defined}"
        raise ExportError(msg)


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
    listing: frozenset[str]
    api: dict[str, list[str]]
    internal: dict[str, list[str]]
    terms: dict[str, str]


def _public_paths(resolved: dict[str, griffe.Object]) -> tuple[dict[str, str], frozenset[str]]:
    """Where each public name is defined, with the name a caller writes, and the modules that list their own names.

    An exported name is public, and so is each name an exported module lists in its ``__all__``. Such a module
    reaches only the names it lists, so the second value says which modules those are.
    """
    public = {target.path: name for name, target in resolved.items()}
    listing = {
        name: target
        for name, target in resolved.items()
        if isinstance(target, griffe.Module) and target.exports is not None
    }
    for name, module in listing.items():
        for member in _public_members(module):
            public.setdefault(member.path, f"{name}.{member.name}")
    return public, frozenset(module.path for module in listing.values())


def _describe_glossary(written: list[_Term], documentation: Path, book: _Book) -> dict[str, dict[str, Any]]:
    """Each term: its summary and types as the file holds them, then what marks it, links to it and is related."""
    names = {anchor_of(term.name): term.name for term in written}
    marked = _marked_by_term(book)
    linking = _linking_pages(documentation, frozenset(names))
    # The other terms each description links to; a term's link to itself relates it to nothing.
    links = {term.name: {names[anchor] for anchor in _linked_terms(term.lines) & set(names)} for term in written}
    return {
        term.name: {
            "anchor": anchor_of(term.name),
            "summary": term.summary,
            "types": [_cite(_cited_target(name, term.name, book), book) for name in term.types],
            "code": marked.get(term.name.casefold(), []),
            "documentation": linking.get(anchor_of(term.name), []),
            "related": sorted(
                (links[term.name] | {other for other, found in links.items() if term.name in found}) - {term.name},
                key=str.casefold,
            ),
        }
        for term in written
    }


def _linked_terms(lines: list[str]) -> set[str]:
    """The anchors a term's lines link to on the glossary page itself."""
    return {anchor for line in lines for anchor in SAME_PAGE_LINK.findall(line)}


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
        above = ".".join(parts[:cut])
        exported = book.public.get(above)
        # A module that lists its own names reaches those names alone, and each is in the book by its own path.
        if exported is None or (cut < len(parts) and above in book.listing):
            continue
        # A page draws the public members of a name. A private member beneath it is on no page.
        if not all(_is_public(part) for part in parts[cut:]):
            break
        return ".".join([exported, *parts[cut:]]), book.api[exported.partition(".")[0]][0], True
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


def _check_signatures(book: _Book) -> None:
    """Refuse when a public signature names a type of the package that no exported name reaches.

    A caller who reads a type on a reference page can import it. A type that an exported module or class
    holds counts as reached, because that page lists it.
    """
    unreached: dict[str, list[str]] = {}
    for name, target in book.resolved.items():
        for holder, annotation in _annotations(name, target):
            for named in _package_types(annotation, book):
                if not _placed(named, book)[2] and holder not in unreached.setdefault(named.path, []):
                    unreached[named.path].append(holder)
    if not unreached:
        return
    problems = []
    for path, holders in sorted(unreached.items()):
        shown = ", ".join(f"{book.package}.{holder}" for holder in holders[:SHOWN_HOLDERS])
        more = f" and {len(holders) - SHOWN_HOLDERS} more" if len(holders) > SHOWN_HOLDERS else ""
        problems.append(f"{path}, named by {shown}{more}")
    msg = f"public signatures name types that {book.package}.__all__ does not export: {'; '.join(problems)}"
    raise ExportError(msg)


def _annotations(name: str, target: griffe.Object) -> Iterator[tuple[str, str | griffe.Expr]]:
    """Each annotation a caller reads under an exported name, with the name of the member that writes it."""
    if isinstance(target, griffe.Function):
        for parameter in target.parameters:
            if parameter.annotation is not None:
                yield name, parameter.annotation
        if target.returns is not None:
            yield name, target.returns
    elif isinstance(target, griffe.Attribute):
        if target.annotation is not None:
            yield name, target.annotation
        # An exported attribute is a type alias, and an alias is its value.
        if "." not in name and target.value is not None:
            yield name, target.value
    elif target.is_class or target.is_module:
        constructor = target.members.get("__init__")
        members = _public_members(target) + ([constructor] if isinstance(constructor, griffe.Function) else [])
        for member in members:
            yield from _annotations(f"{name}.{member.name}", member)


def _package_types(annotation: str | griffe.Expr, book: _Book) -> Iterator[griffe.Object]:
    """The objects of the package that an annotation names. A name that cannot be read is left out."""
    if isinstance(annotation, str):
        return
    prefix = f"{book.package}."
    for part in annotation.iterate(flat=True):
        if not isinstance(part, griffe.ExprName) or not part.canonical_path.startswith(prefix):
            continue
        try:
            found = book.loaded[part.canonical_path.removeprefix(prefix)]
            named = found.final_target if isinstance(found, griffe.Alias) else found
        except (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError):
            continue
        # A type variable stands for the caller's own type, so there is nothing to import.
        if not (isinstance(named, griffe.Attribute) and str(named.value).startswith(TYPE_VARIABLES)):
            yield named


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
    alias = target if isinstance(target, griffe.Attribute) else None
    return {
        "kind": target.kind.value,
        "labels": sorted(target.labels),
        "signature": _signature_of(target),
        "annotation": None if alias is None or alias.annotation is None else str(alias.annotation),
        "value": None if alias is None or alias.value is None else str(alias.value),
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
    """A class's public attributes and functions, or what a module offers, in source order.

    A module that writes its own ``__all__`` offers exactly that list, in the list's order, and a name it
    imported is followed to where it is defined. A module with no list offers what it defines itself.
    """
    if isinstance(target, griffe.Module) and target.exports is not None:
        return [_listed(target, str(name)) for name in target.exports]
    members: list[griffe.Object] = []
    for name, member in target.members.items():
        if isinstance(member, griffe.Alias) or name == "__init__" or not _is_public(name):
            continue
        # A module's special names, such as ``__all__``, say how it is imported, not what it holds.
        if target.is_module and name.startswith("__"):
            continue
        members.append(member)
    return members


def _listed(module: griffe.Module, name: str) -> griffe.Object:
    """The object a module's ``__all__`` names, read through the import that brought it in."""
    try:
        member = module.members[name]
        return member.final_target if isinstance(member, griffe.Alias) else member
    except (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError) as error:
        msg = f"{module.path} lists {name!r} in its __all__, which cannot be read from the source: {error}"
        raise ExportError(msg) from error


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
