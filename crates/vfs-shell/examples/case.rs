//! Run corpus cases and show how each differs from its record:
//! `cargo run -p vfs-shell --example case -- quoting/ builtin-read/some-case`.
#![allow(clippy::unwrap_used, clippy::panic)]

#[path = "../tests/support/mod.rs"]
mod support;

fn main() {
    let filters: Vec<String> = std::env::args().skip(1).collect();
    for case in support::load_cases() {
        if !filters.iter().any(|f| case.name.starts_with(f.as_str())) {
            continue;
        }
        let verdict = support::run_case(&case).and_then(|got| {
            case.judge(&got)
                .map_err(|why| (why, got))
                .map_err(|(why, got)| {
                    format!(
                        "{why}\n--- stderr got\n{}",
                        String::from_utf8_lossy(&got.stderr)
                    )
                })
        });
        if let Err(why) = verdict {
            println!("=== {}\n{}\n--- script\n{}\n", case.name, why, case.source);
        }
    }
}
