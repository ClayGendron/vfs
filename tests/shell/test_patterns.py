"""GNU patterns in the verbs' languages: each served pattern selects the lines GNU's own form selects,
and each construct the two read differently is left to GNU's form."""

from __future__ import annotations

import pytest

from vfs import AsyncVirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.shell.patterns import case_folds_alike, fnmatch_safe, glob_safe, verb_regex

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))

LINES = (
    "alpha",
    "beta gamma",
    "a.b a+b a?b a|b",
    "(paren) [bracket] {brace}",
    "x*y x**y *star",
    "^caret$ dollar$ mid^dle",
    "back\\slash",
    "aaa ab abb abbb",
    "word_one two-words three",
    "tab\there",
    "UPPER lower MiXeD",
    "été naïve",
    "",
    "-dash --double",
    "digits 0123456789",
    "a]b a-b a^b",
)


@pytest.mark.parametrize(
    ("pattern", "dialect", "regex"),
    [
        ("alpha", "basic", "alpha"),
        ("a.b", "basic", "a.b"),
        ("a\\.b", "basic", "a\\.b"),
        ("a+b", "basic", "a\\+b"),
        ("a\\+b", "basic", "a+b"),
        ("a\\(b\\|c\\)*$", "basic", "a(?:b|c)*$"),
        ("*star", "basic", "\\*star"),
        ("^*", "basic", "^\\*"),
        ("mid^dle", "basic", "mid\\^dle"),
        ("dollar$ x", "basic", "dollar\\$ x"),
        ("ab\\{2,3\\}", "basic", "ab{2,3}"),
        ("ab{2}", "basic", "ab\\{2\\}"),
        ("ab{,2}", "extended", "ab{0,2}"),
        ("ab{2,}", "extended", "ab{2,}"),
        ("ab{2}", "extended", "ab{2}"),
        ("a|b", "extended", "a|b"),
        ("(a|b)+c?", "extended", "(?:a|b)+c?"),
        ("[a-c]x", "basic", "[a-c]x"),
        ("[^]a-]", "basic", "[^\\]a\\-]"),
        ("[&~[]", "extended", "[\\&\\~\\[]"),
        ("a.b(c)", "fixed", "a\\.b\\(c\\)"),
    ],
)
def test_a_served_pattern_is_written_in_the_verbs_language(pattern: str, dialect: str, regex: str) -> None:
    translated = verb_regex(pattern, dialect)  # ty: ignore[invalid-argument-type]
    assert translated is not None
    assert translated.regex == regex


@pytest.mark.parametrize(
    ("pattern", "dialect"),
    [
        ("\\<word", "basic"),
        ("\\bword", "extended"),
        ("\\w+", "extended"),
        ("\\(a\\)\\1", "basic"),
        ("[[:alpha:]]", "basic"),
        ("[[.a.]]", "basic"),
        ("[a\\]", "basic"),
        ("*a", "extended"),
        ("a**", "extended"),
        ("a**", "basic"),
        ("()", "extended"),
        ("\\(\\)", "basic"),
        ("a|", "extended"),
        ("a{", "extended"),
        ("a{1,2,3}", "extended"),
        ("a{3,1}", "extended"),
        ("a{x}", "extended"),
        ("a{300}", "extended"),
        ("a^b", "extended"),
        ("a$b", "extended"),
        ("trailing\\", "basic"),
        ("\\t", "basic"),
        ("[z-a]", "basic"),
        ("[unclosed", "basic"),
        ("(open", "extended"),
        ("close)", "extended"),
        ("\\)", "basic"),
        ("\\{1\\}", "basic"),
    ],
)
def test_a_construct_the_two_read_apart_is_left_to_gnus_form(pattern: str, dialect: str) -> None:
    assert verb_regex(pattern, dialect) is None  # ty: ignore[invalid-argument-type]


def test_a_pattern_with_no_operator_keeps_its_text() -> None:
    assert verb_regex("a\\.b", "basic") == ("a\\.b", "a.b")
    assert verb_regex("a.b", "basic") == ("a.b", None)
    assert verb_regex("x(y", "fixed") == ("x\\(y", "x(y")


@pytest.mark.parametrize(
    ("pattern", "served"),
    [
        ("TODO", True),
        ("beta|gamma", True),
        ("pipe", False),
        ("TIME", False),
        ("kmalloc", False),
        ("LAKE", False),
        ("[a-c]x", False),
        ("\u00e9t\u00e9", False),
    ],
)
def test_i_is_served_only_where_glibc_and_the_verb_fold_alike(pattern: str, served: bool) -> None:
    assert case_folds_alike(pattern) is served


@pytest.mark.parametrize(
    ("pattern", "fnmatch", "glob"),
    [
        ("*.md", True, True),
        ("[ab].md", True, True),
        ("[!a]*", True, True),
        ("????.txt", True, True),
        ("[^a]*", False, False),
        ("[[:digit:]]*", False, False),
        ("a\\*", False, False),
        ("[unclosed", False, False),
        ("{a,b}", True, False),
        ("a**", True, False),
        ("a/b", True, False),
        ("", True, False),
    ],
)
def test_name_patterns_are_served_where_fnmatch_reads_them_alike(pattern: str, fnmatch: bool, glob: bool) -> None:
    assert fnmatch_safe(pattern) is fnmatch
    assert glob_safe(pattern) is glob


DIFFERENTIAL = (
    ("alpha", "basic", False),
    ("a.b", "basic", False),
    ("a\\.b", "basic", False),
    ("a+b", "basic", False),
    ("a\\+b", "basic", False),
    ("a\\?b", "basic", False),
    ("a\\|b", "basic", False),
    ("x*y", "basic", False),
    ("x**y", "fixed", False),
    ("*star", "basic", False),
    ("^caret", "basic", False),
    ("^\\^caret", "basic", False),
    ("dollar\\$", "basic", False),
    ("dollar$", "basic", False),
    ("mid^dle", "basic", False),
    ("ab\\{2,3\\}", "basic", False),
    ("ab{2,3}", "extended", False),
    ("(a|b)b+", "extended", False),
    ("\\(a\\|be\\)ta", "basic", False),
    ("[a-c]b", "basic", False),
    ("[^a-z ]", "basic", False),
    ("[]a]b", "basic", False),
    ("[(]paren[)]", "extended", False),
    ("\\[bracket\\]", "basic", False),
    ("{brace}", "basic", False),
    ("\\{brace\\}", "extended", False),
    ("back\\\\slash", "basic", False),
    ("été", "basic", False),
    ("na.ve", "extended", False),
    ("^$", "basic", False),
    ("", "basic", False),
    ("a|b", "fixed", False),
    ("-dash", "basic", False),
    ("t.b", "basic", False),
    ("[0-9][0-9]*$", "basic", False),
    ("^(UPPER|lower)", "extended", False),
    ("UPPER", "basic", True),
    ("BETA|GAMMA", "extended", True),
    ("ALPHA", "fixed", True),
)


async def test_each_served_pattern_selects_the_lines_gnus_form_selects() -> None:
    fs = AsyncVirtualFileSystem()
    assert (
        await fs.write(path="/t/lines.txt", content="\n".join(LINES) + "\n", parents=True, authority=SYSTEM)
    ).success
    assert (await fs.grant("/", "ada", "read_write", authority=SYSTEM)).success
    flag = {"basic": "-G", "extended": "-E", "fixed": "-F"}
    for pattern, dialect, insensitive in DIFFERENTIAL:
        translated = verb_regex(pattern, dialect)
        assert translated is not None, pattern
        quoted = "'" + pattern.replace("'", "'\\''") + "'"
        fold = "-i " if insensitive else ""
        gnu = await fs.cli(f"grep -n {fold}{flag[dialect]} -e {quoted} /t/lines.txt", authority=ADA)
        case_mode = "insensitive" if insensitive else "sensitive"
        verb = await fs.grep(
            translated.regex, paths=("/t/lines.txt",), case_mode=case_mode, allow_scan=True, authority=ADA
        )
        assert verb.success, (pattern, verb.error_message)
        lines = [match.match for row in verb.observations for match in row.matches or []]
        expected = [int(line.split(":", 1)[0]) for line in gnu.stdout.splitlines()]
        assert lines == expected, (pattern, translated.regex, gnu.stdout)
    await fs.close()


async def test_an_interval_with_no_lower_bound_counts_from_zero_as_gnu_grep_does() -> None:
    """GNU grep 3.11 selects lines 2 and 8 of ``LINES`` for ``-E 'ab{,1} '``; the library's own form selects none."""
    fs = AsyncVirtualFileSystem()
    assert (
        await fs.write(path="/t/lines.txt", content="\n".join(LINES) + "\n", parents=True, authority=SYSTEM)
    ).success
    translated = verb_regex("ab{,1} ", "extended")
    assert translated is not None
    verb = await fs.grep(translated.regex, paths=("/t/lines.txt",), allow_scan=True, authority=SYSTEM)
    assert [match.match for row in verb.observations for match in row.matches or []] == [2, 8]
    await fs.close()
