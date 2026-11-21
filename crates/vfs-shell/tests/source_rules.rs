//! The rules the crate's own source is held to: it names no host, it can
//! reach no file, process, network, environment, thread or clock, and it
//! holds no unsafe code.
#![allow(clippy::unwrap_used, clippy::panic)]

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

#[test]
fn nothing_reaches_past_the_machine() {
    let forbidden = [
        "std::fs",
        "std::process",
        "std::net",
        "std::env",
        "std::thread",
        "std::time",
        "std::os",
    ];
    for (path, text) in sources() {
        for name in forbidden {
            assert!(!text.contains(name), "{} uses {name}", path.display());
        }
    }
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
