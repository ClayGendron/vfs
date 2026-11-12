//! The builder's counting with a borrowed lookup: the per-document
//! counting of `LexicalAccumulator::add_doc` in `crates/vfs-core/src/lexical.rs`
//! (tokenize to `Vec<String>`, sort, run-length count, then one map lookup
//! per distinct term) replaced by a streaming count. Each term the
//! tokenizer hands over as a borrowed `&str` is looked up in an interner
//! (`HashMap<String, slot>`) and cloned only when it is new to the whole
//! corpus; its term list carries a pending `(doc, tf)` slot the document
//! bumps in place, and a touched list posts every slot once the document's
//! length is known. The term lists, the block sealing, `finish` and the
//! two drains are the engine's, copied so the drained rows can be compared
//! with `vfs_core::LexicalAccumulator`'s byte for byte.

use std::collections::HashMap;
use std::hash::{BuildHasher, BuildHasherDefault, Hasher};

use vfs_core::{BLOCK_SIZE, BlockRow, SummaryRow};

use crate::variants;

fn append_varint(out: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        out.push((value & 0x7F) as u8 | 0x80);
        value >>= 7;
    }
    out.push(value as u8);
}

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

fn idf(df: u64, n_docs: u64) -> f64 {
    (1.0 + ((n_docs - df) as f64 + 0.5) / (df as f64 + 0.5)).ln()
}

fn term_weight(tf: f64, dl: f64, avg_dl: f64, term_idf: f64) -> f64 {
    let norm = vfs_core::BM25_K1 * (1.0 - vfs_core::BM25_B + vfs_core::BM25_B * dl / avg_dl);
    term_idf * tf * (vfs_core::BM25_K1 + 1.0) / (tf + norm)
}

type BlockRange = (u32, std::ops::Range<usize>, std::ops::Range<usize>, std::ops::Range<usize>);

struct TermList {
    df: u32,
    ids: Vec<u8>,
    tfs: Vec<u8>,
    dls: Vec<u8>,
    sealed: Vec<(u32, u32, u32, u32)>,
    open_count: u32,
    last_id: i64,
    // The document being counted and its running tf for this term.
    pending_doc: i64,
    pending_tf: u32,
}

impl TermList {
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

/// FNV-1a over the term bytes: a non-randomized hasher for the interner,
/// to measure what the default SipHash costs on short keys.
#[derive(Default)]
pub struct Fnv(u64);

impl Hasher for Fnv {
    fn finish(&self) -> u64 {
        self.0
    }

    fn write(&mut self, bytes: &[u8]) {
        let mut hash = if self.0 == 0 { 0xcbf2_9ce4_8422_2325 } else { self.0 };
        for &b in bytes {
            hash ^= u64::from(b);
            hash = hash.wrapping_mul(0x0100_0000_01b3);
        }
        self.0 = hash;
    }
}

pub type FnvBuild = BuildHasherDefault<Fnv>;

/// Which tokenizer feeds the accumulator.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Feed {
    /// (b): the baseline's `Vec<char>` structure through a borrowed sink.
    Baseline,
    /// (f): the combined candidate through a borrowed sink.
    Combined,
}

pub struct BorrowedAccumulator<S: BuildHasher = std::collections::hash_map::RandomState> {
    index: HashMap<String, u32, S>,
    lists: Vec<TermList>,
    touched: Vec<u32>,
    chars: Vec<char>,
    scratch: String,
    n_docs: u64,
    total_dl: u64,
    last_doc_id: i64,
    feed: Feed,
}

impl<S: BuildHasher + Default> BorrowedAccumulator<S> {
    pub fn new(feed: Feed) -> Self {
        Self {
            index: HashMap::with_hasher(S::default()),
            lists: Vec::new(),
            touched: Vec::new(),
            chars: Vec::new(),
            scratch: String::new(),
            n_docs: 0,
            total_dl: 0,
            last_doc_id: 0,
            feed,
        }
    }

    pub fn add_doc(&mut self, doc_id: i64, content: &str) -> Result<u32, String> {
        if doc_id <= self.last_doc_id {
            return Err(format!("doc ids must be strictly increasing and positive; got {doc_id} after {}", self.last_doc_id));
        }
        self.touched.clear();
        let mut dl = 0u32;
        let index = &mut self.index;
        let lists = &mut self.lists;
        let touched = &mut self.touched;
        let mut sink = |term: &str| {
            dl += 1;
            let slot = match index.get(term) {
                Some(&slot) => slot,
                None => {
                    let slot = lists.len() as u32;
                    lists.push(TermList::new());
                    index.insert(term.to_owned(), slot);
                    slot
                }
            };
            let list = &mut lists[slot as usize];
            if list.pending_doc != doc_id {
                list.pending_doc = doc_id;
                list.pending_tf = 0;
                touched.push(slot);
            }
            list.pending_tf += 1;
        };
        match self.feed {
            Feed::Baseline => variants::cand_b_for_each_term(content, &mut self.chars, &mut self.scratch, &mut sink),
            Feed::Combined => {
                let mut parts = Vec::new();
                variants::cand_f_for_each_term(content, &mut parts, &mut self.scratch, &mut sink);
            }
        }
        for &slot in &self.touched {
            let list = &mut self.lists[slot as usize];
            let tf = list.pending_tf;
            list.push(doc_id, tf, dl);
        }
        self.last_doc_id = doc_id;
        self.n_docs += 1;
        self.total_dl += u64::from(dl);
        Ok(dl)
    }

    pub fn distinct_terms(&self) -> usize {
        self.lists.len()
    }

    /// The engine's `finish`, then both drains whole, for the parity check.
    pub fn finish_and_drain(self) -> (u64, f64, Vec<SummaryRow>, Vec<BlockRow>) {
        let n_docs = self.n_docs;
        let avg_dl = if n_docs == 0 { 0.0 } else { self.total_dl as f64 / n_docs as f64 };
        let mut lists = self.lists;
        let mut terms: Vec<(String, TermList)> = self
            .index
            .into_iter()
            .map(|(term, slot)| (term, std::mem::replace(&mut lists[slot as usize], TermList::new())))
            .collect();
        terms.sort_unstable_by(|a, b| a.0.cmp(&b.0));
        let mut scratch = Vec::new();
        let mut tfs = Vec::new();
        let mut dls = Vec::new();
        let mut summaries = Vec::with_capacity(terms.len());
        let mut blocks_out = Vec::new();
        for (term, list) in terms {
            let term_idf = idf(u64::from(list.df), n_docs);
            let mut summary = Vec::new();
            let mut max_weight = 0.0f64;
            let mut previous_first = 0i64;
            for (block_no, (count, ids, tf_range, dl_range)) in list.blocks().into_iter().enumerate() {
                scratch.clear();
                decode_varints(&list.ids[ids.clone()], &mut scratch);
                let first = scratch[0] as i64;
                tfs.clear();
                dls.clear();
                decode_varints(&list.tfs[tf_range.clone()], &mut tfs);
                decode_varints(&list.dls[dl_range.clone()], &mut dls);
                let block_max = tfs
                    .iter()
                    .zip(&dls)
                    .map(|(&tf, &dl)| term_weight(tf as f64, dl as f64, avg_dl, term_idf))
                    .fold(0.0f64, f64::max);
                append_varint(&mut summary, (first - previous_first) as u64);
                summary.extend_from_slice(&block_max.to_le_bytes());
                previous_first = first;
                max_weight = max_weight.max(block_max);
                let mut doc_ids = Vec::with_capacity(ids.len() + 2);
                append_varint(&mut doc_ids, u64::from(count));
                doc_ids.extend_from_slice(&list.ids[ids]);
                blocks_out.push(BlockRow {
                    term: term.clone(),
                    block_no: block_no as u32,
                    doc_count: count,
                    doc_ids,
                    tfs: list.tfs[tf_range].to_vec(),
                    dls: list.dls[dl_range].to_vec(),
                });
            }
            summaries.push(SummaryRow { term, df: list.df, idf: term_idf, max_weight, blocks: summary });
        }
        (n_docs, avg_dl, summaries, blocks_out)
    }
}
