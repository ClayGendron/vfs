//! The laws that hold on the machine as a WebAssembly module, run under a
//! runtime that counts fuel: fuel stops a line that would never end, the
//! count is the same for the same line and replies, a slice hands control
//! back, the module's own memory limit ends a call and not the process, and
//! the machine's byte count ends a line before the runtime's limit does.
#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
#![allow(clippy::arithmetic_side_effects)]

use std::path::PathBuf;
use std::process::Command;
use std::sync::OnceLock;

use shell::host::MemoryHost;
use shell_wasm::wire::{self, Json};
use wasmi::{
    Caller, Config, Engine, Linker, Module, Store, StoreLimits, StoreLimitsBuilder, TypedFunc,
};

/// The module, built once for every test in this file.
fn module_bytes() -> &'static [u8] {
    static BYTES: OnceLock<Vec<u8>> = OnceLock::new();
    BYTES.get_or_init(|| {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let target = root.join("target/module-laws");
        let status = Command::new(env!("CARGO"))
            .args([
                "build",
                "-q",
                "--release",
                "-p",
                "vfs-shell-wasm",
                "--target",
                "wasm32-unknown-unknown",
                "--target-dir",
            ])
            .arg(&target)
            .current_dir(&root)
            .status()
            .expect("cargo runs");
        assert!(status.success(), "the module builds");
        std::fs::read(target.join("wasm32-unknown-unknown/release/shell_wasm.wasm"))
            .expect("the module exists")
    })
}

struct Data {
    limits: StoreLimits,
    /// The fuel the store held when this step began, and the slice it may spend.
    step_start: u64,
    slice: u64,
}

struct Instance {
    store: Store<Data>,
    memory: wasmi::Memory,
    buffer: TypedFunc<u32, u32>,
    buffer_address: TypedFunc<(), u32>,
    start: TypedFunc<u32, u32>,
    step: TypedFunc<u32, u32>,
}

/// How a run under the runtime ended.
#[derive(Debug, PartialEq, Eq)]
enum End {
    Done(i32),
    Ended(String, i32),
    /// The runtime stopped the call: fuel spent, or memory refused.
    Trapped(String),
}

#[derive(Debug)]
struct Run {
    stdout: Vec<u8>,
    end: End,
    /// Fuel each step spent.
    spent: Vec<u64>,
    /// Steps that asked for nothing: the slice handed control back.
    yields: usize,
}

fn instance(fuel: u64, slice: u64, memory_limit: usize) -> Instance {
    let mut config = Config::default();
    config.consume_fuel(true);
    let engine = Engine::new(&config);
    let module = Module::new(&engine, module_bytes()).unwrap();
    let data = Data {
        limits: StoreLimitsBuilder::new().memory_size(memory_limit).build(),
        step_start: fuel,
        slice,
    };
    let mut store = Store::new(&engine, data);
    store.limiter(|data| &mut data.limits);
    store.set_fuel(fuel).unwrap();
    let mut linker = <Linker<Data>>::new(&engine);
    linker
        .func_wrap("host", "slice_spent", |caller: Caller<'_, Data>| -> i32 {
            let left = caller.get_fuel().unwrap_or(0);
            let data = caller.data();
            i32::from(data.step_start.saturating_sub(left) >= data.slice)
        })
        .unwrap();
    let instance = linker.instantiate_and_start(&mut store, &module).unwrap();
    Instance {
        memory: instance.get_memory(&store, "memory").unwrap(),
        buffer: instance.get_typed_func(&store, "buffer").unwrap(),
        buffer_address: instance.get_typed_func(&store, "buffer_address").unwrap(),
        start: instance.get_typed_func(&store, "start").unwrap(),
        step: instance.get_typed_func(&store, "step").unwrap(),
        store,
    }
}

impl Instance {
    /// Call `func` with `text` in the buffer; the JSON it answers, or the trap.
    fn call(&mut self, func: TypedFunc<u32, u32>, text: &str) -> Result<Json, String> {
        let len = u32::try_from(text.len()).unwrap();
        let address = self
            .buffer
            .call(&mut self.store, len)
            .map_err(|e| e.to_string())?;
        self.memory
            .write(&mut self.store, address as usize, text.as_bytes())
            .unwrap();
        let out_len = func.call(&mut self.store, len).map_err(|e| e.to_string())?;
        let out_address = self
            .buffer_address
            .call(&mut self.store, ())
            .map_err(|e| e.to_string())?;
        let mut out = vec![0u8; out_len as usize];
        self.memory
            .read(&self.store, out_address as usize, &mut out)
            .unwrap();
        Ok(wire::parse(&String::from_utf8(out).unwrap()).unwrap())
    }
}

fn start_json(source: &str, extra_limits: &str) -> String {
    format!(
        "{{\"source\":{},\"cwd\":\"/\",\"programs\":[\"cat\",\"wc\"],\"limits\":{{{extra_limits}}}}}",
        wire::quote(source)
    )
}

fn run(source: &str, fuel: u64, slice: u64, memory_limit: usize, limits: &str) -> Run {
    let mut instance = instance(fuel, slice, memory_limit);
    let mut host = MemoryHost::new();
    host.add_dir("/tmp");
    host.add_file("/tmp/data.txt", b"one\ntwo\nthree\n");
    let started = match instance.call(instance.start, &start_json(source, limits)) {
        Ok(json) => json,
        Err(trap) => {
            return Run {
                stdout: Vec::new(),
                end: End::Trapped(trap),
                spent: Vec::new(),
                yields: 0,
            };
        }
    };
    assert!(
        started.get("started").is_some(),
        "the line starts: {started:?}"
    );
    let mut replies = String::from("[]");
    let mut stdout = Vec::new();
    let mut spent = Vec::new();
    let mut yields = 0;
    loop {
        let before = instance.store.get_fuel().unwrap();
        instance.store.data_mut().step_start = before;
        let result = instance.call(instance.step, &replies);
        let after = instance.store.get_fuel().unwrap_or(0);
        spent.push(before - after);
        let step = match result {
            Ok(step) => step,
            Err(trap) => {
                return Run {
                    stdout,
                    end: End::Trapped(trap),
                    spent,
                    yields,
                };
            }
        };
        for chunk in step.get("output").map(Json::list).unwrap_or_default() {
            if let [Json::Number(fd), bytes] = chunk.list()
                && *fd == 1.0
            {
                stdout.extend(bytes.bytes());
            }
        }
        let requests = step.get("requests").map(Json::list).unwrap_or_default();
        let status = step.get("status").unwrap();
        if let Some(code) = status.get("done").and_then(Json::number) {
            return Run {
                stdout,
                end: End::Done(code as i32),
                spent,
                yields,
            };
        }
        if let Some(why) = status.get("ended").and_then(Json::text) {
            let code = status.get("status").and_then(Json::number).unwrap_or(-1.0) as i32;
            return Run {
                stdout,
                end: End::Ended(why.to_owned(), code),
                spent,
                yields,
            };
        }
        if requests.is_empty() {
            yields += 1;
        }
        let mut answers = Vec::new();
        for request in requests {
            answers.push(answer(&mut host, request));
        }
        replies = format!("[{}]", answers.join(","));
    }
}

/// Answer one request from the in-memory host, as JSON.
fn answer(host: &mut MemoryHost, request: &Json) -> String {
    let key = wire::quote(request.get("key").and_then(Json::text).unwrap());
    let path = request
        .get("path")
        .and_then(Json::text)
        .unwrap_or_default()
        .to_owned();
    let reply = match request.get("op").and_then(Json::text).unwrap_or_default() {
        "read" => host.answer(&shell::machine::Request::Read {
            path,
            offset: request.get("offset").and_then(Json::number).unwrap_or(0.0) as u64,
            length: request.get("length").and_then(Json::number).unwrap_or(0.0) as u64,
        }),
        "stat" => host.answer(&shell::machine::Request::Stat { path }),
        "list" => host.answer(&shell::machine::Request::List { path }),
        "value" => shell::machine::Reply::Text("1700000000".to_owned()),
        _ => shell::machine::Reply::Error(shell::machine::HostError::Unsupported),
    };
    match reply {
        shell::machine::Reply::Data { bytes, eof } => {
            format!(
                "{{\"key\":{key},\"reply\":\"data\",\"bytes\":\"{}\",\"eof\":{eof}}}",
                wire::base64_encode(&bytes)
            )
        }
        shell::machine::Reply::Stat { kind, size } => {
            let kind = if kind == shell::machine::EntryKind::Directory {
                "directory"
            } else {
                "file"
            };
            format!("{{\"key\":{key},\"reply\":\"stat\",\"kind\":\"{kind}\",\"size\":{size}}}")
        }
        shell::machine::Reply::Entries(entries) => {
            let items: Vec<String> = entries
                .iter()
                .map(|e| {
                    let kind = if e.kind == shell::machine::EntryKind::Directory {
                        "directory"
                    } else {
                        "file"
                    };
                    format!("{{\"name\":{},\"kind\":\"{kind}\"}}", wire::quote(&e.name))
                })
                .collect();
            format!(
                "{{\"key\":{key},\"reply\":\"entries\",\"entries\":[{}]}}",
                items.join(",")
            )
        }
        shell::machine::Reply::Text(text) => format!(
            "{{\"key\":{key},\"reply\":\"text\",\"text\":{}}}",
            wire::quote(&text)
        ),
        shell::machine::Reply::Done => format!("{{\"key\":{key},\"reply\":\"done\"}}"),
        shell::machine::Reply::Error(_) => {
            format!("{{\"key\":{key},\"reply\":\"error\",\"error\":\"not_found\"}}")
        }
    }
}

const PLENTY: u64 = 50_000_000_000;
const SLICE: u64 = 10_000_000;
const MEMORY: usize = 256 << 20;

#[test]
fn a_line_runs_to_its_end_on_the_module() {
    let run = run(
        "for i in 1 2 3; do echo \"n=$i\"; done; wc -l < /tmp/data.txt",
        PLENTY,
        SLICE,
        MEMORY,
        "",
    );
    assert_eq!(String::from_utf8_lossy(&run.stdout), "n=1\nn=2\nn=3\n3\n");
    assert_eq!(run.end, End::Done(0));
}

#[test]
fn fuel_stops_a_line_that_would_never_end() {
    let run = run(
        "while :; do :; done",
        2_000_000_000,
        SLICE,
        MEMORY,
        "\"loop_iterations\":1000000000000",
    );
    assert!(
        matches!(&run.end, End::Trapped(why) if why.contains("fuel")),
        "{:?}",
        run.end
    );
    assert!(
        run.yields > 0,
        "the slice handed control back before the fuel ran out"
    );
}

#[test]
fn the_same_line_spends_the_same_fuel() {
    let line = "x=0; for i in $(echo 1 2 3 4 5 6 7 8 9); do x=$((x + i)); done; echo $x; cat /tmp/data.txt";
    let first = run(line, PLENTY, SLICE, MEMORY, "");
    let second = run(line, PLENTY, SLICE, MEMORY, "");
    assert_eq!(first.stdout, second.stdout);
    assert_eq!(first.spent, second.spent, "each step spends the same fuel");
    let total: u64 = first.spent.iter().sum();
    assert!(total > 0);
}

#[test]
fn a_slice_hands_control_back_at_a_bounded_interval() {
    let run = run(
        "i=0; while (( i < 20000 )); do i=$((i+1)); done; echo $i",
        PLENTY,
        5_000_000,
        MEMORY,
        "",
    );
    assert_eq!(String::from_utf8_lossy(&run.stdout), "20000\n");
    assert!(run.yields >= 2, "a long line yields: {} yields", run.yields);
    // No step overran its slice by more than the stretch between two checkpoints.
    let longest = run.spent.iter().copied().max().unwrap_or(0);
    assert!(longest < 5_000_000 * 4, "the longest step spent {longest}");
}

#[test]
fn the_machine_counts_its_bytes_before_the_runtime_limit_is_reached() {
    let line = "x=a; while :; do x=$x$x; done";
    let run = run(line, PLENTY, SLICE, MEMORY, "\"memory_bytes\":1048576");
    assert_eq!(
        run.end,
        End::Ended("Budget(\"memory\", 1048576)".to_owned(), 137)
    );
}

#[test]
fn the_runtime_memory_limit_ends_the_call_and_not_the_process() {
    let line = "x=a; while :; do x=$x$x; done";
    // Past the module's first memory, which holds its 8 MiB stack, and short of what the line asks for.
    let run = run(line, PLENTY, SLICE, 32 << 20, "\"memory_bytes\":1073741824");
    assert!(matches!(&run.end, End::Trapped(_)), "{:?}", run.end);
}
