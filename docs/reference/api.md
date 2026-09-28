<!--
DIÁTAXIS TYPE: Reference (information-oriented)
THE RULE: Austere, neutral, complete. Describe the machinery; do not instruct
or explain. Structure MIRRORS the code. Accuracy is the whole job.
SOURCE TO MIGRATE FROM: docs/api.md
-->

# API reference

## Identity

`VirtualFileSystem(..., default_authority: Authority | None = None)`. The authority used for any call that passes none. When it is `None`, such calls run as `Authority.anonymous()`.

`VirtualFileSystem.session(authority: Authority) -> Session`. See [Session](session.md).

Every verb takes a keyword-only `authority: Authority | None = None`. An explicit value wins over the default. See [Authority and Principal](authority.md).

### Error kinds

| Kind | Value | Meaning |
|---|---|---|
| `unauthenticated` | `vfs.unauthenticated` | the target needs a named authority; hint: open a session with an authority, or configure a default |
| `permission_denied` | `vfs.permission_denied` | the authority may not perform the operation on the target |
| `read_only` | `vfs.read_only` | the target is read-only; distinct from authorization |

`vfs.UnauthenticatedError` is the exception class `exception_for_kind` maps to `unauthenticated`, raised by `raise_if_failed` on a result carrying that kind.
