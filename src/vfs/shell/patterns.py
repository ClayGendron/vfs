"""GNU patterns read in the verbs' languages, where the two read a pattern alike.

The shell serves ``grep -r`` and ``find`` from the indexed verbs only when the
answer is the one GNU's own matcher gives. :func:`verb_regex` writes a grep
pattern, basic, extended or fixed, in the regex language of the ``grep`` verb,
and answers ``None`` for any construct the two read differently or that this
module does not know: back-references, ``\\<`` and ``\\w``, POSIX bracket
classes, a quantifier with nothing before it, an empty group. The shell then
runs GNU's form in its own library, which reads every construct.

    verb_regex("a\\(b\\|c\\)*$", "basic")    # 'a(?:b|c)*$'
    verb_regex("\\<word", "basic")           # None: GNU's form serves it

:func:`fnmatch_safe` and :func:`glob_safe` say the same of a ``find`` name
pattern and a ``grep --include`` glob.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

Dialect = Literal["basic", "extended", "fixed"]
"""How GNU grep reads a pattern: ``-G``, ``-E`` or ``-F``."""

REPEAT_CEILING: Final = 255
"""The largest count an interval may name and still be served by the verb."""

_VERB_META: Final = frozenset("\\.^$|?*+()[]{}")
"""Characters the verb's language reads as operators outside a class."""

_CLASS_META: Final = frozenset("\\[]^-&~")
"""Characters the verb's language reads as operators inside a class."""

_ERE_ESCAPABLE: Final = frozenset("\\.[]()*+?{}|^$")
"""Characters an extended pattern may escape to mean themselves."""

_BRE_ESCAPABLE: Final = frozenset("\\.[]*^$/")
"""Characters a basic pattern may escape to mean themselves."""

_UNFOLDED: Final = frozenset("iI[")
"""What keeps an ASCII pattern from ``-i``: the letter glibc folds with the dotless i (U+0131), and a bracket."""


class Translated(NamedTuple):
    """A pattern in the verb's language, and its text when it holds no operator."""

    regex: str
    literal: str | None


# ---------------------------------------------------------------------------
# Grep patterns
# ---------------------------------------------------------------------------


def verb_regex(pattern: str, dialect: Dialect) -> Translated | None:
    """``pattern`` as the ``grep`` verb reads it, matching the lines GNU grep matches, or ``None``."""
    if dialect == "fixed":
        return Translated("".join(_escaped(ch) for ch in pattern), pattern)
    reader = _Reader(pattern, extended=dialect == "extended")
    try:
        regex = reader.alternation()
    except _NotServedError:
        return None
    return Translated(regex, reader.literal())


def case_folds_alike(pattern: str) -> bool:
    """Whether ``-i`` over ``pattern`` folds each letter as glibc's ``towlower`` and the verb both do.

    The two fold every ASCII letter alike, ``k`` with the Kelvin sign and ``s`` with the long s (U+017F)
    included, except ``i``, which glibc also folds with the dotless i (U+0131). So a pattern is
    served under ``-i`` when it is ASCII and holds no ``i`` and no bracket, whose range may.
    """
    return pattern.isascii() and not (_UNFOLDED & set(pattern))


# ---------------------------------------------------------------------------
# Name patterns and globs
# ---------------------------------------------------------------------------


def fnmatch_safe(pattern: str) -> bool:
    """Whether Python's ``fnmatch`` reads ``pattern`` as GNU ``fnmatch`` does with no flags.

    It does for literal characters, ``*``, ``?`` and a closed bracket of characters and
    ranges, ``[!...]`` included; a backslash, ``[^...]`` and a POSIX class are left out.
    """
    if "\\" in pattern:
        return False
    index = 0
    while index < len(pattern):
        if pattern[index] == "[":
            if pattern.startswith("^", index + 1):
                return False
            end = _bracket_end(pattern, index, negator="!")
            if end is None:
                return False
            index = end
        index += 1
    return True


def glob_safe(pattern: str) -> bool:
    """Whether the verbs' glob language reads a slash-free ``pattern`` as GNU ``fnmatch`` does.

    The verbs' globs expand braces and refuse ``**`` inside a name, so those are left out
    beside what :func:`fnmatch_safe` leaves out.
    """
    if not pattern or "/" in pattern or "**" in pattern or "{" in pattern or "}" in pattern:
        return False
    return fnmatch_safe(pattern)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _NotServedError(Exception):
    """A construct the verb does not read as GNU grep reads it."""


class _Reader:
    """One pass over a basic or extended pattern, writing the verb's spelling as it goes."""

    def __init__(self, pattern: str, *, extended: bool) -> None:
        self.text = pattern
        self.extended = extended
        self.index = 0
        self.depth = 0
        self.operators = False

    def literal(self) -> str | None:
        """The pattern's own text when it held no operator, else ``None``."""
        if self.operators:
            return None
        return self._unescaped()

    def alternation(self) -> str:
        branches = [self.branch()]
        while self._at_bar():
            self.operators = True
            self.index += 1 if self.extended else 2
            branches.append(self.branch())
        if any(not branch for branch in branches) and len(branches) > 1:
            raise _NotServedError
        return "|".join(branches)

    def branch(self) -> str:
        out: list[str] = []
        start = True
        while self.index < len(self.text) and not self._at_bar() and not self._at_close():
            atom, start = self.piece(start)
            out.append(atom)
        return "".join(out)

    def piece(self, start: bool) -> tuple[str, bool]:
        """One atom and its quantifiers; the flag says whether the next atom starts an expression."""
        ch = self.text[self.index]
        if ch == "^" and (start or self.extended):
            if not start:
                raise _NotServedError
            self.operators = True
            self.index += 1
            return "^", True
        if ch == "$" and self._at_end_of_branch(self.index + 1):
            self.operators = True
            self.index += 1
            return "$", False
        if ch == "$" and self.extended:
            raise _NotServedError
        if ch == "*" and start:
            if self.extended:
                raise _NotServedError
            self.index += 1
            return self._quantified("\\*"), False
        atom = self.atom()
        return self._quantified(atom), False

    def atom(self) -> str:
        ch = self.text[self.index]
        if ch == "[":
            self.operators = True
            return self.bracket()
        if ch == ".":
            self.operators = True
            self.index += 1
            return "."
        if ch == "\\":
            return self.escape()
        if self.extended and ch == "(":
            self.index += 1
            return self.group(close=")")
        if self.extended and ch in "*+?{|)":
            raise _NotServedError
        self.index += 1
        return _escaped(ch)

    def escape(self) -> str:
        if self.index + 1 >= len(self.text):
            raise _NotServedError
        nxt = self.text[self.index + 1]
        self.index += 2
        if not self.extended and nxt == "(":
            return self.group(close="\\)")
        escapable = _ERE_ESCAPABLE if self.extended else _BRE_ESCAPABLE
        if nxt not in escapable:
            raise _NotServedError
        return _escaped(nxt)

    def group(self, *, close: str) -> str:
        self.operators = True
        self.depth += 1
        inner = self.alternation()
        if not inner or not self.text.startswith(close, self.index):
            raise _NotServedError
        self.index += len(close)
        self.depth -= 1
        return f"(?:{inner})"

    def bracket(self) -> str:
        end = _bracket_end(self.text, self.index, negator="^")
        if end is None:
            raise _NotServedError
        body = self.text[self.index + 1 : end]
        self.index = end + 1
        negated = body.startswith("^")
        if negated:
            body = body[1:]
        members: list[str] = []
        at = 0
        while at < len(body):
            low = body[at]
            if at + 2 < len(body) and body[at + 1] == "-":
                high = body[at + 2]
                if low > high:
                    raise _NotServedError
                members.append(f"{_class_escaped(low)}-{_class_escaped(high)}")
                at += 3
                continue
            members.append(_class_escaped(low))
            at += 1
        return "[" + ("^" if negated else "") + "".join(members) + "]"

    def _quantified(self, atom: str) -> str:
        quantifier = self._quantifier()
        if quantifier is None:
            return atom
        self.operators = True
        if self._quantifier() is not None:
            raise _NotServedError
        return atom + quantifier

    def _quantifier(self) -> str | None:
        if self.index >= len(self.text):
            return None
        ch = self.text[self.index]
        if ch == "*":
            self.index += 1
            return "*"
        if self.extended and ch in "+?":
            self.index += 1
            return ch
        if self.extended and ch == "{":
            return self._interval(1, "}")
        if not self.extended and ch == "\\" and self.index + 1 < len(self.text):
            nxt = self.text[self.index + 1]
            if nxt in "+?":
                self.index += 2
                return nxt
            if nxt == "{":
                return self._interval(2, "\\}")
        return None

    def _interval(self, opening: int, close: str) -> str:
        end = self.text.find(close, self.index + opening)
        if end < 0:
            raise _NotServedError
        body = self.text[self.index + opening : end]
        low, comma, high = body.partition(",")
        if not (low.isascii() and high.isascii()) or not (low.isdigit() or (comma and not low)):
            raise _NotServedError
        if high and not high.isdigit():
            raise _NotServedError
        lo = int(low) if low else 0
        hi = int(high) if high else None
        if lo > REPEAT_CEILING or (hi is not None and (hi > REPEAT_CEILING or hi < lo)):
            raise _NotServedError
        self.index = end + len(close)
        if not comma:
            return f"{{{lo}}}"
        return f"{{{lo},}}" if hi is None else f"{{{lo},{hi}}}"

    def _at_bar(self) -> bool:
        if self.extended:
            return self.text.startswith("|", self.index)
        return self.text.startswith("\\|", self.index)

    def _at_close(self) -> bool:
        if self.depth == 0:
            return False
        return self.text.startswith(")" if self.extended else "\\)", self.index)

    def _at_end_of_branch(self, at: int) -> bool:
        if at >= len(self.text):
            return True
        if self.extended:
            return self.text[at] == "|" or (self.depth > 0 and self.text[at] == ")")
        return self.text.startswith("\\|", at) or (self.depth > 0 and self.text.startswith("\\)", at))

    def _unescaped(self) -> str:
        out: list[str] = []
        at = 0
        while at < len(self.text):
            if self.text[at] == "\\":
                at += 1
            out.append(self.text[at])
            at += 1
        return "".join(out)


def _bracket_end(text: str, start: int, *, negator: str) -> int | None:
    """The index of the ``]`` closing the bracket at ``start``, or ``None`` when the bracket is not served.

    ``negator`` is the character that negates a bracket in the pattern's language; a ``]``
    first after it, or first at all, is a member.
    """
    at = start + 1
    if text.startswith(negator, at):
        at += 1
    if text.startswith("]", at):
        at += 1
    while at < len(text):
        ch = text[at]
        if ch == "]":
            return at
        if ch == "[" and text.startswith((":", ".", "="), at + 1):
            return None
        if ch == "\\":
            return None
        at += 1
    return None


def _escaped(ch: str) -> str:
    return "\\" + ch if ch in _VERB_META else ch


def _class_escaped(ch: str) -> str:
    return "\\" + ch if ch in _CLASS_META else ch
