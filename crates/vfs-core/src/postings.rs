//! Posting-list accumulation, the delta+varint blob codec, and the grep
//! candidate kernel.
//!
//! One gram's doc list is one blob: a varint count, then LEB128 varints of
//! the strictly positive deltas between consecutive ids. Docs must arrive
//! in strictly increasing id order, so each gram's deltas are encoded
//! incrementally as they arrive and peak memory is the compressed index,
//! never a raw id table. Draining is gram-ordered and byte-capped so the
//! host can insert bounded batches.
//!
//! The read side is one fused call, [`candidate_ids`]: the planner's chosen
//! blobs per AND-group come in rarest-first, and at most `cap` sorted
//! survivors go out — decode, AND, OR, allow-list intersect and cap all
//! happen here, so doc ids never materialize on the host until capped.
//! Decode refuses rather than guesses: every malformed-blob class
//! (truncated, over-wide or non-canonical varints, count mismatch,
//! non-positive delta, int64 wrap) is a [`PostingError`], never a wrong
//! candidate set.

use crate::grams::GramExtractor;

const GRAM_SPACE: usize = 1 << 24;

// ceil(63 / 7): the widest canonical varint a legal value can need.
const MAX_VARINT_BYTES: usize = 9;

#[derive(Debug, PartialEq, Eq)]
pub enum PostingError {
    EmptyBlob,
    Truncated,
    OverWide,
    NonCanonical,
    CountMismatch { count: u64, held: u64 },
    NonPositiveDelta,
    Wrap,
}

impl std::fmt::Display for PostingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyBlob => write!(f, "empty posting blob (a valid empty list is one zero byte)"),
            Self::Truncated => write!(f, "truncated varint at end of blob"),
            Self::OverWide => write!(f, "over-wide varint"),
            Self::NonCanonical => write!(f, "non-canonical varint spelling"),
            Self::CountMismatch { count, held } => write!(f, "count header says {count}, blob holds {held}"),
            Self::NonPositiveDelta => write!(f, "non-positive delta"),
            Self::Wrap => write!(f, "doc ids not monotone (int64 wrap)"),
        }
    }
}

impl std::error::Error for PostingError {}

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

// ---------------------------------------------------------------------------
// The read side: streaming decode and the fused candidate kernel
// ---------------------------------------------------------------------------

/// A streaming varint reader with the codec's structural refusals.
struct Varints<'a> {
    blob: &'a [u8],
    pos: usize,
}

impl<'a> Varints<'a> {
    fn new(blob: &'a [u8]) -> Self {
        Self { blob, pos: 0 }
    }

    #[inline]
    fn next(&mut self) -> Result<Option<u64>, PostingError> {
        if self.pos >= self.blob.len() {
            return Ok(None);
        }
        let start = self.pos;
        let mut value: u64 = 0;
        let mut shift: u32 = 0;
        loop {
            let Some(&byte) = self.blob.get(self.pos) else {
                return Err(PostingError::Truncated);
            };
            self.pos += 1;
            if self.pos - start > MAX_VARINT_BYTES {
                return Err(PostingError::OverWide);
            }
            value |= u64::from(byte & 0x7F) << shift;
            if byte & 0x80 == 0 {
                if self.pos - start > 1 && byte == 0 {
                    return Err(PostingError::NonCanonical);
                }
                return Ok(Some(value));
            }
            shift += 7;
        }
    }
}

/// The doc ids of one count-prefixed delta blob, streamed and validated.
struct Postings<'a> {
    varints: Varints<'a>,
    count: u64,
    seen: u64,
    last: i64,
}

impl<'a> Postings<'a> {
    fn new(blob: &'a [u8]) -> Result<Self, PostingError> {
        let mut varints = Varints::new(blob);
        let Some(count) = varints.next()? else {
            return Err(PostingError::EmptyBlob);
        };
        Ok(Self { varints, count, seen: 0, last: 0 })
    }

    /// The next id, or `None` once the blob is exhausted and its count agrees.
    #[inline]
    fn next(&mut self) -> Result<Option<i64>, PostingError> {
        let Some(delta) = self.varints.next()? else {
            if self.seen != self.count {
                return Err(PostingError::CountMismatch { count: self.count, held: self.seen });
            }
            return Ok(None);
        };
        let delta = delta as i64;
        if delta < 1 {
            return Err(PostingError::NonPositiveDelta);
        }
        // Positive deltas keep true ids monotone and positive; an int64 wrap
        // always passes through a non-positive value, so sign is the check.
        self.last = self.last.wrapping_add(delta);
        if self.last <= 0 {
            return Err(PostingError::Wrap);
        }
        self.seen += 1;
        Ok(Some(self.last))
    }

    fn collect(mut self) -> Result<Vec<i64>, PostingError> {
        let mut out = Vec::with_capacity(self.count as usize);
        while let Some(id) = self.next()? {
            out.push(id);
        }
        Ok(out)
    }
}

/// Decode a posting blob to its doc ids, refusing corruption.
pub fn decode_postings(blob: &[u8]) -> Result<Vec<i64>, PostingError> {
    Postings::new(blob)?.collect()
}

/// The grep candidate kernel: at most `cap` sorted survivors, plus the
/// uncapped count so the host can report the truncation.
///
/// Each group is an AND over its blobs, rarest-first as the planner chose
/// them: the first blob is decoded once and every later blob streams
/// against the shrinking survivor set, so nothing but the rarest list ever
/// materializes. Groups OR together (sorted, deduplicated), then meet
/// `allow` (a sorted scoped allow-list) when given. An empty group
/// nominates nothing. Every blob is fully validated even when the
/// intersection is already empty — a corrupt row is refused, never hidden
/// by a lucky short-circuit on the merge.
pub fn candidate_ids(
    groups: &[Vec<&[u8]>],
    allow: Option<&[i64]>,
    cap: usize,
) -> Result<(Vec<i64>, usize), PostingError> {
    let mut union: Vec<i64> = Vec::new();
    let mut merged_groups = 0usize;
    for group in groups {
        let Some((first, rest)) = group.split_first() else {
            continue;
        };
        let mut survivors = decode_postings(first)?;
        for blob in rest {
            survivors = intersect_stream(&survivors, blob)?;
        }
        if !survivors.is_empty() {
            union.extend_from_slice(&survivors);
            merged_groups += 1;
        }
    }
    // One group's survivors are already sorted and unique; only a real
    // union needs the sort.
    if merged_groups > 1 {
        union.sort_unstable();
        union.dedup();
    }
    if let Some(allow) = allow {
        union = intersect_sorted(&union, allow);
    }
    let total = union.len();
    union.truncate(cap);
    Ok((union, total))
}

/// The survivors of `current` that also appear in `blob`, streamed.
fn intersect_stream(current: &[i64], blob: &[u8]) -> Result<Vec<i64>, PostingError> {
    let mut postings = Postings::new(blob)?;
    let mut kept = Vec::with_capacity(current.len());
    let mut pos = 0usize;
    while let Some(id) = postings.next()? {
        while pos < current.len() && current[pos] < id {
            pos += 1;
        }
        if pos < current.len() && current[pos] == id {
            kept.push(id);
            pos += 1;
        }
    }
    Ok(kept)
}

/// The sorted intersection of two sorted, deduplicated id lists.
fn intersect_sorted(left: &[i64], right: &[i64]) -> Vec<i64> {
    let mut out = Vec::with_capacity(left.len().min(right.len()));
    let (mut i, mut j) = (0usize, 0usize);
    while i < left.len() && j < right.len() {
        match left[i].cmp(&right[j]) {
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
            std::cmp::Ordering::Equal => {
                out.push(left[i]);
                i += 1;
                j += 1;
            }
        }
    }
    out
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

    fn varint(value: u64) -> Vec<u8> {
        let mut out = Vec::new();
        append_varint(&mut out, value);
        out
    }

    #[test]
    fn decode_round_trips_the_reference_encoder() {
        for ids in [vec![], vec![1], vec![3, 200, 1 << 62], (1..300).collect::<Vec<i64>>(), vec![i64::MAX]] {
            assert_eq!(decode_postings(&encode_reference(&ids)).unwrap(), ids);
        }
        assert_eq!(decode_postings(&[0]).unwrap(), Vec::<i64>::new());
    }

    #[test]
    fn decode_refuses_every_malformed_class() {
        assert_eq!(decode_postings(b"").unwrap_err(), PostingError::EmptyBlob);
        assert_eq!(decode_postings(&[0x01, 0x81]).unwrap_err(), PostingError::Truncated);
        let mut wide = vec![0x01];
        wide.extend([0x80; 10]);
        wide.push(0x01);
        assert_eq!(decode_postings(&wide).unwrap_err(), PostingError::OverWide);
        let mut minimal = varint(1);
        minimal.extend([0x85, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x01]);
        assert_eq!(decode_postings(&minimal).unwrap_err(), PostingError::OverWide);
        assert_eq!(decode_postings(&[0x01, 0x81, 0x00]).unwrap_err(), PostingError::NonCanonical);
        assert_eq!(decode_postings(&[0x02, 0x01]).unwrap_err(), PostingError::CountMismatch { count: 2, held: 1 });
        assert_eq!(decode_postings(&[0x02, 0x01, 0x00]).unwrap_err(), PostingError::NonPositiveDelta);
        let mut wrap = varint(2);
        wrap.extend(varint(i64::MAX as u64));
        wrap.extend(varint(i64::MAX as u64));
        assert_eq!(decode_postings(&wrap).unwrap_err(), PostingError::Wrap);
    }

    #[test]
    fn candidates_and_or_allow_and_cap() {
        let a = encode_reference(&[1, 2, 3, 5, 8, 13]);
        let b = encode_reference(&[2, 3, 8, 21]);
        let c = encode_reference(&[3, 8, 34]);
        let d = encode_reference(&[40, 41]);
        let groups: Vec<Vec<&[u8]>> = vec![vec![&a, &b, &c], vec![&d], vec![]];
        assert_eq!(candidate_ids(&groups, None, 100).unwrap(), (vec![3, 8, 40, 41], 4));
        assert_eq!(candidate_ids(&groups, Some(&[8, 9, 41]), 100).unwrap(), (vec![8, 41], 2));
        // The cap slices after the allow-list meets the union; the count is pre-cap.
        assert_eq!(candidate_ids(&groups, Some(&[3, 8, 41]), 2).unwrap(), (vec![3, 8], 3));
        assert_eq!(candidate_ids(&groups, None, 0).unwrap(), (vec![], 4));
        // Overlapping groups deduplicate; an empty first blob empties its group.
        let overlap: Vec<Vec<&[u8]>> = vec![vec![&a], vec![&b]];
        assert_eq!(candidate_ids(&overlap, None, 100).unwrap().0, vec![1, 2, 3, 5, 8, 13, 21]);
        let none = encode_reference(&[]);
        let emptied: Vec<Vec<&[u8]>> = vec![vec![&none, &a]];
        assert_eq!(candidate_ids(&emptied, None, 100).unwrap(), (vec![], 0));
        assert_eq!(candidate_ids(&[], None, 100).unwrap(), (vec![], 0));
    }

    #[test]
    fn a_corrupt_later_blob_is_refused_even_when_survivors_are_empty() {
        let none = encode_reference(&[]);
        let groups: Vec<Vec<&[u8]>> = vec![vec![&none, &[0x02, 0x01][..]]];
        assert_eq!(candidate_ids(&groups, None, 10).unwrap_err(), PostingError::CountMismatch { count: 2, held: 1 });
    }
}
