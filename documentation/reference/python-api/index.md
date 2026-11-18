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
- [`Path`](path.md#vfs.Path): a path that has been checked and is safe to route.

## Results

- [`Result`](results.md#vfs.Result): what every call returns.
- [`ResultError`](results.md#vfs.ResultError): one failure carried on a result.

## Identity

- [`Authority`](authority.md#vfs.Authority): who a call is made for, and how that was proven.
- [`Principal`](authority.md#vfs.Principal): one verified identity.

## Permissions

- [`PermissionMap`](permissions.md#vfs.PermissionMap): a default permission with overrides by directory.
- [`PermissionsPayload`](permissions.md#vfs.PermissionsPayload): the JSON form of a `PermissionMap`.
- [`permissions`](permissions.md#vfs.permissions): the module that enforces permissions.

## Mounts

- [`Mount`](mounts.md#vfs.Mount): one storage backend attached at one path.
- [`MountPayload`](mounts.md#vfs.MountPayload): the JSON form of a `Mount`.

## Storage

- [`DatabaseStorage`](storage.md#vfs.DatabaseStorage): a storage backend in a SQL database.
- [`InMemoryStorage`](storage.md#vfs.InMemoryStorage): a storage backend in a private in-memory database.

## Errors

- [`VFSError`](errors.md#vfs.VFSError): the base class of every error VFS raises.
- [`MountError`](errors.md#vfs.MountError): adding or removing a mount failed.
- [`NotFoundError`](errors.md#vfs.NotFoundError): a path does not exist or is not the expected kind.
- [`UnauthenticatedError`](errors.md#vfs.UnauthenticatedError): the caller has not said who it is.
- [`ValidationError`](errors.md#vfs.ValidationError): an argument, a pattern or the configuration is invalid.
- [`WriteConflictError`](errors.md#vfs.WriteConflictError): a write was rejected.
