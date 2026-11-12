"""The shape of the code and the tooling the process relies on."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import TYPE_CHECKING, NamedTuple

from tests.lint.shapes import REPO

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

SRC = REPO / "src" / "vfs"
CRATE = REPO / "crates" / "vfs-core" / "src"
STANDARDS = REPO / "context" / "standards"
SKILLS = REPO / ".claude" / "skills"
SECURITY_SKILL = SKILLS / "security-audit"
SKILLS_LOCK = REPO / "skills-lock.json"
LINT_WORKFLOW = REPO / ".github" / "workflows" / "lint.yml"

DOCUMENT_CITATION = re.compile(r"\b(spec|ADR|story) [0-9]{3}\b")
# vfs's own SHA-256 over the installed skill folder: sorted relative paths and bytes.
SECURITY_SKILL_SHA256 = "ac796659de231c3ab76f6ee012836072bdc82928fb019199925c9062800e16c1"


# The database adapter, and the only modules outside it that may import from it:
# the public export, the backends package's re-export, and the in-memory storage built on it.
ADAPTER = "vfs.storage.backends.database"
ADAPTER_IMPORTERS = frozenset({"vfs", "vfs.storage.backends", "vfs.storage.backends.memory"})

# The modules that import the standard library only, and the layers that sit beneath vfs.offload.
BOTTOM_MODULES = ("vfs.deadline", "vfs.batching")
OFFLOAD = "vfs.offload"
BENEATH_OFFLOAD = ("vfs.pattern_matching", "vfs.results")

# The only modules that read the monotonic clock: the deadline's, and the renderers timing their own work.
CLOCK_READERS = frozenset(
    {"deadline.py", *(f"rendering/{name}.py" for name in ("docx", "markdown", "pdf", "pptx", "xlsx"))}
)


def folder_sha256(root: Path) -> str:
    """One hash over a folder: each file's relative path and bytes, in sorted order, dotfiles left out."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class ImportEdge(NamedTuple):
    """One import of a ``vfs`` module by a module of the package, and where it is written."""

    importer: str
    imported: str
    path: str
    line: int
    type_checking: bool


def import_edges(root: Path = SRC) -> list[ImportEdge]:
    """The package's import graph: every import of a ``vfs`` module in the tree under *root*.

    *root* is the package folder (``.../vfs``). Imports under ``if
    TYPE_CHECKING:`` are edges too, flagged. ``from pkg import name`` is an
    edge to ``pkg.name`` when that is a module of the tree and to ``pkg``
    otherwise; the compiled extension, ``from vfs import _native``, is no
    edge to the package root. The walk reads import statements alone: a
    module loaded through ``importlib`` or ``__import__``, an attribute
    reached through an allowed package, and a name an allowed importer
    re-exports are not edges.
    """
    files = {_module_name(path, root): path for path in sorted(root.rglob("*.py"))}
    edges: list[ImportEdge] = []
    for importer, path in files.items():
        shown = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path.relative_to(root.parent))
        package = importer if path.name == "__init__.py" else importer.rpartition(".")[0]
        edges += [
            ImportEdge(importer, imported, shown, node.lineno, type_checking)
            for node, type_checking in _imports(ast.parse(path.read_text()).body, type_checking=False)
            for imported in _imported_modules(node, package, files)
        ]
    return edges


def adapter_boundary_faults(edges: list[ImportEdge]) -> list[str]:
    """Each import of the database adapter by a module outside it that is not an allowed importer."""
    return [
        f"{edge.path}:{edge.line}: {edge.importer} imports {edge.imported}"
        for edge in edges
        if _within(edge.imported, ADAPTER)
        and not _within(edge.importer, ADAPTER)
        and edge.importer not in ADAPTER_IMPORTERS
    ]


def layering_faults(edges: list[ImportEdge]) -> list[str]:
    """Each ``vfs`` import by a bottom module, and each import of ``vfs.offload`` from a layer beneath it."""
    faults: list[str] = []
    for edge in edges:
        if edge.importer in BOTTOM_MODULES:
            faults.append(f"{edge.path}:{edge.line}: {edge.importer} imports {edge.imported}; it imports no vfs module")
        if _within(edge.imported, OFFLOAD) and any(_within(edge.importer, layer) for layer in BENEATH_OFFLOAD):
            faults.append(f"{edge.path}:{edge.line}: {edge.importer} imports {edge.imported}, which sits above it")
    return faults


def test_src_names_no_context_document() -> None:
    hits = [
        f"{path.relative_to(REPO)}:{number}: {line.strip()[:80]}"
        for path in sorted(SRC.rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if DOCUMENT_CITATION.search(line)
    ]
    assert not hits, "\n".join(hits)


def test_the_security_skill_is_installed_unchanged() -> None:
    assert (SECURITY_SKILL / "SKILL.md").exists(), "the security-audit skill is not installed"
    lock = json.loads(SKILLS_LOCK.read_text())
    assert lock["skills"]["security-audit"]["source"] == "cloudflare/security-audit-skill"
    changed = (
        "the skill folder changed since it was pinned: run `npx skills check`, review the update, then pin "
        "folder_sha256(SECURITY_SKILL) as SECURITY_SKILL_SHA256 in a commit of its own, as standards/landing.md says"
    )
    assert folder_sha256(SECURITY_SKILL) == SECURITY_SKILL_SHA256, changed


def test_the_lint_workflow_covers_context() -> None:
    assert LINT_WORKFLOW.exists(), "no .github/workflows/lint.yml"
    text = LINT_WORKFLOW.read_text()
    for needle in ("context/**", "tests/lint/**", "AGENTS.md", "uv run pytest tests/lint"):
        assert needle in text, f"lint.yml does not mention {needle!r}"


def test_the_standards_agree_with_the_tree() -> None:
    errors: list[str] = [
        f"standards/{gone} still exists"
        for gone in ("commits-and-prs.md", "contributing.md")
        if (STANDARDS / gone).exists()
    ]
    errors += [
        f"standards/{page} is missing" for page in ("how-we-code.md", "landing.md") if not (STANDARDS / page).exists()
    ]
    forbidden = {
        "python-style.md": ("src_old", "there is no sync facade", "SyncVirtualFileSystem"),
        "roadmap.md": ("SyncVirtualFileSystem", "SyncSession"),
        "testing.md": ("--mssql", "fail_under = 99"),
        "tooling.md": ("uvx", "uv pip"),
        "constitution.md": ("context/decisions/", "open-questions.md"),
        # the hop and its tests live at package level; a row naming the adapter's module replays nothing
        "mutant-ledger.md": ("storage/backends/database/offload.py", "tests/storage/database/test_offload.py"),
        # the bump script rewrites pyproject.toml alone and locks by itself; the lane has started
        "release.md": ("src/vfs/__init__.py", "macos-13", "Before the first v2 release", "No release is planned"),
    }
    for page, needles in forbidden.items():
        text = (STANDARDS / page).read_text() if (STANDARDS / page).exists() else ""
        errors += [f"standards/{page} still says {needle!r}" for needle in needles if needle in text]
    required = {
        "testing.md": ("fail_under = 100",),
        "release.md": ("--pre", "--final", "--set", "workflow_dispatch", "--prerelease", "0.1.0a1", "0.1.0b1", "musl"),
        "python-style.md": ("vfs.sync", "AsyncVirtualFileSystem"),
    }
    for page, needles in required.items():
        text = (STANDARDS / page).read_text() if (STANDARDS / page).exists() else ""
        errors += [f"standards/{page} does not say {needle!r}" for needle in needles if needle not in text]
    assert not errors, "\n".join(errors)


def test_the_readme_tells_the_truth_after_the_yank() -> None:
    """The README ships in the wheel and names no dead release; the install guide carries the pin and the musl note."""
    readme = (REPO / "README.md").read_text()
    assert "previous-generation API" not in readme, "the README still says PyPI ships the previous-generation API"
    assert "0.0.22" not in readme, "the README still names the yanked release"
    # Under pip a bare install fails while a yanked final sits beside the alphas; the install line is the pin.
    assert 'pip install "vfs-py>=0.1.0a1,<0.2"' in readme, "the README's install line lacks the pre-release marker"
    assert "pip install vfs-py\n" not in readme, "the README shows the bare install line, which fails under pip"
    guide = (REPO / "docs" / "how-to" / "install.md").read_text()
    assert "vfs-py>=0.1.0a1,<0.2" in guide, "the install guide gives no pin with a pre-release marker"
    assert "python:3.13-slim" in guide, "the install guide does not name a glibc image for the Alpine note"
    assert "how-to/install.md" in (REPO / "mkdocs.yml").read_text(), "the install guide is not in the docs nav"


def test_the_review_skills_write_review_files() -> None:
    assert (SKILLS / "spec_review" / "SKILL.md").exists(), "no spec_review skill"
    code_review = (SKILLS / "code_review" / "SKILL.md").read_text()
    assert "context/reviews/" in code_review, "code_review does not write to context/reviews/"
    assert "Security" in code_review, "code_review has no Security section"


def test_no_module_outside_the_adapter_imports_it() -> None:
    """The router and every other layer reach the database adapter through the storage protocols alone."""
    faults = adapter_boundary_faults(import_edges())
    assert not faults, "\n".join(faults)


def test_the_bottom_modules_import_nothing_from_vfs_and_nothing_beneath_offload_imports_it() -> None:
    """The deadline and the batcher stay at the bottom, and the layers under the hop never reach up to it."""
    modules = {_module_name(path, SRC) for path in SRC.rglob("*.py")}
    named = (*BOTTOM_MODULES, OFFLOAD)
    missing = [f"src/{name.replace('.', '/')}.py is missing" for name in named if name not in modules]
    faults = [*missing, *layering_faults(import_edges())]
    assert not faults, "\n".join(faults)


def test_the_clock_the_deadline_and_the_cadence_have_one_home() -> None:
    """One module reads the clock for a deadline, one makes the pool, and no cadence or float deadline is left."""
    sources = {str(path.relative_to(SRC)): path.read_text() for path in sorted(SRC.rglob("*.py"))}
    word = {name for name, text in sources.items() if re.search(r"\bmonotonic\b", text)}
    imported = {name for name, text in sources.items() if re.search(r"^from time import monotonic", text, re.M)}
    errors = [f"src/vfs/{name} names the monotonic clock" for name in sorted(word - CLOCK_READERS)]
    errors += [f"src/vfs/{name} no longer reads the monotonic clock" for name in sorted(CLOCK_READERS - imported)]
    errors += _line_hits(sources, r"deadline: float", "src/vfs", "takes its deadline as a float")
    errors += _line_hits(sources, r"_PER_CHECK|_past\(", "src/vfs", "keeps a cadence or a clock check of its own")
    pools = _line_hits(sources, r"ThreadPoolExecutor\(", "src/vfs", "makes a thread pool")
    if [hit.partition(":")[0] for hit in pools] != ["src/vfs/offload.py"]:
        errors += pools or ["src/vfs/offload.py makes no thread pool"]
    hops = _line_hits(sources, r"to_thread|run_in_executor", "src/vfs", "hops off the process pool")
    if [hit.partition(":")[0] for hit in hops] != ["src/vfs/embedding/provider.py"]:
        errors += hops or ["src/vfs/embedding/provider.py no longer hops on its own executor"]
    crate = {path.name: path.read_text() for path in sorted(CRATE.glob("*.rs"))}
    errors += _line_hits(crate, r"PER_CHECK|CLOCK_EVERY", "crates/vfs-core/src", "keeps a cadence of its own")
    assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_name(path: Path, root: Path) -> str:
    """The dotted name of the module at *path*; a package's ``__init__`` is the package."""
    parts = path.relative_to(root.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _within(module: str, package: str) -> bool:
    """Whether *module* is *package* or a module beneath it."""
    return module == package or module.startswith(f"{package}.")


def _imports(body: Iterable[ast.AST], *, type_checking: bool) -> Iterator[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Every import statement in or under *body*, with whether it sits under ``if TYPE_CHECKING:``."""
    for node in body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node, type_checking
        elif isinstance(node, ast.If) and getattr(node.test, "id", getattr(node.test, "attr", None)) == "TYPE_CHECKING":
            yield from _imports(node.body, type_checking=True)
            yield from _imports(node.orelse, type_checking=type_checking)
        else:
            yield from _imports(ast.iter_child_nodes(node), type_checking=type_checking)


def _imported_modules(node: ast.Import | ast.ImportFrom, package: str, files: dict[str, Path]) -> list[str]:
    """The ``vfs`` modules one import statement names, relative imports resolved against *package*."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names if _within(alias.name, "vfs")]
    base = node.module or ""
    if node.level:
        anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)]
        base = ".".join([*anchor, base] if base else anchor)
    if not _within(base, "vfs"):
        return []
    modules: list[str] = []
    for alias in node.names:
        if (base, alias.name) == ("vfs", "_native"):
            continue
        submodule = f"{base}.{alias.name}"
        modules.append(submodule if submodule in files else base)
    return list(dict.fromkeys(modules))


def _line_hits(sources: dict[str, str], pattern: str, folder: str, fault: str) -> list[str]:
    """One ``file:line: fault`` string per line of *sources* that matches *pattern*."""
    return [
        f"{folder}/{name}:{number}: {fault}: {line.strip()[:80]}"
        for name, text in sources.items()
        for number, line in enumerate(text.splitlines(), 1)
        if re.search(pattern, line)
    ]
