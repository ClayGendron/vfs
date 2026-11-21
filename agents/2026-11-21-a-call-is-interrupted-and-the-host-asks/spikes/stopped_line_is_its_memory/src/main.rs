//! Spike: is a stopped shell line fully described by the module's linear memory?
//! Run a line to a point where it waits on requests, copy the memory, throw the
//! instance away, restore the bytes into a fresh instance that never saw `start`,
//! answer the requests there, and compare with an uninterrupted run.

use shell::host::MemoryHost;
use shell::machine::{EntryKind, HostError, Reply, Request};
use shell_wasm::wire::{self, Json};
use wasmi::{Caller, Engine, Linker, Memory, Module, Store, TypedFunc};

const MODULE: &str = "/Users/claygendron/Git/Repos/vfs/target/module-laws/wasm32-unknown-unknown/release/shell_wasm.wasm";

struct Inst {
    store: Store<()>,
    memory: Memory,
    buffer: TypedFunc<u32, u32>,
    buffer_address: TypedFunc<(), u32>,
    start: TypedFunc<u32, u32>,
    step: TypedFunc<u32, u32>,
}

fn instance(engine: &Engine, module: &Module) -> Inst {
    let mut store = Store::new(engine, ());
    let mut linker = <Linker<()>>::new(engine);
    linker
        .func_wrap("host", "slice_spent", |_: Caller<'_, ()>| -> i32 { 0 })
        .unwrap();
    let instance = linker.instantiate_and_start(&mut store, module).unwrap();
    Inst {
        memory: instance.get_memory(&store, "memory").unwrap(),
        buffer: instance.get_typed_func(&store, "buffer").unwrap(),
        buffer_address: instance.get_typed_func(&store, "buffer_address").unwrap(),
        start: instance.get_typed_func(&store, "start").unwrap(),
        step: instance.get_typed_func(&store, "step").unwrap(),
        store,
    }
}

impl Inst {
    fn call(&mut self, func: TypedFunc<u32, u32>, text: &str) -> Json {
        let len = u32::try_from(text.len()).unwrap();
        let address = self.buffer.call(&mut self.store, len).unwrap();
        self.memory.write(&mut self.store, address as usize, text.as_bytes()).unwrap();
        let out_len = func.call(&mut self.store, len).unwrap();
        let out_address = self.buffer_address.call(&mut self.store, ()).unwrap();
        let mut out = vec![0u8; out_len as usize];
        self.memory.read(&self.store, out_address as usize, &mut out).unwrap();
        wire::parse(&String::from_utf8(out).unwrap()).unwrap()
    }
}

fn answer(host: &mut MemoryHost, request: &Json) -> String {
    let key = wire::quote(request.get("key").and_then(Json::text).unwrap());
    let path = request.get("path").and_then(Json::text).unwrap_or_default().to_owned();
    let reply = match request.get("op").and_then(Json::text).unwrap_or_default() {
        "read" => host.answer(&Request::Read {
            path,
            offset: request.get("offset").and_then(Json::number).unwrap_or(0.0) as u64,
            length: request.get("length").and_then(Json::number).unwrap_or(0.0) as u64,
        }),
        "stat" => host.answer(&Request::Stat { path }),
        "list" => host.answer(&Request::List { path }),
        "value" => Reply::Text("1700000000".to_owned()),
        _ => Reply::Error(HostError::Unsupported),
    };
    match reply {
        Reply::Data { bytes, eof } => format!(
            "{{\"key\":{key},\"reply\":\"data\",\"bytes\":\"{}\",\"eof\":{eof}}}",
            wire::base64_encode(&bytes)
        ),
        Reply::Stat { kind, size } => {
            let kind = if kind == EntryKind::Directory { "directory" } else { "file" };
            format!("{{\"key\":{key},\"reply\":\"stat\",\"kind\":\"{kind}\",\"size\":{size}}}")
        }
        Reply::Entries(entries) => {
            let items: Vec<String> = entries
                .iter()
                .map(|e| {
                    let kind = if e.kind == EntryKind::Directory { "directory" } else { "file" };
                    format!("{{\"name\":{},\"kind\":\"{kind}\"}}", wire::quote(&e.name))
                })
                .collect();
            format!("{{\"key\":{key},\"reply\":\"entries\",\"entries\":[{}]}}", items.join(","))
        }
        Reply::Text(text) => format!("{{\"key\":{key},\"reply\":\"text\",\"text\":{}}}", wire::quote(&text)),
        Reply::Done => format!("{{\"key\":{key},\"reply\":\"done\"}}"),
        Reply::Error(_) => format!("{{\"key\":{key},\"reply\":\"error\",\"error\":\"not_found\"}}"),
    }
}

fn host() -> MemoryHost {
    let mut host = MemoryHost::new();
    host.add_dir("/tmp");
    host.add_file("/tmp/data.txt", b"one\ntwo\nthree\n");
    host.add_file("/tmp/b.txt", b"alpha\nbeta\n");
    host
}

struct Outcome {
    stdout: Vec<u8>,
    exit: i32,
    asked: usize,
    waits: usize,
    snapshot_bytes: usize,
    snapshot_nonzero: usize,
}

/// Run `source`. When `swap_at` is the index of a step that waits on requests,
/// move the machine to a fresh instance by its memory alone before answering.
fn run(engine: &Engine, module: &Module, source: &str, swap_at: Option<usize>) -> Outcome {
    let mut inst = instance(engine, module);
    let mut host = host();
    let start = format!(
        "{{\"source\":{},\"cwd\":\"/\",\"programs\":[\"cat\",\"wc\",\"grep\",\"head\",\"sort\"],\"limits\":{{}}}}",
        wire::quote(source)
    );
    let started = inst.call(inst.start, &start);
    assert!(started.get("started").is_some(), "the line starts: {started:?}");
    let mut replies = String::from("[]");
    let mut out = Outcome { stdout: Vec::new(), exit: -1, asked: 0, waits: 0, snapshot_bytes: 0, snapshot_nonzero: 0 };
    loop {
        let step = inst.call(inst.step, &replies);
        for chunk in step.get("output").map(Json::list).unwrap_or_default() {
            if let [Json::Number(fd), bytes] = chunk.list() && *fd == 1.0 {
                out.stdout.extend(bytes.bytes());
            }
        }
        let status = step.get("status").unwrap();
        if let Some(code) = status.get("done").and_then(Json::number) {
            out.exit = code as i32;
            return out;
        }
        if let Some(why) = status.get("ended").and_then(Json::text) {
            panic!("the line ended early: {why}");
        }
        let requests = step.get("requests").map(Json::list).unwrap_or_default();
        if !requests.is_empty() {
            if swap_at == Some(out.waits) {
                // The stop: keep only the bytes, drop the instance, restore elsewhere.
                let bytes = inst.memory.data(&inst.store).to_vec();
                out.snapshot_bytes = bytes.len();
                out.snapshot_nonzero = bytes.iter().filter(|b| **b != 0).count();
                drop(inst);
                let mut fresh = instance(engine, module);
                let have = fresh.memory.data(&fresh.store).len();
                if bytes.len() > have {
                    let pages = ((bytes.len() - have) / 65536) as u64;
                    fresh.memory.grow(&mut fresh.store, pages).unwrap();
                }
                fresh.memory.data_mut(&mut fresh.store).copy_from_slice(&bytes);
                inst = fresh;
            }
            out.waits += 1;
        }
        out.asked += requests.len();
        let answers: Vec<String> = requests.iter().map(|r| answer(&mut host, r)).collect();
        replies = format!("[{}]", answers.join(","));
    }
}

fn main() {
    let engine = Engine::default();
    let bytes = std::fs::read(MODULE).unwrap();
    let module = Module::new(&engine, &bytes[..]).unwrap();
    let globals: Vec<String> = module
        .exports()
        .filter(|e| matches!(e.ty(), wasmi::ExternType::Global(_)))
        .map(|e| e.name().to_owned())
        .collect();
    println!("exported globals: {globals:?}");
    let lines = [
        "echo before; x=$(cat /tmp/data.txt | wc -l); echo \"lines=$x\"; for f in data b; do cat /tmp/$f.txt | head -1; done; echo after $x",
        "f() { local n=$1; cat /tmp/b.txt | sort -r; echo \"n=$n\"; }; i=0; while [ $i -lt 3 ]; do f $i; i=$((i+1)); done; echo end $i",
        "cat /tmp/data.txt | grep t | wc -l; a=(x y z); cat /tmp/b.txt; echo ${a[1]} ${#a[@]}; if cat /tmp/nope.txt; then echo yes; else echo no; fi",
    ];
    for source in lines {
        let base = run(&engine, &module, source, None);
        println!("\nline: {source}");
        println!("  uninterrupted: exit {} stdout {} bytes, {} requests in {} waits", base.exit, base.stdout.len(), base.asked, base.waits);
        let mut same = 0;
        let mut size = (0, 0);
        for at in 0..base.waits {
            let moved = run(&engine, &module, source, Some(at));
            let equal = moved.stdout == base.stdout && moved.exit == base.exit && moved.asked == base.asked;
            if equal { same += 1 } else {
                println!("  DIFFERS at wait {at}: exit {} asked {} stdout {:?}", moved.exit, moved.asked, String::from_utf8_lossy(&moved.stdout));
            }
            size = (moved.snapshot_bytes, moved.snapshot_nonzero);
        }
        println!("  moved to a fresh instance at each of {} waits: {} identical; memory {} bytes, {} non-zero", base.waits, same, size.0, size.1);
    }
}
