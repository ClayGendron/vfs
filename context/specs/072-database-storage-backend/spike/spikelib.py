"""Shared helpers for the 072 grep-index spike.

Corpus config, gram extraction (numpy-vectorized, mirroring the live
``code_grams`` semantics: newline-normalize -> NFC -> casefold -> UTF-8 ->
sliding 3-byte grams), a bulk vectorized delta+varint codec for posting
blobs, and the delta+gamma codec copied from ``src2/vfs/postings.py``
(the v1 spec encoding) for size/speed comparison.

Varint blob layout used by the spike index: gaps from a cursor at -1
(first gap = doc0 + 1), LSB-first 7-bit groups with a continuation high
bit, no terminator (doc_count bounds the decode).
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path("/Users/claygendron/Git/Repos")

CORPUS_REPOS = [
    "linux",
    "gitlabhq",
    "freebsd-src",
    "postgres",
    "sqlalchemy",
    "langchain",
    "fastapi",
    "letta",
    "minio",
    "juicefs",
    "seaweedfs",
    "opendal",
    "zoekt",
    "spicedb",
    "jackrabbit-oak",
    "starlette",
]

TEXT_EXTENSIONS = {
    ".c", ".h", ".cc", ".cpp", ".hpp", ".py", ".go", ".rs", ".rb", ".js",
    ".jsx", ".ts", ".tsx", ".java", ".kt", ".scala", ".sh", ".bash", ".pl",
    ".sql", ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".json",
    ".proto", ".erb", ".haml", ".vue", ".css", ".scss", ".el", ".vim",
    ".mk", ".cmake", ".s", ".asm",
}

MAX_FILE_BYTES = 2 << 20        # zoekt SizeMax
MAX_LINE_BYTES = 2000           # codesearch maxLineLen: reject probable-minified
MAX_DOC_GRAMS = 20_000          # both engines' "probably not text" threshold
CHUNK_TARGET_BYTES = 4096       # split large files into ~4K line-aligned docs

DATA_DIR = Path(
    os.environ.get(
        "SPIKE_DATA",
        "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/"
        "9e872841-9a6e-4447-b1d6-49e64fbae415/scratchpad/spike-data",
    )
)

GAMMA_TERMINATOR_BITS = 9  # gamma(16) = 2*floor(log2 16)+1 bits, the 0-remap


# ---------------------------------------------------------------------------
# Gram extraction (mirrors code_grams.fold_content + normalize_content)
# ---------------------------------------------------------------------------

def fold_norm_bytes(content: str) -> bytes:
    """Folded, normalized UTF-8 byte stream — the indexed gram stream."""
    if "\r" in content:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.isascii():
        content = unicodedata.normalize("NFC", content)
    content = content.casefold()
    # casefold can reintroduce non-NFC sequences in exotic cases; the live
    # module encodes post-fold via normalize_content, which re-applies NFC.
    if not content.isascii():
        content = unicodedata.normalize("NFC", content)
    return content.encode("utf-8")


def unique_grams_np(data: bytes) -> np.ndarray:
    """Distinct 24-bit byte trigram keys of *data*, sorted, as uint32."""
    if len(data) < 3:
        return np.empty(0, dtype=np.uint32)
    a = np.frombuffer(data, dtype=np.uint8)
    g = (
        (a[:-2].astype(np.uint32) << 16)
        | (a[1:-1].astype(np.uint32) << 8)
        | a[2:].astype(np.uint32)
    )
    return np.unique(g)


# ---------------------------------------------------------------------------
# Bulk delta+varint codec (numpy-vectorized)
# ---------------------------------------------------------------------------

def gaps_from_segmented_docs(docs: np.ndarray, seg_starts: np.ndarray) -> np.ndarray:
    """Per-segment gaps with cursor -1 semantics, over one concatenated array.

    docs is the concatenation of per-gram sorted doc-id arrays; seg_starts
    holds each segment's start index. Within a segment: gap0 = doc0 + 1,
    gap_i = doc_i - doc_{i-1}.
    """
    gaps = np.empty_like(docs)
    gaps[0] = docs[0] + 1
    gaps[1:] = docs[1:] - docs[:-1]
    gaps[seg_starts[1:]] = docs[seg_starts[1:]] + 1
    return gaps


def varint_encode_segments(
    gaps: np.ndarray, seg_starts: np.ndarray
) -> tuple[bytes, np.ndarray]:
    """Encode concatenated per-segment gaps; return (blob_bytes, seg_byte_offsets).

    seg_byte_offsets has len(seg_starts) + 1 entries; segment i's blob is
    blob[off[i]:off[i+1]].
    """
    v = gaps.astype(np.uint64)
    exp = np.frexp(v.astype(np.float64))[1]  # bit_length; exact below 2**53
    nbytes = np.maximum((exp + 6) // 7, 1).astype(np.int64)
    ends = np.cumsum(nbytes)
    starts = ends - nbytes
    out = np.zeros(int(ends[-1]), dtype=np.uint8)
    max_w = int(nbytes.max())
    for j in range(max_w):
        mask = nbytes > j
        idx = starts[mask] + j
        chunk = ((v[mask] >> np.uint64(7 * j)) & np.uint64(0x7F)).astype(np.uint8)
        cont = (nbytes[mask] - 1 > j).astype(np.uint8) << 7
        out[idx] = chunk | cont
    seg_ends = np.empty(len(seg_starts), dtype=np.int64)
    seg_ends[:-1] = starts[seg_starts[1:]]
    seg_ends[-1] = int(ends[-1])
    seg_offsets = np.empty(len(seg_starts) + 1, dtype=np.int64)
    seg_offsets[0] = 0
    seg_offsets[1:] = seg_ends
    return out.tobytes(), seg_offsets


def varint_decode_np(blob: bytes) -> np.ndarray:
    """Decode one varint posting blob to its sorted doc-id array (uint32)."""
    a = np.frombuffer(blob, dtype=np.uint8)
    is_end = (a & 0x80) == 0
    ends = np.flatnonzero(is_end)
    starts = np.empty_like(ends)
    starts[0] = 0
    starts[1:] = ends[:-1] + 1
    widths = ends - starts + 1
    vals = np.zeros(len(ends), dtype=np.uint64)
    for j in range(int(widths.max())):
        mask = widths > j
        vals[mask] |= (a[starts[mask] + j].astype(np.uint64) & np.uint64(0x7F)) << np.uint64(7 * j)
    return (np.cumsum(vals) - 1).astype(np.uint32)


def varint_decode_py(blob: bytes) -> list[int]:
    """Pure-Python decode of the same varint blob."""
    ids: list[int] = []
    doc = -1
    val = 0
    shift = 0
    for byte in blob:
        val |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            doc += val
            ids.append(doc)
            val = 0
            shift = 0
    return ids


def gamma_bytes_analytic(gaps: np.ndarray, n_segments: int) -> int:
    """Total delta+gamma blob bytes for these segments, computed analytically.

    Applies the codec's zero-remap (values >= 16 shift up by one) and adds
    the 9-bit zero terminator per segment; each segment's blob is padded to
    a whole byte.
    """
    v = gaps.astype(np.int64)
    v = np.where(v >= 16, v + 1, v)
    exp = np.frexp(v.astype(np.float64))[1] - 1
    bits = int((2 * exp + 1).sum()) + n_segments * GAMMA_TERMINATOR_BITS
    # Padding to byte boundaries is per-segment; approximate with +4 bits each.
    return (bits + n_segments * 4) // 8


def gamma_bytes_per_segment(gaps: np.ndarray) -> int:
    """Exact gamma blob size in bytes for one segment's gaps."""
    v = np.where(gaps >= 16, gaps + 1, gaps).astype(np.int64)
    exp = np.frexp(v.astype(np.float64))[1] - 1
    bits = int((2 * exp + 1).sum()) + GAMMA_TERMINATOR_BITS
    return (bits + 7) // 8


# ---------------------------------------------------------------------------
# Delta+gamma codec — copied from src2/vfs/postings.py (the v1 spec encoding)
# ---------------------------------------------------------------------------

_DELTA_ZERO_ENC = 16
_MAX_DOC_ID = (1 << 63) - 1


class PostingCorruptionError(ValueError):
    """Raised when a posting blob fails to decode (truncated, bad terminator)."""


class GammaWriter:
    """LSB-first Elias-gamma bit writer."""

    __slots__ = ("_b", "_nb", "_out")

    def __init__(self) -> None:
        self._out = bytearray()
        self._b = 0
        self._nb = 0

    def _flush_bits(self) -> None:
        while self._nb >= 8:
            self._out.append(self._b & 0xFF)
            self._b >>= 8
            self._nb -= 8

    def _write_bits(self, x: int) -> None:
        if x <= 0:
            msg = f"gamma write of non-positive value {x}"
            raise ValueError(msg)
        lg = x.bit_length() - 1
        mantissa = x & ((1 << lg) - 1)
        self._nb += lg
        if self._nb >= 8:
            self._flush_bits()
        self._b |= 1 << self._nb
        self._nb += 1
        self._b |= mantissa << self._nb
        self._nb += lg
        if self._nb >= 8:
            self._flush_bits()

    def write_value(self, x: int) -> None:
        if x == 0:
            x = _DELTA_ZERO_ENC
        elif x >= _DELTA_ZERO_ENC:
            x += 1
        self._write_bits(x)

    def finish(self) -> bytes:
        self._flush_bits()
        if self._nb > 0:
            self._out.append(self._b & 0xFF)
            self._b = 0
            self._nb = 0
        return bytes(self._out)


class GammaReader:
    """LSB-first Elias-gamma bit reader."""

    __slots__ = ("_b", "_d", "_nb", "_pos")

    def __init__(self, data: bytes) -> None:
        self._d = data
        self._pos = 0
        self._b = 0
        self._nb = 0

    def _next_byte(self) -> int:
        if self._pos >= len(self._d):
            raise PostingCorruptionError("posting blob truncated")
        byte = self._d[self._pos]
        self._pos += 1
        return byte

    def _read_bits(self) -> int:
        lg = 0
        while self._b == 0:
            lg += self._nb
            self._b = self._next_byte()
            self._nb = 8
        nb = ((self._b & -self._b).bit_length()) - 1
        lg += nb
        if lg > 64:
            raise PostingCorruptionError("posting gamma value exceeds 64 bits")
        self._b >>= nb + 1
        self._nb -= nb + 1
        x = 1 << lg
        shift = 0
        while self._nb < lg:
            x |= self._b << shift
            shift += self._nb
            lg -= self._nb
            self._b = self._next_byte()
            self._nb = 8
        x |= (self._b & ((1 << lg) - 1)) << shift
        self._b >>= lg
        self._nb -= lg
        return x

    def read_value(self) -> int:
        i = self._read_bits()
        if i == _DELTA_ZERO_ENC:
            return 0
        if i > _DELTA_ZERO_ENC:
            return i - 1
        return i

    def at_end(self) -> bool:
        return self._pos >= len(self._d) and self._b == 0


def encode_postings_gamma(doc_ids: list[int] | np.ndarray) -> bytes:
    """Encode a sorted doc-id list as a delta+gamma blob (src2 semantics)."""
    writer = GammaWriter()
    prev = -1
    for doc_id in doc_ids:
        d = int(doc_id)
        gap = d - prev
        if gap <= 0:
            msg = f"doc_ids must be sorted ascending and distinct (got gap {gap})"
            raise ValueError(msg)
        writer.write_value(gap)
        prev = d
    writer.write_value(0)
    return writer.finish()


def decode_postings_gamma(blob: bytes, doc_count: int) -> list[int]:
    """Decode a delta+gamma blob into its doc-id list (src2 semantics)."""
    if doc_count < 0:
        raise PostingCorruptionError(f"negative doc_count {doc_count}")
    reader = GammaReader(blob)
    doc_id = -1
    ids: list[int] = []
    for _ in range(doc_count):
        gap = reader.read_value()
        if gap <= 0:
            raise PostingCorruptionError("non-positive gap in posting list")
        doc_id += gap
        ids.append(doc_id)
    if reader.read_value() != 0:
        raise PostingCorruptionError("posting list missing zero terminator")
    return ids
