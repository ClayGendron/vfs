"""Tests for vfs.pattern_matching.grep — the shared grep match authority.

The storage tiers and the router's chaining filter both ride these
functions; these rows pin the public contract directly: the structural
gates, the verifier's modifier wrapping, and the batch matcher's
alignment guarantee.
"""

from __future__ import annotations

from vfs.paths import Path
from vfs.pattern_matching import compile_verifier, filter_candidates, match_texts, verify


class TestFilterCandidates:
    def test_glob_channels_and_ext_facts_gate_in_order(self) -> None:
        paths = [Path("/src/a.py"), Path("/src/b.txt"), Path("/lib/c.py")]
        assert filter_candidates(paths, globs=("/src/**",)) == ["/src/a.py", "/src/b.txt"]
        assert filter_candidates(paths, globs_not=("*.txt",)) == ["/src/a.py", "/lib/c.py"]
        assert filter_candidates(paths, ext=("py",)) == ["/src/a.py", "/lib/c.py"]
        assert filter_candidates(paths, ext_not=("py",)) == ["/src/b.txt"]

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
