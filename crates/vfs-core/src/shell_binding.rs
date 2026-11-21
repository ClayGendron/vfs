//! The shell's machine for Python: `ShellMachine` runs one line, asks its
//! host through the requests each `step` returns, and is given the replies
//! on the next. A panic inside the machine is caught here, answered as one
//! internal error, and poisons that machine; the process goes on.

use std::panic::{AssertUnwindSafe, catch_unwind};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use shell::machine::{
    Config, Entry, EntryKind, HostError, Limits, Machine, ProgramKind, Reply, Request, RequestKey, StartError, Status, Stream,
    WriteMode,
};
use shell::syntax::ParseError;

/// One line of bash, run over requests its Python host answers.
#[pyclass(unsendable, module = "vfs._native")]
pub struct ShellMachine {
    machine: Option<Machine>,
}

type StepTuple<'py> = (Vec<(u8, Bound<'py, PyBytes>)>, Vec<(String, &'static str, Bound<'py, PyDict>)>, (&'static str, i32, Option<String>));

#[pymethods]
impl ShellMachine {
    /// Parse `source` and make a machine ready to run it. A line that does not
    /// parse raises `ValueError(kind, message, line, column)`.
    #[new]
    #[pyo3(signature = (source, *, env, cwd, name, args, stdin, programs, pid, limits=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        source: &str,
        env: Vec<(String, String)>,
        cwd: String,
        name: String,
        args: Vec<String>,
        stdin: Vec<u8>,
        programs: Vec<String>,
        pid: u32,
        limits: Option<std::collections::HashMap<String, u64>>,
    ) -> PyResult<Self> {
        let mut config = Config {
            env,
            cwd,
            name,
            args,
            stdin,
            programs: programs.into_iter().map(|p| (p, ProgramKind::Library)).collect(),
            pid,
            limits: Limits::default(),
        };
        if let Some(limits) = limits {
            let get = |key: &str| limits.get(key).copied();
            let l = &mut config.limits;
            if let Some(v) = get("memory_bytes") {
                l.memory_bytes = usize::try_from(v).unwrap_or(usize::MAX);
            }
            if let Some(v) = get("loop_iterations") {
                l.loop_iterations = v;
            }
            if let Some(v) = get("function_depth") {
                l.function_depth = u32::try_from(v).unwrap_or(u32::MAX);
            }
            if let Some(v) = get("slice") {
                l.slice = v;
            }
            if let Some(v) = get("source_bytes") {
                l.parse.source_bytes = usize::try_from(v).unwrap_or(usize::MAX);
            }
            if let Some(v) = get("tokens") {
                l.parse.tokens = u32::try_from(v).unwrap_or(u32::MAX);
            }
            if let Some(v) = get("depth") {
                l.parse.depth = u32::try_from(v).unwrap_or(u32::MAX);
            }
            if let Some(v) = get("pipeline_stages") {
                l.parse.pipeline_stages = u32::try_from(v).unwrap_or(u32::MAX);
            }
        }
        let started = catch_unwind(AssertUnwindSafe(|| Machine::new(source, config)));
        match started {
            Ok(Ok(machine)) => Ok(ShellMachine { machine: Some(machine) }),
            Ok(Err(StartError::Parse(error))) => Err(parse_error(&error)),
            Ok(Err(StartError::Budget(which, limit))) => {
                Err(PyValueError::new_err(("budget", format!("{which} budget of {limit} exceeded"), 0u32, 0u32)))
            }
            Err(_) => Err(PyValueError::new_err(("internal", "the parser failed".to_owned(), 0u32, 0u32))),
        }
    }

    /// Give the replies to what the last step asked, and run on. Returns the
    /// output, the requests, and the status: `("running", 0, None)`,
    /// `("done", status, None)` or `("ended", status, reason)`.
    fn step<'py>(&mut self, py: Python<'py>, replies: Vec<(String, String, Bound<'py, PyAny>)>) -> PyResult<StepTuple<'py>> {
        let mut decoded = Vec::new();
        for (key, kind, value) in replies {
            let Some(key) = parse_key(&key) else {
                return Err(PyValueError::new_err(format!("not a request key: {key}")));
            };
            decoded.push((key, decode_reply(&kind, &value)?));
        }
        let Some(machine) = self.machine.as_mut() else {
            return Ok((Vec::new(), Vec::new(), ("ended", 1, Some("Internal(\"the machine is poisoned\")".to_owned()))));
        };
        let step = match catch_unwind(AssertUnwindSafe(|| machine.step(decoded))) {
            Ok(step) => step,
            Err(_) => {
                self.machine = None;
                return Ok((Vec::new(), Vec::new(), ("ended", 1, Some("Internal(\"the machine panicked\")".to_owned()))));
            }
        };
        let output = step
            .output
            .iter()
            .map(|(stream, bytes)| (if *stream == Stream::Stdout { 1u8 } else { 2u8 }, PyBytes::new(py, bytes)))
            .collect();
        let mut requests = Vec::new();
        for (key, request) in &step.requests {
            let (op, args) = encode_request(py, request)?;
            requests.push((key.to_string(), op, args));
        }
        let status = match step.status {
            Status::Running => ("running", 0, None),
            Status::Done(code) => ("done", code, None),
            Status::Ended(fatal, code) => ("ended", code, Some(format!("{fatal:?}"))),
        };
        if status.0 != "running" {
            self.machine = None;
        }
        Ok((output, requests, status))
    }

    /// Stop the line: its next step ends it.
    fn cancel(&mut self) {
        if let Some(machine) = self.machine.as_mut() {
            machine.cancel();
        }
    }

    /// Bytes the machine holds now, as it counts them.
    #[getter]
    fn memory_used(&self) -> usize {
        self.machine.as_ref().map_or(0, Machine::memory_used)
    }
}

fn parse_error(error: &ParseError) -> PyErr {
    match error {
        ParseError::Syntax(at, message) => PyValueError::new_err(("syntax", message.clone(), at.line, at.column)),
        ParseError::Refused(at, construct, reason) => {
            PyValueError::new_err(("refused", format!("{construct}: {reason}"), at.line, at.column))
        }
        ParseError::Budget(which, limit) => {
            PyValueError::new_err(("budget", format!("{which} budget of {limit} exceeded"), 0u32, 0u32))
        }
    }
}

fn parse_key(text: &str) -> Option<RequestKey> {
    let (task, ordinal) = text.split_once('#')?;
    let task = task.split('.').map(|n| n.parse::<u32>().ok()).collect::<Option<Vec<u32>>>()?;
    Some(RequestKey {
        task,
        ordinal: ordinal.parse().ok()?,
    })
}

fn kind_of(name: &str) -> EntryKind {
    if name == "directory" { EntryKind::Directory } else { EntryKind::File }
}

fn error_of(name: &str) -> HostError {
    match name {
        "not_found" => HostError::NotFound,
        "not_a_directory" => HostError::NotADirectory,
        "is_a_directory" => HostError::IsADirectory,
        "exists" => HostError::Exists,
        "not_empty" => HostError::NotEmpty,
        "permission_denied" => HostError::PermissionDenied,
        "unsupported" => HostError::Unsupported,
        _ => HostError::Invalid,
    }
}

fn decode_reply(kind: &str, value: &Bound<'_, PyAny>) -> PyResult<Reply> {
    Ok(match kind {
        "data" => {
            let (bytes, eof): (Vec<u8>, bool) = value.extract()?;
            Reply::Data { bytes, eof }
        }
        "done" => Reply::Done,
        "stat" => {
            let (kind, size): (String, u64) = value.extract()?;
            Reply::Stat { kind: kind_of(&kind), size }
        }
        "entries" => {
            let entries: Vec<(String, String)> = value.extract()?;
            Reply::Entries(entries.into_iter().map(|(name, kind)| Entry { name, kind: kind_of(&kind) }).collect())
        }
        "text" => Reply::Text(value.extract()?),
        "error" => Reply::Error(error_of(&value.extract::<String>()?)),
        other => return Err(PyValueError::new_err(format!("not a reply kind: {other}"))),
    })
}

fn encode_request<'py>(py: Python<'py>, request: &Request) -> PyResult<(&'static str, Bound<'py, PyDict>)> {
    let args = PyDict::new(py);
    let op = match request {
        Request::Read { path, offset, length } => {
            args.set_item("path", path)?;
            args.set_item("offset", offset)?;
            args.set_item("length", length)?;
            "read"
        }
        Request::Write { path, data, mode } => {
            args.set_item("path", path)?;
            args.set_item("data", PyBytes::new(py, data))?;
            args.set_item(
                "mode",
                match mode {
                    WriteMode::Truncate => "truncate",
                    WriteMode::Append => "append",
                    WriteMode::CreateNew => "create_new",
                },
            )?;
            "write"
        }
        Request::Touch { path } => {
            args.set_item("path", path)?;
            "touch"
        }
        Request::Stat { path } => {
            args.set_item("path", path)?;
            "stat"
        }
        Request::List { path } => {
            args.set_item("path", path)?;
            "list"
        }
        Request::Mkdir { path, parents } => {
            args.set_item("path", path)?;
            args.set_item("parents", parents)?;
            "mkdir"
        }
        Request::Remove { path, recursive } => {
            args.set_item("path", path)?;
            args.set_item("recursive", recursive)?;
            "remove"
        }
        Request::Copy { from, to, recursive } => {
            args.set_item("source", from)?;
            args.set_item("target", to)?;
            args.set_item("recursive", recursive)?;
            "copy"
        }
        Request::Move { from, to } => {
            args.set_item("source", from)?;
            args.set_item("target", to)?;
            "move"
        }
        Request::Value { name } => {
            args.set_item("name", name)?;
            "value"
        }
    };
    Ok((op, args))
}
