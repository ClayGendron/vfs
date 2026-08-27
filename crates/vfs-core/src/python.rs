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
use pyo3::pybacked::{PyBackedBytes, PyBackedStr};
use pyo3::types::PyBytes;

use crate::chunk::{GRAMMAR_NAMES, split_batch};
use crate::grams::GramExtractor;
use crate::lexical::{self, DrainedLexical, LexicalAccumulator, ScoreBlock};
use crate::postings::{DrainedPostings, PostingsAccumulator};
use crate::verify::{Matcher, count_batch, hits_batch};

/// Bumped on any change to the seam's shapes or semantics; the Python side
/// warns and falls back on mismatch rather than guessing.
const PROTOCOL_VERSION: u32 = 4;

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

/// Grammar names the chunk registry serves; the host's extension map
/// filters against this instead of guessing.
#[pyfunction]
fn supported_grammars() -> Vec<&'static str> {
    GRAMMAR_NAMES.to_vec()
}

/// Structure-aware chunk spans for a batch of `(body, grammar)` pairs,
/// parsed in parallel off the GIL. Per body: `None` when the structure
/// path cannot serve it (unknown grammar, language load failure, a
/// body over 4 GiB) — the host falls back to its character splitter —
/// otherwise `(start, end,
/// line_start, line_end, oversized)` rows of byte offsets and 1-based
/// lines; the host slices text, filters whitespace-only chunks, and
/// re-splits oversized leaves.
#[pyfunction]
#[pyo3(signature = (bodies, *, chunk_size))]
fn chunk_spans(
    py: Python<'_>,
    bodies: Vec<(PyBackedBytes, String)>,
    chunk_size: usize,
) -> Vec<Option<Vec<(u32, u32, u32, u32, bool)>>> {
    let pairs: Vec<(&[u8], &str)> =
        bodies.iter().map(|(body, grammar)| (body.as_ref(), grammar.as_str())).collect();
    py.detach(|| {
        split_batch(&pairs, chunk_size)
            .into_iter()
            .map(|rows| {
                rows.map(|rows| {
                    rows.into_iter()
                        .map(|row| (row.start, row.end, row.line_start, row.line_end, row.oversized))
                        .collect()
                })
            })
            .collect()
    })
}

/// The lexical tokenizer: folded terms in order, duplicates kept.
#[pyfunction]
fn tokenize(content: &str) -> Vec<String> {
    lexical::tokenize(content)
}

/// One byte of class flags per code point (word 1, upper 2, lower 4,
/// digit 8, assigned 16) from the generated tables, for the parity check.
#[pyfunction]
fn lexical_char_classes(py: Python<'_>) -> Bound<'_, PyBytes> {
    PyBytes::new(py, &lexical::char_classes())
}

/// The generated casefold map as `(code point, fold)` pairs.
#[pyfunction]
fn lexical_casefolds() -> Vec<(u32, &'static str)> {
    lexical::casefolds().to_vec()
}

/// The Python shapes of a summary row and a block row.
type SummaryTuple<'py> = (String, u32, f64, f64, Bound<'py, PyBytes>);
type BlockTuple<'py> = (String, u32, u32, Bound<'py, PyBytes>, Bound<'py, PyBytes>, Bound<'py, PyBytes>);

/// Streaming lexical builder: feed `(doc_id, text)` in strictly increasing
/// doc-id order (each call returns the docs' token counts), `finish` for
/// `(n_docs, avg_dl)`, then drain term-ordered summary rows and block rows.
#[pyclass]
struct LexicalBuilder {
    accumulator: Option<LexicalAccumulator>,
    drained: Option<DrainedLexical>,
}

impl LexicalBuilder {
    fn sealed(&mut self, py: Python<'_>) -> &mut DrainedLexical {
        if self.drained.is_none() {
            let accumulator = self.accumulator.take().expect("one of the two is always present");
            self.drained = Some(py.detach(|| accumulator.finish()));
        }
        self.drained.as_mut().expect("just installed")
    }
}

#[pymethods]
impl LexicalBuilder {
    #[new]
    fn new() -> Self {
        Self { accumulator: Some(LexicalAccumulator::new()), drained: None }
    }

    fn add_docs(&mut self, py: Python<'_>, docs: Vec<(i64, PyBackedStr)>) -> PyResult<Vec<u32>> {
        let Some(accumulator) = self.accumulator.as_mut() else {
            return Err(PyValueError::new_err(lexical::LexicalError::Sealed.to_string()));
        };
        py.detach(|| {
            docs.iter()
                .map(|(doc_id, text)| accumulator.add_doc(*doc_id, text).map_err(|err| PyValueError::new_err(err.to_string())))
                .collect()
        })
    }

    fn finish(&mut self, py: Python<'_>) -> (u64, f64) {
        let drained = self.sealed(py);
        (drained.n_docs, drained.avg_dl)
    }

    fn next_df_batch<'py>(&mut self, py: Python<'py>, row_cap: usize) -> Option<Vec<SummaryTuple<'py>>> {
        let drained = self.sealed(py);
        let rows = py.detach(|| drained.next_df_batch(row_cap))?;
        Some(
            rows.into_iter()
                .map(|row| (row.term, row.df, row.idf, row.max_weight, PyBytes::new(py, &row.blocks)))
                .collect(),
        )
    }

    fn next_batch<'py>(&mut self, py: Python<'py>, row_cap: usize) -> Option<Vec<BlockTuple<'py>>> {
        let drained = self.sealed(py);
        let rows = py.detach(|| drained.next_batch(row_cap))?;
        Some(
            rows.into_iter()
                .map(|row| {
                    (
                        row.term,
                        row.block_no,
                        row.doc_count,
                        PyBytes::new(py, &row.doc_ids),
                        PyBytes::new(py, &row.tfs),
                        PyBytes::new(py, &row.dls),
                    )
                })
                .collect(),
        )
    }
}

/// BM25 top-`k` over fetched blocks `(term index, bound, doc_ids, tfs,
/// dls)` with `idfs` by term index; `candidates` is a sorted array of
/// native-endian int64 ids the result is restricted to.
#[pyfunction]
#[pyo3(signature = (blocks, idfs, avg_dl, k, candidates=None))]
fn lexical_score(
    py: Python<'_>,
    blocks: Vec<(usize, f64, PyBackedBytes, PyBackedBytes, PyBackedBytes)>,
    idfs: Vec<f64>,
    avg_dl: f64,
    k: usize,
    candidates: Option<PyBackedBytes>,
) -> PyResult<Vec<(i64, f64)>> {
    if blocks.iter().any(|b| b.0 >= idfs.len()) {
        return Err(PyValueError::new_err("block term index outside idfs"));
    }
    let set: Option<Vec<i64>> = candidates.map(|raw| {
        raw.as_ref().chunks_exact(8).map(|c| i64::from_ne_bytes(c.try_into().expect("8 bytes"))).collect()
    });
    let views: Vec<ScoreBlock> = blocks
        .iter()
        .map(|(term, bound, ids, tfs, dls)| ScoreBlock { term: *term, bound: *bound, doc_ids: ids, tfs, dls })
        .collect();
    Ok(py.detach(|| lexical::score(&views, &idfs, avg_dl, k, set.as_deref())))
}

#[pymodule(name = "_native")]
fn native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("PROTOCOL_VERSION", PROTOCOL_VERSION)?;
    m.add("LEXICAL_UNICODE_VERSION", lexical::UNICODE_VERSION)?;
    m.add("LEXICAL_PYTHON_VERSION", lexical::PYTHON_VERSION)?;
    m.add_function(wrap_pyfunction!(distinct_gram_count, m)?)?;
    m.add_function(wrap_pyfunction!(supported_grammars, m)?)?;
    m.add_function(wrap_pyfunction!(chunk_spans, m)?)?;
    m.add_function(wrap_pyfunction!(tokenize, m)?)?;
    m.add_function(wrap_pyfunction!(lexical_char_classes, m)?)?;
    m.add_function(wrap_pyfunction!(lexical_casefolds, m)?)?;
    m.add_function(wrap_pyfunction!(lexical_score, m)?)?;
    m.add_class::<PostingsBuilder>()?;
    m.add_class::<LexicalBuilder>()?;
    m.add_class::<ContentMatcher>()?;
    Ok(())
}
