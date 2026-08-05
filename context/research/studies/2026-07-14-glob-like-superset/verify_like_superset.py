"""Superset proof for the glob->LIKE prefilter under segment-aware semantics.

The database glob is prefilter-then-verify: a LIKE narrows candidates,
the compiled chokepoint regex is the authority. That structure is
sound only if the LIKE is a *superset* of the authoritative matcher —
over-matching costs wasted row fetches, under-matching silently loses
results before the verifier ever sees them.

This spike enumerates a structured corpus of glob patterns and paths and
checks, for every pair the authoritative matcher accepts, that the LIKE
prefilter accepts it too — under BOTH evaluators the backends face:

- an ANSI reference (case-sensitive, ``%``/``_``/ESCAPE only) — the
  Postgres posture;
- sqlite's builtin LIKE (ASCII-case-insensitive) — checked live.

Since 2026-08-01 (the 073 landing) it imports the LANDED functions —
``reads._glob_like``, ``reads._literal_prefix``, ``glob_patterns
.compile_filter``/``glob_defect``/``derive_ext``, ``descent
.escape_like`` — so every run re-proves the shipped code, and patterns
compile through the landed chokepoint: path-arm patterns are anchored
gitignore-exact before translation, exactly as the backend sees them.

It proves four claims (numbered 2–5 for continuity with the pre-landing
runs; claim 1 — that the pre-073 char-by-char translator under-matched
on ``**/`` — was the story's motivating bug, demonstrated 2026-07-14
and retired with that translator when the fix landed):

2. The landed segment-aware translator (whole ``**`` components fuse
   with their separator into ``%``) satisfies the superset property
   everywhere, on both the path arm and the name arm.
3. sqlite LIKE accepts everything ANSI LIKE accepts on this corpus, so
   a translation proven against the ANSI reference is engine-agnostic:
   sqlite's only divergence (ASCII case folding) errs superset-ward,
   and the authoritative verifier restores exactness.
4. Extension pushdown is sound: when the pattern's last segment ends
   in a derivable literal extension (``**/*.txt`` -> ``txt``), every
   authoritative match satisfies ``lexical_ext(name) == ext OR name ==
   literal-dot-suffix`` — the OR arm covers pure dotfiles (``.txt``
   has no extension by ``extract_extension``'s dot>0 rule but ``*.txt``
   matches it), so an indexed ``ext`` equality can narrow anchor-free
   patterns without dropping rows.
5. No emitted LIKE ever ends in a dangling escape. This invariant is
   load-bearing: Postgres errors on a dangling-escape LIKE
   *data-dependently* (only for rows whose match reaches the trailing
   escape), so a violation would error on some rows and silently drop
   others. The translator only emits ``\\`` in complete pairs and the
   prefix fallback always ends in ``%`` — checked here explicitly.

Scope notes (adversarially audited 2026-07-14; three-agent attack:
~11.5M fuzz trials, 12-mutant mutation audit, differential test against
real PostgreSQL 18.0 + DuckDB through SQLAlchemy ``.like(escape='\\')``
end-to-end — the ANSI reference agreed with Postgres on 100% of pairs):

- This proves *soundness* (superset), never *tightness* — a looser
  translation (``?`` -> ``%``) passes identically; selectivity is a
  performance property the corpus cannot pin.
- The corpus kills the known unsound mutants: backslash names/segments
  (escape handling), ``*.*`` (last-wildcard cut in ``derive_ext``),
  and a >32-char extension (the ``normalize_extension`` cap).
- ``standard_conforming_strings=off`` is an unsupported Postgres
  configuration: SQLAlchemy renders the ESCAPE char inline (the
  pattern itself is a bound parameter).

Moved here 2026-08-05 at spec 073's mining pass (born 2026-07-14 as
that spec's spike). Landed-run record (re-verified 2026-08-05, from
this location): claims 2-5 green — 523,064 authoritative matches with
zero prefilter drops; 6,636 derivable patterns, 81,260 matches kept
by the derived-ext filter. The decision set this study underwrites is
ADR 032.

Run:  uv run python context/research/studies/2026-07-14-glob-like-superset/verify_like_superset.py
Exit: nonzero on any property violation.
"""

from __future__ import annotations

import itertools
import re
import sqlite3
import sys

from vfs.glob_patterns import compile_filter, derive_ext, glob_defect
from vfs.paths import normalize_extension
from vfs.storage.backends.database.descent import LIKE_ESCAPE, escape_like
from vfs.storage.backends.database.reads import _glob_like, _literal_prefix


def prefilter_like(pattern: str) -> str:
    """The LIKE the backend actually applies: anchor, then translate or fall back."""
    anchored = compile_filter(pattern, ()).pattern
    like = _glob_like(anchored)
    if like is not None:
        return like
    return escape_like(_literal_prefix(anchored)) + "%"


def lexical_ext(name: str) -> str | None:
    """Mirror of paths.extract_extension over a bare leaf name (lexical, any kind)."""
    dot = name.rfind(".")
    if dot <= 0:
        return None
    return normalize_extension(name[dot + 1 :])


# ---------------------------------------------------------------------------
# The two LIKE evaluators and the authoritative matcher
# ---------------------------------------------------------------------------


def ansi_like_regex(like: str) -> re.Pattern[str]:
    """Case-sensitive ANSI LIKE with ESCAPE '\\' — the Postgres posture."""
    out: list[str] = []
    chars = iter(like)
    for ch in chars:
        if ch == LIKE_ESCAPE:
            out.append(re.escape(next(chars)))
        elif ch == "%":
            out.append("(?s:.*)")
        elif ch == "_":
            out.append("(?s:.)")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out) + r"\Z")


_SQLITE = sqlite3.connect(":memory:")


def sqlite_like(subject: str, like: str) -> bool:
    row = _SQLITE.execute("SELECT ? LIKE ? ESCAPE ?", (subject, like, LIKE_ESCAPE)).fetchone()
    return bool(row[0])


def authoritative(pattern: str) -> re.Pattern[str] | None:
    """The landed chokepoint semantics; None for patterns the chokepoint refuses."""
    if glob_defect(pattern) is not None:
        return None  # classifies invalid before any row is touched
    return compile_filter(pattern, ()).regex


# ---------------------------------------------------------------------------
# Corpus — structured, not random: every operator, every placement
# ---------------------------------------------------------------------------

# Name vocabulary stresses dotfiles, LIKE metacharacters as data, case,
# and shapes that collide with wildcard translations ('a_b' vs 'a?b').
NAMES = [
    "a", "b", "ab", "a.txt", "bb.txt", ".hidden", "a_b", "50%", "A.txt", ".txt", "b.TXT",
    "a\\b",  # backslash IS the LIKE escape char — data must never trip it
    "c." + "e" * 33,  # extension past extract_extension's 32-char cap
]

# Pattern segments cover: literals, star/question placements, whole and
# (refused) partial '**', character classes, and LIKE metachars needing escape.
SEGMENTS = [
    "a", "ab", "*", "**", "?", "??", "a*", "*.txt", "*.TXT", "?.txt", "a?b", "a_b", "50%",
    "[ab]", "[!a]", "[a].txt", ".hidden", "*.hidden", "a**b",
    "a\\b",  # backslash literal — must be escaped in the emitted LIKE
    "x\\y[ab]",  # backslash inside a class-fallback's literal prefix
    "*.*",  # two wildcards around a dot — ext derivation must cut at the LAST
    "*.[ch]",  # class AFTER the dot — derivation must refuse, not derive "[ch]"
    "[.a]x",  # class holding the only dot — same refusal family
]


def build_paths() -> list[str]:
    paths: list[str] = []
    for depth in (1, 2, 3):
        for combo in itertools.product(NAMES, repeat=depth):
            paths.append("/" + "/".join(combo))
    return paths


def build_patterns() -> list[str]:
    patterns: list[str] = []
    for depth in (1, 2, 3):
        for combo in itertools.product(SEGMENTS, repeat=depth):
            body = "/".join(combo)
            patterns.append("/" + body)  # absolute path-arm
            if depth > 1:
                patterns.append(body)  # relative path-arm (anchored at the root by the chokepoint)
    return patterns


# ---------------------------------------------------------------------------
# The property checks
# ---------------------------------------------------------------------------


def check_superset(patterns: list[str], subjects: list[str], arm: str) -> tuple[int, list[str]]:
    """Every authoritative match must pass the LIKE under both evaluators."""
    matches = 0
    violations: list[str] = []
    for pattern in patterns:
        regex = authoritative(pattern)
        if regex is None:
            continue
        like = prefilter_like(pattern)
        ansi = ansi_like_regex(like)
        for subject in subjects:
            if regex.match(subject) is None:
                continue
            matches += 1
            if ansi.match(subject) is None:
                violations.append(f"[{arm}/ansi]   glob {pattern!r} matches {subject!r} but LIKE {like!r} does not")
            elif not sqlite_like(subject, like):
                violations.append(f"[{arm}/sqlite] glob {pattern!r} matches {subject!r} but LIKE {like!r} does not")
            if len(violations) >= 25:
                return matches, violations
    return matches, violations


def check_ext_pushdown(patterns: list[str], subjects: list[str]) -> tuple[int, int, list[str]]:
    """Derived-ext narrowing must keep every authoritative match.

    Returns (patterns with a derivable ext, matches checked, violations).
    """
    derivable = 0
    matches = 0
    violations: list[str] = []
    for pattern in patterns:
        derived = derive_ext(pattern)
        regex = authoritative(pattern)
        if derived is None or regex is None:
            continue
        derivable += 1
        ext, dot_suffix = derived
        for subject in subjects:
            if regex.match(subject) is None:
                continue
            matches += 1
            leaf = subject.rsplit("/", 1)[-1]
            if lexical_ext(leaf) != ext and leaf != dot_suffix:
                violations.append(
                    f"glob {pattern!r} matches {subject!r} but ext filter ({ext!r} OR name == {dot_suffix!r}) drops it"
                )
                if len(violations) >= 25:
                    return derivable, matches, violations
    return derivable, matches, violations


def check_no_dangling_escape(patterns: list[str]) -> list[str]:
    """Every emitted LIKE must pair its escapes; none may end in a bare one."""
    violations: list[str] = []
    for pattern in patterns:
        like = prefilter_like(pattern)
        i = 0
        while i < len(like):
            if like[i] == LIKE_ESCAPE:
                if i + 1 >= len(like):
                    violations.append(f"glob {pattern!r} emits LIKE {like!r} with a dangling escape")
                    break
                i += 2
            else:
                i += 1
    return violations


def check_engine_agreement(patterns: list[str], subjects: list[str]) -> list[str]:
    """sqlite LIKE must accept everything ANSI LIKE accepts (agnostic claim)."""
    disagreements: list[str] = []
    for pattern in patterns:
        like = prefilter_like(pattern)
        ansi = ansi_like_regex(like)
        for subject in subjects:
            if ansi.match(subject) is not None and not sqlite_like(subject, like):
                disagreements.append(f"ANSI accepts, sqlite rejects: {subject!r} LIKE {like!r}")
                if len(disagreements) >= 10:
                    return disagreements
    return disagreements


def main() -> int:
    paths = build_paths()
    patterns = build_patterns()
    name_patterns = [p for p in SEGMENTS if p != "a**b"]  # name arm: no '/'
    print(f"corpus: {len(patterns)} path patterns x {len(paths)} paths, {len(name_patterns)} name patterns x {len(NAMES)} names")

    failures = 0

    # Claim 2: the landed translator is a superset on both arms, both engines.
    path_matches, fixed_violations = check_superset(patterns, paths, "path")
    name_matches, name_violations = check_superset(name_patterns, NAMES, "name")
    total = path_matches + name_matches
    bad = fixed_violations + name_violations
    if bad:
        print(f"\nclaim 2 FAILED: {len(bad)}+ superset violations out of {total} authoritative matches:")
        for line in bad[:10]:
            print(f"  {line}")
        failures += 1
    else:
        print(f"claim 2 holds: {total} authoritative matches ({path_matches} path, {name_matches} name), zero prefilter drops")

    # Claim 3: sqlite agrees with (or is looser than) the ANSI reference.
    disagreements = check_engine_agreement(patterns[:2000], paths[:2000])
    if disagreements:
        print(f"\nclaim 3 FAILED: sqlite rejects rows ANSI accepts:")
        for line in disagreements:
            print(f"  {line}")
        failures += 1
    else:
        print("claim 3 holds: sqlite LIKE ⊇ ANSI LIKE on the corpus (case folding is its only looseness)")

    # Claim 4: pattern-derived extension narrowing never drops a match.
    derivable, ext_matches, ext_violations = check_ext_pushdown(patterns, paths)
    name_derivable, name_ext_matches, name_ext_violations = check_ext_pushdown(name_patterns, NAMES)
    ext_bad = ext_violations + name_ext_violations
    if ext_bad:
        print(f"\nclaim 4 FAILED: {len(ext_bad)}+ matches dropped by the derived-ext filter:")
        for line in ext_bad[:10]:
            print(f"  {line}")
        failures += 1
    else:
        print(
            f"claim 4 holds: {derivable + name_derivable} derivable patterns, "
            f"{ext_matches + name_ext_matches} matches kept by (ext == derived OR name == dot-suffix)"
        )

    # Claim 5: no emitted LIKE ever ends in (or contains) a dangling escape.
    dangling = check_no_dangling_escape(patterns + name_patterns)
    if dangling:
        print(f"\nclaim 5 FAILED: {len(dangling)} dangling escapes emitted:")
        for line in dangling[:10]:
            print(f"  {line}")
        failures += 1
    else:
        print("claim 5 holds: every emitted LIKE pairs its escapes (Postgres dangling-escape error unreachable)")

    print(f"\n{'FAIL' if failures else 'OK'}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
