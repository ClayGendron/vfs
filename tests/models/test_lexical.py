"""Pins for the lexical tokenizer, the BM25 formula, and the pure builder.

The tokenizer is the one thing indexer and query must agree on, so its
rules are pinned example by example; the formula's two laws (idf never
negative, a single-term score bounded by ``(k1+1)·idf``) and the
builder's draining contract are pinned beside it; and one test proves
the output is identical across processes with different hash seeds.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import pytest

from vfs.models import lexical
from vfs.models.code_grams import fold_content
from vfs.models.lexical import (
    BM25_B,
    BM25_K1,
    MAX_TERM_BYTES,
    MIN_TERM_CHARS,
    TOKENIZER_VERSION,
    CorpusStats,
    DfRow,
    DocRow,
    LexicalIndexBuilder,
    TermRow,
    idf,
    options_fingerprint,
    term_weight,
    tokenize,
)


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
        assert tokenize(text) == expected

    def test_a_single_part_identifier_is_emitted_once(self) -> None:
        assert tokenize("postings") == ["postings"]
        assert tokenize("__init__") == ["__init__"]
        assert tokenize("utf8mb4") == ["utf8mb4"]

    def test_digit_led_pieces_stay_whole(self) -> None:
        assert tokenize("0x1f") == ["0x1f"]
        assert tokenize("0xDEADbeef") == ["0xdeadbeef"]
        assert tokenize("v2_0xFF") == ["v2_0xff", "v2", "0xff"]

    def test_one_character_terms_are_dropped_whole_or_part(self) -> None:
        assert tokenize("a b c") == []
        assert tokenize("getX") == ["getx", "get"]
        assert tokenize("x_y") == ["x_y"]  # the whole survives; both parts are dropped

    def test_terms_over_the_byte_cap_are_dropped_not_truncated(self) -> None:
        assert tokenize("x" * MAX_TERM_BYTES) == ["x" * MAX_TERM_BYTES]
        assert tokenize("x" * (MAX_TERM_BYTES + 1)) == []
        # The cap is bytes post-fold: 33 two-byte letters are 33 chars, 66 bytes.
        assert tokenize("é" * 33) == []
        assert tokenize("é" * 32) == ["é" * 32]

    def test_punctuation_operators_and_whitespace_split_runs(self) -> None:
        assert tokenize("foo.bar(baz, qux) -> a/b\n\tself.x += y2") == ["foo", "bar", "baz", "qux", "self", "y2"]

    def test_folding_agrees_with_the_gram_index(self) -> None:
        # Dotted I (U+0130) and dotless i (U+0131) both fold to ASCII i, as the gram index folds
        # them; ß and É take casefold's spelling. No case change inside these.
        for word in ("İstanbul", "\u0131stanbul", "STRASSE", "Straße", "ÉCOLE"):
            assert tokenize(word) == [fold_content(word)]
        assert tokenize("İstanbul") == tokenize("istanbul") == tokenize("ISTANBUL")

    def test_no_stemming_and_no_stop_list(self) -> None:
        assert tokenize("the indexes index the indexing") == ["the", "indexes", "index", "the", "indexing"]

    def test_duplicates_are_kept_in_order(self) -> None:
        assert tokenize("foo bar foo") == ["foo", "bar", "foo"]

    def test_output_is_identical_across_hash_seeds(self) -> None:
        """Nothing in the pipeline depends on set or dict order."""
        script = (
            "import json, sys\n"
            "from vfs.models.lexical import LexicalIndexBuilder, tokenize\n"
            "text = 'PostingsBuilder pthread_create HTTPServer foo bar foo 0x1f zebra apple'\n"
            "docs = [(1, 'e1', text), (2, 'e2', 'apple zebra'), (3, 'e3', text.upper())]\n"
            "b = LexicalIndexBuilder()\n"
            "b.observe(docs)\n"
            "b.finish()\n"
            "json.dump({'tokens': tokenize(text), 'rows': b.weigh(docs), 'dfs': list(b.dfs)}, sys.stdout)\n"
        )
        outputs = []
        for seed in ("0", "12345"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True)
            outputs.append(json.loads(run.stdout))
        assert outputs[0] == outputs[1]
        assert outputs[0]["tokens"][:3] == ["postingsbuilder", "postings", "builder"]

    def test_the_declared_gates(self) -> None:
        assert (MIN_TERM_CHARS, MAX_TERM_BYTES, TOKENIZER_VERSION) == (2, 64, 1)


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
        assert options_fingerprint() == "bm25=k1:1.2,b:0.75;tokenizer=1;term_bytes=64"
        monkeypatch.setattr(lexical, "BM25_K1", 0.9)
        assert "k1:0.9" in options_fingerprint()


class TestBuilder:
    DOCS = ((1, "e1", "foo bar foo"), (2, "e2", "bar baz"), (3, "e3", ""))

    def _observed(self) -> LexicalIndexBuilder:
        builder = LexicalIndexBuilder()
        assert builder.observe(self.DOCS[:2]) == [DocRow(1, "e1", 3), DocRow(2, "e2", 2)]
        assert builder.observe(self.DOCS[2:]) == [DocRow(3, "e3", 0)]
        return builder

    def test_stats_and_dfs_are_fixed_by_finish(self) -> None:
        builder = self._observed()
        assert builder.dfs == []  # nothing fixed before finish
        assert builder.finish() == CorpusStats(3, 5 / 3)
        assert list(builder.dfs) == [DfRow("bar", 2, idf(2, 3)), DfRow("baz", 1, idf(1, 3)), DfRow("foo", 1, idf(1, 3))]
        assert builder.finish() == CorpusStats(3, 5 / 3)  # idempotent

    def test_pass_two_weighs_each_batch_in_term_order(self) -> None:
        builder = self._observed()
        avg = 5 / 3
        assert builder.weigh(self.DOCS[:1]) == [
            TermRow("bar", 1, 1, term_weight(1, 3, avg, idf(2, 3))),
            TermRow("foo", 1, 2, term_weight(2, 3, avg, idf(1, 3))),
        ]
        assert builder.weigh(self.DOCS[1:]) == [
            TermRow("bar", 2, 1, term_weight(1, 2, avg, idf(2, 3))),
            TermRow("baz", 2, 1, term_weight(1, 2, avg, idf(1, 3))),
        ]
        # Batch boundaries change nothing: one batch weighs the same rows as two.
        whole = self._observed()
        assert sorted(whole.weigh(self.DOCS)) == sorted([*builder.weigh(self.DOCS[:1]), *builder.weigh(self.DOCS[1:])])
        assert whole.finish() == builder.finish()

    def test_an_empty_corpus_has_zero_stats_and_no_rows(self) -> None:
        builder = LexicalIndexBuilder()
        assert builder.finish() == CorpusStats(0, 0.0)
        assert list(builder.dfs) == []
        assert builder.weigh([]) == []

    def test_observing_after_finish_is_refused(self) -> None:
        builder = self._observed()
        builder.finish()
        with pytest.raises(ValueError, match="statistics are fixed"):
            builder.observe([(4, "e4", "late")])

    def test_weighing_a_term_pass_one_never_saw_is_a_caller_bug(self) -> None:
        builder = self._observed()
        with pytest.raises(KeyError):
            builder.weigh([(9, "e9", "unseen_term")])
