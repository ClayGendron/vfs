"""The smallest stdlib-only pytest test over the import graph of src/vfs.

One `ast` walk over every module under src/vfs yields the module-level import
graph (importer -> imported vfs module, with file, line and whether the import
sits under `if TYPE_CHECKING:`). The one test here asserts the contract the
brief names: no module outside `vfs.storage.backends.database` imports from it,
except the modules the allowlist names. Run as a script it also prints the
graph summary and the size baseline (five largest modules, top-level def/class
counts), which the pytest test does not need.

Run from the vfs checkout:
    uv run pytest context/research/studies/.../experiments/01-.../test_import_direction.py -p no:cacheprovider -q
    uv run python   context/research/studies/.../experiments/01-.../test_import_direction.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[6]
SRC = REPO / "src" / "vfs"
PACKAGE = "vfs"

# The contract under test: who may import from the database adapter package.
PROTECTED = "vfs.storage.backends.database"
ALLOWED_IMPORTERS = frozenset({"vfs.storage.backends"})  # the backends package re-exports its adapters

# The declared layer order, bottom first; a module in a lower layer never imports a higher one.
LAYERS = (
    ("vfs.paths", "vfs.models", "vfs.results", "vfs.native"),
    ("vfs.pattern_matching",),
    ("vfs.storage.protocol",),
    ("vfs.storage.backends.database",),
    ("vfs.base",),
    ("vfs.session", "vfs.sync"),
)


class Edge(NamedTuple):
    importer: str
    imported: str
    path: Path
    line: int
    type_checking: bool


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_type_checking_test(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _resolve_relative(importer: str, is_package: bool, level: int, module: str | None) -> str:
    base = importer.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join(base + ([module] if module else []))


def module_edges(path: Path) -> list[Edge]:
    """Every module-level import of a vfs module made by `path`, with its line and TYPE_CHECKING flag."""
    importer = module_name(path)
    is_package = path.name == "__init__.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    edges: list[Edge] = []

    def visit(nodes: list[ast.stmt], type_checking: bool) -> None:
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == PACKAGE or alias.name.startswith(PACKAGE + "."):
                        edges.append(Edge(importer, alias.name, path, node.lineno, type_checking))
            elif isinstance(node, ast.ImportFrom):
                target = (
                    _resolve_relative(importer, is_package, node.level, node.module)
                    if node.level
                    else (node.module or "")
                )
                if target == PACKAGE or target.startswith(PACKAGE + "."):
                    edges.append(Edge(importer, target, path, node.lineno, type_checking))
            elif isinstance(node, ast.If):
                guarded = type_checking or _is_type_checking_test(node.test)
                visit(node.body, guarded)
                visit(node.orelse, type_checking)
            elif isinstance(node, (ast.Try, ast.With)):
                visit(node.body, type_checking)
                for handler in getattr(node, "handlers", []):
                    visit(handler.body, type_checking)

    visit(tree.body, False)
    return edges


def import_graph() -> list[Edge]:
    return [edge for path in sorted(SRC.rglob("*.py")) for edge in module_edges(path)]


def _inside(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def offending_imports(edges: list[Edge]) -> list[Edge]:
    """Imports from PROTECTED by a module outside it and outside the allowlist."""
    return [
        e
        for e in edges
        if _inside(e.imported, PROTECTED)
        and not _inside(e.importer, PROTECTED)
        and not any(_inside(e.importer, ok) for ok in ALLOWED_IMPORTERS)
    ]


def _layer_of(module: str) -> int | None:
    for index, members in enumerate(LAYERS):
        if any(_inside(module, member) for member in members):
            return index
    return None


def upward_imports(edges: list[Edge]) -> list[Edge]:
    """Imports where a lower layer reaches a higher one (the layers contract, direct edges only)."""
    hits = []
    for e in edges:
        low, high = _layer_of(e.importer), _layer_of(e.imported)
        if low is not None and high is not None and high > low:
            hits.append(e)
    return hits


def describe(e: Edge) -> str:
    guard = " (TYPE_CHECKING)" if e.type_checking else ""
    return f"{e.path.relative_to(REPO)}:{e.line}: {e.importer} imports {e.imported}{guard}"


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------


def test_only_the_backends_package_imports_the_database_adapter() -> None:
    hits = offending_imports(import_graph())
    assert not hits, "\n".join(describe(e) for e in hits)


def test_no_layer_imports_a_layer_above_it() -> None:
    hits = upward_imports(import_graph())
    assert not hits, "\n".join(describe(e) for e in hits)


# ---------------------------------------------------------------------------
# The size baseline, from the same walk
# ---------------------------------------------------------------------------


class Size(NamedTuple):
    module: str
    lines: int
    top_level: int


def sizes() -> list[Size]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text()
        tree = ast.parse(text)
        top = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in tree.body)
        out.append(Size(module_name(path), len(text.splitlines()), top))
    return sorted(out, key=lambda s: -s.lines)


if __name__ == "__main__":
    edges = import_graph()
    modules = sorted(SRC.rglob("*.py"))
    print(f"modules under src/vfs: {len(modules)}")
    print(f"module-level vfs-internal import edges: {len(edges)}")
    print(f"  of which under TYPE_CHECKING: {sum(e.type_checking for e in edges)}")
    print()
    print(f"imports from {PROTECTED} by modules outside it (allowlist: {sorted(ALLOWED_IMPORTERS)}):")
    hits = offending_imports(edges)
    for e in hits:
        print("  " + describe(e))
    print(f"  total: {len(hits)}  (runtime: {sum(not e.type_checking for e in hits)}, TYPE_CHECKING: {sum(e.type_checking for e in hits)})")
    print()
    print("imports from a lower declared layer to a higher one:")
    ups = upward_imports(edges)
    for e in ups:
        print("  " + describe(e))
    print(f"  total: {len(ups)}")
    print()
    print("five largest modules by line count (top-level def/class statements):")
    for s in sizes()[:5]:
        print(f"  {s.lines:6d} lines  {s.top_level:3d} top-level defs/classes  {s.module}")
    sys.exit(0)
