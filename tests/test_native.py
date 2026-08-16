"""The engine seam: selection, protocol gate, and Rust/pure parity.

Parity is the seam's soundness law: both engines must produce
byte-identical posting rows and identical gate counts for the same
folded stream, so a wheel with the extension and a wheel without it
build the same index. The parity classes run every case against both
builders directly; the Rust legs skip themselves when the extension is
absent (the pure reference is then the only engine, and the rest of the
suite already exercises it).
"""

from __future__ import annotations

import os
import random
from types import SimpleNamespace

import pytest

import vfs.native as native
from vfs.models.code_grams import iter_byte_trigrams, pack_gram, unique_code_grams
from vfs.models.postings import decode_postings, encode_postings
from vfs.native import (
    EXPECTED_PROTOCOL,
    PurePostingsBuilder,
    _resolve,
    active_core,
    folded_bytes,
    postings_builder,
)

# The pure-fallback CI leg runs this same suite with VFS_PURE_PYTHON=1, so
# expectations derive from the resolved engine, not extension importability.
FORCED_PURE = bool(os.environ.get("VFS_PURE_PYTHON"))

try:
    from vfs import _native
except ImportError:  # pragma: no cover - extension-less environment
    _native = None  # ty: ignore[invalid-assignment]

needs_rust = pytest.mark.skipif(_native is None, reason="vfs._native extension not built")


def builders() -> list:
    """Both engines' builders where available; the pure one always."""
    engines = [PurePostingsBuilder()]
    if _native is not None:
        engines.append(_native.PostingsBuilder())
    return engines


def drain_rows(builder, byte_cap: int = 1 << 20) -> list[tuple[int, bytes, int]]:
    rows: list[tuple[int, bytes, int]] = []
    while (batch := builder.next_batch(byte_cap)) is not None:
        assert batch, "batches are never empty by contract"
        rows.extend(batch)
    return rows


CORPORA: dict[str, list[tuple[int, str]]] = {
    "plain": [(1, "hello world\n"), (7, "world peace\n"), (9, "hello again\n")],
    "duplicates-within-doc": [(2, "abcabcabc"), (5, "abc")],
    "short-and-empty": [(1, ""), (2, "ab"), (3, "abc"), (4, "\n\n\n\n")],
    "unicode": [(1, "naïve café — ☂☂☂"), (2, "İstanbul ısı I i"), (3, "καλημέρα κόσμε")],  # noqa: RUF001
    "crlf": [(1, "a\r\nb\r\nc"), (2, "a\nb\nc")],
    "sparse-ids": [(3, "xyz"), (200, "xyz"), (1_000_000, "xyz abc"), (2**62, "abc")],
}


class TestParity:
    """Byte-identical rows and identical gate counts across engines."""

    @pytest.mark.parametrize("name", sorted(CORPORA))
    @needs_rust
    def test_rows_identical(self, name: str) -> None:
        docs = [(doc_id, folded_bytes(text)) for doc_id, text in CORPORA[name]]
        results = []
        for builder in builders():
            builder.add_docs(docs)
            results.append(drain_rows(builder))
        assert results[0] == results[1]

    @needs_rust
    def test_fuzz_rows_identical(self) -> None:
        rng = random.Random(103)
        alphabet = "ab\n\r\x00é☂ iıİxyz"  # noqa: RUF001
        doc_id = 0
        docs = []
        for _ in range(200):
            doc_id += rng.randint(1, 50)
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
            docs.append((doc_id, folded_bytes(text)))
        pure, rust = PurePostingsBuilder(), _native.PostingsBuilder()
        for start in range(0, len(docs), 37):
            chunk = docs[start : start + 37]
            pure.add_docs(chunk)
            rust.add_docs(chunk)
        assert drain_rows(pure, byte_cap=97) == drain_rows(rust, byte_cap=97)

    @needs_rust
    def test_distinct_gram_count_parity(self) -> None:
        cases = [b"", b"ab", b"abc", b"abcabc", b"abcdefghij", bytes(range(256)) * 3, folded_bytes("İstanbul ısı")]  # noqa: RUF001
        for data in cases:
            exact = len(set(iter_byte_trigrams(data)))
            for cap in (0, 1, 5, 1 << 24):
                rust = _native.distinct_gram_count(data, cap)
                pure_seen: set[int] = set()
                for gram in iter_byte_trigrams(data):
                    pure_seen.add(gram)
                    if len(pure_seen) > cap:
                        break
                assert rust == len(pure_seen), (data[:16], cap)
                if exact <= cap:
                    assert rust == exact

    @needs_rust
    def test_blobs_decode_to_the_fed_doc_ids(self) -> None:
        builder = _native.PostingsBuilder()
        builder.add_docs([(3, b"abc"), (200, b"abcd"), (2**62, b"abc")])
        rows = {gram: blob for gram, blob, _count in drain_rows(builder)}
        assert list(decode_postings(rows[pack_gram(*b"abc")])) == [3, 200, 2**62]
        assert list(decode_postings(rows[pack_gram(*b"bcd")])) == [200]
        assert rows[pack_gram(*b"abc")] == encode_postings([3, 200, 2**62])


class TestBuilderContract:
    """Contract behaviors both engines must share, run against each."""

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_non_increasing_doc_ids_refused(self, index: int) -> None:
        engines = builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        builder.add_docs([(5, b"abc")])
        for bad in (5, 4, 0, -3):
            with pytest.raises(ValueError, match="strictly increasing"):
                builder.add_docs([(bad, b"xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_add_after_drain_refused(self, index: int) -> None:
        engines = builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        builder.add_docs([(1, b"abc")])
        assert builder.next_batch(1 << 20)
        with pytest.raises(ValueError):
            builder.add_docs([(2, b"xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_empty_builder_drains_nothing(self, index: int) -> None:
        engines = builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        assert engines[index].next_batch(1 << 20) is None

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_tiny_byte_cap_still_progresses(self, index: int) -> None:
        engines = builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        builder.add_docs([(1, b"abcdefgh")])
        batches = []
        while (batch := builder.next_batch(1)) is not None:
            batches.append(batch)
        assert [len(b) for b in batches] == [1] * 6


class TestSeamSelection:
    """_resolve's acceptance rules and the diagnostics surface."""

    def test_active_core_matches_extension_presence(self) -> None:
        assert active_core() == ("python" if _native is None or FORCED_PURE else "rust")

    def test_postings_builder_comes_from_the_active_core(self) -> None:
        builder = postings_builder()
        if _native is None or FORCED_PURE:
            assert isinstance(builder, PurePostingsBuilder)
        else:
            assert isinstance(builder, _native.PostingsBuilder)

    def test_resolve_rejects_absent_extension(self) -> None:
        assert _resolve(None) is None

    def test_resolve_rejects_protocol_mismatch_with_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VFS_PURE_PYTHON", raising=False)
        stranger = SimpleNamespace(PROTOCOL_VERSION=EXPECTED_PROTOCOL + 1)
        with pytest.warns(RuntimeWarning, match="protocol"):
            assert _resolve(stranger) is None

    def test_resolve_accepts_protocol_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VFS_PURE_PYTHON", raising=False)
        speaker = SimpleNamespace(PROTOCOL_VERSION=EXPECTED_PROTOCOL)
        assert _resolve(speaker) is speaker

    def test_pure_python_env_forces_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VFS_PURE_PYTHON", "1")
        speaker = SimpleNamespace(PROTOCOL_VERSION=EXPECTED_PROTOCOL)
        assert _resolve(speaker) is None

    def test_dispatch_serves_pure_when_no_engine_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(native, "_active", None)
        assert native.active_core() == "python"
        assert isinstance(native.postings_builder(), PurePostingsBuilder)
        assert native.distinct_gram_count(b"abcabc", 10) == 3
        assert native.distinct_gram_count(b"abcdefgh", 3) == 4


class TestFoldedBytes:
    """The one folded stream both engines consume."""

    def test_matches_the_tokenizer_fold(self) -> None:
        for text in ("Hello\r\nWorld", "İstanbul ısı", "plain"):  # noqa: RUF001
            grams = set(iter_byte_trigrams(folded_bytes(text)))
            assert grams == unique_code_grams(text, folded=True)
