"""The markdown reference extractor — link text to candidate in-mount paths.

:func:`extract_links` hands a batch of document bodies to the engine's
markdown kernel, which walks the tree-sitter-markdown block and inline
trees and returns every destination it holds — inline links, images,
reference definitions, and code spans shaped like a path — with the
line that holds it. This module then keeps the in-mount-shaped ones (a
URL, a protocol-relative ``//`` and an anchor-only destination are not
references; fragments and queries come off) and :func:`link_candidates`
turns one reference into the in-mount paths it may denote, in
resolution order. Storage probes those against the live tree and mints
the ``links`` edges; nothing here touches a session.

Example::

    >>> [refs] = extract_links(["See [the spec](../specs/138/spec.md) and `base.py`."])
    >>> [ref.dest for ref in refs]
    ['../specs/138/spec.md', 'base.py']
    >>> link_candidates(Path("/context/research/memo.md"), "../specs/138/spec.md")
    ('/context/specs/138/spec.md', '/specs/138/spec.md')
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

from vfs import native
from vfs.paths import Path

if TYPE_CHECKING:
    from collections.abc import Sequence

# The extractor version stamped beside the body hash on every entry; a bump
# re-extracts every document once, the chunker's generation law.
LINK_GENERATION: Final = 1

# The edge type the markdown extractor mints — one segment, never ``fs``.
LINK_EDGE_TYPE: Final = "links"

# Extensions the markdown extractor reads, as ``Path.ext`` spells them.
MARKDOWN_EXTENSIONS: Final = frozenset({"md", "markdown"})

# The referring line is stored folded to one line of at most this many chars.
MAX_LINK_CONTEXT_LENGTH: Final = 256

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


class LinkRef(NamedTuple):
    """One reference found in a document: its destination text and the referring line."""

    dest: str
    context: str


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def link_generation() -> str:
    """The extractor generation stamped onto stored link state."""
    return f"md:{LINK_GENERATION}"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_links(bodies: Sequence[str]) -> list[list[LinkRef]]:
    """Every in-mount-shaped reference per body, in document order.

    The engine parses the batch in parallel; per body the rows are
    filtered to in-mount shapes and their fragments and queries dropped.
    """
    parsed = native.markdown_refs([body.encode() for body in bodies])
    batch: list[list[LinkRef]] = []
    for rows in parsed:
        refs: list[LinkRef] = []
        for raw, context in rows:
            dest = clean_dest(raw)
            if dest is not None:
                refs.append(LinkRef(dest, context))
        batch.append(refs)
    return batch


def clean_dest(raw: str) -> str | None:
    """The path part of a destination, or ``None`` when it is not an in-mount reference."""
    dest = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not dest or dest.startswith("//") or _SCHEME.match(dest):
        return None
    return dest


# ---------------------------------------------------------------------------
# Resolution candidates
# ---------------------------------------------------------------------------


def link_candidates(document: Path, dest: str) -> tuple[Path, ...]:
    """The in-mount paths *dest* may denote from *document*, in resolution order.

    A destination starting with ``/`` is root-anchored and yields one
    candidate; any other yields the document-directory join first and
    the root join second. ``..`` clamps at the root, as every vfs path
    does. A candidate that is structurally invalid, the root itself, or
    inside the reserved metadata scope is dropped; a trailing ``/`` is
    insignificant, so a directory reference resolves like a file's.
    """
    dest = dest.rstrip("/") or dest
    joins = (dest,) if dest.startswith("/") else (f"{document.parent_dir}/{dest}", f"/{dest}")
    candidates: list[Path] = []
    for joined in joins:
        try:
            candidate = Path(joined)
        except ValueError:
            continue
        if candidate == "/" or candidate.is_meta or candidate in candidates:
            continue
        candidates.append(candidate)
    return tuple(candidates)
