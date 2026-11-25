//! The module's shadow stack, in its own linear memory, is sized here: the
//! machine's declared depth budgets must end a deep line before this stack
//! does, and a stack overflow past it traps rather than corrupting memory.

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    if std::env::var("CARGO_CFG_TARGET_ARCH").as_deref() == Ok("wasm32") {
        println!("cargo:rustc-link-arg-cdylib=-zstack-size={}", 8 << 20);
    }
}
