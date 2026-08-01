"""Canonical paths for the VFS namespace.

Every caller-supplied path enters through the gate — :class:`Path` (or
:func:`resolve_path` for a non-raising result) — which normalizes and validates
it into a canonical form safe to route and store. The namespace holds authored
content only — files and directories; derived per-file metadata (chunks,
versions, edges) is entry-scoped and addressed by owning file + discriminator,
never by a path. ``/.vfs`` is the reserved meta scope (trash, mount metadata) and
``/.agents`` the capability tree — both ordinary directories structurally.

Examples:

    /src/auth.py                     file
    /.vfs/trash/2026-07-18-10/x.txt  file (trash-side, meta scope)
    /.agents/tools/clone-repo        directory (a tool's unit)
    /.agents/skills/pdf-processing   directory (a skill's unit)
"""

from __future__ import annotations

import posixpath
import unicodedata
from typing import TYPE_CHECKING, Literal, NamedTuple

from pydantic_core import core_schema

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema


ObjectKind = Literal["file", "directory"]

MAX_PATH_LENGTH = 1024  # UTF-8 bytes (BSD/macOS PATH_MAX) — see Path docstring
MAX_SEGMENT_LENGTH = 255  # UTF-8 bytes (POSIX NAME_MAX)

METADATA_ROOT = "/.vfs"

# The conventional trash location: an ordinary meta subtree the delete
# verb reparents into — browsable, writable, no scope of its own.
TRASH_ROOT = f"{METADATA_ROOT}/trash"

# Reserved user-space capability root. Unlike METADATA_ROOT (derived, no indexable
# content), /.agents holds real files, so a tool's/skill's manifest indexes normally.
AGENTS_ROOT = "/.agents"
AGENT_FAMILIES = frozenset({"tools", "skills"})
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
    exceeds ``MAX_PATH_LENGTH`` (1024 UTF-8 bytes — the BSD/macOS
    ``PATH_MAX``, the tightest major-OS floor) — including the outputs of
    ``with_mount`` / ``without_mount`` / ``joinpath``. This guarantees every
    path a ``Result`` returns is valid input to the next request
    (re-addressability). A rebase that would exceed the limit raises
    ``ValueError`` at the ``Path`` layer; the router's rebase seam
    (``Result.with_mount``) converts that per row into a classified
    ``ResultError`` — an over-long global path can therefore never be
    observed, raised, or stored anywhere in the system. Byte denomination
    also bounds every engine's index key: a lawful path always fits under
    the tightest declared ``key_byte_budget``.

    Consequence for deep mounts: a child-local path is only reachable through
    a parent if mount prefix and local path fit 1024 bytes together. Content
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
    def name(self) -> str:
        """Leaf segment (mirrors ``VFSEntry.name``)."""
        return split_path(self).name

    @property
    def kind(self) -> ObjectKind:
        """Structural kind from path markers (mirrors ``VFSEntry.kind``)."""
        return parse_kind(self)

    @property
    def ext(self) -> str | None:
        """Lowercased trailing extension, else ``None``.

        Derived from the path alone, never kind-gated: a directory named
        ``foo.bar/`` carries ``ext = "bar"`` (POSIX parity).
        """
        return extract_extension(self)

    @property
    def is_meta(self) -> bool:
        """Whether this path is under the reserved ``/.vfs`` tree."""
        return is_meta_path(self)

    @property
    def depth(self) -> int:
        """Segment depth: 0 for the root, else the path's segment count."""
        return 0 if self == "/" else str(self).count("/")

    @property
    def is_mutable_target(self) -> bool:
        """Namespace-grammar half of writability — NOT a permission check.

        ``/`` and the ``/.vfs`` root are never mutable; every other path is a
        lawful write target. Use the function ``check_mutable_path`` when the
        rejection *reason* is needed.
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
        if rebase_overflows(mount, self):
            msg = (
                f"Rebased path too long (max {MAX_PATH_LENGTH} bytes): "
                f"mount {mount!r} + local path of {byte_length(self)} bytes"
            )
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
        return posixpath.basename(self)

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


def byte_length(text: str) -> int:
    """UTF-8 bytes of *text* — the denomination of every path limit."""
    return len(text.encode())


def rebase_overflows(mount: str, local: str) -> bool:
    """True when rebasing *local* under *mount* would exceed the path limit.

    The one owner of the rebase-overflow rule: a root on either side is
    an identity rebase and never overflows; otherwise the concatenation
    must fit ``MAX_PATH_LENGTH`` bytes.
    """
    if mount == "/" or local == "/":
        return False
    return byte_length(mount) + byte_length(local) > MAX_PATH_LENGTH


def validate_path(path: str) -> tuple[bool, str]:
    """Check the structural correctness of a path, returning ``(ok, reason)``.

    Rejects null bytes, control characters, lone surrogates, invisible
    bidi/zero-width/format characters, over-length paths, and over-length
    segments. Expects a :func:`normalize_path`-d path so the checks apply to
    the canonical form that gets stored (the gate normalizes before calling).
    """
    reason = _forbidden_char_reason(path)
    if reason is not None:
        return False, f"Path contains {reason}"

    if byte_length(path) > MAX_PATH_LENGTH:
        return False, f"Path too long (max {MAX_PATH_LENGTH} bytes)"

    if path == "/":
        return True, ""

    for segment in path.split("/")[1:]:
        if byte_length(segment) > MAX_SEGMENT_LENGTH:
            return False, f"Path segment too long (max {MAX_SEGMENT_LENGTH} bytes): '{segment[:40]}...'"

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


def validate_segment(value: str, label: str) -> str:
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
    if byte_length(path) > MAX_PATH_LENGTH:
        return False, f"Path too long (max {MAX_PATH_LENGTH} bytes)"
    for segment in path.split("/"):
        if segment == "..":
            return False, "Relative path must not contain '..' segments"
        if byte_length(segment) > MAX_SEGMENT_LENGTH:
            return False, f"Path segment too long (max {MAX_SEGMENT_LENGTH} bytes): '{segment[:40]}...'"
    return True, ""


# ---------------------------------------------------------------------------
# Agent namespace construction
# ---------------------------------------------------------------------------


def tool_path(name: str) -> Path:
    """Build a tool's unit directory: ``/.agents/tools/<name>``.

    The directory is the tool; its ``TOOL.md`` manifest is a plain indexable file.
    """
    validate_segment(name, "tool name")
    return Path(f"{AGENTS_ROOT}/tools/{name}")


def skill_path(name: str) -> Path:
    """Build a skill's unit directory: ``/.agents/skills/<name>``."""
    validate_segment(name, "skill name")
    return Path(f"{AGENTS_ROOT}/skills/{name}")


def tool_manifest_path(name: str) -> Path:
    """Build the indexable manifest path ``/.agents/tools/<name>/TOOL.md``."""
    return tool_path(name).joinpath(TOOL_MANIFEST)


def skill_manifest_path(name: str) -> Path:
    """Build the indexable manifest path ``/.agents/skills/<name>/SKILL.md``."""
    return skill_path(name).joinpath(SKILL_MANIFEST)


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------


def compute_parent_dir(path: Path) -> Path:
    """Return the literal parent directory used by the projected namespace."""
    return split_path(path).directory


def parse_kind(path: Path) -> ObjectKind:
    """Detect ``file`` or ``directory`` from a canonical path.

    Structural spots classify ``directory`` outright — the ``/.vfs`` meta root
    and the ``/.agents`` skeleton — since their dotted or extensionless names
    must not fall into the name lottery. Everything else, including everything
    deeper under ``/.vfs``, takes the ordinary rules: dotted or well-known
    extensionless leaves are files, the rest directories.

    Takes a :class:`Path` (canonical by construction) and does not re-normalize.
    """
    if path == METADATA_ROOT or is_reserved_directory(path):
        return "directory"

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


def is_reserved_directory(path: Path) -> bool:
    """Whether *path* is a structurally-directory reserved spot.

    True for the root, the ``/.vfs`` meta root, and the ``/.agents`` skeleton
    (root, family roots, unit directories). These classify ``directory``
    regardless of their leaf's shape, and content aimed at them is a caller
    error rather than a reclassify-to-file.
    """
    if path in {"/", METADATA_ROOT, AGENTS_ROOT}:
        return True
    if not path.startswith(AGENTS_ROOT + "/"):
        return False
    family, *unit = path[len(AGENTS_ROOT) + 1 :].split("/")
    return len(unit) <= 1 and family in AGENT_FAMILIES


def extract_extension(path: Path) -> str | None:
    """Return the lowercased trailing file extension, or ``None``.

    Takes a canonical :class:`Path`; the return is an extension, not a
    path. A leading dot is not an extension marker: a pure dotfile name
    (``.txt``) carries no extension.
    """
    _, name = split_path(path)
    if not name:
        return None
    dot = name.rfind(".")
    if dot <= 0:
        return None
    return normalize_extension(name[dot + 1 :])


def normalize_extension(text: str) -> str | None:
    """The one extension law: lowercased *text*, or ``None`` when empty or >32 chars.

    Every producer of a stored or derived extension value runs through
    here, so comparisons against the ``ext`` column can never drift.
    """
    ext = text.lower()
    if not ext or len(ext) > 32:
        return None
    return ext


class SplitPath(NamedTuple):
    """A canonical path decomposed into its directory and leaf name."""

    directory: Path
    name: str


def split_path(path: Path) -> SplitPath:
    """Split a path into ``(directory, name)``, the directory re-minted as ``Path``."""
    if path == "/":
        return SplitPath(Path("/"), "")
    directory, name = posixpath.split(path)
    return SplitPath(Path(directory), name)


def is_meta_path(path: Path) -> bool:
    """Return whether *path* lies within the reserved ``/.vfs`` tree.

    Takes a canonical :class:`Path` and does not re-normalize.
    """
    return _under_meta_root(path)


def check_mutable_path(path: Path) -> tuple[bool, str]:
    """Check that *path* is a mutable target, returning ``(ok, reason)``.

    A namespace-grammar check, not a permission check: only the two roots are
    refused — ``/`` and the ``/.vfs`` meta root itself. Everything else,
    including paths inside the meta scope (trash-side writes are ordinary
    writes), is a lawful write target. Whether the caller *may* mutate is the
    principal-permission layer's concern, not this check's.
    """
    if path == "/":
        return False, "Cannot mutate root path"
    if path == METADATA_ROOT:
        return False, "Cannot mutate reserved metadata root '/.vfs'"
    return True, ""


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

    The normalization-free str primitive behind :func:`is_meta_path`.
    """
    return value == METADATA_ROOT or value.startswith(METADATA_ROOT + "/")


# The canonical root instance — minted once, after the gate it runs through.
ROOT = Path("/")
