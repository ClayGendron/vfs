# The shell matches patterns and regular expressions in time linear in the text

A draft, written on 2026-11-21 from the prior-art memo of the shell (`agents/2026-11-21-the-shell-speaks-bash/research-prior-art.md`, sections 2 and 5). It is not reviewed, and nothing is built.

## The outcome wanted

`[[ $x == *a*a*a*a*a*a*a*a*b ]]` over 100,000 characters, `shopt -s extglob; [[ $x == *(*(a)) ]]` over 3,000, `${x//a*b/}` over 20,000, and `[[ $x =~ ^a*$ ]]` over 5,000 each answer in milliseconds, as bash 5.2 answers them in 0.009 to 0.055 seconds, instead of spending the line's fuel or failing a regular-expression search for depth.

## Builds on

The machine's pattern matcher (`crates/vfs-shell/src/machine/pattern.rs`) and regular-expression engine (`crates/vfs-shell/src/machine/regex.rs`). Both backtrack under a step budget and a depth cap; a search that spends its budget fails, and never answers "no match".

## The problem

Measured through `fs.cli` with the module carried: the first two patterns above end on the fuel budget of 20,000,000,000 instructions; `^a*$` over 5,000 characters fails for depth. Bash's own matcher answers each at once.

## Decisions

1. A glob with only `*`, `?` and bracket expressions is matched by the greedy-star algorithm that backtracks to the last star alone, in O(n·m).
2. Extglob groups are matched over a memo of (node, position), so each pair is decided once.
3. `=~` gains a Pike-style simulation of the same syntax tree for leftmost-longest matching with groups; the backtracking walk stays for back-references only, should they be added.
4. The step budget stays as a backstop and still fails the search, never answers no match.

## Tests

A counted law per form: the number of matcher steps on the inputs above is below a declared bound that grows linearly when the input doubles.

## Scope

The two engines in the crate; no host change.

## Not checked

The cost of a Pike simulation against the current walk on the corpus's ordinary patterns.

## Choices to confirm

None.

## One line

No pattern a line can write makes the shell's matcher take more than time linear in its text.
