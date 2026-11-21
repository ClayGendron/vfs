# Structural review of the shell, commits `c3fb99c..10224a7`

A structural read of the nine commits `c3fb99c..10224a7` (about 26,000 lines outside the case files), with probes run through the real `fs.cli` path. It is not a run of the code-review procedure. It was given to the work on 2026-11-21, after step 6 was committed, and it redirected the work. Its verdict: the crate is on the right track, the vfs integration is not, and the branch does not go to a pull request yet.

## What holds

- The shape matches the spec. The three parts point one way, the crate has no dependency and no vfs name, and the machine does no IO behind its one `step(replies)` entry.
- A request key is a function of the line: the task's path in the walk and an ordinal, held by law tests.
- The harness is real: 3,319 cases recorded against a digest-pinned bash 5.3.15. The crate's tests pass; the score is 3,178 of 3,319 (95.8%).
- The WebAssembly module exists and its laws pass under a test runtime: fuel stops an endless line, and the memory limit ends the call, not the process.
- `progress.md` reports what was not taken, including the first finding below.

## Findings

1. **vfs runs the native build, so the ruled design is not what ships.** Fuel is ruled to be counted instructions, which needs the WebAssembly runtime; step 6 wired `cli` to the native machine, which has no fuel, no deadline and no trap. Measured through `fs.cli`:

   | Line | Result |
   |---|---|
   | a function recursing 160 deep through `$( ( { if … case … } ) )`, about 100 bytes | the Python process dies with SIGSEGV; the function-depth budget of 256 never fires |
   | `while :; do y=${x//0/1}; done` with a 1 MB `x` | still running at 20 s; no deadline exists |
   | `while :; do :; done` | the event loop stalls 1.4 s; every other caller waits |
   | `while :; do echo "$x"; done` with a 1 KB `x` | 1.0 GB of stdout returned; the process reaches 2.0 GB |
   | `grep -cE "(a*)*b"` over 300 short lines | the event loop stalls 5.7 s |

   The machine yields at four places only (commands and loop bodies), never inside an expansion, a builtin or a program, and the binding holds the interpreter lock for every slice.
2. **The program seam was dropped.** The spec has the host resolve every program, with a request to start one and to feed or pull its chunks. What was built is a fixed table of 18 names inside the crate, with no program request. vfs cannot add `search`, `traverse` or `grant` as commands, which the roadmap requires. `curl` answers `command not found` (127), not the classified refusal the roadmap names (126). `grep -r` cannot use the indexed `grep` verb: 200 files cost 200 `read` calls, and `find` costs 202 `stat` calls; the roadmap's `grep -rn mfa /enterprise` at ten million files is ten million calls with every body held for the line. A second host cannot mount a program without editing the crate. The fix grows with every program written against the machine's internals.
3. **Each redirection is two writes.** `echo x >> f` issues two `write` calls, a truncate-or-create and then the append. The roadmap pins one.
4. **The run did not follow its own rules.** Only steps 1 and 2 have a committed review, its verdict is "Does not land yet", the dispositions left several findings not taken, and the reviewer never signed again. Steps 3 to 7, including the edits to `base.py`, `session.py` and `sync.py`, have no committed review. The differential fuzzer was not built and the Oils rate was not measured, so the 95.8% is graded only by a corpus the same run wrote. CI has never run on the branch, since a push without a pull request does not start it.

Smaller: compound commands carry no span; 40 nested `$( )` are refused as depth 200 where bash runs them; the regular-expression engine gives up silently at its step budget instead of failing.

## Recommendation

Stop reducing the remaining 141 known failures and take these, in order: carry the runtime and run the module in `cli`, with a deadline and an output cap in the host; restore the host-resolved program request; one write per redirection; build the differential fuzzer; review steps 3 to 7 with a fresh reviewer. Carry `wasmtime` rather than `wasmi` if it is faster and serves the use.

## Disposition

Awaits the work: one line per finding, with the commit that closes it or the reason it stands.
