//! Drive the shell machine over a MemoryHost on one line; report steps, requests, output and time.
use shell::host::MemoryHost;
use shell::machine::{Machine, Status, Stream};
use std::time::{Duration, Instant};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let line = if args[1] == "-f" { std::fs::read_to_string(&args[2]).unwrap() } else { args[1].clone() };
    let wall = Duration::from_secs(std::env::var("PROBE_SECS").ok().and_then(|s| s.parse().ok()).unwrap_or(20));
    let mut host = MemoryHost::new();
    host.add_file("/work/a.txt", b"alpha\nbeta\ngamma\n");
    host.add_dir("/work/d/e");
    let mut config = host.config();
    config.cwd = "/work".to_owned();
    let start = Instant::now();
    let mut machine = match Machine::new(&line, config) {
        Ok(m) => m,
        Err(e) => { println!("start_error={e:?} secs={:.3}", start.elapsed().as_secs_f64()); return; }
    };
    let (mut steps, mut requests, mut out, mut err, mut peak) = (0u64, 0u64, 0usize, Vec::new(), 0usize);
    let mut head = Vec::new();
    let mut replies = Vec::new();
    let status = loop {
        let step = machine.step(std::mem::take(&mut replies));
        steps += 1;
        peak = peak.max(machine.memory_used());
        for (s, b) in step.output {
            match s { Stream::Stdout => { if head.len() < 120 { head.extend_from_slice(&b[..b.len().min(120)]); } out += b.len(); }
                      Stream::Stderr => { if err.len() < 300 { err.extend_from_slice(&b); } } }
        }
        for (k, r) in step.requests { requests += 1; replies.push((k, host.answer(&r))); }
        if !matches!(step.status, Status::Running) { break format!("{:?}", step.status); }
        if start.elapsed() > wall { break format!("PROBE-WALL-STOP after {:?} (the machine was still Running)", wall); }
    };
    println!("status={status} steps={steps} requests={requests} stdout_len={out} peak_counted_bytes={peak} secs={:.3}",
             start.elapsed().as_secs_f64());
    println!("stdout_head={:?}", String::from_utf8_lossy(&head[..head.len().min(120)]));
    println!("stderr_head={:?}", String::from_utf8_lossy(&err[..err.len().min(300)]));
}
