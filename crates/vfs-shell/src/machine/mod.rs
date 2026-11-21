//! The machine: it runs a parsed line and does no IO. Its one entry is
//! [`Machine::step`]: given the replies to what it asked, it runs until it
//! needs something, is done, or has spent its slice, and returns. What it
//! needs is a [`Request`], keyed by its place in the walk of the line, so
//! two runs of one line over one world ask the same keys in the same order.

mod arith;
mod builtins;
mod deparse;
mod exec;
mod expand;
mod files;
mod io;
mod pattern;
mod printf;
mod quote;
mod regex;
mod shell;
mod test;
mod vars;

use std::cell::RefCell;
use std::fmt;
use std::future::Future;
use std::pin::Pin;
use std::rc::Rc;
use std::task::{Context, Poll, Waker};

use crate::syntax::ast::Script;
use crate::syntax::{ParseError, ParseLimits, parse};

pub use exec::{Ctx, Flow};
pub use io::Stream;
pub use shell::Shell;

// ---------------------------------------------------------------------------
// What a host sets
// ---------------------------------------------------------------------------

/// The budgets a line runs under. A host may set any of them.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    pub parse: ParseLimits,
    /// Bytes the machine may hold at once: variables, buffers, output and the tree.
    pub memory_bytes: usize,
    /// Loop iterations across the whole line.
    pub loop_iterations: u64,
    /// Nested function calls.
    pub function_depth: u32,
    /// Machine operations between two returns from `step`, when nothing is asked.
    pub slice: u64,
}

/// 64 MiB: the tree of a full-size line, its variables and its buffers.
pub const MEMORY_BYTES: usize = 64 << 20;
pub const LOOP_ITERATIONS: u64 = 1_000_000;
pub const FUNCTION_DEPTH: u32 = 256;
/// About a millisecond of work on a laptop between two returns.
pub const SLICE: u64 = 10_000;

impl Default for Limits {
    fn default() -> Self {
        Limits {
            parse: ParseLimits::default(),
            memory_bytes: MEMORY_BYTES,
            loop_iterations: LOOP_ITERATIONS,
            function_depth: FUNCTION_DEPTH,
            slice: SLICE,
        }
    }
}

/// How a host lets a program name run.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProgramKind {
    /// The crate's own implementation, run inside the machine over requests.
    Library,
}

/// Everything a line starts with.
#[derive(Clone, Debug)]
pub struct Config {
    /// The environment the line inherits.
    pub env: Vec<(String, String)>,
    /// The absolute working directory.
    pub cwd: String,
    /// `$0`.
    pub name: String,
    /// `$1` and on.
    pub args: Vec<String>,
    /// Bytes the line reads from its standard input.
    pub stdin: Vec<u8>,
    /// The programs the host mounts, by name.
    pub programs: Vec<(String, ProgramKind)>,
    /// The value of `$$`, which a host chooses.
    pub pid: u32,
    pub limits: Limits,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            env: Vec::new(),
            cwd: "/".to_owned(),
            name: "bash".to_owned(),
            args: Vec::new(),
            stdin: Vec::new(),
            programs: Vec::new(),
            pid: 1000,
            limits: Limits::default(),
        }
    }
}

// ---------------------------------------------------------------------------
// Requests and replies
// ---------------------------------------------------------------------------

/// A request's place in the walk: the path of the task that asked, then its ordinal there.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct RequestKey {
    pub task: Vec<u32>,
    pub ordinal: u32,
}

impl fmt::Display for RequestKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let path: Vec<String> = self.task.iter().map(u32::to_string).collect();
        write!(f, "{}#{}", path.join("."), self.ordinal)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WriteMode {
    /// Replace the file, creating it.
    Truncate,
    /// Add to the end, creating it.
    Append,
    /// Create the file; refuse when it exists.
    CreateNew,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EntryKind {
    File,
    Directory,
}

/// Every effect the machine can ask of its host. Paths are always absolute.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Request {
    /// Up to `length` bytes of a file from `offset`.
    Read {
        path: String,
        offset: u64,
        length: u64,
    },
    Write {
        path: String,
        data: Vec<u8>,
        mode: WriteMode,
    },
    /// Create an empty file if none is there.
    Touch {
        path: String,
    },
    Stat {
        path: String,
    },
    List {
        path: String,
    },
    Mkdir {
        path: String,
        parents: bool,
    },
    Remove {
        path: String,
        recursive: bool,
    },
    Copy {
        from: String,
        to: String,
        recursive: bool,
    },
    Move {
        from: String,
        to: String,
    },
    /// A value that is not a function of the line: `time` (seconds since the epoch) or `random`.
    Value {
        name: String,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Entry {
    pub name: String,
    pub kind: EntryKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostError {
    NotFound,
    NotADirectory,
    IsADirectory,
    Exists,
    NotEmpty,
    PermissionDenied,
    Invalid,
    Unsupported,
}

impl HostError {
    /// The text a Unix tool prints for it.
    pub fn message(self) -> &'static str {
        match self {
            HostError::NotFound => "No such file or directory",
            HostError::NotADirectory => "Not a directory",
            HostError::IsADirectory => "Is a directory",
            HostError::Exists => "File exists",
            HostError::NotEmpty => "Directory not empty",
            HostError::PermissionDenied => "Permission denied",
            HostError::Invalid => "Invalid argument",
            HostError::Unsupported => "Operation not supported",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reply {
    Data { bytes: Vec<u8>, eof: bool },
    Done,
    Stat { kind: EntryKind, size: u64 },
    Entries(Vec<Entry>),
    Text(String),
    Error(HostError),
}

// ---------------------------------------------------------------------------
// What a step returns
// ---------------------------------------------------------------------------

/// Why a line ended before its last command, outside its own control.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Fatal {
    /// A budget was spent: which one and its limit.
    Budget(&'static str, u64),
    Cancelled,
    /// A fault in the machine itself; the machine is poisoned.
    Internal(String),
}

/// The exit status of a line a budget or a cancel ended.
pub const BUDGET_STATUS: i32 = 137;
pub const CANCELLED_STATUS: i32 = 130;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Status {
    /// Asked for something, or spent its slice: call `step` again.
    Running,
    /// The line ended with this exit status.
    Done(i32),
    /// The line ended outside its control, with this status.
    Ended(Fatal, i32),
}

#[derive(Debug)]
pub struct Step {
    /// What the line printed since the last step, in order.
    pub output: Vec<(Stream, Vec<u8>)>,
    /// What the line asks now. Each must be answered before the line can go on.
    pub requests: Vec<(RequestKey, Request)>,
    pub status: Status,
}

/// Why a line could not start.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StartError {
    Parse(ParseError),
    Budget(&'static str, u64),
}

// ---------------------------------------------------------------------------
// The machine
// ---------------------------------------------------------------------------

type Root = Pin<Box<dyn Future<Output = Result<i32, Fatal>>>>;

pub struct Machine {
    hub: io::HubRef,
    root: Option<Root>,
    finished: Option<Status>,
}

impl Machine {
    /// Parse `source` and make a machine ready to run it.
    pub fn new(source: &str, config: Config) -> Result<Machine, StartError> {
        let script = parse(source, &config.limits.parse).map_err(StartError::Parse)?;
        Machine::from_script(Rc::new(script), source, config)
    }

    /// A machine over a line already parsed, perhaps judged by its host first.
    pub fn from_script(
        script: Rc<Script>,
        source: &str,
        config: Config,
    ) -> Result<Machine, StartError> {
        let limits = config.limits;
        let hub = Rc::new(RefCell::new(io::Hub::new(
            limits.memory_bytes,
            limits.slice,
            limits.loop_iterations,
        )));
        let tree_bytes = script.footprint.saturating_add(source.len());
        hub.borrow_mut()
            .charge(tree_bytes)
            .map_err(|_| StartError::Budget("memory", limits.memory_bytes as u64))?;
        let root = exec::run_line(Rc::clone(&hub), script, Rc::from(source), config);
        Ok(Machine {
            hub,
            root: Some(root),
            finished: None,
        })
    }

    /// Give the machine the replies to what it asked, and run it on.
    pub fn step(&mut self, replies: Vec<(RequestKey, Reply)>) -> Step {
        if let Some(status) = &self.finished {
            return Step {
                output: Vec::new(),
                requests: Vec::new(),
                status: status.clone(),
            };
        }
        {
            let mut hub = self.hub.borrow_mut();
            for (key, reply) in replies {
                if hub.outstanding.contains_key(&key) {
                    hub.replies.insert(key, reply);
                }
            }
            hub.slice_end = hub.ticks.saturating_add(hub.slice);
            hub.yielded = false;
        }
        let status = self.run();
        let mut hub = self.hub.borrow_mut();
        let output = std::mem::take(&mut hub.output);
        let released: usize = output.iter().map(|(_, bytes)| bytes.len()).sum();
        hub.release(released);
        let requests = std::mem::take(&mut hub.requests);
        drop(hub);
        if !matches!(status, Status::Running) {
            self.finished = Some(status.clone());
            self.root = None;
        }
        Step {
            output,
            requests,
            status,
        }
    }

    /// Stop the line: its next step ends it, as an interrupt would.
    pub fn cancel(&mut self) {
        self.hub.borrow_mut().cancelled = true;
    }

    /// Bytes the machine holds now, as it counts them.
    pub fn memory_used(&self) -> usize {
        self.hub.borrow().memory_used
    }

    fn run(&mut self) -> Status {
        let Some(root) = self.root.as_mut() else {
            return Status::Ended(Fatal::Internal("the machine has no line".to_owned()), 1);
        };
        let mut cx = Context::from_waker(Waker::noop());
        loop {
            self.hub.borrow_mut().progress = false;
            if self.hub.borrow().cancelled {
                return Status::Ended(Fatal::Cancelled, CANCELLED_STATUS);
            }
            match root.as_mut().poll(&mut cx) {
                Poll::Ready(Ok(status)) => return Status::Done(status),
                Poll::Ready(Err(fatal)) => {
                    let status = match fatal {
                        Fatal::Budget(..) => BUDGET_STATUS,
                        Fatal::Cancelled => CANCELLED_STATUS,
                        Fatal::Internal(_) => 1,
                    };
                    return Status::Ended(fatal, status);
                }
                Poll::Pending => {}
            }
            let hub = self.hub.borrow();
            if hub.yielded || !hub.requests.is_empty() {
                return Status::Running;
            }
            if !hub.progress {
                if hub.outstanding.is_empty() {
                    return Status::Ended(
                        Fatal::Internal("the line waits on nothing".to_owned()),
                        1,
                    );
                }
                return Status::Running;
            }
        }
    }
}
