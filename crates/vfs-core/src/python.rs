//! The pyo3 binding maturin embeds into the vfs-py wheel as `vfs._native`.
//!
//! Thin by contract: bytes and ints in, bytes and ints out, no Python
//! objects inside the engine. The host seam (`vfs/native.py`) owns fold and
//! normalization policy, checks `PROTOCOL_VERSION`, and falls back to the
//! pure-Python reference implementation when this module is absent.

use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedBytes;
use pyo3::types::PyBytes;

use crate::grams::GramExtractor;
use crate::postings::{DrainedPostings, PostingsAccumulator};
use crate::verify::{Matcher, count_batch, hits_batch};

/// Bumped on any change to the seam's shapes or semantics; the Python side
/// warns and falls back on mismatch rather than guessing.
const PROTOCOL_VERSION: u32 = 2;

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

/// The compiled match authority for one grep pattern: bodies of UTF-8
/// bytes in, per-line hit facts out. The pattern arrives fully assembled
/// (escaping, word-wrapping, and the language gate are host policy);
/// `budget` is wall seconds from call start — bodies started past it are
/// skipped and the outcome reports incomplete.
#[pyclass]
struct ContentMatcher {
    matcher: Matcher,
}

#[pymethods]
impl ContentMatcher {
    #[new]
    fn new(pattern: &str, case_insensitive: bool) -> PyResult<Self> {
        Matcher::new(pattern, case_insensitive)
            .map(|matcher| Self { matcher })
            .map_err(|err| PyValueError::new_err(err.to_string()))
    }

    /// Matched-line counts per body (non-matching lines when `invert`),
    /// each capped at `cap`; returns (counts, completed).
    #[pyo3(signature = (bodies, *, cap, invert, budget))]
    fn count_lines(
        &self,
        py: Python<'_>,
        bodies: Vec<PyBackedBytes>,
        cap: Option<u64>,
        invert: bool,
        budget: Option<f64>,
    ) -> (Vec<u64>, bool) {
        let deadline = budget.map(|secs| Instant::now() + Duration::from_secs_f64(secs.max(0.0)));
        let slices: Vec<&[u8]> = bodies.iter().map(|body| body.as_ref()).collect();
        let outcome = py.detach(|| count_batch(&self.matcher, &slices, cap, invert, deadline));
        (outcome.results, outcome.completed)
    }

    /// Per body, up-to-`cap` hits as (start_line, end_line, match_line,
    /// context bytes) with 1-based line numbers; returns (hits, completed).
    #[pyo3(signature = (bodies, *, before, after, cap, invert, budget))]
    #[allow(clippy::too_many_arguments)]
    fn hit_lines<'py>(
        &self,
        py: Python<'py>,
        bodies: Vec<PyBackedBytes>,
        before: u32,
        after: u32,
        cap: Option<u64>,
        invert: bool,
        budget: Option<f64>,
    ) -> (Vec<Vec<(u32, u32, u32, Bound<'py, PyBytes>)>>, bool) {
        let deadline = budget.map(|secs| Instant::now() + Duration::from_secs_f64(secs.max(0.0)));
        let slices: Vec<&[u8]> = bodies.iter().map(|body| body.as_ref()).collect();
        let outcome =
            py.detach(|| hits_batch(&self.matcher, &slices, before, after, cap, invert, deadline));
        let rows = outcome
            .results
            .iter()
            .zip(&slices)
            .map(|(hits, body)| {
                hits.iter()
                    .map(|hit| {
                        let content = PyBytes::new(py, &body[hit.span.0..hit.span.1]);
                        (hit.start_line, hit.end_line, hit.match_line, content)
                    })
                    .collect()
            })
            .collect();
        (rows, outcome.completed)
    }
}

#[pymodule(name = "_native")]
fn native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("PROTOCOL_VERSION", PROTOCOL_VERSION)?;
    m.add_function(wrap_pyfunction!(distinct_gram_count, m)?)?;
    m.add_class::<PostingsBuilder>()?;
    m.add_class::<ContentMatcher>()?;
    Ok(())
}
