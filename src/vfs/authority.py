"""Authority — who a call acts for, who does the work, and how it was proven.

Identity reaches the router as one value, an :class:`Authority`: the
non-empty set of **subjects** whose grants apply, the **actor** doing the
work, the **narrowing** the session has given up, and the **provenance**
of the proof. A person at a keyboard is a subject acting as itself; an
agent in a group chat is a set of subjects with the agent as actor; a
batch job is the system actor with no subject at all; a call that names
nobody runs as the anonymous principal, which holds only what a mount
gives everyone.

    me = Principal("alice")
    Authority.of(me)                                   # alice, as herself
    Authority.on_behalf_of({me, Principal("bob")}, actor=Principal("bot", kind="service"))
    Authority.system()                                 # the marked exception
    Authority.anonymous()                              # nobody in particular, by name

Four construction doors exist — the classmethods above — plus the edge
factory that turns a verified token into an authority. Nothing else in
``src/`` builds one, and the invariants below are checked at
construction: a violation is a ``ValueError`` because it can only come
from vfs's own code, never from a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Literal

# ---------------------------------------------------------------------------
# Module constants and shared types
# ---------------------------------------------------------------------------

PrincipalKind = Literal["user", "service", "system", "anonymous"]
"""``user`` is a person; ``service`` an agent deployed as its own identity;
``system`` the actor of :meth:`Authority.system` and nothing else;
``anonymous`` the named nobody of :meth:`Authority.anonymous`."""

Provenance = Literal["edge", "constructed", "system"]
"""How the authority was proven: verified at the transport edge,
constructed in process by trusted code, or the system actor itself."""

SYSTEM_NAME: Final = "system"
"""The reserved subject name of the system principal; no other principal
may carry it, so the name can never collide in an ``owner_id`` column."""

ANONYMOUS_NAME: Final = "anon"
"""The reserved subject name of the anonymous principal, reserved the
same way: nobody in particular still has a name in the audit."""

_RESERVED_NAMES: Final[dict[str, PrincipalKind]] = {SYSTEM_NAME: "system", ANONYMOUS_NAME: "anonymous"}

MAX_SUBJECTS: Final = 64
"""The declared bound on a subject set. An oversize set is refused at the
edge with a classified error; the type's own check is narrowing only."""


class Narrowing(Enum):
    """What a session has given up. Opaque here: the only value is *nothing*."""

    NONE = "none"


# ---------------------------------------------------------------------------
# The principal
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Principal:
    """One verified identity: its name (the token's ``sub``), kind, and scopes.

    ``sub`` is stored unchanged wherever a principal is named (``owner_id``,
    a grant row, a version's subject list), so token-to-row is transparent.
    """

    sub: str
    kind: PrincipalKind = "user"
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.sub or not self.sub.strip():
            msg = "a principal needs a non-empty sub"
            raise ValueError(msg)
        if _RESERVED_NAMES.get(self.sub) != self.kind and (
            self.sub in _RESERVED_NAMES or self.kind in _RESERVED_NAMES.values()
        ):
            msg = f"the names {sorted(_RESERVED_NAMES)} are reserved for their own principal kinds, which take no other"
            raise ValueError(msg)

    @property
    def is_system(self) -> bool:
        return self.kind == "system"

    @property
    def is_anonymous(self) -> bool:
        return self.kind == "anonymous"


# ---------------------------------------------------------------------------
# The authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Authority:
    """The subjects, the actor, the narrowing, and how the proof was made.

    Frozen and hashable: an authority is a value the funnel carries, never
    a session that caches a decision. Rights are re-derived from it on
    every call.
    """

    subjects: frozenset[Principal]
    actor: Principal
    provenance: Provenance
    narrowing: Narrowing = Narrowing.NONE
    source_identity: str | None = None

    def __post_init__(self) -> None:
        if any(p.is_system for p in self.subjects):
            msg = "the system principal is never a subject"
            raise ValueError(msg)
        if not self.subjects and not self.actor.is_system:
            msg = "a subject set is non-empty unless the actor is the system principal"
            raise ValueError(msg)
        if self.actor.is_system and self.subjects:
            msg = "the system actor acts for no subject"
            raise ValueError(msg)
        if len(self.subjects) > MAX_SUBJECTS:
            msg = f"a subject set holds at most {MAX_SUBJECTS} principals, got {len(self.subjects)}"
            raise ValueError(msg)
        if (self.provenance == "system") != self.actor.is_system:
            msg = "the system provenance belongs to the system actor and to nothing else"
            raise ValueError(msg)
        anonymous = self.actor.is_anonymous or any(p.is_anonymous for p in self.subjects)
        if anonymous and (self.subjects != {self.actor} or not self.actor.is_anonymous):
            msg = "the anonymous principal is only ever the sole subject and the actor of Authority.anonymous()"
            raise ValueError(msg)

    @classmethod
    def of(cls, principal: Principal, *, source_identity: str | None = None) -> Authority:
        """*principal* acting as itself — the common case."""
        return cls(
            subjects=frozenset({principal}),
            actor=principal,
            provenance="constructed",
            source_identity=source_identity,
        )

    @classmethod
    def on_behalf_of(
        cls,
        subjects: frozenset[Principal] | set[Principal],
        *,
        actor: Principal,
        source_identity: str | None = None,
    ) -> Authority:
        """*actor* working for every principal in *subjects* at once."""
        return cls(
            subjects=frozenset(subjects),
            actor=actor,
            provenance="constructed",
            source_identity=source_identity,
        )

    @classmethod
    def system(cls) -> Authority:
        """The marked exception: the system actor, no subject, no proof needed."""
        return cls(subjects=frozenset(), actor=Principal(SYSTEM_NAME, kind="system"), provenance="system")

    @classmethod
    def anonymous(cls) -> Authority:
        """Nobody in particular, by name: holds only what a mount gives everyone."""
        nobody = Principal(ANONYMOUS_NAME, kind="anonymous")
        return cls(subjects=frozenset({nobody}), actor=nobody, provenance="constructed")

    @property
    def is_system(self) -> bool:
        return self.actor.is_system

    @property
    def is_anonymous(self) -> bool:
        return self.actor.is_anonymous

    @property
    def subject_names(self) -> tuple[str, ...]:
        """Every subject's ``sub``, sorted — the shape attribution rows store."""
        return tuple(sorted(p.sub for p in self.subjects))

    @property
    def owner_subject(self) -> str | None:
        """The one subject that owns rows this authority creates, or ``None``.

        A single subject owns what it makes. A set owns nothing: the row's
        container governs it, so ``None``. The system actor owns nothing,
        and so does anonymous — else every anonymous caller would own
        every anonymous row.
        """
        if len(self.subjects) != 1 or self.is_anonymous:
            return None
        (only,) = self.subjects
        return only.sub


def owner_for(authority: Authority | None, declared: str | None = None) -> str | None:
    """The ``owner_id`` a new row takes under *authority*.

    Caller identity is not row ownership: an app-path authority derives
    the owner from its subjects, while the system actor stamps whatever
    the write payload *declared*. No authority stamps nothing.
    """
    if authority is None:
        return None
    if authority.is_system:
        return declared
    return authority.owner_subject
