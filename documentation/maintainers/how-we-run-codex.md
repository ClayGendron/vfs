# How we run Codex

This page says how a coding agent starts a Codex run on its own, waits for it, and reads what it found. Codex is used here as a second reviewer, a different model reading the same code. **A run has no time limit, every run is kept on disk, and the review comes back as a file.**

Everything on this page was checked on 2026-11-18 with `codex-cli 0.170.0` on macOS, signed in with a ChatGPT account.

## The two scripts

| Script | What it does |
|---|---|
| `scripts/codex-run.sh PROMPT_FILE WORKDIR MODEL RUNDIR` | Starts one run and returns at once. The run goes on by itself. |
| `scripts/codex-wait.sh RUNDIR [SECONDS]` | Waits for that run, for 540 seconds unless told otherwise. It never stops the run. |

```bash
scripts/codex-run.sh review.md /path/to/a/worktree \
  gpt-6.2-astra runs/review-1
scripts/codex-wait.sh runs/review-1
```

`codex-wait.sh` exits 0 when the run finished well, and 124 when the run is still going. On 124, call it again.

## A run has no time limit

[The working agreement](https://github.com/ClayGendron/vfs/blob/main/AGENTS.md) gives every shell command a timeout. A Codex run is the one thing that gets none, and the two rules fit together this way.

- **The command that starts a run returns in about a second.** It has a timeout like any other.
- **The wait has a deadline.** `codex-wait.sh` stops when its seconds are up.
- **The run itself has no deadline.** A timeout that fires in the middle of a review kills it and loses the work. The first review run here took about six minutes, and nothing says in advance how long the next one takes.

The start script gives the run a session and a process group of its own. A signal sent to the agent's own shell does not reach it. This was tested: the shell that started a run was killed, and the run finished and wrote its files.

## What a run leaves behind

`codex-run.sh` makes the run directory and fills it.

| File | What it holds |
|---|---|
| `prompt.md` | The prompt, as it was sent |
| `meta.env` | The model, the working directory, the sandbox, the Codex version and the start time |
| `events.jsonl` | Every event of the run, written as it happens |
| `last.md` | Codex's last message, which is the review |
| `stderr.log` | What Codex wrote to standard error |
| `session_id` | The id Codex gave the run |
| `rollout.jsonl` | Codex's own full record of the run, copied in when the run ends |
| `exit_code` | Codex's exit status, written last |

- **A run is finished when `exit_code` is there, and it went well when that file holds `0`.** `last.md` proves nothing. Codex makes it before it starts.
- **Codex keeps its own copy of every run** under `~/.codex/sessions/`, by date. It holds the prompt, every message, every command and its output.
- **A run that was stopped can be taken up again** with `codex exec resume <session_id> "<what to do next>"`.
- **Keep the run directory somewhere that lasts** if the review will be read again. A session's scratch directory can be cleared.

## Where Codex reads and writes

- **Codex reads the whole disk and writes only in its working directory.** That is what the default sandbox, `workspace-write`, allows. The start script also closes `/tmp` and `$TMPDIR` to it, which the sandbox would otherwise leave open.
- **Give it a tree of its own to write in.** A git worktree is best, since Codex then reads `AGENTS.md` by itself and can run the tests. A plain empty directory also works, with `EXTRA=--skip-git-repo-check`, and the prompt then says where the repository is.
- **Never point it at the main checkout while other agents read it.** Its scratch files would land among theirs.
- **Tell it which Python to use.** A worktree has no built extension. The prompt names the interpreter of the main checkout, `.venv/bin/python`, which holds the package built from the same commit.

## What the start script sets, and why

| Setting | Why |
|---|---|
| `model_reasoning_effort="high"` | A review is worth the thought |
| `project_doc_max_bytes=262144` | Codex reads only the first 32,768 bytes of `AGENTS.md` unless told otherwise, and the file is longer than that |
| `--json` | The events are kept as they happen, so a run that dies still leaves a record |
| `-o last.md` | The review is a file, and the agent reads the file |

The model is named on the command line. The reviews of 2026-11-18 used `gpt-6.2-astra`. With a ChatGPT account, a model name Codex does not offer is refused at once, and `stderr.log` says so.

## Writing the prompt

The prompt is a file. A good one has five parts.

1. **What Codex is.** A reviewer that did not write the code.
2. **The rules.** Where it may write, which Python to run, no git command that changes state, no network, no whole test suite.
3. **What to review.** One commit or one spec, by name, and the files to read beside it.
4. **Questions.** The places most likely to be wrong, as questions. Never the author's answers, and never the author's summary of the work.
5. **How to report.** A one-line verdict, then findings ranked High, Medium and Low. Each finding has a file and line, a script that shows it, and a label: ran it, read the code, or inferred it.

## Rules for the agent

- **Never read or print `~/.codex/auth.json`,** or any file that holds a token.
- **Never change anything under `~/.codex/`.**
- **Check every finding before acting on it.** Codex's findings come back in the same sure voice whether they are right or wrong. Run its script, or write one.
- **Remove the worktree when the run is read.** [How we work](how-we-work.md) has the rule.
