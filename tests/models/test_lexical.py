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
from array import array
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence

from tests.support.oracles.lexical import PureLexicalBuilder, pure_overlay_postings, pure_score_blocks, pure_tokenize
from tests.support.oracles.postings import decode_postings, decode_varints
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
    OverlayPostings,
    ScoreBlock,
    decode_summary,
    encode_block,
    encode_postings,
    encode_summary,
    idf,
    options_fingerprint,
    overlay_postings,
    select_blocks,
    term_weight,
)


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


def _drained(builder: lexical.LexicalBuilder, cap: int = 100) -> tuple[list, list]:
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
            "from tests.support.oracles.lexical import PureLexicalBuilder, pure_tokenize\n"
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


# Bodies on every tokenizer rule: non-ASCII letters and folds, camel case,
# underscores, digit-led pieces, a term over the byte cap, an empty body.
_MIXED_BODIES: list[tuple[int, str]] = [
    (3, "İstanbul ısı STRASSE Straße καλημέρα κόσμε XMLHttpRequest sha256Hash pthread_create"),  # noqa: RUF001
    (7, "0x1f v2_0xFF getX a_b naïve café " + "x" * (MAX_TERM_BYTES + 1) + " " + "é" * 33 + " Foo_barBaz 1st"),
    (9, "http request HTTP_REQUEST httpRequest café CAFÉ κόσμε and nothing else"),
    (12, ""),
    (40, "sha256Hash sha256hash sha256 pthread create_thread"),
]
_TWENTY_TERMS = [
    "http", "café", "sha256", "request", "κόσμε", "isi", "absent", "xml", "get", "foo",
    "bar", "baz", "1st", "0xff", "v2", "pthread", "create", "hash", "strasse", "nothing",
]  # fmt: skip


class TestOverlayPostings:
    """The overlay counts kernel against its oracle: the same postings, no token materialized."""

    @pytest.mark.parametrize("terms", [["http", "café"], _TWENTY_TERMS], ids=["two", "twenty"])
    def test_the_engine_agrees_with_the_oracle_on_mixed_bodies(self, terms: list[str]) -> None:
        """Guards: a term matched on something other than its exact fold, a body counted
        twice or skipped, or the twenty-term set path missing a present term."""
        engine = overlay_postings(_MIXED_BODIES, terms, budget=None)
        oracle = pure_overlay_postings(_MIXED_BODIES, terms)
        assert isinstance(engine, OverlayPostings)
        assert engine.postings == oracle.postings
        assert engine.reached == oracle.reached == len(_MIXED_BODIES)
        assert engine.total_dl == oracle.total_dl
        assert engine.completed is oracle.completed is True
        assert any(postings for postings in engine.postings)  # the fixture holds the terms it claims

    def test_the_tokenizer_and_its_fingerprint_are_unchanged(self) -> None:
        """Guards: the scanner lift changing a token, which would move the epoch's options hash."""
        assert TOKENIZER_VERSION == 1
        assert options_fingerprint() == (
            "bm25=k1:1.2,b:0.75;tokenizer=1;term_bytes=64;block=128;"
            "codec=ids:count+delta+varint;tfs,dls:varint;summary:delta+varint,le-f64"
        )
        for _doc_id, body in _MIXED_BODIES:
            assert lexical.tokenize(body) == pure_tokenize(body)

    def test_an_exhausted_budget_stops_between_documents(self) -> None:
        """Guards: a body counted after the deadline, or a stopped batch reported complete."""
        docs = [(1, "alpha beta"), (2, "alpha")]
        stopped = overlay_postings(docs, ["alpha"], budget=0.0)
        assert stopped.completed is False
        assert stopped.reached == 0 and stopped.total_dl == 0
        assert stopped.postings == [[]]

    def test_an_empty_batch_counts_nothing_and_completes(self) -> None:
        assert overlay_postings([], ["alpha", "beta"], budget=None) == OverlayPostings([[], []], 0, 0, True)
        assert pure_overlay_postings([], ["alpha", "beta"]) == OverlayPostings([[], []], 0, 0, True)


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
        assert len(decode_summary(b"").first_ids) == 0

    def test_a_torn_or_non_monotone_summary_is_refused(self) -> None:
        blob = encode_summary([1, 129], [1.5, 0.25])
        with pytest.raises(ValueError, match="truncated summary"):
            decode_summary(blob[:-1])
        with pytest.raises(ValueError, match="not monotone"):
            decode_summary(encode_summary([5, 5], [1.0, 1.0]))

    def test_decode_varints_serves_bare_runs(self) -> None:
        assert decode_varints(_varints([0, 1, 127, 128, 300])) == [0, 1, 127, 128, 300]
        assert decode_varints(b"") == []

    def test_encode_block_refuses_misaligned_or_oversized_input(self) -> None:
        with pytest.raises(ValueError, match="must align"):
            encode_block([1, 2], [1], [3, 4])
        too_many = list(range(1, BLOCK_SIZE + 2))
        with pytest.raises(ValueError, match="at most"):
            encode_block(too_many, [1] * len(too_many), [1] * len(too_many))


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
        assert decode_postings(shared[0][3]) == list(range(1, BLOCK_SIZE + 1))
        assert decode_postings(shared[1][3]) == [BLOCK_SIZE + 1, BLOCK_SIZE + 2]  # absolute again
        assert decode_varints(shared[1][4]) == [1, 1]  # tfs
        assert decode_varints(shared[1][5]) == [2, 1]  # dls: 129 is odd (two tokens), 130 even
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
        assert {row[0]: decode_varints(row[5]) for row in rows} == {"foo": [4], "bar": [4]}
        assert {row[0]: decode_varints(row[4]) for row in rows} == {"foo": [3], "bar": [1]}

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
        ranked = pure_score_blocks(blocks, [1.0], self.AVG, 10, candidates=[2, 4, 9])
        assert [chunk for chunk, _ in ranked] == [2, 4]
        assert pure_score_blocks(blocks, [1.0], self.AVG, 10, candidates=[]) == []


class TestSelectBlocks:
    SUMMARY = BlockSummary(array("q", [1, 129, 257, 385]), array("d", [0.5, 2.0, 0.5, 0.5]))

    @staticmethod
    def _one(summary: BlockSummary, candidates: Sequence[int], scores: Sequence[float], theta: float) -> list[int]:
        return select_blocks([summary], candidates, scores, theta)[0]

    def test_every_block_competes_before_a_full_top_k(self) -> None:
        assert self._one(self.SUMMARY, [], [], 0.0) == [0, 1, 2, 3]

    def test_a_block_competes_alone_or_by_lifting_a_candidate(self) -> None:
        candidates = [130, 300]  # in blocks 1 and 2
        scores = [0.1, 1.7]
        # θ = 2.1: block 1 clears it alone with a lifted candidate (0.1 + 2.0),
        # block 2 lifts 1.7 + 0.5 = 2.2, blocks 0 and 3 hold no candidate.
        assert self._one(self.SUMMARY, candidates, scores, 2.1) == [1, 2]
        # θ = 2.25: block 1's max 2.0 < θ and its lift 0.1 + 2.0 < θ.
        assert self._one(self.SUMMARY, candidates, scores, 2.25) == []

    def test_later_terms_maxima_lift_the_earlier_term(self) -> None:
        # A second term with maximum 0.3 is fetched after the 2.0 term, so the
        # first term sees rest = 0.3 and the second sees rest = 0.0.
        later = BlockSummary(array("q", [1]), array("d", [0.3]))
        candidates, scores = [130, 300], [0.1, 1.7]
        assert select_blocks([self.SUMMARY, later], candidates, scores, 2.25) == [[1, 2], []]
        # The answer follows the input order, not the fetch order.
        assert select_blocks([later, self.SUMMARY], candidates, scores, 2.25) == [[], [1, 2]]

    def test_candidates_before_the_first_block_are_ignored(self) -> None:
        summary = BlockSummary(array("q", [100]), array("d", [1.0]))
        assert self._one(summary, [5], [9.0], 5.0) == []
        assert self._one(summary, [100], [9.0], 5.0) == [0]  # a boundary id belongs to the block it starts
        assert self._one(summary, [150], [9.0], 5.0) == [0]

    def test_arrays_and_lists_both_cross_the_seam(self) -> None:
        # The caller holds candidates and scores as arrays across the
        # round-two loop; the seam packs an array once, and a list via one.
        candidates, scores = array("q", [130, 300]), array("d", [0.1, 1.7])
        assert self._one(self.SUMMARY, candidates, scores, 2.1) == [1, 2]
        assert self._one(self.SUMMARY, list(candidates), list(scores), 2.1) == [1, 2]

    def test_an_empty_summary_names_nothing(self) -> None:
        empty = BlockSummary(array("q"), array("d"))
        assert self._one(empty, [1], [1.0], 0.0) == []
        assert select_blocks([], [1], [1.0], 0.0) == []


# A corpus whose common term crosses a block, fed under a base's statistics.
_DELTA_DOCS = [(n, f"wombat common {'rare' if n % 7 == 0 else 'plain'} words{n % 3}") for n in range(1, 300)]


def test_finish_under_matches_the_oracle() -> None:
    engine, oracle = lexical.lexical_builder(), PureLexicalBuilder()
    assert engine.add_docs(_DELTA_DOCS) == oracle.add_docs(_DELTA_DOCS)
    vocabulary = engine.vocabulary()
    assert vocabulary == oracle.vocabulary()
    assert [term for term, _df in vocabulary] == sorted({t for _id, body in _DELTA_DOCS for t in pure_tokenize(body)})
    assert dict(vocabulary)["common"] == len(_DELTA_DOCS)
    idfs = [idf(df, 10_000 + index) for index, (_term, df) in enumerate(vocabulary)]
    own_avg = sum(len(pure_tokenize(body)) for _id, body in _DELTA_DOCS) / len(_DELTA_DOCS)
    assert engine.finish_under(5.5, idfs) == oracle.finish_under(5.5, idfs) == (len(_DELTA_DOCS), own_avg)
    summaries, rows = _drained(engine)
    assert (summaries, rows) == _drained(oracle)
    assert [row[2] for row in summaries] == idfs
    for builder in (lexical.lexical_builder(), PureLexicalBuilder()):
        builder.add_docs(_DELTA_DOCS)
        with pytest.raises(ValueError, match="idf"):
            builder.finish_under(5.5, idfs[:-1])
    with pytest.raises(ValueError):
        engine.add_docs([(10_000, "more")])
    with pytest.raises(ValueError):
        engine.finish_under(5.5, idfs)


def test_term_weight_is_total_at_a_zero_mean_length() -> None:
    """Guards: the zero-mean guard deleted, so a corpus whose mean length is 0 divides by it; or the guard
    reaching a positive mean, so an ordinary score moves."""
    for tf in (1, 3):
        for dl in (0, 7):
            weight = term_weight(tf, dl, 0.0, 2.5)
            assert math.isfinite(weight) and weight == 2.5 * tf * (BM25_K1 + 1.0) / (tf + BM25_K1)
    norm = BM25_K1 * (1.0 - BM25_B + BM25_B * 7 / 9.0)
    assert term_weight(3, 7, 9.0, 2.5) == 2.5 * 3 * (BM25_K1 + 1.0) / (3 + norm)


def test_finish_under_weighs_every_block_under_the_given_statistics() -> None:
    builder = PureLexicalBuilder()
    builder.add_docs(_DELTA_DOCS)
    idfs = [1.5] * len(builder.vocabulary())
    builder.finish_under(5.5, idfs)
    summaries, rows = _drained(builder)
    by_term = {row[0]: row[2] for row in summaries}
    blobs = {row[0]: row[4] for row in summaries}
    for term, block_no, _count, doc_ids, tfs, dls in rows:
        weights = [
            term_weight(tf, dl, 5.5, by_term[term])
            for tf, dl in zip(decode_varints(tfs), decode_varints(dls), strict=True)
        ]
        assert len(decode_postings(doc_ids)) == len(weights)
        summary = decode_summary(blobs[term])
        assert summary.max_weights[block_no] == max(weights)
