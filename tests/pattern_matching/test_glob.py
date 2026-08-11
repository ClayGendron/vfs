"""Tests for vfs.pattern_matching.glob — the one glob compile chokepoint.

Pins the segment-aware contract: ``*`` within a segment, ``**`` across
segments, gitignore-exact anchoring (any ``/`` anchors at the root,
slash-free floats by name), dotfiles ordinary, mid-component ``**``
refused. The demo tree is the spec's acceptance table.
"""

from __future__ import annotations

import glob as stdlib_glob

import pytest

from vfs.paths import ROOT, Path
from vfs.pattern_matching import (
    MAX_PATTERN_ARMS,
    DerivedExt,
    compile_filter,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    expand_pattern,
    filter_paths,
    glob_defect,
    residuals,
)

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

    def test_collection_stops_one_past_the_cap(self):
        pattern = "{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}"  # 2**7 = 128 arms
        arms = expand_pattern(pattern)
        assert len(arms) == MAX_PATTERN_ARMS + 1

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
        assert regex.match("/docs/a.txt")
        assert regex.match("/docs/deep/b.txt") is None

    def test_double_star_spans_segments_including_zero(self):
        regex = compile_glob("/docs/**/*.txt")
        assert regex.match("/docs/a.txt")
        assert regex.match("/docs/deep/nested/b.txt")

    def test_unanchored_path_pattern_anchors_at_the_root(self):
        regex = compile_glob("src/*.py")
        assert regex.match("/src/a.py")
        assert regex.match("/x/src/a.py") is None

    def test_star_slash_pins_depth_one(self):
        regex = compile_glob("*/x.py")
        assert regex.match("/a/x.py")
        assert regex.match("/a/b/x.py") is None
        assert regex.match("/x.py") is None

    def test_explicit_double_star_prefix_reaches_root_level(self):
        regex = compile_glob("**/x.py")
        assert regex.match("/x.py")
        assert regex.match("/a/b/x.py")

    def test_question_mark_matches_one_non_separator_character(self):
        regex = compile_glob("/?.py")
        assert regex.match("/a.py")
        assert regex.match("/ab.py") is None
        assert regex.match("/a/b.py") is None

    def test_name_arm_pattern_compiles_over_names(self):
        regex = compile_glob("*.txt")
        assert regex.match("notes.txt")
        assert regex.match("notes.py") is None


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
        assert regex.match("/a/data/x.csv")
        assert regex.match("/a/data/sub/deep/y.csv")
        assert regex.match("/a/other.csv") is None

    def test_composition_preserves_well_formedness(self):
        for root, pattern in ((Path("/a"), "*.csv"), (ROOT, "**"), (Path("/a/b"), "src/*.py")):
            assert glob_defect(composed_pattern(root, pattern)) is None


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
    "[ab",
    "[&~|]",
    "[a\\-]",
    "[\\\\]",
    "x[!0-9]y",
    "{a,b}",
)


@pytest.mark.skipif(not hasattr(stdlib_glob, "translate"), reason="stdlib glob.translate arrives in 3.13")
class TestTranslateParity:
    """The 3.12-floor translation must be the stdlib's, byte for byte."""

    def test_compiled_source_matches_the_stdlib(self) -> None:
        for pattern in PARITY_PATTERNS:
            gate = compile_filter(pattern, ())
            # The skipif above guards this 3.13+ attribute at runtime.
            expected = stdlib_glob.translate(  # ty: ignore[unresolved-attribute]
                gate.pattern, recursive=True, include_hidden=True, seps="/"
            )
            assert gate.regex.pattern == expected, pattern
