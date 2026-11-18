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
| `StorageBackend`, `ObjectKind` are private | public | Public signatures name them |

One test comes with this change. **Every type named in a public signature is exported.** The docs export holds every public signature, so the rule can be checked from it.

## How `Mount` is built

- **`Mount` is a frozen dataclass with slots, not a `NamedTuple`.** Its `caps` field is computed once, when the mount is built, as `declared_caps - deny_ops`. Every permission check reads it. A `NamedTuple` cannot compute a field when it is built.
- **Its fields are `path`, `storage`, `permissions`, `deny_ops`, `no_overlay`, `owned`, `declared_caps` and the computed `caps`.** There is no second class for the policy and no third for the public view.
- **`Mount.to_payload()` returns the JSON-native form, a `MountPayload`.** A `Mount` holds a live storage object, so `json.dumps` cannot take it whole. `PermissionMap.to_payload()` uses the same name for the same job.
- **`add_mount()` and `remove_mount()` follow a pair that exists.** `add_member()` and `remove_member()` use the same two verbs. `remove_mount()` returns the `Mount` it removed, so the caller can close the storage.
- **A session has no way to reach a `Mount`.** A `Mount` carries the storage object, and a session is what an agent holds. Reaching the storage would go around permissions. Only the file-system object has mount methods, and a test keeps it so.
