# Give an AI Agent the File System

In this tutorial, you will give an AI agent a file system to work in. You will define one tool, hand it to an LLM, ask a question, and watch the AI agent find the answer by running commands.

It takes about ten minutes. The file system runs in memory in a Jupyter notebook. The LLM is Claude, called through the Anthropic API, so you need an API key, and the one request in this tutorial is billed to your account. Any LLM that supports tool calling works the same way.

## Before You Begin

You need Python 3.11 or later with `vfs-py` and `anthropic` installed, and you should have finished [Use the CLI](use-the-cli.md).

```bash
pip install vfs-py anthropic
```

Set your Anthropic API key in the `ANTHROPIC_API_KEY` environment variable before you start the notebook.

Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Create a File System with a Few Files

Open a new notebook and run this in the first cell. These are the same three files from [Use the CLI](use-the-cli.md).

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

This cell prints nothing.

## Step 2: Define the Tool

An AI agent works through tools. Define one tool that runs a command in the file system.

```python
from anthropic import beta_tool


@beta_tool
def cli(command: str) -> str:
    """Run a shell command in a virtual file system and return what it prints.

    The file system holds company documents. The shell supports ls, cat,
    grep, find, head, tail, wc, and pipes. It has no network access.

    Args:
        command: The command line to run, such as "ls /" or "grep -rn MFA /".
    """
    print(f"$ {command}")
    return str(fs.cli(command)) or "(no output)"
```

This cell prints nothing. **This one function is the whole connection between the AI agent and VFS.**

The LLM reads the description to learn what the tool does. When it wants to run a command, the function passes that command to `fs.cli` and returns the output as text. The `print` line is only there so that you can watch the AI agent work.

## Step 3: Ask a Question

Hand the tool to the LLM and ask a question that the files can answer.

```python
import anthropic

client = anthropic.Anthropic()

runner = client.beta.messages.tool_runner(
    model="claude-opus-5-5",
    max_tokens=16000,
    system="You answer questions about company documents. The documents are in a file system that you explore with the cli tool.",
    tools=[cli],
    messages=[{"role": "user", "content": "Do I need MFA to reset my password?"}],
)

answer = runner.until_done()

for block in answer.content:
    if block.type == "text":
        print(block.text)
```

The AI agent chooses its own commands and its own words, so your output will differ. It will look something like this.

```text
$ grep -rni "password" /
$ cat /policies/passwords.md
Yes. The password policy says that MFA is required to reset a password.
```

The lines that start with `$` are the commands the AI agent ran. The last line is its answer.

You never told the AI agent where the answer was. It searched the file system, found the right file, read it, and answered. **It had one tool, and it read only the files it chose to read.**

Those commands ran inside VFS. The AI agent cannot reach the shell, the disk, or the network of your machine through this tool.

## What You Did

You connected an LLM to a file system with one tool and let it work.

- **The tool is one function.** It takes a command, passes it to `fs.cli`, and returns the output.
- **The AI agent already knew the commands.** You did not teach it `grep` or `cat`, and you did not write a tool for each kind of search.
- **The AI agent decided what to read.** Nothing was loaded into its context ahead of time.

To give the AI agent more to work with, you add files. The tool does not change.

## Where to Go Next

- [Control Who Can Access Files](control-who-can-access-files.md) limits what each person, and each AI agent acting for them, can see and change.
- The [Overview](../overview.md) explains why VFS is designed around files and a CLI.
