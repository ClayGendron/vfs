"""Tests for vfs.pattern_matching.grep — the shared grep match authority.

The storage tiers and the router's chaining filter both ride these
functions; these rows pin the public contract directly: the structural
gates, the verifier's modifier wrapping, and the batch matcher's
alignment guarantee.
"""

from __future__ import annotations

from vfs.paths import Path
from vfs.pattern_matching import compile_verifier, filter_candidates, match_texts, split_lines, verify


class TestFilterCandidates:
    def test_glob_channels_and_ext_facts_gate_in_order(self) -> None:
        paths = [Path("/src/a.py"), Path("/src/b.txt"), Path("/lib/c.py")]
        assert filter_candidates(paths, globs=("/src/**",)) == ["/src/a.py", "/src/b.txt"]
        assert filter_candidates(paths, globs_not=("*.txt",)) == ["/src/a.py", "/lib/c.py"]
        assert filter_candidates(paths, ext=("py",)) == ["/src/a.py", "/lib/c.py"]
        assert filter_candidates(paths, ext_not=("py",)) == ["/src/b.txt"]

    def test_ext_members_normalize_dots_and_case(self) -> None:
        paths = [Path("/src/a.py"), Path("/src/b.txt")]
        assert filter_candidates(paths, ext=(".PY",)) == ["/src/a.py"]
        assert filter_candidates(paths, ext_not=(".PY",)) == ["/src/b.txt"]

    def test_no_gates_means_everything_passes(self) -> None:
        paths = [Path("/a"), Path("/.vfs/meta.txt")]
        assert filter_candidates(paths) == paths  # no meta rule: paths in hand are never hidden


class TestCompileVerifier:
    def test_smart_case_is_judged_on_the_raw_pattern(self) -> None:
        lower = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="smart")
        assert lower.search("NEEDLE") is not None
        upper = compile_verifier("Needle", fixed_strings=False, word_regexp=False, case_mode="smart")
        assert upper.search("needle") is None

    def test_fixed_strings_escape_and_word_regexp_wraps(self) -> None:
        fixed = compile_verifier("a.b", fixed_strings=True, word_regexp=False, case_mode="sensitive")
        assert fixed.search("axb") is None
        word = compile_verifier("cat", fixed_strings=False, word_regexp=True, case_mode="sensitive")
        assert word.search("concatenate") is None
        assert word.search("a cat sat") is not None


class TestVerifyAndMatchTexts:
    def test_lines_mode_renders_clamped_context_regions(self) -> None:
        verifier = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        verified = verify("one\nneedle\nthree", verifier, invert=False, before=5, after=5, mode="lines", cap=None)
        assert verified is not None
        matches, score = verified
        assert score is None and matches is not None
        [match] = matches
        assert (match.start, match.match, match.end) == (1, 2, 3)

    def test_match_texts_stays_aligned_with_its_input(self) -> None:
        # Alignment is the contract: duplicate paths with differing
        # texts stay unambiguous because misses hold their slot.
        verifier = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        texts = [(Path("/a"), "no hit"), (Path("/a"), "a needle"), (Path("/b"), "needle")]
        results = match_texts(texts, verifier, invert=False, before=0, after=0, mode="files", cap=None)
        assert results[0] is None
        assert results[1] is not None and results[1].path == "/a"
        assert results[2] is not None and results[2].path == "/b"

    def test_count_mode_reports_the_capped_hit_count_on_score(self) -> None:
        verifier = compile_verifier("x", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        [hit] = match_texts([(Path("/a"), "x\nx\nx")], verifier, invert=False, before=0, after=0, mode="count", cap=2)
        assert hit is not None
        assert (hit.matches, hit.score) == (None, 2.0)


class TestSplitLines:
    def test_newline_is_the_only_line_break(self) -> None:
        # str.splitlines would break on all of these; grep and ripgrep
        # treat every one as an ordinary in-line byte.
        for control in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029", "\r"):
            assert split_lines(f"a{control}b\nnext") == [f"a{control}b", "next"], repr(control)

    def test_the_final_terminator_is_dropped_but_blank_lines_are_kept(self) -> None:
        assert split_lines("a\nb\n") == ["a", "b"]
        assert split_lines("a\n\nb") == ["a", "", "b"]
        assert split_lines("") == []


class TestControlCharacterLineSemantics:
    def test_a_pattern_spans_a_form_feed_inside_one_line(self) -> None:
        verifier = compile_verifier("end.start", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        verified = verify("end\x0cstart\n", verifier, invert=False, before=0, after=0, mode="lines", cap=None)
        assert verified is not None

    def test_line_numbers_after_a_control_byte_stay_true(self) -> None:
        # With splitlines the \x85 minted a phantom line and every later
        # match carried a wrong number — misdirecting downstream edits.
        verifier = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        text = "first\x85still first\nneedle\n"
        verified = verify(text, verifier, invert=False, before=0, after=0, mode="lines", cap=None)
        assert verified is not None
        matches, _score = verified
        assert matches is not None and [m.match for m in matches] == [2]

    def test_count_mode_counts_newline_lines_only(self) -> None:
        verifier = compile_verifier("x", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        verified = verify("x\u2028x\nx\n", verifier, invert=False, before=0, after=0, mode="count", cap=None)
        assert verified is not None
        assert verified[1] == 2.0

    def test_crlf_content_keeps_grep_semantics(self) -> None:
        # The \r stays in-line, so an end anchor rejects it — exactly
        # what grep and rg (without --crlf) report on CRLF files.
        anchored = compile_verifier("foo$", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        assert verify("foo\r\nbar\n", anchored, invert=False, before=0, after=0, mode="lines", cap=None) is None
        plain = compile_verifier("foo", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        verified = verify("foo\r\nbar\n", plain, invert=False, before=0, after=0, mode="lines", cap=None)
        assert verified is not None
        matches, _score = verified
        assert matches is not None and [m.match for m in matches] == [1]
