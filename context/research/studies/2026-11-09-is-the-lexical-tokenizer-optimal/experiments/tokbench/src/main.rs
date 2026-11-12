//! Bench driver for the tokenizer profile study. Loads corpus A (a
//! directory of `.txt` bodies) and corpus B (a manifest of absolute file
//! paths), then for each corpus: the stage profile of `vfs_core::tokenize`,
//! the candidate variants (each asserted byte-identical to the engine's
//! output on every body before it is timed), and the builder's counting
//! against the borrowed-lookup variant. Allocations are counted by the
//! global allocator in `alloc.rs`. Clocks are medians of `passes` passes
//! after one warm-up pass. Writes a Markdown report to stdout and a JSON
//! file of every row.
//!
//! Usage: tokbench <bodies_a dir> <manifest_b file> <out.json> [passes]

#[path = "/Users/claygendron/Git/Repos/vfs/crates/vfs-core/src/lexical_tables.rs"]
#[allow(dead_code)]
mod lexical_tables;

mod alloc;
mod builder_variant;
mod variants;

use std::collections::hash_map::RandomState;
use std::hint::black_box;
use std::time::Instant;

use builder_variant::{BorrowedAccumulator, Feed, FnvBuild};
use vfs_core::LexicalAccumulator;

#[global_allocator]
static GLOBAL: alloc::Counting = alloc::Counting;

struct Corpus {
    name: &'static str,
    bodies: Vec<String>,
    bytes: usize,
    non_ascii_bytes: usize,
    chars: usize,
    tokens: usize,
    reference: Vec<Vec<String>>,
}

fn load_dir(dir: &str) -> Vec<String> {
    let mut names: Vec<_> = std::fs::read_dir(dir)
        .expect("bodies dir")
        .map(|entry| entry.expect("entry").path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "txt"))
        .collect();
    names.sort();
    names.into_iter().map(|path| std::fs::read_to_string(path).expect("utf-8 body")).collect()
}

fn load_manifest(manifest: &str) -> (Vec<String>, usize) {
    let listing = std::fs::read_to_string(manifest).expect("manifest");
    let mut bodies = Vec::new();
    let mut skipped = 0usize;
    for line in listing.lines().filter(|l| !l.is_empty()) {
        match std::fs::read(line) {
            Ok(raw) => match String::from_utf8(raw) {
                Ok(text) => bodies.push(text),
                Err(_) => skipped += 1,
            },
            Err(_) => skipped += 1,
        }
    }
    (bodies, skipped)
}

fn corpus(name: &'static str, bodies: Vec<String>) -> Corpus {
    let bytes = bodies.iter().map(|b| b.len()).sum();
    let non_ascii_bytes = bodies.iter().map(|b| b.bytes().filter(|c| !c.is_ascii()).count()).sum();
    let chars = bodies.iter().map(|b| b.chars().count()).sum();
    let reference: Vec<Vec<String>> = bodies.iter().map(|b| vfs_core::tokenize(b)).collect();
    let tokens = reference.iter().map(|t| t.len()).sum();
    Corpus { name, bodies, bytes, non_ascii_bytes, chars, tokens, reference }
}

fn median(samples: &mut [f64]) -> f64 {
    samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
    samples[samples.len() / 2]
}

/// Median seconds per pass over `passes` timed passes after one warm-up,
/// and the allocations of one pass.
fn time_passes(passes: usize, mut f: impl FnMut() -> u64) -> (f64, alloc::Snapshot, u64) {
    let mut checksum = 0;
    let mut samples = Vec::with_capacity(passes);
    let mut allocs = alloc::Snapshot::default();
    for pass in 0..=passes {
        let before = alloc::snapshot();
        let start = Instant::now();
        checksum = black_box(f());
        let elapsed = start.elapsed().as_secs_f64();
        if pass == 0 {
            allocs = alloc::delta(before, alloc::snapshot());
        } else {
            samples.push(elapsed);
        }
    }
    (median(&mut samples), allocs, checksum)
}

#[derive(Clone)]
struct Row {
    corpus: &'static str,
    section: &'static str,
    variant: &'static str,
    parity: &'static str,
    seconds: f64,
    allocs: alloc::Snapshot,
}

fn per_body(row: &Row, n: usize) -> f64 {
    row.seconds * 1e6 / n as f64
}

fn checksum_terms(terms: &[String]) -> u64 {
    terms.iter().map(|t| t.len() as u64 + 1).sum()
}

/// Assert `candidate` equals the engine's output on every body; the
/// first mismatch is reported and the candidate marked as failing.
fn parity(corpus: &Corpus, candidate: impl Fn(&str) -> Vec<String>) -> &'static str {
    for (body, reference) in corpus.bodies.iter().zip(&corpus.reference) {
        let got = candidate(body);
        if &got != reference {
            let first = got.iter().zip(reference).position(|(a, b)| a != b).unwrap_or(got.len().min(reference.len()));
            eprintln!(
                "PARITY FAILURE on {}: {} terms vs {} reference; first difference at {}: {:?} vs {:?}",
                corpus.name,
                got.len(),
                reference.len(),
                first,
                got.get(first),
                reference.get(first)
            );
            return "FAILS";
        }
    }
    "identical"
}

fn run_corpus(c: &Corpus, passes: usize, rows: &mut Vec<Row>) {
    let n = c.bodies.len();
    println!(
        "corpus {}: bodies {} bytes {} non-ASCII bytes {} ({:.3}%) chars {} tokens {} bytes/body {:.0} tokens/body {:.0}",
        c.name,
        n,
        c.bytes,
        c.non_ascii_bytes,
        100.0 * c.non_ascii_bytes as f64 / c.bytes as f64,
        c.chars,
        c.tokens,
        c.bytes as f64 / n as f64,
        c.tokens as f64 / n as f64
    );
    let ascii_bodies = c.bodies.iter().filter(|b| b.is_ascii()).count();
    println!("  all-ASCII bodies: {ascii_bodies} of {n}");

    let mut push = |section: &'static str, variant: &'static str, parity: &'static str, seconds: f64, allocs: alloc::Snapshot| {
        rows.push(Row { corpus: c.name, section, variant, parity, seconds, allocs });
    };

    // --- The profile: the engine's function, then the pipeline cut stage by stage.
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| vfs_core::tokenize(b).len() as u64).sum());
    push("profile", "vfs_core::tokenize (the engine)", "reference", s, a);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_chars(b)).sum());
    push("profile", "(i) chars collection", "n/a", s, a);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_scan(b)).sum());
    push("profile", "(ii) + run scan and class checks", "n/a", s, a);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_split(b)).sum());
    push("profile", "(iii) + identifier split", "n/a", s, a);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_fold(b)).sum());
    push("profile", "(iv) + fold into scratch", "n/a", s, a);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_check(b)).sum());
    push("profile", "(v) + length check", "n/a", s, a);
    let p = parity(c, variants::stage_full);
    let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::stage_full(b).len() as u64).sum());
    push("profile", "(vi) + clone: the full function, staged copy", p, s, a);

    // --- The candidates, each asserted against the engine before timing.
    let p = parity(c, variants::cand_a_no_vec_char);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::cand_a_no_vec_char(b).len() as u64).sum());
        push("candidate", "(a) no Vec<char>: char_indices and byte slices", p, s, a);
    } else {
        push("candidate", "(a) no Vec<char>: char_indices and byte slices", p, f64::NAN, alloc::Snapshot::default());
    }

    let b_as_vec = |body: &str| {
        let mut out = Vec::new();
        let mut chars = Vec::new();
        let mut scratch = String::new();
        variants::cand_b_for_each_term(body, &mut chars, &mut scratch, |t| out.push(t.to_owned()));
        out
    };
    let p = parity(c, b_as_vec);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || {
            let mut chars = Vec::new();
            let mut scratch = String::new();
            let mut acc = 0u64;
            for body in &c.bodies {
                variants::cand_b_for_each_term(body, &mut chars, &mut scratch, |t| acc += t.len() as u64 + 1);
            }
            acc
        });
        push("candidate", "(b) borrowed &str sink, counter (no clone)", p, s, a);
    } else {
        push("candidate", "(b) borrowed &str sink, counter (no clone)", p, f64::NAN, alloc::Snapshot::default());
    }

    let p = parity(c, variants::cand_c_ascii_runs);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::cand_c_ascii_runs(b).len() as u64).sum());
        push("candidate", "(c) ASCII run fast path on (a)'s scan, Vec<String> out", p, s, a);
    } else {
        push("candidate", "(c) ASCII run fast path on (a)'s scan, Vec<String> out", p, f64::NAN, alloc::Snapshot::default());
    }

    let p = parity(c, variants::cand_d_byte_length_check);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::cand_d_byte_length_check(b).len() as u64).sum());
        push("candidate", "(d) byte-first length check", p, s, a);
    } else {
        push("candidate", "(d) byte-first length check", p, f64::NAN, alloc::Snapshot::default());
    }

    let p = parity(c, variants::cand_e_ascii_class_table);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::cand_e_ascii_class_table(b).len() as u64).sum());
        push("candidate", "(e) 128-entry ASCII class table", p, s, a);
    } else {
        push("candidate", "(e) 128-entry ASCII class table", p, f64::NAN, alloc::Snapshot::default());
    }

    let p = parity(c, variants::cand_f_to_vec);
    if p == "identical" {
        let (s, a, _) = time_passes(passes, || {
            let mut parts = Vec::new();
            let mut scratch = String::new();
            let mut acc = 0u64;
            for body in &c.bodies {
                variants::cand_f_for_each_term(body, &mut parts, &mut scratch, |t| acc += t.len() as u64 + 1);
            }
            acc
        });
        push("candidate", "(f) a+b+c+d+e, counter sink (the builder's use)", p, s, a);
        let (s, a, _) = time_passes(passes, || c.bodies.iter().map(|b| variants::cand_f_to_vec(b).len() as u64).sum());
        push("candidate", "(f) a+b+c+d+e, Vec<String> out (the binding's use)", p, s, a);
    } else {
        push("candidate", "(f) a+b+c+d+e", p, f64::NAN, alloc::Snapshot::default());
    }

    // --- The builder: the engine's accumulator against the borrowed-lookup variant.
    let docs: Vec<(i64, &str)> = c.bodies.iter().enumerate().map(|(i, b)| (i as i64 + 1, b.as_str())).collect();
    let (s, a, _) = time_passes(passes, || {
        let mut acc = LexicalAccumulator::new();
        let mut total = 0u64;
        for &(id, body) in &docs {
            total += u64::from(acc.add_doc(id, body).expect("increasing ids"));
        }
        black_box(&acc);
        total
    });
    push("builder", "LexicalAccumulator::add_doc (the engine)", "reference", s, a);

    // Parity of the drained rows, once per feed and hasher.
    let mut engine = LexicalAccumulator::new();
    for &(id, body) in &docs {
        engine.add_doc(id, body).unwrap();
    }
    let mut drained = engine.finish();
    let (ref_n, ref_avg) = (drained.n_docs, drained.avg_dl);
    let ref_summaries = drained.next_df_batch(usize::MAX).unwrap_or_default();
    let ref_blocks = drained.next_batch(usize::MAX).unwrap_or_default();
    let builder_parity = |feed: Feed| -> &'static str {
        let mut acc: BorrowedAccumulator<RandomState> = BorrowedAccumulator::new(feed);
        for &(id, body) in &docs {
            acc.add_doc(id, body).unwrap();
        }
        let (n_docs, avg_dl, summaries, blocks) = acc.finish_and_drain();
        if n_docs != ref_n || avg_dl != ref_avg || summaries.len() != ref_summaries.len() || blocks.len() != ref_blocks.len() {
            eprintln!("BUILDER PARITY FAILURE ({feed:?}): counts differ");
            return "FAILS";
        }
        for (a, b) in summaries.iter().zip(&ref_summaries) {
            if a.term != b.term || a.df != b.df || a.idf != b.idf || a.max_weight != b.max_weight || a.blocks != b.blocks {
                eprintln!("BUILDER PARITY FAILURE ({feed:?}): summary of {} differs", a.term);
                return "FAILS";
            }
        }
        for (a, b) in blocks.iter().zip(&ref_blocks) {
            if a.term != b.term || a.block_no != b.block_no || a.doc_count != b.doc_count || a.doc_ids != b.doc_ids || a.tfs != b.tfs || a.dls != b.dls {
                eprintln!("BUILDER PARITY FAILURE ({feed:?}): block {} of {} differs", a.block_no, a.term);
                return "FAILS";
            }
        }
        "identical rows"
    };
    println!("  distinct terms: {}", ref_summaries.len());

    for (feed, label_sip, label_fnv) in [
        (Feed::Baseline, "borrowed lookup, (b) feed, SipHash", "borrowed lookup, (b) feed, FNV-1a"),
        (Feed::Combined, "borrowed lookup, (f) feed, SipHash", "borrowed lookup, (f) feed, FNV-1a"),
    ] {
        let p = builder_parity(feed);
        if p != "identical rows" {
            push("builder", label_sip, p, f64::NAN, alloc::Snapshot::default());
            continue;
        }
        let (s, a, _) = time_passes(passes, || {
            let mut acc: BorrowedAccumulator<RandomState> = BorrowedAccumulator::new(feed);
            let mut total = 0u64;
            for &(id, body) in &docs {
                total += u64::from(acc.add_doc(id, body).expect("increasing ids"));
            }
            black_box(&acc);
            total
        });
        push("builder", label_sip, p, s, a);
        let (s, a, _) = time_passes(passes, || {
            let mut acc: BorrowedAccumulator<FnvBuild> = BorrowedAccumulator::new(feed);
            let mut total = 0u64;
            for &(id, body) in &docs {
                total += u64::from(acc.add_doc(id, body).expect("increasing ids"));
            }
            black_box(&acc);
            total
        });
        push("builder", label_fnv, p, s, a);
    }

    // The engine's finish, for the share of the builder outside add_doc.
    let (s, a, _) = time_passes(passes, || {
        let mut acc = LexicalAccumulator::new();
        for &(id, body) in &docs {
            acc.add_doc(id, body).unwrap();
        }
        let mut drained = acc.finish();
        let mut total = drained.n_docs;
        while let Some(batch) = drained.next_batch(20_000) {
            total += batch.len() as u64;
        }
        total
    });
    push("builder", "engine add_doc + finish + block drain (whole build CPU)", "reference", s, a);

    let _ = checksum_terms;
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let dir_a = args.get(1).expect("bodies_a dir");
    let manifest_b = args.get(2).expect("manifest_b");
    let out_json = args.get(3).expect("out.json");
    let passes: usize = args.get(4).map(|s| s.parse().expect("passes")).unwrap_or(7);

    let a = corpus("A", load_dir(dir_a));
    let (bodies_b, skipped) = load_manifest(manifest_b);
    let b = corpus("B", bodies_b);
    println!("passes {passes}; corpus B files skipped as non-UTF-8 or unreadable: {skipped}");

    let mut rows = Vec::new();
    run_corpus(&a, passes, &mut rows);
    run_corpus(&b, passes, &mut rows);

    for c in [&a, &b] {
        let n = c.bodies.len();
        let base = rows.iter().find(|r| r.corpus == c.name && r.section == "profile").map(|r| r.seconds).unwrap();
        println!();
        println!("corpus {} ({} bodies, {} bytes, {} tokens)", c.name, n, c.bytes, c.tokens);
        println!();
        println!("| section | variant | parity | us per body | MB/s | ns per token | allocs per body | reallocs per body | alloc bytes per body | vs engine |");
        println!("|---|---|---|---|---|---|---|---|---|---|");
        for row in rows.iter().filter(|r| r.corpus == c.name) {
            if row.seconds.is_nan() {
                println!("| {} | {} | {} | not timed | | | | | | |", row.section, row.variant, row.parity);
                continue;
            }
            println!(
                "| {} | {} | {} | {:.1} | {:.0} | {:.1} | {:.1} | {:.1} | {:.0} | {:.2}x |",
                row.section,
                row.variant,
                row.parity,
                per_body(row, n),
                c.bytes as f64 / row.seconds / 1e6,
                row.seconds * 1e9 / c.tokens as f64,
                row.allocs.allocs as f64 / n as f64,
                row.allocs.reallocs as f64 / n as f64,
                row.allocs.bytes as f64 / n as f64,
                row.seconds / base
            );
        }
    }

    let mut json = String::from("[\n");
    for (i, row) in rows.iter().enumerate() {
        let c = if row.corpus == "A" { &a } else { &b };
        let n = c.bodies.len();
        json.push_str(&format!(
            "  {{\"corpus\": \"{}\", \"bodies\": {}, \"bytes\": {}, \"tokens\": {}, \"section\": \"{}\", \"variant\": \"{}\", \"parity\": \"{}\", \"seconds_per_pass\": {}, \"us_per_body\": {}, \"allocs_per_pass\": {}, \"reallocs_per_pass\": {}, \"alloc_bytes_per_pass\": {}}}{}\n",
            row.corpus,
            n,
            c.bytes,
            c.tokens,
            row.section,
            row.variant.replace('"', "'"),
            row.parity,
            if row.seconds.is_nan() { "null".to_string() } else { format!("{:.6}", row.seconds) },
            if row.seconds.is_nan() { "null".to_string() } else { format!("{:.3}", per_body(row, n)) },
            row.allocs.allocs,
            row.allocs.reallocs,
            row.allocs.bytes,
            if i + 1 == rows.len() { "" } else { "," }
        ));
    }
    json.push_str("]\n");
    std::fs::write(out_json, json).expect("write json");
}
