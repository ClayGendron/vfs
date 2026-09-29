# Study: traverse vs list on the directories above a usable subtree

Companion to the memo
`../../2026-09-28-traverse-visibility-unix-plan9.md`.

The question: when a caller may use `/projects/alpha` but holds nothing
on `/projects`, what does POSIX let it do with `/projects`? These
scripts answer it by experiment on a real kernel, for each mode of the
ancestor directory.

## Files

- `repro.sh` — POSIX `sh`. Builds `P/alpha/file.txt` and `P/beta/`,
  sets `P` to `0700`, `0100` (search only), `0400` (list only) and
  `0000`, and runs `ls`, `stat`, `cat`, glob, `find`, `mkdir -p` and
  `mkdir` against it. Ends with a leak probe: what a search-only caller
  learns from `stat P` when a hidden sibling appears.
- `errno_matrix.py` — the same matrix through Python's `os` calls, so
  each outcome is an exact errno name. Also shows that a list-only
  directory reveals each entry's kind (`scandir` reads it from the
  directory entry, with no stat).
- `results.md` — the captured outputs and a summary table.

## Rerun

No root, no sudo. Each script chmods only directories it created, under
`${SCRATCH:-./.scratch}`, and removes them on exit (it restores `0700`
first so the tree can be deleted).

macOS or Linux host:

    sh repro.sh
    uv run --no-project python errno_matrix.py

Linux, from macOS, via Docker (optional; the daemon was already running
on 2026-09-28, nothing was started). The study directory is mounted
read-only and the scratch tree lives in the container:

    docker run --rm --platform linux/arm64 --user 1000:1000 \
      -e SCRATCH=/tmp/scratch -v "$PWD":/study:ro \
      python:3.13-slim sh /study/repro.sh
    docker run --rm --platform linux/arm64 --user 1000:1000 \
      -e SCRATCH=/tmp/scratch -v "$PWD":/study:ro \
      python:3.13-slim python /study/errno_matrix.py

Why the owner bits are enough: for a process whose uid owns the
directory, the kernel consults the owner triple only. So owner mode
`0100` behaves, for this process, exactly as `0711` behaves for a
non-owner. No second account is needed.

## Result (2026-09-28)

Darwin 25.5.0 (APFS) and Linux 7.0.12-linuxkit (overlayfs) agree on
every kernel outcome. Search without list reaches the deep file, cannot
list the ancestor, can stat the ancestor with full metadata, and can
probe guessed names (ENOENT vs ok). No search at all answers EACCES for
every name below, existing or not. See `results.md`.
