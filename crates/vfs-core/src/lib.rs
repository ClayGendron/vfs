//! The vfs engine: byte-trigram extraction and posting-list building.
//!
//! This crate is the throughput core behind the vfs gram index. It holds no
//! policy: inputs are pre-folded, newline-normalized UTF-8 bytes prepared by
//! the host language, outputs are the exact posting-blob format the host's
//! reference implementation defines (a varint count header followed by LEB128
//! varints of strictly positive doc-id deltas). Every host binding — Python
//! today, JavaScript and native Rust surfaces later — talks to these types;
//! the `python` cargo feature adds the pyo3 module and nothing else.

mod grams;
mod postings;
mod verify;

#[cfg(feature = "python")]
mod python;

pub use grams::{GRAM_SIZE, GramExtractor};
pub use postings::{AddDocError, DrainedPostings, PostingRow, PostingsAccumulator};
pub use verify::{BatchOutcome, Hit, Matcher, PatternError, count_batch, hits_batch};
