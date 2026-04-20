"""Path utilities for VFS's ``/.vfs/.../__meta__/...`` namespace.

The canonical metadata layout is rooted at ``/.vfs`` and mirrors the
logical user path before crossing a reserved ``__meta__`` boundary.

Examples:

    /src/auth.py                                              file
    /.vfs/src/auth.py/__meta__/chunks/login                   chunk
    /.vfs/src/auth.py/__meta__/versions/3                     version
    /.vfs/src/auth.py/__meta__/edges/out/imports/src/util.py  edge
"""

from __future__ import annotations

import posixpath
import unicodedata
from typing import Literal, NamedTuple


class EdgeParts(NamedTuple):
    source: str
    target: str
    edge_type: str
    direction: Literal["out", "in"]


ObjectKind = Literal["file", "directory", "chunk", "version", "edge", "api"]
MetadataKind = Literal["chunks", "versions", "edges", "apis"]

METADATA_ROOT = "/.vfs"
META_SEGMENT = "__meta__"
EDGE_DIRECTIONS = ("out", "in")
EDGE_DIRECTION_SET = frozenset(EDGE_DIRECTIONS)

METADATA_KIND_MAP: dict[MetadataKind, ObjectKind] = {
    "chunks": "chunk",
    "versions": "version",
    "edges": "edge",
    "apis": "api",
}

MARKER_KINDS: dict[str, ObjectKind] = {
    "/__meta__/chunks/": "chunk",
    "/__meta__/versions/": "version",
    "/__meta__/edges/out/": "edge",
    "/__meta__/edges/in/": "edge",
    "/__meta__/apis/": "api",
}

METADATA_MARKERS = tuple(MARKER_KINDS.keys())

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


# ---------------------------------------------------------------------------
# Normalization and validation
# ---------------------------------------------------------------------------


def normalize_path(path: str) -> str:
    """Normalize a virtual filesystem path."""
    if not path:
        return "/"
    path = unicodedata.normalize("NFC", path).strip()
    if not path.startswith("/"):
        path = "/" + path
    path = posixpath.normpath(path)
    if path.startswith("//"):
        path = path[1:]
    return path


def split_path(path: str) -> tuple[str, str]:
    """Split a normalized path into ``(directory, name)``."""
    path = normalize_path(path)
    if path == "/":
        return "/", ""
    return posixpath.split(path)


def validate_path(path: str) -> tuple[bool, str]:
    """Validate structural correctness of a path."""
    if "\x00" in path:
        return False, "Path contains null bytes"

    for ch in path:
        code = ord(ch)
        if (0x01 <= code <= 0x1F) or code == 0x7F or (0x80 <= code <= 0x9F):
            return False, f"Path contains control character: U+{code:04X}"

    if len(path) > 4096:
        return False, "Path too long (max 4096 characters)"

    normalized = normalize_path(path)
    if normalized == "/":
        return True, ""

    segments = normalized.split("/")[1:]
    for segment in segments:
        if len(segment) > 255:
            return False, f"Path segment too long (max 255): '{segment[:40]}...'"

    return True, ""


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------


def is_meta_root_path(path: str) -> bool:
    """Return whether *path* is exactly within the reserved ``/.vfs`` tree."""
    normalized = normalize_path(path)
    return normalized == METADATA_ROOT or normalized.startswith(METADATA_ROOT + "/")


def meta_root(path: str) -> str:
    """Return the canonical metadata root for a valid endpoint path."""
    normalized = normalize_path(path)
    if normalized in {"/", METADATA_ROOT}:
        msg = f"Reserved path is not a valid metadata endpoint: {path}"
        raise ValueError(msg)
    if is_meta_root_path(normalized):
        if normalized == METADATA_ROOT:
            msg = f"Reserved path is not a valid metadata endpoint: {path}"
            raise ValueError(msg)
        if _is_projected_edge_path(normalized):
            msg = f"Projected edge paths are not valid metadata endpoints: {path}"
            raise ValueError(msg)
        if _is_reserved_metadata_directory(normalized):
            msg = f"Reserved metadata directory is not a valid endpoint: {path}"
            raise ValueError(msg)
        return normalized
    return f"{METADATA_ROOT}{normalized}"


def endpoint_root(path: str) -> str:
    """Return the owning endpoint root for *path*."""
    normalized = normalize_path(path)

    edge_parts = _split_edge_path(normalized)
    if edge_parts is not None:
        return edge_parts.owner_root

    if not is_meta_root_path(normalized):
        return normalized

    nested = _split_nested_endpoint(normalized)
    if nested is not None:
        return nested

    return normalized


def base_path(path: str) -> str:
    """Return the owning file path for a metadata path, else *path* itself."""
    normalized = normalize_path(path)
    if normalized == METADATA_ROOT:
        return "/"

    if not is_meta_root_path(normalized):
        return normalized

    stripped = normalized[len(METADATA_ROOT) :]
    if not stripped:
        return "/"

    marker = stripped.find(f"/{META_SEGMENT}")
    if marker < 0:
        return stripped
    return stripped[:marker] or "/"


def owning_file_path(path: str) -> str:
    """Alias for :func:`base_path` with a more explicit name."""
    return base_path(path)


def parent_path(path: str) -> str:
    """Return the literal parent path used by the projected namespace."""
    normalized = normalize_path(path)
    return split_path(normalized)[0]


def validate_mutation_path(path: str, *, kind: str | None = None) -> tuple[bool, str]:
    """Validate that a caller is not mutating reserved metadata space arbitrarily."""
    normalized = normalize_path(path)
    if normalized == "/":
        return False, "Cannot mutate root path"

    if not is_meta_root_path(normalized):
        return True, ""

    if normalized == METADATA_ROOT:
        return False, "Cannot mutate reserved metadata root '/.vfs'"

    inferred_kind = kind or parse_kind(normalized)
    if inferred_kind in {"chunk", "version", "api"}:
        return True, ""
    if inferred_kind == "edge":
        edge = decompose_edge(normalized)
        if edge is None or edge.direction == "out":
            return True, ""
        return False, "Cannot write directly to inverse edge paths; write the canonical edges/out path instead"

    if _is_reserved_metadata_directory(normalized):
        return True, ""

    if normalized.endswith(f"/{META_SEGMENT}"):
        return True, ""

    if normalized.startswith(METADATA_ROOT + "/") and f"/{META_SEGMENT}/" not in normalized:
        return False, f"Cannot create arbitrary content in reserved metadata space: {path}"

    return False, f"Cannot create arbitrary content in reserved metadata space: {path}"


# ---------------------------------------------------------------------------
# Kind detection
# ---------------------------------------------------------------------------


def parse_kind(path: str) -> ObjectKind:
    """Detect the entity kind from a path."""
    path = normalize_path(path)

    if _is_projected_edge_path(path):
        return "edge"

    nested = _split_nested_endpoint(path)
    if nested is not None:
        if "/__meta__/chunks/" in nested or nested.endswith("/__meta__/chunks"):
            return "chunk"
        if "/__meta__/versions/" in nested or nested.endswith("/__meta__/versions"):
            return "version"

    for marker, kind in MARKER_KINDS.items():
        if marker in path:
            return kind

    if path == METADATA_ROOT:
        return "directory"
    if is_meta_root_path(path):
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


def extract_extension(path: str) -> str | None:
    """Return the lowercased trailing file extension, or ``None``."""
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


# ---------------------------------------------------------------------------
# Path construction
# ---------------------------------------------------------------------------


def _validate_name(value: str, label: str) -> str:
    """Validate that *value* is a non-empty, single-segment name."""
    if not value or not value.strip():
        msg = f"{label} must not be empty"
        raise ValueError(msg)
    if "/" in value:
        msg = f"{label} must not contain '/': {value}"
        raise ValueError(msg)
    return value


def _validate_file_base(path: str) -> str:
    """Normalize *path* and reject metadata / reserved bases for file metadata."""
    normalized = normalize_path(path)
    if normalized in {"/", METADATA_ROOT}:
        msg = f"Base path must not be root or reserved metadata root: {path}"
        raise ValueError(msg)
    if is_meta_root_path(normalized):
        msg = f"Base path must not be a metadata path: {path}"
        raise ValueError(msg)
    return normalized


def _validate_edge_endpoint(path: str, label: str) -> str:
    """Validate *path* as a canonical edge endpoint path."""
    normalized = normalize_path(path)
    if normalized in {"/", METADATA_ROOT}:
        msg = f"{label} must not be root or reserved metadata root"
        raise ValueError(msg)
    if is_meta_root_path(normalized):
        if _is_projected_edge_path(normalized):
            msg = f"{label} must not be a projected edge path: {path}"
            raise ValueError(msg)
        if _is_reserved_metadata_directory(normalized):
            msg = f"{label} must not be a reserved metadata directory: {path}"
            raise ValueError(msg)
    return normalized


def chunk_path(file_path: str, chunk_name: str) -> str:
    """Build a chunk path under the hidden root metadata tree."""
    base = _validate_file_base(file_path)
    _validate_name(chunk_name, "chunk_name")
    return f"{meta_root(base)}/{META_SEGMENT}/chunks/{chunk_name}"


def version_path(file_path: str, version_number: int) -> str:
    """Build a version path under the hidden root metadata tree."""
    base = _validate_file_base(file_path)
    if version_number < 1:
        msg = f"version_number must be >= 1, got {version_number}"
        raise ValueError(msg)
    return f"{meta_root(base)}/{META_SEGMENT}/versions/{version_number}"


def edge_out_path(source: str, target: str, edge_type: str) -> str:
    """Build the canonical writable edge projection path."""
    src = _validate_edge_endpoint(source, "source")
    tgt = _validate_edge_endpoint(target, "target")
    _validate_name(edge_type, "edge_type")
    return f"{meta_root(src)}/{META_SEGMENT}/edges/out/{edge_type}/{tgt.lstrip('/')}"


def edge_in_path(source: str, target: str, edge_type: str) -> str:
    """Build the inverse readable edge projection path."""
    src = _validate_edge_endpoint(source, "source")
    tgt = _validate_edge_endpoint(target, "target")
    _validate_name(edge_type, "edge_type")
    return f"{meta_root(tgt)}/{META_SEGMENT}/edges/in/{edge_type}/{src.lstrip('/')}"


def api_path(mount: str, action: str) -> str:
    """Build an API endpoint path under the hidden metadata tree."""
    base = _validate_file_base(mount)
    _validate_name(action, "action")
    return f"{meta_root(base)}/{META_SEGMENT}/apis/{action}"


# ---------------------------------------------------------------------------
# Path decomposition
# ---------------------------------------------------------------------------


class _EdgePathParts(NamedTuple):
    owner_root: str
    direction: Literal["out", "in"]
    edge_type: str
    embedded_path: str


def decompose_edge(path: str) -> EdgeParts | None:
    """Extract source, target, type, and direction from an edge path."""
    normalized = normalize_path(path)
    split = _split_edge_path(normalized)
    if split is None:
        return None

    owner = _canonical_endpoint_path(split.owner_root)
    if split.direction == "out":
        return EdgeParts(
            source=owner,
            target=split.embedded_path,
            edge_type=split.edge_type,
            direction="out",
        )
    return EdgeParts(
        source=split.embedded_path,
        target=owner,
        edge_type=split.edge_type,
        direction="in",
    )


# ---------------------------------------------------------------------------
# User scoping
# ---------------------------------------------------------------------------

_UNSAFE_USER_ID_CHARS = frozenset("/\\@\0")


def validate_user_id(user_id: str) -> tuple[bool, str]:
    """Validate that *user_id* is safe for use as a path segment."""
    if not user_id or not user_id.strip():
        return False, "user_id must not be empty"
    if len(user_id) > 255:
        return False, "user_id too long (max 255 characters)"
    if ".." in user_id:
        return False, "user_id must not contain '..'"
    for ch in user_id:
        if ch in _UNSAFE_USER_ID_CHARS:
            return False, f"user_id contains unsafe character: {ch!r}"
    return True, ""


def scope_path(path: str, user_id: str) -> str:
    """Prepend ``/{user_id}`` to *path* for per-user storage."""
    valid, err = validate_user_id(user_id)
    if not valid:
        msg = f"Invalid user_id: {err}"
        raise ValueError(msg)
    path = normalize_path(path)
    if path == "/":
        return f"/{user_id}"
    return f"/{user_id}{path}"


def unscope_path(path: str, user_id: str) -> str:
    """Strip the ``/{user_id}`` prefix from a storage path."""
    normalized = normalize_path(path)
    prefix = f"/{user_id}"
    edge = decompose_edge(normalized)
    if edge is not None:
        source = _strip_user_prefix(edge.source, prefix)
        target = _strip_user_prefix(edge.target, prefix)
        if edge.direction == "out":
            return edge_out_path(source, target, edge.edge_type)
        return edge_in_path(source, target, edge.edge_type)
    if is_meta_root_path(normalized) and normalized != METADATA_ROOT:
        rooted = normalized[len(METADATA_ROOT) :] or "/"
        return METADATA_ROOT + _strip_user_prefix(rooted, prefix)
    return _strip_user_prefix(normalized, prefix)


def _strip_user_prefix(path: str, prefix: str) -> str:
    """Strip *prefix* from the start of *path*."""
    if path == prefix:
        return "/"
    if path.startswith(prefix + "/"):
        return path[len(prefix) :]
    msg = f"Path {path!r} does not start with user prefix {prefix!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_edge_path(path: str) -> _EdgePathParts | None:
    """Parse the first edge frame in *path*, treating the suffix as opaque."""
    for direction in EDGE_DIRECTIONS:
        marker = f"/{META_SEGMENT}/edges/{direction}/"
        idx = path.find(marker)
        if idx < 0:
            continue
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
    return None


def _canonical_endpoint_path(path: str) -> str:
    """Return the canonical endpoint represented by *path*."""
    normalized = normalize_path(path)
    if not is_meta_root_path(normalized):
        return normalized
    if normalized == METADATA_ROOT:
        msg = "Reserved metadata root is not a canonical endpoint"
        raise ValueError(msg)

    nested = _split_nested_endpoint(normalized)
    if nested is not None:
        return nested

    stripped = normalized[len(METADATA_ROOT) :]
    if not stripped:
        msg = "Reserved metadata root is not a canonical endpoint"
        raise ValueError(msg)
    return stripped


def _split_nested_endpoint(path: str) -> str | None:
    """Return the chunk/version endpoint root if *path* lies within one."""
    for family in ("chunks", "versions"):
        marker = f"/{META_SEGMENT}/{family}/"
        idx = path.find(marker)
        if idx < 0:
            continue
        rest = path[idx + len(marker) :]
        slash = rest.find("/")
        if slash < 0:
            return path
        return path[: idx + len(marker) + slash]
    return None


def _is_projected_edge_path(path: str) -> bool:
    return _split_edge_path(path) is not None


def _is_reserved_metadata_directory(path: str) -> bool:
    if not is_meta_root_path(path):
        return False

    reserved_suffixes = (
        f"/{META_SEGMENT}",
        f"/{META_SEGMENT}/chunks",
        f"/{META_SEGMENT}/versions",
        f"/{META_SEGMENT}/edges",
        f"/{META_SEGMENT}/edges/out",
        f"/{META_SEGMENT}/edges/in",
        f"/{META_SEGMENT}/apis",
    )
    return any(path.endswith(suffix) for suffix in reserved_suffixes)
