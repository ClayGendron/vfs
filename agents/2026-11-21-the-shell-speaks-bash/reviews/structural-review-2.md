# Second structural review of the shell, at `046ac73`

A second structural read of the branch, with probes through the real `cli` path on macOS, given to the work on 2026-11-21. It is not a run of the code-review procedure; `scripts/ci.sh`, `scripts/docs.sh check` and the wheel budget were not run by it. Its verdict: the branch is on the right track and not ready for a pull request, because on macOS the shell's test suite hangs and one more test fails, both from real defects of the runtime's integration.

## What it confirmed fixed

The four findings of [the first structural review](structural-review.md), each through the real `cli` path: `cli` runs the module inside wasmtime with a fresh instance a line, fuel, a deadline, a memory limit and traps; the 100-byte recursion ends on the nesting budget (137); the replace loop ends on fuel in 1.6 s; the worst stall of the event loop beside a busy loop is 6 ms; the print loop ends at the 16 MiB output budget; `search` is one `search` verb call, `curl` is 126 with the network hint, `git` is 127 with a hint; `echo x >> f` is one write judged by one stat; the differential fuzzer exists and its five finds are fixed. The Rust tests pass, and the corpus scores 3,187 of 3,332 on macOS.

## What blocks the pull request

1. **`cli` breaks in a process forked after the runtime started, on macOS, and its test hangs the suite.** wasmtime catches traps with Mach ports on macOS by default, which a forked child cannot use, so every line in the child fails as internal; the fix of `ac1d370` works on Linux only. The test lets that error escape in the child, which then runs on as a second copy of pytest and deadlocks while the parent waits on it.
2. **A line started with too little fuel reads as internal, not as a budget.** With fuel 0 or 1,000 the module runs out while it is instantiated, and `Instance::new` turns that into a plain string. It passed on Linux because that build's module spent no fuel there: the toolchain is not pinned, so fuel counts differ between builds.
3. **Two case files differ only by letter case**: `command-V-of-missing-name` and `command-v-of-missing-name`, `.sh` and `.json`, cannot both exist on macOS or Windows, so the corpus runs one case fewer there and a checkout shows two files modified.
4. **The step 3 to 7 review has not signed again** since its fixes.

## What is left in the design

Ranked by concern, each for a follow-up spec:

1. One caller's lines can make other callers' lines wait: 32 lines in a slow pattern match made a concurrent `echo hi` wait 6.0 s, while reads and writes beside them stayed under 150 ms, since a pattern match cannot yield and its slice holds a worker of the shared pool. Give the shell a pool of its own, and bound the lines that run at once.
2. Moving bytes into the module is costly: `cat` of 1 MB spends 412 million instructions and `grep -c` 1.09 billion, so the default fuel reads about 50 MB, or greps about 18 MB.
3. The roadmap's headline example is unbuilt: `grep -r` over 200 files is 202 `read` calls, `find` 203 `stat` calls; `traverse` and `grant` are no commands; 145 cases fail and the weighted sample runs at 72%.
4. `ls -l` and `ls -la` are refused as invalid options, one of the commonest lines an agent types, and no follow-up spec names it.
5. The first line in each process costs about 260 ms and 180 MB of peak memory to compile the module; compiling at build time removes both.

## Disposition

1. Fixed in the commit after `046ac73`: the engine is configured with `macos_use_mach_ports(false)`, so a trap is caught by Unix signals, which a forked child inherits; and the test's child body always ends in `os._exit`, so a failure there can only fail the test. Not run on macOS here.
2. Fixed in the same commit: `Instance::new` classifies a trap at instantiation, and running out of fuel there is `Budget("fuel", …)` with status 137; the test runs with fuel 0 and 1,000. The toolchain is reported in `agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md`.
3. Fixed in the same commit: the upper-case case is renamed `command-upper-v-of-missing-name`, and `tests/shell/test_corpus_shape.py` refuses any two corpus paths that differ only by letter case; `tests/shell/README.md` names the rule.
4. A fresh reviewer reads the fixes and signs before the pull request.

Design: item 1 joins `agents/2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md` as a pool of the shell's own beside the bound on concurrent lines; item 2 is `agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md`, whose figures on Linux after the decoder fix are 269 million and 1.13 billion; item 3 is `agents/2026-11-21-the-shell-serves-the-indexed-verbs/spec.md` and `agents/2026-11-21-the-shell-closes-its-known-failures/spec.md`; item 4 joins `agents/2026-11-21-the-shell-runs-the-standing-program-table/spec.md`; item 5 joins the boundary spec, with build-time compilation.
