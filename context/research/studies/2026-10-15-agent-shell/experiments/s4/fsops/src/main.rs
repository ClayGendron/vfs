//! `fsops <op> <args...>`: one POSIX file operation per run, so the shim's
//! mapping of each WASI call can be observed in isolation. Errors print the
//! raw WASI errno and exit 2.
use std::io::{Read, Seek, SeekFrom, Write};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let op = args.get(1).map(String::as_str).unwrap_or("");
    let a = |i: usize| args.get(i).cloned().unwrap_or_default();
    let r: std::io::Result<()> = match op {
        "cat" => (|| { let mut s = String::new(); std::fs::File::open(a(2))?.read_to_string(&mut s)?; std::io::stdout().write_all(s.as_bytes()) })(),
        "catbytes" => (|| { let b = std::fs::read(a(2))?; eprintln!("{} bytes, head={:?}", b.len(), &b[..b.len().min(4)]); Ok(()) })(),
        "write" => std::fs::write(a(2), a(3)),
        "append" => (|| { let mut f = std::fs::OpenOptions::new().append(true).create(true).open(a(2))?; f.write_all(a(3).as_bytes()) })(),
        "patch" => (|| { let mut f = std::fs::OpenOptions::new().write(true).open(a(2))?; f.seek(SeekFrom::Start(a(4).parse().unwrap()))?; f.write_all(a(3).as_bytes()) })(),
        "range" => (|| { let mut f = std::fs::File::open(a(2))?; f.seek(SeekFrom::Start(a(3).parse().unwrap()))?; let mut buf = vec![0u8; a(4).parse().unwrap()]; let n = f.read(&mut buf)?; std::io::stdout().write_all(&buf[..n]) })(),
        "truncate" => (|| { let f = std::fs::OpenOptions::new().write(true).open(a(2))?; f.set_len(a(3).parse().unwrap()) })(),
        "rm" => std::fs::remove_file(a(2)),
        "mv" => std::fs::rename(a(2), a(3)),
        "mkdir" => std::fs::create_dir(a(2)),
        "rmdir" => std::fs::remove_dir(a(2)),
        "ls" => (|| { let mut v = Vec::new(); for e in std::fs::read_dir(a(2))? { let e = e?; v.push(format!("{} {}", if e.file_type()?.is_dir() { "d" } else { "f" }, e.file_name().to_string_lossy())); } v.sort(); println!("{}", v.join("\n")); Ok(()) })(),
        "count" => (|| { let n = std::fs::read_dir(a(2))?.count(); println!("{n}"); Ok(()) })(),
        "stat" => (|| { let m = std::fs::metadata(a(2))?; println!("len={} dir={} readonly={} mtime_ok={}", m.len(), m.is_dir(), m.permissions().readonly(), m.modified().is_ok()); Ok(()) })(),
        "tee" => (|| { let mut b = Vec::new(); std::io::stdin().read_to_end(&mut b)?; std::fs::write(a(2), &b) })(),
        "stdin" => (|| { let mut s = String::new(); std::io::stdin().read_to_string(&mut s)?; print!("{}", s.to_uppercase()); Ok(()) })(),
        "env" => { for (k, v) in std::env::vars() { println!("{k}={v}"); } Ok(()) }
        "cwd" => { println!("{:?}", std::env::current_dir()); Ok(()) }
        "exit" => std::process::exit(a(2).parse().unwrap()),
        _ => Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "usage")),
    };
    if let Err(e) = r {
        eprintln!("{op}: {e} [raw_os_error={:?}]", e.raw_os_error());
        std::process::exit(2);
    }
}
