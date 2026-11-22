# A file carries its executable bit, and the shell shows the rest from rights

A draft, written on 2026-11-22 after the ruling that the shell acts just like Linux bash in every way it can. It is not reviewed, and nothing is built. Its first choice is the developer's to confirm.

## The outcome wanted

`chmod +x s.sh && ./s.sh` runs the script. `./s.sh` without the bit fails as Linux fails. `test -r`, `test -w` and `test -x` tell the truth about the caller, and `ls -l` shows real columns. Two permission systems that disagree are never shown to a caller.

## Builds on

- The entries table (`vfs_entries`) in `src/vfs/models/rows.py`, which holds `owner_id`, `everyone_level`, `created_at`, `updated_at`, `size_bytes` and `kind` for each entry, and no mode bits.
- The rights model: grants, postures and the ladder in `src/vfs/ops.py`, judged on every call.
- `agents/2026-11-22-the-shell-acts-as-bash-where-it-refused/spec.md`, whose routine for running text under a name runs a script file.
- `agents/2026-11-21-the-shell-runs-the-standing-program-table/spec.md`, which holds `ls -l` and `stat`; `chmod` is new here.

## The problem

- `chmod` answers 127, `command not found`.
- `./s.sh` answers 127 for a file that exists.
- `test -x` is true only for a directory.
- `test -w` is 0 for a file the caller may only read, and the write that follows is refused.
- The roadmap (story F4.1) has `ls -l` print no mode bits.
- "Write a script, `chmod +x` it, run it" is a common sequence for an agent, and every step of it fails today.

## Decisions

1. **One bit is stored: `executable`, a boolean column on the entries table, false by default.**
   - `chmod +x` and `chmod -x` set and clear it, as an edit that needs the caller's write rights.
   - So do the numeric and symbolic forms that change only the user's `x` (`chmod 755`, `chmod u+x`).
   - `write`, `copy` and `move` carry the bit, and the batch verbs take it per entry.
   - A version keeps it, so `restore` brings it back.
   - git stores this one bit of a file's mode and no other.
2. **`r` and `w` are never stored. They are worked out from the caller's rights at the moment of asking**, as Linux's `access` call answers "may I read or write this".
   - `test -w f` is true exactly when a `write` of `f` by the caller would pass the gate.
   - This is the only way `ls -l` and the gate never disagree: a stored `rw` bit nothing enforces would show a caller a file it cannot read as readable.
3. **A `chmod` that changes only bits other than the user's `x` succeeds and changes nothing.** That covers the group bits, the other bits, setuid and the sticky bit. A Linux mount with no permission bits answers this way. Who may read or write a file is a grant, and the reference page says so.
4. **`ls -l` and `stat` print:**
   - the derived `rw` and the stored `x`, for the user, and the same for the group and other columns;
   - the owner from `owner_id`, or `root` when there is none;
   - the time from `updated_at`;
   - the size.

   The columns stay where GNU puts them, so an agent that reads them by position reads them right. This replaces the columns of the program-table spec's decision 5 and of the roadmap's F4.1.
5. **`./s.sh`, or any path in command position:**
   - with the bit set, it runs the file through the routine for running text under a name, in a new shell that starts from the line's exported variables and exported functions, its working directory and its open descriptors, as a new bash process does, and not in a subshell, when its first line is `#!/bin/bash`, `#!/usr/bin/env bash`, `#!/bin/sh` or there is no `#!` line;
   - with any other interpreter, it fails with `bad interpreter: No such file or directory`, status 126;
   - without the bit, it fails with `Permission denied`, status 126.

   Running a script as bash text inside the line is not the `run` verb, which runs a tool. Every effect of the script is still a public verb called as the caller.
6. **`find -perm` and `find -executable` read the same bits.**

## Tests

- `chmod +x s.sh && ./s.sh` runs it; `./s.sh` without the bit gives 126 and bash's message; a script with a foreign interpreter gives 126.
- `test -w` matches the outcome of a `write` for a caller with `read` and a caller with `read_write`, on both engines.
- `copy` and `move` carry the bit; a 10,000-entry batch write carries it per entry within the declared chunking budgets.
- `chmod 600 f` on a file without the bit succeeds and changes nothing; on a file with it, it clears the bit and changes no rights.

## Scope

- The entries table and its migration on SQLite and Postgres.
- The verbs that write a row.
- The vfs host's `stat` answer, which gains the bits.
- The shell's `test`, `ls -l`, `stat`, `find`, `chmod` and command lookup.
- The reference pages.

## Not checked

- Whether `Observation` gains the bit as a field or as a column a caller names.
- The migration's cost on a table of 10,000,000 rows on each engine. A boolean column with a default is expected to be cheap, but that is not measured.

## Choices to confirm

- **The design itself** (recommended): one stored `x` bit, with `rw` derived from rights.
  - The alternative is full stored mode bits, which would be a second permission system that nothing enforces.
  - The other alternative is no stored bit, treating every readable file as executable as a mount with no permission bits does.
- Whether a file written with a `#!` first line starts with the bit set. Recommended: no, as on Linux.

## One line

A file stores only its executable bit, and the shell shows read and write from the caller's real rights, so `chmod +x` and `./s.sh` work and `ls -l` never lies.
