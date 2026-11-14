"""Where a scope is judged for an anonymous caller, pinned with no database.

``scope_judged`` builds the judged paths from each root's literal
directory and each arm's, and its referee here is composition itself:
``addressed_by`` over ``composed_pattern`` of every root and arm, the
text the gate once composed and parsed back. Sets are compared as the
backend hands the paths on, after ``address_of(path).stored``; the
order is asserted on its own. A fake clock counts its reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from vfs import deadline as deadline_module
from vfs.deadline import Deadline
from vfs.paths import Path, address_of
from vfs.pattern_matching import ScopeChannel, composed_pattern
from vfs.storage.backends.database import addressing as addressing_module
from vfs.storage.backends.database.addressing import addressed_by, scope_judged

if TYPE_CHECKING:
    from collections.abc import Sequence

PLAIN_ROOTS = tuple(Path(f"/r{index:03}") for index in range(70))

# Roots composition reads past their own text: metacharacters, and both sides of the tombstone.
ODD_ROOTS = tuple(
    Path(root) for root in ("/a*", "/[x]", "/{a,b}", "/a]b", "/.vfs/trash/t", "/.vfs/trash/k*0", "/.vfs/trash/.vfs")
)

# Arms whose literal directory is a path, nothing (a name with a wildcard and one with
# no metacharacter at all), a class, a head-shaped prefix and a brace.
ARMS = ("src/**", "*.py", "Makefile", "[ab]/**", "0/**", "/.vfs/trash/**", "trash/x/**", "{c,d}/x.py")

# Six arms with six literal directories, so 70 roots make 420 distinct judged paths.
SIX_ARMS = tuple(f"d{index}/**" for index in range(6))


class _CountedClock:
    """A fake monotonic clock: 0.0 until its *late_from*-th read, past any wall from then on."""

    def __init__(self, late_from: int) -> None:
        self.late_from = late_from
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return 0.0 if self.reads < self.late_from else 2.0


def _stored(paths: Sequence[str] | None) -> set[str]:
    """The judged paths as the backend hands them to the posture chain: each one's stored form."""
    assert paths is not None
    return {address_of(path).stored for path in paths}


def _composition(patterns: tuple[str, ...], scope: ScopeChannel) -> list[str]:
    """Composition's reading: the entry-wide patterns beside every root composed with every arm, addressed."""
    composed = [composed_pattern(root, arm) for root in scope.roots for arm in scope.arms]
    return addressed_by(sorted((*patterns, *composed)))


def test_scope_judged_judges_what_composition_judges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: a root holding a metacharacter judged at its bare join with the arm,
    an arm's literal directory read through the trash view, a name arm with no
    metacharacter joined to its root as if it named a directory, the judged
    order drifting from entry-wide first then root order by arm order, a refused
    pattern judged anywhere but the root, or the arms expanded once per root."""
    never = Deadline.never()
    scope = ScopeChannel(roots=(*PLAIN_ROOTS, *ODD_ROOTS), arms=ARMS)
    assert _stored(scope_judged(("/z/*.md",), scope, deadline=never)) == _stored(_composition(("/z/*.md",), scope))
    assert _stored(scope_judged((), scope, deadline=never)) == _stored(_composition((), scope))
    named = ScopeChannel(roots=(Path("/r"), Path("/s")), arms=("Makefile", "src/Makefile"))
    assert scope_judged((), named, deadline=never) == ["/r", "/r/src", "/s", "/s/src"]

    plain = ScopeChannel(roots=PLAIN_ROOTS, arms=("src/**", "*.py"))
    ordered = ["/z", *(path for root in PLAIN_ROOTS for path in (f"{root}/src", str(root)))]
    assert scope_judged(("/z/*.md",), plain, deadline=never) == ordered
    reordered = ScopeChannel(roots=(Path("/r"),), arms=("[ab]/**", "0/**"))
    assert scope_judged((), reordered, deadline=never) == ["/r", "/r/0"]
    assert scope_judged(("/z/*.md",), reordered, deadline=never) == ["/z", "/r", "/r/0"]
    assert _composition((), reordered) == ["/r/0", "/r"]

    assert scope_judged(("a**b",), plain, deadline=never) == ["/"]
    assert scope_judged(("/z/*.md",), ScopeChannel(roots=PLAIN_ROOTS, arms=("a**b",)), deadline=never) == ["/"]
    for empty in (ScopeChannel(roots=PLAIN_ROOTS, arms=()), ScopeChannel(roots=(), arms=("src/**",))):
        assert scope_judged((), empty, deadline=never) == ["/"]
        assert scope_judged(("/z/*.md",), empty, deadline=never) == ["/z"]

    expansions: list[tuple[Any, ...]] = []
    real = addressing_module.expand_channel

    def counted(*args: Any) -> tuple[str, ...]:
        expansions.append(args)
        return real(*args)

    monkeypatch.setattr(addressing_module, "expand_channel", counted)
    judged = scope_judged((), ScopeChannel(roots=PLAIN_ROOTS, arms=SIX_ARMS), deadline=never)
    assert judged is not None
    assert (len(judged), len(expansions)) == (420, 1)


@pytest.mark.parametrize(
    ("patterns", "scope", "at", "late_from", "reads"),
    [
        pytest.param(
            tuple(f"/z{index:02}/*.md" for index in range(70)),
            ScopeChannel(roots=(Path("/a"),), arms=()),
            1.0,
            2,
            2,
            id="entry-wide",
        ),
        pytest.param((), ScopeChannel(roots=(Path("/a"), Path("/b")), arms=("*.py",)), -1.0, 1, 2, id="roots"),
        pytest.param((), ScopeChannel(roots=PLAIN_ROOTS, arms=SIX_ARMS), 1.0, 6, 6, id="pairs"),
    ],
)
def test_scope_judged_stops_at_each_check(
    monkeypatch: pytest.MonkeyPatch,
    patterns: tuple[str, ...],
    scope: ScopeChannel,
    at: float,
    late_from: int,
    reads: int,
) -> None:
    """Guards: one of the three reached-count checks deleted, each in the case
    no other check masks. Without the entry-wide check a scope with no arm
    answers the 64 paths its first chunk addressed; without the roots check
    an expired gate with no entry-wide pattern answers no path at all; and
    without the pairs check a stop inside the product answers the 64 paths
    joined so far. Each is a part of the call judged as the whole."""
    clock = _CountedClock(late_from)
    monkeypatch.setattr(deadline_module, "monotonic", clock)
    assert scope_judged(patterns, scope, deadline=Deadline(at=at)) is None
    assert clock.reads == reads


def test_scope_judged_past_its_deadline_judges_nothing_beside_an_entry_wide_pattern() -> None:
    """Guards: a gate already past its wall judged at the entry-wide paths it
    never addressed, or at the root alone, instead of refused."""
    scope = ScopeChannel(roots=(Path("/a"), Path("/b")), arms=("*.py",))
    assert scope_judged(("/z/*.md",), scope, deadline=Deadline(at=-1.0)) is None
