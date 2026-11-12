//! pyo3 prototype of the overlay-counts kernel for the spike: one call per
//! batch of bodies, the tokenize-and-count done detached from the GIL, the
//! per-term postings handed back as plain tuples.

#[path = "/Users/claygendron/Git/Repos/vfs/crates/vfs-core/src/lexical_tables.rs"]
#[allow(dead_code)]
mod lexical_tables;

#[path = "../../kernel.rs"]
mod kernel;

use pyo3::prelude::*;
use pyo3::pybacked::PyBackedStr;

/// Per query term, the `(doc_id, tf, dl)` postings over `docs` in doc order,
/// and the summed document length. `docs` are `(doc_id, body)` in increasing
/// doc-id order. Runs detached from the GIL; the bodies are borrowed, not copied.
#[pyfunction]
fn overlay_postings(py: Python<'_>, docs: Vec<(i64, PyBackedStr)>, terms: Vec<String>) -> (Vec<Vec<(i64, u32, u32)>>, u64) {
    py.detach(|| {
        let borrowed: Vec<(i64, &str)> = docs.iter().map(|(id, body)| (*id, body.as_ref())).collect();
        let term_refs: Vec<&str> = terms.iter().map(String::as_str).collect();
        kernel::overlay_postings(&borrowed, &term_refs)
    })
}

/// One body's token count and the tf of each term: the per-document crossing probe.
#[pyfunction]
fn count_terms(body: &str, terms: Vec<String>) -> (u32, Vec<u32>) {
    let term_refs: Vec<&str> = terms.iter().map(String::as_str).collect();
    let mut chars = Vec::new();
    let mut scratch = String::new();
    kernel::count_terms(body, &term_refs, &mut chars, &mut scratch)
}

#[pymodule]
fn overlay_counts(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(overlay_postings, m)?)?;
    m.add_function(wrap_pyfunction!(count_terms, m)?)?;
    Ok(())
}
