//! The conformance corpus against the reference host. The run fails when a
//! case fails that `known_failures.txt` does not list, and when a listed
//! case passes, so the list can only shrink and is always exact.
#![allow(clippy::unwrap_used, clippy::panic, clippy::indexing_slicing)]

mod support;

use std::collections::BTreeSet;

#[test]
fn the_corpus_matches_the_known_failures_list() {
    let cases = support::load_cases();
    let score = support::score(&cases, support::run_case);
    let names: BTreeSet<String> = cases.iter().map(|case| case.name.clone()).collect();
    let stale: Vec<String> = support::known_failures()
        .into_iter()
        .filter(|name| !names.contains(name))
        .collect();
    let mut problems = Vec::new();
    for (name, why) in score.unlisted_failures.iter().take(20) {
        problems.push(format!("FAILS, not listed: {name}\n{why}\n"));
    }
    if score.unlisted_failures.len() > 20 {
        problems.push(format!(
            "... and {} more unlisted failures",
            score.unlisted_failures.len() - 20
        ));
    }
    for name in &score.listed_passes {
        problems.push(format!("PASSES, still listed: {name}"));
    }
    for name in &stale {
        problems.push(format!("LISTED, no such case: {name}"));
    }
    println!("{}", score.report());
    assert!(
        problems.is_empty(),
        "{}\nrun `scripts/shell_score.sh --write` to rewrite the list",
        problems.join("\n")
    );
}

#[test]
fn the_deltas_list_is_exhaustive() {
    let deltas = support::read_list("deltas.txt");
    let cases = support::load_cases();
    let names: BTreeSet<String> = cases.iter().map(|case| case.name.clone()).collect();
    for (name, reason) in &deltas {
        assert!(
            names.contains(name),
            "deltas.txt names {name}, which is no case"
        );
        assert!(!reason.is_empty(), "deltas.txt gives {name} no reason");
    }
    for case in &cases {
        if case.delta.is_some() {
            assert!(
                deltas.contains_key(&case.name),
                "{} has a .shell.json but deltas.txt does not name it",
                case.name
            );
        }
    }
}
