# A piped `while read` consumes each listing page through a bounded byte pipe

A draft, written on 2026-11-25 and checked against `dev` at `27f3d24d`. It is not reviewed, and the counted tests are unbuilt. This is the remaining part of [roadmap story F7, gate b](../../context/standards/roadmap.md), criterion 1, converted from [the shell pipeline core](../../context/specifications/archive/167-the-shell-pipeline-core/spec.md) and [its runner task](../../context/specifications/archive/167-the-shell-pipeline-core/tasks.md). It rests on the built shell and listing cursor and on unit 167-5's paged `ls`.

## The outcome wanted

An agent runs `ls /d | while IFS= read -r line; do printf '%s\n' "$line"; done` over 10,000 files. Each name arrives once, in listing order, with its spaces and backslashes intact. The listing arrives in ten pages at the proposed default. A reader that pauses long enough to fill its pipe makes the producer wait. Reading the next line of the pipe costs no filesystem call.

## Builds on

- [The shell speaks bash](../2026-11-21-the-shell-speaks-bash/spec.md), built on dev. Decisions 4, 10 and 17 put effects through the admitted host, `read` inside the machine, and loop iterations and function depth under declared limits (`src/vfs/shell/host.py:59`, `crates/vfs-shell/src/machine/mod.rs:61`). Its [F7 acceptance](../2026-11-21-the-shell-speaks-bash/acceptance.md) covers the language constructs, functions, arithmetic, arrays and bounded background jobs. The recorded [piped loop](../../tests/shell/cases/while/while-output-piped.sh) pins the language result. The parser and program-table conversion remainders are independent.
- [A listing comes back a page at a time](../2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md), built on dev, supplies the public cursor in decision 1. [Unit 167-5](../2026-11-25-a-pipeline-runs-gated-verbs-through-cli-with-the-minimal-programs/spec.md) is a conversion draft, unbuilt. Land its paged listing first. Decisions 1–3 supply a gated call per page, `LISTING_PAGE` (proposed 1,000 rows) and the continuation key. Decision 7 requires “writing each page to its standard output before it asks the next”. Decision 13 gives the native test host `list_page`. Both tests below consume this one implementation.
- [A line has a verb budget](../2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md), specified on dev, decision 1 counts “every request it sends”. [An interrupted line replays its replies](../2026-11-22-an-interrupted-line-replays-its-replies/spec.md), also specified, decision 11 journals each host value as given and takes the process id as input for D54. D60 remains open against memory restoration on `origin/a-call-is-interrupted-and-the-host-asks` (interrupt spec, decision 18). Either order with the counted tests is valid.
- [The shell acts as bash where it refused](../2026-11-22-the-shell-acts-as-bash-where-it-refused/spec.md) is specified on dev. The 2026-11-22 ruling supersedes the D47 and D48 refusals. [The descriptor spec](../2026-11-22-shell-descriptors/spec.md), decision 3, owns reads of a record longer than the pipe and an unterminated final record. These tests use newline-terminated records shorter than the pipe, so neither change is a prerequisite.

## The problem

Today the host issues one `ls` without `after` or `limit` (`src/vfs/shell/host.py:429`), and the producer builds its output before writing it (`crates/vfs-shell/src/programs/files.rs:150`, `:173`). Even a correctly printed directory cannot show whether the producer read ahead or whether the pipe exceeded its bound between machine steps. The reference deployment has directories with thousands of children.

On file-backed SQLite and disposable Postgres, a named caller ran the line above over 1,019 distinct names of 128 ASCII bytes including an interior space and a backslash. Both runs returned the complete expected bytes, empty stderr and `statuses == [[0, 0]]`. Each host trace held one `stat` and one unpaged `list` of all 1,019 rows. The same caller's direct cursor calls at `limit=509` returned 509, 509 and 1 rows on both engines. A separate SQLite run returned all 70,000 output bytes for 10,000 six-character names, and ten direct pages of 1,000. These were separate shell and cursor runs on dev.

## Decisions

1. **Count a chunk at the producer's page reply and count queued bytes at the pipe.** Follow the cursor through the last page, including a short final page. A page boundary adds no bytes and ends no shell record. The builtin reads through the newline on its pipe descriptor (`crates/vfs-shell/src/machine/builtins.rs:627`). F7's literal depth of two chunks described the archived queue of row batches. Unit 167-5 replaces that queue with the machine's existing byte bound, `PIPE_CAPACITY` (`crates/vfs-shell/src/machine/io.rs:16`). A pipe may hold names from several small pages. Neither the number of reads nor the number of writes measures occupancy.
2. **Measure the largest actual pipe buffer and observe a blocked write in the native test build.** In `machine/io.rs`, keep two private, per-hub test values under `#[cfg(test)]`: the maximum `state.buffer.len()` after a successful append and a flag set when a live writer returns pending for zero room (`io.rs:350–368`). The fixture creates exactly one pipe. Retain these values until the test inspects them. A pause between calls to `Machine::step` alone could miss a fill and drain within the same step. The values add no wire fields, runtime counters or public API.
3. **Hold the reader at one identified host request to force backpressure.** In the native run, put `test -f /release` immediately before the loop in a brace group on the right of the pipe. Hold only that `Stat` reply and serve the listing normally. Once the first page has provided more than a pipeful of bytes, the blocked-write flag must be set, the peak must equal `PIPE_CAPACITY`, and only the first page may have been requested. Release the reply and drain to completion. A new page request before the release fails the test. This uses the keyed reply interface (`crates/vfs-shell/src/machine/mod.rs:388`) and the builtin's existing stat request (`crates/vfs-shell/src/machine/test.rs:45`), so no sleep or scheduler hook is required.

## Cost

At the [reference deployment](../../AGENTS.md), the median directory has two files. For a stable directory of visible children on one native mount, the fixture shape costs `max(1, ceil(children / LISTING_PAGE))` public listing calls plus the producer's operand check. The median costs one page, the 10,000-name fixture ten at the proposed default. The loop spends one admitted iteration per delivered record under `loop_iterations` (`crates/vfs-shell/src/machine/exec.rs:702`), with zero host requests per pipe read. Input space grows with one listing page and its formatted bytes, at most `PIPE_CAPACITY` queued bytes and the current short record. It is independent of the number of pages. Output accumulated for the caller has its own `output_bytes` bound. This unit adds no SQL, bind parameters, locks or transactions on either engine. The generic floor retains the listing cursor's derived-page cost. Test instrumentation uses constant space per line and is absent from the shipped module.

## Tests

After unit 167-5, write the two tests first. The unpaged baseline above supplies the failing page count.

- `tests/shell/test_host.py::test_while_read_consumes_each_listing_page` uses the existing host spy pattern at `tests/shell/test_host.py:142`. Seed 10,000 six-character names on one mount under a named caller, in reverse listing order. Compare stdout byte for byte with the sorted fixture, stderr with empty, success with true and the pipeline statuses with `[[0, 0]]`. Count every public `ls`, verify the caller, limit, reply size and key chain starting at `None` and ending at an absent `next_after`. Expect ten replies of 1,000 at the proposed default and calculate the expectation from the declared page size. Require the host trace to contain only the producer's operand `stat` and its page requests. This detects both a whole-directory read and any dispatch of the loop's `read`.
- `crates/vfs-shell/src/machine/mod.rs::tests::while_read_drains_a_full_pipe_across_listing_pages` drives the real machine with `MemoryHost::answer_keyed`. Use fixed-width, newline-terminated records of 129 bytes with distinct numeric prefixes, a space and a literal backslash. Set the fixture page size `P = PIPE_CAPACITY / 129 + 1` using integer division, and seed `2 * P + 1` names. Follow decision 3. Fail on a stopped machine or a step that is waiting only on the withheld reply before the full-write witness; step past ordinary slice yields. After release, require page lengths `[P, P, 1]`, peak exactly `PIPE_CAPACITY`, exactly the seeded records in order, empty stderr, exit zero and `[[0, 0]]`. At today's capacity, filling the pipe splits one record four bytes after it starts. This pins both halves of that record without assuming that a page is one pipe write.

## Scope

In scope are the two named tests and test-only observations in `crates/vfs-shell/src/machine/io.rs`. Unit 167-5 owns the listing protocol, producer, page budget and early close. General descriptor behavior, grants, parser changes, verb-call accounting and durable resume stay with the work under Builds on.

## Not checked

The paged shell and its test-only peak counter are unbuilt, so their combined trace was not run. An independent bounded-buffer prototype fed the three real cursor pages from each engine through a 65,536-byte buffer. It reached capacity twice and reproduced every record. Separately the dev WebAssembly machine, driven with one synthetic 509-name listing, emitted zero output while the reader's stat reply was held and reproduced all names after release. This exercised the pause without measuring the machine's private occupancy. The full suite was not run for this specification.

## Choices to confirm

1. **Where the byte peak is visible.** Take test-only observation in the Rust crate (decision 2). Exporting per-pipe statistics to every host would make measurement a runtime interface. The private counter can be removed or exposed later without changing a caller's result.

## One line

A paged listing feeds `while read -r` in order, and a counted full pipe stops the next page request until the loop can read again.
