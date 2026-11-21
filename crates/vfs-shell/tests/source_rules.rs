//! The rules the crate's own source is held to: it names no host, it can
//! reach no file, process, network, environment, thread or clock, and it
//! holds no unsafe code.
#![allow(
    clippy::unwrap_used,
    clippy::panic,
    clippy::string_slice,
    clippy::arithmetic_side_effects,
    clippy::indexing_slicing
)]

use std::fs;
use std::path::{Path, PathBuf};

fn sources() -> Vec<(PathBuf, String)> {
    let mut out = Vec::new();
    walk(&Path::new(env!("CARGO_MANIFEST_DIR")).join("src"), &mut out);
    assert!(!out.is_empty());
    out
}

fn walk(dir: &Path, out: &mut Vec<(PathBuf, String)>) {
    for entry in fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            walk(&path, out);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            let text = fs::read_to_string(&path).unwrap();
            out.push((path, text));
        }
    }
}

#[test]
fn no_identifier_names_the_first_host() {
    for (path, text) in sources() {
        assert!(
            !text.to_lowercase().contains("vfs"),
            "{} names the first host",
            path.display()
        );
    }
}

/// The modules of `std` that reach past the machine.
const FORBIDDEN: &[&str] = &["fs", "process", "net", "env", "thread", "time", "os", "io"];

/// The names a path through `std` reaches, grouped imports included.
fn std_paths(code: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut rest = code;
    while let Some(at) = rest.find("std::") {
        let after = &rest[at + 5..];
        if let Some(group) = after.strip_prefix('{') {
            let end = group.find('}').unwrap_or(group.len());
            for item in group[..end].split(',') {
                let name = item
                    .trim()
                    .split(|c: char| !c.is_alphanumeric() && c != '_')
                    .next()
                    .unwrap_or("");
                found.push(name.to_owned());
            }
        } else {
            let name: String = after
                .chars()
                .take_while(|c| c.is_alphanumeric() || *c == '_')
                .collect();
            found.push(name);
        }
        rest = &rest[at + 5..];
    }
    found
}

#[test]
fn nothing_reaches_past_the_machine() {
    for (path, text) in sources() {
        let code: String = text
            .lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        for name in std_paths(&code) {
            assert!(
                !FORBIDDEN.contains(&name.as_str()),
                "{} reaches std::{name}",
                path.display()
            );
        }
        for token in [
            "fs::File",
            "process::Command",
            "TcpStream",
            "UdpSocket",
            "SystemTime",
            "Instant::",
            "thread_local!",
            "extern crate",
        ] {
            assert!(!code.contains(token), "{} uses {token}", path.display());
        }
    }
}

#[test]
fn the_rule_sees_a_grouped_import() {
    assert_eq!(
        std_paths("use std::{env as _e, fs as _f, process as _p};"),
        vec!["env", "fs", "process"]
    );
    assert_eq!(std_paths("let x = std::fs::read(p);"), vec!["fs"]);
}

#[test]
fn the_crate_holds_no_unsafe_code() {
    for (path, text) in sources() {
        let code: String = text
            .lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect();
        assert!(
            !code.contains("unsafe"),
            "{} holds unsafe code",
            path.display()
        );
    }
    let manifest =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml")).unwrap();
    assert!(manifest.contains("unsafe_code = \"forbid\""));
}

#[test]
fn the_crate_has_no_dependencies() {
    let manifest =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml")).unwrap();
    let deps = manifest
        .split("[dependencies]")
        .nth(1)
        .unwrap()
        .split('[')
        .next()
        .unwrap();
    assert!(
        deps.trim().is_empty(),
        "the crate declares dependencies: {deps}"
    );
}
