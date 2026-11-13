# Build Your First File System

In this tutorial, you will create a virtual file system, write a file to it, and then list and read that file.

It takes about two minutes and runs entirely in memory in a Jupyter notebook, so there is nothing to set up. By the end, you will have a working file system and will have made your first calls to VFS.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed.

```bash
pip install vfs-py
```

This tutorial is written for a Jupyter notebook. Each Python block below is one cell, and the block after it shows what that cell prints.

## Step 1: Create a File System

Open a new notebook and run this in the first cell.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()
```

This cell prints nothing. `fs` is your file system, and everything in this tutorial is done through it.

A new `VirtualFileSystem` **stores its files in memory by default**, so there is nothing to configure. The files last as long as the notebook is running.

## Step 2: Write a File

Write your first file by giving it a path and its content.

```python
fs.write(path="/hello_world.py", content='print("Hello, world!")')
```

```text
write success: 1 file

  created /hello_world.py
```

Every call to VFS returns a result that says what happened. This one says the file was created.

The file now exists at the path `/hello_world.py`. A path always starts with `/`, the root of the file system. **The file is not on your disk.** It lives inside VFS.

## Step 3: List the Files

List the root directory to see your file.

```python
fs.ls("/")
```

```text
/hello_world.py
```

The listing shows the full path of each file in the directory.

## Step 4: Read the File

Read the file back by its path.

```python
fs.read("/hello_world.py")
```

```text
print("Hello, world!")
```

The content is exactly what you wrote in Step 2.

## What You Did

You created a virtual file system and made three calls to it.

- `fs.write` created a file at a path.
- `fs.ls` listed a directory.
- `fs.read` returned the content of a file.

**Every call takes a path and returns a result.** The rest of VFS follows that same shape.

## Where to Go Next

- [Use the CLI](use-the-cli.md) works in a file system with `ls`, `cat`, and `grep`, the way an AI agent does.
- [Keep Your Files in a Database](keep-your-files-in-a-database.md) stores files so they outlast the notebook.
- The [Overview](../overview.md) explains the ideas behind VFS.
