//! Every corpus script parses to a tree, and every malformed one is refused
//! as a syntax error before anything runs.
#![allow(clippy::unwrap_used, clippy::panic, clippy::indexing_slicing)]

mod support;

use shell::syntax::{ParseError, ParseLimits, parse};

/// Whether bash's record says the script is malformed.
fn malformed(case: &support::Case) -> bool {
    let stderr = String::from_utf8_lossy(&case.record.stderr);
    case.record.status == 2
        && (stderr.contains("syntax error")
            || stderr.contains("unexpected EOF")
            || stderr.contains("unexpected end of file"))
}

/// Malformed to bash only because `extglob` was off when bash parsed the
/// line; this shell parses extglob always and fails the same way when it runs.
const EXTGLOB_AT_RUN: &[&str] = &[
    "case/extglob-pattern-is-an-error-when-off",
    "filename-expansion/extglob-not-enabled-is-a-syntax-error",
];

#[test]
fn every_case_parses_or_classifies() {
    let limits = ParseLimits::default();
    let deltas = support::read_list("deltas.txt");
    let mut wrong = Vec::new();
    let cases = support::load_cases();
    for case in &cases {
        let result = parse(&case.source, &limits);
        let ok = match (&result, malformed(case)) {
            (Ok(_), false) => true,
            (Ok(_), true) => EXTGLOB_AT_RUN.contains(&case.name.as_str()),
            (Err(ParseError::Syntax(..)), true) => true,
            (Err(ParseError::Refused(..)), _) => deltas.contains_key(&case.name),
            _ => false,
        };
        if !ok {
            wrong.push(format!("{}: {:?}", case.name, result.as_ref().err()));
        }
    }
    assert!(
        wrong.is_empty(),
        "{} of {} cases:\n{}",
        wrong.len(),
        cases.len(),
        wrong.join("\n")
    );
}
