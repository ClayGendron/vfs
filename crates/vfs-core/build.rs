//! With the `python` feature, build the shell's machine as a WebAssembly
//! module and leave it in `OUT_DIR`, where the binding embeds it. The module
//! is built by a nested cargo run into its own target directory, for the
//! `wasm32-unknown-unknown` target, which the toolchain must have installed.

use std::env;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    if env::var_os("CARGO_FEATURE_PYTHON").is_none() {
        return;
    }
    let manifest = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap_or_default());
    let root = manifest.join("../..");
    for watched in [
        "crates/vfs-shell/src",
        "crates/vfs-shell/Cargo.toml",
        "crates/vfs-shell-wasm/src",
        "crates/vfs-shell-wasm/Cargo.toml",
        "crates/vfs-shell-wasm/build.rs",
    ] {
        println!("cargo:rerun-if-changed={}", root.join(watched).display());
    }
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap_or_default());
    let target_dir = out.join("shell-module");
    let cargo = env::var_os("CARGO").unwrap_or_else(|| "cargo".into());
    let mut command = Command::new(cargo);
    command
        .args([
            "build",
            "--release",
            "-p",
            "vfs-shell-wasm",
            "--target",
            "wasm32-unknown-unknown",
            "--target-dir",
        ])
        .arg(&target_dir)
        .current_dir(&root);
    // The outer build's flags and target are for the host, never for the module.
    for name in [
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_BUILD_TARGET",
        "CARGO_TARGET_DIR",
        "CARGO_BUILD_RUSTFLAGS",
    ] {
        command.env_remove(name);
    }
    let status = command.status();
    if !matches!(status, Ok(s) if s.success()) {
        println!(
            "cargo:warning=the shell module did not build: see the errors above; the target is added with `rustup target add wasm32-unknown-unknown`"
        );
        std::process::exit(1);
    }
    let built = target_dir.join("wasm32-unknown-unknown/release/shell_wasm.wasm");
    let embedded = out.join("shell.wasm");
    if let Err(error) = std::fs::copy(&built, &embedded) {
        println!(
            "cargo:warning=the shell module was not found at {}: {error}",
            built.display()
        );
        std::process::exit(1);
    }
}
