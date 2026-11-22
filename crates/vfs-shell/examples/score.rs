//! Print the corpus score: cases passing over cases total, by area and in all.
//! With `--write`, rewrite `tests/shell/known_failures.txt` from this run.
#![allow(clippy::unwrap_used, clippy::panic)]

#[path = "../tests/support/mod.rs"]
mod support;

fn main() {
    let cases = support::load_cases();
    let score = support::score(&cases, support::run_case);
    print!("{}", score.report());
    if std::env::args().any(|arg| arg == "--write-deltas") {
        write_deltas(&cases);
    }
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

/// Write the shell's own record for each listed delta that is a refusal, and only then.
fn write_deltas(cases: &[support::Case]) {
    let deltas = support::read_list("deltas.txt");
    for case in cases {
        if !deltas.contains_key(&case.name) || case.delta.is_some() {
            continue;
        }
        let Ok(got) = support::run_case(case) else {
            continue;
        };
        let stderr = String::from_utf8_lossy(&got.stderr).into_owned();
        if got.status != 2 || !stderr.contains("refused") || !got.stdout.is_empty() {
            println!("not a refusal, no record written: {}", case.name);
            continue;
        }
        let path = support::shell_dir()
            .join("cases")
            .join(format!("{}.shell.json", case.name));
        let record = format!(
            "{{\n  \"status\": {},\n  \"stdout\": \"\",\n  \"stderr\": {}\n}}\n",
            got.status,
            json_string(&stderr)
        );
        std::fs::write(path, record).unwrap();
        println!("wrote the shell's record: {}", case.name);
    }
}

fn json_string(text: &str) -> String {
    let mut out = String::from("\"");
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
