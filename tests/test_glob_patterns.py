"""Tests for vfs.glob_patterns — the one glob compile chokepoint.

Pins the segment-aware contract: ``*`` within a segment, ``**`` across
segments, gitignore-exact anchoring (any ``/`` anchors at the root,
slash-free floats by name), dotfiles ordinary, mid-component ``**``
refused. The demo tree is the spec's acceptance table.
"""

from __future__ import annotations

from vfs.glob_patterns import (
    compile_filter,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    glob_defect,
    residuals,
)
from vfs.paths import ROOT, Path

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
        assert derive_ext("*.TXT") == ("txt", ".TXT")

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
