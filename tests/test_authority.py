"""The authority value: the three construction doors, the invariants they
enforce, the derived owner, the reserved names, and the caller a call runs as."""

from __future__ import annotations

import logging

import pytest

from vfs.authority import (
    ANONYMOUS_NAME,
    MAX_SUBJECTS,
    SYSTEM_NAME,
    Authority,
    Narrowing,
    Principal,
    caller_for,
    owner_for,
    owner_refusal,
    warn_if_system_default,
)

RESERVED_OWNERS = ("*", "anon", "system", "group:eng", "", "   ")

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


@pytest.mark.parametrize("declared", RESERVED_OWNERS)
def test_a_reserved_name_can_own_no_row(declared: str) -> None:
    # Everyone, a group, the anonymous principal and the system actor name grant rows or
    # principals that own nothing, so a row stamped with one would be owned by no one real.
    assert owner_refusal(declared) is not None
    assert repr(declared) in (owner_refusal(declared) or "")
    assert owner_for(Authority.system(), declared=declared) is None


@pytest.mark.parametrize("declared", [None, "alice", "carol", "systems", "anonymous", "groups", "eng:group"])
def test_any_other_owner_is_admitted(declared: str | None) -> None:
    assert owner_refusal(declared) is None


# ---------------------------------------------------------------------------
# The caller a call runs as
# ---------------------------------------------------------------------------


def test_a_named_authority_is_the_caller_and_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    alice = Authority.of(ALICE)
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        assert caller_for(alice, Authority.system(), op="read") is alice
    assert caplog.records == []


def test_a_call_that_names_no_one_falls_back_to_the_default_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    system = Authority.system()
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        assert caller_for(None, system, op="write") is system
    [record] = caplog.records
    assert (record.name, record.levelno) == ("vfs.authority", logging.DEBUG)
    assert "write" in record.getMessage() and "system" in record.getMessage()


def test_the_fallback_record_names_the_actors_kind_and_never_its_name(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        caller_for(None, Authority.of(Principal("alice@example.com")), op="read")
    [record] = caplog.records
    assert "user" in record.getMessage() and "alice" not in record.getMessage()


def test_with_no_default_the_caller_is_anonymous_and_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        assert caller_for(None, None, op="read") == Authority.anonymous()
    assert caplog.records == []


def test_a_system_default_is_warned_of_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        warn_if_system_default(Authority.system())
    [record] = caplog.records
    assert (record.name, record.levelno) == ("vfs.authority", logging.WARNING)
    assert "default_authority" in record.getMessage()


@pytest.mark.parametrize("default", [None, Authority.of(ALICE), Authority.anonymous()], ids=["none", "alice", "anon"])
def test_any_other_default_warns_nothing(default: Authority | None, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="vfs"):
        warn_if_system_default(default)
    assert caplog.records == []
