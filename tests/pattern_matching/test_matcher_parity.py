"""Engine/oracle matcher parity and the shared language gate.

The shared Rust core is the match authority; the ``re``-based oracle in
``tests/support/oracles/matcher.py`` is its readable twin. These rows
pin two facts: both return identical hits over a case battery
(parity), and the gate refuses the identical out-of-language patterns
with the identical messages whichever side compiles them.
"""

from __future__ import annotations

import pytest

from tests.support.oracles.matcher import _PureMatcher, pure_verifier
from vfs.pattern_matching import ContentMatcher, PatternError, compile_verifier


def rust_verifier(pattern: str, **kwargs) -> ContentMatcher:
    """Compile on the engine."""
    return compile_verifier(pattern, **kwargs)


# (pattern, kwargs) cases; every one must behave identically on the
# engine and the oracle over every corpus body.
CASES: tuple[tuple[str, dict], ...] = (
    ("needle", {}),
    ("needle", {"case_mode": "insensitive"}),
    ("Needle", {"case_mode": "smart"}),
    ("needle", {"case_mode": "smart"}),
    ("a.b", {"fixed_strings": True}),
    ("if (x < 0)", {"fixed_strings": True}),
    ("cat", {"word_regexp": True}),
    ("TODO|FIXME", {}),
    ("ext[234]", {}),
    ("[^x]y", {}),
    ("^inc", {}),
    ("end$", {}),
    (".*needle.*", {}),
    (r"static\s+int", {}),
    (r"\bword\b", {}),
    (r"x*", {}),
    ("^$", {}),
    (r"mutex_lock\(&", {}),
    (r"\w+_probe", {}),
    ("café", {}),
    ("καλημέρα", {"case_mode": "insensitive"}),
    ("[a-z]+_probe", {}),
    (r"a[\x00-\x20]b", {}),
    ("$", {}),
)

BODIES: tuple[str, ...] = (
    "",
    "needle",
    "one\nneedle\nthree\n",
    "no hit here\n",
    "NEEDLE\nNeedle\nneedle",
    "a.b axb a-b\n",
    "if (x < 0) {\n",
    "cat concatenate cats\n",
    "TODO: fix\nnothing\nFIXME later\n",
    "ext2 ext3 ext4 ext5 context\n",
    "xy yy\nxx\n",
    "inc a\n#inc b\ninc c",
    "the end\nend of it\n",
    "static  int x;\nstatic\nint y;\n",
    "word\nwords\nsword\n",
    "\n\n\n",
    "a\r\nb\r\n",
    "mutex_lock(&lock);\n",
    "usb_probe helper_probe2\n",
    "café au lait\nΚΑΛΗΜΈΡΑ κόσμε\n",  # noqa: RUF001
    "x" * 5000 + "\nneedle at end",
    "abc",  # unterminated: `$` matches only zero-width at end-of-text
    "hé\nwörld🚀\nplain é\n",
    # Slice-boundary shapes: bodies past the 16-line slice grain, so
    # budgeted scans cross boundaries; anchors hit lines 1, 17, 33, last.
    "\n".join(f"line{i}" for i in range(1, 41)) + "\n",
    "\n".join("inc word end" if i in (1, 17, 33, 36) else f"filler {i}" for i in range(1, 37)) + "\n",
    "\n".join("" if i in (17, 33) else f"l{i}" for i in range(1, 37)) + "\n",
)

MODES: tuple[dict, ...] = (
    {"before": 0, "after": 0, "cap": None, "invert": False},
    {"before": 1, "after": 2, "cap": None, "invert": False},
    {"before": 0, "after": 0, "cap": 2, "invert": False},
    {"before": 0, "after": 0, "cap": None, "invert": True},
)


class TestEngineParity:
    """Identical hits and counts from the engine and the oracle across the battery."""

    @pytest.mark.parametrize(("pattern", "kwargs"), CASES, ids=[c[0] for c in CASES])
    def test_hits_and_counts_identical(self, pattern: str, kwargs: dict) -> None:
        options = {"fixed_strings": False, "word_regexp": False, "case_mode": "sensitive", **kwargs}
        rust = rust_verifier(pattern, **options)
        pure = pure_verifier(pattern, **options)
        for mode in MODES:
            rust_rows, rust_done = rust.hit_lines(BODIES, budget=None, **mode)
            pure_rows, pure_done = pure.hit_lines(BODIES, budget=None, **mode)
            assert (rust_rows, rust_done) == (pure_rows, pure_done), (pattern, mode)
            counts = {"cap": mode["cap"], "invert": mode["invert"]}
            assert rust.count_lines(BODIES, budget=None, **counts) == pure.count_lines(BODIES, budget=None, **counts)

    @pytest.mark.parametrize(("pattern", "kwargs"), CASES, ids=[c[0] for c in CASES])
    def test_bytes_bodies_match_text_bodies_on_both_engines(self, pattern: str, kwargs: dict) -> None:
        options = {"fixed_strings": False, "word_regexp": False, "case_mode": "sensitive", **kwargs}
        rust = rust_verifier(pattern, **options)
        pure = pure_verifier(pattern, **options)
        encoded = [body.encode("utf-8") for body in BODIES]
        for mode in MODES:
            truth, done = rust.hit_lines(BODIES, budget=None, **mode)
            assert done is True
            for engine in (rust, pure):
                assert engine.hit_lines(encoded, budget=None, **mode) == (truth, True), (pattern, mode)
            counts = {"cap": mode["cap"], "invert": mode["invert"]}
            count_truth = rust.count_lines(BODIES, budget=None, **counts)
            for engine in (rust, pure):
                assert engine.count_lines(encoded, budget=None, **counts) == count_truth

    def test_mixed_batches_verify_each_body_by_its_own_spelling(self) -> None:
        rust = rust_verifier("é", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        pure = pure_verifier("é", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        mixed = ["hé one\nmiss\n", "hé two\n".encode(), b"miss\n", "hé three"]
        for engine in (rust, pure):
            rows, done = engine.hit_lines(mixed, before=0, after=0, cap=None, invert=False, budget=None)
            assert done is True
            assert [[span[2] for span in row] for row in rows] == [[1], [1], [], [1]]
            assert [span[3] for row in rows for span in row] == ["hé one", "hé two", "hé three"]

    def test_pure_per_line_and_whole_text_paths_agree(self) -> None:
        # `[^x]y` walks as newline-capable (per-line path), `xy` does not
        # (whole-text path); both must equal the authority on shared cases.
        for pattern in ("[^x]y", "xy"):
            rust = rust_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            pure = pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            assert isinstance(pure, _PureMatcher)
            rows_r, _ = rust.hit_lines(BODIES, before=0, after=0, cap=None, invert=False, budget=None)
            rows_p, _ = pure.hit_lines(BODIES, before=0, after=0, cap=None, invert=False, budget=None)
            assert rows_r == rows_p, pattern

    @pytest.mark.parametrize(("pattern", "kwargs"), CASES, ids=[c[0] for c in CASES])
    def test_budgeted_scans_match_unbudgeted_on_the_pure_engine(self, pattern: str, kwargs: dict) -> None:
        # A generous budget takes the sliced paths without ever expiring:
        # the answer must be byte-identical to the unbudgeted scan.
        options = {"fixed_strings": False, "word_regexp": False, "case_mode": "sensitive", **kwargs}
        pure = pure_verifier(pattern, **options)
        for mode in MODES:
            truth = pure.hit_lines(BODIES, budget=None, **mode)
            assert pure.hit_lines(BODIES, budget=1e6, **mode) == truth, (pattern, mode)
            counts = {"cap": mode["cap"], "invert": mode["invert"]}
            assert pure.count_lines(BODIES, budget=1e6, **counts) == pure.count_lines(BODIES, budget=None, **counts)

    @pytest.mark.parametrize(("pattern", "kwargs"), CASES, ids=[c[0] for c in CASES])
    def test_budgeted_pure_scans_match_the_authority(self, pattern: str, kwargs: dict) -> None:
        options = {"fixed_strings": False, "word_regexp": False, "case_mode": "sensitive", **kwargs}
        rust = rust_verifier(pattern, **options)
        pure = pure_verifier(pattern, **options)
        for mode in MODES:
            truth = rust.hit_lines(BODIES, budget=None, **mode)
            assert pure.hit_lines(BODIES, budget=1e6, **mode) == truth, (pattern, mode)

    def test_a_budgeted_scan_never_invents_boundary_matches(self) -> None:
        # 40 non-empty lines: `^$` has nothing to match, and a slice end
        # posing as end-of-string would report hits on lines 17 and 33.
        body = "\n".join(f"line{i}" for i in range(1, 41)) + "\n"
        verifier = pure_verifier("^$", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        for spelling in (body, body.encode()):
            assert verifier.count_lines([spelling], cap=None, invert=False, budget=1e4) == ([0], True)
            rows, completed = verifier.hit_lines([spelling], before=0, after=0, cap=None, invert=False, budget=1e4)
            assert (rows, completed) == ([[]], True)

    def test_a_capped_budgeted_scan_keeps_the_genuine_hit(self) -> None:
        # A boundary phantom would consume the cap slot on line 17 and
        # displace the genuine empty line at 19 — the wrong hit entirely.
        body = "\n".join(["filler"] * 16 + ["not-empty", "x", "", "tail"]) + "\n"
        verifier = pure_verifier("^$", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        for spelling in (body, body.encode()):
            for budget in (None, 1e4):
                rows, completed = verifier.hit_lines([spelling], before=0, after=0, cap=1, invert=False, budget=budget)
                assert (rows, completed) == ([[(19, 19, 19, "")]], True), budget

    def test_a_zero_width_match_at_eof_is_served(self) -> None:
        # `$` on an unterminated body matches only zero-width at
        # end-of-text: the EOF qualifier serves it; over-discard loses
        # the final line silently, budgeted and unbudgeted alike.
        verifier = pure_verifier("$", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        for spelling in ("abc", b"abc"):
            for budget in (None, 1e4):
                assert verifier.count_lines([spelling], cap=None, invert=False, budget=budget) == ([1], True)
                mode = {"before": 0, "after": 0, "cap": None, "invert": False}
                rows, completed = verifier.hit_lines([spelling], budget=budget, **mode)
                assert ([[span[2] for span in row] for row in rows], completed) == ([[1]], True), budget
        multi = "one\ntail"
        for budget in (None, 1e4):
            assert verifier.count_lines([multi], cap=None, invert=False, budget=budget) == ([2], True)
            rows, completed = verifier.hit_lines([multi], before=0, after=0, cap=None, invert=False, budget=budget)
            assert ([[span[2] for span in row] for row in rows], completed) == ([[1, 2]], True), budget

    def test_a_genuine_boundary_line_match_is_served_once(self) -> None:
        # Empty lines sitting exactly on slice boundaries are genuine
        # hits: the next slice serves each, exactly once, budget or not.
        body = "\n".join("" if i in (17, 33) else f"l{i}" for i in range(1, 37)) + "\n"
        verifier = pure_verifier("^$", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        for budget in (None, 1e4):
            rows, completed = verifier.hit_lines([body], before=0, after=0, cap=None, invert=False, budget=budget)
            assert ([span[2] for span in rows[0]], completed) == ([17, 33], True), budget

    def test_exhausted_budget_reports_incomplete_on_both(self) -> None:
        bodies = ["needle\n"] * 64
        for build in (rust_verifier, pure_verifier):
            verifier = build("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
            counts, completed = verifier.count_lines(bodies, cap=None, invert=False, budget=0.0)
            assert completed is False
            assert len(counts) == len(bodies)
            rows, completed = verifier.hit_lines(bodies, before=0, after=0, cap=None, invert=False, budget=0.0)
            assert completed is False
            assert len(rows) == len(bodies)

    def test_the_authority_finishes_the_backtracking_shape_within_budget(self) -> None:
        # The linear engine needs no rescue: same shape, same budget,
        # complete answer.
        body = "\n".join("a" * 20 for _ in range(64))
        verifier = rust_verifier("(a+)+bcd", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, completed = verifier.count_lines([body], cap=None, invert=False, budget=0.05)
        assert counts == [0]
        assert completed is True

    def test_expiry_mid_body_returns_a_lawful_subset(self) -> None:
        # Hits found before the wall are kept and reported incomplete —
        # never a silent full success, never an empty lie.
        body = "\n".join(["aaabcd", *("a" * 18 for _ in range(64))])
        verifier = pure_verifier("(a+)+bcd", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, completed = verifier.count_lines([body], cap=None, invert=False, budget=0.001)
        assert counts == [1]  # the first slice's hit survives
        assert completed is False
        rows, completed = verifier.hit_lines([body], before=0, after=0, cap=None, invert=False, budget=0.001)
        assert [span[2] for span in rows[0]] == [1]
        assert completed is False

    def test_a_budgeted_scan_of_an_unterminated_body_completes(self) -> None:
        # The final line without a trailing newline closes its own slice.
        verifier = pure_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, completed = verifier.count_lines(["miss\nneedle"], cap=None, invert=False, budget=30.0)
        assert (counts, completed) == ([1], True)

    def test_the_split_path_honors_the_wall_mid_body(self) -> None:
        # invert forces the per-line path; the same slice grain governs,
        # and verdicts from completed slices survive as the subset.
        body = "\n".join("a" * 18 for _ in range(32))
        verifier = pure_verifier("(a+)+bcd", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, completed = verifier.count_lines([body], cap=None, invert=True, budget=0.05)
        assert completed is False
        assert 0 < counts[0] < 32
        rows, completed = verifier.hit_lines([body], before=0, after=0, cap=None, invert=True, budget=0.05)
        assert completed is False
        assert 0 < len(rows[0]) < 32

    def test_per_line_pure_path_honors_caps(self) -> None:
        # `[^x]y` walks newline-capable, forcing the split path for both
        # count and hit shapes; the cap must stop each at the same lines.
        verifier = pure_verifier("[^x]y", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        body = "ay\nby\ncy\n"
        counts, _ = verifier.count_lines([body], cap=2, invert=False, budget=None)
        assert counts == [2]
        rows, _ = verifier.hit_lines([body], before=0, after=0, cap=2, invert=False, budget=None)
        assert [span[2] for span in rows[0]] == [1, 2]


REFUSALS: tuple[tuple[str, str], ...] = (
    (r"(a)\1", "backreferences are not supported"),
    (r"a(?=b)", "look-around assertions are not supported"),
    (r"a(?<!b)c", "look-around assertions are not supported"),
    (r"(?>ab)", "atomic groups are not supported"),
    (r"a*+", "possessive quantifiers are not supported"),
    (r"(?P<g>a)(?(g)b|c)", "conditional groups are not supported"),
    ("\\Aroot", r"the text anchor \\A is not supported; use \^"),
    (r"end\Z", r"the text anchor \\Z is not supported; use \$"),
    ("(?a)x", r"the ASCII flag \(\?a\) is not supported"),
    ("(?a:x)", r"the ASCII flag \(\?a\) is not supported"),
    ("a\nb", "pattern matches a line terminator"),
    (r"x[\n]y", "pattern matches a line terminator"),
    ("x[\\n-\\n]y", "pattern matches a line terminator"),
    (r"[bad", "unterminated"),
)


class TestLanguageGate:
    """The gate refuses the same patterns with the same messages from either side."""

    @pytest.mark.parametrize(("pattern", "message"), REFUSALS, ids=[repr(c[0]) for c in REFUSALS])
    def test_oracle_side_refuses(self, pattern: str, message: str) -> None:
        with pytest.raises(PatternError, match=message):
            pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")

    @pytest.mark.parametrize(("pattern", "message"), REFUSALS, ids=[repr(c[0]) for c in REFUSALS])
    def test_engine_side_refuses(self, pattern: str, message: str) -> None:
        with pytest.raises(PatternError, match=message):
            rust_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")

    def test_fixed_string_newline_is_refused_not_silent(self) -> None:
        with pytest.raises(PatternError, match="line terminator"):
            pure_verifier("a\nb", fixed_strings=True, word_regexp=False, case_mode="sensitive")

    def test_a_spelling_the_walk_cannot_see_is_refused_by_the_engine(self) -> None:
        # sre resolves \N{...} to its literal before the walk; the crate
        # has no such spelling, and its refusal surfaces as PatternError.
        with pytest.raises(PatternError, match="escape"):
            rust_verifier(r"\N{BULLET}", fixed_strings=False, word_regexp=False, case_mode="sensitive")

    def test_classes_that_merely_admit_a_newline_are_served(self) -> None:
        # A class admitting \n among other members is in-language on both
        # sides; only a class that matches nothing else is refused.
        for pattern in (r"[\nx]y", r"[^\nx]y", "[^ab]y"):
            rust_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
