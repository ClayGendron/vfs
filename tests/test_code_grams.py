"""Tests for the byte-trigram tokenizer and the always-folded gram planner.

The load-bearing property is the module's own contract: the planner may
admit false positives but must never introduce false negatives — every
required gram of a pattern must exist in the folded index stream of any
content the pattern matches, where "matches" is defined solely by Python
``re`` over raw content. The regression classes pin the false-negative
families found by pressure testing: NFC in the gram pipeline (not
substring-stable against a raw-content verifier), the verifier's Turkic-i
case orbit exceeding ``casefold``, raw planning against a folded index,
and unsound group splicing.
"""

from __future__ import annotations

import random
import re
import sys

# sre's case-orbit fix-up table (typeshed has no stub for it) — the source
# of the i / U+0131 / U+0130 unifications the fold must cover.
from re import _casefix  # ty: ignore[unresolved-import]

from vfs.models.code_grams import (
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


def index_grams(content: str) -> set[int]:
    """Grams as index maintenance stores them: the single folded stream."""
    return unique_code_grams(content, folded=True)


def assert_no_false_negative(pattern: str, content: str, *, fixed_strings: bool = False) -> None:
    """The soundness contract: pattern grams must all exist in matching content's index."""
    flags = 0 if fixed_strings else re.NOFLAG
    needle = re.escape(pattern) if fixed_strings else pattern
    assert re.search(needle, content, flags), "test setup: content must actually match"
    query = build_code_gram_query(pattern, fixed_strings=fixed_strings)
    missing = query.required_grams() - index_grams(content)
    assert not missing, f"false negative: grams {[unpack_gram(g) for g in missing]} not in index"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_pack_unpack_round_trip(self) -> None:
        gram = pack_gram(0x61, 0xCC, 0x81)
        assert unpack_gram(gram) == b"a\xcc\x81"

    def test_sliding_window_over_utf8_bytes(self) -> None:
        assert len(list(iter_code_grams("abcd"))) == 4 - GRAM_SIZE + 1
        assert list(iter_code_grams("ab")) == []

    def test_newlines_normalize_before_gramming(self) -> None:
        assert normalize_content("a\r\nb") == normalize_content("a\nb") == b"a\nb"

    def test_the_stream_is_raw_codepoints_never_normalized(self) -> None:
        # The verifier (re over raw content) is codepoint-exact and never
        # unifies canonical-equivalent forms \u2014 so neither does the index:
        # NFC and NFD spellings are different codepoints, different grams.
        nfc = "caf\u00e9 au lait"
        nfd = "cafe\u0301 au lait"
        assert re.search("caf\u00e9", nfd) is None  # the verifier can't match cross-form
        assert unique_code_grams(nfc) != unique_code_grams(nfd)

    def test_folding_lowercases_the_stream(self) -> None:
        assert index_grams("FOO BAR") == unique_code_grams("foo bar")
        assert fold_content("Stra\u00dfe") == "strasse"


# ---------------------------------------------------------------------------
# Regression 1 — NFC in the gram pipeline was a false-negative engine
# ---------------------------------------------------------------------------
# The verifier is re over RAW content and NFC is not substring-stable, so a
# normalized index stream lacked the grams of spans the verifier matched.
# The stream is now raw folded codepoints; these pin the confirmed repros.


class TestRawStreamNoNormalization:
    def test_same_form_patterns_match_same_form_content(self) -> None:
        assert_no_false_negative("cafe\u0301", "un cafe\u0301 noir")
        assert_no_false_negative("caf\u00e9", "un caf\u00e9 noir")

    def test_ascii_pattern_matches_decomposed_content(self) -> None:
        # The confirmed repro: pure-ASCII "abce" matches raw content where
        # an e+U+0301 follows at (2,6), but the NFC'd stream composed the
        # pair and the required gram "bce" vanished — a silent false
        # negative that dropped the file from grep candidates.
        assert_no_false_negative("abce", "xxabce\u0301yy")

    def test_casefold_never_mints_composition_sites(self) -> None:
        # Folding U+00DF (sharp s) to "ss" used to create a fresh s+mark
        # pair that NFC then composed into U+015B, destroying the
        # mark-adjacent grams.
        assert_no_false_negative("\u0301abc", "zz\u00df\u0301abczz")

    def test_combining_mark_group_still_splices_into_the_run(self) -> None:
        # Group transparency is codepoint-level now: e + ( U+0301 ) equals
        # the decomposed spelling, not the composed U+00E9 one.
        grouped = build_code_gram_query("cafe(\u0301)x")
        assert grouped.required_grams() == build_code_gram_query("cafe\u0301x").required_grams()
        assert grouped.required_grams() != build_code_gram_query("caf\u00e9x").required_grams()

    def test_decomposed_content_fuzz_never_false_negative(self) -> None:
        # Seeded port of the fuzzer that found this family (~62/5,495 cases
        # failed under the NFC pipeline): patterns sliced from raw content
        # rich in combining marks and fold-expanding codepoints.
        rng = random.Random(0x024)
        alphabet = "abce\u00df\u0301\u0307\u00e9\u0130\u0131"
        for _ in range(400):
            content = "".join(rng.choice(alphabet) for _ in range(rng.randint(4, 16)))
            length = rng.randint(3, min(6, len(content)))
            start = rng.randint(0, len(content) - length)
            pattern = re.escape(content[start : start + length])
            assert_no_false_negative(pattern, content)


# ---------------------------------------------------------------------------
# Regression 1b — the verifier's case orbit exceeds casefold (Turkic-i)
# ---------------------------------------------------------------------------


class TestTurkicIFold:
    def test_dotless_i_pattern_and_content_unify(self) -> None:
        # sre's _EXTRA_CASES table makes (?i) match i/I against U+0131,
        # which casefold alone does not unify — the confirmed false
        # negative in both directions.
        assert_no_false_negative("(?i)iii", "zz\u0131\u0131\u0131zz")
        assert_no_false_negative("(?i)\u0131\u0131\u0131", "zzIIIzz")
        assert_no_false_negative("\u0131\u0131\u0131", "zz\u0131\u0131\u0131zz")

    def test_dotted_capital_i_unifies_too(self) -> None:
        # Found while pinning the fix: sre uses SIMPLE lowercase, so
        # (?i)U+0130 matches plain "i" — while casefold explodes
        # U+0130 to i+U+0307 instead. A second breaker the original
        # orbit scan missed.
        assert_no_false_negative("(?i)\u0130bc", "zzibczz")
        assert_no_false_negative("(?i)ibc", "zz\u0130bczz")

    def test_every_verifier_case_orbit_pair_folds_identically(self) -> None:
        # The soundness invariant behind the fold: any two codepoints the
        # verifier treats as (?i)-equal must fold to identical text, or a
        # case-insensitive match is pruned before the verify. Exhaustive
        # over every codepoint's case variants plus sre's fix-up table.
        breakers: list[tuple[str, str]] = []
        for cp in range(sys.maxunicode + 1):
            c = chr(cp)
            variants = {c.lower(), c.upper(), c.title(), c.casefold()}
            variants |= {chr(v) for v in _casefix._EXTRA_CASES.get(cp, ())}
            for m in variants:
                if len(m) != 1 or m == c:
                    continue
                if re.fullmatch(f"(?i){re.escape(c)}", m) and fold_content(c) != fold_content(m):
                    breakers.append((hex(cp), hex(ord(m))))
        assert not breakers, f"verifier orbit exceeds the fold: {breakers}"


# ---------------------------------------------------------------------------
# Regression 2 — planning is always folded
# ---------------------------------------------------------------------------


class TestAlwaysFoldedPlanning:
    def test_case_sensitive_pattern_plans_against_the_folded_stream(self) -> None:
        # Raw grams for "Foo" do not exist in a folded index; planning must
        # fold and let the final verify enforce case.
        assert_no_false_negative("Foo", "Foo bar")

    def test_every_case_mode_produces_the_same_plan(self) -> None:
        expected = build_code_gram_query("foo!bar").required_grams()
        assert build_code_gram_query("Foo!Bar").required_grams() == expected
        assert build_code_gram_query("(?i)foo!bar").required_grams() == expected
        assert build_code_gram_query("(?i:foo!bar)").required_grams() == expected

    def test_fixed_strings_fold_too(self) -> None:
        assert grams_for_fixed_string("Foo Bar") == unique_code_grams("foo bar")

    def test_folding_can_shorten_below_gram_size_and_flip_to_any(self) -> None:
        # KELVIN SIGN is 3 UTF-8 bytes raw but folds to one-byte 'k': a
        # pattern that looks indexable can fold below GRAM_SIZE.
        pattern = "\u212a\u212a"
        assert len(pattern.encode()) >= GRAM_SIZE
        assert isinstance(build_code_gram_query(pattern, fixed_strings=True), GramAny)


# ---------------------------------------------------------------------------
# Regression 3 — non-literal group bodies spliced as if adjacent
# ---------------------------------------------------------------------------


class TestGroupSplicing:
    def test_wildcard_group_breaks_adjacency_on_both_sides(self) -> None:
        # The confirmed bug: "abc(.)def" demanded grams bcd/cde, which the
        # folded index of matching content "abcXdef" lacks.
        query = build_code_gram_query("abc(.)def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc(.)def", "zzabcXdefzz")

    def test_partial_inner_run_is_not_extended_to_the_group_edges(self) -> None:
        # The over-claim variant: "abc(d.)ghi" required grams cdg and dgh.
        query = build_code_gram_query("abc(d.)ghi")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("ghi")
        assert_no_false_negative("abc(d.)ghi", "zzabcdXghizz")

    def test_class_bearing_group_breaks_adjacency(self) -> None:
        query = build_code_gram_query("abc([xy])def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc([xy])def", "zzabcydefzz")

    def test_capturing_alternation_breaks_adjacency(self) -> None:
        # Unlike (?:xx|yy), which sre inlines to a bare BRANCH, a capturing
        # group keeps its SUBPATTERN node — the arm that spliced unsoundly.
        query = build_code_gram_query("abc(xx|yy)def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc(xx|yy)def", "zzabcyydefzz")

    def test_group_with_no_runs_does_not_leave_the_buffer_running(self) -> None:
        # A non-empty body yielding no runs must still break the outer run:
        # "abcXYdef" matches but its index has no gram spanning the group.
        query = build_code_gram_query("abc(..)def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc(..)def", "zzabcXYdefzz")

    def test_empty_group_stays_transparent(self) -> None:
        query = build_code_gram_query("abc()def")
        assert query.required_grams() == grams_for_fixed_string("abcdef")
        assert_no_false_negative("abc()def", "zzabcdefzz")

    def test_nested_pure_literal_groups_stay_transparent(self) -> None:
        query = build_code_gram_query("foo((bar))baz")
        assert query.required_grams() == grams_for_fixed_string("foobarbaz")

    def test_lone_surrogate_inside_a_group_is_opaque(self) -> None:
        query = build_code_gram_query("abc(\ud800)def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_group_fuzz_holds_the_no_false_negative_invariant(self) -> None:
        # Bounded, seeded port of the fuzzer that found this family: take a
        # slice of the content as the pattern, wrap an interior span in a
        # group, and usually opacify one grouped char — the pattern still
        # matches the content, so its required grams must be in the index.
        rng = random.Random(0x072)
        alphabet = "abcdef"
        for _ in range(500):
            content = "".join(rng.choice(alphabet) for _ in range(rng.randint(6, 24)))
            length = rng.randint(4, min(8, len(content)))
            start = rng.randint(0, len(content) - length)
            span = content[start : start + length]
            i = rng.randint(1, length - 2)
            j = rng.randint(i, length - 1)
            inner = span[i:j]
            if inner and rng.random() < 0.75:
                k = rng.randrange(len(inner))
                inner = inner[:k] + rng.choice((".", "[a-f]")) + inner[k + 1 :]
            pattern = f"{span[:i]}({inner}){span[j:]}"
            assert_no_false_negative(pattern, content)


# ---------------------------------------------------------------------------
# Planner structure
# ---------------------------------------------------------------------------


class TestPlannerStructure:
    def test_literal_pattern_is_a_conjunction(self) -> None:
        query = build_code_gram_query("hello")
        assert isinstance(query, GramAnd)
        assert query.required_grams() == unique_code_grams("hello")

    def test_top_level_alternation_becomes_an_or(self) -> None:
        query = build_code_gram_query("foobar|bazqux")
        assert isinstance(query, GramOr)
        assert query.required_grams() == unique_code_grams("foobar") | unique_code_grams("bazqux")

    def test_an_unconstrained_branch_collapses_the_or_to_any(self) -> None:
        # "ab" folds under GRAM_SIZE, so one branch has no predicate and
        # the disjunction cannot constrain anything.
        assert isinstance(build_code_gram_query("foobar|ab"), GramAny)

    def test_zero_min_repeats_are_dropped(self) -> None:
        query = build_code_gram_query("foo(bar)*")
        assert query.required_grams() == unique_code_grams("foo")

    def test_min_one_repeats_contribute_their_body(self) -> None:
        query = build_code_gram_query("(abc)+def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_character_classes_split_the_run(self) -> None:
        query = build_code_gram_query("abc[xy]def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc[xy]def", "zzabcxdefzz")

    def test_groups_are_adjacency_transparent(self) -> None:
        assert build_code_gram_query("foo(bar)baz").required_grams() == grams_for_fixed_string("foobarbaz")

    def test_lookaround_content_is_never_required(self) -> None:
        query = build_code_gram_query("foo(?=bar)")
        assert query.required_grams() == unique_code_grams("foo")

    def test_unparseable_and_empty_patterns_degrade_to_any(self) -> None:
        assert isinstance(build_code_gram_query("("), GramAny)
        assert isinstance(build_code_gram_query(""), GramAny)
        assert isinstance(build_code_gram_query("x"), GramAny)


class TestPlannerASTArms:
    def test_query_shape_methods(self) -> None:
        any_query = build_code_gram_query("x")
        assert any_query.is_any() is True
        assert any_query.required_grams() == set()
        or_query = build_code_gram_query("foobar|bazqux")
        assert or_query.is_any() is False
        and_query = build_code_gram_query("foobar")
        assert and_query.is_any() is False

    def test_negated_literal_splits_the_run(self) -> None:
        query = build_code_gram_query("abc[^x]def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_dot_splits_the_run(self) -> None:
        query = build_code_gram_query("abc.def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc.def", "zzabcXdefzz")

    def test_anchors_split_the_run(self) -> None:
        query = build_code_gram_query(r"^abc\bdef$")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_backreference_content_is_never_required(self) -> None:
        # The pure-literal group splices with the following literal into
        # one run; the backreference's dynamic content contributes nothing.
        query = build_code_gram_query(r"(abc)x\1")
        assert query.required_grams() == unique_code_grams("abcx")
        assert_no_false_negative(r"(abc)x\1", "zzabcxabczz")

    def test_negative_lookaround_content_is_never_required(self) -> None:
        query = build_code_gram_query("foobar(?!baz)")
        assert query.required_grams() == unique_code_grams("foobar")

    def test_unknown_constructs_split_conservatively(self) -> None:
        # Atomic groups are not descended into — soundness over strength.
        query = build_code_gram_query("(?>abc)def")
        assert query.required_grams() <= unique_code_grams("abcdef")

    def test_lone_surrogate_literal_splits_the_run(self) -> None:
        query = build_code_gram_query("abc\ud800def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_fixed_strings_through_the_public_builder(self) -> None:
        query = build_code_gram_query("Foo Bar", fixed_strings=True)
        assert isinstance(query, GramAnd)
        assert query.required_grams() == unique_code_grams("foo bar")

    def test_inner_alternation_splits_the_run_conservatively(self) -> None:
        # A non-top-level BRANCH contributes no grams; the runs around it
        # survive. (Single-char alternatives optimize to IN — the branches
        # must be multi-char to parse as a real BRANCH node.)
        query = build_code_gram_query("abc(?:xx|yy)def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc(?:xx|yy)def", "zzabcyydefzz")
