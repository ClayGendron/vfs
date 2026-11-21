//! The shell's machine for Python: `ShellMachine` runs one line inside the
//! machine's WebAssembly module, asks its host through the requests each
//! `step` returns, and is given the replies on the next.
//!
//! The runtime is the wall around the line. It counts every instruction the
//! module executes against the line's fuel, holds its memory under a hard
//! limit, ends a slice that runs past the deadline or a cancel within one
//! epoch tick, and turns a fault in the machine (a panic, a stack overflow)
//! into a trap that ends this line and nothing else. Each line runs in a
//! fresh instance, so a line's fuel is a function of the line and its
//! replies. A slice runs with the interpreter lock released.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use shell::machine::{
    Config, Entry, EntryKind, HostError, Limits, ProgramKind, Reply, Request, Stream, WriteMode,
};
use shell_wasm::wire::{self, WireStatus};
use wasmtime::{
    Caller, Engine, Linker, Memory, Module, ResourceLimiter, Store, Trap, TypedFunc, UpdateDeadline,
};

/// The machine as a WebAssembly module, built by this crate's build script.
const MODULE: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/shell.wasm"));

/// Instructions a line may execute: about five seconds of the machine's work on a laptop.
pub const FUEL: u64 = 20_000_000_000;
/// Instructions between two returns from `step` when nothing is asked: about a millisecond.
pub const FUEL_SLICE: u64 = 10_000_000;
/// Bytes of linear memory an instance may grow to: the machine's own count, with room for its allocator.
pub const MODULE_MEMORY_BYTES: usize = 256 << 20;
/// Bytes of native stack the module's own frames may take before the call traps.
const WASM_STACK_BYTES: usize = 4 << 20;
/// How often the epoch advances; a deadline or a cancel is seen within one tick.
const EPOCH_TICK: Duration = Duration::from_millis(10);

/// The status a line exits with when its deadline passes, as `timeout` exits.
const DEADLINE_STATUS: i32 = 124;
const BUDGET_STATUS: i32 = 137;
const CANCELLED_STATUS: i32 = 130;

type StepTuple<'py> = (
    Vec<(u8, Bound<'py, PyBytes>)>,
    Vec<(String, &'static str, Bound<'py, PyDict>)>,
    (&'static str, i32, Option<String>),
);

/// One line of bash, run over requests its Python host answers.
#[pyclass(frozen, module = "vfs._native")]
pub struct ShellMachine {
    instance: Mutex<Option<Instance>>,
    cancelled: Arc<AtomicBool>,
    memory_used: AtomicU64,
    fuel_used: AtomicU64,
}

#[pymethods]
impl ShellMachine {
    /// Parse `source` and make a machine ready to run it. A line that does not
    /// parse raises `ValueError(kind, message, line, column)`; `fuel` is the
    /// line's instructions and `deadline` the seconds it may run in all.
    #[new]
    #[pyo3(signature = (source, *, env, cwd, name, args, stdin, programs, pid, limits=None, fuel=None, deadline=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        source: &str,
        env: Vec<(String, String)>,
        cwd: String,
        name: String,
        args: Vec<String>,
        stdin: Vec<u8>,
        programs: Vec<String>,
        pid: u32,
        limits: Option<std::collections::HashMap<String, u64>>,
        fuel: Option<u64>,
        deadline: Option<f64>,
    ) -> PyResult<Self> {
        let config = Config {
            env,
            cwd,
            name,
            args,
            stdin,
            programs: programs
                .into_iter()
                .map(|p| (p, ProgramKind::Library))
                .collect(),
            pid,
            limits: limits_from(limits.as_ref()),
        };
        let start = wire::encode_start(source, &config);
        let cancelled = Arc::new(AtomicBool::new(false));
        let fuel = fuel.unwrap_or(FUEL);
        let slice = limits
            .as_ref()
            .and_then(|l| l.get("fuel_slice").copied())
            .unwrap_or(FUEL_SLICE);
        let memory = limits
            .as_ref()
            .and_then(|l| l.get("module_memory_bytes").copied())
            .map_or(MODULE_MEMORY_BYTES, |v| {
                usize::try_from(v).unwrap_or(usize::MAX)
            });
        // A deadline past what an instant can hold is no deadline at all.
        let deadline = deadline.and_then(|seconds| {
            Duration::try_from_secs_f64(seconds.max(0.0))
                .ok()
                .and_then(|left| Instant::now().checked_add(left))
        });
        let watched = Arc::clone(&cancelled);
        let (instance, answer) = py
            .detach(move || {
                on_slice_thread(move || -> Result<(Instance, String), Ended> {
                    let mut instance = Instance::new(fuel, slice, memory, deadline, watched)
                        .map_err(|message| Ended(message, 1))?;
                    let answer = instance.call(Export::Start, start.as_bytes())?;
                    Ok((instance, answer))
                })
                .and_then(|started| started)
            })
            .map_err(|Ended(message, status)| {
                let kind = if status == BUDGET_STATUS {
                    "budget"
                } else {
                    "internal"
                };
                PyValueError::new_err((kind, message, 0u32, 0u32))
            })?;
        if let Err(refusal) = wire::decode_started(&answer) {
            return Err(PyValueError::new_err((
                refusal.kind,
                refusal.message,
                refusal.line,
                refusal.column,
            )));
        }
        let used = instance.fuel_used();
        Ok(ShellMachine {
            instance: Mutex::new(Some(instance)),
            cancelled,
            memory_used: AtomicU64::new(0),
            fuel_used: AtomicU64::new(used),
        })
    }

    /// Give the replies to what the last step asked, and run on. Returns the
    /// output, the requests, and the status: `("running", 0, None)`,
    /// `("done", status, None)` or `("ended", status, reason)`.
    fn step<'py>(
        &self,
        py: Python<'py>,
        replies: Vec<(String, String, Bound<'py, PyAny>)>,
    ) -> PyResult<StepTuple<'py>> {
        let mut decoded = Vec::new();
        for (key, kind, value) in replies {
            let Some(key) = wire::parse_key(&key) else {
                return Err(PyValueError::new_err(format!("not a request key: {key}")));
            };
            decoded.push((key, decode_reply(&kind, &value)?));
        }
        let document = wire::encode_replies(&decoded);
        let outcome = py.detach(|| self.run_step(document.as_bytes()))?;
        let answer = match outcome {
            Err(Ended(reason, status)) => {
                return Ok((Vec::new(), Vec::new(), ("ended", status, Some(reason))));
            }
            Ok(answer) => answer,
        };
        let step = match wire::decode_step(&answer) {
            Ok(step) => step,
            Err(message) => {
                self.drop_instance();
                return Ok((
                    Vec::new(),
                    Vec::new(),
                    ("ended", 1, Some(format!("Internal({message:?})"))),
                ));
            }
        };
        self.memory_used.store(step.memory, Ordering::Relaxed);
        let output = step
            .output
            .iter()
            .map(|(stream, bytes)| {
                (
                    if *stream == Stream::Stdout { 1u8 } else { 2u8 },
                    PyBytes::new(py, bytes),
                )
            })
            .collect();
        let mut requests = Vec::new();
        for (key, request) in &step.requests {
            let (op, args) = encode_request(py, request)?;
            requests.push((key.to_string(), op, args));
        }
        let status = match step.status {
            WireStatus::Running => ("running", 0, None),
            WireStatus::Done(code) => ("done", code, None),
            WireStatus::Ended(reason, code) => ("ended", code, Some(reason)),
        };
        if status.0 != "running" {
            self.drop_instance();
        }
        Ok((output, requests, status))
    }

    /// Stop the line: a running slice ends within one epoch tick, and the next step ends the line.
    fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
    }

    /// Bytes the machine holds now, as it counts them.
    #[getter]
    fn memory_used(&self) -> u64 {
        self.memory_used.load(Ordering::Relaxed)
    }

    /// Instructions the line has executed so far.
    #[getter]
    fn fuel_used(&self) -> u64 {
        self.fuel_used.load(Ordering::Relaxed)
    }
}

impl ShellMachine {
    fn run_step(&self, document: &[u8]) -> PyResult<Result<String, Ended>> {
        let mut guard = self
            .instance
            .try_lock()
            .map_err(|_| PyRuntimeError::new_err("a step of this line is already running"))?;
        let Some(instance) = guard.as_mut() else {
            return Ok(Err(Ended("Internal(\"the line has ended\")".to_owned(), 1)));
        };
        if self.cancelled.load(Ordering::SeqCst) {
            *guard = None;
            return Ok(Err(Ended("Cancelled".to_owned(), CANCELLED_STATUS)));
        }
        let outcome =
            on_slice_thread(|| instance.call(Export::Step, document)).and_then(|called| called);
        self.fuel_used
            .store(instance.fuel_used(), Ordering::Relaxed);
        if outcome.is_err() {
            *guard = None;
        }
        Ok(outcome)
    }

    fn drop_instance(&self) {
        if let Ok(mut guard) = self.instance.lock() {
            *guard = None;
        }
    }
}

// ---------------------------------------------------------------------------
// The runtime
// ---------------------------------------------------------------------------

struct Runtime {
    engine: Engine,
    module: Module,
}

/// The engine and the compiled module, made once a process, and the thread that advances the epoch.
fn runtime() -> Result<&'static Runtime, String> {
    static RUNTIME: OnceLock<Result<Runtime, String>> = OnceLock::new();
    RUNTIME
        .get_or_init(|| {
            let mut config = wasmtime::Config::new();
            config.consume_fuel(true);
            config.epoch_interruption(true);
            config.async_stack_size(WASM_STACK_BYTES);
            config.max_wasm_stack(WASM_STACK_BYTES);
            let engine =
                Engine::new(&config).map_err(|e| format!("the runtime did not start: {e}"))?;
            let module = Module::new(&engine, MODULE)
                .map_err(|e| format!("the shell module did not compile: {e}"))?;
            Ok(Runtime { engine, module })
        })
        .as_ref()
        .map_err(Clone::clone)
        .and_then(|runtime| {
            ensure_ticking(&runtime.engine)?;
            Ok(runtime)
        })
}

/// Start the thread that advances the epoch, once in each process: a process forked after its
/// first line inherits the runtime but not the thread, and gets a thread of its own here.
fn ensure_ticking(engine: &Engine) -> Result<(), String> {
    static TICKING_IN: Mutex<Option<u32>> = Mutex::new(None);
    let mut ticking_in = TICKING_IN
        .lock()
        .map_err(|_| "the epoch thread's record is poisoned".to_owned())?;
    let process = std::process::id();
    if *ticking_in == Some(process) {
        return Ok(());
    }
    let ticking = engine.clone();
    std::thread::Builder::new()
        .name("vfs-shell-epoch".to_owned())
        .spawn(move || {
            loop {
                std::thread::sleep(EPOCH_TICK);
                ticking.increment_epoch();
            }
        })
        .map_err(|e| format!("the epoch thread did not start: {e}"))?;
    *ticking_in = Some(process);
    Ok(())
}

/// Bytes of stack a slice's thread has: the module's own frames, and the host's beneath them.
const SLICE_THREAD_STACK_BYTES: usize = WASM_STACK_BYTES + (4 << 20);

/// Run `work` on a thread with a stack of known size, so the module's frames fit whatever the
/// calling thread's own stack is.
fn on_slice_thread<T: Send>(work: impl FnOnce() -> T + Send) -> Result<T, Ended> {
    std::thread::scope(|scope| {
        std::thread::Builder::new()
            .name("vfs-shell-slice".to_owned())
            .stack_size(SLICE_THREAD_STACK_BYTES)
            .spawn_scoped(scope, work)
            .map_err(|e| {
                Ended(
                    format!(
                        "Internal({:?})",
                        format!("the slice thread did not start: {e}")
                    ),
                    1,
                )
            })?
            .join()
            .map_err(|_| Ended("Internal(\"the slice thread panicked\")".to_owned(), 1))
    })
}

/// Why the runtime stopped a call: the reason in the machine's own words, and the status.
struct Ended(String, i32);

/// What the epoch callback stopped a call for.
#[derive(Clone, Copy)]
enum Stop {
    Cancelled,
    Deadline,
}

struct Data {
    memory_limit: usize,
    memory_refused: bool,
    /// The fuel the store held when this step began, and the slice it may spend.
    step_start: u64,
    slice: u64,
    cancelled: Arc<AtomicBool>,
    deadline: Option<Instant>,
    stopped: Option<Stop>,
}

impl ResourceLimiter for Data {
    fn memory_growing(
        &mut self,
        _current: usize,
        desired: usize,
        _maximum: Option<usize>,
    ) -> wasmtime::Result<bool> {
        if desired > self.memory_limit {
            self.memory_refused = true;
            return Err(wasmtime::format_err!("the module's memory limit"));
        }
        Ok(true)
    }

    fn table_growing(
        &mut self,
        _current: usize,
        _desired: usize,
        _maximum: Option<usize>,
    ) -> wasmtime::Result<bool> {
        Ok(true)
    }
}

#[derive(Clone, Copy)]
enum Export {
    Start,
    Step,
}

struct Instance {
    store: Store<Data>,
    memory: Memory,
    buffer: TypedFunc<u32, u32>,
    buffer_address: TypedFunc<(), u32>,
    start: TypedFunc<u32, u32>,
    step: TypedFunc<u32, u32>,
    fuel: u64,
}

impl Instance {
    fn new(
        fuel: u64,
        slice: u64,
        memory_limit: usize,
        deadline: Option<Instant>,
        cancelled: Arc<AtomicBool>,
    ) -> Result<Instance, String> {
        let runtime = runtime()?;
        let data = Data {
            memory_limit,
            memory_refused: false,
            step_start: fuel,
            slice,
            cancelled,
            deadline,
            stopped: None,
        };
        let mut store = Store::new(&runtime.engine, data);
        store.limiter(|data| data);
        store.set_fuel(fuel).map_err(|e| e.to_string())?;
        store.set_epoch_deadline(1);
        store.epoch_deadline_callback(|mut state| {
            let data = state.data_mut();
            if data.cancelled.load(Ordering::SeqCst) {
                data.stopped = Some(Stop::Cancelled);
                return Ok(UpdateDeadline::Interrupt);
            }
            if data.deadline.is_some_and(|at| Instant::now() >= at) {
                data.stopped = Some(Stop::Deadline);
                return Ok(UpdateDeadline::Interrupt);
            }
            Ok(UpdateDeadline::Continue(1))
        });
        let mut linker = Linker::new(&runtime.engine);
        linker
            .func_wrap("host", "slice_spent", |caller: Caller<'_, Data>| -> i32 {
                let left = caller.get_fuel().unwrap_or(0);
                let data = caller.data();
                i32::from(data.step_start.saturating_sub(left) >= data.slice)
            })
            .map_err(|e| e.to_string())?;
        let instance = linker
            .instantiate(&mut store, &runtime.module)
            .map_err(|e| e.to_string())?;
        let memory = instance
            .get_memory(&mut store, "memory")
            .ok_or("the module exports no memory")?;
        let typed = |store: &mut Store<Data>, name: &str| {
            instance
                .get_typed_func::<u32, u32>(store, name)
                .map_err(|e| e.to_string())
        };
        let buffer = typed(&mut store, "buffer")?;
        let start = typed(&mut store, "start")?;
        let step = typed(&mut store, "step")?;
        let buffer_address = instance
            .get_typed_func::<(), u32>(&mut store, "buffer_address")
            .map_err(|e| e.to_string())?;
        Ok(Instance {
            store,
            memory,
            buffer,
            buffer_address,
            start,
            step,
            fuel,
        })
    }

    fn fuel_used(&self) -> u64 {
        self.fuel.saturating_sub(self.store.get_fuel().unwrap_or(0))
    }

    /// Put `document` in the module's buffer, call the export, and read back what it left.
    fn call(&mut self, export: Export, document: &[u8]) -> Result<String, Ended> {
        self.store.data_mut().step_start = self.store.get_fuel().unwrap_or(0);
        let len = u32::try_from(document.len())
            .map_err(|_| Ended("Budget(\"memory\", 4294967295)".to_owned(), BUDGET_STATUS))?;
        let at = self
            .buffer
            .call(&mut self.store, len)
            .map_err(|e| self.ended(&e))?;
        self.memory
            .write(&mut self.store, at as usize, document)
            .map_err(|e| Ended(format!("Internal({:?})", e.to_string()), 1))?;
        let func = match export {
            Export::Start => &self.start,
            Export::Step => &self.step,
        };
        let out_len = func
            .call(&mut self.store, len)
            .map_err(|e| self.ended(&e))?;
        let at = self
            .buffer_address
            .call(&mut self.store, ())
            .map_err(|e| self.ended(&e))?;
        let mut bytes = vec![0u8; out_len as usize];
        self.memory
            .read(&self.store, at as usize, &mut bytes)
            .map_err(|e| Ended(format!("Internal({:?})", e.to_string()), 1))?;
        String::from_utf8(bytes).map_err(|_| {
            Ended(
                "Internal(\"the module answered with text that is not UTF-8\")".to_owned(),
                1,
            )
        })
    }

    /// Name why the runtime stopped a call, in the words the machine uses for its own ends.
    fn ended(&self, error: &wasmtime::Error) -> Ended {
        let data = self.store.data();
        if let Some(stop) = data.stopped {
            return match stop {
                Stop::Cancelled => Ended("Cancelled".to_owned(), CANCELLED_STATUS),
                Stop::Deadline => Ended("Deadline".to_owned(), DEADLINE_STATUS),
            };
        }
        if data.memory_refused {
            return Ended(
                format!("Budget(\"module_memory\", {})", data.memory_limit),
                BUDGET_STATUS,
            );
        }
        match error.downcast_ref::<Trap>() {
            Some(Trap::OutOfFuel) => {
                Ended(format!("Budget(\"fuel\", {})", self.fuel), BUDGET_STATUS)
            }
            Some(Trap::StackOverflow) => Ended("Budget(\"stack\", 0)".to_owned(), BUDGET_STATUS),
            Some(trap) => Ended(
                format!("Internal({:?})", format!("the machine trapped: {trap}")),
                1,
            ),
            None => Ended(format!("Internal({:?})", error.to_string()), 1),
        }
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn limits_from(given: Option<&std::collections::HashMap<String, u64>>) -> Limits {
    let mut limits = Limits::default();
    let Some(given) = given else {
        return limits;
    };
    let get = |key: &str| given.get(key).copied();
    let size = |v: u64| usize::try_from(v).unwrap_or(usize::MAX);
    let count = |v: u64| u32::try_from(v).unwrap_or(u32::MAX);
    if let Some(v) = get("memory_bytes") {
        limits.memory_bytes = size(v);
    }
    if let Some(v) = get("loop_iterations") {
        limits.loop_iterations = v;
    }
    if let Some(v) = get("function_depth") {
        limits.function_depth = count(v);
    }
    if let Some(v) = get("nesting") {
        limits.nesting = count(v);
    }
    if let Some(v) = get("slice") {
        limits.slice = v;
    }
    if let Some(v) = get("output_bytes") {
        limits.output_bytes = v;
    }
    if let Some(v) = get("source_bytes") {
        limits.parse.source_bytes = size(v);
    }
    if let Some(v) = get("tokens") {
        limits.parse.tokens = count(v);
    }
    if let Some(v) = get("depth") {
        limits.parse.depth = count(v);
    }
    if let Some(v) = get("pipeline_stages") {
        limits.parse.pipeline_stages = count(v);
    }
    limits
}

fn kind_of(name: &str) -> EntryKind {
    if name == "directory" {
        EntryKind::Directory
    } else {
        EntryKind::File
    }
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
            Reply::Stat {
                kind: kind_of(&kind),
                size,
            }
        }
        "entries" => {
            let entries: Vec<(String, String)> = value.extract()?;
            Reply::Entries(
                entries
                    .into_iter()
                    .map(|(name, kind)| Entry {
                        name,
                        kind: kind_of(&kind),
                    })
                    .collect(),
            )
        }
        "text" => Reply::Text(value.extract()?),
        "error" => Reply::Error(error_of(&value.extract::<String>()?)),
        "library" => Reply::Library,
        "started" => Reply::Started,
        "output" => {
            let (stdout, stderr, status): (Vec<u8>, Vec<u8>, Option<i32>) = value.extract()?;
            Reply::Output {
                stdout,
                stderr,
                status,
            }
        }
        "refused" => {
            let (status, message): (i32, String) = value.extract()?;
            Reply::Refused { status, message }
        }
        other => return Err(PyValueError::new_err(format!("not a reply kind: {other}"))),
    })
}

fn encode_request<'py>(
    py: Python<'py>,
    request: &Request,
) -> PyResult<(&'static str, Bound<'py, PyDict>)> {
    let args = PyDict::new(py);
    let op = match request {
        Request::Read {
            path,
            offset,
            length,
        } => {
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
        Request::Copy {
            from,
            to,
            recursive,
        } => {
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
        Request::Start {
            name,
            args: words,
            cwd,
        } => {
            args.set_item("name", name)?;
            args.set_item("args", words)?;
            args.set_item("cwd", cwd)?;
            "start"
        }
        Request::Feed { program, data, eof } => {
            args.set_item("program", program.to_string())?;
            args.set_item("data", PyBytes::new(py, data))?;
            args.set_item("eof", eof)?;
            "feed"
        }
    };
    Ok((op, args))
}
