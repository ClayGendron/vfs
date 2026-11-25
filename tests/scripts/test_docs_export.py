"""The docs export reads the public API from the source, links glossary terms, and refuses a name it cannot place."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "docs_export.py"
_SPEC = importlib.util.spec_from_file_location("docs_export", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
docs_export = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(docs_export)


def _term(name: str, *, description: str | None = None) -> str:
    """One glossary term as the page writes it: a heading, then its description."""
    described = f"The {name.lower()} is one plain thing, and more.\n\n" if description is None else description
    return f"## {name}\n\n{described}"


def _entry(name: str, *, summary: str = "One plain thing.", types: tuple[str, ...] = ()) -> dict[str, Any]:
    """One glossary term as ``glossary.json`` holds it: its name, its one sentence and its types."""
    return {"term": name, "summary": summary, "types": list(types)}


def _glossary(*terms: str) -> str:
    return "# Glossary\n\nThe words.\n\n" + "".join(terms)


GLOSSARY = _glossary(_term("Arm"), _term("Mount"))
TERMS = [_entry("Arm"), _entry("Mount")]

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
    root: Path,
    pages: dict[str, str],
    *,
    glossary: str = GLOSSARY,
    terms: Any = TERMS,
    maintainers: dict[str, str] | None = None,
    others: dict[str, str] | None = None,
) -> Path:
    """A documentation folder: the glossary, *pages* under ``reference/python-api/``, *maintainers* under its own.

    *terms* is what ``glossary.json`` holds, and None writes no such file. *others* are pages by their path
    inside the folder, such as ``tutorials/first.md``.
    """
    documentation = root / "documentation"
    (documentation / "reference" / "python-api").mkdir(parents=True)
    (documentation / "maintainers").mkdir()
    (documentation / "reference" / "glossary.md").write_text(glossary)
    if terms is not None:
        (documentation / "reference" / "glossary.json").write_text(json.dumps(terms))
    for name, text in pages.items():
        (documentation / "reference" / "python-api" / name).write_text(text)
    for name, text in (maintainers or {}).items():
        (documentation / "maintainers" / name).write_text(text)
    for name, text in (others or {}).items():
        (documentation / name).parent.mkdir(parents=True, exist_ok=True)
        (documentation / name).write_text(text)
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
    term_keys = {"anchor", "summary", "types", "code", "documentation", "related"}
    assert all(set(term) == term_keys for term in exported["glossary"].values())
    thing = exported["objects"]["Thing"]
    assert set(thing) == {"kind", "labels", "signature", "annotation", "value", "bases", "doc", "members"}
    assert thing["kind"] == "class"
    assert thing["signature"] == "(name: str, *, size: int = 0) -> None"
    assert (thing["annotation"], thing["value"]) == (None, None)
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


TYPE_VARIABLE = 'from typing import TypeVar\n\nT = TypeVar("T")'

GEARS = '''
"""A module of gears."""

from typing import Literal

{type_variable}

Size = Literal["small", "large"]
"""How big a gear is."""


class Gear:
    """A gear."""


class Tooth:
    """A tooth of a gear."""


Part = Gear | Tooth
"""A part of a machine."""
'''

FITTED = '''
"""A module of things."""

from pathlib import Path

from pkg.gears import Gear, Size, T


class Thing:
    """A thing."""

    spare: Gear | None = None

    def __init__(self, gear: Gear) -> None:
        self.gear = gear

    def fit(self, where: Path, size: Size = "small") -> list[Gear]:
        """Fit a gear."""
        return []

    def pick(self, item: T) -> T:
        """Hand an item back."""
        return item

    def _grind(self, gear: Gear) -> None:
        """Not for callers."""
'''


def _fitted_export(root: Path, *, names: tuple[str, ...], type_variable: str = TYPE_VARIABLE) -> dict[str, Any]:
    """The export of a package whose ``Thing`` names two types of ``pkg.gears`` and ``T`` in its signatures."""
    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    modules = [name for name in names if name == "gears"]
    gears = [name for name in names if name in ("Gear", "Size", "Part", "Tooth")]
    imports = "from pkg.things import Thing\n"
    imports += "from pkg import gears\n" if modules else ""
    imports += f"from pkg.gears import {', '.join(gears)}\n" if gears else ""
    (package / "__init__.py").write_text(f"{imports}\n__all__ = {list(names)!r}\n")
    (package / "things.py").write_text(FITTED)
    (package / "gears.py").write_text(GEARS.format(type_variable=type_variable))
    blocks = "".join(f"\n::: pkg.{name}\n" for name in names)
    documentation = _pages(root, {"things.md": f"# Things\n{blocks}"})
    return docs_export.export(root / "src", documentation, package="pkg")


def test_a_type_a_public_signature_names_is_exported(tmp_path: Path) -> None:
    """A caller who reads a type on a reference page can import it; a private method's types are its own."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _fitted_export(tmp_path / "neither", names=("Thing",))
    message = str(refusal.value)
    assert "pkg.gears.Gear" in message and "pkg.gears.Size" in message
    assert "Thing.fit" in message and "Thing.spare" in message and "Thing.__init__" in message
    assert "_grind" not in message and "Path" not in message
    with pytest.raises(docs_export.ExportError, match=r"pkg\.gears\.Size") as refusal:
        _fitted_export(tmp_path / "one", names=("Thing", "Gear"))
    assert "pkg.gears.Gear" not in str(refusal.value)
    assert set(_fitted_export(tmp_path / "both", names=("Thing", "Gear", "Size"))["objects"]) == {
        "Thing",
        "Gear",
        "Size",
    }


@pytest.mark.parametrize(
    ("type_variable", "also_named"),
    [
        (TYPE_VARIABLE, []),
        ('import typing\n\nT = typing.TypeVar("T")', []),
        ('from typing import ParamSpec\n\nT = ParamSpec("T")', []),
        ('import typing_extensions\n\nT = typing_extensions.TypeVarTuple("T")', []),
        ('from typing import ParamSpec\n\nT = ParamSpec("P").args', ["pkg.gears.T"]),
    ],
    ids=["TypeVar", "typing.TypeVar", "ParamSpec", "TypeVarTuple", "built-from-a-ParamSpec"],
)
def test_a_type_variable_is_not_a_type_to_export(tmp_path: Path, type_variable: str, also_named: list[str]) -> None:
    """A type variable stands for the caller's own type, so a signature that names one names nothing to import.

    What the value is decides, however the call is spelled, and not how its text begins.
    """
    with pytest.raises(docs_export.ExportError) as refusal:
        _fitted_export(tmp_path, names=("Thing",), type_variable=type_variable)
    named = re.findall(r"(pkg\.gears\.\w+), named by", str(refusal.value))
    assert sorted(named) == ["pkg.gears.Gear", "pkg.gears.Size", *also_named]


def test_an_exported_type_alias_names_what_its_value_names(tmp_path: Path) -> None:
    """An alias is its value: a caller who can import ``Part`` and not ``Tooth`` cannot build one."""
    with pytest.raises(docs_export.ExportError, match=r"pkg\.gears\.Tooth, named by pkg\.Part"):
        _fitted_export(tmp_path / "alias", names=("Thing", "Gear", "Size", "Part"))
    whole = _fitted_export(tmp_path / "whole", names=("Thing", "Gear", "Size", "Part", "Tooth"))
    assert set(whole["objects"]) == {"Thing", "Gear", "Size", "Part", "Tooth"}
    part = whole["objects"]["Part"]
    assert (part["kind"], part["annotation"], part["value"], part["doc"]) == (
        "attribute",
        None,
        "Gear | Tooth",
        "A part of a machine.",
    )


def test_a_type_an_exported_module_holds_is_public(tmp_path: Path) -> None:
    """A module's page lists what the module defines, so its types can be imported from it."""
    assert set(_fitted_export(tmp_path, names=("Thing", "gears"))["objects"]) == {"Thing", "gears"}


KIT_PARTS = '''
"""The parts of a kit."""


class Bolt:
    """A bolt."""

    length: int = 1


class Nut:
    """A nut."""


class Spare:
    """A part the kit does not list."""
'''

KIT = '''
"""A kit of parts."""

from pkg.kit.parts import Bolt, Nut, Spare

__all__ = ["Nut", "Bolt"]
'''

HOLDER = '''
"""A module of things."""

from pkg.kit import Bolt, Spare


class Thing:
    """A thing."""

    def hold(self, bolt: Bolt) -> None:
        """Hold a bolt."""
'''

KEEPS_A_SPARE = '''
    def keep(self, spare: Spare) -> None:
        """Keep a spare."""
'''


def _kit_export(root: Path, *, things: str = HOLDER) -> dict[str, Any]:
    """The export of a package that exports ``Thing`` and ``kit``, a package that lists two of its three parts."""
    package = root / "src" / "pkg"
    (package / "kit").mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from pkg import kit\nfrom pkg.things import Thing\n\n__all__ = ['Thing', 'kit']\n"
    )
    (package / "things.py").write_text(things)
    (package / "kit" / "__init__.py").write_text(KIT)
    (package / "kit" / "parts.py").write_text(KIT_PARTS)
    documentation = _pages(root, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.kit\n"})
    return docs_export.export(root / "src", documentation, package="pkg")


def test_a_module_with_its_own_list_shows_that_list(tmp_path: Path) -> None:
    """A package's ``__all__`` is what it offers: its page follows the re-exports, in the list's order."""
    kit = _kit_export(tmp_path)["objects"]["kit"]
    assert [member["name"] for member in kit["members"]] == ["Nut", "Bolt"]
    bolt = kit["members"][1]
    assert (bolt["kind"], bolt["doc"]) == ("class", "A bolt.")
    assert [field["name"] for field in bolt["members"]] == ["length"]


def test_a_type_a_module_does_not_list_is_not_reached_through_it(tmp_path: Path) -> None:
    """A name under an exported package that the package leaves out of ``__all__`` is not public."""
    with pytest.raises(docs_export.ExportError, match=r"pkg\.kit\.parts\.Spare, named by pkg\.Thing\.keep"):
        _kit_export(tmp_path, things=HOLDER + KEEPS_A_SPARE)


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
        (_glossary(_term("Arm"), _term("Mount", description="")), ("Mount", "no description")),
        (_glossary(_term("Arm"), _term("Mount", description="It has no content.\n\n")), ("Mount", "stands on its own")),
        (_glossary(_term("Mount"), _term("Arm")), ("Arm", "alphabetical")),
        (_glossary(_term("Arm"), _term("arm"), _term("Mount")), ("arm", "twice")),
    ],
    ids=["no-description", "a-description-that-does-not-name-the-term", "order", "twice"],
)
def test_a_description_out_of_shape_refuses_the_export(tmp_path: Path, glossary: str, named: tuple[str, ...]) -> None:
    """Reading only the headings lets a term with nothing under it, or one that leans on another line, onto the site."""
    source = _package(tmp_path)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"}, glossary=glossary)
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, documentation, package="pkg")
    assert all(name in str(refusal.value) for name in named)


@pytest.mark.parametrize(
    ("terms", "named"),
    [
        ({"Arm": "One plain thing."}, ("glossary.json", "list")),
        (["Arm", "Mount"], ("glossary.json", "no term")),
        ([{**_entry("Arm"), "avoid": ["limb"]}, _entry("Mount")], ("Arm", "avoid")),
        ([{"term": "Arm", "summary": "One plain thing."}, _entry("Mount")], ("Arm", "keys")),
        ([_entry("Arm", summary=" ".join(["word"] * 25) + " more."), _entry("Mount")], ("Arm", "26 words")),
        ([_entry("Arm", summary="One plain thing"), _entry("Mount")], ("Arm", "full stop")),
        ([_entry("Arm", summary="Part of a [mount](#mount)."), _entry("Mount")], ("Arm", "link")),
        ([{**_entry("Arm"), "types": "Thing"}, _entry("Mount")], ("Arm", "list of names")),
    ],
    ids=[
        "not-a-list",
        "an-entry-with-no-term",
        "an-unknown-key",
        "a-missing-key",
        "a-summary-past-25-words",
        "a-summary-with-no-full-stop",
        "a-summary-with-a-link",
        "types-that-are-not-a-list",
    ],
)
def test_a_term_entry_out_of_shape_refuses_the_export(tmp_path: Path, terms: Any, named: tuple[str, ...]) -> None:
    """Passing the file through unread puts a key nobody defined, or a summary too long for a link, on the site."""
    source = _package(tmp_path)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"}, terms=terms)
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, documentation, package="pkg")
    assert all(name in str(refusal.value) for name in named)


@pytest.mark.parametrize(
    ("terms", "named"),
    [
        ([_entry("Arm")], ("Mount", "glossary.json does not hold")),
        (None, ("Arm", "glossary.json does not hold")),
        ([_entry("Arm"), _entry("Gear"), _entry("Mount")], ("Gear", "does not define")),
        ([_entry("Mount"), _entry("Arm")], ("glossary.json", "order")),
        ([_entry("Arm"), _entry("Arm"), _entry("Mount")], ("Arm", "twice")),
    ],
    ids=["a-term-only-on-the-page", "no-file", "a-term-only-in-the-file", "another-order", "twice-in-the-file"],
)
def test_the_page_and_the_file_hold_the_same_terms(tmp_path: Path, terms: Any, named: tuple[str, ...]) -> None:
    """Pairing the two by position, or by the names they share, shows a term with another term's summary or none."""
    source = _package(tmp_path)
    documentation = _pages(tmp_path, {"things.md": "# Things\n\n::: pkg.Thing\n\n::: pkg.helper\n"}, terms=terms)
    with pytest.raises(docs_export.ExportError) as refusal:
        docs_export.export(source, documentation, package="pkg")
    assert all(name in str(refusal.value) for name in named)


def test_a_heading_inside_a_code_block_is_not_a_term(tmp_path: Path) -> None:
    """Finding headings in the raw text would read a fenced example as a term with no parts."""
    fenced = _term("Arm", description="An arm is more than that.\n\n```markdown\n## Not a term\n```\n\n")
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


class Widget:
    """A :term:`widget` with a handle."""

    def copy(self) -> "Widget":
        """A copy of this :term:`widget`, and of every :term:`widget` under it."""
        return self


def make_widget() -> Widget:
    """Make one."""
    return Widget()


def shape(path: str) -> str:
    """Shape the path of a :term:`widget`; not exported."""
    return path
'''

WIDGET_PAGE = "reference/python-api/things.md"


COG = "## Cog\n\nA cog turns a [gadget](#gadget).\n\n"
GADGET = "## Gadget\n\nA gadget is a thing that holds a [widget](#widget).\n\nMore about gadgets.\n\n"

LINKING_PAGES = {
    "get-started.md": (
        "# Get Started\n\nA [widget](reference/glossary.md#widget), "
        "and a [widget](reference/glossary.md#widget) again.\n"
    ),
    "tutorials/first.md": (
        "# First Steps\n\nA [gadget](../reference/glossary.md#gadget) "
        "holds a [widget](../reference/glossary.md#widget).\n"
    ),
    "how-to/fenced.md": "# Fenced\n\n```markdown\n[widget](../reference/glossary.md#widget)\n```\n",
    "reference/widgets.md": "# Widgets\n\nSee [widget](glossary.md#widget).\n",
}


def _widget_export(
    root: Path, *, types: tuple[str, ...] = (), things: str = WIDGETS, maintainers: dict[str, str] | None = None
) -> dict[str, Any]:
    """The glossary of a package that exports ``Widget`` and ``make_widget``, with the terms Cog, Gadget and Widget."""
    names = ("Widget", "make_widget")
    source = _package(root, things=things, names=names)
    page = "# Things\n" + "".join(f"\n::: pkg.{name}\n" for name in names)
    widget = _term("Widget", description="A widget is small, and a [widget](#widget) links to itself.\n\n")
    documentation = _pages(
        root,
        {"things.md": page},
        glossary=_glossary(COG, GADGET, widget),
        terms=[_entry("Cog"), _entry("Gadget"), _entry("Widget", summary="A small thing with a handle.", types=types)],
        maintainers=maintainers,
        others=LINKING_PAGES,
    )
    return docs_export.export(source, documentation, package="pkg")["glossary"]


def _cited(name: str, *, page: str | None = WIDGET_PAGE, public: bool = True) -> dict[str, Any]:
    return {"name": name, "id": f"pkg.{name}", "page": page, "public": public}


def test_a_term_carries_its_summary_and_its_types_from_the_file(tmp_path: Path) -> None:
    """Dropping the summary leaves a linked term with nothing to show on hover; dropping the types, no class."""
    widget = _widget_export(tmp_path, types=("Widget",))["Widget"]
    assert (widget["anchor"], widget["summary"]) == ("widget", "A small thing with a handle.")
    assert widget["types"] == [_cited("Widget")]


def test_code_is_every_docstring_that_marks_the_term(tmp_path: Path) -> None:
    """Reading only exported docstrings, or listing one twice for two markers, misstates where the term is used."""
    glossary = _widget_export(tmp_path)
    assert glossary["Widget"]["code"] == [
        _cited("Widget"),
        _cited("Widget.copy"),
        _cited("things.shape", page=None, public=False),
    ]
    assert glossary["Gadget"]["code"] == []


PRIVATE_METHOD = '''
    def _polish(self) -> None:
        """Polish this :term:`widget`."""
'''


def test_a_private_member_of_a_public_class_is_cited_as_private(tmp_path: Path) -> None:
    """A reference page does not draw a private method, so a row that links to one there links to nothing."""
    things = WIDGETS.replace("\n\ndef make_widget", PRIVATE_METHOD + "\n\ndef make_widget")
    code = _widget_export(tmp_path, things=things)["Widget"]["code"]
    assert code == [
        _cited("Widget"),
        _cited("Widget.copy"),
        _cited("things.Widget._polish", page=None, public=False),
        _cited("things.shape", page=None, public=False),
    ]


def test_documentation_is_every_page_outside_reference_that_links_the_term(tmp_path: Path) -> None:
    """Counting a reference page, a link in a code block, or a page twice for two links puts a wrong row on the term."""
    glossary = _widget_export(tmp_path)
    assert glossary["Widget"]["documentation"] == [
        {"page": "get-started.md", "title": "Get Started"},
        {"page": "tutorials/first.md", "title": "First Steps"},
    ]
    assert glossary["Gadget"]["documentation"] == [{"page": "tutorials/first.md", "title": "First Steps"}]


def test_related_terms_are_both_directions_of_a_link_in_alphabetical_order(tmp_path: Path) -> None:
    """Counting a term's link to itself, reading one direction only, or listing the linked-to terms first, breaks a leg.

    Gadget links to Widget and is linked from Cog: the terms it links to first would read Widget, then Cog.
    """
    glossary = _widget_export(tmp_path)
    assert glossary["Cog"]["related"] == ["Gadget"]
    assert glossary["Gadget"]["related"] == ["Cog", "Widget"]
    assert glossary["Widget"]["related"] == ["Gadget"]


def test_a_type_is_named_by_its_public_name_and_placed_on_its_page(tmp_path: Path) -> None:
    """Citing where an exported class is defined links it to no page; a private name has only a maintainer page."""
    by_path = _widget_export(tmp_path / "path", types=("things.Widget",))["Widget"]
    assert by_path["types"] == [_cited("Widget")]
    unplaced = _widget_export(tmp_path / "unplaced", types=("Widget", "things.shape"))["Widget"]
    assert unplaced["types"] == [_cited("Widget"), _cited("things.shape", page=None, public=False)]
    page = {"internals.md": "# Internals\n\n::: pkg.things.shape\n"}
    placed = _widget_export(tmp_path / "placed", types=("things.shape",), maintainers=page)["Widget"]
    assert placed["types"] == [_cited("things.shape", page="maintainers/internals.md", public=False)]


@pytest.mark.parametrize("name", ["Gizmo", "Widget.melt"], ids=["not-in-the-source", "not-in-the-class"])
def test_a_type_the_code_does_not_have_refuses_the_export(tmp_path: Path, name: str) -> None:
    """Printing a name the code no longer has leaves the glossary pointing at nothing after a rename."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _widget_export(tmp_path, types=(name,))
    assert "Widget" in str(refusal.value)
    assert name in str(refusal.value)


def test_a_private_docstring_that_marks_an_unknown_term_refuses_the_export(tmp_path: Path) -> None:
    """Checking exported docstrings only lets a marker nobody defined sit in the code until its object is exported."""
    with pytest.raises(docs_export.ExportError) as refusal:
        _widget_export(tmp_path, things=WIDGETS.replace("path of a :term:`widget`", "path of a :term:`sprocket`"))
    assert "pkg.things.shape" in str(refusal.value)
    assert "sprocket" in str(refusal.value)


def test_the_real_glossary_exports(real_export: dict[str, Any]) -> None:
    """A real term whose summary or type did not survive the export shows an empty entry on the site."""
    terms = ["Arm", "Entry", "Interrupt", "Job", "Kernel", "Mount", "Policy", "Session", "Stamp", "Step", "Storage"]
    assert list(real_export["glossary"]) == [*terms, "Turn", "Vid"]
    assert all(term["summary"] for term in real_export["glossary"].values())
    assert real_export["glossary"]["Entry"]["related"] == ["Arm", "Mount", "Storage", "Vid"]
    assert real_export["glossary"]["Mount"]["related"] == ["Entry", "Kernel", "Storage"]
    assert [cited["name"] for cited in real_export["glossary"]["Entry"]["types"]] == ["Entry"]


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
