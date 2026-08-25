"""Seam to the optional Rust engine (``vfs._native``), with the pure fallback.

The pendulum model: every wheel ships the complete pure-Python
implementation, and the compiled ``vfs._native`` module rides beside it
where a wheel exists. This module is the one place that decides which
engine serves — it try-imports the extension, accepts it only when its
``PROTOCOL_VERSION`` matches, warns once and falls back otherwise, and
exposes the active engine for tests and diagnostics::

    from vfs.native import active_core, extension

    active_core()  # "rust" | "python"
    extension()  # the live module, or None on the pure engine

Per-surface dispatch lives with each surface's **owner**, never here —
this module imports nothing from the rest of vfs, so any module may
import it without ordering hazards. ``vfs.models.code_grams`` owns the
folded stream and the gram gate, ``vfs.models.postings`` the builder,
``vfs.pattern_matching`` the match law; each holds its pure reference
implementation beside its dispatch. The one surface served directly
here is structure-aware chunking, whose pure "fallback" is *absence by
contract*: without the extension there is no tree-sitter at all, and
chunking degrades to the character splitter — a declared divergence,
not an equivalent engine.

Setting ``VFS_PURE_PYTHON=1`` in the environment before import forces
the pure engine (the CI fallback leg's switch).
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Final, Literal

try:
    from vfs import _native as _ext
except ImportError:  # pragma: no cover - exercised only in extension-less installs
    _ext = None  # ty: ignore[invalid-assignment]

EXPECTED_PROTOCOL: Final = 3


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

    The handle every surface owner dispatches through. Callers treat the
    module as opaque and feature-test nothing: protocol acceptance
    already happened at import.
    """
    return _active


# ---------------------------------------------------------------------------
# Structure-aware chunk spans
# ---------------------------------------------------------------------------


def structure_grammars() -> frozenset[str]:
    """Grammar names the active engine can split structurally.

    Empty on the pure engine: structure-aware chunking is a native
    capability by contract, and pure installs take the character
    splitter for every extension (the declared degradation).
    """
    if _active is None:
        return frozenset()
    return frozenset(_active.supported_grammars())


def chunk_spans(
    bodies: list[tuple[bytes, str]], *, chunk_size: int
) -> list[list[tuple[int, int, int, int, bool]] | None]:
    """Structure-aware chunk spans per ``(utf-8 body, grammar)`` pair.

    Bodies parse in parallel off the GIL on the Rust engine. Per body:
    ``None`` when the structure path cannot serve it — unknown grammar,
    language load failure, a body over 4 GiB, or the pure engine, where
    every body is ``None`` — and the caller falls back to its character
    splitter; otherwise ``(start, end, line_start, line_end, oversized)``
    rows of byte offsets and 1-based lines. The caller slices text,
    filters whitespace-only chunks, and re-splits oversized leaves.
    """
    if _active is None:
        return [None] * len(bodies)
    return _active.chunk_spans(bodies, chunk_size=chunk_size)
