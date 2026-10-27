# 084. The gate order is the execution policy: executing a program is `read` on its entry, a program never holds more than its caller, and budgets are facts

- **Status:** proposed 2026-10-15. Resolves the open question
  "Per-path / per-principal execute policy" (2026-07-11) and
  supersedes the archived spec 039's rights set. Amends ADR 080 pin 9
  ("`run` on its own axis": there is no `run` and no axis). Feeds specs
  167 and 169. Depends on ADR 082.
- **Date:** 2026-10-15
- **Amended 2026-10-15** after the pre-build review of spec 169 and Clay's answers: the install directory's posture and the `add` grant (pin 7); masking lives in the index; kill exit codes (pin 8).
- **Deciders:** Clay Gendron
- **Decided by:** AI-with-approval (the assistant drafted the rule
  from the study's evaluator; Clay ruled that tools follow the regular
  posture rules and that a session may prepend its own search order)

## Context

The memo (§8; study `06-execution-policy.md`) read every harness that
decides whether a command may run:

- Codex judges an argv with Starlark prefix rules whose verdicts are
  allow, prompt and forbidden, strictest wins; Claude Code evaluates
  deny, ask, allow patterns per subcommand; gemini-cli hard-denies
  command substitution and keeps prefix lists; opencode scans with
  tree-sitter and goes opaque on substitution, heredocs and dynamic
  names. Each says in its own docs or code that the string match "isn't
  a security boundary around the program". The real boundary in every
  one is an OS sandbox over paths and hosts, enforced while the command
  runs. deepagents states the gap as a `NotImplementedError`: path
  permissions plus an execute backend are rejected "because shell
  commands bypass path rules".
- Anthropic's sandbox-runtime and Cloudflare's sandbox-sdk have no
  command policy at all; they police resources.
- Plan 9 has no exec allow-list and no setuid. `OEXEC` is "read, plus
  check execute permission"; the file server enforces the bit; a
  restricted service is a namespace file that binds in only what it
  needs.
- In vfs today: `run` sits at rung `read` in `VERB_RUNGS` but no gate
  reads it, because no storage implements it; `_gate_entry` applies
  permission layers only to write-gated ops; `deny_ops` masks
  mutating and exec verbs per mount and refuses read-family ops;
  `Authority` is frozen and re-derived per call, with a `Narrowing`
  enum whose only value is `NONE`; the four construction doors for an
  authority are vfs-only.
- A table-driven reference evaluator ran 33 cases, from `rm -rf /` to
  a program writing into the bin directory, and every verdict was a
  kind the envelope already has.

## Options considered

- **Dispatch-only: the gate order is the policy, `read` on the entry
  to execute, budgets as facts (chosen).** Pros: no second source of
  truth; nothing a command can do escapes a verb's gate; the parked
  question dissolves. Cons: a host that wants "prompt me" must do it
  in its own tool-permission layer.
- **A rights set with `execute` (spec 039).** Rejected: user-blind, a
  second dimension the total order cannot hold, and "readable but not
  runnable" is already a namespace fact.
- **An `execute` level above `read_write` in the grant ladder.**
  Rejected: it would say "you may trash everyone's rows but not run
  `wc`"; execution is not more dangerous than any verb the program
  can call, because the program holds no more than the caller.
- **A command-string policy language.** Rejected: every peer that has
  one says it is not a boundary; vfs has nothing to lift and no human
  on the call.
- **A program allow-list on the mount.** Rejected: namespace binding
  and entry postures already express it.

## Decision

Nine pins.

1. **The pinned gate order is the execution policy.** Capability, then
   grammar, then permission, fired on every verb a command resolves
   to. The only pre-flight work is resolving the program (itself a
   gated `stat` and `read`), refusing over-shape input, and setting
   budgets. No verdict is passed on the command text.
2. **Executing a program is `read` on its entry.** ADR 080's rule is
   that a verb's rung is the field it reads; executing reads the
   program's body. A caller who can `list` but not `read` an entry gets 126; one who
   cannot list it gets 127. The `read` is issued on every run, a cache
   hit included. Per-principal execution
   is a `read` grant on the entry; "runnable except these paths" is a
   `list` posture on the directory; a program nobody should see is not
   on the index. Tool and MCP entries follow the regular posture rules
   at their paths; no special default.
3. **A program never holds more than its caller.** Its capability is
   the verb set closed over the caller's `Authority`; there is no
   parameter through which to widen it. Tools are the one stated
   exception: a host-registered function runs with the host's own
   authority by the host's choice at registration, and receives only
   the caller's capability from vfs. `serve()` refuses the system
   actor for every served call, including a router whose default
   authority is the system actor; `cli` refuses it in process. It may hold less later through
   `Narrowing` (a manifest-declared verb set is an ABI fact, not a
   policy fact). The `cli` meta-verb refuses an authority whose actor
   is the system principal, classified `invalid`.
4. **No `ask` inside vfs.** vfs allows or classifies. A host that wants
   a human in the loop uses its own tool-permission layer; the static
   parse of ADR 081 gives it an exact summary of which programs,
   verbs and paths a call names before anything runs.
5. **The budget set**, each a declared constant with grep's
   discipline: `STAGE_BUDGET` 64 stages per line and
   `ARGV_BYTE_BUDGET` 128 KiB refuse `invalid` before anything runs;
   `FANOUT_BUDGET` 10,000 paths per stage and `STDOUT_BYTE_BUDGET`
   4 MiB per stage serve what fits and warn
   `budget_exhausted.truncated` naming the budget and the refine move;
   `WALL_TIME_BUDGET` 10 s per command line trips `timeout` (exit
   124); `FUEL_BUDGET` 2 × 10⁹ instructions and `VERB_CALL_BUDGET`
   10,000 dispatches per program run trip `budget_exhausted` (exit
   137); `MEMORY_BYTE_BUDGET` 256 MiB bounds host memory, and a guest
   that hits it aborts (exit 134; the host cannot tell out-of-memory
   from a panic); `STAGING_BYTE_BUDGET` 256 MiB answers `FBIG`. A fan-out over budget is never a refusal. A
   truncation never drops a row it has started. The epoch deadline does
   not cover time inside a verb, so the verb budget is part of the run
   budget. An `xargs` batch is one dispatch against
   `VERB_CALL_BUDGET`; a text kernel's buffered bytes count against
   `MEMORY_BYTE_BUDGET`; `diff` honours the line's deadline inside the
   kernel. Tests count operations; the clock is a kill switch, never an
   assertion.
6. **Limits are per call with module defaults, tightenable per node and
   per call; a mount-level seam is deferred.** Session-wide counters
   are not in v1.
7. **Installing a program is `write` under the ladder.** The default
   directory is created by the host as the system actor at posture
   `read`, so a fresh name needs an `add` grant; an occupied name is
   `contribute` or own; delete is `read_write` or own; every overwrite
   a version, so a bad install is one `restore` away. A kernel name not in the host's `prefer_stored` set may not be
   installed over: `invalid`, refused at write time for `write`,
   `copy` and `move` into an indexed program directory.
8. **A host may mask an installed program by name** through the
   index's `masked` set (not `deny_ops`, which is a verb mask),
   classified `unsupported` like a masked verb. Builtins cannot be
   masked by name: a builtin is reachable only through its verb, and
   masking the name without the verb would lie about capability.
   `deny_ops` does not reach tools: a host masks a tool by not
   registering it or by posture on its entry. A
   kill by memory, fuel or verb-call budget gives the stage exit 137;
   a deadline gives 124.
9. **The classified refusals need no new kind.** `unrecognized` (no
   such program; a developer-plane word), `unsupported` (undeclared or
   masked verb or program; a capability the kernel lacks, such as the
   network), `invalid` (a mutation into `/.vfs`; shadowing a builtin; the system
   actor; over-shape input; a non-wasm row run as a program), `read_only`,
   `permission_denied`, `not_found`, `unauthenticated`, `busy`,
   `budget_exhausted.truncated` (warning), `timeout`,
   `budget_exhausted`, `cancelled`. Two kinds gain a producer: the
   shell emits `truncated`, the runtime emits `budget_exhausted`.

## Consequences

- Both halves of the parked execute-policy question close with no new
  rung, no new level and no new verb. Spec 039 stays archived.
- `rm -rf /` is `busy` at a bind site and the trash elsewhere; `sweep`
  never parses; `curl` is `unsupported`; a program writing into the
  bin directory is judged by the caller's rung there.
- The ops module's and ADR 080's "waits for its own axis" wording goes
  with the verb.
- The `Narrowing` seam is the place for per-program attenuation when
  a manifest declares the verbs a program needs.
- Hosts that prompt keep prompting in their own layer, with better
  information than a string match gives them.
