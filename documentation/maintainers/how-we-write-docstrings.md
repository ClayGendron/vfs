# How we write docstrings

This page holds the rules for a docstring in VFS. A docstring is a page's content, because the reference pages are built from the docstrings. A reader meets it as prose, often without the code beside it.

The rules were set on 2026-11-17, after a study of how Plan 9, Linux, Go and other projects document their code. [Where the rules come from](#where-the-rules-come-from) names each source.

## The rules

### The first sentence

1. **The first sentence is one complete sentence on one line.** It stands alone as the summary, and it ends in a full stop.
2. **A function starts with a command.** "Write one file", "Return the mount". A class, a constant or a property starts with what it is.

### What a docstring says

3. **A docstring states the contract.** It says what the caller passes, what the caller gets back, and what the caller can rely on. It does not say how the code does it, and it does not name who calls it.
4. **A reason comes after the contract.** A private function may give its reason in its last paragraph. A reason that spans several functions goes in the module docstring. History stays in git.
5. **A parameter is named inside a sentence.** It is spelled as in the signature and set as code. No list repeats what the signature already says.
6. **Every public verb says what it returns and how it fails.** It names the errors a caller can act on.
7. **A docstring says what a caller could assume wrongly.** Order, whether a call is all or nothing, and what happens when two calls run at once.

### The order of paragraphs

8. **Paragraphs keep one order.** What it does. Then the parameters and the special cases. Then what it returns and how it fails. Then an example, when there is one.
9. **A special case is one sentence that starts with its condition.** "If `parents` is true, the missing parents are made."

### Sentences

10. **One idea in each sentence.** A sentence that wants a dash, a semicolon or a colon between two clauses is two sentences. A colon may introduce a list or a fenced example. A colon inside code, or inside a role such as `:term:`, is not a colon in the prose.
11. **Sentences are complete, in the present tense, and in plain words.** No fragment, and no word a new reader would have to look up.

### Terms, examples and length

12. **A glossary term carries `:term:` at its first use.** [How we document](how-we-document.md#using-a-term) shows the marker. Any other term of art is defined in the sentence that first uses it, or it is added to the glossary.
13. **An example is given only where the shape of the call is not obvious.** It sits last, inside a fence with its language named. The site does not draw indented code.
14. **Length follows how subtle the thing is.** One sentence is enough when the name and the signature say the rest. More is for what a caller cannot guess.

## One docstring, before and after

This is `write()` on the kernel. The old docstring never said what the call returns, what `overwrite` does, or who `authority` is.

Before:

```
Write one file (*path* + *content* or *data*) or a batch of
*entries*.

Batch entries route by their own paths — grouped per entry,
rebased, and gated per row before anything dispatches. *entries*
and the single form are mutually exclusive, as are *content* (a
text body) and *data* (a bytes body, whose text is a rendering
the rebuild pass derives). The single form is sugar: this gate
constructs the validated :class:`Entry`, and storage only ever
receives entries — raw content never crosses the storage seam.
```

After:

```
Write one file, or a batch of entries.

Pass ``entries``, or pass ``path`` with ``content`` or ``data``.
``content`` is a text body and ``data`` is a bytes body. The two
forms cannot be mixed, and neither can ``content`` and ``data``.

If ``overwrite`` is false, a write to a path that already holds
a file is refused. If ``parents`` is false, every parent
directory must already exist.

``authority`` names the caller. With none, the caller is the
kernel's default authority, or else the anonymous caller.

The call returns a :class:`Result`. A refusal raises nothing and
is carried on the result.
```

## Where the rules come from

| Source | What we took |
|---|---|
| Plan 9 | The manual gives each call a one-line summary, then a description in full sentences with the parameters named in the prose, then a short section for failure |
| Linux | A comment says what the code does and not how. A comment never repeats the signature |
| Go | A doc comment is complete sentences. A special case is its own sentence. The algorithm belongs in comments inside the function |
| Python's PEP 257 | The first sentence of a function is a command |
| OpenBSD, SQLite, Rust | Comments are real sentences. Failure has a fixed place. A term links to where it is defined |

Some of their own words, each checked against the source on 2026-11-17:

- Plan 9, `style(6)`: "If your code is readable, you shouldn't need many comments. A line or two comment above a function explaining what it does is always welcome."
- Plan 9, `dup(2)`: the summary is "duplicate an open file descriptor", and the whole section on failure is "Sets errstr."
- Linux, `Documentation/process/coding-style.rst`: "you want your comments to tell WHAT your code does, not HOW."
- Linux, the same file: "Do not add boilerplate kernel-doc which simply reiterates what's obvious from the signature of the function."
- Linux, `kfree()`: "If @object is NULL, no operation is performed."
- Go, `io.ReadFull`: "ReadFull reads exactly len(buf) bytes from r into buf."
- Go, `os.Rename`: "If there is an error, it will be of type *LinkError."

The written guides are [Go Doc Comments](https://go.dev/doc/comment), the Linux [kernel-doc guide](https://docs.kernel.org/doc-guide/kernel-doc.html), [PEP 257](https://peps.python.org/pep-0257/), the OpenBSD [style(9)](https://man.openbsd.org/style.9) page and the Rust [API guidelines](https://rust-lang.github.io/api-guidelines/documentation.html).

## Where the sources disagree, and what we chose

| Question | What the sources do | What we do | Why |
|---|---|---|---|
| The first word of a function's docstring | Go starts with the name. PEP 257 uses a command. Manual pages use a fragment | A command | The reference page already prints the name as the heading |
| Parameters | Linux, Google and NumPy use labelled lists. Go, Plan 9 and SQLite use prose | Prose, in a fixed order of paragraphs | Every signature is typed, and a list would repeat it |
| Examples | Rust asks for one on every item. Plan 9 has one on 20 of 159 manual pages | Only where the call is not obvious | VFS has a small set of verbs |
| Dashes, semicolons and colons between clauses | Go and Plan 9 almost never use a dash. Both use semicolons freely | None of the three | One idea in each sentence. This is stricter than any source |

## What checks these rules

Review checks them. The build checks three things only.

- A `:term:` marker for a term the glossary does not define stops `scripts/docs.sh check`.
- A docstring with indented code, or with anything else the site cannot draw, stops it too.
- A docstring that cites a spec or a decision record by number fails a lint test.

The docstrings written before 2026-11-17 do not all follow these rules yet. `src/vfs/base.py` and `src/vfs/mounts.py` do.
