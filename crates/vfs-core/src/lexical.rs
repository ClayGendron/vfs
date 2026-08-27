//! The lexical (BM25) engine: the tokenizer, block postings, the builder
//! and the scorer.
//!
//! The tokenizer is a port of the host's reference tokenizer driven by the
//! host interpreter's own character classes (`lexical_tables.rs`, generated),
//! so the two cannot disagree on what a letter, a capital or a fold is. The
//! builder streams documents once — tokenize, count, append each posting to
//! its term's open block, seal a block at `BLOCK_SIZE` — and at `finish`
//! fixes the corpus statistics, each term's idf and every block's true
//! maximum weight, then drains summary rows and block rows in term order.
//! Sealed blocks stay resident until `finish` (a block's true maximum needs
//! the final statistics); residency is per-term structure rather than blob
//! bytes — ~660 B per distinct term measured against ~4.5 B per posting — so
//! an arena for the term streams is the direction if a vocabulary outgrows
//! memory, never a corpus limit.
//!
//! The scorer decodes fetched blocks, accumulates BM25 per document in a
//! fixed order (terms by descending maximum, block order, posting order —
//! the same order the host's fallback uses, so sums are bit-identical),
//! skips blocks that cannot change the top-k, and ranks `score DESC, id ASC`.
//!
//! Wire shapes: `doc_ids` is the gram codec's count-prefixed delta+varint
//! blob (deltas restart at each block, so a block decodes alone); `tfs` and
//! `dls` are plain LEB128 varints; a term's summary is, per block, the
//! varint delta of its first id from the previous block's and the block's
//! maximum weight as a little-endian `f64`.

use std::collections::HashMap;

use crate::lexical_tables::{ASSIGNED, CASEFOLD, DIGIT, LOWER, UPPER, WORD};

pub use crate::lexical_tables::{PYTHON_VERSION, UNICODE_VERSION};

pub const BLOCK_SIZE: usize = 128;
pub const BM25_K1: f64 = 1.2;
pub const BM25_B: f64 = 0.75;
const MIN_TERM_CHARS: usize = 2;
const MAX_TERM_BYTES: usize = 64;

/// Bit flags of `char_classes`, one byte per code point.
pub const CLASS_WORD: u8 = 1;
pub const CLASS_UPPER: u8 = 2;
pub const CLASS_LOWER: u8 = 4;
pub const CLASS_DIGIT: u8 = 8;
pub const CLASS_ASSIGNED: u8 = 16;

#[derive(Debug, PartialEq, Eq)]
pub enum LexicalError {
    NonIncreasingDocId { doc_id: i64, last: i64 },
    Sealed,
}

impl std::fmt::Display for LexicalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NonIncreasingDocId { doc_id, last } => {
                write!(f, "doc ids must be strictly increasing and positive; got {doc_id} after {last}")
            }
            Self::Sealed => write!(f, "statistics are fixed; create a fresh builder"),
        }
    }
}

impl std::error::Error for LexicalError {}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

fn in_ranges(table: &[(u32, u32)], ch: char) -> bool {
    let cp = ch as u32;
    table
        .binary_search_by(|&(lo, hi)| {
            if cp < lo {
                std::cmp::Ordering::Greater
            } else if cp > hi {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

#[inline]
fn is_word(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_alphanumeric() || ch == '_' } else { in_ranges(&WORD, ch) }
}

#[inline]
fn is_upper(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_uppercase() } else { in_ranges(&UPPER, ch) }
}

#[inline]
fn is_lower(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_lowercase() } else { in_ranges(&LOWER, ch) }
}

#[inline]
fn is_digit(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_digit() } else { in_ranges(&DIGIT, ch) }
}

/// The host's `fold_content`: Turkic-i pre-fold, then the interpreter's
/// per-code-point casefold.
fn fold_into(raw: &[char], out: &mut String) {
    out.clear();
    for &ch in raw {
        if ch.is_ascii() {
            out.push(ch.to_ascii_lowercase());
            continue;
        }
        let ch = if ch == '\u{131}' || ch == '\u{130}' { 'i' } else { ch };
        match CASEFOLD.binary_search_by_key(&(ch as u32), |&(cp, _)| cp) {
            Ok(i) => out.push_str(CASEFOLD[i].1),
            Err(_) => out.push(ch),
        }
    }
}

fn emit(terms: &mut Vec<String>, raw: &[char], scratch: &mut String) {
    fold_into(raw, scratch);
    if scratch.chars().count() >= MIN_TERM_CHARS && scratch.len() <= MAX_TERM_BYTES {
        terms.push(scratch.clone());
    }
}

fn case_boundary(piece: &[char], index: usize) -> bool {
    let previous = piece[index - 1];
    if is_lower(previous) || is_digit(previous) {
        return true;
    }
    is_upper(previous) && index + 1 < piece.len() && is_lower(piece[index + 1])
}

/// One word run's parts: split on underscores, then on case changes; a
/// digit-led piece stays whole.
fn identifier_parts<'a>(run: &'a [char], parts: &mut Vec<&'a [char]>) {
    parts.clear();
    for piece in run.split(|&c| c == '_') {
        if piece.is_empty() {
            continue;
        }
        if is_digit(piece[0]) {
            parts.push(piece);
            continue;
        }
        let mut start = 0;
        for index in 1..piece.len() {
            if is_upper(piece[index]) && case_boundary(piece, index) {
                parts.push(&piece[start..index]);
                start = index;
            }
        }
        parts.push(&piece[start..]);
    }
}

/// Folded terms in order, duplicates kept: each word run whole, and its
/// parts when there are more than one.
pub fn tokenize(content: &str) -> Vec<String> {
    let chars: Vec<char> = content.chars().collect();
    let mut terms = Vec::new();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        emit(&mut terms, run, &mut scratch);
        if parts.len() > 1 {
            for part in parts.iter() {
                emit(&mut terms, part, &mut scratch);
            }
        }
    }
    terms
}

/// The class flags of every code point (surrogates zero), for the host's
/// parity check against its own interpreter.
pub fn char_classes() -> Vec<u8> {
    let mut out = vec![0u8; 0x11_0000];
    for (table, flag) in [
        (&WORD[..], CLASS_WORD),
        (&UPPER[..], CLASS_UPPER),
        (&LOWER[..], CLASS_LOWER),
        (&DIGIT[..], CLASS_DIGIT),
        (&ASSIGNED[..], CLASS_ASSIGNED),
    ] {
        for &(lo, hi) in table {
            for cp in lo..=hi {
                out[cp as usize] |= flag;
            }
        }
    }
    out
}

/// The casefold map the tokenizer folds through.
pub fn casefolds() -> &'static [(u32, &'static str)] {
    &CASEFOLD
}

// ---------------------------------------------------------------------------
// Codec and formula
// ---------------------------------------------------------------------------

fn append_varint(out: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        out.push((value & 0x7F) as u8 | 0x80);
        value >>= 7;
    }
    out.push(value as u8);
}

/// Every varint of `blob`, appended to `out`.
fn decode_varints(blob: &[u8], out: &mut Vec<u64>) {
    let mut value: u64 = 0;
    let mut shift = 0u32;
    for &byte in blob {
        value |= u64::from(byte & 0x7F) << shift.min(63);
        if byte & 0x80 == 0 {
            out.push(value);
            value = 0;
            shift = 0;
        } else {
            shift += 7;
        }
    }
}

/// The ids of a count-prefixed delta blob, appended to `out`.
fn decode_ids(blob: &[u8], scratch: &mut Vec<u64>, out: &mut Vec<i64>) {
    scratch.clear();
    decode_varints(blob, scratch);
    let mut id: i64 = 0;
    for &delta in scratch.iter().skip(1) {
        id = id.wrapping_add(delta as i64);
        out.push(id);
    }
}

pub fn idf(df: u64, n_docs: u64) -> f64 {
    (1.0 + ((n_docs - df) as f64 + 0.5) / (df as f64 + 0.5)).ln()
}

/// One posting's contribution, in the host formula's operation order.
pub fn term_weight(tf: f64, dl: f64, avg_dl: f64, term_idf: f64) -> f64 {
    let norm = BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_dl);
    term_idf * tf * (BM25_K1 + 1.0) / (tf + norm)
}

// ---------------------------------------------------------------------------
// Builder
// ---------------------------------------------------------------------------

/// One block's `(count, ids, tfs, dls)` byte ranges inside a `TermList`.
type BlockRange = (u32, std::ops::Range<usize>, std::ops::Range<usize>, std::ops::Range<usize>);

/// One term's postings: three byte streams holding every block back to
/// back, with each sealed block's end offsets, and the open block's state.
struct TermList {
    df: u32,
    ids: Vec<u8>,
    tfs: Vec<u8>,
    dls: Vec<u8>,
    // (count, ids_end, tfs_end, dls_end) per sealed block.
    sealed: Vec<(u32, u32, u32, u32)>,
    open_count: u32,
    last_id: i64,
}

impl TermList {
    fn new() -> Self {
        Self { df: 0, ids: Vec::new(), tfs: Vec::new(), dls: Vec::new(), sealed: Vec::new(), open_count: 0, last_id: 0 }
    }

    fn push(&mut self, doc_id: i64, tf: u32, dl: u32) {
        append_varint(&mut self.ids, (doc_id - self.last_id) as u64);
        append_varint(&mut self.tfs, u64::from(tf));
        append_varint(&mut self.dls, u64::from(dl));
        self.last_id = doc_id;
        self.open_count += 1;
        self.df += 1;
        if self.open_count as usize == BLOCK_SIZE {
            self.seal();
        }
    }

    fn seal(&mut self) {
        self.sealed.push((self.open_count, self.ids.len() as u32, self.tfs.len() as u32, self.dls.len() as u32));
        self.open_count = 0;
        self.last_id = 0;
    }

    /// Every block's byte ranges in order, the open block last.
    fn blocks(&self) -> Vec<BlockRange> {
        let mut out = Vec::with_capacity(self.sealed.len() + 1);
        let (mut a, mut b, mut c) = (0usize, 0usize, 0usize);
        for &(count, ia, ib, ic) in &self.sealed {
            out.push((count, a..ia as usize, b..ib as usize, c..ic as usize));
            (a, b, c) = (ia as usize, ib as usize, ic as usize);
        }
        if self.open_count > 0 {
            out.push((self.open_count, a..self.ids.len(), b..self.tfs.len(), c..self.dls.len()));
        }
        out
    }
}

pub struct LexicalAccumulator {
    terms: HashMap<String, TermList>,
    n_docs: u64,
    total_dl: u64,
    last_doc_id: i64,
    counts: Vec<(String, u32)>,
}

impl LexicalAccumulator {
    pub fn new() -> Self {
        Self { terms: HashMap::new(), n_docs: 0, total_dl: 0, last_doc_id: 0, counts: Vec::new() }
    }

    /// Tokenize and post one document; returns its token count (`dl`).
    pub fn add_doc(&mut self, doc_id: i64, content: &str) -> Result<u32, LexicalError> {
        if doc_id <= self.last_doc_id {
            return Err(LexicalError::NonIncreasingDocId { doc_id, last: self.last_doc_id });
        }
        let mut tokens = tokenize(content);
        let dl = tokens.len() as u32;
        tokens.sort_unstable();
        self.counts.clear();
        for term in tokens {
            match self.counts.last_mut() {
                Some((last, tf)) if *last == term => *tf += 1,
                _ => self.counts.push((term, 1)),
            }
        }
        for (term, tf) in self.counts.drain(..) {
            match self.terms.get_mut(&term) {
                Some(list) => list.push(doc_id, tf, dl),
                None => {
                    let mut list = TermList::new();
                    list.push(doc_id, tf, dl);
                    self.terms.insert(term, list);
                }
            }
        }
        self.last_doc_id = doc_id;
        self.n_docs += 1;
        self.total_dl += u64::from(dl);
        Ok(dl)
    }

    /// Fix the statistics and every term's idf, block maxima and summary.
    pub fn finish(self) -> DrainedLexical {
        let n_docs = self.n_docs;
        let avg_dl = if n_docs == 0 { 0.0 } else { self.total_dl as f64 / n_docs as f64 };
        let mut terms: Vec<(String, TermList)> = self.terms.into_iter().collect();
        terms.sort_unstable_by(|a, b| a.0.cmp(&b.0));
        let mut scratch = Vec::new();
        let mut tfs = Vec::new();
        let mut dls = Vec::new();
        let drained = terms
            .into_iter()
            .map(|(term, list)| {
                let term_idf = idf(u64::from(list.df), n_docs);
                let mut summary = Vec::new();
                let mut max_weight = 0.0f64;
                let mut previous_first = 0i64;
                for (_count, ids, tf_range, dl_range) in list.blocks() {
                    scratch.clear();
                    decode_varints(&list.ids[ids], &mut scratch);
                    let first = scratch[0] as i64;
                    tfs.clear();
                    dls.clear();
                    decode_varints(&list.tfs[tf_range], &mut tfs);
                    decode_varints(&list.dls[dl_range], &mut dls);
                    let block_max = tfs
                        .iter()
                        .zip(&dls)
                        .map(|(&tf, &dl)| term_weight(tf as f64, dl as f64, avg_dl, term_idf))
                        .fold(0.0f64, f64::max);
                    append_varint(&mut summary, (first - previous_first) as u64);
                    summary.extend_from_slice(&block_max.to_le_bytes());
                    previous_first = first;
                    max_weight = max_weight.max(block_max);
                }
                DrainedTerm { term, df: list.df, idf: term_idf, max_weight, summary, list }
            })
            .collect();
        DrainedLexical { n_docs, avg_dl, terms: drained, df_cursor: 0, block_cursor: 0, block_offset: 0 }
    }
}

impl Default for LexicalAccumulator {
    fn default() -> Self {
        Self::new()
    }
}

struct DrainedTerm {
    term: String,
    df: u32,
    idf: f64,
    max_weight: f64,
    summary: Vec<u8>,
    list: TermList,
}

/// One term's summary row: `(term, df, idf, max_weight, blocks)`.
pub struct SummaryRow {
    pub term: String,
    pub df: u32,
    pub idf: f64,
    pub max_weight: f64,
    pub blocks: Vec<u8>,
}

/// One block row: `(term, block_no, doc_count, doc_ids, tfs, dls)`.
pub struct BlockRow {
    pub term: String,
    pub block_no: u32,
    pub doc_count: u32,
    pub doc_ids: Vec<u8>,
    pub tfs: Vec<u8>,
    pub dls: Vec<u8>,
}

pub struct DrainedLexical {
    pub n_docs: u64,
    pub avg_dl: f64,
    terms: Vec<DrainedTerm>,
    df_cursor: usize,
    block_cursor: usize,
    block_offset: usize,
}

impl DrainedLexical {
    /// The next term-ordered batch of at most `row_cap` summary rows;
    /// `None` when exhausted.
    pub fn next_df_batch(&mut self, row_cap: usize) -> Option<Vec<SummaryRow>> {
        if self.df_cursor >= self.terms.len() {
            return None;
        }
        let end = (self.df_cursor + row_cap.max(1)).min(self.terms.len());
        let batch = self.terms[self.df_cursor..end]
            .iter_mut()
            .map(|t| SummaryRow {
                term: t.term.clone(),
                df: t.df,
                idf: t.idf,
                max_weight: t.max_weight,
                blocks: std::mem::take(&mut t.summary),
            })
            .collect();
        self.df_cursor = end;
        Some(batch)
    }

    /// The next term-ordered batch of at most `row_cap` block rows; `None`
    /// when exhausted. A drained term releases its byte streams.
    pub fn next_batch(&mut self, row_cap: usize) -> Option<Vec<BlockRow>> {
        if self.block_cursor >= self.terms.len() {
            return None;
        }
        let row_cap = row_cap.max(1);
        let mut batch = Vec::new();
        while self.block_cursor < self.terms.len() && batch.len() < row_cap {
            let term = &mut self.terms[self.block_cursor];
            let blocks = term.list.blocks();
            while self.block_offset < blocks.len() && batch.len() < row_cap {
                let (count, ids, tfs, dls) = &blocks[self.block_offset];
                let mut doc_ids = Vec::with_capacity(ids.len() + 2);
                append_varint(&mut doc_ids, u64::from(*count));
                doc_ids.extend_from_slice(&term.list.ids[ids.clone()]);
                batch.push(BlockRow {
                    term: term.term.clone(),
                    block_no: self.block_offset as u32,
                    doc_count: *count,
                    doc_ids,
                    tfs: term.list.tfs[tfs.clone()].to_vec(),
                    dls: term.list.dls[dls.clone()].to_vec(),
                });
                self.block_offset += 1;
            }
            if self.block_offset >= blocks.len() {
                term.list = TermList::new();
                self.block_cursor += 1;
                self.block_offset = 0;
            }
        }
        Some(batch)
    }
}

// ---------------------------------------------------------------------------
// Scorer
// ---------------------------------------------------------------------------

/// One fetched block: its query-term index, its summary maximum, its blobs.
pub struct ScoreBlock<'a> {
    pub term: usize,
    pub bound: f64,
    pub doc_ids: &'a [u8],
    pub tfs: &'a [u8],
    pub dls: &'a [u8],
}

/// Rank the documents of `blocks` by BM25: top `k` as `(id, score)`,
/// `score DESC, id ASC`. `candidates`, when given, is a sorted id set the
/// result is restricted to. Blocks that cannot lift any document into the
/// top-k are skipped without a full decode.
pub fn score(blocks: &[ScoreBlock<'_>], idfs: &[f64], avg_dl: f64, k: usize, candidates: Option<&[i64]>) -> Vec<(i64, f64)> {
    // Terms by descending maximum (ties by index), blocks in given order.
    let mut term_bound: Vec<f64> = vec![f64::NEG_INFINITY; idfs.len()];
    for block in blocks {
        term_bound[block.term] = term_bound[block.term].max(block.bound);
    }
    let mut order: Vec<usize> = (0..idfs.len()).filter(|&t| term_bound[t] > f64::NEG_INFINITY).collect();
    order.sort_by(|&a, &b| term_bound[b].partial_cmp(&term_bound[a]).unwrap().then(a.cmp(&b)));
    let mut rest = vec![0.0f64; order.len() + 1];
    for i in (0..order.len()).rev() {
        rest[i] = rest[i + 1] + term_bound[order[i]];
    }
    let admits = |id: i64| candidates.is_none_or(|set| set.binary_search(&id).is_ok());

    let mut partial: HashMap<i64, f64> = HashMap::new();
    let mut theta = 0.0f64;
    let mut ids = Vec::new();
    let mut scratch = Vec::new();
    let mut tfs = Vec::new();
    let mut dls = Vec::new();
    for (position, &term) in order.iter().enumerate() {
        let remaining = rest[position + 1];
        let term_idf = idfs[term];
        for block in blocks.iter().filter(|b| b.term == term) {
            ids.clear();
            decode_ids(block.doc_ids, &mut scratch, &mut ids);
            if theta > 0.0 && block.bound + remaining < theta {
                let lift = block.bound + remaining;
                let competes = ids.iter().any(|id| partial.get(id).is_some_and(|&p| p + lift >= theta));
                if !competes {
                    continue;
                }
            }
            tfs.clear();
            dls.clear();
            decode_varints(block.tfs, &mut tfs);
            decode_varints(block.dls, &mut dls);
            for ((&id, &tf), &dl) in ids.iter().zip(&tfs).zip(&dls) {
                if !admits(id) {
                    continue;
                }
                *partial.entry(id).or_insert(0.0) += term_weight(tf as f64, dl as f64, avg_dl, term_idf);
            }
        }
        if partial.len() >= k && k > 0 {
            let mut scores: Vec<f64> = partial.values().copied().collect();
            let nth = scores.len() - k;
            let (_, kth, _) = scores.select_nth_unstable_by(nth, |a, b| a.partial_cmp(b).unwrap());
            theta = *kth;
        }
    }
    let mut ranked: Vec<(i64, f64)> = partial.into_iter().collect();
    ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap().then(a.0.cmp(&b.0)));
    ranked.truncate(k);
    ranked
}

#[cfg(test)]
mod tests {
    use super::*;

    fn drain(acc: LexicalAccumulator) -> (DrainedLexical, Vec<SummaryRow>, Vec<BlockRow>) {
        let mut drained = acc.finish();
        let mut summaries = Vec::new();
        while let Some(batch) = drained.next_df_batch(3) {
            summaries.extend(batch);
        }
        let mut rows = Vec::new();
        while let Some(batch) = drained.next_batch(2) {
            rows.extend(batch);
        }
        (drained, summaries, rows)
    }

    #[test]
    fn tokenizer_rules() {
        assert_eq!(tokenize("PostingsBuilder"), ["postingsbuilder", "postings", "builder"]);
        assert_eq!(tokenize("pthread_create"), ["pthread_create", "pthread", "create"]);
        assert_eq!(tokenize("HTTPServer"), ["httpserver", "http", "server"]);
        assert_eq!(tokenize("0x1f v2_0xFF"), ["0x1f", "v2_0xff", "v2", "0xff"]);
        assert_eq!(tokenize("a b getX x_y"), ["getx", "get", "x_y"]);
        assert_eq!(tokenize("İstanbul ısı STRASSE"), ["istanbul", "isi", "strasse"]);
        assert_eq!(tokenize(&"x".repeat(65)), Vec::<String>::new());
        assert_eq!(tokenize(&"é".repeat(33)), Vec::<String>::new());
    }

    #[test]
    fn builder_blocks_and_summaries() {
        let mut acc = LexicalAccumulator::new();
        for id in 1..=(BLOCK_SIZE as i64 + 2) {
            acc.add_doc(id, if id % 2 == 0 { "foo bar foo" } else { "foo" }).unwrap();
        }
        assert!(acc.add_doc(3, "late").is_err());
        let (drained, summaries, rows) = drain(acc);
        assert_eq!(drained.n_docs, BLOCK_SIZE as u64 + 2);
        assert_eq!(summaries.iter().map(|s| s.term.as_str()).collect::<Vec<_>>(), ["bar", "foo"]);
        assert_eq!(summaries[1].df, BLOCK_SIZE as u32 + 2);
        // foo spans two blocks: a full one and a two-posting tail.
        let foo: Vec<&BlockRow> = rows.iter().filter(|r| r.term == "foo").collect();
        assert_eq!(foo.iter().map(|r| (r.block_no, r.doc_count)).collect::<Vec<_>>(), [(0, 128), (1, 2)]);
        // The tail block's deltas restart: its first id is absolute.
        let mut tail = Vec::new();
        decode_ids(&foo[1].doc_ids, &mut Vec::new(), &mut tail);
        assert_eq!(tail, [129, 130]);
        // Summary: (delta 1, f64) then (delta 128 — two varint bytes, f64).
        assert_eq!(summaries[1].blocks.len(), 1 + 8 + 2 + 8);
        let first_max = f64::from_le_bytes(summaries[1].blocks[1..9].try_into().unwrap());
        let second_max = f64::from_le_bytes(summaries[1].blocks[11..19].try_into().unwrap());
        assert_eq!(summaries[1].max_weight, first_max.max(second_max));
        // Both blocks hold a tf-2 posting, so their maxima agree.
        assert_eq!(first_max, second_max);
    }

    #[test]
    fn scorer_ranks_and_skips_exactly() {
        let mut acc = LexicalAccumulator::new();
        let docs = ["alpha beta", "alpha alpha gamma", "beta beta beta", "gamma", "alpha beta gamma delta"];
        for (i, doc) in docs.iter().enumerate() {
            acc.add_doc(i as i64 + 1, doc).unwrap();
        }
        let (drained, summaries, rows) = drain(acc);
        let terms = ["alpha", "beta"];
        let idfs: Vec<f64> = terms.iter().map(|t| summaries.iter().find(|s| &s.term == t).unwrap().idf).collect();
        let bounds: HashMap<&str, f64> = summaries.iter().map(|s| (s.term.as_str(), s.max_weight)).collect();
        let blocks: Vec<ScoreBlock> = rows
            .iter()
            .filter_map(|r| {
                terms.iter().position(|t| *t == r.term).map(|term| ScoreBlock {
                    term,
                    bound: bounds[r.term.as_str()],
                    doc_ids: &r.doc_ids,
                    tfs: &r.tfs,
                    dls: &r.dls,
                })
            })
            .collect();
        let full = score(&blocks, &idfs, drained.avg_dl, 10, None);
        assert_eq!(full.len(), 4);
        assert!(full.windows(2).all(|w| w[0].1 >= w[1].1));
        let top1 = score(&blocks, &idfs, drained.avg_dl, 1, None);
        assert_eq!(top1, vec![full[0]]);
        let only = score(&blocks, &idfs, drained.avg_dl, 10, Some(&[3, 4]));
        assert_eq!(only.iter().map(|r| r.0).collect::<Vec<_>>(), [3]);
        assert_eq!(score(&blocks, &idfs, drained.avg_dl, 0, None), vec![]);
    }
}
