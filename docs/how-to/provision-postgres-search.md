<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Assume competence. Steps to a goal. No "why" — link to Explanation.
SOURCE TO MIGRATE FROM: docs/index.md "Backends" SQL provisioning blocks
-->

# How to provision Postgres search artifacts

## Install pgvector once

vfs proves the extension at first touch and never creates it. On your
own server, run this once as a superuser or the database owner, in the
database that will hold the mount:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

On a managed server (RDS, Cloud SQL, Azure) use the provider's
extension allow-list, then the same statement. Until the extension is
present, every verb on the mount refuses `unavailable` and names this
step. The test cluster in `docker/compose.test.yml` installs it from
`docker/initdb/postgres/` at first start.

To do the same from code, when the connected role may create
extensions, call the developer-plane verb once; it installs, proves the
function, and is idempotent:

```python
result = await storage.install_extensions()
```

A role that may not install gets `permission_denied` naming the step
above. First touch itself never installs anything.
