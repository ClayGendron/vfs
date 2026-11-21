//! The earlier study's measured commands: the 100 weighted to the shares
//! agents type, and the 100 that touch every construct. Every one parses,
//! and the run rate, the share whose every command name runs here, is held
//! at its measured floor.
#![allow(
    clippy::unwrap_used,
    clippy::panic,
    clippy::indexing_slicing,
    clippy::arithmetic_side_effects,
    clippy::string_slice
)]

use std::path::PathBuf;

use shell::host::MemoryHost;
use shell::syntax::{ParseLimits, parse};

fn commands(file: &str) -> Vec<String> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../context/research/studies/2026-10-15-agent-shell/experiments/s1")
        .join(file);
    std::fs::read_to_string(path)
        .unwrap()
        .lines()
        .map(|line| {
            let start = line.find("\"cmd\": \"").unwrap() + 8;
            let body = &line[start..line.len() - 2];
            body.replace("\\\"", "\"")
                .replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace("\\\\", "\\")
        })
        .collect()
}

/// The share of `lines` that run with no name unresolved and nothing refused.
fn run_rate(lines: &[String]) -> usize {
    let mut ran = 0;
    for line in lines {
        let mut host = MemoryHost::new();
        host.add_dir("/work/src/vfs");
        let mut config = host.config();
        config.cwd = "/work".to_owned();
        let outcome = host.run(line, config);
        let stderr = String::from_utf8_lossy(&outcome.stderr);
        if !stderr.contains("command not found")
            && !stderr.contains("refused")
            && outcome.ended.is_none()
        {
            ran += 1;
        }
    }
    ran
}

#[test]
fn every_measured_command_parses() {
    for file in ["corpus.jsonl", "corpus-coverage.jsonl"] {
        let lines = commands(file);
        assert_eq!(lines.len(), 100);
        for line in &lines {
            assert!(
                parse(line, &ParseLimits::default()).is_ok(),
                "{file}: {line}"
            );
        }
    }
}

/// The run rate of the weighted sample, measured when this floor was set; it may only rise.
const WEIGHTED_RUN_FLOOR: usize = 72;

#[test]
fn the_weighted_sample_runs_at_its_floor() {
    let rate = run_rate(&commands("corpus.jsonl"));
    println!("weighted sample run rate: {rate} of 100");
    assert!(rate >= WEIGHTED_RUN_FLOOR, "{rate} of 100 ran");
}
