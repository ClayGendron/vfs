//! Option B prototype bench, Rust side.
//!
//!   rustbench tokens <store.sqlite> <out.txt>
//!       tokenize every covered chunk (ascending id); write `#<id>` then one
//!       token per line — the parity oracle diffs this against Python.
//!   rustbench build <store.sqlite> <out.sqlite> <block_size> [epoch]
//!       one streaming pass: tokenize, accumulate compressed postings per
//!       term, flush full blocks as they fill; then df/idf, docs, stats.
//!   rustbench score <blobs.bin> <reps>
//!       decode + score + top-10 per query, timed in-process (no DB).

mod codec;
mod tables;
mod tokenizer;

use codec::{decode_deltas, decode_varints, put_varint};
use rusqlite::{params, Connection};
use std::collections::HashMap;
use std::io::{BufWriter, Read, Write};
use std::time::Instant;
use tokenizer::tokenize;

const K1: f64 = 1.2;
const B: f64 = 0.75;
const TOP_K: usize = 10;

const SCAN: &str = "SELECT c.id, c.entry_id, c.content FROM vfs_chunks c JOIN vfs e ON e.entry_id = c.entry_id \
                    WHERE e.chunked AND e.indexable AND e.deleted_at IS NULL ORDER BY c.id";

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("tokens") => cmd_tokens(&args[2], &args[3]),
        Some("build") => cmd_build(
            &args[2],
            &args[3],
            args[4].parse().expect("block size"),
            args.get(5).map(|s| s.parse().expect("epoch")).unwrap_or(1),
        ),
        Some("score") => cmd_score(&args[2], args[3].parse().expect("reps")),
        _ => {
            eprintln!("usage: rustbench tokens|build|score ...");
            std::process::exit(2);
        }
    }
}

// ---------------------------------------------------------------------------
// tokens
// ---------------------------------------------------------------------------

fn cmd_tokens(store: &str, out_path: &str) {
    let conn = Connection::open(store).expect("open store");
    let mut stmt = conn.prepare(SCAN).expect("prepare");
    let mut rows = stmt.query([]).expect("query");
    let mut out = BufWriter::with_capacity(1 << 20, std::fs::File::create(out_path).expect("create"));
    let mut n_chunks = 0u64;
    let mut n_tokens = 0u64;
    let mut tokenize_ns = 0u128;
    while let Some(row) = rows.next().expect("row") {
        let id: i64 = row.get(0).unwrap();
        let content: String = row.get(2).unwrap();
        let t0 = Instant::now();
        let terms = tokenize(&content);
        tokenize_ns += t0.elapsed().as_nanos();
        writeln!(out, "#{id}").unwrap();
        for t in &terms {
            out.write_all(t.as_bytes()).unwrap();
            out.write_all(b"\n").unwrap();
        }
        n_chunks += 1;
        n_tokens += terms.len() as u64;
    }
    out.flush().unwrap();
    println!(
        "{{\"chunks\": {n_chunks}, \"tokens\": {n_tokens}, \"tokenize_s\": {:.4}}}",
        tokenize_ns as f64 / 1e9
    );
}

// ---------------------------------------------------------------------------
// build
// ---------------------------------------------------------------------------

/// One term's open block plus its running statistics.
struct TermAcc {
    df: u32,
    block_no: u32,
    count: u32,
    last_id: i64,
    max_tf: u32,
    min_dl: u32,
    ids: Vec<u8>,
    tfs: Vec<u8>,
    dls: Vec<u8>,
}

impl TermAcc {
    fn new() -> Self {
        TermAcc { df: 0, block_no: 0, count: 0, last_id: 0, max_tf: 0, min_dl: u32::MAX, ids: Vec::new(), tfs: Vec::new(), dls: Vec::new() }
    }
    fn push(&mut self, id: i64, tf: u32, dl: u32) {
        put_varint(&mut self.ids, (id - self.last_id) as u64);
        put_varint(&mut self.tfs, tf as u64);
        put_varint(&mut self.dls, dl as u64);
        self.last_id = id;
        self.count += 1;
        self.df += 1;
        self.max_tf = self.max_tf.max(tf);
        self.min_dl = self.min_dl.min(dl);
    }
    fn reset_block(&mut self) {
        self.block_no += 1;
        self.count = 0;
        self.last_id = 0;
        self.max_tf = 0;
        self.min_dl = u32::MAX;
        self.ids.clear();
        self.tfs.clear();
        self.dls.clear();
    }
}

fn cmd_build(store: &str, out_path: &str, block_size: u32, epoch: i64) {
    let t_wall = Instant::now();
    let _ = std::fs::remove_file(out_path);
    let src = Connection::open(store).expect("open store");
    let dst = Connection::open(out_path).expect("open out");
    dst.execute_batch(
        "PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;
         CREATE TABLE lex_postings (epoch INTEGER NOT NULL, term VARCHAR(64) NOT NULL, block_no INTEGER NOT NULL,
             doc_count INTEGER NOT NULL, max_tf INTEGER NOT NULL, min_dl INTEGER NOT NULL,
             doc_ids BLOB NOT NULL, tfs BLOB NOT NULL, dls BLOB NOT NULL,
             PRIMARY KEY (epoch, term, block_no)) WITHOUT ROWID;
         CREATE TABLE lex_docs (epoch INTEGER NOT NULL, chunk_id BIGINT NOT NULL, entry_id BINARY(16) NOT NULL,
             dl INTEGER NOT NULL, PRIMARY KEY (epoch, chunk_id)) WITHOUT ROWID;
         CREATE TABLE lex_df (epoch INTEGER NOT NULL, term VARCHAR(64) NOT NULL, df INTEGER NOT NULL, idf DOUBLE NOT NULL,
             PRIMARY KEY (epoch, term)) WITHOUT ROWID;
         CREATE TABLE lex_stats (epoch INTEGER NOT NULL, n_docs INTEGER NOT NULL, avg_dl DOUBLE NOT NULL,
             PRIMARY KEY (epoch)) WITHOUT ROWID;",
    )
    .expect("schema");
    dst.execute_batch("BEGIN").unwrap();
    let mut ins_block = dst
        .prepare("INSERT INTO lex_postings VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)")
        .unwrap();
    let mut ins_doc = dst.prepare("INSERT INTO lex_docs VALUES (?1, ?2, ?3, ?4)").unwrap();

    let mut accs: HashMap<String, TermAcc> = HashMap::new();
    let mut stmt = src.prepare(SCAN).expect("prepare");
    let mut rows = stmt.query([]).expect("query");
    let mut n_docs = 0u64;
    let mut total_dl = 0u64;
    let mut rows_written = 0u64;
    let mut tokenize_ns = 0u128;
    let mut counts: Vec<(String, u32)> = Vec::new();
    while let Some(row) = rows.next().expect("row") {
        let id: i64 = row.get(0).unwrap();
        let entry_id: Vec<u8> = row.get(1).unwrap();
        let content: String = row.get(2).unwrap();
        let t0 = Instant::now();
        let mut terms = tokenize(&content);
        tokenize_ns += t0.elapsed().as_nanos();
        let dl = terms.len() as u32;
        terms.sort_unstable();
        counts.clear();
        for term in terms.drain(..) {
            match counts.last_mut() {
                Some((last, tf)) if *last == term => *tf += 1,
                _ => counts.push((term, 1)),
            }
        }
        for (term, tf) in counts.drain(..) {
            let full = match accs.get_mut(&term) {
                Some(acc) => {
                    acc.push(id, tf, dl);
                    acc.count == block_size
                }
                None => {
                    let mut acc = TermAcc::new();
                    acc.push(id, tf, dl);
                    let full = acc.count == block_size;
                    accs.insert(term.clone(), acc);
                    full
                }
            };
            if full {
                let acc = accs.get_mut(&term).unwrap();
                ins_block
                    .execute(params![epoch, term, acc.block_no, acc.count, acc.max_tf, acc.min_dl, &acc.ids, &acc.tfs, &acc.dls])
                    .unwrap();
                acc.reset_block();
                rows_written += 1;
            }
        }
        ins_doc.execute(params![epoch, id, entry_id, dl]).unwrap();
        n_docs += 1;
        total_dl += dl as u64;
    }
    // Trailing partial blocks, sorted by term; df/idf.
    let mut terms: Vec<&String> = accs.keys().collect();
    terms.sort_unstable();
    let mut ins_df = dst.prepare("INSERT INTO lex_df VALUES (?1, ?2, ?3, ?4)").unwrap();
    let n = n_docs as f64;
    for term in terms {
        let acc = &accs[term];
        let idf = (1.0 + (n - acc.df as f64 + 0.5) / (acc.df as f64 + 0.5)).ln();
        ins_df.execute(params![epoch, term, acc.df, idf]).unwrap();
        if acc.count > 0 {
            rows_written += 1;
            ins_block
                .execute(params![epoch, term, acc.block_no, acc.count, acc.max_tf, acc.min_dl, &acc.ids, &acc.tfs, &acc.dls])
                .unwrap();
        }
    }
    dst.execute("INSERT INTO lex_stats VALUES (?1, ?2, ?3)", params![epoch, n_docs as i64, total_dl as f64 / n]).unwrap();
    drop(ins_block);
    drop(ins_doc);
    drop(ins_df);
    dst.execute_batch("COMMIT").unwrap();
    let block_rows: i64 = dst.query_row("SELECT COUNT(*) FROM lex_postings", [], |r| r.get(0)).unwrap();
    let blob_bytes: i64 = dst
        .query_row("SELECT SUM(LENGTH(doc_ids) + LENGTH(tfs) + LENGTH(dls)) FROM lex_postings", [], |r| r.get(0))
        .unwrap();
    println!(
        "{{\"wall_s\": {:.4}, \"tokenize_s\": {:.4}, \"n_docs\": {n_docs}, \"total_tokens\": {total_dl}, \"terms\": {}, \"block_rows\": {block_rows}, \"rows_written\": {rows_written}, \"blob_bytes\": {blob_bytes}, \"block_size\": {block_size}}}",
        t_wall.elapsed().as_secs_f64(),
        tokenize_ns as f64 / 1e9,
        accs.len()
    );
}

// ---------------------------------------------------------------------------
// score
// ---------------------------------------------------------------------------

struct Block {
    max_tf: u32,
    min_dl: u32,
    ids: Vec<u8>,
    tfs: Vec<u8>,
    dls: Vec<u8>,
}

struct Term {
    idf: f64,
    blocks: Vec<Block>,
}

struct Query {
    avg_dl: f64,
    terms: Vec<Term>,
}

fn read_u32(r: &mut &[u8]) -> u32 {
    let (a, rest) = r.split_at(4);
    *r = rest;
    u32::from_le_bytes(a.try_into().unwrap())
}

fn read_f64(r: &mut &[u8]) -> f64 {
    let (a, rest) = r.split_at(8);
    *r = rest;
    f64::from_le_bytes(a.try_into().unwrap())
}

fn read_bytes(r: &mut &[u8]) -> Vec<u8> {
    let n = read_u32(r) as usize;
    let (a, rest) = r.split_at(n);
    *r = rest;
    a.to_vec()
}

fn read_queries(path: &str) -> Vec<Query> {
    let mut data = Vec::new();
    std::fs::File::open(path).expect("open").read_to_end(&mut data).unwrap();
    let mut r: &[u8] = &data;
    let n_queries = read_u32(&mut r);
    let mut queries = Vec::new();
    for _ in 0..n_queries {
        let avg_dl = read_f64(&mut r);
        let n_terms = read_u32(&mut r);
        let mut terms = Vec::new();
        for _ in 0..n_terms {
            let idf = read_f64(&mut r);
            let n_blocks = read_u32(&mut r);
            let mut blocks = Vec::new();
            for _ in 0..n_blocks {
                let _doc_count = read_u32(&mut r);
                let max_tf = read_u32(&mut r);
                let min_dl = read_u32(&mut r);
                let ids = read_bytes(&mut r);
                let tfs = read_bytes(&mut r);
                let dls = read_bytes(&mut r);
                blocks.push(Block { max_tf, min_dl, ids, tfs, dls });
            }
            terms.push(Term { idf, blocks });
        }
        queries.push(Query { avg_dl, terms });
    }
    queries
}

/// Full evaluation: decode every block, score, sort-merge by id, top-10.
fn score_query(q: &Query, ids: &mut Vec<i64>, tfs: &mut Vec<u64>, dls: &mut Vec<u64>, pairs: &mut Vec<(i64, f64)>) -> Vec<(i64, f64)> {
    pairs.clear();
    let norm_base = K1 * (1.0 - B);
    let norm_scale = K1 * B / q.avg_dl;
    for term in &q.terms {
        for block in &term.blocks {
            let _ = (block.max_tf, block.min_dl);
            ids.clear();
            tfs.clear();
            dls.clear();
            decode_deltas(&block.ids, ids);
            decode_varints(&block.tfs, tfs);
            decode_varints(&block.dls, dls);
            for i in 0..ids.len() {
                let tf = tfs[i] as f64;
                let w = term.idf * tf * (K1 + 1.0) / (tf + norm_base + norm_scale * dls[i] as f64);
                pairs.push((ids[i], w));
            }
        }
    }
    pairs.sort_unstable_by_key(|p| p.0);
    let mut top: Vec<(i64, f64)> = Vec::with_capacity(TOP_K + 1);
    let mut i = 0;
    while i < pairs.len() {
        let id = pairs[i].0;
        let mut s = 0.0;
        while i < pairs.len() && pairs[i].0 == id {
            s += pairs[i].1;
            i += 1;
        }
        if top.len() < TOP_K || s > top[TOP_K - 1].1 {
            top.push((id, s));
            top.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap().then(a.0.cmp(&b.0)));
            top.truncate(TOP_K);
        }
    }
    top
}

fn cmd_score(path: &str, reps: usize) {
    let queries = read_queries(path);
    let mut ids = Vec::new();
    let mut tfs = Vec::new();
    let mut dls = Vec::new();
    let mut pairs = Vec::new();
    let mut out = String::from("[");
    for (qi, q) in queries.iter().enumerate() {
        let mut times = Vec::with_capacity(reps);
        let mut top = Vec::new();
        for _ in 0..reps {
            let t0 = Instant::now();
            top = score_query(q, &mut ids, &mut tfs, &mut dls, &mut pairs);
            times.push(t0.elapsed().as_nanos() as f64 / 1e6);
        }
        times.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let median = times[times.len() / 2];
        let postings: usize = q.terms.iter().map(|t| t.blocks.iter().map(|b| b.tfs.len()).sum::<usize>()).sum();
        if qi > 0 {
            out.push(',');
        }
        out.push_str(&format!(
            "{{\"median_ms\": {median:.4}, \"postings_ge\": {postings}, \"top\": [{}]}}",
            top.iter().map(|(id, s)| format!("[{id}, {s:.9}]")).collect::<Vec<_>>().join(",")
        ));
    }
    out.push(']');
    println!("{out}");
}
