"""The authority value: the three construction doors, the invariants they
enforce, the derived owner, and the one reserved name."""

from __future__ import annotations

import pytest

from vfs.authority import ANONYMOUS_NAME, MAX_SUBJECTS, SYSTEM_NAME, Authority, Narrowing, Principal, owner_for

ALICE = Principal("alice")
BOB = Principal("bob")
BOT = Principal("bot", kind="service", scopes=frozenset({"files:read"}))


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------


def test_a_principal_is_a_frozen_hashable_value() -> None:
    assert Principal("alice") == ALICE
    assert hash(Principal("alice")) == hash(ALICE)
    assert ALICE.kind == "user" and ALICE.scopes == frozenset()
    assert BOT.is_system is False
    with pytest.raises(AttributeError):
        ALICE.sub = "mallory"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize("sub", ["", "   "])
def test_a_principal_needs_a_name(sub: str) -> None:
    with pytest.raises(ValueError, match="non-empty sub"):
        Principal(sub)


@pytest.mark.parametrize(("name", "kind"), [(SYSTEM_NAME, "system"), (ANONYMOUS_NAME, "anonymous")])
def test_the_reserved_names_are_reserved_both_ways(name: str, kind: str) -> None:
    # A user cannot take a reserved name; a reserved kind takes no other.
    with pytest.raises(ValueError, match="reserved"):
        Principal(name)
    with pytest.raises(ValueError, match="reserved"):
        Principal("root", kind=kind)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="reserved"):
        Principal(SYSTEM_NAME if kind == "anonymous" else ANONYMOUS_NAME, kind=kind)  # ty: ignore[invalid-argument-type]
    assert Principal(name, kind=kind).kind == kind  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# Authority — the three doors
# ---------------------------------------------------------------------------


def test_of_is_a_subject_acting_as_itself() -> None:
    authority = Authority.of(ALICE, source_identity="issuer|alice")
    assert authority.subjects == frozenset({ALICE})
    assert authority.actor == ALICE
    assert authority.provenance == "constructed"
    assert authority.narrowing is Narrowing.NONE
    assert authority.source_identity == "issuer|alice"
    assert authority.is_system is False


def test_on_behalf_of_is_a_set_with_an_actor() -> None:
    authority = Authority.on_behalf_of({ALICE, BOB}, actor=BOT)
    assert authority.subjects == frozenset({ALICE, BOB})
    assert authority.actor == BOT
    assert authority.subject_names == ("alice", "bob")
    assert authority.provenance == "constructed"


def test_system_is_the_marked_exception() -> None:
    authority = Authority.system()
    assert authority.is_system is True
    assert authority.subjects == frozenset()
    assert authority.subject_names == ()
    assert authority.provenance == "system"
    assert authority == Authority.system()


def test_anonymous_is_nobody_by_name() -> None:
    nobody = Authority.anonymous()
    assert nobody.is_anonymous is True and nobody.is_system is False
    assert nobody.actor.sub == ANONYMOUS_NAME and nobody.subject_names == (ANONYMOUS_NAME,)
    assert nobody.provenance == "constructed"
    assert nobody == Authority.anonymous()


def test_an_authority_is_hashable_and_equal_by_value() -> None:
    one = Authority.on_behalf_of({ALICE, BOB}, actor=BOT)
    two = Authority.on_behalf_of({BOB, ALICE}, actor=BOT)
    assert one == two and hash(one) == hash(two)
    assert len({one, two, Authority.of(ALICE)}) == 2


# ---------------------------------------------------------------------------
# Invariants at construction
# ---------------------------------------------------------------------------


def test_the_subject_set_is_non_empty_unless_the_actor_is_system() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Authority.on_behalf_of(set(), actor=BOT)


def test_the_system_principal_is_never_a_subject() -> None:
    with pytest.raises(ValueError, match="never a subject"):
        Authority.on_behalf_of({Principal(SYSTEM_NAME, kind="system")}, actor=BOT)
    with pytest.raises(ValueError, match="never a subject"):
        Authority.of(Principal(SYSTEM_NAME, kind="system"))


def test_the_system_actor_acts_for_no_subject() -> None:
    with pytest.raises(ValueError, match="no subject"):
        Authority.on_behalf_of({ALICE}, actor=Principal(SYSTEM_NAME, kind="system"))


def test_the_system_provenance_goes_with_the_system_actor_and_nothing_else() -> None:
    # Provenance is a claim; the one claim a shape can check is this one.
    with pytest.raises(ValueError, match="system provenance"):
        Authority(subjects=frozenset({ALICE}), actor=ALICE, provenance="system")
    with pytest.raises(ValueError, match="system provenance"):
        Authority(subjects=frozenset(), actor=Principal(SYSTEM_NAME, kind="system"), provenance="constructed")


def test_the_anonymous_principal_has_exactly_one_shape() -> None:
    nobody = Principal(ANONYMOUS_NAME, kind="anonymous")
    with pytest.raises(ValueError, match="sole subject"):
        Authority.on_behalf_of({nobody, ALICE}, actor=BOT)
    with pytest.raises(ValueError, match="sole subject"):
        Authority.on_behalf_of({ALICE}, actor=nobody)
    with pytest.raises(ValueError, match="sole subject"):
        Authority.on_behalf_of({nobody}, actor=BOT)


def test_the_set_is_bounded() -> None:
    crowd = {Principal(f"p{i}") for i in range(MAX_SUBJECTS)}
    assert len(Authority.on_behalf_of(crowd, actor=BOT).subjects) == MAX_SUBJECTS
    with pytest.raises(ValueError, match=f"at most {MAX_SUBJECTS}"):
        Authority.on_behalf_of(crowd | {Principal("one-more")}, actor=BOT)


# ---------------------------------------------------------------------------
# Ownership derives from the subjects
# ---------------------------------------------------------------------------


def test_one_subject_owns_what_it_makes() -> None:
    assert Authority.of(ALICE).owner_subject == "alice"
    assert owner_for(Authority.of(ALICE)) == "alice"
    # The app path ignores whatever the payload declared.
    assert owner_for(Authority.of(ALICE), declared="mallory") == "alice"


def test_a_set_owns_nothing_and_the_container_governs() -> None:
    together = Authority.on_behalf_of({ALICE, BOB}, actor=BOT)
    assert together.owner_subject is None
    assert owner_for(together, declared="alice") is None


def test_the_system_actor_stamps_the_declared_owner() -> None:
    assert Authority.system().owner_subject is None
    assert owner_for(Authority.system(), declared="alice") == "alice"
    assert owner_for(Authority.system()) is None


def test_anonymous_owns_nothing() -> None:
    # Else every anonymous caller would own every anonymous row.
    assert Authority.anonymous().owner_subject is None
    assert owner_for(Authority.anonymous(), declared="alice") is None


def test_no_authority_stamps_nothing() -> None:
    assert owner_for(None, declared="alice") is None
