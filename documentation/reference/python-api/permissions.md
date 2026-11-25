# Permissions

A `PermissionMap` is a default permission with overrides by directory, and `PermissionsPayload` is its JSON form. The `permissions` module enforces them.

```python
from vfs import PermissionMap, PermissionsPayload, permissions
```

::: vfs.PermissionMap

::: vfs.PermissionsPayload

::: vfs.permissions

## Access Levels

A `Rung` is one level of access. A `GrantLevel` is the level a grant gives one person or group, and a `Posture` is the level a mount gives everyone. [Access Levels](../access-levels.md) says what each level allows.

```python
from vfs import GrantLevel, Posture, Rung
```

::: vfs.Rung

::: vfs.GrantLevel

::: vfs.Posture
