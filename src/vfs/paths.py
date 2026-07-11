"""Canonical paths for the VFS namespace.

Every caller-supplied path enters through the gate — :class:`Path` (or
:func:`resolve_path` for a non-raising result) — which normalizes and validates
it into a canonical form safe to route and store. The metadata layout is rooted
at ``/.vfs`` and mirrors the logical user path before crossing a reserved
``__meta__`` boundary; chunks are version-addressed.

Examples:

    /src/auth.py                                              file
    /.vfs/src/auth.py/__meta__/chunks/3/login                 chunk
    /.vfs/src/auth.py/__meta__/versions/3                     version
    /.vfs/src/auth.py/__meta__/edges/out/imports/src/util.py  edge
    /.agents/tools/clone-repo                                 tool
    /.agents/skills/pdf-processing                            skill
"""

from __future__ import annotations

import posixpath
import unicodedata
from typing import TYPE_CHECKING, Literal, NamedTuple

from pydantic_core import core_schema

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema


# "tool"/"skill" are user-space capability kinds: the unit is a directory under
# /.agents, while its TOOL.md/SKILL.md manifest stays a plain indexable file.
ObjectKind = Literal["file", "directory", "chunk", "version", "edge", "tool", "skill"]

MAX_PATH_LENGTH = 1024  # hard namespace-wide invariant — see Path docstring
MAX_SEGMENT_LENGTH = 255

METADATA_ROOT = "/.vfs"
META_SEGMENT = "__meta__"
EDGE_DIRECTIONS = ("out", "in")
EDGE_DIRECTION_SET = frozenset(EDGE_DIRECTIONS)

# Reserved user-space capability root. Unlike METADATA_ROOT (derived, no indexable
# content), /.agents holds real files, so a tool's/skill's manifest indexes normally.
AGENTS_ROOT = "/.agents"
AGENT_FAMILY_TO_KIND: dict[str, ObjectKind] = {"tools": "tool", "skills": "skill"}
TOOL_MANIFEST = "TOOL.md"
SKILL_MANIFEST = "SKILL.md"

EXTENSIONLESS_FILES = frozenset(
    {
        # Build / CI
        "Makefile",
        "GNUmakefile",
        "BSDmakefile",
        "Kbuild",
        "Dockerfile",
        "Containerfile",
        "Jenkinsfile",
        "Vagrantfile",
        "Procfile",
        "Justfile",
        "Taskfile",
        "Earthfile",
        "Snakefile",
        "Tiltfile",
        "Caddyfile",
        "BUILD",
        "WORKSPACE",
        # Ruby ecosystem
        "Rakefile",
        "Gemfile",
        "Brewfile",
        "Podfile",
        "Fastfile",
        "Appfile",
        "Scanfile",
        "Berksfile",
        "Capfile",
        "Guardfile",
        "Thorfile",
        "Dangerfile",
        "Steepfile",
        "Appraisals",
        # Other language build files
        "Emakefile",
        "Nukefile",
        # Documentation / metadata
        "LICENSE",
        "LICENCE",
        "README",
        "CHANGELOG",
        "CHANGES",
        "CONTRIBUTING",
        "AUTHORS",
        "CONTRIBUTORS",
        "PATENTS",
        "NOTICE",
        "CREDITS",
        "HISTORY",
        "NEWS",
        "THANKS",
        "TODO",
        "COPYING",
        "COPYRIGHT",
        "INSTALL",
        "CODEOWNERS",
        "MAINTAINERS",
        "OWNERS",
        "VERSION",
        "MANIFEST",
        # Git
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".gitkeep",
        ".git-blame-ignore-revs",
        ".mailmap",
        # Container / orchestration
        ".dockerignore",
        ".helmignore",
        # Editor / formatting
        ".editorconfig",
        ".clang-format",
        ".clang-tidy",
        ".dir-locals",
        # JS / Node
        ".eslintignore",
        ".eslintrc",
        ".prettierignore",
        ".prettierrc",
        ".stylelintignore",
        ".stylelintrc",
        ".babelrc",
        ".browserslistrc",
        ".npmignore",
        ".npmrc",
        ".nvmrc",
        ".node-version",
        # Python
        ".python-version",
        ".flaskenv",
        # Ruby / other version managers
        ".ruby-version",
        ".java-version",
        ".tool-versions",
        # Environment
        ".env",
        ".envrc",
        # YAML linting
        ".yamllint",
    }
)

_EXTENSIONLESS_FILES_LOWER = frozenset(name.lower() for name in EXTENSIONLESS_FILES)

_FORBIDDEN_FORMAT_CHARS = frozenset(
    {0x00AD, 0x200B, 0x200E, 0x200F, 0x2028, 0x2029, 0x2060, 0xFEFF}
    | set(range(0x202A, 0x202F))  # bidi embeddings / overrides (LRE…RLO)
    | set(range(0x2066, 0x206A))  # bidi isolates (LRI…PDI)
)

# ---------------------------------------------------------------------------
# Canonical path gate
# ---------------------------------------------------------------------------


class Path(str):
    """A path that has passed the gate: canonical, validated, safe to route.

    A ``str`` subclass — binds into SQL, f-strings, and dict keys unchanged. One
    constructor, ``Path(value)``: it canonicalizes and validates through
    :func:`resolve_path` and raises ``ValueError`` only on a structurally invalid
    path (null byte, control char, over-long segment/path). Non-canonical input is
    *canonicalized*, not rejected: ``Path("/a/../b") == "/b"``.

    Validates if path can exist within VFS based on *structure only*. Whether a path
    is a legal write target is a separate concern in ``resolve_path(mutation=True)``.

    Derived strings (slicing, ``+``, ``.lstrip``) return plain ``str`` — the badge
    is intentionally not inherited. Re-mint via ``parent_dir`` / ``parent_file`` /
    ``joinpath`` / ``resolve_path`` when you need it back.

    **Length is a hard invariant, not an ingress rule.** No ``Path`` ever
    exceeds ``MAX_PATH_LENGTH`` (1024) — including the outputs of
    ``with_mount`` / ``without_mount`` / ``joinpath``. This guarantees every
    path a ``Result`` returns is valid input to the next request
    (re-addressability). A rebase that would exceed the limit raises
    ``ValueError`` at the ``Path`` layer; the router's rebase seam
    (``Result.with_mount``) converts that per row into a classified
    ``ResultError`` — an over-long global path can therefore never be
    observed, raised, or stored anywhere in the system.

    Consequence for deep mounts: a child-local path is only reachable through
    a parent if ``len(mount_prefix) + len(local_path) <= 1024``. Content
    written *through* the parent always satisfies this (the ingress gate
    bounds the global path); content written directly to a child that is also
    mounted deeper elsewhere may not — such rows surface as ``invalid``
    errors on the parent's results rather than as rows.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> Path:
        # Validate through the one gate; resolve_path mints the branded instance.
        resolved = resolve_path(value)
        if resolved.path is None:
            raise ValueError(resolved.error)
        return resolved.path

    @classmethod
    def _brand(cls, canonical: str) -> Path:
        """Stamp an already-canonical string as a ``Path`` without re-validating.

        The single unchecked construction site, called only where canonicality
        is proven: :func:`resolve_path` (on a string it has just normalized and
        validated) and the rebase pair :meth:`with_mount` / :meth:`without_mount`
        (canonical-absolute concat/strip of two branded paths, length checked
        explicitly). Going through the public ``Path(...)`` constructor at those
        sites would recurse back into the gate; every other mint runs the full
        validation.
        """
        return str.__new__(cls, canonical)

    @property
    def parent_dir(self) -> Path:
        """Literal parent directory — same derivation as ``VFSEntry.parent_dir``."""
        return compute_parent_dir(self)

    @property
    def parent_file(self) -> Path | None:
        """Owning file for a chunk/version/edge meta path, else ``None``.

        Same derivation as ``VFSEntry.parent_file``.
        """
        return compute_parent_file(self)

    @property
    def source_file(self) -> Path | None:
        """Edge tail endpoint for an edge path, else ``None``.

        Same derivation as ``VFSEntry.source_file``.
        """
        parts = decompose_edge(self)
        return parts.source if parts is not None else None

    @property
    def target_file(self) -> Path | None:
        """Edge head endpoint for an edge path, else ``None``.

        Same derivation as ``VFSEntry.target_file``.
        """
        parts = decompose_edge(self)
        return parts.target if parts is not None else None

    @property
    def name(self) -> str:
        """Leaf segment (mirrors ``VFSEntry.name``)."""
        return split_path(self)[1]

    @property
    def kind(self) -> ObjectKind:
        """Structural kind from path markers (mirrors ``VFSEntry.kind``)."""
        return parse_kind(self)

    @property
    def ext(self) -> str | None:
        """Lowercased file extension for a file path, else ``None``.

        Kind-gated like ``VFSEntry.ext``: only ``file`` paths carry an extension
        — chunks, versions, edges, and directories are ``None`` even when their
        leaf ends in a dotted suffix.
        """
        return extract_extension(self) if self.kind == "file" else None

    @property
    def is_meta(self) -> bool:
        """Whether this path is under the reserved ``/.vfs`` tree."""
        return is_meta_path(self)

    @property
    def is_mutable_target(self) -> bool:
        """Namespace-grammar half of writability — NOT a permission check.

        ``/`` and the ``/.vfs`` root are never mutable; inverse-edge paths never
        directly writable; meta endpoints and ordinary paths are. Use the function
        ``check_mutable_path`` when the rejection *reason* is needed.
        """
        ok, _ = check_mutable_path(self)
        return ok

    def joinpath(self, *segments: str) -> Path:
        """Combine this path with one or more segments, re-gating the result.

        Mirrors :meth:`pathlib.PurePath.joinpath`: relative segments extend the
        path; an absolute segment resets it. ``str.join`` is left untouched —
        joining is named, not bolted onto the separator method. Also available as
        the ``/`` operator for a single segment.
        """
        return Path(posixpath.join(self, *segments))

    def __truediv__(self, segment: str) -> Path:
        """``path / "sub"`` — pathlib-style sugar for joining one segment."""
        return self.joinpath(segment)

    def with_mount(self, mount: str) -> Path:
        """Re-root this mount-local path under *mount* (local → global).

        The outbound half of routing; inverse of :meth:`without_mount`. *mount*
        is gated first, so ``/mnt/foo/`` and ``mnt/foo`` behave alike; a root
        mount is the identity. Both sides are canonical and canonical-absolute
        concatenation is canonical, so the result is branded directly — except
        length, the one invariant concatenation can break, which is checked
        explicitly. Raises ``ValueError`` on overflow; the router's rebase seam
        converts that into a classified per-row error (see ``Result.with_mount``).
        """
        mount = Path(mount)
        if mount == "/":
            return self
        if self == "/":
            return mount
        if len(mount) + len(self) > MAX_PATH_LENGTH:
            msg = f"Rebased path too long (max {MAX_PATH_LENGTH}): mount {mount!r} + local path of {len(self)} chars"
            raise ValueError(msg)
        return Path._brand(mount + self)

    def without_mount(self, mount: str) -> Path:
        """Strip the leading *mount* prefix (global → local).

        The inbound half of routing; inverse of :meth:`with_mount`. *mount* is
        gated first; the match is boundary-aware (``/mnt/foo`` is not within
        ``/mnt/foobar``); a root mount is the identity. Raises if this path is
        not under *mount* — that is a routing bug, not a slice. Stripping a
        canonical prefix from a canonical path only shortens it, so the result
        is branded directly — no length guard needed.
        """
        mount = Path(mount)
        if mount == "/":
            return self
        if self == mount:
            return Path._brand("/")
        if not self.startswith(mount + "/"):
            msg = f"Path {self!r} is not within mount {mount!r}"
            raise ValueError(msg)
        return Path._brand(self[len(mount) :])

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: type,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        # Validate-and-coerce str to Path at model boundaries; the str subclass serializes as-is.
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
        )


class ResolvedPath(NamedTuple):
    """Outcome of the path gate: a canonical path, or a rejection reason."""

    path: Path | None
    error: str | None


def resolve_path(path: str, *, mutation: bool = False) -> ResolvedPath:
    """Turn a caller-supplied path into a canonical internal path.

    The single gate every caller-supplied path passes before it reaches
    routing or storage. Normalizes once, then validates the canonical form;
    ``mutation=True`` additionally authorizes the write (rejecting the root
    and reserved metadata space). Returns the canonical path, or an error
    reason with ``path=None``. Never raises — non-``str`` input is reported as
    a rejection, not a ``TypeError``.

    Idempotent on branded input: a :class:`Path` is canonical and validated by
    construction, so it passes through unchanged (making ``Path(p)`` an
    identity) — only the mutation authorization still runs.
    """
    if isinstance(path, Path):
        if mutation:
            ok, reason = check_mutable_path(path)
            if not ok:
                return ResolvedPath(None, reason)
        return ResolvedPath(path, None)
    if not isinstance(path, str):
        return ResolvedPath(None, f"Path must be a string, got {type(path).__name__}")
    canonical = normalize_path(path)
    valid, reason = validate_path(canonical)
    if not valid:
        return ResolvedPath(None, reason)
    # Stamp the validated string; Path(canonical) would re-enter the gate.
    branded = Path._brand(canonical)
    if mutation:
        ok, reason = check_mutable_path(branded)
        if not ok:
            return ResolvedPath(None, reason)
    return ResolvedPath(branded, None)


# ---------------------------------------------------------------------------
# Relative path gate
# ---------------------------------------------------------------------------


class RelativePath(str):
    """A relative path that has passed the gate: canonical, contained, safe to join.

    The relative counterpart of :class:`Path`. A ``str`` subclass holding a
    forward-slash path with *no* leading slash and *no* ``.``/``..`` segments, so
    joining it onto any absolute :class:`Path` can only descend — it can never
    reset to an absolute root (an absolute right-hand side resets the join) nor
    climb out (``..`` clamps silently). Construction canonicalizes (NFC-folds,
    strips per-segment whitespace, drops ``.`` and empty segments) and raises
    ``ValueError`` on an absolute input, a ``..`` segment, an over-long
    segment/path, or a forbidden character.

    Use it wherever a path is addressed *relative to* a known root — a skill's
    bundled files, an archive member: the badge certifies the value is safe to
    feed to :meth:`Path.joinpath`. Derived strings (slicing, ``+``) return plain
    ``str``; re-mint via the constructor when the badge is needed back.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> RelativePath:
        resolved = resolve_relative_path(value)
        if resolved.path is None:
            raise ValueError(resolved.error)
        return resolved.path

    @classmethod
    def _brand(cls, canonical: str) -> RelativePath:
        """Stamp an already-canonical string as a ``RelativePath`` without re-validating.

        The single unchecked construction site; only :func:`resolve_relative_path`
        calls it, on a string it has just normalized and validated.
        """
        return str.__new__(cls, canonical)

    @property
    def name(self) -> str:
        """Leaf segment (mirrors :attr:`Path.name`)."""
        return self.rsplit("/", 1)[-1]

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: type,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        # Validate-and-coerce str to RelativePath at model boundaries; the str subclass serializes as-is.
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
        )


class ResolvedRelativePath(NamedTuple):
    """Outcome of the relative-path gate: a canonical relative path, or a rejection reason."""

    path: RelativePath | None
    error: str | None


def resolve_relative_path(path: str) -> ResolvedRelativePath:
    """Turn a caller-supplied relative path into a canonical, contained path.

    The single gate every relative path passes before it is joined onto a root.
    Normalizes once, then validates the canonical form; an absolute input is a
    category error, rejected up front (it would reset the join and discard the
    root). Returns the canonical relative path, or an error reason with
    ``path=None``. Never raises — non-``str`` input is reported as a rejection,
    not a ``TypeError``.
    """
    if not isinstance(path, str):
        return ResolvedRelativePath(None, f"Path must be a string, got {type(path).__name__}")
    if path.startswith("/"):
        return ResolvedRelativePath(None, f"Relative path must not be absolute: {path!r}")
    canonical = normalize_relative_path(path)
    valid, reason = validate_relative_path(canonical)
    if not valid:
        return ResolvedRelativePath(None, reason)
    return ResolvedRelativePath(RelativePath._brand(canonical), None)


# ---------------------------------------------------------------------------
# Normalization and validation
# ---------------------------------------------------------------------------


def normalize_path(path: str) -> str:
    """Normalize a virtual filesystem path.

    A pure, idempotent, single-pass transform: NFC-folds Unicode, makes the path
    absolute, strips per-segment whitespace, and drops empty/``.`` segments while
    resolving ``..`` (clamped at the root). Surrounding whitespace on a segment is
    insignificant, so ``/a/ b `` and ``/a/b`` collapse to the same canonical path.
    Always returns a normalized path; structural rejection is the separate job of
    :func:`validate_path`.
    """
    if not path:
        return "/"
    resolved: list[str] = []
    for raw in unicodedata.normalize("NFC", path).split("/"):
        segment = raw.strip()
        if not segment or segment == ".":
            continue
        if segment == "..":
            if resolved:
                resolved.pop()
            continue
        resolved.append(segment)
    return "/" + "/".join(resolved)


def validate_path(path: str) -> tuple[bool, str]:
    """Check the structural correctness of a path, returning ``(ok, reason)``.

    Rejects null bytes, control characters, lone surrogates, invisible
    bidi/zero-width/format characters, over-length paths, over-length segments,
    nested ``__meta__`` frames, and metadata paths that violate the namespace
    grammar (malformed or descended-past endpoints). Expects a
    :func:`normalize_path`-d path so the checks apply to the canonical form that
    gets stored (the gate normalizes before calling).
    """
    reason = _forbidden_char_reason(path)
    if reason is not None:
        return False, f"Path contains {reason}"

    if len(path) > MAX_PATH_LENGTH:
        return False, f"Path too long (max {MAX_PATH_LENGTH} characters)"

    if path == "/":
        return True, ""

    segments = path.split("/")[1:]
    if segments.count(META_SEGMENT) > 1:
        return False, f"Path contains nested '{META_SEGMENT}' segments"
    for segment in segments:
        if len(segment) > MAX_SEGMENT_LENGTH:
            return False, f"Path segment too long (max {MAX_SEGMENT_LENGTH}): '{segment[:40]}...'"

    if _under_meta_root(path):
        reason = _meta_grammar_reason(path)
        if reason is not None:
            return False, reason

    return True, ""


def normalize_relative_path(path: str) -> str:
    """Normalize a relative path.

    A pure, idempotent transform mirroring :func:`normalize_path` without
    absolutizing: NFC-folds Unicode, strips per-segment whitespace, and drops
    empty and ``.`` segments. ``..`` is *preserved* — there is no root to clamp
    it against, so :func:`validate_relative_path` rejects it. The result carries
    no leading slash; structural rejection is the separate job of
    :func:`validate_relative_path`.
    """
    segments = [segment.strip() for segment in unicodedata.normalize("NFC", path).split("/")]
    return "/".join(segment for segment in segments if segment and segment != ".")


def validate_relative_path(path: str) -> tuple[bool, str]:
    """Check the structural correctness of a canonical relative path.

    Rejects the empty path, ``..`` segments (which would climb out of the join
    root), over-length paths and segments, and the same null/control/surrogate/
    format characters :func:`validate_path` rejects. Expects a
    :func:`normalize_relative_path`-d path (the gate normalizes before calling).
    """
    if not path:
        return False, "Relative path must not be empty"
    reason = _forbidden_char_reason(path)
    if reason is not None:
        return False, f"Path contains {reason}"
    if len(path) > MAX_PATH_LENGTH:
        return False, f"Path too long (max {MAX_PATH_LENGTH} characters)"
    for segment in path.split("/"):
        if segment == "..":
            return False, "Relative path must not contain '..' segments"
        if len(segment) > MAX_SEGMENT_LENGTH:
            return False, f"Path segment too long (max {MAX_SEGMENT_LENGTH}): '{segment[:40]}...'"
    return True, ""


# ---------------------------------------------------------------------------
# Meta path construction
# ---------------------------------------------------------------------------


def chunk_path(file_path: Path, chunk_name: str, version: int) -> Path:
    """Build a chunk path under the hidden root metadata tree.

    Chunks are tied to the owning file's version:
    ``.../__meta__/chunks/<version>/<chunk_name>``. The result is re-gated, so a
    bad ``chunk_name`` or ``version`` raises here rather than downstream.
    """
    base = _validate_file_base(file_path)
    _validate_name(chunk_name, "chunk_name")
    _validate_version(version, "version")
    return Path(f"{METADATA_ROOT}{base}/{META_SEGMENT}/chunks/{version}/{chunk_name}")


def version_path(file_path: Path, version_number: int) -> Path:
    """Build a version path under the hidden root metadata tree."""
    base = _validate_file_base(file_path)
    _validate_version(version_number, "version_number")
    return Path(f"{METADATA_ROOT}{base}/{META_SEGMENT}/versions/{version_number}")


def validate_edge_endpoint(path: Path, label: str) -> Path:
    """Validate *path* as a canonical, non-metadata edge endpoint.

    Edge endpoints are user-space entities, never reserved ``/.vfs`` paths — so
    any metadata path is rejected outright (mirrors :func:`_validate_file_base`).
    """
    if path in {"/", METADATA_ROOT}:
        msg = f"{label} must not be root or reserved metadata root"
        raise ValueError(msg)
    if path.is_meta:
        msg = f"{label} must not be a metadata path: {path}"
        raise ValueError(msg)
    _reject_embedded_meta_segment(path, label)
    return path


def edge_out_path(source: Path, target: Path, edge_type: str) -> Path:
    """Build the canonical writable edge projection path."""
    src = validate_edge_endpoint(source, "source")
    tgt = validate_edge_endpoint(target, "target")
    _validate_name(edge_type, "edge_type")
    return Path(f"{METADATA_ROOT}{src}/{META_SEGMENT}/edges/out/{edge_type}/{tgt.lstrip('/')}")


def edge_in_path(source: Path, target: Path, edge_type: str) -> Path:
    """Build the inverse readable edge projection path."""
    src = validate_edge_endpoint(source, "source")
    tgt = validate_edge_endpoint(target, "target")
    _validate_name(edge_type, "edge_type")
    return Path(f"{METADATA_ROOT}{tgt}/{META_SEGMENT}/edges/in/{edge_type}/{src.lstrip('/')}")


# ---------------------------------------------------------------------------
# Agent namespace construction
# ---------------------------------------------------------------------------


def tool_path(name: str) -> Path:
    """Build a tool's unit directory: ``/.agents/tools/<name>`` (``kind="tool"``).

    The directory is the tool; its ``TOOL.md`` manifest is a plain indexable file.
    """
    _validate_name(name, "tool name")
    return Path(f"{AGENTS_ROOT}/tools/{name}")


def skill_path(name: str) -> Path:
    """Build a skill's unit directory: ``/.agents/skills/<name>`` (``kind="skill"``)."""
    _validate_name(name, "skill name")
    return Path(f"{AGENTS_ROOT}/skills/{name}")


def tool_manifest_path(name: str) -> Path:
    """Build the indexable manifest path ``/.agents/tools/<name>/TOOL.md``."""
    return tool_path(name).joinpath(TOOL_MANIFEST)


def skill_manifest_path(name: str) -> Path:
    """Build the indexable manifest path ``/.agents/skills/<name>/SKILL.md``."""
    return skill_path(name).joinpath(SKILL_MANIFEST)


# ---------------------------------------------------------------------------
# Path decomposition
# ---------------------------------------------------------------------------


class EdgeParts(NamedTuple):
    source: Path
    target: Path
    edge_type: str
    direction: Literal["out", "in"]


class _EdgePathParts(NamedTuple):
    owner_root: str
    direction: Literal["out", "in"]
    edge_type: str
    embedded_path: str


def decompose_edge(path: Path) -> EdgeParts | None:
    """Extract source, target, type, and direction from an edge path.

    Takes a canonical :class:`Path` and does not re-normalize.
    """
    split = _split_edge_path(path)
    if split is None:
        return None

    # Re-gate both endpoints through the public constructor; branding is
    # reserved for resolve_path and db-load.
    owner = Path(_canonical_endpoint_path(split.owner_root))
    embedded = Path(split.embedded_path)
    if split.direction == "out":
        return EdgeParts(
            source=owner,
            target=embedded,
            edge_type=split.edge_type,
            direction="out",
        )
    return EdgeParts(
        source=embedded,
        target=owner,
        edge_type=split.edge_type,
        direction="in",
    )


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------


def compute_parent_file(path: Path) -> Path | None:
    """Return the owning file for a chunk, version, or edge meta path, else ``None``.

    Chunks, versions, and edges all hang off a file under ``__meta__``, so they
    resolve to that file. Plain files and directories have no parent file and
    return ``None``. Takes a canonical :class:`Path` and returns one.
    """
    if path.kind not in {"chunk", "version", "edge"}:
        return None
    # A chunk/version/edge kind is only returned for a path under /.vfs that
    # carries a /__meta__ frame, so the marker is always present after stripping.
    stripped = path[len(METADATA_ROOT) :]
    marker = stripped.find(f"/{META_SEGMENT}")
    return Path(stripped[:marker] or "/")


def compute_parent_dir(path: Path) -> Path:
    """Return the literal parent directory used by the projected namespace."""
    return split_path(path)[0]


def parse_kind(path: Path) -> ObjectKind:
    """Detect the entity kind from a canonical path.

    Metadata markers are only meaningful inside the reserved ``/.vfs`` tree; an
    ordinary path that merely embeds ``__meta__`` segments is a plain file or
    directory. Chunks are version-addressed (``chunks/<version>/<name>``), so a
    bare ``chunks/<version>`` is the version-scoped directory, not a chunk.

    Takes a :class:`Path` (canonical by construction) and does not re-normalize.
    """
    if is_meta_path(path):
        if _is_projected_edge_path(path):
            return "edge"
        chunk_tail = _meta_family_tail(path, "chunks")
        if chunk_tail is not None:
            return "chunk" if len(chunk_tail) >= 2 else "directory"
        version_tail = _meta_family_tail(path, "versions")
        if version_tail is not None:
            return "version" if version_tail else "directory"
        return "directory"

    agent_kind = _agent_namespace_kind(path)
    if agent_kind is not None:
        return agent_kind

    _, name = split_path(path)
    if not name:
        return "directory"

    if name.startswith("."):
        return "file"

    dot = name.rfind(".")
    if dot > 0:
        return "file"

    if name.lower() in _EXTENSIONLESS_FILES_LOWER:
        return "file"

    return "directory"


def extract_extension(path: Path) -> str | None:
    """Return the lowercased trailing file extension, or ``None``.

    Takes a canonical :class:`Path`; the return is an extension, not a path.
    """
    _, name = split_path(path)
    if not name:
        return None
    dot = name.rfind(".")
    if dot <= 0:
        return None
    ext = name[dot + 1 :].lower()
    if not ext or len(ext) > 32:
        return None
    return ext


def split_path(path: Path) -> tuple[Path, str]:
    """Split a path into ``(directory, name)``, the directory re-minted as ``Path``."""
    if path == "/":
        return Path("/"), ""
    directory, name = posixpath.split(path)
    return Path(directory), name


def is_meta_path(path: Path) -> bool:
    """Return whether *path* lies within the reserved ``/.vfs`` tree.

    Takes a canonical :class:`Path` and does not re-normalize.
    """
    return _under_meta_root(path)


def check_mutable_path(path: Path, *, kind: str | None = None) -> tuple[bool, str]:
    """Check that *path* is a mutable target, returning ``(ok, reason)``.

    A namespace-grammar check, not a permission check: ordinary paths are valid
    targets, but the reserved ``/.vfs`` tree admits mutations only at the
    machine-authored endpoint shapes (chunks, versions, canonical out-edges)
    and the reserved directory skeleton — never arbitrary content,
    inverse-edge projections, or the roots. Takes a :class:`Path`, which is
    canonical by construction — so ``/.vfs/..`` cannot reach here as anything
    other than the ``/`` it normalizes to.

    Two adjacent concerns live elsewhere: whether the caller *may* mutate
    (principal permissions), and whether a kind's dependents are minted
    correctly (e.g. a chunk arriving with its file + version) — the latter is
    the entry-creation chokepoint's job, not this path check's.
    """
    if path == "/":
        return False, "Cannot mutate root path"

    if not is_meta_path(path):
        return True, ""

    if path == METADATA_ROOT:
        return False, "Cannot mutate reserved metadata root '/.vfs'"

    inferred_kind = kind or path.kind
    if inferred_kind in {"chunk", "version"}:
        return True, ""
    if inferred_kind == "edge":
        edge = decompose_edge(path)
        if edge is None or edge.direction == "out":
            return True, ""
        return False, "Cannot write directly to inverse edge paths; write the canonical edges/out path instead"

    if _is_reserved_metadata_directory(path):
        return True, ""

    return False, f"Cannot create arbitrary content in reserved metadata space: {path}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _forbidden_char_reason(text: str) -> str | None:
    """Return why *text* contains a forbidden code point, or ``None`` if clean.

    Shared by :func:`validate_path` and :func:`_validate_name` so a whole path and
    a single name segment reject the same null/control/surrogate/format characters.
    """
    if "\x00" in text:
        return "null bytes"
    for ch in text:
        code = ord(ch)
        if (0x01 <= code <= 0x1F) or code == 0x7F or (0x80 <= code <= 0x9F):
            return f"control character: U+{code:04X}"
        if 0xD800 <= code <= 0xDFFF:
            return f"lone surrogate: U+{code:04X}"
        if code in _FORBIDDEN_FORMAT_CHARS:
            return f"disallowed format/bidi character: U+{code:04X}"
    return None


def _under_meta_root(value: str) -> bool:
    """Whether a *canonical* string lies in the reserved ``/.vfs`` tree.

    The normalization-free str primitive behind :func:`is_meta_path`, also used
    by the internal parsing layer (which holds canonical-but-unbranded slices).
    """
    return value == METADATA_ROOT or value.startswith(METADATA_ROOT + "/")


def _is_canonical_version(value: str) -> bool:
    """Whether *value* is a canonical positive-integer segment (no leading zeros)."""
    return value.isascii() and value.isdigit() and value == str(int(value)) and int(value) >= 1


def _meta_grammar_reason(path: str) -> str | None:
    """Reason a ``/.vfs`` path violates the metadata grammar, or ``None`` if valid.

    Valid forms are the skeleton directories above an endpoint and the complete
    endpoints: ``chunks/<int>/<name>``, ``versions/<int>``, and
    ``edges/<out|in>/<type>/<target...>``. Endpoints are terminal (chunks and
    versions admit no descendants); versions are canonical positive integers.
    Edges keep a multi-segment target, so the tail past ``<type>`` is opaque. A
    meta frame must have a non-empty owner before it.
    """
    segments = [segment for segment in path[len(METADATA_ROOT) :].split("/") if segment]
    if META_SEGMENT not in segments:
        return None  # an owner directory above the frame (or /.vfs itself)
    frame_pos = segments.index(META_SEGMENT)
    if frame_pos == 0:
        return f"Metadata path requires an owner before '{META_SEGMENT}'"
    tail = segments[frame_pos + 1 :]
    if not tail:
        return None  # a bare '.../__meta__' reserved directory
    family, rest = tail[0], tail[1:]

    if family == "chunks":
        if rest and not _is_canonical_version(rest[0]):
            return f"Chunk version must be a positive integer: '{rest[0]}'"
        if len(rest) > 2:
            return f"Chunk endpoints have no descendants: {path}"
        return None
    if family == "versions":
        if rest and not _is_canonical_version(rest[0]):
            return f"Version must be a positive integer: '{rest[0]}'"
        if len(rest) > 1:
            return f"Version endpoints have no descendants: {path}"
        return None
    if family == "edges":
        if rest and rest[0] not in EDGE_DIRECTION_SET:
            return f"Edge direction must be 'out' or 'in': '{rest[0]}'"
        return None
    return f"Unknown metadata family '{family}' under {META_SEGMENT}"


def _validate_name(value: str, label: str) -> str:
    """Validate that *value* is a safe, non-empty, single path segment.

    Rejects empties, ``/``, the traversal names ``.``/``..``, and the same
    null/control/surrogate/format characters :func:`validate_path` rejects — so a
    segment a builder embeds can never re-point the path or fail the gate later.
    """
    if not value or not value.strip():
        msg = f"{label} must not be empty"
        raise ValueError(msg)
    if "/" in value:
        msg = f"{label} must not contain '/': {value}"
        raise ValueError(msg)
    if value in {".", ".."}:
        msg = f"{label} must not be '.' or '..': {value}"
        raise ValueError(msg)
    reason = _forbidden_char_reason(value)
    if reason is not None:
        msg = f"{label} contains {reason}"
        raise ValueError(msg)
    return value


def _validate_version(value: int, label: str) -> int:
    """Validate that *value* is a positive ``int`` (rejecting ``bool``/``float``)."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{label} must be an int, got {type(value).__name__}"
        raise ValueError(msg)
    if value < 1:
        msg = f"{label} must be >= 1, got {value}"
        raise ValueError(msg)
    return value


def _reject_embedded_meta_segment(normalized: str, label: str) -> None:
    """Reject a base/endpoint that contains a reserved ``__meta__`` segment.

    Building metadata on top of such a path would yield a nested ``__meta__``
    frame, which the gate rejects and which corrupts edge/chunk decomposition.
    """
    if META_SEGMENT in normalized.split("/"):
        msg = f"{label} must not contain a reserved metadata segment '{META_SEGMENT}'"
        raise ValueError(msg)


def _validate_file_base(path: Path) -> Path:
    """Reject root, reserved, or metadata bases for file metadata.

    Takes a canonical :class:`Path`; only the namespace rules a ``Path``
    does not itself imply are checked here.
    """
    if path in {"/", METADATA_ROOT}:
        msg = f"Base path must not be root or reserved metadata root: {path}"
        raise ValueError(msg)
    if path.is_meta:
        msg = f"Base path must not be a metadata path: {path}"
        raise ValueError(msg)
    _reject_embedded_meta_segment(path, "Base path")
    return path


def _split_edge_path(path: str) -> _EdgePathParts | None:
    """Parse the edge frame in *path*, treating the suffix as opaque.

    Anchored to the reserved ``/.vfs`` tree, and to whichever edge frame appears
    *first* in the path — direction is read by position, so an ``edges/out``
    substring embedded in an inverse-edge target cannot flip the direction.
    """
    if not path.startswith(METADATA_ROOT + "/"):
        return None
    best = None
    for direction in EDGE_DIRECTIONS:
        marker = f"/{META_SEGMENT}/edges/{direction}/"
        idx = path.find(marker)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, direction, marker)
    if best is None:
        return None
    idx, direction, marker = best
    owner_root = path[:idx]
    rest = path[idx + len(marker) :]
    slash = rest.find("/")
    if slash < 0:
        return None
    edge_type = rest[:slash]
    embedded = rest[slash + 1 :]
    if not edge_type or not embedded:
        return None
    return _EdgePathParts(
        owner_root=owner_root,
        direction=direction,
        edge_type=edge_type,
        embedded_path="/" + embedded,
    )


def _split_nested_endpoint(path: str) -> str | None:
    """Return the chunk/version endpoint root if *path* lies within one.

    Chunks are version-addressed (``chunks/<version>/<name>``), so the
    endpoint spans two segments; versions (``versions/<N>``) span one.
    Anything deeper (an edge or descendant) collapses to the endpoint root.
    """
    if not path.startswith(METADATA_ROOT + "/"):
        return None
    for family, depth in (("chunks", 2), ("versions", 1)):
        marker = f"/{META_SEGMENT}/{family}/"
        idx = path.find(marker)
        if idx < 0:
            continue
        start = idx + len(marker)
        segments = path[start:].split("/")
        return path[:start] + "/".join(segments[:depth])
    return None


def _canonical_endpoint_path(path: str) -> str:
    """Return the canonical endpoint represented by *path*."""
    normalized = normalize_path(path)
    if not _under_meta_root(normalized):
        return normalized
    if normalized == METADATA_ROOT:
        msg = "Reserved metadata root is not a canonical endpoint"
        raise ValueError(msg)

    nested = _split_nested_endpoint(normalized)
    if nested is not None:
        return nested

    stripped = normalized[len(METADATA_ROOT) :]
    return stripped


def _is_reserved_metadata_directory(path: str) -> bool:
    if not _under_meta_root(path):
        return False

    reserved_suffixes = (
        f"/{META_SEGMENT}",
        f"/{META_SEGMENT}/chunks",
        f"/{META_SEGMENT}/versions",
        f"/{META_SEGMENT}/edges",
        f"/{META_SEGMENT}/edges/out",
        f"/{META_SEGMENT}/edges/in",
    )
    return any(path.endswith(suffix) for suffix in reserved_suffixes)


def _meta_family_tail(path: str, family: str) -> list[str] | None:
    """Return the non-empty segments after ``/__meta__/<family>/``, or ``None``.

    Used to gauge endpoint completeness (a chunk needs ``<version>/<name>``).
    """
    marker = f"/{META_SEGMENT}/{family}/"
    idx = path.find(marker)
    if idx < 0:
        return None
    tail = path[idx + len(marker) :]
    return [segment for segment in tail.split("/") if segment]


def _is_projected_edge_path(path: str) -> bool:
    return _split_edge_path(path) is not None


def _agent_namespace_kind(path: str) -> ObjectKind | None:
    """Kind for the reserved ``/.agents`` capability namespace, else ``None``.

    The root is a directory (its dotfile leaf would otherwise read as a file); a
    unit directory directly under a family — ``/.agents/tools/<name>`` →
    ``tool``, ``/.agents/skills/<name>`` → ``skill`` — takes the family kind.
    Family roots and anything deeper return ``None``, so they fall through to the
    ordinary rules and a ``TOOL.md``/``SKILL.md`` manifest stays a plain file.
    """
    if path == AGENTS_ROOT:
        return "directory"
    if not path.startswith(AGENTS_ROOT + "/"):
        return None
    segments = [segment for segment in path[len(AGENTS_ROOT) :].split("/") if segment]
    if len(segments) == 2:
        return AGENT_FAMILY_TO_KIND.get(segments[0])
    return None
