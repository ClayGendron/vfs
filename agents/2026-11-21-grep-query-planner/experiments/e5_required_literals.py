"""E5: a case-exact required-literal extraction, and a property test that it never rules out a match.

The extraction walks the parsed pattern, not the folded gram plan. A literal joins a run only where matching is
case-sensitive; anything else ends the run: a class, any-char, an assertion, a group boundary, a repeat, or a literal
under a case-insensitive scope. A concatenation requires the best of its runs and mandatory sub-results. An
alternation requires the union of its branches' requirements, or nothing when any branch requires nothing. A repeat
with min >= 1 passes its body's requirement through. The answer is a set of literals of which every match contains at
least one, or None. Branches and class members are never deduplicated by fold.

This prototype runs over Python's ``re`` parser to test the algorithm; the design builds it over the matcher's own
regex-syntax HIR in the Rust crate, where case-insensitivity is already lowered to classes.

    uv run python agents/2026-11-21-grep-query-planner/experiments/e5_required_literals.py [cases]
"""

from __future__ import annotations

import random
import re
import sys
from re import _constants as C  # noqa: N812
from re import _parser as P  # noqa: N812

Literals = frozenset[str] | None


def required_literals(pattern: str, *, insensitive: bool) -> Literals:
    flags = re.IGNORECASE if insensitive else 0
    parsed = P.parse(pattern, flags)
    if parsed.state.flags & re.IGNORECASE:
        return None
    return _seq(list(parsed), insensitive=False)


def _seq(items: list, *, insensitive: bool) -> Literals:
    pieces: list[frozenset[str]] = []
    run: list[str] = []

    def close() -> None:
        if run:
            pieces.append(frozenset(["".join(run)]))
            run.clear()

    for op, av in items:
        if op is C.LITERAL and not insensitive:
            run.append(chr(av))
            continue
        close()
        if op is C.SUBPATTERN:
            _group, add, remove, body = av
            scoped = (insensitive or bool(add & re.IGNORECASE)) and not (remove & re.IGNORECASE)
            sub = _seq(list(body), insensitive=scoped)
            if sub is not None:
                pieces.append(sub)
        elif op is C.BRANCH:
            branches = [_seq(list(alt), insensitive=insensitive) for alt in av[1]]
            if all(branch is not None for branch in branches):
                pieces.append(frozenset().union(*branches))
        elif op in (C.MAX_REPEAT, C.MIN_REPEAT, C.POSSESSIVE_REPEAT):
            low, _high, body = av
            if low >= 1:
                sub = _seq(list(body), insensitive=insensitive)
                if sub is not None:
                    pieces.append(sub)
        elif op is C.ATOMIC_GROUP:
            sub = _seq(list(av), insensitive=insensitive)
            if sub is not None:
                pieces.append(sub)
    close()
    usable = [piece for piece in pieces if piece and all(piece)]
    if not usable:
        return None
    return max(usable, key=lambda piece: (min(len(lit) for lit in piece), -len(piece)))


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

ALPHABET = "abAB_ "


def random_pattern(rng: random.Random, depth: int = 0) -> str:
    parts = []
    for _ in range(rng.randint(1, 4)):
        roll = rng.random()
        if roll < 0.35:
            parts.append(rng.choice("abAB_"))
        elif roll < 0.45:
            parts.append(rng.choice(["[aA]", "[ab]", "[^a]", ".", "\\w"]))
        elif roll < 0.52:
            parts.append(rng.choice(["^", "$", "\\b"]))
        elif roll < 0.65 and depth < 3:
            parts.append("(" + random_pattern(rng, depth + 1) + ")" + rng.choice(["", "?", "*", "+", "{2}", "{0,1}"]))
        elif roll < 0.75 and depth < 3:
            parts.append("(?i:" + random_pattern(rng, depth + 1) + ")")
        elif roll < 0.82 and depth < 3:
            parts.append("(?-i:" + random_pattern(rng, depth + 1) + ")")
        elif roll < 0.92 and depth < 3:
            parts.append("(?:" + "|".join(random_pattern(rng, depth + 1) for _ in range(rng.randint(2, 3))) + ")")
        else:
            parts.append(rng.choice("ab") + rng.choice(["?", "*", "+"]))
    text = "".join(parts)
    if depth == 0 and rng.random() < 0.15:
        text = "(?i)" + text
    return text


def main() -> None:
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
    rng = random.Random(20261121)
    checked = with_literal = violations = 0
    for _ in range(cases):
        pattern = random_pattern(rng)
        insensitive = rng.random() < 0.2
        try:
            compiled = re.compile(pattern, re.MULTILINE | (re.IGNORECASE if insensitive else 0))
            literals = required_literals(pattern, insensitive=insensitive)
        except re.error:
            continue
        if literals is None:
            continue
        with_literal += 1
        for _ in range(20):
            body = "".join(rng.choice(ALPHABET + "\n") for _ in range(rng.randint(0, 24)))
            checked += 1
            if compiled.search(body) and not any(literal in body for literal in literals):
                violations += 1
                if violations <= 10:
                    print(f"VIOLATION pattern={pattern!r} insensitive={insensitive} literals={sorted(literals)} body={body!r}")
    print(f"patterns with a literal: {with_literal} of {cases}; bodies checked: {checked}; violations: {violations}")
    for pattern, insensitive in [
        ("[Kk]malloc", False), ("Kmalloc|kmalloc", False), ("(?i)kmalloc", False), ("(?i:KMALLOC)", False),
        ("kmalloc", True), ("^struct dentry \\{", False), ("f_ref|f_count", False), ("x(?i:y)z", False),
        ("\\.read_iter|\\.write_iter|\\.mmap", False), ("i_count", False), ("a|.", False),
    ]:  # fmt: skip
        print(f"{pattern!r:40} insensitive={insensitive!s:5} -> {required_literals(pattern, insensitive=insensitive)}")


if __name__ == "__main__":
    main()
