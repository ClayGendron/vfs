//! The pyo3 binding maturin embeds into the vfs-py wheel as `vfs._native`.
//!
//! Thin by contract: bytes and ints in, bytes and ints out, no Python
//! objects inside the engine. The host seam (`vfs/native.py`) owns fold and
//! normalization policy, checks `PROTOCOL_VERSION`, and falls back to the
//! pure-Python reference implementation when this module is absent.

use std::sync::{Mutex, OnceLock};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::grams::GramExtractor;
use crate::postings::{DrainedPostings, PostingsAccumulator};

/// Bumped on any change to the seam's shapes or semantics; the Python side
/// warns and falls back on mismatch rather than guessing.
const PROTOCOL_VERSION: u32 = 1;

static GATE: OnceLock<Mutex<GramExtractor>> = OnceLock::new();

/// Count distinct trigrams of pre-folded bytes, early-exiting past `cap`:
/// any return value greater than `cap` means "over cap".
#[pyfunction]
fn distinct_gram_count(data: &[u8], cap: usize) -> usize {
    let gate = GATE.get_or_init(|| Mutex::new(GramExtractor::new()));
    gate.lock().expect("gate poisoned").distinct_capped(data, cap)
}

/// Streaming posting-set builder: feed (doc_id, folded bytes) in strictly
/// increasing doc-id order, then drain gram-ordered byte-capped batches of
/// (gram_key, blob, doc_count) rows.
#[pyclass]
struct PostingsBuilder {
    accumulator: Option<PostingsAccumulator>,
    drained: Option<DrainedPostings>,
}

#[pymethods]
impl PostingsBuilder {
    #[new]
    fn new() -> Self {
        Self { accumulator: Some(PostingsAccumulator::new()), drained: None }
    }

    fn add_docs(&mut self, py: Python<'_>, docs: Vec<(i64, Vec<u8>)>) -> PyResult<()> {
        let Some(accumulator) = self.accumulator.as_mut() else {
            return Err(PyValueError::new_err("builder is already draining; create a fresh one"));
        };
        py.detach(|| {
            for (doc_id, data) in &docs {
                accumulator
                    .add_doc(*doc_id, data)
                    .map_err(|err| PyValueError::new_err(err.to_string()))?;
            }
            Ok(())
        })
    }

    fn next_batch<'py>(
        &mut self,
        py: Python<'py>,
        byte_cap: usize,
    ) -> PyResult<Option<Vec<(u32, Bound<'py, PyBytes>, u32)>>> {
        if self.drained.is_none() {
            let Some(accumulator) = self.accumulator.take() else {
                return Err(PyValueError::new_err("builder was never fed; create a fresh one"));
            };
            self.drained = Some(py.detach(|| accumulator.finish()));
        }
        let drained = self.drained.as_mut().expect("just installed");
        let Some(rows) = py.detach(|| drained.next_batch(byte_cap)) else {
            return Ok(None);
        };
        Ok(Some(
            rows.into_iter()
                .map(|row| (row.gram, PyBytes::new(py, &row.blob), row.doc_count))
                .collect(),
        ))
    }
}

#[pymodule(name = "_native")]
fn native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("PROTOCOL_VERSION", PROTOCOL_VERSION)?;
    m.add_function(wrap_pyfunction!(distinct_gram_count, m)?)?;
    m.add_class::<PostingsBuilder>()?;
    Ok(())
}
