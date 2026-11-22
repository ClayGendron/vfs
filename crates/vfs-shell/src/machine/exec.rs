//! Running a tree. Every command is an async function over the shell it
//! runs in; a pipeline's stages are forks joined in one future, so they run
//! side by side over bounded pipes; a job run with `&` is polled beside the
//! commands of the list that started it.

use std::collections::BTreeMap;
use std::future::Future;
use std::pin::Pin;
use std::rc::Rc;
use std::task::{Context, Poll};

use super::expand::{self, Mode, eval_arith, expand_fields, expand_single};
use super::files::{self, FileReader, FileWriter, ReadBuffer};
use super::io::{self, HubRef, Stream, Task, join_all};
use super::shell::{Fd, JobRef, Options, Shell, WriteOutcome};
use super::vars::{self, AssocMap, Value, Var};
use super::{Config, Fatal, HostError, ProgramKind, Reply, Request, WriteMode, builtins, quote};
use crate::programs;
use crate::syntax::ast::{
    AndOr, Arg, AssignValue, Assignment, CaseEnd, Command, CompoundCommand, Connector, List,
    Pipeline, RedirFd, RedirOp, RedirTarget, Redirect, Script, SimpleCommand, Stage, Word,
};
use crate::syntax::is_name;

/// How control leaves a command other than by finishing.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Flow {
    Break(u32),
    Continue(u32),
    Return(i32),
    Exit(i32),
    /// An error that skips the rest of the current input line, as bash's arithmetic errors do.
    Discard(i32),
    /// The current simple command fails with this status and is not run.
    CommandFailed(i32),
    /// `${x:?}` or an unbound variable: the shell exits.
    ExpansionExit,
    Fatal(Fatal),
}

impl From<Fatal> for Flow {
    fn from(fatal: Fatal) -> Self {
        Flow::Fatal(fatal)
    }
}

pub type Status = Result<i32, Flow>;
type Exec<'b> = Pin<Box<dyn Future<Output = Status> + 'b>>;

/// What every command of a line shares.
pub struct Ctx<'a> {
    pub script: &'a Script,
    pub limits: super::Limits,
}

impl Ctx<'_> {
    pub fn line_of(&self, offset: u32) -> u32 {
        self.script.line_of(offset)
    }
}

/// The exit status a subshell ends with when control leaves it.
fn subshell_status(flow: Flow) -> Status {
    match flow {
        Flow::Exit(status) | Flow::Return(status) => Ok(status),
        Flow::Break(_) | Flow::Continue(_) => Ok(0),
        Flow::Discard(status) | Flow::CommandFailed(status) => Ok(status),
        Flow::ExpansionExit => Ok(1),
        Flow::Fatal(fatal) => Err(Flow::Fatal(fatal)),
    }
}

// ---------------------------------------------------------------------------
// The line
// ---------------------------------------------------------------------------

pub fn run_line(
    hub: HubRef,
    script: Rc<Script>,
    source: Rc<str>,
    config: Config,
) -> Pin<Box<dyn Future<Output = Result<i32, Fatal>>>> {
    Box::pin(async move {
        let script_ref: &Script = &script;
        let ctx = Ctx {
            script: script_ref,
            limits: config.limits,
        };
        let mut sh = new_shell(hub, source, &config)?;
        let outcome = run_top(&ctx, &mut sh, &script_ref.body).await;
        let status = match outcome {
            Ok(status) => status,
            Err(Flow::Exit(status) | Flow::Return(status)) => status,
            Err(Flow::ExpansionExit) => 127,
            Err(Flow::Discard(status) | Flow::CommandFailed(status)) => status,
            Err(Flow::Break(_) | Flow::Continue(_)) => sh.last_status,
            Err(Flow::Fatal(fatal)) => return Err(fatal),
        };
        flush_all(&mut sh).await?;
        // A write refused only as the line ends fails the line, once it has been said.
        let mut status = status;
        for (path, error) in files::unreported(&sh.hub) {
            let text = format!("bash: line {}: {}: {}\n", sh.lineno, path, error.message());
            if sh.error_text(&text).await.is_err() {
                break;
            }
            status = 1;
        }
        Ok(status & 0xff)
    })
}

fn new_shell(hub: HubRef, source: Rc<str>, config: &Config) -> Result<Shell, Fatal> {
    let mut fds = BTreeMap::new();
    fds.insert(0, Fd::Buffer(ReadBuffer::new(&hub, config.stdin.clone())?));
    fds.insert(1, Fd::Terminal(Stream::Stdout));
    fds.insert(2, Fd::Terminal(Stream::Stderr));
    let programs = config.programs.iter().cloned().collect();
    let mut sh = Shell {
        vars: vars::Vars::default(),
        functions: BTreeMap::new(),
        positional: config.args.clone(),
        arg0: config.name.clone(),
        options: Options::new(),
        fds,
        cwd: config.cwd.clone(),
        last_status: 0,
        pipestatus: vec![0],
        published: (0, Vec::new()),
        top_level: true,
        lineno: 1,
        task: vec![0],
        next_child: 0,
        next_request: 0,
        function_depth: 0,
        nesting: 0,
        defer_writes: false,
        in_background: false,
        break_status: None,
        loop_depth: 0,
        in_condition: false,
        subshell: 0,
        frames: Vec::new(),
        jobs: Vec::new(),
        last_job_pid: None,
        pid: config.pid,
        bash_pid: config.pid,
        getopts_char: 0,
        getopts_optind: 1,
        programs: Rc::new(programs),
        hub,
        dir_stack: Vec::new(),
        next_fd: 10,
        source,
        hashed: BTreeMap::new(),
        in_funsub: false,
        literal_splits: false,
        single_word: false,
        pending_outputs: Vec::new(),
    };
    for (name, value) in &config.env {
        if is_name(name) {
            let var = sh.vars.entry(name);
            var.value = Some(Value::Scalar(value.clone()));
            var.attrs |= vars::EXPORT;
        }
    }
    let cwd = config.cwd.clone();
    sh.set_plain("PWD", &cwd);
    for (name, value) in [
        ("IFS", " \t\n"),
        ("OPTIND", "1"),
        ("PS4", "+ "),
        ("PS2", "> "),
        ("SHLVL", "1"),
        ("BASH", "/bin/bash"),
        ("HOSTTYPE", "x86_64"),
        ("OSTYPE", "linux-gnu"),
        ("OPTERR", "1"),
        ("PPID", "1"),
        ("UID", "1000"),
        ("EUID", "1000"),
    ] {
        if !sh.has_var(name) {
            sh.set_plain(name, value);
        }
    }
    if let Some(var) = sh.vars.get_mut("PWD") {
        var.attrs |= vars::EXPORT;
    }
    Ok(sh)
}

/// The top level: an error that discards skips the rest of its input line.
async fn run_top<'a>(ctx: &'a Ctx<'_>, sh: &mut Shell, list: &'a List) -> Status {
    let mut status = 0;
    let mut skip_line: Option<u32> = None;
    let mut jobs: Vec<Task<'a, ()>> = Vec::new();
    for item in &list.items {
        let start_line = ctx.line_of(item.and_or.first.span.start);
        if skip_line == Some(start_line) {
            continue;
        }
        skip_line = None;
        let result = run_item(ctx, sh, item, &mut jobs).await;
        match result {
            Ok(code) => status = code,
            Err(Flow::Discard(code)) => {
                status = code;
                sh.last_status = code;
                let end = item
                    .and_or
                    .rest
                    .last()
                    .map_or(&item.and_or.first, |(_, p)| p)
                    .span
                    .end;
                skip_line = Some(ctx.line_of(end));
            }
            Err(Flow::CommandFailed(code)) => {
                status = code;
                sh.last_status = code;
            }
            Err(flow @ (Flow::Break(_) | Flow::Continue(_))) => {
                let _ = flow;
                status = sh.last_status;
            }
            Err(flow) => {
                drain_jobs(jobs).await;
                return Err(flow);
            }
        }
    }
    drain_jobs(jobs).await;
    Ok(status)
}

async fn drain_jobs(jobs: Vec<Task<'_, ()>>) {
    join_all(jobs).await;
}

/// Run one item of a list: in the foreground, or as a job beside what follows.
async fn run_item<'a>(
    ctx: &'a Ctx<'_>,
    sh: &mut Shell,
    item: &'a crate::syntax::ast::ListItem,
    jobs: &mut Vec<Task<'a, ()>>,
) -> Status {
    if item.background {
        let mut child = sh.fork();
        child.in_condition = false;
        // Bash reports a job of one negated pipeline without its `!`; any longer job keeps every `!`.
        child.in_background = item.and_or.rest.is_empty() && item.and_or.first.negated;
        let id = sh.jobs.len().saturating_add(1);
        let pid = child.bash_pid;
        let hub = sh.hub.clone();
        hub.borrow_mut().job_status.insert(pid, None);
        sh.jobs.push(JobRef { id, pid });
        sh.last_job_pid = Some(pid);
        if !sh.options.monitor {
            // A job's standard input is the empty input when job control is off,
            // unless the line redirected it.
        }
        let and_or = &item.and_or;
        jobs.push(Box::pin(async move {
            let result = exec_and_or(ctx, &mut child, and_or).await;
            let status = match result {
                Ok(status) => status,
                Err(flow) => subshell_status(flow).unwrap_or(1),
            };
            let _ = flush_all(&mut child).await;
            child.fds.clear();
            hub.borrow_mut().job_status.insert(pid, Some(status));
        }));
        sh.last_status = 0;
        return Ok(0);
    }
    let main = exec_and_or(ctx, sh, &item.and_or);
    WithJobs { main, jobs }.await
}

/// Poll a command and the jobs running beside it until the command is done.
struct WithJobs<'j, 'a> {
    main: Exec<'j>,
    jobs: &'j mut Vec<Task<'a, ()>>,
}

impl Future for WithJobs<'_, '_> {
    type Output = Status;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Status> {
        let this = self.get_mut();
        this.jobs
            .retain_mut(|job| job.as_mut().poll(cx).is_pending());
        this.main.as_mut().poll(cx)
    }
}

pub fn exec_list<'b>(ctx: &'b Ctx<'_>, sh: &'b mut Shell, list: &'b List) -> Exec<'b> {
    Box::pin(async move {
        let mut status = sh.last_status;
        let mut jobs: Vec<Task<'b, ()>> = Vec::new();
        for item in &list.items {
            match run_item(ctx, sh, item, &mut jobs).await {
                Ok(code) => status = code,
                Err(flow) => {
                    drain_jobs(jobs).await;
                    return Err(flow);
                }
            }
        }
        drain_jobs(jobs).await;
        Ok(status)
    })
}

fn exec_and_or<'b>(ctx: &'b Ctx<'_>, sh: &'b mut Shell, and_or: &'b AndOr) -> Exec<'b> {
    Box::pin(async move {
        let outer_condition = sh.in_condition;
        let last_index = and_or.rest.len();
        let mut status;
        sh.in_condition = outer_condition || last_index > 0;
        let first = exec_pipeline(ctx, sh, &and_or.first).await;
        sh.in_condition = outer_condition;
        status = first?;
        let mut last_ran = 0usize;
        for (index, (connector, pipeline)) in and_or.rest.iter().enumerate() {
            let run = match connector {
                Connector::And => status == 0,
                Connector::Or => status != 0,
            };
            if !run {
                continue;
            }
            let is_last = index.saturating_add(1) == last_index;
            sh.in_condition = outer_condition || !is_last;
            let result = exec_pipeline(ctx, sh, pipeline).await;
            sh.in_condition = outer_condition;
            status = result?;
            last_ran = index.saturating_add(1);
        }
        let final_pipeline = if last_ran == 0 {
            &and_or.first
        } else {
            and_or
                .rest
                .get(last_ran.saturating_sub(1))
                .map_or(&and_or.first, |(_, p)| p)
        };
        if status != 0
            && sh.options.errexit
            && !sh.in_condition
            && last_ran == last_index
            && !final_pipeline.negated
        {
            return Err(Flow::Exit(status));
        }
        Ok(status)
    })
}

fn exec_pipeline<'b>(ctx: &'b Ctx<'_>, sh: &'b mut Shell, pipeline: &'b Pipeline) -> Exec<'b> {
    Box::pin(async move {
        let top = std::mem::take(&mut sh.top_level);
        let before = sh.published.0;
        let result = run_pipeline(ctx, sh, pipeline).await;
        sh.top_level = top;
        if top {
            report_statuses(sh, before, &result)?;
        }
        result
    })
}

/// Keep the statuses of a pipeline of the top level: the `PIPESTATUS` it set, or the status
/// the line stopped with inside it.
fn report_statuses(sh: &mut Shell, before: u64, result: &Status) -> Result<(), Flow> {
    let entry = match result {
        Ok(_) if sh.published.0 != before => sh.published.1.clone(),
        Ok(_) => return Ok(()),
        Err(
            Flow::Exit(status)
            | Flow::Return(status)
            | Flow::Discard(status)
            | Flow::CommandFailed(status),
        ) => vec![*status],
        Err(_) => return Ok(()),
    };
    let mut hub = sh.hub.borrow_mut();
    hub.charge(super::status_bytes(&entry))
        .map_err(Flow::Fatal)?;
    hub.statuses.push(entry);
    Ok(())
}

fn run_pipeline<'b>(ctx: &'b Ctx<'_>, sh: &'b mut Shell, pipeline: &'b Pipeline) -> Exec<'b> {
    Box::pin(async move {
        io::checkpoint(&sh.hub).await?;
        let outer_condition = sh.in_condition;
        if pipeline.negated {
            sh.in_condition = true;
        }
        // Only the job's own pipeline drops its `!`; nothing nested inside the job sees the flag.
        let whole_job = std::mem::take(&mut sh.in_background);
        let result = run_stages(ctx, sh, pipeline).await;
        sh.in_condition = outer_condition;
        let mut status = result?;
        if pipeline.negated && !whole_job {
            status = i32::from(status == 0);
        }
        sh.last_status = status;
        // A compound command keeps the PIPESTATUS of the last pipeline inside it, and a function
        // definition keeps the one before it; `( )`, `[[ ]]` and `(( ))` set their own, as in bash.
        let keeps = matches!(
            pipeline.stages.as_slice(),
            [Stage { command: Command::Compound(compound, _), .. }]
                if !matches!(
                    **compound,
                    CompoundCommand::Subshell(_) | CompoundCommand::Cond(..) | CompoundCommand::Arith(..)
                )
        ) || matches!(
            pipeline.stages.as_slice(),
            [Stage {
                command: Command::Function(_),
                ..
            }]
        );
        // Bash records a negated `[[ ]]` or `(( ))` with its `!` applied, and any other command without.
        let test_alone = matches!(
            pipeline.stages.as_slice(),
            [Stage { command: Command::Compound(compound, _), .. }]
                if matches!(**compound, CompoundCommand::Cond(..) | CompoundCommand::Arith(..))
        );
        if test_alone && pipeline.negated && !whole_job {
            sh.pipestatus = vec![status];
        }
        if !keeps {
            let statuses: BTreeMap<i64, String> = (0i64..)
                .zip(sh.pipestatus.iter().map(i32::to_string))
                .collect();
            set_value(sh, "PIPESTATUS", Value::Indexed(statuses))?;
            sh.published = (sh.published.0.wrapping_add(1), sh.pipestatus.clone());
        }
        Ok(status)
    })
}

async fn run_stages(ctx: &Ctx<'_>, sh: &mut Shell, pipeline: &Pipeline) -> Status {
    let stages = &pipeline.stages;
    if stages.len() == 1 {
        let Some(stage) = stages.first() else {
            return Ok(0);
        };
        let status = exec_command(ctx, sh, &stage.command).await?;
        sh.pipestatus = vec![status];
        return Ok(status);
    }
    let count = stages.len();
    let lastpipe = sh.options.shopt("lastpipe") && !sh.options.monitor;
    let mut tasks: Vec<Task<'_, Status>> = Vec::new();
    let mut previous: Option<io::ReadEnd> = None;
    let mut last_input = None;
    for (index, stage) in stages.iter().enumerate() {
        let is_last = index.saturating_add(1) == count;
        let (reader, writer) = if is_last {
            (None, None)
        } else {
            let (r, w) = io::pipe(&sh.hub);
            (Some(r), Some(w))
        };
        let input = previous.take();
        if is_last && lastpipe {
            last_input = input;
            break;
        }
        let mut child = sh.fork();
        child.in_condition = sh.in_condition;
        if let Some(input) = input {
            child.fds.insert(0, Fd::PipeIn(input));
        }
        if let Some(writer) = writer {
            if stage.pipe_stderr {
                child.fds.insert(2, Fd::PipeOut(writer.clone()));
            }
            child.fds.insert(1, Fd::PipeOut(writer));
        }
        previous = reader;
        let command = &stage.command;
        tasks.push(Box::pin(async move {
            let result = exec_command(ctx, &mut child, command).await;
            let status = match result {
                Ok(status) => Ok(status),
                Err(flow) => subshell_status(flow),
            };
            let flushed = flush_all(&mut child).await;
            child.fds.clear();
            flushed?;
            status
        }));
    }
    let mut lastpipe_status = None;
    if lastpipe {
        let Some(stage) = stages.last() else {
            return Ok(0);
        };
        let saved = sh.fds.get(&0).cloned();
        if let Some(input) = last_input {
            sh.fds.insert(0, Fd::PipeIn(input));
        }
        let (results, done) = {
            let mut main = Some(exec_command(ctx, sh, &stage.command));
            let mut joined = join_all(tasks);
            let mut done: Option<Status> = None;
            let mut finished: Option<Vec<Status>> = None;
            std::future::poll_fn(|cx| {
                if let Some(task) = main.as_mut()
                    && let Poll::Ready(result) = task.as_mut().poll(cx)
                {
                    done = Some(result);
                    main = None;
                }
                if finished.is_none()
                    && let Poll::Ready(results) = Pin::new(&mut joined).poll(cx)
                {
                    finished = Some(results);
                }
                if main.is_none() && finished.is_some() {
                    Poll::Ready(())
                } else {
                    Poll::Pending
                }
            })
            .await;
            (finished.unwrap_or_default(), done)
        };
        match saved {
            Some(fd) => {
                sh.fds.insert(0, fd);
            }
            None => {
                sh.fds.remove(&0);
            }
        }
        lastpipe_status = done;
        return finish_pipeline(sh, results, lastpipe_status);
    }
    let results = join_all(tasks).await;
    finish_pipeline(sh, results, lastpipe_status.take())
}

fn finish_pipeline(sh: &mut Shell, results: Vec<Status>, last: Option<Status>) -> Status {
    let mut statuses = Vec::new();
    for result in results {
        statuses.push(result?);
    }
    if let Some(last) = last {
        statuses.push(last?);
    }
    let mut status = statuses.last().copied().unwrap_or(0);
    if sh.options.pipefail
        && let Some(failed) = statuses.iter().rev().find(|s| **s != 0)
    {
        status = *failed;
    }
    sh.pipestatus = statuses;
    Ok(status)
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

pub fn exec_command<'b>(ctx: &'b Ctx<'_>, sh: &'b mut Shell, command: &'b Command) -> Exec<'b> {
    Box::pin(async move {
        // After `set -n` the line is read and nothing more runs, as bash does.
        if sh.options.noexec {
            return Ok(0);
        }
        match command {
            Command::Simple(simple) => exec_simple(ctx, sh, simple).await,
            Command::Function(def) => {
                sh.functions.insert(def.name.clone(), Rc::clone(def));
                Ok(0)
            }
            Command::Compound(compound, redirects) => {
                let saved = match apply_redirects(ctx, sh, redirects).await? {
                    Ok(saved) => saved,
                    Err(status) => return Ok(status),
                };
                let result = exec_compound(ctx, sh, compound).await;
                let written = restore(sh, saved).await?;
                if written { result } else { result.map(|_| 1) }
            }
        }
    })
}

fn exec_compound<'b>(
    ctx: &'b Ctx<'_>,
    sh: &'b mut Shell,
    compound: &'b CompoundCommand,
) -> Exec<'b> {
    Box::pin(async move {
        nest(ctx, sh)?;
        let status = exec_compound_inner(ctx, sh, compound).await;
        sh.nesting = sh.nesting.saturating_sub(1);
        status
    })
}

/// Open one more level of nesting, or end the line when the budget is spent.
pub fn nest(ctx: &Ctx<'_>, sh: &mut Shell) -> Result<(), Flow> {
    if sh.nesting >= ctx.limits.nesting {
        return Err(Flow::Fatal(Fatal::Budget(
            "nesting",
            u64::from(ctx.limits.nesting),
        )));
    }
    sh.nesting = sh.nesting.saturating_add(1);
    Ok(())
}

fn exec_compound_inner<'b>(
    ctx: &'b Ctx<'_>,
    sh: &'b mut Shell,
    compound: &'b CompoundCommand,
) -> Exec<'b> {
    Box::pin(async move {
        match compound {
            CompoundCommand::Brace(list) => exec_list(ctx, sh, list).await,
            CompoundCommand::Subshell(list) => {
                let mut child = sh.fork();
                // A subshell is outside every loop of its parent: `break` there only says so.
                child.loop_depth = 0;
                let result = exec_list(ctx, &mut child, list).await;
                let status = match result {
                    Ok(status) => Ok(status),
                    Err(flow) => subshell_status(flow),
                };
                flush_all(&mut child).await?;
                child.fds.clear();
                let status = status?;
                sh.last_status = status;
                Ok(status)
            }
            CompoundCommand::If {
                branches,
                otherwise,
            } => {
                for (condition, body) in branches {
                    let outer = sh.in_condition;
                    sh.in_condition = true;
                    let tested = exec_list(ctx, sh, condition).await;
                    sh.in_condition = outer;
                    if tested? == 0 {
                        return exec_list(ctx, sh, body).await;
                    }
                }
                match otherwise {
                    Some(body) => exec_list(ctx, sh, body).await,
                    None => {
                        sh.last_status = 0;
                        Ok(0)
                    }
                }
            }
            CompoundCommand::While {
                until,
                condition,
                body,
            } => {
                let mut status = 0;
                sh.loop_depth = sh.loop_depth.saturating_add(1);
                let result: Status = async {
                    loop {
                        io::checkpoint(&sh.hub).await?;
                        let outer = sh.in_condition;
                        sh.in_condition = true;
                        let tested = exec_list(ctx, sh, condition).await;
                        sh.in_condition = outer;
                        let tested = match tested {
                            Ok(code) => code,
                            Err(Flow::Break(n)) => {
                                if n > 1 {
                                    return Err(Flow::Break(n.saturating_sub(1)));
                                }
                                // A break in the condition leaves the loop with 0, whatever its own status.
                                sh.break_status = None;
                                break;
                            }
                            Err(Flow::Continue(n)) => {
                                if n > 1 {
                                    return Err(Flow::Continue(n.saturating_sub(1)));
                                }
                                continue;
                            }
                            Err(flow) => return Err(flow),
                        };
                        if (tested == 0) == *until {
                            break;
                        }
                        // An iteration is a run of the body; the last test that ends the loop is not one.
                        sh.hub.borrow_mut().count_iteration()?;
                        match exec_list(ctx, sh, body).await {
                            Ok(code) => status = code,
                            Err(Flow::Break(n)) => {
                                if n > 1 {
                                    return Err(Flow::Break(n.saturating_sub(1)));
                                }
                                status = sh.break_status.take().unwrap_or(0);
                                break;
                            }
                            Err(Flow::Continue(n)) => {
                                if n > 1 {
                                    return Err(Flow::Continue(n.saturating_sub(1)));
                                }
                            }
                            Err(flow) => return Err(flow),
                        }
                    }
                    Ok(status)
                }
                .await;
                sh.loop_depth = sh.loop_depth.saturating_sub(1);
                let status = result?;
                sh.last_status = status;
                Ok(status)
            }
            CompoundCommand::For {
                name,
                words,
                body,
                span,
            } => {
                sh.lineno = ctx.line_of(span.start);
                let items = match words {
                    Some(words) => match expand::expand_words(ctx, sh, words).await {
                        Ok(items) => items,
                        Err(Flow::CommandFailed(code)) => return Ok(code),
                        Err(flow) => return Err(flow),
                    },
                    None => sh.positional.clone(),
                };
                if !is_name(name) {
                    sh.error_text(&format!(
                        "bash: line {}: `{}': not a valid identifier\n",
                        sh.lineno, name
                    ))
                    .await?;
                    sh.last_status = 1;
                    return Ok(1);
                }
                run_for(ctx, sh, name, items, body).await
            }
            CompoundCommand::Select {
                name,
                words,
                body,
                span,
            } => {
                sh.lineno = ctx.line_of(span.start);
                let items = match words {
                    Some(words) => expand::expand_words(ctx, sh, words).await?,
                    None => sh.positional.clone(),
                };
                builtins::run_select(ctx, sh, name, items, body).await
            }
            CompoundCommand::ArithFor {
                init,
                test,
                step,
                body,
                span,
            } => {
                sh.lineno = ctx.line_of(span.start);
                if let Some(word) = init {
                    let text = expand_single(ctx, sh, word, Mode::Single).await?;
                    eval_arith(ctx, sh, &text).await?;
                }
                let mut status = 0;
                sh.loop_depth = sh.loop_depth.saturating_add(1);
                let result: Status = async {
                    loop {
                        io::checkpoint(&sh.hub).await?;
                        if let Some(word) = test {
                            let text = expand_single(ctx, sh, word, Mode::Single).await?;
                            if eval_arith(ctx, sh, &text).await? == 0 {
                                break;
                            }
                        }
                        sh.hub.borrow_mut().count_iteration()?;
                        match exec_list(ctx, sh, body).await {
                            Ok(code) => status = code,
                            Err(Flow::Break(n)) => {
                                if n > 1 {
                                    return Err(Flow::Break(n.saturating_sub(1)));
                                }
                                status = sh.break_status.take().unwrap_or(0);
                                break;
                            }
                            Err(Flow::Continue(n)) => {
                                if n > 1 {
                                    return Err(Flow::Continue(n.saturating_sub(1)));
                                }
                            }
                            Err(flow) => return Err(flow),
                        }
                        if let Some(word) = step {
                            let text = expand_single(ctx, sh, word, Mode::Single).await?;
                            eval_arith(ctx, sh, &text).await?;
                        }
                    }
                    Ok(status)
                }
                .await;
                sh.loop_depth = sh.loop_depth.saturating_sub(1);
                let status = result?;
                sh.last_status = status;
                Ok(status)
            }
            CompoundCommand::Case { word, arms } => {
                let subject = expand_single(ctx, sh, word, Mode::Single).await?;
                let nocase = sh.options.shopt("nocasematch");
                let mut status = 0;
                let mut index = 0usize;
                let mut falling = false;
                while let Some(arm) = arms.get(index) {
                    let mut matched = falling;
                    if !matched {
                        for pattern in &arm.patterns {
                            let compiled = expand::compile_pattern(ctx, sh, pattern).await?;
                            let options = super::pattern::MatchOptions {
                                nocase,
                                ..Default::default()
                            };
                            if compiled.matches(&subject, options) {
                                matched = true;
                                break;
                            }
                        }
                    }
                    if matched {
                        status = exec_list(ctx, sh, &arm.body).await?;
                        match arm.end {
                            CaseEnd::Break => break,
                            CaseEnd::FallThrough => {
                                falling = true;
                            }
                            CaseEnd::Continue => {
                                falling = false;
                            }
                        }
                    } else {
                        falling = false;
                    }
                    index = index.saturating_add(1);
                }
                sh.last_status = status;
                Ok(status)
            }
            CompoundCommand::Arith(word, span) => {
                sh.lineno = ctx.line_of(span.start);
                let text = expand_single(ctx, sh, word, Mode::Single).await?;
                if sh.options.xtrace {
                    let line = format!("(({text}))");
                    trace(sh, &line).await?;
                }
                let value = match eval_arith(ctx, sh, &text).await {
                    Ok(value) => value,
                    Err(Flow::Discard(code)) => {
                        sh.last_status = code;
                        return Ok(code);
                    }
                    Err(flow) => return Err(flow),
                };
                let status = i32::from(value == 0);
                sh.last_status = status;
                Ok(status)
            }
            CompoundCommand::Cond(expr, span) => {
                sh.lineno = ctx.line_of(span.start);
                let status = super::test::eval_cond(ctx, sh, expr).await?;
                sh.last_status = status;
                Ok(status)
            }
        }
    })
}

async fn run_for(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    items: Vec<String>,
    body: &List,
) -> Status {
    let mut status = 0;
    sh.loop_depth = sh.loop_depth.saturating_add(1);
    let result: Status = async {
        for item in items {
            sh.hub.borrow_mut().count_iteration()?;
            io::checkpoint(&sh.hub).await?;
            if let Err(flow) = assign_scalar(sh, name, item, false).await {
                if let Flow::CommandFailed(code) = flow {
                    return Ok(code);
                }
                return Err(flow);
            }
            match exec_list(ctx, sh, body).await {
                Ok(code) => status = code,
                Err(Flow::Break(n)) => {
                    if n > 1 {
                        return Err(Flow::Break(n.saturating_sub(1)));
                    }
                    if let Some(code) = sh.break_status.take() {
                        status = code;
                    }
                    break;
                }
                Err(Flow::Continue(n)) => {
                    if n > 1 {
                        return Err(Flow::Continue(n.saturating_sub(1)));
                    }
                }
                Err(flow) => return Err(flow),
            }
        }
        Ok(status)
    }
    .await;
    sh.loop_depth = sh.loop_depth.saturating_sub(1);
    let status = result?;
    sh.last_status = status;
    Ok(status)
}

// ---------------------------------------------------------------------------
// Simple commands
// ---------------------------------------------------------------------------

async fn exec_simple(ctx: &Ctx<'_>, sh: &mut Shell, simple: &SimpleCommand) -> Status {
    sh.lineno = ctx.line_of(simple.span.start);
    sh.hub.borrow_mut().tick();
    match exec_simple_inner(ctx, sh, simple).await {
        Ok(status) => {
            sh.last_status = status;
            Ok(status)
        }
        Err(Flow::CommandFailed(status)) => {
            sh.last_status = status;
            Ok(status)
        }
        Err(flow) => Err(flow),
    }
}

/// An argument after expansion: plain fields, or an assignment for a declaration builtin.
pub enum Expanded {
    Field(String),
    Assign(Assignment),
}

async fn exec_simple_inner(ctx: &Ctx<'_>, sh: &mut Shell, simple: &SimpleCommand) -> Status {
    sh.hub.borrow_mut().last_sub_status = None;
    // Words first; assignments to declaration builtins are kept whole.
    let mut args: Vec<Expanded> = Vec::new();
    let mut declaration_name = None;
    for arg in &simple.words {
        match arg {
            Arg::Word(word) => {
                for field in expand_fields(ctx, sh, word).await? {
                    args.push(Expanded::Field(field));
                }
            }
            Arg::Assign(assignment) => {
                if declaration_name.is_none() {
                    declaration_name = first_field(&args);
                }
                args.push(Expanded::Assign(assignment.clone()));
            }
        }
    }
    let name = first_field(&args);
    let Some(name) = name else {
        return assignment_only(ctx, sh, simple).await;
    };
    // A declaration builtin's assignments only stay assignments if it is one.
    let words: Vec<String> = args
        .iter()
        .map(|arg| match arg {
            Expanded::Field(text) => text.clone(),
            Expanded::Assign(assignment) => assignment_text(assignment),
        })
        .collect();
    if let Some((construct, reason)) = crate::syntax::REFUSED
        .iter()
        .find(|(refused, _)| *refused == name)
    {
        sh.error_text(&format!(
            "bash: line {}: {}: refused: {}\n",
            sh.lineno, construct, reason
        ))
        .await?;
        return Err(Flow::Exit(2));
    }
    // Temporary assignments, visible to this command only.
    let temporary = !simple.assignments.is_empty();
    if temporary {
        sh.vars.scopes.push(vars::Scope::default());
        for assignment in &simple.assignments {
            if let Err(flow) = perform_assignment(ctx, sh, assignment, true).await {
                sh.vars.scopes.pop();
                return Err(flow);
            }
        }
    }
    sh.defer_writes = writes_nothing_else(sh, &name, &words, &simple.redirects);
    let applied = apply_redirects(ctx, sh, &simple.redirects).await;
    sh.defer_writes = false;
    let saved = match applied {
        Ok(Ok(saved)) => saved,
        Ok(Err(status)) => {
            if temporary {
                sh.vars.scopes.pop();
            }
            return Ok(status);
        }
        Err(flow) => {
            if temporary {
                sh.vars.scopes.pop();
            }
            return Err(flow);
        }
    };
    if sh.options.xtrace {
        let mut line: Vec<String> = Vec::new();
        for assignment in &simple.assignments {
            let value = sh.get_var(&assignment.name).unwrap_or_default();
            line.push(format!("{}={}", assignment.name, quote::trace(&value)));
        }
        line.extend(words.iter().map(|w| quote::trace(w)));
        trace(sh, &line.join(" ")).await?;
    }
    let mut result = dispatch(ctx, sh, &name, words, args).await;
    if !sh.pending_outputs.is_empty()
        && let Err(flow) = run_pending_outputs(ctx, sh).await
    {
        result = Err(flow);
    }
    let restored = restore(sh, saved).await;
    if temporary {
        sh.vars.scopes.pop();
    }
    if restored? { result } else { result.map(|_| 1) }
}

fn first_field(args: &[Expanded]) -> Option<String> {
    args.first().map(|arg| match arg {
        Expanded::Field(text) => text.clone(),
        Expanded::Assign(assignment) => assignment_text(assignment),
    })
}

fn assignment_text(assignment: &Assignment) -> String {
    let mut text = assignment.name.clone();
    if assignment.append {
        text.push('+');
    }
    text.push('=');
    if let AssignValue::Scalar(word) = &assignment.value {
        text.push_str(&word.static_text().unwrap_or_default());
    }
    text
}

async fn dispatch(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    words: Vec<String>,
    args: Vec<Expanded>,
) -> Status {
    if let Some(def) = sh.functions.get(name).cloned()
        && (!builtins::is_special(name) || !sh.options.posix)
    {
        return call_function(ctx, sh, &def, words).await;
    }
    if builtins::is_builtin(name) {
        return builtins::run(ctx, sh, name, words, args).await;
    }
    run_program(ctx, sh, name, words).await
}

pub async fn run_program(ctx: &Ctx<'_>, sh: &mut Shell, name: &str, words: Vec<String>) -> Status {
    if name.contains('/') {
        sh.error_text(&format!(
            "bash: line {}: {}: No such file or directory\n",
            sh.lineno, name
        ))
        .await?;
        return Ok(127);
    }
    if sh.programs.get(name) == Some(&ProgramKind::Library) {
        if let Some(status) = programs::run(ctx, sh, name, words).await? {
            return Ok(status);
        }
        return not_found(sh, name).await;
    }
    let key = sh.key();
    let start = Request::Start {
        name: name.to_owned(),
        args: words.iter().skip(1).cloned().collect(),
        cwd: sh.cwd.clone(),
    };
    match io::host_call(&sh.hub, key.clone(), start).await? {
        Reply::Library => match programs::run(ctx, sh, name, words).await? {
            Some(status) => Ok(status),
            None => not_found(sh, name).await,
        },
        Reply::Started => programs::run_host(sh, name, key).await,
        Reply::Refused { status, message } => {
            sh.error_text(&format!(
                "bash: line {}: {}: {}\n",
                sh.lineno, name, message
            ))
            .await?;
            Ok(status)
        }
        _ => not_found(sh, name).await,
    }
}

async fn not_found(sh: &mut Shell, name: &str) -> Status {
    sh.error_text(&format!(
        "bash: line {}: {}: command not found\n",
        sh.lineno, name
    ))
    .await?;
    Ok(127)
}

pub async fn call_function(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    def: &Rc<crate::syntax::ast::FunctionDef>,
    words: Vec<String>,
) -> Status {
    if sh.function_depth >= ctx.limits.function_depth {
        return Err(Flow::Fatal(Fatal::Budget(
            "function_depth",
            u64::from(ctx.limits.function_depth),
        )));
    }
    if let Some(limit) = sh
        .get_var("FUNCNEST")
        .and_then(|v| v.parse::<u32>().ok())
        .filter(|n| *n > 0)
        && sh.function_depth >= limit
    {
        sh.error_text(&format!(
            "bash: line {}: {}: maximum function nesting level exceeded ({})\n",
            sh.lineno, def.name, limit
        ))
        .await?;
        return Err(Flow::Exit(1));
    }
    let mut args = words.into_iter();
    args.next();
    let saved_positional = std::mem::replace(&mut sh.positional, args.collect());
    sh.frames.push((def.name.clone(), sh.lineno));
    sh.vars.scopes.push(vars::Scope::default());
    sh.function_depth = sh.function_depth.saturating_add(1);
    let saved_loop = std::mem::replace(&mut sh.loop_depth, 0);
    let result = exec_command(ctx, sh, &def.body).await;
    sh.loop_depth = saved_loop;
    sh.function_depth = sh.function_depth.saturating_sub(1);
    sh.vars.scopes.pop();
    sh.frames.pop();
    sh.positional = saved_positional;
    match result {
        Ok(status) => Ok(status),
        Err(Flow::Return(status)) => {
            sh.last_status = status;
            Ok(status)
        }
        Err(Flow::Break(_) | Flow::Continue(_)) => Ok(0),
        Err(flow) => Err(flow),
    }
}

/// A command of assignments alone: they persist, and its status is the last substitution's.
async fn assignment_only(ctx: &Ctx<'_>, sh: &mut Shell, simple: &SimpleCommand) -> Status {
    let mut failed = None;
    for assignment in &simple.assignments {
        if sh.options.xtrace {
            // Traced after the value is known.
        }
        match perform_assignment(ctx, sh, assignment, false).await {
            Ok(()) => {}
            Err(Flow::CommandFailed(code)) => {
                failed = Some(code);
                break;
            }
            Err(flow) => return Err(flow),
        }
        if sh.options.xtrace {
            let value = trace_value(sh, assignment);
            trace(
                sh,
                &format!(
                    "{}{}={}",
                    assignment.name,
                    if assignment.append { "+" } else { "" },
                    value
                ),
            )
            .await?;
        }
    }
    let saved = match apply_redirects(ctx, sh, &simple.redirects).await? {
        Ok(saved) => saved,
        Err(status) => return Ok(status),
    };
    restore(sh, saved).await?;
    if let Some(code) = failed {
        return Ok(code);
    }
    Ok(sh.hub.borrow().last_sub_status.unwrap_or(0))
}

fn trace_value(sh: &Shell, assignment: &Assignment) -> String {
    match &assignment.value {
        AssignValue::Scalar(_) => quote::trace(&sh.get_var(&assignment.name).unwrap_or_default()),
        AssignValue::Array(_) => {
            let values = expand::array_values(sh, &assignment.name);
            format!(
                "({})",
                values
                    .iter()
                    .map(|v| quote::trace(v))
                    .collect::<Vec<_>>()
                    .join(" ")
            )
        }
    }
}

pub async fn trace(sh: &mut Shell, text: &str) -> Result<(), Flow> {
    let ps4 = sh.get_var("PS4").unwrap_or_else(|| "+ ".to_owned());
    let first = ps4.chars().next().map(String::from).unwrap_or_default();
    let mut prefix = String::new();
    for _ in 0..sh.subshell_trace_level() {
        prefix.push_str(&first);
    }
    prefix.push_str(&ps4);
    sh.error_text(&format!("{prefix}{text}\n")).await?;
    Ok(())
}

impl Shell {
    fn subshell_trace_level(&self) -> u32 {
        self.hub.borrow().sub_depth
    }
}

// ---------------------------------------------------------------------------
// Assignments
// ---------------------------------------------------------------------------

/// A parsed subscript: a number for an indexed array, a key for an associative one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Index {
    Number(i64),
    Key(String),
}

pub fn resolve_nameref(sh: &Shell, name: &str) -> String {
    let mut current = name.to_owned();
    for _ in 0..10 {
        match sh.vars.get(&current) {
            Some(var) if var.has(vars::NAMEREF) => match &var.value {
                Some(Value::Scalar(target)) if !target.is_empty() => current = target.clone(),
                _ => return current,
            },
            _ => return current,
        }
    }
    current
}

/// The subscript of `name[sub]`, evaluated as the array's kind asks.
pub async fn subscript(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    sub: &Word,
) -> Result<Index, Flow> {
    let is_assoc = sh.vars.get(name).is_some_and(Var::is_assoc);
    let text = expand_single(ctx, sh, sub, Mode::Single).await?;
    if is_assoc {
        return Ok(Index::Key(text));
    }
    Ok(Index::Number(eval_arith(ctx, sh, &text).await?))
}

async fn perform_assignment(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    assignment: &Assignment,
    temporary: bool,
) -> Result<(), Flow> {
    let name = resolve_nameref(sh, &assignment.name);
    match &assignment.value {
        AssignValue::Scalar(word) => {
            let value = expand_single(ctx, sh, word, Mode::Assignment).await?;
            match &assignment.index {
                Some(sub) => {
                    let index = subscript(ctx, sh, &name, sub).await?;
                    assign_element(sh, &name, index, value, assignment.append).await
                }
                None => {
                    if temporary {
                        if let Some(var) = sh.vars.get(&name)
                            && var.has(vars::READONLY)
                        {
                            sh.error_text(&format!(
                                "bash: line {}: {}: readonly variable\n",
                                sh.lineno, name
                            ))
                            .await?;
                            return Err(Flow::CommandFailed(0));
                        }
                        let current = sh.vars.get(&name).cloned();
                        let local = sh.vars.local(&name);
                        if let Some(local) = local {
                            if let Some(current) = current {
                                local.attrs = current.attrs;
                                if assignment.append {
                                    local.value = current.value;
                                }
                            }
                            local.attrs |= vars::EXPORT;
                        }
                    }
                    assign_scalar(sh, &name, value, assignment.append).await
                }
            }
        }
        AssignValue::Array(elements) => {
            if assignment.index.is_some() {
                sh.error_text(&format!(
                    "bash: line {}: {}[{}]: cannot assign list to array member\n",
                    sh.lineno,
                    name,
                    assignment
                        .index
                        .as_ref()
                        .and_then(Word::static_text)
                        .unwrap_or_default()
                ))
                .await?;
                return Err(Flow::CommandFailed(1));
            }
            assign_array(ctx, sh, &name, elements, assignment.append).await
        }
    }
}

pub async fn assign_array(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    elements: &[crate::syntax::ast::ArrayElement],
    append: bool,
) -> Result<(), Flow> {
    if readonly_error(sh, name).await? {
        return Err(Flow::CommandFailed(1));
    }
    let is_assoc = sh.vars.get(name).is_some_and(Var::is_assoc);
    if is_assoc {
        let mut map = match (append, sh.vars.get(name).and_then(|v| v.value.clone())) {
            (true, Some(Value::Assoc(map))) => map,
            _ => AssocMap::new(),
        };
        let mut pending_key: Option<String> = None;
        for element in elements {
            match &element.key {
                Some(key) => {
                    let key = expand_single(ctx, sh, key, Mode::Single).await?;
                    let value = expand_single(ctx, sh, &element.value, Mode::Assignment).await?;
                    let value = if element.append {
                        format!("{}{}", map.get(&key).cloned().unwrap_or_default(), value)
                    } else {
                        value
                    };
                    map.insert(key, value);
                }
                None => {
                    for field in expand_fields(ctx, sh, &element.value).await? {
                        match pending_key.take() {
                            None => pending_key = Some(field),
                            Some(key) => map.insert(key, field),
                        }
                    }
                }
            }
        }
        if let Some(key) = pending_key {
            map.insert(key, String::new());
        }
        set_value(sh, name, Value::Assoc(map))?;
        return Ok(());
    }
    let mut map = match (append, sh.vars.get(name).and_then(|v| v.value.clone())) {
        (true, Some(Value::Indexed(map))) => map,
        (true, Some(Value::Scalar(text))) => BTreeMap::from([(0, text)]),
        _ => BTreeMap::new(),
    };
    let mut next = map.keys().next_back().map_or(0, |k| k.saturating_add(1));
    let integer = sh.vars.get(name).is_some_and(|v| v.has(vars::INTEGER));
    for element in elements {
        match &element.key {
            Some(key) => {
                let text = expand_single(ctx, sh, key, Mode::Single).await?;
                let mut index = eval_arith(ctx, sh, &text).await?;
                if index < 0 {
                    index = next.saturating_add(index);
                }
                let mut value = expand_single(ctx, sh, &element.value, Mode::Assignment).await?;
                if integer {
                    value = eval_arith(ctx, sh, &value).await?.to_string();
                }
                if element.append {
                    value = format!("{}{}", map.get(&index).cloned().unwrap_or_default(), value);
                }
                map.insert(index, value);
                next = index.saturating_add(1);
            }
            None => {
                for field in expand_fields(ctx, sh, &element.value).await? {
                    let value = if integer {
                        eval_arith(ctx, sh, &field).await?.to_string()
                    } else {
                        field
                    };
                    map.insert(next, value);
                    next = next.saturating_add(1);
                }
            }
        }
    }
    set_value(sh, name, Value::Indexed(map))?;
    Ok(())
}

async fn readonly_error(sh: &mut Shell, name: &str) -> Result<bool, Flow> {
    if sh.vars.get(name).is_some_and(|v| v.has(vars::READONLY)) {
        sh.error_text(&format!(
            "bash: line {}: {}: readonly variable\n",
            sh.lineno, name
        ))
        .await?;
        return Ok(true);
    }
    Ok(false)
}

/// Store a value, counting its bytes.
pub fn set_value(sh: &mut Shell, name: &str, value: Value) -> Result<(), Flow> {
    let new_bytes = value.footprint();
    let var = sh.vars.entry(name);
    let old_bytes = var.value.as_ref().map_or(0, Value::footprint);
    var.value = Some(value);
    let mut hub = sh.hub.borrow_mut();
    hub.release(old_bytes);
    hub.charge(new_bytes)?;
    Ok(())
}

/// Assign a scalar, honouring the variable's attributes.
pub async fn assign_scalar(
    sh: &mut Shell,
    name: &str,
    value: String,
    append: bool,
) -> Result<(), Flow> {
    let name = resolve_nameref(sh, name);
    if !is_name(&name) {
        sh.error_text(&format!(
            "bash: line {}: `{}': not a valid identifier\n",
            sh.lineno, name
        ))
        .await?;
        return Err(Flow::CommandFailed(1));
    }
    if readonly_error(sh, &name).await? {
        return Err(if sh.function_depth > 0 {
            Flow::Return(1)
        } else {
            Flow::CommandFailed(1)
        });
    }
    let attrs = sh.vars.get(&name).map_or(0, |v| v.attrs);
    let mut value = value;
    if attrs & vars::INTEGER != 0 {
        let current = if append {
            sh.get_var(&name).unwrap_or_default()
        } else {
            String::new()
        };
        let computed = match super::arith::evaluate(sh, &value) {
            Ok(v) => v,
            Err(super::arith::ArithFailure::Error(message)) => {
                sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                    .await?;
                return Err(Flow::Exit(1));
            }
            Err(super::arith::ArithFailure::Unbound(message)) => {
                sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                    .await?;
                return Err(Flow::ExpansionExit);
            }
            Err(super::arith::ArithFailure::Flow(flow)) => return Err(flow),
        };
        value = if append {
            current
                .parse::<i64>()
                .unwrap_or(0)
                .wrapping_add(computed)
                .to_string()
        } else {
            computed.to_string()
        };
    } else if append {
        value = format!("{}{}", sh.get_var(&name).unwrap_or_default(), value);
    }
    if attrs & vars::LOWER != 0 {
        value = value.to_lowercase();
    } else if attrs & vars::UPPER != 0 {
        value = value.to_uppercase();
    } else if attrs & vars::CAPITALIZE != 0 {
        let mut chars = value.chars();
        value = match chars.next() {
            Some(first) => first
                .to_uppercase()
                .chain(chars.flat_map(char::to_lowercase))
                .collect(),
            None => String::new(),
        };
    }
    let existing = sh.vars.get(&name).and_then(|v| v.value.clone());
    match existing {
        Some(Value::Indexed(mut map)) => {
            map.insert(0, value);
            set_value(sh, &name, Value::Indexed(map))?;
        }
        Some(Value::Assoc(mut map)) => {
            map.insert("0".to_owned(), value);
            set_value(sh, &name, Value::Assoc(map))?;
        }
        _ => set_value(sh, &name, Value::Scalar(value))?,
    }
    if sh.options.allexport
        && let Some(var) = sh.vars.get_mut(&name)
    {
        var.attrs |= vars::EXPORT;
    }
    Ok(())
}

pub async fn assign_element(
    sh: &mut Shell,
    name: &str,
    index: Index,
    value: String,
    append: bool,
) -> Result<(), Flow> {
    if readonly_error(sh, name).await? {
        return Err(Flow::CommandFailed(1));
    }
    let attrs = sh.vars.get(name).map_or(0, |v| v.attrs);
    let existing = sh.vars.get(name).and_then(|v| v.value.clone());
    let mut value = value;
    if attrs & vars::INTEGER != 0 {
        value = match super::arith::evaluate(sh, &value) {
            Ok(v) => v.to_string(),
            Err(super::arith::ArithFailure::Error(message)) => {
                sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                    .await?;
                return Err(Flow::CommandFailed(1));
            }
            Err(super::arith::ArithFailure::Unbound(message)) => {
                sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                    .await?;
                return Err(Flow::ExpansionExit);
            }
            Err(super::arith::ArithFailure::Flow(flow)) => return Err(flow),
        };
    }
    if attrs & vars::LOWER != 0 {
        value = value.to_lowercase();
    } else if attrs & vars::UPPER != 0 {
        value = value.to_uppercase();
    }
    match (existing, index) {
        (Some(Value::Assoc(mut map)), Index::Key(key)) => {
            let value = if append {
                format!("{}{}", map.get(&key).cloned().unwrap_or_default(), value)
            } else {
                value
            };
            map.insert(key, value);
            set_value(sh, name, Value::Assoc(map))
        }
        (existing, Index::Number(n)) => {
            let mut map = match existing {
                Some(Value::Indexed(map)) => map,
                Some(Value::Scalar(text)) => BTreeMap::from([(0, text)]),
                _ => BTreeMap::new(),
            };
            let key = if n < 0 {
                let top = map.keys().next_back().map_or(0, |k| k.saturating_add(1));
                let key = top.saturating_add(n);
                if key < 0 {
                    sh.error_text(&format!(
                        "bash: line {}: {}[{}]: bad array subscript\n",
                        sh.lineno, name, n
                    ))
                    .await?;
                    return Err(Flow::CommandFailed(1));
                }
                key
            } else {
                n
            };
            let value = if append {
                format!("{}{}", map.get(&key).cloned().unwrap_or_default(), value)
            } else {
                value
            };
            map.insert(key, value);
            set_value(sh, name, Value::Indexed(map))
        }
        (_, Index::Key(key)) => {
            let mut map = AssocMap::new();
            map.insert(key, value);
            set_value(sh, name, Value::Assoc(map))
        }
    }
}

// ---------------------------------------------------------------------------
// Substitutions
// ---------------------------------------------------------------------------

/// Run `list` in a subshell and return what it printed, trailing newlines removed.
pub async fn capture(ctx: &Ctx<'_>, sh: &mut Shell, list: &List) -> Result<String, Flow> {
    // `$(<file)` reads the file without running anything.
    if let Some(path) = read_file_shortcut(list) {
        let path = expand_single(ctx, sh, path, Mode::Single).await?;
        let absolute = absolute(sh, &path);
        return match read_whole(sh, &absolute).await? {
            Ok(bytes) => Ok(trim_newlines(String::from_utf8_lossy(&bytes).into_owned())),
            Err(error) => {
                sh.error_text(&format!(
                    "bash: line {}: {}: {}\n",
                    sh.lineno,
                    path,
                    error.message()
                ))
                .await?;
                Ok(String::new())
            }
        };
    }
    let mut child = sh.fork();
    nest(ctx, &mut child)?;
    child.loop_depth = 0;
    let (reader, writer) = io::pipe(&sh.hub);
    child.fds.insert(1, Fd::PipeOut(writer));
    if !sh.options.shopt("inherit_errexit") {
        child.options.errexit = false;
    }
    let hub = sh.hub.clone();
    let depth = hub.borrow().sub_depth;
    hub.borrow_mut().sub_depth = depth.saturating_add(1);
    let (status, bytes) = {
        let run = Box::pin(async {
            let result = exec_list(ctx, &mut child, list).await;
            let status = match result {
                Ok(status) => Ok(status),
                Err(flow) => subshell_status(flow),
            };
            let flushed = flush_all(&mut child).await;
            child.fds.clear();
            flushed?;
            status
        });
        let read = Box::pin(async {
            let mut bytes = Vec::new();
            loop {
                let chunk = reader.read(io::PIPE_CAPACITY).await;
                if chunk.is_empty() {
                    break;
                }
                hub.borrow_mut().charge(chunk.len())?;
                bytes.extend_from_slice(&chunk);
            }
            Ok::<Vec<u8>, Fatal>(bytes)
        });
        let mut run = Some(run);
        let mut read = Some(read);
        let mut status = None;
        let mut bytes = None;
        std::future::poll_fn(|cx| {
            if let Some(task) = run.as_mut()
                && let Poll::Ready(result) = task.as_mut().poll(cx)
            {
                status = Some(result);
                run = None;
            }
            if let Some(task) = read.as_mut()
                && let Poll::Ready(result) = task.as_mut().poll(cx)
            {
                bytes = Some(result);
                read = None;
            }
            if run.is_none() && read.is_none() {
                Poll::Ready(())
            } else {
                Poll::Pending
            }
        })
        .await;
        (status, bytes)
    };
    hub.borrow_mut().sub_depth = depth;
    let status = status.unwrap_or(Ok(0))?;
    let bytes = bytes.unwrap_or(Ok(Vec::new()))?;
    sh.hub.borrow_mut().release(bytes.len());
    sh.last_status = status;
    sh.hub.borrow_mut().last_sub_status = Some(status);
    let mut text = String::from_utf8_lossy(&bytes).into_owned();
    if text.contains('\0') {
        text.retain(|c| c != '\0');
        sh.error_text(&format!(
            "bash: line {}: warning: command substitution: ignored null byte in input\n",
            sh.lineno
        ))
        .await?;
    }
    Ok(trim_newlines(text))
}

fn trim_newlines(mut text: String) -> String {
    while text.ends_with('\n') {
        text.pop();
    }
    text
}

fn read_file_shortcut(list: &List) -> Option<&Word> {
    let [item] = list.items.as_slice() else {
        return None;
    };
    if !item.and_or.rest.is_empty() || item.background {
        return None;
    }
    let [stage] = item.and_or.first.stages.as_slice() else {
        return None;
    };
    let Command::Simple(simple) = &stage.command else {
        return None;
    };
    if !simple.words.is_empty() || !simple.assignments.is_empty() {
        return None;
    }
    let [redirect] = simple.redirects.as_slice() else {
        return None;
    };
    match (&redirect.op, &redirect.target, &redirect.fd) {
        (RedirOp::Read, RedirTarget::Word(word), RedirFd::Default | RedirFd::Number(0)) => {
            Some(word)
        }
        _ => None,
    }
}

/// `<(list)` or `>(list)`: run it now and name a descriptor that holds its side.
pub async fn process_sub(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    input: bool,
    list: &List,
) -> Result<String, Flow> {
    let fd = sh.next_fd.max(60);
    let fd = (fd..).find(|n| !sh.fds.contains_key(n)).unwrap_or(fd);
    let fd = 63u32
        .saturating_sub(u32::try_from(sh.fds.keys().filter(|k| **k >= 60).count()).unwrap_or(0))
        .max(fd.min(63));
    if input {
        let text = capture_raw(ctx, sh, list).await?;
        let buffer = ReadBuffer::new(&sh.hub, text)?;
        sh.fds.insert(fd, Fd::Buffer(buffer));
    } else {
        // What is written to the descriptor is fed to the list when the command ends.
        let (reader, writer) = io::pipe(&sh.hub);
        sh.fds.insert(fd, Fd::PipeOut(writer));
        sh.pending_outputs.push((fd, reader, list.clone()));
    }
    Ok(format!("/dev/fd/{fd}"))
}

/// What a list prints, untrimmed.
async fn capture_raw(ctx: &Ctx<'_>, sh: &mut Shell, list: &List) -> Result<Vec<u8>, Flow> {
    let mut child = sh.fork();
    nest(ctx, &mut child)?;
    child.loop_depth = 0;
    let (reader, writer) = io::pipe(&sh.hub);
    child.fds.insert(1, Fd::PipeOut(writer));
    let (status, bytes) = {
        let run = Box::pin(async {
            let result = exec_list(ctx, &mut child, list).await;
            let flushed = flush_all(&mut child).await;
            child.fds.clear();
            flushed?;
            match result {
                Ok(status) => Ok(status),
                Err(flow) => subshell_status(flow),
            }
        });
        let read = Box::pin(async {
            let mut bytes = Vec::new();
            loop {
                let chunk = reader.read(io::PIPE_CAPACITY).await;
                if chunk.is_empty() {
                    break;
                }
                bytes.extend_from_slice(&chunk);
            }
            bytes
        });
        let mut run = Some(run);
        let mut read = Some(read);
        let mut status = None;
        let mut bytes = None;
        std::future::poll_fn(|cx| {
            if let Some(task) = run.as_mut()
                && let Poll::Ready(result) = task.as_mut().poll(cx)
            {
                status = Some(result);
                run = None;
            }
            if let Some(task) = read.as_mut()
                && let Poll::Ready(result) = task.as_mut().poll(cx)
            {
                bytes = Some(result);
                read = None;
            }
            if run.is_none() && read.is_none() {
                Poll::Ready(())
            } else {
                Poll::Pending
            }
        })
        .await;
        (status, bytes)
    };
    status.unwrap_or(Ok(0))?;
    Ok(bytes.unwrap_or_default())
}

/// Feed what was written to each `>(list)` to its list, now that the command is done.
pub async fn run_pending_outputs(ctx: &Ctx<'_>, sh: &mut Shell) -> Result<(), Flow> {
    let pending = std::mem::take(&mut sh.pending_outputs);
    for (fd, reader, list) in pending {
        sh.fds.remove(&fd);
        let mut child = sh.fork();
        child.fds.insert(0, Fd::PipeIn(reader));
        let result = exec_list(ctx, &mut child, &list).await;
        flush_all(&mut child).await?;
        child.fds.clear();
        if let Err(Flow::Fatal(fatal)) = result {
            return Err(Flow::Fatal(fatal));
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Paths and files
// ---------------------------------------------------------------------------

/// `path` made absolute against the working directory, with `.` and `..` resolved.
pub fn absolute(sh: &Shell, path: &str) -> String {
    let joined = if path.starts_with('/') {
        path.to_owned()
    } else {
        format!("{}/{}", sh.cwd, path)
    };
    normalize(&joined)
}

pub fn normalize(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            other => parts.push(other),
        }
    }
    format!("/{}", parts.join("/"))
}

/// Write out every file this shell holds bytes for.
pub async fn flush_all(sh: &mut Shell) -> Result<(), Fatal> {
    for writer in files::dirty_writers(&sh.hub, None) {
        let key = sh.key();
        FileWriter::flush(&writer, &sh.hub, key).await?;
    }
    Ok(())
}

/// Write out bytes held for `path` before it is read.
pub async fn sync_path(sh: &mut Shell, path: &str) -> Result<(), Fatal> {
    for writer in files::dirty_writers(&sh.hub, Some(path)) {
        let key = sh.key();
        FileWriter::flush(&writer, &sh.hub, key).await?;
    }
    Ok(())
}

/// A whole file's bytes, or why it cannot be read.
pub async fn read_whole(sh: &mut Shell, path: &str) -> Result<Result<Vec<u8>, HostError>, Fatal> {
    sync_path(sh, path).await?;
    let mut bytes = Vec::new();
    let mut offset = 0u64;
    let mut open = None;
    loop {
        let key = sh.key();
        let opened = open.get_or_insert_with(|| key.clone()).clone();
        let reply = io::host_call(
            &sh.hub,
            key,
            Request::Read {
                path: path.to_owned(),
                open: opened,
                offset,
                length: files::CHUNK as u64,
            },
        )
        .await?;
        match reply {
            Reply::Data { bytes: chunk, eof } => {
                sh.hub
                    .borrow()
                    .fits(bytes.len().saturating_add(chunk.len()))?;
                offset = offset.saturating_add(chunk.len() as u64);
                let empty = chunk.is_empty();
                bytes.extend_from_slice(&chunk);
                if eof || empty {
                    return Ok(Ok(bytes));
                }
            }
            Reply::Error(error) => return Ok(Err(error)),
            _ => return Ok(Err(HostError::Invalid)),
        }
    }
}

/// Open `path` for reading as a descriptor.
pub async fn open_read(sh: &mut Shell, path: &str) -> Result<Result<Fd, HostError>, Fatal> {
    if let Some(fd) = device(sh, path, true) {
        return Ok(fd);
    }
    let absolute = absolute(sh, path);
    sync_path(sh, &absolute).await?;
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key.clone(),
        Request::Read {
            path: absolute.clone(),
            open: key.clone(),
            offset: 0,
            length: files::CHUNK as u64,
        },
    )
    .await?;
    match reply {
        Reply::Data { bytes, eof } => Ok(Ok(Fd::FileIn(FileReader::new(
            &sh.hub, absolute, key, bytes, eof,
        )?))),
        Reply::Error(error) => Ok(Err(error)),
        _ => Ok(Err(HostError::Invalid)),
    }
}

/// The special files under `/dev` the shell itself provides.
fn device(sh: &Shell, path: &str, reading: bool) -> Option<Result<Fd, HostError>> {
    match path {
        "/dev/null" => Some(Ok(if reading {
            Fd::Buffer(ReadBuffer::new(&sh.hub, Vec::new()).ok()?)
        } else {
            Fd::Null
        })),
        "/dev/stdin" => Some(sh.fds.get(&0).cloned().ok_or(HostError::NotFound)),
        "/dev/stdout" => Some(sh.fds.get(&1).cloned().ok_or(HostError::NotFound)),
        "/dev/stderr" => Some(sh.fds.get(&2).cloned().ok_or(HostError::NotFound)),
        _ => {
            let number = path.strip_prefix("/dev/fd/")?.parse::<u32>().ok()?;
            Some(sh.fds.get(&number).cloned().ok_or(HostError::NotFound))
        }
    }
}

/// Open `path` for writing as a descriptor.
pub async fn open_write(
    sh: &mut Shell,
    path: &str,
    mode: WriteMode,
) -> Result<Result<Fd, HostError>, Fatal> {
    if let Some(fd) = device(sh, path, false) {
        return Ok(fd);
    }
    let absolute = absolute(sh, path);
    sync_path(sh, &absolute).await?;
    if sh.defer_writes {
        if let Err(error) = openable(sh, &absolute).await? {
            return Ok(Err(error));
        }
        return Ok(Ok(Fd::FileOut(FileWriter::open(&sh.hub, absolute, mode))));
    }
    // The command may act before it ends, so the file is created, truncated or judged now, as bash
    // opens it, and a refusal stops the command before it runs.
    let writer = FileWriter::open(&sh.hub, absolute, mode);
    let key = sh.key();
    FileWriter::flush(&writer, &sh.hub, key).await?;
    let refused = writer.borrow_mut().error.take();
    Ok(match refused {
        Some(error) => Err(error),
        None => Ok(Fd::FileOut(writer)),
    })
}

/// Whether a simple command can act on nothing before its redirections end, so a file it writes
/// can wait for one write of all its bytes: it only prints, or `cat` copies an input its own
/// redirections give it. `printf -v` sets a variable, and `cat` of an inherited input consumes it.
fn writes_nothing_else(sh: &Shell, name: &str, words: &[String], redirects: &[Redirect]) -> bool {
    if sh.functions.contains_key(name) {
        return false;
    }
    match name {
        "echo" | ":" | "true" => true,
        "printf" => !words.iter().skip(1).any(|word| word.starts_with("-v")),
        "cat" => {
            words.len() == 1
                && redirects.iter().any(|redirect| {
                    matches!(redirect.fd, RedirFd::Default | RedirFd::Number(0))
                        && match (&redirect.op, &redirect.target) {
                            (RedirOp::HereDoc | RedirOp::HereString, _) => true,
                            // A literal file of its own; `/dev/stdin` and its kin are the input it inherits.
                            (RedirOp::Read, RedirTarget::Word(word)) => word
                                .static_text()
                                .is_some_and(|path| !path.starts_with("/dev/")),
                            _ => false,
                        }
                })
        }
        _ => false,
    }
}

/// Judge, by reading alone, whether `path` can be opened for writing: not a directory, and in a
/// directory that exists. The write itself waits for the redirection's first flush.
async fn openable(sh: &mut Shell, path: &str) -> Result<Result<(), HostError>, Fatal> {
    let key = sh.key();
    match io::host_call(
        &sh.hub,
        key,
        Request::Stat {
            path: path.to_owned(),
        },
    )
    .await?
    {
        Reply::Stat {
            kind: super::EntryKind::Directory,
            ..
        } => Ok(Err(HostError::IsADirectory)),
        Reply::Error(HostError::NotFound) => {
            let parent = path
                .rsplit_once('/')
                .map_or("/", |(dir, _)| if dir.is_empty() { "/" } else { dir });
            let key = sh.key();
            match io::host_call(
                &sh.hub,
                key,
                Request::Stat {
                    path: parent.to_owned(),
                },
            )
            .await?
            {
                Reply::Stat {
                    kind: super::EntryKind::Directory,
                    ..
                } => Ok(Ok(())),
                Reply::Stat { .. } => Ok(Err(HostError::NotADirectory)),
                Reply::Error(error) => Ok(Err(error)),
                _ => Ok(Ok(())),
            }
        }
        Reply::Error(error) => Ok(Err(error)),
        _ => Ok(Ok(())),
    }
}

// ---------------------------------------------------------------------------
// Redirections
// ---------------------------------------------------------------------------

/// What a command's redirections replaced, to put back when it ends.
pub struct Saved {
    previous: Vec<(u32, Option<Fd>)>,
    opened: Vec<Fd>,
}

/// Apply redirections; on failure the command is not run and this is its status.
pub async fn apply_redirects(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    redirects: &[Redirect],
) -> Result<Result<Saved, i32>, Flow> {
    let mut saved = Saved {
        previous: Vec::new(),
        opened: Vec::new(),
    };
    for redirect in redirects {
        match apply_one(ctx, sh, redirect, &mut saved).await {
            Ok(Ok(())) => {}
            Ok(Err(message)) => {
                sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                    .await?;
                restore(sh, saved).await?;
                return Ok(Err(1));
            }
            Err(Flow::CommandFailed(code)) => {
                restore(sh, saved).await?;
                return Ok(Err(code));
            }
            Err(flow) => {
                restore(sh, saved).await?;
                return Err(flow);
            }
        }
    }
    Ok(Ok(saved))
}

async fn apply_one(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    redirect: &Redirect,
    saved: &mut Saved,
) -> Result<Result<(), String>, Flow> {
    let default_fd = match redirect.op {
        RedirOp::Read
        | RedirOp::ReadWrite
        | RedirOp::DupIn
        | RedirOp::HereDoc
        | RedirOp::HereString => 0,
        _ => 1,
    };
    let (fd, var) = match &redirect.fd {
        RedirFd::Default => (default_fd, None),
        RedirFd::Number(n) => (*n, None),
        RedirFd::Variable(name) => {
            let fd = (sh.next_fd.max(10)..)
                .find(|n| !sh.fds.contains_key(n))
                .unwrap_or(10);
            (fd, Some(name.clone()))
        }
    };
    let target_fd = match redirect.op {
        RedirOp::HereDoc => {
            let RedirTarget::HereDoc(index) = &redirect.target else {
                return Ok(Err("bad here-document".to_owned()));
            };
            let Some(doc) = ctx.script.heredocs.get(*index) else {
                return Ok(Err("bad here-document".to_owned()));
            };
            let text = if doc.quoted {
                doc.body.static_text().unwrap_or_default()
            } else {
                expand_single(ctx, sh, &doc.body, Mode::Single).await?
            };
            Some(Fd::Buffer(ReadBuffer::new(&sh.hub, text.into_bytes())?))
        }
        RedirOp::HereString => {
            let RedirTarget::Word(word) = &redirect.target else {
                return Ok(Err("bad here-string".to_owned()));
            };
            let mut text = expand_single(ctx, sh, word, Mode::Single).await?;
            text.push('\n');
            Some(Fd::Buffer(ReadBuffer::new(&sh.hub, text.into_bytes())?))
        }
        _ => None,
    };
    if let Some(target) = target_fd {
        replace_fd(sh, saved, fd, Some(target), var.as_deref());
        return Ok(Ok(()));
    }
    let RedirTarget::Word(word) = &redirect.target else {
        return Ok(Err("bad redirection".to_owned()));
    };
    let fields = expand_fields(ctx, sh, word).await?;
    let raw = word.static_text().unwrap_or_default();
    let target = match fields.as_slice() {
        [one] => one.clone(),
        _ => {
            return Ok(Err(format!(
                "{}: ambiguous redirect",
                if raw.is_empty() { "$".to_owned() } else { raw }
            )));
        }
    };
    match redirect.op {
        RedirOp::DupIn | RedirOp::DupOut => {
            if target == "-" {
                replace_fd(sh, saved, fd, None, var.as_deref());
                return Ok(Ok(()));
            }
            let (number, close_source) = match target.strip_suffix('-') {
                Some(base) => (base.parse::<u32>().ok(), true),
                None => (target.parse::<u32>().ok(), false),
            };
            match number {
                Some(source) => {
                    let Some(copy) = sh.fds.get(&source).cloned() else {
                        return Ok(Err(format!("{source}: Bad file descriptor")));
                    };
                    replace_fd(sh, saved, fd, Some(copy), var.as_deref());
                    if close_source {
                        replace_fd(sh, saved, source, None, None);
                    }
                    Ok(Ok(()))
                }
                None if redirect.op == RedirOp::DupOut
                    && matches!(redirect.fd, RedirFd::Default) =>
                {
                    let opened = match open_write(sh, &target, WriteMode::Truncate).await? {
                        Ok(fd) => fd,
                        Err(error) => return Ok(Err(format!("{}: {}", target, error.message()))),
                    };
                    saved.opened.push(opened.clone());
                    replace_fd(sh, saved, 1, Some(opened.clone()), None);
                    replace_fd(sh, saved, 2, Some(opened), None);
                    Ok(Ok(()))
                }
                None => Ok(Err(format!("{target}: ambiguous redirect"))),
            }
        }
        RedirOp::Read | RedirOp::ReadWrite => {
            let opened = match open_read(sh, &target).await? {
                Ok(fd) => fd,
                Err(HostError::NotFound) if redirect.op == RedirOp::ReadWrite => {
                    match open_write(sh, &target, WriteMode::Append).await? {
                        // The created file is written when the redirection ends, as any other.
                        Ok(created) => {
                            saved.opened.push(created);
                            Fd::Buffer(ReadBuffer::new(&sh.hub, Vec::new())?)
                        }
                        Err(error) => return Ok(Err(format!("{}: {}", target, error.message()))),
                    }
                }
                Err(error) => return Ok(Err(format!("{}: {}", target, error.message()))),
            };
            replace_fd(sh, saved, fd, Some(opened), var.as_deref());
            Ok(Ok(()))
        }
        RedirOp::Write
        | RedirOp::Clobber
        | RedirOp::Append
        | RedirOp::WriteBoth
        | RedirOp::AppendBoth => {
            let append = matches!(redirect.op, RedirOp::Append | RedirOp::AppendBoth);
            if sh.options.noclobber
                && matches!(redirect.op, RedirOp::Write | RedirOp::WriteBoth)
                && device(sh, &target, false).is_none()
            {
                let absolute = absolute(sh, &target);
                let key = sh.key();
                let reply = io::host_call(&sh.hub, key, Request::Stat { path: absolute }).await?;
                if matches!(
                    reply,
                    Reply::Stat {
                        kind: super::EntryKind::File,
                        ..
                    }
                ) {
                    return Ok(Err(format!("{target}: cannot overwrite existing file")));
                }
            }
            // With noclobber set, the one write refuses a file that appeared since the check above.
            let mode = if append {
                WriteMode::Append
            } else if sh.options.noclobber
                && matches!(redirect.op, RedirOp::Write | RedirOp::WriteBoth)
            {
                WriteMode::CreateNew
            } else {
                WriteMode::Truncate
            };
            let opened = match open_write(sh, &target, mode).await? {
                Ok(fd) => fd,
                Err(error) => return Ok(Err(format!("{}: {}", target, error.message()))),
            };
            saved.opened.push(opened.clone());
            if matches!(redirect.op, RedirOp::WriteBoth | RedirOp::AppendBoth) {
                replace_fd(sh, saved, 1, Some(opened.clone()), None);
                replace_fd(sh, saved, 2, Some(opened), None);
            } else {
                replace_fd(sh, saved, fd, Some(opened), var.as_deref());
            }
            Ok(Ok(()))
        }
        RedirOp::HereDoc | RedirOp::HereString => Ok(Ok(())),
    }
}

fn replace_fd(sh: &mut Shell, saved: &mut Saved, fd: u32, value: Option<Fd>, var: Option<&str>) {
    if let Some(name) = var {
        // `{name}>file` keeps its descriptor open after the command.
        let var = sh.vars.entry(name);
        var.value = Some(Value::Scalar(fd.to_string()));
        match value {
            Some(value) => {
                sh.fds.insert(fd, value);
            }
            None => {
                sh.fds.remove(&fd);
            }
        }
        return;
    }
    let previous = match value {
        Some(value) => sh.fds.insert(fd, value),
        None => sh.fds.remove(&fd),
    };
    saved.previous.push((fd, previous));
}

/// Put back what redirections replaced, writing out files they opened.
/// Put back the descriptors a command's redirections replaced, and write what its files hold.
/// False when a write was refused: the line has said so, and the command fails with status 1.
pub async fn restore(sh: &mut Shell, saved: Saved) -> Result<bool, Flow> {
    for (fd, previous) in saved.previous.into_iter().rev() {
        match previous {
            Some(value) => {
                sh.fds.insert(fd, value);
            }
            None => {
                sh.fds.remove(&fd);
            }
        }
    }
    let mut written = true;
    for opened in saved.opened {
        if let Fd::FileOut(writer) = opened {
            let key = sh.key();
            FileWriter::flush(&writer, &sh.hub, key).await?;
            let failed = writer.borrow_mut().error.take();
            if let Some(error) = failed {
                let path = writer.borrow().path.clone();
                sh.error_text(&format!(
                    "bash: line {}: {}: {}\n",
                    sh.lineno,
                    path,
                    error.message()
                ))
                .await?;
                written = false;
            }
        }
    }
    Ok(written)
}

/// Write to a descriptor; a broken pipe ends this shell as SIGPIPE would.
pub async fn write_or_die(sh: &mut Shell, fd: u32, bytes: &[u8]) -> Result<bool, Flow> {
    match sh.write_fd(fd, bytes).await? {
        WriteOutcome::Done => Ok(true),
        WriteOutcome::Broken => Err(Flow::Exit(141)),
        WriteOutcome::BadFd => Ok(false),
    }
}
