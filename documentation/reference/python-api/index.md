# Python API

Every name that `import vfs` makes public, grouped by what it is for. Each one links to the page that documents it.

## File Systems

- [`AsyncVirtualFileSystem`](async-virtual-file-system.md#vfs.AsyncVirtualFileSystem): the file system, with calls you `await`.
- [`VirtualFileSystem`](virtual-file-system.md#vfs.VirtualFileSystem): the same file system, with plain calls.

## Sessions

- [`AsyncSession`](sessions.md#vfs.AsyncSession): one caller and one file system, with calls you `await`.
- [`Session`](sessions.md#vfs.Session): the same, with plain calls.

## Entries and Paths

- [`Entry`](entry.md#vfs.Entry): the full record of one file or directory.
- [`Observation`](entry.md#vfs.Observation): what a call returns about one entry.
- [`Match`](entry.md#vfs.Match): one region of an entry that a search found.
- [`Edge`](entry.md#vfs.Edge): a typed link from one entry to another.
- [`ObjectKind`](entry.md#vfs.ObjectKind): what an entry is, a file or a directory.
- [`Source`](entry.md#vfs.Source): what an entry's body was written as, text or bytes.
- [`ContentHash`](entry.md#vfs.ContentHash): the SHA-256 of a body.
- [`Vid`](entry.md#vfs.Vid): the short value on a row that names one entry at one version.
- [`ABSENT`](entry.md#vfs.ABSENT): the mark, given where a vid is given, that requires nothing at the path.
- [`RenderStatus`](entry.md#vfs.RenderStatus): how the rendering of a binary body into text ended.
- [`Path`](path.md#vfs.Path): a path that has been checked and is safe to route.

## Operations

- [`Op`](operations.md#vfs.Op): the name of one operation.
- [`EditOperation`](operations.md#vfs.EditOperation): one change that `edit` makes.
- [`TwoPathOperation`](operations.md#vfs.TwoPathOperation): one pair of paths for `move` or `copy`.
- [`CaseMode`](operations.md#vfs.CaseMode): how `grep` treats letter case.
- [`GrepOutputMode`](operations.md#vfs.GrepOutputMode): what `grep` returns.

## Results

- [`Result`](results.md#vfs.Result): what every call returns.
- [`ResultError`](results.md#vfs.ResultError): one failure carried on a result.
- [`LineResult`](results.md#vfs.LineResult): what a line of the shell printed and exited with.
- [`ErrorKind`](results.md#vfs.ErrorKind): what went wrong.
- [`Severity`](results.md#vfs.Severity): how much to trust the rest of the result.
- [`RetryClass`](results.md#vfs.RetryClass): whether trying again can help.

## Identity

- [`Authority`](authority.md#vfs.Authority): who a call is made for, and how that was proven.
- [`Principal`](authority.md#vfs.Principal): one verified identity.
- [`PrincipalKind`](authority.md#vfs.PrincipalKind): what a principal is, such as a person or a service.
- [`Provenance`](authority.md#vfs.Provenance): how an authority was proven.
- [`Narrowing`](authority.md#vfs.Narrowing): what a session has given up.

## Permissions

- [`PermissionMap`](permissions.md#vfs.PermissionMap): a default permission with overrides by directory.
- [`PermissionsPayload`](permissions.md#vfs.PermissionsPayload): the JSON form of a `PermissionMap`.
- [`permissions`](permissions.md#vfs.permissions): the module that enforces permissions.
- [`Rung`](permissions.md#vfs.Rung): one level of access.
- [`GrantLevel`](permissions.md#vfs.GrantLevel): the level a grant gives one person or group.
- [`Posture`](permissions.md#vfs.Posture): the level a mount gives everyone.

## Mounts

- [`Mount`](mounts.md#vfs.Mount): one storage backend attached at one path.
- [`MountPayload`](mounts.md#vfs.MountPayload): the JSON form of a `Mount`.
- [`Location`](mounts.md#vfs.Location): the mount that holds a path.
- [`EdgeLocation`](mounts.md#vfs.EdgeLocation): the mounts that hold the two ends of an edge.

## Storage

- [`SQLiteStorage`](storage.md#vfs.SQLiteStorage): a storage backend in SQLite, for a demo or a local application.
- [`PostgresStorage`](storage.md#vfs.PostgresStorage): a storage backend in Postgres, for a shared deployment.
- [`InMemoryStorage`](storage.md#vfs.InMemoryStorage): a storage backend in a private in-memory database.
- [`DatabaseStorage`](storage.md#vfs.DatabaseStorage): the storage backend the others are built on, which serves any SQLAlchemy URL.
- [`StorageBackend`](storage.md#vfs.StorageBackend): what every storage backend has.
- [`ResolvedPair`](storage.md#vfs.ResolvedPair): the two checked paths a backend gets for a move or a copy.
- [`ScopeChannel`](storage.md#vfs.ScopeChannel): the scope of a search, as a backend gets it.
- [`RecordPlace`](storage.md#vfs.RecordPlace): the database a root storage names for the file system's records.

## Search

- [`ranking`](ranking.md#vfs.ranking): the module that says how a storage backend ranks.
- [`rerank`](ranking.md#vfs.rerank): the module that reorders the results of several mounts.
- [`embedding`](embedding.md#vfs.embedding): the module of embedding providers.

## Rendering

- [`rendering`](rendering.md#vfs.rendering): the module that renders files that are not text.

## Errors

- [`VFSError`](errors.md#vfs.VFSError): the base class of every error VFS raises.
- [`MountError`](errors.md#vfs.MountError): adding or removing a mount failed.
- [`NotFoundError`](errors.md#vfs.NotFoundError): a path does not exist or is not the expected kind.
- [`UnauthenticatedError`](errors.md#vfs.UnauthenticatedError): the caller has not said who it is.
- [`ValidationError`](errors.md#vfs.ValidationError): an argument, a pattern or the configuration is invalid.
- [`WriteConflictError`](errors.md#vfs.WriteConflictError): a write was rejected.
