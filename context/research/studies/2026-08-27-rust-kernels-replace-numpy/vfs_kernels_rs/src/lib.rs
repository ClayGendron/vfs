//! Throwaway kernels for the "Rust kernels replace numpy" study.
//!
//! Every kernel takes blobs / packed arrays as bytes and returns packed
//! native-endian arrays as `bytes` (i64 or f64), so that nothing boxed
//! crosses the boundary: the caller wraps the result in `array('q')`,
//! `array('d')`, `memoryview`, or `np.frombuffer` as it likes.
//!
//! Varint layout is vfs's posting codec: LEB128, LSB-first 7-bit groups,
//! high bit continues; a posting blob is a count varint then strictly
//! positive deltas. Validation mirrors `vfs.models.postings`: truncated,
//! over-wide (> 9 bytes) and non-canonical spellings, count mismatch,
//! non-positive delta and int64 wrap are all refused.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedBytes;
use pyo3::types::PyBytes;

const MAX_VARINT_BYTES: usize = 9;

type Res<T> = Result<T, &'static str>;

/// A streaming varint reader with the codec's structural checks.
struct Varints<'a> {
    blob: &'a [u8],
    pos: usize,
}

impl<'a> Varints<'a> {
    fn new(blob: &'a [u8]) -> Self {
        Varints { blob, pos: 0 }
    }

    #[inline]
    fn next(&mut self) -> Res<Option<u64>> {
        if self.pos >= self.blob.len() {
            return Ok(None);
        }
        let mut value: u64 = 0;
        let mut shift: u32 = 0;
        let start = self.pos;
        loop {
            if self.pos >= self.blob.len() {
                return Err("truncated varint at end of blob");
            }
            let byte = self.blob[self.pos];
            self.pos += 1;
            if self.pos - start > MAX_VARINT_BYTES {
                return Err("over-wide varint");
            }
            value |= u64::from(byte & 0x7F) << shift;
            if byte & 0x80 == 0 {
                if self.pos - start > 1 && byte == 0 {
                    return Err("non-canonical varint spelling");
                }
                return Ok(Some(value));
            }
            shift += 7;
        }
    }
}

fn decode_varints_vec(blob: &[u8]) -> Res<Vec<i64>> {
    let mut out = Vec::with_capacity(blob.len());
    let mut reader = Varints::new(blob);
    while let Some(v) = reader.next()? {
        out.push(v as i64);
    }
    Ok(out)
}

/// The doc ids of a count-prefixed delta blob, validated.
fn decode_postings_vec(blob: &[u8]) -> Res<Vec<i64>> {
    let mut reader = Varints::new(blob);
    let Some(count) = reader.next()? else {
        return Err("empty posting blob (a valid empty list is one zero byte)");
    };
    let mut out = Vec::with_capacity(count as usize);
    let mut id: i64 = 0;
    let mut seen: u64 = 0;
    while let Some(delta) = reader.next()? {
        let delta = delta as i64;
        if delta < 1 {
            return Err("non-positive delta");
        }
        id = id.wrapping_add(delta);
        if id <= 0 {
            return Err("doc ids not monotone (int64 wrap)");
        }
        out.push(id);
        seen += 1;
    }
    if seen != count {
        return Err("count header mismatch");
    }
    Ok(out)
}

fn i64_bytes<'py>(py: Python<'py>, values: &[i64]) -> Bound<'py, PyBytes> {
    PyBytes::new_with(py, values.len() * 8, |buf| {
        for (chunk, v) in buf.chunks_exact_mut(8).zip(values) {
            chunk.copy_from_slice(&v.to_ne_bytes());
        }
        Ok(())
    })
    .expect("bytes allocation")
}

fn f64_bytes<'py>(py: Python<'py>, values: &[f64]) -> Bound<'py, PyBytes> {
    PyBytes::new_with(py, values.len() * 8, |buf| {
        for (chunk, v) in buf.chunks_exact_mut(8).zip(values) {
            chunk.copy_from_slice(&v.to_ne_bytes());
        }
        Ok(())
    })
    .expect("bytes allocation")
}

fn as_i64s(raw: &[u8]) -> Vec<i64> {
    raw.chunks_exact(8).map(|c| i64::from_ne_bytes(c.try_into().expect("8 bytes"))).collect()
}

fn as_f64s(raw: &[u8]) -> Vec<f64> {
    raw.chunks_exact(8).map(|c| f64::from_ne_bytes(c.try_into().expect("8 bytes"))).collect()
}

fn err(e: &'static str) -> PyErr {
    PyValueError::new_err(e)
}

// ---------------------------------------------------------------------------
// Site 1: posting decode
// ---------------------------------------------------------------------------

/// Decode a posting blob to packed i64 doc ids (native endian).
#[pyfunction]
fn decode_postings<'py>(py: Python<'py>, blob: PyBackedBytes) -> PyResult<Bound<'py, PyBytes>> {
    let ids = py.detach(|| decode_postings_vec(&blob)).map_err(err)?;
    Ok(i64_bytes(py, &ids))
}

/// Control: the same decode returned as a Python list of ints.
#[pyfunction]
fn decode_postings_list(py: Python<'_>, blob: PyBackedBytes) -> PyResult<Vec<i64>> {
    py.detach(|| decode_postings_vec(&blob)).map_err(err)
}

/// Decode a bare varint run (the lexical `tfs` / `dls` blobs) to packed i64.
#[pyfunction]
fn decode_varints<'py>(py: Python<'py>, blob: PyBackedBytes) -> PyResult<Bound<'py, PyBytes>> {
    let values = py.detach(|| decode_varints_vec(&blob)).map_err(err)?;
    Ok(i64_bytes(py, &values))
}

// ---------------------------------------------------------------------------
// Site 2: the grep ladder's set algebra
// ---------------------------------------------------------------------------

/// Fused decode+intersect over rarest-first blobs: survivors as packed i64.
///
/// The rarest blob is decoded once; every later blob is stream-decoded
/// with a two-pointer merge against the sorted survivors, so later blobs
/// never materialize. Every blob is still fully validated.
#[pyfunction]
fn intersect_rarest<'py>(py: Python<'py>, blobs: Vec<PyBackedBytes>) -> PyResult<Bound<'py, PyBytes>> {
    let survivors = py
        .detach(|| -> Res<Vec<i64>> {
            let Some(first) = blobs.first() else {
                return Ok(Vec::new());
            };
            let mut current = decode_postings_vec(first)?;
            for blob in &blobs[1..] {
                let mut reader = Varints::new(blob);
                let Some(count) = reader.next()? else {
                    return Err("empty posting blob (a valid empty list is one zero byte)");
                };
                let mut kept = Vec::with_capacity(current.len());
                let mut pos = 0usize;
                let mut id: i64 = 0;
                let mut seen: u64 = 0;
                while let Some(delta) = reader.next()? {
                    let delta = delta as i64;
                    if delta < 1 {
                        return Err("non-positive delta");
                    }
                    id = id.wrapping_add(delta);
                    if id <= 0 {
                        return Err("doc ids not monotone (int64 wrap)");
                    }
                    seen += 1;
                    while pos < current.len() && current[pos] < id {
                        pos += 1;
                    }
                    if pos < current.len() && current[pos] == id {
                        kept.push(id);
                        pos += 1;
                    }
                }
                if seen != count {
                    return Err("count header mismatch");
                }
                current = kept;
                if current.is_empty() {
                    break;
                }
            }
            Ok(current)
        })
        .map_err(err)?;
    Ok(i64_bytes(py, &survivors))
}

/// Sorted, deduplicated union of packed i64 arrays (the OR of AND-groups).
#[pyfunction]
fn union_sorted<'py>(py: Python<'py>, parts: Vec<PyBackedBytes>) -> Bound<'py, PyBytes> {
    let merged = py.detach(|| {
        let mut all: Vec<i64> = Vec::with_capacity(parts.iter().map(|p| p.len() / 8).sum());
        for part in &parts {
            all.extend(part.chunks_exact(8).map(|c| i64::from_ne_bytes(c.try_into().expect("8 bytes"))));
        }
        all.sort_unstable();
        all.dedup();
        all
    });
    i64_bytes(py, &merged)
}

/// Intersection of two sorted packed i64 arrays (the allow-list join).
#[pyfunction]
fn intersect_sorted<'py>(py: Python<'py>, a: PyBackedBytes, b: PyBackedBytes) -> Bound<'py, PyBytes> {
    let out = py.detach(|| {
        let a = as_i64s(&a);
        let b = as_i64s(&b);
        let mut out = Vec::with_capacity(a.len().min(b.len()));
        let (mut i, mut j) = (0usize, 0usize);
        while i < a.len() && j < b.len() {
            match a[i].cmp(&b[j]) {
                std::cmp::Ordering::Less => i += 1,
                std::cmp::Ordering::Greater => j += 1,
                std::cmp::Ordering::Equal => {
                    out.push(a[i]);
                    i += 1;
                    j += 1;
                }
            }
        }
        out
    });
    i64_bytes(py, &out)
}

// ---------------------------------------------------------------------------
// Site 3: the term summary codec
// ---------------------------------------------------------------------------

/// `(first_ids as packed i64, max_weights as packed f64)` of a summary blob.
#[pyfunction]
fn decode_summary<'py>(py: Python<'py>, blob: PyBackedBytes) -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
    let (firsts, maxes) = py
        .detach(|| -> Res<(Vec<i64>, Vec<f64>)> {
            let blob: &[u8] = &blob;
            let mut firsts = Vec::with_capacity(blob.len() / 10);
            let mut maxes = Vec::with_capacity(blob.len() / 10);
            let mut pos = 0usize;
            let mut first: i64 = 0;
            while pos < blob.len() {
                let mut delta: u64 = 0;
                let mut shift: u32 = 0;
                loop {
                    if pos >= blob.len() {
                        return Err("truncated summary");
                    }
                    let byte = blob[pos];
                    pos += 1;
                    delta |= u64::from(byte & 0x7F) << shift;
                    if byte & 0x80 == 0 {
                        break;
                    }
                    shift += 7;
                }
                first = first.wrapping_add(delta as i64);
                if pos + 8 > blob.len() {
                    return Err("truncated summary");
                }
                let weight = f64::from_le_bytes(blob[pos..pos + 8].try_into().expect("8 bytes"));
                pos += 8;
                firsts.push(first);
                maxes.push(weight);
            }
            Ok((firsts, maxes))
        })
        .map_err(err)?;
    Ok((i64_bytes(py, &firsts), f64_bytes(py, &maxes)))
}

// ---------------------------------------------------------------------------
// Site 4: block selection between rounds
// ---------------------------------------------------------------------------

/// Block numbers that can still change a top-k (see `competing_blocks`).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn competing_blocks<'py>(
    py: Python<'py>,
    first_ids: PyBackedBytes,
    max_weights: PyBackedBytes,
    candidates: PyBackedBytes,
    scores: PyBackedBytes,
    theta: f64,
    rest: f64,
) -> Bound<'py, PyBytes> {
    let out = py.detach(|| {
        let firsts = as_i64s(&first_ids);
        let maxes = as_f64s(&max_weights);
        let cands = as_i64s(&candidates);
        let scores = as_f64s(&scores);
        let mut best = vec![f64::NEG_INFINITY; firsts.len()];
        if !cands.is_empty() && !firsts.is_empty() {
            for (&c, &s) in cands.iter().zip(&scores) {
                // searchsorted(side="right") - 1
                let index = firsts.partition_point(|&f| f <= c);
                if index > 0 && s > best[index - 1] {
                    best[index - 1] = s;
                }
            }
        }
        let mut out: Vec<i64> = Vec::new();
        for i in 0..firsts.len() {
            let m = maxes[i] + rest;
            if m >= theta || best[i] + m >= theta {
                out.push(i as i64);
            }
        }
        out
    });
    i64_bytes(py, &out)
}

#[pymodule]
fn vfs_kernels_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_postings, m)?)?;
    m.add_function(wrap_pyfunction!(decode_postings_list, m)?)?;
    m.add_function(wrap_pyfunction!(decode_varints, m)?)?;
    m.add_function(wrap_pyfunction!(intersect_rarest, m)?)?;
    m.add_function(wrap_pyfunction!(union_sorted, m)?)?;
    m.add_function(wrap_pyfunction!(intersect_sorted, m)?)?;
    m.add_function(wrap_pyfunction!(decode_summary, m)?)?;
    m.add_function(wrap_pyfunction!(competing_blocks, m)?)?;
    Ok(())
}
