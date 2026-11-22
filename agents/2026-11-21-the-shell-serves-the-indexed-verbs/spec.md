# The shell serves grep, find and the verbs with no Unix name from the indexed verbs

A draft, written on 2026-11-21 from the structural review of the shell (`agents/2026-11-21-the-shell-speaks-bash/reviews/structural-review.md`, finding 2) and the shell's `progress.md`. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it.

## The outcome wanted

`grep -rn mfa /enterprise | head -20` costs one call of the `grep` verb, not one `read` for each file beneath the root, and `find /docs -name '*.md'` one call of `glob`. `traverse`, `grant`, `revoke`, `grants`, `edit`, `mkedge` and `rmedge` run as programs of the shell, each one call of its verb as the caller.

## Builds on

The program request of `agents/2026-11-21-the-shell-speaks-bash/spec.md`: a name the machine does not run itself is a `Start` request, and the vfs host already runs `search` as the `search` verb (`src/vfs/shell/host.py`, `_PROGRAMS`).

## The problem

- The library's `grep -r` and `find` walk with `list` and `read`: 200 files under a root cost 200 `read` calls, and every body is held for the line. At the reference deployment's ten million files the roadmap's example is ten million calls.

## Decisions

1. The vfs host resolves `grep` itself when its options and operands are ones the `grep` verb serves (`-r`, `-n`, `-i`, `-l`, `-c`, `-w`, `-F`, `-E`, `--include`, `--exclude` over paths), and answers `library` otherwise, so every other form keeps the library's GNU output.
2. The host's `grep` prints exactly what GNU grep prints for the rows the verb returns; the corpus's program-tier `grep -r` cases are run through the vfs host to hold it.
3. `find` is served from `glob` for the `-name`, `-type` and `-path` forms, and from the library otherwise.
4. Each verb with no Unix name is one entry of `_PROGRAMS`, with a usage line on a bad argument and status 2.
5. A redirection opens its file with a write of no bytes when its command could act first, so the caller's refusal is known before the command runs. Once the roadmap's write planning (`write(plan=True)`) lands, that opening write becomes a plan call and one write holds everywhere. Library programs that only read (`grep`, `sort`, `head`, `sed` without `-i`) could defer their file as `echo` does now.

## Tests

A spied test counts one `grep` verb call for `grep -rn x /docs` over 200 files and the same stdout as the library's; one per verb program.

## Scope

The vfs host and `cli`. The machine and the wire are unchanged.

## Not checked

Whether the `grep` verb's rows carry what `-n` and context lines need for every file kind; whether a `glob` answer orders as `find` prints.

## Choices to confirm

Whether a form the verb cannot serve falls back to the library silently or says so on standard error.

## One line

A recursive grep in the shell is one indexed verb call, not a read of every file.
