# A served grep hands its matches to the line a page at a time

A draft, written on 2026-11-22 from finding M1 of `context/reviews/2026-11-22-the-shell-serves-the-indexed-verbs-code-review.md`. It is not reviewed, and nothing is built.

## The outcome wanted

`grep -rn TODO / | head -1` and `find / -name '*.md' | head -1` hold one page of matches at a time, and stop asking for the next page once the line's reader has gone, as the library's walk stops at its next write.

## Builds on

The served `grep` and `find` of `src/vfs/shell/programs.py`, the host's feed replies in `src/vfs/shell/host.py`, and the listing cursor (`after` and `limit`) that `glob` already takes.

## The problem

- A served program holds its whole answer before the line reads a byte of it. Over 400 files, `grep -rn x / | head -1` served is one `grep` call at a 40.6 MB peak; the library's walk is 2 `read` and 21 `ls` calls at 2.0 MB. At the reference deployment a `grep -r` over a common word under `/` holds every matching line of the corpus.
- The `grep` verb takes no cursor, so it cannot be asked for its answer a page at a time.
- The order a served program prints in is the library's walk, files before subdirectories in each directory, which is not the path order a cursor pages in.

## Decisions to make

1. Whether `grep` gains `after` and `limit`, as `glob` has them, paging its rows in path order.
2. Whether a served program prints in path order, which bash's own readdir order leaves free, so that its pages can be written as they arrive; or keeps the library's order and holds one directory's rows at a time.
3. Whether the host replies to each feed with one page, so that a reader that is gone ends the program before the next call.

## Tests

A counted test: `grep -rn x / | head -1` over 10,000 files issues one `grep` call of one page, and holds no more than one page of rows.

## One line

A served grep reads its answer a page at a time, so `| head` bounds it as it bounds the library.
