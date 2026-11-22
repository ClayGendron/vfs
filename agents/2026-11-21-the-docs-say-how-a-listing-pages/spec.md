# The docs say how a listing pages

A draft, written on 2026-11-21 by the documentation check of `agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md`. That work changed docstrings only, because a page under `documentation/` is written under a person's guidance. It is not reviewed, and nothing is built.

## The outcome wanted

A reader of the published docs learns that `ls`, `tree` and `glob` page, what a key is, and what a page costs across mounts, without reading the API reference first.

## The problem

The listing cursor landed with `after=`, `limit=` and `Result.next_after` described in the docstrings of `AsyncVirtualFileSystem.ls`, `tree` and `glob`, of `Result`, and of the storage protocol. Three places outside the reference say nothing of it.

- **The glossary has no term for a page.** The docstring of `ls` first marked "page" as a glossary term, and the docs gate refused it, because `documentation/reference/glossary.md` defines none. The marker was dropped.
- **`documentation/maintainers/mounts.md` counts the storage calls of a listing over mounts, and not of a page.** A page asks only the mounts whose paths lie after its key, a storage that does not declare `listing_cursor` is asked for its whole listing and cut by the kernel, and a mount point's row obeys the key like any row.
- **No tutorial or how-to shows a listing read a page at a time.** `documentation/tutorials/build-your-first-file-system.md` lists `/` whole.

## Decisions

1. **A glossary term "Page"**, in `glossary.md` and `glossary.json`: the rows of one listing call after a key, at most `limit` of them, with the key of the next; and the term marked again in the docstring of `ls`.
2. **A paragraph in `mounts.md`** on what a page costs across mounts, beside the paragraph that counts a listing's calls.
3. **One short section in the first tutorial**, a drain loop over `next_after`.

## Tests

`scripts/docs.sh check` passes, with the glossary term exported and linked from the docstring.

## Scope

In: the three pages. Out: any change to the code.

## One line

The glossary, the mounts page and the first tutorial say how a listing pages.
