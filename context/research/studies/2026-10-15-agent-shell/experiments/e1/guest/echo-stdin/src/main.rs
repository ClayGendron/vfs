//! echo-stdin — copy stdin to stdout, byte for byte; report the byte count on stderr.
use std::io::{self, Read, Write};

fn main() {
    let mut buf = Vec::new();
    io::stdin().read_to_end(&mut buf).expect("stdin");
    io::stdout().write_all(&buf).expect("stdout");
    eprintln!("echo-stdin: {} bytes", buf.len());
}
