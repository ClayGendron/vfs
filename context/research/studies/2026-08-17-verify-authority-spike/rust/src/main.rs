//! S3 of the verify-authority spike: regex-crate verify over raw bytes.
//!
//! Reads the manifest spike.py's bench phase writes (patterns already
//! spelled for the regex crate, per-query candidate file lists), preloads
//! every referenced file once (untimed), then times three strategies per
//! query, median over `runs`:
//!
//! - `regex_1t`  — find_iter over the whole body, enclosing line recovered
//!   and sliced per match (single thread): the full-Rust-authority shape.
//! - `regex_mt`  — the same, rayon-parallel across files.
//! - `prefilter_1t` — memmem on the guaranteed literal, line recovery per
//!   hit; Confirmed rows count the line outright, Candidate rows run the
//!   regex on the line slice only (single thread).
//!
//! Output: one JSON object on stdout keyed by query label, with wall ms
//! plus files/lines counts for the S0 parity check. Line slices are
//! materialized as ranges only — handing them back across a pyo3 boundary
//! is priced separately by the Python side's encode-tax measurement.

use std::collections::HashMap;
use std::time::Instant;

use memchr::{memchr, memmem, memrchr};
use rayon::prelude::*;
use regex::bytes::{Regex, RegexBuilder};
use serde::Deserialize;
use serde_json::{json, Map, Value};

#[derive(Deserialize)]
struct Query {
    label: String,
    pattern: String,
    ci: bool,
    multiline: bool,
    literal: Option<String>,
    confirmed: bool,
    files: Vec<String>,
}

#[derive(Deserialize)]
struct Manifest {
    root: String,
    runs: usize,
    queries: Vec<Query>,
}

fn line_bounds(hay: &[u8], start: usize, end: usize) -> (usize, usize) {
    let ls = memrchr(b'\n', &hay[..start]).map_or(0, |i| i + 1);
    let le = memchr(b'\n', &hay[end..]).map_or(hay.len(), |i| end + i);
    (ls, le)
}

/// Distinct matched lines in one body; matches never span lines (patterns
/// exclude `\n` by the manifest's spelling law).
fn regex_lines(re: &Regex, hay: &[u8]) -> u64 {
    let mut lines = 0u64;
    let mut last_start = usize::MAX;
    for m in re.find_iter(hay) {
        let (ls, le) = line_bounds(hay, m.start(), m.end());
        if ls != last_start {
            last_start = ls;
            lines += 1;
            std::hint::black_box(&hay[ls..le]);
        }
    }
    lines
}

fn prefilter_lines(finder: &memmem::Finder, re: Option<&Regex>, hay: &[u8]) -> u64 {
    let mut lines = 0u64;
    let mut pos = 0usize;
    while pos <= hay.len() {
        let Some(off) = finder.find(&hay[pos..]) else { break };
        let hit = pos + off;
        let (ls, le) = line_bounds(hay, hit, hit + finder.needle().len());
        let line = &hay[ls..le];
        let admitted = match re {
            None => true,
            Some(r) => r.is_match(line),
        };
        if admitted {
            lines += 1;
            std::hint::black_box(line);
        }
        pos = le + 1;
    }
    lines
}

fn median(mut samples: Vec<f64>) -> f64 {
    samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
    samples[samples.len() / 2]
}

fn timed<F: FnMut() -> (u64, u64)>(runs: usize, mut f: F) -> (f64, u64, u64) {
    let mut samples = Vec::with_capacity(runs);
    let mut counts = (0, 0);
    for _ in 0..runs {
        let t0 = Instant::now();
        counts = f();
        samples.push(t0.elapsed().as_secs_f64() * 1000.0);
    }
    (median(samples), counts.0, counts.1)
}

fn main() {
    let manifest_path = std::env::args().nth(1).expect("usage: verify-spike <manifest.json>");
    let manifest: Manifest =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).expect("read manifest"))
            .expect("parse manifest");

    let mut contents: HashMap<&str, Vec<u8>> = HashMap::new();
    for q in &manifest.queries {
        for f in &q.files {
            if !contents.contains_key(f.as_str()) {
                let path = std::path::Path::new(&manifest.root).join(f);
                contents.insert(f.as_str(), std::fs::read(&path).expect("read file"));
            }
        }
    }
    eprintln!("preloaded {} files", contents.len());

    let mut out = Map::new();
    for q in &manifest.queries {
        let re = RegexBuilder::new(&q.pattern)
            .case_insensitive(q.ci)
            .multi_line(q.multiline)
            .build()
            .unwrap_or_else(|e| panic!("{}: pattern rejected by regex crate: {e}", q.label));
        let bodies: Vec<&[u8]> = q.files.iter().map(|f| contents[f.as_str()].as_slice()).collect();

        let (ms_1t, files_1t, lines_1t) = timed(manifest.runs, || {
            let mut files = 0u64;
            let mut lines = 0u64;
            for hay in &bodies {
                let n = regex_lines(&re, hay);
                if n > 0 {
                    files += 1;
                    lines += n;
                }
            }
            (files, lines)
        });
        let (ms_mt, files_mt, lines_mt) = timed(manifest.runs, || {
            bodies
                .par_iter()
                .map(|hay| {
                    let n = regex_lines(&re, hay);
                    (u64::from(n > 0), n)
                })
                .reduce(|| (0, 0), |a, b| (a.0 + b.0, a.1 + b.1))
        });
        let mut row = Map::new();
        row.insert("candidates".into(), json!(bodies.len()));
        row.insert("regex_1t".into(), json!({"ms": ms_1t, "files": files_1t, "lines": lines_1t}));
        row.insert("regex_mt".into(), json!({"ms": ms_mt, "files": files_mt, "lines": lines_mt}));
        if let Some(lit) = &q.literal {
            let finder = memmem::Finder::new(lit.as_bytes());
            let line_re = if q.confirmed { None } else { Some(&re) };
            let (ms_pf, files_pf, lines_pf) = timed(manifest.runs, || {
                let mut files = 0u64;
                let mut lines = 0u64;
                for hay in &bodies {
                    let n = prefilter_lines(&finder, line_re, hay);
                    if n > 0 {
                        files += 1;
                        lines += n;
                    }
                }
                (files, lines)
            });
            row.insert("prefilter_1t".into(), json!({"ms": ms_pf, "files": files_pf, "lines": lines_pf}));
        }
        eprintln!(
            "  {:<22} n={:>6}  1t {:>9.1}ms  mt {:>9.1}ms  lines {}",
            q.label,
            bodies.len(),
            ms_1t,
            ms_mt,
            lines_1t
        );
        out.insert(q.label.clone(), Value::Object(row));
    }
    println!("{}", serde_json::to_string_pretty(&Value::Object(out)).unwrap());
}
