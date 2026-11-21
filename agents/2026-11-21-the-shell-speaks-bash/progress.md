# Progress

## Step in hand

Step 2, the crate and its parser. Step 1, the harness, is done.

## Score

0 of 3,320 cases pass: no machine exists yet. All 3,320 parse, or classify as bash classifies them (`crates/vfs-shell/tests/parse_corpus.rs`).

## Done

- **Step 0.** The spec review is `reviews/spec-review.md` (verdict "Not yet", five Highs, six Mediums). The research on bash suites is `research-bash-suites.md`. The research on the WebAssembly runtime is in flight.
- **Step 1.** The recorder is `scripts/shell_record.py`. The referee is `debian:sid-slim` pinned by digest `sha256:07a3205e…`, with bash 5.3.15 and GNU coreutils 9.12, sed 4.9, grep 3.12 and findutils 4.11; Alpine's package mirror is refused by the proxy, so the image is used as pulled and carries no build step. The seed tree is `tests/shell/world/`. The case format is `tests/shell/README.md`. There are 3,320 recorded cases in 38 areas: 2,889 language-tier and 431 program-tier. Every case recorded on its first two runs with equal output. The known-failures list is `tests/shell/known_failures.txt`, the deltas list is `tests/shell/deltas.txt`, and the score is `scripts/shell_score.sh` (`--write` rewrites the list).
- **Step 2, in part.** `crates/vfs-shell` has no dependencies, forbids unsafe code and denies `unwrap`, `expect`, `panic`, indexing, string slicing and unchecked arithmetic. `tests/source_rules.rs` holds the source rules of decisions 1, 4 and 9. The parser is recursive descent with a depth check on every descent. It builds for `wasm32-unknown-unknown`.

## Decided inside the laws

- A case runs as `bash --norc --noprofile -c "$script" bash` in `/work`, as an unprivileged user, with the fixed environment in `tests/shell/README.md`, so `$0` is `bash` and errors read `bash: line N: ...`.
- Bash parses and runs one top-level command at a time, and this shell parses the whole line first. A case about a syntax error puts the error in its first command, so the two agree. Two cases are malformed to bash only because `extglob` was off when bash parsed them; this shell parses extglob always and fails the same way when it runs.
- Refused at parse time, by command name: `eval`, `source`, `.`, `exec`, `trap`, `jobs`, `fg`, `bg`, `disown`, `suspend`, `alias`, `unalias`, and the `coproc` keyword. 35 cases use them; each is in `deltas.txt` and gets the shell's own record once the machine refuses it.
- A here-document body lives in a side table of the script (`Script::heredocs`); its redirection holds the index.
- Arithmetic is parsed when it runs, from expanded text, as bash does, under the line's depth budget.

## Reported and not taken

- The spec review's Highs and Mediums are answered in `reviews/spec-review.md`'s disposition once the machine's design settles them; none was taken as a change to a decision.

## Next

The machine: the step entry, requests and replies, request keys, expansions, the first builtins, and the reference host.
