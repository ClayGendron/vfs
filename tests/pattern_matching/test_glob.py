"""Tests for vfs.pattern_matching.glob — the one glob compile chokepoint.

Pins the segment-aware contract: ``*`` within a segment, ``**`` across
segments, gitignore-exact anchoring (any ``/`` anchors at the root,
slash-free floats by name), dotfiles ordinary, mid-component ``**``
refused. The demo tree is the spec's acceptance table.
"""

from __future__ import annotations

import glob as stdlib_glob
import re
from itertools import product

import pytest

from tests.support.oracles import glob as oracle
from vfs.base import AsyncVirtualFileSystem
from vfs.paths import ROOT, Path
from vfs.pattern_matching import (
    GLOB_CHANNEL_LABELS,
    MAX_PATTERN_ARMS,
    DerivedExt,
    PatternError,
    canonical_pattern,
    compile_filter,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    escape_glob,
    expand_pattern,
    filter_paths,
    glob_defect,
    passes_filters,
    passes_row_filters,
    residuals,
)
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind

DEMO_TREE = [Path("/notes.txt"), Path("/docs/a.txt"), Path("/docs/deep/nested/b.txt")]


def matched(pattern: str, ext: tuple[str, ...] = ()) -> list[str]:
    glob = compile_filter(pattern, ext)
    return [str(path) for path in DEMO_TREE if glob.matches(path)]


# =========================================================================
# glob_defect
# =========================================================================


class TestGlobDefect:
    def test_mid_component_double_star_is_the_defect(self):
        assert glob_defect("a**b") is not None
        assert glob_defect("/docs/a**b.txt") is not None
        assert glob_defect("x**") is not None

    def test_triple_star_is_caught_by_the_same_rule(self):
        assert glob_defect("***") is not None
        assert glob_defect("/docs/***/x.txt") is not None

    def test_whole_component_double_star_is_legal(self):
        assert glob_defect("**") is None
        assert glob_defect("**/x.py") is None
        assert glob_defect("/docs/**/*.txt") is None

    def test_ordinary_patterns_have_no_defect(self):
        assert glob_defect("*.txt") is None
        assert glob_defect("/docs/*.txt") is None
        assert glob_defect("[ab]*.py") is None

    def test_empty_components_are_the_second_defect(self):
        # No stored path has an empty segment: letting these through
        # would be silent empty success (or, worse, a router-manufactured
        # match the authority rejects) — the same false-friend class.
        for pattern in ("/data/", "data/", "//data", "/data//x", "/*/", "**/", "/", ""):
            assert glob_defect(pattern) is not None, pattern

    def test_the_leading_anchor_slash_is_not_an_empty_component(self):
        assert glob_defect("/data/*.txt") is None
        assert glob_defect("/x") is None

    def test_the_defect_names_the_component(self):
        defect = glob_defect("/docs/a**b.txt")
        assert defect is not None
        assert "a**b.txt" in defect

    def test_malformed_braces_are_the_third_defect(self):
        assert glob_defect("{a,b") is not None  # unclosed
        assert glob_defect("a}b") is not None  # bare close
        assert glob_defect("x{}y") is not None  # empty group
        assert glob_defect("{a,{b,c}}") is not None  # nested

    def test_class_escaped_braces_are_not_brace_syntax(self):
        assert glob_defect("/f[{]a,b[}].txt") is None
        assert glob_defect("[{]") is None

    def test_brace_arms_are_component_gated_naming_the_arm(self):
        # Expansion can manufacture defects the raw text hides; the
        # refusal names the arm so the caller sees what was built.
        defect = glob_defect("x/{a,}")
        assert defect is not None
        assert "empty component" in defect
        assert "'x/'" in defect
        starred = glob_defect("{a**b,c}")
        assert starred is not None
        assert "'a**b'" in starred

    def test_well_formed_braces_have_no_defect(self):
        assert glob_defect("*.{ts,tsx}") is None
        assert glob_defect("{src,docs}/**/*.md") is None
        assert glob_defect("{a}") is None


# =========================================================================
# escape_glob — literal path text quoted for the pattern language
# =========================================================================


class TestEscapeGlob:
    def test_every_metachar_survives_the_round_trip(self):
        # The escaped text must compile defect-free and match exactly
        # itself — the literal-text law every composition seam leans on.
        for text in ("[x]", "{a,b}", "a*b", "c?d", "data [prod]", "*?[]{}", "[!x]", "[]]"):
            escaped = escape_glob(text)
            assert glob_defect(escaped) is None, escaped
            gate = compile_filter(escaped, ())
            assert gate.matches(Path(f"/{text}")), escaped

    def test_escaped_text_matches_nothing_else(self):
        assert not compile_filter(escape_glob("a*b"), ()).matches(Path("/ab"))
        assert not compile_filter(escape_glob("[x]"), ()).matches(Path("/x"))
        assert not compile_filter(escape_glob("c?d"), ()).matches(Path("/cxd"))

    def test_plain_text_is_untouched(self):
        assert escape_glob("/data/plain.txt") == "/data/plain.txt"
        assert escape_glob("a-b.c!d") == "a-b.c!d"


# =========================================================================
# expand_pattern — brace alternation into plain arms
# =========================================================================


class TestExpandPattern:
    def test_brace_free_patterns_pass_through(self):
        assert expand_pattern("*.py") == ("*.py",)
        assert expand_pattern("/src/**/*.md") == ("/src/**/*.md",)

    def test_alternation_and_cross_product(self):
        assert expand_pattern("*.{ts,tsx}") == ("*.ts", "*.tsx")
        assert expand_pattern("{a,b}/{c,d}") == ("a/c", "a/d", "b/c", "b/d")

    def test_single_and_empty_alternatives(self):
        assert expand_pattern("{a}") == ("a",)
        assert expand_pattern("x{a,}") == ("xa", "x")

    def test_mixed_subject_arms_are_legal(self):
        # One anchored arm, one floating arm — dispatch is per-pattern.
        assert expand_pattern("{src/a,b}") == ("src/a", "b")

    def test_duplicates_collapse_to_first_appearance(self):
        assert expand_pattern("{a,a}") == ("a",)
        assert expand_pattern("{a,ab}{b,}") == ("ab", "a", "abb")

    def test_class_escaped_braces_stay_literal(self):
        assert expand_pattern("/[{]a,b[}].txt") == ("/[{]a,b[}].txt",)

    def test_commas_and_classes_inside_groups(self):
        # A class inside an alternative may contain a comma or brace.
        assert expand_pattern("{[a,]x,y}") == ("[a,]x", "y")

    def test_class_edge_forms_stay_opaque_to_the_scanner(self):
        # A negated class and a leading-literal-] class both span whole.
        assert expand_pattern("[!,]{a,b}") == ("[!,]a", "[!,]b")
        assert expand_pattern("[]]{a,b}") == ("[]]a", "[]]b")

    def test_an_over_cap_expansion_refuses_naming_the_pattern_and_the_cap(self):
        pattern = "{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}"  # 2**7 = 128 arms
        with pytest.raises(PatternError, match=rf"^{re.escape(repr(pattern))}: expands past the arm cap \(64\)"):
            expand_pattern(pattern)

    def test_a_defective_pattern_refuses_with_identity_and_diagnosis(self):
        # The exception carries the pattern and the defect; the channel
        # label is the caller's to prefix — the language never knows it.
        with pytest.raises(PatternError, match=r"^'a\*\*b': '\*\*' inside a component"):
            expand_pattern("a**b")
        with pytest.raises(PatternError, match=r"^'x/\{a,\}': empty component.*expansion arm 'x/'"):
            expand_pattern("x/{a,}")

    def test_expansion_is_idempotent_over_its_own_arms(self):
        # A surface handed pre-expanded arms loses nothing by expanding again.
        for pattern in ("*.{ts,tsx}", "{src,docs}/**/*.md", "*.py"):
            arms = expand_pattern(pattern)
            assert tuple(arm for a in arms for arm in expand_pattern(a)) == arms

    def test_a_cap_sized_expansion_is_exact(self):
        pattern = "{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}"  # 2**6 = 64 arms
        arms = expand_pattern(pattern)
        assert len(arms) == MAX_PATTERN_ARMS
        assert len(set(arms)) == MAX_PATTERN_ARMS


# =========================================================================
# compile_glob — anchoring and segment semantics at the regex level
# =========================================================================


class TestCompileGlob:
    def test_star_stops_at_the_separator(self):
        regex = compile_glob("/docs/*.txt")
        assert regex.is_match("/docs/a.txt")
        assert not regex.is_match("/docs/deep/b.txt")

    def test_double_star_spans_segments_including_zero(self):
        regex = compile_glob("/docs/**/*.txt")
        assert regex.is_match("/docs/a.txt")
        assert regex.is_match("/docs/deep/nested/b.txt")

    def test_unanchored_path_pattern_anchors_at_the_root(self):
        regex = compile_glob("src/*.py")
        assert regex.is_match("/src/a.py")
        assert not regex.is_match("/x/src/a.py")

    def test_star_slash_pins_depth_one(self):
        regex = compile_glob("*/x.py")
        assert regex.is_match("/a/x.py")
        assert not regex.is_match("/a/b/x.py")
        assert not regex.is_match("/x.py")

    def test_explicit_double_star_prefix_reaches_root_level(self):
        regex = compile_glob("**/x.py")
        assert regex.is_match("/x.py")
        assert regex.is_match("/a/b/x.py")

    def test_question_mark_matches_one_non_separator_character(self):
        regex = compile_glob("/?.py")
        assert regex.is_match("/a.py")
        assert not regex.is_match("/ab.py")
        assert not regex.is_match("/a/b.py")

    def test_name_arm_pattern_compiles_over_names(self):
        regex = compile_glob("*.txt")
        assert regex.is_match("notes.txt")
        assert not regex.is_match("notes.py")

    def test_a_class_reducing_to_bare_bang_matches_any_character(self):
        # Inverted-range pruning can leave "!" alone in the class body
        # ([!z-a]); fnmatch's rule is "any character", never crash.
        for pattern in ("[!z-a]", "x[!z-a]y"):
            assert glob_defect(pattern) is None
            regex = compile_glob(pattern)
            assert regex.is_match(pattern.replace("[!z-a]", "q"))
            assert not regex.is_match(pattern.replace("[!z-a]", ""))


# =========================================================================
# compile_filter — the shared per-candidate predicate
# =========================================================================


class TestCompileFilter:
    def test_the_spec_acceptance_table(self):
        assert matched("/docs/*.txt") == ["/docs/a.txt"]
        assert matched("*/b.txt") == []
        assert matched("docs/*.txt") == ["/docs/a.txt"]
        assert matched("/docs/**/*.txt") == ["/docs/a.txt", "/docs/deep/nested/b.txt"]
        assert matched("*.txt") == ["/notes.txt", "/docs/a.txt", "/docs/deep/nested/b.txt"]
        assert matched("**/*.txt") == ["/notes.txt", "/docs/a.txt", "/docs/deep/nested/b.txt"]
        assert matched("/*.txt") == ["/notes.txt"]

    def test_filter_carries_the_anchored_pattern_for_the_prefilter(self):
        assert compile_filter("docs/*.txt", ()).pattern == "/docs/*.txt"
        assert compile_filter("/docs/*.txt", ()).pattern == "/docs/*.txt"
        assert compile_filter("*.txt", ()).pattern == "*.txt"

    def test_subject_rule_a_slash_selects_the_path_arm(self):
        assert compile_filter("*.txt", ()).by_path is False
        assert compile_filter("docs/*.txt", ()).by_path is True

    def test_name_arm_double_star_behaves_as_star(self):
        glob = compile_filter("**", ())
        assert all(glob.matches(path) for path in DEMO_TREE)

    def test_dotfiles_match_wildcards(self):
        glob = compile_filter("*", ())
        assert glob.matches(Path("/.hidden"))
        anchored = compile_filter("/docs/*", ())
        assert anchored.matches(Path("/docs/.hidden"))

    def test_matching_stays_case_sensitive(self):
        glob = compile_filter("a*", ())
        assert glob.matches(Path("/a.txt"))
        assert not glob.matches(Path("/A.txt"))

    def test_ext_gate_reads_the_path_derived_extension(self):
        glob = compile_filter("*", ext=(".PY",))
        assert glob.matches(Path("/x/a.py"))
        assert not glob.matches(Path("/x/a.txt"))
        assert glob.matches(Path("/x/dir.py"))  # kind-free: any path with the suffix

    def test_ext_gate_and_pattern_gate_compose(self):
        glob = compile_filter("/docs/*", ext=("txt",))
        assert glob.matches(Path("/docs/a.txt"))
        assert not glob.matches(Path("/docs/a.py"))
        assert not glob.matches(Path("/other/a.txt"))

    def test_pure_dotfile_has_no_extension_for_the_ext_gate(self):
        glob = compile_filter("*.txt", ext=("txt",))
        assert not glob.matches(Path("/.txt"))  # lexical ext is None
        without_ext = compile_filter("*.txt", ())
        assert without_ext.matches(Path("/.txt"))


# =========================================================================
# derive_ext — the pattern-pinned extension fact
# =========================================================================


class TestDeriveExt:
    """Unit rows on the pattern-derived extension — fires only when sound."""

    def test_pattern_tail_pins_the_extension(self):
        assert derive_ext("**/*.txt") == ("txt", ".txt")
        assert derive_ext("/docs/?.py") == ("py", ".py")
        assert derive_ext("[a].txt") == ("txt", ".txt")
        assert derive_ext("/docs/a.txt") == ("txt", ".txt")

    def test_derived_ext_lowercases_but_the_suffix_keeps_case(self):
        assert derive_ext("*.TXT") == DerivedExt(ext="txt", dot_suffix=".TXT")

    def test_underivable_patterns_return_none(self):
        assert derive_ext("*") is None
        assert derive_ext("*.*") is None  # wildcard is the whole tail
        assert derive_ext("**/Makefile*") is None  # no literal tail at all
        assert derive_ext("*.t?t") is None  # wildcard after the dot
        assert derive_ext("*rc") is None  # dotless tail
        assert derive_ext("*." + "x" * 33) is None  # past the column cap

    def test_a_class_after_the_dot_kills_the_derivation(self):
        # ']' must sit in the cut set: without it "*.[ch]" would derive
        # the literal ext "[ch]" and the pushdown would drop every row.
        assert derive_ext("*.[ch]") is None
        assert derive_ext("[.a]x") is None


# =========================================================================
# effective_pattern — roots + root-anchored filters
# =========================================================================


class TestEffectivePattern:
    def test_name_arm_patterns_pass_through_any_root(self):
        assert effective_pattern(ROOT, "*.txt") == "*.txt"
        assert effective_pattern(Path("/data"), "*.txt") == "*.txt"
        assert effective_pattern(Path("/data"), "**") == "**"

    def test_path_arm_patterns_join_under_the_root(self):
        assert effective_pattern(Path("/data"), "src/*.py") == "/data/src/*.py"
        assert effective_pattern(Path("/data"), "**/*.txt") == "/data/**/*.txt"

    def test_a_leading_slash_anchors_at_the_root_not_the_namespace(self):
        assert effective_pattern(Path("/data"), "/x/*.py") == "/data/x/*.py"

    def test_the_default_root_reduces_to_plain_anchoring(self):
        assert effective_pattern(ROOT, "src/*.py") == "/src/*.py"
        assert effective_pattern(ROOT, "/docs/*.txt") == "/docs/*.txt"
        assert effective_pattern(ROOT, "*/x.py") == "/*/x.py"

    def test_a_metachar_root_splices_as_literal_text(self):
        composed = effective_pattern(Path("/data/[x]"), "src/*.py")
        assert composed == "/data/[[]x[]]/src/*.py"
        regex = compile_glob(composed)
        assert regex.is_match("/data/[x]/src/a.py")
        assert not regex.is_match("/data/x/src/a.py")


# =========================================================================
# composed_pattern — one scope root folded into one spatial pattern
# =========================================================================


class TestComposedPattern:
    def test_name_arm_goes_spatial_under_the_root(self):
        assert composed_pattern(Path("/a/data"), "*.csv") == "/a/data/**/*.csv"
        assert composed_pattern(Path("/data"), "b.txt") == "/data/**/b.txt"

    def test_the_default_root_floats_from_the_namespace_root(self):
        assert composed_pattern(ROOT, "*.csv") == "/**/*.csv"

    def test_path_arm_delegates_to_effective_pattern(self):
        assert composed_pattern(Path("/data"), "src/*.py") == "/data/src/*.py"
        assert composed_pattern(Path("/data"), "**/*.txt") == "/data/**/*.txt"
        assert composed_pattern(ROOT, "src/*.py") == "/src/*.py"

    def test_a_leading_slash_keeps_the_direct_children_spelling(self):
        assert composed_pattern(Path("/a"), "/*.csv") == "/a/*.csv"

    def test_manufactured_adjacent_double_star_canonicalizes(self):
        # Composition itself mints the adjacency; canonicalization must
        # therefore sit downstream of composition, not only at parse.
        assert composed_pattern(Path("/a"), "**") == "/a/**"
        assert composed_pattern(ROOT, "**") == "/**"
        assert composed_pattern(Path("/a"), "**/**/x") == "/a/**/x"

    def test_a_composed_name_arm_still_hits_direct_children(self):
        # The named battery case: ** spans zero segments, so the float
        # made spatial loses no direct-child matches.
        regex = compile_glob(composed_pattern(Path("/a/data"), "*.csv"))
        assert regex.is_match("/a/data/x.csv")
        assert regex.is_match("/a/data/sub/deep/y.csv")
        assert not regex.is_match("/a/other.csv")

    def test_composition_preserves_well_formedness(self):
        for root, pattern in ((Path("/a"), "*.csv"), (ROOT, "**"), (Path("/a/b"), "src/*.py")):
            assert glob_defect(composed_pattern(root, pattern)) is None

    def test_a_metachar_root_composes_defect_free_and_literal(self):
        # ADR 030's worked example: the root is a path, never syntax —
        # a brace or bracket in it must not refuse or capture siblings.
        for name in ("data [prod]", "[x]", "{a,b}", "a*b", "c?d"):
            root = Path(f"/{name}")
            composed = composed_pattern(root, "*.csv")
            assert glob_defect(composed) is None, composed
            regex = compile_glob(composed)
            assert regex.is_match(f"/{name}/x.csv")
            assert not regex.is_match("/ab/x.csv")


# =========================================================================
# residuals — the segment-wise derivative at the mount seam
# =========================================================================


class TestResiduals:
    def test_the_root_binding_receives_the_pattern_verbatim(self):
        assert residuals("/data/*.txt", ROOT) == {("data", "*.txt")}

    def test_a_literal_prefix_is_consumed(self):
        assert residuals("/data/*.txt", Path("/data")) == {("*.txt",)}
        assert residuals("/data/deep/b.txt", Path("/data")) == {("deep", "b.txt")}

    def test_a_wildcard_component_consumes_a_matching_segment(self):
        assert residuals("/d*/x.txt", Path("/data")) == {("x.txt",)}
        assert residuals("/*/x.txt", Path("/data")) == {("x.txt",)}

    def test_a_character_class_consumes_like_a_wildcard(self):
        assert residuals("/[dD]ata/x.txt", Path("/data")) == {("x.txt",)}
        assert residuals("/[xy]ata/x.txt", Path("/data")) == frozenset()

    def test_double_star_survives_consumption(self):
        assert residuals("/**/*.txt", Path("/data")) == {("**", "*.txt")}
        assert residuals("/**/*.txt", Path("/deep/nested")) == {("**", "*.txt")}

    def test_double_star_may_also_match_zero_components(self):
        # The ambiguous case: ** either spans "api" or stops before it —
        # both derivatives are live, and the set is the whole answer.
        assert residuals("/data/**/api/*.txt", Path("/data/api")) == {
            ("**", "api", "*.txt"),
            ("*.txt",),
        }

    def test_a_dead_prefix_yields_the_empty_set(self):
        assert residuals("/docs/*.md", Path("/data")) == frozenset()
        assert residuals("/data/api/*.py", Path("/data/apix")) == frozenset()

    def test_exhaustion_at_the_bind_point_is_the_empty_tuple(self):
        assert residuals("/data", Path("/data")) == {()}
        assert residuals("/d*", Path("/data")) == {()}
        assert residuals("/*", Path("/data")) == {()}

    def test_a_trailing_double_star_stays_live(self):
        assert residuals("/data/**", Path("/data")) == {("**",)}

    def test_adjacent_double_stars_canonicalize_to_one(self):
        # ``**/**`` matches what one ``**`` matches; without the collapse
        # the zero-match arm starves and mounted rows silently vanish.
        assert residuals("/**/**/x.txt", Path("/data")) == residuals("/**/x.txt", Path("/data"))
        assert residuals("/**/**/a/*", Path("/b/a")) == {("**", "a", "*"), ("*",)}

    def test_a_nested_mount_consumes_across_both_bind_segments(self):
        assert residuals("/deep/data/api/*.py", Path("/deep/data")) == {("api", "*.py")}
        assert residuals("/deep/data/api/*.py", Path("/deep/data/api")) == {("*.py",)}

    def test_rendering_a_residual_is_an_anchored_entry_local_pattern(self):
        (residual,) = residuals("/data/deep/*.txt", Path("/data"))
        assert "/" + "/".join(residual) == "/deep/*.txt"


class TestFilterPaths:
    """The public path filter — a pure predicate over paths in hand."""

    def test_keeps_matches_in_input_order_with_duplicates(self) -> None:
        paths = [Path("/b.txt"), Path("/a.md"), Path("/a.txt"), Path("/b.txt")]
        assert filter_paths(paths, "*.txt") == ["/b.txt", "/a.txt", "/b.txt"]

    def test_ext_and_anchoring_apply_like_every_other_surface(self) -> None:
        paths = [Path("/src/a.py"), Path("/lib/a.py"), Path("/src/b.txt")]
        assert filter_paths(paths, "/src/*") == ["/src/a.py", "/src/b.txt"]
        assert filter_paths(paths, "*", ("py",)) == ["/src/a.py", "/lib/a.py"]

    def test_meta_paths_are_never_hidden(self) -> None:
        assert filter_paths([Path("/.vfs/trash/x")], "*") == ["/.vfs/trash/x"]


class TestChannelLabels:
    """The frozen channel→label vocabulary every minting site shares."""

    def test_one_label_per_channel(self) -> None:
        expected = {"pattern": "glob pattern", "globs": "grep glob", "globs_not": "glob exclusion"}
        assert dict(GLOB_CHANNEL_LABELS) == expected

    def test_the_map_is_frozen(self) -> None:
        with pytest.raises(TypeError):
            GLOB_CHANNEL_LABELS["pattern"] = "drift"  # ty: ignore[invalid-assignment]


# =========================================================================
# Translation parity — the in-house translate against the stdlib's
# =========================================================================

# Defect-free patterns exercising every translation branch: wildcards,
# classes (negation, ranges, inverted ranges, escapes), literals, braces
# taken literally by the compile chokepoint, and the ``**`` forms.
PARITY_PATTERNS = (
    "*",
    "**",
    "?x",
    "*.txt",
    ".*",
    "a*b",
    "src/*.py",
    "/a",
    "**/x",
    "a/**",
    "a/**/b",
    "/data/[ab]/**/*.csv",
    "[a-z]",
    "[!a-z]",
    "[!]a",
    "[]]",
    "[^ab]",
    "[[a]",
    "[a-]",
    "[-a]",
    "[z-a]",
    "[a-c-e]",
    "[d-c-b-a]",
    "[!z-a]",
    "[ab",
    "[&~|]",
    "[a\\-]",
    "[\\\\]",
    "x[!0-9]y",
    "{a,b}",
    "[z-a!b]",
    "[--!!!]",
    "[--!!-!]",
    # Programs past 64 steps: the state spans words, so every carry and
    # every reach across a word boundary decides a verdict.
    "/" + "a" * 70,
    "/" + "a" * 63 + "*b",
    "/" + "x" * 60 + "/**/*.py",
    "/" + "x" * 61 + "/**",
)

# Subjects for the verdict pin: names and paths across dotfiles, the class
# metacharacters, multi-byte characters, deep paths and the empty string.
PARITY_SUBJECTS = (
    "",
    "a",
    "x",
    "q",
    "ab",
    "abc",
    "a.txt",
    "notes.txt",
    ".hidden",
    "[",
    "]",
    "!",
    "-",
    "^",
    "&",
    "\\",
    "xay",
    "x5y",
    "é",
    "日本",
    "😀",
    "/a",
    "/x",
    "/a/b",
    "/a/x/b",
    "/a/x/y/b",
    "/src/a.py",
    "/src/app/a.py",
    "/x/src/a.py",
    "/data/a/x.csv",
    "/data/b/deep/y.csv",
    "/data/c/x.csv",
    "/.hidden/x",
    "/x/.hidden",
    "/é/日本",
    "/a/",
    "//",
    "/" + "/".join("abcdefghij"),
    "/" + "x" * 255,
    "a/b",
    "/" + "a" * 70,
    "/" + "a" * 69,
    "/" + "a" * 63 + "zzb",
    "/" + "x" * 60 + "/d/e.py",
    "/" + "x" * 60 + "/e.py",
    "/" + "x" * 61 + "/",
    "/" + "x" * 61,
)


_STDLIB_TRANSLATE = pytest.mark.skipif(
    not hasattr(stdlib_glob, "translate"), reason="stdlib glob.translate arrives in 3.13"
)


def _oracle_verdict(pattern: str, subject: str) -> bool:
    """Today's matcher: ``re.match`` over the stdlib-text translation."""
    return re.match(oracle._translate(canonical_pattern(pattern), recursive=True), subject) is not None


def _engine_verdict(pattern: str, subject: str) -> bool:
    return compile_filter(pattern, ()).program.is_match(subject)


class TestTranslateParity:
    """The oracle is the stdlib's text; the engine answers as the oracle does."""

    @_STDLIB_TRANSLATE
    def test_the_oracle_is_the_stdlibs_text(self) -> None:
        for pattern in PARITY_PATTERNS:
            gate = compile_filter(pattern, ())
            # The skipif above guards this 3.13+ attribute at runtime.
            expected = stdlib_glob.translate(  # ty: ignore[unresolved-attribute]
                gate.pattern, recursive=True, include_hidden=True, seps="/"
            )
            assert oracle._translate(gate.pattern, recursive=True) == expected, pattern

    def test_verdicts_match_the_oracle(self) -> None:
        for pattern, subject in product(PARITY_PATTERNS, PARITY_SUBJECTS):
            assert _engine_verdict(pattern, subject) is _oracle_verdict(pattern, subject), (pattern, subject)

    @pytest.mark.slow
    def test_exhaustive_fuzz_agrees_with_the_oracle(self) -> None:
        # Every defect-free pattern up to depth 4 against every short subject;
        # the two multi-byte characters reach the engine's non-ASCII masks.
        subjects = ["".join(c) for n in range(4) for c in product("[]!-azb/é日", repeat=n)]
        assert len(subjects) == 1_111
        patterns = [
            "".join(c) for n in range(1, 5) for c in product("[]!-az*", repeat=n) if glob_defect("".join(c)) is None
        ]
        assert len(patterns) == 2_654
        for pattern in patterns:
            program = compile_filter(pattern, ()).program
            source = re.compile(oracle._translate(canonical_pattern(pattern), recursive=True))
            for subject in subjects:
                assert program.is_match(subject) is (source.match(subject) is not None), (pattern, subject)

    @pytest.mark.slow
    def test_every_short_class_agrees_with_the_oracle(self) -> None:
        # Class bodies long enough for ranges, inverted-range merges, a merge
        # that exposes a negating "!", and the "!" chunk before a dash.
        subjects = list("!-az]^[b/é")
        bodies = ["".join(c) for n in range(1, 7) for c in product("!-az]^[", repeat=n)]
        assert len(bodies) == 137_256
        for body in bodies:
            pattern = "[" + body + "]"
            if glob_defect(pattern) is not None:
                continue
            program = compile_filter(pattern, ()).program
            source = re.compile(oracle._translate(canonical_pattern(pattern), recursive=True))
            for subject in subjects:
                assert program.is_match(subject) is (source.match(subject) is not None), (pattern, subject)

    @_STDLIB_TRANSLATE
    @pytest.mark.slow
    def test_exhaustive_class_machinery_fuzz_keeps_the_oracle_byte_identical(self) -> None:
        # Every defect-free pattern up to depth 6 over the class-machinery
        # alphabet: same bytes as the stdlib, and no pattern ever raises.
        alphabet = "[]!-az*"
        for length in range(1, 7):
            for combo in product(alphabet, repeat=length):
                pattern = "".join(combo)
                if glob_defect(pattern) is not None:
                    continue
                gate = compile_filter(pattern, ())
                expected = stdlib_glob.translate(  # ty: ignore[unresolved-attribute]
                    gate.pattern, recursive=True, include_hidden=True, seps="/"
                )
                assert oracle._translate(gate.pattern, recursive=True) == expected, pattern


class TestRowFactParity:
    """The string gate answers exactly as the Path gate, fact for fact."""

    PARITY_PATHS = (
        "/Makefile",
        "/src/main.py",
        "/src/app/main.py",
        "/src/.py",
        "/src/app.tests/x.py",
        "/docs/readme.md",
        "/a/x/a/f.txt",
        "/Docs/Readme.MD",
        "/.hidden/config",
        "/.vfs/state/s.txt",
    )
    PARITY_PATTERNS = (
        "src/**/*.py",
        "*.py",
        "Makefile",
        "docs/*",
        "**/[mr]*.py",
        "/a/**",
        "?",
        "**",
        "/.vfs/**",
    )

    def test_hits_agrees_with_matches_everywhere(self) -> None:
        for text, pattern in product(self.PARITY_PATHS, self.PARITY_PATTERNS):
            path = Path(text)
            gate = compile_filter(pattern, ("py", "md"))
            bare = compile_filter(pattern, ())
            for compiled in (gate, bare):
                assert compiled.hits(str(path), path.name, path.ext) is compiled.matches(path), (
                    f"{pattern!r} disagrees on {path}"
                )

    def test_passes_row_filters_agrees_with_passes_filters(self) -> None:
        gates = [compile_filter("src/**", ()), compile_filter("*.md", ())]
        not_gates = [compile_filter("**/app/**", ())]
        channels = (
            (gates, [], frozenset(), frozenset()),
            (gates, not_gates, frozenset({"py"}), frozenset()),
            ([], not_gates, frozenset(), frozenset({"md"})),
            ([], [], frozenset({"py", "txt"}), frozenset({"md"})),
        )
        for text in self.PARITY_PATHS:
            path = Path(text)
            for admit, deny, wanted, unwanted in channels:
                expected = passes_filters(path, admit, deny, wanted, unwanted)
                actual = passes_row_filters(str(path), path.name, path.ext, admit, deny, wanted, unwanted)
                assert actual is expected, f"{text!r} disagrees under {wanted}/{unwanted}"


# =========================================================================
# The native glob program — no backtracking, no Python re
# =========================================================================


class _CountingRe:
    """A stand-in for the glob module's ``re`` that counts matcher calls."""

    def __init__(self) -> None:
        self.calls = 0

    def _counted(self, name: str):
        def call(*args, **kwargs):
            self.calls += 1
            return getattr(re, name)(*args, **kwargs)

        return call

    def __getattr__(self, name: str):
        if name in {"compile", "match", "fullmatch"}:
            return self._counted(name)
        return getattr(re, name)


class TestGlobProgram:
    def test_glob_matching_never_reaches_python_re(self, monkeypatch: pytest.MonkeyPatch) -> None:
        counting = _CountingRe()
        monkeypatch.setattr(glob_module, "re", counting)
        shape = "*a" * 12 + "*b"
        assert compile_filter(shape, ()).matches(Path("/d/" + "a" * 255)) is False
        assert residuals("/x/" + shape, Path("/x/" + "a" * 255)) == frozenset()
        assert counting.calls == 0

    def test_a_lone_surrogate_pattern_is_refused(self) -> None:
        defect = glob_defect("a\udc80")
        assert defect is not None and "lone surrogate: U+DC80" in defect

    def test_a_question_mark_matches_one_character_of_any_width(self) -> None:
        gate = compile_filter("?", ())
        for name in ("é", "日", "😀"):
            assert gate.matches(Path("/" + name)), name
        assert not gate.matches(Path("/ab"))


async def test_a_backtracking_shape_globs_through_the_verb() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.write(path="/d/" + "a" * 200, content="x", parents=True)
    miss = await fs.glob("*a" * 12 + "*b")
    assert miss.success is True and miss.paths == ()
    hit = await fs.glob("*a*")
    assert hit.paths == ("/d/" + "a" * 200,)


async def test_a_lone_surrogate_pattern_answers_invalid_through_grep() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.write(path="/a.txt", content="x")
    result = await fs.grep("x", globs=("a\udc80",), allow_scan=True)
    assert result.success is False
    assert result.errors[0].kind is ErrorKind.invalid
