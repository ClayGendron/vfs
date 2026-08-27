"""Pins for the lexical tokenizer, the BM25 formula, the codecs, the pure
builder, the pure scorer and block selection.

The tokenizer is the one thing indexer and query must agree on, so its
rules are pinned example by example; the formula's two laws (idf never
negative, a single-term score bounded by ``(k1+1)·idf``); the builder's
block shape (sealing, restarting deltas, the true maximum in the
summary); the scorer's order and tie-break; and what
``competing_blocks`` keeps — all pinned beside one test proving the
output is identical across processes with different hash seeds.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

from vfs.models import lexical
from vfs.models.code_grams import fold_content
from vfs.models.lexical import (
    BLOCK_SIZE,
    BM25_B,
    BM25_K1,
    MAX_TERM_BYTES,
    MIN_TERM_CHARS,
    TOKENIZER_VERSION,
    BlockSummary,
    PureLexicalBuilder,
    ScoreBlock,
    competing_blocks,
    decode_summary,
    encode_postings,
    encode_summary,
    idf,
    options_fingerprint,
    pure_score_blocks,
    pure_tokenize,
    term_weight,
)
from vfs.models.postings import decode_postings, decode_varints


def _varints(values: list[int]) -> bytes:
    out = bytearray()
    for value in values:
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
    return bytes(out)


def _block(term: int, bound: float, ids: list[int], tfs: list[int], dls: list[int]) -> ScoreBlock:
    return ScoreBlock(term, bound, encode_postings(ids), _varints(tfs), _varints(dls))


def _drained(builder: PureLexicalBuilder, cap: int = 100) -> tuple[list, list]:
    summaries: list = []
    while (batch := builder.next_df_batch(cap)) is not None:
        summaries.extend(batch)
    rows: list = []
    while (batch := builder.next_batch(cap)) is not None:
        rows.extend(batch)
    return summaries, rows


class TestTokenizer:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("PostingsBuilder", ["postingsbuilder", "postings", "builder"]),
            ("pthread_create", ["pthread_create", "pthread", "create"]),
            ("HTTPServer", ["httpserver", "http", "server"]),
            ("XMLHttpRequest", ["xmlhttprequest", "xml", "http", "request"]),
            ("sha256Hash", ["sha256hash", "sha256", "hash"]),
            ("getValue", ["getvalue", "get", "value"]),
        ],
    )
    def test_identifiers_emit_the_whole_and_their_parts(self, text: str, expected: list[str]) -> None:
        assert pure_tokenize(text) == expected

    def test_a_single_part_identifier_is_emitted_once(self) -> None:
        assert pure_tokenize("postings") == ["postings"]
        assert pure_tokenize("__init__") == ["__init__"]
        assert pure_tokenize("utf8mb4") == ["utf8mb4"]

    def test_digit_led_pieces_stay_whole(self) -> None:
        assert pure_tokenize("0x1f") == ["0x1f"]
        assert pure_tokenize("0xDEADbeef") == ["0xdeadbeef"]
        assert pure_tokenize("v2_0xFF") == ["v2_0xff", "v2", "0xff"]

    def test_one_character_terms_are_dropped_whole_or_part(self) -> None:
        assert pure_tokenize("a b c") == []
        assert pure_tokenize("getX") == ["getx", "get"]
        assert pure_tokenize("x_y") == ["x_y"]  # the whole survives; both parts are dropped

    def test_terms_over_the_byte_cap_are_dropped_not_truncated(self) -> None:
        assert pure_tokenize("x" * MAX_TERM_BYTES) == ["x" * MAX_TERM_BYTES]
        assert pure_tokenize("x" * (MAX_TERM_BYTES + 1)) == []
        # The cap is bytes post-fold: 33 two-byte letters are 33 chars, 66 bytes.
        assert pure_tokenize("é" * 33) == []
        assert pure_tokenize("é" * 32) == ["é" * 32]

    def test_punctuation_operators_and_whitespace_split_runs(self) -> None:
        assert pure_tokenize("foo.bar(baz, qux) -> a/b\n\tself.x += y2") == ["foo", "bar", "baz", "qux", "self", "y2"]

    def test_folding_agrees_with_the_gram_index(self) -> None:
        # Dotted I (U+0130) and dotless i (U+0131) both fold to ASCII i, as the gram index folds
        # them; ß and É take casefold's spelling. No case change inside these.
        for word in ("İstanbul", "\u0131stanbul", "STRASSE", "Straße", "ÉCOLE"):
            assert pure_tokenize(word) == [fold_content(word)]
        assert pure_tokenize("İstanbul") == pure_tokenize("istanbul") == pure_tokenize("ISTANBUL")

    def test_no_stemming_and_no_stop_list(self) -> None:
        assert pure_tokenize("the indexes index the indexing") == ["the", "indexes", "index", "the", "indexing"]

    def test_duplicates_are_kept_in_order(self) -> None:
        assert pure_tokenize("foo bar foo") == ["foo", "bar", "foo"]

    def test_output_is_identical_across_hash_seeds(self) -> None:
        """Nothing in the pipeline depends on set or dict order."""
        script = (
            "import json, sys\n"
            "from vfs.models.lexical import PureLexicalBuilder, pure_tokenize\n"
            "text = 'PostingsBuilder pthread_create HTTPServer foo bar foo 0x1f zebra apple'\n"
            "docs = [(1, text), (2, 'apple zebra'), (3, text.upper())]\n"
            "b = PureLexicalBuilder()\n"
            "b.add_docs(docs)\n"
            "b.finish()\n"
            "rows = [[str(v) if isinstance(v, bytes) else v for v in r] for r in b.next_batch(100)]\n"
            "dfs = [[str(v) if isinstance(v, bytes) else v for v in r] for r in b.next_df_batch(100)]\n"
            "json.dump({'tokens': pure_tokenize(text), 'rows': rows, 'dfs': dfs}, sys.stdout)\n"
        )
        outputs = []
        for seed in ("0", "12345"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True)
            outputs.append(json.loads(run.stdout))
        assert outputs[0] == outputs[1]
        assert outputs[0]["tokens"][:3] == ["postingsbuilder", "postings", "builder"]

    def test_the_declared_gates(self) -> None:
        assert (MIN_TERM_CHARS, MAX_TERM_BYTES, TOKENIZER_VERSION, BLOCK_SIZE) == (2, 64, 1, 128)


class TestFormula:
    def test_constants_are_the_lucene_defaults(self) -> None:
        assert (BM25_K1, BM25_B) == (1.2, 0.75)

    def test_idf_is_never_negative(self) -> None:
        # A term in every document (df == N) is the floor; Lucene's
        # smoothing keeps it strictly positive.
        assert idf(10, 10) == pytest.approx(math.log(1 + 0.5 / 10.5))
        assert idf(10, 10) > 0
        assert idf(1, 1000) > idf(500, 1000) > idf(1000, 1000) > 0

    def test_single_term_score_is_bounded_by_k1_plus_one_times_idf(self) -> None:
        term_idf = idf(3, 100)
        for tf in (1, 5, 50, 5000):
            weight = term_weight(tf, 40, 40.0, term_idf)
            assert weight <= (BM25_K1 + 1) * term_idf
        assert term_weight(5000, 40, 40.0, term_idf) == pytest.approx((BM25_K1 + 1) * term_idf, rel=1e-3)

    def test_longer_documents_are_penalised(self) -> None:
        term_idf = idf(3, 100)
        assert (
            term_weight(2, 10, 40.0, term_idf)
            > term_weight(2, 40, 40.0, term_idf)
            > term_weight(2, 400, 40.0, term_idf)
        )

    def test_the_formula_spelled_out(self) -> None:
        tf, dl, avg_dl, term_idf = 3, 50, 40.0, 1.5
        expected = term_idf * tf * (BM25_K1 + 1) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avg_dl))
        assert term_weight(tf, dl, avg_dl, term_idf) == expected

    def test_options_fingerprint_reads_the_live_constants(self, monkeypatch) -> None:
        assert options_fingerprint().startswith("bm25=k1:1.2,b:0.75;tokenizer=1;term_bytes=64;block=128;codec=")
        monkeypatch.setattr(lexical, "BM25_K1", 0.9)
        assert "k1:0.9" in options_fingerprint()
        monkeypatch.setattr(lexical, "BLOCK_SIZE", 64)
        assert "block=64" in options_fingerprint()


class TestSummaryCodec:
    def test_round_trip(self) -> None:
        firsts, maxes = [1, 129, 5000, 2**40], [1.5, 0.25, 3.0, 1e-9]
        blob = encode_summary(firsts, maxes)
        assert len(blob) == 4 * 8 + 1 + 2 + 2 + 6  # a f64 per block plus the varint deltas (1, 128, 4871, ~2**40)
        summary = decode_summary(blob)
        assert isinstance(summary, BlockSummary)
        assert summary.first_ids.tolist() == firsts and summary.max_weights.tolist() == maxes
        assert decode_summary(b"").first_ids.size == 0

    def test_decode_varints_serves_bare_runs(self) -> None:
        assert decode_varints(_varints([0, 1, 127, 128, 300])).tolist() == [0, 1, 127, 128, 300]
        assert decode_varints(b"").size == 0


class TestBuilder:
    def test_blocks_seal_at_the_block_size_with_deltas_restarting(self) -> None:
        builder = PureLexicalBuilder()
        docs = [(i, f"shared unique{i}" if i % 2 else "shared") for i in range(1, BLOCK_SIZE + 3)]
        assert builder.add_docs(docs[:50]) == [2 if i % 2 else 1 for i in range(1, 51)]
        builder.add_docs(docs[50:])
        n_docs, avg_dl = builder.finish()
        assert n_docs == BLOCK_SIZE + 2
        summaries, rows = _drained(builder, cap=3)
        shared = [row for row in rows if row[0] == "shared"]
        assert [(row[1], row[2]) for row in shared] == [(0, BLOCK_SIZE), (1, 2)]
        assert decode_postings(shared[0][3]).tolist() == list(range(1, BLOCK_SIZE + 1))
        assert decode_postings(shared[1][3]).tolist() == [BLOCK_SIZE + 1, BLOCK_SIZE + 2]  # absolute again
        assert decode_varints(shared[1][4]).tolist() == [1, 1]  # tfs
        assert decode_varints(shared[1][5]).tolist() == [2, 1]  # dls: 129 is odd (two tokens), 130 even
        # Terms and rows drain in bytewise term order, every term once in the summaries.
        assert [s[0] for s in summaries] == sorted({term for term, *_ in rows})
        assert [row[0] for row in rows] == sorted(row[0] for row in rows)
        # The summary: two blocks, first ids 1 and 129, the maximum the true one.
        summary = decode_summary(next(s for s in summaries if s[0] == "shared")[4])
        assert summary.first_ids.tolist() == [1, BLOCK_SIZE + 1]
        term_idf = idf(BLOCK_SIZE + 2, n_docs)
        assert summary.max_weights.tolist() == [term_weight(1, 1, avg_dl, term_idf)] * 2
        assert next(s for s in summaries if s[0] == "shared")[3] == term_weight(1, 1, avg_dl, term_idf)

    def test_the_summary_holds_the_true_maximum_not_the_max_tf_min_dl_bound(self) -> None:
        # Two postings: (tf=3, dl=100) and (tf=1, dl=2). The loose bound
        # pairs max_tf with min_dl and overstates; the summary is the truth.
        builder = PureLexicalBuilder()
        builder.add_docs([(1, "term " * 3 + "pad " * 97), (2, "term pad")])
        n_docs, avg_dl = builder.finish()
        summaries = builder.next_df_batch(10)
        assert summaries is not None
        (summary,) = [s for s in summaries if s[0] == "term"]
        term_idf = idf(2, n_docs)
        truth = max(term_weight(3, 100, avg_dl, term_idf), term_weight(1, 2, avg_dl, term_idf))
        loose = term_weight(3, 2, avg_dl, term_idf)
        assert summary[3] == truth < loose
        assert decode_summary(summary[4]).max_weights.tolist() == [truth]

    def test_document_length_counts_every_token_not_distinct_terms(self) -> None:
        builder = PureLexicalBuilder()
        assert builder.add_docs([(1, "foo foo foo bar")]) == [4]
        builder.finish()
        rows = builder.next_batch(10)
        assert rows is not None
        assert {row[0]: decode_varints(row[5]).tolist() for row in rows} == {"foo": [4], "bar": [4]}
        assert {row[0]: decode_varints(row[4]).tolist() for row in rows} == {"foo": [3], "bar": [1]}

    def test_an_empty_corpus_has_zero_stats_and_no_rows(self) -> None:
        builder = PureLexicalBuilder()
        assert builder.finish() == (0, 0.0)
        assert builder.next_df_batch(5) is None and builder.next_batch(5) is None

    def test_feeding_after_finish_is_refused(self) -> None:
        builder = PureLexicalBuilder()
        builder.add_docs([(1, "early")])
        builder.finish()
        with pytest.raises(ValueError, match="statistics are fixed"):
            builder.add_docs([(2, "late")])

    def test_non_increasing_doc_ids_are_refused(self) -> None:
        builder = PureLexicalBuilder()
        builder.add_docs([(5, "abc")])
        with pytest.raises(ValueError, match="strictly increasing"):
            builder.add_docs([(5, "abc")])


class TestScorer:
    AVG = 10.0

    def test_orders_by_score_then_chunk_id_and_honours_k(self) -> None:
        # Two docs tie exactly (same tf and dl under one term): the lower id leads.
        blocks = [_block(0, 1.0, [3, 7, 9], [2, 1, 2], [10, 10, 10])]
        ranked = pure_score_blocks(blocks, [1.5], self.AVG, 10)
        assert [chunk for chunk, _ in ranked] == [3, 9, 7]
        assert ranked[0][1] == ranked[1][1] == term_weight(2, 10, self.AVG, 1.5)
        assert pure_score_blocks(blocks, [1.5], self.AVG, 2) == ranked[:2]
        assert pure_score_blocks(blocks, [1.5], self.AVG, 0) == []
        assert pure_score_blocks([], [1.5], self.AVG, 5) == []

    def test_sums_across_terms_and_blocks(self) -> None:
        blocks = [
            _block(0, 2.0, [1, 2], [1, 1], [10, 10]),
            _block(1, 1.0, [2, 3], [1, 3], [10, 10]),
            _block(1, 1.0, [200], [1], [10]),
        ]
        ranked = dict(pure_score_blocks(blocks, [2.0, 1.0], self.AVG, 10))
        assert ranked[2] == term_weight(1, 10, self.AVG, 2.0) + term_weight(1, 10, self.AVG, 1.0)
        assert set(ranked) == {1, 2, 3, 200}

    def test_candidates_restrict_the_ranking(self) -> None:
        blocks = [_block(0, 1.0, [1, 2, 3, 4], [1, 1, 1, 1], [10, 10, 10, 10])]
        ranked = pure_score_blocks(blocks, [1.0], self.AVG, 10, candidates=np.array([2, 4, 9], dtype=np.int64))
        assert [chunk for chunk, _ in ranked] == [2, 4]
        assert pure_score_blocks(blocks, [1.0], self.AVG, 10, candidates=np.array([], dtype=np.int64)) == []


class TestCompetingBlocks:
    SUMMARY = BlockSummary(np.array([1, 129, 257, 385], dtype=np.int64), np.array([0.5, 2.0, 0.5, 0.5]))

    def test_every_block_competes_before_a_full_top_k(self) -> None:
        none = np.array([], dtype=np.int64)
        assert competing_blocks(self.SUMMARY, none, np.array([]), 0.0).tolist() == [0, 1, 2, 3]

    def test_a_block_competes_alone_or_by_lifting_a_candidate(self) -> None:
        candidates = np.array([130, 300], dtype=np.int64)  # in blocks 1 and 2
        scores = np.array([0.1, 1.7])
        # θ = 2.1: block 1 clears it alone with a lifted candidate (0.1 + 2.0),
        # block 2 lifts 1.7 + 0.5 = 2.2, blocks 0 and 3 hold no candidate.
        assert competing_blocks(self.SUMMARY, candidates, scores, 2.1).tolist() == [1, 2]
        # θ = 2.25: only block 1 (its max 2.0 + 0.1 = 2.1 < θ, but 2.0 alone? no: 2.0 < 2.25).
        assert competing_blocks(self.SUMMARY, candidates, scores, 2.25).tolist() == []
        # The other overflowing terms' maxima lift every block.
        assert competing_blocks(self.SUMMARY, candidates, scores, 2.25, rest=0.3).tolist() == [1, 2]

    def test_candidates_before_the_first_block_are_ignored(self) -> None:
        summary = BlockSummary(np.array([100], dtype=np.int64), np.array([1.0]))
        assert competing_blocks(summary, np.array([5], dtype=np.int64), np.array([9.0]), 5.0).tolist() == []
        assert competing_blocks(summary, np.array([150], dtype=np.int64), np.array([9.0]), 5.0).tolist() == [0]

    def test_an_empty_summary_names_nothing(self) -> None:
        empty = BlockSummary(np.array([], dtype=np.int64), np.array([]))
        assert competing_blocks(empty, np.array([1], dtype=np.int64), np.array([1.0]), 0.0).size == 0
