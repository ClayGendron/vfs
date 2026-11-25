//! Print the tree a line parses to: `cargo run -p vfs-shell --example parse -- 'echo hi'`.
fn main() {
    let source = std::env::args().nth(1).unwrap_or_default();
    match shell::syntax::parse(&source, &shell::syntax::ParseLimits::default()) {
        Ok(script) => println!("{:#?}", script.body),
        Err(error) => println!("{error:?}"),
    }
}
