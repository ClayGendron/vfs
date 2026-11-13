# Use the CLI

In this tutorial, you will work in a virtual file system with the CLI built into VFS. You will list, read, and search files, join commands with a pipe, and write a file, all with commands you already know from a terminal.

The CLI is the interface an AI agent uses to work in VFS. AI agents already know commands like `ls`, `cat`, and `grep`, so there is nothing new to teach them. Here, you will run those commands yourself. It takes about five minutes and runs entirely in memory in a Jupyter notebook.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Build Your First File System](build-your-first-file-system.md).

Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Create a File System with a Few Files

Open a new notebook and run this in the first cell.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()

files = {
    "/policies/mfa.md": "All logins require MFA.\nReport a lost device within 24 hours.\n",
    "/policies/passwords.md": "Passwords rotate every 90 days.\nMFA is required to reset a password.\n",
    "/runbooks/reset-mfa.md": "To reset MFA, open a ticket with the service desk.\n",
}

for path, content in files.items():
    fs.write(path=path, content=content, parents=True)
```

This cell prints nothing. It writes three short files into two directories. The `parents=True` argument creates the `/policies` and `/runbooks` directories along the way.

## Step 2: Run a Command

You run a command by passing it to `fs.cli` as a line of text. Start with `ls`.

```python
fs.cli("ls")
```

```text
policies
runbooks
```

Every command starts in the root directory, `/`, so `ls` listed the two directories there. Give `ls` a path to look inside one of them.

```python
fs.cli("ls /policies")
```

```text
mfa.md
passwords.md
```

The output is what a terminal would print, but these commands do not run in a terminal. **They run inside VFS**, and they never reach the shell or the disk of your machine.

## Step 3: Read a File

Read a file with `cat`.

```python
fs.cli("cat /policies/mfa.md")
```

```text
All logins require MFA.
Report a lost device within 24 hours.
```

## Step 4: Search Across Files

Search every file for the word `MFA` with `grep`.

```python
fs.cli("grep -rn MFA /")
```

```text
/policies/mfa.md:1:All logins require MFA.
/policies/passwords.md:2:MFA is required to reset a password.
/runbooks/reset-mfa.md:1:To reset MFA, open a ticket with the service desk.
```

The `-r` flag searches every file under the path, and `-n` adds line numbers. Each line of output is a path, a line number, and the line that matched.

## Step 5: Join Commands with a Pipe

A pipe sends the output of one command into the next. Search again, and keep only the first two matches with `head`.

```python
fs.cli("grep -rn MFA / | head -n 2")
```

```text
/policies/mfa.md:1:All logins require MFA.
/policies/passwords.md:2:MFA is required to reset a password.
```

Or count the matches with `wc`.

```python
fs.cli("grep -rn MFA / | wc -l")
```

```text
3
```

This is how an AI agent keeps its reading small. **It asks for only the part of the answer it needs**, even when the search matches thousands of lines.

## Step 6: Write a File

Write a new file with `echo` and a redirect.

```python
fs.cli("echo 'Lock your screen when you leave your desk.' > /policies/screens.md")
```

This cell prints nothing, the same as in a terminal. List the directory to see the new file.

```python
fs.cli("ls /policies")
```

```text
mfa.md
passwords.md
screens.md
```

## Step 7: See the API Behind a Command

The CLI is a layer over the Python API you used in the first tutorial. When it runs a command, it parses the line and makes the matching API calls for you. The `grep` from Step 4 is this call.

```python
fs.grep("MFA", paths=("/",))
```

```text
/policies/mfa.md:1:All logins require MFA.
/policies/passwords.md:2:MFA is required to reset a password.
/runbooks/reset-mfa.md:1:To reset MFA, open a ticket with the service desk.
```

The output is the same because it is the same search. A pipe is different. There is no single API call for `grep` into `head`, so the CLI ran `grep` and then passed its output to `head`.

**Every command goes through the API.** This matters later, because any access rule you set on a file system applies to the CLI too.

## What You Did

You worked in a virtual file system with five commands and two pieces of shell syntax.

- `ls` listed a directory.
- `cat` read a file.
- `grep` searched across files.
- `head` and `wc` trimmed and counted the output of another command through a pipe, `|`.
- `echo` wrote a file through a redirect, `>`.

Each one printed what a terminal would print, and each one ran inside VFS.

## Where to Go Next

- [Keep Your Files in a Database](keep-your-files-in-a-database.md) stores files so they outlast the notebook.
- [Give an AI Agent the File System](give-an-ai-agent-the-file-system.md) hands this CLI to an LLM as one tool.
