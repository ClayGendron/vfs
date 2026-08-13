//! Purpose-built posting-list kernel for the vfs grep spike.
//!
//! Varint layout matches the spike index: LSB-first 7-bit groups with a
//! continuation high bit; gaps from a cursor at -1 (first gap = doc0 + 1).
//!
//! `intersect_rarest` is the fused hot path: decode the first (rarest) blob
//! once, then stream-decode each subsequent blob merging against the current
//! sorted candidate list with a two-pointer walk — later blobs never
//! materialize their full id lists.

use pyo3::prelude::*;

#[inline]
fn decode_into(blob: &[u8], out: &mut Vec<i64>) {
    let mut doc: i64 = -1;
    let mut val: u64 = 0;
    let mut shift: u32 = 0;
    for &byte in blob {
        val |= ((byte & 0x7F) as u64) << shift;
        if byte & 0x80 != 0 {
            shift += 7;
        } else {
            doc += val as i64;
            out.push(doc);
            val = 0;
            shift = 0;
        }
    }
}

/// Decode one varint posting blob to its sorted doc-id list.
#[pyfunction]
fn decode_postings(blob: &[u8]) -> Vec<i64> {
    let mut out = Vec::with_capacity(blob.len());
    decode_into(blob, &mut out);
    out
}

/// Fused decode+intersect over rarest-first blobs; returns surviving doc ids.
#[pyfunction]
fn intersect_rarest(blobs: Vec<Vec<u8>>) -> Vec<i64> {
    let Some(first) = blobs.first() else {
        return Vec::new();
    };
    let mut current = Vec::with_capacity(first.len());
    decode_into(first, &mut current);

    for blob in &blobs[1..] {
        if current.is_empty() {
            break;
        }
        let mut kept = Vec::with_capacity(current.len());
        let mut pos = 0usize; // cursor into `current` (sorted ascending)
        let mut doc: i64 = -1;
        let mut val: u64 = 0;
        let mut shift: u32 = 0;
        for &byte in blob.iter() {
            val |= ((byte & 0x7F) as u64) << shift;
            if byte & 0x80 != 0 {
                shift += 7;
            } else {
                doc += val as i64;
                val = 0;
                shift = 0;
                while pos < current.len() && current[pos] < doc {
                    pos += 1;
                }
                if pos == current.len() {
                    break;
                }
                if current[pos] == doc {
                    kept.push(doc);
                    pos += 1;
                }
            }
        }
        current = kept;
    }
    current
}

#[pymodule]
fn vfs_postings_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_postings, m)?)?;
    m.add_function(wrap_pyfunction!(intersect_rarest, m)?)?;
    Ok(())
}
