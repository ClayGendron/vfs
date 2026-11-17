# How we name things

This page holds the rules for naming classes and methods in VFS. They exist so that a word has one meaning, and a meaning has one word, in the code as well as in the [glossary](../reference/glossary.md).

## The name of the project

In prose the project is **VFS**, in capitals. The lower-case `vfs` is the Python package, and it appears only as code: `from vfs import Entry`, `vfs.Mount`, `src/vfs/`.

## Nouns

- **A noun is a type or a glossary term.** `Mount`, `Entry` and `Session` are classes. "Member" and "posture" are glossary terms.
- **A noun is never a method name by itself.** A method called `posture()` does not say whether it reads the posture or sets it. A method called `session()` does not say that it creates something that must be closed.
- **One concept has one noun, in public code and in private code.** A concept may have several representations. Each one carries the same word. There is no second noun for the private one.

## Methods

| Form | Meaning | Examples |
|---|---|---|
| Verb, then noun | The method does that to the thing, and the noun means the same as the type | `add_mount()`, `remove_mount()`, `set_posture()` |
| Plural noun | The method returns the collection of that thing | `mounts()`, `grants()`, `capabilities()` |
| Bare verb | The action is the verb | `read()`, `write()`, `grant()`, `revoke()` |

The file verbs that share a name with a Unix command are bare verbs too, whatever part of speech the word is in English: `ls()`, `stat()`, `tree()`, `glob()`, `grep()`, `mkdir()`.

## The verbs

A method that acts on a noun takes its verb from this list, so a name can be guessed before it is looked up.

| Verb | Used when | Example |
|---|---|---|
| `add`, `remove` | The thing joins or leaves a collection the file system keeps | `add_mount()`, `remove_member()` |
| `set` | One value is replaced by another | `set_posture()` |
| `update` | A thing is changed in place and stays the same thing | `update_mount()` |
| `open`, `close` | The thing has a lifetime and must be closed | `open_session()`, `close()` |

"Get" is not on the list. A plural noun already returns what exists, and a method that makes something new each time it is called is `open`, not `get`.

## Public and private

- **A type that a public signature names is public.** A caller who reads `storage: StorageBackend` on a reference page can write `from vfs import StorageBackend` and open its page.
- **A private object is documented on a Maintainers page,** never beside the public API. It carries no compatibility promise.
- **"Bind" is kept free.** In Plan 9 and in Linux, to bind is to make something already in the file tree appear at a second path. VFS does not do that today, and the word is reserved for it.

## Why "mount" and not "binding"

Plan 9 and Linux each keep a private live record of a mount and publish a separate description of it. Every layer is named for the mount: Plan 9's kernel record is `Mount` whether the `bind` call or the `mount` call made it, and Linux has `mount`, `vfsmount`, `statmount` and `mountinfo`. Neither uses "binding" as a noun. VFS follows them with one class, `Mount`.

## Where the code does not follow these rules yet

These names were decided on 2026-11-16 and are not changed in the code yet. This section is deleted when they are.

| Today | Under the rules | Why |
|---|---|---|
| `Binding`, `MountMeta`, `MountInfo` | one public class, `Mount` | One concept, one noun |
| `mounts()` returns `MountInfo` rows | `mounts()` returns `Mount`s | A plural noun returns that noun |
| `bind()`, `unbind()` | not public; `add_mount()` and `remove_mount()` are the public pair | "Bind" is kept free |
| `remount()` | `update_mount()` | It changes a mount in place |
| `session()` | `open_session()` | It creates something that must be closed |
| `posture()` | `set_posture()` | It sets |
| `StorageBackend`, `ObjectKind` are private | public | Public signatures name them |
