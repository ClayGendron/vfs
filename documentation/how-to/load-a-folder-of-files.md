# Load a Folder of Files

This guide shows how to copy a folder of files from your disk into VFS with one call, and then work with those files. Use it when the files you want an AI agent to work with already exist, such as a code repository or a folder of documents.

The example loads the VFS repository itself, which holds about two thousand text files. **To load your own repository or folder, skip Step 1 and change two lines in Step 2.** Every other step is the same.

## Before You Begin

You need Python 3.11 or later with `vfs-py` installed, `git` to fetch the example, and a file system to load into.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem()
```

This one keeps its files in memory. To keep them after your program stops, create the file system on a database, as shown in [Keep Your Files in a Database](../tutorials/keep-your-files-in-a-database.md). The steps below are the same for both.

## Step 1: Get the Example Folder

Clone the VFS repository. Run this in a terminal, in the directory where your notebook or script runs.

```bash
git clone https://github.com/ClayGendron/vfs.git
```

This creates a folder named `vfs`. If you are loading your own folder, you already have it, so skip this step.

## Step 2: Choose What to Load

Name the folder on your disk and the path it will have in VFS, and say which files to take.

```python
from pathlib import Path

folder = Path("vfs")
destination = "/vfs"

suffixes = {
    ".md", ".py", ".rs", ".toml",
    ".txt", ".sh", ".yml", ".json",
}
skip = {
    ".git", ".venv", "node_modules", "__pycache__", "target",
}

files = [
    file
    for file in sorted(folder.rglob("*"))
    if file.is_file()
    and file.suffix in suffixes
    and not skip.intersection(file.relative_to(folder).parts)
]

len(files)
```

```text
2032
```

The repository changes, so your number will differ.

**`folder` and `destination` are the two lines to change for your own folder.** `folder` is where the files are on your disk. `destination` is where they will live in VFS, and it does not have to match the name on your disk.

The other two settings decide which files are taken.

- **`suffixes` lists the kinds of file to load.** Keep it to text files, and add the suffixes your folder uses.
- **`skip` lists folder names to leave out**, wherever they appear. The ones here hold Git's own data, installed packages, and build output, which no reader of the files needs.

## Step 3: Read the Files into Entries

Build one `Entry` for each file. An entry holds the path the file will have in VFS and its content.

```python
from vfs import Entry

entries = []
unreadable = []

for file in files:
    try:
        content = file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        unreadable.append(file)
        continue
    path = (
        f"{destination}/{file.relative_to(folder).as_posix()}"
    )
    entries.append(Entry(path=path, content=content))

len(entries), len(unreadable)
```

```text
(2032, 0)
```

Each file keeps its place inside the folder, so `vfs/src/vfs/sync.py` on your disk becomes `/vfs/src/vfs/sync.py` in VFS. A file that is not valid text is set aside in `unreadable` instead of stopping the load.

## Step 4: Write the Entries in One Call

Pass the list to `fs.write`.

```python
result = fs.write(entries, parents=True)

result
```

```text
write success: 2032 files (2032 created)
```

`parents=True` creates each folder that does not exist yet, so the whole tree is made along the way.

**A batch is written together or not at all.** If VFS refuses one entry, it writes none of them, so a failed load never leaves half a folder behind.

## Step 5: Check the Result

A load does not raise an exception when it fails. It returns a result that says what happened, so check it.

```python
result.success
```

```text
True
```

When `success` is `False`, each refused entry is in `result.failures` with its path and the reason.

```python
for failure in result.failures:
    print(failure.path, failure.message)
```

This loop prints nothing here, because every entry was written.

## Step 6: Work with the Loaded Files

The repository is now in VFS, and every call works on it. List what arrived.

```python
fs.ls("/vfs")
```

```text
/vfs/.claude
/vfs/.github
/vfs/AGENTS.md
/vfs/CLAUDE.md
/vfs/CONTRIBUTING.md
/vfs/Cargo.toml
/vfs/README.md
/vfs/conftest.py
/vfs/context
/vfs/crates
/vfs/docker
/vfs/docs
/vfs/documentation
/vfs/mkdocs.yml
/vfs/pyproject.toml
/vfs/scripts
/vfs/skills-lock.json
/vfs/src
/vfs/tests
```

Find files by name. A pattern with no `/` matches a file name at any depth below the paths you give.

```python
fs.glob("*.yml", paths=("/vfs/.github",))
```

```text
/vfs/.github/workflows/deploy-docs.yml
/vfs/.github/workflows/lint.yml
/vfs/.github/workflows/publish.yml
/vfs/.github/workflows/test-dialects.yml
/vfs/.github/workflows/test.yml
```

Search the contents. This finds where a class is defined, and answers with the file and the line.

```python
fs.grep("class VirtualFileSystem", paths=("/vfs/src",))
```

```text
/vfs/src/vfs/sync.py:82:class VirtualFileSystem:
```

From here you can run the same searches as commands, as shown in [Use the CLI](../tutorials/use-the-cli.md), or hand the loaded files to an AI agent, as shown in [Give an AI Agent the File System](../tutorials/give-an-ai-agent-the-file-system.md).

## Variations

### Load Only the Files Git Tracks

In a repository, Git already knows which files belong to the project. Asking it for the list leaves out everything your `.gitignore` names, with no `skip` set to maintain.

```python
import subprocess

listed = subprocess.run(
    ["git", "-C", str(folder), "ls-files"],
    capture_output=True,
    text=True,
    check=True,
)

files = [
    folder / name
    for name in listed.stdout.splitlines()
    if Path(name).suffix in suffixes
]
```

Then continue from Step 3.

### Load the Same Folder Again

Running the load a second time updates the files that are already there.

```text
write success: 2032 files (2032 updated)
```

To refuse a load that would replace existing files, pass `overwrite=False`. If any path is already taken, nothing is written, and each taken path is reported as "Already exists".

```python
result = fs.write(entries, parents=True, overwrite=False)
```

### Load a Very Large Folder

One call can carry ten thousand files. For a larger folder, load it in batches, and read each batch from disk only when it is its turn, so the whole folder is never in memory at once.

```python
for start in range(0, len(files), 10_000):
    batch = [
        Entry(
            path=(
                f"{destination}/"
                f"{file.relative_to(folder).as_posix()}"
            ),
            content=file.read_text(encoding="utf-8"),
        )
        for file in files[start : start + 10_000]
    ]
    result = fs.write(batch, parents=True)
    if not result.success:
        break
```

Each batch is written together or not at all, but the batches are separate. If one fails, the batches before it stay written, and `result.failures` says which entries stopped the load.

### Load into a File System That Is Closed to Everyone

After you set a posture of `none`, a call with no name attached is refused. Load as the system, which may write anywhere.

```python
from vfs import Authority

result = fs.write(
    entries,
    parents=True,
    authority=Authority.system(),
)
```

The loaded files belong to no person, so who can read them is decided only by the grants and the posture you set. [Access Levels](../reference/access-levels.md) lists what each level allows.
