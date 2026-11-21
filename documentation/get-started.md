# Get Started

This page takes you from nothing to a working file system in about a minute, and then shows where to go next.

## Install VFS

You need Python 3.11 or later.

```bash
pip install vfs-py
```

That is all you need for this page. It keeps files in memory or in SQLite.

To keep files in a database server, add the driver for it instead.

| Database | Install |
|---|---|
| PostgreSQL | `pip install "vfs-py[postgres]"` |
| SQL Server | `pip install "vfs-py[mssql]"` |
| Oracle | `pip install "vfs-py[oracle]"` |

SQL Server also needs Microsoft's ODBC Driver 18 installed on the machine.

## Create a File System and Use It

Run this in a Python script, a Python prompt, or a Jupyter notebook.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()

fs.write(
    path="/notes/hello.md",
    content="Hello from VFS.",
    parents=True,
)

print(fs.read("/notes/hello.md"))
```

```text
Hello from VFS.
```

That is a working file system. Three things just happened.

- **You created a file system with nothing to set up.** A new `VirtualFileSystem` keeps its files in memory, so there is no server and no configuration.
- **You wrote a file at a path.** The file is not on your disk. It lives inside VFS, at `/notes/hello.md`.
- **You read it back by the same path.** Every call to VFS takes a path and returns a result that says what happened.

## Where to Go Next

Choose by what you want to do.

- **Learn VFS step by step.** The tutorials build on each other, and each takes a few minutes. Start with [Build Your First File System](tutorials/build-your-first-file-system.md), then [Use the CLI](tutorials/use-the-cli.md), [Keep Your Files in a Database](tutorials/keep-your-files-in-a-database.md), [Give an AI Agent the File System](tutorials/give-an-ai-agent-the-file-system.md), and [Control Who Can Access Files](tutorials/control-who-can-access-files.md).
- **Bring your own files.** [Load a Folder of Files](how-to/load-a-folder-of-files.md) copies a repository or a folder of documents into VFS with one call.
- **Look something up.** [Access Levels](reference/access-levels.md) lists what each level of access allows.
- **Understand the design.** The [Overview](overview.md) explains how to think about VFS, and [Why VFS Stores Files in a Database](explanation/why-vfs-stores-files-in-a-database.md) explains its most surprising choice.
