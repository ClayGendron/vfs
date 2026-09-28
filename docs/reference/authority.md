<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Structure MIRRORS the code. Accuracy is the whole job.
-->

# Authority and Principal

Module `vfs.authority`. Both types are re-exported from `vfs`.

```python
from vfs import Authority, Principal
```

## Constants

| Name | Value | Meaning |
|---|---|---|
| `SYSTEM_NAME` | `"system"` | reserved `sub` of the system principal |
| `ANONYMOUS_NAME` | `"anon"` | reserved `sub` of the anonymous principal |
| `MAX_SUBJECTS` | `64` | upper bound on a subject set |

## Types

`PrincipalKind` is `Literal["user", "service", "system", "anonymous"]`.

`Provenance` is `Literal["edge", "constructed", "system"]`.

`Narrowing` is an `Enum` with one member, `Narrowing.NONE`.

## `Principal`

A frozen, hashable dataclass.

| Field | Type | Default |
|---|---|---|
| `sub` | `str` | required |
| `kind` | `PrincipalKind` | `"user"` |
| `scopes` | `frozenset[str]` | empty |

Properties: `is_system` (kind is `system`), `is_anonymous` (kind is `anonymous`).

Construction raises `ValueError` when:

| Condition | Message |
|---|---|
| `sub` is empty or whitespace | `a principal needs a non-empty sub` |
| `sub` is a reserved name with any other kind, or the kind is `system` or `anonymous` with any other `sub` | `the names ['anon', 'system'] are reserved for their own principal kinds, which take no other` |

## `Authority`

A frozen, hashable dataclass. Equality and hashing are by value; subject order does not matter.

| Field | Type | Default |
|---|---|---|
| `subjects` | `frozenset[Principal]` | required |
| `actor` | `Principal` | required |
| `provenance` | `Provenance` | required |
| `narrowing` | `Narrowing` | `Narrowing.NONE` |
| `source_identity` | `str \| None` | `None` |

### Doors

| Door | Signature | Result |
|---|---|---|
| `Authority.of` | `(principal, *, source_identity=None)` | subjects `{principal}`, actor `principal`, provenance `constructed` |
| `Authority.on_behalf_of` | `(subjects, *, actor, source_identity=None)` | subjects `frozenset(subjects)`, actor `actor`, provenance `constructed` |
| `Authority.system` | `()` | subjects empty, actor `Principal("system", kind="system")`, provenance `system` |
| `Authority.anonymous` | `()` | subjects `{anon}`, actor `anon`, provenance `constructed`, where `anon` is `Principal("anon", kind="anonymous")` |

### Rules

Checked at every construction. Each raises `ValueError`.

| Rule | Message |
|---|---|
| no subject has kind `system` | `the system principal is never a subject` |
| subjects non-empty unless the actor is system | `a subject set is non-empty unless the actor is the system principal` |
| a system actor has no subjects | `the system actor acts for no subject` |
| at most `MAX_SUBJECTS` subjects | `a subject set holds at most 64 principals, got N` |
| provenance is `system` if and only if the actor is system | `the system provenance belongs to the system actor and to nothing else` |
| an anonymous principal appears only as the sole subject and the actor | `the anonymous principal is only ever the sole subject and the actor of Authority.anonymous()` |

### Properties

| Property | Type | Value |
|---|---|---|
| `is_system` | `bool` | the actor's kind is `system` |
| `is_anonymous` | `bool` | the actor's kind is `anonymous` |
| `subject_names` | `tuple[str, ...]` | every subject's `sub`, sorted |
| `owner_subject` | `str \| None` | the sole subject's `sub` when there is exactly one subject and the authority is not anonymous; otherwise `None` |

## `owner_for`

<!-- skip: next -->
```python
owner_for(authority: Authority | None, declared: str | None = None) -> str | None
```

The `owner_id` a new row takes.

| `authority` | Returns |
|---|---|
| `None` | `None` |
| system actor | `declared` |
| one subject, not anonymous | that subject's `sub`; `declared` is ignored |
| a set of two or more | `None` |
| anonymous | `None` |

## Where the value is consumed

Every verb on `VirtualFileSystem` and every method on the storage protocol accepts `authority: Authority | None`. The router fills a `None` before dispatch: the call's own value, else the filesystem's `default_authority`, else `Authority.anonymous()`. A value of any other type is refused with the error kind `vfs.invalid` and the message `<op> authority must be an Authority, got <type>`.

Mount administration (`add_mount`, `remove_mount`, `locate`, and the bind-site probes) runs as `Authority.system()` regardless of the caller or the default.

## Version attribution

`vfs.models.Version` carries `actor: str | None`, `subjects: tuple[str, ...]`, `provenance: Provenance | None`, and `source_identity: str | None`. `Version.create` fills all four from an authority. In the schema (format version 13) the versions table holds the columns `actor`, `provenance`, and `source_identity`; the `version_subjects` table holds one row per `(entry_id, version_number, principal_id)`. No verb writes version rows in the current release.
