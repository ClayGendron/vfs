//! A line's statuses: one entry for each pipeline of its top level that set
//! `PIPESTATUS`, in order, each the machine's `PIPESTATUS` right after it,
//! which the recorded cases pin against bash. A pipeline inside a compound
//! command, a function, a subshell or a job adds none of its own, so the count
//! is bounded by the source, never by a loop.
#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
#![allow(clippy::arithmetic_side_effects)]

use shell::host::{MemoryHost, Outcome};

fn run(source: &str) -> Outcome {
    let mut host = MemoryHost::new();
    host.add_dir("/work");
    host.add_file("/work/a.txt", b"alpha\nbeta\n");
    let mut config = host.config();
    config.cwd = "/work".to_owned();
    host.run(source, config)
}

fn statuses(source: &str) -> Vec<Vec<i32>> {
    run(source).statuses
}

#[test]
fn a_pipeline_reports_each_stage() {
    assert_eq!(statuses("false | true"), vec![vec![1, 0]]);
    assert_eq!(statuses("cat /nope | wc -l"), vec![vec![1, 0]]);
}

#[test]
fn each_top_level_pipeline_is_one_entry_in_order() {
    assert_eq!(statuses("false; true | false"), vec![vec![1], vec![0, 1]]);
    assert_eq!(statuses("true\nfalse\n"), vec![vec![0], vec![1]]);
}

#[test]
fn a_pipeline_an_and_or_skipped_is_absent() {
    assert_eq!(statuses("false && true"), vec![vec![1]]);
    assert_eq!(
        statuses("true || false; false | false"),
        vec![vec![0], vec![1, 1]]
    );
}

#[test]
fn a_loop_is_one_entry_whatever_its_count() {
    let line = "for i in {1..1000}; do false | true; done";
    assert_eq!(statuses(line), vec![vec![1, 0]]);
}

#[test]
fn a_function_call_and_a_subshell_are_one_status() {
    assert_eq!(statuses("f() { false | true; }; f"), vec![vec![0]]);
    assert_eq!(statuses("(exit 3)"), vec![vec![3]]);
    assert_eq!(statuses("x=$(false)"), vec![vec![1]]);
}

#[test]
fn a_job_adds_no_entry_and_wait_reports_it() {
    assert_eq!(statuses("false | true & wait $!"), vec![vec![0]]);
    assert_eq!(statuses("(exit 4) & wait $!"), vec![vec![4]]);
}

#[test]
fn the_last_entry_is_where_the_line_stopped() {
    assert_eq!(
        statuses("set -e; true; false; true"),
        vec![vec![0], vec![0], vec![1]]
    );
    assert_eq!(statuses("true; exit 3; true"), vec![vec![0], vec![3]]);
}

/// A conditional and an arithmetic command set `PIPESTATUS` as a simple command does.
#[test]
fn a_test_or_arithmetic_command_is_one_status() {
    assert_eq!(statuses("[[ -f /nope ]]"), vec![vec![1]]);
    assert_eq!(statuses("true | false; (( 0 ))"), vec![vec![0, 1], vec![1]]);
    assert_eq!(statuses("! [[ 1 == 1 ]]"), vec![vec![1]]);
}

#[test]
fn a_line_that_never_parsed_has_no_entry() {
    assert_eq!(statuses("if"), Vec::<Vec<i32>>::new());
}

/// Each entry is what `${PIPESTATUS[*]}` reads right after its pipeline.
#[test]
fn each_entry_is_the_pipestatus_bash_reads_after_it() {
    let items = [
        "false | true | false",
        "if false | true; then :; fi",
        "while false; do :; done",
        "! false | true",
        "{ false | false; }",
        "case x in x) false | true ;; esac",
        "cat a.txt | grep -q beta",
        "set -o pipefail; false | true",
    ];
    for item in items {
        let probed = format!("{item}; echo \"${{PIPESTATUS[*]}}\"");
        let printed = String::from_utf8(run(&probed).stdout).unwrap();
        let expected: Vec<i32> = printed
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let entries = statuses(item);
        assert_eq!(entries.last(), Some(&expected), "{item}");
    }
}
