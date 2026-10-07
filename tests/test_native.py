"""The engine seam: the required extension, the protocol gate, and parity.

Parity is the seam's soundness law: the engine must produce the same
posting rows, gate counts, tokens, summary and block rows, and scores
as the readable oracles in ``tests/support/oracles`` — so the crate is
pinned to a specification a reader can follow. The oracle tokenizer
takes its character classes from the running interpreter, so the tests
that would see Unicode-version drift skip off the interpreter that
generated the engine's tables.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import unicodedata

import pytest

from tests.support.lexical_fidelity import CORPUS, QUERIES
from tests.support.oracles.grams import distinct_gram_count as oracle_gram_count
from tests.support.oracles.lexical import (
    PureLexicalBuilder,
    pure_score_blocks,
    pure_tokenize,
)
from tests.support.oracles.lexical import (
    decode_summary as oracle_decode_summary,
)
from tests.support.oracles.lexical import (
    select_blocks as oracle_select_blocks,
)
from tests.support.oracles.postings import PurePostingsBuilder, decode_postings
from vfs import _native
from vfs.models.code_grams import (
    distinct_gram_count,
    folded_bytes,
    iter_byte_trigrams,
    pack_gram,
    unique_code_grams,
)
from vfs.models.lexical import (
    BLOCK_SIZE,
    ScoreBlock,
    decode_summary,
    encode_summary,
    lexical_builder,
    score_blocks,
    select_blocks,
    tokenize,
)
from vfs.models.postings import MAX_DOC_ID, encode_postings, postings_builder
from vfs.native import EXPECTED_PROTOCOL, chunk_spans, structure_grammars

# The oracle tokenizer follows the interpreter's Unicode tables; the engine's
# are generated once. Off the generating interpreter they may differ.
DRIFTING_INTERPRETER = unicodedata.unidata_version != _native.LEXICAL_UNICODE_VERSION
skip_on_drift = pytest.mark.skipif(
    DRIFTING_INTERPRETER,
    reason=f"oracle follows Unicode {unicodedata.unidata_version}; engine tables are {_native.LEXICAL_UNICODE_VERSION}",
)


def builders() -> list:
    """The oracle builder and the engine's."""
    return [PurePostingsBuilder(), _native.PostingsBuilder()]


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
    def test_rows_identical(self, name: str) -> None:
        docs = [(doc_id, folded_bytes(text)) for doc_id, text in CORPORA[name]]
        results = []
        for builder in builders():
            builder.add_docs(docs)
            results.append(drain_rows(builder))
        assert results[0] == results[1]

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

    def test_distinct_gram_count_parity(self) -> None:
        cases = [b"", b"ab", b"abc", b"abcabc", b"abcdefghij", bytes(range(256)) * 3, folded_bytes("İstanbul ısı")]  # noqa: RUF001
        for data in cases:
            exact = len(set(iter_byte_trigrams(data)))
            for cap in (0, 1, 5, 1 << 24):
                rust = distinct_gram_count(data, cap)
                assert rust == oracle_gram_count(data, cap), (data[:16], cap)
                if exact <= cap:
                    assert rust == exact

    def test_blobs_decode_to_the_fed_doc_ids(self) -> None:
        builder = _native.PostingsBuilder()
        builder.add_docs([(3, b"abc"), (200, b"abcd"), (2**62, b"abc")])
        rows = {gram: blob for gram, blob, _count in drain_rows(builder)}
        assert decode_postings(rows[pack_gram(*b"abc")]) == [3, 200, 2**62]
        assert decode_postings(rows[pack_gram(*b"bcd")]) == [200]
        assert rows[pack_gram(*b"abc")] == encode_postings([3, 200, 2**62])


def _oracle_candidates(groups: list[list[list[int]]], allow: list[int] | None, cap: int) -> tuple[list[int], int]:
    """Plain sets: AND within a group, OR across, meet the allow-list, cap."""
    union: set[int] = set()
    for group in groups:
        if group:
            survivors = set(group[0])
            for ids in group[1:]:
                survivors &= set(ids)
            union |= survivors
    if allow is not None:
        union &= set(allow)
    ordered = sorted(union)
    return ordered[:cap], len(ordered)


class TestCandidateKernel:
    """The fused decode + AND + OR + allow + cap call against a set oracle."""

    def test_generated_ladders_match_the_oracle(self) -> None:
        rng = random.Random(141)
        universe = range(1, 50_000)
        for _ in range(200):
            groups: list[list[list[int]]] = []
            for _g in range(rng.randint(1, 4)):
                core = sorted(rng.sample(universe, rng.randint(0, 300)))
                blobs = []
                for _b in range(rng.randint(1, 4)):
                    extra = rng.sample(universe, rng.randint(0, 3000))
                    blobs.append(sorted(set(core) | set(extra)) if rng.random() < 0.7 else sorted(set(extra)))
                groups.append(blobs)
            allow = None if rng.random() < 0.5 else sorted(rng.sample(universe, rng.randint(0, 5000)))
            cap = rng.choice((1, 10, 25_000))
            fed = [[encode_postings(ids) for ids in group] for group in groups]
            assert _native.candidate_ids(fed, allow, cap) == _oracle_candidates(groups, allow, cap)

    def test_hand_cases(self) -> None:
        a, b, c, d = [1, 2, 3, 5, 8, 13], [2, 3, 8, 21], [3, 8, 34], [40, 41]
        enc = encode_postings
        groups = [[enc(a), enc(b), enc(c)], [enc(d)], []]
        assert _native.candidate_ids(groups, None, 100) == ([3, 8, 40, 41], 4)
        # The allow-list meets the union before the cap; the count is pre-cap.
        assert _native.candidate_ids(groups, [3, 8, 41], 2) == ([3, 8], 3)
        assert _native.candidate_ids(groups, [9], 100) == ([], 0)
        assert _native.candidate_ids(groups, None, 0) == ([], 4)
        # OR deduplicates shared ids; an empty group nominates nothing.
        assert _native.candidate_ids([[enc(a)], [enc(b)]], None, 100)[0] == sorted(set(a) | set(b))
        assert _native.candidate_ids([[enc([]), enc(a)]], None, 100) == ([], 0)
        assert _native.candidate_ids([], None, 100) == ([], 0)
        assert _native.candidate_ids([[enc([1, MAX_DOC_ID])]], [MAX_DOC_ID], 5) == ([MAX_DOC_ID], 1)

    def test_a_corrupt_blob_is_refused_with_the_codec_message(self) -> None:
        with pytest.raises(ValueError, match="count header says 2, blob holds 1"):
            _native.candidate_ids([[b"\x02\x01"]], None, 10)
        # Refused even after the intersection has already emptied.
        with pytest.raises(ValueError, match="non-positive delta"):
            _native.candidate_ids([[encode_postings([]), b"\x02\x01\x00"]], None, 10)

    @pytest.mark.slow
    def test_the_widest_ladder_caps_on_the_engine_side(self) -> None:
        # The `return` shape from the landing store: ~200 K postings over
        # four blobs, 46 K survivors; only the capped prefix crosses the seam.
        rng = random.Random(7)
        rare = sorted(rng.sample(range(1, 700_000), 46_000))
        wider = [sorted(set(rare) | set(rng.sample(range(1, 700_000), 50_000))) for _ in range(3)]
        fed = [[encode_postings(ids) for ids in (rare, *wider)]]
        ids, total = _native.candidate_ids(fed, None, 25_000)
        assert (len(ids), total) == (25_000, 46_000)
        assert ids == rare[:25_000]


class TestBuilderContract:
    """Contract behaviors both engines must share, run against each."""

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_non_increasing_doc_ids_refused(self, index: int) -> None:
        engines = builders()
        builder = engines[index]
        builder.add_docs([(5, b"abc")])
        for bad in (5, 4, 0, -3):
            with pytest.raises(ValueError, match="strictly increasing"):
                builder.add_docs([(bad, b"xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_add_after_drain_refused(self, index: int) -> None:
        engines = builders()
        builder = engines[index]
        builder.add_docs([(1, b"abc")])
        assert builder.next_batch(1 << 20)
        with pytest.raises(ValueError):
            builder.add_docs([(2, b"xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_empty_builder_drains_nothing(self, index: int) -> None:
        engines = builders()
        assert engines[index].next_batch(1 << 20) is None

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_tiny_byte_cap_still_progresses(self, index: int) -> None:
        engines = builders()
        builder = engines[index]
        builder.add_docs([(1, b"abcdefgh")])
        batches = []
        while (batch := builder.next_batch(1)) is not None:
            batches.append(batch)
        assert [len(b) for b in batches] == [1] * 6


# A subprocess that swaps the extension for *stand_in* before importing the
# seam: the seam's module-level refusals cannot be exercised in-process.
def _import_seam_with(stand_in: str) -> subprocess.CompletedProcess[str]:
    script = f"import sys, types\nsys.modules['vfs._native'] = {stand_in}\nimport vfs.native\n"
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)


class TestSeamGate:
    """The extension is required: absent or mismatched, import fails and names the fix."""

    def test_absent_extension_fails_the_import(self) -> None:
        run = _import_seam_with("None")
        assert run.returncode != 0
        assert "ImportError: vfs requires its compiled extension vfs._native" in run.stderr
        assert "uv sync --reinstall-package vfs-py" in run.stderr

    def test_protocol_mismatch_fails_the_import(self) -> None:
        run = _import_seam_with(f"types.SimpleNamespace(PROTOCOL_VERSION={EXPECTED_PROTOCOL + 1})")
        assert run.returncode != 0
        assert f"speaks protocol {EXPECTED_PROTOCOL + 1} but this vfs expects {EXPECTED_PROTOCOL}" in run.stderr

    def test_the_live_extension_speaks_the_expected_protocol(self) -> None:
        assert _native.PROTOCOL_VERSION == EXPECTED_PROTOCOL

    def test_builders_come_from_the_engine(self) -> None:
        assert isinstance(postings_builder(), _native.PostingsBuilder)
        assert isinstance(lexical_builder(), _native.LexicalBuilder)


class TestChunkSeam:
    """The structure-aware chunk surface."""

    def test_the_engine_serves_the_registry(self) -> None:
        grammars = structure_grammars()
        assert {"python", "c", "rust", "markdown"} <= grammars

    def test_rows_carry_spans_lines_and_the_oversized_flag(self) -> None:
        body = b"def f(x):\n    return x + 1\n\n\ndef g(y):\n    return y * 2\n"
        (rows,) = chunk_spans([(body, "python")], chunk_size=32)
        assert rows is not None and len(rows) >= 2
        assert rows[0][0] == 0 and rows[-1][1] == len(body)
        assert rows[0][2] == 1  # 1-indexed lines
        assert all(not oversized for _s, _e, _ls, _le, oversized in rows)

    def test_unknown_grammar_rows_are_none(self) -> None:
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
    """Identical tokens, rows and scores from the engine and the oracle."""

    @pytest.mark.parametrize("name", sorted(LEXICAL_CORPORA))
    def test_tokens_identical(self, name: str) -> None:
        for _doc_id, text in LEXICAL_CORPORA[name]:
            assert tokenize(text) == pure_tokenize(text)

    def test_fuzz_tokens_identical(self) -> None:
        for _doc_id, text in _fuzz_docs(11, 500):
            assert tokenize(text) == pure_tokenize(text), text

    @skip_on_drift
    def test_character_classes_are_the_generating_interpreters(self) -> None:
        """On the interpreter that generated them, the tables are exactly
        its ``\\w`` / upper / lower / digit / assigned classes and its casefold."""
        flags = _native.lexical_char_classes()
        points = [cp for cp in range(0x110000) if not 0xD800 <= cp <= 0xDFFF]
        word = re.compile(r"\w")
        mine = bytearray(0x110000)
        for cp in points:
            ch = chr(cp)
            mine[cp] = (
                (1 if word.fullmatch(ch) else 0)
                | (2 if ch.isupper() else 0)
                | (4 if ch.islower() else 0)
                | (8 if ch.isdigit() else 0)
                | (16 if unicodedata.category(ch) != "Cn" else 0)
            )
        differing = [cp for cp in points if flags[cp] != mine[cp]]
        assert differing == [], [hex(cp) for cp in differing[:10]]
        folds = dict(_native.lexical_casefolds())
        for cp in points:
            ch = chr(cp)
            assert folds.get(cp, ch) == ch.casefold(), hex(cp)

    @pytest.mark.parametrize("name", sorted(LEXICAL_CORPORA))
    def test_rows_identical(self, name: str) -> None:
        pure, rust = PureLexicalBuilder(), _native.LexicalBuilder()
        assert pure.add_docs(LEXICAL_CORPORA[name]) == rust.add_docs(LEXICAL_CORPORA[name])
        assert _drain_lexical(pure) == _drain_lexical(rust)

    def test_fuzz_rows_identical_across_batch_boundaries(self) -> None:
        docs = _fuzz_docs(23, 300)
        pure, rust = PureLexicalBuilder(), _native.LexicalBuilder()
        for start in range(0, len(docs), 37):
            assert pure.add_docs(docs[start : start + 37]) == rust.add_docs(docs[start : start + 37])
        pure_out, rust_out = _drain_lexical(pure), _drain_lexical(rust)
        assert pure_out == rust_out
        assert any(row[1] > 0 for row in pure_out[2])  # the fuzz vocabulary spans blocks

    @pytest.mark.parametrize("name", ["fixture", "spanning"])
    def test_scores_identical(self, name: str) -> None:
        builder = _native.LexicalBuilder()
        builder.add_docs(LEXICAL_CORPORA[name])
        (_n, avg_dl), summaries, rows = _drain_lexical(builder)
        ids = [doc_id for doc_id, _ in LEXICAL_CORPORA[name]]
        queries = [*QUERIES, "shared filler2", "run xx filler4 filler1", "absent_term"]
        for query in queries:
            blocks, idfs = _score_blocks_for(query, summaries, rows)
            for k in (1, 10, 1000):
                for candidates in (None, ids[::3], ids[:0]):
                    pure = pure_score_blocks(blocks, idfs, avg_dl, k, candidates=candidates)
                    assert score_blocks(blocks, idfs, avg_dl, k, candidates=candidates) == pure, (query, k)


class TestLexicalKernels:
    """Summary decode and block selection against the stdlib oracles."""

    def test_generated_summaries_decode_identically(self) -> None:
        rng = random.Random(142)
        for _ in range(100):
            count = rng.randint(0, 60)
            firsts = sorted(rng.sample(range(1, 1 << 40), count))
            maxes = [rng.random() * 10 for _ in range(count)]
            blob = encode_summary(firsts, maxes)
            summary = decode_summary(blob)
            assert (summary.first_ids.tolist(), summary.max_weights.tolist()) == oracle_decode_summary(blob)
            assert summary.first_ids.tolist() == firsts and summary.max_weights.tolist() == maxes

    def test_generated_selections_match_the_oracle(self) -> None:
        rng = random.Random(143)
        for _ in range(200):
            raw = []
            for _term in range(rng.randint(0, 6)):
                count = rng.randint(0, 40)
                firsts = sorted(rng.sample(range(1, 10_000), count))
                raw.append((firsts, [rng.random() * 5 for _ in range(count)]))
            summaries = [decode_summary(encode_summary(firsts, maxes)) for firsts, maxes in raw]
            candidates = sorted(rng.sample(range(0, 10_500), rng.randint(0, 50)))
            scores = [rng.random() * 8 for _ in candidates]
            theta = rng.random() * 6
            assert select_blocks(summaries, candidates, scores, theta) == oracle_select_blocks(
                raw, candidates, scores, theta
            )


class TestLexicalBuilderContract:
    """Contract behaviors both lexical engines must share."""

    @staticmethod
    def _builders() -> list:
        return [PureLexicalBuilder(), _native.LexicalBuilder()]

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_non_increasing_doc_ids_refused(self, index: int) -> None:
        engines = self._builders()
        builder = engines[index]
        assert builder.add_docs([(5, "abc def")]) == [2]
        for bad in (5, 4, 0, -3):
            with pytest.raises(ValueError, match="strictly increasing"):
                builder.add_docs([(bad, "xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_add_after_finish_refused(self, index: int) -> None:
        engines = self._builders()
        builder = engines[index]
        builder.add_docs([(1, "abc")])
        assert builder.finish() == (1, 1.0)
        assert builder.finish() == (1, 1.0)  # idempotent
        with pytest.raises(ValueError, match="statistics are fixed"):
            builder.add_docs([(2, "xyz")])

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_empty_builder_drains_nothing(self, index: int) -> None:
        engines = self._builders()
        builder = engines[index]
        assert builder.finish() == (0, 0.0)
        assert builder.next_df_batch(10) is None
        assert builder.next_batch(10) is None

    @pytest.mark.parametrize("index", [0, 1], ids=["pure", "rust"])
    def test_drains_seal_without_an_explicit_finish(self, index: int) -> None:
        engines = self._builders()
        builder = engines[index]
        builder.add_docs([(1, "abc abc"), (2, "abc")])
        assert [row[0] for row in builder.next_batch(0)] == ["abc"]  # a zero cap still yields one row
        assert builder.next_batch(10) is None
        assert builder.finish() == (2, 1.5)


class TestLexicalSeam:
    """The lexical surfaces dispatch through the engine."""

    def test_builder_and_tokenizer_come_from_the_engine(self) -> None:
        assert isinstance(lexical_builder(), _native.LexicalBuilder)
        assert tokenize("PostingsBuilder pthread_create") == pure_tokenize("PostingsBuilder pthread_create")
        assert tokenize("HTTPServer") == ["httpserver", "http", "server"]

    def test_the_scorer_serves_the_dispatch(self) -> None:
        builder = lexical_builder()
        builder.add_docs(LEXICAL_CORPORA["fixture"])
        (_n, avg_dl), summaries, rows = _drain_lexical(builder)
        blocks, idfs = _score_blocks_for("publish scheduler budget", summaries, rows)
        candidates = [10, 11, 12, 40]
        ranked = score_blocks(blocks, idfs, avg_dl, 5, candidates=candidates)
        assert ranked == pure_score_blocks(blocks, idfs, avg_dl, 5, candidates=candidates)
        assert {chunk for chunk, _ in ranked} <= set(candidates)


class TestFoldedBytes:
    """The one folded stream both engines consume."""

    def test_matches_the_tokenizer_fold(self) -> None:
        for text in ("Hello\r\nWorld", "İstanbul ısı", "plain"):  # noqa: RUF001
            grams = set(iter_byte_trigrams(folded_bytes(text)))
            assert grams == unique_code_grams(text, folded=True)
