//! Posting-list accumulation and the delta+varint blob codec.
//!
//! One gram's doc list is one blob: a varint count, then LEB128 varints of
//! the strictly positive deltas between consecutive ids — byte-identical to
//! the host reference codec. Docs must arrive in strictly increasing id
//! order, so each gram's deltas are encoded incrementally as they arrive and
//! peak memory is the compressed index, never a raw id table. Draining is
//! gram-ordered and byte-capped so the host can insert bounded batches.

use crate::grams::GramExtractor;

const GRAM_SPACE: usize = 1 << 24;

#[derive(Debug, PartialEq, Eq)]
pub enum AddDocError {
    NonIncreasingDocId { doc_id: i64, last: i64 },
}

impl std::fmt::Display for AddDocError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NonIncreasingDocId { doc_id, last } => {
                write!(f, "doc ids must be strictly increasing and positive; got {doc_id} after {last}")
            }
        }
    }
}

impl std::error::Error for AddDocError {}

struct GramList {
    gram: u32,
    last_id: i64,
    count: u32,
    deltas: Vec<u8>,
}

pub struct PostingsAccumulator {
    // gram -> index into `lists`, -1 when absent; direct index beats hashing
    // at this key-space size and makes the drain order the natural gram order.
    slots: Vec<i32>,
    lists: Vec<GramList>,
    extractor: GramExtractor,
    scratch: Vec<u32>,
    last_doc_id: i64,
}

impl PostingsAccumulator {
    pub fn new() -> Self {
        Self {
            slots: vec![-1i32; GRAM_SPACE],
            lists: Vec::new(),
            extractor: GramExtractor::new(),
            scratch: Vec::new(),
            last_doc_id: 0,
        }
    }

    /// Extract `data`'s distinct grams and post `doc_id` on each of them.
    pub fn add_doc(&mut self, doc_id: i64, data: &[u8]) -> Result<(), AddDocError> {
        if doc_id <= self.last_doc_id {
            return Err(AddDocError::NonIncreasingDocId { doc_id, last: self.last_doc_id });
        }
        let mut scratch = std::mem::take(&mut self.scratch);
        self.extractor.unique_grams(data, &mut scratch);
        for &gram in scratch.iter() {
            let slot = &mut self.slots[gram as usize];
            if *slot < 0 {
                *slot = self.lists.len() as i32;
                self.lists.push(GramList { gram, last_id: 0, count: 0, deltas: Vec::new() });
            }
            let list = &mut self.lists[*slot as usize];
            append_varint(&mut list.deltas, (doc_id - list.last_id) as u64);
            list.last_id = doc_id;
            list.count += 1;
        }
        self.scratch = scratch;
        self.last_doc_id = doc_id;
        Ok(())
    }

    /// Seal the accumulator into its gram-ordered drain.
    pub fn finish(mut self) -> DrainedPostings {
        self.lists.sort_unstable_by_key(|list| list.gram);
        DrainedPostings { lists: self.lists, cursor: 0 }
    }
}

impl Default for PostingsAccumulator {
    fn default() -> Self {
        Self::new()
    }
}

pub struct PostingRow {
    pub gram: u32,
    pub blob: Vec<u8>,
    pub doc_count: u32,
}

pub struct DrainedPostings {
    lists: Vec<GramList>,
    cursor: usize,
}

impl DrainedPostings {
    /// The next gram-ordered batch of encoded rows, sliced by accumulated
    /// blob bytes only (a batch always carries at least one row); `None`
    /// when exhausted. Drained rows release their delta buffers.
    pub fn next_batch(&mut self, byte_cap: usize) -> Option<Vec<PostingRow>> {
        if self.cursor >= self.lists.len() {
            return None;
        }
        let mut batch = Vec::new();
        let mut batch_bytes = 0usize;
        while self.cursor < self.lists.len() {
            let list = &mut self.lists[self.cursor];
            let mut blob = Vec::with_capacity(list.deltas.len() + 5);
            append_varint(&mut blob, u64::from(list.count));
            blob.extend_from_slice(&list.deltas);
            if !batch.is_empty() && batch_bytes + blob.len() > byte_cap {
                break;
            }
            list.deltas = Vec::new();
            batch_bytes += blob.len();
            batch.push(PostingRow { gram: list.gram, blob, doc_count: list.count });
            self.cursor += 1;
        }
        Some(batch)
    }
}

fn append_varint(out: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        out.push((value & 0x7F) as u8 | 0x80);
        value >>= 7;
    }
    out.push(value as u8);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn encode_reference(doc_ids: &[i64]) -> Vec<u8> {
        let mut out = Vec::new();
        append_varint(&mut out, doc_ids.len() as u64);
        let mut prev = 0i64;
        for &id in doc_ids {
            append_varint(&mut out, (id - prev) as u64);
            prev = id;
        }
        out
    }

    fn drain_all(drained: &mut DrainedPostings, byte_cap: usize) -> Vec<PostingRow> {
        let mut rows = Vec::new();
        while let Some(batch) = drained.next_batch(byte_cap) {
            rows.extend(batch);
        }
        rows
    }

    #[test]
    fn blobs_match_reference_codec_in_gram_order() {
        let mut acc = PostingsAccumulator::new();
        acc.add_doc(3, b"abc").unwrap();
        acc.add_doc(200, b"bcd").unwrap();
        acc.add_doc(1_000_000, b"abc").unwrap();
        let rows = drain_all(&mut acc.finish(), usize::MAX);
        let key = |w: &[u8]| (u32::from(w[0]) << 16) | (u32::from(w[1]) << 8) | u32::from(w[2]);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].gram, key(b"abc"));
        assert_eq!(rows[0].blob, encode_reference(&[3, 1_000_000]));
        assert_eq!(rows[0].doc_count, 2);
        assert_eq!(rows[1].gram, key(b"bcd"));
        assert_eq!(rows[1].blob, encode_reference(&[200]));
    }

    #[test]
    fn refuses_non_increasing_doc_ids() {
        let mut acc = PostingsAccumulator::new();
        acc.add_doc(5, b"abc").unwrap();
        assert!(acc.add_doc(5, b"xyz").is_err());
        assert!(acc.add_doc(4, b"xyz").is_err());
        let mut fresh = PostingsAccumulator::new();
        assert!(fresh.add_doc(0, b"abc").is_err());
        assert!(fresh.add_doc(-3, b"abc").is_err());
    }

    #[test]
    fn byte_cap_slices_batches_but_never_starves() {
        let mut acc = PostingsAccumulator::new();
        acc.add_doc(1, b"abcdefgh").unwrap();
        let mut drained = acc.finish();
        let mut total = 0;
        while let Some(batch) = drained.next_batch(1) {
            assert_eq!(batch.len(), 1, "cap below one blob still yields one row");
            total += batch.len();
        }
        assert_eq!(total, 6);
    }

    #[test]
    fn empty_and_short_docs_post_nothing() {
        let mut acc = PostingsAccumulator::new();
        acc.add_doc(1, b"").unwrap();
        acc.add_doc(2, b"ab").unwrap();
        let mut drained = acc.finish();
        assert!(drained.next_batch(1024).is_none());
    }
}
