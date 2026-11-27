# Take VFS to Production

This guide shows what to change before a file system serves real users: where its files are kept, where VFS keeps its own records, and which database to choose. Read it before you deploy, because the default keeps everything in memory.

**VFS keeps two kinds of data: your files, and its own records.** A record is a row VFS keeps about calls. Sessions and jobs are kept as records. Sessions and jobs are designed and not yet built, but the place their records are kept is built, and this page says where it is.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Keep Your Files in a Database](../tutorials/keep-your-files-in-a-database.md). For Postgres, install the extra with `pip install "vfs-py[postgres]"`.

## Step 1: Know What the Default Keeps

A file system made with no storage keeps everything in memory.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()
```

Its files are in memory, and so are its records. **All of it ends when the process ends**, and no other process can see any of it. That is right for a first trial and for a test. It is not right for production.

## Step 2: Give the Root a Database

The storage you give the file system is its root. VFS keeps its records in the root's own database, beside the files.

```python
from vfs import PostgresStorage, VirtualFileSystem

fs = VirtualFileSystem(
    storage=PostgresStorage(
        url="postgresql+asyncpg://app@db/vfs",
        schema="vfs",
    ),
)
```

Now the files and the records are both in the `vfs` schema of that database, and every process that opens a file system on it sees them. VFS makes its own tables there the first time it needs them. Their names begin `vfs_kernel_`, `vfs_session` or `vfs_job`, and VFS never touches a table of yours.

On SQLite the records are in the same file as the files, so `vfs.db` is still the only file. A copy of it carries the records too.

## Step 3: Do Not Put a Database Beneath a Memory Root

A database mounted beneath a root in memory keeps its files, and not the records.

```python
from vfs import SQLiteStorage, VirtualFileSystem

fs = VirtualFileSystem()
fs.add_mount(SQLiteStorage(path="data.db"), "/data")
```

The files under `/data` outlive the process. The records do not, because the root is in memory and the records follow the root. VFS logs one warning under the logger `vfs.kernel_store` the first time it writes a record while such a mount is held. **To keep the records, make the root storage the database.**

## Step 4: Choose the Engine for the Load

SQLite is a good fit for a demo or a local application. A SQLite file has one writer at a time, and VFS's records share that writer with your files. While a large batch of files is being written, a record waits for the batch to end. A record that waits longer than about 20 seconds is not written, and VFS warns that it was not.

Choose Postgres for a system with long batches or many writers at once. On Postgres, VFS keeps its records on a second pool of connections of the same size as your storage's, so a batch of files does not make a record wait.

## Step 5: Grant a Serving Role on Postgres

VFS makes its tables at first use, so the role it connects as needs `CREATE` on the schema once. If your serving role may not create tables, connect once as a role that may, so the tables are made, then grant the serving role these rights on each table whose name begins `vfs_kernel_`, `vfs_session` or `vfs_job`:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
  ON vfs.vfs_kernel_meta TO app;
```

Until both are done, VFS refuses its records to the serving role, and the refusal names the grant and each table.

## What You Did

- **You gave the root a database.** VFS keeps its records in the root's own database, and a root in memory keeps them in memory.
- **You kept the records with the files.** A database mounted beneath a memory root keeps only its files, and VFS warns once when that is the shape.
- **You chose the engine for the load.** SQLite for a local application, Postgres for long batches and many writers.
