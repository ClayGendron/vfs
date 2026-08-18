"""Rust/pure matcher parity, the shared language gate, and the divergence catalog.

The shared Rust core is the match authority; the pure-Python matcher is
its approximation for extension-less installs. These rows pin three
facts: both engines return identical hits over a case battery (parity),
both refuse the identical out-of-language patterns with the identical
messages (the gate), and the *known* residual divergences of the pure
engine — the ``re.IGNORECASE`` Turkic case orbit and Python-only
spellings the sre walk cannot see — stay exactly as documented, each
engine's answer asserted separately. A divergence row failing means the
residual moved: update the catalog knowingly, never silently.
"""

from __future__ import annotations

from time import monotonic

import pytest

import vfs.pattern_matching.grep as grep_mod
from vfs.pattern_matching import ContentMatcher, PatternError, compile_verifier
from vfs.pattern_matching.grep import _PureMatcher

try:
    from vfs import _native
except ImportError:  # pragma: no cover - extension-less environment
    _native = None  # ty: ignore[invalid-assignment]

needs_rust = pytest.mark.skipif(_native is None, reason="vfs._native extension not built")


def pure_verifier(pattern: str, **kwargs) -> ContentMatcher:
    """Compile on the pure engine regardless of the active core."""
    live = grep_mod.extension
    grep_mod.extension = lambda: None  # ty: ignore[invalid-assignment]
    try:
        return compile_verifier(pattern, **kwargs)
    finally:
        grep_mod.extension = live


def rust_verifier(pattern: str, **kwargs) -> ContentMatcher:
    """Compile on the Rust engine regardless of the active core."""
    live = grep_mod.extension
    grep_mod.extension = lambda: _native  # ty: ignore[invalid-assignment]
    try:
        return compile_verifier(pattern, **kwargs)
    finally:
        grep_mod.extension = live


# (pattern, kwargs) cases; every one must behave identically on both
# engines over every corpus body. Divergence-zone cases (Turkic orbit,
# Python-only spellings) live in the catalog below, never here.
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
    "hé\nwörld🚀\nplain é\n",
)

MODES: tuple[dict, ...] = (
    {"before": 0, "after": 0, "cap": None, "invert": False},
    {"before": 1, "after": 2, "cap": None, "invert": False},
    {"before": 0, "after": 0, "cap": 2, "invert": False},
    {"before": 0, "after": 0, "cap": None, "invert": True},
)


class TestEngineParity:
    """Identical hits and counts from both engines across the battery."""

    @needs_rust
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

    @needs_rust
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

    def test_bytes_bodies_match_text_bodies_on_the_pure_engine(self) -> None:
        # No extension required: the fallback CI leg pins its own twin.
        pure = pure_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        encoded = [body.encode("utf-8") for body in BODIES]
        for mode in MODES:
            assert pure.hit_lines(encoded, budget=None, **mode) == pure.hit_lines(BODIES, budget=None, **mode)

    @needs_rust
    def test_mixed_batches_verify_each_body_by_its_own_spelling(self) -> None:
        rust = rust_verifier("é", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        pure = pure_verifier("é", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        mixed = ["hé one\nmiss\n", "hé two\n".encode(), b"miss\n", "hé three"]
        for engine in (rust, pure):
            rows, done = engine.hit_lines(mixed, before=0, after=0, cap=None, invert=False, budget=None)
            assert done is True
            assert [[span[2] for span in row] for row in rows] == [[1], [1], [], [1]]
            assert [span[3] for row in rows for span in row] == ["hé one", "hé two", "hé three"]

    @needs_rust
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

    @needs_rust
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

    def test_a_backtracking_pattern_stays_inside_the_wall_budget(self) -> None:
        # The ReDoS shape: catastrophic per-line backtracking must stop
        # at an inter-slice check, never run the whole body out.
        body = "\n".join("a" * 18 for _ in range(64))
        verifier = pure_verifier("(a+)+bcd", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        for spelling in (body, body.encode()):
            started = monotonic()
            counts, completed = verifier.count_lines([spelling], cap=None, invert=False, budget=0.05)
            elapsed = monotonic() - started
            assert elapsed < 2.0, elapsed  # one slice's backtracking, the documented floor
            assert counts == [0]
            assert completed is False

    @needs_rust
    def test_the_authority_finishes_the_backtracking_shape_within_budget(self) -> None:
        # The linear engine needs no rescue: same shape, same budget,
        # complete answer.
        body = "\n".join("a" * 18 for _ in range(64))
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
    """Both engines refuse the same patterns with the same messages."""

    @pytest.mark.parametrize(("pattern", "message"), REFUSALS, ids=[repr(c[0]) for c in REFUSALS])
    def test_pure_engine_refuses(self, pattern: str, message: str) -> None:
        with pytest.raises(PatternError, match=message):
            pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")

    @needs_rust
    @pytest.mark.parametrize(("pattern", "message"), REFUSALS, ids=[repr(c[0]) for c in REFUSALS])
    def test_rust_engine_refuses(self, pattern: str, message: str) -> None:
        with pytest.raises(PatternError, match=message):
            rust_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")

    def test_fixed_string_newline_is_refused_not_silent(self) -> None:
        with pytest.raises(PatternError, match="line terminator"):
            pure_verifier("a\nb", fixed_strings=True, word_regexp=False, case_mode="sensitive")


class TestDivergenceCatalog:
    """The pure engine's accepted residuals, pinned so movement is loud.

    The authority's answer is the contract; the pure rows document the
    approximation error an extension-less install carries.
    """

    @needs_rust
    def test_turkic_orbit_authority_answer(self) -> None:
        # Unicode simple folding has no i-to-Turkic-dotless/dotted mapping:
        # the authority (and ripgrep) reject the orbit under case folding.
        for pattern, body in (("istanbul", "İstanbul\n"), ("isi", "ısı\n")):  # noqa: RUF001
            verifier = rust_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="insensitive")
            counts, _ = verifier.count_lines([body], cap=None, invert=False, budget=None)
            assert counts == [0], pattern

    def test_turkic_orbit_pure_approximation(self) -> None:
        # sre's extra-cases table unifies the orbit, so the fallback
        # over-matches here — the documented residual.
        for pattern, body in (("istanbul", "İstanbul\n"), ("isi", "ısı\n")):  # noqa: RUF001
            verifier = pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="insensitive")
            counts, _ = verifier.count_lines([body], cap=None, invert=False, budget=None)
            assert counts == [1], pattern

    @needs_rust
    def test_named_escape_spelling_refused_by_authority(self) -> None:
        with pytest.raises(PatternError, match="escape"):
            rust_verifier(r"\N{BULLET}", fixed_strings=False, word_regexp=False, case_mode="sensitive")

    def test_named_escape_spelling_slips_the_pure_gate(self) -> None:
        # The sre walk sees only the parsed literal, not the spelling —
        # the fallback serves it. The residual is acceptance, never a
        # wrong match: the literal means the same codepoint.
        verifier = pure_verifier(r"\N{BULLET}", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, _ = verifier.count_lines(["a • b\n"], cap=None, invert=False, budget=None)
        assert counts == [1]


class TestPurePathSelection:
    """The gate's newline-capability walk picks the pure engine's shape."""

    def test_newline_free_patterns_take_the_whole_text_path(self) -> None:
        for pattern in ("needle", "a|b", "x[yz]", r"\d+"):
            matcher = pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            assert isinstance(matcher, _PureMatcher)
            assert matcher._multi_rx is not None, pattern

    def test_newline_capable_patterns_take_the_per_line_path(self) -> None:
        for pattern in ("[^x]y", r"a\s+b", r"a\D", r"a\W"):
            matcher = pure_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            assert isinstance(matcher, _PureMatcher)
            assert matcher._multi_rx is None, pattern

    def test_class_with_excluded_newline_is_whole_text_safe(self) -> None:
        matcher = pure_verifier(r"[^\nx]y", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        assert isinstance(matcher, _PureMatcher)
        assert matcher._multi_rx is not None

    def test_verbose_flag_stays_in_the_language(self) -> None:
        matcher = pure_verifier("(?x) a b  # comment", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        counts, _ = matcher.count_lines(["ab\n"], cap=None, invert=False, budget=None)
        assert counts == [1]
        if _native is not None:
            authority = rust_verifier(
                "(?x) a b  # comment", fixed_strings=False, word_regexp=False, case_mode="sensitive"
            )
            assert authority.count_lines(["ab\n"], cap=None, invert=False, budget=None)[0] == [1]
