# Keep Your Files in a Database

In this tutorial, you will create a file system that stores its files in a database. You will write a file, close the file system, open it again, and find the file still there.

The file system in the first tutorial lived in memory, so its files were gone when the notebook stopped. This one keeps them. It takes about three minutes. The database is a single SQLite file named `vfs.db`, created in the folder where your notebook runs, so there is still no server to set up. The last step deletes it.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Build Your First File System](build-your-first-file-system.md).

Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Create a File System on a Database

Open a new notebook and run this in the first cell.

```python
from vfs import DatabaseStorage, VirtualFileSystem

fs = VirtualFileSystem(storage=DatabaseStorage(url="sqlite+aiosqlite:///vfs.db"))
```

This cell prints nothing. The `storage` argument tells the file system where to keep its files, and the URL names the database. Here, `sqlite+aiosqlite` is the kind of database and its driver, which is installed with `vfs-py`, and `vfs.db` is the file the database lives in.

## Step 2: Write a File

Write a file exactly as you did in the first tutorial.

```python
fs.write(path="/hello_world.py", content='print("Hello, world!")')
```

```text
write success: 1 file

  created /hello_world.py
```

Nothing about the call changed. **Where the files are stored is decided once, when the file system is created.** Every call after that is the same.

## Step 3: Find the Database on Disk

Check that the database file now exists.

```python
from pathlib import Path

Path("vfs.db").exists()
```

```text
True
```

VFS created `vfs.db` when you wrote the file. **Your file is a row in that database.** There is no `hello_world.py` on your disk, only `vfs.db`.

## Step 4: Close and Reopen the File System

Close the file system.

```python
fs.close()
```

This cell prints nothing. The file system is gone from memory, as if your application had stopped. Now create it again on the same database and read the file.

```python
fs = VirtualFileSystem(storage=DatabaseStorage(url="sqlite+aiosqlite:///vfs.db"))

fs.read("/hello_world.py")
```

```text
print("Hello, world!")
```

The file survived, because it was never only in memory. It will still be there if you restart the notebook.

## Step 5: Clean Up

When you are done, close the file system and delete the database.

```python
fs.close()

Path("vfs.db").unlink()
```

This cell prints nothing. Close the file system first, so the database is no longer in use when you delete it. Once it is closed, `vfs.db` is the only file there is to remove.

## What You Did

You gave a file system a database, wrote a file, and read it back after closing and reopening the file system.

- **One argument made the files last.** `storage=DatabaseStorage(url=...)` is the only line that differs from the first tutorial.
- **The files live in the database.** VFS stores each file as a row and never writes it to your disk as a file.

SQLite is a good fit for a laptop. VFS also runs on Postgres, SQL Server, and Oracle, where the URL names that database instead.

## Where to Go Next

- [Give an AI Agent the File System](give-an-ai-agent-the-file-system.md) hands the CLI to an LLM as one tool.
- [Control Who Can Access Files](control-who-can-access-files.md) gives two people different access to one file system.
