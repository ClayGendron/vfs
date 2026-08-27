"""The engine seam: selection, protocol gate, and Rust/pure parity.

Parity is the seam's soundness law: both engines must produce
byte-identical posting rows and identical gate counts for the same
folded stream — and, for the lexical index, identical tokens, summary
and block rows, and scores — so a wheel with the extension and a wheel
without it build and rank the same index. The parity classes run every
case against both engines directly; the Rust legs skip themselves when
the extension is absent (the pure reference is then the only engine,
and the rest of the suite already exercises it).
"""

from __future__ import annotations

import os
import random
import re
import unicodedata
from types import SimpleNamespace

import numpy as np
import pytest

import vfs.native as native
from tests.support.lexical_fidelity import CORPUS, QUERIES
from vfs.models.code_grams import (
    distinct_gram_count,
    folded_bytes,
    iter_byte_trigrams,
    pack_gram,
    unique_code_grams,
)
from vfs.models.lexical import (
    BLOCK_SIZE,
    PureLexicalBuilder,
    ScoreBlock,
    decode_summary,
    lexical_builder,
    pure_score_blocks,
    pure_tokenize,
    score_blocks,
    tokenize,
)
from vfs.models.postings import (
    PurePostingsBuilder,
    decode_postings,
    encode_postings,
    postings_builder,
)
from vfs.native import (
    EXPECTED_PROTOCOL,
    _resolve,
    active_core,
    chunk_spans,
    structure_grammars,
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
        assert isinstance(postings_builder(), PurePostingsBuilder)
        assert distinct_gram_count(b"abcabc", 10) == 3
        assert distinct_gram_count(b"abcdefgh", 3) == 4


class TestChunkSeam:
    """The structure-aware chunk surface: native rows, pure absence."""

    def test_pure_engine_serves_no_structure_grammars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(native, "_active", None)
        assert native.structure_grammars() == frozenset()
        assert native.chunk_spans([(b"def f(): pass\n", "python")] * 3, chunk_size=8) == [None, None, None]

    @needs_rust
    def test_rust_engine_serves_the_registry(self) -> None:
        if FORCED_PURE:
            pytest.skip("VFS_PURE_PYTHON forces the pure engine")
        grammars = structure_grammars()
        assert {"python", "c", "rust", "markdown"} <= grammars

    @needs_rust
    def test_rows_carry_spans_lines_and_the_oversized_flag(self) -> None:
        if FORCED_PURE:
            pytest.skip("VFS_PURE_PYTHON forces the pure engine")
        body = b"def f(x):\n    return x + 1\n\n\ndef g(y):\n    return y * 2\n"
        (rows,) = chunk_spans([(body, "python")], chunk_size=32)
        assert rows is not None and len(rows) >= 2
        assert rows[0][0] == 0 and rows[-1][1] == len(body)
        assert rows[0][2] == 1  # 1-indexed lines
        assert all(not oversized for _s, _e, _ls, _le, oversized in rows)

    @needs_rust
    def test_unknown_grammar_rows_are_none(self) -> None:
        if FORCED_PURE:
            pytest.skip("VFS_PURE_PYTHON forces the pure engine")
        good = b"x = 1\n" * 400
        assert chunk_spans([(good, "no_such_grammar"), (good, "python")], chunk_size=64)[0] is None


# Lexical parity corpora: the fixture corpus, a shared term that spans
# blocks, and a fuzz alphabet of identifier shapes, folds and joiners.
_SHARED = "shared_term appears in every document of this run"
LEXICAL_CORPORA: dict[str, list[tuple[int, str]]] = {
    "fixture": [(10 + i, text) for i, text in enumerate(CORPUS.values())],
    "spanning": [(i, f"{_SHARED} plus filler{i % 5} {'x' * (i % 7)}") for i in range(1, BLOCK_SIZE * 2 + 3)],
    "unicode": [(1, "İstanbul ısı I i STRASSE Straße"), (2, "καλημέρα κόσμε XMLHttpRequest sha256Hash"), (3, "")],  # noqa: RUF001
    "sparse-ids": [(3, "alpha beta"), (200, "alpha"), (1_000_000, "beta gamma"), (2**62, "alpha beta gamma")],
}


def _fuzz_docs(seed: int, count: int) -> list[tuple[int, str]]:
    rng = random.Random(seed)
    alphabet = [
        "ab",
        "_",
        " ",
        "CD",
        "ef",
        "\n",
        "İ",
        "\u0131",
        "é",
        "ß",
        "0x9",
        "XMLHttpRequest",
        "sha256Hash",
        "getX",
        "1",
    ]
    docs = []
    doc_id = 0
    for _ in range(count):
        doc_id += rng.randint(1, 40)
        docs.append((doc_id, "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))))
    return docs


def _drain_lexical(builder) -> tuple[tuple[int, float], list, list]:
    stats = builder.finish()
    summaries: list = []
    while (batch := builder.next_df_batch(7)) is not None:
        assert batch
        summaries.extend(batch)
    rows: list = []
    while (batch := builder.next_batch(5)) is not None:
        assert batch
        rows.extend(batch)
    return stats, summaries, rows


def _score_blocks_for(query: str, summaries: list, rows: list) -> tuple[list[ScoreBlock], list[float]]:
    by_term = {row[0]: row for row in summaries}
    terms = [t for t in dict.fromkeys(pure_tokenize(query)) if t in by_term]
    idfs = [by_term[t][2] for t in terms]
    blocks: list[ScoreBlock] = []
    for index, term in enumerate(terms):
        summary = decode_summary(by_term[term][4])
        blocks.extend(
            ScoreBlock(index, float(summary.max_weights[row[1]]), row[3], row[4], row[5])
            for row in rows
            if row[0] == term
        )
    return blocks, idfs


class TestLexicalParity:
    """Identical tokens, rows and scores from both lexical engines."""

    @needs_rust
    @pytest.mark.parametrize("name", sorted(LEXICAL_CORPORA))
    def test_tokens_identical(self, name: str) -> None:
        for _doc_id, text in LEXICAL_CORPORA[name]:
            assert _native.tokenize(text) == pure_tokenize(text)

    @needs_rust
    def test_fuzz_tokens_identical(self) -> None:
        for _doc_id, text in _fuzz_docs(11, 500):
            assert _native.tokenize(text) == pure_tokenize(text), text

    @needs_rust
    def test_character_classes_match_the_interpreter(self) -> None:
        """The generated tables are this interpreter's classes wherever both
        assign the code point; an unassigned code point on either side is a
        Unicode-version drift, not a bug, and the versions must then differ."""
        flags = np.frombuffer(_native.lexical_char_classes(), dtype=np.uint8)
        points = np.array([cp for cp in range(0x110000) if not 0xD800 <= cp <= 0xDFFF])
        chars = [chr(cp) for cp in points]
        word = re.compile(r"\w")
        mine = np.zeros(0x110000, dtype=np.uint8)
        for flag, predicate in (
            (1, lambda ch: word.fullmatch(ch) is not None),
            (2, str.isupper),
            (4, str.islower),
            (8, str.isdigit),
            (16, lambda ch: unicodedata.category(ch) != "Cn"),
        ):
            mine[points[[predicate(ch) for ch in chars]]] |= flag
        differing = np.flatnonzero((flags ^ mine) & 0x0F)
        both_assigned = (flags[differing] & 16) & (mine[differing] & 16)
        assert not both_assigned.any(), differing[:10]
        folds = dict(_native.lexical_casefolds())
        for cp in points.tolist():
            ch = chr(cp)
            expected = ch.casefold()
            if folds.get(cp, ch) != expected:
                assert not (flags[cp] & 16 and mine[cp] & 16), hex(cp)
        if unicodedata.unidata_version == _native.LEXICAL_UNICODE_VERSION:
            assert differing.size == 0

    @needs_rust
    @pytest.mark.parametrize("name", sorted(LEXICAL_CORPORA))
    def test_rows_identical(self, name: str) -> None:
        pure, rust = PureLexicalBuilder(), _native.LexicalBuilder()
        assert pure.add_docs(LEXICAL_CORPORA[name]) == rust.add_docs(LEXICAL_CORPORA[name])
        assert _drain_lexical(pure) == _drain_lexical(rust)

    @needs_rust
    def test_fuzz_rows_identical_across_batch_boundaries(self) -> None:
        docs = _fuzz_docs(23, 300)
        pure, rust = PureLexicalBuilder(), _native.LexicalBuilder()
        for start in range(0, len(docs), 37):
            assert pure.add_docs(docs[start : start + 37]) == rust.add_docs(docs[start : start + 37])
        pure_out, rust_out = _drain_lexical(pure), _drain_lexical(rust)
        assert pure_out == rust_out
        assert any(row[1] > 0 for row in pure_out[2])  # the fuzz vocabulary spans blocks

    @needs_rust
    @pytest.mark.parametrize("name", ["fixture", "spanning"])
    def test_scores_identical(self, name: str) -> None:
        builder = _native.LexicalBuilder()
        builder.add_docs(LEXICAL_CORPORA[name])
        (_n, avg_dl), summaries, rows = _drain_lexical(builder)
        ids = np.array([doc_id for doc_id, _ in LEXICAL_CORPORA[name]], dtype=np.int64)
        queries = [*QUERIES, "shared filler2", "run xx filler4 filler1", "absent_term"]
        for query in queries:
            blocks, idfs = _score_blocks_for(query, summaries, rows)
            for k in (1, 10, 1000):
                for candidates in (None, ids[::3], ids[:0]):
                    pure = pure_score_blocks(blocks, idfs, avg_dl, k, candidates=candidates)
                    raw = None if candidates is None else candidates.tobytes()
                    assert _native.lexical_score(blocks, idfs, avg_dl, k, raw) == pure, (query, k)


class TestLexicalBuilderContract:
    """Contract behaviors both lexical engines must share."""

    @staticmethod
    def _builders() -> list:
        engines = [PureLexicalBuilder()]
        if _native is not None:
            engines.append(_native.LexicalBuilder())
        return engines

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_non_increasing_doc_ids_refused(self, index: int) -> None:
        engines = self._builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        assert builder.add_docs([(5, "abc def")]) == [2]
        for bad in (5, 4, 0, -3):
            with pytest.raises(ValueError, match="strictly increasing"):
                builder.add_docs([(bad, "xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_add_after_finish_refused(self, index: int) -> None:
        engines = self._builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        builder.add_docs([(1, "abc")])
        assert builder.finish() == (1, 1.0)
        assert builder.finish() == (1, 1.0)  # idempotent
        with pytest.raises(ValueError, match="statistics are fixed"):
            builder.add_docs([(2, "xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_empty_builder_drains_nothing(self, index: int) -> None:
        engines = self._builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        assert builder.finish() == (0, 0.0)
        assert builder.next_df_batch(10) is None
        assert builder.next_batch(10) is None

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_drains_seal_without_an_explicit_finish(self, index: int) -> None:
        engines = self._builders()
        if index >= len(engines):
            pytest.skip("vfs._native extension not built")
        builder = engines[index]
        builder.add_docs([(1, "abc abc"), (2, "abc")])
        assert [row[0] for row in builder.next_batch(0)] == ["abc"]  # a zero cap still yields one row
        assert builder.next_batch(10) is None
        assert builder.finish() == (2, 1.5)


class TestLexicalSeam:
    """The lexical surfaces dispatch through the active engine."""

    def test_builder_and_tokenizer_come_from_the_active_core(self) -> None:
        builder = lexical_builder()
        if _native is None or FORCED_PURE:
            assert isinstance(builder, PureLexicalBuilder)
        else:
            assert isinstance(builder, _native.LexicalBuilder)
        assert tokenize("PostingsBuilder pthread_create") == pure_tokenize("PostingsBuilder pthread_create")

    def test_pure_when_no_engine_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(native, "_active", None)
        assert isinstance(lexical_builder(), PureLexicalBuilder)
        assert tokenize("HTTPServer") == ["httpserver", "http", "server"]
        builder = PureLexicalBuilder()
        builder.add_docs(LEXICAL_CORPORA["fixture"])
        (_n, avg_dl), summaries, rows = _drain_lexical(builder)
        blocks, idfs = _score_blocks_for("flush cache", summaries, rows)
        assert score_blocks(blocks, idfs, avg_dl, 3) == pure_score_blocks(blocks, idfs, avg_dl, 3)

    @needs_rust
    def test_rust_scorer_serves_the_dispatch(self) -> None:
        if FORCED_PURE:
            pytest.skip("VFS_PURE_PYTHON forces the pure engine")
        builder = lexical_builder()
        builder.add_docs(LEXICAL_CORPORA["fixture"])
        (_n, avg_dl), summaries, rows = _drain_lexical(builder)
        blocks, idfs = _score_blocks_for("publish scheduler budget", summaries, rows)
        candidates = np.array([10, 11, 12, 40], dtype=np.int64)
        ranked = score_blocks(blocks, idfs, avg_dl, 5, candidates=candidates)
        assert ranked == pure_score_blocks(blocks, idfs, avg_dl, 5, candidates=candidates)
        assert {chunk for chunk, _ in ranked} <= set(candidates.tolist())


class TestFoldedBytes:
    """The one folded stream both engines consume."""

    def test_matches_the_tokenizer_fold(self) -> None:
        for text in ("Hello\r\nWorld", "İstanbul ısı", "plain"):  # noqa: RUF001
            grams = set(iter_byte_trigrams(folded_bytes(text)))
            assert grams == unique_code_grams(text, folded=True)
