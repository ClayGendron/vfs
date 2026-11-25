# Verification of the nine shell contracts against the code

Each problem and regression case of the nine specs under `agents/2026-11-22-shell-*` was run on 2026-11-22 against `dev` at `5a823ea`, which includes the served `grep -r` and `find` of `agents/2026-11-21-the-shell-serves-the-indexed-verbs/`. Four independent checks ran: through `fs.cli` on an in-memory `AsyncVirtualFileSystem` with postures and grants, through the native `MemoryHost` in temporary crate tests, and through the wasm module under wasmi for the wire. The references were local bash 5.2.21, GNU coreutils 9.4, GNU grep 3.11 and GNU sed 4.9, not the pinned bash 5.3 and coreutils 9.12 of `scripts/shell_record.py`; a case that depends on the version is marked. The scripts sit outside the repository and were not kept. The rulings that followed are at the end.

## The verdict, one line each

| Spec | Its problems | Its design |
|---|---|---|
| Wire and instance lifecycle | Real in the decoder; one reachable from the product | Mostly serves third-party hosts, which are ruled out |
| Runtime termination | All real | Sound |
| Parsing and memory | All real but one | Sound, with two claims corrected |
| File reads and metadata | All real | Over-built; replaced by the public `read` per open and session stamps |
| Descriptors | All real | Sound locally; its writer guard replaced by session stamps |
| File operations | All real, and the worst of the set | Sound locally; its guarded removal replaced by session stamps |
| Sed edits | All real | Sound; its publication rides `if_version` and session stamps |
| Filters and matching | All real but one | Sound; decision 4 narrows to glob consumers |
| Builtins and variables | All real | Sound locally; positive `read -t` needs no timer protocol |

## Wire and instance lifecycle

- Escaped UTF-16 halves are decoded one at a time: `"😀"` becomes two U+FFFD, and a lone or reversed half is accepted. Reproduced in the guest decoder. Not reachable from the product: the only encoder is `wire::quote`, which writes non-control characters raw, and Python never writes the JSON.
- Integers pass through `f64`: `9007199254740993` decodes as `9007199254740992`, `1.5` as 1, `-5` as 0, `1e3` as 1000. Reproduced, and reachable: `run_line(limits=...)` admits values to 2^64, which cross `encode_start` into the guest.
- A second start on an active instance: a malformed or failing one leaves the old line active, and a valid one silently replaces it. Reproduced under wasmi. Not reachable: the binding starts every line in a fresh instance.
- A malformed mutation record decodes leniently: a write with no data is an empty truncate, an unknown mode is truncate, bad base64 characters are skipped, a duplicate key keeps the first. Reproduced.
- The output range is copied after a bounds-checked `memory.read`; the host allocates `out_len` first. Not testable without a hostile module; no unchecked pointer exists.
- Already as decision 4 asks: a step on an idle instance, a terminal step clearing the machine, idle after a failed first start, idempotent cancel. Decision 2's discard-and-internal already happens when `decode_step` fails.

## Runtime termination

- The deadline is snapshotted before the work is queued, and a verb is awaited without it: four 1-second reads under a 0.3-second deadline were dispatched at 0.02, 1.03, 2.04 and 3.05 seconds, and the line ended at 4.06 seconds with 124. A slow write committed and the line then reported 124. Reproduced.
- Encoding holds the GIL: 50 MB of stdin stalled a 1 ms ticker thread for 135 ms, and the guest's `Vec<char>` reader spent the 256 MiB module memory. Reproduced.
- A fatal budget in a background job becomes status 1, the line continues, a later write lands, and the line reports success. Reproduced; the same loop in the foreground ends at 137.
- `search -n`: 0, a word, -1 and a non-ASCII digit are usage errors already; 2147483648 is dispatched and refused by the verb; a 5000-digit value raises `ValueError` out of `run_line`. The code moved to `src/vfs/shell/programs.py`.
- Invalid `fuel`: -1 and 2^64 raise `OverflowError`, 1.5 and `"10"` raise `TypeError`, `True` is accepted as 1. Reproduced.
- Startup stops: a deadline at startup is `internal`, exit 2; fuel at startup is exit 2 and during a step 137. Reproduced.
- A fork during cold initialization hangs the child until its alarm; a warm fork works. Reproduced.
- The `slice` limit does nothing in the product, as the wasm build replaces the counter; `fuel_slice` 0 already never yields a permanently empty step. Reproduced.

## Parsing and memory

- A double-quoted here-document delimiter with an expansion, `"E$x"`, keeps only its literal parts, so body text runs as commands: `echo INJECTED` ran. Reproduced; listed as `found/here-document-delimiter-from-an-expansion-is-literal`.
- Memory charges: a subshell releases its parent's charge (23,751 to 3,752 to 0 while `a` holds 20,000 bytes), a function's locals are never released, and an associative map's 1,024 buckets are uncharged. Reproduced.
- Repeated `printf` and `tr` repetition build their whole temporary before any charge and fail on module memory; a single `printf '%*s'` is charged first. Partly reproduced.
- Expanded arithmetic uses the fixed `PARSE_DEPTH`, not the configured depth. Reproduced, but a bound exists: the claim of an unbounded native stack is false; 200,000 parentheses give an arithmetic error at exit 1.
- Deep `!` and nested builtins overflow the native stack; in wasm they are classified 137. Reproduced natively.
- The final here-document's subparser adds its tokens unchecked. Reproduced.
- The pipeline-stage allowance counts the final stage; only a limit of 0 admits one command. The claim holds at 0 alone.
- `a[1 + 1]=x` is a command not found; so are `a[$(( 1 + 1 ))]=x` and `a[$(echo 1 2|wc -w)]=x`. Reproduced.
- `declare -f` prints a function that does not parse back. Reproduced.
- The debug corpus overflows its stack with `RUST_MIN_STACK` unset. Reproduced.

## File reads and metadata

- A range read fetches the whole body: `head -c 10` on a 5 MiB file is one router read of 5,242,880 bytes and 80 ranged requests answered from the cache; `head` with a file operand reads the whole file into the module. `ls` over 3,000 children is one unpaged call. Reproduced.
- The cache is keyed by path: `cat f; cat f` around another caller's edit prints the old body twice with one router read, and around a revoke prints the secret twice. Reproduced.
- After the cache forgets, a reader's next chunk comes from a newer version: `{ read -r x; touch z; grep -c ^A; } < a` mixed two versions. Reproduced.
- The cache scans every held path on each insert (200 empty files, 20,100 visits; 400, 80,200) and charges keys and empty bodies nothing. Reproduced.
- Warnings on a successful partial `ls` or `glob` are dropped. Reproduced.
- `test -r`, `-w`, `-O` and `-G` mean "exists"; `-nt` and `-ot` compare existence only. Reproduced.
- False: acceptance criterion 2's "a guarded write after delete/recreate with the same numeric version". Versions count across a delete and a re-create (v1, v2, delete, v4), and a move onto a tombstoned path is refused `exists`. The real hazard is a move that frees the path: moving `/x/p` away and then writing, moving or copying another file to `/x/p` gives a different entry at the version the caller saw, and `write(if_version=...)` overwrites it. Reproduced four ways.
- Self-contradictory: decision 5 names the field `modified_at`, its table `updated_at`.
- Duplicated: paging restates the public `ls(after=, limit=)` and the listing cursor; `exact_bytes` restates spec 178's byte ranges, which a byte-exact reader cuts locally.

## Descriptors

- Two output redirections whose first is refused: with `echo`, the second is created or truncated anyway. Reproduced on the deferred path only.
- A refused writer appends later: under `noclobber`, another caller's file created in the window received 1,048,576 bytes of the failed writer, and a refusal after one accepted chunk still let later chunks land. Reproduced.
- A refused final flush through `{fd}>` exits 0 with an empty file. Reproduced; `exec 3>f` is refused at parse, so `{fd}>` is the only persistent form.
- A refused chunk reads as EOF. Reproduced.
- A delimited read of a 64 KiB-plus record ends the line "the line waits on nothing", as does `mapfile`. Reproduced.
- `lastpipe` with an early-exiting reader ends the line the same way. Reproduced.
- A fifth process substitution takes the first one's descriptor, an occupied fd 62 is replaced, and `/dev/fd/63` leaks past its command. Reproduced.
- `echo hi > >(cat)` spends its fuel; output substitutions run only after their producer. Reproduced.
- `|&` duplicates stderr before the stage's own redirections. Reproduced from the manual; bash not run.
- `{ head -n 1; cat; } < f` prints the first line only. Reproduced.
- `tee` holds its whole input and opens targets at EOF; `-p` is ignored; unknown options become file names. Reproduced.
- A successful writer follows the path: after a delete and re-create, or a move away and a move in, later chunks land in the other file with status 0. Reproduced.

## File operations

- `X=; rm -rf "$X"`, `rm -rf .`, `rm -r ""` delete the working directory, `rm -rf ..` its parent, `deep/.` and `deep/..` their resolved directories, with status 0 and no message, on both hosts. Reproduced. The root is already refused on both.
- `rm -i`, `rm -ri` and `rm -I` with the answer `n` or EOF delete everything. Reproduced.
- `cp -i`, `mv -i` and `cp -u` record nothing; production refuses an occupied target with `File exists`, so it loses nothing, while `MemoryHost` replaces it, and `mv deep full` over a non-empty `full/deep` destroys its child. Reproduced.
- GNU coreutils 9.4 exits 1 on a declined `cp -i`, not 0 as decision 3 says; to be pinned against the recorder.
- `mkdir -m 700 d` makes `700` and `d`; `--mode=700` and `-m700` are errors; `touch -r a f` touches `a`; `touch -d 2020-01-01 f` makes a file `2020-01-01`. Reproduced.
- `cp --target-directory=nowhere a` makes a file `nowhere`; `-t` is unparsed. Reproduced.
- `rm -f` treats a failed lookup as absence, and `rm` reports it as not found. Reproduced.
- Library `find -empty` with a failed listing or stat prints partial results with status 0, and an unknown size reads as 0. Reproduced; the served `find` never lists.
- `MemoryHost` makes a directory beneath a regular file. Reproduced.
- The window between `rm -i`'s stat and its delete is the window plain `rm` has today, since answers are read from the line's own stdin without a host call.

## Sed edits

- `--sandbox` is discarded: `w`, `r` and `s///w` act. Reproduced; GNU refuses all three, even unreachable.
- `sed -i '2s//x/' f` fails and truncates `f` to its first line; with two files the second is truncated. Reproduced; GNU leaves both.
- A refused backup (a directory, or a read-only target) still replaces the source. Reproduced.
- An identity edit of a bytes body with invalid UTF-8 rewrites it as text with U+FFFD. Reproduced; GNU is byte-exact.
- `sed -f s.sed` with `1r other` reads nothing; the inline form reads. Reproduced.
- `w -` writes to stdout; GNU sed 4.9 writes a file named `-`. Reproduced.
- A bytes body that is valid UTF-8 comes back as text from any shell write, `cat a > b` included, because the host chooses text for every decodable body. Reproduced; host-wide.
- Contradicted: "reject a text-sourced replacement that is not valid UTF-8" refuses what `write` documents, that a text file becomes bytes when it is not text.

## Filters and matching

- `sort`, `sort -u`, `uniq` and `tr` decode with replacement: distinct invalid bytes collapse. Reproduced.
- Any `GLOBIGNORE`, not only an empty one, forces `dotglob` on. Reproduced, and wider than stated.
- Parameter replacement ignores `nocasematch`. Reproduced.
- `sort -n` orders large integers right, but `-nu` merges adjacent ones through `f64`. Reproduced.
- An empty `-f` pattern file matches every line. Reproduced.
- `--regexp x` and `--max-count 1` with separate values read the value as a file. Reproduced.
- Pattern exhaustion: glob consumers answer a miss, which negation turns into a match, and pathname expansion passes the raw pattern to the command. Reproduced. Already right: `grep` and `grep -v` (status 2), `sed`, and `[[ =~ ]]` (status 2). The partial best capture was not reproduced.
- Case-insensitive bracket ranges do not fold in `grep -i`, `sed s///I` or `[[ =~ ]]`. Reproduced.

## Builtins and variables

- `select` ignores loop accounting and `break`. Reproduced; also problem 4 of `agents/2026-11-21-the-shell-closes-its-known-failures/`.
- `wait` sees another fork's jobs. Reproduced.
- `(( a[i++] += 5 ))` evaluates the subscript twice; `(( a[-1] = 9 ))` writes a literal key; `(( m += 1 ))` replaces an associative map. Reproduced; the plain assignment `a[-1]=9` is right.
- `unset 'm[@]'` removes the whole map, and `unset 'a[@]'` the declared array. Reproduced, and wider than stated.
- `read` and `printf -v` with a subscript that fails write index 0; readonly arrays are overwritten by `read -a` and `mapfile`. Reproduced; the `mapfile` case is already listed.
- `read -t 0` reads a whole line; `read -n 0` on a file reads one character. Reproduced.
- Field splitting swaps U+F0000 for an escaped separator. Reproduced at U+F0000, not at U+E000.
- `${!ref:=dflt}` assigns `ref`. Reproduced.
- `printf %n` consumes no argument; `%a` prints decimal. Reproduced.
- `localvar_unset` is ignored when on; `${x@E}` leaves `\u`, `\U` and `\c` escapes literal; `/dev/fd/N` exists for any N. Reproduced.
- The shell has no `sleep`, and a line where every task waits with no host request outstanding ends as an internal fault, so a live writer on an empty pipe is always running or waiting on the host. A positive `read -t` is exact without a timer protocol.

## Rulings, 2026-11-22

1. The shell is no platform for third-party hosts and the module and its host ship together. Feature negotiation, legacy-host fallbacks, mixed old and new pairs and capability discovery leave every spec.
2. The guard against a changed file belongs to vfs, not to the shell: roadmap story K10, `agents/2026-11-22-the-session-remembers-what-it-read/`. A session stamps each file it reads with its entry id and version, and a later mutation through the session is refused when either has moved. The shell's `if_identity`, `if_object`, `guarded_write`, `guarded_remove`, `guarded_rmdir`, `write_body`, `writer-v1` and the namespace incarnation are withdrawn.
3. A line run without a session is its own session: its stamps live for the line.
4. Strict is on by default: a session refuses every mutation of an existing file it holds no stamp for, except an append. A recursive delete is covered by the directory's own stamp.
5. Bodies and listings stamp: file content, `grep` matches, and `ls`, `find`, `glob` and `stat` rows. The shell's own probes, such as the stat before a redirection or a removal, never stamp.
6. A multi-chunk writer is guarded by its stamp: each append refreshes it and the next requires it.
7. The shell reads through the public `read` verb: one call for each open, with rights and version judged again, held for that open only. A prefix read rides spec 178's public `read(range=)` when it lands. No storage path of the shell's own is built.
8. The first work built is the safety slice: `rm` operand validation and `-i`/`-I`, `sed --sandbox`, no publication after a failed evaluation, a backup before its replacement, a refused writer that stays failed, and reads judged at each open.
