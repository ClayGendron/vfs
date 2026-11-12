//! Bench driver for the overlay-counts kernel spike. Reads the 2,000 bodies
//! study 02's generator wrote (one file each, UTF-8), then times, pass over
//! pass, the engine's `tokenize` as the Python overlay calls it today and
//! the kernel variants in `kernel.rs`, with no Python anywhere.
//!
//! Usage: overlay-kernel-bench <bodies dir> [passes]

#[path = "/Users/claygendron/Git/Repos/vfs/crates/vfs-core/src/lexical_tables.rs"]
#[allow(dead_code)]
mod lexical_tables;

#[path = "../../kernel.rs"]
mod kernel;

use std::collections::HashMap;
use std::hint::black_box;
use std::time::Instant;

// Study 02's five glean queries, folded as the verb folds them.
const QUERIES: &[(&str, &[&str])] = &[
    ("2 words (ranks 300, 3000)", &["lubavibu", "nessstenha"]),
    ("3 words (ranks 40, 1500, 9000)", &["bavozo", "lubeproes", "namenessho"]),
    ("4 words (ranks 700, 2000, 5000, 15000)", &["stkien", "ivethha", "cobu", "ivewearce"]),
    ("2 very common (ranks 5, 12)", &["goniha", "bitiondu"]),
    ("2 rare (ranks 8000, 20000)", &["mikelode", "larocon"]),
];

fn load(dir: &str) -> Vec<String> {
    let mut names: Vec<_> = std::fs::read_dir(dir)
        .expect("bodies dir")
        .map(|entry| entry.expect("entry").path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "txt"))
        .collect();
    names.sort();
    names.into_iter().map(|path| std::fs::read_to_string(path).expect("utf-8 body")).collect()
}

fn median(samples: &mut Vec<f64>) -> f64 {
    samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
    samples[samples.len() / 2]
}

/// Time `passes` runs of `f` over the whole corpus; returns the median seconds per pass.
fn time_passes(passes: usize, mut f: impl FnMut() -> u64) -> (f64, u64) {
    let mut checksum = 0;
    let mut samples = Vec::with_capacity(passes);
    for pass in 0..=passes {
        let start = Instant::now();
        checksum = black_box(f());
        if pass > 0 {
            samples.push(start.elapsed().as_secs_f64());
        }
    }
    (median(&mut samples), checksum)
}

struct Row {
    variant: &'static str,
    query: &'static str,
    terms: usize,
    seconds: f64,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let dir = args.get(1).expect("bodies dir");
    let passes: usize = args.get(2).map(|s| s.parse().expect("passes")).unwrap_or(7);
    let bodies = load(dir);
    let n_bodies = bodies.len();
    let bytes: usize = bodies.iter().map(|b| b.len()).sum();
    let chars: usize = bodies.iter().map(|b| b.chars().count()).sum();

    // The reference token stream, and the parity oracle for every variant.
    let reference: Vec<Vec<String>> = bodies.iter().map(|b| vfs_core::tokenize(b)).collect();
    let tokens: usize = reference.iter().map(|t| t.len()).sum();
    println!(
        "bodies {n_bodies} bytes {bytes} chars {chars} tokens {tokens} bytes/body {:.0} tokens/body {:.0} passes {passes}",
        bytes as f64 / n_bodies as f64,
        tokens as f64 / n_bodies as f64
    );

    // Parity: the fused kernel's token count and tfs must match the engine's tokenizer plus a dictionary.
    let mut scratch_chars = Vec::new();
    let mut scratch = String::new();
    for (_, terms) in QUERIES {
        for (body, reference_tokens) in bodies.iter().zip(&reference) {
            let mut counts: HashMap<&str, u32> = HashMap::new();
            for token in reference_tokens {
                *counts.entry(token.as_str()).or_insert(0) += 1;
            }
            let expected: Vec<u32> = terms.iter().map(|t| counts.get(t).copied().unwrap_or(0)).collect();
            let (total, tfs) = kernel::count_terms(body, terms, &mut scratch_chars, &mut scratch);
            assert_eq!(total as usize, reference_tokens.len(), "token count parity");
            assert_eq!(tfs, expected, "tf parity (fused)");
            let (total_d, tfs_d) = kernel::count_terms_dictionary(body, terms, &mut scratch_chars, &mut scratch);
            assert_eq!(total_d as usize, reference_tokens.len(), "token count parity (dictionary)");
            assert_eq!(tfs_d, expected, "tf parity (dictionary)");
            let (total_a, tfs_a) = kernel::count_terms_ascii(body, terms, &mut scratch_chars, &mut scratch);
            assert_eq!(total_a as usize, reference_tokens.len(), "token count parity (ascii)");
            assert_eq!(tfs_a, expected, "tf parity (ascii)");
        }
    }
    let ascii_bodies = bodies.iter().filter(|b| b.is_ascii()).count();
    println!(
        "parity: fused, dictionary and ascii kernels agree with vfs_core::tokenize + HashMap on every body and query ({ascii_bodies} of {n_bodies} bodies are all-ASCII)"
    );

    let mut rows: Vec<Row> = Vec::new();

    // A. The engine's tokenizer alone, as the Python overlay calls it: a Vec<String> per body.
    let (seconds, _) = time_passes(passes, || {
        let mut acc = 0u64;
        for body in &bodies {
            acc += vfs_core::tokenize(body).len() as u64;
        }
        acc
    });
    rows.push(Row { variant: "A tokenize -> Vec<String>", query: "(no terms)", terms: 0, seconds });

    for (query, terms) in QUERIES {
        // B. tokenize, then HashMap<&str, u32> over every token, then look up the terms: Counter's shape.
        let (seconds, _) = time_passes(passes, || {
            let mut acc = 0u64;
            for body in &bodies {
                let toks = vfs_core::tokenize(body);
                let mut counts: HashMap<&str, u32> = HashMap::new();
                for token in &toks {
                    *counts.entry(token.as_str()).or_insert(0) += 1;
                }
                acc += toks.len() as u64;
                for t in terms.iter() {
                    acc += u64::from(counts.get(t).copied().unwrap_or(0));
                }
            }
            acc
        });
        rows.push(Row { variant: "B tokenize + HashMap<&str,u32> + lookup", query, terms: terms.len(), seconds });

        // C. tokenize, then compare every token to the short term list; no dictionary.
        let (seconds, _) = time_passes(passes, || {
            let mut acc = 0u64;
            for body in &bodies {
                let toks = vfs_core::tokenize(body);
                acc += toks.len() as u64;
                for token in &toks {
                    for t in terms.iter() {
                        if token == t {
                            acc += 1;
                        }
                    }
                }
            }
            acc
        });
        rows.push(Row { variant: "C tokenize + linear compare", query, terms: terms.len(), seconds });

        // D. The fused kernel: no per-token allocation, no dictionary.
        let (seconds, _) = time_passes(passes, || {
            let mut acc = 0u64;
            let mut chars = Vec::new();
            let mut scratch = String::new();
            for body in &bodies {
                let (total, tfs) = kernel::count_terms(body, terms, &mut chars, &mut scratch);
                acc += u64::from(total) + tfs.iter().map(|&t| u64::from(t)).sum::<u64>();
            }
            acc
        });
        rows.push(Row { variant: "D fused count (no alloc, no map)", query, terms: terms.len(), seconds });

        // E. The fused tokenizer feeding a HashMap<String, u32> of every token.
        let (seconds, _) = time_passes(passes, || {
            let mut acc = 0u64;
            let mut chars = Vec::new();
            let mut scratch = String::new();
            for body in &bodies {
                let (total, tfs) = kernel::count_terms_dictionary(body, terms, &mut chars, &mut scratch);
                acc += u64::from(total) + tfs.iter().map(|&t| u64::from(t)).sum::<u64>();
            }
            acc
        });
        rows.push(Row { variant: "E fused + HashMap<String,u32>", query, terms: terms.len(), seconds });

        // G. The headroom probe: the same rules over bytes for all-ASCII bodies.
        let (seconds, _) = time_passes(passes, || {
            let mut acc = 0u64;
            let mut chars = Vec::new();
            let mut scratch = String::new();
            for body in &bodies {
                let (total, tfs) = kernel::count_terms_ascii(body, terms, &mut chars, &mut scratch);
                acc += u64::from(total) + tfs.iter().map(|&t| u64::from(t)).sum::<u64>();
            }
            acc
        });
        rows.push(Row { variant: "G ascii byte path (headroom probe)", query, terms: terms.len(), seconds });

        // F. The batch entry point the pyo3 prototype wraps: per-term postings over the corpus.
        let docs: Vec<(i64, &str)> = bodies.iter().enumerate().map(|(i, b)| (i as i64 + 1, b.as_str())).collect();
        let (seconds, _) = time_passes(passes, || {
            let (per_term, total_dl) = kernel::overlay_postings(&docs, terms);
            total_dl + per_term.iter().map(|p| p.len() as u64).sum::<u64>()
        });
        rows.push(Row { variant: "F overlay_postings batch", query, terms: terms.len(), seconds });
    }

    println!();
    println!("| variant | query | terms | s per pass | us per body | MB/s | ns per token |");
    println!("|---|---|---|---|---|---|---|");
    for row in &rows {
        println!(
            "| {} | {} | {} | {:.4} | {:.1} | {:.0} | {:.1} |",
            row.variant,
            row.query,
            row.terms,
            row.seconds,
            row.seconds * 1e6 / n_bodies as f64,
            bytes as f64 / row.seconds / 1e6,
            row.seconds * 1e9 / tokens as f64
        );
    }
}
