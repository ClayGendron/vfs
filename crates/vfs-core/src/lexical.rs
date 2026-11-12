//! The lexical (BM25) engine: the tokenizer, block postings, the builder
//! and the scorer.
//!
//! The tokenizer is a port of the host's reference tokenizer driven by the
//! host interpreter's own character classes (`lexical_tables.rs`, generated),
//! so the two cannot disagree on what a letter, a capital or a fold is.
//!
//! The builder streams documents once — scan, count, append each posting to
//! its term's open block, seal a block at `BLOCK_SIZE` — and at `finish`
//! fixes the corpus statistics, each term's idf and every block's true
//! maximum weight, then drains summary rows and block rows in term order.
//! The count is made in place, with one owned copy of each term. The scanner
//! hands each folded term over as a borrowed slice; an interner maps it to
//! its term list and clones it the first time the corpus shows it, never
//! again; the list carries the document being counted and the term's running
//! count in it; and once the scan has fixed the document's length, each list
//! the document reached appends one posting. No token is materialized and
//! no document's terms are sorted. The allocations that remain are the
//! vocabulary's first-sight cost, one string and three posting streams per
//! term new to the corpus, amortised over the corpus: a chunk costs what it
//! adds to the vocabulary, not what it holds. Beside them are the scanner's
//! parts vector, one a document, a term's block offsets when its first block
//! seals, the interner's table each time it doubles, a logarithm of the
//! vocabulary, and the first allocation of the vector of term lists and of
//! each of the builder's three reused buffers, four a builder. The
//! reallocations are the posting streams, the block offsets, the vector of
//! term lists and the three reused buffers growing, and the scanner's parts
//! vector when one run has more than four parts.
//!
//! Sealed blocks stay resident until `finish` (a block's true maximum needs
//! the final statistics); residency is per-term structure rather than blob
//! bytes — ~660 B per distinct term measured against ~4.5 B per posting when
//! each term's list sat in a map under its string — so an arena for the term
//! streams is the direction if a vocabulary outgrows memory, never a corpus
//! limit. Counting in place adds 24 B to a term's slot: 16 B for the pending
//! document and count on its list, 8 B for the slot index beside its string.
//! Under the growth slack of the list vector and the interner's table that
//! measured, on vocabularies of 200,000 to 400,000 terms of two postings
//! each, 31 to 48 B a term more than the map while feeding (80 B less at
//! 262,144 terms, where the map had doubled and the vector was exactly
//! full), and a peak in `finish` of 400 B a term while the sorted pairs and
//! the drained terms both exist, or of 464 while the pairs are built from a
//! list vector that has just doubled, against the map's 368 and 442.
//! The three reused buffers stay at their high-water marks until `finish`
//! returns; the largest is the scanner's, 4 B a character of the longest
//! document.
//!
//! The scorer decodes fetched blocks, accumulates BM25 per document in a
//! fixed order (terms by descending maximum, block order, posting order —
//! the same order the host's fallback uses, so sums are bit-identical),
//! skips blocks that cannot change the top-k, and ranks `score DESC, id ASC`.
//!
//! The overlay counts kernel (`overlay_postings`) runs the same scanner as
//! `tokenize` over a batch of live bodies and counts the query terms as it
//! goes — each folded term is handed to the counter as a borrowed slice,
//! so no token is materialized and no dictionary of the body is built; the
//! match against the query is a linear compare for a short query and a
//! hash lookup past `LINEAR_MATCH_TERMS`, exact on the folded term either
//! way. It reads the clock between documents, every `CHECK_EVERY` of them.
//!
//! Wire shapes: `doc_ids` is the gram codec's count-prefixed delta+varint
//! blob (deltas restart at each block, so a block decodes alone); `tfs` and
//! `dls` are plain LEB128 varints; a term's summary is, per block, the
//! varint delta of its first id from the previous block's and the block's
//! maximum weight as a little-endian `f64`.

use std::collections::HashMap;

use crate::deadline::{CHECK_EVERY, Deadline};
use crate::lexical_tables::{ASSIGNED, CASEFOLD, DIGIT, LOWER, UPPER, WORD};

pub use crate::lexical_tables::{PYTHON_VERSION, UNICODE_VERSION};

pub const BLOCK_SIZE: usize = 128;
pub const BM25_K1: f64 = 1.2;
pub const BM25_B: f64 = 0.75;
const MIN_TERM_CHARS: usize = 2;
const MAX_TERM_BYTES: usize = 64;

/// Query terms up to which the overlay kernel compares each token linearly;
/// past it a hash map of the terms is built once per call.
const LINEAR_MATCH_TERMS: usize = 8;

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
    TruncatedSummary,
    NonMonotoneSummary,
}

impl std::fmt::Display for LexicalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NonIncreasingDocId { doc_id, last } => {
                write!(f, "doc ids must be strictly increasing and positive; got {doc_id} after {last}")
            }
            Self::Sealed => write!(f, "statistics are fixed; create a fresh builder"),
            Self::TruncatedSummary => write!(f, "truncated summary blob"),
            Self::NonMonotoneSummary => write!(f, "summary first ids not monotone"),
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

/// Fold `raw` into `scratch` and hand it to `sink` when it passes the two
/// length rules: at least `MIN_TERM_CHARS` characters, at most `MAX_TERM_BYTES`.
fn emit(raw: &[char], scratch: &mut String, sink: &mut impl FnMut(&str)) {
    fold_into(raw, scratch);
    if scratch.chars().count() >= MIN_TERM_CHARS && scratch.len() <= MAX_TERM_BYTES {
        sink(scratch);
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

/// The one scanner every tokenizer surface shares: each word run of
/// `content` folded and handed to `sink` as a borrowed term, then its parts
/// when there are more than one. `chars` and `scratch` are the caller's
/// reusable buffers; a term lives only for its `sink` call.
fn scan_terms(content: &str, chars: &mut Vec<char>, scratch: &mut String, mut sink: impl FnMut(&str)) {
    chars.clear();
    chars.extend(content.chars());
    let mut parts: Vec<&[char]> = Vec::new();
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
        emit(run, scratch, &mut sink);
        if parts.len() > 1 {
            for part in parts.iter() {
                emit(part, scratch, &mut sink);
            }
        }
    }
}

/// Folded terms in order, duplicates kept: each word run whole, and its
/// parts when there are more than one.
pub fn tokenize(content: &str) -> Vec<String> {
    let mut terms = Vec::new();
    scan_terms(content, &mut Vec::new(), &mut String::new(), |term| terms.push(term.to_owned()));
    terms
}

/// What one `overlay_postings` call counted: per query term in the caller's
/// order, the `(doc_id, tf, dl)` postings of the bodies holding it in the
/// order the bodies were given; the bodies counted; their summed token
/// count; and whether every body was reached before the deadline.
#[derive(Debug, PartialEq, Eq)]
pub struct OverlayOutcome {
    pub postings: Vec<Vec<(i64, u32, u32)>>,
    pub reached: u64,
    pub total_dl: u64,
    pub completed: bool,
}

/// The query terms' positions: a linear compare up to `LINEAR_MATCH_TERMS`,
/// a map built once past it. A term repeated in the query resolves to its
/// first position; the caller copies that position's tf to the others.
enum TermIndex<'a> {
    Linear(&'a [&'a str]),
    Mapped(HashMap<&'a str, usize>),
}

impl<'a> TermIndex<'a> {
    fn new(terms: &'a [&'a str]) -> Self {
        if terms.len() <= LINEAR_MATCH_TERMS {
            return Self::Linear(terms);
        }
        let mut mapped = HashMap::with_capacity(terms.len());
        for (position, &term) in terms.iter().enumerate() {
            mapped.entry(term).or_insert(position);
        }
        Self::Mapped(mapped)
    }

    fn position(&self, token: &str) -> Option<usize> {
        match self {
            Self::Linear(terms) => terms.iter().position(|&term| term == token),
            Self::Mapped(mapped) => mapped.get(token).copied(),
        }
    }
}

/// Tokenize and count a batch of live bodies for `terms`: the overlay's
/// query-time postings, without materializing a token or a dictionary.
///
/// Bodies are counted in the order given; the deadline is read before
/// every `CHECK_EVERY`th body, and a batch that reaches it stops there with
/// `completed` false and the postings of the bodies it did count.
pub fn overlay_postings(docs: &[(i64, &str)], terms: &[&str], deadline: Deadline) -> OverlayOutcome {
    let index = TermIndex::new(terms);
    let first_of: Vec<usize> = terms.iter().map(|term| index.position(term).expect("every term is its own")).collect();
    let mut postings: Vec<Vec<(i64, u32, u32)>> = vec![Vec::new(); terms.len()];
    let mut tfs = vec![0u32; terms.len()];
    let mut reached = 0u64;
    let mut total_dl = 0u64;
    let mut chars = Vec::new();
    let mut scratch = String::new();
    for (ordinal, &(doc_id, content)) in docs.iter().enumerate() {
        if ordinal % CHECK_EVERY == 0 && deadline.past() {
            return OverlayOutcome { postings, reached, total_dl, completed: false };
        }
        tfs.fill(0);
        let mut dl = 0u32;
        scan_terms(content, &mut chars, &mut scratch, |token| {
            dl += 1;
            if let Some(position) = index.position(token) {
                tfs[position] += 1;
            }
        });
        for (position, &first) in first_of.iter().enumerate() {
            let tf = tfs[first];
            if tf > 0 {
                postings[position].push((doc_id, tf, dl));
            }
        }
        reached += 1;
        total_dl += u64::from(dl);
    }
    OverlayOutcome { postings, reached, total_dl, completed: true }
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

/// The inverse of the builder's summary encoding: per block, the varint
/// delta of its first id and its maximum weight as a little-endian f64.
/// Refuses a blob that ends mid-block or whose first ids do not climb.
pub fn decode_summary(blob: &[u8]) -> Result<(Vec<i64>, Vec<f64>), LexicalError> {
    let mut firsts = Vec::new();
    let mut maxes = Vec::new();
    let mut position = 0usize;
    let mut first: i64 = 0;
    while position < blob.len() {
        let mut delta: u64 = 0;
        let mut shift = 0u32;
        loop {
            let Some(&byte) = blob.get(position) else {
                return Err(LexicalError::TruncatedSummary);
            };
            position += 1;
            delta |= u64::from(byte & 0x7F) << shift.min(63);
            if byte & 0x80 == 0 {
                break;
            }
            shift += 7;
        }
        let Some(raw) = blob.get(position..position + 8) else {
            return Err(LexicalError::TruncatedSummary);
        };
        position += 8;
        let next = first.wrapping_add(delta as i64);
        if !firsts.is_empty() && next <= first {
            return Err(LexicalError::NonMonotoneSummary);
        }
        first = next;
        firsts.push(first);
        maxes.push(f64::from_le_bytes(raw.try_into().expect("8 bytes")));
    }
    Ok((firsts, maxes))
}

/// The block numbers of a term that can still change a top-k.
///
/// A block competes when its maximum (plus `rest`, the summed maxima of
/// the other terms not yet fetched) clears `theta` on its own, or when
/// the best-scored candidate inside its id range would cross `theta`
/// with that lift. `candidates` is sorted, `scores` aligned with it; a
/// candidate before the first block lies in no block.
pub fn competing_blocks(
    first_ids: &[i64],
    max_weights: &[f64],
    candidates: &[i64],
    scores: &[f64],
    theta: f64,
    rest: f64,
) -> Vec<usize> {
    let mut best = vec![f64::NEG_INFINITY; first_ids.len()];
    if !first_ids.is_empty() {
        for (&candidate, &score) in candidates.iter().zip(scores) {
            // The block whose first id is the last one <= candidate.
            let index = first_ids.partition_point(|&first| first <= candidate);
            if index > 0 {
                let slot = &mut best[index - 1];
                *slot = slot.max(score);
            }
        }
    }
    let mut out = Vec::new();
    for (block, (&max, &lift)) in max_weights.iter().zip(&best).enumerate() {
        if max + rest >= theta || lift + max + rest >= theta {
            out.push(block);
        }
    }
    out
}

/// Per-query block selection: for every term's summary `(first_ids,
/// max_weights)`, the blocks that can still change the top-k, aligned to
/// the input order. Terms are taken in descending maximum (ties by input
/// position), each with `rest` the summed maxima of the terms after it —
/// the ones the caller has not fetched yet. A summary without blocks has
/// maximum zero and names nothing.
pub fn select_blocks(
    summaries: &[(&[i64], &[f64])],
    candidates: &[i64],
    scores: &[f64],
    theta: f64,
) -> Vec<Vec<usize>> {
    let maxima: Vec<f64> =
        summaries.iter().map(|(_, maxes)| maxes.iter().copied().fold(0.0, f64::max)).collect();
    let mut order: Vec<usize> = (0..summaries.len()).collect();
    order.sort_by(|&a, &b| maxima[b].total_cmp(&maxima[a]));
    let mut out = vec![Vec::new(); summaries.len()];
    for (position, &term) in order.iter().enumerate() {
        let rest = order[position + 1..].iter().map(|&later| maxima[later]).fold(0.0, |acc, m| acc + m);
        let (firsts, maxes) = summaries[term];
        out[term] = competing_blocks(firsts, maxes, candidates, scores, theta, rest);
    }
    out
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
/// back, with each sealed block's end offsets, the open block's state, and
/// the term's running count in the document being counted.
struct TermList {
    df: u32,
    ids: Vec<u8>,
    tfs: Vec<u8>,
    dls: Vec<u8>,
    // (count, ids_end, tfs_end, dls_end) per sealed block.
    sealed: Vec<(u32, u32, u32, u32)>,
    open_count: u32,
    last_id: i64,
    // The document being counted and this term's occurrences in it so far.
    pending_doc: i64,
    pending_tf: u32,
}

impl TermList {
    /// An empty list. `pending_doc` starts at 0, which is no document: the
    /// builder accepts only positive ids, so a first occurrence always opens.
    fn new() -> Self {
        Self {
            df: 0,
            ids: Vec::new(),
            tfs: Vec::new(),
            dls: Vec::new(),
            sealed: Vec::new(),
            open_count: 0,
            last_id: 0,
            pending_doc: 0,
            pending_tf: 0,
        }
    }

    /// Count one occurrence in `doc_id`; true when it is the document's first.
    fn count(&mut self, doc_id: i64) -> bool {
        if self.pending_doc == doc_id {
            self.pending_tf += 1;
            return false;
        }
        self.pending_doc = doc_id;
        self.pending_tf = 1;
        true
    }

    /// Post the counted document once its length is known.
    fn post_pending(&mut self, dl: u32) {
        self.push(self.pending_doc, self.pending_tf, dl);
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

/// The streaming builder. `interner` maps each distinct term to its slot in
/// `lists` and holds the one owned copy of it; `touched` is the slots the
/// document being counted reached; `chars` and `scratch` are the scanner's
/// buffers. The three buffers are reused, so they allocate only to grow.
pub struct LexicalAccumulator {
    interner: HashMap<String, u32>,
    lists: Vec<TermList>,
    touched: Vec<u32>,
    chars: Vec<char>,
    scratch: String,
    n_docs: u64,
    total_dl: u64,
    last_doc_id: i64,
}

impl LexicalAccumulator {
    pub fn new() -> Self {
        Self {
            interner: HashMap::new(),
            lists: Vec::new(),
            touched: Vec::new(),
            chars: Vec::new(),
            scratch: String::new(),
            n_docs: 0,
            total_dl: 0,
            last_doc_id: 0,
        }
    }

    /// How many distinct terms the corpus has shown so far.
    pub fn distinct_terms(&self) -> usize {
        self.interner.len()
    }

    /// Tokenize and post one document; returns its token count (`dl`).
    ///
    /// Each term is counted on its own list as the scanner emits it, and a
    /// term new to the corpus is cloned into the interner then, once. The
    /// postings wait for the scan to end, because each carries the length.
    pub fn add_doc(&mut self, doc_id: i64, content: &str) -> Result<u32, LexicalError> {
        if doc_id <= self.last_doc_id {
            return Err(LexicalError::NonIncreasingDocId { doc_id, last: self.last_doc_id });
        }
        let Self { interner, lists, touched, chars, scratch, .. } = self;
        let mut dl = 0u32;
        scan_terms(content, chars, scratch, |term| {
            dl += 1;
            let slot = match interner.get(term) {
                Some(&slot) => slot,
                None => {
                    // Loud, never a wrap that would hand two terms one list;
                    // the lists alone pass 500 GB before this can fire.
                    let slot = u32::try_from(lists.len()).expect("more distinct terms than a slot index holds");
                    lists.push(TermList::new());
                    interner.insert(term.to_owned(), slot);
                    slot
                }
            };
            if lists[slot as usize].count(doc_id) {
                touched.push(slot);
            }
        });
        for slot in touched.drain(..) {
            lists[slot as usize].post_pending(dl);
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
        // Lay the terms out by slot, then pair each with its list: the interner's
        // table is freed before the pairs exist, and both vectors once they are paired.
        let mut by_slot = vec![String::new(); self.lists.len()];
        for (term, slot) in self.interner {
            by_slot[slot as usize] = term;
        }
        let mut terms: Vec<(String, TermList)> = by_slot.into_iter().zip(self.lists).collect();
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

    // A body on every tokenizer rule: Turkic folds, casefold spellings, Greek,
    // camel case, digit-led pieces, underscores, over-cap terms, a short part.
    const MIXED_BODY: &str = "İstanbul ısı STRASSE Straße καλημέρα κόσμε XMLHttpRequest sha256Hash pthread_create \
        0x1f v2_0xFF getX a_b naïve café xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
        ééééééééééééééééééééééééééééééééé Foo_barBaz 1st";

    #[test]
    fn tokenize_output_is_unchanged() {
        let expected = [
            "istanbul", "isi", "strasse", "strasse", "καλημέρα", "κόσμε", "xmlhttprequest", "xml", "http", "request",
            "sha256hash", "sha256", "hash", "pthread_create", "pthread", "create", "0x1f", "v2_0xff", "v2", "0xff",
            "getx", "get", "a_b", "naïve", "café", "foo_barbaz", "foo", "bar", "baz", "1st",
        ];
        assert_eq!(tokenize(MIXED_BODY), expected);
        assert_eq!(tokenize(""), Vec::<String>::new());
    }

    /// The counting path spelled out: tokenize, count every token, read the query terms out.
    fn counted(docs: &[(i64, &str)], terms: &[&str]) -> (Vec<Vec<(i64, u32, u32)>>, u64) {
        let mut postings = vec![Vec::new(); terms.len()];
        let mut total_dl = 0u64;
        for &(doc_id, body) in docs {
            let tokens = tokenize(body);
            let dl = tokens.len() as u32;
            total_dl += u64::from(dl);
            for (position, term) in terms.iter().enumerate() {
                let tf = tokens.iter().filter(|token| token == term).count() as u32;
                if tf > 0 {
                    postings[position].push((doc_id, tf, dl));
                }
            }
        }
        (postings, total_dl)
    }

    #[test]
    fn overlay_postings_agrees_with_tokenize_counts() {
        let docs = [
            (7i64, MIXED_BODY),
            (3, "http request HTTP_REQUEST httpRequest and nothing else"),
            (90, ""),
            (12, "sha256Hash sha256hash sha256 café CAFÉ κόσμε"),
        ];
        let two = ["http", "café"];
        let twenty: Vec<&str> = [
            "http", "café", "sha256", "request", "κόσμε", "isi", "absent", "xml", "get", "foo", "bar", "baz", "1st",
            "0xff", "v2", "pthread", "create", "hash", "strasse", "nothing",
        ]
        .to_vec();
        for terms in [&two[..], &twenty[..]] {
            let (expected, total_dl) = counted(&docs, terms);
            let outcome = overlay_postings(&docs, terms, Deadline::never());
            assert_eq!(outcome.postings, expected);
            assert_eq!((outcome.reached, outcome.total_dl, outcome.completed), (4, total_dl, true));
        }
        // The twenty-term query takes the set path and finds every present term.
        let outcome = overlay_postings(&docs, &twenty, Deadline::never());
        assert_eq!(outcome.postings[6], Vec::<(i64, u32, u32)>::new());
        assert_eq!(outcome.postings[0], vec![(7, 1, 30), (3, 3, 11)]);
        assert_eq!(overlay_postings(&[], &two, Deadline::never()).postings, vec![Vec::new(), Vec::new()]);
    }

    #[test]
    fn overlay_postings_stops_between_documents_at_the_deadline() {
        let docs: Vec<(i64, &str)> = (1..=70).map(|id| (id, "alpha beta alpha")).collect();
        let passed = Deadline::at(std::time::Instant::now() - std::time::Duration::from_secs(1));
        let stopped = overlay_postings(&docs, &["alpha"], passed);
        assert_eq!((stopped.reached, stopped.total_dl, stopped.completed), (0, 0, false));
        assert_eq!(stopped.postings, vec![Vec::new()]);
        let ahead = Deadline::at(std::time::Instant::now() + std::time::Duration::from_secs(60));
        let finished = overlay_postings(&docs, &["alpha"], ahead);
        assert_eq!((finished.reached, finished.total_dl, finished.completed), (70, 210, true));
        assert_eq!(finished.postings[0].len(), 70);
        assert_eq!(finished.postings[0][69], (70, 2, 3));
    }

    #[test]
    fn overlay_postings_reads_the_deadline_before_every_64th_document() {
        // Guards: the clock read before the first document alone, or before every document.
        let docs: Vec<(i64, &str)> = (1..=200).map(|id| (id, "alpha beta alpha")).collect();
        let ahead = Deadline::at(std::time::Instant::now() + std::time::Duration::from_secs(60));
        let before = crate::deadline::clock_reads();
        let finished = overlay_postings(&docs, &["alpha"], ahead);
        assert_eq!((finished.reached, finished.completed), (200, true));
        let reads = crate::deadline::clock_reads() - before;
        assert_eq!(reads, 4, "one read before documents 0, 64, 128 and 192");
        let unbounded = overlay_postings(&docs, &["alpha"], Deadline::never());
        assert_eq!((unbounded.reached, crate::deadline::clock_reads() - before), (200, 4));
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

    /// Guards against a term taking a second slot, against a term's running
    /// count carrying over from one document into the next, and against a
    /// document's length counting its distinct terms.
    #[test]
    fn builder_interns_a_term_once() {
        let mut acc = LexicalAccumulator::new();
        acc.add_doc(1, "alpha beta alpha gamma").unwrap();
        assert_eq!(acc.distinct_terms(), 3);
        acc.add_doc(2, "gamma beta alpha beta").unwrap();
        assert_eq!(acc.distinct_terms(), 3);
        let (_, summaries, rows) = drain(acc);
        let dfs: Vec<(&str, u32)> = summaries.iter().map(|s| (s.term.as_str(), s.df)).collect();
        assert_eq!(dfs, [("alpha", 2), ("beta", 2), ("gamma", 2)]);
        // Each term's one block holds both documents' counts and lengths, in
        // document order; a length is every token, four in each document.
        let decoded = |blob: &[u8]| {
            let mut values = Vec::new();
            decode_varints(blob, &mut values);
            values
        };
        let tfs: Vec<Vec<u64>> = rows.iter().map(|row| decoded(&row.tfs)).collect();
        assert_eq!(tfs, [[2, 1], [1, 2], [1, 1]]);
        let dls: Vec<Vec<u64>> = rows.iter().map(|row| decoded(&row.dls)).collect();
        assert_eq!(dls, [[4, 4], [4, 4], [4, 4]]);
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

    #[test]
    fn summary_round_trips_and_refuses_torn_blobs() {
        let mut blob = Vec::new();
        let firsts = [1i64, 129, 5000, 1 << 40];
        let maxes = [1.5f64, 0.25, 3.0, 1e-9];
        let mut previous = 0i64;
        for (&first, &weight) in firsts.iter().zip(&maxes) {
            append_varint(&mut blob, (first - previous) as u64);
            blob.extend_from_slice(&weight.to_le_bytes());
            previous = first;
        }
        assert_eq!(decode_summary(&blob).unwrap(), (firsts.to_vec(), maxes.to_vec()));
        assert_eq!(decode_summary(&[]).unwrap(), (vec![], vec![]));
        assert_eq!(decode_summary(&blob[..blob.len() - 1]).unwrap_err(), LexicalError::TruncatedSummary);
        assert_eq!(decode_summary(&[0x81]).unwrap_err(), LexicalError::TruncatedSummary);
        let mut flat = Vec::new();
        append_varint(&mut flat, 5);
        flat.extend_from_slice(&1.0f64.to_le_bytes());
        append_varint(&mut flat, 0);
        flat.extend_from_slice(&1.0f64.to_le_bytes());
        assert_eq!(decode_summary(&flat).unwrap_err(), LexicalError::NonMonotoneSummary);
    }

    #[test]
    fn competing_blocks_lift_by_the_best_candidate_inside() {
        let firsts = [1i64, 129, 257, 385];
        let maxes = [0.5f64, 2.0, 0.5, 0.5];
        assert_eq!(competing_blocks(&firsts, &maxes, &[], &[], 0.0, 0.0), vec![0, 1, 2, 3]);
        let candidates = [130i64, 300];
        let scores = [0.1f64, 1.7];
        assert_eq!(competing_blocks(&firsts, &maxes, &candidates, &scores, 2.1, 0.0), vec![1, 2]);
        assert_eq!(competing_blocks(&firsts, &maxes, &candidates, &scores, 2.25, 0.0), Vec::<usize>::new());
        assert_eq!(competing_blocks(&firsts, &maxes, &candidates, &scores, 2.25, 0.3), vec![1, 2]);
        // A candidate before the first block lies in no block; one on a
        // boundary belongs to the block it starts.
        assert_eq!(competing_blocks(&[100], &[1.0], &[5], &[9.0], 5.0, 0.0), Vec::<usize>::new());
        assert_eq!(competing_blocks(&[100], &[1.0], &[100], &[9.0], 5.0, 0.0), vec![0]);
        assert_eq!(competing_blocks(&[], &[], &[1], &[1.0], 0.0, 0.0), Vec::<usize>::new());
    }

    #[test]
    fn select_blocks_orders_terms_by_maximum_and_answers_in_input_order() {
        // Term a (max 2.0) is fetched first with rest = 0.5 + 0.0; term b
        // (max 0.5) after it with rest = 0; the empty term c contributes
        // nothing and names nothing.
        let a: (&[i64], &[f64]) = (&[1, 129], &[2.0, 1.0]);
        let b: (&[i64], &[f64]) = (&[1], &[0.5]);
        let c: (&[i64], &[f64]) = (&[], &[]);
        let selected = select_blocks(&[b, a, c], &[130], &[0.1], 2.4);
        // a's block 1: 1.0 + 0.5 rest < 2.4 alone, lifted 0.1 + 1.0 + 0.5 < 2.4 -> out;
        // a's block 0: 2.0 + 0.5 >= 2.4 -> in. b's block 0: 0.5 < 2.4, lift 0.1 -> out.
        assert_eq!(selected, vec![Vec::<usize>::new(), vec![0], Vec::<usize>::new()]);
        assert_eq!(select_blocks(&[], &[1], &[1.0], 0.0), Vec::<Vec<usize>>::new());
    }
}
