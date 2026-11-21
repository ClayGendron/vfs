"""The shape of the code and the tooling the process relies on."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from collections import Counter
from typing import TYPE_CHECKING, NamedTuple

import pytest

from tests.lint.allowlist import MODULE_LINE_BASELINE, UPWARD_IMPORT_ALLOWANCE
from tests.lint.shapes import REPO

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

Ladder = tuple[tuple[str, ...], ...]

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

# The layer ladder, bottom first: an import between two units points to a lower rung. A module
# belongs to the unit that is its deepest named prefix, and units that share a rung stay apart.
LAYERS: Ladder = (
    ("vfs.native",),
    ("vfs.deadline", "vfs.batching", "vfs.ops", "vfs.authority", "vfs.paths"),
    ("vfs.models",),
    ("vfs.results",),
    ("vfs.pattern_matching",),
    ("vfs.offload",),
    ("vfs.storage", "vfs.embedding", "vfs.rendering"),
    (
        "vfs.storage.backends",
        "vfs.params",
        "vfs.rerank",
        "vfs.permissions",
        "vfs.exceptions",
        "vfs.fanout",
        "vfs.chain",
    ),
    ("vfs.mounts",),
    ("vfs.listing",),
    ("vfs.base",),
    ("vfs.session", "vfs.skills"),
    ("vfs.sync",),
    ("vfs",),
)
# The package root: the prefix of every module, so a module it alone places has no rung of its own.
ROOT = "vfs"
# The modules that import no vfs module of either kind, whatever the ladder places beneath them.
IMPORTS_NO_VFS_MODULE = ("vfs.deadline", "vfs.batching", "vfs.native")
# A module over this many lines is held at its exact count in MODULE_LINE_BASELINE.
MODULE_LINE_CEILING = 1000

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


class Placement(NamedTuple):
    """Where a module sits on the ladder: its rung, counted from the bottom, and the unit it belongs to."""

    rung: int
    unit: str


def placement(module: str, layers: Ladder = LAYERS) -> Placement:
    """The rung and the unit of *module*: the longest name on the ladder that is it or a dotted prefix of it.

    The root is a prefix of every module, so a ladder that names the root places every module.
    """
    named = [Placement(rung, name) for rung, names in enumerate(layers) for name in names if _within(module, name)]
    return max(named, key=lambda placed: len(placed.unit))


def ladder_shape_faults(
    modules: Iterable[str], layers: Ladder = LAYERS, declared: Iterable[str] = IMPORTS_NO_VFS_MODULE
) -> list[str]:
    """Each way the map is not whole over *modules*, the dotted names of the tree's modules.

    A name twice, a name or a declared name that is no module, a module the root alone places, and a
    part named beneath its package. Importing a part runs its package first and the walk records no
    edge for that, so a deeper name sits no lower than the nearest name it extends, the root aside.
    """
    tree = set(modules)
    names = [name for rung in layers for name in rung]
    rungs = {name: rung for rung, rung_names in enumerate(layers) for name in rung_names}
    faults = [f"LAYERS names {name} twice" for name, count in Counter(names).items() if count > 1]
    faults += [f"LAYERS names {name}, which is no module of src/vfs" for name in rungs if name not in tree]
    faults += [
        f"{module} has no rung: name it in LAYERS"
        for module in sorted(tree)
        if module != ROOT and placement(module, layers).unit == ROOT
    ]
    for name, rung in rungs.items():
        extended = [other for other in rungs if other != ROOT and name.startswith(f"{other}.")]
        if extended and rung < rungs[nearest := max(extended, key=len)]:
            faults.append(f"LAYERS names {name} beneath {nearest}, the package it is part of")
    faults += [
        f"IMPORTS_NO_VFS_MODULE names {name}, which is no module of src/vfs" for name in declared if name not in tree
    ]
    return faults


def ladder_faults(
    edges: Iterable[ImportEdge],
    allowance: frozenset[tuple[str, str]] = UPWARD_IMPORT_ALLOWANCE,
    layers: Ladder = LAYERS,
) -> list[str]:
    """Each import between two units that points up the ladder or across a rung, and each stale entry.

    An import under ``if TYPE_CHECKING:`` is judged like any other. *allowance* admits upward imports
    alone, by the exact pair of importer and imported; an entry that admits none is stale.
    """
    faults: list[str] = []
    admitted: set[tuple[str, str]] = set()
    for edge in edges:
        importer, imported = placement(edge.importer, layers), placement(edge.imported, layers)
        if importer.unit == imported.unit or imported.rung < importer.rung:
            continue
        written = f"{edge.path}:{edge.line}: {edge.importer} imports {edge.imported}"
        if imported.rung == importer.rung:
            faults.append(f"{written}, which shares its rung")
        elif (edge.importer, edge.imported) in allowance:
            admitted.add((edge.importer, edge.imported))
        else:
            faults.append(f"{written}, which sits above it")
    faults += [
        f"tests/lint/allowlist.py: ({importer}, {imported}) matches no upward import; remove the entry"
        for importer, imported in sorted(allowance - admitted)
    ]
    return faults


def no_vfs_import_faults(edges: Iterable[ImportEdge], declared: Iterable[str] = IMPORTS_NO_VFS_MODULE) -> list[str]:
    """Each ``vfs`` import, of either kind, by a declared module or a module beneath one.

    No rung and no allowance entry admits one: the ladder says what a module may not reach, and this
    says the module reaches nothing at all.
    """
    names = tuple(declared)
    return [
        f"{edge.path}:{edge.line}: {edge.importer} imports {edge.imported}; it is declared to import no vfs module"
        for edge in edges
        if any(_within(edge.importer, name) for name in names)
    ]


def size_faults(
    counts: dict[str, int], baseline: dict[str, int] = MODULE_LINE_BASELINE, ceiling: int = MODULE_LINE_CEILING
) -> list[str]:
    """Each module whose line count in *counts* is not what *baseline* holds it to.

    A listed module equals its entry, so one that shrinks takes its entry down and cannot grow back;
    a module at or under *ceiling* has no entry, and an unlisted module never exceeds *ceiling*.
    """
    faults: list[str] = []
    for path, entry in baseline.items():
        count = counts.get(path)
        if count is None:
            faults.append(f"{path}: MODULE_LINE_BASELINE names it, which is no module of src/vfs")
        elif count <= ceiling:
            faults.append(f"{path}: holds {count} lines, within the ceiling of {ceiling}; remove the entry")
        elif count > entry:
            faults.append(f"{path}: grew to {count} lines from its entry of {entry}; move out as many as were added")
        elif count < entry:
            faults.append(f"{path}: holds {count} lines, fewer than its entry of {entry}; lower the entry")
    faults += [
        f"{path}: holds {count} lines, over the ceiling of {ceiling}, with no entry in MODULE_LINE_BASELINE"
        for path, count in counts.items()
        if count > ceiling and path not in baseline
    ]
    return faults


def line_counts(root: Path = SRC) -> dict[str, int]:
    """Each module's line count as ``wc -l`` prints it: the newline bytes of its file.

    *root* is the package folder (``.../src/vfs``); a key is the file's path from the folder that holds ``src``.
    """
    return {
        path.relative_to(root.parents[1]).as_posix(): path.read_bytes().count(b"\n")
        for path in sorted(root.rglob("*.py"))
    }


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
    # a release audit's record waits on the fixes it reproduces; both standards say so, and the gate holds the words
    required = {
        "testing.md": ("fail_under = 100",),
        "release.md": (
            *("--pre", "--final", "--set", "workflow_dispatch", "--prerelease", "0.1.0a1", "0.1.0b1", "musl"),
            *("never lands while", "Blocks the release"),
        ),
        "landing.md": ("that audit's record",),
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


def test_the_review_rubric_names_the_two_checks() -> None:
    """The review holds the gate's declarations one-way, so its rubric names both lines and every closing."""
    lines = ("Layer map:", "Size:", "ladder unchanged", "ladder changed", "allowlist unchanged", "allowlist changed")
    declarations = ("ADAPTER_IMPORTERS", "MODULE_LINE_CEILING", "IMPORTS_NO_VFS_MODULE")
    command_paths = "tests/lint/test_code_shape.py tests/lint/allowlist.py"
    structural_note = "placeholder memo or a spec"
    required = {
        SKILLS / "ownership_review" / "SKILL.md": (*lines, *declarations, command_paths),
        SKILLS / "code_review" / "SKILL.md": lines,
        REPO / "context" / "reviews" / "README.md": (*lines, structural_note),
        STANDARDS / "how-we-code.md": (structural_note, "LAYERS"),
    }
    errors = [
        f"{page.relative_to(REPO)} does not say {needle!r}"
        for page, needles in required.items()
        for needle in needles
        if needle not in page.read_text()
    ]
    assert not errors, "\n".join(errors)


def test_no_module_outside_the_adapter_imports_it() -> None:
    """The router and every other layer reach the database adapter through the storage protocols alone."""
    faults = adapter_boundary_faults(import_edges())
    assert not faults, "\n".join(faults)


def test_imports_point_down_the_ladder() -> None:
    """The map is whole, every import between two units points down it, and the declared modules import no vfs."""
    edges = import_edges()
    faults = [*ladder_shape_faults(_tree_modules()), *ladder_faults(edges), *no_vfs_import_faults(edges)]
    assert not faults, "\n".join(faults)


@pytest.mark.parametrize(
    ("importer", "imported", "type_checking", "from_the_ladder", "from_the_declared_set"),
    [
        ("vfs.deadline", "vfs.results", False, 1, 1),
        ("vfs.batching", "vfs.paths", False, 1, 1),
        ("vfs.pattern_matching.glob", "vfs.offload", False, 1, 0),
        ("vfs.results.kinds", "vfs.offload", True, 1, 0),
        ("vfs.pattern_matching.grep", "vfs.offload", True, 1, 0),
        ("vfs.deadline", "vfs.batching", True, 1, 1),
        ("vfs.batching", "vfs.deadline", False, 1, 1),
        ("vfs.deadline", "vfs.native", False, 0, 1),
    ],
)
def test_the_ladder_refuses_what_the_retired_rule_refused(
    importer: str, imported: str, type_checking: bool, from_the_ladder: int, from_the_declared_set: int
) -> None:
    """Each import the bottom-modules rule refused is still a fault, of either kind of import.

    Guards: typing-only rows skipped, a shared rung admitted, and the declared set judged by rung.
    """
    row = _row(importer, imported, type_checking=type_checking)
    ladder = ladder_faults([row], allowance=frozenset())
    declared = no_vfs_import_faults([row])
    assert (len(ladder), len(declared)) == (from_the_ladder, from_the_declared_set)
    assert ladder or declared
    assert all(fault.startswith(f"{row.path}:{row.line}: ") for fault in (*ladder, *declared))


def test_the_ladder_names_a_stale_entry_and_an_unplaced_module() -> None:
    """The allowance is exact, a shared rung is never admitted, and the map is whole with no part beneath its package.

    Guards: a stale entry kept, an entry admitting a shared rung, a prefix of its pair or its pair of
    units, an entry counted as used by a downward import, an unnamed module given the top rung, a deeper
    name judged against the root or a farther package, a declared name matched exactly, and a name
    read as a prefix without its dot.
    """
    edges = import_edges()
    modules = sorted(_tree_modules())
    session = ("vfs.base", "vfs.session")
    [unadmitted] = ladder_faults(edges, allowance=UPWARD_IMPORT_ALLOWANCE - {session})
    assert unadmitted.startswith("src/vfs/base.py:")
    assert unadmitted.endswith(": vfs.base imports vfs.session, which sits above it")
    stale = ladder_faults(edges, allowance=UPWARD_IMPORT_ALLOWANCE | {("vfs.paths", "vfs.base")})
    assert stale == ["tests/lint/allowlist.py: (vfs.paths, vfs.base) matches no upward import; remove the entry"]
    sideways = _row("vfs.paths", "vfs.ops")
    shared = "src/vfs/paths.py:7: vfs.paths imports vfs.ops, which shares its rung"
    assert ladder_faults([sideways], allowance=frozenset()) == [shared]
    shared_and_stale = ladder_faults([sideways], allowance=frozenset({("vfs.paths", "vfs.ops")}))
    assert shared_and_stale == [shared, _stale("vfs.paths", "vfs.ops")]
    line_law = _row("vfs.results.preview", "vfs.pattern_matching.grep")
    upward = f"{line_law.path}:7: {line_law.importer} imports {line_law.imported}, which sits above it"
    assert ladder_faults([line_law], allowance=frozenset({(line_law.importer, line_law.imported)})) == []
    for near_miss in (
        ("vfs.results", "vfs.pattern_matching"),
        ("vfs.results.preview", "vfs.pattern_matching"),
        ("vfs.results", "vfs.pattern_matching.grep"),
    ):
        assert ladder_faults([line_law], allowance=frozenset({near_miss})) == [upward, _stale(*near_miss)]
    for unused in (_row("vfs.base", "vfs.paths"), _row("vfs.results.render", "vfs.results.kinds")):
        entry = (unused.importer, unused.imported)
        assert ladder_faults([unused], allowance=frozenset({entry})) == [_stale(*entry)]

    assert ladder_shape_faults(modules, layers=_joining(0, "vfs.models")) == ["LAYERS names vfs.models twice"]
    no_module = "vfs.gone, which is no module of src/vfs"
    assert ladder_shape_faults(modules, layers=_joining(0, "vfs.gone")) == [f"LAYERS names {no_module}"]
    assert ladder_shape_faults([*modules, "vfs.fresh"]) == ["vfs.fresh has no rung: name it in LAYERS"]
    loose = "vfs.loose.anything"
    assert ladder_shape_faults([*modules, loose]) == [f"{loose} has no rung: name it in LAYERS"]
    cache = "vfs.results_cache"
    assert ladder_shape_faults([*modules, cache]) == [f"{cache} has no rung: name it in LAYERS"]
    assert ladder_shape_faults([*modules, "vfs.offloaded"], layers=_joining(0, "vfs.offloaded")) == []
    declared = (*IMPORTS_NO_VFS_MODULE, "vfs.gone")
    assert ladder_shape_faults(modules, declared=declared) == [f"IMPORTS_NO_VFS_MODULE names {no_module}"]
    beneath = "LAYERS names vfs.storage.ranking beneath vfs.storage, the package it is part of"
    for rung in (0, 1):
        assert ladder_shape_faults(modules, layers=_joining(rung, "vfs.storage.ranking")) == [beneath]
    assert ladder_shape_faults(modules) == []
    adapter_on_the_seam = _joining(placement("vfs.storage").rung, ADAPTER)
    beneath = f"LAYERS names {ADAPTER} beneath vfs.storage.backends, the package it is part of"
    assert ladder_shape_faults(modules, layers=adapter_on_the_seam) == [beneath]
    light = "vfs.offload.light"
    results, offload = placement("vfs.results").rung, placement("vfs.offload").rung
    beneath = f"LAYERS names {light} beneath vfs.offload, the package it is part of"
    assert ladder_shape_faults([*modules, light], layers=_with_rung(results, light)) == [beneath]
    assert ladder_shape_faults([*modules, light], layers=_joining(offload, light)) == []
    assert ladder_shape_faults([*modules, light], layers=_with_rung(offload + 1, light)) == []

    floor = _with_rung(0, "vfs.clock")
    for module in ("vfs.deadline", "vfs.batching", "vfs.native"):
        row = _row(module, "vfs.clock")
        assert ladder_faults([row], allowance=frozenset(), layers=floor) == []
        assert len(no_vfs_import_faults([row])) == 1
    part = _row("vfs.deadline.clock", "vfs.native")
    assert ladder_faults([part], allowance=frozenset()) == []
    assert no_vfs_import_faults([part]) == [
        "src/vfs/deadline/clock.py:7: vfs.deadline.clock imports vfs.native; it is declared to import no vfs module"
    ]
    leaf = _row("vfs.paths", "vfs.native")
    assert ladder_faults([leaf], allowance=frozenset()) == []
    assert no_vfs_import_faults([leaf]) == []
    assert len(no_vfs_import_faults([leaf], declared=("vfs.paths",))) == 1
    assert no_vfs_import_faults([_row("vfs.deadline2", "vfs.paths")]) == []


def test_a_listed_module_never_grows_and_an_unlisted_one_stays_under_the_ceiling() -> None:
    """Each module over the ceiling is held at its exact line count, and no other module crosses the ceiling."""
    faults = size_faults(line_counts())
    assert not faults, "\n".join(faults)


def test_the_size_baseline_names_growth_staleness_and_a_missing_entry() -> None:
    """A listed module equals its entry, and an entry exists exactly for a module over the ceiling.

    Guards: equality loosened to "at most", the ceiling comparison off by one, and a missing file passed over.
    """
    listed, unlisted = "src/vfs/listed.py", "src/vfs/unlisted.py"

    def faults(counts: dict[str, int]) -> list[str]:
        return size_faults(counts, baseline={listed: 1200}, ceiling=1000)

    [grown] = faults({listed: 1201})
    assert grown.startswith(f"{listed}: ") and "1201" in grown and "1200" in grown
    [stale] = faults({listed: 1199})
    assert stale.startswith(f"{listed}: ") and stale.endswith("lower the entry")
    [unneeded] = faults({listed: 1000})
    assert unneeded.startswith(f"{listed}: ") and unneeded.endswith("remove the entry")
    [gone] = faults({})
    assert gone.startswith(f"{listed}: ") and "no module" in gone
    [over] = faults({listed: 1200, unlisted: 1001})
    assert over.startswith(f"{unlisted}: ") and "no entry" in over
    assert faults({listed: 1200, unlisted: 1000}) == []
    assert size_faults({unlisted: 1001}, baseline={}, ceiling=2000) == []
    assert len(size_faults({unlisted: 501}, baseline={}, ceiling=500)) == 1


def test_a_line_count_is_the_newline_bytes_of_a_file(tmp_path: Path) -> None:
    """A module's size is its newline bytes, keyed by its path from the folder that holds ``src``.

    Guards: a count of text lines, which reads an unterminated last line or a form feed as one more.
    """
    package = tmp_path / "src" / "vfs"
    (package / "deep").mkdir(parents=True)
    (package / "whole.py").write_bytes(b"one\ntwo\n")
    (package / "deep" / "ragged.py").write_bytes(b"one\ntwo\x0cstill two\nthree")
    (package / "notes.txt").write_bytes(b"not a module\n")
    assert line_counts(package) == {"src/vfs/whole.py": 2, "src/vfs/deep/ragged.py": 2}


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


def test_vfs_prints_nothing_and_each_logger_is_its_modules_own() -> None:
    """No module prints, every ``getLogger`` takes ``__name__``, and no record goes to the root logger."""
    errors: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            where = f"src/vfs/{path.relative_to(SRC)}:{node.lineno}"
            callee = ast.unparse(node.func)
            if callee.rpartition(".")[2] == "print":
                errors.append(f"{where} calls print")
            if callee.rpartition(".")[2] == "getLogger" and (
                [ast.unparse(arg) for arg in node.args] != ["__name__"] or node.keywords
            ):
                errors.append(f"{where} names a logger other than its module's")
            if callee.partition(".")[0] == "logging" and callee != "logging.getLogger":
                errors.append(f"{where} logs to the root logger")
    assert not errors, "\n".join(errors)


def test_get_started_names_the_three_engine_extras_and_no_other() -> None:
    """The install lines stay few: the base package and one extra per server engine, each one pyproject declares."""
    page = (REPO / "documentation" / "get-started.md").read_text()
    named = {name.strip() for group in re.findall(r"vfs-py\[([^\]]*)\]", page) for name in group.split(",")}
    declared = set(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["optional-dependencies"])
    assert named == {"postgres", "mssql", "oracle"}
    assert named <= declared, f"the page names extras pyproject.toml does not declare: {sorted(named - declared)}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_name(path: Path, root: Path) -> str:
    """The dotted name of the module at *path*; a package's ``__init__`` is the package."""
    parts = path.relative_to(root.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _tree_modules() -> set[str]:
    """The dotted name of every module of the package."""
    return {_module_name(path, SRC) for path in SRC.rglob("*.py")}


def _row(importer: str, imported: str, *, type_checking: bool = False) -> ImportEdge:
    """One hand-built import row, written at line 7 of the importer's own file."""
    return ImportEdge(importer, imported, f"src/{importer.replace('.', '/')}.py", 7, type_checking)


def _stale(importer: str, imported: str) -> str:
    """The fault for an allowance entry that admits no upward import."""
    return f"tests/lint/allowlist.py: ({importer}, {imported}) matches no upward import; remove the entry"


def _joining(rung: int, name: str) -> tuple[tuple[str, ...], ...]:
    """The live ladder with *name* added to the rung at index *rung*."""
    return (*LAYERS[:rung], (*LAYERS[rung], name), *LAYERS[rung + 1 :])


def _with_rung(rung: int, name: str) -> tuple[tuple[str, ...], ...]:
    """The live ladder with one new rung at index *rung*, holding *name* alone."""
    return (*LAYERS[:rung], (name,), *LAYERS[rung:])


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
