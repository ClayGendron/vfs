# 167 — tasks

Five slices, landing in order: A, B (A and B are independent), C, D, E. Each task lands green (`scripts/ci.sh`). C and D run the four engine legs before landing.

## Slice A — the renderer and the vocabulary (spec §1)

1. **`run` out.** Remove `run` from `Op`, `EXEC_OPS` (the class goes), `VERB_RUNGS`, `PARAMS`, `_DEFAULT_PROJECTION`, `base.py`, `session.py` and `README.md`. Delete `SupportsRun` from `protocol.py`, `_FAMILY_OPS` and `storage/__init__.py`. Move every test that used `run` to a live op (the file list is §1 item 2).
2. **The placeholder.** Add it in `_render_read`, `_render_block` and `_format_field`, replacing the bare `vfs.unavailable` line. Tests pin the grammar byte-for-byte.
3. **The budget and the spec 155 markers.** Add `budget=` on `render_result` and `to_str`, the marker, and `RENDER_CHARACTER_BUDGET`. Add the empty markers, the slash, the collapsed errors and `rank` for the verb tools.
4. **`to_payload(include_bytes=False)`.** Update the envelope docstring and the producer-exclusivity note in `kinds.py`.

## Slice B — the parser (spec §2)

5. **Kinds.** Add `vfs.invalid.syntax`, `vfs.unsupported.construct` and `vfs.unsupported.form`, with contracts. Add the caret block in the display.
6. **Lexer and parser.** Tokens, the quoting table, the AST, `time`, redirections, here-documents, lists, subshells and groups, the refusal set, and the parser budgets. Add the parse-level spec tests (`quoting`, `expansion`, `redirect`, `heredoc`, `pipeline`, `lists`, `errors`, `refused`) and the study 01 corpus criterion.

## Slice C — the pipe, the ABI and `cli` (spec §3, §5, §6, §7)

7. **ABI.** `Program` with `shapes(args)`, `Call`, `Forms`, `VirtualFileSystem.bound(authority) -> Fs` (absolute paths only, the admitted authority), and `shell/status.py`.
8. **Runner.** Stages, queues, the plain projection, stderr routing, early close, redirections, here-documents, `$( )`, the expansion order, state scope, statuses, and budgets with an injectable clock.
9. **The `cli` Result and its display.** Cases (a) and (b), the extras, the verdict, the cap and the `cli` render branch.
10. **The minimal programs** (spec §4, slice C's set), each with its forms table and `--help`.
11. **The session and the entry points.** `VirtualFileSystem.cli` (fresh per call), `Session.cli` (cwd, env, status, history; the lock), the system-actor refusal, the default env, and `MANAGEMENT_METHODS`.
12. **The oracle fixtures for slice C.** Add the pinned-image script and the committed fixtures. Add the stdout spec tests of criterion 15.

## Slice D — the program forms (spec §4, §4.1)

13. **`copy` and `move` gain `overwrite=`** on the router, params, protocol and both backends, with all five engine legs.
14. **The remaining verb builtins**, by the §4.1 table, with oracle fixtures. This includes `restore`, `glean` and `graph`.
15. **The read-shaped text forms** in Python: `head tail sed wc cut nl`, with the shared BRE-to-ERE function and the sed replacement grammar.
16. **The remaining shell builtins**, `set -e` and its spec-test file.
17. **The never table** with its hints.
18. **`glob(case_mode=)`** on the protocol and both backends, with the per-dialect prefilter, all five engine legs and a scale review.

## Slice E — the coverage harness and the docs (spec §8)

19. **Coverage harness.** The synthesized corpus and the four rates.
20. **Docs.** Add `docs/reference/shell.md` (the grammar, the program table with forms, the exit codes, the refusal table). Update the README verb table. Mark specs 148 and 155 folded.
