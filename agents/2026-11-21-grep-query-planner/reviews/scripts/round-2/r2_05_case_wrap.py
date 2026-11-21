"""Decision 7's extraction (e5) through the matcher's own wrapping: fixed strings, word wrap, smart case, Unicode
case pairs, `\\b` inside runs, `{0}` and `{n,m}`. The authority is the Rust matcher compiled by compile_verifier; the
extraction is run on the text and insensitivity compile_verifier derives. Every body the matcher hits must hold one
of the literals.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys

from vfs.pattern_matching import PatternError, compile_verifier
from vfs.pattern_matching import grep as pm

spec = importlib.util.spec_from_file_location("e5", sys.argv[1])
e5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e5)

PATTERNS = ["ſtrasse", "strasse", "Kelvin", "Kelvin", "kelvin", "İstanbul", "istanbul", "x(?i:İ)y", "foo\\bbar",
            "foo\\b bar", "(abc){0}x", "(ab){2,3}z", "a{1,3}b", "x(?:ab){0,1}y", "a.b", "f_ref|f_count", "\\x41B",
            "\\u017ftr", "(ab)\\1", "(?=foo)bar", "a(?i)b", "a#b", "a-b", "[k]x", "(?x) k x # c"]  # fmt: skip
BODIES = ["ſtrasse", "strasse", "STRASSE", "Kelvin", "Kelvin", "kelvin", "İstanbul", "istanbul", "xİy", "xiy",
          "foo bar", "foobar", "x", "ababz", "aab", "xy", "xaby", "a b", "a_b", "f_ref", "f_count", "AB", "ſtr", "abab",
          "foobar", "a#b", "a-b", "kx", "Kx"]  # fmt: skip


def main() -> None:
    violations = checked = 0
    for pattern, mode, fixed, word in itertools.product(PATTERNS, ("sensitive", "insensitive", "smart"), (False, True),
                                                        (False, True)):
        try:
            verifier = compile_verifier(pattern, fixed_strings=fixed, word_regexp=word, case_mode=mode)
        except PatternError as exc:
            if mode == "sensitive" and not fixed and not word:
                print(f"{pattern!r}: refused by the gate or crate ({str(exc)[:50]})")
            continue
        text = pm._escape_fixed(pattern) if fixed else pattern
        if word:
            text = rf"\b(?:{text})\b"
        insensitive = mode == "insensitive" or (mode == "smart" and not any(ch.isupper() for ch in pattern))
        lits = e5.required_literals(text, insensitive=insensitive)
        if lits is None:
            continue
        hits = verifier.count_lines(BODIES, cap=None, invert=False, budget=None)[0]
        for body, hit in zip(BODIES, hits, strict=True):
            checked += 1
            if hit and not any(lit in body for lit in lits):
                violations += 1
                print(f"VIOLATION {pattern!r} mode={mode} fixed={fixed} word={word} literals={sorted(lits)} body={body!r}")
    print(f"checked {checked} hit bodies against literals; violations {violations}")


main()
