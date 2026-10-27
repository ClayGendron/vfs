# The agent shell: what the field built, what the corpus says agents type, and what ran on the live tree

- **Status:** research memo (commits us to nothing). Feeds five ADRs
  and the shell specs; see §13 for the forks each ADR must decide.
  Awaiting Clay's review.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-15: "build a full CLI like unix and plan9
  have. agents shouldn't feel limited from what they can do with a bash
  terminal", built so capability grows over time (pipes, text programs,
  wasm programs, Python and JavaScript guests, a hermetic runtime), and
  designed for multimodal content from day one with MCP's content
  blocks as the only wire format. Two rules Clay set during the day:
  common commands keep their native names and flag semantics (`sed` is
  `sed`, never a vfs spelling); and only MCP, no provider-specific
  adapters.
- **Method:** nine parallel studies and one executed spike, each a
  subagent with the same brief
  (`studies/2026-10-15-agent-shell/00-brief.md`), each told to label
  every claim EXECUTED, READ or INFERRED and to copy nothing. One
  experiment ran before the studies: Clay mined his own Claude Code
  transcripts for command frequencies with a script that records only
  command names, flags and shell constructs
  (`studies/2026-10-15-agent-shell/experiments/e2/`). Every study that
  ranks by usage ranks by that corpus. The ten reports are the numbered
  files beside the brief; scripts, binaries and outputs are under
  `experiments/<id>/`. This memo is the synthesis.
- **Sources (clones refreshed to `origin/HEAD` on 2026-10-15; licences
  read from each checkout, `refresh.log` and `licenses.log` in the
  studies folder):** `oils` bdc8364 (Apache-2.0), `mvdan-sh` 0e8ea6f
  (BSD-3), `brush` c495882 (MIT), `busybox` 371fe9f (GPL-2.0, study
  only), `toybox` 6a0c0ef (0BSD), `uutils-coreutils` 4945ecf (MIT),
  `sbase` b30fb56 (MIT), `plan9port` b6564bd9 (MIT), `nushell`
  818d4ac06 (MIT), `elvish` 26a8bd5 (BSD-2), `PowerShell` db1d0a5
  (MIT), `TermKit` 2d368b8 (BSD), `monty` 2bb9f08a (MIT, v1.1.0),
  `wasmtime-py` 280ce73 (Apache-2.0; wheel 49.0.0 executed), `WASI`
  463701e, `browser_wasi_shim` b068ec2, `wasi-virt` 448f6df,
  `componentize-py` 9ff99da, `cpython` fdec4df (PSF), `pyodide`
  adc5b63 (MPL-2.0), `RustPython` 88f5189 (MIT), `quickjs-ng` 9b06171
  (MIT), `quickjs-rs` 278cf32 (MIT), `llm-wasm-sandbox` 680c927 (MIT),
  `just-bash` 9ab0e0d (Apache-2.0), `just-bash-py` 48d111c
  (Apache-2.0), `bashkit` b7904a4 (MIT), `lifo` 5a35d05 (MIT),
  `amla-sandbox` 169384f (Python MIT; wasm runtime AGPL/BUSL, study
  only), `codex` 16e578d (Apache-2.0), `opencode` 13263f30ed (MIT),
  `claude-agent-sdk-python` aada024 (MIT), `deepagents` 0bf167654
  (MIT), `deepagentsjs` 9f3bfd5 (MIT), `eve` 5666d2f0d (Apache-2.0),
  `sandbox-runtime` 9a277e5 (Apache-2.0), `sandbox-sdk` a080a65
  (Apache-2.0), `modelcontextprotocol` 86f6e0c6, `python-sdk`
  754254c0 (MIT), `fastmcp` e2fcc41 (Apache-2.0), `mcpfs` 640511e
  (MIT), `agentfs` 0a014eb, `agentvfs` 82663b4 (MIT), `ripgrep`
  3fce3b5. Two clones were dirty and not refreshed: `plan9` (at
  ed1a9c21e) and `gemini-cli` (at d42e3f1e7, whose working tree has
  been replaced by an unrelated project; cited only through `git
  show` or the July memo; needs a re-clone). `9front` (a0806493, MIT per `lib/legal/mit`) was
  cloned fresh but reports dirty from case-colliding filenames. `bash`
  was not cloned (the mirror is gone); bash semantics come from the
  POSIX text, mvdan-sh's bash dialect and brush. Web sources are cited
  inline in the studies with fetch dates.

---

## 1. The answer, in one page

The shell is small, measurable, and mostly decided by what agents
actually type.

- **What agents type is nine commands.** Across 12,627 real Bash calls
  from 418 transcripts, nine commands make 86% of every pipeline
  segment: `grep`, `head`, `echo`, `sed`, `cd`, `uv run`, `tail`,
  `cat`, `ls`. Pipes appear in 74% of calls and `&&` in 44%. Control
  flow, functions, arithmetic, arrays and background jobs together
  touch under 10%. (§2)
- **The grammar is a bash-shaped POSIX subset, parsed by us, refusing
  the rest loudly.** Pipes, lists, redirections, here-documents,
  variables, command substitution, globs and braces are v1. `for`,
  `if`, functions, `[[ ]]`, arithmetic, `<( )`, arrays and `&` are
  refused at parse time with a classified `unsupported.construct` that
  names the construct and its line and column. That v1 admits 86 of
  100 corpus-weighted commands outright. (§3)
- **The catalog is about 25 programs for 87% coverage.** Classified by
  how vfs answers them: 30% of segments are vfs verbs, 35% pure text
  programs, 24% shell builtins, 1% guest interpreters, 9% host
  programs that never run (`uv`, `git`, `docker`). The ceiling is 90%.
  Every program keeps its Unix name; the corpus only orders which forms
  land first. (§4)
- **One program ABI, two pipe shapes.** Every program takes argv, env,
  cwd, a stdin stream and a filesystem capability, and returns stdout,
  stderr and an exit code. The capability is the vfs verbs bound to
  the caller's authority, so a program cannot even express a widened
  call. The pipe carries chunks of exactly one shape, rows or bytes;
  conversion happens only where shapes differ, by two laws. Executed
  over the live tree: `ls | wc -l` counts entries, `cat f | wc -l`
  counts lines, errors never cross a byte seam, a 10,000-row pipe runs
  at queue depth two. (§5)
- **The bin directory is `/.agents/bin`, resolved as a Plan 9 union.**
  Shell builtins, then the kernel's program table, then `$PATH`
  directories searched under the caller's authority. Kernel names win;
  a host promotes a stored program over a kernel name; agents shadow
  privately through their own `PATH`. (§5)
- **The wasm mechanism works, executed.** A real jq clone built for
  wasm, stored as an entry, resolved from a bin directory, run under
  wasmtime from Python with every file call served by vfs verbs, with
  errno, trash, versions, timeouts, memory limits, a compiled-module
  cache and a three-stage pipe. The shim is 627 lines. The database is
  the latency, not Python. (§6)
- **Guests: Monty first, QuickJS second, CPython-on-WASI as the
  escalation.** Measured on this machine. Monty is a process pool with
  0.8 ms sessions and host functions as its door; CPython-on-WASI has
  no host-function door at all. (§7)
- **No command policy.** Every peer that judges command strings does
  so because its runtime is an OS shell that can run anything, and
  each says the match is not a security boundary. In vfs the gate
  order already is the policy. `run` stays at the `read` rung on the
  program's row, which closes the parked execute-policy question. (§8)
- **A shell session is `Session` plus four in-memory fields.** cwd,
  env, last status, history. None is a row; env as rows was tried and
  leaks across principals. Jobs are out of scope at v1; MCP tasks are
  the wire shape when they come. (§9)
- **MCP's five blocks, verbatim, one text block first.** The vocabulary
  is unchanged since the revision the July memo read. Text is the only
  block every client renders, and two clients replace the content
  array with structured content, so the text block and the payload
  must each stand alone. Two live-tree gaps: a bytes row renders empty
  today, and `to_payload` inlines base64 without bound. (§10)
- **The peers converged on the same shape and each retrofitted bytes
  after shipping.** None has permissions in the data path, versions,
  trash, ranked search, media rows or rows in the pipe. bashkit's
  coverage method (the Oils bash spec suite at a pinned commit, real
  bash as denominator, 97.3%) is the yardstick to adopt. (§11)

One line: pipes and `&&` are v1 not later, the catalog is 25 programs,
the verbs are the capability, rows are the pipe, MCP blocks are the
wire, and every piece of the mechanism has now run.

---

## 2. What the corpus measured (experiment E2)

Clay ran `experiments/e2/mine_commands.py` over `~/.claude/projects`
on 2026-10-15. It reads every transcript, takes the command of each
Bash tool call, and records only command names, flags and shell
constructs. No arguments or paths leave the file. Output:
`experiments/e2/commands.md`.

| Fact | Value |
|---|---|
| Transcripts, calls, pipeline segments | 418, 12,627, 67,446 |
| Distinct command names | 214 |
| Top nine by segment share | `grep` 20.9%, `head` 15.8%, `echo` 13.4%, `sed` 12.1%, `cd` 9.3%, `uv run` 5.3%, `tail` 4.1%, `cat` 3.9%, `ls` 3.1% |
| Calls containing a pipe | 74% |
| `&&` / `2>&1` / `>` / heredoc / `$VAR` | 44% / 16% / 14% / 12.5% / 12% |
| `for` / `$( )` / backticks / `\|\|` / `if` / `while` / `&` | 4.7% / 3.7% / 4.4% / 1.4% / 0.9% / 0.4% / 0.2% |
| Median segments per call | about 4 |

Three readings that bind the design. First, `sed -n` is 7,739 of
8,180 sed uses: ranged line reads. The first `sed` can serve that
form and `-i s///` and cover 95% of demand; the full language comes
later under the same name. Second, pipes and chains are the grammar
agents need; loops and conditionals are rare. Third, `uv run` and
`python3` together are about 6.5% of segments, which is the demand
for a guest interpreter, and `git` at 2.8% is the largest thing that
will never run inside vfs.

---

## 3. The grammar (study 01)

**The v1 grammar** is a static, bash-shaped subset of POSIX.1-2024,
parsed once by our own parser, no `eval`, no re-scanning. Admitted:
the three POSIX quotings plus `$'…'`; `$VAR`, `${VAR}` and the ten
POSIX parameter operators; `$?`, `$#`, `$@`, `$*`, `$0`–`$9`; `$( )`
and backticks (backticks are 4.4% of traffic, more than `$( )`);
tilde; globs and `{a,b}` brace expansion (vfs's `glob` already speaks
it); pipelines with `!`; `;`, newline, `&&`, `||`; `< > >> >| <> n>
n>> n< <&m >&m n>&m 2>&1 &> &>>`; `<<` and `<<-` here-documents with
the terminator on its own line; `( )` subshells and `{ }` groups;
assignment prefixes. Reserved words are reserved so later slices admit
them without changing today's meaning.

**Refused at v1, each as a classified fact.** `if for while until
case`, functions, `[[ ]]`, `$(( ))`, `select`, `coproc`, `time`,
`<( )`, `<<<`, `|&`, arrays and the bash parameter extras are
`unsupported.construct` with the construct's name and the slice that
will admit it. `&` is refused: the hermetic runtime has no process to
detach, and both just-bash and bashkit fake it (one runs it
synchronously, the other polls once), which lies to the model. `set`,
`shopt`, `eval`, `exec`, `trap`, `source` as commands are
`unrecognized`. Malformed text is `invalid.syntax` with line, column,
what was open, what must follow, and an `incomplete` flag for input
that ended inside a construct.

**Measured.** A 100-command corpus fit to the E2 shares went through
seven parsers. mvdan-sh in bash mode, bashkit, just-bash and
just-bash-py admitted 100 of 100; mvdan-sh in POSIX mode 98; lifo 84,
with one genuine parser hang. The proposed v1 admits 86 of 100
outright and 91 with `for`. The Oils spec suite's weight is in arrays
and arithmetic, 152 cases for constructs that are 1.4% of agent
traffic.

**Growth plan.** Slice 1 the pipeline core above; slice 2 control flow
(`for`, `if`, `while`, `case`, `[[ ]]`) to about 97%; slice 3
functions and arithmetic; slice 4 the long tail, each construct
admitted only when a measured corpus shows it above about 1%. Never:
`&`, `coproc`, `trap`, `eval`, `exec`, `set -e` as a mode.

**Plan 9's rc** is the better-designed grammar and contributes
semantics, not syntax: one pass, never re-split a substituted value,
and a list-valued pipeline status. A bash-trained model emits zero rc.

**Adopt** mvdan-sh's AST shape and error wording (which construct is
open and what would close it, not bash's "unexpected token"), brush's
one-predicate feature staging, OSH's static parse and its
`$((`-is-always-arithmetic rule, nushell's refused-feature error that
names the replacement, just-bash's parser budgets. **Reject** rc's
syntax, nushell's respelled redirections, a dialect enum, and lifo's
grammar.

---

## 4. The catalog (study 02)

**Classified by how vfs answers** (executed over the E2 corpus):

| Class | Share of segments | Examples |
|---|---:|---|
| vfs-verb builtin | 29.7% | `grep`, `cat`, `ls`, `find`, `rg`, `mkdir`, `cp`, `rm`, `mv`, `stat`, `tree` |
| pure text program | 35.1% | `head`, `tail`, `sed`, `wc`, `cut`, `awk`, `sort`, `nl`, `tr`, `uniq`, `tee`, `diff` |
| shell builtin | 24.1% | `echo`, `cd`, `sleep`, `unset`, `printf`, `source`, `export`, `test`, `date`, `which` |
| guest interpreter | 1.2% | `python3`, `perl`, `python`, `bash` |
| never | 9.1% | `uv` 5.4%, `git` 2.8%, `docker`, `ps`, `curl`, `gh`, `pkill` |

Coverage by tier: tier 1 (verb builtins, shell builtins, the
read-shaped forms of `head`, `tail`, `sed -n`, `wc`) about 87%; tier 2
(all text programs) 89%; tier 4 (guests) 90%. The remainder is host
programs with no meaning inside vfs, refused with a hint.

**Peer agreement.** Forty commands ship in all four full agent shells
(just-bash 90 names, bashkit 193, just-bash-py 69, lifo 81); that
intersection is almost exactly tiers 1 and 2. Fifty-four ship in
every classic set. Six hundred ninety-four are Unix-only (devices,
boot, network, typesetting) and appear zero times in the corpus.

**Cost per program, measured on the peers.** A median text program is
233 lines in just-bash and 525 in bashkit. The interpreters are
2,500 to 15,000: `awk`, `sed`, `find`, `rg` with its own regex, `jq`,
`tar`, `sqlite3`. Those are the candidates for wasm programs rather
than hand kernels.

**The wasm tier is real.** `uu_wc` from uutils built to
`wasm32-wasip1` in 16 seconds and ran correctly under wasmtime from
Python with piped stdin. uutils' wasm feature set covers 78
utilities, every tier-2 text program, but not `grep`, `sed`, `awk`,
`find` or `diff`.

**Clay's rule, recorded.** Native names and real flag semantics. The
corpus orders forms: `sed -n 'a,bp'` and `sed -i 's/x/y/'` before the
full sed language; `grep -n -r -v -i -E --include -A` first; `find
-name -path -type -not -o -prune -maxdepth` first (the predicate
grammar is used, 282 uses with `-o` 186). A form outside the
implemented subset returns a classified `unsupported` naming the form,
never a wrong answer. `rg` and `grep` are one verb with two names, two
flag tables and two renderers. `ls -la` prints the row's real columns
in the long format's positions, never fake mode bits.

**The coverage score**, defined on calls: parse rate, resolve rate
(with the refusal rate reported beside it), flag rate, run rate
against a bash oracle on a synthesized fixture. Reported total and
in-scope (excluding the never class), counts never wall-clock.

---

## 5. The program ABI, the bin namespace, and the pipe (study 03)

**Every peer gives a program the same six things and takes three
back.** just-bash, bashkit, lifo, nushell plugins, WASI's command
world, busybox, toybox and uutils all agree: argv, env, cwd, a stdin
stream and a filesystem capability in; a stdout stream, stderr text
and an exit code out. The vfs ABI is that shape with two decisions on
top.

1. **The filesystem capability is the verb set curried with the
   caller's `Authority`.** There is no authority parameter. A program
   has no door through which to widen identity. ADR 069's no-side-door
   rule becomes a type.
2. **The pipe carries chunks of exactly one of two shapes**, `Rows` (a
   `Result` slice, rows plus classified errors, op-tagged) or `Bytes`
   (a buffer with a mime). A program declares what it consumes and
   produces. Conversion happens only at a seam where shapes differ.

**The two laws, executed over `InMemoryStorage`.** Rows become bytes
only for a byte-shaped consumer, through the one render chokepoint
with the producing op's default projection, so `ls | wc -l` counts
entries and `cat f | wc -l` counts lines with no special case; a
single bytes-bodied `read` row crosses raw with its mime (PowerShell's
byte-pipe lesson, built in from day one). Bytes become rows only for a
row-shaped consumer, as exactly one row at a synthetic address
`/.vfs/run/<call>/stdout`, UTF-8 without NUL as `content`, else `data`
with a sniffed mime. Same shape passes untouched: `glob | grep` hands
`Observation`s as `observations=` and re-parses no text. **Errors
never cross a byte seam.** The first run of `ls /nope | wc -l` printed
1 because the error line rendered into the pipe; fixed to 0 as Unix
does. A 10,000-row `ls | wc -l` ran in 10 chunks at a maximum queue
depth of 2.

**The program kinds.** Builtins (verb programs, Python, rows to rows),
kernels (text programs in `crates/vfs-core`, bytes to bytes, no file
access), guests (wasm binaries and scripts, bytes to bytes always). The
kind is invisible on the pipe, which is what lets a name change kind
over time.

**One name, many kinds.** The name is the contract; the kind is a
table row, as busybox's applet flags choose a strategy the caller
never sees. Each program declares its forms in a toybox-style option
grammar plus a `supported` subset. A known-but-unimplemented form
refuses with `unsupported.form`, exit 2, naming the form. A swap of
kind is pinned by a parity test over the E2 forms with the old
implementation as oracle.

**The bin namespace.** A third reserved family, `/.agents/bin`, whose
unit is a file: `jq.wasm` serves `jq`. Not a top-level `/bin`, because
agents ingest whole repositories at `/` and `bin/` is an ordinary
directory in thousands of them. Resolution is a union in order: shell
builtins that must be builtins (`cd`, `export`, `exit`), then the
kernel's program table, then `$PATH` directories in the namespace
(default `/.agents/bin`) searched with `stat` under the caller's
authority. A word with a slash bypasses the union. Kernel names win; a
host promotes a stored program by configuration; agents shadow
privately through a `PATH` prefix. `run` executes stored programs
only; `list` to resolve (else 127), `read` to execute (else 126).
Builtins are not stored entries; `type`, `which` and `help` answer
from the union.

**Exit codes.** Verb failure 1; usage or unsupported form 2; timeout
124; found but not executable 126; not found 127; cancelled 130; a
program's own code otherwise. `$?` is the last stage, or the rightmost
non-zero under pipefail; `PIPESTATUS` is the vector. MCP `isError` is
`$? != 0`.

**Live-tree gaps the exercise exposed.** `run`'s default projection is
the path, so program output renders as `/.vfs/run/2/stdout`; it needs
`read`'s verbatim arrangement. `read` elides `data` unless projected,
so a byte-shaped `cat` must ask for it; the shell knows the consumer's
shape before running, so this is planning, not sniffing. No media
placeholder exists in the renderer. `Observation.path` is required,
hence the synthetic address.

---

## 6. The filesystem boundary and the wasm mechanism (studies 04 and 10)

Both studies built a WASI preview1 shim over the live tree and ran
real programs. Study 04 proved the file-call mapping with the real
CPython 3.12 and QuickJS wasm binaries; study 10 proved the whole
install-resolve-run-cache-timeout mechanism with a real jq clone.

**Whole-file staging holds at one verb per open.** `cat` is one
`read` (5 SQL statements); a new write is one `write` (16); append,
patch and truncate are a read plus a write (21); a directory open is
one `ls` (6), and a 2,000-entry listing is 17 `fd_readdir` round trips
on one verb. Nothing between open and close touches the database. The
natural shim does two verbs per file (a `stat` then a `read` or
`write`); it folds to one by classifying from the read's error kind.

**The July memo's checklist was exact.** The union of preview1
functions actually called by Rust std, CPython and QuickJS is the
memo's 24 names to the letter. The spike registered 46, 35 real and
11 stubs, and no stub was ever hit across six binaries. `path_link`
is linked by real tools and must exist as a stub or instantiation
traps.

**There are no mode bits.** preview1 and WASI 0.2 carry a filetype
only. CPython printed `st_mode 0o100000`. The ladder reaches a guest
only as errno: `none` is ENOENT, `list` lets stat and ls succeed and
answers EACCES on read, and so on down the ladder. vfs's `ErrorKind`
already names its errno in a comment per member, and the chain from
kind to errno to libc to the guest's message was proven: "No such
file or directory (os error 44)", "Capabilities insufficient (os
error 76)" for a `..` escape refused with zero verb calls.

**The mechanism, executed.** Install is `write(data=)`. Resolve is one
`ls` of the bin directory. Load is `read(columns={"data"})` plus a
compiled-module cache that turned jaq's 285 to 411 ms compile into a 1
to 17 ms deserialize. Run is a worker thread with a per-run shim,
linker and store; vfs verbs are coroutines and wasmtime callbacks are
synchronous, so each verb is posted onto the event loop. `upper
in.txt out.txt` produced version 1 then version 2 of the output. A
guest `rm` landed in the trash. A spinning guest was killed at 0.66 s
with `TrapCode.INTERRUPT`, distinguishable from a Rust abort and an
out-of-bounds store by code, never by message. A greedy guest hit a
32 MiB store limit; without a limit it took a gigabyte of host RAM.
A three-stage pipe moved bytes between wasm programs with UTF-8
preserved.

**What the July memo got wrong, measured.** Two verbs per file, not
one. The cache key must be the content hash, not the version: a
same-bytes rewrite advanced the version and recompiled. `/.agents/bin`
is not refused today, so the bin family is a free choice. Out of
memory is a guest abort, not a memory trap. The thread race is real,
13.4% of concurrent exit codes wrong across four threads, and defused
for exit codes by recording the code in per-run state before raising
(8,000 of 8,000 correct). "Any wasi build" means a dependency closure
inside wasi-libc: jaq 3.1 failed twice on a C allocator and a file
lock before jaq 1.6 built. `rmdir` must pass `cascade=False` or a
guest's `rmdir` becomes `rm -rf`.

**Python host now, Rust later.** The Python trampoline is 6 µs per
host call and a decoding `fd_write` 15 µs, against 2 µs for
wasmtime's Rust preview1. Programs in this class make 10 to 30 host
calls per run against 24 to 121 ms of verb time on in-memory SQLite.
The database is the latency. The Rust shim in `crates/vfs-core`
arrives with line-at-a-time guests on megabyte inputs or many guests
per process.

**wasmtime-py cannot host concurrent guests safely yet.** The trap
global is still a module global at 49.0.0; study 05 measured 18%
wrong and 18% lost exceptions under eight threads, and study 04 found
a second race in the installed wheel's handle slab, fixed in the
checkout. Rule: one guest at a time per process, or worker processes,
and host imports never raise.

**Text versus bytes on write-back is a host decision.** A guest only
ever hands the shim bytes. Writing a text tool's output as `data=`
hides it from `grep` and `glean` until a reindex. Decode UTF-8 to
`content`, else `data`, with the extension as tie-break so a PNG that
happens to decode never becomes text. Never sniff alone.

---

## 7. Guest interpreters (study 05)

Measured on this machine, 2026-10-15:

| Guest | Cold start | Warm print | Host call round trip | Interrupt | Snapshot | Memory |
|---|---:|---:|---:|---|---|---:|
| Monty 1.1.0, worker pool | 5 ms pool, 0.8 ms warm checkout | 0.1 ms | 96 µs | yes, 201 ms on a 200 ms budget | 2.6 KB continuation | 10 MB per worker |
| QuickJS-NG via quickjs-rs | 150 ms once, 0.27 ms per context | 0.23 ms | 283 µs | yes | 1.3 MB whole heap | +58 MB |
| CPython 3.12 WASI under wasmtime | 738 ms compile once, 29 ms per run | 29 ms | none; no host-function door | yes, epoch | none | 431 MB after compile |
| CPython 3.14 Wizer snapshot (bashkit's artifact) | 1.7 s compile once | 6 ms per call | none | yes | none | 415 MB |
| Pyodide under node | 1,045 ms | 0.17 ms | 1.8 µs | only in a Worker | none | needs a JS runtime |
| RustPython to wasm | builds | `-c` exits 1 silently | | | | |

**Monty first.** Its three doors are exactly the contract: host
functions by name, an importable `vfs` module with stubs for its type
checker, and an `os` callback that receives normalized absolute paths.
No WASI shim, no C shim, no build pipeline. It is already a process
pool, so the wasmtime thread problem does not arise, and under
`AsyncMonty` its file access can await the verbs directly. The cost is
the subset: no class inheritance, generators, `match`, `del`,
`@property`, and 23 stdlib modules without `csv`, `enum`, `io`,
`string` or `struct`. The subset is a product fact to document, with
each rejection rendered as a classified error naming the next move.
Its `max_suspensions` default of 1,000 host calls per checkout is a
budget knob and a reminder that the contract must be batch-first.

**QuickJS-NG second** for JavaScript, in the same worker pool, via
quickjs-rs as the reference shape. One unverified sign: the
`langchain-quickjs` package may have become a native extension after
July, which would change its isolation story.

**CPython-on-WASI is the escalation**, not the first guest. The Wizer
path is fast enough, but a CPython program can only reach the host
through WASI syscalls; verbs-as-functions needs a guest-side C module
compiled into the binary, a WASI-SDK and Wizer pipeline, and a 40 MB
artifact per wasmtime version. bashkit did this for HTTP. Pyodide and
RustPython are rejected.

**The contract must be a message protocol**, verb name plus JSON
arguments to a `Result` payload, so each interpreter binds it through
its own door and a swap is a binding layer. Denied by construction:
network, host filesystem, host env, spawn, config and secrets, and a
nested shell. State changes inside vfs are governed by the ladder and
the trash, not by Meta's rule of two; "communicate externally" is what
a guest must never do.

---

## 8. Execution policy (study 06)

**The vfs shell needs no command policy.** Codex judges an argv with
Starlark prefix rules; Claude Code matches `Bash(git *)` patterns per
subcommand; gemini-cli and opencode scan and classify. Each does so
because its runtime is an OS shell that can run anything, and each
says in its own docs or code that the string match "isn't a security
boundary around the program". The real boundary in every one is an OS
sandbox over paths and hosts, enforced while the command runs.
deepagents states ADR 069's enforcement gap as a `NotImplementedError`:
path permissions plus an execute backend are rejected "because shell
commands bypass path rules".

vfs is in the other position. The shell reaches storage only through
the gated verbs, and a program runs as its caller with the caller's
authority value. So the pinned gate order, capability then grammar
then permission, is the execution policy. The three pre-flight jobs
that remain are resolving the program (itself a gated read), refusing
over-shape input, and setting budgets. A table-driven reference
evaluator ran 33 cases, from `rm -rf /` (busy at a bind site, else
trash) to a 200-stage pipeline (`invalid`), and every verdict was a
kind the envelope already has.

**`run` stays at `read` on the program row.** ADR 080's rule is that a
verb's rung is the field it reads; running reads the program's body.
Plan 9 says the same in one line: exec is read plus the x bit, and
vfs has no bits by ADR 080's choice of a total order. An `execute`
level above `read_write` would say "you may trash everyone's rows but
not run `wc`". This dissolves both halves of the parked
execute-policy question: per-principal is a grant of `read` on the
bin row; per-path is a posture of `list` on the bin prefix; a program
nobody should see is not bound in. Spec 039 stays archived. One rule
to amend: the ops module and ADR 080 say `run` "waits for its own
axis".

**A program never holds more than its caller.** The capability is the
verbs closed over the caller's authority, and the four construction
doors for an authority are vfs-only. Every peer agrees on the
direction and none has a mechanism by which a program raises its
caller. The one hole is the system actor: `cli` and `run` must refuse
`Authority.system()` at the params gate.

**Today, no gate reads `run`'s rung**, because no storage implements
`SupportsRun`, and the tests pin that a mount declaring `run`
executes with no rights check. The shell's program resolution is the
gate when it lands.

**The budget set**, mirroring grep's discipline: `STAGE_BUDGET` 64
and `ARGV_BYTE_BUDGET` 128 KiB refuse `invalid` pre-flight;
`FANOUT_BUDGET` 10,000 paths per stage and `STDOUT_BYTE_BUDGET` 4 MiB
per stage serve what fits and warn `truncated`; `WALL_TIME_BUDGET`
10 s per line, `FUEL_BUDGET` 2 × 10⁹ instructions, `MEMORY_BYTE_BUDGET`
256 MiB and `VERB_CALL_BUDGET` 10,000 trip at runtime as `timeout` or
`budget_exhausted`. A fan-out over budget is never a refusal. The
epoch does not cover time inside a verb, so the verb budget is part
of the run budget.

**Install rule.** `bin` joins `AGENT_FAMILIES`; install is `write`
under the ladder (fresh at `add`, overwrite at `contribute` or own,
delete at `read_write` or own, every overwrite a version); the default
posture of `/.agents/bin` is `read`, Plan 9's `r-x` for the world,
safe because a program cannot escalate; a builtin name may not be
installed over. One small new lever: `deny_ops` extended to installed
program names, classified `unsupported`, never to builtins.

**Reject:** an `execute` rung anywhere; a command-string policy
language; an `ask` verdict inside vfs (that is the harness's
tool-permission layer); a program allow-list on the mount; a
protected-path list; session-wide counters at v1.

---

## 9. Session state and jobs (study 07)

**A shell session is the existing `Session` plus four in-memory
fields**: `cwd`, `env`, `last_status`, `history`. None is a row. A
reference `ShellSession` over the live tree ran `cd`, `ls`, `export`,
`echo $X`, `pwd` and `history` by hand-dispatch onto the existing
verbs, and two sessions with different authorities over one tree saw
different things with zero rights checks in the shell layer. `cd` is
`stat` at the `list` rung plus a kind check.

**Env as rows was tried and rejected.** Every candidate home accepted
the write, including unknown `/.agents` families; rows under `/.vfs`
hide from unscoped search but are governed by the ordinary ladder, so
a principal with `read` at `/` read another's env row. Every `export`
would mint a version and every `unset` would land in the trash. Plan
9's `/env` is a device over kernel memory, not stored rows; so would
ours be, as a synthesized read-only projection if a consumer ever
asks.

**The namespace thesis, settled.** Spec 148's narrowing is Plan 9's
per-process namespace in its subtractive form, `RFNAMEG` plus
`RFNOMNT`. It is not additive `bind`: ADR 063 forbids a session from
widening, so the bin namespace is a mount-table fact set by the admin
plane, and a session can only hide programs from it.

**Jobs are out of scope at v1.** Nothing in v1 runs long: a
10,000-file write is one bounded call (executed, 3.3 s in memory,
10,000 rows, no job needed), `glean` and `grep` are budgeted, and no
storage runs programs yet. `&` parses to a classified refusal. When
guest programs land, the shape is fixed by two precedents vfs already
follows: Plan 9 creates a process with a verb and observes it through
files; MCP's tasks extension (2025-11-25, experimental) binds a task to
the authorization context, polls it, collects its result and cancels
it, and its `input_required` status is exactly spec 148's `pending`.
So the verb creates, `/.vfs/jobs/<id>/{status,result}` observes, and
the task is the wire. `/.vfs/sessions` and `/.vfs/jobs` need posture
rules before anything is stored there.

**What spec 148 must gain:** the four fields; `cd` semantics; one
session per conversation with child sessions that copy cwd and env
and never write back; the subtractive-only rule; `pending` mapped to
`input_required`; the reserved trees above; close cancels. `$status`
is the classified kind, rc-style, and `$?` is derived from it.

---

## 10. MCP content blocks and the content channel (study 08)

**The current revision is 2026-07-28**, a large stateless rewrite,
and the content-block vocabulary is unchanged in shape since
2025-06-18: exactly `text`, `image`, `audio`, `resource_link` and
embedded `resource`, with the same required fields and the same
annotations. There is no video block and the schema rejects one;
video rides as a resource link. What changed around the blocks: a
required `resultType` on every result; `structuredContent` may be any
JSON value; `outputSchema` any 2020-12 schema; required `ttlMs` and
`cacheScope` on list and read results; `resources/subscribe` replaced
by `subscriptions/listen`; resource-not-found is `-32602`; the typed
`_meta` key grammar with reserved prefixes. The spec gives no
tool-result size guidance and no accepted image mime list for content
blocks.

**The client matrix, verified in source.** Text is the only block
every client renders. Image is the only media block every harness
shows a model. opencode flattens a resource link to a bare URI and
pulls images out into a following user message; codex shows links and
embedded resources as raw JSON text and, when `structuredContent` is
present, discards the content array entirely; Claude Code's docs
describe inline PNG, JPEG, GIF and WebP with originals saved to disk
and a 25,000-token result cap including image data, and a closed bug
plus Anthropic's own SDK say links and blobs are dropped. Nobody
fetches a resource link. The search's claim that codex drops links
was wrong for current main.

**Two live-tree gaps, executed.** `to_str()` renders a bytes row as
an empty body; no placeholder exists in the renderer. `to_payload()`
inlines base64 bytes without bound when `data` is projected.

**The projection, proposed.** One rendered `TextContent` first,
holding the whole result with placeholders and errors, then typed
blocks in row order keyed by path in `_meta`: `ImageContent` for the
four accepted image types within budget, `AudioContent` likewise,
`ResourceLink` with a `vfs:///path` URI for everything else, never an
embedded blob at v1. `isError` is `not result.success`; on error the
text block leads with the errors, because one client keeps only the
text and another middle-truncates it. `structuredContent` is
`to_payload()` with row bytes stripped and `data` removed from the
populated mask. Implement `resources` minimally at v1 so links are
honest: capability `{}`, empty list, one template `vfs:///{+path}`,
`read` returning a blob or text with the caller's authority. The
placeholder grammar, one line, exact bytes, no `|`:
`[binary /photos/pixel.png image/png 70B v3 -- PNG 1x1 RGB]`.

**Reject:** any provider-specific adapter beyond MCP's shapes; base64
in any text block ever (fastmcp still does it); per-row interleaved
blocks as the primary channel; relying on annotations for anything
load-bearing.

---

## 11. The peers, and what we copy as ideas (study 09)

| | just-bash | bashkit | just-bash-py | lifo | amla |
|---|---|---|---|---|---|
| Language, size | TypeScript, 300k lines (152k tests) | Rust, 299k lines | Python, 49k | TypeScript, 38k | Python 7k over a closed wasm runtime |
| Commands | ~90 | 167 | 69 | 81 | 13 |
| Runtimes | QuickJS, CPython wasm, sql.js | Monty, CPython wasm, a TS interpreter, sqlite | none | Node-compat layer | JS in wasm |
| Tool contract | `bash(command)` plus `readFile`, `writeFile` | `{commands, timeout_ms}` to `{stdout, stderr, exit_code, …}` | none | none | `sandbox(code, language)` to one string |
| Output cap | 30,000 chars with a marker | 1 MiB with a flag; per-builtin caps explicit | none; `seq` stops silently at 100,000 with exit 0 | none | fuel error |
| Media | latin1 byte string | lossy text plus intact bytes; `images` empty | no byte path | mime on the inode, discarded by `cat` | n/a |
| Bash conformance | Oils suite vendored, 2,728 cases | Oils fetched at a pinned commit, 97.3% of what real bash passes | 46% of the Oils suite | none | none |
| Activity | 4.4k stars, 1.5M weekly downloads | 39 releases in seven months | last commit June | | mirror only |

**Copy as ideas.** The three-tier fidelity method: recorded real-bash
fixtures, the Oils suite at a pinned commit with real bash as the
denominator, and a replayed agent-session corpus; report the number as
bashkit does, N of M cases real bash passes, per file, misses listed by
cause. A negative spec with stable IDs for every refusal. One string
in, `{stdout, stderr, exit_code}` out, a visible truncation marker,
`error` as a separate field for "failed before running", exit 124 on
timeout. bashkit's `command not found` hints. A static `analyze()`
summary as the host's prompt primitive, advisory not boundary.
Budgets with liberal and hardened profiles and refusals that are
explicit. `--help` per program as a contract.

**Reject.** Three tools (`bash`, `readFile`, `writeFile`): Vercel's
own README says bash may be the only tool, its shipped example passes
only `bash`, `readFile` has no size limit, and a second read door
would bypass `read`'s ladder. Text-only pipes and a latin1 byte
string. Permissions as inode metadata. An MCP server inside the shell
package (bashkit removed theirs).

**Their scars, in order of arrival.** Both leaders retrofitted bytes
into their pipes after launch (just-bash 3.0, bashkit 0.16), then
budgets with profiles and "refuse explicitly, never truncate silently",
then streaming pipelines (just-bash's `rg | head` still scans the
whole tree, issue open), then guest runtimes behind flags, then static
analysis for permission prompts, then snapshots. Hosts keep asking for
a search hook and an effect summary; vfs has both natively, because
`grep` is `storage.grep()` and the ops vocabulary is the effect
summary.

**What vfs does that none of them do**, with evidence: permissions in
the data path (just-bash's modes are metadata, bashkit declines by
policy, ChromaFs prunes the tree outside the shell); versions and
trash; ranked search and graph (every peer stops at grep; ChromaFs
replaced RAG with grep and still needs a coarse regex filter); media
rows and typed content on the wire; rows in the pipe; a real database
at 10,000-file batches (ChromaFs caches the whole tree in memory,
Convex caps near 1,000 files).

**The consumers** confirm the pattern and name what they gave up.
Mintlify's ChromaFs is just-bash's parser over its filesystem
interface answered by a Chroma store, with the tree cached in memory
and a two-phase grep; it is read-only, has no versions and no ranked
search, and reports session creation falling from 46 s to 100 ms.
Convex keeps metadata in tables and bytes in storage with a soft cap
near 1,000 files and no versions or permissions.

---

## 12. Live-tree gaps the shell depends on

Consolidated from every study. None is a shell feature; each is a
precondition.

1. `_DEFAULT_PROJECTION["run"]` is `("path",)` and program output
   falls into the Markdown-table arrangement that squashes newlines.
   `run` needs `read`'s verbatim arrangement. (03)
2. No media placeholder rule exists in `render.py`; a bytes row renders
   as an empty body. (03, 08)
3. `to_payload()` inlines base64 bytes without bound when `data` is
   projected. (08)
4. `read` elides `data` unless projected and answers an unprojected
   read of a bytes row with a `vfs.unavailable` warning on success.
   Correct for agents; the shell's byte-shaped consumers must project
   it. (03, 04, 10)
5. No gate reads `run`'s rung; a mount declaring `run` executes with
   no rights check (pinned by a test). (06)
6. `AGENT_FAMILIES` has no `bin`; `/.agents/bin` is written as an
   ordinary directory today. (03, 06, 10)
7. `.wasm` is stored as `application/octet-stream`; `application/wasm`
   is the IANA type. (10)
8. `glob` has no `case_mode`, which `find -iname` needs. (02)
9. `ls /.vfs/mounts` answers `not_found` despite the paths module's
   example; the mount table is not in the namespace. (07)
10. `/.vfs/sessions` and `/.vfs/jobs` need posture rules before
    anything is stored there; today every `read` holder at `/` reads
    all of `/.vfs`. (07)
11. There is no public statement counter; the spike spied on the
    engine host's engine directly. (10)
12. `Narrowing` exists with one value, `NONE`; it is the attenuation
    seam when per-program capability narrowing lands. (06)

---

## 13. The five ADRs and their forks

Each fork lists the options and the lean the evidence supports. The
leans are not decisions.

### ADR 1, the shell surface at v1 (study 01)

1. POSIX subset vs rc vs an own grammar. Lean: a POSIX-2024 subset
   parsed by our own parser with named bash-isms admitted. Traffic is
   100% bash-shaped; rc and a new grammar start at zero.
2. Which bash-isms at v1. Lean: `$( )`, backticks, `{a,b}`, `$'…'`,
   `&>` yes; `[[ ]]` in slice 2; arrays in slice 4.
3. Does `set -e` exist. Lean: no mode at v1; `&&` is the agent's
   errexit; `set` is 6 of 67,000 segments.
4. pipefail or rc's status list. Lean: POSIX rightmost status for `$?`
   plus every stage's status on the `Result`, so the renderer can flag
   a masked failure without changing `$?`.
5. Does `&` exist. Lean: refuse at parse time; 0.2% of calls, no
   process to detach, and faking it lies to the model.
6. Static vs run-time refusal of unsupported constructs. Lean: static;
   nothing runs on a refused line.
7. One error or many. Lean: the first.

### ADR 2, the program ABI and the bin namespace (studies 02, 03, 06, 10)

1. Rows, bytes, or both-tagged in the pipe. Lean: both, each chunk
   one shape, two laws at the seams.
2. The structured-to-bytes form. Lean: canonical text by default,
   `to-json` explicit; not JSON lines by default.
3. Verbs only through the capability, builtins included. Lean: yes;
   one door, as a type.
4. Builtins as bin entries. Lean: no at v1; a synthetic program-table
   mount later if agents `ls` the bin directory expecting them. Stub
   files rejected.
5. Per-mount vs `PATH`. Lean: `PATH`; a mounted stranger's bin
   directory must not auto-join.
6. Who may shadow a kernel name. Lean: nobody by write; the host
   promotes by configuration; agents shadow via their own `PATH`.
7. The output row's address. Lean: `/.vfs/run/<id>/stdout`, readable
   later under budget.
8. Per-family exit codes. Lean: yes (1, 2, 124, 126, 127, 130).
9. Which family is `unsupported.form`. Lean: a child of `unsupported`.
10. `sed`, `awk`, `jq` as kernels or wasm. Lean: kernels for the
    measured forms now, wasm for the full language later, same name
    throughout; `jq` as wasm rather than a crate dependency.
11. `find`. Lean: its own program with the predicate grammar, compiled
    to `glob`, `tree` and `stat`.
12. `rg` and `grep`. Lean: one verb, two names, two flag tables, two
    renderers.
13. Bytes-capable programs. Lean: a per-program flag; `wc -c`,
    `base64`, `sha256sum`, `cp`, `tee`, `>` consume `data`; `grep`,
    `sed`, `cut`, `sort` consume the rendering or the placeholder.
14. `ls -la`. Lean: real columns in the long format's positions; never
    fake mode bits.
15. Where programs live. Lean: `/.agents/bin` as a third family.
16. Basename resolution with suffix dispatch. Lean: strip a known
    suffix set; the suffix selects the runtime.
17. What a program's written file becomes. Lean: UTF-8 to `content`,
    else `data`, extension as tie-break; never sniff alone.
18. What a program reads for a media row. Lean: bytes through
    `path_open`, placeholder through stdin.
19. Compiled-module cache location. Lean: host disk keyed on
    `content_hash`; rows under `/.vfs/` left open.
20. The `.wasm` mime. Lean: add `application/wasm`.

### ADR 3, the pipe payload (studies 03, 10)

Decided by the shape above: one ordered stream of chunks, rows or
bytes, values never lazy, laziness only in the channel; row-to-bytes
through the one renderer with the producing op's projection, a single
bytes-bodied read row crossing raw; bytes-to-rows as one row at a
synthetic address; errors never cross a byte seam; bounded queues of
declared depth; a row-shaped consumer that must see everything
materializes and says so; early close reports `cancelled` as info.
One fork: whether a program may declare `consumes: "json"` so `jq`
gets the payload without `to-json`. Lean: not at v1.

### ADR 4, execution policy (studies 06, 10, 04)

1. Execute rung vs per-principal grant vs allow-list. Lean: `run` is
   `read` on the program row; postures and grants do the rest;
   `deny_ops` extended to program names as the one host mask.
2. Pre-flight vs dispatch-only. Lean: dispatch-only at v1;
   manifest-declared verb attenuation later, which is an ABI fact.
3. Limits per mount or per session. Lean: per call with module
   defaults; a mount may tighten, never loosen.
4. Host denies a builtin by name. Lean: programs yes, builtins no.
5. Default posture of `/.agents/bin`. Lean: `read`.
6. One bin directory vs per-agent `PATH`. Lean: one at v1; decide the
   union with the "where does an agent's bundle live" question.
7. The system actor in the shell. Lean: refuse `invalid`.
8. Python vs Rust host for the shim. Lean: Python now with a
   process-wide guest lock, Rust when two programs run at once.
9. One guest per process vs many. Lean: many with the recorded-exit
   rule, and an upstream issue for a thread-local.
10. May a guest see `/.vfs` and `/.agents`. Lean: hide `/.vfs`, show
    `/.agents` read-only.
11. Attribution of a guest's write-back. Lean: the caller's authority
    unchanged, with the program path and revision stamped in
    `source_identity`.
12. Whole-file vs chunked staging. Lean: whole-file with a staging
    budget at v1; chunked reads of large bytes rows as the named
    future.

### ADR 5, the content channel (studies 08, 03, 05)

1. Inline media budget. Lean: 1 MiB per block and 4 MiB per result,
   with a count cap of 8.
2. Accepted image set. Lean: PNG, JPEG, GIF, WebP, the only list a
   studied MCP client publishes.
3. Embedded blob vs link for non-image media. Lean: link only at v1.
4. One text block plus payload vs interleave. Lean: one text block
   first, media after, keyed by path.
5. Implement `resources` at v1. Lean: minimal yes.
6. URI scheme. Lean: `vfs:///`, never `file://` (a client fetching
   `file://` on its own would read the host's disk).
7. The `_meta` prefix. A reverse-DNS prefix vfs owns; decide the
   domain.
8. Bytes in `to_payload`. Lean: never on the wire; an in-process flag
   for the existing round-trip tests.
9. Vendor `_meta` hints. Lean: no at v1.
10. Error-result text shape. Lean: errors first, rows after.
11. Jobs and sessions in the namespace (study 07). Lean: env in
    memory; history an in-memory ring merged with spec 148's
    `surfaced` buffer; one session per conversation with copying
    children; jobs out of scope now, files plus MCP tasks together
    later; both `$?` and `$status`; both a session cwd and a per-call
    `workdir`; a map plus an exported set; the mount table projected
    later as `/.vfs/sessions/<id>/ns`.

### The tool surface (study 09)

One `cli(command)` tool beside the existing gated verbs, never a
second `readFile` around `read`'s ladder; hosts may expose only `cli`
by listing. Output: a byte budget on execution as a classified fact
plus a render cap near 30,000 characters in the text projection with
one canonical marker stating characters removed, rows remaining and
how to page. The coverage metric: the Oils suite fetched at a pinned
commit with real bash as denominator, plus the replayed agent corpus,
plus a negative spec with stable IDs.

---

## 14. The build, in slices, revised by the evidence

The earlier plan put pipes in slice 2. The corpus moves them.

1. **Slice 1, the pipeline core.** The parser (grammar above), the
   verb builtins, the shell builtins, the read-shaped forms of `head`,
   `tail`, `sed -n` and `wc`, pipes with the two laws, `&&` `||` `;`,
   redirections, here-documents, the renderer with the placeholder and
   the render cap, the exit-code table, `$?` and `PIPESTATUS`, the
   session's four fields, the coverage harness. About 87% of segments.
   Depends on the live-tree gaps 1 to 4 and 6. Ships in `0.1.0a1`
   with spec 155.
2. **Slice 2, the text programs as Rust kernels.** `cut`, `sort`,
   `uniq`, `tr`, `nl`, `tee`, `xargs`, `diff`, `base64`, the hash
   sums, the measured forms of `sed`, `awk` and `find`, `rg` as a
   second front end on `grep`. About 89%.
3. **Slice 3, the bin family and the wasm host.** `/.agents/bin`, the
   union resolution, `run` through the preview1 shim with whole-file
   staging, budgets, the cache keyed on content hash, `application/
   wasm`, the first installed programs (uutils' 78, jaq). Python host.
4. **Slice 4, control flow and the first guest.** `for`, `if`,
   `while`, `case`, `[[ ]]` to about 97%; Monty behind the capability
   contract as `python3`; `python3 --version` reports the subset.
5. **Slice 5, growth by table.** QuickJS as `node`; functions and
   arithmetic; CPython-on-WASI when the subset chafes; jobs as files
   plus MCP tasks when programs run long; the Rust shim when
   concurrency demands it. Each addition is a row in a table or an
   entry in a directory, measured by the coverage score.

MCP `serve()` becomes one tool, `cli(command)`, over the same
`Result`, with the adapter from §10 and the minimal `resources`
capability. It can land beside slice 1 or after; nothing in the shell
waits on it.

---

## 15. Corrections to the record and housekeeping

- The July hermetic-runtime memo's "verified end to end" meant
  read-verified. Everything is now executed, and §6 lists what it got
  wrong: two verbs per file, the cache key, the bin path, out of
  memory as an abort, the race at 13%, the wasi dependency-closure
  filter, `path_link`.
- The July multimodal memo's answers all stand; its eleven ADR
  decisions are narrowed by study 08 to the ten forks in §13.
- Monty has moved from 0.0.19 to 1.1.0 with a filesystem story, 23
  stdlib modules, an `os` callback and snapshots; the July memo's
  Monty section is stale.
- Node shipped `node:vfs` in v26.4.0 behind a flag, "not a sandbox";
  the proposal the brief cited has landed.
- The `gemini-cli` clone's working tree holds an unrelated project of
  Clay's and must be moved or re-cloned before any future study.
- Three open-question entries get a researched line pointing here:
  the shell pipe payload, the hermetic-runtime guest bet, the result
  content channel, and the per-path/per-principal execute policy.
  The `serve()` re-spec question gets its answer from §13: one tool.
- A stray `workspace/` directory that a sandbox package created at the
  repo root during study 05 was inspected and removed.

## 16. The Python runtime, after the spike (studies 11, 12 and 13; added 2026-10-16)

§7's lean (Monty first, CPython-on-WASI as the escalation) did not
survive the Python requirement. Study 11 executed every candidate
against numpy, pandas, scipy and matplotlib: only CPython loads the
stack, WASI CPython as shipped cannot (`dlopen not implemented`), and
Pyodide needs a JavaScript host whose runtime is ending. Study 12
executed a native CPython that sandboxes itself with Landlock, seccomp
and Seatbelt: it runs unprivileged in a web server on most hosts, but
its wall is the kernel's and is absent on gVisor, Lambda and Windows.
Clay's reframing (a basic interpreter frozen once a year, not a
tracked environment) made the static WebAssembly build affordable, and
spike 173 (study `13-wasi-python-spike.md`) proved it in an hour:

| fact | measured |
|---|---|
| CPython 3.14.8 + numpy 2.5.2 + pandas 3.0.6 as builtins, pinned sources | builds in ~10 min, **zero upstream patches**, twelve recipe files |
| `import numpy` under the preview1 shim over `InMemoryStorage` | 0 opens of any `.so`, 0 host preopens, origin `built-in` |
| pandas CSV job on the Wizer snapshot (`read_csv` from a row, `groupby`, `to_csv` to a row, 1e6-row groupby) | exit 0, 15 verbs, 93 SQL, 96 preview1 calls, 120 ms, 108 MiB; reproduced by the session |
| cold start per call | snapshot 3.0–4.8 ms; plain reactor 80–120 ms with a cached zip row; first `import numpy` without the snapshot 1.9 s (256 re-stagings of the zip row) |
| kernels vs native | 1.3× (groupby) to 2.3× (`arange(1e6).sum()`), no SIMD, no BLAS, no threads |
| sizes | 39.5 MB `.wasm` numpy (8.4 MB xz); 94.5 MB numpy+pandas snapshot (19.7 MB xz); `.cwasm` 34–111 MB, never shipped |
| the verb door | a 30-line C module calling a custom import bound with `Linker.define_func` |
| matplotlib | gated on C++ exceptions: wasi-sdk 24 cannot link them, wasi-sdk 33 can (both executed); weeks on the CPython 3.15 line |
| scipy | gated on Fortran: f2c as Pyodide does; months |

Two platform facts for the docs: numpy's default integer is 32-bit on
wasm32 (`arange(1e6).sum()` wraps), and a C++ `throw` aborts the guest
on the SDK-24 line. Two host facts for spec 172: Wizer needs a WASI
reactor entry (`_initialize` once, `vfs_run` per call), and
`zipimport` reopens the zip for every module, so the shim must cache a
staged buffer by `(path, version)`. The record is ADR 086 (nine pins,
four leans pending Clay) and spec 172 (four slices).
