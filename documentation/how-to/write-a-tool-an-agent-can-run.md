# Write a Tool an Agent Can Run

This guide shows how to write a tool, which is a Python function an agent runs by name from a shell line, the way it runs `grep`. It then shows how a tool can stop the line to ask a person a question, and carry on with the answer. Use it when an agent needs something your application knows how to do, or needs an answer only a person can give.

**A tool is a program.** It lives beside the programs VFS ships, an agent finds it the same way, and it takes its input from a pipe and passes its output to the next program like any other.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, and you should have finished [Interrupt a Call and Ask a Person](interrupt-a-call-and-ask-a-person.md). This guide uses the two calls that guide teaches, `answer` and `resume`.

Each Python block below is one notebook cell, and the block after it shows what that cell prints.

## Step 1: Write a Tool

Put `@tool` on a function. The function's name is the program's name, the first line of its documentation is its description, and its parameters are its arguments.

```python
from vfs import tool

@tool
def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())
```

Create a file system with the tool, add two reports, and open a session for an agent named Scout.

```python
from vfs import Authority, Principal, VirtualFileSystem

fs = VirtualFileSystem(tools=[word_count])
system = Authority.system()
scout = fs.open_session(Authority.of(Principal("scout")))

fs.write(
    path="/reports/q2.md",
    content="# Second Quarter Report\n\nRevenue was flat.\n",
    parents=True,
    authority=system,
)
fs.write(
    path="/reports/q3.md",
    content="# Third Quarter Report\n\nRevenue grew.\n",
    parents=True,
    authority=system,
)
```

```text
write success: 1 file

  created /reports/q3.md
```

You can also add a tool to a file system that already exists, with `fs.add_tool(word_count)`.

## Step 2: Find the Tool

Every program an agent can run by name is in one folder, `/.vfs/bin`. List it.

```python
scout.cli("ls /.vfs/bin")
```

```text
cat
cp
cut
find
grep
head
ls
mkdir
mv
rm
sed
sort
tail
tee
touch
tr
uniq
wc
word_count
```

Your tool is in the list with the programs VFS ships. The shell finds a program by looking in the folders named by `PATH`, as any shell does, and `PATH` starts as this one folder.

```python
scout.cli("echo $PATH; type word_count")
```

```text
/.vfs/bin
word_count is /.vfs/bin/word_count
```

Each entry in the folder is a file, and reading it shows how to use the program. **Reading a tool never runs it.**

```python
scout.cli("cat /.vfs/bin/word_count")
```

```text
word_count: Count the words in a piece of text.

usage: word_count TEXT

  TEXT  text, required; read from standard input when it is not given

A tool: it runs inside the application that hosts this file system.
```

An agent that has never seen your tool can find it with `ls` and learn it with `cat`, and `word_count --help` prints the same text.

VFS serves this folder itself. Nothing in it is stored, so it always describes the tools your application has now, and nobody can write to it.

## Step 3: Run the Tool

Scout runs the tool by its name.

```python
scout.cli('word_count "the quick brown fox"')
```

```text
4
```

What the function returns is the program's output, so it works in a pipe.

```python
scout.cli("cat /reports/q3.md | word_count")
```

```text
6
```

Here nothing was given for `text`, so the tool read it from the pipe. The function's parameters become the command line by the same rules for every tool.

| Parameter | On the command line |
|---|---|
| A value with no default | Given by position, or as `--name value` |
| A value with a default | `--name value` |
| `True` or `False` | `--name` or `--no-name` |
| A list | `--name a --name b` |
| Anything nested | `--name '<json>'` |

A tool also ends as a program does. It ends with status 0 when the function returns. To fail on purpose, raise `ToolError` with a message: the message goes to standard error and the status is 1. A wrong argument is status 2, and your function is not called.

## Step 4: Read and Write Files as the Caller

A tool that works with files takes a parameter typed `Session`. The agent does not supply it. VFS fills it in with a session for whoever is running the tool.

```python
from vfs import Session

@tool
def title(path: str, *, files: Session) -> str:
    """Print the title of a report."""
    first_line = files.read(path).one().content.splitlines()[0]
    return first_line.removeprefix("# ")

fs.add_tool(title)
scout.cli("title /reports/q3.md")
```

```text
Third Quarter Report
```

**Through that session, a tool can reach only what its caller can.** When Scout runs `title`, the read is Scout's read: it is checked against Scout's access and against your policy, like any call Scout makes. A tool cannot be used to read a file its caller may not read.

A tool can be an `async` function. Type the parameter as `AsyncSession` and await its calls.

## Step 5: Ask a Person a Question

An agent often needs something only a person knows. Write a tool that asks.

```python
from vfs import interrupt

@tool
def ask_user(question: str, option: list[str] | None = None) -> str:
    """Ask the person a question and print their answer."""
    return interrupt(question, options=option)

fs.add_tool(ask_user)
```

`interrupt` stops the tool, and the shell line with it, until a person has answered. It then returns the answer. This tool returns the answer straight away, so the answer becomes the program's output.

Scout uses it in a line. The line asks which report to open and then prints that report's title.

```python
line = (
    'quarter=$(ask_user "Which quarter should I open?" --option q2 --option q3); '
    "title /reports/$quarter.md"
)
result = scout.cli(line)
result
```

```text
INTERRUPTED ask_user: Interrupted (interrupt 4e8a1d77, run 91c3f0b2) — Which quarter should I open? Answer the interrupt, then resume the run. (retry: resume)
```

The line has stopped inside `$( )`, waiting for the tool. The result carries the question.

```python
stopped = result.interrupts[0]

stopped.kind, stopped.message, stopped.options
```

```text
('question', 'Which quarter should I open?', ['q2', 'q3'])
```

Your application shows the question to a person, in whatever way it likes. When Ada chooses, give her answer as a value and resume the run.

```python
ada = Authority.of(Principal("ada"))

fs.answer(stopped.id, value="q3", authority=ada)
scout.resume(stopped.run_id)
```

```text
Third Quarter Report
```

**The line carried on from where it stopped.** The answer became the tool's output, the variable `quarter` received it, and the next command used it. The line was not started again: VFS saved it as it stood and continued it.

Two things are checked for you. An answer that is not one of the options is refused, and nothing is recorded. And an agent cannot answer its own question, because `answer` is a call only your application can make.

A person can also decline to answer. Had Ada declined, your application would have recorded this in place of the value.

```python
fs.answer(stopped.id, allow=False, reason="Ask me tomorrow.", authority=ada)
```

The tool then fails with that reason on standard error and status 1, and the line treats it as it treats any command that fails. An agent can plan for it, with `ask_user "..." || echo "no answer"`.

## Step 6: Ask, Then Act

A tool can ask in the middle of its work. This one reads a report, asks which language to translate it into, and writes the translation.

```python
@tool
def translate(path: str, *, files: Session) -> str:
    """Translate a report into another language."""
    text = files.read(path).one().content
    language = interrupt(
        f"Translate {path} into which language?",
        options=["french", "german"],
    )
    target = path.replace(".md", f".{language}.md")
    files.write(path=target, content=translate_text(text, language))
    return target

fs.add_tool(translate)
```

Here `translate_text` stands for your own code. Scout runs the tool, Ada answers, and the run resumes.

```python
result = scout.cli("translate /reports/q3.md")
stopped = result.interrupts[0]

fs.answer(stopped.id, value="french", authority=ada)
scout.resume(stopped.run_id)
```

```text
/reports/q3.french.md
```

There is one thing to know about a tool that asks in the middle. **When the run resumes, the tool's function starts again from its first line.** VFS can save a shell line as it stands, and it cannot save a Python function part-way through. So the function runs again, and this time `interrupt` returns Ada's answer and the function carries on. A tool that asks two questions is started three times, and each call to `interrupt` returns its own answer, in order.

Three rules make that safe.

- **A tool asks before it changes a file.** Once a tool has written through its session, a call to `interrupt` fails the tool. So a tool that starts again never has a write of its own to repeat, and each change it makes happens once. `translate` follows the rule: it reads, then asks, then writes.
- **An answer is for the files the tool had read.** If `/reports/q3.md` changes while the question is waiting, Ada's answer is not used. The question is asked again, about the report as it now is.
- **What a tool does outside VFS is yours to order.** VFS cannot see a request to another service, so it cannot keep one from running again. Put such code after the last call to `interrupt`, as you would put the write.

## Step 7: Have a Person Approve a Tool

Some tools should not run at all until a person has said yes. This one publishes a report to a website, which VFS can neither preview nor undo.

```python
@tool(approval=True)
def publish(path: str, *, files: Session) -> str:
    """Publish a report to the company website."""
    post_to_website(files.read(path).one().content)
    return f"published {path}"

fs.add_tool(publish)
```

Here `post_to_website` stands for your own code. With `approval=True`, every run is interrupted before the function is called.

```python
result = scout.cli("publish /reports/q3.md")
stopped = result.interrupts[0]

stopped.kind, stopped.message
```

```text
('approval', 'publish /reports/q3.md needs a person.')
```

An approval is answered with a yes or a no.

```python
fs.answer(stopped.id, allow=True, authority=ada)
scout.resume(stopped.run_id)
```

```text
published /reports/q3.md
```

**The function ran once, after Ada said yes.** An approval is asked before the function starts, so there is nothing to start again.

A policy can ask for the same approval without a change to the tool. A run of a tool reaches your policy as the operation `"run"`, with the tool's path in `call.paths` and its arguments in `call.arguments`, and the ready-made `review` policy interrupts every one.

## Step 8: Decide Who May Run a Tool

A tool is your code. It runs inside your application, with everything your application can reach, so decide who may start it.

Access to a tool is access to its entry in `/.vfs/bin`. A caller who may read the entry may run the tool. A caller who may only list it sees the name and is refused. A caller with no access does not see it at all. On an open file system that means anyone may run every tool, as anyone may read every file.

Close the file system, and give Scout the one tool it needs.

```python
fs.set_posture("/", "none", authority=system)
fs.grant("/reports", "scout", "read", authority=system)
fs.grant("/.vfs/bin/title", "scout", "read", authority=system)

scout.cli("title /reports/q3.md; publish /reports/q3.md")
```

```text
Third Quarter Report
bash: line 1: publish: command not found
```

Scout runs `title` and cannot find `publish`. The programs VFS ships are different. Every caller may run them, because each one can do only what its caller can: `cat` reads a file as the caller, and is refused where the caller is.

## Test a Tool on Its Own

A tool can be tested with no file system and no shell. Call `invoke` with its arguments.

```python
word_count.invoke({"text": "one two three"})
```

```text
3
```

For a tool that asks, give the answers in the order the tool will ask for them.

```python
ask_user.invoke({"question": "Which quarter?"}, answers=["q3"])
```

```text
'q3'
```

## What to Remember

A function with `@tool` is a program in `/.vfs/bin`, and an agent finds it and runs it like any other. It reaches files as its caller. It can ask a person a question with `interrupt`, and the shell line waits for the answer and carries on from where it stopped.
