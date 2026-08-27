//! Cosine top-k over one page of packed float32 vectors.
//!
//! The host stores an embedding as packed little-endian float32 bytes,
//! unit-normalized on write, and its query the same way — so cosine
//! similarity is the plain dot product, and that is what this kernel
//! computes. One call scores one fetched page: `ids.len()` rows of
//! `query.len()` components concatenated in id order, back the top `k`
//! as `(id, score)` ordered `score DESC, id ASC`. That order is total —
//! ties break on id — so the same `k` from any two pages merge to the
//! same answer on every engine. Every row decodes byte by byte with
//! `f32::from_le_bytes` (the buffer's alignment and the host's
//! endianness never matter) and accumulates in float32 from the first
//! component to the last, so a score is bit-reproducible.

use std::cmp::Ordering;

use rayon::prelude::*;

/// Bytes per packed component.
const COMPONENT_BYTES: usize = 4;

/// Pages with fewer rows than this score on the calling thread; larger
/// pages split their dot products across the rayon pool.
const PARALLEL_ROWS: usize = 4096;

#[derive(Debug, PartialEq, Eq)]
pub enum VectorError {
    EmptyQuery,
    LengthMismatch { rows: usize, dimension: usize, actual: usize },
}

impl std::fmt::Display for VectorError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyQuery => write!(f, "the query vector is empty"),
            Self::LengthMismatch { rows, dimension, actual } => {
                let expected = rows.saturating_mul(*dimension).saturating_mul(COMPONENT_BYTES);
                write!(f, "expected {expected} bytes for {rows} vectors of {dimension} components, got {actual}")
            }
        }
    }
}

impl std::error::Error for VectorError {}

// ---------------------------------------------------------------------------
// Top-k
// ---------------------------------------------------------------------------

/// The top `k` of `ids` by dot product with `query`, `score DESC, id ASC`.
///
/// `vectors` holds `ids.len()` packed little-endian float32 rows of
/// `query.len()` components in id order. An empty query, or a byte
/// length other than `ids.len() * query.len() * 4`, is refused.
pub fn cosine_topk(query: &[f32], ids: &[i64], vectors: &[u8], k: usize) -> Result<Vec<(i64, f32)>, VectorError> {
    if query.is_empty() {
        return Err(VectorError::EmptyQuery);
    }
    let expected = ids.len().checked_mul(query.len()).and_then(|n| n.checked_mul(COMPONENT_BYTES));
    if expected != Some(vectors.len()) {
        return Err(VectorError::LengthMismatch { rows: ids.len(), dimension: query.len(), actual: vectors.len() });
    }
    if k == 0 || ids.is_empty() {
        return Ok(Vec::new());
    }
    let stride = query.len() * COMPONENT_BYTES;
    let mut ranked: Vec<(i64, f32)> = if ids.len() < PARALLEL_ROWS {
        vectors.chunks_exact(stride).zip(ids).map(|(row, id)| (*id, dot(query, row))).collect()
    } else {
        vectors.par_chunks_exact(stride).zip(ids).map(|(row, id)| (*id, dot(query, row))).collect()
    };
    if k < ranked.len() {
        ranked.select_nth_unstable_by(k - 1, rank_order);
        ranked.truncate(k);
    }
    ranked.sort_unstable_by(rank_order);
    Ok(ranked)
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// The dot product of `query` and one packed row, accumulated in float32
/// from the first component to the last.
fn dot(query: &[f32], row: &[u8]) -> f32 {
    let mut acc = 0.0f32;
    for (q, bytes) in query.iter().zip(row.chunks_exact(COMPONENT_BYTES)) {
        acc += q * f32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]);
    }
    acc
}

/// `score DESC, id ASC`; a NaN score takes its IEEE total-order place so
/// the ordering stays total on every bit pattern.
fn rank_order(a: &(i64, f32), b: &(i64, f32)) -> Ordering {
    b.1.partial_cmp(&a.1).unwrap_or_else(|| b.1.total_cmp(&a.1)).then(a.0.cmp(&b.0))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn packed(rows: &[&[f32]]) -> Vec<u8> {
        rows.iter().flat_map(|row| row.iter().flat_map(|v| v.to_le_bytes())).collect()
    }

    #[test]
    fn exact_top_k_by_dot_product() {
        let page = packed(&[&[0.0, 1.0], &[1.0, 0.0], &[0.6, 0.8]]);
        let top = cosine_topk(&[1.0, 0.0], &[1, 2, 3], &page, 2).unwrap();
        assert_eq!(top, vec![(2, 1.0), (3, 0.6)]);
    }

    #[test]
    fn ties_break_on_ascending_id() {
        let page = packed(&[&[1.0, 0.0], &[1.0, 0.0], &[0.0, 1.0]]);
        let top = cosine_topk(&[1.0, 0.0], &[9, 4, 1], &page, 3).unwrap();
        assert_eq!(top, vec![(4, 1.0), (9, 1.0), (1, 0.0)]);
    }

    #[test]
    fn k_past_the_page_returns_every_row() {
        let page = packed(&[&[1.0], &[-1.0]]);
        assert_eq!(cosine_topk(&[1.0], &[1, 2], &page, 10).unwrap(), vec![(1, 1.0), (2, -1.0)]);
    }

    #[test]
    fn k_zero_and_the_empty_page_are_empty() {
        assert_eq!(cosine_topk(&[1.0], &[1], &packed(&[&[1.0]]), 0).unwrap(), vec![]);
        assert_eq!(cosine_topk(&[1.0], &[], &[], 5).unwrap(), vec![]);
    }

    #[test]
    fn a_length_mismatch_is_refused() {
        let err = cosine_topk(&[1.0, 0.0], &[1, 2], &packed(&[&[1.0, 0.0]]), 1).unwrap_err();
        assert_eq!(err, VectorError::LengthMismatch { rows: 2, dimension: 2, actual: 8 });
        assert_eq!(err.to_string(), "expected 16 bytes for 2 vectors of 2 components, got 8");
    }

    #[test]
    fn an_empty_query_is_refused() {
        assert_eq!(cosine_topk(&[], &[1], &[], 1).unwrap_err(), VectorError::EmptyQuery);
        assert_eq!(VectorError::EmptyQuery.to_string(), "the query vector is empty");
    }

    #[test]
    fn a_nan_row_keeps_the_order_total() {
        let page = packed(&[&[f32::NAN], &[0.5], &[-f32::NAN]]);
        let top = cosine_topk(&[1.0], &[1, 2, 3], &page, 3).unwrap();
        assert!(top[0].1.is_nan() && top[0].0 == 1);
        assert_eq!(top[1], (2, 0.5));
        assert!(top[2].1.is_nan() && top[2].0 == 3);
    }

    #[test]
    fn the_parallel_path_agrees_with_the_serial_one() {
        let rows = PARALLEL_ROWS + 100;
        let ids: Vec<i64> = (1..=rows as i64).collect();
        let vectors: Vec<f32> = (0..rows).flat_map(|i| [(i % 17) as f32 / 17.0, ((i * 7) % 13) as f32 / 13.0]).collect();
        let page: Vec<u8> = vectors.iter().flat_map(|v| v.to_le_bytes()).collect();
        let parallel = cosine_topk(&[0.6, 0.8], &ids, &page, 50).unwrap();
        let serial: Vec<(i64, f32)> = {
            let mut all: Vec<(i64, f32)> = page
                .chunks_exact(8)
                .zip(&ids)
                .map(|(row, id)| (*id, dot(&[0.6, 0.8], row)))
                .collect();
            all.sort_by(rank_order);
            all.truncate(50);
            all
        };
        assert_eq!(parallel, serial);
    }
}
