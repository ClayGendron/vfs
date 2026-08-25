"""Tests for the byte-trigram tokenizer and the always-folded gram planner.

The load-bearing property is the module's own contract: the planner may
admit false positives but must never introduce false negatives — every
required gram of a pattern must exist in the folded index stream of any
content the pattern matches, where "matches" is defined solely by Python
``re`` over raw content. The regression classes pin the false-negative
families found by pressure testing: NFC in the gram pipeline (not
substring-stable against a raw-content verifier), the verifier's Turkic-i
case orbit exceeding ``casefold``, raw planning against a folded index,
and unsound group splicing. The expansion-upgrade classes pin the bounded
variant planner: per-upgrade shape rows (classes, alternations at any
depth, anchor transparency), the declared caps as cap-mutant rows, and a
match-preserving mutation fuzz.
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
    MAX_CLASS_MEMBERS,
    MAX_VARIANT_WIDTH,
    GramAnd,
    GramAny,
    GramOr,
    GramQuery,
    build_code_gram_query,
    fold_content,
    grams_for_fixed_string,
    iter_code_grams,
    normalize_content,
    pack_gram,
    unique_code_grams,
    unpack_gram,
)
from vfs.pattern_matching.glob import MAX_PATTERN_ARMS


def index_grams(content: str) -> set[int]:
    """Grams as index maintenance stores them: the single folded stream."""
    return unique_code_grams(content, folded=True)


def plan_satisfied(query: GramQuery, grams: set[int]) -> bool:
    """The candidate predicate as grep evaluates it: AND needs every gram, OR takes any branch."""
    if isinstance(query, GramAny):
        return True
    if isinstance(query, GramAnd):
        return query.grams <= grams
    return any(plan_satisfied(branch, grams) for branch in query.branches)


def branch_gram_sets(query: GramQuery) -> set[frozenset[int]]:
    """The plan's variants as comparable gram sets (a lone AND is one variant)."""
    if isinstance(query, GramAnd):
        return {query.grams}
    assert isinstance(query, GramOr)
    sets: set[frozenset[int]] = set()
    for branch in query.branches:
        assert isinstance(branch, GramAnd)
        sets.add(branch.grams)
    return sets


def assert_no_false_negative(pattern: str, content: str, *, fixed_strings: bool = False) -> None:
    """The soundness contract: matching content's folded index must satisfy the plan."""
    flags = 0 if fixed_strings else re.NOFLAG
    needle = re.escape(pattern) if fixed_strings else pattern
    assert re.search(needle, content, flags), "test setup: content must actually match"
    query = build_code_gram_query(pattern, fixed_strings=fixed_strings)
    assert plan_satisfied(query, index_grams(content)), (
        f"false negative: no variant of {pattern!r} satisfied by the index of {content!r}"
    )


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

    def test_a_lone_surrogate_meters_instead_of_raising(self) -> None:
        # A surrogate-carrying str (a pattern literal, a surrogatepass
        # decode) grams as the WTF-8 bytes the verify spelling produces.
        assert normalize_content("abc\ud800def") == "abc\ud800def".encode("utf-8", "surrogatepass")

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
        # The over-claim variant: "abc(d.)ghi" once required grams cdg and
        # dgh. The guaranteed "d" joins abc; the wildcard still severs.
        query = build_code_gram_query("abc(d.)ghi")
        assert query.required_grams() == unique_code_grams("abcd") | unique_code_grams("ghi")
        assert_no_false_negative("abc(d.)ghi", "zzabcdXghizz")

    def test_over_cap_class_group_breaks_adjacency(self) -> None:
        # [0-9] exceeds MAX_CLASS_MEMBERS, so the group's class keeps its
        # adjacency break; small classes fork variants instead.
        query = build_code_gram_query("abc([0-9])def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc([0-9])def", "zzabc5defzz")

    def test_nested_group_splices_its_guaranteed_prefix(self) -> None:
        # Groups are transparent: "de" joins abc; the wildcard still severs
        # before ghi, so no gram spanning the unknown byte is claimed.
        query = build_code_gram_query("abc(d(e.))ghi")
        assert query.required_grams() == unique_code_grams("abcde") | unique_code_grams("ghi")
        assert_no_false_negative("abc(d(e.))ghi", "zzabcdeXghizz")

    def test_capturing_alternation_composes_with_context(self) -> None:
        # Unlike (?:xx|yy), which sre inlines to a bare BRANCH, a capturing
        # group keeps its SUBPATTERN node — its arms fork sound variants.
        query = build_code_gram_query("abc(xx|yy)def")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("abcxxdef")),
            frozenset(unique_code_grams("abcyydef")),
        }
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

    def test_over_cap_character_classes_split_the_run(self) -> None:
        query = build_code_gram_query("abc[0-9]def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")
        assert_no_false_negative("abc[0-9]def", "zzabc7defzz")

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

    def test_anchors_are_adjacency_transparent(self) -> None:
        # Zero-width nodes contribute no bytes and sever no adjacency; the
        # flanking literals are byte-adjacent in any actual match.
        query = build_code_gram_query(r"^abc:\bdef$")
        assert query.required_grams() == grams_for_fixed_string("abc:def")
        assert_no_false_negative(r"^abc:\bdef$", "abc:def")

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

    def test_inner_alternation_composes_with_context(self) -> None:
        # A non-top-level BRANCH forks one variant per arm, each composed
        # with the surrounding literals. (Single-char alternatives optimize
        # to IN — the arms must be multi-char to parse as a real BRANCH.)
        query = build_code_gram_query("abc(?:xx|yy)def")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("abcxxdef")),
            frozenset(unique_code_grams("abcyydef")),
        }
        assert_no_false_negative("abc(?:xx|yy)def", "zzabcyydefzz")


# ---------------------------------------------------------------------------
# Expansion upgrades — declared caps, classes, alternations, anchors
# ---------------------------------------------------------------------------


class TestDeclaredCaps:
    def test_declared_cap_values(self) -> None:
        # The declared constants every cap-mutant row below is shaped by.
        assert MAX_CLASS_MEMBERS == 8
        assert MAX_VARIANT_WIDTH == 64

    def test_width_ceiling_matches_the_glob_surface(self) -> None:
        # Both pattern surfaces degrade at the same declared width.
        assert MAX_VARIANT_WIDTH == MAX_PATTERN_ARMS


class TestCharClassExpansion:
    def test_small_class_forks_one_variant_per_member(self) -> None:
        query = build_code_gram_query("ext[234]")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("ext2")),
            frozenset(unique_code_grams("ext3")),
            frozenset(unique_code_grams("ext4")),
        }
        assert_no_false_negative("ext[234]", "mount -t ext3 /dev/sda1")

    def test_folding_class_collapses_to_a_single_variant(self) -> None:
        # [fF] dedupes post-fold to one variant: [fF]oo now plans exactly
        # like (?i)foo — a plain AND on the folded run.
        query = build_code_gram_query("[fF]oo")
        assert isinstance(query, GramAnd)
        assert query.grams == frozenset(unique_code_grams("foo"))
        assert query.required_grams() == build_code_gram_query("(?i)foo").required_grams()
        assert_no_false_negative("[fF]oo", "seen Foo here")

    def test_ranges_enumerate_like_literal_members(self) -> None:
        query = build_code_gram_query("abc[x-z]def")
        assert branch_gram_sets(query) == {frozenset(unique_code_grams(f"abc{c}def")) for c in "xyz"}
        assert_no_false_negative("abc[x-z]def", "zzabcydefzz")

    def test_cap_boundary_class_expands(self) -> None:
        # Exactly MAX_CLASS_MEMBERS members expand — lowering the declared
        # cap below 8 fails this row (cap mutant).
        query = build_code_gram_query("abc[0-7]def")
        assert isinstance(query, GramOr)
        assert len(query.branches) == 8

    def test_over_cap_class_keeps_the_break(self) -> None:
        # Ten digits exceed the cap: no expansion, today's break — raising
        # the declared cap to 10+ fails this row (cap mutant).
        query = build_code_gram_query("abc[0-9]def")
        assert isinstance(query, GramAnd)
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")

    def test_negated_and_category_classes_keep_the_break(self) -> None:
        for pattern in ("abc[^xy]def", r"abc[\d]def", r"abc\wdef"):
            query = build_code_gram_query(pattern)
            assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def"), pattern

    def test_unencodable_class_members_keep_the_break(self) -> None:
        # A lone surrogate cannot be required as index bytes — as a class
        # literal or inside an enumerable range, the class keeps its break.
        for pattern in ("abc[x\ud800]def", "abc[\ud800-\ud802]def"):
            query = build_code_gram_query(pattern)
            assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def"), pattern

    def test_multi_range_class_over_cap_post_fold(self) -> None:
        # Each range fits the cap on its own; their union (9 members after
        # the fold) exceeds it, so the class keeps its break.
        query = build_code_gram_query("abc[a-fx-z]def")
        assert query.required_grams() == unique_code_grams("abc") | unique_code_grams("def")


class TestAlternationCrossProducts:
    def test_prefix_factored_alternation_is_indexable(self) -> None:
        # sre factors the shared first char: min|max parses as m(in|ax),
        # not a top-level BRANCH — the any-depth handling must see it.
        query = build_code_gram_query("min|max")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("min")),
            frozenset(unique_code_grams("max")),
        }
        assert_no_false_negative("min|max", "min value found")

    def test_group_alternation_composes_with_context(self) -> None:
        query = build_code_gram_query("foo_(bar|baz)")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("foo_bar")),
            frozenset(unique_code_grams("foo_baz")),
        }
        assert_no_false_negative("foo_(bar|baz)", "call foo_baz(x)")

    def test_anchored_group_alternation_composes(self) -> None:
        query = build_code_gram_query("^(import|from)")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("import")),
            frozenset(unique_code_grams("from")),
        }
        assert_no_false_negative("^(import|from)", "from vfs import base")

    def test_gramless_arm_still_collapses_the_or(self) -> None:
        # The collapse law survives the upgrades: the "#" arm can guarantee
        # no trigram, so the whole disjunction is unconstrained.
        assert isinstance(build_code_gram_query("^(#|Using)"), GramAny)

    def test_repeated_alternation_forks_standalone_arms(self) -> None:
        # Every repetition matches one arm, so at least one arm's grams
        # appear; adjacency to the context is severed by the repeat.
        query = build_code_gram_query("(foo|bar)+")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("foo")),
            frozenset(unique_code_grams("bar")),
        }
        assert_no_false_negative("(foo|bar)+", "barfoo run")

    def test_width_cap_arm_boundary(self) -> None:
        # 64 arms survive; a 65th degrades the whole alternation to the
        # break — raising the declared width ceiling fails this row.
        arms = [f"a{i:02d}" for i in range(65)]
        wide = build_code_gram_query("needle(" + "|".join(arms[:64]) + ")")
        assert isinstance(wide, GramOr)
        assert len(wide.branches) == 64
        over = build_code_gram_query("needle(" + "|".join(arms) + ")")
        # sre hoists the arms' shared "a", so it stays adjacent to needle.
        assert isinstance(over, GramAnd)
        assert over.required_grams() == unique_code_grams("needlea")


class TestAnchorTransparency:
    def test_anchors_join_runs_across_zero_width_nodes(self) -> None:
        query = build_code_gram_query(r"foo:\bbar")
        assert query.required_grams() == grams_for_fixed_string("foo:bar")
        assert_no_false_negative(r"foo:\bbar", "zzfoo:barzz")

    def test_boundary_wrapped_short_literal_is_one_run(self) -> None:
        query = build_code_gram_query(r"\bmin\b")
        assert isinstance(query, GramAnd)
        assert query.required_grams() == unique_code_grams("min")
        assert_no_false_negative(r"\bmin\b", "the min value")

    def test_unsatisfiable_assertion_is_vacuously_sound(self) -> None:
        # foo\bbar has no matches (word chars flank the boundary): there is
        # no content to lose, so requiring the joined grams is sound.
        assert re.search(r"foo\bbar", "foobar") is None
        query = build_code_gram_query(r"foo\bbar")
        assert query.required_grams() == grams_for_fixed_string("foobar")


class TestCompositionCaps:
    def test_junk_class_cannot_starve_a_gram_bearing_branch(self) -> None:
        # The monotonicity guard: over-cap digit classes break instead of
        # expanding, so the branch carrying every gram keeps its width.
        pattern = r" +[0-9]+\.[0-9]+% .* (Interpreter|jdk\.internal).*"
        query = build_code_gram_query(pattern)
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams(" interpreter")),
            frozenset(unique_code_grams(" jdk.internal")),
        }
        assert_no_false_negative(pattern, "  3.14% x Interpreter::run")

    def test_class_products_compose_up_to_the_ceiling(self) -> None:
        query = build_code_gram_query("[0-7][0-7]abcd")
        assert isinstance(query, GramOr)
        assert len(query.branches) == 64
        assert_no_false_negative("[0-7][0-7]abcd", "zz37abcdzz")

    def test_over_ceiling_product_degrades_the_last_node(self) -> None:
        # The third class would push the product to 128: it degrades to
        # the break and the surviving variants dedupe to one AND on "abcd"
        # — raising the width ceiling to 128+ fails this row (cap mutant).
        query = build_code_gram_query("[0-7][0-7][01]abcd")
        assert isinstance(query, GramAnd)
        assert query.grams == frozenset(unique_code_grams("abcd"))
        assert_no_false_negative("[0-7][0-7][01]abcd", "zz370abcdzz")

    def test_class_inside_branch_inside_anchored_group(self) -> None:
        query = build_code_gram_query("^(ext[23]|xfs)$")
        assert branch_gram_sets(query) == {
            frozenset(unique_code_grams("ext2")),
            frozenset(unique_code_grams("ext3")),
            frozenset(unique_code_grams("xfs")),
        }
        assert_no_false_negative("^(ext[23]|xfs)$", "ext3")


class TestUpgradeSoundness:
    def test_upgraded_plans_never_prune_matching_content(self) -> None:
        rows = [
            ("[fF]oo", "seen Foo here"),
            ("^(import|from)", "from vfs import base"),
            ("foo_(bar|baz)", "call foo_baz(x)"),
            ("MAP_(UNINITIALIZED|TYPE|SHARED_VALIDATE)", "flags & MAP_TYPE"),
            ("ext[234]|jfs|xfs", "mount -t ext3 /dev/sda1"),
            ("(?i)mutex_lock", "called Mutex_Lock(&lock)"),
            (r"^#define HWCAP[0-9]*_[A-Z0-9_]+", "#define HWCAP2_SVE2 (1 << 1)"),
        ]
        for pattern, content in rows:
            assert_no_false_negative(pattern, content)

    def test_upgrade_fuzz_holds_the_no_false_negative_invariant(self) -> None:
        # Seeded fuzz across all three upgrades: slice the content, then
        # mutate the pattern in ways that provably preserve the match —
        # fork a char into a class, fork a tail into an alternation with a
        # junk arm, anchor at content edges.
        rng = random.Random(0x100)
        alphabet = "abcdefF ßı"
        for _ in range(500):
            content = "".join(rng.choice(alphabet) for _ in range(rng.randint(6, 24)))
            length = rng.randint(4, min(10, len(content)))
            start = rng.randint(0, len(content) - length)
            span = content[start : start + length]
            parts = [re.escape(c) for c in span]
            mutation = rng.random()
            if mutation < 0.4:
                i = rng.randrange(len(span))
                if span[i].isalpha():
                    parts[i] = f"[{span[i]}{rng.choice('qz')}]"
            elif mutation < 0.8:
                i = rng.randint(1, len(span) - 1)
                junk = "".join(rng.choice("qz") for _ in range(3))
                parts[i:] = [f"({''.join(parts[i:])}|{junk})"]
            pattern = "".join(parts)
            if start == 0 and rng.random() < 0.5:
                pattern = "^" + pattern
            if start + length == len(content) and rng.random() < 0.5:
                pattern = pattern + "$"
            assert_no_false_negative(pattern, content)
