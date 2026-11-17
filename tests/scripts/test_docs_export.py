"""The docs export reads the public API from the source, links glossary terms, and refuses a name it cannot place."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "docs_export.py"
_SPEC = importlib.util.spec_from_file_location("docs_export", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
docs_export = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(docs_export)

PARTS = {
    "Types": "- **Types:** none.\n",
    "Producers": "- **Producers:** `things.helper`\n",
    "Consumers": "- **Consumers:** none.\n",
}


def _term(name: str, *, parts: tuple[str, ...] = tuple(PARTS), definition: str = "One plain thing.\n\n") -> str:
    """One glossary term as the page writes it: a heading, a definition, then *parts* in the order given."""
    return f"## {name}\n\n{definition}" + "".join(PARTS.get(part, f"- **{part}:** yes.\n") for part in parts) + "\n"


def _glossary(*terms: str) -> str:
    return "# Glossary\n\nThe words.\n\n" + "".join(terms)


GLOSSARY = _glossary(_term("Arm"), _term("Mount"))

THINGS = '''
"""A module of things."""


class Thing:
    """A thing that sits on a :term:`mount`."""

    zeta: int = 1
    _hidden: int = 2

    def __init__(self, name: str, *, size: int = 0) -> None:
        self.name = name

    def walk(self, depth: int) -> list[str]:
        """Walk the thing."""
        return []

    def _private(self) -> None:
        """Not for callers."""

    def alpha(self) -> None:
        """Comes last in the source and first in the alphabet."""

    def __len__(self) -> int:
        return 0


def helper(path: str) -> bool:
    """Help with a path."""
    return True
'''


def _package(root: Path, *, things: str = THINGS, names: tuple[str, ...] = ("Thing", "helper")) -> Path:
    """A source folder holding one small package, ``pkg``, that exports *names* from ``pkg.things``."""
    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    exported = ", ".join(names)
    (package / "__init__.py").write_text(f"from pkg.things import {exported}\n\n__all__ = {list(names)!r}\n")
    (package / "things.py").write_text(things)
    return root / "src"


def _pages(
    root: Path, pages: dict[str, str], *, glossary: str = GLOSSARY, maintainers: dict[str, str] | None = None
) -> Path:
    """A documentation folder: the glossary, *pages* under ``reference/python-api/``, *maintainers* under its own."""
    documentation = root / "documentation"
    (documentation / "reference" / "python-api").mkdir(parents=True)
    (documentation / "maintainers").mkdir()
    (documentation / "reference" / "glossary.md").write_text(glossary)
    for name, text in pages.items():
        (documentation / "reference" / "python-api" / name).write_text(text)
    for name, text in (maintainers or {}).items():
        (documentation / "maintainers" / name).write_text(text)
    return documentation


def _export(root: Path, *, things: str = THINGS, pages: dict[str, str] | None = None) -> dict[str, Any]:
    source = _package(root, things=things)
    documentation = _pages(root, pages or {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"})
    return docs_export.export(source, documentation, package="pkg")


@pytest.fixture(scope="module")
def real_export() -> dict[str, Any]:
    """The export of the real tree, loaded once: Griffe reads every file under ``src/vfs``."""
    return docs_export.export(REPO / "src", REPO / "documentation")


def test_the_export_holds_exactly_the_names_of_all(real_export: dict[str, Any]) -> None:
    """Reading the names from anywhere but ``__all__``, or dropping one that fails to resolve, breaks the equality."""
    tree = ast.parse((REPO / "src" / "vfs" / "__init__.py").read_text())
    exported = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    )
    assert real_export["names"] == list(exported)
    assert set(real_export["objects"]) == set(exported)


def test_the_export_has_the_documented_shape(tmp_path: Path) -> None:
    """A renamed key, or a missing value written as an absent key and not as null, breaks the app's reader."""
    exported = _export(tmp_path)
    assert set(exported) == {"names", "objects", "internals", "glossary"}
    assert exported["internals"] == {}
    assert list(exported["glossary"]) == ["Arm", "Mount"]
    assert set(exported["glossary"]["Arm"]) == {"anchor", "types", "producers", "consumers"}
    thing = exported["objects"]["Thing"]
    assert set(thing) == {"kind", "labels", "signature", "bases", "doc", "members"}
    assert thing["kind"] == "class"
    assert thing["signature"] == "(name: str, *, size: int = 0) -> None"
    member_keys = {"name", "kind", "labels", "signature", "annotation", "value", "doc", "members"}
    assert all(set(member) == member_keys for member in thing["members"])
    zeta = thing["members"][0]
    assert (zeta["name"], zeta["kind"], zeta["annotation"], zeta["value"], zeta["signature"]) == (
        "zeta",
        "attribute",
        "int",
        "1",
        None,
    )
    helper = exported["objects"]["helper"]
    assert (helper["kind"], helper["signature"], helper["members"]) == ("function", "(path: str) -> bool", [])


def test_the_source_is_read_and_never_imported(tmp_path: Path) -> None:
    """Loading the package by import would run the module's body, and the body raises."""
    exported = _export(tmp_path, things='raise RuntimeError("the module was imported")\n' + THINGS)
    assert exported["names"] == ["Thing", "helper"]
    assert exported["objects"]["helper"]["doc"] == "Help with a path."


def test_members_are_public_and_in_source_order(tmp_path: Path) -> None:
    """Sorting the members, or keeping an underscore-led one or the constructor, changes the list.

    ``name`` is the attribute the constructor assigns: a public attribute, listed where it is assigned.
    """
    members = [member["name"] for member in _export(tmp_path)["objects"]["Thing"]["members"]]
    assert members == ["zeta", "name", "walk", "alpha", "__len__"]


def test_an_attribute_set_in_the_constructor_exports_no_value(tmp_path: Path) -> None:
    """Exporting the right-hand side of ``self.name = name`` would print the parameter's name as a value."""
    members = {member["name"]: member for member in _export(tmp_path)["objects"]["Thing"]["members"]}
    assert (members["name"]["kind"], members["name"]["value"]) == ("attribute", None)
    assert members["zeta"]["value"] == "1"


LABELLED = '''
"""A module of labelled things."""

from dataclasses import dataclass


@dataclass
class Thing:
    """A thing."""

    size: int = 0

    @property
    def area(self) -> int:
        """Its area."""
        return 0

    @classmethod
    def make(cls) -> "Thing":
        """Make one."""
        return cls()

    async def fetch(self) -> None:
        """Fetch it."""

    def plain(self) -> None:
        """Nothing special."""


def helper(path: str) -> bool:
    """Help with a path."""
    return True
'''


def test_labels_say_how_a_name_is_declared(tmp_path: Path) -> None:
    """Dropping the labels leaves a page unable to tell a property from a field, or an async call from a plain one."""
    exported = _export(tmp_path, things=LABELLED)
    thing = exported["objects"]["Thing"]
    assert thing["labels"] == ["dataclass"]
    assert exported["objects"]["helper"]["labels"] == []
    declared = {member["name"]: (member["kind"], member["labels"]) for member in thing["members"]}
    assert declared == {
        "size": ("attribute", ["class-attribute", "instance-attribute"]),
        "area": ("attribute", ["property"]),
        "make": ("function", ["classmethod"]),
        "fetch": ("function", ["async"]),
        "plain": ("function", []),
    }


MODULE_HEAD = (
    'import os\nfrom pathlib import Path\n\nLIMIT: int = 3\n"""The most things one call takes."""\n\n_SECRET = 1\n'
)


def _module_export(root: Path, *, names: tuple[str, ...]) -> dict[str, Any]:
    """The export of a package whose ``things`` module is exported, beside any of its names in *names*."""
    source = _package(root, names=names)
    imports = "".join(f"from pkg.things import {name}\n" for name in names if name != "things")
    (source / "pkg" / "__init__.py").write_text(f"from pkg import things\n{imports}\n__all__ = {list(names)!r}\n")
    (source / "pkg" / "things.py").write_text(MODULE_HEAD + THINGS)
    blocks = "".join(f"\n::: pkg.{name}\n" for name in names)
    documentation = _pages(root, {"things.md": f"# Things\n{blocks}"})
    return docs_export.export(source, documentation, package="pkg")["objects"]


def test_a_module_lists_what_it_defines(tmp_path: Path) -> None:
    """Listing a module's imports, or dropping its own attributes, misstates what the module holds."""
    module = _module_export(tmp_path, names=("things",))["things"]
    assert module["kind"] == "module"
    assert [member["name"] for member in module["members"]] == ["LIMIT", "Thing", "helper"]
    limit = module["members"][0]
    assert (limit["kind"], limit["annotation"], limit["value"], limit["doc"]) == (
        "attribute",
        "int",
        "3",
        "The most things one call takes.",
    )


def test_a_class_only_a_module_lists_carries_its_own_members(tmp_path: Path) -> None:
    """A class no page pulls in by name has no other place for its members; an exported one would list them twice."""
    only_here = _module_export(tmp_path / "only", names=("things",))["things"]
    thing = next(member for member in only_here["members"] if member["name"] == "Thing")
    assert [member["name"] for member in thing["members"]] == ["zeta", "name", "walk", "alpha", "__len__"]
    assert all(member["members"] == [] for member in thing["members"])
    exported_too = _module_export(tmp_path / "both", names=("things", "Thing"))
    thing = next(member for member in exported_too["things"]["members"] if member["name"] == "Thing")
    assert thing["members"] == []
    assert len(exported_too["Thing"]["members"]) == 5


@pytest.mark.parametrize(
    ("marker", "link"),
    [
        (":term:`mount`", "[mount](/reference/glossary#mount)"),
        (":term:`Mount`", "[Mount](/reference/glossary#mount)"),
        (":term:`arms <arm>`", "[arms](/reference/glossary#arm)"),
    ],
)
def test_a_term_marker_becomes_a_glossary_link(tmp_path: Path, marker: str, link: str) -> None:
    """Matching the term by exact case, or showing the target where the marker gives its own words, breaks a leg."""
    things = THINGS.replace("A thing that sits on a :term:`mount`.", f"A thing with {marker} in it.")
    assert _export(tmp_path, things=things)["objects"]["Thing"]["doc"] == f"A thing with {link} in it."


def test_a_term_the_glossary_lacks_refuses_the_export(tmp_path: Path) -> None:
    """Logging the unknown term and writing the file anyway would publish a marker nobody defined."""
    things = THINGS.replace(":term:`mount`", ":term:`mountain`")
    source = _package(tmp_path, things=things)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"})
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, documentation, package="pkg")
    assert "pkg.things.Thing" in str(refusal.value)
    assert "mountain" in str(refusal.value)
    out = tmp_path / "api.json"
    code = docs_export.main(
        ["--source", str(source), "--documentation", str(documentation), "--package", "pkg", "--out", str(out)]
    )
    assert code == 1
    assert not out.exists()


@pytest.mark.parametrize(
    ("glossary", "named"),
    [
        (_glossary(_term("Arm"), _term("Mount", parts=("Types", "Producers"))), ("Mount", "Consumers")),
        (_glossary(_term("Arm", parts=("Producers", "Types", "Consumers")), _term("Mount")), ("Arm",)),
        (_glossary(_term("Arm", parts=("Seen by callers", "In code", "Instead of")), _term("Mount")), ("Arm", "Types")),
        (_glossary(_term("Arm", parts=(*PARTS, "Instead of")), _term("Mount")), ("Arm", "Instead of")),
        (_glossary(_term("Arm", parts=(*PARTS, "Consumers")), _term("Mount")), ("Arm", "Consumers")),
        (_glossary(_term("Arm"), _term("Mount", definition="")), ("Mount", "definition")),
        (_glossary(_term("Mount"), _term("Arm")), ("Arm", "alphabetical")),
        (_glossary(_term("Arm"), _term("arm"), _term("Mount")), ("arm", "twice")),
    ],
    ids=[
        "a-part-missing",
        "parts-out-of-order",
        "the-earlier-parts",
        "an-unknown-part",
        "a-part-twice",
        "no-definition",
        "order",
        "twice",
    ],
)
def test_a_glossary_term_out_of_shape_refuses_the_export(tmp_path: Path, glossary: str, named: tuple[str, ...]) -> None:
    """Reading only the headings lets a term with no code reference, or a part nobody defined, onto the site."""
    source = _package(tmp_path)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"}, glossary=glossary)
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, documentation, package="pkg")
    assert all(name in str(refusal.value) for name in named)


def test_a_heading_inside_a_code_block_is_not_a_term(tmp_path: Path) -> None:
    """Finding headings in the raw text would read a fenced example as a term with no parts."""
    fenced = _term("Arm", definition="One plain thing.\n\n```markdown\n## Not a term\n```\n\n")
    source = _package(tmp_path)
    documentation = _pages(
        tmp_path,
        {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"},
        glossary=_glossary(fenced, _term("Mount")),
    )
    assert docs_export.glossary_terms(documentation) == {"arm": "arm", "mount": "mount"}
    assert docs_export.export(source, documentation, package="pkg")["names"] == ["Thing", "helper"]


@pytest.mark.parametrize(
    ("role", "code"),
    [
        (":func:`helper`", "`helper`"),
        (":meth:`Thing.walk`", "`Thing.walk`"),
        (":class:`Thing`", "`Thing`"),
        (":func:`~pkg.things.helper`", "`helper`"),
    ],
)
def test_a_code_role_becomes_inline_code(tmp_path: Path, role: str, code: str) -> None:
    """Leaving the role as written, or keeping the dotted path a leading tilde asks to drop, breaks a leg."""
    things = THINGS.replace("Help with a path.", f"Help with a path, as {role} does.")
    assert _export(tmp_path, things=things)["objects"]["helper"]["doc"] == f"Help with a path, as {code} does."


@pytest.mark.parametrize(
    ("pages", "named"),
    [
        ({"things.md": "# Things\n\n::: pkg.Thing\n"}, ("pkg.helper",)),
        (
            {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n", "more.md": "# More\n\n::: pkg.helper\n"},
            ("pkg.helper", "things.md", "more.md"),
        ),
        (
            {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n\n::: pkg.secret\n"},
            ("pkg.secret", "things.md"),
        ),
    ],
    ids=["on-no-page", "on-two-pages", "not-exported"],
)
def test_every_exported_name_is_on_exactly_one_page(
    tmp_path: Path, pages: dict[str, str], named: tuple[str, ...]
) -> None:
    """Checking one direction only lets an undocumented name, a doubled one, or a private one through."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _export(tmp_path, pages=pages)
    assert all(name in str(refusal.value) for name in named)


HIDDEN = (
    THINGS
    + '''

def hidden(path: str) -> bool:
    """Not exported; it sits on a :term:`mount`."""
    return True


class _Engine:
    """Not exported either."""

    def turn(self) -> None:
        """Turn once."""
'''
)

API_PAGE = {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"}


def _internal_export(root: Path, maintainers: dict[str, str]) -> dict[str, Any]:
    """The export of a package with two private objects, with *maintainers* as its maintainer pages."""
    source = _package(root, things=HIDDEN)
    documentation = _pages(root, API_PAGE, maintainers=maintainers)
    return docs_export.export(source, documentation, package="pkg")


def test_a_maintainer_page_pulls_in_a_private_object(tmp_path: Path) -> None:
    """Refusing every unexported name leaves the engine's own parts with no page for the glossary to point at."""
    page = "# Internals\n\n::: pkg.things.hidden\n\n::: pkg.things._Engine\n"
    exported = _internal_export(tmp_path, {"internals.md": page})
    assert exported["names"] == ["Thing", "helper"]
    assert set(exported["internals"]) == {"things.hidden", "things._Engine"}
    hidden = exported["internals"]["things.hidden"]
    assert set(hidden) == set(exported["objects"]["helper"])
    assert (hidden["kind"], hidden["signature"]) == ("function", "(path: str) -> bool")
    assert hidden["doc"] == "Not exported; it sits on a [mount](/reference/glossary#mount)."
    assert [member["name"] for member in exported["internals"]["things._Engine"]["members"]] == ["turn"]


@pytest.mark.parametrize(
    ("maintainers", "named"),
    [
        (
            {"internals.md": "# Internals\n\n::: pkg.things.missing\n"},
            ("pkg.things.missing", "maintainers/internals.md"),
        ),
        ({"internals.md": "# Internals\n\n::: pkg.things.Thing\n"}, ("pkg.things.Thing", "public")),
        ({"internals.md": "# Internals\n\n::: pkg.helper\n"}, ("pkg.helper", "public")),
        (
            {"one.md": "# One\n\n::: pkg.things.hidden\n", "two.md": "# Two\n\n::: pkg.things.hidden\n"},
            ("pkg.things.hidden", "maintainers/one.md", "maintainers/two.md"),
        ),
    ],
    ids=["not-in-the-source", "public-by-its-path", "public-by-its-name", "on-two-pages"],
)
def test_a_maintainer_page_holds_only_private_objects_once(
    tmp_path: Path, maintainers: dict[str, str], named: tuple[str, ...]
) -> None:
    """Describing a public object twice, or a name nobody defined, puts a second or an empty entry on the site."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _internal_export(tmp_path, maintainers)
    assert all(name in str(refusal.value) for name in named)


def test_a_private_object_on_an_api_page_is_still_refused(tmp_path: Path) -> None:
    """Letting any page pull in a private object would show it beside the public API as if it were promised."""
    source = _package(tmp_path, things=HIDDEN)
    pages = {"things.md": API_PAGE["things.md"] + "\n::: pkg.things.hidden\n"}
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, _pages(tmp_path, pages), package="pkg")
    assert "pkg.things.hidden" in str(refusal.value)
    assert "__all__" in str(refusal.value)


WIDGETS = '''
"""A module of widgets."""

from collections.abc import Iterable


class Widget:
    """A widget.

    More about it, which is no part of its summary.
    """

    def copy(self) -> "Widget":
        """A copy of this widget."""
        return self

    def bare(self) -> None:
        return None


def make_widget() -> Widget:
    """Make a widget
    out of nothing."""
    return Widget()


def use_widgets(widgets: Iterable[Widget]) -> None:
    """Use every widget."""


def shape(path: str) -> str:
    """Shape a path; not exported."""
    return path
'''

WIDGET_PAGE = "reference/python-api/things.md"


def _cites(*, types: str = "none", producers: str = "none", consumers: str = "none") -> str:
    """A glossary whose one term, Widget, cites the names written in each part."""
    parts = f"- **Types:** {types}\n- **Producers:** {producers}\n- **Consumers:** {consumers}\n"
    return _glossary(f"## Widget\n\nA thing.\n\n{parts}\n")


def _widget_glossary(root: Path, glossary: str, *, maintainers: dict[str, str] | None = None) -> dict[str, Any]:
    """The Widget term as the export describes it, from a package that exports the class and two functions."""
    names = ("Widget", "make_widget", "use_widgets")
    source = _package(root, things=WIDGETS, names=names)
    page = "# Things\n" + "".join(f"\n::: pkg.{name}\n" for name in names)
    documentation = _pages(root, {"things.md": page}, glossary=glossary, maintainers=maintainers)
    return docs_export.export(source, documentation, package="pkg")["glossary"]["Widget"]


def _cited(name: str, summary: str, *, generated: bool, page: str | None = WIDGET_PAGE, public: bool = True) -> dict:
    return {
        "name": name,
        "id": f"pkg.{name}",
        "page": page,
        "summary": summary,
        "public": public,
        "generated": generated,
    }


def test_a_term_lists_its_types_and_what_the_type_hints_show(tmp_path: Path) -> None:
    """Listing only what the page writes by hand leaves every function that returns or takes the type unlisted."""
    widget = _widget_glossary(tmp_path, _cites(types="`Widget`"))
    assert widget == {
        "anchor": "widget",
        "types": [_cited("Widget", "A widget.", generated=False)],
        "producers": [
            _cited("Widget.copy", "A copy of this widget.", generated=True),
            _cited("make_widget", "Make a widget out of nothing.", generated=True),
        ],
        "consumers": [_cited("use_widgets", "Use every widget.", generated=True)],
    }


def test_a_name_written_by_hand_keeps_its_side(tmp_path: Path) -> None:
    """Trusting the hint over the page lists a function that returns the thing it removes as a producer of it."""
    widget = _widget_glossary(tmp_path, _cites(types="`Widget`", consumers="`make_widget`"))
    assert [cited["name"] for cited in widget["producers"]] == ["Widget.copy"]
    assert widget["consumers"] == [
        _cited("make_widget", "Make a widget out of nothing.", generated=False),
        _cited("use_widgets", "Use every widget.", generated=True),
    ]


def test_a_term_with_no_type_lists_what_the_page_names(tmp_path: Path) -> None:
    """A thing that is a plain string has no hint to find it by, so its functions are the ones the page names."""
    widget = _widget_glossary(tmp_path, _cites(producers="`things.shape`", consumers="`make_widget`, `use_widgets`"))
    assert widget["types"] == []
    assert widget["producers"] == [
        _cited("things.shape", "Shape a path; not exported.", generated=False, page=None, public=False)
    ]
    assert [cited["name"] for cited in widget["consumers"]] == ["make_widget", "use_widgets"]


def test_a_private_name_links_to_the_maintainer_page_that_pulls_it_in(tmp_path: Path) -> None:
    """Leaving the page out gives the site a private name with nowhere to send the reader."""
    page = {"internals.md": "# Internals\n\n::: pkg.things.shape\n"}
    widget = _widget_glossary(tmp_path, _cites(types="`Widget`", producers="`things.shape`"), maintainers=page)
    assert widget["producers"][0] == _cited(
        "things.shape", "Shape a path; not exported.", generated=False, page="maintainers/internals.md", public=False
    )


def test_a_public_object_named_by_its_path_is_cited_by_its_public_name(tmp_path: Path) -> None:
    """Citing where the object is defined would link an exported class to no page."""
    widget = _widget_glossary(tmp_path, _cites(types="`things.Widget`", producers="`things.Widget.copy`"))
    assert widget["types"] == [_cited("Widget", "A widget.", generated=False)]
    assert widget["producers"][0] == _cited("Widget.copy", "A copy of this widget.", generated=False)


@pytest.mark.parametrize(
    ("glossary", "named"),
    [
        (_cites(types="`Widget`", producers="`make_gadget`"), ("Widget", "make_gadget")),
        (_cites(types="`Widget.melt`"), ("Widget", "Widget.melt")),
        (_cites(), ("Widget", "names no")),
        (_cites(types="`Widget`", consumers="`Widget.bare`"), ("Widget", "Widget.bare", "docstring")),
    ],
    ids=["a-name-not-in-the-source", "a-member-not-in-the-class", "nothing-cited", "a-name-with-no-docstring"],
)
def test_a_term_that_cites_nothing_real_refuses_the_export(
    tmp_path: Path, glossary: str, named: tuple[str, ...]
) -> None:
    """Printing a name the code no longer has leaves the glossary pointing at nothing after a rename."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _widget_glossary(tmp_path, glossary)
    assert all(name in str(refusal.value) for name in named)


def test_the_real_glossary_cites_only_what_exists(real_export: dict[str, Any]) -> None:
    """A term of the real page with no name under any part, or a name with no summary, shows an empty row."""
    for term, parts in real_export["glossary"].items():
        cited = [*parts["types"], *parts["producers"], *parts["consumers"]]
        assert cited, term
        assert all(entry["summary"] for entry in cited), term


def test_the_command_writes_the_export_as_json(tmp_path: Path) -> None:
    """Writing anything but the export's own JSON to the path the app reads leaves the app with no API."""
    source = _package(tmp_path)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"})
    out = tmp_path / "generated" / "api.json"
    code = docs_export.main(
        ["--source", str(source), "--documentation", str(documentation), "--package", "pkg", "--out", str(out)]
    )
    assert code == 0
    assert json.loads(out.read_text()) == docs_export.export(source, documentation, package="pkg")
