# Add a Tool an Agent Can Run

This guide shows how to turn a Python function into a program an agent can run from a shell line, and how that program can stop to ask a person a question. Use it when an agent needs to do something your application already knows how to do, such as translate a document or publish a page.

**A tool is a function you write. An agent runs it by name, like `grep` or `cat`.** It can take its input from a pipe and pass its output to the next program. If you already have LangChain tools, you can add them as they are.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Interrupt a Call and Ask a Person](interrupt-a-call-and-ask-a-person.md).

The examples use a file system in memory, an agent named Scout and a person named Ada.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem()
system = Authority.system()
ada = Authority.of(Principal("ada"))
scout = fs.open_session(Authority.of(Principal("scout")))

fs.write(
    path="/reports/q3.md",
    content="Revenue grew in the third quarter.\n",
    parents=True,
    authority=system,
)
```

```text
write success: 1 file

  created /reports/q3.md
```

## Step 1: Write a Tool

Put `@fs.tool` on a function. Its name becomes the program's name, its first line of documentation becomes its help text, and its parameters become its arguments.

```python
from vfs import Session

@fs.tool
def shout(path: str, times: int = 1, *, files: Session) -> str:
    """Print a file in capital letters."""
    text = files.read(path).content
    return text.upper() * times
```

The parameter typed `Session` is not an argument the agent supplies. VFS fills it in with a session for whoever runs the tool. **Read and write files through that session, and the tool can touch only what its caller can.** A tool run by Scout sees the files Scout sees.

A tool can be an `async` function. Type the parameter as `AsyncSession` and await its calls.

## Step 2: Run the Tool from a Shell Line

Scout runs the tool by its name.

```python
scout.cli("shout /reports/q3.md")
```

```text
REVENUE GREW IN THE THIRD QUARTER.
```

The parameters became the command line. A parameter with no default is given by position. A parameter with a default is a flag.

```python
scout.cli("shout /reports/q3.md --times 2 | wc -l")
```

```text
2
```

The tool's return value is its output, so it works in a pipe like any other program. The rules that turn parameters into a command line are the same for every tool.

| Parameter | On the command line |
|---|---|
| A value with no default | Given by position, or as `--name value` |
| A value with a default | `--name value` |
| `True` or `False` | `--name` or `--no-name` |
| A list | `--name a --name b`, or the remaining positions when it is the last parameter with no default |
| Anything nested | `--name '<json>'` |
| All of them at once | `--json '<json>'` |

An agent does not have to guess. Every tool answers `--help`.

```python
scout.cli("shout --help")
```

```text
shout: Print a file in capital letters.

usage: shout PATH [--times N]

  PATH       (text, required)
  --times N  (whole number, default 1)
```

A tool that raises `ToolError` fails as a program does: its message goes to standard error and its exit status is 1. A wrong argument is exit status 2, and the function is never called.

## Step 3: Add a LangChain Tool

A LangChain tool is added as it is.

```python
from langchain_core.tools import tool

@tool
def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())

fs.add_tool(word_count)
```

It is now a program too. Its one required parameter takes what is piped in.

```python
scout.cli("cat /reports/q3.md | word_count")
```

```text
6
```

A LangChain tool can read and write files as its caller in the same way. Mark a parameter as injected, and VFS supplies the session.

```python
from typing import Annotated

from langchain_core.tools import InjectedToolArg

@tool
def first_line(path: str, files: Annotated[Session, InjectedToolArg]) -> str:
    """Return the first line of a file."""
    return files.read(path).content.splitlines()[0]

fs.add_tool(first_line)
```

A tool's name must be free. Adding a tool whose name is a shell builtin, such as `echo`, or a program VFS ships, such as `grep`, is refused when you add it, so an agent never runs something other than what the name says.

## Step 4: Ask a Person Before a Tool Runs

Some tools act outside VFS. This one publishes a report to a website.

```python
@fs.tool(approve=True)
def publish(path: str, *, files: Session) -> str:
    """Publish a report to the company website."""
    post_to_website(files.read(path).content)
    return f"published {path}"
```

Here `post_to_website` stands for your own code. With `approve=True`, every run of the tool is interrupted before the function is called.

```python
result = scout.cli("publish /reports/q3.md")
result
```

```text
INTERRUPTED publish: Interrupted (interrupt 4e8a1d77, run 91c3f0b2) — publish /reports/q3.md needs a person. Answer the interrupt, then resume the run. (retry: resume)
```

Answer it and resume the run, as you would for a change to a file.

```python
stopped = result.interrupts[0]

fs.answer(stopped.id, allow=True, authority=ada)
scout.resume(stopped.run_id)
```

```text
published /reports/q3.md
```

**The function ran once, after Ada said yes.** This is the right choice for any tool that does something VFS cannot undo. VFS can show a preview of a change to a file, and it can undo one. It cannot do either for what a tool does elsewhere.

## Step 5: Ask a Question from Inside a Tool

A tool can also stop part-way to ask for something only a person knows. Call `interrupt` with the question, and it returns the answer.

```python
from vfs import interrupt

@fs.tool
def translate(path: str, *, files: Session) -> str:
    """Translate a report into another language."""
    text = files.read(path).content
    language = interrupt({"question": f"Translate {path} into which language?"})
    target = f"{path}.{language}.md"
    files.write(path=target, content=translate_text(text, language))
    return target
```

Here `translate_text` stands for your own code. The first time the tool runs, `interrupt` stops it.

```python
result = scout.cli("translate /reports/q3.md")
stopped = result.interrupts[0]

stopped.payload
```

```text
{'question': 'Translate /reports/q3.md into which language?'}
```

This interrupt asks for a value, not a yes or a no. Give the value when you answer.

```python
fs.answer(stopped.id, value="french", authority=ada)
scout.resume(stopped.run_id)
```

```text
/reports/q3.md.french.md
```

There is one rule to know. **When the run resumes, the tool's function starts again from its first line.** This time `interrupt` returns the answer and the function carries on. A tool that asks two questions is started three times, and each call to `interrupt` returns its own answer, in order.

VFS makes that safe for everything the tool does through its session. A file the tool read is not read again, and a file the tool wrote is not written again: VFS gives the tool back what it got the first time. What VFS cannot see, it cannot protect. Code that acts outside VFS, placed before a call to `interrupt`, runs again each time.

So follow one habit. **Ask first, then act.** Put every call to `interrupt` before anything the tool does outside VFS, as `translate` does. If a tool must act before it can ask, use `approve=True` from Step 4, which never starts the function twice.

A LangChain tool that calls LangGraph's own `interrupt()` works the same way, with no change to the tool. Install `vfs-py[langchain]` to use it.

## What a Tool Can and Cannot Do

A tool is your code, and it runs inside your application with everything your application can reach. VFS controls three things about it.

- **Who may run it.** A tool is listed at `/.vfs/tools/<name>`, and access to that path decides who can see it and who can run it, as access decides for any file.
- **What it does to files.** Calls made through the session it is given run as the caller, under the caller's access and under your policy.
- **Who may answer it.** Only your application can call `answer`. An agent cannot answer its own tool's question.

VFS does not control what the function does on its own: a request to another service, a file on your disk, a database of yours. Treat a tool as you would any code you let an agent start.

## What to Remember

A function with `@fs.tool` is a program an agent can run. It reads and writes files as its caller. It can be made to wait for a person before it starts, or it can stop to ask a question and carry on with the answer.
