//! Print the corpus score: cases passing over cases total, by area and in all.
//! With `--write`, rewrite `tests/shell/known_failures.txt` from this run.
#![allow(clippy::unwrap_used, clippy::panic)]

#[path = "../tests/support/mod.rs"]
mod support;

fn main() {
    let cases = support::load_cases();
    let score = support::score(&cases, support::run_case);
    print!("{}", score.report());
    if std::env::args().any(|arg| arg == "--write") {
        let mut text = String::from(
            "# Every corpus case that does not yet pass. The corpus test fails when an unlisted case fails\n# and when a listed case passes; `scripts/shell_score.sh --write` rewrites this file.\n",
        );
        for name in &score.failing {
            text.push_str(name);
            text.push('\n');
        }
        std::fs::write(support::shell_dir().join("known_failures.txt"), text).unwrap();
        println!("wrote {} known failures", score.failing.len());
    }
}
