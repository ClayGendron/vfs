//! Run a script file over a MemoryHost (cwd /work) and pass its stdout, stderr and status through.
use shell::host::MemoryHost;
use std::io::Write;

fn main() {
    let path = std::env::args().nth(1).unwrap();
    let source = std::fs::read_to_string(path).unwrap();
    let mut host = MemoryHost::new();
    host.add_dir("/work");
    host.add_dir("/tmp");
    let mut config = host.config();
    config.cwd = "/work".to_owned();
    let outcome = host.run(&source, config);
    std::io::stdout().write_all(&outcome.stdout).ok();
    std::io::stderr().write_all(&outcome.stderr).ok();
    if let Some(why) = outcome.ended { eprintln!("[ended: {why}]"); }
    std::process::exit(outcome.status);
}
