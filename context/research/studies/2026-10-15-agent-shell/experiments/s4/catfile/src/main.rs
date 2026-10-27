//! A twenty-line WASI program for the vfs shim experiment.
//! `catfile <path>` reads the file, prints it to stdout, then appends a
//! line to `<path>.out` and lists the directory `/data`.
use std::io::{Read, Write};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let path = args.get(1).map(String::as_str).unwrap_or("/data/hello.txt");
    let mut text = String::new();
    std::fs::File::open(path).expect("open").read_to_string(&mut text).expect("read");
    std::io::stdout().write_all(text.as_bytes()).expect("stdout");
    let meta = std::fs::metadata(path).expect("stat");
    eprintln!("stat: len={} is_file={}", meta.len(), meta.is_file());
    std::fs::write(format!("{path}.out"), format!("copied {} bytes\n", text.len())).expect("write");
    let mut names: Vec<String> = std::fs::read_dir("/data").expect("readdir")
        .map(|e| e.expect("entry").file_name().to_string_lossy().into_owned()).collect();
    names.sort();
    eprintln!("readdir /data: {}", names.join(","));
    std::process::exit(if text.is_empty() { 3 } else { 0 });
}
