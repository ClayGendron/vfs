//! Run every case under a directory laid out as the corpus is, and print each one the shell
//! does not answer as bash recorded: its name, then why. The differential fuzzer reads this.
#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::arithmetic_side_effects
)]

#[path = "../tests/support/mod.rs"]
mod support;

fn main() {
    let root = std::env::args().nth(1).expect("a directory of cases");
    let cases = support::load_cases_from(std::path::Path::new(&root));
    let mut differ = 0;
    for case in &cases {
        if let Err(why) = support::run_case(case).and_then(|got| case.judge(&got)) {
            differ += 1;
            println!("DIFFER {}", case.name);
            println!("{}", why.replace('\n', "\n    "));
        }
    }
    println!("judged {} cases, {} differ", cases.len(), differ);
}
