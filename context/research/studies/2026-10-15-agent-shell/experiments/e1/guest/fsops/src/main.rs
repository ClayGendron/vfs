//! fsops ls DIR | mv A B | rm A | mkdir D | stat P | append P TEXT — the directory and mutation calls.
use std::{env, fs, io::{Seek, SeekFrom, Write}, process};

fn main() {
    let a: Vec<String> = env::args().collect();
    let r = match (a.get(1).map(String::as_str), a.get(2), a.get(3)) {
        (Some("ls"), Some(d), _) => fs::read_dir(d).map(|it| {
            let mut names: Vec<String> = it.filter_map(|e| e.ok()).map(|e| {
                let k = if e.file_type().map(|t| t.is_dir()).unwrap_or(false) { "d" } else { "f" };
                format!("{} {}", k, e.file_name().to_string_lossy())
            }).collect();
            names.sort();
            for n in names { println!("{n}"); }
        }),
        (Some("mv"), Some(x), Some(y)) => fs::rename(x, y),
        (Some("rm"), Some(x), _) => fs::remove_file(x),
        (Some("rmdir"), Some(x), _) => fs::remove_dir(x),
        (Some("mkdir"), Some(x), _) => fs::create_dir(x),
        (Some("stat"), Some(x), _) => fs::metadata(x).map(|m| println!("{} {} bytes", if m.is_dir() {"d"} else {"f"}, m.len())),
        (Some("append"), Some(x), Some(t)) => fs::OpenOptions::new().append(true).open(x).and_then(|mut f| { f.write_all(t.as_bytes())?; f.write_all(b"\n") }),
        (Some("seek"), Some(x), _) => fs::File::open(x).and_then(|mut f| { f.seek(SeekFrom::End(-4))?; let mut s = String::new(); std::io::Read::read_to_string(&mut f, &mut s)?; print!("{s}"); Ok(()) }),
        _ => { eprintln!("usage: fsops ls|mv|rm|rmdir|mkdir|stat|append|seek ..."); process::exit(2); }
    };
    if let Err(e) = r { eprintln!("fsops: {e}"); process::exit(1); }
}
