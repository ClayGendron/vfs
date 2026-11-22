//! Distinct byte-trigram extraction over a pre-folded byte stream.
//!
//! A trigram is three consecutive bytes packed big-endian into the low 24
//! bits of a `u32` — the same key space the host index stores. The extractor
//! owns a 2 MiB presence bitset over all 2^24 keys and clears only the bits
//! it set (via the collected output), so per-document cost is O(len + unique)
//! with no per-document allocation or memset.

pub const GRAM_SIZE: usize = 3;

const GRAM_SPACE: usize = 1 << 24;

pub struct GramExtractor {
    seen: Vec<u64>,
    scratch: Vec<u32>,
}

impl GramExtractor {
    pub fn new() -> Self {
        Self { seen: vec![0u64; GRAM_SPACE / 64], scratch: Vec::new() }
    }

    /// Collect the distinct packed trigrams of `data` into `out`, in first-
    /// arrival order. `out` is cleared first and holds no duplicates.
    pub fn unique_grams(&mut self, data: &[u8], out: &mut Vec<u32>) {
        out.clear();
        if data.len() < GRAM_SIZE {
            return;
        }
        let mut gram: u32 = (u32::from(data[0]) << 8) | u32::from(data[1]);
        for &byte in &data[2..] {
            gram = ((gram << 8) | u32::from(byte)) & 0x00FF_FFFF;
            let word = (gram >> 6) as usize;
            let bit = 1u64 << (gram & 63);
            if self.seen[word] & bit == 0 {
                self.seen[word] |= bit;
                out.push(gram);
            }
        }
        for &gram in out.iter() {
            self.seen[(gram >> 6) as usize] &= !(1u64 << (gram & 63));
        }
    }

    /// Count distinct trigrams, stopping as soon as the count exceeds `cap`;
    /// returns `min(distinct, cap + 1)`, so `result > cap` means "over cap".
    pub fn distinct_capped(&mut self, data: &[u8], cap: usize) -> usize {
        let mut scratch = std::mem::take(&mut self.scratch);
        scratch.clear();
        if data.len() >= GRAM_SIZE {
            let mut gram: u32 = (u32::from(data[0]) << 8) | u32::from(data[1]);
            for &byte in &data[2..] {
                gram = ((gram << 8) | u32::from(byte)) & 0x00FF_FFFF;
                let word = (gram >> 6) as usize;
                let bit = 1u64 << (gram & 63);
                if self.seen[word] & bit == 0 {
                    self.seen[word] |= bit;
                    scratch.push(gram);
                    if scratch.len() > cap {
                        break;
                    }
                }
            }
            for &gram in scratch.iter() {
                self.seen[(gram >> 6) as usize] &= !(1u64 << (gram & 63));
            }
        }
        let count = scratch.len();
        self.scratch = scratch;
        count
    }
}

impl Default for GramExtractor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn reference(data: &[u8]) -> Vec<u32> {
        data.windows(GRAM_SIZE)
            .map(|w| (u32::from(w[0]) << 16) | (u32::from(w[1]) << 8) | u32::from(w[2]))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }

    #[test]
    fn matches_reference_and_resets_between_docs() {
        let mut extractor = GramExtractor::new();
        let mut out = Vec::new();
        for data in [&b"abcabcabc"[..], b"", b"ab", b"xyz", b"\x00\xff\x00\xff", b"hello world"] {
            extractor.unique_grams(data, &mut out);
            let mut sorted = out.clone();
            sorted.sort_unstable();
            assert_eq!(sorted, reference(data), "doc {data:?}");
        }
    }

    #[test]
    fn arrival_order_is_first_occurrence() {
        let mut extractor = GramExtractor::new();
        let mut out = Vec::new();
        extractor.unique_grams(b"abcbca", &mut out);
        let key = |w: &[u8]| (u32::from(w[0]) << 16) | (u32::from(w[1]) << 8) | u32::from(w[2]);
        assert_eq!(out, vec![key(b"abc"), key(b"bcb"), key(b"cbc"), key(b"bca")]);
    }

    #[test]
    fn distinct_capped_exact_and_over() {
        let mut extractor = GramExtractor::new();
        assert_eq!(extractor.distinct_capped(b"abcabc", 10), 3);
        assert_eq!(extractor.distinct_capped(b"abcdefgh", 3), 4);
        assert_eq!(extractor.distinct_capped(b"", 3), 0);
        assert_eq!(extractor.distinct_capped(b"ab", 3), 0);
        // The bitset was cleared even on the early-exit path.
        assert_eq!(extractor.distinct_capped(b"abcdefgh", 100), 6);
    }
}
