"""Seam to the Rust engine (``vfs._native``) — required, protocol-gated.

vfs has one engine. The compiled extension is built into every wheel by
maturin, and importing this module without it — or with a build whose
``PROTOCOL_VERSION`` does not match — raises ``ImportError`` naming the
fix. There is no pure-Python runtime fallback; readable reference
implementations live in ``tests/support/oracles`` as parity referees.

    from vfs.native import extension

    extension().tokenize(text)

Per-surface dispatch lives with each surface's **owner**, never here —
this module imports nothing from the rest of vfs, so any module may
import it without ordering hazards. ``vfs.models.code_grams`` owns the
gram gate, ``vfs.models.postings`` the builder, ``vfs.models.lexical``
the tokenizer, lexical builder and scorer, ``vfs.pattern_matching`` the
match law. The one surface served directly here is structure-aware
chunking.
"""

from __future__ import annotations

from typing import Any, Final

try:
    from vfs import _native as _ext
except ImportError as error:  # pragma: no cover - pinned by a subprocess test
    message = (
        "vfs requires its compiled extension vfs._native; reinstall the wheel "
        "or run `uv sync --reinstall-package vfs-py`"
    )
    raise ImportError(message) from error

EXPECTED_PROTOCOL: Final = 4

if _ext.PROTOCOL_VERSION != EXPECTED_PROTOCOL:  # pragma: no cover - pinned by a subprocess test
    message = (
        f"vfs._native speaks protocol {_ext.PROTOCOL_VERSION} but this vfs expects "
        f"{EXPECTED_PROTOCOL}; run `uv sync --reinstall-package vfs-py`"
    )
    raise ImportError(message)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


def extension() -> Any:
    """The live extension module — the handle every surface owner dispatches through.

    Callers treat the module as opaque and feature-test nothing: protocol
    acceptance already happened at import.
    """
    return _ext


# ---------------------------------------------------------------------------
# Structure-aware chunk spans
# ---------------------------------------------------------------------------


def structure_grammars() -> frozenset[str]:
    """Grammar names the engine can split structurally."""
    return frozenset(_ext.supported_grammars())


def chunk_spans(
    bodies: list[tuple[bytes, str]], *, chunk_size: int
) -> list[list[tuple[int, int, int, int, bool]] | None]:
    """Structure-aware chunk spans per ``(utf-8 body, grammar)`` pair.

    Bodies parse in parallel off the GIL. Per body: ``None`` when the
    structure path cannot serve it — unknown grammar, language load
    failure, a body over 4 GiB — and the caller falls back to its
    character splitter; otherwise ``(start, end, line_start, line_end,
    oversized)`` rows of byte offsets and 1-based lines. The caller
    slices text, filters whitespace-only chunks, and re-splits oversized
    leaves.
    """
    return _ext.chunk_spans(bodies, chunk_size=chunk_size)
