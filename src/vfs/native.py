"""Seam to the optional Rust engine (``vfs._native``), with the pure fallback.

The pendulum model: every wheel ships the complete pure-Python
implementation, and the compiled ``vfs._native`` module rides beside it
where a wheel exists. This module is the one place that decides which
engine serves — it try-imports the extension, accepts it only when its
``PROTOCOL_VERSION`` matches, warns once and falls back otherwise, and
exposes the active engine for tests and diagnostics::

    from vfs.native import active_core, distinct_gram_count, postings_builder

    active_core()  # "rust" | "python"
    builder = postings_builder()  # same contract either way
    builder.add_docs([(doc_id, folded_bytes(content)), ...])
    while (rows := builder.next_batch(byte_cap)) is not None:
        ...  # gram-ordered (gram_key, blob, doc_count) rows

Both engines speak pre-folded bytes: callers prepare the stream with
:func:`folded_bytes` (fold, then newline-normalize and encode), so fold
policy lives in exactly one place — ``vfs.models.code_grams`` — and the
engines are byte-identical in output, pinned by the parity suite. Setting
``VFS_PURE_PYTHON=1`` in the environment before import forces the pure
engine (the CI fallback leg's switch).
"""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from vfs.models.code_grams import fold_content, iter_byte_trigrams, normalize_content
from vfs.models.postings import encode_postings

try:
    from vfs import _native as _ext
except ImportError:  # pragma: no cover - exercised only in extension-less installs
    _ext = None  # ty: ignore[invalid-assignment]

if TYPE_CHECKING:
    from vfs.models.code_grams import GramKey

EXPECTED_PROTOCOL: Final = 3


class PostingsBuilder(Protocol):
    """The one builder contract both engines implement.

    Docs are fed in strictly increasing doc-id order as pre-folded bytes;
    draining yields gram-ordered batches of ``(gram_key, blob, doc_count)``
    rows sliced by accumulated blob bytes (each batch carries at least one
    row). Feeding after the first drain raises ``ValueError``.
    """

    def add_docs(self, docs: list[tuple[int, bytes]]) -> None: ...

    def next_batch(self, byte_cap: int) -> list[tuple[int, bytes, int]] | None: ...


# ---------------------------------------------------------------------------
# Engine selection
# ---------------------------------------------------------------------------


def _resolve(ext: Any) -> Any | None:
    """Accept the extension only on an exact protocol match, else warn once."""
    if ext is None or os.environ.get("VFS_PURE_PYTHON"):
        return None
    if ext.PROTOCOL_VERSION != EXPECTED_PROTOCOL:
        message = (
            f"vfs._native speaks protocol {ext.PROTOCOL_VERSION} but this vfs expects "
            f"{EXPECTED_PROTOCOL}; using the pure-Python engine (reinstall to realign)"
        )
        warnings.warn(message, RuntimeWarning, stacklevel=2)
        return None
    return ext


_active = _resolve(_ext)


def active_core() -> Literal["rust", "python"]:
    """Which engine serves this process — for tests and diagnostics."""
    return "python" if _active is None else "rust"


def extension() -> Any | None:
    """The live extension module, or ``None`` on the pure engine.

    For seams that dispatch per call site (the grep matcher lives in
    ``vfs.pattern_matching``, which owns the match law and the pure
    reference implementation — it cannot be imported from here without a
    cycle). Callers treat the module as opaque and feature-test nothing:
    protocol acceptance already happened at import.
    """
    return _active


# ---------------------------------------------------------------------------
# Engine surface
# ---------------------------------------------------------------------------


def folded_bytes(content: str) -> bytes:
    """The folded, newline-normalized UTF-8 stream both engines consume."""
    return normalize_content(fold_content(content))


def distinct_gram_count(data: bytes, cap: int) -> int:
    """Distinct trigrams of *data*, early-exiting past *cap*.

    Any return value greater than *cap* means "over cap" — the exact count
    is not computed beyond that point.
    """
    if _active is not None:
        return _active.distinct_gram_count(data, cap)
    seen: set[GramKey] = set()
    for gram in iter_byte_trigrams(data):
        seen.add(gram)
        if len(seen) > cap:
            break
    return len(seen)


def postings_builder() -> PostingsBuilder:
    """A fresh posting-set builder from the active engine."""
    if _active is not None:
        return _active.PostingsBuilder()
    return PurePostingsBuilder()


class PurePostingsBuilder:
    """The reference builder: dict accumulation, then the reference codec.

    Peak memory holds every gram's raw doc-id list (the Rust engine holds
    only the compressed deltas); acceptable for the fallback path, whose
    contract is correctness, not the throughput target.
    """

    def __init__(self) -> None:
        self._postings: dict[GramKey, list[int]] = {}
        self._last_doc = 0
        self._rows: list[tuple[int, bytes, int]] | None = None
        self._cursor = 0

    def add_docs(self, docs: list[tuple[int, bytes]]) -> None:
        if self._rows is not None:
            raise ValueError("builder is already draining; create a fresh one")
        for doc_id, data in docs:
            if doc_id <= self._last_doc:
                message = f"doc ids must be strictly increasing and positive; got {doc_id} after {self._last_doc}"
                raise ValueError(message)
            self._last_doc = doc_id
            for gram in set(iter_byte_trigrams(data)):
                self._postings.setdefault(gram, []).append(doc_id)

    def next_batch(self, byte_cap: int) -> list[tuple[int, bytes, int]] | None:
        if self._rows is None:
            self._rows = [(gram, encode_postings(ids), len(ids)) for gram, ids in sorted(self._postings.items())]
            self._postings = {}
        if self._cursor >= len(self._rows):
            return None
        batch: list[tuple[int, bytes, int]] = []
        batch_bytes = 0
        while self._cursor < len(self._rows):
            row = self._rows[self._cursor]
            if batch and batch_bytes + len(row[1]) > byte_cap:
                break
            batch.append(row)
            batch_bytes += len(row[1])
            self._cursor += 1
        return batch
