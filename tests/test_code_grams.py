"""Unit tests for the code-oriented byte-trigram tokenizer and query planner."""

from __future__ import annotations

from vfs.code_grams import (
    GRAM_SIZE,
    GramAnd,
    GramAny,
    GramOr,
    build_code_gram_query,
    fold_content,
    grams_for_fixed_string,
    iter_code_grams,
    normalize_content,
    pack_gram,
    unique_code_grams,
    unpack_gram,
)

# ---------------------------------------------------------------------------
# Normalization and packing
# ---------------------------------------------------------------------------


def test_normalize_collapses_crlf_and_cr() -> None:
    assert normalize_content("a\r\nb\rc\nd") == b"a\nb\nc\nd"


def test_normalize_passes_through_when_no_carriage_returns() -> None:
    assert normalize_content("hello\nworld") == b"hello\nworld"


def test_pack_unpack_roundtrip_for_ascii() -> None:
    gram = pack_gram(0x66, 0x6F, 0x6F)  # "foo"
    assert unpack_gram(gram) == b"foo"


def test_pack_unpack_roundtrip_for_high_bytes() -> None:
    # Byte sequence inside the UTF-8 encoding of a non-ASCII code point.
    gram = pack_gram(0xE2, 0x9C, 0x93)  # part of "✓"
    assert unpack_gram(gram) == b"\xe2\x9c\x93"


def test_pack_uses_24_bits_only() -> None:
    gram = pack_gram(0xFF, 0xFF, 0xFF)
    assert gram == 0xFFFFFF
    assert gram >> 24 == 0


# ---------------------------------------------------------------------------
# Sliding byte trigram tokenizer
# ---------------------------------------------------------------------------


def _grams_as_bytes(content: str, *, folded: bool = False) -> list[bytes]:
    return [unpack_gram(g) for g in iter_code_grams(content, folded=folded)]


def test_short_inputs_have_no_grams() -> None:
    assert _grams_as_bytes("") == []
    assert _grams_as_bytes("a") == []
    assert _grams_as_bytes("ab") == []


def test_basic_ascii_trigrams() -> None:
    assert _grams_as_bytes("hello") == [b"hel", b"ell", b"llo"]


def test_trigrams_preserve_punctuation_and_operators() -> None:
    grams = _grams_as_bytes("foo|bar")
    assert b"oo|" in grams
    assert b"o|b" in grams
    assert b"|ba" in grams


def test_trigrams_preserve_path_separators() -> None:
    grams = _grams_as_bytes("path/to/file.py")
    assert b"th/" in grams
    assert b"h/t" in grams
    assert b"/to" in grams
    assert b"to/" in grams


def test_trigrams_preserve_whitespace() -> None:
    grams = _grams_as_bytes("a b\tc")
    assert b"a b" in grams
    assert b" b\t" in grams
    assert b"b\tc" in grams


def test_trigrams_cross_normalized_newlines() -> None:
    grams = _grams_as_bytes("a\r\nb")
    assert b"a\nb" in grams


def test_trigrams_walk_inside_utf8_byte_sequence() -> None:
    # "a✓b" => 61 e2 9c 93 62, so we expect grams crossing the multibyte char.
    grams = _grams_as_bytes("a✓b")
    assert b"a\xe2\x9c" in grams
    assert b"\xe2\x9c\x93" in grams
    assert b"\x9c\x93b" in grams


def test_unique_code_grams_dedupes() -> None:
    assert unique_code_grams("aaaaa") == {pack_gram(ord("a"), ord("a"), ord("a"))}


def test_iter_code_grams_does_not_dedupe() -> None:
    assert len(list(iter_code_grams("aaaaa"))) == len("aaaaa") - GRAM_SIZE + 1


def test_folded_grams_lowercase_ascii() -> None:
    raw = unique_code_grams("Hello")
    folded = unique_code_grams("Hello", folded=True)
    assert raw != folded
    assert folded == unique_code_grams("hello")


def test_fold_content_uses_unicode_casefold() -> None:
    # German sharp-s casefolds to "ss"; this is why ``casefold`` is preferred
    # over ``lower`` for case-insensitive search.
    assert fold_content("Straße") == "strasse"


# ---------------------------------------------------------------------------
# Fixed-string gram extraction
# ---------------------------------------------------------------------------


def test_grams_for_fixed_string_returns_all_trigrams() -> None:
    assert grams_for_fixed_string("postgres") == unique_code_grams("postgres")


def test_grams_for_fixed_string_short_input() -> None:
    assert grams_for_fixed_string("ab") == set()


def test_grams_for_fixed_string_includes_punctuation() -> None:
    grams = grams_for_fixed_string("a?.b")
    assert pack_gram(ord("a"), ord("?"), ord(".")) in grams


# ---------------------------------------------------------------------------
# build_code_gram_query — fixed strings
# ---------------------------------------------------------------------------


def test_query_fixed_string_emits_and() -> None:
    query = build_code_gram_query("postgres", fixed_strings=True)
    assert isinstance(query, GramAnd)
    assert query.required_grams() == unique_code_grams("postgres")


def test_query_fixed_string_too_short_degrades_to_any() -> None:
    query = build_code_gram_query("ab", fixed_strings=True)
    assert isinstance(query, GramAny)


def test_query_empty_pattern_is_any() -> None:
    assert isinstance(build_code_gram_query(""), GramAny)


# ---------------------------------------------------------------------------
# build_code_gram_query — regex literals
# ---------------------------------------------------------------------------


def test_query_simple_literal_regex_extracts_run() -> None:
    query = build_code_gram_query("postgres")
    assert isinstance(query, GramAnd)
    assert query.required_grams() == unique_code_grams("postgres")


def test_query_dot_star_breaks_run_but_keeps_neighbouring_literals() -> None:
    query = build_code_gram_query("foo.*bar")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("foo") <= query.required_grams()
    assert unique_code_grams("bar") <= query.required_grams()
    # The "." must NOT appear as a literal in any required gram.
    assert pack_gram(ord("o"), ord("o"), ord(".")) not in query.required_grams()


def test_query_quantified_char_does_not_appear_in_run() -> None:
    # ``a?b`` allows zero ``a``s — the only guaranteed literal is "b".
    query = build_code_gram_query("a?bcd")
    assert isinstance(query, GramAnd)
    # We should have grams from "bcd" (length 3).
    assert pack_gram(ord("b"), ord("c"), ord("d")) in query.required_grams()
    # And no gram should rely on the optional "a".
    assert pack_gram(ord("a"), ord("b"), ord("c")) not in query.required_grams()


def test_query_character_class_breaks_run() -> None:
    query = build_code_gram_query("[a-z]+Exception")
    assert isinstance(query, GramAnd)
    # All Exception trigrams should be required.
    assert unique_code_grams("Exception") <= query.required_grams()


def test_query_no_useful_literals_degrades_to_any() -> None:
    # ``a.*b`` has no run of length >= 3.
    assert isinstance(build_code_gram_query("a.*b"), GramAny)
    assert isinstance(build_code_gram_query(".*"), GramAny)
    assert isinstance(build_code_gram_query("[a-z]{2,}"), GramAny)


# ---------------------------------------------------------------------------
# build_code_gram_query — alternation
# ---------------------------------------------------------------------------


def test_query_top_level_alternation_emits_or() -> None:
    query = build_code_gram_query("foo|bar")
    assert isinstance(query, GramOr)
    assert len(query.branches) == 2
    branch_grams = {frozenset(b.required_grams()) for b in query.branches}
    assert frozenset(unique_code_grams("foo")) in branch_grams
    assert frozenset(unique_code_grams("bar")) in branch_grams


def test_query_alternation_with_unconstrained_branch_is_any() -> None:
    # Second branch has no useful literals, so the whole OR is unsafe.
    assert isinstance(build_code_gram_query("foo|a.*b"), GramAny)


def test_query_grouped_alternation_extracts_neighbour_literals() -> None:
    # ``Postgres(FileSystem|Backend)`` is not a top-level alternation — the
    # ``(`` is balanced — so we treat it as a literal-run pattern. The
    # guaranteed literal is "Postgres"; the alternation contributes no
    # required grams in this conservative tier.
    query = build_code_gram_query("Postgres(FileSystem|Backend)")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("Postgres") <= query.required_grams()


# ---------------------------------------------------------------------------
# build_code_gram_query — unsafe constructs
# ---------------------------------------------------------------------------


def test_query_lookahead_keeps_outer_literal() -> None:
    # ``foo(?=bar)`` matches lines that contain "foo" with "bar" right after.
    # The outer "foo" literal IS in the matched line — sound to require its
    # grams. We flush at the assertion boundary so "bar" is not required as a
    # gram even though it must appear; tightening this would require treating
    # zero-width assertions as forward-extending the literal run.
    query = build_code_gram_query("foo(?=bar)")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("foo") <= query.required_grams()


def test_query_lookbehind_keeps_outer_literal() -> None:
    query = build_code_gram_query("(?<=foo)bar")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("bar") <= query.required_grams()


def test_query_negative_lookahead_keeps_outer_literal() -> None:
    query = build_code_gram_query("foo(?!bar)")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("foo") <= query.required_grams()


def test_query_negative_lookbehind_keeps_outer_literal() -> None:
    query = build_code_gram_query("(?<!foo)bar")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("bar") <= query.required_grams()


def test_query_lookaround_only_pattern_is_any() -> None:
    # Pattern is just a lookahead — no outer literal to require.
    assert isinstance(build_code_gram_query("(?=foo)"), GramAny)


# ---------------------------------------------------------------------------
# Folded query mode
# ---------------------------------------------------------------------------


def test_query_fixed_string_folded_uses_lowercase_grams() -> None:
    query = build_code_gram_query("Postgres", fixed_strings=True, folded=True)
    assert isinstance(query, GramAnd)
    assert query.required_grams() == unique_code_grams("postgres")


def test_query_alternation_folded() -> None:
    query = build_code_gram_query("FOO|Bar", folded=True)
    assert isinstance(query, GramOr)
    branch_grams = {frozenset(b.required_grams()) for b in query.branches}
    assert frozenset(unique_code_grams("foo")) in branch_grams
    assert frozenset(unique_code_grams("bar")) in branch_grams


# ---------------------------------------------------------------------------
# AST-walker soundness — adversarial cases surfaced by the audit
# ---------------------------------------------------------------------------


def test_named_group_does_not_demand_group_name_grams() -> None:
    # Group names like ``name`` must not appear as required grams: the regex
    # engine consumes them at parse time, so they are never in matched bytes.
    query = build_code_gram_query("(?P<name>foo)bar")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foobar")
    assert query.required_grams() <= matched_bytes


def test_inline_comment_does_not_inject_grams() -> None:
    query = build_code_gram_query("foo(?#xxx)bar")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foobar")
    assert query.required_grams() <= matched_bytes


def test_verbose_mode_ignores_whitespace() -> None:
    query = build_code_gram_query("(?x)foo bar baz")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foobarbaz")
    assert query.required_grams() <= matched_bytes


def test_hex_escape_resolves_to_byte() -> None:
    # ``\x66`` is the literal ``f``; pattern matches ``foo``.
    query = build_code_gram_query(r"\x66oo")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foo")
    assert query.required_grams() <= matched_bytes


def test_unicode_escape_resolves_to_byte() -> None:
    query = build_code_gram_query(r"foo")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foo")
    assert query.required_grams() <= matched_bytes


def test_optional_group_does_not_force_inner_grams() -> None:
    # ``(foo)?bar`` matches ``bar`` without ``foo``, so ``foo`` is NOT
    # required.
    query = build_code_gram_query("(foo)?bar")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("bar")
    assert query.required_grams() <= matched_bytes


def test_zero_or_more_group_does_not_force_inner_grams() -> None:
    query = build_code_gram_query("(?:foo)?bar")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("bar")
    assert query.required_grams() <= matched_bytes


def test_zero_repeat_range_group_does_not_force_inner_grams() -> None:
    query = build_code_gram_query("(abc){0,3}xyz")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("xyz")
    assert query.required_grams() <= matched_bytes


def test_required_repeat_group_keeps_inner_grams() -> None:
    # ``(?:foo){2}bar`` requires ``foo`` to appear; inner literals are OK.
    query = build_code_gram_query("(?:foo){2}bar")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foofoobar")
    assert query.required_grams() <= matched_bytes
    # And both "foo" and "bar" trigrams should be in the required set.
    assert unique_code_grams("foo") <= query.required_grams()
    assert unique_code_grams("bar") <= query.required_grams()


def test_scoped_inline_flag_does_not_emit_case_sensitive_grams() -> None:
    # ``(?i:FOO)bar`` matches ``Foobar`` etc.; in raw (case-sensitive) mode
    # the planner must NOT require ``FOO`` grams because content might have
    # ``Foo``. Only ``bar`` is required.
    query = build_code_gram_query("(?i:FOO)bar", folded=False)
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("Foobar")
    assert query.required_grams() <= matched_bytes


def test_scoped_inline_flag_under_folded_emits_lower_grams() -> None:
    # In folded mode the index is lowercased, so an inline ``(?i:...)`` is a
    # no-op against the folded byte stream.
    query = build_code_gram_query("(?i:FOO)bar", folded=True)
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("Foobar", folded=True)
    assert query.required_grams() <= matched_bytes
    assert unique_code_grams("foo") <= query.required_grams()


def test_negated_scoped_flag_under_outer_ignorecase() -> None:
    # ``(?i)(?-i:Exact)or`` — outer is case-insensitive, inner island is
    # case-sensitive. In folded mode we still emit ``exact`` (folded) which
    # is sound because the folded indexer also lowercased the content.
    query = build_code_gram_query("(?i)(?-i:Exact)or", folded=True)
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("Exactor", folded=True)
    assert query.required_grams() <= matched_bytes


def test_three_way_alternation_is_or_of_branches() -> None:
    query = build_code_gram_query("foo|bar|baz")
    assert isinstance(query, GramOr)
    assert len(query.branches) == 3
    branch_grams = {frozenset(b.required_grams()) for b in query.branches}
    assert frozenset(unique_code_grams("foo")) in branch_grams
    assert frozenset(unique_code_grams("bar")) in branch_grams
    assert frozenset(unique_code_grams("baz")) in branch_grams


def test_escaped_pipe_is_literal_not_alternation() -> None:
    # ``a\|b`` matches the literal ``a|b`` — single-AND, not alternation.
    query = build_code_gram_query(r"a\|b")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("a|b")
    assert query.required_grams() <= matched_bytes
    # And the literal "|" trigram should be requirable.
    assert pack_gram(ord("a"), ord("|"), ord("b")) in query.required_grams()


def test_pipe_inside_char_class_is_not_alternation() -> None:
    # ``foo[a|b]bar`` — the ``|`` is a literal inside the class.
    query = build_code_gram_query("foo[a|b]bar")
    assert isinstance(query, GramAnd)
    # "foo" and "bar" are required; the class itself contributes nothing.
    assert unique_code_grams("foo") <= query.required_grams()
    assert unique_code_grams("bar") <= query.required_grams()


def test_invalid_regex_degrades_to_any() -> None:
    # Unbalanced parens — sre_parse raises; we degrade rather than propagate.
    assert isinstance(build_code_gram_query("foo(bar"), GramAny)


def test_backref_does_not_emit_grams_for_referenced_group() -> None:
    # ``(foo)\1`` matches ``foofoo``. Backref content is dynamic.
    query = build_code_gram_query(r"(foo)\1")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foofoo")
    assert query.required_grams() <= matched_bytes


def test_atomic_group_does_not_break_soundness() -> None:
    query = build_code_gram_query("(?>foo)bar")
    # We currently degrade unknown ops to flush; verify whatever shape we
    # return is sound — every required gram must appear in a real match.
    matched_bytes = unique_code_grams("foobar")
    if isinstance(query, GramAnd):
        assert query.required_grams() <= matched_bytes


def test_dot_with_dotall_flag_is_not_a_literal() -> None:
    # ``(?s)foo.bar`` — under DOTALL, ``.`` matches newline too. It still
    # matches one byte, but we don't know which, so the run flushes.
    query = build_code_gram_query("(?s)foo.bar")
    assert isinstance(query, GramAnd)
    assert unique_code_grams("foo") <= query.required_grams()
    assert unique_code_grams("bar") <= query.required_grams()


def test_word_boundary_does_not_break_run() -> None:
    # ``\b`` is a zero-width assertion; the literal ``foobar`` is still
    # required.
    query = build_code_gram_query(r"\bfoobar\b")
    assert isinstance(query, GramAnd)
    matched_bytes = unique_code_grams("foobar")
    assert query.required_grams() <= matched_bytes


# ---------------------------------------------------------------------------
# Unicode normalization — index/query agreement
# ---------------------------------------------------------------------------


def test_nfc_and_nfd_produce_same_grams_raw() -> None:
    # ``café`` in NFC vs NFD must yield the same byte trigrams so the index
    # writer and query planner agree regardless of source encoding.
    nfc = "café"
    nfd = "café"
    assert unique_code_grams(nfc) == unique_code_grams(nfd)


def test_nfc_and_nfd_produce_same_grams_folded() -> None:
    nfc = "Café"
    nfd = "Café"
    assert unique_code_grams(nfc, folded=True) == unique_code_grams(nfd, folded=True)


def test_german_eszett_folds_to_ss() -> None:
    # ``Straße`` casefolds to ``strasse`` per Unicode rules. The folded index
    # and folded query agree on this byte stream.
    assert unique_code_grams("Straße", folded=True) == unique_code_grams("strasse")


def test_pattern_lone_surrogate_degrades_to_any() -> None:
    # A pattern that cannot be UTF-8 encoded must not crash the planner.
    bad = "foo\ud800bar"
    result = build_code_gram_query(bad)
    # We accept either ANY or a sound AND — just must not raise.
    if isinstance(result, GramAnd):
        # Required grams must be encodable bytes; the only safe runs are
        # "foo" before the surrogate and "bar" after.
        assert all(0 <= g <= 0xFFFFFF for g in result.required_grams())
