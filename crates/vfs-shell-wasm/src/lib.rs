//! The shell's machine as a WebAssembly module.
//!
//! The module has one machine at a time and one shared buffer. A host asks
//! for `buffer(len)`, writes JSON into the memory it points at, and calls
//! `start(len)` with a line and its configuration, then `step(len)` with the
//! replies to what the last step asked. Each returns the length of the JSON
//! it left in the buffer: the step's output, its requests and its status.
//! A host that counts fuel outside the module answers the import
//! `host.slice_spent()`, and the machine hands control back when it says so.
//!
//! The only unsafe code is here: the export attributes, and the one call to
//! the host's import. The machine itself forbids unsafe code.

pub mod wire;

use std::cell::RefCell;

use shell::machine::{Machine, Status, Step};

thread_local! {
    static STATE: RefCell<State> = const { RefCell::new(State { machine: None, buffer: Vec::new() }) };
}

struct State {
    machine: Option<Machine>,
    buffer: Vec<u8>,
}

/// Make the shared buffer `len` bytes long and return where it starts.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn buffer(len: u32) -> u32 {
    STATE.with(|state| {
        let mut state = state.borrow_mut();
        state.buffer.clear();
        state.buffer.resize(usize::try_from(len).unwrap_or(0), 0);
        address(&state.buffer)
    })
}

/// Where the shared buffer starts now.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn buffer_address() -> u32 {
    STATE.with(|state| address(&state.borrow().buffer))
}

fn address(buffer: &[u8]) -> u32 {
    u32::try_from(buffer.as_ptr().addr()).unwrap_or(0)
}

/// Start a line from the JSON in the first `len` bytes of the buffer.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn start(len: u32) -> u32 {
    STATE.with(|state| {
        let mut state = state.borrow_mut();
        let text = take_text(&state.buffer, len);
        let answer = match wire::decode_start(&text) {
            Err(message) => error_json(&message),
            Ok((source, config)) => match Machine::new(&source, config) {
                Ok(mut machine) => {
                    if cfg!(target_arch = "wasm32") {
                        machine.set_slice_probe(Box::new(probe));
                    }
                    state.machine = Some(machine);
                    "{\"started\":true}".to_owned()
                }
                Err(error) => error_json(&format!("{error:?}")),
            },
        };
        put(&mut state.buffer, answer)
    })
}

/// Run the machine on, given the replies in the first `len` bytes of the buffer.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn step(len: u32) -> u32 {
    STATE.with(|state| {
        let mut state = state.borrow_mut();
        let text = take_text(&state.buffer, len);
        let answer = match (wire::decode_replies(&text), state.machine.as_mut()) {
            (Err(message), _) => error_json(&message),
            (_, None) => error_json("no line has started"),
            (Ok(replies), Some(machine)) => {
                let step: Step = machine.step(replies);
                let memory = machine.memory_used();
                if !matches!(step.status, Status::Running) {
                    state.machine = None;
                }
                wire::encode_step(&step, memory)
            }
        };
        put(&mut state.buffer, answer)
    })
}

/// Stop the line: its next step ends it.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn cancel() {
    STATE.with(|state| {
        if let Some(machine) = state.borrow_mut().machine.as_mut() {
            machine.cancel();
        }
    });
}

fn take_text(buffer: &[u8], len: u32) -> String {
    let len = usize::try_from(len).unwrap_or(0).min(buffer.len());
    String::from_utf8_lossy(buffer.get(..len).unwrap_or_default()).into_owned()
}

fn put(buffer: &mut Vec<u8>, text: String) -> u32 {
    *buffer = text.into_bytes();
    u32::try_from(buffer.len()).unwrap_or(0)
}

fn error_json(message: &str) -> String {
    format!("{{\"error\":{}}}", wire::quote(message))
}

#[cfg(target_arch = "wasm32")]
#[allow(unsafe_code)]
mod host {
    #[link(wasm_import_module = "host")]
    unsafe extern "C" {
        /// Whether the fuel this step may spend is spent: 1 or 0.
        pub safe fn slice_spent() -> i32;
    }
}

#[cfg(target_arch = "wasm32")]
fn probe() -> bool {
    host::slice_spent() != 0
}

#[cfg(not(target_arch = "wasm32"))]
fn probe() -> bool {
    false
}
